"""Exact-history and active finite-state abstractions for soft-reset campaigns."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast


class ResetCapability(StrEnum):
    """Reset capabilities relevant to active automata learning."""

    HARD = "hard"
    SOFT = "soft"
    NONE = "none"


class OutputSymbol(StrEnum):
    """Stable discretized outputs used by the first state learner."""

    PUBLIC_OK = "PUBLIC_OK"
    REL_EQUAL = "REL_EQUAL"
    REL_GREATER = "REL_GREATER"
    REL_LESS = "REL_LESS"
    REL_INCONCLUSIVE = "REL_INCONCLUSIVE"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"


@dataclass(frozen=True, slots=True)
class HistorySymbol:
    """Finite abstraction of one public query/response interaction."""

    relation_id: str
    hole_signature: str
    outcome_class: str

    def __post_init__(self) -> None:
        if not self.relation_id or not self.hole_signature or not self.outcome_class:
            raise ValueError("history symbols require relation, holes, and outcome")

    def key(self) -> str:
        """Return the stable learner input symbol for this interaction class."""
        return f"{self.relation_id}|{self.hole_signature}|{self.outcome_class}"


@dataclass(frozen=True, slots=True)
class HistoryState:
    """Exact bounded-history state used before a learned quotient is trusted."""

    suffix: tuple[HistorySymbol, ...]

    def state_id(self) -> str:
        """Return a deterministic state label suitable for constraint provenance."""
        if not self.suffix:
            return "history-empty"
        encoded = json.dumps(
            [symbol.key() for symbol in self.suffix],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"history-{hashlib.sha256(encoded).hexdigest()[:16]}"


class ExactHistoryTracker:
    """Track a bounded public interaction suffix as a sound state key."""

    def __init__(self, maximum_depth: int) -> None:
        """Create an empty tracker with a positive suffix bound."""
        if maximum_depth < 1:
            raise ValueError("maximum_depth must be positive")
        self._maximum_depth = maximum_depth
        self._history: list[HistorySymbol] = []

    @property
    def maximum_depth(self) -> int:
        """Return the configured suffix length."""
        return self._maximum_depth

    def observe(self, symbol: HistorySymbol) -> HistoryState:
        """Append a symbol and return the resulting exact bounded state."""
        self._history.append(symbol)
        if len(self._history) > self._maximum_depth:
            self._history = self._history[-self._maximum_depth :]
        return self.state()

    def reset(self, capability: ResetCapability) -> None:
        """Clear exact history only when the public reset contract justifies it."""
        if capability is ResetCapability.HARD:
            self._history.clear()

    def state(self) -> HistoryState:
        """Return the current immutable bounded-history key."""
        return HistoryState(tuple(self._history))


@dataclass(frozen=True, slots=True)
class MacroAlphabet:
    """Versioned finite learner input/output alphabets and discretizer identity."""

    abstraction_version: str
    input_symbols: tuple[str, ...]
    output_symbols: tuple[str, ...]
    discretizer_version: str = "output-symbols/v1"

    def __post_init__(self) -> None:
        if not self.abstraction_version or not self.discretizer_version:
            raise ValueError("alphabet versions must be nonempty")
        _require_unique_nonempty(self.input_symbols, "input alphabet")
        _require_unique_nonempty(self.output_symbols, "output alphabet")

    @classmethod
    def from_history_symbols(
        cls,
        symbols: Iterable[HistorySymbol],
        *,
        abstraction_version: str = "macro-history/v1",
        outputs: Iterable[str] = tuple(item.value for item in OutputSymbol),
    ) -> MacroAlphabet:
        """Canonicalize public query classes into a deterministic learner alphabet."""
        return cls(
            abstraction_version=abstraction_version,
            input_symbols=tuple(sorted({symbol.key() for symbol in symbols})),
            output_symbols=tuple(sorted(set(outputs))),
        )

    def fingerprint(self) -> str:
        """Hash the public alphabet identity."""
        return _digest(self.to_data())

    def to_data(self) -> dict[str, object]:
        """Return stable JSON data for model persistence."""
        return {
            "abstraction_version": self.abstraction_version,
            "input_symbols": list(self.input_symbols),
            "output_symbols": list(self.output_symbols),
            "discretizer_version": self.discretizer_version,
        }

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> MacroAlphabet:
        """Decode a persisted macro alphabet."""
        return cls(
            abstraction_version=_string(data, "abstraction_version"),
            input_symbols=tuple(_string_list(data, "input_symbols")),
            output_symbols=tuple(_string_list(data, "output_symbols")),
            discretizer_version=_string(data, "discretizer_version"),
        )


@dataclass(frozen=True, slots=True)
class MealyEdge:
    """One deterministic Mealy transition."""

    output: str
    next_state: str

    def to_data(self) -> dict[str, str]:
        """Return stable JSON data for this transition."""
        return {"output": self.output, "next_state": self.next_state}

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> MealyEdge:
        """Decode one deterministic transition."""
        return cls(output=_string(data, "output"), next_state=_string(data, "next_state"))


@dataclass(frozen=True, slots=True)
class LearnedMealyMachine:
    """Serializable deterministic Mealy abstraction learned from public sequences."""

    model_id: str
    alphabet: MacroAlphabet
    states: tuple[str, ...]
    initial_state: str
    transitions: Mapping[str, Mapping[str, MealyEdge]]
    algorithm: str
    membership_cache_digest: str
    conformance: Mapping[str, object]
    counterexamples: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = ()
    status: str = "active"

    def __post_init__(self) -> None:
        if not self.model_id or not self.algorithm or not self.status:
            raise ValueError("model metadata must be nonempty")
        _require_unique_nonempty(self.states, "states")
        if self.initial_state not in self.states:
            raise ValueError("initial state must be part of the model")
        state_set = set(self.states)
        for state in self.states:
            edges = self.transitions.get(state)
            if edges is None:
                raise ValueError(f"missing transition row for state {state}")
            if set(edges) != set(self.alphabet.input_symbols):
                raise ValueError(f"transition row for {state} does not cover the alphabet")
            for symbol, edge in edges.items():
                if edge.output not in self.alphabet.output_symbols:
                    raise ValueError(f"transition output {edge.output} is outside the alphabet")
                if edge.next_state not in state_set:
                    raise ValueError(f"transition {state}/{symbol} targets an unknown state")

    def predict(
        self,
        sequence: Sequence[str],
        *,
        start_state: str | None = None,
    ) -> tuple[str, ...]:
        """Predict an output word from the model."""
        state = self.initial_state if start_state is None else start_state
        if state not in self.states:
            raise ValueError("unknown start state")
        outputs: list[str] = []
        for symbol in sequence:
            if symbol not in self.alphabet.input_symbols:
                raise ValueError(f"input symbol outside alphabet: {symbol}")
            edge = self.transitions[state][symbol]
            outputs.append(edge.output)
            state = edge.next_state
        return tuple(outputs)

    def access_sequence(self, state: str) -> tuple[str, ...] | None:
        """Return a shortest input sequence reaching `state`, if reachable."""
        if state not in self.states:
            raise ValueError("unknown state")
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(self.initial_state, ())])
        seen = {self.initial_state}
        while queue:
            current, path = queue.popleft()
            if current == state:
                return path
            for symbol in self.alphabet.input_symbols:
                edge = self.transitions[current][symbol]
                if edge.next_state not in seen:
                    seen.add(edge.next_state)
                    queue.append((edge.next_state, (*path, symbol)))
        return None

    def distinguish(
        self,
        states: frozenset[str],
        *,
        max_depth: int = 4,
    ) -> tuple[str, ...] | None:
        """Find a bounded suffix that separates the supplied states by output trace."""
        if len(states) < 2:
            raise ValueError("distinguishing requires at least two states")
        unknown = states.difference(self.states)
        if unknown:
            raise ValueError(f"unknown states: {sorted(unknown)}")
        queue: deque[tuple[str, ...]] = deque((symbol,) for symbol in self.alphabet.input_symbols)
        seen: set[tuple[str, ...]] = set()
        while queue:
            suffix = queue.popleft()
            if suffix in seen:
                continue
            seen.add(suffix)
            traces = {self.predict(suffix, start_state=state) for state in states}
            if len(traces) > 1:
                return suffix
            if len(suffix) < max_depth:
                for symbol in self.alphabet.input_symbols:
                    queue.append((*suffix, symbol))
        return None

    def transition_coverage(self, sequences: Iterable[Sequence[str]]) -> float:
        """Measure the fraction of model transitions visited by public sequences."""
        total = len(self.states) * len(self.alphabet.input_symbols)
        if total == 0:
            raise ValueError("empty transition system")
        covered: set[tuple[str, str]] = set()
        for sequence in sequences:
            state = self.initial_state
            for symbol in sequence:
                edge = self.transitions[state][symbol]
                covered.add((state, symbol))
                state = edge.next_state
        return len(covered) / total

    def artifact_digest(self) -> str:
        """Return the stable model artifact digest."""
        return _digest(self.to_data(include_digest=False))

    def to_data(self, *, include_digest: bool = True) -> dict[str, object]:
        """Return stable JSON data for durable state-model persistence."""
        data: dict[str, object] = {
            "model_id": self.model_id,
            "status": self.status,
            "algorithm": self.algorithm,
            "alphabet": self.alphabet.to_data(),
            "states": list(self.states),
            "initial_state": self.initial_state,
            "transitions": {
                state: {
                    symbol: self.transitions[state][symbol].to_data()
                    for symbol in self.alphabet.input_symbols
                }
                for state in self.states
            },
            "membership_cache_digest": self.membership_cache_digest,
            "conformance": dict(self.conformance),
            "counterexamples": [
                {"input": list(sequence), "observed": list(outputs)}
                for sequence, outputs in self.counterexamples
            ],
        }
        if include_digest:
            data["artifact_digest"] = self.artifact_digest()
        return data

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> LearnedMealyMachine:
        """Decode a persisted learned Mealy machine and verify its digest if present."""
        alphabet = MacroAlphabet.from_data(_mapping(data, "alphabet"))
        raw_transitions = _mapping(data, "transitions")
        transitions: dict[str, dict[str, MealyEdge]] = {}
        for state, row in raw_transitions.items():
            if not isinstance(row, dict):
                raise TypeError("transition rows must be objects")
            transitions[state] = {
                symbol: MealyEdge.from_data(cast("Mapping[str, object]", edge))
                for symbol, edge in row.items()
                if isinstance(edge, dict)
            }
        counterexamples = tuple(
            (
                tuple(_string_list(item, "input")),
                tuple(_string_list(item, "observed")),
            )
            for item in _mapping_list(data, "counterexamples")
        )
        model = cls(
            model_id=_string(data, "model_id"),
            status=_string(data, "status"),
            algorithm=_string(data, "algorithm"),
            alphabet=alphabet,
            states=tuple(_string_list(data, "states")),
            initial_state=_string(data, "initial_state"),
            transitions=transitions,
            membership_cache_digest=_string(data, "membership_cache_digest"),
            conformance=_mapping(data, "conformance"),
            counterexamples=counterexamples,
        )
        digest = data.get("artifact_digest")
        if digest is not None and digest != model.artifact_digest():
            raise ValueError("learned state model digest mismatch")
        return model

    @classmethod
    def from_aalpy(
        cls,
        *,
        model_id: str,
        alphabet: MacroAlphabet,
        automaton: Any,
        membership_cache_digest: str,
        conformance: Mapping[str, object],
    ) -> LearnedMealyMachine:
        """Convert an AALpy Mealy machine into the project persistence format."""
        setup = automaton.to_state_setup()
        states = tuple(str(state) for state in setup)
        transitions: dict[str, dict[str, MealyEdge]] = {}
        for state, row in setup.items():
            state_id = str(state)
            transitions[state_id] = {}
            for symbol in alphabet.input_symbols:
                try:
                    output, next_state = row[symbol]
                except KeyError as error:
                    raise ValueError(
                        f"AALpy model lacks transition for {state}/{symbol}"
                    ) from error
                transitions[state_id][symbol] = MealyEdge(str(output), str(next_state))
        return cls(
            model_id=model_id,
            alphabet=alphabet,
            states=states,
            initial_state=states[0],
            transitions=transitions,
            algorithm="aalpy-lstar-mealy/v1",
            membership_cache_digest=membership_cache_digest,
            conformance=conformance,
        )


class MembershipOracle(Protocol):
    """Public membership-query boundary used by exact and learned state adapters."""

    def __call__(self, sequence: tuple[str, ...]) -> tuple[str, ...]:
        """Execute one input word from the configured public start condition."""
        ...


class MembershipCache:
    """Deterministic membership-query cache with an auditable digest."""

    def __init__(self) -> None:
        """Create an empty cache."""
        self._responses: dict[tuple[str, ...], tuple[str, ...]] = {}

    @property
    def query_count(self) -> int:
        """Return the number of distinct cached membership words."""
        return len(self._responses)

    def query(
        self,
        sequence: Sequence[str],
        oracle: MembershipOracle,
    ) -> tuple[str, ...]:
        """Return a cached membership response or execute the public oracle."""
        key = tuple(sequence)
        if key not in self._responses:
            response = tuple(oracle(key))
            if len(response) != len(key):
                raise ValueError("membership output length must match input length")
            self._responses[key] = response
        return self._responses[key]

    def digest(self) -> str:
        """Return a stable digest of cached membership evidence."""
        rows = [
            {"input": list(sequence), "output": list(output)}
            for sequence, output in sorted(self._responses.items())
        ]
        return _digest({"membership_cache_version": "1.0", "rows": rows})

    def to_data(self) -> dict[str, object]:
        """Return stable JSON data for the cache."""
        return {
            "membership_cache_version": "1.0",
            "rows": [
                {"input": list(sequence), "output": list(output)}
                for sequence, output in sorted(self._responses.items())
            ],
            "digest": self.digest(),
        }


class OneStateLearner:
    """Trivial hard-reset learner for campaigns with no persistent hidden state."""

    def learn(
        self,
        *,
        model_id: str,
        alphabet: MacroAlphabet,
        output: str = OutputSymbol.PUBLIC_OK.value,
        outputs_by_symbol: Mapping[str, str] | None = None,
    ) -> LearnedMealyMachine:
        """Return a one-state model with self-loops on every input."""
        if outputs_by_symbol is None:
            if output not in alphabet.output_symbols:
                raise ValueError("one-state output must be in the output alphabet")
            resolved_outputs = {symbol: output for symbol in alphabet.input_symbols}
        else:
            if set(outputs_by_symbol) != set(alphabet.input_symbols):
                raise ValueError("per-symbol outputs must cover the input alphabet exactly")
            if any(value not in alphabet.output_symbols for value in outputs_by_symbol.values()):
                raise ValueError("one-state output must be in the output alphabet")
            resolved_outputs = dict(outputs_by_symbol)
        transitions = {
            "q0": {
                symbol: MealyEdge(output=resolved_outputs[symbol], next_state="q0")
                for symbol in alphabet.input_symbols
            }
        }
        return LearnedMealyMachine(
            model_id=model_id,
            alphabet=alphabet,
            states=("q0",),
            initial_state="q0",
            transitions=transitions,
            algorithm="one-state-hard-reset/v1",
            membership_cache_digest=_digest({"one_state": resolved_outputs}),
            conformance={"held_out_accuracy": 1.0, "tested_sequences": 0},
        )


class ExactHistoryLearner:
    """Build an explicit bounded-history Mealy model from membership queries."""

    def learn(
        self,
        *,
        model_id: str,
        alphabet: MacroAlphabet,
        oracle: MembershipOracle,
        maximum_depth: int,
    ) -> LearnedMealyMachine:
        """Materialize all public history states up to `maximum_depth`."""
        if maximum_depth < 1:
            raise ValueError("exact-history depth must be positive")
        cache = MembershipCache()
        words: set[tuple[str, ...]] = {()}
        words.update(generated_sequences(alphabet.input_symbols, max_depth=maximum_depth))
        ordered_words = tuple(sorted(words, key=lambda item: (len(item), item)))
        states = tuple(_history_word_state_id(word) for word in ordered_words)
        word_by_state = dict(zip(states, ordered_words, strict=True))
        transitions: dict[str, dict[str, MealyEdge]] = {}
        for state in states:
            word = word_by_state[state]
            transitions[state] = {}
            for symbol in alphabet.input_symbols:
                extended = (*word, symbol)
                observed = cache.query(extended, oracle)[-1]
                next_word = extended[-maximum_depth:]
                transitions[state][symbol] = MealyEdge(
                    output=observed,
                    next_state=_history_word_state_id(next_word),
                )
        provisional = LearnedMealyMachine(
            model_id=model_id,
            alphabet=alphabet,
            states=states,
            initial_state=_history_word_state_id(()),
            transitions=transitions,
            algorithm=f"exact-history/v1-depth-{maximum_depth}",
            membership_cache_digest=cache.digest(),
            conformance={"status": "pending"},
        )
        held_out = generated_sequences(alphabet.input_symbols, max_depth=maximum_depth)
        conformance = evaluate_conformance(provisional, oracle, held_out)
        return LearnedMealyMachine(
            model_id=provisional.model_id,
            alphabet=provisional.alphabet,
            states=provisional.states,
            initial_state=provisional.initial_state,
            transitions=provisional.transitions,
            algorithm=provisional.algorithm,
            membership_cache_digest=cache.digest(),
            conformance=conformance.to_data(),
            counterexamples=tuple(
                (item.sequence, item.observed) for item in conformance.counterexamples
            ),
            status="active" if not conformance.counterexamples else "counterexample",
        )


@dataclass(frozen=True, slots=True)
class Counterexample:
    """One observed word where the learned model disagrees with public evidence."""

    sequence: tuple[str, ...]
    expected: tuple[str, ...]
    observed: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        """Return stable JSON data for reports and state-model metadata."""
        return {
            "sequence": list(self.sequence),
            "expected": list(self.expected),
            "observed": list(self.observed),
        }


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    """Approximate equivalence evidence for a learned deterministic abstraction."""

    tested_sequences: int
    exact_matches: int
    counterexamples: tuple[Counterexample, ...]
    transition_coverage: float

    @property
    def held_out_accuracy(self) -> float:
        """Return exact sequence accuracy over the tested portfolio."""
        if self.tested_sequences == 0:
            return 1.0
        return self.exact_matches / self.tested_sequences

    def to_data(self) -> dict[str, object]:
        """Return stable report data."""
        return {
            "tested_sequences": self.tested_sequences,
            "exact_matches": self.exact_matches,
            "held_out_accuracy": self.held_out_accuracy,
            "transition_coverage": self.transition_coverage,
            "counterexamples": [item.to_data() for item in self.counterexamples],
        }


class AalpyMealyLearner:
    """AALpy-backed deterministic Mealy learner over public macro symbols."""

    def __init__(self, *, max_states: int = 8) -> None:
        """Configure the deterministic conformance depth bound."""
        if max_states < 1:
            raise ValueError("max_states must be positive")
        self.max_states = max_states

    @staticmethod
    def available() -> bool:
        """Return whether AALpy is installed in the active Python environment."""
        return importlib.util.find_spec("aalpy") is not None

    def learn(
        self,
        *,
        model_id: str,
        alphabet: MacroAlphabet,
        oracle: MembershipOracle,
        held_out_sequences: Iterable[Sequence[str]],
    ) -> LearnedMealyMachine:
        """Learn and validate one deterministic Mealy abstraction with AALpy L*."""
        if not self.available():
            raise RuntimeError("AALpy is not installed")
        from aalpy.learning_algs import run_Lstar  # type: ignore[import-untyped]
        from aalpy.oracles import WMethodEqOracle  # type: ignore[import-untyped]

        cache = MembershipCache()
        sul = _CachedMembershipSul(cache, oracle)
        eq_oracle = WMethodEqOracle(list(alphabet.input_symbols), sul, self.max_states)
        automaton = run_Lstar(
            list(alphabet.input_symbols),
            sul,
            eq_oracle,
            "mealy",
            cache_and_non_det_check=False,
            return_data=False,
            print_level=0,
        )
        provisional = LearnedMealyMachine.from_aalpy(
            model_id=model_id,
            alphabet=alphabet,
            automaton=automaton,
            membership_cache_digest=cache.digest(),
            conformance={"status": "pending"},
        )
        conformance = evaluate_conformance(provisional, oracle, held_out_sequences)
        return LearnedMealyMachine(
            model_id=provisional.model_id,
            alphabet=provisional.alphabet,
            states=provisional.states,
            initial_state=provisional.initial_state,
            transitions=provisional.transitions,
            algorithm=provisional.algorithm,
            membership_cache_digest=cache.digest(),
            conformance=conformance.to_data(),
            counterexamples=tuple(
                (item.sequence, item.observed) for item in conformance.counterexamples
            ),
            status="active" if not conformance.counterexamples else "counterexample",
        )


class _CachedMembershipSul:
    """AALpy SUL adapter backed by whole-word public membership queries."""

    def __init__(self, cache: MembershipCache, oracle: MembershipOracle) -> None:
        self.cache = cache
        self.oracle = oracle
        self._prefix: tuple[str, ...] = ()
        self.num_queries = 0
        self.num_steps = 0
        self.num_cached_queries = 0

    def query(self, word: tuple[str, ...]) -> list[str]:
        """Execute one AALpy membership query."""
        self.pre()
        output = [self.step(letter) for letter in word]
        self.post()
        self.num_queries += 1
        self.num_steps += len(word)
        return output

    def pre(self) -> None:
        """Reset the public start condition for a new membership word."""
        self._prefix = ()

    def post(self) -> None:
        """No cleanup is needed for pure public membership functions."""
        return None

    def step(self, letter: str) -> str:
        """Execute one input symbol by querying the full current prefix."""
        before = self.cache.query_count
        self._prefix = (*self._prefix, letter)
        output = self.cache.query(self._prefix, self.oracle)[-1]
        if self.cache.query_count == before:
            self.num_cached_queries += 1
        return output


def evaluate_conformance(
    model: LearnedMealyMachine,
    oracle: MembershipOracle,
    sequences: Iterable[Sequence[str]],
) -> ConformanceResult:
    """Evaluate a learned model against a deterministic held-out sequence portfolio."""
    tested = 0
    exact = 0
    counterexamples: list[Counterexample] = []
    normalized_sequences = [tuple(sequence) for sequence in sequences]
    for sequence in normalized_sequences:
        expected = model.predict(sequence)
        observed = tuple(oracle(sequence))
        if len(observed) != len(sequence):
            raise ValueError("held-out membership output length must match input length")
        tested += 1
        if expected == observed:
            exact += 1
        else:
            counterexamples.append(Counterexample(sequence, expected, observed))
    return ConformanceResult(
        tested_sequences=tested,
        exact_matches=exact,
        counterexamples=tuple(counterexamples),
        transition_coverage=model.transition_coverage(normalized_sequences),
    )


def generated_sequences(alphabet: Sequence[str], *, max_depth: int) -> tuple[tuple[str, ...], ...]:
    """Generate deterministic nonempty conformance sequences up to a bounded depth."""
    if max_depth < 1:
        raise ValueError("max_depth must be positive")
    _require_unique_nonempty(tuple(alphabet), "input alphabet")
    sequences: list[tuple[str, ...]] = []
    frontier: list[tuple[str, ...]] = [()]
    for _ in range(max_depth):
        next_frontier: list[tuple[str, ...]] = []
        for prefix in frontier:
            for symbol in alphabet:
                sequence = (*prefix, symbol)
                sequences.append(sequence)
                next_frontier.append(sequence)
        frontier = next_frontier
    return tuple(sequences)


def state_model_provenance(model_id: str, state_id: str) -> tuple[str, str]:
    """Return standard provenance markers for state-conditioned constraints."""
    if not model_id or not state_id:
        raise ValueError("state provenance requires model and state identifiers")
    return (f"state-model:{model_id}", f"state:{state_id}")


def _history_word_state_id(word: tuple[str, ...]) -> str:
    if not word:
        return "history-empty"
    return (
        "history-"
        + hashlib.sha256(
            json.dumps(list(word), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )


def _require_unique_nonempty(values: tuple[str, ...], label: str) -> None:
    if not values or any(not value for value in values):
        raise ValueError(f"{label} must contain nonempty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")


def _digest(data: Mapping[str, object]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a nonempty string")
    return value


def _string_list(data: Mapping[str, object], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be a string list")
    return value


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return cast("Mapping[str, object]", value)


def _mapping_list(data: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(f"{key} must be a list of objects")
    return cast("list[Mapping[str, object]]", value)
