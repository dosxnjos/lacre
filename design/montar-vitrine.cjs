// montar-vitrine.cjs: gera design/vitrine.html (standalone: tokens, CSS do app e telas capturadas embutidos).
// Uso (da raiz do repo): node design/montar-vitrine.cjs
// Entradas: design/tokens.css, ui/src/styles.css (sem a linha @import), design/quadros.json, design/vitrine.modelo.html.
// Sem dependências; sem rede. Regerar quadros.json: node design/capturar-telas.cjs (precisa de `npm run ui:build`).
'use strict';
const fs = require('fs');
const path = require('path');
const raiz = path.resolve(__dirname, '..');
const ler = (p) => fs.readFileSync(path.join(raiz, p), 'utf8');

const tokens = ler('design/tokens.css');
const appCss = ler('ui/src/styles.css').replace(/^@import\s+[^;]+;\s*$/m, '');
const quadros = JSON.parse(ler('design/quadros.json'));
let modelo = ler('design/vitrine.modelo.html');

// amostras de cor: lê os tokens do primeiro bloco :root (claro) e descreve cada um
const bloco = tokens.match(/:root\s*\{([^}]*)\}/)[1];
const cores = [...bloco.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].filter(([, n]) => !/^--(font|font-display|mono|shadow|shadow-pill)$/.test(n));
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const grade = '<h3>Cor (o valor mostrado é o do tema ativo)</h3>\n<div class="vit-grade">' + cores.map(([, n, v]) =>
  `<div class="vit-cor"><div class="vit-cor-amostra" style="background: var(${n});"></div><div class="vit-cor-nome"><code>${n}</code><span data-valor="${n}"></span></div></div>`).join('') + '</div>' +
  // o valor é lido do tema ativo em tempo de execução: o fonte da vitrine não repete nenhum hexadecimal fora do tokens.css
  '<script>for (const e of document.querySelectorAll("[data-valor]")) e.textContent = getComputedStyle(document.documentElement).getPropertyValue(e.dataset.valor).trim();<\/script>';

const telas = Object.entries(quadros).map(([id, q]) =>
  `<div class="vit-rotulo" id="q-${id}"><h3>${esc(q.titulo)}</h3><code>${id}</code></div>\n<div class="vit-moldura">${q.html}</div>`).join('\n');

// veredito nas 3 situações: o verde e o vermelho vêm das telas capturadas; o amarelo é o verde com as classes trocadas
// (o mock do app não produz veredito amarelo; a marcação é a mesma, só muda a classe de situação)
const verde = (quadros['resultado-verde'].html.match(/<section class="verdict verdict-ok[\s\S]*?<\/section>/) || [])[0];
const vermelho = (quadros['resultado-alerta'].html.match(/<section class="verdict verdict-alert[\s\S]*?<\/section>/) || [])[0];
if (!verde || !vermelho) throw new Error('veredito não encontrado nos quadros capturados');
const semId = (h) => h.replace(/ aria-labelledby="[^"]*"/g, '').replace(/ id="verdict-title"/g, '');
const amarelo = verde.replace('verdict-ok', 'verdict-warn').replace('seal-ok', 'seal-warn');
const veredito = [['verde', verde], ['amarelo (derivado)', amarelo], ['vermelho', vermelho]].map(([n, h]) => `<div class="vit-caixa"><p class="vit-nota">${n}</p>${semId(h)}</div>`).join('\n');

const trocar = (txt, marca, valor) => { if (!txt.includes(marca)) throw new Error('marca ausente no modelo: ' + marca); return txt.split(marca).join(valor); };
modelo = trocar(modelo, '/*TOKENS*/', tokens.trimEnd());
modelo = trocar(modelo, '/*APP-CSS*/', appCss.trimEnd());
modelo = trocar(modelo, '<!--TOKENS-COR-->', grade);
modelo = trocar(modelo, '<!--QUADROS-->', telas);
modelo = trocar(modelo, '<!--VEREDITOS-->', veredito);
fs.writeFileSync(path.join(raiz, 'design/vitrine.html'), modelo);
console.log(`gerado design/vitrine.html (${modelo.length} bytes, ${Object.keys(quadros).length} quadros, ${cores.length} tokens de cor)`);
