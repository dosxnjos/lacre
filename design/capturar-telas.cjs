// capturar-telas.cjs: grava o DOM real do app em modo exemplo (mock do navegador, dados fictícios do próprio repo)
// em cada estado de tela, para a vitrine usar as classes e o HTML de verdade (nada desenhado à mão que possa
// divergir do app). Saída: design/quadros.json  { id: { titulo, html } }.
// Uso (da raiz do repo, depois de `npm run ui:build`):  node design/capturar-telas.cjs [pasta-do-dist]
// Chromium: o do fork da casa (C:/Dev/playwright) ou playwright-core/playwright do node_modules, se houver.
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');

const CANDIDATOS = ['playwright-core', 'playwright', 'C:/Dev/playwright/packages/playwright-core'];
function pw() { for (const c of CANDIDATOS) { try { return require(c); } catch {} } throw new Error('playwright-core não encontrado'); }

const raiz = path.resolve(__dirname, '..');
const dist = path.resolve(process.argv[2] || path.join(raiz, 'ui', 'dist'));
const MIME = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

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
  const quadros = {};
  const novaPagina = async (query) => {
    const ctx = await browser.newContext({ locale: 'pt-BR', viewport: { width: 1180, height: 900 }, colorScheme: 'light' });
    const page = await ctx.newPage();
    await page.goto(base + '?' + query);
    return { ctx, page };
  };
  const foto = async (page, id, titulo) => {
    const html = await page.evaluate(() => document.getElementById('app').innerHTML);
    quadros[id] = { titulo, html };
    console.log('quadro', id, html.length);
  };
  const espera = (page, sel, t = 20000) => page.waitForSelector(sel, { timeout: t });

  // 1. pré-requisito faltando
  { const { ctx, page } = await novaPagina('mock=nousbmux'); await espera(page, '.steps'); await foto(page, 'pre-requisito', 'Pré-requisito faltando (Apple Dispositivos)'); await ctx.close(); }
  // 2. início, procurando, achou, vários aparelhos, não confiável
  { const { ctx, page } = await novaPagina('mock=default'); await espera(page, '.starting', 3000).catch(() => {}); await foto(page, 'iniciando', 'Iniciando o motor');
    await espera(page, '.searching'); await foto(page, 'conectar-procurando', 'Conectar: procurando o aparelho');
    await espera(page, '.found .device'); await foto(page, 'conectar-achou', 'Conectar: aparelho encontrado');
    await page.click('[data-fk="tech"]').catch(() => {});
    await page.click('.found .btn-primary'); await espera(page, '.progress-steps'); await page.waitForTimeout(1500); await foto(page, 'lendo', 'Lendo o aparelho (progresso por etapa)');
    await espera(page, '.verdict'); await page.waitForTimeout(1500);
    await foto(page, 'resultado-alerta', 'Resultado: veredito vermelho, avisos, cartão de diagnósticos antigos');
    await page.click('[data-fk="restart"]'); await page.waitForTimeout(300); await foto(page, 'resultado-reiniciar', 'Resultado: "Conferir outro iPhone" avisa que os diagnósticos antigos ficam');
    await page.click('[data-fk="tech"]'); await foto(page, 'resultado-tecnico', 'Resultado com "detalhes técnicos" ligados');
    await page.click('[data-fk="tab-factory"]'); await espera(page, '.howto'); await foto(page, 'fabrica-inicio', 'Conferência de fábrica: antes de começar');
    await page.click('[data-fk="tab-tests"]'); await espera(page, '.checks');
    await foto(page, 'testes-inicio', 'Testes manuais: nenhum feito');
    const pares = await page.$$('.checks .check');
    if (pares[0]) { await pares[0].$('summary').then(s => s && s.click()); }
    const botoes = async (i, tipo) => { const b = await page.$$(`.checks .check:nth-child(${i}) .seg-${tipo}`); if (b[0]) await b[0].click(); };
    await botoes(1, 'pass'); await botoes(2, 'fail'); await botoes(3, 'skip');
    await foto(page, 'testes-marcados', 'Testes manuais: aprovado, reprovado e pulado, com o passo a passo aberto');
    await page.click('[data-fk="tab-report"]'); await espera(page, '.pane'); await foto(page, 'relatorio', 'Relatório: exportar HTML/TXT');
    await page.click('.report .actions .btn-primary'); await espera(page, '.export-note'); await foto(page, 'relatorio-exportado', 'Relatório: aviso de exportação concluída');
    await page.click('[data-fk="tab-factory"]'); await page.click('.actions.start .btn-primary');
    await espera(page, '.running'); await foto(page, 'fabrica-aguardando', 'Fábrica: esperando o aperto dos botões');
    await page.waitForTimeout(5800); await foto(page, 'fabrica-gerando', 'Fábrica: gerando e baixando');
    await page.waitForFunction(() => document.querySelector('.factory') && !document.querySelector('.running'), null, { timeout: 40000 }); await page.waitForTimeout(1200); await foto(page, 'fabrica-pronta', 'Fábrica: concluída (selo, partes, bateria)');
    await ctx.close(); }
  { const { ctx, page } = await novaPagina('mock=two'); await espera(page, '.devices [role="radio"]'); await page.click('.devices .device'); await foto(page, 'conectar-varios', 'Conectar: vários aparelhos, um selecionado'); await ctx.close(); }
  { const { ctx, page } = await novaPagina('mock=untrusted'); await page.waitForTimeout(4600); await foto(page, 'conectar-confianca', 'Conectar: falta tocar em Confiar no iPhone'); await ctx.close(); }
  // 3. veredito verde e amarelo/vermelho de fábrica
  { const { ctx, page } = await novaPagina('mock=clean'); await espera(page, '.found .device'); await page.click('.found .btn-primary'); await espera(page, '.verdict'); await page.waitForTimeout(1200); await foto(page, 'resultado-verde', 'Resultado: veredito verde'); await ctx.close(); }
  { const { ctx, page } = await novaPagina('mock=swap&speed=20'); await espera(page, '.found .device', 30000); await page.click('.found .btn-primary'); await espera(page, '.verdict'); await page.click('[data-fk="tab-factory"]'); await page.click('.actions.start .btn-primary');
    await espera(page, '.verdict-alert, .callout-alert', 40000).catch(() => {}); await page.waitForTimeout(800); await foto(page, 'fabrica-peca-trocada', 'Fábrica: peça trocada (alerta)'); await ctx.close(); }
  // 4. demonstração (selo de carimbo) e fábrica com a conexão caída
  { const { ctx, page } = await novaPagina('mock=default'); await espera(page, '[data-fk="demo"]'); await page.click('[data-fk="demo"]'); await espera(page, '.verdict'); await page.waitForTimeout(700); await foto(page, 'demonstracao', 'Demonstração (distintivo "exemplo" no topo, fábrica concluída)'); await ctx.close(); }
  { const { ctx, page } = await novaPagina('mock=reconnect'); await espera(page, '.found .device'); await page.click('.found .btn-primary'); await espera(page, '.verdict'); await page.click('[data-fk="tab-factory"]'); await page.click('.actions.start .btn-primary');
    await page.waitForSelector('.is-paused', { timeout: 30000 }); await foto(page, 'fabrica-reconectando', 'Fábrica: a conexão caiu, retomando'); await ctx.close(); }
  { const { ctx, page } = await novaPagina('mock=fdrfail&speed=20'); await espera(page, '.found .device', 30000); await page.click('.found .btn-primary'); await espera(page, '.verdict'); await page.click('[data-fk="tab-factory"]'); await page.click('.actions.start .btn-primary');
    await page.waitForSelector('.callout-alert', { timeout: 40000 }); await foto(page, 'fabrica-erro', 'Fábrica: erro, tentar de novo'); await ctx.close(); }
  // 5. apagar diagnósticos antigos: falha parcial e erro
  for (const [q, id, titulo] of [['mock=delfail&speed=20', 'apagar-falha-parcial', 'Diagnósticos antigos: um não pôde ser apagado'], ['mock=delerror&speed=20', 'apagar-erro', 'Diagnósticos antigos: falha ao apagar']]) {
    const { ctx, page } = await novaPagina(q); await espera(page, '.found .device', 30000); await page.click('.found .btn-primary'); await espera(page, '.verdict');
    await page.waitForSelector('[data-fk="delete-archives"]', { timeout: 20000 }); await page.click('[data-fk="delete-archives"]'); await page.waitForTimeout(1500); await foto(page, id, titulo); await ctx.close();
  }
  await browser.close(); srv.close();
  fs.writeFileSync(path.join(__dirname, 'quadros.json'), JSON.stringify(quadros, null, 1));
  console.log('gravado quadros.json com', Object.keys(quadros).length, 'quadros');
})().catch(e => { console.error('ERRO', e.message); process.exit(1); });
