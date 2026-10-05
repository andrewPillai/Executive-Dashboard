"""Verify every payload file against FILE_MANIFEST.json using Python standard library."""
from pathlib import Path
import hashlib, json
root = Path(__file__).resolve().parent
manifest = json.loads((root / "FILE_MANIFEST.json").read_text())
errors = []
for item in manifest["files"]:
    path = root / item["path"]
    if not path.is_file():
        errors.append("Missing: " + item["path"])
    elif path.stat().st_size != item["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        errors.append("Changed: " + item["path"])
if errors:
    raise SystemExit("\n".join(errors))
print(f"Verified {len(manifest['files'])} payload files.")
