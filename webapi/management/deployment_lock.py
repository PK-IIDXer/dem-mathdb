"""Cross-process deployment lock shared by the API and schema updater."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.engine import make_url


DEPLOYMENT_LOCK_ENV = "DEM_WORKSPACE_DEPLOYMENT_LOCK_PATH"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    # msvcrt.locking has no shared mode (LK_RLCK / LK_NBRLCK behave exactly like
    # LK_LOCK / LK_NBLCK), so two API processes could not both hold the "shared"
    # lock.  LockFileEx without LOCKFILE_EXCLUSIVE_LOCK is a real shared lock.
    _LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
    _LOCKFILE_EXCLUSIVE_LOCK = 0x00000002

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.LockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    ]
    _kernel32.LockFileEx.restype = wintypes.BOOL
    _kernel32.UnlockFileEx.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    ]
    _kernel32.UnlockFileEx.restype = wintypes.BOOL

    def _lock_byte(handle: BinaryIO, *, exclusive: bool) -> None:
        flags = _LOCKFILE_FAIL_IMMEDIATELY
        if exclusive:
            flags |= _LOCKFILE_EXCLUSIVE_LOCK
        overlapped = _Overlapped()
        if not _kernel32.LockFileEx(
            msvcrt.get_osfhandle(handle.fileno()), flags, 0, 1, 0, ctypes.byref(overlapped)
        ):
            raise OSError(ctypes.get_last_error(), "LockFileEx failed")

    def _unlock_byte(handle: BinaryIO) -> None:
        overlapped = _Overlapped()
        if not _kernel32.UnlockFileEx(
            msvcrt.get_osfhandle(handle.fileno()), 0, 1, 0, ctypes.byref(overlapped)
        ):
            raise OSError(ctypes.get_last_error(), "UnlockFileEx failed")

else:
    import fcntl

    def _lock_byte(handle: BinaryIO, *, exclusive: bool) -> None:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)

    def _unlock_byte(handle: BinaryIO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class DeploymentLockBusy(RuntimeError):
    pass


def deployment_lock_path(management_database_url: str | None) -> Path:
    configured = os.environ.get(DEPLOYMENT_LOCK_ENV, "").strip()
    if configured:
        return Path(configured).resolve()
    if management_database_url:
        url = make_url(management_database_url)
        if url.get_backend_name() == "sqlite" and url.database not in (
            None,
            "",
            ":memory:",
        ):
            database = Path(url.database).resolve()
            return database.parent / ".workspace-schema.lock"
        identity = hashlib.sha256(management_database_url.encode()).hexdigest()[:16]
        return _REPOSITORY_ROOT / "build" / f"workspace-schema-{identity}.lock"
    return _REPOSITORY_ROOT / "build" / ".workspace-schema.lock"


class DeploymentLock:
    """A one-byte shared/exclusive lock held for the object's lifetime."""

    def __init__(self, path: Path, *, exclusive: bool) -> None:
        self.path = path
        self.exclusive = exclusive
        self._file: BinaryIO | None = None

    def acquire(self) -> "DeploymentLock":
        if self._file is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        if handle.tell() == 0:
            try:
                handle.write(b"\0")
                handle.flush()
            except OSError:
                # Another process created the byte and locked it first; the lock
                # attempt below reports whether that holder conflicts with us.
                pass
        handle.seek(0)
        try:
            _lock_byte(handle, exclusive=self.exclusive)
        except (BlockingIOError, OSError) as exc:
            handle.close()
            raise DeploymentLockBusy(f"deployment lock is busy: {self.path}") from exc
        self._file = handle
        return self

    def release(self) -> None:
        handle, self._file = self._file, None
        if handle is None:
            return
        try:
            handle.seek(0)
            _unlock_byte(handle)
        finally:
            handle.close()

    def __enter__(self) -> "DeploymentLock":
        return self.acquire()

    def __exit__(self, *exc_info: object) -> None:
        self.release()
