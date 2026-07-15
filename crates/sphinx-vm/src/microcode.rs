//! Explicit public micro-op lowering and fault-free scheduling costs.

use crate::isa::Instruction;

/// A public experiment request encoded by one lowered instruction.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VaultRequest {
    /// Secret-indexed vault read.
    Probe { lane: usize, token: u8, epoch: u8 },
    /// Public reference-bank read.
    Anchor { bank: u8, epoch: u8 },
    /// Public phase advance.
    Pad { amount: u16 },
    /// Replay-state drain.
    Fence,
}

/// One explicit in-order micro-operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MicroOp {
    /// Decode an ordinary instruction or vault request.
    Decode,
    /// Execute a register/flag/control/digest operation.
    Execute,
    /// Calculate a public architectural data-memory address.
    Address,
    /// Access public architectural data memory.
    DataMemory,
    /// Calculate a private vault index through the documented mapping family.
    VaultIndex,
    /// Read one private synthetic vault bank.
    VaultRead,
    /// Read one public synthetic anchor bank.
    PublicBankRead,
    /// Discard the vault value without an architectural data effect.
    MixDiscard,
    /// Advance the hidden phase by a public amount.
    PhaseStep { amount: u16 },
    /// Drain the hidden replay pipeline.
    DrainReplay,
    /// Retire the architectural instruction.
    Retire { cycles: u8 },
}

impl MicroOp {
    /// Return the normalized public fault-free cost of this micro-op.
    #[must_use]
    pub fn fault_free_cycles(self) -> u64 {
        match self {
            Self::PhaseStep { amount } => u64::from(amount),
            Self::Retire { cycles } => u64::from(cycles),
            Self::Decode
            | Self::Execute
            | Self::Address
            | Self::DataMemory
            | Self::VaultIndex
            | Self::VaultRead
            | Self::PublicBankRead
            | Self::MixDiscard
            | Self::DrainReplay => 1,
        }
    }
}

/// Fully lowered instruction with a public cache tag and optional vault request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MicroProgram {
    operations: Vec<MicroOp>,
    request: Option<VaultRequest>,
    cache_tag: u8,
}

impl MicroProgram {
    /// Borrow the explicit micro-op sequence.
    #[must_use]
    pub fn operations(&self) -> &[MicroOp] {
        &self.operations
    }

    /// Return the experiment request, if this is an experiment instruction.
    #[must_use]
    pub fn request(&self) -> Option<VaultRequest> {
        self.request
    }

    /// Return a public four-bit micro-op cache tag.
    #[must_use]
    pub fn cache_tag(&self) -> u8 {
        self.cache_tag
    }

    /// Return the normalized, secret-independent scheduler cost.
    #[must_use]
    pub fn fault_free_cycles(&self) -> u64 {
        self.operations
            .iter()
            .copied()
            .map(MicroOp::fault_free_cycles)
            .sum()
    }
}

/// Lower an instruction through the one public microcode table used by all variants.
#[must_use]
pub fn lower(instruction: &Instruction) -> MicroProgram {
    let (operations, request, cache_tag) = match instruction {
        Instruction::Load { .. } | Instruction::Store { .. } => (
            vec![
                MicroOp::Address,
                MicroOp::DataMemory,
                MicroOp::Retire { cycles: 1 },
            ],
            None,
            0x8,
        ),
        Instruction::Add { .. }
        | Instruction::Xor { .. }
        | Instruction::And { .. }
        | Instruction::Or { .. }
        | Instruction::Shl { .. }
        | Instruction::Shr { .. } => (
            vec![MicroOp::Execute, MicroOp::Retire { cycles: 1 }],
            None,
            0x3,
        ),
        Instruction::Probe { lane, token, epoch } => (
            vec![
                MicroOp::Decode,
                MicroOp::VaultIndex,
                MicroOp::VaultRead,
                MicroOp::MixDiscard,
                MicroOp::Retire { cycles: 1 },
            ],
            Some(VaultRequest::Probe {
                lane: *lane,
                token: *token,
                epoch: *epoch,
            }),
            0xc,
        ),
        Instruction::Anchor { bank, epoch } => (
            vec![
                MicroOp::Decode,
                MicroOp::PublicBankRead,
                MicroOp::MixDiscard,
                MicroOp::Retire { cycles: 1 },
            ],
            Some(VaultRequest::Anchor {
                bank: *bank,
                epoch: *epoch,
            }),
            0xd,
        ),
        Instruction::Pad { amount } => (
            vec![
                MicroOp::PhaseStep { amount: *amount },
                MicroOp::Retire { cycles: 0 },
            ],
            Some(VaultRequest::Pad { amount: *amount }),
            0xe,
        ),
        Instruction::Fence => (
            vec![MicroOp::DrainReplay, MicroOp::Retire { cycles: 1 }],
            Some(VaultRequest::Fence),
            0xf,
        ),
        instruction => (
            vec![MicroOp::Retire { cycles: 1 }],
            None,
            ordinary_cache_tag(instruction),
        ),
    };
    MicroProgram {
        operations,
        request,
        cache_tag,
    }
}

fn ordinary_cache_tag(instruction: &Instruction) -> u8 {
    match instruction {
        Instruction::MovI { .. } => 0x0,
        Instruction::Mov { .. } => 0x1,
        Instruction::Cmp { .. } => 0x2,
        Instruction::Jmp { .. } | Instruction::Jz { .. } | Instruction::Jnz { .. } => 0x4,
        Instruction::Call { .. } | Instruction::Ret => 0x5,
        Instruction::Loop { .. } => 0x6,
        Instruction::MixOut { .. } => 0x7,
        Instruction::Halt => 0xb,
        _ => 0xa,
    }
}

#[cfg(test)]
mod tests {
    use crate::isa::{Instruction, Program};

    use super::lower;

    #[test]
    fn every_instruction_lowers_to_its_documented_static_cost() {
        let source = include_str!("../../../tests/fixtures/programs/full-v1.canonical.spx");
        let parsed = Program::parse(source, 4, 128, 4096);
        let program = match parsed {
            Ok(value) => value,
            Err(error) => panic!("golden program should validate: {error}"),
        };
        for instruction in program.instructions() {
            let microprogram = lower(instruction);
            assert!(!microprogram.operations().is_empty());
            assert_eq!(
                microprogram.fault_free_cycles(),
                instruction.static_cycles()
            );
            assert!(microprogram.cache_tag() <= 0x0f);
        }
        let pad_zero = lower(&Instruction::Pad { amount: 0 });
        assert_eq!(pad_zero.fault_free_cycles(), 0);
    }
}
