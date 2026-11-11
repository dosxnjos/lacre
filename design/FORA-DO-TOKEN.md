# Fora do token (Lacre)

O que ainda não vem de `design/tokens.css`, contado em 10/11/2026 (PR de design). "Cor fora do token" = valor hexadecimal, `rgb()` ou `hsl()` em
`ui/src`, `design/vitrine.modelo.html` ou `design/montar-vitrine.cjs` (o `quadros.json` e o `vitrine.html` são gerados e não entram).

| o quê | antes | depois | onde / por quê |
| --- | --- | --- | --- |
| cor literal fora do token | **30** | **2** | sobrou `ui/src/qr.ts` (preto e branco puros: QR com contraste máximo para a câmera, de propósito). Os 28 de `ui/src/report.ts` viraram `reportPalette()` (`ui/src/report-palette.ts`), que lê `tokens.css` |
| cor literal no CSS do app (`styles.css`) | 0 | 0 | já estava limpo |
| emoji na interface (`ui/src`, `ui/index.html`, relatório exportado) | **0** | **0** | o app nunca usou emoji nem biblioteca de ícones: só arte SVG própria (selo, marca, aparelho). Nada para trocar; a regra "ícone é Lucide, nunca emoji" está no `DESIGN.md` |
| raio com valor duplicado (`99px` e `999px` para "pílula") | 2 | 1 | `.bar` passou de `99px` para `999px` (barra de 6 px de altura: mesmo desenho) |

Não migrado de propósito (o `CLAUDE.md` pede para não mexer sem pedido do mantenedor): 368 valores em `px` no `styles.css` (espaço, raio, tamanho de letra) e as
durações de movimento. Se um dia virarem token, cada troca mantém o valor exato.

Como conferir: procurar valores hexadecimais e `rgb(`/`rgba(` em `ui/src` (fora de `ui/src/mock-data`), em `design/vitrine.modelo.html` e em `design/montar-vitrine.cjs`;
deve sobrar só `qr.ts`. Emoji: script Node com a regex Unicode `\p{Extended_Pictographic}` sobre `ui/src` e `ui/index.html`.
