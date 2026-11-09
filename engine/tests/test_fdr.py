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

import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

DIR = F.SYSDIAGNOSE_DIR
OLD = "sysdiagnose_2026.11.01_10-00-00-0300_iPhone-OS_iPhone_23G90.tar.gz"


def stamped(offset_s: float = 0, tag: str = "iPhone-OS_iPhone_23G90") -> str:
    """An archive name dated now (+offset), the way the iPhone names it."""
    t = dt.datetime.now().astimezone() + dt.timedelta(seconds=offset_s)
    return f"sysdiagnose_{t.strftime('%Y.%m.%d_%H-%M-%S%z')}_{tag}.tar.gz"


NEW = stamped()
NEW_PATH = f"{DIR}/{NEW}"


def inprog(final: str) -> str:
    return "IN_PROGRESS_" + final[: -len(".tar.gz")] + ".tmp"


class FakeAfc:
    """DiagnosticLogs/sysdiagnose of a fake iPhone, driven by how many times it was listed.

    At listing number `press_at` the buttons are pressed: `IN_PROGRESS_<final>.tmp` appears; after
    `write_lists` more listings it is renamed to `final`."""

    def __init__(self, archive: Path | None, final: str = NEW, existing: dict[str, bytes] | None = None,
                 press_at: int | None = 2, write_lists: int = 2):
        self.final = final
        self.content = archive.read_bytes() if archive is not None else b""
        self.files: dict[str, bytes] = {f"{DIR}/{n}": b for n, b in (existing or {}).items()}
        self.press_at, self.write_lists = press_at, write_lists
        self.lists = 0
        self.writing_left: int | None = None
        self.on_list = None  # callable(n) for tests that change the folder at a given listing
        self.removed: list[str] = []
        self.handles: dict[int, list] = {}
        self.reads = 0
        self.stall_reads: set[int] | None = None  # these fread calls never answer
        self.stall_all_reads = False
        self.list_error: Exception | None = None

    def press(self):
        self.files[f"{DIR}/{inprog(self.final)}"] = b"..."
        self.writing_left = self.write_lists

    async def listdir(self, d):
        assert d == DIR
        if self.list_error is not None:
            raise self.list_error
        self.lists += 1
        if self.writing_left is not None:
            self.writing_left -= 1
            if self.writing_left <= 0:
                self.files.pop(f"{DIR}/{inprog(self.final)}", None)
                self.files[f"{DIR}/{self.final}"] = self.content
                self.writing_left = None
        if self.press_at is not None and self.lists == self.press_at:
            self.press()
        if self.on_list:
            self.on_list(self.lists)
        return [p.rsplit("/", 1)[1] for p in self.files]

    async def stat(self, p):
        return {"st_size": len(self.files[p])}

    async def fopen(self, p, mode="r"):
        assert mode == "r" and p in self.files
        h = len(self.handles) + 1
        self.handles[h] = [p, 0]
        return h

    async def fseek(self, h, off, whence=0):
        self.handles[h][1] = off

    async def fread(self, h, sz):
        self.reads += 1
        if self.stall_all_reads or (self.stall_reads and self.reads in self.stall_reads):
            await asyncio.sleep(3600)
        p, pos = self.handles[h]
        data = self.files[p][pos:pos + sz]
        self.handles[h][1] += len(data)
        return data

    async def fclose(self, h):
        self.handles.pop(h, None)

    async def rm_single(self, path, force=False):
        assert path.startswith(DIR + "/")
        self.removed.append(path)
        self.files.pop(path, None)
        return True

    async def exists(self, path):
        return path in self.files


class FakeManager:
    afc: FakeAfc
    unplugged = False

    def __init__(self, lockdown):
        self.afc = FakeManager.afc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None


class FakeLockdown:
    async def close(self):
        return None


@pytest.fixture
def fake_device(monkeypatch, workdir):
    import pymobiledevice3.lockdown as ld
    import pymobiledevice3.services.crash_reports as cr
    from lacre_engine import paths

    async def fake_create(**kw):
        if FakeManager.unplugged:
            from pymobiledevice3.exceptions import DeviceNotFoundError
            raise DeviceNotFoundError("UDID")
        return FakeLockdown()

    monkeypatch.setattr(ld, "create_using_usbmux", fake_create)
    monkeypatch.setattr(cr, "CrashReportsManager", FakeManager)
    monkeypatch.setattr(paths, "temp_parent", lambda: workdir / "lacre-fdr")
    for name, value in (("STALL_TIMEOUT_S", 0.2), ("RECONNECT_POLL_S", 0.01), ("TRIGGER_POLL_S", 0.01),
                        ("GENERATE_POLL_S", 0.01), ("SETTLE_S", 0.01), ("DEFERRED_CLEANUP_POLL_S", 0.01),
                        ("DEFERRED_CLEANUP_TIMEOUT_S", 5), ("WATCH_AFTER_CANCEL_S", 0.2)):
        monkeypatch.setattr(F, name, value)
    FakeManager.unplugged = False
    F._claimed.clear()
    yield workdir / "lacre-fdr"
    F._claimed.clear()


def leftovers(tmp_parent: Path) -> list[str]:
    """Files left in the app temp folder, the pending-cleanups file aside."""
    if not tmp_parent.exists():
        return []
    return [p.name for p in tmp_parent.iterdir() if p.name != "pending-cleanups.json"]


def pending(tmp_parent: Path) -> list:
    f = tmp_parent / "pending-cleanups.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


async def _nostage(s):
    pass


def run(coro):
    async def main():
        try:
            return await coro
        finally:
            await F.wait_background(3)
    return asyncio.run(main())


def test_final_archive_name_and_date():
    assert F.final_archive_name(OLD) == OLD
    assert F.final_archive_name(inprog(NEW)) == NEW
    assert F.final_archive_name("IN_PROGRESS_sysdiagnose_a.tar.gz") == "sysdiagnose_a.tar.gz"
    for bad in ("notes.txt", "../sysdiagnose_a.tar.gz", "sysdiagnose_a.tar", "IN_PROGRESS_x.log", "sysdiagnose_.tar.gz",
                "a/sysdiagnose_b.tar.gz", "x\\sysdiagnose_b.tar.gz"):
        assert F.final_archive_name(bad) is None, bad
    assert F.archive_date(OLD) == "2026-11-01T10:00:00"
    assert F.archive_date("sysdiagnose_weird.tar.gz") is None


def test_collect_fdr_stages_and_cleanup(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"))
    stages: list[str] = []

    async def stage(s):
        stages.append(s)

    res = run(F.collect_fdr("UDID", 60, stage))
    assert stages == ["waiting_trigger", "generating", "downloading", "extracting", "cleaning", "done"]
    assert res["has_fdr"] and res["battery_health_percent"] == 79 and res["device_archive_removed"] is True
    assert res["other_archives"] == []
    assert afc.removed == [NEW_PATH] and afc.files == {}  # deleted on the device
    assert leftovers(fake_device) == [] and pending(fake_device) == []  # nothing on the PC
    assert not F._claimed


def test_old_archives_are_kept_and_reported_extra_ones_deleted(fake_device, workdir):
    extra = stamped(8, "extra")
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), existing={OLD: b"owner's old one"})
    afc.on_list = lambda n: afc.files.__setitem__(f"{DIR}/{extra}", b"second press") if n == 3 else None
    res = run(F.collect_fdr("UDID", 60, _nostage))
    assert set(afc.removed) == {NEW_PATH, f"{DIR}/{extra}"}
    assert list(afc.files) == [f"{DIR}/{OLD}"]  # the archive that was already there is untouched
    assert res["other_archives"] == [{"name": OLD, "date": "2026-11-01T10:00:00"}]


def test_archive_being_written_before_the_check_is_not_ours(fake_device, workdir):
    other = stamped(-3600, "owner")  # started an hour before the check: not ours
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"),
                                    existing={inprog(other): b"being written before the check"})

    def finish_owner(n):
        if n == 3:
            afc.files.pop(f"{DIR}/{inprog(other)}", None)
            afc.files[f"{DIR}/{other}"] = b"finished"

    afc.on_list = finish_owner
    res = run(F.collect_fdr("UDID", 60, _nostage))
    assert afc.removed == [NEW_PATH]  # the check took its own archive, not the one already being written
    assert f"{DIR}/{other}" in afc.files
    assert res["other_archives"] == [{"name": other, "date": F.archive_date(other)}]


def test_buttons_pressed_just_before_start_are_taken_as_the_check(fake_device, workdir):
    # Real case (09/11): the buttons were pressed a moment before "start"; iOS then ignores new presses
    # while it writes that archive, so the check must take it instead of waiting forever.
    synced = "sysdiagnose_2026.11.09_03-21-03-0800_iPhone-OS_iPhone_23G83.tar.gz.synced"
    FakeAfc_ = FakeAfc(make_archive(workdir / "dev.tar.gz"), existing={synced: b"sent to Apple"}, press_at=None)
    FakeAfc_.press()  # already being written when the check starts
    FakeManager.afc = afc = FakeAfc_
    res = run(F.collect_fdr("UDID", 60, _nostage))
    assert res["has_fdr"] and afc.removed == [NEW_PATH]
    assert res["other_archives"] == [{"name": synced, "date": "2026-11-09T03:21:03"}]
    assert f"{DIR}/{synced}" in afc.files  # an old one is only deleted when the user asks
    assert asyncio.run(F.delete_archives("UDID", [synced]))["deleted"] == [synced]


def test_missing_folder_counts_as_empty(fake_device, workdir):
    from pymobiledevice3.exceptions import AfcFileNotFoundError
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"))
    afc.list_error = AfcFileNotFoundError("no folder yet", 8)
    afc.on_list = None

    async def scenario():
        task = asyncio.create_task(F.collect_fdr("UDID", 60, _nostage))
        await asyncio.sleep(0.05)
        afc.list_error = None  # the folder appears when the iPhone starts the first sysdiagnose
        return await task

    res = run(scenario())
    assert res["has_fdr"] and afc.removed == [NEW_PATH]


def test_unplug_while_waiting_for_the_buttons_resumes(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), press_at=6)
    stages: list[str] = []

    def unplug_once(n):
        if n == 3:
            FakeManager.unplugged = True
            afc.list_error = ConnectionResetError("cable")

            async def replug():
                await asyncio.sleep(0.05)
                FakeManager.unplugged = False
                afc.list_error = None

            asyncio.get_running_loop().create_task(replug())

    afc.on_list = unplug_once

    async def stage(s):
        stages.append(s)

    res = run(F.collect_fdr("UDID", 60, stage))
    assert stages[:3] == ["waiting_trigger", "reconnecting", "waiting_trigger"]
    assert res["has_fdr"] and afc.files == {}


def test_unplug_while_generating_resumes_without_a_new_press(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), write_lists=6)
    stages: list[str] = []

    def unplug_during_generation(n):
        if n == 4:  # the iPhone keeps writing the archive while the PC does not see it
            FakeManager.unplugged = True
            afc.list_error = ConnectionResetError("cable")

            async def replug():
                await asyncio.sleep(0.05)
                afc.files.pop(f"{DIR}/{inprog(NEW)}", None)
                afc.files[NEW_PATH] = afc.content
                afc.writing_left = None
                FakeManager.unplugged = False
                afc.list_error = None

            asyncio.get_running_loop().create_task(replug())

    afc.on_list = unplug_during_generation

    async def stage(s):
        stages.append(s)

    res = run(F.collect_fdr("UDID", 60, stage))
    assert stages[:4] == ["waiting_trigger", "generating", "reconnecting", "generating"]
    assert res["has_fdr"] and afc.removed == [NEW_PATH]


def test_download_stall_waits_for_the_device_and_resumes(fake_device, workdir, monkeypatch):
    monkeypatch.setattr(F, "CHUNK_BYTES", 64)  # several reads even for the small synthetic archive
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"))
    afc.stall_reads = {2}  # the second read never answers
    stages: list[str] = []

    async def stage(s):
        stages.append(s)
        if s == "reconnecting":
            FakeManager.unplugged = True

            async def replug():
                await asyncio.sleep(0.05)
                FakeManager.unplugged = False

            asyncio.get_running_loop().create_task(replug())

    res = run(F.collect_fdr("UDID", 60, stage))
    assert stages == ["waiting_trigger", "generating", "downloading", "reconnecting", "downloading",
                      "extracting", "cleaning", "done"]
    assert res["has_fdr"] and res["battery_health_percent"] == 79  # the resumed file is intact
    assert afc.removed == [NEW_PATH]


def test_reconnects_but_never_delivers_gives_up(fake_device, workdir, monkeypatch):
    monkeypatch.setattr(F, "RECONNECT_TIMEOUT_S", 0.5)
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"))
    afc.stall_all_reads = True  # the link comes back but no byte ever arrives
    stages: list[str] = []

    async def stage(s):
        stages.append(s)

    async def scenario():
        with pytest.raises(EngineError) as ei:
            await asyncio.wait_for(F.collect_fdr("UDID", 60, stage), 10)
        return ei.value

    err = run(scenario())
    assert err.code == "device_gone"
    assert stages.count("reconnecting") == 1  # no flip-flopping between reconnecting and downloading
    assert afc.files == {}  # the background cleanup deleted the archive (listing still works)
    assert leftovers(fake_device) == []


def test_device_never_comes_back_then_cleanup_later(fake_device, workdir, monkeypatch):
    monkeypatch.setattr(F, "RECONNECT_TIMEOUT_S", 0.3)
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"))
    afc.stall_reads = {1}

    async def stage(s):
        if s == "reconnecting":
            FakeManager.unplugged = True

    async def scenario():
        with pytest.raises(EngineError) as ei:
            await F.collect_fdr("UDID", 60, stage)
        assert ei.value.code == "no_device"
        assert pending(fake_device)  # saved, in case the app is closed now
        FakeManager.unplugged = False  # plugged back later: the background cleanup deletes it

    run(scenario())
    assert afc.removed == [NEW_PATH] and afc.files == {}
    assert leftovers(fake_device) == [] and pending(fake_device) == []


def test_cleanup_survives_an_app_close(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), write_lists=1000)
    stages: list[str] = []

    async def stage(s):
        stages.append(s)

    async def first_session():
        task = asyncio.create_task(F.collect_fdr("UDID", 60, stage))
        while "generating" not in stages:
            await asyncio.sleep(0.01)
        task.cancel()  # the app is closed while the iPhone writes the archive
        with pytest.raises(asyncio.CancelledError):
            await task
        await F.stop_background(1)

    asyncio.run(first_session())
    assert pending(fake_device) and leftovers(fake_device) == []
    afc.files.pop(f"{DIR}/{inprog(NEW)}")
    afc.files[NEW_PATH] = afc.content  # finished while the app was closed

    async def next_start():
        assert F.resume_pending() == 1
        await F.wait_background(3)

    asyncio.run(next_start())
    assert afc.removed == [NEW_PATH] and afc.files == {}
    assert pending(fake_device) == []


def test_buttons_pressed_right_after_cancel_are_cleaned(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), existing={OLD: b"old"}, press_at=None)

    async def scenario():
        task = asyncio.create_task(F.collect_fdr("UDID", 600, _nostage))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        afc.press()  # the instructions were still on screen
        afc.press_at = None

    run(scenario())
    assert afc.removed == [NEW_PATH]
    assert list(afc.files) == [f"{DIR}/{OLD}"]


def test_cancel_while_waiting_leaves_nothing(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(None, existing={OLD: b"old"}, press_at=None)

    async def scenario():
        task = asyncio.create_task(F.collect_fdr("UDID", 600, _nostage))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())
    assert afc.removed == [] and list(afc.files) == [f"{DIR}/{OLD}"]
    assert leftovers(fake_device) == [] and pending(fake_device) == []


def test_collect_fdr_corrupt_archive(fake_device, workdir):
    bad = workdir / "bad.tar.gz"
    bad.write_bytes(b"not a tar at all" * 10)
    FakeManager.afc = afc = FakeAfc(bad)
    with pytest.raises(EngineError) as ei:
        run(F.collect_fdr("UDID", 60, _nostage))
    assert ei.value.code == "fdr_no_archive"
    assert afc.removed == [NEW_PATH]  # the device copy was still deleted
    assert leftovers(fake_device) == []


def test_background_cleanup_skips_an_archive_a_check_is_working_on(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(None, existing={NEW: b"being downloaded"}, press_at=None)
    F._claimed.add(NEW_PATH)
    job = F._Job("k", "UDID", frozenset(), (time.time() - 60, time.time() + 60))
    assert asyncio.run(F._sweep_new(afc, job)) is True
    assert afc.removed == []


def test_resumed_cleanup_never_deletes_what_the_owner_made_later(fake_device, workdir):
    later = stamped(0, "owner-later")  # made today, 3 days after the interrupted check
    own_old = stamped(-3 * 24 * 3600, "check")
    FakeManager.afc = afc = FakeAfc(None, existing={OLD: b"o", later: b"owner", own_old: b"the check's"},
                                    press_at=None)
    t0 = time.time() - 3 * 24 * 3600
    F._save(F._Job("old", "UDID", frozenset({OLD}), (t0, t0 + 900), own=f"{DIR}/{own_old}", created=t0))

    async def next_start():
        assert F.resume_pending() == 1
        await F.wait_background(3)

    asyncio.run(next_start())
    assert afc.removed == [f"{DIR}/{own_old}"]  # only the check's own archive
    assert set(afc.files) == {f"{DIR}/{OLD}", f"{DIR}/{later}"}


def test_a_bad_saved_entry_does_not_block_the_others(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(None, existing={NEW: b"left by a check"}, press_at=None)
    good = F._Job("good", "UDID", frozenset(), (time.time() - 60, time.time()), own=NEW_PATH).to_json()
    fake_device.mkdir(parents=True, exist_ok=True)
    (fake_device / "pending-cleanups.json").write_text(json.dumps([
        {"key": "bad", "udid": "UDID", "created": "yesterday", "window": [0, 1]},
        {"key": "worse", "udid": "UDID", "before": [["x"]], "created": time.time(), "window": [0, 1]},
        "junk", good,
    ]), encoding="utf-8")

    async def next_start():
        assert F.resume_pending() == 1
        await F.wait_background(3)

    asyncio.run(next_start())
    assert afc.removed == [NEW_PATH] and pending(fake_device) == []


def test_cleanup_is_saved_before_the_phone_can_get_an_archive(fake_device, workdir):
    FakeManager.afc = afc = FakeAfc(make_archive(workdir / "dev.tar.gz"), write_lists=1000)
    seen: dict = {}

    async def stage(s):
        if s == "waiting_trigger":
            seen["waiting"] = pending(fake_device)
        if s == "generating":
            seen["generating"] = pending(fake_device)
            raise SystemExit  # stands for a crash: no cancel path, no cleanup code runs

    async def scenario():
        with pytest.raises(SystemExit):
            await F.collect_fdr("UDID", 60, stage)

    asyncio.run(scenario())
    assert len(seen["waiting"]) == 1 and seen["waiting"][0]["own"] is None
    assert seen["generating"][0]["own"] == NEW_PATH


def test_zero_byte_archive_does_not_wait_forever(fake_device, workdir, monkeypatch):
    monkeypatch.setattr(F, "GENERATE_TIMEOUT_S", 0.5)
    FakeManager.afc = FakeAfc(None)  # the iPhone renames an empty archive and stops

    async def scenario():
        with pytest.raises(EngineError) as ei:
            await asyncio.wait_for(F.collect_fdr("UDID", 60, _nostage), 10)
        return ei.value

    assert run(scenario()).code == "timeout"


def test_cancel_while_extracting_removes_the_download_after_the_thread(fake_device, workdir, monkeypatch):
    import threading
    FakeManager.afc = FakeAfc(make_archive(workdir / "dev.tar.gz"))
    real = F.extract_report
    release = threading.Event()

    def slow_extract(path):
        with open(path, "rb"):
            release.wait(5)  # holds the file open, as tarfile does
        return real(path)

    monkeypatch.setattr(F, "extract_report", slow_extract)
    stages: list[str] = []

    async def stage(s):
        stages.append(s)

    async def scenario():
        task = asyncio.create_task(F.collect_fdr("UDID", 60, stage))
        while "extracting" not in stages:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()

    run(scenario())
    assert leftovers(fake_device) == []


def test_startup_sweep_removes_downloads_left_by_a_killed_engine(fake_device):
    from lacre_engine import paths
    parent = paths.temp_parent()
    (parent / "dl-abc").mkdir(parents=True)
    (parent / "dl-abc" / "sysdiagnose.tar.gz").write_bytes(b"seller logs")
    (parent / "pending-cleanups.json").write_text("[]", encoding="utf-8")
    (parent / "dl-busy").mkdir()
    (parent / "dl-busy" / "sysdiagnose.tar.gz").write_bytes(b"another app copy is downloading")
    old = time.time() - 3600
    for p in (parent / "dl-abc", parent / "dl-abc" / "sysdiagnose.tar.gz"):
        os.utime(p, (old, old))
    assert paths.sweep_local_temp() == 1
    assert leftovers(parent) == ["dl-busy"] and (parent / "pending-cleanups.json").exists()


def test_delete_archives_only_accepts_plain_archive_names(fake_device, workdir):
    other = "sysdiagnose_2026.10.30_09-00-00-0300_b.tar.gz"
    FakeManager.afc = afc = FakeAfc(None, existing={OLD: b"a", other: b"b", "notes.txt": b"n"}, press_at=None)
    res = asyncio.run(F.delete_archives("UDID", [
        OLD, "../" + other, "notes.txt", inprog(NEW), 42, "sysdiagnose_gone.tar.gz",
    ]))
    assert res["deleted"] == [OLD, "sysdiagnose_gone.tar.gz"]  # an already-gone one counts as deleted
    assert len(res["failed"]) == 4
    assert afc.removed == [f"{DIR}/{OLD}"]
    assert set(afc.files) == {f"{DIR}/{other}", f"{DIR}/notes.txt"}
