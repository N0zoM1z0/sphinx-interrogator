"""Command-line entry points for inspecting and exercising the design scaffold."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from sphinx_interrogator.ast import Program
from sphinx_interrogator.protocol import VmClient
from sphinx_interrogator.relations import AnchorSwitchTemplate


@click.group()
def main() -> None:
    """Relational interrogation tools for the synthetic SphinxVM target."""


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
@click.option("--profile", type=click.Path(path_type=Path, exists=True), required=True)
def hello(vm: Path, profile: Path) -> None:
    """Start a local public VM process and print its handshake as JSON."""
    with VmClient.start(vm, profile=profile) as client:
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


if __name__ == "__main__":
    main()
