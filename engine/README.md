# lacre-engine

Python engine of Lacre: reads a USB iPhone **read-only** through the `pymobiledevice3` library and
speaks JSON Lines on stdin/stdout. Contract: [`docs/PROTOCOL.md`](../docs/PROTOCOL.md).

| file | role |
| --- | --- |
| `lacre_engine/server.py` | JSON Lines server (one asyncio loop, one task per request, cancel, shutdown) |
| `lacre_engine/collect.py` | `prereq`, `devices`, `read` (lockdown, diagnostics IORegistry, MCInstall read-only) |
| `lacre_engine/fdr.py` | `fdr`: waits for the button-triggered sysdiagnose, pulls it, keeps only the FDR plist and the battery log, deletes the archive on the device and on the PC |
| `lacre_engine/analyze.py` | `analyze`: pure rules (port of `reference_conferir.py`), codes + params only, `today` is an argument |
| `lacre_engine/errors.py` | PROTOCOL error codes and the pymobiledevice3 exception mapping |
| `reference_conferir.py` | the original prototype (source of truth for the rules; not used at runtime) |

```sh
uv run --project engine python -m lacre_engine          # start the server (dev)
uv run --project engine pytest -q                        # tests (fixtures are sanitized, no device needed)
uv run --project engine --with pyinstaller python engine/build.py   # freeze -> engine/dist/lacre-engine/
uv run --project engine python engine/build.py --smoke   # hello + devices against the frozen exe
```

Notes:
- The frozen build excludes IPython/jedi/PIL/av/setuptools (pulled in by `--collect-all pymobiledevice3`,
  never used by the engine): 72 MB instead of 241 MB, and no slow runtime hooks at start.
- pymobiledevice3 takes seconds to import from source; the server imports it on a background thread at
  start so `hello` answers at once.
- The process ends with `os._exit` after flushing: a normal interpreter shutdown crashes (0xC0000005,
  "could not acquire lock for stdin") while the stdin reader thread is blocked in `readline()`.
