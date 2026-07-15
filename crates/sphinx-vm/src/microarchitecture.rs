//! Pure hidden microarchitectural state transition, independent of fault policy.

use serde::{Deserialize, Serialize};

use crate::microcode::VaultRequest;

/// A validated two-bit synthetic bank.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Bank(u8);

impl Bank {
    /// Construct a bank in `0..=3`.
    pub fn new(value: u8) -> Result<Self, &'static str> {
        if value <= 3 {
            Ok(Self(value))
        } else {
            Err("bank must fit in two bits")
        }
    }

    /// Return the numeric bank.
    #[must_use]
    pub fn get(self) -> u8 {
        self.0
    }
}

/// Hidden fields a public profile may preserve across soft reset.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MicroStateField {
    /// Two-bit phase.
    Phase,
    /// Most recent secret probe bank.
    LastBank,
    /// Two-bit replay credit.
    ReplayCredit,
    /// Four-bit micro-op cache tag and valid bit.
    UopCache,
}

/// Small persistent public-instruction micro-op cache state.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct UopCache {
    tag: u8,
    valid: bool,
}

impl UopCache {
    /// Return the four-bit tag.
    #[must_use]
    pub fn tag(self) -> u8 {
        self.tag
    }

    /// Return whether the tag is valid.
    #[must_use]
    pub fn valid(self) -> bool {
        self.valid
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct PendingProbe {
    bank: Bank,
    epoch: u8,
    guard: bool,
}

/// Complete private scheduler state. No serializer is intentionally implemented.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MicroState {
    phase: u8,
    last_bank: Option<Bank>,
    replay_credit: u8,
    uop_cache: UopCache,
    pending_probe: Option<PendingProbe>,
    history_hash: u64,
}

impl MicroState {
    /// Return the two-bit phase for System A tests/models.
    #[must_use]
    pub fn phase(&self) -> u8 {
        self.phase
    }

    /// Return the last secret bank for System A tests/models.
    #[must_use]
    pub fn last_bank(&self) -> Option<Bank> {
        self.last_bank
    }

    /// Return the two-bit replay credit for System A tests/models.
    #[must_use]
    pub fn replay_credit(&self) -> u8 {
        self.replay_credit
    }

    /// Return the small cache state for System A tests/models.
    #[must_use]
    pub fn uop_cache(&self) -> UopCache {
        self.uop_cache
    }

    /// Produce the exact documented soft-reset state.
    #[must_use]
    pub fn soft_reset(&self, preserved: &[MicroStateField]) -> Self {
        let mut reset = Self::default();
        for field in preserved {
            match field {
                MicroStateField::Phase => reset.phase = self.phase,
                MicroStateField::LastBank => reset.last_bank = self.last_bank,
                MicroStateField::ReplayCredit => reset.replay_credit = self.replay_credit,
                MicroStateField::UopCache => reset.uop_cache = self.uop_cache,
            }
        }
        reset
    }
}

/// Secret bank resolved for a probe before the pure state transition.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResolvedRequest {
    /// Resolved secret-indexed probe.
    Probe {
        lane: usize,
        token: u8,
        epoch: u8,
        bank: Bank,
    },
    /// Public anchor.
    Anchor { bank: Bank, epoch: u8 },
    /// Public phase step.
    Pad { amount: u16 },
    /// Replay drain.
    Fence,
    /// Ordinary instruction without a vault event.
    None,
}

/// Predicate values consumed by a separate fault policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FaultContext {
    /// Whether resolved secret and public banks collide.
    pub collision: bool,
    /// Whether the pre-probe phase enabled the guarded cell.
    pub guard: bool,
    /// Whether pre-anchor replay credit suppresses the reference fault.
    pub suppress: bool,
    /// Replay credit immediately before anchor processing.
    pub replay_credit: u8,
}

/// Pure state-transition result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Transition {
    /// Next private state.
    pub next: MicroState,
    /// Fault predicates only when a matching-epoch probe/anchor cell completed.
    pub fault_context: Option<FaultContext>,
}

/// Resolve the public request shape with a private bank where required.
pub fn resolve_request(request: Option<VaultRequest>, probe_bank: Option<Bank>) -> ResolvedRequest {
    match request {
        Some(VaultRequest::Probe { lane, token, epoch }) => {
            probe_bank.map_or(ResolvedRequest::None, |bank| ResolvedRequest::Probe {
                lane,
                token,
                epoch,
                bank,
            })
        }
        Some(VaultRequest::Anchor { bank, epoch }) => {
            Bank::new(bank).map_or(ResolvedRequest::None, |bank| ResolvedRequest::Anchor {
                bank,
                epoch,
            })
        }
        Some(VaultRequest::Pad { amount }) => ResolvedRequest::Pad { amount },
        Some(VaultRequest::Fence) => ResolvedRequest::Fence,
        None => ResolvedRequest::None,
    }
}

/// Apply one instruction's hidden-state transition without choosing a fault variant.
#[must_use]
pub fn transition(state: &MicroState, request: ResolvedRequest, cache_tag: u8) -> Transition {
    let mut next = state.clone();
    next.uop_cache = UopCache {
        tag: cache_tag & 0x0f,
        valid: true,
    };
    let mut fault_context = None;
    match request {
        ResolvedRequest::Probe {
            lane,
            token,
            epoch,
            bank,
        } => {
            let lane_low = u8::try_from(lane & 0b11).unwrap_or_default();
            let guard = state.phase == ((lane_low ^ token ^ epoch) & 0b11);
            next.pending_probe = Some(PendingProbe { bank, epoch, guard });
            next.phase = (state.phase + 1 + epoch) & 0b11;
            next.history_hash = mix_history(state.history_hash, bank.get(), guard);
        }
        ResolvedRequest::Anchor { bank, epoch } => {
            if let Some(probe) = next.pending_probe.take() {
                if probe.epoch == epoch {
                    let collision = probe.bank == bank;
                    fault_context = Some(FaultContext {
                        collision,
                        guard: probe.guard,
                        suppress: state.replay_credit == 3,
                        replay_credit: state.replay_credit,
                    });
                    next.replay_credit = if collision {
                        state.replay_credit.saturating_add(1).min(3)
                    } else {
                        state.replay_credit.saturating_sub(1)
                    };
                    next.last_bank = Some(probe.bank);
                    next.history_hash =
                        mix_history(state.history_hash, probe.bank.get(), collision);
                }
            }
        }
        ResolvedRequest::Pad { amount } => {
            let amount_low = u8::try_from(amount & 0b11).unwrap_or_default();
            next.phase = (state.phase + amount_low) & 0b11;
            next.history_hash = mix_history(state.history_hash, amount_low, false);
        }
        ResolvedRequest::Fence => {
            next.pending_probe = None;
            next.replay_credit = 0;
            next.history_hash = mix_history(state.history_hash, 0xf, false);
        }
        ResolvedRequest::None => {
            next.history_hash = mix_history(state.history_hash, cache_tag & 0x0f, false);
        }
    }
    Transition {
        next,
        fault_context,
    }
}

fn mix_history(history: u64, value: u8, predicate: bool) -> u64 {
    let tagged = u64::from(value) | (u64::from(predicate) << 8);
    (history ^ tagged).wrapping_mul(0x0000_0100_0000_01b3)
}

#[cfg(test)]
mod tests {
    use serde::Deserialize;

    use crate::fault::{timing_delta, FaultVariant};
    use crate::mapping::BankMapping;

    use super::{transition, Bank, MicroState, MicroStateField, ResolvedRequest};

    #[derive(Deserialize)]
    struct ModelVectors {
        model_version: String,
        bank_vectors: Vec<BankVector>,
        cell_vectors: Vec<CellVector>,
    }

    #[derive(Deserialize)]
    struct BankVector {
        secret: u8,
        token: u8,
        salt: u8,
        epoch: u8,
        bank: u8,
    }

    #[derive(Deserialize)]
    struct CellVector {
        phase: u8,
        replay_credit: u8,
        lane: usize,
        token: u8,
        epoch: u8,
        secret_bank: u8,
        anchor_bank: u8,
        next_phase: u8,
        next_replay_credit: u8,
        last_bank: u8,
        reference_delta: i64,
        weak_delta: i64,
        signed_delta: i64,
    }

    fn bank(value: u8) -> Bank {
        match Bank::new(value) {
            Ok(bank) => bank,
            Err(error) => panic!("test bank should validate: {error}"),
        }
    }

    #[test]
    fn transition_matches_guard_collision_and_replay_equations() {
        let initial = MicroState::default();
        let probe = transition(
            &initial,
            ResolvedRequest::Probe {
                lane: 0,
                token: 0,
                epoch: 0,
                bank: bank(2),
            },
            0xc,
        );
        assert_eq!(probe.next.phase(), 1);
        let anchor = transition(
            &probe.next,
            ResolvedRequest::Anchor {
                bank: bank(2),
                epoch: 0,
            },
            0xd,
        );
        assert_eq!(anchor.next.replay_credit(), 1);
        assert_eq!(anchor.next.last_bank(), Some(bank(2)));
        assert_eq!(
            anchor.fault_context,
            Some(super::FaultContext {
                collision: true,
                guard: true,
                suppress: false,
                replay_credit: 0,
            })
        );
    }

    #[test]
    fn hard_and_soft_reset_preserve_exactly_named_fields() {
        let probe = transition(
            &MicroState::default(),
            ResolvedRequest::Probe {
                lane: 1,
                token: 1,
                epoch: 1,
                bank: bank(3),
            },
            0xc,
        );
        let populated = transition(
            &probe.next,
            ResolvedRequest::Anchor {
                bank: bank(3),
                epoch: 1,
            },
            0xd,
        )
        .next;
        let soft = populated.soft_reset(&[
            MicroStateField::Phase,
            MicroStateField::LastBank,
            MicroStateField::UopCache,
        ]);
        assert_eq!(soft.phase(), populated.phase());
        assert_eq!(soft.last_bank(), populated.last_bank());
        assert_eq!(soft.uop_cache(), populated.uop_cache());
        assert_eq!(soft.replay_credit(), 0);
        assert_eq!(MicroState::default().phase(), 0);
        assert_eq!(MicroState::default().last_bank(), None);
        assert!(!MicroState::default().uop_cache().valid());
    }

    #[test]
    fn concrete_mapping_and_transition_match_cross_language_vectors() {
        let source = include_str!("../../../tests/fixtures/model/micro-vectors.json");
        let vectors: ModelVectors = match serde_json::from_str(source) {
            Ok(value) => value,
            Err(error) => panic!("model vectors should decode: {error}"),
        };
        assert_eq!(vectors.model_version, "1.0");
        for vector in vectors.bank_vectors {
            let mapping = match BankMapping::new(vec![vector.secret], vec![0], vec![vector.salt], 1)
            {
                Ok(value) => value,
                Err(error) => panic!("vector mapping should validate: {error}"),
            };
            assert_eq!(
                mapping.bank(0, vector.token, vector.epoch).map(Bank::get),
                Some(vector.bank)
            );
        }
        for vector in vectors.cell_vectors {
            let initial = MicroState {
                phase: vector.phase,
                replay_credit: vector.replay_credit,
                ..MicroState::default()
            };
            let probed = transition(
                &initial,
                ResolvedRequest::Probe {
                    lane: vector.lane,
                    token: vector.token,
                    epoch: vector.epoch,
                    bank: bank(vector.secret_bank),
                },
                0xc,
            )
            .next;
            for (variant, expected_delta) in [
                (FaultVariant::Reference, vector.reference_delta),
                (FaultVariant::Weak, vector.weak_delta),
                (FaultVariant::Signed, vector.signed_delta),
            ] {
                let anchored = transition(
                    &probed,
                    ResolvedRequest::Anchor {
                        bank: bank(vector.anchor_bank),
                        epoch: vector.epoch,
                    },
                    0xd,
                );
                assert_eq!(anchored.next.phase(), vector.next_phase);
                assert_eq!(anchored.next.replay_credit(), vector.next_replay_credit);
                assert_eq!(
                    anchored.next.last_bank().map(Bank::get),
                    Some(vector.last_bank)
                );
                assert_eq!(
                    timing_delta(variant, anchored.fault_context),
                    expected_delta
                );
            }
        }
    }
}
