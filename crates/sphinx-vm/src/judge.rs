//! One-shot local judge with an atomic per-campaign-token submission policy.

use std::fs::{self, OpenOptions};
use std::io::Write as _;
use std::path::Path;

use serde::Serialize;
use sha2::{Digest as _, Sha256};

use crate::challenge::{hex_encode, judge_material, ChallengeError};

/// Public result of one judge invocation.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct JudgeResponse {
    /// Judge response schema version.
    pub judge_version: String,
    /// Public challenge identifier.
    pub challenge_id: String,
    /// Public campaign token.
    pub campaign_token: String,
    /// Whether this invocation recorded the token's one allowed submission.
    pub submission_recorded: bool,
    /// Whether the recorded guess exactly matched the private ordered cells.
    pub accepted: bool,
}

/// Submit one final ordered-nibble guess. Every valid first guess consumes the token.
pub fn submit(
    public_directory: impl AsRef<Path>,
    private_directory: impl AsRef<Path>,
    campaign_token: &str,
    guess_hex: &str,
) -> Result<JudgeResponse, ChallengeError> {
    let private_directory = private_directory.as_ref();
    let (public, secret) = judge_material(public_directory.as_ref(), private_directory)?;
    if !constant_time_equal(campaign_token.as_bytes(), public.campaign_token.as_bytes()) {
        return Err(ChallengeError::Invalid(
            "campaign token does not belong to this challenge".to_owned(),
        ));
    }
    let guess = parse_guess(guess_hex, secret.len())?;
    let marker_name = hex_encode(&Sha256::digest(campaign_token.as_bytes()));
    let marker_path = private_directory.join("judge-used").join(marker_name);
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        options.mode(0o600);
    }
    let marker = options.open(&marker_path);
    let mut marker = match marker {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            return Ok(JudgeResponse {
                judge_version: "1.0".to_owned(),
                challenge_id: public.challenge_id,
                campaign_token: public.campaign_token,
                submission_recorded: false,
                accepted: false,
            });
        }
        Err(error) => return Err(ChallengeError::Io(error)),
    };
    marker.write_all(b"submission-used\n")?;
    marker.sync_all()?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;

        fs::set_permissions(&marker_path, fs::Permissions::from_mode(0o600))?;
    }
    Ok(JudgeResponse {
        judge_version: "1.0".to_owned(),
        challenge_id: public.challenge_id,
        campaign_token: public.campaign_token,
        submission_recorded: true,
        accepted: constant_time_equal(&guess, &secret),
    })
}

fn parse_guess(value: &str, cells: usize) -> Result<Vec<u8>, ChallengeError> {
    if value.len() != cells || !value.is_ascii() {
        return Err(ChallengeError::Invalid(format!(
            "guess must contain exactly {cells} lowercase hexadecimal cells"
        )));
    }
    value
        .bytes()
        .map(|byte| match byte {
            b'0'..=b'9' => Ok(byte - b'0'),
            b'a'..=b'f' => Ok(byte - b'a' + 10),
            _ => Err(ChallengeError::Invalid(
                "guess must use lowercase hexadecimal".to_owned(),
            )),
        })
        .collect()
}

fn constant_time_equal(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut difference = 0_u8;
    for (left, right) in left.iter().zip(right) {
        difference |= left ^ right;
    }
    difference == 0
}

#[cfg(test)]
mod tests {
    use std::io::Write as _;
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::submit;
    use crate::challenge::{create, judge_material, CreateChallenge};
    use crate::fault::FaultVariant;

    static NEXT_PATH: AtomicU64 = AtomicU64::new(0);

    fn temporary_path() -> std::path::PathBuf {
        let ordinal = NEXT_PATH.fetch_add(1, Ordering::Relaxed);
        std::env::temp_dir().join(format!("sphinx-judge-{}-{ordinal}", std::process::id()))
    }

    fn write_private_root(path: &std::path::Path) {
        if let Some(parent) = path.parent() {
            if let Err(error) = std::fs::create_dir_all(parent) {
                panic!("private root parent should be created: {error}");
            }
        }
        let mut options = std::fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt as _;

            options.mode(0o600);
        }
        let mut file = match options.open(path) {
            Ok(value) => value,
            Err(error) => panic!("private root should be created: {error}"),
        };
        if let Err(error) = file.write_all(&[19_u8; 32]) {
            panic!("private root should be written: {error}");
        }
    }

    #[test]
    fn judge_accepts_at_most_one_guess_for_the_public_token() {
        let root = temporary_path();
        let private_root = root.join("root.bin");
        write_private_root(&private_root);
        let profile = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../benchmarks/profiles/tutorial.toml");
        let options = CreateChallenge {
            profile_path: profile,
            public_output: root.join("public"),
            private_output: root.join("private"),
            private_root_path: private_root,
            challenge_id: Some("judge-test".to_owned()),
            campaign_label: "judge-campaign".to_owned(),
            fault_variant: FaultVariant::Reference,
        };
        let public = match create(&options) {
            Ok(value) => value,
            Err(error) => panic!("challenge should be created: {error}"),
        };
        let material = judge_material(&root.join("public"), &root.join("private"));
        let (_, secret) = match material {
            Ok(value) => value,
            Err(error) => panic!("judge material should load: {error}"),
        };
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let guess: String = secret
            .iter()
            .map(|value| char::from(HEX[usize::from(*value)]))
            .collect();
        assert!(submit(
            root.join("public"),
            root.join("private"),
            "wrong-campaign-token",
            &guess
        )
        .is_err());
        assert!(submit(
            root.join("public"),
            root.join("private"),
            &public.campaign_token,
            "not-hex"
        )
        .is_err());
        let first = match submit(
            root.join("public"),
            root.join("private"),
            &public.campaign_token,
            &guess,
        ) {
            Ok(value) => value,
            Err(error) => panic!("first judge submission failed: {error}"),
        };
        assert!(first.submission_recorded);
        assert!(first.accepted);
        let second = match submit(
            root.join("public"),
            root.join("private"),
            &public.campaign_token,
            &guess,
        ) {
            Ok(value) => value,
            Err(error) => panic!("second judge invocation failed: {error}"),
        };
        assert!(!second.submission_recorded);
        assert!(!second.accepted);
        let _cleanup = std::fs::remove_dir_all(root);
    }
}
