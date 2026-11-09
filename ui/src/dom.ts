// Tiny DOM helpers. All dynamic text goes through textContent (never innerHTML),
// so device names or values coming from the phone can't inject markup.

type Leaf = Node | string | number | null | undefined | false;
type Child = Leaf | Child[];
type Attrs = Record<string, string | number | boolean | null | undefined | EventListener>;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs | null = null, ...children: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v as EventListener);
      else if (k === "class") el.className = String(v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, String(v));
    }
  }
  append(el, children);
  return el;
}

export function append(el: Element, children: Child[]): void {
  for (const c of (children as unknown[]).flat(Infinity) as Leaf[]) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

/** Parses a trusted, static SVG string (illustrations shipped with the app). */
export function svg(markup: string, cls = ""): HTMLElement {
  const wrap = document.createElement("span");
  wrap.className = `svg ${cls}`.trim();
  wrap.innerHTML = markup; // trusted: built from constants; dynamic labels are escaped by esc()
  return wrap;
}

export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
