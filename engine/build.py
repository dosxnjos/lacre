"""Freeze the engine with PyInstaller (onedir) -> engine/dist/lacre-engine/lacre-engine(.exe).

Run from anywhere:
    uv run --project C:\\Dev\\lacre\\engine --with pyinstaller python build.py

Then smoke-test the frozen binary (hello + devices over stdin/stdout, startup time):
    uv run --project C:\\Dev\\lacre\\engine python build.py --smoke
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
WORK = HERE / "build"
NAME = "lacre-engine"
EXE = DIST / NAME / (NAME + (".exe" if sys.platform == "win32" else ""))
EXCLUDES = ("IPython", "jedi", "parso", "traitlets", "av", "PIL", "setuptools", "tkinter", "matplotlib",
            "pytest", "_pytest")


def build() -> None:
    import PyInstaller.__main__  # noqa: PLC0415  (only needed for the build)

    entry = WORK / "entry.py"
    WORK.mkdir(parents=True, exist_ok=True)
    entry.write_text("import sys\nfrom lacre_engine.server import main\nsys.exit(main())\n", encoding="utf-8")
    shutil.rmtree(DIST / NAME, ignore_errors=True)
    PyInstaller.__main__.run([
        str(entry),
        "--name", NAME,
        "--onedir",
        "--console",  # the shell starts it with CREATE_NO_WINDOW, so no window shows
        "--noconfirm",
        "--clean",
        "--log-level", "WARN",
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(WORK),
        "--paths", str(HERE),
        "--collect-all", "pymobiledevice3",
        "--collect-submodules", "lacre_engine",
        "--copy-metadata", "pymobiledevice3",
        # Interactive-shell and media stacks pulled in by --collect-all but never used by the engine's
        # read/fdr paths; dropping them cuts size and startup (their runtime hooks run at every start).
        *[arg for mod in EXCLUDES for arg in ("--exclude-module", mod)],
    ])
    if not EXE.exists():
        raise SystemExit(f"build failed: {EXE} not found")
    size = sum(p.stat().st_size for p in (DIST / NAME).rglob("*") if p.is_file())
    print(f"built {EXE} ({size / 1e6:.0f} MB in {DIST / NAME})")


def smoke(runs: int = 3) -> None:
    """Start the frozen engine, time spawn -> first `hello` answer, then ask `devices` and shut down."""
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW, like the shell
    for i in range(runs):
        t0 = time.perf_counter()
        p = subprocess.Popen([str(EXE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=flags)
        assert p.stdin and p.stdout
        p.stdin.write(b'{"v":1,"id":"h","cmd":"hello","args":{}}\n')
        p.stdin.flush()
        hello = json.loads(p.stdout.readline())
        t_hello = time.perf_counter() - t0
        if i == runs - 1:  # last run: give the background import time, as the UI's first screen would
            time.sleep(6)
        t1 = time.perf_counter()
        p.stdin.write(b'{"v":1,"id":"d","cmd":"devices","args":{}}\n')
        p.stdin.flush()
        devices = json.loads(p.stdout.readline())
        t_dev = time.perf_counter() - t1
        p.stdin.write(b'{"v":1,"id":"s","cmd":"shutdown","args":{}}\n')
        p.stdin.flush()
        bye = json.loads(p.stdout.readline())
        code = p.wait(timeout=30)
        n = len(devices.get("data") or []) if devices.get("ok") else devices.get("error")
        print(f"run {i + 1}: hello ok={hello['ok']} {hello.get('data')} in {t_hello:.2f}s; "
              f"devices ok={devices['ok']} count={n} answered {t_dev:.2f}s after sending;shutdown ok={bye['ok']} exit={code}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="only smoke-test an existing build")
    a = ap.parse_args()
    if not a.smoke:
        build()
    smoke()
