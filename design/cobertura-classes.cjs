// cobertura-classes.cjs: "a vitrine cobre todo componente?" como NÚMERO.
// Abre a vitrine num Chromium (servida em 127.0.0.1), junta todas as classes que as folhas de estilo da
// própria página definem (inclui @media/@supports) e testa se cada uma aparece em algum elemento do DOM.
// Uso: node cobertura-classes.cjs <vitrine.html> [--ignorar <arquivo.txt>] [--json <saida.json>] [--prefixo <p>]
//   --ignorar  arquivo com uma classe por linha (# comenta) que NÃO precisa aparecer (justificar no DESIGN.md)
//   --prefixo  só conta classes que começam com isto (ex.: "nm-" no BI)
// Saída: "COBERTURA: N de M classes (X%), faltam K: ..." e código 1 se faltar alguma não ignorada.
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');

const CANDIDATOS_PW = [process.env.PLAYWRIGHT_CORE, 'playwright-core', 'playwright'].filter(Boolean);
function carregarPlaywright() {
  for (const c of CANDIDATOS_PW) { try { return require(c); } catch {} }
  throw new Error('playwright-core não encontrado');
}
const a = { arquivo: null, ignorar: null, json: null, prefixo: '' };
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  const x = argv[i];
  if (x === '--ignorar') a.ignorar = argv[++i];
  else if (x === '--json') a.json = argv[++i];
  else if (x === '--prefixo') a.prefixo = argv[++i];
  else if (x.startsWith('--')) { console.error('opção desconhecida: ' + x); process.exit(2); }
  else a.arquivo = x;
}
if (!a.arquivo) { console.error('Uso: node cobertura-classes.cjs <vitrine.html> [--ignorar f.txt] [--json s.json] [--prefixo p]'); process.exit(2); }

const MIME = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' };
(async () => {
  const arq = path.resolve(a.arquivo);
  const pasta = path.dirname(arq);
  const srv = http.createServer((req, res) => {
    const p = path.join(pasta, decodeURIComponent(req.url.split('?')[0]));
    if (!p.startsWith(pasta) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'content-type': MIME[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const { chromium } = carregarPlaywright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`http://127.0.0.1:${srv.address().port}/${encodeURIComponent(path.basename(arq))}`);
  await page.waitForTimeout(300);
  const r = await page.evaluate((prefixo) => {
    const classes = new Set();
    const visitar = (regras) => {
      for (const rg of regras) {
        if (rg.selectorText) {
          for (const m of rg.selectorText.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) classes.add(m[1]);
        }
        if (rg.cssRules) visitar(rg.cssRules);
      }
    };
    for (const f of document.styleSheets) { try { visitar(f.cssRules); } catch (e) {} }
    const lista = [...classes].filter(c => c.startsWith(prefixo)).sort();
    const presentes = [], faltam = [];
    for (const c of lista) (document.querySelector('.' + CSS.escape(c)) ? presentes : faltam).push(c);
    return { total: lista.length, presentes: presentes.length, faltam };
  }, a.prefixo);
  await browser.close();
  srv.close();
  let ign = new Set();
  if (a.ignorar) ign = new Set(fs.readFileSync(a.ignorar, 'utf8').split('\n').map(s => s.replace(/#.*/, '').trim()).filter(Boolean));
  const faltam = r.faltam.filter(c => !ign.has(c));
  const ignoradasUsadas = r.faltam.filter(c => ign.has(c));
  const pct = r.total ? ((100 * (r.total - faltam.length)) / r.total).toFixed(1) : '100';
  console.log(`ARQUIVO ${a.arquivo}`);
  console.log(`COBERTURA: ${r.total - faltam.length} de ${r.total} classes (${pct}%), faltam ${faltam.length}${faltam.length ? ': ' + faltam.join(' ') : ''}`);
  if (ign.size) console.log(`IGNORADAS (justificadas): ${ignoradasUsadas.length} de ${ign.size} listadas${ignoradasUsadas.length ? ': ' + ignoradasUsadas.join(' ') : ''}`);
  if (a.json) fs.writeFileSync(a.json, JSON.stringify({ total: r.total, faltam, ignoradas: ignoradasUsadas }, null, 2));
  process.exit(faltam.length ? 1 : 0);
})().catch(e => { console.error(e.message); process.exit(2); });
