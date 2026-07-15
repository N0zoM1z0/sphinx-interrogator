//! Public JSON Lines protocol server.

use std::collections::{hash_map::Entry, HashMap};

use serde::Deserialize;
use serde_json::{json, Value};

use crate::config::Profile;
use crate::isa::Program;
use crate::machine::{Machine, PublicInput, ResetKind};

const PROTOCOL_VERSION: &str = "1.0";
const MAX_PROGRAM_BYTES: usize = 65_536;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ClientIdentity {
    name: String,
    version: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HelloRequest {
    protocol_version: String,
    request_id: String,
    kind: String,
    client: ClientIdentity,
}

#[derive(Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct WirePublicInput {
    #[serde(default)]
    registers: Vec<u16>,
    #[serde(default)]
    memory: HashMap<String, u16>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ExecuteRequest {
    protocol_version: String,
    request_id: String,
    kind: String,
    session_id: String,
    reset: String,
    program: String,
    #[serde(default)]
    public_input: WirePublicInput,
    logical_batch_id: String,
    execution_seed_id: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CloseRequest {
    protocol_version: String,
    request_id: String,
    kind: String,
}

enum ParsedRequest {
    Hello(HelloRequest),
    Execute(ExecuteRequest),
    Close(CloseRequest),
}

/// Stateful process-boundary server for one private challenge.
pub struct Server {
    profile: Profile,
    secret: Vec<u8>,
    sessions: HashMap<String, Machine>,
    physical_executions_used: u64,
}

impl Server {
    /// Construct a server from a public profile and private secret cells.
    pub fn new(profile: Profile, secret: Vec<u8>) -> Result<Self, String> {
        let _validation = Machine::new(profile.clone(), secret.clone())?;
        Ok(Self {
            profile,
            secret,
            sessions: HashMap::new(),
            physical_executions_used: 0,
        })
    }

    /// Parse one JSON request and return `(serialized_response, should_close)`.
    #[must_use]
    pub fn handle_line(&mut self, line: &str) -> (String, bool) {
        let value: Value = match serde_json::from_str(line) {
            Ok(value) => value,
            Err(error) => {
                return (
                    serialize_value(error_response(
                        "unknown",
                        "invalid_json",
                        format!("invalid JSON: {error}"),
                        true,
                    )),
                    false,
                );
            }
        };
        let request_id = value
            .get("request_id")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
            .to_owned();
        let request = match parse_request(value) {
            Ok(request) => request,
            Err(message) => {
                return (
                    serialize_value(error_response(
                        &request_id,
                        "schema_error",
                        message,
                        true,
                    )),
                    false,
                );
            }
        };
        match self.handle_request(request) {
            Ok((response, should_close)) => (serialize_value(response), should_close),
            Err((code, message, recoverable)) => (
                serialize_value(error_response(&request_id, code, message, recoverable)),
                false,
            ),
        }
    }

    fn handle_request(
        &mut self,
        request: ParsedRequest,
    ) -> Result<(Value, bool), (&'static str, String, bool)> {
        match request {
            ParsedRequest::Hello(request) => self.handle_hello(request),
            ParsedRequest::Execute(request) => self.handle_execute(request),
            ParsedRequest::Close(request) => self.handle_close(request),
        }
    }

    fn handle_hello(
        &self,
        request: HelloRequest,
    ) -> Result<(Value, bool), (&'static str, String, bool)> {
        check_version(&request.protocol_version)?;
        if request.kind != "hello" {
            return Err((
                "schema_error",
                "hello request has inconsistent kind".to_owned(),
                true,
            ));
        }
        if request.client.name.is_empty() || request.client.version.is_empty() {
            return Err((
                "schema_error",
                "client name and version must be non-empty".to_owned(),
                true,
            ));
        }
        Ok((
            json!({
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request.request_id,
                "kind": "hello_result",
                "ok": true,
                "server": {
                    "name": "sphinx-vm",
                    "version": env!("CARGO_PKG_VERSION"),
                    "build_id": "design-scaffold"
                },
                "profile": {
                    "name": self.profile.name,
                    "semantic_version": self.profile.semantic_version,
                    "bucket_width": self.profile.bucket_width,
                    "lanes": self.profile.lanes,
                    "hard_reset_available": self.profile.hard_reset_budget > 0
                },
                "limits": {
                    "max_program_bytes": MAX_PROGRAM_BYTES,
                    "max_instructions": self.profile.max_program_instructions,
                    "max_gas": self.profile.max_gas,
                    "logical_queries": self.profile.logical_query_budget,
                    "physical_executions": self.profile.physical_execution_budget
                }
            }),
            false,
        ))
    }

    fn handle_execute(
        &mut self,
        request: ExecuteRequest,
    ) -> Result<(Value, bool), (&'static str, String, bool)> {
        check_version(&request.protocol_version)?;
        if request.kind != "execute" {
            return Err((
                "schema_error",
                "execute request has inconsistent kind".to_owned(),
                true,
            ));
        }
        if request.program.len() > MAX_PROGRAM_BYTES {
            return Err((
                "invalid_program",
                format!("program exceeds {MAX_PROGRAM_BYTES} bytes"),
                true,
            ));
        }
        if request.logical_batch_id.is_empty() {
            return Err((
                "schema_error",
                "logical_batch_id must be non-empty".to_owned(),
                true,
            ));
        }
        if !request.public_input.memory.is_empty() {
            return Err((
                "invalid_program",
                "memory initialization is reserved until LOAD/STORE milestone M1".to_owned(),
                true,
            ));
        }
        if self.physical_executions_used >= self.profile.physical_execution_budget {
            return Err((
                "budget_exhausted",
                "physical execution budget exhausted".to_owned(),
                false,
            ));
        }
        let reset = parse_reset(&request.reset)?;
        let program = Program::parse(
            &request.program,
            self.profile.lanes,
            self.profile.max_program_instructions,
            self.profile.max_gas,
        )
        .map_err(|error| ("invalid_program", error.to_string(), true))?;

        if let Entry::Vacant(entry) = self.sessions.entry(request.session_id.clone()) {
            let machine = Machine::new(self.profile.clone(), self.secret.clone())
                .map_err(|message| ("internal_error", message, false))?;
            entry.insert(machine);
        }
        self.physical_executions_used = self.physical_executions_used.saturating_add(1);
        let used = self.physical_executions_used;
        let remaining = self.profile.physical_execution_budget.saturating_sub(used);
        let machine = self.sessions.get_mut(&request.session_id).ok_or_else(|| {
            (
                "internal_error",
                "session creation failed".to_owned(),
                false,
            )
        })?;
        let public_input = PublicInput {
            registers: request.public_input.registers,
        };
        let result = machine.execute(
            &program,
            reset,
            &public_input,
            request.execution_seed_id.as_deref(),
        );
        let status = if result.halted {
            "halted"
        } else {
            "gas_exhausted"
        };
        Ok((
            json!({
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request.request_id,
                "kind": "execute_result",
                "ok": true,
                "session_id": request.session_id,
                "status": status,
                "public_digest": format!("{:016x}", result.public_digest),
                "observation": {
                    "cycle_bucket": result.cycle_bucket,
                    "bucket_width": result.bucket_width,
                    "samples_in_vm": 1
                },
                "public_metrics": {
                    "retired_instructions": result.retired_instructions,
                    "static_cycles": result.static_cycles
                },
                "budget": {
                    "physical_executions_used": used,
                    "physical_executions_remaining": remaining
                }
            }),
            false,
        ))
    }

    fn handle_close(
        &self,
        request: CloseRequest,
    ) -> Result<(Value, bool), (&'static str, String, bool)> {
        check_version(&request.protocol_version)?;
        if request.kind != "close" {
            return Err((
                "schema_error",
                "close request has inconsistent kind".to_owned(),
                true,
            ));
        }
        Ok((
            json!({
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request.request_id,
                "kind": "close_result",
                "ok": true
            }),
            true,
        ))
    }
}

fn parse_request(value: Value) -> Result<ParsedRequest, String> {
    let kind = value
        .get("kind")
        .and_then(Value::as_str)
        .ok_or_else(|| "request kind must be a string".to_owned())?
        .to_owned();
    match kind.as_str() {
        "hello" => serde_json::from_value(value)
            .map(ParsedRequest::Hello)
            .map_err(|error| error.to_string()),
        "execute" => serde_json::from_value(value)
            .map(ParsedRequest::Execute)
            .map_err(|error| error.to_string()),
        "close" => serde_json::from_value(value)
            .map(ParsedRequest::Close)
            .map_err(|error| error.to_string()),
        _ => Err(format!("unknown request kind {kind}")),
    }
}

fn parse_reset(value: &str) -> Result<ResetKind, (&'static str, String, bool)> {
    match value {
        "hard" => Ok(ResetKind::Hard),
        "soft" => Ok(ResetKind::Soft),
        "none" => Ok(ResetKind::None),
        _ => Err((
            "schema_error",
            format!("unknown reset mode {value}"),
            true,
        )),
    }
}

fn check_version(version: &str) -> Result<(), (&'static str, String, bool)> {
    if version == PROTOCOL_VERSION {
        Ok(())
    } else {
        Err((
            "unsupported_version",
            format!("server supports {PROTOCOL_VERSION}, received {version}"),
            false,
        ))
    }
}

fn error_response(request_id: &str, code: &str, message: String, recoverable: bool) -> Value {
    json!({
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "kind": "error",
        "ok": false,
        "error": {
            "code": code,
            "message": message,
            "recoverable": recoverable
        }
    })
}

fn serialize_value(value: Value) -> String {
    serde_json::to_string(&value).unwrap_or_else(|error| {
        format!(
            "{{\"protocol_version\":\"1.0\",\"request_id\":\"unknown\",\"kind\":\"error\",\"ok\":false,\"error\":{{\"code\":\"internal_error\",\"message\":\"serialization failed: {error}\",\"recoverable\":false}}}}"
        )
    })
}

#[cfg(test)]
mod tests {
    use serde_json::Value;

    use crate::config::Profile;

    use super::Server;

    fn profile() -> Profile {
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
            hard_reset_budget: 10,
            logical_query_budget: 10,
            physical_execution_budget: 10,
            max_program_instructions: 128,
            max_gas: 4096,
            server_diagnostics: false,
        }
    }

    #[test]
    fn hello_response_has_expected_kind() {
        let server = Server::new(profile(), vec![0, 1, 2, 3]);
        let mut server = match server {
            Ok(value) => value,
            Err(error) => panic!("server construction failed: {error}"),
        };
        let (line, close) = server.handle_line(
            r#"{"protocol_version":"1.0","request_id":"r1","kind":"hello","client":{"name":"test","version":"0"}}"#,
        );
        assert!(!close);
        let parsed: Result<Value, _> = serde_json::from_str(&line);
        let value = match parsed {
            Ok(value) => value,
            Err(error) => panic!("response was not JSON: {error}"),
        };
        assert_eq!(value["kind"], "hello_result");
    }
}
