"""DiagnosticsService wrapper: a refused connection right after plugging in is retried once."""
from __future__ import annotations

import asyncio

import pytest
from pymobiledevice3 import exceptions as pe

from lacre_engine import collect as C


class FakeSvc:
    closed = 0

    def __init__(self, lockdown):
        pass

    async def close(self):
        FakeSvc.closed += 1


@pytest.fixture
def fake_svc(monkeypatch):
    monkeypatch.setattr(C, "DiagnosticsService", FakeSvc)
    monkeypatch.setattr(C.asyncio, "sleep", _no_sleep)
    FakeSvc.closed = 0


async def _no_sleep(_s):
    return None


def test_refused_once_then_ok(fake_svc):
    calls = []

    async def fn(svc):
        calls.append(svc)
        if len(calls) == 1:
            raise pe.ConnectionFailedError("usbmuxd rejected the Connect request")
        return {"ok": True}

    d = C._Diag(object())
    assert asyncio.run(d.call(fn, 5)) == {"ok": True}
    assert len(calls) == 2 and calls[0] is not calls[1]  # a fresh service on the retry
    assert FakeSvc.closed == 1


def test_refused_twice_gives_up(fake_svc):
    async def fn(svc):
        raise pe.ConnectionFailedError("refused")

    d = C._Diag(object())
    with pytest.raises(pe.ConnectionFailedError):
        asyncio.run(d.call(fn, 5))
    assert d.svc is None


def test_device_ids_are_masked_in_messages():
    from lacre_engine.errors import redact, short
    msg = "usbmux has no device matching udid 00008030-0005ABCDEF012345 over USB"
    assert "00008030" not in short(RuntimeError(msg)) and "<udid>" in short(RuntimeError(msg))
    assert redact("old " + "a" * 40 + " id") == "old <udid> id"
    assert redact("sysdiagnose_2026.11.09_07-40-22-0300_iPhone-OS_iPhone_23G90.tar.gz").startswith("sysdiagnose_2026")
