# Contributing to Lacre

Thanks for helping buyers avoid bad used iPhones. Bug reports, translations, results from phones
with known repairs and code are all welcome.

## Ground rules

- **Read-only, always.** The engine must never call a service that writes to the iPhone (install a
  profile, erase, supervise, change settings...). The only allowed exception is deleting the
  sysdiagnose archive the engine itself requested.
- **Never commit a real device read.** Reads contain serial numbers, IMEIs, UDIDs, board and battery
  serials and the owner's device name. `.gitignore` blocks `*.raw.json`, `reports/` and
  `relatorios/`; test fixtures must be sanitized (replace every identifier with a fake value of the
  same shape) before they go into `engine/tests/fixtures/`.
- **The protocol is the contract.** The engine and the UI talk only through the JSON Lines messages
  in [docs/PROTOCOL.md](docs/PROTOCOL.md). Changing a message, an item code or a parameter means
  updating that document, the engine and the UI dictionary in the same pull request.
- **The engine emits codes, the UI writes text.** No human-readable sentence comes out of the engine.
  Every user-facing string lives in the UI dictionary, in both pt-BR and English.
- Code, comments and identifiers in English.

## Project layout

| Path | What it is |
| --- | --- |
| `engine/` | Python 3.12 engine (`pymobiledevice3==11.50.2`), frozen with PyInstaller (onedir) |
| `engine/reference_conferir.py` | the original command-line prototype (Portuguese); source of truth for the rules |
| `src-tauri/` | Tauri 2 shell in Rust: starts the engine, bridges commands and events, file dialogs |
| `ui/` | TypeScript + Vite interface, i18n, manual test checklist (`ui/src/checklist.ts`) |
| `touch-test/` | standalone touch test page opened in Safari on the phone |
| `docs/` | how it works, limitations, protocol |

## Development setup

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js 22+, Rust stable and the
[Tauri 2 prerequisites](https://v2.tauri.app/start/prerequisites/). On Windows, Apple's
**Apple Devices** app for the USB service.

```sh
npm install
npm run dev          # app with the engine run from source
```

Engine tests (no phone needed, fixtures only):

```sh
uv run --project engine --python 3.12 pytest engine/tests
```

Release build:

```sh
uv run --project engine --with pyinstaller python engine/build.py
npm run build
```

## Pull requests

1. One topic per pull request; describe what changed and how you tested it.
2. Engine changes: add or update a test with a sanitized fixture.
3. UI text: add both the pt-BR and the English string.
4. If you tested on a real phone, say which model and iOS version, never its identifiers.

## Reporting a phone with a replaced part

This is the most valuable contribution right now (see [docs/LIMITATIONS.md](docs/LIMITATIONS.md)).
Open an issue with the model, iOS version, which part was replaced and by whom (Apple, authorized
shop, third party), and the `FailureData` / `FailureProperties` section of the factory report with
every serial, IMEI and identifier replaced by `X`s of the same length.

## License

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
