// Dictionary shape. Both languages implement it, so `tsc` fails if any code is missing.
import type {
  ErrorCode, FdrPart, FdrStage, ItemCode, NoticeCode, OriginKind, Params, PartName, ReadStep, Status, VerdictCode,
} from "../types";

/** Formatting helpers bound to the current language. */
export interface Fx {
  /** Localized part name for either part family; adds "n of m" for display components. */
  part(p: Params): string;
  fdrPart(p: Params): string;
  /** "2022-03" / "2022-03-14" -> "Mar 2022" in the current language. */
  month(v: unknown): string;
  list(v: unknown): string;
  num(v: unknown, digits?: number): string;
  /** Escapes nothing: dictionary output is always set as text. */
  s(v: unknown, fallback?: string): string;
}

export type Msg = string | ((p: Params, x: Fx) => string);

export interface Dict {
  langName: string;
  app: {
    name: string;
    tagline: string;
    switchLang: string;
    skipToContent: string;
    mockBadge: string;
    demoBadge: string;
  };
  common: {
    retry: string;
    cancel: string;
    back: string;
    close: string;
    continue: string;
    showTech: string;
    hideTech: string;
    technical: string;
    elapsed: string;
    minutes: (m: number, s: number) => string;
  };
  status: Record<Status, string>;
  startup: {
    starting: string;
    engineFailedTitle: string;
    engineFailedText: string;
    prereqTitle: string;
    prereqText: string;
    prereqWhy: string;
    prereqStep1: string;
    prereqStep2: string;
    prereqStep3: string;
    prereqButton: string;
    usbmuxdTitle: string;
    usbmuxdText: string;
  };
  connect: {
    title: string;
    text: string;
    stepCable: string;
    stepUnlock: string;
    stepTrust: string;
    searching: string;
    cableHint: string;
    trustHint: string;
    found: string;
    pickOne: string;
    ios: (v: string) => string;
    checkButton: string;
    privacy: string;
    demoButton: string;
    demoHint: string;
  };
  reading: {
    title: string;
    text: string;
    steps: Record<ReadStep, string>;
    analyzing: string;
    failedTitle: string;
  };
  nav: {
    results: string;
    factory: string;
    tests: string;
    report: string;
    another: string;
    anotherConfirm: string;
    anotherYes: string;
    /** Armed restart while the iPhone still holds old diagnostics: leaving does not delete them. */
    anotherKeep: string;
  };
  results: {
    checkedOn: (date: string) => string;
    readFrom: string;
    sections: { purchase: string; factory: string; parts: string; battery: string };
    sectionNotes: { purchase: string; factory: string; parts: string; battery: string };
    notices: string;
    deviceTitle: string;
    deviceRows: {
      model: string; name: string; ios: string; modelNumber: string; region: string; serial: string; imei: string;
      assembly: string; assemblySerial: string; assemblyBoard: string; noAssembly: string;
    };
    factoryCtaTitle: string;
    factoryCtaText: string;
    factoryCtaButton: string;
    sealDate: (d: string) => string;
    nextTests: string;
    nextTestsButton: string;
    counts: (ok: number, warn: number, alert: number) => string;
  };
  fdr: {
    title: string;
    lead: string;
    facts: { what: string; time: string; local: string; cleanup: string; photo: string };
    howTitle: string;
    howText: string;
    howSignal: string;
    howWrong: string;
    illustrationAlt: string;
    illustrationLabels: { volUp: string; volDown: string; side: string; together: string };
    start: string;
    stages: Record<FdrStage, { title: string; text: string }>;
    running: string;
    cancelled: string;
    /** After a failure past the trigger: the check's report may be on the iPhone; the engine deletes it on its own. */
    cleanupLater: string;
    failedTitle: string;
    doneTitle: string;
    doneText: string;
    redo: string;
    /** USB link lost during the check (stage `reconnecting`); the engine resumes when the iPhone is back. */
    lost: { title: string; text: string; elsewhere: string; open: string };
    /** The check's own archive could not be confirmed deleted yet (the engine keeps trying). */
    archiveLeft: string;
    /** Diagnostics that were already on the iPhone before the check. */
    oldArchives: {
      title: (n: number) => string;
      text: (n: number) => string;
      listLabel: string;
      created: (date: string) => string;
      undated: string;
      button: (n: number) => string;
      busy: string;
      deleted: (n: number) => string;
      failed: (n: number) => string;
      beforeLeaving: (n: number) => string;
    };
  };
  tests: {
    title: string;
    lead: string;
    progress: (done: number, total: number, failed: number) => string;
    pass: string;
    fail: string;
    skip: string;
    clear: string;
    howTo: string;
    qrTitle: string;
    qrText: string;
    qrNoPage: string;
    wallTitle: string;
    wallText: string;
  };
  report: {
    title: string;
    lead: string;
    exportHtml: string;
    exportTxt: string;
    saved: (path: string) => string;
    savedBrowser: string;
    saveCancelled: string;
    privacy: string;
    docTitle: (model: string) => string;
    generated: (when: string) => string;
    readOverUsb: string;
    manualTitle: string;
    manualNone: string;
    notDone: string;
    factoryNotDone: string;
    disclaimerTitle: string;
    disclaimer: string;
    keepPrivate: string;
    resultWord: Record<"pass" | "fail" | "skip" | "pending", string>;
    madeWith: string;
  };
  items: Record<ItemCode, { title: Msg; text: Msg }>;
  verdicts: Record<VerdictCode, { title: Msg; text: Msg }>;
  notices: Record<NoticeCode, Msg>;
  errors: Record<ErrorCode, { title: string; text: Msg }>;
  unknownError: (code: string) => string;
  parts: Record<PartName, string>;
  partIndexed: (name: string, index: number, count: number) => string;
  fdrParts: Record<FdrPart, string>;
  origin: Record<OriginKind, string>;
  missing: Record<"cameras" | "display" | "battery", string>;
  techLabels: Record<string, string>;
}
