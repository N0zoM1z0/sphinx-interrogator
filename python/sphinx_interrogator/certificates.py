"""Versioned relation certificates and a deterministic in-memory registry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import cast


class ProofMethod(StrEnum):
    """Declared proof method ordered by campaign acceptance strength."""

    EMPIRICAL_ONLY = "empirical-only"
    DIFFERENTIAL_PROPERTY = "differential-property"
    EXHAUSTIVE_ENUMERATION = "exhaustive-enumeration"
    SMT_BOUNDED_COMPLETE = "smt-bounded-complete"
    THEOREM = "theorem"

    @property
    def strength(self) -> int:
        """Return the proof-strength lattice rank used by campaign policy."""
        return {
            ProofMethod.EMPIRICAL_ONLY: 0,
            ProofMethod.DIFFERENTIAL_PROPERTY: 1,
            ProofMethod.EXHAUSTIVE_ENUMERATION: 2,
            ProofMethod.SMT_BOUNDED_COMPLETE: 3,
            ProofMethod.THEOREM: 4,
        }[self]


@dataclass(frozen=True, slots=True)
class RelationCertificate:
    """Serializable proof metadata bound to one canonical relation instance."""

    certificate_schema_version: str
    certificate_id: str
    semantic_version: str
    profile_scope: tuple[str, ...]
    relation_instance_hash: str
    proof_method: ProofMethod
    architectural_claim: str
    fault_free_claim: str
    preconditions: tuple[str, ...]
    artifact_digest: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject malformed or accidentally unscoped certificate metadata."""
        if self.certificate_schema_version != "1.0":
            raise ValueError("unsupported certificate schema version")
        if not self.certificate_id:
            raise ValueError("certificate_id must not be empty")
        if not self.semantic_version:
            raise ValueError("semantic_version must not be empty")
        if not self.profile_scope:
            raise ValueError("profile_scope must not be empty")
        for role, digest in (
            ("relation_instance_hash", self.relation_instance_hash),
            ("artifact_digest", self.artifact_digest),
        ):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(f"{role} must be lowercase SHA-256")
        if not self.architectural_claim or not self.fault_free_claim:
            raise ValueError("certificate claims must not be empty")
        expected_digest = _artifact_digest(_artifact_data(self))
        if self.artifact_digest != expected_digest:
            raise ValueError("certificate artifact digest does not match its claims")
        if self.certificate_id != f"cert:{expected_digest[:24]}":
            raise ValueError("certificate ID does not match its artifact digest")

    def meets(self, minimum: ProofMethod) -> bool:
        """Return whether campaign policy may consume this certificate as hard evidence."""
        return self.proof_method.strength >= minimum.strength

    def to_data(self) -> dict[str, object]:
        """Return stable schema-shaped data."""
        data = asdict(self)
        data["proof_method"] = self.proof_method.value
        data["profile_scope"] = list(self.profile_scope)
        data["preconditions"] = list(self.preconditions)
        data["limitations"] = list(self.limitations)
        return data

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> RelationCertificate:
        """Strictly decode persisted proof metadata and verify its artifact binding."""
        expected_fields = {
            "certificate_schema_version",
            "certificate_id",
            "semantic_version",
            "profile_scope",
            "relation_instance_hash",
            "proof_method",
            "architectural_claim",
            "fault_free_claim",
            "preconditions",
            "artifact_digest",
            "limitations",
        }
        extras = sorted(set(data) - expected_fields)
        if extras:
            raise ValueError(f"certificate contains unknown fields: {', '.join(extras)}")
        return cls(
            certificate_schema_version=_string(data, "certificate_schema_version"),
            certificate_id=_string(data, "certificate_id"),
            semantic_version=_string(data, "semantic_version"),
            profile_scope=_string_tuple(data, "profile_scope"),
            relation_instance_hash=_string(data, "relation_instance_hash"),
            proof_method=ProofMethod(_string(data, "proof_method")),
            architectural_claim=_string(data, "architectural_claim"),
            fault_free_claim=_string(data, "fault_free_claim"),
            preconditions=_string_tuple(data, "preconditions"),
            artifact_digest=_string(data, "artifact_digest"),
            limitations=_string_tuple(data, "limitations"),
        )


class CertificateRegistry:
    """Deterministically issue and cache certificates by their complete claims."""

    def __init__(self) -> None:
        self._by_artifact: dict[str, RelationCertificate] = {}

    def issue(
        self,
        *,
        relation_instance_hash: str,
        semantic_version: str,
        profile_scope: tuple[str, ...],
        proof_method: ProofMethod,
        architectural_claim: str,
        fault_free_claim: str,
        preconditions: tuple[str, ...],
        limitations: tuple[str, ...] = (),
    ) -> RelationCertificate:
        """Return the canonical cached certificate for one complete claim set."""
        artifact = {
            "certificate_schema_version": "1.0",
            "semantic_version": semantic_version,
            "profile_scope": list(profile_scope),
            "relation_instance_hash": relation_instance_hash,
            "proof_method": proof_method.value,
            "architectural_claim": architectural_claim,
            "fault_free_claim": fault_free_claim,
            "preconditions": list(preconditions),
            "limitations": list(limitations),
        }
        artifact_digest = _artifact_digest(artifact)
        cached = self._by_artifact.get(artifact_digest)
        if cached is not None:
            return cached
        certificate = RelationCertificate(
            certificate_schema_version="1.0",
            certificate_id=f"cert:{artifact_digest[:24]}",
            semantic_version=semantic_version,
            profile_scope=profile_scope,
            relation_instance_hash=relation_instance_hash,
            proof_method=proof_method,
            architectural_claim=architectural_claim,
            fault_free_claim=fault_free_claim,
            preconditions=preconditions,
            artifact_digest=artifact_digest,
            limitations=limitations,
        )
        self._by_artifact[artifact_digest] = certificate
        return certificate

    def load(self, data: Mapping[str, object]) -> RelationCertificate:
        """Verify and cache a certificate recovered from durable campaign storage."""
        certificate = RelationCertificate.from_data(data)
        cached = self._by_artifact.get(certificate.artifact_digest)
        if cached is not None:
            if cached != certificate:
                raise ValueError("certificate registry contains a conflicting artifact")
            return cached
        self._by_artifact[certificate.artifact_digest] = certificate
        return certificate

    def get(self, artifact_digest: str) -> RelationCertificate | None:
        """Look up a previously issued certificate without synthesizing one."""
        return self._by_artifact.get(artifact_digest)

    def __len__(self) -> int:
        return len(self._by_artifact)


DEFAULT_CERTIFICATE_REGISTRY = CertificateRegistry()


def _artifact_data(certificate: RelationCertificate) -> dict[str, object]:
    return {
        "certificate_schema_version": certificate.certificate_schema_version,
        "semantic_version": certificate.semantic_version,
        "profile_scope": list(certificate.profile_scope),
        "relation_instance_hash": certificate.relation_instance_hash,
        "proof_method": certificate.proof_method.value,
        "architectural_claim": certificate.architectural_claim,
        "fault_free_claim": certificate.fault_free_claim,
        "preconditions": list(certificate.preconditions),
        "limitations": list(certificate.limitations),
    }


def _artifact_digest(artifact: Mapping[str, object]) -> str:
    encoded = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"certificate {key} must be a string")
    return value


def _string_tuple(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"certificate {key} must be a string list")
    return tuple(cast("list[str]", value))
