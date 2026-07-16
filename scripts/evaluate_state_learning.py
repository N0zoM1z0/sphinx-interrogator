#!/usr/bin/env python3
"""Evaluate M8 state-learning variants on a deterministic soft-reset fixture."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sphinx_interrogator.learner import (
    AalpyMealyLearner,
    ExactHistoryLearner,
    MacroAlphabet,
    OneStateLearner,
    evaluate_conformance,
    generated_sequences,
)

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """Parse state-learning evaluation options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "runs/state-learning-m8")
    parser.add_argument("--max-depth", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    """Run no-learner, exact-history, and learned-state variants."""
    args = parse_args()
    if args.max_depth < 1:
        raise ValueError("--max-depth must be positive")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    alphabet = MacroAlphabet(
        abstraction_version="soft-reset-toggle/v1",
        input_symbols=("ping", "toggle"),
        output_symbols=("OFF", "ON"),
    )
    held_out = generated_sequences(alphabet.input_symbols, max_depth=args.max_depth)
    no_learner = OneStateLearner().learn(
        model_id="state-eval-no-learner",
        alphabet=alphabet,
        output="OFF",
    )
    exact = ExactHistoryLearner().learn(
        model_id="state-eval-exact-history",
        alphabet=alphabet,
        oracle=_toggle_oracle,
        maximum_depth=args.max_depth,
    )
    learned = AalpyMealyLearner(max_states=2).learn(
        model_id="state-eval-aalpy",
        alphabet=alphabet,
        oracle=_toggle_oracle,
        held_out_sequences=held_out,
    )
    variants = [
        _variant("no_learner", no_learner, held_out),
        _variant("exact_history", exact, held_out),
        _variant("learned_state", learned, held_out),
    ]
    by_mode = {variant["mode"]: variant for variant in variants}
    targets = {
        "exact_history_accuracy_eq_1": by_mode["exact_history"]["held_out_accuracy"] == 1.0,
        "learned_state_accuracy_ge_0_95": by_mode["learned_state"]["held_out_accuracy"] >= 0.95,
        "learned_state_beats_no_learner": (
            by_mode["learned_state"]["held_out_accuracy"]
            > by_mode["no_learner"]["held_out_accuracy"]
        ),
    }
    report = {
        "report_version": "1.0",
        "profile_name": "research",
        "fixture": "deterministic-soft-reset-toggle",
        "alphabet": alphabet.to_data(),
        "held_out_sequences": len(held_out),
        "variants": variants,
        "targets_met": targets,
    }
    _write_json(output / "state-learning-report.json", report)
    _write_markdown(output / "state-learning-report.md", report)
    print(json.dumps(targets, indent=2, sort_keys=True))
    return int(not all(targets.values()))


def _variant(mode: str, model: object, held_out: tuple[tuple[str, ...], ...]) -> dict[str, object]:
    conformance = evaluate_conformance(model, _toggle_oracle, held_out)
    return {
        "mode": mode,
        "model_id": model.model_id,
        "algorithm": model.algorithm,
        "states": len(model.states),
        "held_out_accuracy": conformance.held_out_accuracy,
        "counterexamples": len(conformance.counterexamples),
        "transition_coverage": conformance.transition_coverage,
        "artifact_digest": model.artifact_digest(),
    }


def _toggle_oracle(sequence: tuple[str, ...]) -> tuple[str, ...]:
    state = "OFF"
    outputs = []
    for symbol in sequence:
        if symbol == "toggle":
            state = "ON" if state == "OFF" else "OFF"
        elif symbol != "ping":
            raise ValueError(f"unexpected input {symbol}")
        outputs.append(state)
    return tuple(outputs)


def _write_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_markdown(path: Path, report: dict[str, object]) -> None:
    lines = [
        "# State Learning Evaluation",
        "",
        f"- Fixture: `{report['fixture']}`",
        f"- Held-out sequences: `{report['held_out_sequences']}`",
        "",
        "| mode | states | held-out accuracy | counterexamples | coverage |",
        "|---|---:|---:|---:|---:|",
    ]
    variants = report.get("variants")
    if not isinstance(variants, list):
        raise TypeError("report variants must be a list")
    for variant in variants:
        if not isinstance(variant, dict):
            raise TypeError("variant must be an object")
        lines.append(
            "| "
            f"{variant['mode']} | {variant['states']} | "
            f"{float(variant['held_out_accuracy']):.3f} | "
            f"{variant['counterexamples']} | "
            f"{float(variant['transition_coverage']):.3f} |"
        )
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
