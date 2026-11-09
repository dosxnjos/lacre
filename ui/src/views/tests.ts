import { h, svg } from "../dom";
import { t } from "../i18n";
import { icons } from "../art";
import { CHECKLIST, GROUPS, TOUCH_TEST_URL, type CheckItem } from "../checklist";
import { qrSvg } from "../qr";
import type { Ctx, State } from "../state";
import type { CheckResult, Lang } from "../types";

/** Which how-to panels are open; survives re-renders (e.g. a language switch). */
const openItems = new Set<string>(CHECKLIST.filter((c) => c.key).map((c) => c.id));

export function checkStats(s: State): { done: number; failed: number; total: number } {
  let done = 0, failed = 0;
  for (const c of CHECKLIST) {
    const r = s.checks[c.id];
    if (r) done++;
    if (r === "fail") failed++;
  }
  return { done, failed, total: CHECKLIST.length };
}

function progressNode(s: State): HTMLElement {
  const st = checkStats(s);
  const pct = Math.round((100 * st.done) / st.total);
  return h("div", { class: "tests-progress", id: "tests-progress" },
    h("p", { class: "tabular", role: "status", "aria-live": "polite" }, t().tests.progress(st.done, st.total, st.failed)),
    h("div", { class: "bar", "aria-hidden": "true" }, h("span", { style: `width:${pct}%` })),
  );
}

function qrCard(): HTMLElement {
  const d = t().tests;
  const holder = h("div", { class: "qr-code", "aria-hidden": "true" });
  qrSvg(TOUCH_TEST_URL).then((markup) => { holder.innerHTML = markup; }).catch(() => { holder.remove(); });
  return h("aside", { class: "qr-card", "aria-labelledby": "qr-title" },
    holder,
    h("div", { class: "qr-body" },
      h("h3", { id: "qr-title", class: "qr-title" }, d.qrTitle),
      h("p", null, d.qrText),
      h("p", { class: "mono small qr-url" }, TOUCH_TEST_URL),
      h("p", { class: "muted small" }, d.qrNoPage),
    ),
  );
}

function wallCallout(): HTMLElement {
  const d = t().tests;
  return h("div", { class: "callout callout-wall" },
    svg(icons.plug, "fact-icon"),
    h("div", null, h("p", { class: "callout-title" }, d.wallTitle), h("p", null, d.wallText)),
  );
}

function segButtons(item: CheckItem, lang: Lang, r: CheckResult | undefined, act: Ctx["act"]): HTMLElement {
  const d = t().tests;
  const opts: [CheckResult, string][] = [["pass", d.pass], ["fail", d.fail], ["skip", d.skip]];
  return h("div", { class: "seg", role: "group", "aria-label": item.title[lang] },
    opts.map(([val, label]) => h("button", {
      type: "button",
      class: `seg-btn seg-${val}`,
      "data-val": val,
      "aria-pressed": String(r === val),
      // setCheck toggles: clicking the active answer clears it.
      onclick: (() => act.setCheck(item.id, val)) as EventListener,
    }, label)),
  );
}

function checkRow(item: CheckItem, s: State, act: Ctx["act"]): HTMLElement {
  const lang = s.lang;
  const r = s.checks[item.id];
  const det = h("details", { class: "check-how", open: openItems.has(item.id) },
    h("summary", null,
      h("span", { class: "check-title" }, item.title[lang]),
      svg(icons.chevron, "check-chevron")),
    h("ol", { class: "how" }, item.how.map((step) => h("li", null, step[lang]))),
  );
  det.addEventListener("toggle", () => { if (det.open) openItems.add(item.id); else openItems.delete(item.id); });
  return h("li", { class: `check${r ? ` is-${r}` : ""}${item.key ? " is-key" : ""}`, id: `check-${item.id}` },
    det,
    segButtons(item, lang, r, act),
  );
}

/** Updates one checklist row and the progress line in place (keeps focus and scroll). */
export function patchCheck(s: State, id: string): void {
  const row = document.getElementById(`check-${id}`);
  if (row) {
    const r = s.checks[id];
    row.classList.remove("is-pass", "is-fail", "is-skip");
    if (r) row.classList.add(`is-${r}`);
    row.querySelectorAll<HTMLButtonElement>(".seg-btn").forEach((b) => {
      const val = b.dataset.val as CheckResult;
      b.setAttribute("aria-pressed", String(r === val));
    });
  }
  const old = document.getElementById("tests-progress");
  if (old) old.replaceWith(progressNode(s));
}

export function testsView({ s, act }: Ctx): HTMLElement {
  const d = t().tests;
  const lang = s.lang;
  return h("div", { class: "tests" },
    h("header", { class: "page-head" },
      h("h1", { class: "title" }, d.title),
      h("p", { class: "lead" }, d.lead),
      progressNode(s)),
    GROUPS.map((g) => {
      const items = CHECKLIST.filter((c) => c.group === g.id);
      return h("section", { class: "block check-group", "aria-labelledby": `grp-${g.id}` },
        h("h2", { id: `grp-${g.id}`, class: "block-title" }, g.title[lang]),
        g.note ? h("p", { class: "block-note" }, g.note[lang]) : null,
        g.id === "screen" ? h("div", { class: "touch-aids" }, wallCallout(), qrCard()) : null,
        h("ul", { class: "list checks" }, items.map((it) => checkRow(it, s, act))),
      );
    }),
  );
}
