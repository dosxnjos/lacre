# CLAUDE.md: lacre

App de mesa (Tauri + motor Python) para conferir iPhone usado. Repositório **público**: nunca dado real de aparelho
(série, IMEI, UDID) em código, mock, teste ou vitrine; leitura real (`*.raw.json`) não se versiona.

- Interface: `ui/` (TypeScript + Vite). Conferir: `npm run ui:build`; motor: `uv run --project engine --python 3.12 pytest engine/tests` ([CONTRIBUTING](CONTRIBUTING.md)).
- UI: cor, sombra e fonte só por `design/tokens.css` (fonte única, lida por `@import` em `ui/src/styles.css`); cor literal nova no CSS é erro; espaço, raio e tamanho de letra ainda são px literais, não migre sem pedido ([DESIGN](design/DESIGN.md)).
- Ícone é Lucide (`lucide-static`, um arquivo por ícone em `ui/src/icons.ts`; SVG inline na vitrine), nunca emoji ([DESIGN](design/DESIGN.md)). Armadilhas: [docs/ARMADILHAS.md](docs/ARMADILHAS.md).
- Todo controle tem hover e clique com movimento curto, só dentro de `prefers-reduced-motion: no-preference` (Regra da Vida, [DESIGN](design/DESIGN.md) § Motion).
- Tela mudou: `npm run ui:build`, `node design/capturar-telas.cjs`, `node design/montar-vitrine.cjs`, e `node design/cobertura-classes.cjs design/vitrine.html` (tem de dar 100%), `node design/testar-vitrine.cjs` (clique real nos controles da vitrine) e `node design/testar-movimento.cjs` (ícones e movimento no app).
