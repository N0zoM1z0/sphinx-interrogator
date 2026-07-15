//! Location-aware parser for the public probe DSL.

use std::collections::HashMap;

use crate::isa::{Instruction, ProgramError};

enum UnresolvedInstruction {
    Ready(Instruction),
    Jmp(String),
    Jz(String),
    Jnz(String),
    Call(String),
    Loop { count: u16, target: String },
}

struct UnresolvedLine {
    instruction: UnresolvedInstruction,
    source_line: usize,
}

pub(crate) fn parse_program(source: &str, lanes: usize) -> Result<Vec<Instruction>, ProgramError> {
    if lanes == 0 {
        return Err(ProgramError::Limit(
            "profile declares zero lanes".to_owned(),
        ));
    }
    let mut labels = HashMap::new();
    let mut unresolved = Vec::new();
    for (index, raw_line) in source.lines().enumerate() {
        let source_line = index + 1;
        let line = strip_comment(raw_line).trim();
        if line.is_empty() {
            continue;
        }
        let instruction_text = if let Some((candidate, rest)) = line.split_once(':') {
            let label = candidate.trim();
            if !is_identifier(label) {
                return Err(parse_error(source_line, format!("invalid label {label:?}")));
            }
            if labels.insert(label.to_owned(), unresolved.len()).is_some() {
                return Err(parse_error(source_line, format!("duplicate label {label}")));
            }
            rest.trim()
        } else {
            line
        };
        if instruction_text.is_empty() {
            continue;
        }
        unresolved.push(UnresolvedLine {
            instruction: parse_instruction(instruction_text, source_line, lanes)?,
            source_line,
        });
    }
    if unresolved.is_empty() {
        return Err(parse_error(1, "program contains no instruction".to_owned()));
    }

    unresolved
        .into_iter()
        .map(|line| resolve_instruction(line.instruction, line.source_line, &labels))
        .collect()
}

fn resolve_instruction(
    instruction: UnresolvedInstruction,
    line: usize,
    labels: &HashMap<String, usize>,
) -> Result<Instruction, ProgramError> {
    let target = |name: String| {
        labels
            .get(&name)
            .copied()
            .ok_or_else(|| parse_error(line, format!("unknown label {name}")))
    };
    match instruction {
        UnresolvedInstruction::Ready(value) => Ok(value),
        UnresolvedInstruction::Jmp(name) => Ok(Instruction::Jmp {
            target: target(name)?,
        }),
        UnresolvedInstruction::Jz(name) => Ok(Instruction::Jz {
            target: target(name)?,
        }),
        UnresolvedInstruction::Jnz(name) => Ok(Instruction::Jnz {
            target: target(name)?,
        }),
        UnresolvedInstruction::Call(name) => Ok(Instruction::Call {
            target: target(name)?,
        }),
        UnresolvedInstruction::Loop {
            count,
            target: name,
        } => Ok(Instruction::Loop {
            count,
            target: target(name)?,
        }),
    }
}

fn parse_instruction(
    source: &str,
    line: usize,
    lanes: usize,
) -> Result<UnresolvedInstruction, ProgramError> {
    let mut pieces = source.splitn(2, char::is_whitespace);
    let opcode = pieces.next().unwrap_or_default().to_ascii_uppercase();
    let operands = pieces.next().unwrap_or_default().trim();
    let args = split_operands(operands, line)?;
    let ready = |instruction| Ok(UnresolvedInstruction::Ready(instruction));

    match opcode.as_str() {
        "MOVI" => {
            require_arity(&args, 2, line, &opcode)?;
            ready(Instruction::MovI {
                dst: parse_register(args[0], line)?,
                value: parse_word(args[1], line)?,
            })
        }
        "MOV" => {
            require_arity(&args, 2, line, &opcode)?;
            ready(Instruction::Mov {
                dst: parse_register(args[0], line)?,
                src: parse_register(args[1], line)?,
            })
        }
        "ADD" | "XOR" | "AND" | "OR" => {
            require_arity(&args, 3, line, &opcode)?;
            let dst = parse_register(args[0], line)?;
            let lhs = parse_register(args[1], line)?;
            let rhs = parse_register(args[2], line)?;
            ready(match opcode.as_str() {
                "ADD" => Instruction::Add { dst, lhs, rhs },
                "XOR" => Instruction::Xor { dst, lhs, rhs },
                "AND" => Instruction::And { dst, lhs, rhs },
                _ => Instruction::Or { dst, lhs, rhs },
            })
        }
        "SHL" | "SHR" => {
            require_arity(&args, 3, line, &opcode)?;
            let dst = parse_register(args[0], line)?;
            let src = parse_register(args[1], line)?;
            let amount = parse_bounded_u8(args[2], line, "shift amount", 15)?;
            ready(if opcode == "SHL" {
                Instruction::Shl { dst, src, amount }
            } else {
                Instruction::Shr { dst, src, amount }
            })
        }
        "LOAD" => {
            require_arity(&args, 2, line, &opcode)?;
            let (base, offset) = parse_address(args[1], line)?;
            ready(Instruction::Load {
                dst: parse_register(args[0], line)?,
                base,
                offset,
            })
        }
        "STORE" => {
            require_arity(&args, 2, line, &opcode)?;
            let (base, offset) = parse_address(args[0], line)?;
            ready(Instruction::Store {
                base,
                offset,
                src: parse_register(args[1], line)?,
            })
        }
        "CMP" => {
            require_arity(&args, 2, line, &opcode)?;
            ready(Instruction::Cmp {
                lhs: parse_register(args[0], line)?,
                rhs: parse_register(args[1], line)?,
            })
        }
        "JMP" | "JZ" | "JNZ" | "CALL" => {
            require_arity(&args, 1, line, &opcode)?;
            if !is_identifier(args[0]) {
                return Err(parse_error(
                    line,
                    format!("invalid target label {}", args[0]),
                ));
            }
            let target = args[0].to_owned();
            Ok(match opcode.as_str() {
                "JMP" => UnresolvedInstruction::Jmp(target),
                "JZ" => UnresolvedInstruction::Jz(target),
                "JNZ" => UnresolvedInstruction::Jnz(target),
                _ => UnresolvedInstruction::Call(target),
            })
        }
        "RET" => {
            require_arity(&args, 0, line, &opcode)?;
            ready(Instruction::Ret)
        }
        "LOOP" => {
            require_arity(&args, 2, line, &opcode)?;
            if !is_identifier(args[1]) {
                return Err(parse_error(
                    line,
                    format!("invalid target label {}", args[1]),
                ));
            }
            Ok(UnresolvedInstruction::Loop {
                count: parse_u16(args[0], line, "loop count")?,
                target: args[1].to_owned(),
            })
        }
        "MIXOUT" => {
            require_arity(&args, 1, line, &opcode)?;
            ready(Instruction::MixOut {
                src: parse_register(args[0], line)?,
            })
        }
        "PROBE" => {
            require_arity(&args, 3, line, &opcode)?;
            let lane = parse_usize(args[0], line, "lane")?;
            if lane >= lanes {
                return Err(parse_error(
                    line,
                    format!("lane {lane} is outside 0..{lanes}"),
                ));
            }
            ready(Instruction::Probe {
                lane,
                token: parse_bounded_u8(args[1], line, "token", 15)?,
                epoch: parse_bounded_u8(args[2], line, "epoch", 1)?,
            })
        }
        "ANCHOR" => {
            require_arity(&args, 2, line, &opcode)?;
            ready(Instruction::Anchor {
                bank: parse_bounded_u8(args[0], line, "bank", 3)?,
                epoch: parse_bounded_u8(args[1], line, "epoch", 1)?,
            })
        }
        "PAD" => {
            require_arity(&args, 1, line, &opcode)?;
            ready(Instruction::Pad {
                amount: parse_u16(args[0], line, "padding")?,
            })
        }
        "FENCE" => {
            require_arity(&args, 0, line, &opcode)?;
            ready(Instruction::Fence)
        }
        "HALT" => {
            require_arity(&args, 0, line, &opcode)?;
            ready(Instruction::Halt)
        }
        _ => Err(parse_error(line, format!("unknown opcode {opcode}"))),
    }
}

fn split_operands(source: &str, line: usize) -> Result<Vec<&str>, ProgramError> {
    if source.is_empty() {
        return Ok(Vec::new());
    }
    let operands: Vec<&str> = source.split(',').map(str::trim).collect();
    if operands.iter().any(|operand| operand.is_empty()) {
        return Err(parse_error(line, "empty operand".to_owned()));
    }
    Ok(operands)
}

fn parse_address(value: &str, line: usize) -> Result<(u8, i16), ProgramError> {
    let inner = value
        .strip_prefix('[')
        .and_then(|rest| rest.strip_suffix(']'))
        .ok_or_else(|| parse_error(line, format!("invalid memory address {value}")))?
        .trim();
    let compact: String = inner
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect();
    let split = compact
        .char_indices()
        .skip(1)
        .find(|(_, character)| matches!(character, '+' | '-'));
    let (register, offset) = if let Some((index, sign)) = split {
        let register = &compact[..index];
        let magnitude = &compact[index + 1..];
        if magnitude.is_empty() || magnitude.starts_with('+') || magnitude.starts_with('-') {
            return Err(parse_error(line, format!("invalid memory offset {value}")));
        }
        let parsed = parse_integer(magnitude, line, "memory offset")?;
        let signed = if sign == '-' { -parsed } else { parsed };
        (register, parse_i16_value(signed, line, "memory offset")?)
    } else {
        (compact.as_str(), 0)
    };
    Ok((parse_register(register, line)?, offset))
}

fn require_arity(
    args: &[&str],
    expected: usize,
    line: usize,
    opcode: &str,
) -> Result<(), ProgramError> {
    if args.len() == expected {
        Ok(())
    } else {
        Err(parse_error(
            line,
            format!("{opcode} expects {expected} operands, got {}", args.len()),
        ))
    }
}

fn parse_register(value: &str, line: usize) -> Result<u8, ProgramError> {
    if value.len() != 2 {
        return Err(parse_error(line, format!("invalid register {value}")));
    }
    let index = value
        .strip_prefix('r')
        .or_else(|| value.strip_prefix('R'))
        .ok_or_else(|| parse_error(line, format!("invalid register {value}")))?;
    if !index.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(parse_error(line, format!("invalid register {value}")));
    }
    parse_bounded_u8(index, line, "register", 7)
}

fn parse_word(value: &str, line: usize) -> Result<u16, ProgramError> {
    let parsed = parse_integer(value, line, "immediate")?;
    if !(-32_768..=65_535).contains(&parsed) {
        return Err(parse_error(
            line,
            format!("immediate {value} is outside signed/unsigned 16-bit syntax"),
        ));
    }
    Ok(if parsed < 0 {
        (parsed as i16) as u16
    } else {
        parsed as u16
    })
}

fn parse_u16(value: &str, line: usize, role: &str) -> Result<u16, ProgramError> {
    let parsed = parse_integer(value, line, role)?;
    u16::try_from(parsed).map_err(|_| parse_error(line, format!("{role} {value} is not u16")))
}

fn parse_i16_value(value: i64, line: usize, role: &str) -> Result<i16, ProgramError> {
    i16::try_from(value).map_err(|_| parse_error(line, format!("{role} {value} is not i16")))
}

fn parse_usize(value: &str, line: usize, role: &str) -> Result<usize, ProgramError> {
    let parsed = parse_integer(value, line, role)?;
    usize::try_from(parsed)
        .map_err(|_| parse_error(line, format!("{role} {value} is not non-negative")))
}

fn parse_bounded_u8(value: &str, line: usize, role: &str, maximum: u8) -> Result<u8, ProgramError> {
    let parsed = parse_integer(value, line, role)?;
    let converted =
        u8::try_from(parsed).map_err(|_| parse_error(line, format!("{role} {value} is not u8")))?;
    if converted > maximum {
        return Err(parse_error(
            line,
            format!("{role} {converted} exceeds {maximum}"),
        ));
    }
    Ok(converted)
}

fn parse_integer(value: &str, line: usize, role: &str) -> Result<i64, ProgramError> {
    let (negative, magnitude) = value
        .strip_prefix('-')
        .map_or((false, value), |rest| (true, rest));
    if magnitude.is_empty() {
        return Err(parse_error(line, format!("invalid {role} {value}")));
    }
    let parsed = if let Some(hex) = magnitude
        .strip_prefix("0x")
        .or_else(|| magnitude.strip_prefix("0X"))
    {
        i64::from_str_radix(hex, 16)
    } else {
        magnitude.parse::<i64>()
    }
    .map_err(|_| parse_error(line, format!("invalid {role} {value}")))?;
    Ok(if negative { -parsed } else { parsed })
}

fn strip_comment(line: &str) -> &str {
    let hash = line.find('#');
    let semicolon = line.find(';');
    match (hash, semicolon) {
        (Some(left), Some(right)) => &line[..left.min(right)],
        (Some(index), None) | (None, Some(index)) => &line[..index],
        (None, None) => line,
    }
}

fn is_identifier(value: &str) -> bool {
    let mut characters = value.chars();
    matches!(characters.next(), Some(first) if first.is_ascii_alphabetic() || first == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

fn parse_error(line: usize, message: String) -> ProgramError {
    ProgramError::Parse {
        line,
        column: 1,
        message,
    }
}
