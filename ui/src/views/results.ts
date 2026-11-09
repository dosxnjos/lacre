import { h, svg } from "../dom";
import { formatDate, formatSealDate, fx, msg, t } from "../i18n";
import { sealMark } from "../art";
import { localizeModel } from "../models";
import type { Ctx } from "../state";
import type { Analysis, Section } from "../types";
import { button, itemRow, list } from "./common";

const stamped = new WeakSet<Analysis>();

export function sectionById(a: Analysis, id: Section["id"]): Section | null {
  return (a.sections.find((x) => x && x.id === id) as Section | undefined) ?? null;
}

export function countStatuses(a: Analysis): { ok: number; warn: number; alert: number } {
  const c = { ok: 0, warn: 0, alert: 0 };
  for (const sec of a.sections) for (const it of sec?.items ?? []) if (it.status in c) c[it.status as keyof typeof c]++;
  return c;
}

export function verdictBanner(a: Analysis, s: Ctx["s"]): HTMLElement {
  const d = t();
  const v = d.verdicts[a.verdict.code];
  const c = countStatuses(a);
  const model = localizeModel(a.device.model_name, a.device.product_type, s.lang);
  // The seal "stamps" in once per analysis, not on every re-render (language switch, toggles).
  const stamp = !stamped.has(a);
  stamped.add(a);
  return h("section", { class: `verdict verdict-${a.verdict.status}${stamp ? " stamp" : ""}`, "aria-labelledby": "verdict-title" },
    svg(sealMark(a.verdict.status), "verdict-seal"),
    h("div", { class: "verdict-body" },
      h("p", { class: "verdict-device" },
        h("span", { class: "vd-model" }, model),
        h("span", { class: "vd-name" }, `“${a.device.name}”`),
        h("span", { class: "vd-ios" }, `iOS ${a.device.ios}`),
      ),
      h("h1", { id: "verdict-title", class: "verdict-title" }, v ? msg(v.title, a.verdict.params) : a.verdict.code),
      v ? h("p", { class: "verdict-text" }, msg(v.text, a.verdict.params)) : null,
      h("p", { class: "verdict-meta" },
        h("span", null, d.results.counts(c.ok, c.warn, c.alert)),
        s.checkedAt ? h("span", null, d.results.checkedOn(formatDate(s.checkedAt, true))) : null,
      ),
    ),
  );
}

function sectionBlock(id: Section["id"], sec: Section | null, s: Ctx["s"], extra?: HTMLElement | null): HTMLElement | null {
  if (!sec) return null;
  const d = t().results;
  return h("section", { class: "block", "aria-labelledby": `sec-${id}` },
    h("h2", { id: `sec-${id}`, class: "block-title" }, d.sections[id]),
    h("p", { class: "block-note" }, d.sectionNotes[id]),
    extra ?? null,
    list(sec.items.map((it) => itemRow(it, s.showTech))),
  );
}

export function deviceBlock(a: Analysis, s: Ctx["s"]): HTMLElement {
  const d = t().results;
  const r = d.deviceRows;
  const dev = a.device;
  const x = fx();
  const assembly = dev.assembly
    ? `${x.month(dev.assembly)} (${dev.assembly_source === "board" ? r.assemblyBoard : r.assemblySerial})`
    : r.noAssembly;
  const rows: [string, string, boolean?][] = [
    [r.model, `${localizeModel(dev.model_name, dev.product_type, s.lang)} (${dev.product_type})`],
    [r.name, dev.name],
    [r.ios, dev.ios],
    [r.modelNumber, dev.model_number],
    [r.region, dev.region],
    [r.assembly, assembly],
  ];
  if (s.showTech) {
    rows.push([r.serial, dev.serial, true]);
    dev.imei.forEach((im, i) => rows.push([dev.imei.length > 1 ? `${r.imei} ${i + 1}` : r.imei, im, true]));
  }
  return h("section", { class: "block", "aria-labelledby": "sec-device" },
    h("h2", { id: "sec-device", class: "block-title" }, d.deviceTitle),
    h("dl", { class: "list kv" }, rows.map(([k, v, mono]) => h("div", { class: "kv-row" }, h("dt", null, k), h("dd", { class: mono ? "mono" : null }, v || "?")))),
  );
}

export function resultsView({ s, act }: Ctx): HTMLElement {
  const a = s.analysis!;
  const d = t();
  const factory = sectionById(a, "factory");
  const notices = a.notices ?? [];

  const factoryCta = !factory
    ? h("section", { class: "block cta", "aria-labelledby": "cta-factory" },
        h("div", null,
          h("h2", { id: "cta-factory", class: "cta-title" }, d.results.factoryCtaTitle),
          h("p", null, d.results.factoryCtaText)),
        h("div", { class: "actions" },
          button(s.fdr.status === "running" ? d.fdr.running : d.results.factoryCtaButton, () => act.setTab("factory"), "primary")),
      )
    : null;

  const sealLine = factory?.seal_date ? h("p", { class: "block-sub" }, d.results.sealDate(formatSealDate(factory.seal_date))) : null;

  return h("div", { class: "results" },
    verdictBanner(a, s),
    notices.length
      ? h("section", { class: "notices", "aria-label": d.results.notices },
          h("h2", { class: "notices-title" }, d.results.notices),
          h("ul", null, notices.map((n) => h("li", null, d.notices[n.code] ? msg(d.notices[n.code], n.params) : n.code))))
      : null,
    sectionBlock("purchase", sectionById(a, "purchase"), s),
    factoryCta,
    sectionBlock("factory", factory, s, sealLine),
    sectionBlock("parts", sectionById(a, "parts"), s),
    sectionBlock("battery", sectionById(a, "battery"), s),
    deviceBlock(a, s),
    h("section", { class: "block next" },
      h("p", null, d.results.nextTests),
      h("div", { class: "actions" }, button(d.results.nextTestsButton, () => act.setTab("tests"), "secondary"))),
  );
}
