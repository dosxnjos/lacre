// Inline SVG artwork. Colors come from CSS classes (see styles.css) so light/dark both work.
import { esc } from "./dom";

/** Scalloped seal (rosette) path in a 100x100 box. */
function sealPath(bumps = 18, base = 43, outer = 49): string {
  const c = 50;
  const pt = (r: number, a: number) => `${(c + r * Math.cos(a)).toFixed(2)} ${(c + r * Math.sin(a)).toFixed(2)}`;
  let d = `M ${pt(base, -Math.PI / 2)}`;
  for (let k = 0; k < bumps; k++) {
    const a0 = -Math.PI / 2 + (2 * Math.PI * k) / bumps;
    const a1 = a0 + (2 * Math.PI) / bumps;
    d += ` Q ${pt(outer, (a0 + a1) / 2)} ${pt(base, a1)}`;
  }
  return d + " Z";
}
const SEAL = sealPath();

const GLYPH: Record<string, string> = {
  ok: '<path class="seal-glyph" d="M34 51 l11 11 l22 -24" fill="none" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>',
  warn: '<path class="seal-glyph" d="M50 30 v25" fill="none" stroke-width="7.5" stroke-linecap="round"/><circle class="seal-glyph-fill" cx="50" cy="68" r="4.6"/>',
  alert: '<path class="seal-glyph" d="M50 30 v25" fill="none" stroke-width="7.5" stroke-linecap="round"/><circle class="seal-glyph-fill" cx="50" cy="68" r="4.6"/>',
  na: '<path class="seal-glyph" d="M36 50 h28" fill="none" stroke-width="7" stroke-linecap="round"/>',
};

/** The verdict seal. `status` drives color via the .seal-<status> class. */
export function sealMark(status: string): string {
  return `<svg viewBox="0 0 100 100" class="seal seal-${status}" aria-hidden="true" focusable="false">
  <path class="seal-body" d="${SEAL}"/>
  <circle class="seal-ring" cx="50" cy="50" r="34" fill="none" stroke-width="1.6" stroke-dasharray="2.2 3.2"/>
  ${GLYPH[status] ?? GLYPH.na}
</svg>`;
}

/** Small brand mark for the header. */
export function brandMark(): string {
  return `<svg viewBox="0 0 100 100" class="brand-mark" aria-hidden="true" focusable="false">
  <path class="brand-body" d="${SEAL}"/>
  <path class="brand-glyph" d="M34 51 l11 11 l22 -24" fill="none" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;
}

/** iPhone with the "Trust This Computer?" alert and a cable. */
export function connectArt(): string {
  return `<svg viewBox="0 0 240 300" class="art art-connect" aria-hidden="true" focusable="false">
  <rect class="a-body" x="60" y="8" width="120" height="244" rx="24"/>
  <rect class="a-screen" x="68" y="16" width="104" height="228" rx="17"/>
  <rect class="a-island" x="102" y="24" width="36" height="10" rx="5"/>
  <rect class="a-dim" x="68" y="16" width="104" height="228" rx="17"/>
  <rect class="a-dialog" x="78" y="98" width="84" height="74" rx="11"/>
  <rect class="a-ink" x="92" y="110" width="56" height="6" rx="3"/>
  <rect class="a-ink2" x="86" y="122" width="68" height="4" rx="2"/>
  <rect class="a-ink2" x="96" y="130" width="48" height="4" rx="2"/>
  <line class="a-line" x1="78" y1="142" x2="162" y2="142"/>
  <line class="a-line" x1="120" y1="142" x2="120" y2="172"/>
  <rect class="a-trust" x="84" y="150" width="30" height="14" rx="7"/>
  <rect class="a-ink2" x="129" y="155" width="24" height="4" rx="2"/>
  <circle class="a-tap" cx="99" cy="157" r="12"/>
  <rect class="a-plug" x="110" y="252" width="20" height="16" rx="3"/>
  <path class="a-cable" d="M120 268 C120 284 120 290 120 300"/>
</svg>`;
}

/** Front view of an iPhone with both volume buttons and the side button pressed together. */
export function buttonsArt(labels: { volUp: string; volDown: string; side: string; together: string }): string {
  return `<svg viewBox="0 0 420 300" class="art art-buttons" role="img" aria-label="${esc(labels.together)}">
  <rect class="a-body" x="160" y="18" width="100" height="220" rx="22"/>
  <rect class="a-screen" x="167" y="25" width="86" height="206" rx="16"/>
  <rect class="a-island" x="195" y="32" width="30" height="8" rx="4"/>
  <rect class="a-flash" x="167" y="25" width="86" height="206" rx="16"/>
  <rect class="a-btn-idle" x="155" y="52" width="5" height="14" rx="2"/>
  <rect class="a-btn" x="154" y="76" width="6" height="30" rx="2.5"/>
  <rect class="a-btn" x="154" y="114" width="6" height="30" rx="2.5"/>
  <rect class="a-btn" x="260" y="86" width="6" height="46" rx="2.5"/>
  <g class="a-press">
    <path d="M124 91 h22 m-7 -6 l7 6 l-7 6"/>
    <path d="M124 129 h22 m-7 -6 l7 6 l-7 6"/>
    <path d="M296 109 h-22 m7 -6 l-7 6 l7 6"/>
  </g>
  <text class="a-label" x="118" y="95" text-anchor="end">${esc(labels.volUp)}</text>
  <text class="a-label" x="118" y="133" text-anchor="end">${esc(labels.volDown)}</text>
  <text class="a-label" x="302" y="113" text-anchor="start">${esc(labels.side)}</text>
  <text class="a-caption" x="210" y="276" text-anchor="middle">${esc(labels.together)}</text>
</svg>`;
}

// Small UI icons are Lucide and live in icons.ts; this file keeps only the app's own artwork.
