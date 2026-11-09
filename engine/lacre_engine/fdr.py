"""Factory record (FDR) through a sysdiagnose triggered on the device by the buttons.

Same steps as `pymobiledevice3 crash sysdiagnose OUT --erase`, done here so each one emits a stage event,
can be cancelled and survives the iPhone dropping off USB:

  waiting_trigger -> (user presses the buttons) -> generating -> downloading -> extracting -> cleaning -> done
  (any of the first three can go to `reconnecting` and back)

Only `logs/FDR/FDRDiagnosticReport.plist` and `logs/BatteryHealth/BatteryHealth.log` are read from the
archive. The download lives in one app-owned temp folder (paths.temp_parent()) that is removed before
answering, on cancel, and swept at the next start if the engine was killed.

The check lists DiagnosticLogs/sysdiagnose first. What it deletes there (its only writes on the device):
- the archive it downloaded, right after the download;
- any other archive that was not in that first listing (an extra button press, or a press right after a
  cancel), so the check leaves nothing behind. Archives already on the phone are never touched here: they
  are returned in `other_archives` and deleted only through `delete_archives`, when the user asks.

Device loss: every device operation has a watchdog (an unplugged iPhone does not always close the usbmux
socket). On loss the engine emits `reconnecting`, waits for the iPhone and resumes the same phase (the
download resumes at the same byte). It gives up with the last error only after RECONNECT_TIMEOUT_S
without any progress.

Cleanup that cannot finish now (device gone, archive still being written, cancel) is saved to
paths.pending_file() and retried in the background, and again at the next engine start.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import math
import plistlib
import re
import shutil
import tarfile
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, Optional

from . import paths
from .collect import to_jsonable
from .errors import EngineError, map_exception, short

log = logging.getLogger("lacre.fdr")

Stage = Callable[[str], Awaitable[None]]
Progressed = Callable[[], Awaitable[None]]

FDR_PLIST = "logs/FDR/FDRDiagnosticReport.plist"
BATTERY_LOG = "logs/BatteryHealth/BatteryHealth.log"
RX_MAX_CAPACITY = re.compile(r'"Maximum Capacity Percent"\s*=\s*(\d+)')
# Upper bound for one member we read (the FDR plist is a few KB; the battery log well under 1 MB).
MAX_MEMBER_BYTES = 32 * 1024 * 1024

# A device operation that answers nothing for this long counts as a lost device.
STALL_TIMEOUT_S = 30
CLOSE_TIMEOUT_S = 5
# After losing the device: how long to wait without any progress, and how often to try again.
RECONNECT_TIMEOUT_S = 900
RECONNECT_POLL_S = 3
# Polling the folder while waiting for the buttons and while the iPhone writes the archive.
TRIGGER_POLL_S = 0.5
GENERATE_POLL_S = 2
# Time the iPhone gets to write the archive once it started (on top of the wait for the buttons).
GENERATE_TIMEOUT_S = 1200
# The archive is complete when its final name is there, nothing is still being written and its size is
# stable for this long (pymobiledevice3 waits 3 s after the "stopped" notification for the same reason).
SETTLE_S = 3
CHUNK_BYTES = 1024 * 1024
# Background cleanup: polling while it is fresh, then a slow retry for as long as the app is open, and
# how long it keeps watching after a cancel in waiting_trigger (the buttons may be pressed right after).
DEFERRED_CLEANUP_TIMEOUT_S = 1800
DEFERRED_CLEANUP_POLL_S = 10
DEFERRED_CLEANUP_SLOW_POLL_S = 120
WATCH_AFTER_CANCEL_S = 180
# Saved cleanups older than this are dropped (iOS has pruned the archive by then).
PENDING_MAX_AGE_S = 7 * 24 * 3600
# Pairing ("Trust this computer?") may wait for a person; the connect itself still has a ceiling.
PAIR_TIMEOUT_S = 120
# Archives the check may delete besides its own: dated inside the check's window, widened by this much
# for the difference between the iPhone's clock and the PC's.
CLOCK_SKEW_S = 600

SYSDIAGNOSE_DIR = "DiagnosticLogs/sysdiagnose"
RX_FINAL_ARCHIVE = re.compile(r"^sysdiagnose_[^/\\]+\.tar\.gz$")
RX_ARCHIVE_DATE = re.compile(
    r"^sysdiagnose_(\d{4})\.(\d{2})\.(\d{2})_(\d{2})-(\d{2})-(\d{2})(?:-?([+-])(\d{2})(\d{2}))?")
# Error codes that mean "the device is (temporarily) unreachable": worth waiting for.
LOST_CODES = ("device_gone", "no_device", "usbmux_unavailable", "passcode_required")

# Background cleanup tasks (kept referenced so they are not garbage-collected).
_background: set[asyncio.Task] = set()
# Archives a running check is working on right now: background cleanups never touch them.
_claimed: set[str] = set()


def _fdr_to_json(v: Any) -> Any:
    """FDR plist -> JSON. bytes -> plain hex string (as the prototype did), dates -> ISO text."""
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    if isinstance(v, dict):
        return {str(k): _fdr_to_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_fdr_to_json(x) for x in v]
    return to_jsonable(v)


def extract_report(archive: Path) -> dict:
    """Read only the two wanted members from a sysdiagnose .tar.gz and build a RawFdr."""
    found: dict[str, bytes] = {}
    with tarfile.open(archive, mode="r:*") as t:
        for m in t:
            if "/._" in m.name or not m.isfile():
                continue
            for target in (FDR_PLIST, BATTERY_LOG):
                if target not in found and m.name.endswith(target):
                    if m.size > MAX_MEMBER_BYTES:
                        log.warning("member %s too large (%d bytes), skipped", target, m.size)
                        continue
                    f = t.extractfile(m)
                    if f is not None:
                        found[target] = f.read()
            if len(found) == 2:
                break
    res: dict = {"has_fdr": FDR_PLIST in found, "fdr": None, "battery_health_percent": None, "seal_date": None}
    if res["has_fdr"]:
        try:
            fdr = _fdr_to_json(plistlib.loads(found[FDR_PLIST]))
            res["fdr"] = json.loads(json.dumps(fdr))
            if isinstance(fdr, dict) and fdr.get("SealDate") is not None:
                res["seal_date"] = str(fdr.get("SealDate"))
        except Exception as e:  # noqa: BLE001  corrupt plist = no usable record
            log.warning("FDR plist unreadable: %s", short(e))
            res["has_fdr"] = False
    if BATTERY_LOG in found:
        m = RX_MAX_CAPACITY.search(found[BATTERY_LOG].decode("utf-8", "replace"))
        res["battery_health_percent"] = int(m.group(1)) if m else None
    return res


# ------------------------------------------------------------------ archive names


def final_archive_name(entry: str) -> Optional[str]:
    """Final archive name for a listing entry, or None if the entry is not a sysdiagnose archive.

    `IN_PROGRESS_sysdiagnose_X.tmp` and `IN_PROGRESS_sysdiagnose_X.tar.gz` (still being written) map to
    `sysdiagnose_X.tar.gz`, as pymobiledevice3 does when it detects a new sysdiagnose."""
    name = entry
    if "IN_PROGRESS_" in name:
        name = name.replace("IN_PROGRESS_", "")
        for ext in (".tmp", ".tar.gz"):
            if name.endswith(ext):
                name = name[: -len(ext)] + ".tar.gz"
                break
        else:
            return None
    return name if RX_FINAL_ARCHIVE.match(name) else None


def finals_of(entries: Iterable[str]) -> frozenset[str]:
    """Final names of every archive in a listing, finished or still being written."""
    return frozenset(f for f in (final_archive_name(e) for e in entries) if f)


def archive_date(name: str) -> Optional[str]:
    """Local date-time in the archive name (`sysdiagnose_2026.11.09_07-40-22-0300_...`) as ISO text."""
    m = RX_ARCHIVE_DATE.match(name)
    if not m:
        return None
    y, mo, d, h, mi, s = m.groups()[:6]
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}"


def archive_epoch(name: str) -> Optional[float]:
    """When the iPhone created the archive, from its name (UTC offset in the name; PC local time if none)."""
    import datetime as dt

    m = RX_ARCHIVE_DATE.match(name)
    if not m:
        return None
    y, mo, d, h, mi, s, sign, oh, om = m.groups()
    try:
        if sign:
            tz = dt.timezone((-1 if sign == "-" else 1) * dt.timedelta(hours=int(oh), minutes=int(om)))
            return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), tzinfo=tz).timestamp()
        return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s)).timestamp()
    except (ValueError, OverflowError):
        return None


def in_window(name: str, window: Optional[tuple[float, float]]) -> bool:
    """True when the archive was created inside the check's time window (so the check made it)."""
    if window is None:
        return False
    t = archive_epoch(name)
    return t is not None and window[0] - CLOCK_SKEW_S <= t <= window[1] + CLOCK_SKEW_S


def _path(name: str) -> str:
    return f"{SYSDIAGNOSE_DIR}/{name}"


# ------------------------------------------------------------------ device plumbing


async def _maybe_await(v: Any) -> Any:
    return await v if inspect.isawaitable(v) else v


async def _step(aw: Awaitable[Any], what: str) -> Any:
    """One device operation with the stall watchdog."""
    try:
        return await asyncio.wait_for(aw, STALL_TIMEOUT_S)
    except asyncio.TimeoutError as e:
        raise EngineError("device_gone", f"{what}: no answer for {STALL_TIMEOUT_S}s") from e


async def _quiet_close(aw: Awaitable[Any]) -> None:
    try:
        await asyncio.wait_for(aw, CLOSE_TIMEOUT_S)
    except Exception:  # noqa: BLE001  closing a dead connection may fail or hang; nothing to do about it
        pass


@asynccontextmanager
async def _connect(udid: str, autopair: bool = False) -> AsyncIterator[Any]:
    """Lockdown + CrashReportsManager whose teardown can never hang on a dead connection."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.crash_reports import CrashReportsManager

    if autopair:
        # the "Trust this computer?" prompt may be waiting for a person: a longer ceiling, never none
        create = create_using_usbmux(serial=udid, autopair=True, connection_type="USB", pair_timeout=PAIR_TIMEOUT_S)
        try:
            lockdown = await asyncio.wait_for(create, PAIR_TIMEOUT_S + STALL_TIMEOUT_S)
        except asyncio.TimeoutError as e:
            raise EngineError("device_gone", f"connect: no answer for {PAIR_TIMEOUT_S + STALL_TIMEOUT_S}s") from e
    else:
        lockdown = await _step(create_using_usbmux(serial=udid, autopair=False, connection_type="USB"), "connect")
    try:
        cm = CrashReportsManager(lockdown)
        await _step(cm.__aenter__(), "open diagnostics folder")
        try:
            yield cm
        finally:
            await _quiet_close(cm.__aexit__(None, None, None))
    finally:
        await _quiet_close(_maybe_await(lockdown.close()))


async def _list(afc) -> list[str]:
    """The sysdiagnose folder listing; a folder that does not exist yet is empty."""
    from pymobiledevice3.exceptions import AfcFileNotFoundError

    try:
        return list(await _step(afc.listdir(SYSDIAGNOSE_DIR), "list diagnostics"))
    except AfcFileNotFoundError:
        return []


async def _remote_rm(afc, remote_path: str) -> bool:
    """Delete one archive on the device and confirm it is gone."""
    await _step(afc.rm_single(remote_path, force=True), "delete")
    try:
        return not await _step(afc.exists(remote_path), "check deletion")
    except Exception:  # noqa: BLE001
        return False


async def _run_resilient(udid: str, stage: Stage, resume_stage: str,
                         op: Callable[[Any, Progressed], Awaitable[Any]],
                         deadline: Optional[float] = None) -> Any:
    """Run `op(cm, progressed)` on a fresh connection; if the device is lost, emit `reconnecting`, wait for
    it and run `op` again (it keeps its own state, so it resumes). `op` calls `progressed()` whenever it
    gets real work done; only that resets the clock, so a device that reconnects but never delivers
    anything still ends with an error after RECONNECT_TIMEOUT_S."""
    lost_since: Optional[float] = None
    last: Optional[EngineError] = None

    async def progressed() -> None:
        nonlocal lost_since
        if lost_since is not None:
            lost_since = None
            log.info("fdr: device back, %s resumed", resume_stage)
            await stage(resume_stage)

    while True:
        try:
            async with _connect(udid) as cm:
                return await op(cm, progressed)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            err = map_exception(e)
            if err.code not in LOST_CODES:
                raise err from e
            last = err
        now = time.monotonic()
        if deadline is not None and now > deadline:
            raise EngineError("timeout", f"{resume_stage}: time is up while the device was away ({last.detail})")
        if lost_since is None:
            lost_since = now
            log.warning("fdr: device lost during %s (%s); waiting for it", resume_stage, last.detail)
            await stage("reconnecting")
        elif now - lost_since > RECONNECT_TIMEOUT_S:
            raise EngineError(last.code, f"no progress for {RECONNECT_TIMEOUT_S}s after losing the device "
                                         f"({last.detail})")
        await asyncio.sleep(RECONNECT_POLL_S)


# ------------------------------------------------------------------ cleanup (now, later, after a restart)


@dataclass
class _Job:
    """What one check may delete on the device and what is still to do. Saved to disk before the check
    can create anything, so it survives an app close, a crash or a power cut."""

    key: str
    udid: str
    before: Optional[frozenset[str]]  # final names listed when the check started (never deleted)
    window: tuple[float, float]  # epoch range in which this check could have made an archive
    own: Optional[str] = None  # path of the archive the check took as its own
    done: set[str] = field(default_factory=set)  # paths already deleted
    created: float = field(default_factory=time.time)

    def to_json(self) -> dict:
        return {"key": self.key, "udid": self.udid, "before": sorted(self.before) if self.before is not None else None,
                "window": list(self.window), "own": self.own, "done": sorted(self.done), "created": self.created}

    @staticmethod
    def from_json(e: Any) -> "_Job":
        """Strict: anything malformed raises ValueError (that entry is dropped, the others still run)."""
        if not isinstance(e, dict):
            raise ValueError("not an object")
        key, udid, own = e.get("key"), e.get("udid"), e.get("own")
        before, window, done, created = e.get("before"), e.get("window"), e.get("done") or [], e.get("created")
        if not (isinstance(key, str) and isinstance(udid, str) and udid and (own is None or isinstance(own, str))):
            raise ValueError("bad key, udid or own")
        if before is not None and not (isinstance(before, list) and all(isinstance(x, str) for x in before)):
            raise ValueError("bad before")
        if not (isinstance(window, list) and len(window) == 2
                and all(isinstance(x, (int, float)) and math.isfinite(x) for x in window)):
            raise ValueError("bad window")
        if not (isinstance(done, list) and all(isinstance(x, str) for x in done)):
            raise ValueError("bad done")
        if not (isinstance(created, (int, float)) and math.isfinite(created) and created <= time.time() + CLOCK_SKEW_S):
            raise ValueError("bad created")
        return _Job(key, udid, frozenset(before) if before is not None else None, (float(window[0]), float(window[1])),
                    own, set(done), float(created))


async def _sweep_new(afc, job: _Job) -> bool:
    """Delete the archives this check created; True when none is left (none present, none being written).

    "Created by this check" = the check's own archive, or one whose final name was not listed when the check
    started AND whose date (in its name) falls in the check's time window. The date bound keeps a cleanup
    resumed days later from deleting archives the owner made since. With `before` unknown only `own` counts.
    An IN_PROGRESS leftover of an archive already deleted (`done`) is not waited for."""
    pending = False
    for entry in await _list(afc):
        final = final_archive_name(entry)
        if final is None:
            continue
        path = _path(final)
        if path != job.own and (job.before is None or final in job.before or not in_window(final, job.window)):
            continue
        if path in _claimed:
            continue  # a running check is working on it and deletes it itself
        if entry != final:  # still being written
            if path not in job.done:
                pending = True
            continue
        if await _remote_rm(afc, path):
            job.done.add(path)
            if path != job.own:
                log.info("fdr: extra sysdiagnose created during the check deleted: %s", final)
        else:
            pending = True
    return not pending


def _pending_load() -> list[Any]:
    try:
        data = json.loads(paths.pending_file().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _pending_write(entries: list[dict]) -> None:
    f = paths.pending_file()
    try:
        if not entries:
            f.unlink(missing_ok=True)
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries), encoding="utf-8")
        tmp.replace(f)
    except OSError as e:
        log.warning("pending cleanups not saved: %s", short(e))


def _save(job: _Job) -> None:
    entries = [e for e in _pending_load() if not (isinstance(e, dict) and e.get("key") == job.key)]
    _pending_write(entries + [job.to_json()])


def _pending_drop(key: str) -> None:
    entries = _pending_load()
    left = [e for e in entries if not (isinstance(e, dict) and e.get("key") == key)]
    if len(left) != len(entries):
        _pending_write(left)


async def _deferred_cleanup(job: _Job, watch_s: float) -> None:
    """Keep trying to delete what a check created (device unplugged, archive still being written, buttons
    pressed after a cancel), for as long as the app is open and the entry is fresh: every
    DEFERRED_CLEANUP_POLL_S at first, then every DEFERRED_CLEANUP_SLOW_POLL_S. Keeps watching for at
    least `watch_s` even when the folder is clean."""
    start = time.monotonic()
    fresh_until = start + max(DEFERRED_CLEANUP_TIMEOUT_S, watch_s)

    def poll() -> float:
        return DEFERRED_CLEANUP_POLL_S if time.monotonic() < fresh_until else DEFERRED_CLEANUP_SLOW_POLL_S

    def alive() -> bool:
        return time.time() - job.created < PENDING_MAX_AGE_S

    reported = False
    while alive():
        try:
            async with _connect(job.udid) as cm:
                while alive():
                    if await _sweep_new(cm.afc, job) and time.monotonic() - start >= watch_s:
                        log.info("deferred cleanup: nothing left on the device")
                        _pending_drop(job.key)
                        return
                    _save(job)  # remember what was already deleted
                    await asyncio.sleep(poll())
        except asyncio.CancelledError:
            raise  # app closing: the saved entry is resumed at the next start
        except Exception as e:  # noqa: BLE001
            if not reported:
                log.info("deferred cleanup: device not reachable, will keep trying (%s)", short(e))
                reported = True
        await asyncio.sleep(poll())
    log.warning("deferred cleanup: entry too old, dropped; a sysdiagnose may remain on the device")
    _pending_drop(job.key)


def _schedule_deferred_cleanup(job: _Job, watch_s: float = 0, save: bool = True) -> None:
    if save:
        _save(job)
    task = asyncio.get_running_loop().create_task(_deferred_cleanup(job, watch_s))
    _background.add(task)
    task.add_done_callback(_background.discard)


def resume_pending() -> int:
    """At engine start: restart the saved cleanups (an earlier session was closed, or died, before
    finishing). Malformed or stale entries are dropped one by one; the valid ones still run."""
    now = time.time()
    raw = _pending_load()
    jobs: list[_Job] = []
    for e in raw:
        try:
            job = _Job.from_json(e)
        except ValueError as err:
            log.warning("pending cleanup entry dropped: %s", err)
            continue
        if now - job.created < PENDING_MAX_AGE_S:
            jobs.append(job)
    if len(jobs) != len(raw):
        _pending_write([j.to_json() for j in jobs])
    for job in jobs:
        _schedule_deferred_cleanup(job, save=False)
    if jobs:
        log.info("resumed %d pending device cleanup(s) from an earlier session", len(jobs))
    return len(jobs)


async def wait_background(timeout: float) -> None:
    """Give pending background cleanups a chance to finish."""
    if _background:
        await asyncio.wait(set(_background), timeout=timeout)


async def stop_background(timeout: float) -> None:
    """At shutdown: stop the background cleanups (they are saved and resume at the next start)."""
    tasks = set(_background)
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.wait(tasks, timeout=timeout)


# ------------------------------------------------------------------ the check, phase by phase


async def _wait_for_new_archive(cm, before: frozenset[str], deadline: float, progressed: Progressed) -> str:
    """Wait for the buttons: an archive whose final name was not there when the check started."""
    while True:
        entries = await _list(cm.afc)
        await progressed()
        for entry in sorted(entries):
            final = final_archive_name(entry)
            if final and final not in before and _path(final) not in _claimed:
                return final
        if time.monotonic() > deadline:
            raise EngineError("timeout", "the buttons were not pressed in time")
        await asyncio.sleep(TRIGGER_POLL_S)


async def _wait_until_written(cm, final: str, deadline: float, progressed: Progressed) -> None:
    """Wait until the iPhone finished writing `final` (renamed, nothing in progress, size stable)."""
    missing = 0
    last_size: Optional[int] = None
    while True:
        if time.monotonic() > deadline:
            raise EngineError("timeout", "the iPhone took too long to write the archive")
        entries = await _list(cm.afc)
        await progressed()
        writing = any(e != final and final_archive_name(e) == final for e in entries)
        if final in entries and not writing:
            size = int((await _step(cm.afc.stat(_path(final)), "stat")).get("st_size") or 0)
            if size > 0 and size == last_size:
                return
            last_size = size
            await asyncio.sleep(SETTLE_S)
            continue
        last_size = None
        missing = 0 if writing else missing + 1
        if missing >= 10:  # neither written nor finished for ~20 s: iOS gave up on it
            raise EngineError("fdr_no_archive", "the archive disappeared while it was being written")
        await asyncio.sleep(GENERATE_POLL_S)


def _rm_tmp(tmp: Path, after: Optional["asyncio.Future[Any]"] = None) -> None:
    """Remove the download folder now; if Windows still holds a file in it (the extraction thread after a
    cancel, an antivirus scan), keep retrying in the background. The startup sweep is the last resort."""
    if after is None or after.done():
        shutil.rmtree(tmp, ignore_errors=True)
        if not tmp.exists():
            return

    async def later() -> None:
        if after is not None:
            await asyncio.wait({after})
        for _ in range(60):
            shutil.rmtree(tmp, ignore_errors=True)
            if not tmp.exists():
                return
            await asyncio.sleep(1)
        log.warning("fdr: the local download could not be removed yet; it is swept at the next start")

    try:
        task = asyncio.get_running_loop().create_task(later())
    except RuntimeError:
        return
    _background.add(task)
    task.add_done_callback(_background.discard)


async def collect_fdr(udid: str, timeout_s: float, stage: Stage) -> dict:
    parent = paths.temp_parent()
    parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="dl-", dir=parent))
    remote_path: Optional[str] = None
    removed_remote = False
    job: Optional[_Job] = None
    deferred = False
    extract: Optional[asyncio.Future] = None
    try:
        # 1. what is already on the phone (also pairs, if needed)
        try:
            async with _connect(udid, autopair=True) as cm:
                before = finals_of(await _list(cm.afc))
        except EngineError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            raise map_exception(e) from e
        # Written ahead: from here on the phone can get an archive from this check, so the cleanup must
        # survive anything (app closed, crash, power cut). The window bounds what it may delete.
        started = time.time()
        job = _Job(uuid.uuid4().hex, udid, before,
                   (started, started + float(timeout_s) + GENERATE_TIMEOUT_S + WATCH_AFTER_CANCEL_S))
        _save(job)

        # 2. the buttons
        await stage("waiting_trigger")
        trigger_deadline = time.monotonic() + float(timeout_s)
        final = await _run_resilient(udid, stage, "waiting_trigger",
                                     lambda cm, p: _wait_for_new_archive(cm, before, trigger_deadline, p),
                                     deadline=trigger_deadline)
        remote_path = _path(final)
        _claimed.add(remote_path)
        job.own = remote_path
        _save(job)
        log.info("fdr: sysdiagnose detected on the device: %s", final)

        # 3. the iPhone writes the archive (5 to 10 minutes)
        await stage("generating")
        gen_deadline = time.monotonic() + GENERATE_TIMEOUT_S
        await _run_resilient(udid, stage, "generating",
                             lambda cm, p: _wait_until_written(cm, final, gen_deadline, p), deadline=gen_deadline)

        # 4. download, resuming at the same byte after a loss
        await stage("downloading")
        local = tmp / "sysdiagnose.tar.gz"
        state = {"got": 0, "size": None}
        with open(local, "wb") as f:
            async def download(cm, progressed: Progressed) -> None:
                afc = cm.afc
                if state["size"] is None:
                    state["size"] = int((await _step(afc.stat(remote_path), "stat")).get("st_size") or 0)
                size = state["size"]
                handle = await _step(afc.fopen(remote_path, "r"), "open")
                try:
                    if state["got"]:
                        await _step(afc.fseek(handle, state["got"]), "seek")
                    while state["got"] < size:
                        chunk = await _step(afc.fread(handle, min(CHUNK_BYTES, size - state["got"])), "read")
                        if not chunk:
                            raise EngineError("fdr_no_archive", f"empty read at {state['got']} of {size} bytes")
                        f.write(chunk)
                        state["got"] += len(chunk)
                        await progressed()
                finally:
                    await _quiet_close(afc.fclose(handle))

            await _run_resilient(udid, stage, "downloading", download)
        if local.stat().st_size == 0:
            raise EngineError("fdr_no_archive", "download produced no file")

        # 5. delete on the device: this archive and any extra one the check created
        job.window = (job.window[0], time.time())  # nothing after now was made by this check
        clean = False
        try:
            async with _connect(udid) as cm:
                removed_remote = await _remote_rm(cm.afc, remote_path)
                _claimed.discard(remote_path)
                if removed_remote:
                    job.done.add(remote_path)
                    log.info("fdr: sysdiagnose downloaded and deleted on the device")
                else:
                    log.warning("the sysdiagnose could not be confirmed deleted on the device")
                clean = await _sweep_new(cm.afc, job)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001  the data is here; deleting continues in the background
            log.warning("fdr: deleting on the device failed (%s); retrying in the background", short(e))
        _claimed.discard(remote_path)
        if clean and removed_remote:
            _pending_drop(job.key)
        else:
            _schedule_deferred_cleanup(job)
        deferred = True

        # 6. read the two files (the thread keeps the file open: never remove it under the thread)
        await stage("extracting")
        extract = asyncio.ensure_future(asyncio.to_thread(extract_report, local))
        try:
            res = await asyncio.shield(extract)
        except tarfile.TarError as e:
            raise EngineError("fdr_no_archive", short(e)) from e
        res["device_archive_removed"] = removed_remote
        res["other_archives"] = [{"name": n, "date": archive_date(n)} for n in sorted(before)]
        await stage("cleaning")
        _rm_tmp(tmp)
        log.info("fdr: local temp folder removed: %s", not tmp.exists())
        await stage("done")
        return res
    except BaseException as e:
        if remote_path is not None:
            _claimed.discard(remote_path)
        if job is not None and not deferred:
            # Whatever the check created (or the buttons create right after a cancel) is deleted later.
            if remote_path is None:
                job.window = (job.window[0], time.time() + WATCH_AFTER_CANCEL_S)
            _schedule_deferred_cleanup(job, watch_s=WATCH_AFTER_CANCEL_S if remote_path is None else 0)
        if isinstance(e, (asyncio.CancelledError, EngineError)) or not isinstance(e, Exception):
            raise
        err = map_exception(e)
        if err.code == "internal" and remote_path is None:
            err = EngineError("fdr_no_archive", short(e))
        raise err from e
    finally:
        if remote_path is not None:
            _claimed.discard(remote_path)
        _rm_tmp(tmp, after=extract)


async def delete_archives(udid: str, names: Iterable[Any]) -> dict:
    """Delete sysdiagnose archives the user chose (the ones that were already on the phone).

    Only plain archive names inside DiagnosticLogs/sysdiagnose are accepted; anything else is refused."""
    wanted: list[str] = []
    refused: list[str] = []
    for n in names:
        if isinstance(n, str) and final_archive_name(n) == n and _path(n) not in _claimed:
            if n not in wanted:
                wanted.append(n)
        else:
            refused.append(str(n)[:120])
    deleted: list[str] = []
    failed: list[str] = list(refused)
    if not wanted:
        return {"deleted": deleted, "failed": failed}
    try:
        async with _connect(udid) as cm:
            present = set(await _list(cm.afc))
            for n in wanted:
                if n not in present:
                    deleted.append(n)  # already gone (iOS prunes old diagnostics on its own)
                elif await _remote_rm(cm.afc, _path(n)):
                    deleted.append(n)
                else:
                    failed.append(n)
    except EngineError:
        raise
    except Exception as e:  # noqa: BLE001
        raise map_exception(e) from e
    log.info("fdr: %d older sysdiagnose(s) deleted at the user's request, %d failed", len(deleted), len(failed))
    return {"deleted": deleted, "failed": failed}
