// Lucide icons (lucide-static, ISC: see THIRD-PARTY-NOTICES.md), imported one file at a time so only the
// icons the app uses go into the bundle. Every icon keeps Lucide's 24px grid, stroke 2 and currentColor;
// size and color come from the CSS class of the wrapper (see `svg()` in dom.ts).
import check from "lucide-static/icons/check.svg?raw";
import triangleAlert from "lucide-static/icons/triangle-alert.svg?raw";
import circleX from "lucide-static/icons/circle-x.svg?raw";
import circleMinus from "lucide-static/icons/circle-minus.svg?raw";
import info from "lucide-static/icons/info.svg?raw";
import shield from "lucide-static/icons/shield.svg?raw";
import clock from "lucide-static/icons/clock.svg?raw";
import laptop from "lucide-static/icons/laptop.svg?raw";
import trash from "lucide-static/icons/trash-2.svg?raw";
import image from "lucide-static/icons/image.svg?raw";
import plug from "lucide-static/icons/plug.svg?raw";
import shoppingBag from "lucide-static/icons/shopping-bag.svg?raw";
import chevronRight from "lucide-static/icons/chevron-right.svg?raw";
import type { Status } from "./types";

/** Drops the license comment and marks the icon as decorative: the text next to it carries the meaning. */
function lucide(raw: string): string {
  return raw.replace(/<!--[\s\S]*?-->\s*/, "").replace("<svg", '<svg aria-hidden="true" focusable="false"');
}

export const icons = {
  check: lucide(check),
  triangleAlert: lucide(triangleAlert),
  circleX: lucide(circleX),
  circleMinus: lucide(circleMinus),
  info: lucide(info),
  /** "Your data stays here" lines (privacy, why a prerequisite is needed). */
  shield: lucide(shield),
  clock: lucide(clock),
  laptop: lucide(laptop),
  trash: lucide(trash),
  /** The screenshot the factory check leaves in Photos. */
  photo: lucide(image),
  /** "Keep it plugged in" before the touch tests. */
  plug: lucide(plug),
  /** Get the Apple Devices app from the Microsoft Store (prerequisite screen). */
  store: lucide(shoppingBag),
  /** Disclosure arrow of "how to test", rotated by CSS when open. */
  chevron: lucide(chevronRight),
};

/** One shape per situation, so color is never the only signal (same set as the Icons section of the showcase). */
const STATUS_ICON: Record<Status, string> = {
  ok: icons.check,
  warn: icons.triangleAlert,
  alert: icons.circleX,
  na: icons.circleMinus,
};

export function statusIcon(status: string): string {
  return STATUS_ICON[status as Status] ?? icons.circleMinus;
}

/** Icon for a one-line result note (export done, delete failed...). */
export function noteIcon(kind: "ok" | "err" | "info"): string {
  return kind === "ok" ? icons.check : kind === "err" ? icons.circleX : icons.info;
}
