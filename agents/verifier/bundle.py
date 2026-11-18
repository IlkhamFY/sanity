"""Pack a finished run into an evidence bundle, and check a received one.

    python bundle.py build  --dir ATTEMPT_DIR [--out PATH]
    python bundle.py verify --bundle PATH [--sha256 HEX] [--extract DIR]

The bundle is the lasting record of a verification: scratch folders are
temporary, and the bundle is what goes to the Writer and stays in the group.
It is a .tar.gz of the run folder's evidence plus a manifest.json:

    equations.json, equations.v<n>.json   what the Reader sent
    conversation.jsonl                    questions and answers, if any
    verify/PLAN.md, verify/checks/**, verify/lean/**, verify/RESULTS.md, verify/verdicts.json
    manifest.json                         paper, attempt, code commit, versions, sha256 of every file

``build`` refuses to pack a run whose verdicts.json was computed on a
different equations.json than the one in the folder. ``verify`` checks the
bundle's sha256 (if given), rejects unsafe paths, and compares every file with
the manifest. To re-run a bundle: check out the manifest's code commit,
extract, and run ``python agents/verifier/verify_run.py <extracted>/verify``.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import io
import json
import platform
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from verify_run import code_commit, run_identity

SKIP_PARTS = {"__pycache__", ".lake", "build", ".pytest_cache"}
SKIP_SUFFIXES = {".olean", ".ilean", ".pyc", ".tar.gz"}
REQUIRED = ("equations.json", "verify/RESULTS.md", "verify/verdicts.json")
MANIFEST = "manifest.json"


class BundleError(ValueError):
    """Raised when a run cannot be packed or a bundle does not check out."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_files(attempt_dir: Path) -> list[str]:
    """Relative POSIX paths of every file that belongs in the bundle, sorted."""
    root = Path(attempt_dir)
    chosen = []
    for name in ["equations.json", "conversation.jsonl"] + sorted(p.name for p in root.glob("equations.v*.json")):
        if (root / name).is_file():
            chosen.append(name)
    verify = root / "verify"
    if verify.is_dir():
        for path in sorted(verify.rglob("*")):
            rel = path.relative_to(root)
            if not path.is_file() or SKIP_PARTS & set(rel.parts):
                continue
            if any(path.name.endswith(suffix) for suffix in SKIP_SUFFIXES):
                continue
            chosen.append(rel.as_posix())
    return sorted(set(chosen))


def _versions() -> dict:
    try:
        import sympy
        sympy_version = sympy.__version__
    except ImportError:  # pragma: no cover - sympy is a requirement
        sympy_version = None
    return {"python": platform.python_version(), "sympy": sympy_version}


def build(attempt_dir: Path, out: Path | None = None) -> tuple[Path, str]:
    """Write the bundle and return (path, sha256)."""
    root = Path(attempt_dir)
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise BundleError(f"cannot bundle {root}: missing {', '.join(missing)} (run verify_run.py first)")
    verdicts = json.loads((root / "verify" / "verdicts.json").read_text(encoding="utf-8"))
    used = verdicts.get("inputs", {}).get("equations_sha256")
    current = sha256_bytes((root / "equations.json").read_bytes())
    if used != current:
        raise BundleError("verdicts.json was computed on a different equations.json; run verify_run.py again")
    paper, attempt = run_identity(root)
    files = evidence_files(root)
    manifest = {
        "format": 1,
        "paper": paper,
        "attempt": attempt,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "code_commit": code_commit(),
        **_versions(),
        "files": [
            {"path": rel, "sha256": sha256_bytes((root / rel).read_bytes()), "bytes": (root / rel).stat().st_size}
            for rel in files
        ],
    }
    name = f"{paper}-{attempt}.tar.gz" if attempt is not None else f"{paper}.tar.gz"
    out = Path(out) if out else root / name
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            entries = [(MANIFEST, (json.dumps(manifest, indent=2) + "\n").encode())]
            entries += [(rel, (root / rel).read_bytes()) for rel in files]
            for rel, data in entries:
                info = tarfile.TarInfo(rel)
                info.size, info.mtime, info.mode = len(data), 0, 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                tar.addfile(info, io.BytesIO(data))
    out.write_bytes(raw.getvalue())
    return out, sha256_bytes(raw.getvalue())


def verify(bundle: Path, expected_sha256: str | None = None) -> dict:
    """Check a bundle. Returns its manifest; raises BundleError on any problem."""
    data = Path(bundle).read_bytes()
    sha = sha256_bytes(data)
    if expected_sha256 and sha != expected_sha256.lower():
        raise BundleError(f"sha256 mismatch: expected {expected_sha256}, bundle is {sha}")
    try:
        tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise BundleError(f"not a readable .tar.gz: {exc}") from None
    contents = {}
    with tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile():
                raise BundleError(f"unsafe or unexpected entry in bundle: {member.name}")
            contents[member.name] = tar.extractfile(member).read()
    if MANIFEST not in contents:
        raise BundleError("bundle has no manifest.json")
    manifest = json.loads(contents.pop(MANIFEST))
    listed = {entry["path"]: entry["sha256"] for entry in manifest.get("files", [])}
    if set(listed) != set(contents):
        extra = sorted(set(contents) - set(listed))
        absent = sorted(set(listed) - set(contents))
        raise BundleError(f"files differ from manifest: extra {extra}, missing {absent}")
    for rel, digest in listed.items():
        if sha256_bytes(contents[rel]) != digest:
            raise BundleError(f"{rel}: sha256 does not match the manifest")
    for name in REQUIRED:
        if name not in contents:
            raise BundleError(f"bundle lacks {name}")
    manifest["sha256"] = sha
    return manifest


def extract(bundle: Path, dest: Path, expected_sha256: str | None = None) -> dict:
    """Verify, then unpack into ``dest`` (which must be empty or absent)."""
    manifest = verify(bundle, expected_sha256)
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise BundleError(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle, mode="r:gz") as tar:
        tar.extractall(dest, filter="data")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifier evidence bundles.")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dir", required=True, type=Path)
    b.add_argument("--out", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("--bundle", required=True, type=Path)
    v.add_argument("--sha256")
    v.add_argument("--extract", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            path, sha = build(args.dir, args.out)
            print(json.dumps({"bundle": str(path), "sha256": sha, "files": evidence_files(args.dir)}, indent=2))
        else:
            if args.extract:
                manifest = extract(args.bundle, args.extract, args.sha256)
            else:
                manifest = verify(args.bundle, args.sha256)
            print(json.dumps({"ok": True, **{k: manifest[k] for k in ("paper", "attempt", "code_commit", "sha256")},
                              "files": len(manifest["files"])}, indent=2))
    except BundleError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
