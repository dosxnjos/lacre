// Data shapes from docs/PROTOCOL.md (engine <-> UI contract). Keep in sync.

export type Status = "ok" | "warn" | "alert" | "na";
export type Params = Record<string, unknown>;

export type PurchaseCode =
  | "findmy_on" | "findmy_off" | "findmy_unknown"
  | "mdm_supervised" | "mdm_cloud_config" | "mdm_none" | "mdm_unknown"
  | "profiles_installed" | "profiles_none" | "profiles_unknown"
  | "activation_state" | "origin_prefix";

export type FactoryCode =
  | "fdr_summary" | "fdr_part_mismatch" | "fdr_unverified" | "fdr_service_flag"
  | "fdr_data_failed_to_report" | "fdr_apticket" | "fdr_not_available";

export type PartsCode =
  | "part_date_ok" | "part_date_late" | "part_date_much_later" | "part_date_much_older"
  | "part_no_serial" | "part_undecodable" | "part_no_anchor"
  | "cameras_unreadable" | "display_unreadable" | "display_no_dates"
  | "faceid_pairing_ok" | "faceid_pairing_unexpected" | "touchid_not_checked";

export type BatteryCode =
  | "battery_health_official" | "battery_health_estimate" | "battery_cycles"
  | "battery_age_ok" | "battery_age_younger";

export type ItemCode = PurchaseCode | FactoryCode | PartsCode | BatteryCode;

export type VerdictCode =
  | "alert_items" | "factory_ok" | "factory_ok_with_warnings"
  | "incomplete" | "warnings" | "dates_ok";

export type NoticeCode =
  | "board_serial_date_gap" | "no_assembly_date" | "low_cycles_old_device" | "screenshot_left_in_photos";

export type ErrorCode =
  | "no_device" | "not_trusted" | "passcode_required" | "usbmux_unavailable" | "device_gone"
  | "timeout" | "fdr_no_archive" | "fdr_missing_report" | "cancelled" | "internal"
  // UI-side codes (not emitted by the engine)
  | "engine_unavailable" | "save_failed";

/** Part names used by fdr_part_mismatch / fdr_unverified (`part`). */
export type FdrPart =
  | "battery" | "display" | "display_touch" | "display_panel" | "board"
  | "serial" | "imei" | "wifi" | "bluetooth" | "other";

/** Part names used in the parts section (`part`). */
export type PartName =
  | "camera_back" | "camera_ultrawide" | "camera_tele" | "camera_front" | "faceid_ir"
  | "faceid_projector" | "lidar" | "display_component" | "battery";

export type OriginKind =
  | "new_retail" | "apple_replacement" | "apple_refurb" | "engraved" | "demo_or_thirdparty_refurb" | "unknown";

export type ReadStep = "identity" | "battery" | "hardware" | "parts" | "platform" | "mdm";
export const READ_STEPS: ReadStep[] = ["identity", "battery", "hardware", "parts", "platform", "mdm"];

/** `reconnecting`: the USB link dropped during waiting_trigger, generating or downloading; the engine waits
 *  for the iPhone and resumes (e.g. ... downloading [-> reconnecting -> downloading]* -> extracting ...).
 *  It is not a step of its own: the step list shows the step it paused (see `progressStage`). */
export type FdrStage = "waiting_trigger" | "generating" | "downloading" | "reconnecting" | "extracting" | "cleaning" | "done";
export const FDR_STAGES: FdrStage[] = ["waiting_trigger", "generating", "downloading", "extracting", "cleaning", "done"];
/** The step of FDR_STAGES a stage belongs to (`reconnecting` belongs to the step it paused,
 *  `downloading` when unknown). */
export function progressStage(stage: FdrStage | null, pausedFrom: FdrStage | null = null): FdrStage | null {
  if (stage !== "reconnecting") return stage;
  return pausedFrom && pausedFrom !== "reconnecting" ? pausedFrom : "downloading";
}

export interface Hello { engine_version: string; pymobiledevice3: string; platform: string }
export interface Prereq { usbmux_ok: boolean; hint: "apple_devices_missing" | "usbmuxd_missing" | null }
export interface Device { udid: string; name: string; product_type: string; ios: string; connection: string }

/** Opaque raw read (same format as the prototype's .json). */
export type RawRead = Record<string, unknown>;
export interface RawFdr {
  has_fdr: boolean;
  fdr?: unknown;
  battery_health_percent: number | null;
  seal_date: string | null;
  /** The engine confirmed the check's own archive is gone from the iPhone (missing in older results). */
  device_archive_removed?: boolean;
  /** Sysdiagnose archives that were already on the iPhone before the check (missing = none). */
  other_archives?: OldArchive[];
}

/** `date` is local "YYYY-MM-DDTHH:MM:SS" parsed from the archive name, or null. */
export interface OldArchive { name: string; date: string | null }
export interface DeleteArchivesResult { deleted: string[]; failed: string[] }

export interface Item { code: ItemCode; status: Status; params: Params }

export interface Section {
  id: "purchase" | "factory" | "parts" | "battery";
  items: Item[];
  seal_date?: string | null;
  verified_count?: number;
  failed_count?: number;
}

export interface AnalysisDevice {
  model_name: string;
  product_type: string;
  ios: string;
  name: string;
  serial: string;
  imei: string[];
  model_number: string;
  region: string;
  assembly: string | null;
  assembly_source: "serial" | "board" | null;
}

export interface Analysis {
  verdict: { status: Exclude<Status, "na">; code: VerdictCode; params: Params };
  device: AnalysisDevice;
  sections: (Section | null)[];
  notices: { code: NoticeCode; params: Params }[];
}

export interface EngineError { code: ErrorCode | string; detail: string }

export interface EngineEvent {
  v?: number;
  id: string;
  event: "progress" | "fdr";
  step?: ReadStep;
  done?: number;
  total?: number;
  stage?: FdrStage;
}

export type Lang = "pt-BR" | "en";

export type CheckResult = "pass" | "fail" | "skip";
