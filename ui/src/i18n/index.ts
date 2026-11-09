import type { Dict, Fx, Msg } from "./dict";
import type { Lang, Params } from "../types";
import { en } from "./en";
import { ptBR } from "./pt-BR";

const DICTS: Record<Lang, Dict> = { "pt-BR": ptBR, en };

let current: Lang = "en";

export function setLang(l: Lang): void {
  current = l;
  document.documentElement.lang = l;
}
export function getLang(): Lang { return current; }
export function t(): Dict { return DICTS[current]; }

export function normalizeLang(v: unknown): Lang | null {
  if (typeof v !== "string" || !v) return null;
  return v.toLowerCase().startsWith("pt") ? "pt-BR" : "en";
}
export function systemLang(): Lang {
  return normalizeLang(navigator.language) ?? "en";
}

function makeFx(d: Dict, lang: Lang): Fx {
  const monthFmt = new Intl.DateTimeFormat(lang, { month: "short", year: "numeric", timeZone: "UTC" });
  const listFmt = new Intl.ListFormat(lang, { style: "long", type: "conjunction" });
  const fx: Fx = {
    s: (v, fallback = "") => (v === null || v === undefined || v === "" ? fallback : String(v)),
    num: (v, digits = 0) => {
      const n = Number(v);
      if (v === null || v === undefined || Number.isNaN(n)) return "?";
      return n.toLocaleString(lang, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
    },
    month: (v) => {
      const m = /^(\d{4})-(\d{2})/.exec(String(v ?? ""));
      if (!m) return v ? String(v) : "?";
      return monthFmt.format(new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, 15)));
    },
    list: (v) => (Array.isArray(v) ? listFmt.format(v.map(String)) : v ? String(v) : ""),
    part: (p) => {
      const key = String(p.part ?? "");
      const base = (d.parts as Record<string, string>)[key] ?? (d.fdrParts as Record<string, string>)[key] ?? (key || d.fdrParts.other);
      const i = Number(p.index), c = Number(p.count);
      return i && c && c > 1 ? d.partIndexed(base, i, c) : base;
    },
    fdrPart: (p) => {
      const key = String(p.part ?? "other");
      return (d.fdrParts as Record<string, string>)[key] ?? d.fdrParts.other;
    },
  };
  return fx;
}

/** Resolves a dictionary message with params in the current language. */
export function msg(m: Msg, params: Params = {}): string {
  return typeof m === "function" ? m(params ?? {}, makeFx(t(), current)) : m;
}

export function fx(): Fx { return makeFx(t(), current); }

/** FDR SealDate comes as "DD/MM/YYYY HH:MM:SS GMT"; show it as a localized date. Falls back to the raw text. */
export function formatSealDate(raw: unknown): string {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})/.exec(String(raw ?? ""));
  if (!m) return String(raw ?? "");
  const d = new Date(Date.UTC(Number(m[3]), Number(m[2]) - 1, Number(m[1]), 12));
  return new Intl.DateTimeFormat(current, { dateStyle: "long", timeZone: "UTC" }).format(d);
}

export function formatDate(d: Date, withTime = false): string {
  return new Intl.DateTimeFormat(current, withTime
    ? { dateStyle: "long", timeStyle: "short" }
    : { dateStyle: "long" }).format(d);
}
