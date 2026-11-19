"""Fetch a paper from the public arXiv API into runs/<slug>/source/.

    python3 scripts/fetch_paper.py 2410.11128v1
    python3 scripts/fetch_paper.py 10.1140/epjc/s10052-025-14303-w

The Atom API, the PDF, and the e-print come from export.arxiv.org. A 429 or 503
is retried three times, waiting 5s, then 15s, then 45s. If the API still has no
entry, an arXiv id falls back to the abs page HTML meta tags. A DOI is resolved
with the API. If arXiv has no record, the command stops. With neither pymupdf
nor pdftoppm, the preview is skipped and the publisher renders the first page later.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from html import unescape
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
RETRY_STATUS = {429, 503}
# After a 429 or 503: wait 5s, try again, wait 15s, try again, wait 45s, try once more.
BACKOFF_SECONDS = (5, 15, 45)

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
    """Return (subject, example). No arXiv id and no DOI means an example.

    The returned subject is the section the site files the row under.
    A local file may also store a content guess in meta["subject"]; that does
    not change the section. Those rows are Examples.
    """
    if meta.get("arxiv_id") or meta.get("doi"):
        return subject_for_category(meta.get("primary_category")), False
    return "Examples", True


def subject_errors(meta: dict) -> list[str]:
    """Schema-level subject and example checks shared by the guard and the publisher."""
    mapped, example = classify(meta)
    errors = []
    if bool(meta.get("example")) != example:
        errors.append(f"example is {meta.get('example')}, expected {example}")
    if not example and meta.get("subject") != mapped:
        errors.append(f"subject is {meta.get('subject')!r}, category maps to {mapped!r}")
    if example and not str(meta.get("subject") or "").strip():
        errors.append("subject is empty")
    return errors


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


_FILE_SUFFIXES = {".pdf", ".tex", ".md", ".markdown"}
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SUBJECT_KEYS = (
    (("black hole", "gravitational wave", "relativity", "astrophys"), ASTRO_GR),
    (("chemistry", "molecule", "reaction", "catalyst", "catalysis"), "Chemistry"),
    (("theorem", "lemma", "manifold", "algebra"), "Mathematics"),
    (("qubit", "quantum", "entanglement"), "Quantum physics"),
    (("condensed matter", "superconduct", "lattice"), "Condensed matter"),
    (("physics", "lagrangian", "particle"), "Physics"),
)


def is_local_spec(spec: str) -> bool:
    """A filesystem path, not an arXiv id or DOI."""
    path = Path(spec)
    if path.is_file():
        return True
    return path.suffix.lower() in _FILE_SUFFIXES


def slug_from_path(path: Path, explicit: str | None) -> str:
    if explicit:
        slug = explicit.strip().lower()
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    if not _SLUG.fullmatch(slug or ""):
        raise FetchError(f"slug must be lowercase words and hyphens: {explicit or path.stem}")
    return slug


def infer_subject(text: str) -> str:
    """A coarse section from words in the file, or unknown."""
    haystack = text.lower()
    for words, subject in _SUBJECT_KEYS:
        if any(word in haystack for word in words):
            return subject
    return "unknown"


def _brace_group(text: str, open_at: int) -> str:
    """The contents of the brace that starts at open_at, which points at '{'."""
    depth = 0
    out = []
    for char in text[open_at:]:
        if char == "{":
            depth += 1
            if depth == 1:
                continue
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
        if depth >= 1:
            out.append(char)
    return "".join(out)


def _tex_command(text: str, name: str) -> str | None:
    match = re.search(rf"\\{name}\b", text)
    if not match:
        return None
    rest = text[match.end():].lstrip()
    if not rest.startswith("{"):
        return None
    return _collapse(_brace_group(rest, 0))


def _split_authors(raw: str) -> list[str]:
    """Names exactly as written. No name is filled in."""
    text = re.sub(r"\\(?:thanks|email|inst|affiliation|address|footnote)\s*\{[^{}]*\}", " ", raw)
    text = text.replace(r"\and", "\n")
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    parts = re.split(r"\s*(?:\n|,|;|\band\b|&)\s*", text)
    names = [_collapse(part) for part in parts]
    return [name for name in names if name and name.lower() != "unknown"]


def _authors_or_unknown(names: list[str]) -> list[str]:
    return names or ["unknown"]


def parse_tex(text: str) -> dict:
    title = _tex_command(text, "title")
    author = _tex_command(text, "author")
    abstract_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.S)
    abstract = _collapse(abstract_match.group(1)) if abstract_match else ""
    return {
        "title": title,
        "authors": _authors_or_unknown(_split_authors(author or "")),
        "abstract": abstract,
    }


def parse_markdown(text: str) -> dict:
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    title = _collapse(title_match.group(1)) if title_match else None
    author_match = re.search(r"(?im)^(?:authors?|by)\s*:\s*(.+)$", text)
    authors = _authors_or_unknown(_split_authors(author_match.group(1)) if author_match else [])
    abstract_match = re.search(r"(?ims)^#{1,3}\s+abstract\s*\n+(.+?)(?:\n#{1,3}\s|\Z)", text)
    abstract = _collapse(abstract_match.group(1)) if abstract_match else ""
    return {"title": title, "authors": authors, "abstract": abstract}


def _looks_like_authors(line: str) -> bool:
    if not line or len(line) > 180 or line.endswith("."):
        return False
    if re.search(r"\b(and|&)\b|,", line) and re.search(r"[A-Za-z]", line):
        return True
    return bool(re.fullmatch(r"[A-Z][\w.'’-]+(?:\s+[A-Z][\w.'’-]+){1,4}", line))


def parse_plain_header(text: str) -> dict:
    """Title, authors, and abstract from the first page of plain text."""
    lines = [_collapse(line) for line in text.splitlines()]
    lines = [line for line in lines if line and not re.match(r"arXiv:", line, re.I)]
    title = None
    authors: list[str] = []
    body_start = 0
    for index, line in enumerate(lines):
        if line.lower() == "abstract" or line.lower().startswith("abstract "):
            body_start = index
            break
        if title is None:
            title = line
            continue
        if _looks_like_authors(line):
            authors = _split_authors(line)
            continue
        break
    abstract = ""
    for line in lines[body_start:]:
        if line.lower() in {"abstract", "introduction"}:
            continue
        if line.lower().startswith("introduction"):
            break
        abstract = _collapse(f"{abstract} {line}")
        if len(abstract) > 800:
            break
    return {"title": title, "authors": _authors_or_unknown(authors), "abstract": abstract}


def pdf_text(path: Path) -> str | None:
    """First-page text, or None when neither pymupdf nor pdftotext is installed."""
    try:
        import pymupdf
    except ImportError:
        pymupdf = None
    if pymupdf is not None:
        document = pymupdf.open(path)
        try:
            if document.page_count < 1:
                return ""
            return document[0].get_text() or ""
        finally:
            document.close()
    if not shutil.which("pdftotext"):
        return None
    import subprocess

    completed = subprocess.run(
        ["pdftotext", "-f", "1", "-l", "1", "-q", str(path), "-"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.decode("utf-8", "replace")


def _local_record(path: Path) -> tuple[dict, str]:
    suffix = path.suffix.lower()
    if suffix == ".tex":
        return parse_tex(path.read_text(encoding="utf-8", errors="replace")), path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".md", ".markdown"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return parse_markdown(text), text
    if suffix == ".pdf":
        text = pdf_text(path)
        if text is None:
            print(
                "warning: neither pymupdf nor pdftotext is installed; "
                f"title taken from the filename {path.name}",
                file=sys.stderr,
            )
            return {"title": None, "authors": ["unknown"], "abstract": ""}, ""
        return parse_plain_header(text), text
    text = path.read_text(encoding="utf-8", errors="replace")
    return parse_plain_header(text), text


def build_file_meta(path: Path, slug: str, fetched_at: str) -> dict:
    record, text = _local_record(path)
    title = record.get("title") or path.stem
    if not record.get("title"):
        print(f"warning: no title in {path.name}; using the filename", file=sys.stderr)
    return {
        "title": title,
        "authors": record["authors"],
        "abstract": record.get("abstract") or "",
        "arxiv_id": None,
        "version": None,
        "primary_category": None,
        "doi": None,
        "journal_ref": None,
        "fetched_at": fetched_at,
        "slug": slug,
        "subject": infer_subject(f"{title}\n{record.get('abstract') or ''}\n{text}"),
        "example": True,
        "source": "file",
    }


def fetch_local(path: Path, repo: Path, slug: str | None, now: datetime | None) -> Path:
    """Copy a pasted or generated file into runs/<slug>/source/. No network."""
    if not path.is_file():
        raise FetchError(f"not a file: {path}")
    slug = slug_from_path(path, slug)
    when = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    meta = build_file_meta(path, slug, when.isoformat().replace("+00:00", "Z"))
    _validate_meta(meta)
    dest = repo / "runs" / slug / "source"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest / path.name)
    (dest / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if path.suffix.lower() == ".pdf":
        try:
            wrote = render_preview_png(dest / path.name, dest / "preview.png")
        except FetchError:
            raise
        except Exception as exc:
            raise FetchError(f"preview failed: {exc}") from None
        if not wrote:
            print(
                "warning: neither pymupdf nor pdftoppm is installed; skipping preview.png. "
                "The publisher uses the arXiv first page when it publishes.",
                file=sys.stderr,
            )
    return dest


def _validate_meta(meta: dict) -> None:
    import jsonschema

    schema = json.loads((REPO / "docs" / "schemas" / "meta.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(meta, schema)


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


def _read_once(url: str, opener) -> tuple[int, bytes]:
    if opener is not None:
        return opener(url)
    try:
        with urlopen(_request(url), timeout=60) as response:
            return getattr(response, "status", 200), response.read()
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code in {404, *RETRY_STATUS}:
            return int(code), b""
        raise FetchError(f"{url}: {exc}") from None


def _read(url: str, opener, sleeper=time.sleep) -> tuple[int, bytes]:
    """GET `url`. On 429 or 503, wait 5s, 15s, and 45s, trying again after each wait."""
    status, payload = _read_once(url, opener)
    for delay in BACKOFF_SECONDS:
        if status not in RETRY_STATUS:
            return status, payload
        sleeper(delay)
        status, payload = _read_once(url, opener)
    return status, payload


def _metas(html: str, key: str) -> list[str]:
    found = []
    want = key.lower()
    for match in re.finditer(r"<meta\b([^>]*)>", html, re.I):
        attrs = {
            name.lower(): unescape(value)
            for name, _quote, value in re.findall(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", match.group(1), re.I | re.S)
        }
        label = (attrs.get("name") or attrs.get("property") or "").lower()
        if label == want and attrs.get("content"):
            text = _collapse(attrs["content"])
            if text:
                found.append(text)
    return found


def parse_abs_html(html: str, ident: str, version: str | None) -> dict:
    """Bibliographic fields from an arXiv abs page, when the API did not answer."""
    titles = _metas(html, "citation_title")
    if not titles:
        raise FetchError("arXiv abs page has no citation_title")
    raw = (_metas(html, "citation_arxiv_id") or [ident])[0]
    match = _ARXIV.search(raw)
    arxiv_id = match.group(1) if match else ident
    parsed_version = match.group(2).lower() if match and match.group(2) else None
    if version:
        parsed_version = version
    abstract = (_metas(html, "citation_abstract") or _metas(html, "og:description") or [""])[0]
    doi = (_metas(html, "citation_doi") or [None])[0]
    journal = (_metas(html, "citation_journal_ref") or [None])[0]
    category = None
    subject = re.search(r'class="primary-subject"[^>]*>[^<]*\(([a-z0-9][a-z0-9.-]*)\)', html, re.I)
    if subject:
        category = subject.group(1)
    return {
        "title": titles[0],
        "authors": _metas(html, "citation_author"),
        "abstract": abstract,
        "arxiv_id": arxiv_id,
        "version": parsed_version,
        "primary_category": category,
        "doi": doi,
        "journal_ref": journal,
    }


def abs_url(arxiv_id: str, version: str | None) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}{version or ''}"


def preview_backend() -> str | None:
    """pymupdf, else pdftoppm, else nothing."""
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        pymupdf = None
    else:
        return "pymupdf"
    if shutil.which("pdftoppm"):
        return "pdftoppm"
    return None


def render_preview_png(pdf_path: Path, dest: Path) -> bool:
    """Crop page 1 to the title, authors, and abstract. False when no renderer exists."""
    backend = preview_backend()
    if backend is None:
        return False
    if backend == "pymupdf":
        import pymupdf
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
            return True
        finally:
            document.close()
    _preview_with_poppler(pdf_path, dest)
    return True


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


def fetch_paper(spec: str, repo: Path, *, opener=None, now: datetime | None = None, sleeper=time.sleep, slug: str | None = None) -> Path:
    """Download into runs/<slug>/source/ and return that directory.

    `spec` is an arXiv id, a DOI, or a local PDF, TeX, or Markdown file.
    A local file never touches the network.
    """
    if is_local_spec(spec):
        return fetch_local(Path(spec), repo, slug, now)
    kind, ident, version = parse_spec(spec)
    status, payload = _read(api_url(kind, ident, version), opener, sleeper)
    entry = None
    if status == 200 and payload:
        try:
            entry = parse_entry(payload)
        except FetchError:
            entry = None
    if entry is None and kind == "arxiv":
        html_status, html = _read(abs_url(ident, version), opener, sleeper)
        if html_status != 200 or not html:
            raise FetchError(f"arXiv API returned {status} and the abs page returned {html_status}")
        entry = parse_abs_html(html.decode("utf-8", "replace"), ident, version)
    elif entry is None:
        raise FetchError(f"arXiv API returned {status}")
    if version and kind == "arxiv":
        entry["version"] = version
    when = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    fetched_at = when.isoformat().replace("+00:00", "Z")
    meta = build_meta(entry, fetched_at)
    _validate_meta(meta)
    dest = repo / "runs" / meta["slug"] / "source"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pdf_status, pdf = _read(pdf_url(meta["arxiv_id"], meta["version"]), opener, sleeper)
    if pdf_status != 200 or not pdf.startswith(b"%PDF"):
        raise FetchError("arXiv did not return a PDF")
    (dest / "paper.pdf").write_bytes(pdf)
    try:
        wrote_preview = render_preview_png(dest / "paper.pdf", dest / "preview.png")
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"preview failed: {exc}") from None
    if not wrote_preview:
        print(
            "warning: neither pymupdf nor pdftoppm is installed; skipping preview.png. "
            "The publisher uses the arXiv first page when it publishes.",
            file=sys.stderr,
        )
    src_status, src = _read(src_url(meta["arxiv_id"], meta["version"]), opener, sleeper)
    if src_status == 200 and src.startswith(b"\x1f\x8b"):
        (dest / "source.tar.gz").write_bytes(src)
    elif src_status == 200 and src.lstrip().startswith((b"\\", b"%")):
        (dest / "source.tex").write_bytes(src)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch an arXiv paper, a DOI, or a local file into runs/<slug>/source/.")
    parser.add_argument("spec", help="arXiv id, DOI, or a path to a PDF, .tex, or .md file")
    parser.add_argument("--slug", help="Run slug for a local file. Defaults to the filename.")
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    try:
        dest = fetch_paper(args.spec, args.repo, slug=args.slug)
    except FetchError as exc:
        print(str(exc))
        return 1
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
