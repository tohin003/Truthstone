"""Leave the checkout the way it looks after a local build and a coverage run.

Runs in the repository after the initial commit. Everything created here is untracked and
matched by the project's .gitignore: build/, dist/, src/datapipe.egg-info/, .coverage and
htmlcov/. Output is deterministic (fixed timestamps, no randomness).
"""

from __future__ import annotations

import gzip
import io
import sqlite3
import tarfile
import zipfile
from pathlib import Path

VERSION = "0.3.0"
ZIP_STAMP = (2026, 10, 19, 16, 42, 10)
EPOCH = 1792428130  # 2026-10-19T16:42:10Z

root = Path.cwd()
package = root / "src" / "datapipe"
sources = {path.name: path.read_bytes() for path in sorted(package.glob("*.py"))}

metadata = (
    "Metadata-Version: 2.1\n"
    "Name: datapipe\n"
    f"Version: {VERSION}\n"
    "Summary: Load order exports (CSV) into a SQLite database for reporting.\n"
    "Requires-Python: >=3.11\n"
    "Description-Content-Type: text/markdown\n"
    "\n"
).encode() + (root / "README.md").read_bytes()


def write(rel: str, data: bytes | str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)


# -- build/: what `python -m build` / setuptools leaves behind ------------------------
for name, data in sources.items():
    write(f"build/lib/datapipe/{name}", data)

# -- src/datapipe.egg-info/ -----------------------------------------------------------
write("src/datapipe.egg-info/PKG-INFO", metadata)
write(
    "src/datapipe.egg-info/SOURCES.txt",
    "README.md\npyproject.toml\n"
    + "".join(f"src/datapipe/{name}\n" for name in sources)
    + "".join(
        f"src/datapipe.egg-info/{n}\n"
        for n in ("PKG-INFO", "SOURCES.txt", "dependency_links.txt", "top_level.txt")
    )
    + "tests/test_db.py\ntests/test_pipeline.py\ntests/test_readers.py\ntests/test_transforms.py\n",
)
write("src/datapipe.egg-info/dependency_links.txt", "\n")
write("src/datapipe.egg-info/top_level.txt", "datapipe\n")

# -- dist/: a wheel and an sdist --------------------------------------------------------
dist_info = f"datapipe-{VERSION}.dist-info"
wheel_files = {f"datapipe/{name}": data for name, data in sources.items()}
wheel_files[f"{dist_info}/METADATA"] = metadata
wheel_files[f"{dist_info}/WHEEL"] = (
    b"Wheel-Version: 1.0\nGenerator: setuptools (75.1.0)\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n"
)
wheel_files[f"{dist_info}/top_level.txt"] = b"datapipe\n"
wheel_files[f"{dist_info}/RECORD"] = "".join(f"{name},,\n" for name in wheel_files).encode() + (
    f"{dist_info}/RECORD,,\n".encode()
)
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as wheel:
    for name, data in wheel_files.items():
        info = zipfile.ZipInfo(name, date_time=ZIP_STAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        wheel.writestr(info, data)
write(f"dist/datapipe-{VERSION}-py3-none-any.whl", buffer.getvalue())

sdist_members = {
    "PKG-INFO": metadata,
    "README.md": (root / "README.md").read_bytes(),
    "pyproject.toml": (root / "pyproject.toml").read_bytes(),
    **{f"src/datapipe/{name}": data for name, data in sources.items()},
}
raw = io.BytesIO()
with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
    for name, data in sdist_members.items():
        info = tarfile.TarInfo(f"datapipe-{VERSION}/{name}")
        info.size = len(data)
        info.mtime = EPOCH
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
packed = io.BytesIO()
with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=EPOCH) as gz:
    gz.write(raw.getvalue())
write(f"dist/datapipe-{VERSION}.tar.gz", packed.getvalue())

# -- .coverage: coverage.py's SQLite data file ---------------------------------------
coverage = sqlite3.connect(root / ".coverage")
coverage.executescript(
    """
    CREATE TABLE coverage_schema (version integer);
    CREATE TABLE meta (key text, value text, unique (key));
    CREATE TABLE file (id integer primary key, path text, unique (path));
    CREATE TABLE context (id integer primary key, context text, unique (context));
    CREATE TABLE line_bits (file_id integer, context_id integer, numbits blob,
                            unique (file_id, context_id));
    INSERT INTO coverage_schema VALUES (7);
    INSERT INTO meta VALUES ('version', '7.6.1'), ('has_arcs', '0');
    INSERT INTO context VALUES (1, '');
    """
)
for index, name in enumerate(sources, start=1):
    coverage.execute("INSERT INTO file VALUES (?, ?)", (index, f"{root.name}/src/datapipe/{name}"))
    coverage.execute("INSERT INTO line_bits VALUES (?, 1, ?)", (index, bytes([0xFF] * (8 + index))))
coverage.commit()
coverage.close()

# -- htmlcov/: the HTML report ---------------------------------------------------------
rows = "".join(
    f'<tr class="region"><td class="name left"><a href="z_5f1c0a9e_{name[:-3]}_py.html">'
    f"src/datapipe/{name}</a></td><td>{20 + 7 * i}</td><td>{i % 3}</td><td>{100 - 2 * (i % 3)}%</td></tr>\n"
    for i, name in enumerate(sources)
)
write(
    "htmlcov/index.html",
    "<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"><title>Coverage report</title>"
    '<link rel="stylesheet" href="style.css" type="text/css"></head>\n<body>\n'
    "<h1>Coverage report: 97%</h1>\n<table class=\"index\">\n"
    "<tr><th>Module</th><th>statements</th><th>missing</th><th>coverage</th></tr>\n"
    f"{rows}</table>\n<p>created at 2026-10-19 16:42 +0000</p>\n</body>\n</html>\n",
)
for name in sources:
    stem = name[:-3]
    write(
        f"htmlcov/z_5f1c0a9e_{stem}_py.html",
        f"<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>Coverage for src/datapipe/{name}</title>"
        '<link rel="stylesheet" href="style.css" type="text/css"></head>\n<body>\n'
        f"<h1>Coverage for <b>src/datapipe/{name}</b></h1>\n</body></html>\n",
    )
write("htmlcov/style.css", "body { font-family: sans-serif; }\n.index td { padding: 0 1em; }\n")
write("htmlcov/status.json", '{"note":"This file is an internal implementation detail of coverage.py.","format":5}\n')
write("htmlcov/.gitignore", "# Created by coverage.py\n*\n")
