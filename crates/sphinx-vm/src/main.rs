//! JSONL process entry point for SphinxVM.

use std::env;
use std::io::{self, Write as _};
use std::path::PathBuf;

use sphinx_vm::protocol::MAX_REQUEST_LINE_BYTES;
use sphinx_vm::{Profile, Server};

enum BoundedLine {
    Eof,
    Line(String),
    TooLarge,
    InvalidUtf8,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("sphinx-vm: {error}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let profile_path = parse_profile_path(env::args().skip(1))?;
    let profile = Profile::load(&profile_path).map_err(|error| error.to_string())?;
    let secret = scaffold_secret(profile.secret_cells);
    let mut server = Server::new(profile, secret)?;
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

fn parse_profile_path(mut args: impl Iterator<Item = String>) -> Result<PathBuf, String> {
    let mut profile = PathBuf::from("benchmarks/profiles/tutorial.toml");
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--profile" => {
                let value = args
                    .next()
                    .ok_or_else(|| "--profile requires a path".to_owned())?;
                profile = PathBuf::from(value);
            }
            "--help" | "-h" => {
                println!("Usage: sphinx-vm [--profile PATH]");
                std::process::exit(0);
            }
            unknown => return Err(format!("unknown argument {unknown}")),
        }
    }
    Ok(profile)
}

fn scaffold_secret(cells: usize) -> Vec<u8> {
    (0..cells)
        .map(|index| u8::try_from((index * 7 + 3) & 0x0f).unwrap_or_default())
        .collect()
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
