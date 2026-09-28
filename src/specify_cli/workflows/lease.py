"""Atomic, expiring ownership leases for workflow runs.

The workflow engine persists run state so a paused run can be resumed from a
new process.  A plain ``state.json`` transition is not a concurrency control
mechanism: two resumers can both read ``paused`` and both write ``running``.
This module makes the ownership transition explicit and serializes it with a
small lock file local to the run directory.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_LEASE_TTL_SECONDS = 300


class RunLeaseError(RuntimeError):
    """Base exception for a workflow-run ownership lease."""


class ActiveRunLeaseError(RunLeaseError):
    """Raised when another non-expired owner already holds the run."""


class StaleRunLeaseError(RunLeaseError):
    """Raised when reclaiming an expired lease was not explicitly authorized."""


class RunLeaseLostError(RunLeaseError):
    """Raised when this owner no longer owns the persisted lease."""

def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("Invalid workflow lease: timestamp must be a string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Invalid workflow lease: timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise TypeError("Invalid workflow lease: expected a JSON object")
    owner_nonce = record.get("owner_nonce")
    if not isinstance(owner_nonce, str) or not owner_nonce:
        raise ValueError("Invalid workflow lease: missing owner_nonce")
    _parse_timestamp(record.get("acquired_at"))
    _parse_timestamp(record.get("heartbeat_at"))
    _parse_timestamp(record.get("expires_at"))
    return record


def is_expired(record: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Return whether a validated lease record has passed its expiry time."""
    return _parse_timestamp(record["expires_at"]) <= (now or _utcnow())


def read_run_lease(run_dir: Path) -> dict[str, Any] | None:
    """Read the durable lease record, if the run currently has one."""
    path = run_dir / "lease.json"
    try:
        with path.open(encoding="utf-8") as lease_file:
            return _validate_record(json.load(lease_file))
    except FileNotFoundError:
        return None


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold a cross-process exclusive lock for the lifetime of this context."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        if os.name == "nt":  # pragma: no cover - exercised on Windows CI
            import msvcrt

            lock_file.seek(0)
            if not lock_file.read(1):
                lock_file.write("0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    fd, temporary_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as lease_file:
            json.dump(data, lease_file, indent=2)
            lease_file.flush()
            os.fsync(lease_file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


class RunLease:
    """An acquired run lease with an owner nonce and background heartbeat."""

    def __init__(
        self,
        manager: RunLeaseManager,
        record: dict[str, Any],
        recovered_lease: dict[str, Any] | None,
    ) -> None:
        self._manager = manager
        self.record = record
        self.recovered_lease = recovered_lease
        self._stopped = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._lost_error: RunLeaseLostError | None = None

    @property
    def owner_nonce(self) -> str:
        return self.record["owner_nonce"]

    def start_heartbeat(self) -> None:
        """Renew this lease periodically while a step is executing."""
        if self._heartbeat_thread is not None:
            return
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"specify-workflow-lease-{self.owner_nonce[:8]}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        interval = max(1.0, self._manager.ttl_seconds / 3)
        while not self._stopped.wait(interval):
            try:
                self.record = self._manager.heartbeat(self.owner_nonce)
            except RunLeaseLostError as exc:
                self._lost_error = exc
                return

    def assert_owned(self) -> None:
        """Fail before a state write if this process lost ownership."""
        if self._lost_error is not None:
            raise self._lost_error
        record = self._manager.assert_owner(self.owner_nonce)
        self.record = record

    def stop_heartbeat(self) -> None:
        self._stopped.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=max(1.0, self._manager.ttl_seconds))

    def release(self) -> bool:
        """Release only if this nonce is still the active owner."""
        return self._manager.release(self.owner_nonce)


class RunLeaseManager:
    """Coordinates one expiring lease file for a single workflow run."""

    def __init__(self, run_dir: Path, *, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS) -> None:
        if ttl_seconds < 3:
            raise ValueError("Workflow lease TTL must be at least 3 seconds")
        self.run_dir = run_dir
        self.ttl_seconds = ttl_seconds
        self._lease_path = run_dir / "lease.json"
        self._lock_path = run_dir / ".lease.lock"

    def _new_record(self, *, recovery_reason: str | None = None) -> dict[str, Any]:
        now = _utcnow()
        record: dict[str, Any] = {
            "owner_nonce": uuid.uuid4().hex,
            "pid": os.getpid(),
            "acquired_at": now.isoformat(),
            "heartbeat_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.ttl_seconds)).isoformat(),
        }
        if recovery_reason is not None:
            record["recovery_reason"] = recovery_reason
        return record

    def acquire(self, *, recovery_reason: str | None = None) -> RunLease:
        """Claim the run or require an explicit reason to reclaim a stale owner."""
        normalized_reason = recovery_reason.strip() if recovery_reason else None
        with _exclusive_file_lock(self._lock_path):
            existing = read_run_lease(self.run_dir)
            if existing is not None and not is_expired(existing):
                raise ActiveRunLeaseError(
                    "Workflow run is already owned by another resumer "
                    f"(nonce {existing['owner_nonce']}, expires {existing['expires_at']})."
                )
            if existing is not None and normalized_reason is None:
                raise StaleRunLeaseError(
                    "Workflow run has an expired lease. Re-run with an explicit "
                    "--recover-stale-lease reason after verifying the previous owner "
                    "is no longer executing."
                )
            record = self._new_record(recovery_reason=normalized_reason)
            _atomic_write_json(self._lease_path, record)
        return RunLease(self, record, existing)

    def assert_owner(self, owner_nonce: str) -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            current = read_run_lease(self.run_dir)
            if current is None or current["owner_nonce"] != owner_nonce:
                raise RunLeaseLostError("Workflow run lease was replaced by another owner.")
            return current

    def heartbeat(self, owner_nonce: str) -> dict[str, Any]:
        with _exclusive_file_lock(self._lock_path):
            current = read_run_lease(self.run_dir)
            if current is None or current["owner_nonce"] != owner_nonce:
                raise RunLeaseLostError("Workflow run lease was replaced by another owner.")
            now = _utcnow()
            current["heartbeat_at"] = now.isoformat()
            current["expires_at"] = (
                now + timedelta(seconds=self.ttl_seconds)
            ).isoformat()
            _atomic_write_json(self._lease_path, current)
            return current

    def release(self, owner_nonce: str) -> bool:
        with _exclusive_file_lock(self._lock_path):
            current = read_run_lease(self.run_dir)
            if current is None or current["owner_nonce"] != owner_nonce:
                return False
            self._lease_path.unlink()
            return True
