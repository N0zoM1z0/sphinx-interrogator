//! Public profile configuration.

use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

/// Error returned while loading a profile.
#[derive(Debug)]
pub enum ProfileError {
    /// The profile file could not be read.
    Io(std::io::Error),
    /// The TOML document could not be decoded.
    Decode(toml::de::Error),
    /// A semantic profile invariant was violated.
    Invalid(String),
}

impl std::fmt::Display for ProfileError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "could not read profile: {error}"),
            Self::Decode(error) => write!(formatter, "could not decode profile: {error}"),
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

/// Public challenge profile shared through the protocol.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Profile {
    /// Profile file schema version.
    pub profile_version: String,
    /// Human-readable profile name.
    pub name: String,
    /// Semantic version of profile behavior.
    pub semantic_version: String,
    /// Number of public probe lanes.
    pub lanes: usize,
    /// Number of four-bit secret cells.
    pub secret_cells: usize,
    /// Whether the private challenge includes a hidden lane permutation.
    pub hidden_permutation: bool,
    /// Whether the private challenge includes hidden per-lane salts.
    pub hidden_salts: bool,
    /// Fault implementation mode (`reference` or `off` in version 1).
    pub fault_mode: String,
    /// Width of the public timing bucket.
    pub bucket_width: u64,
    /// Noise model name.
    pub noise_mode: String,
    /// Magnitude of ordinary bounded jitter.
    pub noise_bound: i64,
    /// Probability of a research-profile outlier.
    #[serde(default)]
    pub outlier_probability: f64,
    /// Magnitude of a research-profile outlier.
    #[serde(default)]
    pub outlier_bound: i64,
    /// Microarchitectural fields preserved by soft reset.
    #[serde(default)]
    pub soft_reset_preserves: Vec<String>,
    /// Number of hard resets available to a challenge.
    pub hard_reset_budget: u64,
    /// Logical relation-query budget.
    pub logical_query_budget: u64,
    /// Physical execution budget.
    pub physical_execution_budget: u64,
    /// Static instruction-count limit.
    pub max_program_instructions: usize,
    /// Dynamic gas limit.
    pub max_gas: u64,
    /// Whether private diagnostics were compiled into this server.
    pub server_diagnostics: bool,
}

impl Profile {
    /// Load and validate a profile from TOML.
    pub fn load(path: impl AsRef<Path>) -> Result<Self, ProfileError> {
        let text = fs::read_to_string(path)?;
        let profile: Self = toml::from_str(&text)?;
        profile.validate()?;
        Ok(profile)
    }

    /// Validate invariants needed by the scaffold implementation.
    pub fn validate(&self) -> Result<(), ProfileError> {
        if self.profile_version != "1.0" {
            return Err(ProfileError::Invalid(format!(
                "unsupported profile version {}",
                self.profile_version
            )));
        }
        if !(1..=64).contains(&self.lanes) {
            return Err(ProfileError::Invalid(
                "lanes must be between 1 and 64".to_owned(),
            ));
        }
        if !(1..=64).contains(&self.secret_cells) {
            return Err(ProfileError::Invalid(
                "secret_cells must be between 1 and 64".to_owned(),
            ));
        }
        if self.bucket_width == 0 {
            return Err(ProfileError::Invalid(
                "bucket_width must be positive".to_owned(),
            ));
        }
        if self.noise_bound < 0 {
            return Err(ProfileError::Invalid(
                "noise_bound must be non-negative".to_owned(),
            ));
        }
        if !matches!(self.fault_mode.as_str(), "reference" | "off") {
            return Err(ProfileError::Invalid(format!(
                "unsupported fault_mode {}",
                self.fault_mode
            )));
        }
        if self.server_diagnostics {
            return Err(ProfileError::Invalid(
                "public scaffold refuses profiles with server_diagnostics=true".to_owned(),
            ));
        }
        Ok(())
    }

    /// Return whether soft reset preserves a named microarchitectural field.
    #[must_use]
    pub fn preserves_on_soft_reset(&self, field: &str) -> bool {
        self.soft_reset_preserves.iter().any(|name| name == field)
    }
}
