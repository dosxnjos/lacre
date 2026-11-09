"""Read-only collection from a USB iPhone through the pymobiledevice3 library (in-process).

Only these device calls are made, all read-only:
- usbmux device list; lockdown values (`all_values`);
- diagnostics_relay IORegistry queries (battery = IOPMPowerSource, IOService tree, camera/display/platform
  classes);
- MCInstall `GetCloudConfiguration` and `GetProfileList`.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import logging
import plistlib
import re
from typing import Any, Awaitable, Callable, Optional

from pymobiledevice3 import exceptions as pe
from pymobiledevice3 import usbmux
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.diagnostics import DiagnosticsService
from pymobiledevice3.services.mobile_config import MobileConfigService

from .errors import CONNECTION_LOST, EngineError, map_exception, short

log = logging.getLogger("lacre.collect")

Progress = Callable[[str, int, int], Awaitable[None]]
STEPS = ("identity", "battery", "hardware", "parts", "platform", "mdm")

CAMERA_CLASS_RX = r"^AppleH\d+CamIn$"
DISPLAY_CLASS_RX = r"^AppleCLCD\d*$"
CAMERA_FALLBACK = [f"AppleH{n}CamIn" for n in range(9, 21)]
DISPLAY_FALLBACK = ["AppleCLCD", "AppleCLCD2"]

QUERY_TIMEOUT_S = 180
TREE_TIMEOUT_S = 300
PAIR_TIMEOUT_S = 30


async def maybe_await(v: Any) -> Any:
    return await v if inspect.isawaitable(v) else v


def to_jsonable(v: Any) -> Any:
    """Plist values -> JSON values. bytes -> {"$hex"}, dates -> ISO text, UID -> int."""
    if isinstance(v, dict):
        return {str(k): to_jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [to_jsonable(x) for x in v]
    if isinstance(v, (bytes, bytearray)):
        return {"$hex": bytes(v).hex()}
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, plistlib.UID):
        return v.data
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def find_classes(tree: Any, pattern: str) -> list[str]:
    found: list[str] = []
    rx = re.compile(pattern)
    stack = [tree]
    while stack:  # iterative walk: the IOService tree is deep
        node = stack.pop()
        if isinstance(node, dict):
            c = node.get("className")
            if isinstance(c, str) and rx.search(c) and c not in found:
                found.append(c)
            children = node.get("children") or []
            if isinstance(children, list):
                stack.extend(reversed(children))
    return found


# ---------------------------------------------------------------- prerequisites and device list

async def prereq() -> dict:
    import sys
    try:
        mux = await usbmux.create_mux()
        await mux.close()
        return {"usbmux_ok": True, "hint": None}
    except Exception as e:  # noqa: BLE001
        log.info("usbmux not reachable: %s", short(e))
        return {"usbmux_ok": False, "hint": "apple_devices_missing" if sys.platform == "win32" else "usbmuxd_missing"}


async def list_usb_devices() -> list[dict]:
    try:
        devices = await usbmux.list_devices()
    except Exception as e:  # noqa: BLE001
        raise EngineError("usbmux_unavailable", short(e)) from e
    out: list[dict] = []
    for d in devices:
        if not d.is_usb:
            continue
        entry = {"udid": d.serial, "name": None, "product_type": None, "ios": None, "connection": "USB",
                 "error": None}
        try:
            ld = await create_using_usbmux(serial=d.serial, autopair=False, connection_type="USB")
            try:
                si = ld.short_info
                entry.update(name=si.get("DeviceName"), product_type=si.get("ProductType"),
                             ios=si.get("ProductVersion"))
            finally:
                await maybe_await(ld.close())
        except Exception as e:  # noqa: BLE001
            entry["error"] = map_exception(e).code
            log.info("device %s… lockdown failed: %s", str(d.serial)[:4], short(e))
        out.append(entry)
    return out


# ---------------------------------------------------------------- read

class _Diag:
    """DiagnosticsService wrapper that reconnects after a timeout (the connection is unusable then)."""

    def __init__(self, lockdown) -> None:
        self.lockdown = lockdown
        self.svc: Optional[DiagnosticsService] = None

    async def call(self, fn: Callable[[DiagnosticsService], Awaitable[Any]], timeout: float) -> Any:
        for attempt in (1, 2):
            if self.svc is None:
                self.svc = DiagnosticsService(self.lockdown)
            try:
                return await asyncio.wait_for(maybe_await(fn(self.svc)), timeout)
            except pe.ConnectionFailedError:
                # usbmux "connection refused" (seen right after plugging in): the service was not ready yet
                await self.close()
                if attempt == 2:
                    raise
                await asyncio.sleep(1.5)
            except (asyncio.TimeoutError, *CONNECTION_LOST):
                await self.close()
                raise

    async def close(self) -> None:
        if self.svc is not None:
            try:
                await maybe_await(self.svc.close())
            except Exception:  # noqa: BLE001
                pass
            self.svc = None


async def _optional(label: str, coro_fn: Callable[[], Awaitable[Any]]) -> Any:
    """Optional collection: a failure becomes None (logged), never fails the read.
    A lost connection is not optional: it aborts the read as `device_gone`."""
    try:
        return await coro_fn()
    except asyncio.CancelledError:
        raise
    except CONNECTION_LOST as e:
        raise EngineError("device_gone", short(e)) from e
    except Exception as e:  # noqa: BLE001
        log.info("%s: not readable (%s)", label, short(e))
        return None


async def read_device(udid: str, progress: Progress) -> dict:
    total = len(STEPS)
    data: dict = {"collected_at": dt.datetime.now().isoformat(timespec="seconds")}

    await progress("identity", 0, total)
    try:
        lockdown = await create_using_usbmux(serial=udid, autopair=True, connection_type="USB",
                                             pair_timeout=PAIR_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001
        raise map_exception(e) from e
    diag = _Diag(lockdown)
    try:
        data["info"] = to_jsonable(lockdown.all_values)
        await progress("identity", 1, total)

        data["battery"] = to_jsonable(await _optional(
            "battery", lambda: diag.call(lambda s: s.get_battery(), QUERY_TIMEOUT_S)))
        await progress("battery", 2, total)

        tree = await _optional("ioservice tree", lambda: diag.call(
            lambda s: s.ioregistry(plane="IOService"), TREE_TIMEOUT_S))
        cam_classes = find_classes(tree, CAMERA_CLASS_RX)
        display_classes = find_classes(tree, DISPLAY_CLASS_RX)
        del tree
        data["classes"] = {"camera": cam_classes, "display": display_classes}
        await progress("hardware", 3, total)

        async def read_classes(label: str, classes: list[str]) -> dict:
            out = {}
            for c in classes:
                r = await _optional(f"{label} ({c})", lambda c=c: diag.call(
                    lambda s: s.ioregistry(ioclass=c), QUERY_TIMEOUT_S))
                if isinstance(r, dict) and r:
                    out[c] = to_jsonable(r)
            return out

        data["cameras"] = await read_classes("cameras", cam_classes)
        if not data["cameras"]:  # tree failed or a new class name: try the known names
            data["cameras"] = await read_classes("cameras", CAMERA_FALLBACK)
        data["display"] = await read_classes("display", display_classes)
        if not data["display"]:
            data["display"] = await read_classes("display", DISPLAY_FALLBACK)
        await progress("parts", 4, total)

        data["platform"] = to_jsonable(await _optional("platform", lambda: diag.call(
            lambda s: s.ioregistry(ioclass="IOPlatformExpertDevice"), QUERY_TIMEOUT_S)))
        await progress("platform", 5, total)
        await diag.close()

        async def mc_call(name: str):
            svc = MobileConfigService(lockdown)
            try:
                return await asyncio.wait_for(maybe_await(getattr(svc, name)()), QUERY_TIMEOUT_S)
            finally:
                try:
                    await maybe_await(svc.close())
                except Exception:  # noqa: BLE001
                    pass

        data["cloud"] = to_jsonable(await _optional("cloud configuration", lambda: mc_call("get_cloud_configuration")))
        data["profiles"] = to_jsonable(await _optional("profile list", lambda: mc_call("get_profile_list")))
        await progress("mdm", 6, total)
        return data
    finally:
        await diag.close()
        try:
            await maybe_await(lockdown.close())
        except Exception:  # noqa: BLE001
            pass
