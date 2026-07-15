//! Challenge creation, isolated serving, and one-shot judge CLI for SphinxVM.

use std::io::{self, Write as _};
use std::path::PathBuf;

use clap::{Parser, Subcommand};
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
        /// Challenge root containing public/ and private/.
        #[arg(long)]
        challenge: PathBuf,
    },
    /// Create and inspect development/evaluation challenge packages.
    Challenge {
        #[command(subcommand)]
        command: ChallengeCommand,
    },
    /// Submit one final ordered-nibble guess to the one-shot local judge.
    Judge {
        /// Challenge root.
        #[arg(long)]
        challenge: PathBuf,
        /// Public campaign token from public/challenge.json.
        #[arg(long)]
        campaign_token: String,
        /// Ordered lowercase hexadecimal secret cells.
        #[arg(long)]
        guess: String,
    },
}

#[derive(Debug, Subcommand)]
enum ChallengeCommand {
    /// Generate a new public/private challenge directory.
    Create {
        /// Public profile template.
        #[arg(long)]
        profile: PathBuf,
        /// New output directory; existing paths are never overwritten.
        #[arg(long)]
        output: PathBuf,
        /// Optional public identifier.
        #[arg(long)]
        challenge_id: Option<String>,
        /// Optional reproducible development/evaluation seed.
        #[arg(long)]
        seed: Option<u64>,
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

fn main() {
    let cli = Cli::parse();
    if let Err(error) = run(cli) {
        eprintln!("sphinx-vm: {error}");
        std::process::exit(2);
    }
}

fn run(cli: Cli) -> Result<(), String> {
    match cli.command {
        Command::Serve { challenge } => serve(&challenge),
        Command::Challenge {
            command:
                ChallengeCommand::Create {
                    profile,
                    output,
                    challenge_id,
                    seed,
                    fault,
                },
        } => {
            let public = challenge::create(&CreateChallenge {
                profile_path: profile,
                output,
                challenge_id,
                seed,
                fault_variant: fault,
            })
            .map_err(|error| error.to_string())?;
            let serialized = serde_json::to_string(&public).map_err(|error| error.to_string())?;
            println!("{serialized}");
            Ok(())
        }
        Command::Judge {
            challenge,
            campaign_token,
            guess,
        } => {
            let result = judge::submit(challenge, &campaign_token, &guess)
                .map_err(|error| error.to_string())?;
            let serialized = serde_json::to_string(&result).map_err(|error| error.to_string())?;
            println!("{serialized}");
            Ok(())
        }
    }
}

fn serve(challenge_root: &PathBuf) -> Result<(), String> {
    let loaded = challenge::load(challenge_root).map_err(|error| error.to_string())?;
    let mut server = Server::new(loaded.profile, loaded.private_machine)?;
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout().lock());
    let mut input = stdin.lock();
    loop {
        let (response, should_close) = match read_bounded_line(&mut input, MAX_REQUEST_LINE_BYTES)
            .map_err(|error| {
            format!("stdin read failed: {error}")
        })? {
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
        writeln!(stdout, "{response}").map_err(|error| format!("stdout write failed: {error}"))?;
        stdout
            .flush()
            .map_err(|error| format!("stdout flush failed: {error}"))?;
        if should_close {
            break;
        }
    }
    Ok(())
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
