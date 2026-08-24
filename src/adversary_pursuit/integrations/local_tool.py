"""Bounded, shell-free execution boundary for optional local analysis tools."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LocalToolReceipt(BaseModel):
    """Secret-safe receipt for one deterministic local tool invocation."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-local-tool-receipt-1.0"] = (
        "pivotglass-local-tool-receipt-1.0"
    )
    system: Literal["go-roast", "nucleotide"]
    operation: str
    executable: str
    request_sha256: str
    started_at: datetime
    completed_at: datetime
    exit_code: int
    output_bytes: int
    complete: bool
    boundary_reason: str | None = None


@dataclass(frozen=True)
class LocalToolResult:
    stdout: str
    stderr: str
    receipt: LocalToolReceipt


class LocalToolRunner:
    """Execute a configured binary without a shell and with bounded output."""

    def __init__(
        self,
        system: Literal["go-roast", "nucleotide"],
        executable: str,
        *,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> None:
        self.system = system
        self.executable = _resolve_executable(executable)
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def run(self, operation: str, args: list[str], *, stdin: str = "") -> LocalToolResult:
        request_sha256 = hashlib.sha256(
            json.dumps(
                {"system": self.system, "operation": operation, "args": args, "stdin": stdin},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        started_at = datetime.now(UTC)
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                [self.executable, *args],
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                shell=False,
                close_fds=True,
                env=_minimal_environment(),
            )
            boundary_reason: str | None = None
            assert process.stdin is not None
            process.stdin.write(stdin)
            process.stdin.close()
            deadline = time.monotonic() + self.timeout_seconds
            while process.poll() is None:
                output_bytes = os.fstat(stdout_file.fileno()).st_size + os.fstat(
                    stderr_file.fileno()
                ).st_size
                if output_bytes > self.max_output_bytes:
                    boundary_reason = "output_limit"
                    process.kill()
                    break
                if time.monotonic() >= deadline:
                    boundary_reason = "timeout"
                    process.kill()
                    break
                time.sleep(0.01)
            process.wait()
            if boundary_reason is None and (
                os.fstat(stdout_file.fileno()).st_size
                + os.fstat(stderr_file.fileno()).st_size
                > self.max_output_bytes
            ):
                boundary_reason = "output_limit"

            if process.returncode is None:
                process.kill()
                process.wait()

            stdout_size = os.fstat(stdout_file.fileno()).st_size
            stderr_size = os.fstat(stderr_file.fileno()).st_size
            output_bytes = stdout_size + stderr_size
            if output_bytes > self.max_output_bytes:
                boundary_reason = boundary_reason or "output_limit"
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(min(stdout_size, self.max_output_bytes)).decode(
                "utf-8", errors="replace"
            )
            remaining = max(0, self.max_output_bytes - len(stdout.encode()))
            stderr = stderr_file.read(remaining).decode("utf-8", errors="replace")

        completed_at = datetime.now(UTC)
        exit_code = int(process.returncode or 0)
        complete = boundary_reason is None and exit_code == 0
        receipt = LocalToolReceipt(
            system=self.system,
            operation=operation,
            executable=self.executable,
            request_sha256=request_sha256,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=exit_code,
            output_bytes=output_bytes,
            complete=complete,
            boundary_reason=boundary_reason,
        )
        if boundary_reason == "timeout":
            raise ValueError(f"{self.system} exceeded the configured time budget")
        if boundary_reason == "output_limit":
            raise ValueError(f"{self.system} exceeded the configured output budget")
        if exit_code != 0:
            detail = _safe_error(stderr)
            raise ValueError(f"{self.system} failed with exit code {exit_code}: {detail}")
        return LocalToolResult(stdout=stdout, stderr=stderr, receipt=receipt)


def local_tool_status(executable: str) -> dict[str, str | bool]:
    """Return non-executing availability state for one configured binary."""
    try:
        resolved = _resolve_executable(executable)
    except ValueError:
        return {"configured": bool(executable), "available": False, "executable": executable}
    return {"configured": True, "available": True, "executable": resolved}


def _resolve_executable(value: str) -> str:
    candidate = value.strip()
    if not candidate or "\x00" in candidate:
        raise ValueError("local integration executable is missing or invalid")
    if os.sep in candidate or (os.altsep and os.altsep in candidate):
        path = Path(candidate).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"configured executable is unavailable: {candidate}")
        return str(path)
    resolved = shutil.which(candidate)
    if not resolved:
        raise ValueError(f"configured executable is not on PATH: {candidate}")
    return str(Path(resolved).resolve())


def _minimal_environment() -> dict[str, str]:
    allowed = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")
    return {name: os.environ[name] for name in allowed if name in os.environ}


def _safe_error(value: str) -> str:
    compact = " ".join(value.split())
    return compact[:500] or "no diagnostic was returned"
