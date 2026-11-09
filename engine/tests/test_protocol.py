"""JSON Lines protocol: the real server in a subprocess, plus in-process checks of concurrency/cancel."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from lacre_engine import server as S

ENGINE = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"


def _req(rid, cmd, args=None) -> str:
    return json.dumps({"v": 1, "id": rid, "cmd": cmd, "args": args or {}})


def test_subprocess_hello_analyze_shutdown():
    raw = json.loads((FIX / "iphone11_raw.json").read_text(encoding="utf-8"))
    fdr = json.loads((FIX / "iphone11_fdr.json").read_text(encoding="utf-8"))
    lines = [
        _req("h", "hello"),
        _req("a", "analyze", {"raw": raw, "fdr": fdr, "today": "2026-11-09"}),
        _req("bad", "analyze", {"raw": raw}),
        "this is not json",
        _req("x", "does_not_exist"),
        _req("s", "shutdown"),
    ]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-m", "lacre_engine"], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=ENGINE, env=env)
    assert p.returncode == 0, p.stderr
    out = [json.loads(line) for line in p.stdout.splitlines()]  # every stdout line is protocol JSON
    assert all(m["v"] == 1 for m in out)
    by_id = {m["id"]: m for m in out}
    assert by_id["h"]["ok"] and by_id["h"]["data"]["pymobiledevice3"] == "11.50.2"
    assert by_id["h"]["data"]["engine_version"]
    a = by_id["a"]["data"]
    assert by_id["a"]["ok"] and a["verdict"]["code"] == "alert_items"
    assert a["device"]["model_name"] == "iPhone 11"
    assert by_id["bad"]["ok"] is False and by_id["bad"]["error"]["code"] == "internal"
    assert by_id[None]["ok"] is False
    assert by_id["x"]["error"]["code"] == "internal"
    assert by_id["s"] == {"v": 1, "id": "s", "ok": True, "data": {}}


def test_in_process_cancel_and_concurrency(monkeypatch):
    """A long fdr request is cancelled by `cancel` while other requests keep being answered."""
    import lacre_engine.fdr as F

    async def fake_collect(udid, timeout_s, stage):
        await stage("waiting_trigger")
        await asyncio.sleep(3600)

    monkeypatch.setattr(F, "collect_fdr", fake_collect)
    sent: list[dict] = []

    async def scenario():
        srv = S.Server(lambda b: sent.append(json.loads(b.decode("utf-8"))))
        srv.handle_line(_req("f", "fdr", {"udid": "U", "timeout_s": 900}))
        await asyncio.sleep(0.05)
        srv.handle_line(_req("h", "hello"))
        await asyncio.sleep(0.05)
        srv.handle_line(_req("c", "cancel", {"target_id": "f"}))
        for _ in range(100):
            if any(m.get("id") == "f" and "ok" in m for m in sent):
                break
            await asyncio.sleep(0.01)
        srv.handle_line(_req("c2", "cancel", {"target_id": "nope"}))
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    ids = [(m["id"], m.get("event") or m.get("ok")) for m in sent]
    assert ("f", "fdr") in ids
    assert {"v": 1, "id": "f", "event": "fdr", "stage": "waiting_trigger"} in sent
    hello_i = next(i for i, m in enumerate(sent) if m["id"] == "h")
    fdr_end = next(i for i, m in enumerate(sent) if m["id"] == "f" and "ok" in m)
    assert hello_i < fdr_end  # hello answered while fdr was still waiting
    assert sent[fdr_end]["error"]["code"] == "cancelled"
    assert next(m for m in sent if m["id"] == "c")["data"] == {"found": True}
    assert next(m for m in sent if m["id"] == "c2")["data"] == {"found": False}


def test_serve_eof_exits():
    """EOF on stdin ends the server (the shell went away)."""
    lines = iter([_req("h", "hello").encode() + b"\n", b""])
    sent: list[bytes] = []
    asyncio.run(asyncio.wait_for(S.serve(lambda: next(lines), sent.append), 30))
    assert json.loads(sent[0])["id"] == "h"
