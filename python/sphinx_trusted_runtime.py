"""Trusted local orchestration for split SphinxVM challenge processes.

This module is intentionally outside ``sphinx_interrogator`` and its built wheel. System B receives
only the returned public directory and socket paths, never the private directory.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChallengeBundle:
    """Trusted paths for one split challenge package."""

    public_directory: Path
    private_directory: Path
    private_root_file: Path


@dataclass(frozen=True, slots=True)
class PublicEndpoints:
    """Capabilities that trusted orchestration may hand to System B."""

    public_directory: Path
    vm_socket: Path
    judge_socket: Path | None


def create_private_root(binary: Path, output: Path) -> Path:
    """Create one protected 256-bit root through the Rust target CLI."""
    completed = _run(
        [str(binary), "challenge", "private-root", "--output", str(output)],
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"private root creation failed: {completed.stderr.strip()}")
    return output


def create_challenge(
    binary: Path,
    *,
    profile: Path,
    root: Path,
    private_root_file: Path,
    challenge_id: str,
    campaign_label: str,
    fault: str,
) -> ChallengeBundle:
    """Create disjoint public/private directories using a protected root."""
    public_directory = root / "public"
    private_directory = root / "private"
    completed = _run(
        [
            str(binary),
            "challenge",
            "create",
            "--profile",
            str(profile),
            "--public-output",
            str(public_directory),
            "--private-output",
            str(private_directory),
            "--private-root-file",
            str(private_root_file),
            "--challenge-id",
            challenge_id,
            "--campaign-label",
            campaign_label,
            "--fault",
            fault,
        ],
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"challenge creation failed: {completed.stderr.strip()}")
    return ChallengeBundle(public_directory, private_directory, private_root_file)


@contextmanager
def launch_endpoints(
    binary: Path,
    bundle: ChallengeBundle,
    *,
    socket_directory: Path,
    with_judge: bool,
    launcher_prefix: Sequence[str] = (),
) -> Iterator[PublicEndpoints]:
    """Launch one VM and optional one-shot judge, then expose public capabilities."""
    socket_directory.mkdir(parents=True, exist_ok=True)
    vm_socket = socket_directory / "vm.sock"
    judge_socket = socket_directory / "judge.sock" if with_judge else None
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    private_fd = os.open(bundle.private_directory, directory_flags)
    try:
        vm_process = _spawn(
            [
                *launcher_prefix,
                str(binary),
                "serve",
                "--public-challenge",
                str(bundle.public_directory),
                "--private-challenge-fd",
                str(private_fd),
                "--socket",
                str(vm_socket),
            ],
            pass_fds=(private_fd,),
        )
        judge_process = (
            _spawn(
                [
                    *launcher_prefix,
                    str(binary),
                    "judge-serve",
                    "--public-challenge",
                    str(bundle.public_directory),
                    "--private-challenge-fd",
                    str(private_fd),
                    "--socket",
                    str(judge_socket),
                ],
                pass_fds=(private_fd,),
            )
            if judge_socket is not None
            else None
        )
    finally:
        os.close(private_fd)
    try:
        _wait_for_socket(vm_process, vm_socket, "VM")
        if judge_process is not None and judge_socket is not None:
            _wait_for_socket(judge_process, judge_socket, "judge")
        yield PublicEndpoints(bundle.public_directory, vm_socket, judge_socket)
    finally:
        _stop(judge_process)
        _stop(vm_process)
        for path in (vm_socket, judge_socket):
            if path is not None:
                path.unlink(missing_ok=True)


def _spawn(
    command: Sequence[str],
    *,
    pass_fds: Sequence[int] = (),
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={"LANG": "C.UTF-8", "PATH": os.defpath},
        pass_fds=tuple(pass_fds),
    )


def _run(command: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        env={"LANG": "C.UTF-8", "PATH": os.defpath},
    )


def _wait_for_socket(process: subprocess.Popen[str], path: Path, role: str) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            stderr = "" if process.stderr is None else process.stderr.read().strip()
            raise RuntimeError(f"{role} process exited {return_code}: {stderr}")
        if path.exists():
            return
        time.sleep(0.01)
    _stop(process)
    raise RuntimeError(f"{role} process did not create its public socket")


def _stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)
