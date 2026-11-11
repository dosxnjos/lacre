// testar-vitrine.cjs: prova de que os controles de demonstração da vitrine respondem ao clique e de que a paleta
// do relatório exportado sai de design/tokens.css. Sem dependências além do Playwright (playwright-core, ou a pasta
// indicada em PLAYWRIGHT_CORE) e do esbuild (vem com o vite). Uso (da raiz, depois de montar-vitrine.cjs):
//   node design/testar-vitrine.cjs        (código 1 se algum teste falhar)
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');
const assert = require('assert');
const raiz = path.resolve(__dirname, '..');
const pw = () => { for (const c of [process.env.PLAYWRIGHT_CORE, 'playwright-core', 'playwright'].filter(Boolean)) { try { return require(c); } catch {} } throw new Error('playwright-core não encontrado'); };
let ok = 0; const falhas = [];
const teste = async (nome, fn) => { try { await fn(); ok++; console.log('ok    ' + nome); } catch (e) { falhas.push(nome); console.log('FALHA ' + nome + '\n      ' + String(e.message).split('\n').slice(0, 6).join(' / ')); } };

(async () => {
  // 1. paleta do relatório: sai dos tokens, com os mesmos valores do claro e do escuro
  const esbuild = require('esbuild');
  const rawPlugin = { name: 'raw', setup(b) {
    b.onResolve({ filter: /\?raw$/ }, (a) => ({ path: path.resolve(a.resolveDir, a.path.replace(/\?raw$/, '')), namespace: 'raw' }));
    b.onLoad({ filter: /.*/, namespace: 'raw' }, (a) => ({ contents: fs.readFileSync(a.path, 'utf8'), loader: 'text' })); } };
  const r = await esbuild.build({ entryPoints: [path.join(raiz, 'ui/src/report-palette.ts')], bundle: true, format: 'cjs', platform: 'node', write: false, plugins: [rawPlugin] });
  const m = { exports: {} }; new Function('module', 'exports', 'require', r.outputFiles[0].text)(m, m.exports, require);
  const css = m.exports.reportPalette();
  const tokens = fs.readFileSync(path.join(raiz, 'design/tokens.css'), 'utf8');
  const val = (bloco, n) => bloco.match(new RegExp('--' + n + ':\\s*([^;]+);'))[1].trim();
  const claro = tokens.match(/:root\s*\{([^}]*)\}/)[1], escuro = tokens.match(/prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^}]*)\}/)[1];
  await teste('paleta do relatório: tema claro vem dos tokens', () => {
    const c = css.split('@media')[0];
    for (const [curta, tok] of [['bg', 'bg'], ['card', 'surface'], ['tx', 'ink'], ['ok', 'ok'], ['alert-bg', 'alert-bg'], ['rule', 'line-strong']]) assert(c.includes(`--${curta}:${val(claro, tok)}`), curta);
  });
  await teste('paleta do relatório: tema escuro vem dos tokens', () => {
    const d = css.split('@media')[1];
    for (const [curta, tok] of [['bg', 'bg'], ['card', 'surface'], ['mut', 'ink-2'], ['warn', 'warn'], ['na-bg', 'na-bg']]) assert(d.includes(`--${curta}:${val(escuro, tok)}`), curta);
  });
  await teste('paleta do relatório: nenhum hexadecimal solto em report.ts', () => {
    const t = fs.readFileSync(path.join(raiz, 'ui/src/report.ts'), 'utf8');
    assert(!/#[0-9a-fA-F]{3,8}\b/.test(t), 'hexadecimal literal em report.ts');
  });

  // 2. vitrine servida por HTTP local (o Chromium do MCP bloqueia file://)
  const pasta = path.join(raiz, 'design');
  const srv = http.createServer((q, s) => {
    const p = path.join(pasta, decodeURIComponent(q.url.split('?')[0]));
    if (!p.startsWith(pasta) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { s.writeHead(404); s.end(); return; }
    s.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); fs.createReadStream(p).pipe(s);
  });
  await new Promise((res) => srv.listen(0, '127.0.0.1', res));
  const url = `http://127.0.0.1:${srv.address().port}/vitrine.html`;
  const browser = await pw().chromium.launch();
  try {
    const ctx = await browser.newContext({ viewport: { width: 1180, height: 900 }, colorScheme: 'light' });
    const page = await ctx.newPage();
    const erros = []; page.on('pageerror', (e) => erros.push(e.message)); page.on('console', (c) => { if (c.type() === 'error') erros.push(c.text()); });
    await page.goto(url);
    const cor = (sel, prop) => page.$eval(sel, (e, p) => getComputedStyle(e)[p], prop);
    const pressed = (sel) => page.$eval(sel, (e) => e.getAttribute('aria-pressed'));
    const valorBg = () => page.$eval('[data-valor="--bg"]', (e) => e.textContent);

    await teste('Tema: Escuro muda o fundo e os valores de cor mostrados', async () => {
      const antes = await cor('body', 'backgroundColor');
      assert.strictEqual(await valorBg(), val(claro, 'bg'));
      await page.click('[data-demo="tema"] [data-tema="escuro"]');
      assert.notStrictEqual(await cor('body', 'backgroundColor'), antes, 'fundo não mudou');
      assert.strictEqual(await valorBg(), val(escuro, 'bg'));
      assert.strictEqual(await pressed('[data-demo="tema"] [data-tema="escuro"]'), 'true');
      assert.strictEqual(await pressed('[data-demo="tema"] [data-tema="claro"]'), 'false');
    });
    await teste('Tema: Claro volta ao claro', async () => {
      await page.click('[data-demo="tema"] [data-tema="claro"]');
      assert.strictEqual(await valorBg(), val(claro, 'bg'));
    });
    await teste('Tema: Sistema devolve o controle ao sistema', async () => {
      await page.click('[data-demo="tema"] [data-tema="sistema"]');
      assert.strictEqual(await page.$eval('html', (e) => e.hasAttribute('data-tema')), false);
    });
    await teste('Seletor passou/falhou/pular: o clique troca o apertado', async () => {
      const primeiro = (await page.$$('#componentes .vit-caixa.vit-linha .seg'))[0];
      await (await primeiro.$('.seg-fail')).click();
      assert.strictEqual(await (await primeiro.$('.seg-fail')).getAttribute('aria-pressed'), 'true');
      assert.strictEqual(await (await primeiro.$('.seg-pass')).getAttribute('aria-pressed'), 'false');
    });
    await teste('Idioma PT/EN: o clique troca o apertado', async () => {
      await page.click('#componentes .lang-btn:nth-child(2)');
      assert.strictEqual(await pressed('#componentes .lang-btn:nth-child(2)'), 'true');
      assert.strictEqual(await pressed('#componentes .lang-btn:nth-child(1)'), 'false');
    });
    await teste('Botão discreto: o clique alterna "armado" (cor de alerta)', async () => {
      const sel = '#componentes .btn-quiet:not([disabled]):not(.is-armed)';
      const antes = await cor(sel, 'color');
      await page.click(sel);
      assert.notStrictEqual(antes, await cor('#componentes .btn-quiet.is-armed', 'color'));
    });
    await teste('Vitrine sem erro de console e sem emoji', async () => {
      assert.deepStrictEqual(erros, []);
      const emoji = await page.evaluate(() => (document.body.innerText.match(/\p{Extended_Pictographic}/gu) || []).length);
      assert.strictEqual(emoji, 0);
    });
    await ctx.close();
  } finally { await browser.close(); srv.close(); }
  console.log(`\n${ok} passaram, ${falhas.length} falharam`);
  process.exit(falhas.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
