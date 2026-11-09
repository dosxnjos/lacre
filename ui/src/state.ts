import type { Backend } from "./backend";
import type {
  Analysis, CheckResult, Device, EngineError, FdrStage, Hello, Lang, Prereq, RawFdr, RawRead, ReadStep,
} from "./types";

export type Phase = "startup" | "engine_failed" | "prereq" | "connect" | "reading" | "results";
export type Tab = "results" | "factory" | "tests" | "report";

export interface FdrState {
  status: "idle" | "running" | "done" | "failed" | "cancelled";
  stage: FdrStage | null;
  /** While `stage` is `reconnecting`: the stage the link dropped in (the step list keeps it current). */
  pausedFrom?: FdrStage | null;
  startedAt: number | null;
  finishedAt: number | null;
  eventId: string | null;
  error: EngineError | null;
}

export interface State {
  lang: Lang;
  backend: Backend | null;
  phase: Phase;
  hello: Hello | null;
  prereq: Prereq | null;
  startupError: EngineError | null;
  devices: Device[];
  connectError: EngineError | null;
  selectedUdid: string | null;
  read: { done: ReadStep[]; current: ReadStep | null; analyzing: boolean; error: EngineError | null };
  raw: RawRead | null;
  rawFdr: RawFdr | null;
  analysis: Analysis | null;
  checkedAt: Date | null;
  device: Device | null;
  tab: Tab;
  fdr: FdrState;
  checks: Record<string, CheckResult>;
  showTech: boolean;
  demo: boolean;
  exportNote: Note | null;
  /** Deleting the diagnostics that were already on the iPhone (factory tab). */
  archives: { busy: boolean; note: Note | null };
}

export interface Note { kind: "ok" | "err" | "info"; text: string }

export function initialState(lang: Lang): State {
  return {
    lang,
    backend: null,
    phase: "startup",
    hello: null,
    prereq: null,
    startupError: null,
    devices: [],
    connectError: null,
    selectedUdid: null,
    read: { done: [], current: null, analyzing: false, error: null },
    raw: null,
    rawFdr: null,
    analysis: null,
    checkedAt: null,
    device: null,
    tab: "results",
    fdr: { status: "idle", stage: null, startedAt: null, finishedAt: null, eventId: null, error: null },
    checks: {},
    showTech: false,
    demo: false,
    exportNote: null,
    archives: { busy: false, note: null },
  };
}

export interface Actions {
  retryStartup(): void;
  openStore(): void;
  selectDevice(udid: string): void;
  startRead(): void;
  startDemo(): void;
  setTab(tab: Tab): void;
  startFdr(): void;
  cancelFdr(): void;
  deleteOldArchives(): void;
  toggleTech(): void;
  setCheck(id: string, r: CheckResult | null): void;
  exportReport(kind: "html" | "txt"): void;
  setLang(l: Lang): void;
  restart(): void;
}

export interface Ctx { s: State; act: Actions }
