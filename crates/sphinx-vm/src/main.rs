//! Split challenge creation, isolated serving, and one-shot judge CLI for SphinxVM.

use std::fs;
use std::io::{self, Write as _};
use std::path::{Path, PathBuf};

use clap::{Parser, Subcommand};
use serde::Deserialize;
use sphinx_vm::challenge::{self, CreateChallenge};
use sphinx_vm::fault::FaultVariant;
use sphinx_vm::judge;
use sphinx_vm::protocol::MAX_REQUEST_LINE_BYTES;
use sphinx_vm::Server;

#[derive(Debug, Parser)]
#[command(
    name = "sphinx-vm",
    version,
    about = "Synthetic SphinxVM challenge target"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Serve one generated challenge over the public JSONL protocol.
    Serve {
        /// Public challenge directory exposed to the client.
        #[arg(long)]
        public_challenge: PathBuf,
        /// Protected private directory path for trusted direct tests.
        #[arg(long)]
        private_challenge: Option<PathBuf>,
        /// Inherited protected directory FD supplied by trusted orchestration.
        #[arg(long)]
        private_challenge_fd: Option<i32>,
        /// Optional public Unix-domain socket; omit only for trusted stdio tests.
        #[arg(long)]
        socket: Option<PathBuf>,
    },
    /// Create and inspect development/evaluation challenge packages.
    Challenge {
        #[command(subcommand)]
        command: ChallengeCommand,
    },
    /// Submit one final ordered-nibble guess to the one-shot local judge.
    Judge {
        /// Public challenge directory.
        #[arg(long)]
        public_challenge: PathBuf,
        /// Protected private challenge directory.
        #[arg(long)]
        private_challenge: PathBuf,
        /// Public campaign token from challenge.json.
        #[arg(long)]
        campaign_token: String,
        /// Ordered lowercase hexadecimal secret cells.
        #[arg(long)]
        guess: String,
    },
    /// Serve one final judge submission over a public Unix-domain socket.
    JudgeServe {
        /// Public challenge directory.
        #[arg(long)]
        public_challenge: PathBuf,
        /// Protected private directory path for trusted direct tests.
        #[arg(long)]
        private_challenge: Option<PathBuf>,
        /// Inherited protected directory FD supplied by trusted orchestration.
        #[arg(long)]
        private_challenge_fd: Option<i32>,
        /// Public Unix-domain socket used for one submission.
        #[arg(long)]
        socket: PathBuf,
    },
}

#[derive(Debug, Subcommand)]
enum ChallengeCommand {
    /// Generate a protected random 256-bit challenge root.
    PrivateRoot {
        /// New root file; existing paths are never overwritten.
        #[arg(long)]
        output: PathBuf,
    },
    /// Generate new disjoint public/private challenge directories.
    Create {
        /// Public profile template.
        #[arg(long)]
        profile: PathBuf,
        /// New public output directory.
        #[arg(long)]
        public_output: PathBuf,
        /// New protected private output directory.
        #[arg(long)]
        private_output: PathBuf,
        /// Existing protected 32-byte private root file.
        #[arg(long)]
        private_root_file: PathBuf,
        /// Optional public identifier.
        #[arg(long)]
        challenge_id: Option<String>,
        /// Private label that domain-separates the one-shot campaign token.
        #[arg(long)]
        campaign_label: String,
        /// Private fault assignment, deliberately absent from public artifacts.
        #[arg(long, default_value = "reference")]
        fault: FaultVariant,
    },
}

enum BoundedLine {
    Eof,
    Line(String),
    TooLarge,
    InvalidUtf8,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct JudgeSocketRequest {
    judge_protocol_version: String,
    campaign_token: String,
    guess: String,
}

fn main() {
    let cli = Cli::parse();
    if let Err(error) = run(cli) {
        eprintln!("sphinx-vm: {error}");
        std::process::exit(2);
    }
}

fn run(cli: Cli) -> Result<(), String> {
    match cli.command {
        Command::Serve {
            public_challenge,
            private_challenge,
            private_challenge_fd,
            socket,
        } => {
            let private_directory =
                resolve_private_directory(private_challenge, private_challenge_fd)?;
            serve(&public_challenge, &private_directory, socket.as_deref())
        }
        Command::Challenge {
            command: ChallengeCommand::PrivateRoot { output },
        } => challenge::create_private_root(output).map_err(|error| error.to_string()),
        Command::Challenge {
            command:
                ChallengeCommand::Create {
                    profile,
                    public_output,
                    private_output,
                    private_root_file,
                    challenge_id,
                    campaign_label,
                    fault,
                },
        } => {
            let public = challenge::create(&CreateChallenge {
                profile_path: profile,
                public_output,
                private_output,
                private_root_path: private_root_file,
                challenge_id,
                campaign_label,
                fault_variant: fault,
            })
            .map_err(|error| error.to_string())?;
            let serialized = serde_json::to_string(&public).map_err(|error| error.to_string())?;
            println!("{serialized}");
            Ok(())
        }
        Command::Judge {
            public_challenge,
            private_challenge,
            campaign_token,
            guess,
        } => {
            let result =
                judge::submit(public_challenge, private_challenge, &campaign_token, &guess)
                    .map_err(|error| error.to_string())?;
            let serialized = serde_json::to_string(&result).map_err(|error| error.to_string())?;
            println!("{serialized}");
            Ok(())
        }
        Command::JudgeServe {
            public_challenge,
            private_challenge,
            private_challenge_fd,
            socket,
        } => {
            let private_directory =
                resolve_private_directory(private_challenge, private_challenge_fd)?;
            judge_serve(&public_challenge, &private_directory, &socket)
        }
    }
}

fn resolve_private_directory(
    path: Option<PathBuf>,
    descriptor: Option<i32>,
) -> Result<PathBuf, String> {
    match (path, descriptor) {
        (Some(path), None) => Ok(path),
        (None, Some(descriptor)) if descriptor >= 0 => {
            #[cfg(target_os = "linux")]
            {
                Ok(PathBuf::from(format!("/proc/self/fd/{descriptor}")))
            }
            #[cfg(all(unix, not(target_os = "linux")))]
            {
                Ok(PathBuf::from(format!("/dev/fd/{descriptor}")))
            }
            #[cfg(not(unix))]
            {
                let _ = descriptor;
                Err("private challenge file descriptors require Unix".to_owned())
            }
        }
        (None, Some(_)) => Err("private challenge file descriptor must be nonnegative".to_owned()),
        (Some(_), Some(_)) => {
            Err("provide exactly one of --private-challenge or --private-challenge-fd".to_owned())
        }
        (None, None) => {
            Err("provide exactly one of --private-challenge or --private-challenge-fd".to_owned())
        }
    }
}

fn serve(
    public_directory: &Path,
    private_directory: &Path,
    socket: Option<&Path>,
) -> Result<(), String> {
    let loaded =
        challenge::load(public_directory, private_directory).map_err(|error| error.to_string())?;
    let mut server = Server::new(loaded.profile, loaded.private_machine)?;
    if let Some(socket_path) = socket {
        return serve_unix(&mut server, socket_path);
    }
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout().lock());
    let mut input = stdin.lock();
    serve_protocol(&mut server, &mut input, &mut stdout, "stdin", "stdout")
}

fn serve_protocol(
    server: &mut Server,
    input: &mut impl io::BufRead,
    output: &mut impl io::Write,
    input_name: &str,
    output_name: &str,
) -> Result<(), String> {
    loop {
        let (response, should_close) = match read_bounded_line(input, MAX_REQUEST_LINE_BYTES)
            .map_err(|error| format!("{input_name} read failed: {error}"))?
        {
            BoundedLine::Eof => break,
            BoundedLine::Line(line) if line.trim().is_empty() => continue,
            BoundedLine::Line(line) => server.handle_line(&line),
            BoundedLine::TooLarge => (
                Server::transport_error_line(
                    "request_too_large",
                    format!("request exceeds {MAX_REQUEST_LINE_BYTES} encoded bytes"),
                    true,
                ),
                false,
            ),
            BoundedLine::InvalidUtf8 => (
                Server::transport_error_line(
                    "invalid_json",
                    "request is not valid UTF-8".to_owned(),
                    true,
                ),
                false,
            ),
        };
        writeln!(output, "{response}")
            .map_err(|error| format!("{output_name} write failed: {error}"))?;
        output
            .flush()
            .map_err(|error| format!("{output_name} flush failed: {error}"))?;
        if should_close {
            break;
        }
    }
    Ok(())
}

#[cfg(unix)]
fn serve_unix(server: &mut Server, socket_path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt as _;
    use std::os::unix::net::UnixListener;

    prepare_socket_path(socket_path)?;
    let listener = UnixListener::bind(socket_path)
        .map_err(|error| format!("Unix socket bind failed: {error}"))?;
    fs::set_permissions(socket_path, fs::Permissions::from_mode(0o666))
        .map_err(|error| format!("Unix socket permission update failed: {error}"))?;
    let outcome = (|| {
        let (stream, _) = listener
            .accept()
            .map_err(|error| format!("Unix socket accept failed: {error}"))?;
        let reader_stream = stream
            .try_clone()
            .map_err(|error| format!("Unix socket clone failed: {error}"))?;
        let mut input = io::BufReader::new(reader_stream);
        let mut output = io::BufWriter::new(stream);
        serve_protocol(server, &mut input, &mut output, "socket", "socket")
    })();
    let cleanup = fs::remove_file(socket_path);
    match (outcome, cleanup) {
        (Err(error), _) => Err(error),
        (Ok(()), Err(error)) => Err(format!("Unix socket cleanup failed: {error}")),
        (Ok(()), Ok(())) => Ok(()),
    }
}

#[cfg(not(unix))]
fn serve_unix(_server: &mut Server, _socket_path: &Path) -> Result<(), String> {
    Err("Unix-domain socket serving is not supported on this platform".to_owned())
}

#[cfg(unix)]
fn judge_serve(
    public_directory: &Path,
    private_directory: &Path,
    socket_path: &Path,
) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt as _;
    use std::os::unix::net::UnixListener;

    prepare_socket_path(socket_path)?;
    let listener = UnixListener::bind(socket_path)
        .map_err(|error| format!("judge Unix socket bind failed: {error}"))?;
    fs::set_permissions(socket_path, fs::Permissions::from_mode(0o666))
        .map_err(|error| format!("judge Unix socket permission update failed: {error}"))?;
    let outcome = (|| {
        let (stream, _) = listener
            .accept()
            .map_err(|error| format!("judge Unix socket accept failed: {error}"))?;
        let reader_stream = stream
            .try_clone()
            .map_err(|error| format!("judge Unix socket clone failed: {error}"))?;
        let mut input = io::BufReader::new(reader_stream);
        let mut output = io::BufWriter::new(stream);
        let request = match read_bounded_line(&mut input, 4096)
            .map_err(|error| format!("judge socket read failed: {error}"))?
        {
            BoundedLine::Line(line) => serde_json::from_str::<JudgeSocketRequest>(&line)
                .map_err(|error| format!("invalid judge request: {error}"))?,
            BoundedLine::Eof => return Err("judge socket closed before a request".to_owned()),
            BoundedLine::TooLarge => return Err("judge request exceeds 4096 bytes".to_owned()),
            BoundedLine::InvalidUtf8 => return Err("judge request is not valid UTF-8".to_owned()),
        };
        if request.judge_protocol_version != "1.0" {
            return Err("unsupported judge protocol version".to_owned());
        }
        let response = judge::submit(
            public_directory,
            private_directory,
            &request.campaign_token,
            &request.guess,
        )
        .map_err(|error| error.to_string())?;
        let serialized = serde_json::to_string(&response).map_err(|error| error.to_string())?;
        writeln!(output, "{serialized}")
            .map_err(|error| format!("judge socket write failed: {error}"))?;
        output
            .flush()
            .map_err(|error| format!("judge socket flush failed: {error}"))
    })();
    let cleanup = fs::remove_file(socket_path);
    match (outcome, cleanup) {
        (Err(error), _) => Err(error),
        (Ok(()), Err(error)) => Err(format!("judge Unix socket cleanup failed: {error}")),
        (Ok(()), Ok(())) => Ok(()),
    }
}

#[cfg(not(unix))]
fn judge_serve(
    _public_directory: &Path,
    _private_directory: &Path,
    _socket_path: &Path,
) -> Result<(), String> {
    Err("Unix-domain judge serving is not supported on this platform".to_owned())
}

#[cfg(unix)]
fn prepare_socket_path(socket_path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt as _;

    if socket_path.exists() {
        return Err(format!(
            "Unix socket path already exists: {}",
            socket_path.display()
        ));
    }
    let parent = socket_path
        .parent()
        .ok_or_else(|| format!("Unix socket path has no parent: {}", socket_path.display()))?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("socket parent creation failed: {error}"))?;
    fs::set_permissions(parent, fs::Permissions::from_mode(0o755))
        .map_err(|error| format!("socket parent permission update failed: {error}"))
}

fn read_bounded_line(
    reader: &mut impl io::BufRead,
    maximum_bytes: usize,
) -> io::Result<BoundedLine> {
    let mut collected = Vec::new();
    let mut too_large = false;
    let mut saw_data = false;

    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            if !saw_data {
                return Ok(BoundedLine::Eof);
            }
            break;
        }
        saw_data = true;
        let newline = available.iter().position(|byte| *byte == b'\n');
        let consumed = newline.map_or(available.len(), |index| index + 1);
        if !too_large {
            if collected.len().saturating_add(consumed) > maximum_bytes {
                too_large = true;
                collected.clear();
            } else {
                collected.extend_from_slice(&available[..consumed]);
            }
        }
        reader.consume(consumed);
        if newline.is_some() {
            break;
        }
    }

    if too_large {
        return Ok(BoundedLine::TooLarge);
    }
    if collected.last() == Some(&b'\n') {
        collected.pop();
    }
    if collected.last() == Some(&b'\r') {
        collected.pop();
    }
    match String::from_utf8(collected) {
        Ok(line) => Ok(BoundedLine::Line(line)),
        Err(_) => Ok(BoundedLine::InvalidUtf8),
    }
}

#[cfg(test)]
mod tests {
    use std::io::Cursor;

    use super::{read_bounded_line, BoundedLine};

    #[test]
    fn bounded_reader_recovers_after_oversized_line() {
        let mut input = Cursor::new(b"123456\nok\n".to_vec());
        assert!(matches!(
            read_bounded_line(&mut input, 4),
            Ok(BoundedLine::TooLarge)
        ));
        match read_bounded_line(&mut input, 4) {
            Ok(BoundedLine::Line(line)) => assert_eq!(line, "ok"),
            _ => panic!("expected the line following an oversized request"),
        }
    }

    #[test]
    fn bounded_reader_rejects_invalid_utf8_without_exiting() {
        let mut input = Cursor::new(vec![0xff, b'\n']);
        assert!(matches!(
            read_bounded_line(&mut input, 4),
            Ok(BoundedLine::InvalidUtf8)
        ));
    }
}
