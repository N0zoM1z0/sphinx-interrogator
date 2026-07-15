//! Domain-separated deterministic sampling for public observation-noise profiles.

use serde::{Deserialize, Serialize};
use sha2::{Digest as _, Sha256};

/// Publicly declared noise distribution family.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NoiseMode {
    /// No jitter.
    None,
    /// Uniform deterministic seeded jitter in `[-noise_bound, noise_bound]`.
    BoundedSeeded,
    /// Seeded bounded jitter with a declared bounded outlier mixture.
    BoundedMixture,
}

/// Public parameters and private key needed for one deterministic sample.
#[derive(Debug, Clone, Copy)]
pub struct NoiseConfiguration<'a> {
    /// Public distribution family.
    pub mode: NoiseMode,
    /// Public ordinary absolute bound.
    pub noise_bound: i64,
    /// Public outlier probability for mixture mode.
    pub outlier_probability: f64,
    /// Public mixture absolute bound.
    pub outlier_bound: i64,
    /// Private domain-separated 256-bit sampling key.
    pub private_key: &'a [u8; 32],
}

/// Public request schedule coordinates included in noise derivation.
#[derive(Debug, Clone, Copy)]
pub struct NoiseContext<'a> {
    /// Server-global physical execution ordinal.
    pub physical_execution: u64,
    /// Public session identifier.
    pub session_id: &'a str,
    /// Optional public execution-seed identifier.
    pub execution_seed_id: Option<&'a str>,
}

/// Sample one reproducible signed jitter value without mutable global RNG state.
#[must_use]
pub fn sample(configuration: NoiseConfiguration<'_>, context: NoiseContext<'_>) -> i64 {
    if configuration.mode == NoiseMode::None {
        return 0;
    }
    let mut hash = Sha256::new();
    hash.update(b"sphinx-observation-noise/v1\0");
    hash.update(configuration.private_key);
    hash.update(context.physical_execution.to_be_bytes());
    update_field(&mut hash, context.session_id.as_bytes());
    update_field(
        &mut hash,
        context.execution_seed_id.unwrap_or_default().as_bytes(),
    );
    let digest = hash.finalize();
    let selector = u64::from_be_bytes(digest[0..8].try_into().unwrap_or_default());
    let ordinary = u64::from_be_bytes(digest[8..16].try_into().unwrap_or_default());
    let outlier = u64::from_be_bytes(digest[16..24].try_into().unwrap_or_default());
    if configuration.mode == NoiseMode::BoundedMixture
        && mixture_selected(selector, configuration.outlier_probability)
    {
        symmetric(outlier, configuration.outlier_bound)
    } else {
        symmetric(ordinary, configuration.noise_bound)
    }
}

fn update_field(hash: &mut Sha256, value: &[u8]) {
    hash.update(u64::try_from(value.len()).unwrap_or(u64::MAX).to_be_bytes());
    hash.update(value);
}

fn mixture_selected(random: u64, probability: f64) -> bool {
    if probability <= 0.0 {
        return false;
    }
    if probability >= 1.0 {
        return true;
    }
    let scaled = probability * (u64::MAX as f64);
    (random as f64) <= scaled
}

fn symmetric(random: u64, bound: i64) -> i64 {
    let magnitude = bound.unsigned_abs();
    if magnitude == 0 {
        return 0;
    }
    let width = magnitude.saturating_mul(2).saturating_add(1);
    i64::try_from(random % width).unwrap_or_default() - bound
}

#[cfg(test)]
mod tests {
    use super::{sample, NoiseConfiguration, NoiseContext, NoiseMode};

    const KEY: [u8; 32] = [0x5a; 32];

    #[test]
    fn bounded_samples_are_reproducible_and_schedule_separated() {
        let configuration = NoiseConfiguration {
            mode: NoiseMode::BoundedSeeded,
            noise_bound: 2,
            outlier_probability: 0.0,
            outlier_bound: 0,
            private_key: &KEY,
        };
        let context = NoiseContext {
            physical_execution: 7,
            session_id: "session",
            execution_seed_id: Some("public-seed"),
        };
        let first = sample(configuration, context);
        assert_eq!(first, sample(configuration, context));
        assert!((-2..=2).contains(&first));
        assert_ne!(
            sample(
                configuration,
                NoiseContext {
                    physical_execution: 8,
                    ..context
                }
            ),
            sample(
                configuration,
                NoiseContext {
                    physical_execution: 9,
                    ..context
                }
            )
        );
    }

    #[test]
    fn forced_mixture_sample_respects_outlier_bound() {
        let value = sample(
            NoiseConfiguration {
                mode: NoiseMode::BoundedMixture,
                noise_bound: 1,
                outlier_probability: 1.0,
                outlier_bound: 8,
                private_key: &KEY,
            },
            NoiseContext {
                physical_execution: 0,
                session_id: "s",
                execution_seed_id: None,
            },
        );
        assert!((-8..=8).contains(&value));
    }
}
