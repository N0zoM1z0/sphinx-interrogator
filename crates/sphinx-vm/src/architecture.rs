//! Pure architectural state and small-step semantics.

use std::collections::BTreeMap;

use crate::isa::{Instruction, Program};

/// Number of 16-bit general-purpose registers.
pub const REGISTER_COUNT: usize = 8;
/// Number of 16-bit data-memory words.
pub const MEMORY_WORDS: usize = 256;
const RETURN_STACK_LIMIT: usize = 16;

/// Public arithmetic flags.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Flags {
    /// Result is zero.
    pub zero: bool,
    /// Most-significant result bit is set.
    pub negative: bool,
    /// Unsigned carry/no-borrow bit.
    pub carry: bool,
    /// Signed overflow bit.
    pub overflow: bool,
}

/// Public execution status.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum ArchitecturalStatus {
    /// The current program can retire another instruction.
    #[default]
    Running,
    /// `HALT` retired.
    Halted,
    /// The next instruction could not retire within the public gas budget.
    GasExhausted,
}

/// Architecturally silent event made available to the microarchitecture layer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExperimentEvent {
    /// A secret-indexed vault request.
    Probe { lane: usize, token: u8, epoch: u8 },
    /// A public reference-bank request.
    Anchor { bank: u8, epoch: u8 },
    /// A public phase step.
    Pad { amount: u16 },
    /// A public replay drain.
    Fence,
}

/// Result of one attempted architectural step.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StepResult {
    /// Event for the independent microarchitecture, if any.
    pub experiment: Option<ExperimentEvent>,
    /// Whether an instruction retired.
    pub retired: bool,
}

/// Complete programmer-visible state plus bounded execution control.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArchitecturalState {
    registers: [u16; REGISTER_COUNT],
    flags: Flags,
    memory: [u16; MEMORY_WORDS],
    digest: u64,
    pc: usize,
    return_stack: Vec<usize>,
    loop_remaining: BTreeMap<usize, u16>,
    status: ArchitecturalStatus,
    gas_remaining: u64,
    gas_used: u64,
    retired_instructions: u64,
    static_cycles: u64,
}

impl Default for ArchitecturalState {
    fn default() -> Self {
        Self {
            registers: [0; REGISTER_COUNT],
            flags: Flags::default(),
            memory: [0; MEMORY_WORDS],
            digest: 0,
            pc: 0,
            return_stack: Vec::new(),
            loop_remaining: BTreeMap::new(),
            status: ArchitecturalStatus::Running,
            gas_remaining: 0,
            gas_used: 0,
            retired_instructions: 0,
            static_cycles: 0,
        }
    }
}

impl ArchitecturalState {
    /// Reset transient execution control while preserving architectural data.
    pub fn prepare_execution(&mut self, gas_limit: u64) {
        self.pc = 0;
        self.return_stack.clear();
        self.loop_remaining.clear();
        self.status = ArchitecturalStatus::Running;
        self.gas_remaining = gas_limit;
        self.gas_used = 0;
        self.retired_instructions = 0;
        self.static_cycles = 0;
    }

    /// Replace the entire architectural state and prepare a new program.
    pub fn hard_reset(&mut self, gas_limit: u64) {
        *self = Self::default();
        self.prepare_execution(gas_limit);
    }

    /// Set one initial public register.
    pub fn set_register(&mut self, index: usize, value: u16) -> Result<(), &'static str> {
        let register = self
            .registers
            .get_mut(index)
            .ok_or("register index is outside 0..8")?;
        *register = value;
        Ok(())
    }

    /// Set one initial public memory word.
    pub fn set_memory(&mut self, address: usize, value: u16) -> Result<(), &'static str> {
        let word = self
            .memory
            .get_mut(address)
            .ok_or("memory address is outside 0..256")?;
        *word = value;
        Ok(())
    }

    /// Borrow all public registers.
    #[must_use]
    pub fn registers(&self) -> &[u16; REGISTER_COUNT] {
        &self.registers
    }

    /// Return the public flags.
    #[must_use]
    pub fn flags(&self) -> Flags {
        self.flags
    }

    /// Borrow public data memory.
    #[must_use]
    pub fn memory(&self) -> &[u16; MEMORY_WORDS] {
        &self.memory
    }

    /// Return the public digest.
    #[must_use]
    pub fn digest(&self) -> u64 {
        self.digest
    }

    /// Return the next program counter.
    #[must_use]
    pub fn pc(&self) -> usize {
        self.pc
    }

    /// Return the current public status.
    #[must_use]
    pub fn status(&self) -> ArchitecturalStatus {
        self.status
    }

    /// Return gas charged during the current execution.
    #[must_use]
    pub fn gas_used(&self) -> u64 {
        self.gas_used
    }

    /// Return retired instructions in the current execution.
    #[must_use]
    pub fn retired_instructions(&self) -> u64 {
        self.retired_instructions
    }

    /// Return accumulated public fault-free static cycles.
    #[must_use]
    pub fn static_cycles(&self) -> u64 {
        self.static_cycles
    }

    /// Execute one pure architectural step.
    pub fn step(&mut self, program: &Program) -> StepResult {
        if self.status != ArchitecturalStatus::Running {
            return StepResult {
                experiment: None,
                retired: false,
            };
        }
        let Some(instruction) = program.instructions().get(self.pc) else {
            self.status = ArchitecturalStatus::Halted;
            return StepResult {
                experiment: None,
                retired: false,
            };
        };
        let gas = instruction.gas_cost();
        if gas > self.gas_remaining {
            self.status = ArchitecturalStatus::GasExhausted;
            return StepResult {
                experiment: None,
                retired: false,
            };
        }
        self.gas_remaining -= gas;
        self.gas_used = self.gas_used.saturating_add(gas);
        self.static_cycles = self
            .static_cycles
            .saturating_add(instruction.static_cycles());
        self.retired_instructions = self.retired_instructions.saturating_add(1);

        let current_pc = self.pc;
        self.pc = self.pc.saturating_add(1);
        let experiment = self.execute_instruction(current_pc, instruction);
        StepResult {
            experiment,
            retired: true,
        }
    }

    fn execute_instruction(
        &mut self,
        current_pc: usize,
        instruction: &Instruction,
    ) -> Option<ExperimentEvent> {
        match instruction {
            Instruction::MovI { dst, value } => self.registers[usize::from(*dst)] = *value,
            Instruction::Mov { dst, src } => {
                self.registers[usize::from(*dst)] = self.registers[usize::from(*src)];
            }
            Instruction::Add { dst, lhs, rhs } => {
                let left = self.registers[usize::from(*lhs)];
                let right = self.registers[usize::from(*rhs)];
                let (result, carry) = left.overflowing_add(right);
                self.registers[usize::from(*dst)] = result;
                self.flags = Flags {
                    zero: result == 0,
                    negative: result & 0x8000 != 0,
                    carry,
                    overflow: ((left ^ result) & (right ^ result) & 0x8000) != 0,
                };
            }
            Instruction::Xor { dst, lhs, rhs } => {
                let result = self.registers[usize::from(*lhs)] ^ self.registers[usize::from(*rhs)];
                self.registers[usize::from(*dst)] = result;
                self.set_logic_flags(result);
            }
            Instruction::And { dst, lhs, rhs } => {
                let result = self.registers[usize::from(*lhs)] & self.registers[usize::from(*rhs)];
                self.registers[usize::from(*dst)] = result;
                self.set_logic_flags(result);
            }
            Instruction::Or { dst, lhs, rhs } => {
                let result = self.registers[usize::from(*lhs)] | self.registers[usize::from(*rhs)];
                self.registers[usize::from(*dst)] = result;
                self.set_logic_flags(result);
            }
            Instruction::Shl { dst, src, amount } => {
                let value = self.registers[usize::from(*src)];
                let result = value << *amount;
                self.registers[usize::from(*dst)] = result;
                self.flags = Flags {
                    zero: result == 0,
                    negative: result & 0x8000 != 0,
                    carry: *amount != 0 && (value >> (16 - *amount)) & 1 != 0,
                    overflow: false,
                };
            }
            Instruction::Shr { dst, src, amount } => {
                let value = self.registers[usize::from(*src)];
                let result = value >> *amount;
                self.registers[usize::from(*dst)] = result;
                self.flags = Flags {
                    zero: result == 0,
                    negative: result & 0x8000 != 0,
                    carry: *amount != 0 && (value >> (*amount - 1)) & 1 != 0,
                    overflow: false,
                };
            }
            Instruction::Load { dst, base, offset } => {
                let address = effective_address(self.registers[usize::from(*base)], *offset);
                self.registers[usize::from(*dst)] = self.memory[address];
            }
            Instruction::Store { base, offset, src } => {
                let address = effective_address(self.registers[usize::from(*base)], *offset);
                self.memory[address] = self.registers[usize::from(*src)];
            }
            Instruction::Cmp { lhs, rhs } => {
                let left = self.registers[usize::from(*lhs)];
                let right = self.registers[usize::from(*rhs)];
                let result = left.wrapping_sub(right);
                self.flags = Flags {
                    zero: result == 0,
                    negative: result & 0x8000 != 0,
                    carry: left >= right,
                    overflow: ((left ^ right) & (left ^ result) & 0x8000) != 0,
                };
            }
            Instruction::Jmp { target } => self.pc = *target,
            Instruction::Jz { target } => {
                if self.flags.zero {
                    self.pc = *target;
                }
            }
            Instruction::Jnz { target } => {
                if !self.flags.zero {
                    self.pc = *target;
                }
            }
            Instruction::Call { target } => {
                if self.return_stack.len() < RETURN_STACK_LIMIT {
                    self.return_stack.push(self.pc);
                    self.pc = *target;
                } else {
                    self.status = ArchitecturalStatus::GasExhausted;
                }
            }
            Instruction::Ret => {
                if let Some(target) = self.return_stack.pop() {
                    self.pc = target;
                } else {
                    self.status = ArchitecturalStatus::GasExhausted;
                }
            }
            Instruction::Loop { count, target } => {
                let remaining = self
                    .loop_remaining
                    .get(&current_pc)
                    .copied()
                    .unwrap_or(*count);
                if remaining > 0 {
                    self.loop_remaining.insert(current_pc, remaining - 1);
                    self.pc = *target;
                } else {
                    self.loop_remaining.remove(&current_pc);
                }
            }
            Instruction::MixOut { src } => {
                self.digest = mix_digest(self.digest, self.registers[usize::from(*src)]);
            }
            Instruction::Probe { lane, token, epoch } => {
                return Some(ExperimentEvent::Probe {
                    lane: *lane,
                    token: *token,
                    epoch: *epoch,
                });
            }
            Instruction::Anchor { bank, epoch } => {
                return Some(ExperimentEvent::Anchor {
                    bank: *bank,
                    epoch: *epoch,
                });
            }
            Instruction::Pad { amount } => {
                return Some(ExperimentEvent::Pad { amount: *amount });
            }
            Instruction::Fence => return Some(ExperimentEvent::Fence),
            Instruction::Halt => self.status = ArchitecturalStatus::Halted,
        }
        None
    }

    fn set_logic_flags(&mut self, result: u16) {
        self.flags = Flags {
            zero: result == 0,
            negative: result & 0x8000 != 0,
            carry: false,
            overflow: false,
        };
    }
}

fn effective_address(base: u16, offset: i16) -> usize {
    (i32::from(base) + i32::from(offset)).rem_euclid(MEMORY_WORDS as i32) as usize
}

fn mix_digest(digest: u64, value: u16) -> u64 {
    let mixed = digest ^ u64::from(value);
    mixed.wrapping_mul(0x0000_0100_0000_01b3)
}

#[cfg(test)]
mod tests {
    use super::{ArchitecturalState, ArchitecturalStatus};
    use crate::isa::Program;

    fn run(source: &str, gas: u64) -> ArchitecturalState {
        let program = match Program::parse(source, 4, 128, gas) {
            Ok(value) => value,
            Err(error) => panic!("test program should validate: {error}"),
        };
        let mut state = ArchitecturalState::default();
        state.hard_reset(gas);
        while state.status() == ArchitecturalStatus::Running {
            state.step(&program);
        }
        state
    }

    #[test]
    fn executes_memory_flags_branches_calls_and_loops() {
        let state = run(
            r#"
                MOVI r0, 255
                MOVI r1, 7
                STORE [r0 + 2], r1
                LOAD r2, [r0 + 2]
                CMP r1, r2
                JNZ failed
                CALL mix
                JMP loop_body
                mix: MIXOUT r2
                RET
                loop_body: ADD r3, r3, r1
                LOOP 2, loop_body
                HALT
                failed: MOVI r3, 65535
                HALT
            "#,
            4096,
        );
        assert_eq!(state.status(), ArchitecturalStatus::Halted);
        assert_eq!(state.registers()[2], 7);
        assert_eq!(state.registers()[3], 21);
        assert_eq!(state.memory()[1], 7);
        assert!(!state.flags().zero);
        assert_ne!(state.digest(), 0);
    }

    #[test]
    fn experiment_instructions_preserve_architectural_data() {
        let mut state = ArchitecturalState::default();
        assert!(state.set_register(0, 0x1234).is_ok());
        assert!(state.set_memory(7, 0xabcd).is_ok());
        let before_registers = *state.registers();
        let before_memory = *state.memory();
        let before_flags = state.flags();
        let before_digest = state.digest();
        let parsed = Program::parse(
            "PROBE 0, 3, 1\nANCHOR 2, 1\nPAD 4\nFENCE\nHALT\n",
            4,
            16,
            64,
        );
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("experiment program should validate: {error}"),
        };
        state.prepare_execution(64);
        for _ in 0..4 {
            let step = state.step(&program);
            assert!(step.retired);
            assert!(step.experiment.is_some());
        }
        assert_eq!(*state.registers(), before_registers);
        assert_eq!(*state.memory(), before_memory);
        assert_eq!(state.flags(), before_flags);
        assert_eq!(state.digest(), before_digest);
    }

    #[test]
    fn gas_exhaustion_is_deterministic_and_does_not_retire_partial_step() {
        let source = "start: PAD 1\nLOOP 20, start\nHALT\n";
        let program = match Program::parse(source, 1, 8, 3) {
            Ok(value) => value,
            Err(error) => panic!("loop should be statically bounded: {error}"),
        };
        let mut state = ArchitecturalState::default();
        state.hard_reset(3);
        while state.status() == ArchitecturalStatus::Running {
            state.step(&program);
        }
        assert_eq!(state.status(), ArchitecturalStatus::GasExhausted);
        assert_eq!(state.gas_used(), 3);
        assert_eq!(state.retired_instructions(), 3);
    }

    #[test]
    fn arithmetic_logic_and_shift_flags_follow_documented_word_semantics() {
        let overflow = run("MOVI r0, 32767\nMOVI r1, 1\nADD r2, r0, r1\nHALT\n", 64);
        assert_eq!(overflow.registers()[2], 0x8000);
        assert_eq!(
            overflow.flags(),
            super::Flags {
                zero: false,
                negative: true,
                carry: false,
                overflow: true,
            }
        );

        let carry = run("MOVI r0, 65535\nMOVI r1, 1\nADD r2, r0, r1\nHALT\n", 64);
        assert_eq!(carry.registers()[2], 0);
        assert!(carry.flags().zero);
        assert!(carry.flags().carry);
        assert!(!carry.flags().overflow);

        let shift_left = run("MOVI r0, 32769\nSHL r1, r0, 1\nHALT\n", 64);
        assert_eq!(shift_left.registers()[1], 2);
        assert!(shift_left.flags().carry);
        let shift_right = run("MOVI r0, 1\nSHR r1, r0, 1\nHALT\n", 64);
        assert_eq!(shift_right.registers()[1], 0);
        assert!(shift_right.flags().zero);
        assert!(shift_right.flags().carry);

        let logic = run(
            "MOVI r0, 43690\nMOVI r1, 3855\nXOR r2, r0, r1\nAND r3, r0, r1\nOR r4, r0, r1\nMOV r5, r4\nHALT\n",
            64,
        );
        assert_eq!(logic.registers()[2], 0xa5a5);
        assert_eq!(logic.registers()[3], 0x0a0a);
        assert_eq!(logic.registers()[4], 0xafaf);
        assert_eq!(logic.registers()[5], 0xafaf);
        assert!(logic.flags().negative);
        assert!(!logic.flags().carry);
        assert!(!logic.flags().overflow);

        let comparison = run("MOVI r0, 32768\nMOVI r1, 1\nCMP r0, r1\nHALT\n", 64);
        assert_eq!(comparison.registers()[0], 0x8000);
        assert!(comparison.flags().carry);
        assert!(comparison.flags().overflow);
        assert!(!comparison.flags().negative);

        let taken = run(
            "MOVI r0, 1\nMOVI r1, 1\nCMP r0, r1\nJZ equal\nMOVI r7, 65535\nequal: HALT\n",
            64,
        );
        assert_eq!(taken.registers()[7], 0);
    }
}
