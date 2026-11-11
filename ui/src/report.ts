// Self-contained export (HTML with inline CSS, or plain text) in the current language.
import { esc } from "./dom";
import { formatDate, formatSealDate, fx, getLang, msg, t } from "./i18n";
import { CHECKLIST, GROUPS } from "./checklist";
import { localizeModel, modelSlug } from "./models";
import { reportPalette } from "./report-palette";
import type { State } from "./state";
import type { Analysis, Section, Status } from "./types";
import { itemText, itemTitle, techPairs } from "./views/common";

const ORDER: Section["id"][] = ["purchase", "factory", "parts", "battery"];

function sec(a: Analysis, id: Section["id"]): Section | null {
  return (a.sections.find((x) => x && x.id === id) as Section | undefined) ?? null;
}

export function reportFileName(s: State): string {
  const a = s.analysis!;
  const d = s.checkedAt ?? new Date();
  const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return `lacre-${modelSlug(localizeModel(a.device.model_name, a.device.product_type, "en"))}-${ymd}`;
}

function deviceRows(s: State): [string, string][] {
  const a = s.analysis!;
  const r = t().results.deviceRows;
  const dev = a.device;
  const assembly = dev.assembly
    ? `${fx().month(dev.assembly)} (${dev.assembly_source === "board" ? r.assemblyBoard : r.assemblySerial})`
    : r.noAssembly;
  const rows: [string, string][] = [
    [r.model, `${localizeModel(dev.model_name, dev.product_type, s.lang)} (${dev.product_type})`],
    [r.name, dev.name],
    [r.ios, dev.ios],
    [r.modelNumber, dev.model_number],
    [r.region, dev.region],
    [r.serial, dev.serial],
    ...dev.imei.map((im, i): [string, string] => [dev.imei.length > 1 ? `${r.imei} ${i + 1}` : r.imei, im]),
    [r.assembly, assembly],
  ];
  return rows;
}

const CSS = `
${reportPalette()}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.5 "Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,sans-serif}
main{max-width:820px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;line-height:1.2;margin:0 0 6px;font-weight:650;letter-spacing:-.01em}
h2{font-size:18px;margin:32px 0 8px;font-weight:650}
p{margin:0 0 8px}.mut{color:var(--mut)}.small{font-size:13px}
.verdict{border-radius:16px;padding:18px 20px;margin:20px 0}
.verdict h2{margin:0 0 4px;font-size:20px}
.v-ok{background:var(--ok-bg);color:var(--ok)}.v-warn{background:var(--warn-bg);color:var(--warn)}.v-alert{background:var(--alert-bg);color:var(--alert)}
.verdict p{color:var(--tx)}
.card{background:var(--card);border:1px solid var(--ln);border-radius:14px;overflow:hidden}
table{width:100%;border-collapse:collapse}td,th{padding:10px 14px;border-top:1px solid var(--ln);text-align:left;vertical-align:top}
tr:first-child td,tr:first-child th{border-top:0}th{font-weight:500;color:var(--mut);width:38%}
.chip{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;white-space:nowrap}
.s-ok{color:var(--ok);background:var(--ok-bg)}.s-warn{color:var(--warn);background:var(--warn-bg)}
.s-alert{color:var(--alert);background:var(--alert-bg)}.s-na,.s-skip,.s-pending{color:var(--na);background:var(--na-bg)}
.s-pass{color:var(--ok);background:var(--ok-bg)}.s-fail{color:var(--alert);background:var(--alert-bg)}
td.c{width:1%;white-space:nowrap}.t{font-weight:600;margin:0}.x{color:var(--mut);margin:2px 0 0}
.tech{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--mut);margin-top:4px;word-break:break-all}
.notices{background:var(--card);border:1px solid var(--ln);border-radius:14px;padding:6px 20px}
.disc{border-top:1px solid var(--ln);margin-top:36px;padding-top:16px;font-size:13px;color:var(--mut)}
@media print{body{background:var(--paper)}.card,.notices{border-color:var(--rule)}}
`;

export function buildHtml(s: State): string {
  const a = s.analysis!;
  const d = t();
  const lang = getLang();
  const st = (x: Status | string) => d.status[x as Status] ?? x;
  const when = formatDate(new Date(), true);
  const model = localizeModel(a.device.model_name, a.device.product_type, s.lang);
  const v = d.verdicts[a.verdict.code];
  const rowsHtml = (secn: Section) => secn.items.map((it) => {
    const tech = techPairs(it.params).map(([k, val]) => `${esc(k)}: ${esc(val)}`).join("<br>");
    return `<tr><td class="c"><span class="chip s-${it.status}">${esc(st(it.status))}</span></td><td><p class="t">${esc(itemTitle(it))}</p>`
      + `${itemText(it) ? `<p class="x">${esc(itemText(it))}</p>` : ""}${tech ? `<div class="tech">${tech}</div>` : ""}</td></tr>`;
  }).join("");

  let body = `<h1>${esc(d.report.docTitle(model))}</h1>
${s.demo ? `<p class="verdict v-warn"><strong>${esc(d.app.demoBadge)}</strong></p>` : ""}
<p class="mut">${esc(d.report.generated(when))}. ${esc(d.report.readOverUsb)}</p>
<div class="verdict v-${a.verdict.status}"><h2>${esc(v ? msg(v.title, a.verdict.params) : a.verdict.code)}</h2>
${v ? `<p>${esc(msg(v.text, a.verdict.params))}</p>` : ""}</div>`;

  if (a.notices?.length) {
    body += `<h2>${esc(d.results.notices)}</h2><div class="notices"><ul>${a.notices.map((n) => `<li>${esc(d.notices[n.code] ? msg(d.notices[n.code], n.params) : n.code)}</li>`).join("")}</ul></div>`;
  }
  for (const id of ORDER) {
    const x = sec(a, id);
    body += `<h2>${esc(d.results.sections[id])}</h2>`;
    if (!x) {
      body += `<div class="card"><table><tr><td class="c"><span class="chip s-na">${esc(d.report.notDone)}</span></td><td>${esc(d.report.factoryNotDone)}</td></tr></table></div>`;
      continue;
    }
    body += `<p class="mut small">${esc(d.results.sectionNotes[id])}${x.seal_date ? ` ${esc(d.results.sealDate(formatSealDate(x.seal_date)))}.` : ""}</p>`;
    body += `<div class="card"><table>${rowsHtml(x)}</table></div>`;
  }

  body += `<h2>${esc(d.report.manualTitle)}</h2>`;
  for (const g of GROUPS) {
    const items = CHECKLIST.filter((c) => c.group === g.id);
    body += `<p class="t" style="margin:16px 0 6px">${esc(g.title[lang])}</p><div class="card"><table>${items.map((c) => {
      const r = s.checks[c.id] ?? "pending";
      return `<tr><td class="c"><span class="chip s-${r}">${esc(d.report.resultWord[r])}</span></td><td>${esc(c.title[lang])}</td></tr>`;
    }).join("")}</table></div>`;
  }

  body += `<h2>${esc(d.results.deviceTitle)}</h2><div class="card"><table>${deviceRows(s).map(([k, val]) => `<tr><th>${esc(k)}</th><td>${esc(val || "?")}</td></tr>`).join("")}</table></div>`;
  body += `<div class="disc"><p><b>${esc(d.report.disclaimerTitle)}.</b> ${esc(d.report.disclaimer)}</p><p>${esc(d.report.keepPrivate)}</p><p>${esc(d.report.madeWith)}</p></div>`;

  return `<!doctype html>
<html lang="${esc(lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><title>${esc(d.report.docTitle(model))}</title>
<style>${CSS}</style></head><body><main>
${body}
</main></body></html>
`;
}

export function buildTxt(s: State): string {
  const a = s.analysis!;
  const d = t();
  const lang = getLang();
  const st = (x: string) => (d.status as Record<string, string>)[x] ?? x;
  const model = localizeModel(a.device.model_name, a.device.product_type, s.lang);
  const v = d.verdicts[a.verdict.code];
  const out: string[] = [];
  const rule = (title: string) => { out.push("", title, "-".repeat(Math.min(60, title.length))); };

  out.push(d.report.docTitle(model), "=".repeat(Math.min(60, d.report.docTitle(model).length)));
  if (s.demo) out.push(`*** ${d.app.demoBadge.toUpperCase()} ***`, "");
  out.push(`${d.report.generated(formatDate(new Date(), true))}. ${d.report.readOverUsb}`, "");
  out.push(`[${st(a.verdict.status).toUpperCase()}] ${v ? msg(v.title, a.verdict.params) : a.verdict.code}`);
  if (v) out.push(msg(v.text, a.verdict.params));

  if (a.notices?.length) {
    rule(d.results.notices);
    for (const n of a.notices) out.push(`- ${d.notices[n.code] ? msg(d.notices[n.code], n.params) : n.code}`);
  }
  for (const id of ORDER) {
    const x = sec(a, id);
    rule(d.results.sections[id]);
    if (!x) { out.push(`[${d.report.notDone}] ${d.report.factoryNotDone}`); continue; }
    if (x.seal_date) out.push(`${d.results.sealDate(formatSealDate(x.seal_date))}.`);
    for (const it of x.items) {
      out.push(`[${st(it.status)}] ${itemTitle(it)}`);
      const txt = itemText(it);
      if (txt) out.push(`    ${txt}`);
      for (const [k, val] of techPairs(it.params)) out.push(`    ${k}: ${val}`);
    }
  }
  rule(d.report.manualTitle);
  for (const g of GROUPS) {
    out.push("", `${g.title[lang]}:`);
    for (const c of CHECKLIST.filter((c) => c.group === g.id)) {
      out.push(`  [${d.report.resultWord[s.checks[c.id] ?? "pending"]}] ${c.title[lang]}`);
    }
  }
  rule(d.results.deviceTitle);
  for (const [k, val] of deviceRows(s)) out.push(`${k}: ${val || "?"}`);
  rule(d.report.disclaimerTitle);
  out.push(d.report.disclaimer, "", d.report.keepPrivate, d.report.madeWith, "");
  return out.join("\r\n");
}
