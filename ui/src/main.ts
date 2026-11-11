import "./styles.css";
import { getBackend, toEngineError } from "./backend";
import { h, svg } from "./dom";
import { normalizeLang, setLang, systemLang, t } from "./i18n";
import { brandMark, icons } from "./art";
import { statusIcon } from "./icons";
import { localizeModel } from "./models";
import { buildHtml, buildTxt, reportFileName } from "./report";
import { initialState, type Actions, type Ctx, type State, type Tab } from "./state";
import type {
  Analysis, DeleteArchivesResult, Device, EngineEvent, Hello, Lang, ListArchivesResult, OldArchive, Prereq, RawFdr, RawRead,
} from "./types";
import { READ_STEPS } from "./types";
import { errorText } from "./views/common";
import { connectView, prereqView, readingView, startupView } from "./views/flow";
import { resultsView } from "./views/results";
import { elapsedText, factoryView, lostNotice } from "./views/factory";
import { checkStats, patchCheck, testsView } from "./views/tests";
import { reportView } from "./views/report";

const APPLE_DEVICES_URL = "https://apps.microsoft.com/detail/9np83lwlpz9k";
const POLL_MS = 2000;

const root = document.getElementById("app")!;
const s: State = initialState(systemLang());
setLang(s.lang);

let pollTimer: number | null = null;
let fdrTicker: number | null = null;
let pendingCancel = false;
let restartArmed = false;

/** Bumped on every change to `s.oldArchives`: a `list_archives` answer from before it is stale. */
let archivesGen = 0;

function setOldArchives(list: OldArchive[] | null): void {
  s.oldArchives = list;
  archivesGen++;
}

/** Old diagnostics still on the connected iPhone (not deleted yet). */
function oldArchivesLeft(): number {
  return !s.demo && s.device ? (s.oldArchives?.length ?? 0) : 0;
}
let restartTimer: number | null = null;

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------ rendering

function header(): HTMLElement {
  const d = t();
  const other: Lang = s.lang === "pt-BR" ? "en" : "pt-BR";
  return h("header", { class: "topbar" },
    h("div", { class: "brand" },
      svg(brandMark(), "brand-svg"),
      h("span", { class: "brand-name" }, d.app.name),
      h("span", { class: "brand-tagline" }, d.app.tagline)),
    h("div", { class: "topbar-end" },
      s.demo ? h("span", { class: "mock-badge" }, d.app.demoBadge)
        : s.backend?.isMock ? h("span", { class: "mock-badge" }, d.app.mockBadge) : null,
      h("div", { class: "lang", role: "group", "aria-label": d.app.switchLang },
        (["pt-BR", "en"] as Lang[]).map((l) => h("button", {
          type: "button",
          class: "lang-btn",
          "data-fk": `lang-${l}`,
          lang: l,
          "aria-pressed": String(s.lang === l),
          title: l === other ? d.app.switchLang : null,
          onclick: (() => act.setLang(l)) as EventListener,
        }, l === "pt-BR" ? "PT" : "EN")),
      ),
    ),
  );
}

function fdrNavMeta(): string {
  const f = s.fdr;
  if (f.status === "running") return elapsedText(f.startedAt);
  return "";
}

function sideNav(): HTMLElement {
  const d = t();
  const a = s.analysis!;
  const st = checkStats(s);
  const tabs: [Tab, string, HTMLElement | null][] = [
    ["results", d.nav.results, svg(statusIcon(a.verdict.status), `nav-status nav-status-${a.verdict.status}`)],
    ["factory", d.nav.factory,
      s.fdr.status === "running"
        ? h("span", { class: "nav-meta tabular", id: "nav-fdr-meta" }, fdrNavMeta())
        : s.fdr.status === "done" ? svg(icons.check, "nav-check") : null],
    ["tests", d.nav.tests, h("span", { class: "nav-meta tabular", id: "nav-tests-meta" }, `${st.done}/${st.total}`)],
    ["report", d.nav.report, null],
  ];
  const dev = s.device;
  return h("nav", { class: "sidenav", "aria-label": d.app.name },
    h("div", { class: "nav-device" },
      h("span", { class: "nav-device-model" }, localizeModel(a.device.model_name, a.device.product_type, s.lang)),
      h("span", { class: "nav-device-name" }, a.device.name || dev?.name || "")),
    h("ul", { class: "nav-list" },
      tabs.map(([id, label, meta]) => h("li", null,
        h("button", {
          type: "button",
          class: `nav-item${s.tab === id ? " is-active" : ""}`,
          "aria-current": s.tab === id ? "page" : null,
          "data-fk": `tab-${id}`,
          onclick: (() => act.setTab(id)) as EventListener,
        }, h("span", null, label), meta)))),
    h("div", { class: "nav-foot" },
      h("button", {
        type: "button", class: "btn btn-quiet tech-toggle", "data-fk": "tech",
        "aria-pressed": String(s.showTech),
        onclick: act.toggleTech as EventListener,
      }, s.showTech ? d.common.hideTech : d.common.showTech),
      // Two-step restart (no native confirm dialog): the first click arms it for a few seconds.
      h("button", {
        type: "button", class: `btn btn-quiet${restartArmed ? " is-armed" : ""}`, "data-fk": "restart",
        title: restartArmed ? d.nav.anotherConfirm : null,
        disabled: s.fdr.status === "running" || s.archives.busy,
        onclick: act.restart as EventListener,
      }, restartArmed ? (oldArchivesLeft() ? d.nav.anotherKeep : d.nav.anotherYes) : d.nav.another)),
  );
}

function content(): HTMLElement {
  const ctx: Ctx = { s, act };
  switch (s.phase) {
    case "startup":
    case "engine_failed":
      return startupView(ctx);
    case "prereq":
      return prereqView(ctx);
    case "connect":
      return connectView(ctx);
    case "reading":
      return readingView(ctx);
    case "results": {
      const view = s.tab === "factory" ? factoryView(ctx) : s.tab === "tests" ? testsView(ctx) : s.tab === "report" ? reportView(ctx) : resultsView(ctx);
      // The hands-on tests can mean plugging cables: if the link drops during the copy, say so on any tab.
      // The slot is always there (and is the live region) so the banner comes and goes without a render.
      const slot = s.tab === "factory" ? null
        : h("div", { id: "fdr-lost", role: "status", "aria-live": "polite" }, lostBanner());
      return h("div", { class: "shell" }, sideNav(), h("div", { class: "pane" }, slot, view));
    }
  }
}

/** Lost-connection banner for the tabs other than factory (null when the link is fine). */
function lostBanner(): HTMLElement | null {
  return s.fdr.status === "running" && s.fdr.stage === "reconnecting" ? lostNotice(() => act.setTab("factory")) : null;
}

function render(): void {
  const fk = (document.activeElement as HTMLElement | null)?.dataset?.fk;
  const y = window.scrollY;
  document.title = s.analysis
    ? `${t().app.name}: ${localizeModel(s.analysis.device.model_name, s.analysis.device.product_type, s.lang)}`
    : t().app.name;
  root.replaceChildren(
    h("a", { class: "skip", href: "#main" }, t().app.skipToContent),
    header(),
    h("main", { id: "main", class: `main phase-${s.phase}`, tabindex: "-1" }, content()),
  );
  window.scrollTo(0, y);
  if (fk) root.querySelector<HTMLElement>(`[data-fk="${fk}"]`)?.focus();
}

function patchFdrClock(): void {
  const txt = elapsedText(s.fdr.startedAt);
  const a = document.getElementById("fdr-elapsed");
  if (a) a.textContent = txt;
  const b = document.getElementById("nav-fdr-meta");
  if (b) b.textContent = txt;
}

// ------------------------------------------------------------------ engine events

function onEngineEvent(e: EngineEvent): void {
  if (!e || typeof e !== "object") return;
  if (e.event === "progress" && s.phase === "reading") {
    const n = Math.max(0, Math.min(READ_STEPS.length, Number(e.done ?? 0)));
    // `done` counts finished steps (steps run in READ_STEPS order); the next one is in progress.
    s.read.done = READ_STEPS.slice(0, n);
    s.read.current = n < READ_STEPS.length ? READ_STEPS[n] : null;
    render();
  } else if (e.event === "fdr" && s.fdr.status === "running") {
    if (e.id) s.fdr.eventId = e.id;
    const prev = s.fdr.stage;
    if (e.stage) s.fdr.stage = e.stage;
    if (s.fdr.stage === "reconnecting" && prev !== "reconnecting") s.fdr.pausedFrom = prev;
    if (pendingCancel && s.fdr.eventId) {
      pendingCancel = false;
      void sendCancel(s.fdr.eventId);
    }
    // Other tabs only show the lost-connection banner: swap it in place (a full render would drop
    // keyboard focus on the Tests tab).
    const lostChanged = (prev === "reconnecting") !== (s.fdr.stage === "reconnecting");
    if (s.phase !== "results") return;
    if (s.tab === "factory") render();
    else if (lostChanged) {
      const banner = lostBanner();
      document.getElementById("fdr-lost")?.replaceChildren(...(banner ? [banner] : []));
    }
  }
}

async function sendCancel(target: string): Promise<void> {
  try { await s.backend!.engine("cancel", { target_id: target }); } catch { /* the fdr call reports the outcome */ }
}

// ------------------------------------------------------------------ flow

async function boot(): Promise<void> {
  s.phase = "startup";
  render();
  try {
    if (!s.backend) {
      s.backend = await getBackend();
      await s.backend.onEngineEvent(onEngineEvent);
      try {
        const st = await s.backend.getSettings();
        const l = normalizeLang(st.lang);
        if (l) { s.lang = l; setLang(l); }
      } catch { /* keep the system language */ }
      render();
    }
    let lastErr: unknown = null;
    for (let i = 0; i < 4 && !s.hello; i++) {
      try { s.hello = await s.backend.engine<Hello>("hello"); } catch (e) { lastErr = e; await sleep(800); }
    }
    if (!s.hello) throw lastErr ?? new Error("no hello");
  } catch (e) {
    s.startupError = toEngineError(e);
    s.phase = "engine_failed";
    render();
    return;
  }
  await checkPrereq();
}

async function checkPrereq(): Promise<void> {
  try {
    s.prereq = await s.backend!.engine<Prereq>("prereq");
  } catch (e) {
    s.startupError = toEngineError(e);
    s.phase = "engine_failed";
    render();
    return;
  }
  if (!s.prereq.usbmux_ok) {
    s.phase = "prereq";
    render();
    return;
  }
  goConnect();
}

function goConnect(): void {
  s.phase = "connect";
  s.devices = [];
  s.connectError = null;
  s.selectedUdid = null;
  render();
  startPolling();
}

function startPolling(): void {
  stopPolling();
  const tick = async () => {
    if (s.phase !== "connect") return;
    let devices: Device[] = [];
    let err: ReturnType<typeof toEngineError> | null = null;
    try {
      const r = await s.backend!.engine<Device[]>("devices");
      devices = Array.isArray(r) ? r.filter((d) => d && d.udid) : [];
    } catch (e) {
      err = toEngineError(e);
    }
    if (s.phase !== "connect") return;
    if (err?.code === "usbmux_unavailable") {
      s.prereq = { usbmux_ok: false, hint: "apple_devices_missing" };
      s.phase = "prereq";
      render();
      return;
    }
    const before = JSON.stringify([s.devices, s.connectError?.code ?? null, s.selectedUdid]);
    s.devices = devices;
    s.connectError = err;
    if (!devices.some((d) => d.udid === s.selectedUdid)) s.selectedUdid = devices.length === 1 ? devices[0].udid : null;
    if (JSON.stringify([s.devices, s.connectError?.code ?? null, s.selectedUdid]) !== before) render();
    pollTimer = window.setTimeout(tick, POLL_MS);
  };
  void tick();
}

function stopPolling(): void {
  if (pollTimer !== null) { clearTimeout(pollTimer); pollTimer = null; }
}

/** Lists the old diagnostics on the iPhone in the background, right after the quick read (read only).
 *  A failure is ignored: the card just does not show. */
async function loadOldArchives(udid: string): Promise<void> {
  const gen = archivesGen;
  let r: ListArchivesResult;
  try {
    r = await s.backend!.engine<ListArchivesResult>("list_archives", { udid });
  } catch {
    return;
  }
  // Another iPhone, a restart, the demo, a finished factory check or a delete happened meanwhile.
  if (gen !== archivesGen || s.demo || s.device?.udid !== udid || s.phase !== "results") return;
  const list = (Array.isArray(r?.archives) ? r.archives : [])
    .filter((a) => a && typeof a.name === "string" && a.name)
    .map((a) => ({ name: a.name, date: typeof a.date === "string" ? a.date : null }));
  setOldArchives(list);
  // "Check another iPhone" armed before the list arrived: it was armed without the warning, so disarm it
  // (the next click shows the warning next to the card).
  if (list.length && restartArmed) {
    restartArmed = false;
    if (restartTimer !== null) { clearTimeout(restartTimer); restartTimer = null; }
    render();
    return;
  }
  // Only the results tab shows the card now (a full render would drop keyboard focus on the Tests tab).
  if (list.length && s.tab === "results") render();
}

async function startRead(): Promise<void> {
  const dev = s.devices.find((d) => d.udid === s.selectedUdid);
  if (!dev) return;
  stopPolling();
  setOldArchives(null);
  s.device = dev;
  s.phase = "reading";
  s.read = { done: [], current: READ_STEPS[0], analyzing: false, error: null };
  render();
  try {
    const raw = await s.backend!.engine<RawRead>("read", { udid: dev.udid });
    s.raw = raw;
    s.read.done = [...READ_STEPS];
    s.read.current = null;
    s.read.analyzing = true;
    render();
    s.analysis = await s.backend!.engine<Analysis>("analyze", { raw, fdr: null, today: today() });
    s.rawFdr = null;
    s.checkedAt = new Date();
    s.fdr = { status: "idle", stage: null, startedAt: null, finishedAt: null, eventId: null, error: null };
    s.phase = "results";
    s.tab = "results";
    window.scrollTo(0, 0);
    render();
  } catch (e) {
    s.read.error = toEngineError(e);
    s.read.analyzing = false;
    render();
    return;
  }
  void loadOldArchives(dev.udid); // not awaited: the results screen is already up
}

async function startDemo(): Promise<void> {
  stopPolling();
  const [{ default: raw }, { default: rawFdr }] = await Promise.all([
    import("./mock-data/raw.json"), import("./mock-data/fdr.json"),
  ]);
  try {
    s.analysis = await s.backend!.engine<Analysis>("analyze", { raw, fdr: rawFdr, today: today() });
  } catch (e) {
    s.connectError = toEngineError(e);
    render();
    return;
  }
  s.demo = true;
  setOldArchives(null); // the demo never shows the old-diagnostics card
  s.raw = raw as unknown as RawRead;
  s.rawFdr = rawFdr as unknown as RawFdr;
  s.device = null;
  s.checkedAt = new Date();
  s.fdr = { status: "done", stage: "done", startedAt: Date.now(), finishedAt: Date.now(), eventId: null, error: null };
  s.phase = "results";
  s.tab = "results";
  window.scrollTo(0, 0);
  render();
}

async function startFdr(): Promise<void> {
  if (!s.device || !s.raw || s.fdr.status === "running" || s.archives.busy) return;
  pendingCancel = false;
  s.archives.note = null;
  s.fdr = { status: "running", stage: "waiting_trigger", startedAt: Date.now(), finishedAt: null, eventId: null, error: null };
  s.tab = "factory";
  render();
  window.scrollTo(0, 0);
  fdrTicker = window.setInterval(patchFdrClock, 1000);
  try {
    const rawFdr = await s.backend!.engine<RawFdr>("fdr", { udid: s.device.udid, timeout_s: 900 });
    s.fdr.stage = "done";
    s.rawFdr = rawFdr;
    // Fresher than the list from the quick read, and it leaves out the check's own archive.
    setOldArchives(Array.isArray(rawFdr?.other_archives) ? rawFdr.other_archives.slice() : []);
    s.analysis = await s.backend!.engine<Analysis>("analyze", { raw: s.raw, fdr: rawFdr, today: today() });
    s.checkedAt = new Date();
    s.fdr.status = "done";
  } catch (e) {
    const err = toEngineError(e);
    s.fdr.status = err.code === "cancelled" ? "cancelled" : "failed";
    s.fdr.error = err;
  } finally {
    s.fdr.finishedAt = Date.now();
    if (fdrTicker !== null) { clearInterval(fdrTicker); fdrTicker = null; }
    render();
  }
}

/** Deletes, at the user's request, the old diagnostics listed on the iPhone. */
async function deleteOldArchives(): Promise<void> {
  const listAtStart = s.oldArchives;
  const udid = s.device?.udid;
  const names = (listAtStart ?? []).map((a) => a.name);
  // Not during a factory check: the engine would hold the delete until the check ends.
  if (s.archives.busy || s.demo || !udid || !listAtStart || !names.length || s.fdr.status === "running") return;
  const job: State["archives"] = { busy: true, note: null };
  s.archives = job;
  render();
  // The device was switched, the app restarted (restart replaces s.archives) or the list was replaced
  // meanwhile: stale answer.
  const stale = () => {
    if (s.archives !== job || s.device?.udid !== udid || s.oldArchives !== listAtStart) {
      if (s.archives === job) { s.archives = { busy: false, note: null }; render(); }
      return true;
    }
    return false;
  };
  let note: State["archives"]["note"];
  try {
    const r = await s.backend!.engine<DeleteArchivesResult>("delete_archives", { udid, names });
    if (stale()) return;
    const o = t().fdr.oldArchives; // after the await: the language may have changed meanwhile
    const deleted = new Set(Array.isArray(r?.deleted) ? r.deleted : []);
    const failed = (Array.isArray(r?.failed) ? r.failed : []).filter((n) => names.includes(n));
    const remaining = listAtStart.filter((a) => !deleted.has(a.name));
    setOldArchives(remaining);
    const gone = names.filter((n) => deleted.has(n)).length;
    const left = remaining.length;
    note = failed.length || left
      ? { kind: "err", text: [gone ? o.deleted(gone) : "", o.failed(failed.length || left)].filter(Boolean).join(" ") }
      : { kind: "ok", text: o.deleted(gone) };
  } catch (e) {
    if (stale()) return;
    const err = toEngineError(e);
    const et = errorText(err.code);
    note = { kind: "err", text: `${et.title}. ${et.text}${s.showTech && err.detail ? ` (${err.detail})` : ""}` };
  } finally {
    job.busy = false;
  }
  s.archives = { busy: false, note };
  // Keep keyboard users oriented: from the button (which may vanish with the card) to the result note.
  const active = document.activeElement as HTMLElement | null;
  const fromButton = !active || active === document.body || active.dataset?.fk === "delete-archives";
  render();
  if (fromButton && s.phase === "results" && (s.tab === "factory" || s.tab === "results")) {
    (root.querySelector<HTMLElement>('[data-fk="archives-note"]')
      ?? document.getElementById(s.tab === "factory" ? "factory-title" : "main"))?.focus();
  }
}

async function exportReport(kind: "html" | "txt"): Promise<void> {
  if (!s.analysis) return;
  const d = t().report;
  try {
    const contents = kind === "html" ? buildHtml(s) : buildTxt(s);
    const path = await s.backend!.saveTextFile(reportFileName(s), contents, kind);
    s.exportNote = path
      ? { kind: "ok", text: s.backend!.isMock ? d.savedBrowser : d.saved(path) }
      : { kind: "info", text: d.saveCancelled };
  } catch (e) {
    const err = toEngineError(e);
    s.exportNote = { kind: "err", text: `${t().errors.save_failed.title}. ${t().errors.save_failed.text}${s.showTech ? ` (${err.detail})` : ""}` };
  }
  render();
}

const act: Actions = {
  retryStartup: () => {
    if (!s.hello) void boot();
    else { s.phase = "startup"; render(); void checkPrereq(); }
  },
  openStore: () => { void s.backend?.openExternal(APPLE_DEVICES_URL).catch(() => window.open(APPLE_DEVICES_URL, "_blank")); },
  selectDevice: (udid) => { s.selectedUdid = udid; render(); },
  startRead: () => { void startRead(); },
  startDemo: () => { void startDemo(); },
  setTab: (tab) => {
    s.tab = tab;
    s.exportNote = null;
    s.archives.note = null;
    render();
    window.scrollTo(0, 0);
    document.getElementById("main")?.focus({ preventScroll: true });
  },
  startFdr: () => { void startFdr(); },
  deleteOldArchives: () => { void deleteOldArchives(); },
  cancelFdr: () => {
    if (s.fdr.status !== "running") return;
    if (s.fdr.eventId) void sendCancel(s.fdr.eventId);
    else pendingCancel = true;
  },
  toggleTech: () => { s.showTech = !s.showTech; render(); },
  setCheck: (id, r) => {
    if (r === null || s.checks[id] === r) delete s.checks[id];
    else s.checks[id] = r;
    patchCheck(s, id);
    const meta = document.getElementById("nav-tests-meta");
    if (meta) { const st = checkStats(s); meta.textContent = `${st.done}/${st.total}`; }
  },
  exportReport: (kind) => { void exportReport(kind); },
  setLang: (l) => {
    if (l === s.lang) return;
    s.lang = l;
    setLang(l);
    s.exportNote = null;
    s.archives.note = null;
    render();
    void s.backend?.setSettings(l).catch(() => { /* not persisted; still switched */ });
  },
  restart: () => {
    if (s.fdr.status === "running" || s.archives.busy) return;
    if (s.analysis && !restartArmed) {
      restartArmed = true;
      const left = oldArchivesLeft();
      if (left) {
        // Leaving does not delete the old diagnostics: say so where the delete button is (results tab,
        // or the factory tab after a finished check; stay put if the current tab already shows it).
        const showsCard = s.tab === "results" || (s.tab === "factory" && s.fdr.status === "done");
        if (!showsCard) s.tab = s.fdr.status === "done" ? "factory" : "results";
        s.archives.note = { kind: "info", text: t().fdr.oldArchives.beforeLeaving(left) };
      }
      render();
      if (left) document.querySelector<HTMLElement>('[data-fk="archives-note"]')?.focus();
      if (restartTimer !== null) clearTimeout(restartTimer);
      restartTimer = window.setTimeout(() => { restartArmed = false; if (s.phase === "results") render(); }, left ? 30000 : 5000);
      return;
    }
    restartArmed = false;
    if (restartTimer !== null) { clearTimeout(restartTimer); restartTimer = null; }
    s.raw = null;
    s.rawFdr = null;
    s.analysis = null;
    s.device = null;
    s.checks = {};
    s.showTech = false;
    s.demo = false;
    s.exportNote = null;
    setOldArchives(null);
    s.archives = { busy: false, note: null };
    s.fdr = { status: "idle", stage: null, startedAt: null, finishedAt: null, eventId: null, error: null };
    goConnect();
  },
};

void boot();
