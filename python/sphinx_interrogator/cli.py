"""Command-line entry points for inspecting public relations and the VM endpoint."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import click

from sphinx_interrogator.ast import Program
from sphinx_interrogator.persistence import CampaignRepository
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.reducer import (
    ReductionConfig,
    ReductionMode,
    RelationReducer,
    SignatureKind,
    default_model_committee,
)
from sphinx_interrogator.relations import (
    AnchorSwitchTemplate,
    ContextLiftTemplate,
    HardReplayTemplate,
    RelationInstance,
    RepeatAmplifyTemplate,
)
from sphinx_interrogator.tutorial import recover_tutorial


@click.group()
def main() -> None:
    """Relational interrogation tools for the synthetic SphinxVM target."""


@main.command("doctor")
def doctor() -> None:
    """Print a public, non-secret capability summary for this client package."""
    click.echo(
        json.dumps(
            {
                "doctor_version": "1.0",
                "package": "sphinx_interrogator",
                "black_box_boundary": "public-jsonl-process-only",
                "synthetic_only": True,
                "commands": [
                    "doctor",
                    "recover",
                    "replay",
                    "inspect",
                    "reduce",
                    "benchmark",
                    "hello",
                    "render-cell",
                    "render-anchor-switch",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


@main.command("render-anchor-switch")
@click.option("--lane", type=click.IntRange(min=0), required=True)
@click.option("--token", type=click.IntRange(0, 15), required=True)
@click.option("--epoch", type=click.IntRange(0, 1), required=True)
@click.option("--bank-a", type=click.IntRange(0, 3), required=True)
@click.option("--bank-b", type=click.IntRange(0, 3), required=True)
@click.option("--pad", type=click.IntRange(min=0), default=0, show_default=True)
def render_anchor_switch(
    lane: int,
    token: int,
    epoch: int,
    bank_a: int,
    bank_b: int,
    pad: int,
) -> None:
    """Render the two programs in one certified anchor-switch instance."""
    relation = AnchorSwitchTemplate().instantiate(
        instance_id="cli-preview",
        lane=lane,
        token=token,
        epoch=epoch,
        bank_a=bank_a,
        bank_b=bank_b,
        pad=pad,
    )
    click.echo("# source")
    click.echo(relation.source_program.render(), nl=False)
    click.echo("# follow-up")
    click.echo(relation.follow_up_programs[0].render(), nl=False)
    click.echo(f"# certificate: {relation.certificate.artifact_digest}")


@main.command("hello")
@click.option("--vm", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--challenge", type=click.Path(path_type=Path, exists=True), required=True)
def hello(vm: Path, challenge: Path) -> None:
    """Start a local public VM process and print its handshake as JSON."""
    with VmClient.start(vm, challenge=challenge) as client:
        result = client.hello()
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@main.command("render-cell")
@click.option("--lane", type=click.IntRange(min=0), required=True)
@click.option("--token", type=click.IntRange(0, 15), required=True)
@click.option("--epoch", type=click.IntRange(0, 1), required=True)
@click.option("--anchor", type=click.IntRange(0, 3), required=True)
@click.option("--pad", type=click.IntRange(min=0), default=0, show_default=True)
def render_cell(lane: int, token: int, epoch: int, anchor: int, pad: int) -> None:
    """Render one canonical experiment cell."""
    program = Program.experiment_cell(
        lane=lane,
        token=token,
        epoch=epoch,
        anchor=anchor,
        pad=pad,
    )
    click.echo(program.render(), nl=False)


@main.command("inspect")
@click.option("--run", "run_directory", type=click.Path(path_type=Path, exists=True), required=True)
def inspect_run(run_directory: Path) -> None:
    """Print a deterministic public summary of one persisted campaign."""
    repository = CampaignRepository.open(run_directory)
    try:
        report = repository.report()
    finally:
        repository.close()
    click.echo(json.dumps(report, indent=2, sort_keys=True))


@main.command("replay")
@click.option("--run", "run_directory", type=click.Path(path_type=Path, exists=True), required=True)
def replay_run(run_directory: Path) -> None:
    """Rebuild SQLite from the append-only log and verify identical materialized state."""
    repository = CampaignRepository.open(run_directory)
    try:
        before = repository.database.digest()
        after = repository.rebuild()
        report = {
            "replay_version": "1.0",
            "campaign_id": repository.manifest.campaign_id,
            "before_digest": before,
            "after_digest": after,
            "matched": before == after,
        }
    finally:
        repository.close()
    click.echo(json.dumps(report, indent=2, sort_keys=True))
    if not report["matched"]:
        raise click.ClickException("materialized replay digest mismatch")


@main.command("reduce")
@click.option(
    "--family",
    type=click.Choice(
        [
            "anchor-switch/v1",
            "repeat-amplify/v1",
            "context-lift/v1",
            "hard-replay/v1",
        ]
    ),
    default="repeat-amplify/v1",
    show_default=True,
)
@click.option("--output", type=click.Path(path_type=Path), default=None)
def reduce_witness(family: str, output: Path | None) -> None:
    """Reduce a built-in public witness sample and emit a JSON report."""
    relation, known_relations = _cli_reduction_seed(family)
    reducer = RelationReducer(
        models=default_model_committee(relation.involved_lanes),
        known_relations=known_relations,
        config=ReductionConfig(
            mode=ReductionMode.IMPLIES_CORE,
            signature_kind=SignatureKind.SIGN,
            max_predicate_evaluations=512,
            max_generated_candidates=2_048,
        ),
    )
    result = reducer.reduce(relation)
    report = result.to_data()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is None:
        click.echo(encoded, nl=False)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        click.echo(str(output))
    if not result.improved:
        raise click.ClickException("witness could not be reduced under the configured predicate")


@main.command("benchmark")
@click.option(
    "--report",
    "report_path",
    type=click.Path(path_type=Path, exists=True),
    default=Path("runs/standard-benchmark-v1/standard-benchmark-report.json"),
    show_default=True,
)
def benchmark_report(report_path: Path) -> None:
    """Inspect an existing standard benchmark report without rerunning the target."""
    raw = report_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise click.ClickException("benchmark report must be a JSON object")
    variants = data.get("variants", [])
    if not isinstance(variants, list):
        raise click.ClickException("benchmark report variants must be a list")
    click.echo(
        json.dumps(
            {
                "benchmark_report_version": "1.0",
                "path": str(report_path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "targets_met": bool(data.get("targets_met")),
                "variant_count": len(variants),
                "full_published_matrix": bool(data.get("full_published_matrix")),
            },
            indent=2,
            sort_keys=True,
        )
    )


@main.command("recover")
@click.option("--vm", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--challenge", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--run", "run_directory", type=click.Path(path_type=Path), required=True)
@click.option("--seed", type=click.IntRange(min=0), required=True)
@click.option("--submit-judge/--no-submit-judge", default=True, show_default=True)
def recover(
    vm: Path,
    challenge: Path,
    run_directory: Path,
    seed: int,
    submit_judge: bool,
) -> None:
    """Run exact tutorial recovery through the public black-box protocol."""
    result = recover_tutorial(
        vm_binary=vm,
        challenge=challenge,
        run_directory=run_directory,
        campaign_seed=seed,
        submit_judge=submit_judge,
    )
    click.echo(json.dumps(result.report, indent=2, sort_keys=True))
    if result.status not in {"unique_exact", "unique_exact_unjudged"}:
        raise click.ClickException(f"tutorial recovery ended with {result.status}")


def _cli_reduction_seed(
    family: str,
) -> tuple[RelationInstance, dict[str, RelationInstance]]:
    anchor = AnchorSwitchTemplate().instantiate(
        instance_id="cli-anchor",
        lane=0,
        token=0,
        epoch=0,
        bank_a=3,
        bank_b=2,
        pad=8,
        repeats=4,
    )
    if family == "anchor-switch/v1":
        return anchor, {}
    if family == "repeat-amplify/v1":
        return (
            RepeatAmplifyTemplate().instantiate(
                instance_id="cli-repeat",
                lane=0,
                token=0,
                epoch=0,
                anchor=2,
                pad=8,
                repeats=6,
            ),
            {},
        )
    if family == "context-lift/v1":
        return (
            ContextLiftTemplate().instantiate(
                instance_id="cli-context",
                base=anchor,
                prefix_pad=8,
                suffix_fence=True,
            ),
            {anchor.instance_hash: anchor},
        )
    if family == "hard-replay/v1":
        replay_program = Program.experiment_cell(
            lane=0,
            token=0,
            epoch=0,
            anchor=2,
            pad=4,
        )
        return (
            HardReplayTemplate().instantiate(
                instance_id="cli-hard-replay",
                program=replay_program,
                repetitions=4,
                deterministic_observation=True,
            ),
            {},
        )
    # The click choice should make this path unreachable, but keep it explicit.
    raise click.ClickException(f"unsupported reduction family {family}")


if __name__ == "__main__":
    main()
