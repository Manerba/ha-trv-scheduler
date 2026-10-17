"""Build a reproducible source-only installation ZIP and SHA-256 checksum."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/trv_scheduler"
version = json.loads((COMPONENT / "manifest.json").read_text())["version"]
destination = ROOT / "dist"
destination.mkdir(exist_ok=True)
archive = destination / f"trv-scheduler-{version}.zip"
files = [p for p in COMPONENT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
files += [ROOT / "README.md", ROOT / "docs/behavior.md"]
with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
    for path in sorted(files):
        info = ZipInfo(str(path.relative_to(ROOT)), date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        output.writestr(info, path.read_bytes())
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
print(archive)
print(digest)
