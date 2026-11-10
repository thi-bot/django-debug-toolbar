"""Build the in-browser (WebAssembly) demo of the example project.

Usage, from the repository root (requires uv):

    python example/wasm/build.py [--serve [PORT]]

The output in example/wasm/build/ is a static site, which can be hosted
anywhere that serves static files.
"""

import argparse
import functools
import hashlib
import http.server
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WASM_DIR = ROOT / "example" / "wasm"
SITE_DIR = WASM_DIR / "site"
OUTPUT_DIR = WASM_DIR / "build"

# Must match the Python version of the Pyodide release used in sw.js, so the
# precompiled bytecode is valid there.
PYTHON_VERSION = "3.14"

# Files of the example project that aren't needed in the browser.
EXAMPLE_EXCLUDE_DIRS = {"__pycache__", "build", "site"}
EXAMPLE_EXCLUDE_SUFFIXES = {".db", ".sqlite3", ".png"}
EXAMPLE_EXCLUDE_FILES = {"build.py", "screenshot.py"}


def build_wheel(out_dir: Path) -> Path:
    """Build a django-debug-toolbar wheel from the working tree."""
    subprocess.run(["uv", "build", "--wheel", "--out-dir", out_dir, ROOT], check=True)
    return next(out_dir.glob("django_debug_toolbar-*.whl"))


def install_packages(wheel: Path, target: Path):
    """Install the toolbar and its dependencies (Django…) into ``target``."""
    subprocess.run(
        ["uv", "pip", "install", "--quiet", "--target", target]
        + ["--python-version", PYTHON_VERSION, "--only-binary", ":all:", wheel],
        check=True,
    )
    # Not needed at runtime, and large.
    shutil.rmtree(target / "bin", ignore_errors=True)
    shutil.rmtree(target / "django" / "contrib" / "gis")
    for po_file in target.rglob("*.po"):
        po_file.unlink()


def copy_example_project(target: Path):
    for file in sorted((ROOT / "example").rglob("*")):
        relative = file.relative_to(ROOT)
        if (
            file.is_dir()
            or EXAMPLE_EXCLUDE_DIRS.intersection(relative.parts)
            or file.suffix in EXAMPLE_EXCLUDE_SUFFIXES
            or file.name in EXAMPLE_EXCLUDE_FILES
        ):
            continue
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(file, target / relative)


def compile_bytecode(target: Path):
    """Precompile, as compiling Django's modules takes seconds in Pyodide.

    Hash-based .pyc files that are never checked against the sources, as
    file timestamps aren't preserved when unpacking the archive.
    """
    subprocess.run(
        ["uv", "run", "--no-project", "--python", PYTHON_VERSION]
        + ["python", "-m", "compileall", "-q", "-j0"]
        + ["--invalidation-mode", "unchecked-hash", target],
        check=True,
    )


def zip_directory(source: Path, path: Path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(source.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(source))


def build():
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wheel = build_wheel(tmp / "dist")
        app_dir = tmp / "app"
        install_packages(wheel, app_dir)
        copy_example_project(app_dir)
        compile_bytecode(app_dir)
        bundle = tmp / "app.zip"
        zip_directory(app_dir, bundle)

        digest = hashlib.sha256()
        for file in (bundle, SITE_DIR / "sw.js"):
            digest.update(file.read_bytes())
        build_id = digest.hexdigest()[:12]

        # Versioned directory, so browsers never use stale cached files.
        assets_dir = OUTPUT_DIR / "_wasm" / build_id
        assets_dir.mkdir(parents=True)
        shutil.copy(bundle, assets_dir)

    (assets_dir / "manifest.json").write_text(json.dumps({"app": bundle.name}))
    shutil.copy(SITE_DIR / "index.html", OUTPUT_DIR)
    service_worker = (SITE_DIR / "sw.js").read_text()
    (OUTPUT_DIR / "sw.js").write_text(service_worker.replace("__BUILD_ID__", build_id))
    size = (assets_dir / bundle.name).stat().st_size / 1e6
    print(
        f"Built the demo in {OUTPUT_DIR.relative_to(ROOT)} "
        f"(build {build_id}, {bundle.name}: {size:.1f} MB)"
    )


def serve(port: int):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=OUTPUT_DIR
    )
    with http.server.ThreadingHTTPServer(("localhost", port), handler) as server:
        print(f"Serving the demo at http://localhost:{port}/")
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--serve",
        nargs="?",
        type=int,
        const=8000,
        metavar="PORT",
        help="serve the demo locally after building it (default port: 8000)",
    )
    args = parser.parse_args()
    if not shutil.which("uv"):
        parser.error("uv is required: https://docs.astral.sh/uv/")
    build()
    if args.serve:
        try:
            serve(args.serve)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
