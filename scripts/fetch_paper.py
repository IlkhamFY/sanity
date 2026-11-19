"""Fetch a paper from the public arXiv API into runs/<slug>/source/.

    python3 scripts/fetch_paper.py 2410.11128v1
    python3 scripts/fetch_paper.py 10.1140/epjc/s10052-025-14303-w

Only export.arxiv.org is requested: the Atom API, the PDF, and the e-print.
A DOI is resolved with the same API. If arXiv has no record, the command stops.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
EXPORT = "https://export.arxiv.org"
ATOM = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
USER_AGENT = "sanity-fetch/1.0 (mailto:ilkhamfy@gmail.com)"
NS = {"a": ATOM, "x": ARXIV_NS}

# The live index files the Kerr run under this one section (site/public/data/papers.json).
# astro-ph and gr-qc both use it.
ASTRO_GR = "Astrophysics / General relativity"


class FetchError(RuntimeError):
    """The id could not be fetched from the arXiv export host."""


def subject_for_category(category: str | None) -> str:
    """Map an arXiv primary category to the section the site already uses."""
    cat = (category or "").strip()
    if cat.startswith("astro-ph") or cat == "gr-qc" or cat.startswith("gr-qc."):
        return ASTRO_GR
    if cat in {"physics.chem-ph", "chem-ph"} or cat.startswith("chem-") or cat.startswith("chem."):
        return "Chemistry"
    if cat == "math" or cat.startswith("math."):
        return "Mathematics"
    if cat == "quant-ph" or cat.startswith("quant-ph."):
        return "Quantum physics"
    if cat.startswith("cond-mat"):
        return "Condensed matter"
    return "Physics"


def classify(meta: dict) -> tuple[str, bool]:
    """Return (subject, example). No arXiv id and no DOI means an example."""
    if meta.get("arxiv_id") or meta.get("doi"):
        return subject_for_category(meta.get("primary_category")), False
    return "Examples", True


_ARXIV = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?", re.I)
_DOI = re.compile(r"(10\.\d{4,9}/[^\s?#]+)", re.I)


def parse_spec(spec: str) -> tuple[str, str, str | None]:
    """Return ('arxiv', id, version or None) or ('doi', doi, None)."""
    text = spec.strip()
    doi_in_arxiv = re.search(r"arxiv\.(\d{4}\.\d{4,5})(v\d+)?", text, re.I)
    if doi_in_arxiv and "10.48550" in text.lower():
        return "arxiv", doi_in_arxiv.group(1), doi_in_arxiv.group(2)
    looks_arxiv = bool(re.search(r"arxiv", text, re.I)) or bool(
        re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", text, re.I)
    )
    if looks_arxiv:
        match = _ARXIV.search(text)
        if not match:
            raise FetchError(f"not an arXiv id: {spec}")
        version = match.group(2)
        return "arxiv", match.group(1), version.lower() if version else None
    match = _DOI.search(text)
    if match:
        return "doi", match.group(1).rstrip("."), None
    raise FetchError(f"not an arXiv id or DOI: {spec}")


def api_url(kind: str, ident: str, version: str | None) -> str:
    if kind == "arxiv":
        return f"{EXPORT}/api/query?id_list={ident}{version or ''}"
    return f"{EXPORT}/api/query?search_query=doi:{quote(ident, safe='')}"


def pdf_url(arxiv_id: str, version: str | None) -> str:
    return f"{EXPORT}/pdf/{arxiv_id}{version or ''}"


def src_url(arxiv_id: str, version: str | None) -> str:
    return f"{EXPORT}/src/{arxiv_id}{version or ''}"


def slug_for(arxiv_id: str) -> str:
    return "arxiv-" + arxiv_id.replace(".", "-")


def _collapse(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_entry(payload: bytes) -> dict:
    """One Atom entry from the export API. Raises FetchError if there is none."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise FetchError(f"arXiv API did not return Atom: {exc}") from None
    total = root.findtext("opensearch:totalResults", default="", namespaces={
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    })
    entry = root.find("a:entry", NS)
    if entry is None or (total.strip() == "0"):
        raise FetchError("arXiv has no record for that id")
    title = _collapse(entry.findtext("a:title", default="", namespaces=NS))
    if title.lower().startswith("error"):
        raise FetchError("arXiv has no record for that id")
    abstract = _collapse(entry.findtext("a:summary", default="", namespaces=NS))
    authors = [
        _collapse(name.text)
        for name in entry.findall("a:author/a:name", NS)
        if name.text and _collapse(name.text)
    ]
    raw_id = entry.findtext("a:id", default="", namespaces=NS) or ""
    match = _ARXIV.search(raw_id)
    if not match:
        raise FetchError(f"arXiv entry has no id: {raw_id}")
    primary = entry.find("x:primary_category", NS)
    category = primary.get("term") if primary is not None and primary.get("term") else None
    if not category:
        cat = entry.find("a:category", NS)
        category = cat.get("term") if cat is not None else None
    doi = _collapse(entry.findtext("x:doi", default="", namespaces=NS)) or None
    journal = _collapse(entry.findtext("x:journal_ref", default="", namespaces=NS)) or None
    version = match.group(2)
    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "arxiv_id": match.group(1),
        "version": version.lower() if version else None,
        "primary_category": category,
        "doi": doi,
        "journal_ref": journal,
    }


def build_meta(entry: dict, fetched_at: str) -> dict:
    subject, example = classify(entry)
    return {
        "title": entry["title"],
        "authors": entry["authors"],
        "abstract": entry["abstract"],
        "arxiv_id": entry["arxiv_id"],
        "version": entry["version"],
        "primary_category": entry["primary_category"],
        "doi": entry["doi"],
        "journal_ref": entry["journal_ref"],
        "fetched_at": fetched_at,
        "slug": slug_for(entry["arxiv_id"]),
        "subject": subject,
        "example": example,
    }


def _request(url: str) -> Request:
    return Request(url, headers={"User-Agent": USER_AGENT})


def _read(url: str, opener) -> tuple[int, bytes]:
    if opener is not None:
        return opener(url)
    try:
        with urlopen(_request(url), timeout=60) as response:
            return getattr(response, "status", 200), response.read()
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            return 404, b""
        raise FetchError(f"{url}: {exc}") from None


def render_preview_png(pdf_path: Path, dest: Path) -> None:
    """Crop page 1 to the title, authors, and abstract. pymupdf, else pdftoppm."""
    try:
        import pymupdf
    except ImportError:
        pymupdf = None
    if pymupdf is not None:
        from paper_preview import preview_clip

        document = pymupdf.open(pdf_path)
        try:
            page = document[0]
            clip = preview_clip(page)
            if clip.width < 8:
                raise FetchError("preview clip is empty")
            zoom = 1200 / clip.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(dest))
            return
        finally:
            document.close()
    _preview_with_poppler(pdf_path, dest)


def _preview_with_poppler(pdf_path: Path, dest: Path) -> None:
    import shutil
    import subprocess

    if not shutil.which("pdftoppm"):
        raise FetchError("install pymupdf or poppler (pdftoppm) to render the preview")
    dest.parent.mkdir(parents=True, exist_ok=True)
    prefix = dest.with_suffix("")
    subprocess.run(
        ["pdftoppm", "-f", "1", "-l", "1", "-png", "-r", "144", "-y", "0", "-H", "700", str(pdf_path), str(prefix)],
        check=True,
    )
    rendered = prefix.with_name(prefix.name + "-1.png")
    if not rendered.is_file():
        raise FetchError("pdftoppm did not write a preview")
    rendered.replace(dest)


def fetch_paper(spec: str, repo: Path, *, opener=None, now: datetime | None = None) -> Path:
    """Download into runs/<slug>/source/ and return that directory."""
    kind, ident, version = parse_spec(spec)
    status, payload = _read(api_url(kind, ident, version), opener)
    if status != 200 or not payload:
        raise FetchError(f"arXiv API returned {status}")
    entry = parse_entry(payload)
    if version and kind == "arxiv":
        entry["version"] = version
    when = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    fetched_at = when.isoformat().replace("+00:00", "Z")
    meta = build_meta(entry, fetched_at)
    import jsonschema

    schema = json.loads((REPO / "docs" / "schemas" / "meta.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(meta, schema)
    dest = repo / "runs" / meta["slug"] / "source"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pdf_status, pdf = _read(pdf_url(meta["arxiv_id"], meta["version"]), opener)
    if pdf_status != 200 or not pdf.startswith(b"%PDF"):
        raise FetchError("arXiv did not return a PDF")
    (dest / "paper.pdf").write_bytes(pdf)
    try:
        render_preview_png(dest / "paper.pdf", dest / "preview.png")
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"preview failed: {exc}") from None
    src_status, src = _read(src_url(meta["arxiv_id"], meta["version"]), opener)
    if src_status == 200 and src.startswith(b"\x1f\x8b"):
        (dest / "source.tar.gz").write_bytes(src)
    elif src_status == 200 and src.lstrip().startswith((b"\\", b"%")):
        (dest / "source.tex").write_bytes(src)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch an arXiv paper or a DOI into runs/<slug>/source/.")
    parser.add_argument("spec", help="arXiv id (2410.11128 or 2410.11128v1) or a DOI")
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    try:
        dest = fetch_paper(args.spec, args.repo)
    except FetchError as exc:
        print(str(exc))
        return 1
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
