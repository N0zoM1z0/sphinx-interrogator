#!/usr/bin/env python3
"""Adversarial audit of the System A/System B process and filesystem boundary."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sphinx_interrogator.protocol import ProtocolError, decode_execute_response
from sphinx_trusted_runtime import create_challenge, create_private_root

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT_ROOTS = {"ctypes", "sphinx_vm"}
FORBIDDEN_SOURCE_MARKERS = ("/proc/", "process_vm_readv", "private/secret")
FORBIDDEN_SOURCE_PATTERNS = (re.compile(r"\bptrace\s*\("),)
FORBIDDEN_RESPONSE_KEYS = {
    "secret",
    "bank",
    "phase",
    "replay_credit",
    "pending_probe",
    "fault_delta",
    "exact_cycles",
    "noise_sample",
}
FORBIDDEN_PUBLIC_KEYS = {
    "secret",
    "permutation",
    "salts",
    "fault_variant",
    "generation_root_seed",
    "generation_root_seed_hex",
    "private_root",
    "private_root_hex",
    "noise_key",
    "noise_key_hex",
    "commitment_nonce",
    "commitment_nonce_hex",
}
VM_UID = 61_001
CLIENT_UID = 61_002

_ROOT_BROKER = r"""
import os
import subprocess
import sys

uid = int(sys.argv[1])
binary, public_dir, private_dir, socket_path, stderr_path = sys.argv[2:]
flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
private_fd = os.open(private_dir, flags)
os.set_inheritable(private_fd, True)
stderr = open(stderr_path, "wb")

def demote():
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)

command = [
    binary,
    "serve",
    "--public-challenge",
    public_dir,
    "--private-challenge-fd",
    str(private_fd),
    "--socket",
    socket_path,
]
process = subprocess.Popen(
    command,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=stderr,
    env={"LANG": "C.UTF-8", "PATH": os.defpath},
    pass_fds=(private_fd,),
    preexec_fn=demote,
    start_new_session=True,
)
print(process.pid, flush=True)
"""

_UNTRUSTED_CLIENT = r"""
import json
import socket
import sys

public_dir, socket_path = sys.argv[1:]
with open(public_dir + "/challenge.json", encoding="utf-8") as handle:
    challenge = json.load(handle)
with open(public_dir + "/profile.toml", encoding="utf-8") as handle:
    profile_prefix = handle.read(64)

transport = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
transport.connect(socket_path)
reader = transport.makefile("r", encoding="utf-8")
writer = transport.makefile("w", encoding="utf-8", newline="\n")

def exchange(request):
    writer.write(json.dumps(request, separators=(",", ":"), sort_keys=True) + "\n")
    writer.flush()
    line = reader.readline()
    if not line:
        raise RuntimeError("VM closed the public socket")
    return json.loads(line)

hello = exchange({
    "protocol_version": "1.0",
    "request_id": "isolated-hello",
    "kind": "hello",
    "client": {"name": "isolated-client", "version": "1"},
})
execution = exchange({
    "protocol_version": "1.0",
    "request_id": "isolated-execute",
    "kind": "execute",
    "session_id": "isolated-session",
    "reset": "hard",
    "program": "PROBE 0, 0, 0\nANCHOR 0, 0\nHALT\n",
    "public_input": {"registers": [], "memory": {}},
    "logical_batch_id": "isolated-batch",
    "execution_seed_id": "isolated-seed",
})
closed = exchange({
    "protocol_version": "1.0",
    "request_id": "isolated-close",
    "kind": "close",
})
writer.close()
reader.close()
transport.close()
print(json.dumps({
    "challenge_id": challenge["challenge_id"],
    "profile_prefix": profile_prefix,
    "responses": [hello, execution, closed],
}, sort_keys=True))
"""


def audit_python_sources() -> list[str]:
    """Reject imports and host-introspection markers that bypass the public protocol."""
    errors: list[str] = []
    for path in sorted((ROOT / "python/sphinx_interrogator").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names = [node.module]
            for name in names:
                if name.split(".", maxsplit=1)[0] in FORBIDDEN_IMPORT_ROOTS:
                    errors.append(f"{path.relative_to(ROOT)} imports forbidden module {name}")
        lowered = source.lower()
        for marker in FORBIDDEN_SOURCE_MARKERS:
            if marker in lowered:
                errors.append(f"{path.relative_to(ROOT)} contains forbidden marker {marker!r}")
        for pattern in FORBIDDEN_SOURCE_PATTERNS:
            if pattern.search(lowered):
                errors.append(
                    f"{path.relative_to(ROOT)} contains forbidden pattern {pattern.pattern!r}"
                )
    return errors


def walk_keys(value: Any) -> set[str]:
    """Collect all serialized mapping keys recursively."""
    if isinstance(value, dict):
        return set(value).union(*(walk_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(walk_keys(item) for item in value))
    return set()


def audit_recursive_response_validation() -> list[str]:
    """Prove nested private fields are rejected by the durable decoder."""
    response = json_load(ROOT / "tests/fixtures/protocol/execute_response.json")
    if not isinstance(response, dict) or not isinstance(response.get("observation"), dict):
        return ["execute response fixture is not schema-shaped"]
    response["observation"]["secret"] = "forbidden"
    try:
        decode_execute_response(json.dumps(response), expected_request_id="execute-1")
    except ProtocolError:
        return []
    return ["nested private response field was accepted by the public decoder"]


def audit_live_process(binary: Path) -> list[str]:
    """Run VM and client under distinct numeric UIDs with an inherited private FD."""
    errors: list[str] = []
    if os.name != "posix":
        return ["adversarial UID boundary audit requires POSIX"]
    prerequisites = (
        ("sudo", shutil.which("sudo")),
        ("setpriv", shutil.which("setpriv")),
        ("python3", "/usr/bin/python3" if Path("/usr/bin/python3").is_file() else None),
    )
    missing = [name for name, path in prerequisites if path is None]
    if missing:
        return [f"boundary audit prerequisites are missing: {missing}"]
    sudo_probe = subprocess.run(
        ["sudo", "-n", "true"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if sudo_probe.returncode != 0:
        return ["passwordless sudo is required for the adversarial UID audit"]

    vm_pid: int | None = None
    try:
        with _isolated_tempdir() as root:
            root.chmod(0o755)
            isolated_binary = root / "sphinx-vm"
            shutil.copy2(binary, isolated_binary)
            isolated_binary.chmod(0o755)
            challenge_root = root / "challenge"
            private_root = challenge_root / "private-root.bin"
            create_private_root(isolated_binary, private_root)
            bundle = create_challenge(
                isolated_binary,
                profile=ROOT / "benchmarks/profiles/tutorial.toml",
                root=challenge_root,
                private_root_file=private_root,
                challenge_id="challenge-0001",
                campaign_label="campaign-0001",
                fault="reference",
            )
            challenge_root.chmod(0o755)
            socket_directory = root / "socket"
            socket_directory.mkdir(mode=0o755)
            _sudo(
                [
                    "chown",
                    "-R",
                    f"{VM_UID}:{VM_UID}",
                    str(bundle.private_directory),
                    str(private_root),
                    str(socket_directory),
                ]
            )

            public_metadata = json_load(bundle.public_directory / "challenge.json")
            with (bundle.public_directory / "profile.toml").open("rb") as handle:
                public_profile = tomllib.load(handle)
            leaked_public = sorted(
                (walk_keys(public_metadata) | walk_keys(public_profile)).intersection(
                    FORBIDDEN_PUBLIC_KEYS
                )
            )
            if leaked_public:
                errors.append(f"public challenge artifacts contain private fields: {leaked_public}")
            errors.extend(
                _audit_modes(bundle.public_directory, bundle.private_directory, private_root)
            )

            socket_path = socket_directory / "vm.sock"
            stderr_path = root / "vm.stderr"
            broker = subprocess.run(
                [
                    "sudo",
                    "-n",
                    sys.executable,
                    "-c",
                    _ROOT_BROKER,
                    str(VM_UID),
                    str(isolated_binary),
                    str(bundle.public_directory),
                    str(bundle.private_directory),
                    str(socket_path),
                    str(stderr_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
            if broker.returncode != 0:
                return [f"root FD broker failed: {broker.stderr.strip()}"]
            vm_pid = int(broker.stdout.strip())
            _wait_for_socket(vm_pid, socket_path, stderr_path)
            errors.extend(_audit_vm_process(vm_pid, bundle.private_directory))
            proc_attempt = _run_as(CLIENT_UID, ["cat", f"/proc/{vm_pid}/environ"])
            if (
                proc_attempt.returncode == 0
                and str(bundle.private_directory) in proc_attempt.stdout
            ):
                errors.append("untrusted UID recovered the private path from VM environment")

            for private_path in (
                bundle.private_directory,
                bundle.private_directory / "secret.bin",
                bundle.private_directory / "config.toml",
                private_root,
            ):
                attempted = _run_as(CLIENT_UID, ["cat", str(private_path)])
                if attempted.returncode == 0:
                    errors.append(
                        f"untrusted UID {CLIENT_UID} read private path {private_path.name}"
                    )

            client = _run_as(
                CLIENT_UID,
                [
                    str(prerequisites[2][1]),
                    "-c",
                    _UNTRUSTED_CLIENT,
                    str(bundle.public_directory),
                    str(socket_path),
                ],
            )
            if client.returncode != 0:
                errors.append(f"isolated public client failed: {client.stderr.strip()}")
                _sudo(["kill", "-TERM", str(vm_pid)], check=False)
                vm_pid = None
            else:
                transcript = json.loads(client.stdout)
                leaked = sorted(walk_keys(transcript).intersection(FORBIDDEN_RESPONSE_KEYS))
                if leaked:
                    errors.append(f"public response contains forbidden internal fields: {leaked}")
                responses = transcript.get("responses")
                if not isinstance(responses, list) or [item.get("kind") for item in responses] != [
                    "hello_result",
                    "execute_result",
                    "close_result",
                ]:
                    errors.append("isolated public client received an invalid response sequence")
                _wait_for_exit(vm_pid, stderr_path)
                vm_pid = None
    except (OSError, ProtocolError, subprocess.TimeoutExpired, ValueError) as error:
        errors.append(f"live boundary audit failed: {error}")
    finally:
        if vm_pid is not None:
            _sudo(["kill", "-TERM", str(vm_pid)], check=False)

    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    print(f"audited target binary sha256={digest}")
    return errors


def _audit_modes(
    public_directory: Path,
    private_directory: Path,
    private_root: Path,
) -> list[str]:
    expected_modes = {
        private_directory: 0o700,
        private_directory / "judge-used": 0o700,
        private_directory / "secret.bin": 0o600,
        private_directory / "config.toml": 0o600,
        private_root: 0o600,
        public_directory: 0o755,
        public_directory / "profile.toml": 0o644,
        public_directory / "challenge.json": 0o644,
    }
    errors = []
    for path, expected in expected_modes.items():
        measured = _sudo(["stat", "-c", "%a", str(path)])
        actual = int(measured.stdout.strip(), 8)
        if actual != expected:
            errors.append(f"challenge path {path.name} has mode {actual:o}, expected {expected:o}")
    return errors


def _audit_vm_process(vm_pid: int, private_directory: Path) -> list[str]:
    errors = []
    status = Path(f"/proc/{vm_pid}/status").read_text(encoding="utf-8")
    uid_line = next((line for line in status.splitlines() if line.startswith("Uid:")), "")
    effective_uid = int(uid_line.split()[2]) if uid_line else -1
    if effective_uid != VM_UID:
        errors.append(f"VM effective UID is {effective_uid}, expected {VM_UID}")
    command_line = _sudo(["cat", f"/proc/{vm_pid}/cmdline"]).stdout.replace("\0", " ")
    if str(private_directory) in command_line:
        errors.append("VM command line exposes the private challenge path")
    environment = _sudo(["cat", f"/proc/{vm_pid}/environ"]).stdout
    if str(private_directory) in environment:
        errors.append("VM environment exposes the private challenge path")
    return errors


def _wait_for_socket(vm_pid: int, socket_path: Path, stderr_path: Path) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        if not Path(f"/proc/{vm_pid}").exists():
            raise RuntimeError(f"VM exited before socket creation: {_read_optional(stderr_path)}")
        time.sleep(0.01)
    raise RuntimeError(f"VM did not create its socket: {_read_optional(stderr_path)}")


def _wait_for_exit(vm_pid: int, stderr_path: Path) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        status_path = Path(f"/proc/{vm_pid}/status")
        if not status_path.exists():
            return
        status = status_path.read_text(encoding="utf-8")
        state_line = next((line for line in status.splitlines() if line.startswith("State:")), "")
        if "Z" in state_line:
            return
        time.sleep(0.01)
    command_line = _sudo(["cat", f"/proc/{vm_pid}/cmdline"]).stdout.replace("\0", " ")
    wait_channel = _sudo(["cat", f"/proc/{vm_pid}/wchan"]).stdout.strip()
    descriptors = _sudo(["ls", "-l", f"/proc/{vm_pid}/fd"]).stdout.strip()
    raise RuntimeError(
        f"VM did not exit after close: state={state_line!r} wchan={wait_channel!r} "
        f"cmd={command_line!r} fds={descriptors!r} stderr={_read_optional(stderr_path)}"
    )


def _run_as(uid: int, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "sudo",
            "-n",
            "setpriv",
            f"--reuid={uid}",
            f"--regid={uid}",
            "--clear-groups",
            *command,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        env={"LANG": "C.UTF-8", "PATH": os.defpath},
    )


def _sudo(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sudo", "-n", *command],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )


@contextmanager
def _isolated_tempdir() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="sphinx-boundary-"))
    try:
        yield root
    finally:
        _sudo(["rm", "-rf", str(root)], check=False)


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def json_load(path: Path) -> Any:
    """Load one public JSON document for the external boundary audit."""
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    """Run static, recursive-schema, and isolated live boundary checks."""
    configured = os.environ.get("SPHINX_VM_BINARY")
    if configured is None:
        print("SPHINX_VM_BINARY is required", file=sys.stderr)
        return 2
    binary = Path(configured).resolve()
    errors = [*audit_python_sources(), *audit_recursive_response_validation()]
    if not binary.is_file():
        errors.append(f"target binary does not exist: {binary}")
    else:
        errors.extend(audit_live_process(binary))
    if errors:
        print("boundary audit failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "boundary audit passed: recursive schema validation, FD brokering, "
        "and distinct-UID isolation held"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
