"""Analysis rules against the sanitized iPhone 11 fixtures, plus synthetic mutations."""
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from lacre_engine import analyze as A

FIX = Path(__file__).parent / "fixtures"
TODAY = "2026-11-09"


@pytest.fixture
def raw() -> dict:
    return json.loads((FIX / "iphone11_raw.json").read_text(encoding="utf-8"))


@pytest.fixture
def fdr() -> dict:
    return json.loads((FIX / "iphone11_fdr.json").read_text(encoding="utf-8"))


def section(a: dict, sid: str) -> dict | None:
    return next((s for s in a["sections"] if s and s["id"] == sid), None)


def codes(a: dict, sid: str) -> list[str]:
    return [i["code"] for i in section(a, sid)["items"]]


def find(a: dict, sid: str, code: str, **params) -> list[dict]:
    return [i for i in section(a, sid)["items"]
            if i["code"] == code and all(i["params"].get(k) == v for k, v in params.items())]


# ---------------------------------------------------------------- fixture expectations

def test_fixture_full(raw, fdr):
    a = A.analyze(raw, fdr, TODAY)
    assert a["verdict"] == {"status": "alert", "code": "alert_items", "params": {}}
    assert [s["id"] for s in a["sections"]] == ["purchase", "factory", "parts", "battery"]

    dev = a["device"]
    assert dev["model_name"] == "iPhone 11" and dev["product_type"] == "iPhone12,1"
    assert dev["assembly"] == "2022-07" and dev["assembly_source"] == "serial"
    assert len(dev["imei"]) == 2

    findmy = find(a, "purchase", "findmy_on")
    assert len(findmy) == 1 and findmy[0]["status"] == "alert"
    assert findmy[0]["params"]["account_masked"].endswith("@example.com")
    assert find(a, "purchase", "mdm_none")[0]["status"] == "ok"
    prof = find(a, "purchase", "profiles_installed")[0]
    assert prof["status"] == "warn" and prof["params"]["count"] == 1 and prof["params"]["names"] == ["Example DNS"]
    assert find(a, "purchase", "activation_state", state="Activated")[0]["status"] == "ok"
    assert find(a, "purchase", "origin_prefix", prefix="M", kind="new_retail")[0]["status"] == "ok"

    fac = section(a, "factory")
    assert fac["verified_count"] == 50 and fac["failed_count"] == 0
    assert fac["seal_date"] == "01/07/2022 01:17:04 GMT"
    assert codes(a, "factory") == ["fdr_summary"]  # "not required to seal" keys are silent
    summ = fac["items"][0]
    assert summ["status"] == "ok" and summ["params"]["failed"] == 0 and summ["params"]["verified"] == 50

    part_items = section(a, "parts")["items"]
    dated = [i for i in part_items if i["code"].startswith("part_")]
    assert dated and all(i["code"] == "part_date_ok" and i["status"] == "ok" for i in dated)
    assert {i["params"]["part"] for i in dated} == {
        "camera_back", "camera_ultrawide", "camera_front", "faceid_ir", "faceid_projector",
        "display_component", "battery"}
    disp = [i for i in dated if i["params"]["part"] == "display_component"]
    assert [i["params"]["index"] for i in disp] == [1, 2, 3, 4] and all(i["params"]["count"] == 4 for i in disp)
    assert find(a, "parts", "faceid_pairing_ok")[0]["status"] == "ok"

    health = find(a, "battery", "battery_health_official")[0]
    assert health["params"]["percent"] == 79 and health["status"] == "alert"  # < 80 per PROTOCOL
    cyc = find(a, "battery", "battery_cycles")[0]
    assert cyc["params"] == {"cycles": 1042, "design_cycles": 500} and cyc["status"] == "na"
    est = find(a, "battery", "battery_health_estimate")[0]
    assert est["status"] == "na" and est["params"]["nominal_pct"] == 78 and est["params"]["raw_pct"] == 80
    assert find(a, "battery", "battery_age_ok")[0]["status"] == "ok"

    assert [n["code"] for n in a["notices"]] == ["screenshot_left_in_photos"]
    json.dumps(a)  # JSON-serializable


def test_fixture_without_fdr(raw):
    a = A.analyze(raw, None, TODAY)
    assert section(a, "factory") is None and a["sections"][1] is None
    assert not find(a, "battery", "battery_health_official")
    assert a["notices"] == []
    assert a["verdict"]["code"] == "alert_items"  # Find My still on


def test_today_parameter_is_used(raw, fdr):
    # Same input, different "today": the analysis must not depend on the wall clock.
    a1 = A.analyze(raw, fdr, "2026-11-09")
    a2 = A.analyze(raw, fdr, dt.date(2026, 11, 9))
    assert a1 == a2


# ---------------------------------------------------------------- verdict paths

def _clean(raw: dict) -> dict:
    r = copy.deepcopy(raw)
    r["info"]["NonVolatileRAM"]["fm-activation-locked"] = {"$hex": b"NO".hex()}
    r["profiles"] = {"ProfileMetadata": {}}
    return r


def test_verdict_factory_ok(raw, fdr):
    a = A.analyze(_clean(raw), {**fdr, "battery_health_percent": 90}, TODAY)
    assert find(a, "purchase", "findmy_off")[0]["status"] == "ok"
    assert a["verdict"]["code"] == "factory_ok" and a["verdict"]["status"] == "ok"


def test_verdict_factory_ok_with_warnings(raw, fdr):
    a = A.analyze(_clean(raw), {**fdr, "battery_health_percent": 82}, TODAY)
    assert find(a, "battery", "battery_health_official")[0]["status"] == "warn"
    assert a["verdict"]["code"] == "factory_ok_with_warnings"


def test_verdict_dates_ok_and_warnings(raw):
    assert A.analyze(_clean(raw), None, TODAY)["verdict"]["code"] == "dates_ok"
    a = A.analyze(raw | {"info": _clean(raw)["info"]}, None, TODAY)  # profile still installed
    assert a["verdict"] == {"status": "warn", "code": "warnings", "params": {}}


@pytest.mark.parametrize("pct,status", [(85, "ok"), (84, "warn"), (80, "warn"), (79, "alert")])
def test_battery_official_thresholds(raw, fdr, pct, status):
    a = A.analyze(raw, {**fdr, "battery_health_percent": pct}, TODAY)
    assert find(a, "battery", "battery_health_official")[0]["status"] == status


# ---------------------------------------------------------------- synthetic mutations

def test_fdr_part_mismatch_battery(raw, fdr):
    f = copy.deepcopy(fdr)
    f["fdr"]["FailureData"].append(
        {"vcrt": {"SealedInstance": "SEALED-AAAA", "LiveInstance": "LIVE-BBBB"}})
    a = A.analyze(raw, f, TODAY)
    mm = find(a, "factory", "fdr_part_mismatch")
    assert len(mm) == 1
    assert mm[0]["status"] == "alert"
    assert mm[0]["params"] == {"key": "vcrt", "part": "battery", "sealed": "SEALED-AAAA", "live": "LIVE-BBBB"}
    assert section(a, "factory")["failed_count"] == 1
    assert find(a, "factory", "fdr_summary")[0]["status"] == "alert"


def test_fdr_part_missing_live_and_unverified(raw, fdr):
    f = copy.deepcopy(fdr)
    f["fdr"]["FailureData"].append({"tcrt": {"SealedInstance": "X"}})
    f["fdr"]["FailureProperties"].append({"WMac": {"WarningMessage": "could not query"}})
    f["fdr"]["DataFailedToReport"] = ["something"]
    f["fdr"]["ApTicket"] = "Untrusted"
    a = A.analyze(_clean(raw), f, TODAY)
    mm = find(a, "factory", "fdr_part_mismatch")[0]
    assert mm["params"]["part"] == "display_touch" and mm["params"]["live"] is None
    un = find(a, "factory", "fdr_unverified")[0]
    assert un["status"] == "warn" and un["params"] == {"key": "WMac", "part": "wifi", "message": "could not query"}
    assert find(a, "factory", "fdr_data_failed_to_report")[0]["status"] == "warn"
    assert find(a, "factory", "fdr_apticket", value="Untrusted")[0]["status"] == "warn"
    assert section(a, "factory")["failed_count"] == 2
    assert a["verdict"]["code"] == "alert_items"


def test_fdr_not_available(raw):
    a = A.analyze(_clean(raw), {"has_fdr": False, "fdr": None, "battery_health_percent": 88, "seal_date": None}, TODAY)
    assert codes(a, "factory") == ["fdr_not_available"]
    assert find(a, "battery", "battery_health_official")[0]["status"] == "ok"
    # no verified FDR -> falls through to the date rules; fdr_not_available is a warn
    assert a["verdict"]["code"] == "warnings"


def test_camera_dated_two_years_after_assembly(raw):
    r = copy.deepcopy(raw)
    # assembly 2022-W27; supplier DNL, year digit 4, week 27 -> 2024-W27
    r["cameras"]["AppleH10CamIn"]["BackCameraModuleSerialNumString"] = "DNL42726L4EG51C6D"
    a = A.analyze(r, None, TODAY)
    it = find(a, "parts", "part_date_much_later", part="camera_back")
    assert len(it) == 1 and it[0]["status"] == "alert" and it[0]["params"]["made"] == "2024-07"
    assert it[0]["params"]["months"] == 24


def test_part_late_and_much_older(raw):
    r = copy.deepcopy(raw)
    r["cameras"]["AppleH10CamIn"]["FrontCameraModuleSerialNumString"] = "DNM24549MVG103K1H"  # 2022-W45: +18 w
    r["cameras"]["AppleH10CamIn"]["BackCameraModuleSerialNumString"] = "DNL02026L4EG51C6D"   # 2020-W20: older
    a = A.analyze(r, None, TODAY)
    late = find(a, "parts", "part_date_late", part="camera_front")[0]
    assert late["status"] == "warn" and late["params"]["weeks"] == 18
    old = find(a, "parts", "part_date_much_older", part="camera_back")[0]
    assert old["status"] == "warn" and old["params"]["months"] > 18


def test_missing_nvram_findmy_unknown(raw):
    r = copy.deepcopy(raw)
    del r["info"]["NonVolatileRAM"]
    a = A.analyze(r, None, TODAY)
    assert find(a, "purchase", "findmy_unknown")[0]["status"] == "warn"


def test_no_cameras_incomplete_without_fdr(raw):
    r = _clean(raw)
    r["cameras"] = {}
    a = A.analyze(r, None, TODAY)
    assert find(a, "parts", "cameras_unreadable")[0]["status"] == "warn"
    assert not find(a, "parts", "faceid_pairing_ok")
    assert a["verdict"] == {"status": "warn", "code": "incomplete", "params": {"missing": ["cameras"]}}


def test_no_cameras_with_fdr_is_factory_verdict(raw, fdr):
    r = _clean(raw)
    r["cameras"] = {}
    a = A.analyze(r, {**fdr, "battery_health_percent": 90}, TODAY)
    assert a["verdict"]["code"] == "factory_ok_with_warnings"


def test_display_unreadable_and_no_dates(raw):
    r = _clean(raw)
    r["display"] = {}
    a = A.analyze(r, None, TODAY)
    assert find(a, "parts", "display_unreadable")[0]["status"] == "warn"
    assert a["verdict"]["params"]["missing"] == ["display"]
    r["display"] = {"AppleCLCD": {"Panel_ID": "XXXX+YYYYYY"}}
    a = A.analyze(r, None, TODAY)
    assert find(a, "parts", "display_no_dates")[0]["status"] == "warn"


def test_mdm_variants(raw):
    r = copy.deepcopy(raw)
    r["cloud"] = {"IsSupervised": True, "OrganizationName": "ACME"}
    assert find(A.analyze(r, None, TODAY), "purchase", "mdm_supervised", org="ACME")[0]["status"] == "alert"
    r["cloud"] = {"IsSupervised": False, "ConfigurationSource": 2}
    assert find(A.analyze(r, None, TODAY), "purchase", "mdm_cloud_config", source=2)[0]["status"] == "warn"
    r["cloud"] = None
    assert find(A.analyze(r, None, TODAY), "purchase", "mdm_unknown")[0]["status"] == "warn"
    r["profiles"] = None
    assert find(A.analyze(r, None, TODAY), "purchase", "profiles_unknown")[0]["status"] == "warn"


@pytest.mark.parametrize("prefix,kind,status", [
    ("M", "new_retail", "ok"), ("N", "apple_replacement", "warn"), ("F", "apple_refurb", "warn"),
    ("P", "engraved", "ok"), ("3", "demo_or_thirdparty_refurb", "warn"),
    ("5", "demo_or_thirdparty_refurb", "warn"), ("Z", "unknown", "warn")])
def test_origin_prefix(raw, prefix, kind, status):
    r = copy.deepcopy(raw)
    r["info"]["ModelNumber"] = prefix + "HDH3"
    it = find(A.analyze(r, None, TODAY), "purchase", "origin_prefix")[0]
    assert it["params"]["prefix"] == prefix and it["params"]["kind"] == kind and it["status"] == status


def test_faceid_unexpected_and_touchid(raw):
    r = copy.deepcopy(raw)
    r["cameras"]["AppleH10CamIn"]["RomeoStatus"] = "Invalid"
    assert find(A.analyze(r, None, TODAY), "parts", "faceid_pairing_unexpected", value="Invalid")
    r = copy.deepcopy(raw)
    r["info"]["ProductType"] = "iPhone12,8"
    del r["cameras"]["AppleH10CamIn"]["RomeoStatus"]
    assert find(A.analyze(r, None, TODAY), "parts", "touchid_not_checked")[0]["status"] == "na"


def test_part_no_serial_undecodable_no_anchor(raw):
    r = copy.deepcopy(raw)
    r["info"]["SerialNumber"] = "ABCDEFGHJK"  # randomized 10-char: no date
    r["info"]["MLBSerialNumber"] = "??"
    r["platform"] = {}
    r["cameras"]["AppleH10CamIn"]["BackCameraModuleSerialNumString"] = ""
    r["cameras"]["AppleH10CamIn"]["FrontCameraModuleSerialNumString"] = "ZZ"
    a = A.analyze(r, None, TODAY)
    assert a["device"]["assembly"] is None
    assert "no_assembly_date" in [n["code"] for n in a["notices"]]
    assert find(a, "parts", "part_no_serial", part="camera_back")[0]["status"] == "na"
    assert find(a, "parts", "part_undecodable", part="camera_front")[0]["status"] == "na"
    assert find(a, "parts", "part_no_anchor", part="faceid_ir")[0]["params"]["made"] == "2022-04"
    assert a["verdict"]["code"] == "alert_items"  # findmy
    r["info"]["NonVolatileRAM"]["fm-activation-locked"] = {"$hex": b"NO".hex()}
    r["profiles"] = {}
    assert A.analyze(r, None, TODAY)["verdict"]["code"] == "incomplete"


def test_board_serial_gap_notice(raw):
    r = copy.deepcopy(raw)
    r["info"]["MLBSerialNumber"] = "DVX2058196BA133S"  # board 2022-W05, serial 2022-W27: ~154 days
    a = A.analyze(r, None, TODAY)
    gap = [n for n in a["notices"] if n["code"] == "board_serial_date_gap"]
    assert gap and gap[0]["params"] == {"board": "2022-01", "serial": "2022-07"}


def test_battery_younger_and_low_cycles(raw):
    r = copy.deepcopy(raw)
    r["battery"]["BatteryData"]["LifetimeData"]["TotalOperatingTime"] = 2000  # ~0.2 years on
    r["battery"]["BatteryData"]["CycleCount"] = 40
    a = A.analyze(r, None, TODAY)
    assert find(a, "battery", "battery_age_younger")[0]["status"] == "warn"
    assert find(a, "battery", "battery_cycles")[0]["params"]["cycles"] == 40
    assert "low_cycles_old_device" in [n["code"] for n in a["notices"]]


def test_design_cycles_table():
    assert A.design_cycles("iPhone15,3") == 500   # 14 Pro Max
    assert A.design_cycles("iPhone15,4") == 1000  # 15
    assert A.design_cycles("iPhone16,1") == 1000  # 15 Pro
    assert A.design_cycles("iPhone17,5") == 1000


def test_unknown_camera_module(raw):
    r = copy.deepcopy(raw)
    r["cameras"]["AppleH10CamIn"]["BackMacroCameraModuleSerialNumString"] = "DNL21026L4EG51C6D"
    it = find(A.analyze(r, None, TODAY), "parts", "part_date_ok", part="camera_other")
    assert it and it[0]["params"]["module"] == "BackMacroCameraModule"


# ---------------------------------------------------------------- decoding tables

def test_old_serial_iphone11_j1_is_week27_2022():
    today = dt.date(2026, 11, 9)
    floor = A.year_floor("iPhone12,1", today)
    assert floor == 2018
    assert A.old_serial_date("DV6J110JH32D", floor, today) == dt.date.fromisocalendar(2022, 27, 1)


def test_old_serial_jh_week40_family_fallback():
    # 'J' = year digit 2, second half; 'H' = 14th week letter -> week 14 + 26 = 40.
    # iPhone5,x is not in FAMILY_YEAR: floor falls back to today.year - 9, so the digit resolves to the
    # only year ending in 2 inside [today.year-9, today.year].
    today = dt.date(2026, 11, 9)
    floor = A.year_floor("iPhone5,2", today)
    assert floor == 2017
    assert A.old_serial_date("C8QJHABCDEFG", floor, today) == dt.date.fromisocalendar(2022, 40, 1)
    # Read in 2014 (the era of the iPhone 5), the same fallback resolves to 2012.
    then = dt.date(2014, 6, 1)
    assert A.old_serial_date("C8QJHABCDEFG", A.year_floor("iPhone5,2", then), then) == \
        dt.date.fromisocalendar(2012, 40, 1)


def test_old_serial_first_half_and_invalid():
    today = dt.date(2026, 11, 9)
    # 'H' = index 4: digit 2, first half; '1' -> week 1 -> 2022-W01 for an iPhone 11
    assert A.old_serial_date("C8QH1ABCDEFG", 2018, today) == dt.date.fromisocalendar(2022, 1, 1)
    assert A.old_serial_date("C8QA1ABCDEFG", 2018, today) is None  # 'A' not a year letter
    assert A.old_serial_date("C8QH0ABCDEFG", 2018, today) is None  # '0' not a week letter
    assert A.old_serial_date("SHORT", 2018, today) is None


def test_part_serial_and_future_year():
    today = dt.date(2026, 11, 9)
    assert A.part_serial_date("DNL21026L4EG51C6D", 2018, today) == dt.date.fromisocalendar(2022, 10, 1)
    assert A.part_serial_date({"$hex": b"FL8220908G8P3QVJ0\x00".hex()}, 2018, today) == \
        dt.date.fromisocalendar(2022, 20, 1)
    assert A.part_serial_date("DNL29926", 2018, today) is None  # week 99
    # digit 7 with floor 2018 -> 2027 > today.year -> None
    assert A.part_serial_date("DNL71026L4EG", 2018, today) is None
    # week 53 in a 52-week year falls back to week 52
    assert A.week_to_date(2021, 53, today) == dt.date.fromisocalendar(2021, 52, 1)
    # dates more than 14 days in the future are rejected
    assert A.week_to_date(2026, 52, today) is None


def test_hex_text():
    assert A.hex_text({"$hex": "59455300"}) == "YES"
    assert A.hex_text({"$hex": "zz"}) is None
    assert A.hex_text({"$hex": "0001"}) is None
    assert A.hex_text("  x ") == "x"
    assert A.hex_text("") is None and A.hex_text(5) is None
