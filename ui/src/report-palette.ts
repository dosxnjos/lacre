// Paleta do relatório exportado (HTML autônomo), gerada a partir de design/tokens.css (fonte única de cor).
// O relatório não pode ler o CSS do app, então os valores são copiados para dentro dele na hora de montar.
import tokensCss from "../../design/tokens.css?raw";

/** Variável curta do relatório -> token de design/tokens.css. */
const MAP: Array<[string, string]> = [
  ["bg", "bg"], ["card", "surface"], ["tx", "ink"], ["mut", "ink-2"], ["ln", "line"], ["rule", "line-strong"], ["paper", "paper"],
  ["ok", "ok"], ["ok-bg", "ok-bg"], ["warn", "warn"], ["warn-bg", "warn-bg"],
  ["alert", "alert"], ["alert-bg", "alert-bg"], ["na", "na"], ["na-bg", "na-bg"],
];

function pairs(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

/** CSS `:root{...}` do tema claro mais o `@media (prefers-color-scheme: dark)` do escuro, com os nomes curtos do relatório. */
export function reportPalette(tokens: string = tokensCss): string {
  const light = tokens.match(/:root\s*\{([^}]*)\}/)?.[1];
  const dark = tokens.match(/prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^}]*)\}/)?.[1];
  if (!light || !dark) throw new Error("design/tokens.css: blocos :root (claro e escuro) não encontrados");
  const l = pairs(light);
  const d = { ...l, ...pairs(dark) };
  const decl = (src: Record<string, string>) =>
    MAP.map(([short, token]) => {
      if (!(token in src)) throw new Error(`design/tokens.css: token --${token} ausente`);
      return `--${short}:${src[token]}`;
    }).join(";");
  return `:root{color-scheme:light dark;${decl(l)}}\n@media (prefers-color-scheme:dark){:root{${decl(d)}}}`;
}
