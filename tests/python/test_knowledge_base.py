"""Tests for graph-shaped interrogation knowledge and provenance."""

from sphinx_interrogator.knowledge_base import InterrogationKnowledgeBase, QueryRecord
from sphinx_interrogator.model import ExecutionObservation, ExecutionResult


def result(request_id: str, bucket: int) -> ExecutionResult:
    """Build a small public execution result fixture."""
    return ExecutionResult(
        request_id=request_id,
        session_id="s",
        status="halted",
        public_digest="0000000000000000",
        observation=ExecutionObservation(bucket, 1),
        retired_instructions=1,
        static_cycles=1,
        physical_executions_used=1,
        physical_executions_remaining=9,
        logical_queries_used=1,
        logical_queries_remaining=9,
        hard_resets_used=1,
        hard_resets_remaining=9,
        server_version="0.1.0",
        profile_version="0.1.0",
    )


def test_response_diversity_and_ttl() -> None:
    """The knowledge base should retain rich responses and expire stateful evidence."""
    knowledge = InterrogationKnowledgeBase()
    knowledge.add_query(
        QueryRecord(
            query_id="q1",
            program_text="HALT\n",
            results=(result("r1", 1), result("r2", 2)),
            created_at_step=0,
            expires_after_step=0,
        )
    )
    assert knowledge.response_diversity("q1") == 2
    assert knowledge.live_query_ids() == ("q1",)
    knowledge.advance()
    assert knowledge.live_query_ids() == ()
