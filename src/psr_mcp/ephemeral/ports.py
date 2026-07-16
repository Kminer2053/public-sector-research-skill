"""Ports and value objects for content that must be purged."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ArtifactKind(StrEnum):
    SOURCE = "source"
    EXTRACTED = "extracted"
    RESULT = "result"


@dataclass(frozen=True, slots=True)
class WorkspaceRef:
    workspace_id: str
    created_at: datetime
    expires_at: datetime
    hard_expires_at: datetime


@dataclass(frozen=True, slots=True)
class PurgeResult:
    workspace_id: str
    deleted: bool
    already_absent: bool = False


class EphemeralWorkspaceStore(Protocol):
    async def create(
        self,
        *,
        expires_at: datetime,
        hard_expires_at: datetime,
    ) -> WorkspaceRef: ...

    async def write_bytes(
        self,
        ref: WorkspaceRef,
        kind: ArtifactKind,
        data: bytes,
    ) -> None: ...

    async def read_bytes(self, ref: WorkspaceRef, kind: ArtifactKind) -> bytes: ...

    async def block_access(self, ref: WorkspaceRef) -> None: ...

    async def purge(self, ref: WorkspaceRef) -> PurgeResult: ...

    async def purge_expired(self) -> list[PurgeResult]: ...
