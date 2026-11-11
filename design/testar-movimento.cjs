// testar-movimento.cjs: prova, no app real em modo exemplo (dados fictícios), de que os ícones são Lucide e de que
// os controles respondem ao ponteiro: sobem no hover, afundam no clique, ficam parados quando desativados e quando o
// sistema pede movimento reduzido. Playwright (playwright-core, ou a pasta em PLAYWRIGHT_CORE).
// Uso (da raiz, depois de `npm run ui:build`):  node design/testar-movimento.cjs [pasta-do-dist]   (código 1 se falhar)
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');
const assert = require('assert');
const raiz = path.resolve(__dirname, '..');
const dist = path.resolve(process.argv[2] || path.join(raiz, 'ui', 'dist'));
const pw = () => { for (const c of [process.env.PLAYWRIGHT_CORE, 'playwright-core', 'playwright'].filter(Boolean)) { try { return require(c); } catch {} } throw new Error('playwright-core não encontrado'); };
const MIME = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml' };
let ok = 0; const falhas = [];
const teste = async (nome, fn) => { try { await fn(); ok++; console.log('ok    ' + nome); } catch (e) { falhas.push(nome); console.log('FALHA ' + nome + '\n      ' + String(e.message).split('\n').slice(0, 4).join(' / ')); } };

// matrix(a, b, c, d, tx, ty) -> { escala, tx, ty }; "none" -> identidade
function matriz(t) {
  if (!t || t === 'none') return { escala: 1, tx: 0, ty: 0 };
  const n = t.match(/matrix\(([^)]+)\)/)[1].split(',').map(Number);
  return { escala: Math.round(n[0] * 1000) / 1000, tx: n[4], ty: n[5] };
}

(async () => {
  const srv = http.createServer((req, res) => {
    const u = decodeURIComponent(req.url.split('?')[0]);
    const p = path.join(dist, u === '/' ? 'index.html' : u);
    if (!p.startsWith(dist) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'content-type': MIME[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}/`;
  const browser = await pw().chromium.launch();
  const abrir = async (reducedMotion) => {
    const ctx = await browser.newContext({ locale: 'pt-BR', viewport: { width: 1180, height: 860 }, reducedMotion });
    const page = await ctx.newPage();
    await page.goto(base + '?mock=default');
    await page.waitForSelector('.found .btn-primary', { timeout: 30000 });
    return { ctx, page };
  };
  const transform = (page, sel) => page.$eval(sel, (el) => getComputedStyle(el).transform);
  const pausa = (page) => page.waitForTimeout(350);

  try {
    // 1. movimento permitido
    { const { ctx, page } = await abrir('no-preference');
      const sel = '.found .btn-primary';
      await teste('botão primário em repouso não tem deslocamento', async () => { assert.deepStrictEqual(matriz(await transform(page, sel)), { escala: 1, tx: 0, ty: 0 }); });
      await teste('hover no botão primário sobe 1 px', async () => { await page.hover(sel); await pausa(page); assert.strictEqual(matriz(await transform(page, sel)).ty, -1); });
      await teste('pressionar o botão primário afunda e encolhe (escala 0,98)', async () => {
        const b = await page.$(sel); const box = await b.boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down(); await pausa(page);
        const m = matriz(await transform(page, sel));
        await page.mouse.move(5, 5); await page.mouse.up();
        assert.strictEqual(m.escala, 0.98); assert(m.ty > 0, 'ty ' + m.ty);
      });
      await teste('botão desativado não se move no hover', async () => {
        await page.$eval(sel, (el) => { el.disabled = true; }); await page.hover(sel, { force: true }); await pausa(page);
        const m = matriz(await transform(page, sel)); await page.$eval(sel, (el) => { el.disabled = false; });
        assert.deepStrictEqual(m, { escala: 1, tx: 0, ty: 0 });
      });
      await page.click(sel); await page.waitForSelector('.verdict', { timeout: 30000 }); await page.waitForTimeout(800);
      await teste('item da navegação desliza 2 px no hover', async () => { const s = '[data-fk="tab-tests"]'; await page.hover(s); await pausa(page); assert.strictEqual(matriz(await transform(page, s)).tx, 2); });
      await teste('etiquetas usam o ícone Lucide da situação (nenhum ponto)', async () => {
        const r = await page.$$eval('.chip', (cs) => cs.map((c) => [c.className, c.querySelector('svg.lucide')?.getAttribute('class') || '']));
        assert(r.length > 5, 'poucas etiquetas: ' + r.length);
        const esperado = { 'chip-ok': 'lucide-check', 'chip-warn': 'lucide-triangle-alert', 'chip-alert': 'lucide-circle-x', 'chip-na': 'lucide-circle-minus' };
        for (const [cls, svg] of r) { const k = Object.keys(esperado).find((x) => cls.includes(x)); assert(k && svg.includes(esperado[k]), cls + ' -> ' + svg); }
        assert.strictEqual(await page.$$eval('.chip-dot, .nav-dot', (x) => x.length), 0);
      });
      await teste('navegação mostra o ícone do veredito, não só a cor', async () => { assert.strictEqual(await page.$$eval('.nav-status svg.lucide', (x) => x.length), 1); });
      await teste('todo svg pequeno de ícone é Lucide e decorativo (aria-hidden)', async () => {
        const r = await page.$$eval('.chip-icon svg, .nav-status svg, .callout-icon svg, .fact-icon svg, .inline-icon svg, .note-icon svg', (x) => x.map((s) => [s.classList.contains('lucide'), s.getAttribute('aria-hidden')]));
        for (const [luc, ah] of r) { assert(luc, 'svg sem classe lucide'); assert.strictEqual(ah, 'true'); }
      });
      await teste('nenhum emoji na interface', async () => { const txt = await page.$eval('#app', (el) => el.innerText); assert(!/\p{Extended_Pictographic}/u.test(txt), 'emoji encontrado'); });
      await ctx.close(); }
    // 2. movimento reduzido: cor muda, posição não
    { const { ctx, page } = await abrir('reduce');
      const sel = '.found .btn-primary';
      await teste('movimento reduzido: hover não desloca o botão', async () => { await page.hover(sel); await pausa(page); assert.deepStrictEqual(matriz(await transform(page, sel)), { escala: 1, tx: 0, ty: 0 }); });
      await teste('movimento reduzido: pressionar não desloca o botão', async () => {
        const b = await page.$(sel); const box = await b.boundingBox();
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down(); await pausa(page);
        const m = matriz(await transform(page, sel)); await page.mouse.move(5, 5); await page.mouse.up();
        assert.deepStrictEqual(m, { escala: 1, tx: 0, ty: 0 });
      });
      await ctx.close(); }
  } finally { await browser.close(); srv.close(); }
  console.log(`\n${ok} ok, ${falhas.length} falha(s)`);
  process.exit(falhas.length ? 1 : 0);
})().catch((e) => { console.error('ERRO', e.message); process.exit(1); });
