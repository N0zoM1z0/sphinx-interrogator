//! Strict public challenge-profile contract with no private fault or seed fields.

use std::collections::HashSet;
use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::microarchitecture::MicroStateField;
use crate::noise::NoiseMode;

/// Error returned while loading or serializing a public profile.
#[derive(Debug)]
pub enum ProfileError {
    /// The profile file could not be read or written.
    Io(std::io::Error),
    /// The TOML document could not be decoded.
    Decode(toml::de::Error),
    /// The TOML document could not be encoded.
    Encode(toml::ser::Error),
    /// A semantic profile invariant was violated.
    Invalid(String),
}

impl std::fmt::Display for ProfileError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "could not access profile: {error}"),
            Self::Decode(error) => write!(formatter, "could not decode profile: {error}"),
            Self::Encode(error) => write!(formatter, "could not encode profile: {error}"),
            Self::Invalid(message) => write!(formatter, "invalid profile: {message}"),
        }
    }
}

impl std::error::Error for ProfileError {}

impl From<std::io::Error> for ProfileError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<toml::de::Error> for ProfileError {
    fn from(value: toml::de::Error) -> Self {
        Self::Decode(value)
    }
}

impl From<toml::ser::Error> for ProfileError {
    fn from(value: toml::ser::Error) -> Self {
        Self::Encode(value)
    }
}

/// Public challenge profile serialized into the public challenge directory.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    /// Public profile schema version.
    pub profile_version: String,
    /// Public family name. It must not reveal a blind fault-control assignment.
    pub name: String,
    /// Semantic behavior version.
    pub semantic_version: String,
    /// Number of public probe lanes.
    pub lanes: usize,
    /// Number of four-bit recovery cells.
    pub secret_cells: usize,
    /// Whether a private lane permutation exists in this public family.
    pub hidden_permutation: bool,
    /// Whether private per-lane salts exist in this public family.
    pub hidden_salts: bool,
    /// Public quantization width.
    pub bucket_width: u64,
    /// Public noise family.
    pub noise_mode: NoiseMode,
    /// Public ordinary jitter bound.
    pub noise_bound: i64,
    /// Public mixture probability.
    #[serde(default)]
    pub outlier_probability: f64,
    /// Public mixture outlier bound.
    #[serde(default)]
    pub outlier_bound: i64,
    /// Exact hidden fields retained across soft reset.
    #[serde(default)]
    pub soft_reset_preserves: Vec<MicroStateField>,
    /// Public hard-reset budget.
    pub hard_reset_budget: u64,
    /// Public logical-query budget.
    pub logical_query_budget: u64,
    /// Public physical-execution budget.
    pub physical_execution_budget: u64,
    /// Public encoded instruction limit.
    pub max_program_instructions: usize,
    /// Public dynamic gas limit.
    pub max_gas: u64,
}

impl Profile {
    /// Load and validate a public profile from TOML.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, ProfileError> {
        let text = fs::read_to_string(path)?;
        Self::from_toml(&text)
    }

    /// Decode and validate public profile text.
    pub fn from_toml(text: &str) -> Result<Self, ProfileError> {
        let profile: Self = toml::from_str(text)?;
        profile.validate()?;
        Ok(profile)
    }

    /// Serialize canonical public profile text.
    pub fn canonical_toml(&self) -> Result<String, ProfileError> {
        self.validate()?;
        Ok(toml::to_string_pretty(self)?)
    }

    /// Validate all public invariants and contradictory noise/reset settings.
    pub fn validate(&self) -> Result<(), ProfileError> {
        if self.profile_version != "1.0" {
            return Err(invalid(format!(
                "unsupported profile version {}",
                self.profile_version
            )));
        }
        if self.name.is_empty() || self.name.len() > 128 {
            return Err(invalid("name must contain 1..128 bytes"));
        }
        if self.semantic_version.is_empty() || self.semantic_version.len() > 64 {
            return Err(invalid("semantic_version must contain 1..64 bytes"));
        }
        if !(1..=64).contains(&self.lanes) {
            return Err(invalid("lanes must be between 1 and 64"));
        }
        if !(1..=64).contains(&self.secret_cells) {
            return Err(invalid("secret_cells must be between 1 and 64"));
        }
        if self.lanes != self.secret_cells {
            return Err(invalid(
                "version 1 requires one public lane per secret cell",
            ));
        }
        if self.bucket_width == 0 {
            return Err(invalid("bucket_width must be positive"));
        }
        if !(0..=1_000_000).contains(&self.noise_bound) {
            return Err(invalid("noise_bound must be in 0..=1000000"));
        }
        if !(0..=1_000_000).contains(&self.outlier_bound) {
            return Err(invalid("outlier_bound must be in 0..=1000000"));
        }
        if !self.outlier_probability.is_finite() || !(0.0..=1.0).contains(&self.outlier_probability)
        {
            return Err(invalid("outlier_probability must be finite in 0..=1"));
        }
        match self.noise_mode {
            NoiseMode::None
                if self.noise_bound != 0
                    || self.outlier_probability != 0.0
                    || self.outlier_bound != 0 =>
            {
                return Err(invalid(
                    "noise_mode=none requires all noise parameters to be zero",
                ));
            }
            NoiseMode::BoundedSeeded
                if self.outlier_probability != 0.0 || self.outlier_bound != 0 =>
            {
                return Err(invalid(
                    "bounded_seeded does not permit mixture outlier parameters",
                ));
            }
            NoiseMode::BoundedMixture
                if self.outlier_probability <= 0.0 || self.outlier_bound <= self.noise_bound =>
            {
                return Err(invalid(
                    "bounded_mixture requires positive probability and outlier_bound > noise_bound",
                ));
            }
            _ => {}
        }
        let mut fields = HashSet::new();
        if self
            .soft_reset_preserves
            .iter()
            .any(|field| !fields.insert(*field))
        {
            return Err(invalid("soft_reset_preserves contains a duplicate field"));
        }
        if self.logical_query_budget == 0 || self.physical_execution_budget == 0 {
            return Err(invalid(
                "logical and physical execution budgets must be positive",
            ));
        }
        if !(1..=4096).contains(&self.max_program_instructions) {
            return Err(invalid("max_program_instructions must be in 1..=4096"));
        }
        if self.max_gas == 0 || self.max_gas > 1_000_000_000 {
            return Err(invalid("max_gas must be in 1..=1000000000"));
        }
        Ok(())
    }

    /// Return whether soft reset preserves one typed hidden field.
    #[must_use]
    pub fn preserves_on_soft_reset(&self, field: MicroStateField) -> bool {
        self.soft_reset_preserves.contains(&field)
    }
}

fn invalid(message: impl Into<String>) -> ProfileError {
    ProfileError::Invalid(message.into())
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::Profile;

    fn profile_path(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../benchmarks/profiles")
            .join(name)
    }

    #[test]
    fn all_public_profiles_round_trip_without_private_fields() {
        for name in [
            "tutorial.toml",
            "standard.toml",
            "research.toml",
            "fault_free.toml",
        ] {
            let profile = match Profile::load(profile_path(name)) {
                Ok(value) => value,
                Err(error) => panic!("profile {name} should validate: {error}"),
            };
            let rendered = match profile.canonical_toml() {
                Ok(value) => value,
                Err(error) => panic!("profile {name} should serialize: {error}"),
            };
            assert!(!rendered.contains("fault"));
            assert!(!rendered.contains("noise_key"));
            assert!(!rendered.contains("challenge_seed"));
            assert!(!rendered.contains("commitment_nonce"));
            assert!(!rendered.contains("diagnostic"));
            let decoded = match Profile::from_toml(&rendered) {
                Ok(value) => value,
                Err(error) => panic!("rendered profile {name} should decode: {error}"),
            };
            assert_eq!(decoded, profile);
        }
        let standard = std::fs::read(profile_path("standard.toml"));
        let control = std::fs::read(profile_path("fault_free.toml"));
        match (standard, control) {
            (Ok(standard), Ok(control)) => assert_eq!(standard, control),
            (Err(error), _) | (_, Err(error)) => {
                panic!("blind-control profile should be readable: {error}")
            }
        }
    }

    #[test]
    fn rejects_private_unknown_and_contradictory_noise_fields() {
        let source = std::fs::read_to_string(profile_path("tutorial.toml"));
        let source = match source {
            Ok(value) => value,
            Err(error) => panic!("tutorial profile should be readable: {error}"),
        };
        let private = format!("{source}\nfault_variant = \"off\"\n");
        assert!(Profile::from_toml(&private).is_err());
        let contradictory = source.replace("noise_bound = 0", "noise_bound = 1");
        assert!(Profile::from_toml(&contradictory).is_err());
    }
}
