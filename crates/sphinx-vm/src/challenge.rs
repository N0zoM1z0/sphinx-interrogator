//! Reproducible public/private challenge generation and strict loading.

use std::fs::{self, OpenOptions};
use std::io::Write as _;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};

use crate::fault::FaultVariant;
use crate::machine::PrivateMachineConfig;
use crate::mapping::BankMapping;
use crate::profile::{Profile, ProfileError};
use crate::protocol::PROTOCOL_VERSION;

const CHALLENGE_VERSION: &str = "1.0";
const PRIVATE_VERSION: &str = "1.0";

/// Public budget copy bound into challenge metadata.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ChallengeBudgets {
    /// Hard reset budget.
    pub hard_resets: u64,
    /// Logical query budget.
    pub logical_queries: u64,
    /// Physical execution budget.
    pub physical_executions: u64,
}

/// Public challenge metadata. It contains commitments but no private configuration.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicChallenge {
    /// Public challenge schema version.
    pub challenge_version: String,
    /// Public challenge identifier.
    pub challenge_id: String,
    /// SHA-256 of exact public profile bytes.
    pub profile_sha256: String,
    /// Salted non-oracular commitment to private material.
    pub commitment: String,
    /// Required public process protocol.
    pub protocol_version: String,
    /// One public final-submission campaign token.
    pub campaign_token: String,
    /// Public budget copy.
    pub budgets: ChallengeBudgets,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PrivateConfigFile {
    private_version: String,
    permutation: Vec<usize>,
    salts: Vec<u8>,
    fault_variant: FaultVariant,
    generation_root_seed_hex: String,
    noise_key_hex: String,
    commitment_nonce_hex: String,
}

struct LoadedMaterial {
    profile: Profile,
    public: PublicChallenge,
    private: PrivateConfigFile,
    secret: Vec<u8>,
    noise_key: [u8; 32],
}

/// Validated challenge material needed by the server, with no secret accessors.
#[derive(Debug, Clone)]
pub struct LoadedChallenge {
    /// Public profile.
    pub profile: Profile,
    /// Public challenge metadata.
    pub public: PublicChallenge,
    /// Opaque runtime-private machine configuration.
    pub private_machine: PrivateMachineConfig,
}

/// Options for creating one isolated challenge directory.
#[derive(Debug, Clone)]
pub struct CreateChallenge {
    /// Source public profile template.
    pub profile_path: PathBuf,
    /// New output directory; it must not already exist.
    pub output: PathBuf,
    /// Optional stable public identifier.
    pub challenge_id: Option<String>,
    /// Optional deterministic development/evaluation seed.
    pub seed: Option<u64>,
    /// Private fault assignment, absent from public metadata/profile.
    pub fault_variant: FaultVariant,
}

/// Challenge creation/loading failure.
#[derive(Debug)]
pub enum ChallengeError {
    /// File or permission failure.
    Io(std::io::Error),
    /// Public profile failure.
    Profile(ProfileError),
    /// Public/private JSON failure.
    Json(serde_json::Error),
    /// Private TOML decode failure.
    TomlDecode(toml::de::Error),
    /// Private TOML encode failure.
    TomlEncode(toml::ser::Error),
    /// OS entropy failure.
    Random(getrandom::Error),
    /// Semantic or integrity failure.
    Invalid(String),
}

impl std::fmt::Display for ChallengeError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "challenge file error: {error}"),
            Self::Profile(error) => write!(formatter, "challenge profile error: {error}"),
            Self::Json(error) => write!(formatter, "challenge JSON error: {error}"),
            Self::TomlDecode(error) => write!(formatter, "private config decode error: {error}"),
            Self::TomlEncode(error) => write!(formatter, "private config encode error: {error}"),
            Self::Random(error) => write!(formatter, "challenge entropy error: {error}"),
            Self::Invalid(message) => write!(formatter, "invalid challenge: {message}"),
        }
    }
}

impl std::error::Error for ChallengeError {}

impl From<std::io::Error> for ChallengeError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<ProfileError> for ChallengeError {
    fn from(value: ProfileError) -> Self {
        Self::Profile(value)
    }
}

impl From<serde_json::Error> for ChallengeError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

impl From<toml::de::Error> for ChallengeError {
    fn from(value: toml::de::Error) -> Self {
        Self::TomlDecode(value)
    }
}

impl From<toml::ser::Error> for ChallengeError {
    fn from(value: toml::ser::Error) -> Self {
        Self::TomlEncode(value)
    }
}

/// Create a complete new challenge without overwriting existing material.
pub fn create(options: &CreateChallenge) -> Result<PublicChallenge, ChallengeError> {
    let profile = Profile::load(&options.profile_path)?;
    let profile_text = profile.canonical_toml()?;
    let profile_hash = sha256_hex(profile_text.as_bytes());
    let root_seed = root_seed(options.seed)?;
    let challenge_id = options.challenge_id.clone().unwrap_or_else(|| {
        format!(
            "challenge-{}",
            &hex_encode(&derive(&root_seed, b"challenge-id", &[]))[..16]
        )
    });
    validate_public_id("challenge_id", &challenge_id)?;
    let campaign_token = format!(
        "campaign-{}",
        &hex_encode(&derive(
            &root_seed,
            b"campaign-token",
            challenge_id.as_bytes()
        ))[..24]
    );

    let secret = derive_secret(&root_seed, profile.secret_cells);
    let permutation = derive_permutation(&root_seed, &profile);
    let salts = derive_salts(&root_seed, &profile);
    validate_private_mapping(&profile, &permutation, &salts)?;
    let noise_key = derive(&root_seed, b"noise-key", challenge_id.as_bytes());
    let nonce = derive(&root_seed, b"commitment-nonce", challenge_id.as_bytes());
    let commitment = commitment(
        &challenge_id,
        &profile_hash,
        &secret,
        &permutation,
        &salts,
        options.fault_variant,
        &root_seed,
        &noise_key,
        &nonce,
    );
    let public = PublicChallenge {
        challenge_version: CHALLENGE_VERSION.to_owned(),
        challenge_id,
        profile_sha256: profile_hash,
        commitment,
        protocol_version: PROTOCOL_VERSION.to_owned(),
        campaign_token,
        budgets: ChallengeBudgets {
            hard_resets: profile.hard_reset_budget,
            logical_queries: profile.logical_query_budget,
            physical_executions: profile.physical_execution_budget,
        },
    };
    let private = PrivateConfigFile {
        private_version: PRIVATE_VERSION.to_owned(),
        permutation,
        salts,
        fault_variant: options.fault_variant,
        generation_root_seed_hex: hex_encode(&root_seed),
        noise_key_hex: hex_encode(&noise_key),
        commitment_nonce_hex: hex_encode(&nonce),
    };

    create_tree(&options.output)?;
    write_new(&options.output.join("private/secret.bin"), &secret, 0o600)?;
    let private_text = toml::to_string_pretty(&private)?;
    write_new(
        &options.output.join("private/config.toml"),
        private_text.as_bytes(),
        0o600,
    )?;
    write_new(
        &options.output.join("public/profile.toml"),
        profile_text.as_bytes(),
        0o644,
    )?;
    let mut public_text = serde_json::to_string_pretty(&public)?;
    public_text.push('\n');
    write_new(
        &options.output.join("public/challenge.json"),
        public_text.as_bytes(),
        0o644,
    )?;
    Ok(public)
}

/// Load and integrity-check all server material from one challenge directory.
pub fn load(root: impl AsRef<Path>) -> Result<LoadedChallenge, ChallengeError> {
    let material = load_material(root.as_ref())?;
    let mapping = BankMapping::new(
        material.secret,
        material.private.permutation,
        material.private.salts,
        material.profile.lanes,
    )
    .map_err(ChallengeError::Invalid)?;
    Ok(LoadedChallenge {
        profile: material.profile,
        public: material.public,
        private_machine: PrivateMachineConfig::new(
            mapping,
            material.private.fault_variant,
            material.noise_key,
        ),
    })
}

pub(crate) fn judge_material(root: &Path) -> Result<(PublicChallenge, Vec<u8>), ChallengeError> {
    let material = load_material(root)?;
    Ok((material.public, material.secret))
}

fn load_material(root: &Path) -> Result<LoadedMaterial, ChallengeError> {
    let profile_path = root.join("public/profile.toml");
    let profile_text = fs::read_to_string(&profile_path)?;
    let profile = Profile::from_toml(&profile_text)?;
    let public: PublicChallenge =
        serde_json::from_slice(&fs::read(root.join("public/challenge.json"))?)?;
    validate_public(&profile, &profile_text, &public)?;
    let private: PrivateConfigFile =
        toml::from_str(&fs::read_to_string(root.join("private/config.toml"))?)?;
    if private.private_version != PRIVATE_VERSION {
        return Err(invalid(format!(
            "unsupported private version {}",
            private.private_version
        )));
    }
    validate_private_mapping(&profile, &private.permutation, &private.salts)?;
    let secret = fs::read(root.join("private/secret.bin"))?;
    if secret.len() != profile.secret_cells || secret.iter().any(|value| *value > 15) {
        return Err(invalid(
            "secret.bin does not match the public cell contract",
        ));
    }
    let noise_key = decode_32("noise_key_hex", &private.noise_key_hex)?;
    let generation_root_seed = decode_32(
        "generation_root_seed_hex",
        &private.generation_root_seed_hex,
    )?;
    let nonce = decode_32("commitment_nonce_hex", &private.commitment_nonce_hex)?;
    let expected = commitment(
        &public.challenge_id,
        &public.profile_sha256,
        &secret,
        &private.permutation,
        &private.salts,
        private.fault_variant,
        &generation_root_seed,
        &noise_key,
        &nonce,
    );
    if !constant_time_equal(expected.as_bytes(), public.commitment.as_bytes()) {
        return Err(invalid("private material does not match public commitment"));
    }
    Ok(LoadedMaterial {
        profile,
        public,
        private,
        secret,
        noise_key,
    })
}

fn validate_public(
    profile: &Profile,
    profile_text: &str,
    public: &PublicChallenge,
) -> Result<(), ChallengeError> {
    if public.challenge_version != CHALLENGE_VERSION {
        return Err(invalid(format!(
            "unsupported challenge version {}",
            public.challenge_version
        )));
    }
    if public.protocol_version != PROTOCOL_VERSION {
        return Err(invalid(format!(
            "challenge protocol {} does not match server {PROTOCOL_VERSION}",
            public.protocol_version
        )));
    }
    validate_public_id("challenge_id", &public.challenge_id)?;
    validate_public_id("campaign_token", &public.campaign_token)?;
    if public.profile_sha256 != sha256_hex(profile_text.as_bytes()) {
        return Err(invalid("public profile hash mismatch"));
    }
    let expected_budgets = ChallengeBudgets {
        hard_resets: profile.hard_reset_budget,
        logical_queries: profile.logical_query_budget,
        physical_executions: profile.physical_execution_budget,
    };
    if public.budgets != expected_budgets {
        return Err(invalid("public challenge budgets do not match profile"));
    }
    if public.commitment.len() != 64
        || !public
            .commitment
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(invalid("commitment is not lowercase SHA-256"));
    }
    Ok(())
}

fn validate_private_mapping(
    profile: &Profile,
    permutation: &[usize],
    salts: &[u8],
) -> Result<(), ChallengeError> {
    if permutation.len() != profile.lanes || salts.len() != profile.lanes {
        return Err(invalid(
            "private mapping length does not match public lanes",
        ));
    }
    let identity: Vec<usize> = (0..profile.lanes).collect();
    if profile.hidden_permutation {
        let mut sorted = permutation.to_vec();
        sorted.sort_unstable();
        if sorted != identity {
            return Err(invalid("hidden permutation is not a lane bijection"));
        }
    } else if permutation != identity {
        return Err(invalid(
            "profile disables hidden permutation but private mapping is non-identity",
        ));
    }
    if salts.iter().any(|salt| *salt > 15) {
        return Err(invalid("private salt does not fit in four bits"));
    }
    if profile.hidden_salts {
        if salts.contains(&0) {
            return Err(invalid("enabled hidden salts must be nonzero"));
        }
    } else if salts.iter().any(|salt| *salt != 0) {
        return Err(invalid(
            "profile disables hidden salts but private salt is nonzero",
        ));
    }
    Ok(())
}

fn create_tree(root: &Path) -> Result<(), ChallengeError> {
    if root.exists() {
        return Err(invalid(format!(
            "output directory already exists: {}",
            root.display()
        )));
    }
    if let Some(parent) = root.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::create_dir(root)?;
    fs::create_dir(root.join("public"))?;
    fs::create_dir(root.join("private"))?;
    fs::create_dir(root.join("private/judge-used"))?;
    set_mode(root, 0o755)?;
    set_mode(&root.join("public"), 0o755)?;
    set_mode(&root.join("private"), 0o700)?;
    set_mode(&root.join("private/judge-used"), 0o700)?;
    Ok(())
}

fn write_new(path: &Path, data: &[u8], mode: u32) -> Result<(), ChallengeError> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt as _;
        options.mode(mode);
    }
    let mut file = options.open(path)?;
    file.write_all(data)?;
    file.sync_all()?;
    set_mode(path, mode)?;
    Ok(())
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> Result<(), ChallengeError> {
    use std::os::unix::fs::PermissionsExt as _;

    fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
    Ok(())
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) -> Result<(), ChallengeError> {
    Ok(())
}

fn root_seed(seed: Option<u64>) -> Result<[u8; 32], ChallengeError> {
    if let Some(seed) = seed {
        let mut hash = Sha256::new();
        hash.update(b"sphinx-development-root-seed/v1\0");
        hash.update(seed.to_be_bytes());
        return Ok(hash.finalize().into());
    }
    let mut seed = [0_u8; 32];
    getrandom::getrandom(&mut seed).map_err(ChallengeError::Random)?;
    Ok(seed)
}

fn derive(root: &[u8; 32], domain: &[u8], context: &[u8]) -> [u8; 32] {
    let mut hash = Sha256::new();
    hash.update(b"sphinx-challenge-derivation/v1\0");
    hash.update(
        u64::try_from(domain.len())
            .unwrap_or(u64::MAX)
            .to_be_bytes(),
    );
    hash.update(domain);
    hash.update(root);
    hash.update(
        u64::try_from(context.len())
            .unwrap_or(u64::MAX)
            .to_be_bytes(),
    );
    hash.update(context);
    hash.finalize().into()
}

fn derive_secret(root: &[u8; 32], cells: usize) -> Vec<u8> {
    (0..cells)
        .map(|index| {
            let context = u64::try_from(index).unwrap_or(u64::MAX).to_be_bytes();
            derive(root, b"secret-cell", &context)[0] & 0x0f
        })
        .collect()
}

fn derive_permutation(root: &[u8; 32], profile: &Profile) -> Vec<usize> {
    let mut permutation: Vec<usize> = (0..profile.lanes).collect();
    if profile.hidden_permutation {
        for index in (1..permutation.len()).rev() {
            let context = u64::try_from(index).unwrap_or(u64::MAX).to_be_bytes();
            let block = derive(root, b"lane-permutation", &context);
            let random = u64::from_be_bytes(block[0..8].try_into().unwrap_or_default());
            let modulus = u64::try_from(index + 1).unwrap_or(u64::MAX);
            let selected = usize::try_from(random % modulus).unwrap_or_default();
            permutation.swap(index, selected);
        }
    }
    permutation
}

fn derive_salts(root: &[u8; 32], profile: &Profile) -> Vec<u8> {
    if !profile.hidden_salts {
        return vec![0; profile.lanes];
    }
    (0..profile.lanes)
        .map(|index| {
            let context = u64::try_from(index).unwrap_or(u64::MAX).to_be_bytes();
            1 + (derive(root, b"lane-salt", &context)[0] % 15)
        })
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn commitment(
    challenge_id: &str,
    profile_hash: &str,
    secret: &[u8],
    permutation: &[usize],
    salts: &[u8],
    fault_variant: FaultVariant,
    generation_root_seed: &[u8; 32],
    noise_key: &[u8; 32],
    nonce: &[u8; 32],
) -> String {
    let mut hash = Sha256::new();
    hash.update(b"sphinx-challenge-commitment/v1\0");
    update_hash_field(&mut hash, challenge_id.as_bytes());
    update_hash_field(&mut hash, profile_hash.as_bytes());
    update_hash_field(&mut hash, secret);
    hash.update(
        u64::try_from(permutation.len())
            .unwrap_or(u64::MAX)
            .to_be_bytes(),
    );
    for lane in permutation {
        hash.update(u64::try_from(*lane).unwrap_or(u64::MAX).to_be_bytes());
    }
    update_hash_field(&mut hash, salts);
    update_hash_field(&mut hash, fault_variant.to_string().as_bytes());
    hash.update(generation_root_seed);
    hash.update(noise_key);
    hash.update(nonce);
    hex_encode(&hash.finalize())
}

fn update_hash_field(hash: &mut Sha256, value: &[u8]) {
    hash.update(u64::try_from(value.len()).unwrap_or(u64::MAX).to_be_bytes());
    hash.update(value);
}

fn validate_public_id(role: &str, value: &str) -> Result<(), ChallengeError> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-'))
    {
        Err(invalid(format!("{role} is not a valid public identifier")))
    } else {
        Ok(())
    }
}

fn decode_32(role: &str, value: &str) -> Result<[u8; 32], ChallengeError> {
    if value.len() != 64 {
        return Err(invalid(format!(
            "{role} must contain 64 lowercase hex digits"
        )));
    }
    let mut output = [0_u8; 32];
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        let high = hex_digit(pair[0]).ok_or_else(|| invalid(format!("invalid {role}")))?;
        let low = hex_digit(pair[1]).ok_or_else(|| invalid(format!("invalid {role}")))?;
        output[index] = (high << 4) | low;
    }
    Ok(output)
}

fn hex_digit(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        _ => None,
    }
}

pub(crate) fn hex_encode(value: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(value.len().saturating_mul(2));
    for byte in value {
        output.push(char::from(HEX[usize::from(*byte >> 4)]));
        output.push(char::from(HEX[usize::from(*byte & 0x0f)]));
    }
    output
}

fn sha256_hex(value: &[u8]) -> String {
    hex_encode(&Sha256::digest(value))
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

fn invalid(message: impl Into<String>) -> ChallengeError {
    ChallengeError::Invalid(message.into())
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::{create, derive, load, root_seed, CreateChallenge};
    use crate::fault::FaultVariant;

    static NEXT_PATH: AtomicU64 = AtomicU64::new(0);

    fn temporary_path(label: &str) -> std::path::PathBuf {
        let ordinal = NEXT_PATH.fetch_add(1, Ordering::Relaxed);
        std::env::temp_dir().join(format!(
            "sphinx-vm-{label}-{}-{ordinal}",
            std::process::id()
        ))
    }

    fn tutorial_profile() -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../benchmarks/profiles/tutorial.toml")
    }

    #[test]
    fn deterministic_generation_separates_public_and_private_material() {
        let root = temporary_path("challenge");
        let options = CreateChallenge {
            profile_path: tutorial_profile(),
            output: root.clone(),
            challenge_id: Some("test-challenge".to_owned()),
            seed: Some(7),
            fault_variant: FaultVariant::Reference,
        };
        let public = match create(&options) {
            Ok(value) => value,
            Err(error) => panic!("challenge should be created: {error}"),
        };
        assert!(root.join("public/profile.toml").is_file());
        assert!(root.join("public/challenge.json").is_file());
        assert!(root.join("private/secret.bin").is_file());
        assert!(root.join("private/config.toml").is_file());
        let public_text = std::fs::read_to_string(root.join("public/challenge.json"));
        let public_text = match public_text {
            Ok(value) => value,
            Err(error) => panic!("public metadata should be readable: {error}"),
        };
        assert!(!public_text.contains("fault_variant"));
        assert!(!public_text.contains("noise_key"));
        assert!(!public_text.contains("permutation"));
        assert_eq!(public.challenge_id, "test-challenge");
        assert!(load(&root).is_ok());

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt as _;

            let private_mode = match std::fs::metadata(root.join("private")) {
                Ok(metadata) => metadata.permissions().mode() & 0o777,
                Err(error) => panic!("private directory metadata failed: {error}"),
            };
            let secret_mode = match std::fs::metadata(root.join("private/secret.bin")) {
                Ok(metadata) => metadata.permissions().mode() & 0o777,
                Err(error) => panic!("secret metadata failed: {error}"),
            };
            assert_eq!(private_mode, 0o700);
            assert_eq!(secret_mode, 0o600);
        }
        let _cleanup = std::fs::remove_dir_all(root);
    }

    #[test]
    fn tampering_with_public_or_private_material_is_detected() {
        let root = temporary_path("tamper");
        let options = CreateChallenge {
            profile_path: tutorial_profile(),
            output: root.clone(),
            challenge_id: Some("tamper-test".to_owned()),
            seed: Some(11),
            fault_variant: FaultVariant::Weak,
        };
        if let Err(error) = create(&options) {
            panic!("challenge should be created: {error}");
        }
        let secret_path = root.join("private/secret.bin");
        let mut secret = match std::fs::read(&secret_path) {
            Ok(value) => value,
            Err(error) => panic!("secret should be readable: {error}"),
        };
        secret[0] ^= 1;
        if let Err(error) = std::fs::write(&secret_path, secret) {
            panic!("test tamper write failed: {error}");
        }
        assert!(load(&root).is_err());
        let _cleanup = std::fs::remove_dir_all(root);
    }

    #[test]
    fn commitment_binds_the_complete_private_machine_configuration() {
        let root = temporary_path("private-config-tamper");
        let options = CreateChallenge {
            profile_path: tutorial_profile(),
            output: root.clone(),
            challenge_id: Some("private-config-tamper".to_owned()),
            seed: Some(13),
            fault_variant: FaultVariant::Weak,
        };
        if let Err(error) = create(&options) {
            panic!("challenge should be created: {error}");
        }
        let config_path = root.join("private/config.toml");
        let config = match std::fs::read_to_string(&config_path) {
            Ok(value) => value,
            Err(error) => panic!("private config should be readable: {error}"),
        };
        let tampered = config.replace("fault_variant = \"weak\"", "fault_variant = \"signed\"");
        assert_ne!(tampered, config);
        if let Err(error) = std::fs::write(&config_path, tampered) {
            panic!("test tamper write failed: {error}");
        }
        assert!(load(&root).is_err());
        let _cleanup = std::fs::remove_dir_all(root);
    }

    #[test]
    fn challenge_derivations_use_distinct_domains() {
        let root = match root_seed(Some(23)) {
            Ok(value) => value,
            Err(error) => panic!("deterministic root seed should succeed: {error}"),
        };
        let index = 0_u64.to_be_bytes();
        let secret_block = derive(&root, b"secret-cell", &index);
        let noise_key = derive(&root, b"noise-key", b"domain-test");
        let nonce = derive(&root, b"commitment-nonce", b"domain-test");
        assert_ne!(secret_block, noise_key);
        assert_ne!(secret_block, nonce);
        assert_ne!(noise_key, nonce);
    }
}
