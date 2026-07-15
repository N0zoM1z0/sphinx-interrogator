//! Semantic and resource validation for resolved programs.

use std::collections::{HashSet, VecDeque};

use crate::isa::{Instruction, ProgramError};

const RETURN_STACK_LIMIT: usize = 16;
const MAX_ABSTRACT_STATES: usize = 65_536;

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct ControlState {
    pc: usize,
    returns: Vec<usize>,
}

pub(crate) fn validate_program(
    instructions: &[Instruction],
    lanes: usize,
    max_instructions: usize,
    _max_gas: u64,
) -> Result<(), ProgramError> {
    if lanes == 0 {
        return Err(ProgramError::Limit(
            "profile declares zero lanes".to_owned(),
        ));
    }
    if instructions.is_empty() {
        return Err(ProgramError::Limit("program is empty".to_owned()));
    }
    if instructions.len() > max_instructions {
        return Err(ProgramError::Limit(format!(
            "{} instructions exceed maximum {max_instructions}",
            instructions.len()
        )));
    }
    if !matches!(instructions.last(), Some(Instruction::Halt)) {
        return Err(ProgramError::Validation {
            instruction: instructions.len() - 1,
            message: "program must end with HALT".to_owned(),
        });
    }
    for (pc, instruction) in instructions.iter().enumerate() {
        validate_operands(pc, instruction, lanes)?;
        if let Some(target) = instruction.branch_target() {
            if target >= instructions.len() {
                return Err(validation(
                    pc,
                    format!("target {target} is outside the program"),
                ));
            }
        }
        match instruction {
            Instruction::Jmp { target }
            | Instruction::Jz { target }
            | Instruction::Jnz { target }
            | Instruction::Call { target }
                if *target <= pc =>
            {
                return Err(validation(
                    pc,
                    "backward control flow is allowed only through LOOP".to_owned(),
                ));
            }
            Instruction::Loop { target, .. } if *target > pc => {
                return Err(validation(pc, "LOOP target must not be forward".to_owned()));
            }
            _ => {}
        }
    }
    validate_control_flow(instructions)
}

fn validate_operands(
    pc: usize,
    instruction: &Instruction,
    lanes: usize,
) -> Result<(), ProgramError> {
    let registers: &[u8] = match instruction {
        Instruction::MovI { dst, .. } => std::slice::from_ref(dst),
        Instruction::Mov { dst, src } => &[*dst, *src],
        Instruction::Add { dst, lhs, rhs }
        | Instruction::Xor { dst, lhs, rhs }
        | Instruction::And { dst, lhs, rhs }
        | Instruction::Or { dst, lhs, rhs } => &[*dst, *lhs, *rhs],
        Instruction::Shl { dst, src, .. } | Instruction::Shr { dst, src, .. } => &[*dst, *src],
        Instruction::Load { dst, base, .. } => &[*dst, *base],
        Instruction::Store { base, src, .. } => &[*base, *src],
        Instruction::Cmp { lhs, rhs } => &[*lhs, *rhs],
        Instruction::MixOut { src } => std::slice::from_ref(src),
        _ => &[],
    };
    if let Some(register) = registers.iter().find(|register| **register >= 8) {
        return Err(validation(
            pc,
            format!("register r{register} is outside r0..r7"),
        ));
    }
    match instruction {
        Instruction::Shl { amount, .. } | Instruction::Shr { amount, .. } if *amount > 15 => {
            Err(validation(pc, format!("shift amount {amount} exceeds 15")))
        }
        Instruction::Probe { lane, .. } if *lane >= lanes => {
            Err(validation(pc, format!("lane {lane} is outside 0..{lanes}")))
        }
        Instruction::Probe { token, .. } if *token > 15 => {
            Err(validation(pc, format!("probe token {token} exceeds 15")))
        }
        Instruction::Probe { epoch, .. } | Instruction::Anchor { epoch, .. } if *epoch > 1 => {
            Err(validation(pc, format!("epoch {epoch} exceeds 1")))
        }
        Instruction::Anchor { bank, .. } if *bank > 3 => {
            Err(validation(pc, format!("anchor bank {bank} exceeds 3")))
        }
        _ => Ok(()),
    }
}

fn validate_control_flow(instructions: &[Instruction]) -> Result<(), ProgramError> {
    let mut pending = VecDeque::from([ControlState {
        pc: 0,
        returns: Vec::new(),
    }]);
    let mut visited = HashSet::new();
    while let Some(state) = pending.pop_front() {
        if !visited.insert(state.clone()) {
            continue;
        }
        if visited.len() > MAX_ABSTRACT_STATES {
            return Err(ProgramError::Limit(format!(
                "control-flow analysis exceeds {MAX_ABSTRACT_STATES} states"
            )));
        }
        let instruction = instructions.get(state.pc).ok_or_else(|| {
            validation(
                state.pc.saturating_sub(1),
                "reachable path falls off the program".to_owned(),
            )
        })?;
        let mut enqueue = |pc: usize, returns: Vec<usize>| -> Result<(), ProgramError> {
            if pc >= instructions.len() {
                return Err(validation(
                    state.pc,
                    "reachable path falls off the program".to_owned(),
                ));
            }
            pending.push_back(ControlState { pc, returns });
            Ok(())
        };
        match instruction {
            Instruction::Halt => {}
            Instruction::Jmp { target } => enqueue(*target, state.returns)?,
            Instruction::Jz { target } | Instruction::Jnz { target } => {
                enqueue(*target, state.returns.clone())?;
                enqueue(state.pc + 1, state.returns)?;
            }
            Instruction::Call { target } => {
                if state.returns.len() >= RETURN_STACK_LIMIT {
                    return Err(validation(
                        state.pc,
                        "return stack may exceed 16 entries".to_owned(),
                    ));
                }
                let mut returns = state.returns;
                returns.push(state.pc + 1);
                enqueue(*target, returns)?;
            }
            Instruction::Ret => {
                let mut returns = state.returns;
                let target = returns.pop().ok_or_else(|| {
                    validation(
                        state.pc,
                        "RET is reachable with an empty return stack".to_owned(),
                    )
                })?;
                enqueue(target, returns)?;
            }
            Instruction::Loop { target, .. } => {
                enqueue(*target, state.returns.clone())?;
                enqueue(state.pc + 1, state.returns)?;
            }
            _ => enqueue(state.pc + 1, state.returns)?,
        }
    }
    Ok(())
}

fn validation(instruction: usize, message: String) -> ProgramError {
    ProgramError::Validation {
        instruction,
        message,
    }
}
