//! SphinxVM: a deliberately synthetic target for relational-interrogation research.
//!
//! The crate keeps three concepts separate: architectural execution, fault-free
//! timing, and the injected faulty timing semantics. The public binary exposes only
//! the JSONL protocol defined in `spec/protocol.schema.json`.

pub mod architecture;
pub mod challenge;
pub mod fault;
pub mod isa;
pub mod judge;
pub mod machine;
pub mod mapping;
pub mod microarchitecture;
pub mod microcode;
pub mod noise;
mod parser;
pub mod profile;
pub mod protocol;
mod validate;

pub use architecture::{ArchitecturalState, Flags};
pub use isa::{Instruction, Program, ProgramError};
pub use machine::{ExecutionResult, Machine, ResetKind};
pub use profile::Profile;
pub use protocol::Server;
