import { h, svg } from "../dom";
import { formatDate, formatSealDate, msg, t } from "../i18n";
import { buttonsArt, icons } from "../art";
import type { Ctx } from "../state";
import { FDR_STAGES, progressStage, type OldArchive } from "../types";
import { button, errorBox, itemRow, list } from "./common";
import { sectionById } from "./results";

export function elapsedText(startedAt: number | null, until: number | null = null): string {
  if (!startedAt) return t().common.minutes(0, 0);
  const sec = Math.max(0, Math.floor(((until ?? Date.now()) - startedAt) / 1000));
  return t().common.minutes(Math.floor(sec / 60), sec % 60);
}

function facts(): HTMLElement {
  const f = t().fdr.facts;
  const rows: [string, string][] = [
    [icons.shield, f.what], [icons.clock, f.time], [icons.laptop, f.local], [icons.trash, f.cleanup], [icons.photo, f.photo],
  ];
  return h("ul", { class: "facts" }, rows.map(([ic, txt]) => h("li", null, svg(ic, "fact-icon"), h("span", null, txt))));
}

function howTo(action: HTMLElement | null = null): HTMLElement {
  const d = t().fdr;
  return h("div", { class: "howto" },
    h("figure", { class: "howto-art" }, svg(buttonsArt(d.illustrationLabels))),
    h("div", { class: "howto-body" },
      h("h2", { class: "block-title" }, d.howTitle),
      h("p", { class: "howto-main" }, d.howText),
      h("p", null, d.howSignal),
      h("p", { class: "muted" }, d.howWrong),
      action,
    ),
  );
}

function stageList(s: Ctx["s"]): HTMLElement {
  const d = t().fdr;
  // `reconnecting` is not a step of its own: the step it paused stays current, with a paused note.
  const stage = progressStage(s.fdr.stage, s.fdr.pausedFrom ?? null);
  const paused = s.fdr.stage === "reconnecting";
  const cur = stage ? FDR_STAGES.indexOf(stage) : -1;
  return h("ol", { class: "progress-steps stages", id: "fdr-stages" },
    FDR_STAGES.filter((x) => x !== "done").map((st, i) => {
      const done = i < cur || stage === "done";
      const now = i === cur && stage !== "done";
      return h("li", { class: done ? "is-done" : now ? `is-current${paused ? " is-paused" : ""}` : "", "aria-current": now ? "step" : null },
        h("span", { class: "ps-mark", "aria-hidden": "true" }, done ? svg(icons.check) : now ? h("span", { class: "spinner tiny" }) : null),
        h("span", { class: "stage-body" },
          h("span", { class: "stage-title" }, d.stages[st].title),
          now ? h("span", { class: "stage-text" }, paused ? d.stages.reconnecting.text : d.stages[st].text) : null),
      );
    }),
  );
}

/** Calm warning while the engine waits for the iPhone to come back (stage `reconnecting`).
 *  On other tabs it is a shorter banner with a way back to the factory tab.
 *  Not a live region itself: the factory tab's running block and the other tabs' banner slot are. */
export function lostNotice(openFactory?: () => void): HTMLElement {
  const d = t().fdr.lost;
  return h("div", { class: "callout callout-warn" },
    h("p", { class: "callout-title" }, d.title),
    h("p", null, openFactory ? d.elsewhere : d.text),
    openFactory ? h("div", { class: "actions" }, button(d.open, openFactory, "secondary", { "data-fk": "fdr-lost-open" })) : null,
  );
}

/** Archive date "YYYY-MM-DDTHH:MM:SS" (local time, from the archive name) in the current language. */
function archiveDate(a: OldArchive): string {
  const o = t().fdr.oldArchives;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(a.date ?? "");
  if (!m) return o.undated;
  const dt = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), Number(m[6]));
  return Number.isNaN(dt.getTime()) ? o.undated : o.created(formatDate(dt, true));
}

/** Diagnostics that were already on the iPhone before the check: listed, deleted only if the user asks. */
function oldArchivesCard({ s, act }: Ctx): HTMLElement | null {
  const archives = s.rawFdr?.other_archives ?? [];
  if (s.demo || !s.device || !archives.length) return null;
  const o = t().fdr.oldArchives;
  const n = archives.length;
  const busy = s.archives.busy;
  return h("section", { class: "block old-archives", "aria-labelledby": "old-archives-title" },
    h("h2", { class: "block-title", id: "old-archives-title" }, o.title(n)),
    h("p", { class: "block-note" }, o.text(n)),
    h("ul", { class: "list archive-list", "aria-label": o.listLabel },
      archives.map((a) => h("li", null,
        h("span", null, archiveDate(a)),
        s.showTech ? h("span", { class: "mono small" }, a.name) : null))),
    h("div", { class: "actions" },
      // Stays focusable while busy (aria-disabled, not disabled): the action ignores clicks meanwhile.
      h("button", {
        type: "button", class: "btn btn-secondary", "data-fk": "delete-archives",
        "aria-disabled": busy ? "true" : null, "aria-busy": busy ? "true" : null,
        onclick: act.deleteOldArchives as EventListener,
      }, busy ? o.busy : o.button(n))),
  );
}

export function factoryView({ s, act }: Ctx): HTMLElement {
  const d = t().fdr;
  const f = s.fdr;
  const head = h("header", { class: "page-head" },
    h("h1", { class: "title", id: "factory-title", tabindex: "-1" }, d.title),
    h("p", { class: "lead" }, d.lead));

  if (f.status === "running") {
    const waiting = f.stage === "waiting_trigger" || !f.stage;
    return h("div", { class: "factory" },
      head,
      h("section", { class: "block running", "aria-live": "polite" },
        h("div", { class: "running-head" },
          h("p", { class: "running-title" }, d.running),
          h("p", { class: "elapsed" }, h("span", { class: "muted" }, `${t().common.elapsed} `), h("span", { id: "fdr-elapsed", class: "tabular" }, elapsedText(f.startedAt)))),
        stageList(s),
        f.stage === "reconnecting" ? lostNotice() : null,
        h("div", { class: "actions" }, button(t().common.cancel, act.cancelFdr, "secondary", { id: "fdr-cancel" })),
      ),
      waiting ? howTo() : null,
      facts(),
    );
  }

  if (f.status === "done" && s.analysis) {
    const sec = sectionById(s.analysis, "factory");
    const note = s.archives.note;
    return h("div", { class: "factory" },
      head,
      h("section", { class: "block" },
        h("h2", { class: "block-title" }, d.doneTitle),
        h("p", { class: "block-note" }, d.doneText),
        sec?.seal_date ? h("p", { class: "block-sub" }, t().results.sealDate(formatSealDate(sec.seal_date))) : null,
        sec ? list(sec.items.map((it) => itemRow(it, s.showTech))) : null,
        h("div", { class: "actions" },
          button(t().nav.results, () => act.setTab("results"), "primary"),
          button(t().nav.tests, () => act.setTab("tests"), "secondary")),
      ),
      h("div", { class: "callout callout-info" }, svg(icons.photo, "fact-icon"), h("p", null, msg(t().notices.screenshot_left_in_photos))),
      !s.demo && s.rawFdr?.device_archive_removed === false
        ? h("div", { class: "callout callout-info", role: "status" }, svg(icons.trash, "fact-icon"), h("p", null, d.archiveLeft))
        : null,
      oldArchivesCard({ s, act }),
      // Outside the card: the card disappears once every old diagnostic is deleted, the note stays.
      note ? h("p", { class: `export-note note-${note.kind}`, role: "status", tabindex: "-1", "data-fk": "archives-note" }, note.text) : null,
      s.demo ? null : h("div", { class: "actions" }, button(d.redo, act.startFdr, "quiet", s.archives.busy ? { disabled: "" } : {})),
    );
  }

  // Failed after the buttons were pressed: the iPhone may hold the check's report (the engine deletes it
  // on its own). Not `done`: that stage is set before `analyze`, when the report is already deleted.
  const maybeLeft = f.status === "failed" && !!f.stage && f.stage !== "waiting_trigger" && f.stage !== "done";
  return h("div", { class: "factory" },
    head,
    f.status === "failed" && f.error ? errorBox(String(f.error.code), f.error.detail, s.showTech) : null,
    maybeLeft ? h("div", { class: "callout callout-info" }, h("p", null, d.cleanupLater)) : null,
    f.status === "cancelled" ? h("div", { class: "callout callout-info", role: "status" }, h("p", null, d.cancelled)) : null,
    facts(),
    howTo(h("div", { class: "actions start" }, button(f.status === "idle" ? d.start : t().common.retry, act.startFdr, "primary", { class: "btn btn-primary btn-large" }))),
  );
}
