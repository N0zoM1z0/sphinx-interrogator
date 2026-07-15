//! Public JSON Lines protocol server.

use std::collections::{hash_map::Entry, BTreeMap, HashMap, HashSet};

use serde::Deserialize;
use serde_json::{json, Value};

use crate::config::Profile;
use crate::isa::Program;
use crate::machine::{Machine, PublicInput, ResetKind};

/// Exact public protocol version implemented by this server.
pub const PROTOCOL_VERSION: &str = "1.0";
/// Maximum encoded JSONL request size, including protocol metadata.
pub const MAX_REQUEST_LINE_BYTES: usize = 131_072;
const MAX_PROGRAM_BYTES: usize = 65_536;
const MAX_SESSIONS: usize = 64;
const MAX_ID_BYTES: usize = 128;

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
    memory: BTreeMap<String, u16>,
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

type RequestFailure = (&'static str, String, bool);

/// Stateful process-boundary server for one private challenge.
pub struct Server {
    profile: Profile,
    secret: Vec<u8>,
    sessions: HashMap<String, Machine>,
    logical_batches: HashSet<String>,
    physical_executions_used: u64,
    hard_resets_used: u64,
}

impl Server {
    /// Construct a server from a public profile and private secret cells.
    pub fn new(profile: Profile, secret: Vec<u8>) -> Result<Self, String> {
        let _validation = Machine::new(profile.clone(), secret.clone())?;
        Ok(Self {
            profile,
            secret,
            sessions: HashMap::new(),
            logical_batches: HashSet::new(),
            physical_executions_used: 0,
            hard_resets_used: 0,
        })
    }

    /// Parse one JSON request and return `(serialized_response, should_close)`.
    #[must_use]
    pub fn handle_line(&mut self, line: &str) -> (String, bool) {
        if line.len() > MAX_REQUEST_LINE_BYTES {
            return (
                Self::transport_error_line(
                    "request_too_large",
                    format!("request exceeds {MAX_REQUEST_LINE_BYTES} encoded bytes"),
                    true,
                ),
                false,
            );
        }
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
            .filter(|candidate| valid_id(candidate))
            .unwrap_or("unknown")
            .to_owned();
        let request = match parse_request(value) {
            Ok(request) => request,
            Err(message) => {
                return (
                    serialize_value(error_response(&request_id, "schema_error", message, true)),
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

    /// Serialize an error detected by the bounded transport reader.
    #[must_use]
    pub fn transport_error_line(code: &str, message: String, recoverable: bool) -> String {
        serialize_value(error_response("unknown", code, message, recoverable))
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
        validate_id("request_id", &request.request_id)?;
        if request.kind != "hello" {
            return Err((
                "schema_error",
                "hello request has inconsistent kind".to_owned(),
                true,
            ));
        }
        if request.client.name.is_empty()
            || request.client.name.len() > MAX_ID_BYTES
            || request.client.version.is_empty()
            || request.client.version.len() > 64
        {
            return Err((
                "schema_error",
                "client name and version must be non-empty".to_owned(),
                true,
            ));
        }
        let mut capabilities = vec!["close", "execute", "soft_reset"];
        if self.profile.hard_reset_budget > 0 {
            capabilities.push("hard_reset");
        }
        capabilities.sort_unstable();
        Ok((
            json!({
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request.request_id,
                "kind": "hello_result",
                "ok": true,
                "server": {
                    "name": "sphinx-vm",
                    "version": env!("CARGO_PKG_VERSION"),
                    "build_id": option_env!("SPHINX_BUILD_ID").unwrap_or(env!("CARGO_PKG_VERSION"))
                },
                "profile": {
                    "name": self.profile.name,
                    "semantic_version": self.profile.semantic_version,
                    "bucket_width": self.profile.bucket_width,
                    "lanes": self.profile.lanes,
                    "hard_reset_available": self.profile.hard_reset_budget > 0
                },
                "capabilities": capabilities,
                "limits": {
                    "max_request_line_bytes": MAX_REQUEST_LINE_BYTES,
                    "max_program_bytes": MAX_PROGRAM_BYTES,
                    "max_instructions": self.profile.max_program_instructions,
                    "max_gas": self.profile.max_gas,
                    "max_sessions": MAX_SESSIONS,
                    "hard_resets": self.profile.hard_reset_budget,
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
        validate_id("request_id", &request.request_id)?;
        validate_id("session_id", &request.session_id)?;
        validate_id("logical_batch_id", &request.logical_batch_id)?;
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
        if request.public_input.registers.len() > 8 {
            return Err((
                "schema_error",
                "public_input.registers contains more than eight values".to_owned(),
                true,
            ));
        }
        if request
            .execution_seed_id
            .as_ref()
            .is_some_and(|seed| seed.len() > MAX_ID_BYTES)
        {
            return Err((
                "schema_error",
                format!("execution_seed_id exceeds {MAX_ID_BYTES} bytes"),
                true,
            ));
        }
        let memory = parse_public_memory(&request.public_input.memory)?;
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

        if !self.logical_batches.contains(&request.logical_batch_id)
            && self.logical_batches.len() as u64 >= self.profile.logical_query_budget
        {
            return Err((
                "budget_exhausted",
                "logical query budget exhausted".to_owned(),
                false,
            ));
        }
        if reset == ResetKind::Hard && self.hard_resets_used >= self.profile.hard_reset_budget {
            return Err((
                "budget_exhausted",
                "hard reset budget exhausted".to_owned(),
                false,
            ));
        }
        if !self.sessions.contains_key(&request.session_id) && self.sessions.len() >= MAX_SESSIONS {
            return Err((
                "session_limit",
                format!("server supports at most {MAX_SESSIONS} concurrent sessions"),
                false,
            ));
        }
        if let Entry::Vacant(entry) = self.sessions.entry(request.session_id.clone()) {
            let machine = Machine::new(self.profile.clone(), self.secret.clone())
                .map_err(|message| ("internal_error", message, false))?;
            entry.insert(machine);
        }
        self.logical_batches
            .insert(request.logical_batch_id.clone());
        self.physical_executions_used = self.physical_executions_used.saturating_add(1);
        if reset == ResetKind::Hard {
            self.hard_resets_used = self.hard_resets_used.saturating_add(1);
        }
        let used = self.physical_executions_used;
        let remaining = self.profile.physical_execution_budget.saturating_sub(used);
        let logical_used = u64::try_from(self.logical_batches.len()).unwrap_or(u64::MAX);
        let logical_remaining = self
            .profile
            .logical_query_budget
            .saturating_sub(logical_used);
        let hard_resets_remaining = self
            .profile
            .hard_reset_budget
            .saturating_sub(self.hard_resets_used);
        let machine = self.sessions.get_mut(&request.session_id).ok_or_else(|| {
            (
                "internal_error",
                "session creation failed".to_owned(),
                false,
            )
        })?;
        let public_input = PublicInput {
            registers: request.public_input.registers,
            memory,
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
                    "physical_executions_remaining": remaining,
                    "logical_queries_used": logical_used,
                    "logical_queries_remaining": logical_remaining,
                    "hard_resets_used": self.hard_resets_used,
                    "hard_resets_remaining": hard_resets_remaining
                },
                "semantics": {
                    "server_version": env!("CARGO_PKG_VERSION"),
                    "profile_version": self.profile.semantic_version
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
        validate_id("request_id", &request.request_id)?;
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

fn parse_public_memory(
    memory: &BTreeMap<String, u16>,
) -> Result<Vec<(usize, u16)>, RequestFailure> {
    if memory.len() > 256 {
        return Err((
            "schema_error",
            "public_input.memory contains more than 256 words".to_owned(),
            true,
        ));
    }
    let mut parsed = BTreeMap::new();
    for (key, value) in memory {
        let address = key.parse::<usize>().map_err(|_| {
            (
                "schema_error",
                format!("public_input.memory key {key:?} is not a decimal address"),
                true,
            )
        })?;
        if key != &address.to_string() {
            return Err((
                "schema_error",
                format!("public_input.memory key {key:?} is not canonical decimal"),
                true,
            ));
        }
        if address >= 256 {
            return Err((
                "schema_error",
                format!("public_input.memory address {address} is outside 0..256"),
                true,
            ));
        }
        if parsed.insert(address, *value).is_some() {
            return Err((
                "schema_error",
                format!("public_input.memory contains duplicate address {address}"),
                true,
            ));
        }
    }
    Ok(parsed.into_iter().collect())
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
        _ => Err(("schema_error", format!("unknown reset mode {value}"), true)),
    }
}

fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= MAX_ID_BYTES
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-'))
}

fn validate_id(field: &str, value: &str) -> Result<(), (&'static str, String, bool)> {
    if valid_id(value) {
        Ok(())
    } else {
        Err((
            "schema_error",
            format!("{field} is not a valid protocol identifier"),
            true,
        ))
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

    use super::{Server, MAX_REQUEST_LINE_BYTES};

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

    fn server() -> Server {
        match Server::new(profile(), vec![0, 1, 2, 3]) {
            Ok(value) => value,
            Err(error) => panic!("server construction failed: {error}"),
        }
    }

    fn response_value(line: &str) -> Value {
        match serde_json::from_str(line) {
            Ok(value) => value,
            Err(error) => panic!("response was not JSON: {error}"),
        }
    }

    #[test]
    fn hello_response_has_expected_kind() {
        let mut server = server();
        let (line, close) = server.handle_line(
            r#"{"protocol_version":"1.0","request_id":"r1","kind":"hello","client":{"name":"test","version":"0"}}"#,
        );
        assert!(!close);
        let value = response_value(&line);
        assert_eq!(value["kind"], "hello_result");
    }

    #[test]
    fn execute_response_tracks_logical_and_reset_budgets() {
        let mut server = server();
        let first = r#"{"protocol_version":"1.0","request_id":"r1","kind":"execute","session_id":"s1","reset":"hard","program":"HALT\n","logical_batch_id":"b1"}"#;
        let second = r#"{"protocol_version":"1.0","request_id":"r2","kind":"execute","session_id":"s1","reset":"soft","program":"HALT\n","logical_batch_id":"b1"}"#;
        let (first_line, _) = server.handle_line(first);
        let (second_line, _) = server.handle_line(second);
        let first_value = response_value(&first_line);
        let second_value = response_value(&second_line);
        assert_eq!(first_value["budget"]["logical_queries_used"], 1);
        assert_eq!(first_value["budget"]["hard_resets_used"], 1);
        assert_eq!(second_value["budget"]["logical_queries_used"], 1);
        assert_eq!(second_value["budget"]["hard_resets_used"], 1);
        assert_eq!(second_value["budget"]["physical_executions_used"], 2);
        assert_eq!(second_value["semantics"]["profile_version"], "0.1.0");
    }

    #[test]
    fn rejects_invalid_identifiers_and_register_overflow() {
        let mut server = server();
        let invalid_id = r#"{"protocol_version":"1.0","request_id":"bad id","kind":"hello","client":{"name":"test","version":"0"}}"#;
        let (id_line, _) = server.handle_line(invalid_id);
        let id_value = response_value(&id_line);
        assert_eq!(id_value["request_id"], "unknown");
        assert_eq!(id_value["error"]["code"], "schema_error");

        let registers = r#"{"protocol_version":"1.0","request_id":"r2","kind":"execute","session_id":"s1","reset":"hard","program":"HALT\n","public_input":{"registers":[0,0,0,0,0,0,0,0,0],"memory":{}},"logical_batch_id":"b1"}"#;
        let (register_line, _) = server.handle_line(registers);
        let register_value = response_value(&register_line);
        assert_eq!(register_value["error"]["code"], "schema_error");
    }

    #[test]
    fn applies_sparse_public_memory_and_rejects_noncanonical_addresses() {
        let mut server = server();
        let request = r#"{"protocol_version":"1.0","request_id":"r1","kind":"execute","session_id":"s1","reset":"hard","program":"LOAD r0, [r1]\nMIXOUT r0\nHALT\n","public_input":{"registers":[0,7],"memory":{"7":4660}},"logical_batch_id":"b1"}"#;
        let (line, _) = server.handle_line(request);
        let value = response_value(&line);
        assert_eq!(value["kind"], "execute_result");
        assert_eq!(value["status"], "halted");
        assert_ne!(value["public_digest"], "0000000000000000");
        assert_eq!(value["public_metrics"]["static_cycles"], 5);

        for (index, address) in ["01", "256", "not-an-address"].iter().enumerate() {
            let invalid = format!(
                "{{\"protocol_version\":\"1.0\",\"request_id\":\"bad{index}\",\"kind\":\"execute\",\"session_id\":\"s1\",\"reset\":\"hard\",\"program\":\"HALT\\n\",\"public_input\":{{\"memory\":{{\"{address}\":1}}}},\"logical_batch_id\":\"bad-batch\"}}"
            );
            let (invalid_line, _) = server.handle_line(&invalid);
            let invalid_value = response_value(&invalid_line);
            assert_eq!(invalid_value["error"]["code"], "schema_error");
        }
    }

    #[test]
    fn rejects_oversized_direct_requests_without_parsing() {
        let mut server = server();
        let oversized = "x".repeat(MAX_REQUEST_LINE_BYTES + 1);
        let (line, close) = server.handle_line(&oversized);
        let value = response_value(&line);
        assert!(!close);
        assert_eq!(value["error"]["code"], "request_too_large");
    }

    #[test]
    fn invalid_program_does_not_mutate_session_or_budgets() {
        let mut server = server();
        let invalid = r#"{"protocol_version":"1.0","request_id":"bad","kind":"execute","session_id":"s1","reset":"hard","program":"MOVI r8, 0\nHALT\n","logical_batch_id":"b1"}"#;
        let (invalid_line, _) = server.handle_line(invalid);
        assert_eq!(
            response_value(&invalid_line)["error"]["code"],
            "invalid_program"
        );

        let valid = r#"{"protocol_version":"1.0","request_id":"good","kind":"execute","session_id":"s1","reset":"hard","program":"HALT\n","logical_batch_id":"b1"}"#;
        let (valid_line, _) = server.handle_line(valid);
        let value = response_value(&valid_line);
        assert_eq!(value["budget"]["physical_executions_used"], 1);
        assert_eq!(value["budget"]["logical_queries_used"], 1);
        assert_eq!(value["budget"]["hard_resets_used"], 1);
    }

    #[test]
    fn arbitrary_bounded_protocol_text_never_panics() {
        let mut server = server();
        let mut state = 0xa076_1d64_78bd_642f_u64;
        for length in 0..1024 {
            let mut line = String::with_capacity(length);
            for _ in 0..length {
                state ^= state >> 12;
                state ^= state << 25;
                state ^= state >> 27;
                let byte = 0x20 + u8::try_from(state % 95).unwrap_or_default();
                line.push(char::from(byte));
            }
            let _response = server.handle_line(&line);
        }
    }
}
