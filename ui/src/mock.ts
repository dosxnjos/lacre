// Browser-only mock backend (no Tauri shell). Returns the sanitized fixture data and
// simulates the engine's progress/fdr events so the whole flow can be seen in a browser.
// Scenarios via the URL: ?mock=clean | swap | nousbmux | two | untrusted | fdrfail | reconnect | delfail | delerror
// (reconnect: the USB link drops during the copy and comes back; delfail: one old diagnostic can't be
// deleted; delerror: delete_archives fails with device_gone).
import type { Backend } from "./backend";
import type { DeleteArchivesResult, Device, EngineError, EngineEvent, Lang, ListArchivesResult, OldArchive, RawFdr } from "./types";
import { READ_STEPS } from "./types";
import raw from "./mock-data/raw.json";
import fdr from "./mock-data/fdr.json";
import { mockAnalysis } from "./mock-data/analysis";

const scenario = new URLSearchParams(location.search).get("mock") ?? "default";
const speed = Number(new URLSearchParams(location.search).get("speed") ?? "1") || 1;

const fakeDevices: Device[] = [
  { udid: "00008030-0000000000000000", name: "iPhone de Teste", product_type: "iPhone12,1", ios: "26.6.2", connection: "USB" },
  { udid: "00008110-1111111111111111", name: "iPhone da Loja", product_type: "iPhone14,5", ios: "18.7", connection: "USB" },
];

// Diagnostics "already on the iPhone" before the check (names as the engine sees them; one without a date).
// Answered by list_archives after the quick read and by fdr as other_archives (?mock=clean: none).
const oldArchives: OldArchive[] = [
  { name: "sysdiagnose_2026.08.14_19-22-05-0300_iPhone-OS_iPhone_23A341.tar.gz", date: "2026-08-14T19:22:05" },
  { name: "sysdiagnose_2026.10.02_08-41-37-0300_iPhone-OS_iPhone_23A341.tar.gz", date: "2026-10-02T08:41:37" },
  { name: "sysdiagnose_unnamed.tar.gz", date: null },
];

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms / speed));
const fail = (code: string, detail = ""): never => { throw { code, detail } satisfies EngineError; };

export function createMockBackend(): Backend {
  const handlers = new Set<(e: EngineEvent) => void>();
  const emit = (e: EngineEvent) => handlers.forEach((h) => h({ v: 1, ...e }));
  const cancelled = new Set<string>();
  let seq = 0;
  const started = Date.now();
  let lang: Lang | null = null;
  // What is on the mock iPhone now: a delete removes entries, list_archives and fdr report what is left.
  let onPhone: OldArchive[] = scenario === "clean" ? [] : structuredClone(oldArchives);

  async function engine(cmd: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const id = `mock-${++seq}`;
    switch (cmd) {
      case "hello":
        await wait(300);
        return { engine_version: "0.1.0-mock", pymobiledevice3: "11.50.2", platform: "browser" };
      case "prereq":
        await wait(200);
        return scenario === "nousbmux" ? { usbmux_ok: false, hint: "apple_devices_missing" } : { usbmux_ok: true, hint: null };
      case "devices": {
        await wait(150);
        // Nothing plugged in for the first seconds, so the connect screen is visible.
        if (Date.now() - started < 3500 / speed) return [];
        if (scenario === "untrusted" && Date.now() - started < 9000 / speed) fail("not_trusted", "pairing dialog pending");
        return scenario === "two" ? fakeDevices : fakeDevices.slice(0, 1);
      }
      case "read": {
        for (let i = 0; i < READ_STEPS.length; i++) {
          emit({ id, event: "progress", step: READ_STEPS[i], done: i, total: READ_STEPS.length });
          await wait(i === 2 ? 1400 : 650);
        }
        emit({ id, event: "progress", step: "mdm", done: 6, total: 6 });
        return structuredClone(raw);
      }
      case "fdr": {
        const plan: [EngineEvent["stage"], number][] = [
          ["waiting_trigger", 5000], ["generating", 6000], ["downloading", 2500], ["extracting", 1200], ["cleaning", 900],
        ];
        if (scenario === "reconnect") plan.splice(3, 0, ["reconnecting", 8000], ["downloading", 1500]);
        for (const [stage, ms] of plan) {
          emit({ id, event: "fdr", stage });
          const until = Date.now() + ms / speed;
          while (Date.now() < until) {
            if (cancelled.has(id)) fail("cancelled", "cancelled by user");
            await wait(100 * speed);
          }
        }
        if (scenario === "fdrfail") fail("fdr_no_archive", "no sysdiagnose received");
        emit({ id, event: "fdr", stage: "done" });
        const out = structuredClone(fdr) as RawFdr;
        if (scenario === "clean" || scenario === "swap") out.battery_health_percent = 88;
        out.device_archive_removed = true;
        out.other_archives = structuredClone(onPhone);
        return out;
      }
      case "list_archives":
        await wait(600);
        return { archives: structuredClone(onPhone) } satisfies ListArchivesResult;
      case "delete_archives": {
        await wait(1200);
        if (scenario === "delerror") fail("device_gone", "lost the device while deleting");
        const names = Array.isArray(args.names) ? args.names.map(String) : [];
        const out: DeleteArchivesResult = { deleted: [], failed: [] };
        names.forEach((n, i) => (scenario === "delfail" && i === 0 ? out.failed : out.deleted).push(n));
        onPhone = onPhone.filter((a) => !out.deleted.includes(a.name));
        return out;
      }
      case "cancel":
        cancelled.add(String(args.target_id));
        return {};
      case "analyze":
        await wait(250);
        return mockAnalysis(scenario, Boolean(args.fdr));
      case "shutdown":
        return {};
      default:
        return fail("internal", `unknown cmd ${cmd}`);
    }
  }

  return {
    isMock: true,
    engine: engine as Backend["engine"],
    onEngineEvent: async (h) => { handlers.add(h); return () => handlers.delete(h); },
    status: async () => ({ running: true, mock: true }),
    saveTextFile: async (defaultName, contents, kind) => {
      const blob = new Blob([contents], { type: kind === "html" ? "text/html;charset=utf-8" : "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${defaultName}.${kind}`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      return a.download;
    },
    getSettings: async () => ({ lang }),
    setSettings: async (l) => { lang = l; },
    openExternal: async (url) => { window.open(url, "_blank", "noopener"); },
  };
}
