"""Restricted filesystem implementation for short-lived public research content."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from psr_mcp.ephemeral.ports import ArtifactKind, PurgeResult, WorkspaceRef

_LEASE_NAME: Final = "lease.json"
_BLOCKED_NAME: Final = "purge.marker"
_ARTIFACT_NAMES: Final = {
    ArtifactKind.SOURCE: "source.bin",
    ArtifactKind.EXTRACTED: "extracted.bin",
    ArtifactKind.RESULT: "result.bin",
}


class WorkspaceAccessBlocked(RuntimeError):
    pass


class FilesystemEphemeralWorkspaceStore:
    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime],
        create_root: bool,
    ) -> None:
        self._root = root
        self._now = now
        self._create_root = create_root

    @property
    def root(self) -> Path:
        return self._root

    async def open(self) -> None:
        await asyncio.to_thread(self._open_sync)

    async def create(
        self,
        *,
        expires_at: datetime,
        hard_expires_at: datetime,
    ) -> WorkspaceRef:
        return await asyncio.to_thread(
            self._create_sync,
            expires_at,
            hard_expires_at,
        )

    async def write_bytes(
        self,
        ref: WorkspaceRef,
        kind: ArtifactKind,
        data: bytes,
    ) -> None:
        await asyncio.to_thread(self._write_sync, ref, kind, data)

    async def read_bytes(self, ref: WorkspaceRef, kind: ArtifactKind) -> bytes:
        return await asyncio.to_thread(self._read_sync, ref, kind)

    async def block_access(self, ref: WorkspaceRef) -> None:
        await asyncio.to_thread(self._block_sync, ref)

    async def purge(self, ref: WorkspaceRef) -> PurgeResult:
        return await asyncio.to_thread(self._purge_sync, ref.workspace_id)

    async def purge_expired(self) -> list[PurgeResult]:
        return await asyncio.to_thread(self._purge_expired_sync)

    def _open_sync(self) -> None:
        if self._create_root:
            self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self._root.is_absolute():
            raise ValueError("ephemeral root must be absolute")
        if not self._root.exists() or not self._root.is_dir() or self._root.is_symlink():
            raise ValueError("ephemeral root must be an existing non-symlink directory")
        mode = stat.S_IMODE(self._root.stat().st_mode)
        if mode & 0o077:
            raise ValueError("ephemeral root must not be accessible by group or others")

    def _create_sync(self, expires_at: datetime, hard_expires_at: datetime) -> WorkspaceRef:
        created_at = _utc(self._now())
        expires_at = _utc(expires_at)
        hard_expires_at = _utc(hard_expires_at)
        if expires_at <= created_at:
            raise ValueError("workspace expiry must be in the future")
        if hard_expires_at < expires_at:
            raise ValueError("hard expiry must not precede normal expiry")
        for _ in range(10):
            workspace_id = secrets.token_urlsafe(24)
            path = self._path_for(workspace_id)
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                continue
            ref = WorkspaceRef(
                workspace_id=workspace_id,
                created_at=created_at,
                expires_at=expires_at,
                hard_expires_at=hard_expires_at,
            )
            self._write_lease(path, ref)
            return ref
        raise RuntimeError("could not allocate an ephemeral workspace")

    def _write_sync(self, ref: WorkspaceRef, kind: ArtifactKind, data: bytes) -> None:
        path = self._require_accessible(ref)
        target = path / _ARTIFACT_NAMES[kind]
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)

    def _read_sync(self, ref: WorkspaceRef, kind: ArtifactKind) -> bytes:
        path = self._require_accessible(ref)
        target = path / _ARTIFACT_NAMES[kind]
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target, flags)
        try:
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)

    def _block_sync(self, ref: WorkspaceRef) -> None:
        path = self._path_for(ref.workspace_id)
        if not path.exists():
            return
        marker = path / _BLOCKED_NAME
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(marker, flags, 0o600)
        except FileExistsError:
            return
        os.close(descriptor)

    def _purge_sync(self, workspace_id: str) -> PurgeResult:
        path = self._path_for(workspace_id)
        if not path.exists():
            return PurgeResult(workspace_id=workspace_id, deleted=False, already_absent=True)
        if path.is_symlink() or not path.is_dir():
            raise ValueError("workspace path is not a safe directory")
        shutil.rmtree(path)
        return PurgeResult(workspace_id=workspace_id, deleted=True)

    def _purge_expired_sync(self) -> list[PurgeResult]:
        now = _utc(self._now())
        results: list[PurgeResult] = []
        if not self._root.exists():
            return results
        for path in self._root.iterdir():
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                ref = self._read_lease(path)
            except (OSError, ValueError, json.JSONDecodeError):
                created = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                if (now - created).total_seconds() < 7_200:
                    continue
                results.append(self._purge_sync(path.name))
                continue
            if now >= ref.expires_at or now >= ref.hard_expires_at:
                results.append(self._purge_sync(ref.workspace_id))
        return results

    def _require_accessible(self, ref: WorkspaceRef) -> Path:
        path = self._path_for(ref.workspace_id)
        if not path.exists() or path.is_symlink() or not path.is_dir():
            raise FileNotFoundError("ephemeral workspace is unavailable")
        if (path / _BLOCKED_NAME).exists():
            raise WorkspaceAccessBlocked("ephemeral workspace access is blocked")
        now = _utc(self._now())
        if now >= ref.expires_at or now >= ref.hard_expires_at:
            raise WorkspaceAccessBlocked("ephemeral workspace has expired")
        return path

    def _path_for(self, workspace_id: str) -> Path:
        if not workspace_id or any(character not in _SAFE_ID_CHARS for character in workspace_id):
            raise ValueError("invalid workspace identifier")
        candidate = self._root / workspace_id
        if candidate.parent != self._root:
            raise ValueError("workspace must remain inside the ephemeral root")
        return candidate

    def _write_lease(self, path: Path, ref: WorkspaceRef) -> None:
        payload = {
            "workspace_id": ref.workspace_id,
            "created_at": ref.created_at.isoformat(),
            "expires_at": ref.expires_at.isoformat(),
            "hard_expires_at": ref.hard_expires_at.isoformat(),
        }
        target = path / _LEASE_NAME
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
                json.dump(payload, stream, separators=(",", ":"), sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)

    def _read_lease(self, path: Path) -> WorkspaceRef:
        target = path / _LEASE_NAME
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target, flags)
        try:
            with os.fdopen(descriptor, encoding="utf-8", closefd=False) as stream:
                payload = json.load(stream)
        finally:
            os.close(descriptor)
        if payload.get("workspace_id") != path.name:
            raise ValueError("workspace lease identifier mismatch")
        return WorkspaceRef(
            workspace_id=payload["workspace_id"],
            created_at=_utc(datetime.fromisoformat(payload["created_at"])),
            expires_at=_utc(datetime.fromisoformat(payload["expires_at"])),
            hard_expires_at=_utc(datetime.fromisoformat(payload["hard_expires_at"])),
        )


_SAFE_ID_CHARS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("ephemeral timestamps must be timezone-aware")
    return value.astimezone(UTC)
