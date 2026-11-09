"""Factory record (FDR) through a sysdiagnose triggered on the device by the buttons.

Library equivalent of `pymobiledevice3 crash sysdiagnose OUT --erase --timeout T`
(`CrashReportsManager.get_new_sysdiagnose`), split into its steps so each one emits a stage event and
can be cancelled:

  waiting_trigger -> (user presses the buttons) -> generating -> downloading -> extracting -> cleaning -> done

Only `logs/FDR/FDRDiagnosticReport.plist` and `logs/BatteryHealth/BatteryHealth.log` are read from the
archive. The archive is deleted on the device right after download (the only write the engine ever does
on the device, and only to the file it asked for) and the local temp dir is removed before answering.
If the request is cancelled after the device started writing the archive, a background task waits for
the device to finish it and then deletes it, so no sysdiagnose is left behind on the iPhone.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import plistlib
import re
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .collect import to_jsonable
from .errors import EngineError, map_exception, short

log = logging.getLogger("lacre.fdr")

Stage = Callable[[str], Awaitable[None]]

FDR_PLIST = "logs/FDR/FDRDiagnosticReport.plist"
BATTERY_LOG = "logs/BatteryHealth/BatteryHealth.log"
RX_MAX_CAPACITY = re.compile(r'"Maximum Capacity Percent"\s*=\s*(\d+)')
# Upper bound for one member we read (the FDR plist is a few KB; the battery log well under 1 MB).
MAX_MEMBER_BYTES = 32 * 1024 * 1024
# How long the background cleanup waits for a cancelled sysdiagnose to finish before deleting it.
DEFERRED_CLEANUP_TIMEOUT_S = 900

# Background cleanup tasks (kept referenced so they are not garbage-collected).
_background: set[asyncio.Task] = set()


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


async def _maybe_await(v: Any) -> Any:
    return await v if inspect.isawaitable(v) else v


async def _remote_rm(afc, remote_path: str) -> bool:
    """Delete the archive on the device and confirm it is gone."""
    await afc.rm_single(remote_path, force=True)
    try:
        return not await afc.exists(remote_path)
    except Exception:  # noqa: BLE001
        return False


async def _deferred_cleanup(udid: str, remote_path: str) -> None:
    """After a cancel mid-generation: wait for the device to finish the archive, then delete it."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.crash_reports import CrashReportsManager

    deadline = time.monotonic() + DEFERRED_CLEANUP_TIMEOUT_S
    try:
        lockdown = await create_using_usbmux(serial=udid, autopair=False, connection_type="USB")
        try:
            async with CrashReportsManager(lockdown) as cm:
                while time.monotonic() < deadline:
                    try:
                        if await cm.afc.exists(remote_path) and await _remote_rm(cm.afc, remote_path):
                            log.info("deferred cleanup: cancelled sysdiagnose removed from the device")
                            return
                        # still being written (IN_PROGRESS_ file) or not yet renamed: try again later
                    except Exception as e:  # noqa: BLE001
                        log.info("deferred cleanup retry: %s", short(e))
                    await asyncio.sleep(10)
                log.warning("deferred cleanup: gave up waiting for the cancelled sysdiagnose")
        finally:
            await _maybe_await(lockdown.close())
    except Exception as e:  # noqa: BLE001
        log.warning("deferred cleanup failed: %s", short(e))


def _schedule_deferred_cleanup(udid: str, remote_path: str) -> None:
    task = asyncio.get_running_loop().create_task(_deferred_cleanup(udid, remote_path))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def wait_background(timeout: float) -> None:
    """Give pending background cleanups a chance to finish (used at shutdown)."""
    if _background:
        await asyncio.wait(set(_background), timeout=timeout)


async def collect_fdr(udid: str, timeout_s: float, stage: Stage) -> dict:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.crash_reports import CrashReportsManager

    tmp = Path(tempfile.mkdtemp(prefix="lacre-fdr-"))
    remote_path: Optional[str] = None
    removed_remote = False
    try:
        try:
            lockdown = await create_using_usbmux(serial=udid, autopair=True, connection_type="USB")
        except Exception as e:  # noqa: BLE001
            raise map_exception(e) from e
        try:
            async with CrashReportsManager(lockdown) as cm:
                end_time = time.monotonic() + float(timeout_s)
                await stage("waiting_trigger")
                remote_path = await cm._get_new_sysdiagnose_filename(end_time)
                log.info("fdr: sysdiagnose detected on the device: %s", remote_path.rsplit("/", 1)[-1])
                await stage("generating")
                await cm._wait_for_sysdiagnose_to_finish(end_time)
                await stage("downloading")
                local = tmp / "sysdiagnose.tar.gz"
                await cm.afc.pull(remote_path, str(local), progress_bar=False)
                removed_remote = await _remote_rm(cm.afc, remote_path)
                if removed_remote:
                    log.info("fdr: sysdiagnose downloaded and deleted on the device")
                else:
                    log.warning("the sysdiagnose could not be confirmed deleted on the device")
                if not local.exists() or local.stat().st_size == 0:
                    raise EngineError("fdr_no_archive", "download produced no file")
                await stage("extracting")
                try:
                    res = await asyncio.to_thread(extract_report, local)
                except tarfile.TarError as e:
                    raise EngineError("fdr_no_archive", short(e)) from e
                res["device_archive_removed"] = removed_remote
        finally:
            await _maybe_await(lockdown.close())
        await stage("cleaning")
        shutil.rmtree(tmp, ignore_errors=True)
        log.info("fdr: local temp folder removed: %s", not tmp.exists())
        await stage("done")
        return res
    except (asyncio.CancelledError, EngineError):
        if remote_path and not removed_remote:
            _schedule_deferred_cleanup(udid, remote_path)
        raise
    except Exception as e:  # noqa: BLE001
        if remote_path and not removed_remote:
            _schedule_deferred_cleanup(udid, remote_path)
        err = map_exception(e)
        if err.code == "internal" and remote_path is None:
            err = EngineError("fdr_no_archive", short(e))
        raise err from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
