//! Concrete architectural and microarchitectural execution.

use crate::architecture::{ArchitecturalState, ArchitecturalStatus, ExperimentEvent};
use crate::config::Profile;
use crate::isa::Program;

/// Public S-box used by both the implementation and the solver specification.
pub const SBOX4: [u8; 16] = [6, 11, 0, 4, 13, 3, 15, 8, 10, 2, 5, 12, 1, 14, 7, 9];

/// Reset mode selected by a public execute request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResetKind {
    /// Clear architectural and all microarchitectural state.
    Hard,
    /// Clear architectural state and preserve only profile-declared hidden fields.
    Soft,
    /// Continue from the current session state.
    None,
}

/// Optional public inputs supplied with an execution request.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PublicInput {
    /// Initial values for `r0..r7`; missing entries are zero.
    pub registers: Vec<u16>,
    /// Sparse initial values for public 16-bit data memory.
    pub memory: Vec<(usize, u16)>,
}

/// Public execution result before protocol serialization.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecutionResult {
    /// Whether the program halted normally or exhausted gas.
    pub halted: bool,
    /// Secret-independent architectural output digest.
    pub public_digest: u64,
    /// Quantized aggregate cycle bucket.
    pub cycle_bucket: u64,
    /// Public bucket width used for quantization.
    pub bucket_width: u64,
    /// Number of retired instructions.
    pub retired_instructions: u64,
    /// Public fault-free static cycles of retired instructions.
    pub static_cycles: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ProbeEvent {
    bank: u8,
    epoch: u8,
    guard: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
struct MicroState {
    phase: u8,
    last_bank: Option<u8>,
    replay_credit: u8,
    pending_probe: Option<ProbeEvent>,
}

/// Stateful SphinxVM session.
#[derive(Debug, Clone)]
pub struct Machine {
    profile: Profile,
    secret: Vec<u8>,
    permutation: Vec<usize>,
    salts: Vec<u8>,
    architecture: ArchitecturalState,
    micro: MicroState,
    execution_counter: u64,
}

impl Machine {
    /// Construct a session from a public profile and private four-bit cells.
    ///
    /// Version-1 scaffold challenges use identity lane mapping and zero salts. The
    /// full task specification requires private challenge generation for research
    /// profiles; keeping those parameters explicit here prevents protocol leakage.
    pub fn new(profile: Profile, secret: Vec<u8>) -> Result<Self, String> {
        profile.validate().map_err(|error| error.to_string())?;
        if secret.len() != profile.secret_cells {
            return Err(format!(
                "secret contains {} cells; profile requires {}",
                secret.len(),
                profile.secret_cells
            ));
        }
        if secret.iter().any(|cell| *cell > 15) {
            return Err("every secret cell must fit in four bits".to_owned());
        }
        let permutation = (0..profile.lanes)
            .map(|lane| lane % profile.secret_cells)
            .collect();
        let salts = vec![0; profile.lanes];
        Ok(Self {
            profile,
            secret,
            permutation,
            salts,
            architecture: ArchitecturalState::default(),
            micro: MicroState::default(),
            execution_counter: 0,
        })
    }

    /// Return the public profile.
    #[must_use]
    pub fn profile(&self) -> &Profile {
        &self.profile
    }

    /// Apply the documented reset semantics.
    pub fn reset(&mut self, kind: ResetKind) {
        match kind {
            ResetKind::None => {}
            ResetKind::Hard => {
                self.architecture = ArchitecturalState::default();
                self.micro = MicroState::default();
            }
            ResetKind::Soft => {
                self.architecture = ArchitecturalState::default();
                let old = self.micro.clone();
                self.micro = MicroState {
                    phase: if self.profile.preserves_on_soft_reset("phase") {
                        old.phase
                    } else {
                        0
                    },
                    last_bank: if self.profile.preserves_on_soft_reset("last_bank") {
                        old.last_bank
                    } else {
                        None
                    },
                    replay_credit: if self.profile.preserves_on_soft_reset("replay_credit") {
                        old.replay_credit
                    } else {
                        0
                    },
                    pending_probe: None,
                };
            }
        }
    }

    /// Execute one validated program and return only public observations.
    #[must_use]
    pub fn execute(
        &mut self,
        program: &Program,
        reset: ResetKind,
        input: &PublicInput,
        execution_seed_id: Option<&str>,
    ) -> ExecutionResult {
        self.reset(reset);
        self.architecture.prepare_execution(self.profile.max_gas);
        for (index, value) in input.registers.iter().take(8).enumerate() {
            let _result = self.architecture.set_register(index, *value);
        }
        for (address, value) in &input.memory {
            let _result = self.architecture.set_memory(*address, *value);
        }

        let mut fault_cycles = 0_i64;
        while self.architecture.status() == ArchitecturalStatus::Running {
            let step = self.architecture.step(program);
            if let Some(event) = step.experiment {
                self.execute_experiment(event, &mut fault_cycles);
            }
        }

        let noise = self.sample_noise(execution_seed_id);
        let static_cycles = self.architecture.static_cycles();
        let concrete_cycles = saturating_add_signed(static_cycles, fault_cycles + noise);
        let cycle_bucket = concrete_cycles / self.profile.bucket_width;
        self.execution_counter = self.execution_counter.saturating_add(1);

        ExecutionResult {
            halted: self.architecture.status() == ArchitecturalStatus::Halted,
            public_digest: self.architecture.digest(),
            cycle_bucket,
            bucket_width: self.profile.bucket_width,
            retired_instructions: self.architecture.retired_instructions(),
            static_cycles,
        }
    }

    fn execute_experiment(&mut self, event: ExperimentEvent, fault_cycles: &mut i64) {
        match event {
            ExperimentEvent::Probe { lane, token, epoch } => {
                let bank = self.bank(lane, token, epoch);
                let lane_low = u8::try_from(lane & 0b11).unwrap_or_default();
                let guard_value = lane_low ^ token ^ epoch;
                let guard = self.micro.phase == (guard_value & 0b11);
                self.micro.pending_probe = Some(ProbeEvent { bank, epoch, guard });
                self.micro.phase = (self.micro.phase + 1 + epoch) & 0b11;
            }
            ExperimentEvent::Anchor { bank, epoch } => {
                if let Some(probe) = self.micro.pending_probe.take() {
                    if probe.epoch == epoch {
                        let collision = probe.bank == bank;
                        let suppress = self.micro.replay_credit == 0b11;
                        if self.profile.fault_mode == "reference"
                            && collision
                            && probe.guard
                            && !suppress
                        {
                            *fault_cycles += 1;
                        }
                        self.micro.replay_credit = if collision {
                            self.micro.replay_credit.saturating_add(1).min(3)
                        } else {
                            self.micro.replay_credit.saturating_sub(1)
                        };
                        self.micro.last_bank = Some(probe.bank);
                    }
                }
            }
            ExperimentEvent::Pad { amount } => {
                let phase_step = u8::try_from(amount & 0b11).unwrap_or_default();
                self.micro.phase = (self.micro.phase + phase_step) & 0b11;
            }
            ExperimentEvent::Fence => {
                self.micro.pending_probe = None;
                self.micro.replay_credit = 0;
            }
        }
    }

    fn bank(&self, lane: usize, token: u8, epoch: u8) -> u8 {
        let secret_index = self.permutation[lane];
        let input = self.secret[secret_index] ^ token ^ self.salts[lane];
        let value = SBOX4[usize::from(input)];
        (value >> (2 * epoch)) & 0b11
    }

    fn sample_noise(&self, execution_seed_id: Option<&str>) -> i64 {
        if self.profile.noise_mode == "none" || self.profile.noise_bound == 0 {
            return 0;
        }
        let mut hash = 0xcbf2_9ce4_8422_2325_u64 ^ self.execution_counter;
        if let Some(seed) = execution_seed_id {
            for byte in seed.as_bytes() {
                hash ^= u64::from(*byte);
                hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
            }
        }
        let bound = self.profile.noise_bound.unsigned_abs();
        let width = bound.saturating_mul(2).saturating_add(1);
        let sample = hash % width;
        i64::try_from(sample).unwrap_or_default() - self.profile.noise_bound
    }
}

fn saturating_add_signed(base: u64, delta: i64) -> u64 {
    if delta >= 0 {
        base.saturating_add(delta.unsigned_abs())
    } else {
        base.saturating_sub(delta.unsigned_abs())
    }
}

#[cfg(test)]
mod tests {
    use crate::architecture::ArchitecturalState;
    use crate::config::Profile;
    use crate::isa::Program;

    use super::{Machine, PublicInput, ResetKind};

    fn tutorial_profile() -> Profile {
        Profile {
            profile_version: "1.0".to_owned(),
            name: "tutorial".to_owned(),
            semantic_version: "0.1.0".to_owned(),
            lanes: 4,
            secret_cells: 4,
            hidden_permutation: false,
            hidden_salts: false,
            fault_mode: "reference".to_owned(),
            bucket_width: 1,
            noise_mode: "none".to_owned(),
            noise_bound: 0,
            outlier_probability: 0.0,
            outlier_bound: 0,
            soft_reset_preserves: Vec::new(),
            hard_reset_budget: 100,
            logical_query_budget: 100,
            physical_execution_budget: 100,
            max_program_instructions: 128,
            max_gas: 4096,
            server_diagnostics: false,
        }
    }

    #[test]
    fn complete_architecture_is_secret_and_fault_independent() {
        let profile = tutorial_profile();
        let parsed = Program::parse(
            "MOVI r0, 7\nMOVI r1, 12\nADD r2, r0, r1\nSTORE [r0 + 1], r2\nPROBE 0, 3, 1\nANCHOR 2, 1\nLOAD r3, [r0 + 1]\nCMP r2, r3\nMIXOUT r3\nFENCE\nHALT\n",
            4,
            128,
            4096,
        );
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("test program did not parse: {error}"),
        };
        let first_machine = Machine::new(profile.clone(), vec![0, 1, 2, 3]);
        let mut off_profile = profile;
        off_profile.fault_mode = "off".to_owned();
        let second_machine = Machine::new(off_profile, vec![15, 14, 13, 12]);
        let mut first = match first_machine {
            Ok(value) => value,
            Err(error) => panic!("first machine construction failed: {error}"),
        };
        let mut second = match second_machine {
            Ok(value) => value,
            Err(error) => panic!("second machine construction failed: {error}"),
        };
        let left = first.execute(&program, ResetKind::Hard, &PublicInput::default(), None);
        let right = second.execute(&program, ResetKind::Hard, &PublicInput::default(), None);
        assert_eq!(first.architecture, second.architecture);
        assert_eq!(left.public_digest, right.public_digest);
        assert_eq!(left.static_cycles, right.static_cycles);
    }

    #[test]
    fn fault_free_control_removes_secret_timing_delta() {
        let mut profile = tutorial_profile();
        profile.fault_mode = "off".to_owned();
        let parsed = Program::parse("PROBE 0, 0, 0\nANCHOR 1, 0\nHALT\n", 4, 128, 4096);
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("test program did not parse: {error}"),
        };
        let machine = Machine::new(profile, vec![0, 1, 2, 3]);
        let mut vm = match machine {
            Ok(value) => value,
            Err(error) => panic!("machine construction failed: {error}"),
        };
        let result = vm.execute(&program, ResetKind::Hard, &PublicInput::default(), None);
        assert_eq!(result.cycle_bucket, result.static_cycles);
    }

    #[test]
    fn generated_experiments_preserve_architecture_for_several_secrets() {
        let profile = tutorial_profile();
        let secrets = [
            vec![0, 0, 0, 0],
            vec![1, 5, 9, 13],
            vec![15, 14, 13, 12],
            vec![3, 7, 11, 15],
        ];
        for token in 0..=15 {
            let source = format!(
                "MOVI r0, {token}\nADD r1, r0, r0\nPROBE 0, {token}, 0\nANCHOR 1, 0\nMIXOUT r1\nHALT\n"
            );
            let parsed = Program::parse(&source, 4, 32, 4096);
            let program = match parsed {
                Ok(value) => value,
                Err(error) => panic!("generated program should validate: {error}"),
            };
            let mut reference: Option<ArchitecturalState> = None;
            for secret in &secrets {
                let machine = Machine::new(profile.clone(), secret.clone());
                let mut machine = match machine {
                    Ok(value) => value,
                    Err(error) => panic!("generated machine should construct: {error}"),
                };
                let _result = machine.execute(
                    &program,
                    ResetKind::Hard,
                    &PublicInput::default(),
                    Some("generated-noninterference"),
                );
                if let Some(expected) = &reference {
                    assert_eq!(&machine.architecture, expected);
                } else {
                    reference = Some(machine.architecture.clone());
                }
            }
        }
    }
}
