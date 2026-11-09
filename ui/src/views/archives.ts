// Old diagnostics already on the iPhone: listed, deleted only if the user asks. Shown on the results
// tab (listed right after the quick read) and on the factory tab after a finished check. Only one tab
// is rendered at a time, so the ids and data-fk below never repeat on the page.
import { h } from "../dom";
import { formatDate, t } from "../i18n";
import type { Ctx, State } from "../state";
import type { OldArchive } from "../types";

/** Archive date "YYYY-MM-DDTHH:MM:SS" (local time, from the archive name) in the current language. */
function archiveDate(a: OldArchive): string {
  const o = t().fdr.oldArchives;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(a.date ?? "");
  if (!m) return o.undated;
  const dt = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), Number(m[6]));
  return Number.isNaN(dt.getTime()) ? o.undated : o.created(formatDate(dt, true));
}

/** The card (null when there is nothing to show), then the result note outside it: the card disappears
 *  once every old diagnostic is deleted, the note stays. */
export function oldArchivesBlock({ s, act }: Ctx): (HTMLElement | null)[] {
  return [oldArchivesCard({ s, act }), archivesNote(s)];
}

function oldArchivesCard({ s, act }: Ctx): HTMLElement | null {
  const archives = s.oldArchives ?? [];
  // Hidden during a factory check: it brings a fresher list when it ends.
  if (s.demo || !s.device || !archives.length || s.fdr.status === "running") return null;
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

function archivesNote(s: State): HTMLElement | null {
  const note = s.archives.note;
  return note ? h("p", { class: `export-note note-${note.kind}`, role: "status", tabindex: "-1", "data-fk": "archives-note" }, note.text) : null;
}
