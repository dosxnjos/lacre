import { h, svg } from "../dom";
import { t } from "../i18n";
import { icons } from "../art";
import type { Ctx } from "../state";
import { button } from "./common";
import { checkStats } from "./tests";
import { sectionById } from "./results";

export function reportView({ s, act }: Ctx): HTMLElement {
  const d = t().report;
  const st = checkStats(s);
  const hasFactory = s.analysis ? Boolean(sectionById(s.analysis, "factory")) : false;
  const note = s.exportNote;
  return h("div", { class: "report" },
    h("header", { class: "page-head" },
      h("h1", { class: "title" }, d.title),
      h("p", { class: "lead" }, d.lead)),
    h("section", { class: "block" },
      h("ul", { class: "list kv" },
        h("li", { class: "kv-row" }, h("span", { class: "kv-k" }, t().nav.factory), h("span", null, hasFactory ? t().fdr.doneTitle : d.notDone)),
        h("li", { class: "kv-row" }, h("span", { class: "kv-k" }, d.manualTitle), h("span", { class: "tabular" }, t().tests.progress(st.done, st.total, st.failed))),
      ),
      h("div", { class: "actions" },
        button(d.exportHtml, () => act.exportReport("html"), "primary"),
        button(d.exportTxt, () => act.exportReport("txt"), "secondary")),
      note ? h("p", { class: `export-note note-${note.kind}`, role: "status" }, note.text) : null,
      h("p", { class: "fine" }, svg(icons.shield, "inline-icon"), d.privacy),
    ),
  );
}
