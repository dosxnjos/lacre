import { h, svg } from "../dom";
import { msg, t } from "../i18n";
import { icons, noteIcon, statusIcon } from "../icons";
import type { Note } from "../state";
import type { Item, Status } from "../types";

/** Params that are identifiers or raw values: shown only with "technical details". */
export const TECH_KEYS = ["serial", "key", "sealed", "live", "detail", "value", "prefix", "source"];

export function chip(status: Status): HTMLElement {
  return h("span", { class: `chip chip-${status}` }, svg(statusIcon(status), "chip-icon"), t().status[status]);
}

/** Title line of a warning or error box: the situation icon before the text. */
export function calloutTitle(icon: string, text: string): HTMLElement {
  return h("p", { class: "callout-title" }, svg(icon, "callout-icon"), h("span", null, text));
}

/** One-line result under a button (export, delete), with the icon of its outcome. */
export function noteLine(note: Note, extra: Record<string, string> = {}): HTMLElement {
  return h("p", { class: `export-note note-${note.kind}`, role: "status", ...extra }, svg(noteIcon(note.kind), "note-icon"), h("span", null, note.text));
}

export function itemTitle(it: Item): string {
  const d = t().items[it.code];
  return d ? msg(d.title, it.params) : it.code;
}
export function itemText(it: Item): string {
  const d = t().items[it.code];
  return d ? msg(d.text, it.params) : "";
}

export function techPairs(params: Record<string, unknown>): [string, string][] {
  const out: [string, string][] = [];
  for (const k of TECH_KEYS) {
    const v = params[k];
    if (v === null || v === undefined || v === "") continue;
    out.push([t().techLabels[k] ?? k, Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v)]);
  }
  return out;
}

export function itemRow(it: Item, showTech: boolean): HTMLElement {
  const tech = showTech ? techPairs(it.params) : [];
  return h("li", { class: `row row-${it.status}` },
    chip(it.status),
    h("div", { class: "row-body" },
      h("p", { class: "row-title" }, itemTitle(it)),
      itemText(it) ? h("p", { class: "row-text" }, itemText(it)) : null,
      tech.length ? h("dl", { class: "tech" }, tech.map(([k, v]) => [h("dt", null, k), h("dd", null, v)])) : null,
    ),
  );
}

export function list(rows: HTMLElement[], cls = ""): HTMLElement {
  return h("ul", { class: `list ${cls}`.trim() }, rows);
}

export function button(label: string, onClick: () => void, kind: "primary" | "secondary" | "quiet" = "secondary", extra: Record<string, string> = {}): HTMLButtonElement {
  return h("button", { type: "button", class: `btn btn-${kind}`, onclick: onClick as EventListener, ...extra }, label);
}

export function errorText(code: string): { title: string; text: string } {
  const e = (t().errors as Record<string, { title: string; text: Parameters<typeof msg>[0] }>)[code];
  return e ? { title: e.title, text: msg(e.text) } : { title: t().errors.internal.title, text: t().unknownError(code) };
}

export function errorBox(code: string, detail: string, showTech: boolean, onRetry?: () => void): HTMLElement {
  const e = errorText(code);
  return h("div", { class: "callout callout-alert", role: "alert" },
    calloutTitle(icons.circleX, e.title),
    h("p", null, e.text),
    showTech && detail ? h("p", { class: "mono small" }, detail) : null,
    onRetry ? h("div", { class: "actions" }, button(t().common.retry, onRetry, "secondary")) : null,
  );
}
