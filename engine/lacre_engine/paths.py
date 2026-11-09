"""Where the engine keeps its temporary files, and the startup sweep of what a killed engine left behind.

Kept free of pymobiledevice3 imports so the server can sweep at startup without paying that import."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

log = logging.getLogger("lacre.paths")

PENDING_NAME = "pending-cleanups.json"


def temp_parent() -> Path:
    """One app-owned folder for every sysdiagnose download, so leftovers can be swept safely."""
    return Path(tempfile.gettempdir()) / "lacre-fdr"


def pending_file() -> Path:
    """Device cleanups still to do (survives an app close; resumed at the next start)."""
    return temp_parent() / PENDING_NAME


# A download written to in the last minutes may belong to another running copy of the app: left alone.
BUSY_S = 600


def _recently_written(p: Path, now: float) -> bool:
    try:
        stamps = [p.stat().st_mtime] + ([c.stat().st_mtime for c in p.rglob("*")] if p.is_dir() else [])
    except OSError:
        return False
    return now - max(stamps) < BUSY_S


def sweep_local_temp() -> int:
    """Delete downloads left by an engine that was killed mid-check (they hold the seller's logs).

    Removes what is in temp_parent() except the pending-cleanups file, plus the `lacre-fdr-*` folders
    that version 0.1.0 created directly in the temp folder, skipping anything written in the last
    BUSY_S (another copy of the app may be downloading). Returns how many entries were removed."""
    import time

    now = time.time()
    removed = 0
    parent = temp_parent()
    candidates = [p for p in parent.iterdir() if p.name != PENDING_NAME] if parent.is_dir() else []
    candidates += [p for p in Path(tempfile.gettempdir()).glob("lacre-fdr-*") if p.is_dir()]
    for p in candidates:
        if _recently_written(p, now):
            continue
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            removed += 1
        except OSError as e:
            log.warning("could not remove a leftover temp entry: %s", type(e).__name__)
    if removed:
        log.info("removed %d leftover download(s) from an earlier session", removed)
    return removed
