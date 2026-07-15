//! JSONL process entry point for SphinxVM.

use std::env;
use std::io::{self, BufRead as _, Write as _};
use std::path::PathBuf;

use sphinx_vm::{Profile, Server};

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
    for line_result in stdin.lock().lines() {
        let line = line_result.map_err(|error| format!("stdin read failed: {error}"))?;
        if line.trim().is_empty() {
            continue;
        }
        let (response, should_close) = server.handle_line(&line);
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
