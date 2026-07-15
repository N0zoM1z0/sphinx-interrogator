//! Fault policies over pure microarchitectural transition predicates.

use serde::{Deserialize, Serialize};

use crate::microarchitecture::FaultContext;

/// Private fault policy selected when a challenge is created.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FaultVariant {
    /// Negative control: never add a timing delta.
    Off,
    /// Guarded replay reference fault.
    Reference,
    /// Weaker mutation that fires only with zero replay credit.
    Weak,
    /// Signed calibration mutation from the public model family.
    Signed,
}

impl std::fmt::Display for FaultVariant {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let name = match self {
            Self::Off => "off",
            Self::Reference => "reference",
            Self::Weak => "weak",
            Self::Signed => "signed",
        };
        formatter.write_str(name)
    }
}

impl std::str::FromStr for FaultVariant {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "off" => Ok(Self::Off),
            "reference" => Ok(Self::Reference),
            "weak" => Ok(Self::Weak),
            "signed" => Ok(Self::Signed),
            _ => Err(format!("unknown fault variant {value}")),
        }
    }
}

/// Evaluate only the timing mutation; architectural semantics never call this module.
#[must_use]
pub fn timing_delta(variant: FaultVariant, context: Option<FaultContext>) -> i64 {
    let Some(context) = context else {
        return 0;
    };
    match variant {
        FaultVariant::Off => 0,
        FaultVariant::Reference => {
            i64::from(context.collision && context.guard && !context.suppress)
        }
        FaultVariant::Weak => {
            i64::from(context.collision && context.guard && context.replay_credit == 0)
        }
        FaultVariant::Signed => {
            if context.collision && context.guard && !context.suppress {
                1
            } else if !context.collision && context.guard && context.replay_credit == 2 {
                -1
            } else {
                0
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{timing_delta, FaultVariant};
    use crate::microarchitecture::FaultContext;

    #[test]
    fn mutation_ladder_changes_only_the_declared_delta() {
        let collision = Some(FaultContext {
            collision: true,
            guard: true,
            suppress: false,
            replay_credit: 1,
        });
        assert_eq!(timing_delta(FaultVariant::Off, collision), 0);
        assert_eq!(timing_delta(FaultVariant::Reference, collision), 1);
        assert_eq!(timing_delta(FaultVariant::Weak, collision), 0);
        assert_eq!(timing_delta(FaultVariant::Signed, collision), 1);

        let signed_negative = Some(FaultContext {
            collision: false,
            guard: true,
            suppress: false,
            replay_credit: 2,
        });
        assert_eq!(timing_delta(FaultVariant::Reference, signed_negative), 0);
        assert_eq!(timing_delta(FaultVariant::Signed, signed_negative), -1);
    }
}
