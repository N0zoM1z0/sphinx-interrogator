//! Composition of independent architecture, microcode, fault, and noise semantics.

use crate::architecture::{ArchitecturalState, ArchitecturalStatus};
use crate::fault::{timing_delta, FaultVariant};
use crate::isa::Program;
use crate::mapping::BankMapping;
use crate::microarchitecture::{resolve_request, transition, MicroState};
use crate::microcode::{lower, VaultRequest};
use crate::noise::{sample, NoiseConfiguration, NoiseContext};
use crate::profile::Profile;

/// Reset mode selected by a public execute request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResetKind {
    /// Clear architectural and every hidden microarchitectural field.
    Hard,
    /// Clear architectural state and preserve exactly the public-profile subset.
    Soft,
    /// Preserve state and begin another program in the same session.
    None,
}

/// Optional public inputs supplied with an execution request.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PublicInput {
    /// Initial values for `r0..r7`; missing entries are unchanged after reset.
    pub registers: Vec<u16>,
    /// Sparse initial values for public 16-bit data memory.
    pub memory: Vec<(usize, u16)>,
}

/// Public request-schedule coordinates used only for deterministic noise derivation.
#[derive(Debug, Clone, Copy)]
pub struct ExecutionContext<'a> {
    /// Server-global one-based physical execution number.
    pub physical_execution: u64,
    /// Public session identifier.
    pub session_id: &'a str,
    /// Optional public execution-seed identifier.
    pub execution_seed_id: Option<&'a str>,
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
    /// Public fault-free static cycles of retired microcode.
    pub static_cycles: u64,
}

/// Private, validated machine parameters never implementing serialization.
#[derive(Debug, Clone)]
pub struct PrivateMachineConfig {
    mapping: BankMapping,
    fault_variant: FaultVariant,
    noise_key: [u8; 32],
}

impl PrivateMachineConfig {
    /// Construct validated runtime-private parameters.
    #[must_use]
    pub fn new(mapping: BankMapping, fault_variant: FaultVariant, noise_key: [u8; 32]) -> Self {
        Self {
            mapping,
            fault_variant,
            noise_key,
        }
    }

    /// Construct identity mapping and zero salts for deterministic System A tests.
    pub fn identity(
        secret: Vec<u8>,
        lanes: usize,
        fault_variant: FaultVariant,
        noise_key: [u8; 32],
    ) -> Result<Self, String> {
        Ok(Self::new(
            BankMapping::identity(secret, lanes)?,
            fault_variant,
            noise_key,
        ))
    }
}

/// Stateful SphinxVM session.
#[derive(Debug, Clone)]
pub struct Machine {
    profile: Profile,
    private: PrivateMachineConfig,
    architecture: ArchitecturalState,
    micro: MicroState,
}

impl Machine {
    /// Construct a session from strictly separated public and private configuration.
    pub fn new(profile: Profile, private: PrivateMachineConfig) -> Result<Self, String> {
        profile.validate().map_err(|error| error.to_string())?;
        if private.mapping.secret_cells() != profile.secret_cells {
            return Err(format!(
                "private mapping contains {} cells; profile requires {}",
                private.mapping.secret_cells(),
                profile.secret_cells
            ));
        }
        Ok(Self {
            profile,
            private,
            architecture: ArchitecturalState::default(),
            micro: MicroState::default(),
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
                self.micro = self.micro.soft_reset(&self.profile.soft_reset_preserves);
            }
        }
    }

    /// Execute one validated program and return only aggregate public observations.
    #[must_use]
    pub fn execute(
        &mut self,
        program: &Program,
        reset: ResetKind,
        input: &PublicInput,
        context: ExecutionContext<'_>,
    ) -> ExecutionResult {
        self.reset(reset);
        self.architecture.prepare_execution(self.profile.max_gas);
        for (index, value) in input.registers.iter().take(8).enumerate() {
            let _set_result = self.architecture.set_register(index, *value);
        }
        for (address, value) in &input.memory {
            let _set_result = self.architecture.set_memory(*address, *value);
        }

        let mut scheduled_static_cycles = 0_u64;
        let mut fault_cycles = 0_i64;
        while self.architecture.status() == ArchitecturalStatus::Running {
            let instruction = program.instructions().get(self.architecture.pc());
            let Some(instruction) = instruction else {
                let _step = self.architecture.step(program);
                continue;
            };
            let microprogram = lower(instruction);
            let step = self.architecture.step(program);
            if !step.retired {
                continue;
            }
            let static_cycles = microprogram.fault_free_cycles();
            scheduled_static_cycles = scheduled_static_cycles.saturating_add(static_cycles);
            let probe_bank = match microprogram.request() {
                Some(VaultRequest::Probe { lane, token, epoch }) => {
                    self.private.mapping.bank(lane, token, epoch)
                }
                _ => None,
            };
            let resolved = resolve_request(microprogram.request(), probe_bank);
            let hidden_transition = transition(&self.micro, resolved, microprogram.cache_tag());
            fault_cycles = fault_cycles.saturating_add(timing_delta(
                self.private.fault_variant,
                hidden_transition.fault_context,
            ));
            self.micro = hidden_transition.next;
        }

        debug_assert_eq!(scheduled_static_cycles, self.architecture.static_cycles());
        let jitter = sample(
            NoiseConfiguration {
                mode: self.profile.noise_mode,
                noise_bound: self.profile.noise_bound,
                outlier_probability: self.profile.outlier_probability,
                outlier_bound: self.profile.outlier_bound,
                private_key: &self.private.noise_key,
            },
            NoiseContext {
                physical_execution: context.physical_execution,
                session_id: context.session_id,
                execution_seed_id: context.execution_seed_id,
            },
        );
        let concrete_cycles =
            saturating_add_signed(scheduled_static_cycles, fault_cycles.saturating_add(jitter));
        let cycle_bucket = concrete_cycles / self.profile.bucket_width;

        ExecutionResult {
            halted: self.architecture.status() == ArchitecturalStatus::Halted,
            public_digest: self.architecture.digest(),
            cycle_bucket,
            bucket_width: self.profile.bucket_width,
            retired_instructions: self.architecture.retired_instructions(),
            static_cycles: scheduled_static_cycles,
        }
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
pub(crate) fn evaluate_fault_free(
    program: &Program,
    input: &PublicInput,
    gas: u64,
) -> (ArchitecturalState, u64) {
    let mut architecture = ArchitecturalState::default();
    architecture.prepare_execution(gas);
    for (index, value) in input.registers.iter().take(8).enumerate() {
        let _set_result = architecture.set_register(index, *value);
    }
    for (address, value) in &input.memory {
        let _set_result = architecture.set_memory(*address, *value);
    }
    let mut cycles = 0_u64;
    while architecture.status() == ArchitecturalStatus::Running {
        let microprogram = program.instructions().get(architecture.pc()).map(lower);
        let step = architecture.step(program);
        if step.retired {
            if let Some(microprogram) = microprogram {
                cycles = cycles.saturating_add(microprogram.fault_free_cycles());
            }
        }
    }
    (architecture, cycles)
}

#[cfg(test)]
mod tests {
    use crate::architecture::ArchitecturalState;
    use crate::fault::FaultVariant;
    use crate::isa::Program;
    use crate::microarchitecture::MicroStateField;
    use crate::noise::NoiseMode;
    use crate::profile::Profile;

    use super::{
        evaluate_fault_free, ExecutionContext, Machine, PrivateMachineConfig, PublicInput,
        ResetKind,
    };

    const NOISE_KEY: [u8; 32] = [0x42; 32];

    fn tutorial_profile() -> Profile {
        Profile {
            profile_version: "1.0".to_owned(),
            name: "tutorial".to_owned(),
            semantic_version: "0.1.0".to_owned(),
            lanes: 4,
            secret_cells: 4,
            hidden_permutation: false,
            hidden_salts: false,
            bucket_width: 1,
            noise_mode: NoiseMode::None,
            noise_bound: 0,
            outlier_probability: 0.0,
            outlier_bound: 0,
            soft_reset_preserves: Vec::new(),
            hard_reset_budget: 100,
            logical_query_budget: 100,
            physical_execution_budget: 100,
            max_program_instructions: 128,
            max_gas: 4096,
        }
    }

    fn private(secret: Vec<u8>, variant: FaultVariant) -> Result<PrivateMachineConfig, String> {
        PrivateMachineConfig::identity(secret, 4, variant, NOISE_KEY)
    }

    fn context(physical_execution: u64) -> ExecutionContext<'static> {
        ExecutionContext {
            physical_execution,
            session_id: "test-session",
            execution_seed_id: Some("test-seed"),
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
        let first_config = match private(vec![0, 1, 2, 3], FaultVariant::Reference) {
            Ok(value) => value,
            Err(error) => panic!("first private config failed: {error}"),
        };
        let second_config = match private(vec![15, 14, 13, 12], FaultVariant::Off) {
            Ok(value) => value,
            Err(error) => panic!("second private config failed: {error}"),
        };
        let first_machine = Machine::new(profile.clone(), first_config);
        let second_machine = Machine::new(profile, second_config);
        let mut first = match first_machine {
            Ok(value) => value,
            Err(error) => panic!("first machine construction failed: {error}"),
        };
        let mut second = match second_machine {
            Ok(value) => value,
            Err(error) => panic!("second machine construction failed: {error}"),
        };
        let left = first.execute(
            &program,
            ResetKind::Hard,
            &PublicInput::default(),
            context(1),
        );
        let right = second.execute(
            &program,
            ResetKind::Hard,
            &PublicInput::default(),
            context(1),
        );
        assert_eq!(first.architecture, second.architecture);
        assert_eq!(left.public_digest, right.public_digest);
        assert_eq!(left.static_cycles, right.static_cycles);
    }

    #[test]
    fn fault_free_evaluator_matches_public_static_schedule() {
        let parsed = Program::parse(
            "PROBE 0, 0, 0\nANCHOR 1, 0\nPAD 2\nFENCE\nHALT\n",
            4,
            128,
            4096,
        );
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("test program did not parse: {error}"),
        };
        let (architecture, cycles) = evaluate_fault_free(&program, &PublicInput::default(), 4096);
        assert_eq!(cycles, 14);
        assert_eq!(cycles, architecture.static_cycles());
    }

    #[test]
    fn off_variant_removes_secret_timing_delta() {
        let profile = tutorial_profile();
        let parsed = Program::parse("PROBE 0, 0, 0\nANCHOR 2, 0\nHALT\n", 4, 128, 4096);
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("test program did not parse: {error}"),
        };
        let config = match private(vec![0, 1, 2, 3], FaultVariant::Off) {
            Ok(value) => value,
            Err(error) => panic!("private config failed: {error}"),
        };
        let machine = Machine::new(profile, config);
        let mut vm = match machine {
            Ok(value) => value,
            Err(error) => panic!("machine construction failed: {error}"),
        };
        let result = vm.execute(
            &program,
            ResetKind::Hard,
            &PublicInput::default(),
            context(1),
        );
        assert_eq!(result.cycle_bucket, result.static_cycles);
    }

    #[test]
    fn mutation_ladder_changes_observation_but_not_machine_architecture() {
        let profile = tutorial_profile();
        let parsed = Program::parse(
            "PROBE 0, 0, 0\nANCHOR 2, 0\nPAD 3\nPROBE 0, 0, 0\nANCHOR 2, 0\nPAD 3\nPROBE 0, 0, 0\nANCHOR 0, 0\nHALT\n",
            4,
            128,
            4096,
        );
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("mutation-ladder program failed: {error}"),
        };
        let mut reference_architecture: Option<ArchitecturalState> = None;
        for (variant, expected_delta) in [
            (FaultVariant::Off, 0),
            (FaultVariant::Reference, 2),
            (FaultVariant::Weak, 1),
            (FaultVariant::Signed, 1),
        ] {
            let config = match private(vec![0, 1, 2, 3], variant) {
                Ok(value) => value,
                Err(error) => panic!("private mutation config failed: {error}"),
            };
            let mut machine = match Machine::new(profile.clone(), config) {
                Ok(value) => value,
                Err(error) => panic!("mutation machine failed: {error}"),
            };
            let result = machine.execute(
                &program,
                ResetKind::Hard,
                &PublicInput::default(),
                context(1),
            );
            assert_eq!(result.cycle_bucket - result.static_cycles, expected_delta);
            if let Some(expected) = &reference_architecture {
                assert_eq!(&machine.architecture, expected);
            } else {
                reference_architecture = Some(machine.architecture.clone());
            }
        }
    }

    #[test]
    fn fault_free_cost_is_secret_independent_over_all_reduced_cells() {
        let profile = tutorial_profile();
        for secret_cell in 0..=15 {
            for token in 0..=15 {
                for epoch in 0..=1 {
                    for anchor in 0..=3 {
                        let source =
                            format!("PROBE 0, {token}, {epoch}\nANCHOR {anchor}, {epoch}\nHALT\n");
                        let program = match Program::parse(&source, 4, 8, 128) {
                            Ok(value) => value,
                            Err(error) => panic!("reduced cell failed to parse: {error}"),
                        };
                        let config = match private(vec![secret_cell, 0, 0, 0], FaultVariant::Off) {
                            Ok(value) => value,
                            Err(error) => panic!("reduced private config failed: {error}"),
                        };
                        let mut machine = match Machine::new(profile.clone(), config) {
                            Ok(value) => value,
                            Err(error) => panic!("reduced machine failed: {error}"),
                        };
                        let result = machine.execute(
                            &program,
                            ResetKind::Hard,
                            &PublicInput::default(),
                            context(1),
                        );
                        assert_eq!(result.static_cycles, 10);
                        assert_eq!(result.cycle_bucket, result.static_cycles);
                    }
                }
            }
        }
    }

    #[test]
    fn soft_reset_preserves_only_profile_declared_hidden_state() {
        let mut profile = tutorial_profile();
        profile.soft_reset_preserves = vec![
            MicroStateField::Phase,
            MicroStateField::ReplayCredit,
            MicroStateField::UopCache,
        ];
        let config = match private(vec![0, 1, 2, 3], FaultVariant::Reference) {
            Ok(value) => value,
            Err(error) => panic!("private config failed: {error}"),
        };
        let machine = Machine::new(profile, config);
        let mut vm = match machine {
            Ok(value) => value,
            Err(error) => panic!("machine construction failed: {error}"),
        };
        let populate = Program::parse("PROBE 0, 0, 0\nANCHOR 2, 0\nHALT\n", 4, 16, 128);
        let populate = match populate {
            Ok(value) => value,
            Err(error) => panic!("populate program failed: {error}"),
        };
        let _first = vm.execute(
            &populate,
            ResetKind::Hard,
            &PublicInput::default(),
            context(1),
        );
        let before = vm.micro.clone();
        vm.reset(ResetKind::Soft);
        assert_eq!(vm.micro.phase(), before.phase());
        assert_eq!(vm.micro.replay_credit(), before.replay_credit());
        assert_eq!(vm.micro.uop_cache(), before.uop_cache());
        assert_eq!(vm.micro.last_bank(), None);
        assert_eq!(vm.architecture.registers(), &[0; 8]);
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
                let config = match private(secret.clone(), FaultVariant::Reference) {
                    Ok(value) => value,
                    Err(error) => panic!("generated private config failed: {error}"),
                };
                let machine = Machine::new(profile.clone(), config);
                let mut machine = match machine {
                    Ok(value) => value,
                    Err(error) => panic!("generated machine should construct: {error}"),
                };
                let _result = machine.execute(
                    &program,
                    ResetKind::Hard,
                    &PublicInput::default(),
                    context(1),
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
