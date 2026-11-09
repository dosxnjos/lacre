"""FDR extraction and cleanup, with a synthetic sysdiagnose archive and a fake device (no iPhone needed)."""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import plistlib
import shutil
import tarfile
import tempfile
from pathlib import Path

import pytest

from lacre_engine import fdr as F
from lacre_engine.analyze import analyze
from lacre_engine.errors import EngineError

ROOT = "sysdiagnose_2026.11.09_10-00-00-0300_iPhone-OS_iPhone_23G90"
FDR_DOC = {
    "ApTicket": "Trusted",
    "SealDate": "01/07/2022 01:17:04 GMT",
    "DataFailedToReport": [],
    "FailureData": [{"vcrt": {"SealedInstance": "SEALED-1", "LiveInstance": "LIVE-2"}}],
    "FailureProperties": [],
    "VerifiedData": [{"tcrt": {"LiveInstance": "T-1"}}, {"blob": {"LiveInstance": b"\x01\x02\xff"}}],
    "VerifiedProperties": [{"SrNm": {"LiveProperty": "SERIAL"}}],
    "When": dt.datetime(2026, 11, 9, 10, 0, 0),
}


def _add(t: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    t.addfile(info, io.BytesIO(data))


def make_archive(path: Path, with_fdr: bool = True, with_battery: bool = True) -> Path:
    with tarfile.open(path, "w:gz") as t:
        _add(t, f"{ROOT}/logs/other/huge.log", b"x" * 100_000)
        _add(t, f"{ROOT}/logs/FDR/._FDRDiagnosticReport.plist", b"appledouble junk")
        if with_fdr:
            _add(t, f"{ROOT}/logs/FDR/FDRDiagnosticReport.plist", plistlib.dumps(FDR_DOC))
        if with_battery:
            _add(t, f"{ROOT}/logs/BatteryHealth/BatteryHealth.log",
                 b'{\n  "Cycle Count" = 1042;\n  "Maximum Capacity Percent" = 79;\n}\n')
    return path


@pytest.fixture
def workdir():
    d = Path(tempfile.mkdtemp(prefix="lacre-test-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_extract_report(workdir):
    res = F.extract_report(make_archive(workdir / "a.tar.gz"))
    assert res["has_fdr"] is True
    assert res["battery_health_percent"] == 79
    assert res["seal_date"] == "01/07/2022 01:17:04 GMT"
    assert res["fdr"]["VerifiedData"][1]["blob"]["LiveInstance"] == "0102ff"  # bytes -> hex
    assert res["fdr"]["When"] == "2026-11-09T10:00:00"
    a = analyze({"info": {"ProductType": "iPhone12,1"}}, res, "2026-11-09")
    fac = next(s for s in a["sections"] if s and s["id"] == "factory")
    mm = [i for i in fac["items"] if i["code"] == "fdr_part_mismatch"]
    assert mm and mm[0]["params"]["part"] == "battery"


def test_extract_without_fdr(workdir):
    res = F.extract_report(make_archive(workdir / "b.tar.gz", with_fdr=False))
    assert res["has_fdr"] is False and res["fdr"] is None and res["battery_health_percent"] == 79


def test_extract_without_battery_log(workdir):
    res = F.extract_report(make_archive(workdir / "c.tar.gz", with_battery=False))
    assert res["has_fdr"] is True and res["battery_health_percent"] is None


# ---------------------------------------------------------------- fake device for collect_fdr

class FakeAfc:
    def __init__(self, archive: Path | None, remote: str):
        self.archive, self.remote = archive, remote
        self.present = {remote}
        self.removed: list[str] = []

    async def pull(self, src, dst, progress_bar=True):
        assert progress_bar is False
        if self.archive is not None:
            shutil.copyfile(self.archive, dst)

    async def rm_single(self, path, force=False):
        self.removed.append(path)
        self.present.discard(path)
        return True

    async def exists(self, path):
        return path in self.present


class FakeManager:
    afc: FakeAfc
    wait_forever = False
    instances: list["FakeManager"] = []

    def __init__(self, lockdown):
        FakeManager.instances.append(self)
        self.afc = FakeManager.afc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def _get_new_sysdiagnose_filename(self, end_time):
        await asyncio.sleep(0)
        return self.afc.remote

    async def _wait_for_sysdiagnose_to_finish(self, end_time):
        if FakeManager.wait_forever:
            await asyncio.sleep(3600)


class FakeLockdown:
    async def close(self):
        return None


@pytest.fixture
def fake_device(monkeypatch, workdir):
    import pymobiledevice3.lockdown as ld
    import pymobiledevice3.services.crash_reports as cr

    async def fake_create(**kw):
        return FakeLockdown()

    monkeypatch.setattr(ld, "create_using_usbmux", fake_create)
    monkeypatch.setattr(cr, "CrashReportsManager", FakeManager)
    made: list[Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*a, **kw):
        p = real_mkdtemp(*a, **kw)
        made.append(Path(p))
        return p

    monkeypatch.setattr(F.tempfile, "mkdtemp", tracking_mkdtemp)
    FakeManager.wait_forever = False
    FakeManager.instances = []
    return made


def test_collect_fdr_stages_and_cleanup(fake_device, workdir):
    remote = "DiagnosticLogs/sysdiagnose/sysdiagnose_x.tar.gz"
    FakeManager.afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), remote)
    stages: list[str] = []

    async def stage(s):
        stages.append(s)

    res = asyncio.run(F.collect_fdr("UDID", 60, stage))
    assert stages == ["waiting_trigger", "generating", "downloading", "extracting", "cleaning", "done"]
    assert res["has_fdr"] and res["battery_health_percent"] == 79 and res["device_archive_removed"] is True
    assert FakeManager.afc.removed == [remote]  # deleted on the device
    assert fake_device and all(not p.exists() for p in fake_device)  # deleted on the PC


def test_collect_fdr_no_archive(fake_device, workdir):
    remote = "DiagnosticLogs/sysdiagnose/sysdiagnose_y.tar.gz"
    FakeManager.afc = FakeAfc(None, remote)

    async def stage(s):
        pass

    with pytest.raises(EngineError) as ei:
        asyncio.run(F.collect_fdr("UDID", 60, stage))
    assert ei.value.code == "fdr_no_archive"
    assert all(not p.exists() for p in fake_device)


def test_collect_fdr_corrupt_archive(fake_device, workdir):
    bad = workdir / "bad.tar.gz"
    bad.write_bytes(b"not a tar at all" * 10)
    FakeManager.afc = FakeAfc(bad, "DiagnosticLogs/sysdiagnose/z.tar.gz")

    async def stage(s):
        pass

    with pytest.raises(EngineError) as ei:
        asyncio.run(F.collect_fdr("UDID", 60, stage))
    assert ei.value.code == "fdr_no_archive"
    assert FakeManager.afc.removed  # the device copy was still deleted
    assert all(not p.exists() for p in fake_device)


def test_collect_fdr_cancel_mid_generation_cleans_device_later(fake_device, workdir):
    remote = "DiagnosticLogs/sysdiagnose/sysdiagnose_c.tar.gz"
    FakeManager.afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), remote)
    FakeManager.wait_forever = True
    stages: list[str] = []

    async def stage(s):
        stages.append(s)

    async def scenario():
        task = asyncio.create_task(F.collect_fdr("UDID", 600, stage))
        while "generating" not in stages:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await F.wait_background(5)

    asyncio.run(scenario())
    assert stages == ["waiting_trigger", "generating"]
    assert FakeManager.afc.removed == [remote]  # background cleanup removed the archive on the device
    assert all(not p.exists() for p in fake_device)


def test_collect_fdr_cancel_while_waiting_trigger_leaves_nothing(fake_device, workdir):
    FakeManager.afc = FakeAfc(None, "unused")

    async def never(self, end_time):
        await asyncio.sleep(3600)

    FakeManager._get_new_sysdiagnose_filename, orig = never, FakeManager._get_new_sysdiagnose_filename
    try:
        async def stage(s):
            pass

        async def scenario():
            task = asyncio.create_task(F.collect_fdr("UDID", 600, stage))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not F._background

        asyncio.run(scenario())
    finally:
        FakeManager._get_new_sysdiagnose_filename = orig
    assert FakeManager.afc.removed == []
    assert all(not p.exists() for p in fake_device)
