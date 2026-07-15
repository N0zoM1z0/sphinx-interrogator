//! Typed private secret mapping into the public synthetic bank family.

use crate::microarchitecture::Bank;

/// Public four-bit S-box specified by the SphinxVM model.
pub const SBOX4: [u8; 16] = [6, 11, 0, 4, 13, 3, 15, 8, 10, 2, 5, 12, 1, 14, 7, 9];

/// A validated four-bit value.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Nibble(u8);

impl Nibble {
    /// Construct a four-bit value.
    pub fn new(value: u8) -> Result<Self, &'static str> {
        if value <= 15 {
            Ok(Self(value))
        } else {
            Err("nibble must fit in four bits")
        }
    }

    /// Return the numeric nibble.
    #[must_use]
    pub fn get(self) -> u8 {
        self.0
    }
}

/// Validated private mapping parameters for all public lanes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BankMapping {
    secret: Vec<Nibble>,
    permutation: Vec<usize>,
    salts: Vec<Nibble>,
}

impl BankMapping {
    /// Validate private cells, lane permutation, and salts.
    pub fn new(
        secret: Vec<u8>,
        permutation: Vec<usize>,
        salts: Vec<u8>,
        lanes: usize,
    ) -> Result<Self, String> {
        if secret.is_empty() {
            return Err("secret must contain at least one cell".to_owned());
        }
        if permutation.len() != lanes || salts.len() != lanes {
            return Err(format!(
                "private mapping has {} permutation entries and {} salts for {lanes} lanes",
                permutation.len(),
                salts.len()
            ));
        }
        if let Some(index) = permutation.iter().find(|index| **index >= secret.len()) {
            return Err(format!("permutation index {index} is outside the secret"));
        }
        let secret = secret
            .into_iter()
            .map(|value| Nibble::new(value).map_err(str::to_owned))
            .collect::<Result<Vec<_>, _>>()?;
        let salts = salts
            .into_iter()
            .map(|value| Nibble::new(value).map_err(str::to_owned))
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Self {
            secret,
            permutation,
            salts,
        })
    }

    /// Build identity-lane, zero-salt parameters for deterministic tests.
    pub fn identity(secret: Vec<u8>, lanes: usize) -> Result<Self, String> {
        if secret.len() != lanes {
            return Err("identity mapping requires one secret cell per lane".to_owned());
        }
        Self::new(secret, (0..lanes).collect(), vec![0; lanes], lanes)
    }

    /// Resolve one documented S-box projection.
    #[must_use]
    pub fn bank(&self, lane: usize, token: u8, epoch: u8) -> Option<Bank> {
        if token > 15 || epoch > 1 {
            return None;
        }
        let secret_index = *self.permutation.get(lane)?;
        let secret = self.secret.get(secret_index)?.get();
        let salt = self.salts.get(lane)?.get();
        let input = secret ^ token ^ salt;
        Bank::new((SBOX4[usize::from(input)] >> (2 * epoch)) & 0b11).ok()
    }

    /// Return the number of private secret cells without revealing them.
    #[must_use]
    pub fn secret_cells(&self) -> usize {
        self.secret.len()
    }
}

#[cfg(test)]
mod tests {
    use super::{BankMapping, SBOX4};

    #[test]
    fn exhaustive_epochs_reconstruct_every_public_sbox_value() {
        assert_eq!(
            SBOX4
                .iter()
                .copied()
                .collect::<std::collections::BTreeSet<_>>()
                .len(),
            16
        );
        for secret in 0..=15 {
            for token in 0..=15 {
                let mapping = match BankMapping::identity(vec![secret], 1) {
                    Ok(value) => value,
                    Err(error) => panic!("identity mapping should validate: {error}"),
                };
                let low = mapping.bank(0, token, 0).map(|bank| bank.get());
                let high = mapping.bank(0, token, 1).map(|bank| bank.get());
                let expected = SBOX4[usize::from(secret ^ token)];
                assert_eq!(low, Some(expected & 0b11));
                assert_eq!(high, Some((expected >> 2) & 0b11));
            }
        }
    }

    #[test]
    fn permutation_and_salt_are_applied_before_the_sbox() {
        let mapping = match BankMapping::new(vec![1, 14], vec![1, 0], vec![3, 5], 2) {
            Ok(value) => value,
            Err(error) => panic!("mapping should validate: {error}"),
        };
        let expected = SBOX4[usize::from(14_u8 ^ 7 ^ 3)] & 0b11;
        assert_eq!(mapping.bank(0, 7, 0).map(|bank| bank.get()), Some(expected));
    }
}
