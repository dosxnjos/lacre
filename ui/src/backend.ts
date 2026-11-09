// Backend bridge: Tauri commands when running inside the shell, a mock otherwise
// (so `npm run ui:dev` shows the whole flow in a plain browser).
import type { EngineError, EngineEvent, Lang } from "./types";

export interface Settings { lang?: Lang | string | null }

export interface Backend {
  readonly isMock: boolean;
  engine<T = unknown>(cmd: string, args?: Record<string, unknown>): Promise<T>;
  onEngineEvent(handler: (e: EngineEvent) => void): Promise<() => void>;
  status(): Promise<unknown>;
  saveTextFile(defaultName: string, contents: string, kind: "html" | "txt"): Promise<string | null>;
  getSettings(): Promise<Settings>;
  setSettings(lang: Lang): Promise<void>;
  openExternal(url: string): Promise<void>;
}

/** Normalizes anything thrown by invoke() into {code, detail}. */
export function toEngineError(e: unknown): EngineError {
  if (e && typeof e === "object" && "code" in e) {
    const o = e as { code: unknown; detail?: unknown };
    return { code: String(o.code), detail: String(o.detail ?? "") };
  }
  if (typeof e === "string") {
    try {
      const o = JSON.parse(e);
      if (o && typeof o === "object" && "code" in o) return { code: String(o.code), detail: String(o.detail ?? "") };
    } catch { /* not JSON */ }
    return { code: "internal", detail: e };
  }
  return { code: "internal", detail: e instanceof Error ? e.message : String(e) };
}

function hasTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function tauriBackend(): Promise<Backend> {
  const { invoke } = await import("@tauri-apps/api/core");
  const { listen } = await import("@tauri-apps/api/event");
  const call = async <T>(cmd: string, args?: Record<string, unknown>): Promise<T> => {
    try {
      return await invoke<T>(cmd, args);
    } catch (e) {
      throw toEngineError(e);
    }
  };
  return {
    isMock: false,
    engine: (cmd, args = {}) => call("engine_request", { cmd, args }),
    onEngineEvent: async (handler) => listen<EngineEvent>("engine-event", (e) => handler(e.payload)),
    status: () => call("engine_status"),
    saveTextFile: async (defaultName, contents, kind) => {
      const r = await call<unknown>("save_text_file", { defaultName, contents, kind });
      return typeof r === "string" ? r : r ? String(r) : null;
    },
    getSettings: async () => {
      const r = await call<unknown>("get_settings");
      return r && typeof r === "object" ? (r as Settings) : {};
    },
    setSettings: async (lang) => { await call("set_settings", { lang }); },
    openExternal: async (url) => { await call("open_external", { url }); },
  };
}

let instance: Promise<Backend> | null = null;

export function getBackend(): Promise<Backend> {
  if (!instance) {
    instance = hasTauri() ? tauriBackend() : import("./mock").then((m) => m.createMockBackend());
  }
  return instance;
}
