---
name: Lacre (Seal Check)
description: App de mesa para conferir um iPhone usado antes da compra; calmo, técnico por baixo, claro por cima.
colors:
  seal: "#0f5f73"
  seal-hover: "#0c5162"
  seal-tint: "#e2eff2"
  seal-ink: "#ffffff"
  bg: "#eef1f4"
  bg-deep: "#e3e8ed"
  surface: "#ffffff"
  surface-2: "#f5f7f9"
  ink: "#15202b"
  ink-2: "#47545f"
  ink-3: "#7a8793"
  line: "#dbe1e7"
  line-strong: "#c5cdd5"
  ok: "#1b7548"
  ok-bg: "#e2f2e9"
  ok-line: "#bfe0cc"
  warn: "#8f5400"
  warn-bg: "#fbf0d9"
  warn-line: "#efd6a3"
  alert: "#b0281d"
  alert-bg: "#fce7e4"
  alert-line: "#f2c3bc"
  na: "#56636f"
  na-bg: "#e9edf1"
  na-line: "#d3dae1"
  focus: "#2f8aa3"
  paper: "#ffffff"
typography:
  display:
    fontFamily: "Segoe UI Variable Display, Segoe UI, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.18
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Segoe UI Variable Display, Segoe UI, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Segoe UI Variable Display, Segoe UI, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 650
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, -apple-system, BlinkMacSystemFont, system-ui, Helvetica Neue, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 650
  mono:
    fontFamily: "ui-monospace, Cascadia Mono, SF Mono, Consolas, monospace"
    fontSize: "13px"
rounded:
  btn: "10px"
  btn-large: "12px"
  callout: "14px"
  card: "16px"
  cta: "18px"
  verdict: "22px"
  pill: "999px"
spacing:
  gap-1: "8px"
  gap-2: "12px"
  gap-3: "18px"
  gap-4: "24px"
  page-x: "24px"
components:
  button-primary:
    backgroundColor: "{colors.seal}"
    textColor: "{colors.seal-ink}"
    rounded: "{rounded.btn}"
    padding: "9px 18px"
    height: "40px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.btn}"
    padding: "9px 18px"
  chip-ok:
    backgroundColor: "{colors.ok-bg}"
    textColor: "{colors.ok}"
    rounded: "{rounded.pill}"
  chip-warn:
    backgroundColor: "{colors.warn-bg}"
    textColor: "{colors.warn}"
    rounded: "{rounded.pill}"
  chip-alert:
    backgroundColor: "{colors.alert-bg}"
    textColor: "{colors.alert}"
    rounded: "{rounded.pill}"
  verdict-ok:
    backgroundColor: "{colors.ok-bg}"
    textColor: "{colors.ok}"
    rounded: "{rounded.verdict}"
    padding: "26px 28px"
---

# Design System: Lacre (Seal Check)

> **Estado: provisório, a confirmar pelo Gabriel.** Documento gerado em 10/11/2026 a partir do código
> (`ui/src/styles.css`, antes de `design/tokens.css`) pelo fluxo `document` da skill `impeccable`, modo "scan".
> O Creative North Star e a linguagem qualitativa abaixo são **proposta** (a skill pergunta ao dono; a sessão
> que gerou não tinha com quem falar). Os valores (cor, tamanho, raio) são os do código, sem invenção.
> Os valores de cor do frontmatter valem para o tema claro; o escuro está em `design/tokens.css`, fonte única.

## Overview

**Creative North Star: "O lacre de garantia" (proposta)**

Quem usa o Lacre está diante de um iPhone usado que talvez custe caro. O app precisa soar como o selo de
garantia de uma loja séria: calmo, legível de relance e honesto sobre o que NÃO consegue provar. Por baixo
trabalha um motor técnico (Python, protocolo do iPhone); por cima, nada de jargão: um veredito grande, em
três cores, e a lista do que foi conferido.

O uso é de mesa, com a pessoa de pé ou sentada, com o iPhone no cabo: informação densa o bastante para decidir,
sem pressa. O único elemento "alto" da tela de resultado é o veredito (selo + frase); tudo o mais é contido.
A cor nunca é o único sinal: cada situação leva ícone e texto (etiqueta, selo).

**Key Characteristics:**
- Um elemento alto por tela (o veredito, ou o título da tela de passos).
- Três situações de cor (confere, atenção, problema) mais "sem dado"; a cor de ação (teal do selo) é uma só.
- Claro e escuro pelo sistema; só fontes do sistema; nenhuma requisição de rede.
- Texto de apoio sempre em linguagem de quem compra o aparelho; o dado técnico fica atrás do botão "detalhes técnicos".

## Colors

Paleta fria e neutra, com um teal profundo (o "selo") como única cor de ação, mais o semáforo de situação.

### Primary
- **Teal do selo** (`--seal`, #0f5f73 claro / #5db6c8 escuro): botão primário, selo da marca, ícones de fato, barra de progresso, número do passo.
  `--seal-hover` e `--seal-tint` acompanham (fundo de cartão de chamada).

### Neutral
- **Fundo** (`--bg` #eef1f4) e **fundo fundo** (`--bg-deep` #e3e8ed): página e trilhos (barra de progresso, seletor de idioma).
- **Superfície** (`--surface` #ffffff) e **superfície 2** (`--surface-2` #f5f7f9): cartões, listas; bloco técnico (`dl.tech`).
- **Tinta** em três graus (`--ink` #15202b, `--ink-2` #47545f, `--ink-3` #7a8793): texto, apoio, metadado. ⚠️ `--ink-3` no claro mede 3,24:1 sobre o fundo (abaixo de 4,5:1 para texto pequeno): ver Dívida.
- **Linhas** (`--line`, `--line-strong`): divisórias e contorno de botão secundário.

### Semantic
- **Confere** (`--ok` / `-bg` / `-line`), **Atenção** (`--warn` ...), **Problema** (`--alert` ...), **Sem dado** (`--na` ...): etiqueta (`chip`), veredito (`verdict-*`), selo (`seal-*`), linha de lista (`row-*`), aviso (`callout-*`).
- **Foco** (`--focus`): anel de 3 px em todo controle (`:focus-visible`).
- **Branco fixo** (`--paper`): clarão da animação dos botões e fundo do QR code (precisa de contraste para a câmera, nos dois temas).

### Named Rules
**A Regra do Semáforo Único.** Cada situação tem exatamente uma família de 3 tokens (texto, fundo, linha); nunca misturar a de uma situação com a de outra no mesmo componente.
**A Regra do Token.** Cor nova só entra em `design/tokens.css`; hexadecimal/`rgb()` no CSS do app é erro.

## Typography

**Display e título:** Segoe UI Variable Display (cai para Segoe UI, San Francisco do sistema, `system-ui`). **Texto:** Segoe UI Variable Text. **Mono:** `ui-monospace`/Cascadia/Consolas (valor técnico, série, chave).

**Character:** fonte do próprio sistema operacional: o app parece nativo em cada plataforma e não baixa fonte nenhuma.

### Hierarchy
- **Veredito** (700, 28 px, 1,18, -0,02em): a frase do selo (`.verdict-title`; 23 px abaixo de 760 px).
- **Título de tela** (650, 28 px, 1,2, -0,015em): `.title`; 24 px abaixo de 760 px.
- **Título de bloco** (650, 19 px, -0,01em): `.block-title`.
- **Corpo** (400, 15 px, 1,5): padrão da interface; `.lead` 16,5 px; linhas de lista 14 px em `--ink-2`.
- **Rótulo** (650, 12,5 px): etiqueta de situação.
- **Técnico** (mono, 13 px / 12,5 px): `.mono`, `dl.tech`.

## Layout

Casca única: barra do topo fixa de 56 px (marca, aviso de modo exemplo, idioma) e conteúdo em coluna. Na tela de resultado, dois níveis: coluna de navegação de 228 px (`sticky`, a 80 px do topo) e painel de até 780 px; abaixo de 980 px a navegação vira faixa horizontal; abaixo de 760 px o veredito encolhe e as grades de duas colunas viram uma; abaixo de 560 px as linhas empilham.
Ritmo: vãos de 8/10/12/14/18/24 px, margens de bloco de 34 px; o espaço **ainda é px literal no CSS** (não há token de espaço: ver Migração).

## Elevation & Depth

Quase plano: profundidade por **camada tonal** (fundo → superfície → superfície 2) e contorno de 1 px; sombra só em cartão de seleção (`--shadow`, dupla: contato + ambiente) e no botão "apertado" dos seletores (`--shadow-pill`). A barra do topo usa `backdrop-filter` com 82% de opacidade do fundo.

### Named Rules
**A Regra do Plano por Padrão.** Superfície em repouso é plana; sombra aparece como resposta (selecionado, apertado).

## Shapes

Cantos generosos e crescentes com o tamanho do elemento: botão 10 px (grande 12), aviso e aparelho 14, lista e cartão 16, chamada 18, veredito 22; etiqueta e seletor em pílula (999 px / 10 px). Selo do veredito: a "etiqueta de garantia" com borda ondulada (SVG próprio); o carimbo entra girando 14° em 0,5 s (some com movimento reduzido).

## Components

Botões (`.btn-primary`, `-secondary`, `-quiet`, `-large`; desativado; "armado" = confirmação em dois passos), etiqueta (`.chip-*`), veredito (`.verdict-*` + selo), aviso (`.callout-*`), cartão de chamada (`.cta`), avisos do resultado (`.notices`), bloco com título (`.block`), lista de itens (`.list`, `.row-*`, `.tech`), par chave-valor (`.kv`), navegação lateral (`.sidenav`, `.nav-item`, ponto de situação), seletor de idioma (`.lang`), seletor passou/falhou/pulou (`.seg`), barra e passos de progresso, tela de conexão (arte, procurando, aparelho achado, escolha entre vários), cartão de QR e testes na mão (`details.check-how`). A vitrine mostra todos, nos estados reais do app.

## Do's and Don'ts

### Do:
- **Do** usar `var(--token)` para toda cor; criar token novo em `design/tokens.css` se faltar.
- **Do** dar a cada estado ícone ou texto além da cor (o app já faz: etiqueta, selo).
- **Do** manter um único elemento alto por tela.
- **Do** regerar `design/quadros.json` e `design/vitrine.html` quando uma tela mudar (`design/montar-vitrine.cjs`).

### Don't:
- **Don't** usar fonte baixada, CDN ou imagem externa (o app nunca fala com a rede).
- **Don't** usar o logotipo, a fonte ou os ícones da Apple; "iPhone" só descreve o aparelho, não é nome do app.
- **Don't** pôr dado real de aparelho (série, IMEI, UDID) em exemplo, mock ou vitrine: o repositório é público.

## Cobertura da vitrine

- `design/vitrine.html`: **196 de 196 classes** de CSS do app aparecem em algum elemento (script `design/cobertura-classes.cjs`); 25 telas e estados capturados do app em modo exemplo, mais os componentes isolados.
- O veredito **amarelo** é derivado do verde (o modo exemplo do app não produz amarelo); a marcação é a mesma, muda só a classe.

## Dívida conhecida (medida na vitrine, nada corrigido)

Medido por `checar-tela.cjs` em 10/11/2026 (celular de 390 px; claro e escuro). **Não corrigido de propósito**: muda a aparência do app instalado; decisão do Gabriel.
- **Alvo de toque abaixo de 44 px:** `.seg-btn` 30 px de altura, `.lang-btn` 28, `.nav-item` 37, `.skip` 39, `.btn` 43 (a HIG pede 44).
- **Contraste abaixo de 4,5:1 em texto pequeno:** `--ink-3` no claro 3,24:1 (`.nav-meta`, `.brand-tagline`, `.nav-device-name`, `p.fine`), 3,42:1 (`dl.tech dt`), 3,67:1 (`.stage-title`, `.check-title` desativado); `dl.tech dt` no escuro 4,29:1.
- **Literais restantes:** `ui/src/qr.ts` (QR preto sobre branco: precisa do contraste máximo, de propósito) e `ui/src/report.ts` (o relatório exportado é um HTML autônomo com paleta própria embutida: não pode ler o CSS do app).

## Migração (o que falta para "tudo por token")

1. **Feito em 10/11/2026:** as cores, a sombra e as fontes moram em `design/tokens.css` (lido por `@import`); os 5 literais que sobravam no CSS viraram token (`--paper`, `--shadow-pill`); prova: 1972 pares elemento×estado com estilo calculado idêntico antes e depois, claro e escuro.
2. **Espaço, raio, tamanho de letra e duração de movimento** continuam px/s literais (centenas de ocorrências). Se virarem token, cada troca deve manter o valor exato; o ganho é consistência, o risco é visual.
3. **`report.ts`** poderia gerar a paleta do relatório a partir de `tokens.css` em tempo de build; hoje há duas cópias à mão.
