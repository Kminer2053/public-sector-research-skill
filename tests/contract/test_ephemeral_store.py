from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from psr_mcp.ephemeral.filesystem import (
    FilesystemEphemeralWorkspaceStore,
    WorkspaceAccessBlocked,
)
from psr_mcp.ephemeral.ports import ArtifactKind, WorkspaceRef


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


@pytest.mark.anyio
async def test_workspace_permissions_write_read_block_and_purge(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 7, 16, tzinfo=UTC))
    root = tmp_path / "ephemeral"
    store = FilesystemEphemeralWorkspaceStore(root, now=clock.now, create_root=True)
    await store.open()
    ref = await store.create(
        expires_at=clock.value + timedelta(hours=1),
        hard_expires_at=clock.value + timedelta(hours=2),
    )
    workspace = root / ref.workspace_id

    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    await store.write_bytes(ref, ArtifactKind.SOURCE, b"content-canary")
    assert await store.read_bytes(ref, ArtifactKind.SOURCE) == b"content-canary"
    assert stat.S_IMODE((workspace / "source.bin").stat().st_mode) == 0o600

    await store.block_access(ref)
    with pytest.raises(WorkspaceAccessBlocked):
        await store.read_bytes(ref, ArtifactKind.SOURCE)
    result = await store.purge(ref)
    assert result.deleted is True
    assert not workspace.exists()
    assert (await store.purge(ref)).already_absent is True


@pytest.mark.anyio
async def test_expired_workspace_is_purged_with_fake_clock(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 7, 16, tzinfo=UTC))
    store = FilesystemEphemeralWorkspaceStore(
        tmp_path / "ephemeral",
        now=clock.now,
        create_root=True,
    )
    await store.open()
    ref = await store.create(
        expires_at=clock.value + timedelta(minutes=10),
        hard_expires_at=clock.value + timedelta(hours=2),
    )
    await store.write_bytes(ref, ArtifactKind.RESULT, b"result-canary")
    clock.value += timedelta(minutes=11)

    results = await store.purge_expired()
    assert [result.workspace_id for result in results] == [ref.workspace_id]
    assert not (store.root / ref.workspace_id).exists()


@pytest.mark.anyio
async def test_workspace_rejects_unsafe_ids_and_symlink_root(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 7, 16, tzinfo=UTC))
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    os.symlink(real, linked)
    store = FilesystemEphemeralWorkspaceStore(linked, now=clock.now, create_root=False)
    with pytest.raises(ValueError, match="non-symlink"):
        await store.open()

    safe = FilesystemEphemeralWorkspaceStore(real, now=clock.now, create_root=False)
    await safe.open()
    bad = WorkspaceRef(
        workspace_id="../escape",
        created_at=clock.value,
        expires_at=clock.value + timedelta(hours=1),
        hard_expires_at=clock.value + timedelta(hours=2),
    )
    with pytest.raises(ValueError, match="identifier"):
        await safe.purge(bad)


@pytest.mark.anyio
async def test_root_and_timestamp_guards_fail_closed(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 7, 16, tzinfo=UTC))
    with pytest.raises(ValueError, match="absolute"):
        await FilesystemEphemeralWorkspaceStore(
            Path("relative"),
            now=clock.now,
            create_root=False,
        ).open()

    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="existing"):
        await FilesystemEphemeralWorkspaceStore(
            missing,
            now=clock.now,
            create_root=False,
        ).open()

    permissive = tmp_path / "permissive"
    permissive.mkdir(mode=0o755)
    permissive.chmod(0o755)
    with pytest.raises(ValueError, match="group or others"):
        await FilesystemEphemeralWorkspaceStore(
            permissive,
            now=clock.now,
            create_root=False,
        ).open()

    root = tmp_path / "safe"
    root.mkdir(mode=0o700)
    store = FilesystemEphemeralWorkspaceStore(root, now=clock.now, create_root=False)
    await store.open()
    with pytest.raises(ValueError, match="future"):
        await store.create(
            expires_at=clock.value,
            hard_expires_at=clock.value + timedelta(hours=1),
        )
    with pytest.raises(ValueError, match="hard expiry"):
        await store.create(
            expires_at=clock.value + timedelta(hours=2),
            hard_expires_at=clock.value + timedelta(hours=1),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        await store.create(
            expires_at=datetime(2026, 7, 16, 1, 0),
            hard_expires_at=clock.value + timedelta(hours=1),
        )


@pytest.mark.anyio
async def test_collision_block_and_unsafe_workspace_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(datetime(2026, 7, 16, tzinfo=UTC))
    root = tmp_path / "ephemeral"
    store = FilesystemEphemeralWorkspaceStore(root, now=clock.now, create_root=True)
    await store.open()
    (root / "collision").mkdir(mode=0o700)
    values: Iterator[str] = iter(("collision", "allocated"))
    monkeypatch.setattr(
        "psr_mcp.ephemeral.filesystem.secrets.token_urlsafe",
        lambda _length: next(values),
    )
    ref = await store.create(
        expires_at=clock.value + timedelta(hours=1),
        hard_expires_at=clock.value + timedelta(hours=2),
    )
    assert ref.workspace_id == "allocated"

    await store.block_access(ref)
    await store.block_access(ref)
    await store.purge(ref)
    await store.block_access(ref)

    unsafe_file = root / "unsafe-file"
    unsafe_file.write_bytes(b"not-a-directory")
    unsafe_ref = WorkspaceRef(
        workspace_id="unsafe-file",
        created_at=clock.value,
        expires_at=clock.value + timedelta(hours=1),
        hard_expires_at=clock.value + timedelta(hours=2),
    )
    with pytest.raises(ValueError, match="safe directory"):
        await store.purge(unsafe_ref)


@pytest.mark.anyio
async def test_expiry_scan_handles_corrupt_and_non_workspace_entries(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 7, 16, tzinfo=UTC))
    root = tmp_path / "ephemeral"
    store = FilesystemEphemeralWorkspaceStore(root, now=clock.now, create_root=True)
    assert await store.purge_expired() == []
    await store.open()

    recent = root / "recent-corrupt"
    recent.mkdir(mode=0o700)
    (recent / "lease.json").write_text("{bad-json")
    ignored_file = root / "ordinary-file"
    ignored_file.write_text("ignore")

    old = root / "old-corrupt"
    old.mkdir(mode=0o700)
    (old / "lease.json").write_text("{bad-json")
    old_timestamp = (clock.value - timedelta(hours=3)).timestamp()
    os.utime(old, (old_timestamp, old_timestamp))

    results = await store.purge_expired()
    assert [result.workspace_id for result in results] == ["old-corrupt"]
    assert recent.exists()
    assert ignored_file.exists()


@pytest.mark.anyio
async def test_missing_expired_and_mismatched_workspace_access(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 7, 16, tzinfo=UTC))
    root = tmp_path / "ephemeral"
    store = FilesystemEphemeralWorkspaceStore(root, now=clock.now, create_root=True)
    await store.open()
    ref = await store.create(
        expires_at=clock.value + timedelta(minutes=1),
        hard_expires_at=clock.value + timedelta(hours=2),
    )

    missing = WorkspaceRef(
        workspace_id="missing",
        created_at=clock.value,
        expires_at=clock.value + timedelta(hours=1),
        hard_expires_at=clock.value + timedelta(hours=2),
    )
    with pytest.raises(FileNotFoundError):
        await store.read_bytes(missing, ArtifactKind.RESULT)

    clock.value += timedelta(minutes=2)
    with pytest.raises(WorkspaceAccessBlocked, match="expired"):
        await store.write_bytes(ref, ArtifactKind.RESULT, b"late")

    lease = root / ref.workspace_id / "lease.json"
    payload = lease.read_text().replace(ref.workspace_id, "different")
    lease.write_text(payload)
    old_timestamp = (clock.value - timedelta(hours=3)).timestamp()
    os.utime(root / ref.workspace_id, (old_timestamp, old_timestamp))
    results = await store.purge_expired()
    assert [result.workspace_id for result in results] == [ref.workspace_id]
