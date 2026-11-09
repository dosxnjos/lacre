"""Pure analysis of a RawRead (+ optional RawFdr) into the PROTOCOL `Analysis` structure.

Ported rule by rule from `reference_conferir.py` (`avaliar`, `avaliar_fdr`, `veredito` and the decoding
helpers). Differences from the prototype, all deliberate:
- no prose: every finding is an item code + params (the UI translates);
- `today` is a parameter (the prototype read `date.today()` at import time);
- input keys are the PROTOCOL English ones (`battery`, `display`, `platform`, `cloud`, `profiles`).

Nothing here touches the device or the clock.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

# ---------------------------------------------------------------- tables

# Proper product names (not translated; identical in pt-BR and en).
MODELS = {
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8", "iPhone10,2": "iPhone 8 Plus",
    "iPhone10,5": "iPhone 8 Plus", "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X",
    "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max", "iPhone11,6": "iPhone XS Max",
    "iPhone11,8": "iPhone XR", "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max", "iPhone12,8": "iPhone SE (2nd generation)",
    "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro",
    "iPhone13,4": "iPhone 12 Pro Max", "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13",
    "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,6": "iPhone SE (3rd generation)", "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus",
    "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max", "iPhone15,4": "iPhone 15",
    "iPhone15,5": "iPhone 15 Plus", "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus", "iPhone17,1": "iPhone 16 Pro",
    "iPhone17,2": "iPhone 16 Pro Max", "iPhone17,5": "iPhone 16e",
}

# Launch year of each product family (number before the comma): resolves the decade of a 1-digit year.
FAMILY_YEAR = {7: 2014, 8: 2015, 9: 2016, 10: 2017, 11: 2018, 12: 2019, 13: 2020,
               14: 2021, 15: 2022, 16: 2023, 17: 2024, 18: 2025, 19: 2026}

# First letter of the sale model number -> (status, kind). Community reading; Apple does not publish it.
MODEL_PREFIX = {
    "M": ("ok", "new_retail"),
    "N": ("warn", "apple_replacement"),
    "F": ("warn", "apple_refurb"),
    "P": ("ok", "engraved"),
    "3": ("warn", "demo_or_thirdparty_refurb"),
    "5": ("warn", "demo_or_thirdparty_refurb"),
}

# IORegistry camera module name -> PROTOCOL part code.
CAMERA_PARTS = {
    "BackCameraModule": "camera_back",
    "BackSuperWideCameraModule": "camera_ultrawide",
    "BackTeleCameraModule": "camera_tele",
    "BackTelephotoCameraModule": "camera_tele",
    "FrontCameraModule": "camera_front",
    "FrontIRCameraModule": "faceid_ir",
    "FrontIRStructuredLightProjector": "faceid_projector",
    "BackLiDARCameraModule": "lidar",
}
RX_CAMERA_KEY = re.compile(r"^(.*(?:CameraModule|Projector|LiDAR\w*))SerialNumString$")
FACEID_STATUS_KEY = "RomeoStatus"  # Face ID: projector pairing with the board
TOUCHID_MODELS = ("iPhone12,8", "iPhone14,6")

# FDR 4-letter classes -> PROTOCOL part code (partial mapping, only where the content confirms it).
FDR_PARTS = {
    "vcrt": "battery", "bat#": "battery", "tcrt": "display_touch", "GpCl": "display",
    "drp#": "display_panel", "mlb#": "board", "SrNm": "serial",
    "imei": "imei", "ime2": "imei", "WMac": "wifi", "BMac": "bluetooth",
}

# Old 12-char serial: 4th char = year + half, 5th char = week inside the half (1-27).
# Tables checked against OpenCore macserial (AppleYearReverse / AppleTblWeek).
YEAR_LETTERS = "CDFGHJKLMNPQRSTVWXYZ"
WEEK_LETTERS = "123456789CDFGHJKLMNPQRTVWXY"

# Part/board serial "PPP Y WW...": supplier (3) + year (1 digit) + week (2).
RX_PART = re.compile(r"^[A-Z0-9]{3}(\d)(\d{2})[A-Z0-9]")

# Part date thresholds, in weeks relative to the assembly anchor.
LATE_WEEKS = 10
MUCH_LATER_WEEKS = 26
MUCH_OLDER_WEEKS = 78
WEEKS_PER_MONTH = 4.35
# Board vs serial date gap that raises a notice.
ANCHOR_GAP_DAYS = 120

# Official battery health thresholds (Settings > Battery > Health).
BATTERY_OK_PCT = 85
BATTERY_WARN_PCT = 80

# Notices that make the verdict "warn" (screenshot_left_in_photos is informational only).
WARNING_NOTICES = {"board_serial_date_gap", "no_assembly_date", "low_cycles_old_device"}


# ---------------------------------------------------------------- small helpers

def d_(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def hex_text(v: Any) -> str | None:
    """`{"$hex": ...}` or plain string -> printable text (up to the first NUL), else None."""
    if isinstance(v, dict) and "$hex" in v:
        try:
            t = bytes.fromhex(v["$hex"]).split(b"\x00")[0].decode("utf-8", "replace").strip()
            return t if t and t.isprintable() else None
        except (ValueError, TypeError):
            return None
    return v.strip() if isinstance(v, str) and v.strip() else None


def plain(v: Any) -> Any:
    """FDR values for params: `{"$hex"}` -> text when printable, else the hex string; others unchanged."""
    if isinstance(v, dict) and "$hex" in v:
        return hex_text(v) or v["$hex"]
    return v


def ym(d: dt.date | None) -> str | None:
    return f"{d.year:04d}-{d.month:02d}" if d else None


def parse_today(today: str | dt.date) -> dt.date:
    if isinstance(today, dt.date):
        return today
    return dt.date.fromisoformat(str(today))


# ---------------------------------------------------------------- date decoding

def year_floor(product_type: str, today: dt.date) -> int:
    """First plausible part manufacturing year for this model (family launch year - 1)."""
    m = re.match(r"^iPhone(\d+),", product_type or "")
    if m and int(m.group(1)) in FAMILY_YEAR:
        return FAMILY_YEAR[int(m.group(1))] - 1
    return today.year - 9


def resolve_year(digit: int, floor: int, today: dt.date) -> int | None:
    """Single year digit -> the only year in [floor, floor+9] ending in it; None if in the future."""
    for year in range(floor, floor + 10):
        if year % 10 == digit:
            return year if year <= today.year else None
    return None


def week_to_date(year: int | None, week: int, today: dt.date) -> dt.date | None:
    if not year:
        return None
    for w in (week, 52):
        try:
            d = dt.date.fromisocalendar(year, w, 1)
            return d if d <= today + dt.timedelta(days=14) else None
        except ValueError:
            continue
    return None


def old_serial_date(sn: str, floor: int, today: dt.date) -> dt.date | None:
    """12-char device serial (made until ~May/2021): 4th = year+half, 5th = week.
    Randomized serials (8-14 chars, usually 10) carry no date."""
    if not sn or len(sn) != 12:
        return None
    a, w = sn[3], sn[4]
    if a not in YEAR_LETTERS or w not in WEEK_LETTERS:
        return None
    i = YEAR_LETTERS.index(a)
    week = WEEK_LETTERS.index(w) + 1 + 26 * (i % 2)
    return week_to_date(resolve_year(i // 2, floor, today), week, today)


def part_serial_date(sn: Any, floor: int, today: dt.date) -> dt.date | None:
    """Part/board serial in the PPP Y WW... format."""
    sn = hex_text(sn)
    if not sn:
        return None
    m = RX_PART.match(sn.strip().upper())
    if not m:
        return None
    week = int(m.group(2))
    if not 1 <= week <= 53:
        return None
    return week_to_date(resolve_year(int(m.group(1)), floor, today), week, today)


def design_cycles(product_type: str) -> int:
    """Apple rates 80% capacity at 500 cycles (iPhone 14 and earlier) or 1000 (iPhone 15 and later)."""
    m = re.match(r"^iPhone(\d+),(\d+)", product_type or "")
    if not m:
        return 500
    major, minor = int(m.group(1)), int(m.group(2))
    if major >= 16 or (major == 15 and minor >= 4):
        return 1000
    return 500


def item(code: str, status: str, **params: Any) -> dict:
    return {"code": code, "status": status, "params": params}


# ---------------------------------------------------------------- factory record (FDR)

def analyze_fdr(raw_fdr: dict | None) -> dict | None:
    """RawFdr -> the `factory` section (or None when no FDR was attempted)."""
    if not raw_fdr:
        return None
    if not raw_fdr.get("has_fdr"):
        return {"id": "factory", "items": [item("fdr_not_available", "warn")],
                "seal_date": raw_fdr.get("seal_date"), "verified_count": 0, "failed_count": 0}
    f = d_(raw_fdr.get("fdr"))
    items: list[dict] = []
    failed = 0

    def entries(lst):
        for x in lst or []:
            for k, v in d_(x).items():
                yield k, d_(v)

    verified = [k for k, _ in entries(f.get("VerifiedData"))] + [k for k, _ in entries(f.get("VerifiedProperties"))]
    for section, field in (("FailureData", "Instance"), ("FailureProperties", "Property")):
        for k, v in entries(f.get(section)):
            live, sealed = v.get("Live" + field), v.get("Sealed" + field)
            warning = str(v.get("WarningMessage", ""))
            part = FDR_PARTS.get(k, "other")
            if k == "SrvP":
                # Not a part: a service flag. Seen 0 -> 1 on an Apple replacement unit (model number "N...",
                # sealed after the model was discontinued) whose physical parts all matched. Undocumented by
                # Apple, so it is shown as a warning to explain, not as a swapped part.
                if live != sealed:
                    items.append(item("fdr_service_flag", "warn", key=k, sealed=plain(sealed), live=plain(live)))
                continue
            if sealed is not None and live != sealed:
                failed += 1
                items.append(item("fdr_part_mismatch", "alert", key=k, part=part,
                                  sealed=plain(sealed), live=plain(live)))
            elif "not required to seal" in warning:
                continue  # key Apple does not seal: informational
            else:
                failed += 1
                items.append(item("fdr_unverified", "warn", key=k, part=part, message=warning or None))
    if f.get("DataFailedToReport"):
        items.append(item("fdr_data_failed_to_report", "warn", detail=str(f.get("DataFailedToReport"))[:200]))
    if f.get("ApTicket") not in (None, "Trusted"):
        items.append(item("fdr_apticket", "warn", value=str(f.get("ApTicket"))))
    named = sorted({FDR_PARTS[k] for k in verified if k in FDR_PARTS})
    items.insert(0, item("fdr_summary", "ok" if not failed else "alert",
                         verified=len(verified), failed=failed, named_parts=named))
    return {"id": "factory", "items": items, "seal_date": f.get("SealDate") or raw_fdr.get("seal_date"),
            "verified_count": len(verified), "failed_count": failed}


# ---------------------------------------------------------------- main analysis

def analyze(raw: dict, raw_fdr: dict | None, today: str | dt.date) -> dict:
    """RawRead + RawFdr|None + today -> PROTOCOL `Analysis`."""
    today = parse_today(today)
    raw = d_(raw)
    info = d_(raw.get("info"))
    plat = d_(raw.get("platform"))
    bat = d_(raw.get("battery"))
    bd = d_(bat.get("BatteryData"))
    purchase: list[dict] = []
    parts: list[dict] = []
    battery: list[dict] = []
    notices: list[dict] = []
    coverage = {"cameras": False, "display": False, "battery": False}

    product_type = str(info.get("ProductType") or "?")
    floor = year_floor(product_type, today)
    model_number = hex_text(info.get("ModelNumber")) or hex_text(plat.get("model-number")) or "?"
    sn = hex_text(info.get("SerialNumber")) or hex_text(plat.get("serial-number")) or ""
    mlb = hex_text(info.get("MLBSerialNumber")) or hex_text(plat.get("mlb-serial-number")) or ""

    # --- anchor: when the device was assembled (the later of board and serial)
    d_board = part_serial_date(mlb, floor, today)
    d_serial = old_serial_date(sn, floor, today)
    if d_serial and (not d_board or d_serial >= d_board):
        anchor, anchor_source = d_serial, "serial"
    elif d_board:
        anchor, anchor_source = d_board, "board"
    else:
        anchor, anchor_source = None, None
    if d_board and d_serial and abs((d_serial - d_board).days) > ANCHOR_GAP_DAYS:
        notices.append({"code": "board_serial_date_gap", "params": {"board": ym(d_board), "serial": ym(d_serial)}})
    if not anchor:
        notices.append({"code": "no_assembly_date", "params": {}})

    # --- purchase locks
    nvram = d_(info.get("NonVolatileRAM"))
    findmy = (hex_text(nvram.get("fm-activation-locked")) or "").upper()
    account = hex_text(nvram.get("fm-account-masked"))
    if findmy == "YES":
        purchase.append(item("findmy_on", "alert", account_masked=account))
    elif findmy == "NO":
        purchase.append(item("findmy_off", "ok"))
    else:
        purchase.append(item("findmy_unknown", "warn"))

    cloud = raw.get("cloud")
    if not isinstance(cloud, dict) or not cloud:
        purchase.append(item("mdm_unknown", "warn"))
    else:
        org = cloud.get("OrganizationName")
        if cloud.get("IsSupervised") or cloud.get("IsMDMUnremovable") or org:
            purchase.append(item("mdm_supervised", "alert", org=str(org) if org else None))
        elif cloud.get("ConfigurationSource", 0) not in (0, None):
            purchase.append(item("mdm_cloud_config", "warn", source=cloud.get("ConfigurationSource")))
        else:
            purchase.append(item("mdm_none", "ok"))

    profiles = raw.get("profiles")
    profile_list: list[dict] = []
    if isinstance(profiles, dict):
        profile_list = [p for p in d_(profiles.get("ProfileMetadata")).values() if isinstance(p, dict)]
    elif isinstance(profiles, list):
        profile_list = [p for p in profiles if isinstance(p, dict)]
    if profiles is None:
        purchase.append(item("profiles_unknown", "warn"))
    elif profile_list:
        names = [str(p.get("PayloadDisplayName", "?")) for p in profile_list]
        purchase.append(item("profiles_installed", "warn", count=len(profile_list), names=names))
    else:
        purchase.append(item("profiles_none", "ok"))

    state = info.get("ActivationState") or "?"
    purchase.append(item("activation_state", "ok" if state == "Activated" else "warn", state=state))

    prefix = model_number[:1]
    status, kind = MODEL_PREFIX.get(prefix, ("warn", "unknown"))
    purchase.append(item("origin_prefix", status, prefix=prefix, kind=kind, model_number=model_number))

    # --- parts
    def judge(part: str, serial: Any, cov: str | None = None, **extra: Any) -> None:
        serial = hex_text(serial)
        if not serial:
            parts.append(item("part_no_serial", "na", part=part, **extra))
            return
        d = part_serial_date(serial, floor, today)
        if not d:
            parts.append(item("part_undecodable", "na", part=part, serial=serial, **extra))
            return
        if cov:
            coverage[cov] = True
        base = dict(part=part, serial=serial, made=ym(d), **extra)
        if not anchor:
            parts.append(item("part_no_anchor", "na", **base))
            return
        weeks = (d - anchor).days / 7
        if weeks > MUCH_LATER_WEEKS:
            parts.append(item("part_date_much_later", "alert", months=round(weeks / WEEKS_PER_MONTH), **base))
        elif weeks > LATE_WEEKS:
            parts.append(item("part_date_late", "warn", weeks=round(weeks), **base))
        elif weeks < -MUCH_OLDER_WEEKS:
            parts.append(item("part_date_much_older", "warn", months=round(-weeks / WEEKS_PER_MONTH), **base))
        else:
            parts.append(item("part_date_ok", "ok", **base))

    cam_props: dict = {}
    for v in d_(raw.get("cameras")).values():
        cam_props.update(d_(v))
    for k, v in sorted(cam_props.items()):
        m = RX_CAMERA_KEY.match(k)
        if m:
            module = m.group(1)
            if module in CAMERA_PARTS:
                judge(CAMERA_PARTS[module], v, "cameras")
            else:
                judge("camera_other", v, "cameras", module=module)
    if not any(RX_CAMERA_KEY.match(k) for k in cam_props):
        parts.append(item("cameras_unreadable", "warn"))
    faceid = hex_text(cam_props.get(FACEID_STATUS_KEY))
    if faceid:
        if faceid.lower() in ("valid", "ok", "success"):
            parts.append(item("faceid_pairing_ok", "ok", value=faceid))
        else:
            parts.append(item("faceid_pairing_unexpected", "warn", value=faceid))

    panel = None
    for v in d_(raw.get("display")).values():
        for k, val in d_(v).items():
            if re.search(r"panel.?id", k, re.I):
                panel = hex_text(val) or panel
    if panel:
        tokens = [t for t in panel.split("+") if t]
        valid = [t for t in tokens if part_serial_date(t, floor, today)]
        if not valid:
            parts.append(item("display_no_dates", "warn"))
        for i, t in enumerate(valid, 1):
            judge("display_component", t, "display", index=i, count=len(valid))
    else:
        parts.append(item("display_unreadable", "warn"))
    if FACEID_STATUS_KEY not in cam_props and product_type in TOUCHID_MODELS:
        parts.append(item("touchid_not_checked", "na"))

    # --- battery (estimates do not count in the verdict; the official number is Settings' one)
    judge("battery", bd.get("Serial") or bat.get("Serial"), "battery")
    design = bd.get("DesignCapacity") or bat.get("DesignCapacity")
    nominal = bat.get("NominalChargeCapacity")
    raw_max = bat.get("AppleRawMaxCapacity")
    cycles = bd.get("CycleCount") if bd.get("CycleCount") is not None else bat.get("CycleCount")
    hours = d_(bd.get("LifetimeData")).get("TotalOperatingTime")

    health = (raw_fdr or {}).get("battery_health_percent") if raw_fdr else None
    if isinstance(health, (int, float)) and not isinstance(health, bool):
        st = "ok" if health >= BATTERY_OK_PCT else "warn" if health >= BATTERY_WARN_PCT else "alert"
        battery.append(item("battery_health_official", st, percent=int(health)))
    if isinstance(design, (int, float)) and design > 0 and (nominal or raw_max):
        battery.append(item(
            "battery_health_estimate", "na",
            nominal_pct=round(100 * nominal / design) if isinstance(nominal, (int, float)) else None,
            raw_pct=round(100 * raw_max / design) if isinstance(raw_max, (int, float)) else None,
            nominal_mah=nominal if isinstance(nominal, (int, float)) else None,
            raw_mah=raw_max if isinstance(raw_max, (int, float)) else None,
            design_mah=design))
    if cycles is not None:
        battery.append(item("battery_cycles", "na", cycles=cycles, design_cycles=design_cycles(product_type)))
    if isinstance(hours, (int, float)) and hours > 0 and anchor:
        age_days = max(1, (today - anchor).days)
        years_on, device_years = round(hours / 24 / 365.25, 1), round(age_days / 365.25, 1)
        if age_days > 365 and hours / (age_days * 24) < 0.5:
            battery.append(item("battery_age_younger", "warn", years_on=years_on, device_years=device_years))
        else:
            battery.append(item("battery_age_ok", "ok", years_on=years_on, device_years=device_years))
    if isinstance(cycles, int) and cycles < 100 and anchor and (today - anchor).days > 2 * 365:
        notices.append({"code": "low_cycles_old_device", "params": {"cycles": cycles}})

    factory = analyze_fdr(raw_fdr)
    if raw_fdr:
        # A sysdiagnose leaves a screenshot in Photos (the button combo takes one).
        notices.append({"code": "screenshot_left_in_photos", "params": {}})

    sections = [
        {"id": "purchase", "items": purchase},
        factory,
        {"id": "parts", "items": parts},
        {"id": "battery", "items": battery},
    ]
    imeis = [x for x in (info.get("InternationalMobileEquipmentIdentity"),
                         info.get("InternationalMobileEquipmentIdentity2")) if x]
    device = {
        "model_name": MODELS.get(product_type, product_type),
        "product_type": product_type,
        "ios": info.get("ProductVersion"),
        "build": info.get("BuildVersion"),
        "name": info.get("DeviceName"),
        "serial": sn or None,
        "imei": imeis,
        "model_number": model_number if model_number != "?" else None,
        "region": info.get("RegionInfo"),
        "assembly": ym(anchor),
        "assembly_source": anchor_source,
    }
    analysis = {"device": device, "sections": sections, "notices": notices}
    analysis["verdict"] = verdict(analysis, coverage, anchor is not None)
    return {"verdict": analysis["verdict"], "device": device, "sections": sections, "notices": notices}


def verdict(analysis: dict, coverage: dict, has_anchor: bool) -> dict:
    """Port of `veredito()`: the first matching rule wins."""
    statuses = [it["status"] for sec in analysis["sections"] if sec for it in sec["items"]]
    warn_notices = any(n["code"] in WARNING_NOTICES for n in analysis["notices"])
    factory = next((s for s in analysis["sections"] if s and s["id"] == "factory"), None)
    if "alert" in statuses:
        return {"status": "alert", "code": "alert_items", "params": {}}
    if factory and factory["failed_count"] == 0 and factory["verified_count"]:
        if "warn" in statuses or warn_notices:
            return {"status": "warn", "code": "factory_ok_with_warnings", "params": {}}
        return {"status": "ok", "code": "factory_ok", "params": {}}
    missing = [k for k in ("cameras", "display", "battery") if not coverage[k]]
    if not has_anchor or missing:
        return {"status": "warn", "code": "incomplete", "params": {"missing": missing}}
    if "warn" in statuses or warn_notices:
        return {"status": "warn", "code": "warnings", "params": {}}
    return {"status": "ok", "code": "dates_ok", "params": {}}
