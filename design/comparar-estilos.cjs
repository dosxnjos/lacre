// comparar-estilos.cjs: prova de "nenhuma mudança visível" para refatoração de CSS/tokens.
// Modo 1 (gravar):   node design/comparar-estilos.cjs gravar <pasta-dist> <saida.json>
// Modo 2 (comparar): node design/comparar-estilos.cjs comparar <antes.json> <depois.json>   (código 1 se houver diferença)
// Grava, para cada elemento do app em 5 estados (procurando, achou, resultado, testes, fábrica) e nos dois temas
// (claro e escuro), o estilo CALCULADO de cor, fundo, bordas, sombra, fill, stroke e contorno. Usa o modo exemplo do app.
// Uso típico: construir o dist ANTES da mudança e copiar para uma pasta, mudar, construir de novo, gravar os dois, comparar.
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');
const CANDIDATOS = ['playwright-core', 'playwright', process.env.PLAYWRIGHT_CORE].filter(Boolean);
const pw = () => { for (const c of CANDIDATOS) { try { return require(c); } catch {} } throw new Error('playwright-core não encontrado'); };
const MIME = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json' };

async function gravar(distArg, saida) {
  const dist = path.resolve(distArg);
  const srv = http.createServer((q, r) => {
    const u = decodeURIComponent(q.url.split('?')[0]);
    const p = path.join(dist, u === '/' ? 'index.html' : u);
    if (!p.startsWith(dist) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { r.writeHead(404); r.end(); return; }
    r.writeHead(200, { 'content-type': MIME[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(r);
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const b = await pw().chromium.launch();
  const res = {};
  for (const esq of ['light', 'dark']) {
    const ctx = await b.newContext({ locale: 'pt-BR', viewport: { width: 1180, height: 900 }, colorScheme: esq, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    const dump = async (id) => {
      res[esq + ':' + id] = await page.evaluate(() => {
        const o = []; let i = 0;
        const props = ['color', 'backgroundColor', 'borderTopColor', 'borderBottomColor', 'boxShadow', 'fill', 'stroke', 'outlineColor'];
        for (const el of document.querySelectorAll('#app *')) {
          const s = getComputedStyle(el);
          o.push((el.tagName + '.' + (el.getAttribute('class') || '') + '#' + (i++)).slice(0, 80) + '|' + props.map((p) => s[p]).join('|'));
        }
        return o;
      });
    };
    await page.goto('http://127.0.0.1:' + srv.address().port + '/?mock=default');
    await page.waitForSelector('.searching'); await dump('procurando');
    await page.waitForSelector('.found .device'); await dump('achou');
    await page.click('.found .btn-primary'); await page.waitForSelector('.verdict'); await page.waitForTimeout(1500); await dump('resultado');
    await page.click('[data-fk="tab-tests"]'); await page.waitForSelector('.checks');
    await page.click('.checks .check:nth-child(1) .seg-pass'); await page.click('.checks .check:nth-child(2) .seg-fail'); await page.click('.checks .check:nth-child(3) .seg-skip'); await dump('testes');
    await page.click('[data-fk="tab-factory"]'); await page.waitForSelector('.howto'); await dump('fabrica');
    await ctx.close();
  }
  await b.close(); srv.close();
  fs.writeFileSync(saida, JSON.stringify(res));
  console.log('gravado', saida, Object.entries(res).map(([k, v]) => k + ':' + v.length).join(' '));
}

function comparar(a, d) {
  const A = JSON.parse(fs.readFileSync(a, 'utf8')), D = JSON.parse(fs.readFileSync(d, 'utf8'));
  let total = 0, dif = 0;
  for (const k of Object.keys(A)) {
    if (!D[k] || A[k].length !== D[k].length) { console.log('TAMANHO DIFERENTE', k); dif++; continue; }
    A[k].forEach((l, i) => { total++; if (l !== D[k][i]) { dif++; if (dif <= 8) console.log('DIF', k, l, '=>', D[k][i]); } });
  }
  console.log(`elementos x estados comparados: ${total}, diferenças: ${dif}`);
  process.exit(dif ? 1 : 0);
}

const [modo, x, y] = process.argv.slice(2);
if (modo === 'gravar') gravar(x, y).catch((e) => { console.error(e.message); process.exit(2); });
else if (modo === 'comparar') comparar(x, y);
else { console.error('Uso: gravar <dist> <saida.json> | comparar <antes.json> <depois.json>'); process.exit(2); }
