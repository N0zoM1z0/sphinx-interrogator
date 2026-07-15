//! SphinxVM: a deliberately synthetic target for relational-interrogation research.
//!
//! The crate keeps three concepts separate: architectural execution, fault-free
//! timing, and the injected faulty timing semantics. The public binary exposes only
//! the JSONL protocol defined in `spec/protocol.schema.json`.

pub mod architecture;
pub mod config;
pub mod isa;
pub mod machine;
mod parser;
pub mod protocol;
mod validate;

pub use architecture::{ArchitecturalState, Flags};
pub use config::Profile;
pub use isa::{Instruction, Program, ProgramError};
pub use machine::{ExecutionResult, Machine, ResetKind};
pub use protocol::Server;
