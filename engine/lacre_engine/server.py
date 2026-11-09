"""JSON Lines server (docs/PROTOCOL.md): one request per stdin line, responses/events on stdout.

One asyncio loop; every request runs in its own task, so requests can overlap (e.g. `cancel` while an
`fdr` waits). Device work for one UDID is serialized by a per-UDID lock. stdout carries only protocol
lines; everything else goes to stderr.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from typing import Any, Callable, Optional

from . import __version__
from .errors import EngineError, map_exception, short

log = logging.getLogger("lacre.server")

PROTOCOL_VERSION = 1
SHUTDOWN_GRACE_S = 10.0
FINISH_GRACE_S = 3.0


def pmd3_version() -> str:
    try:
        from importlib.metadata import version
        return version("pymobiledevice3")
    except Exception:  # noqa: BLE001  frozen build without metadata
        try:
            from pymobiledevice3 import _version
            return str(getattr(_version, "__version__", getattr(_version, "version", "unknown")))
        except Exception:  # noqa: BLE001
            return "unknown"


class Server:
    def __init__(self, write: Callable[[bytes], None]) -> None:
        self._write = write
        self._tasks: dict[str, asyncio.Task] = {}
        self._udid_locks: dict[str, asyncio.Lock] = {}
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------ output

    def send(self, msg: dict) -> None:
        msg = {"v": PROTOCOL_VERSION, **msg}
        line = json.dumps(msg, ensure_ascii=False, separators=(",", ":"), default=str)
        self._write(line.encode("utf-8") + b"\n")

    def ok(self, rid: Any, data: Any) -> None:
        self.send({"id": rid, "ok": True, "data": data})

    def fail(self, rid: Any, code: str, detail: str = "") -> None:
        self.send({"id": rid, "ok": False, "error": {"code": code, "detail": detail}})

    # ------------------------------------------------------------ input

    def handle_line(self, raw: bytes | str) -> None:
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        text = text.strip().lstrip("﻿")
        if not text:
            return
        try:
            req = json.loads(text)
            if not isinstance(req, dict):
                raise ValueError("request is not an object")
        except ValueError as e:
            self.fail(None, "internal", f"bad request line: {short(e)}")
            return
        rid = req.get("id")
        cmd = req.get("cmd")
        args = req.get("args") or {}
        if not isinstance(args, dict):
            self.fail(rid, "internal", "args must be an object")
            return
        handler = getattr(self, f"cmd_{cmd}", None) if isinstance(cmd, str) else None
        if handler is None:
            self.fail(rid, "internal", f"unknown cmd: {cmd!r}")
            return
        key = str(rid)
        if key in self._tasks:
            self.fail(rid, "internal", "duplicate request id in flight")
            return
        task = asyncio.get_running_loop().create_task(self._run(rid, cmd, handler, args))
        self._tasks[key] = task
        task.add_done_callback(lambda _t, k=key: self._tasks.pop(k, None))

    async def _run(self, rid: Any, cmd: str, handler, args: dict) -> None:
        try:
            data = await handler(rid, args)
            self.ok(rid, data)
        except asyncio.CancelledError:
            self.fail(rid, "cancelled", "")
        except EngineError as e:
            self.fail(rid, e.code, e.detail)
        except Exception as e:  # noqa: BLE001
            err = map_exception(e)
            log.exception("%s failed", cmd)
            self.fail(rid, err.code, err.detail)

    def _lock(self, udid: str) -> asyncio.Lock:
        return self._udid_locks.setdefault(udid, asyncio.Lock())

    @staticmethod
    def _udid(args: dict) -> str:
        udid = args.get("udid")
        if not isinstance(udid, str) or not udid:
            raise EngineError("no_device", "missing udid")
        return udid

    # ------------------------------------------------------------ commands

    async def cmd_hello(self, rid, args):
        return {"engine_version": __version__, "pymobiledevice3": pmd3_version(), "platform": sys.platform,
                "protocol": PROTOCOL_VERSION}

    async def cmd_prereq(self, rid, args):
        from .collect import prereq
        return await prereq()

    async def cmd_devices(self, rid, args):
        from .collect import list_usb_devices
        return await list_usb_devices()

    async def cmd_read(self, rid, args):
        from .collect import read_device
        udid = self._udid(args)

        async def progress(step: str, done: int, total: int) -> None:
            self.send({"id": rid, "event": "progress", "step": step, "done": done, "total": total})

        async with self._lock(udid):
            return await read_device(udid, progress)

    async def cmd_fdr(self, rid, args):
        from .fdr import collect_fdr
        udid = self._udid(args)
        timeout_s = args.get("timeout_s", 900)
        if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or timeout_s <= 0:
            timeout_s = 900

        async def stage(name: str) -> None:
            self.send({"id": rid, "event": "fdr", "stage": name})

        async with self._lock(udid):
            return await collect_fdr(udid, float(timeout_s), stage)

    async def cmd_cancel(self, rid, args):
        target = args.get("target_id")
        task = self._tasks.get(str(target))
        found = task is not None and task is not asyncio.current_task() and not task.done()
        if found:
            task.cancel()
        return {"found": found}

    async def cmd_analyze(self, rid, args):
        from .analyze import analyze
        raw = args.get("raw")
        today = args.get("today")
        if not isinstance(raw, dict):
            raise EngineError("internal", "analyze: raw must be an object")
        if not isinstance(today, str):
            raise EngineError("internal", "analyze: today (YYYY-MM-DD) is required")
        fdr = args.get("fdr")
        try:
            return analyze(raw, fdr if isinstance(fdr, dict) else None, today)
        except ValueError as e:
            raise EngineError("internal", f"analyze: {short(e)}") from e

    async def cmd_shutdown(self, rid, args):
        self._stopping.set()
        return {}

    # ------------------------------------------------------------ lifecycle

    async def drain(self) -> None:
        """Cancel in-flight requests and let background cleanups run a little."""
        me = asyncio.current_task()
        pending = [t for t in self._tasks.values() if t is not me and not t.done()]
        if pending:  # quick requests get a moment to answer; long ones (fdr) are cancelled
            _, pending = await asyncio.wait(pending, timeout=FINISH_GRACE_S)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.wait(pending, timeout=SHUTDOWN_GRACE_S)
        fdr_mod = sys.modules.get("lacre_engine.fdr")  # never import it just to shut down
        if fdr_mod is not None and hasattr(fdr_mod, "wait_background"):
            try:
                await fdr_mod.wait_background(SHUTDOWN_GRACE_S)
            except Exception:  # noqa: BLE001
                pass


def _warm_imports() -> None:
    try:
        import importlib
        for mod in ("lacre_engine.collect", "lacre_engine.fdr", "pymobiledevice3.services.crash_reports"):
            importlib.import_module(mod)
    except Exception as e:  # noqa: BLE001
        log.warning("warm import failed: %s", short(e))


async def serve(read_line: Callable[[], bytes], write: Callable[[bytes], None], warm: bool = False) -> None:
    """Run until `shutdown` or EOF. `read_line` blocks (it runs on a daemon thread); b"" means EOF."""
    loop = asyncio.get_running_loop()
    server = Server(write)
    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

    def reader() -> None:
        try:
            while True:
                line = read_line()
                if not line:
                    break
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as e:  # noqa: BLE001
            log.warning("stdin reader stopped: %s", short(e))
        finally:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except RuntimeError:
                pass  # loop already closed

    threading.Thread(target=reader, name="stdin-reader", daemon=True).start()
    log.info("engine %s ready (%s)", __version__, sys.platform)
    if warm:
        # pymobiledevice3 takes seconds to import (requests, prompt_toolkit...): load it in the background
        # so `hello` answers at once and the first `devices` does not pay the full import.
        threading.Thread(target=_warm_imports, name="warm-imports", daemon=True).start()

    while not server._stopping.is_set():
        get = asyncio.ensure_future(queue.get())
        stop = asyncio.ensure_future(server._stopping.wait())
        done, _ = await asyncio.wait({get, stop}, return_when=asyncio.FIRST_COMPLETED)
        if get not in done:
            get.cancel()
            break
        stop.cancel()
        line = get.result()
        if line is None:  # EOF: the shell went away
            break
        server.handle_line(line)
    # let the shutdown response (and any just-finished responses) go out first
    await asyncio.sleep(0)
    await server.drain()


def main() -> int:
    for s in (sys.stdin, sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    out = sys.stdout.buffer
    inp = sys.stdin.buffer
    # Anything printed by libraries (progress bars, prints) must not corrupt the protocol stream.
    sys.stdout = sys.stderr
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("pymobiledevice3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def write(b: bytes) -> None:
        out.write(b)
        out.flush()

    code = 0
    try:
        asyncio.run(serve(inp.readline, write, warm=True))
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001
        logging.getLogger("lacre.server").exception("server crashed")
        code = 1
    # Hard exit: the stdin reader is a daemon thread blocked in readline(); a normal interpreter
    # shutdown aborts with "could not acquire lock for <stdin>" (0xC0000005) when it is still running.
    for s in (out, sys.stderr):
        try:
            s.flush()
        except Exception:  # noqa: BLE001
            pass
    os._exit(code)
