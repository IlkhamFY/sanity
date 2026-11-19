"""Validate published runs. Exit 1 on the first batch of problems.

    python3 scripts/guard.py

Checks every runs/<slug> that has equations.json:

- equations.json and verdicts.json match docs/schemas
- every HOLDS or FAILS verdict names a check script that is in the run
- the summary and the catch name only equations whose verdict is FAILS
- counts in site/public/data/papers.json match those verdicts
- report.html has no external URL except Google Fonts and KaTeX
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from fetch_paper import classify
from publish_run import find_verdicts, load_json, tally

REPO = Path(__file__).resolve().parents[1]
EQUATIONS_SCHEMA = REPO / "docs" / "schemas" / "equations.schema.json"
VERDICTS_SCHEMA = REPO / "docs" / "schemas" / "verdicts.schema.json"
META_SCHEMA = REPO / "docs" / "schemas" / "meta.schema.json"

# Web-report allows Google Fonts and a KaTeX CDN. Nothing else.
_FONT_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
_KATEX_HOSTS = {"cdn.jsdelivr.net", "unpkg.com", "katex.org"}

_PAREN = re.compile(r"\((\d+(?:\.\d+)*)\)")
_EQWORD = re.compile(r"\b(?:eq|eqn|equation)\.?\s+\(?(\d+(?:\.\d+)*)\)?", re.I)
_URL = re.compile(r"(?:https?:)?//[^\s\"'<>)]+", re.I)
_HEADING = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>(.*?)(?=<h[1-3][\s>]|$)", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_SECTION = re.compile(r"summary|judgement|judgment|catch", re.I)
_ARXIV = re.compile(r"arXiv:\d{4}\.\d{4,5}", re.I)
_DOI = re.compile(r"\b10\.\d{4,9}/\S+")


def equation_names(text: str) -> set[str]:
    """Equation numbers a summary actually names, not years or counts."""
    names = {match.group(1) for match in _PAREN.finditer(text or "")}
    names.update(match.group(1) for match in _EQWORD.finditer(text or ""))
    return names


def failing_claims(verdicts: dict) -> set[str]:
    return {
        str(claim.get("claim"))
        for claim in verdicts.get("claims") or []
        if claim.get("verdict") == "FAILS" and claim.get("claim") is not None
    }


def summary_errors(text: str, fails: set[str], where: str) -> list[str]:
    bad = []
    for name in sorted(equation_names(text), key=lambda item: (len(item), item)):
        if name not in fails:
            bad.append(f"{where} names Eq. ({name}), whose verdict is not FAILS")
    return bad


def _schema_errors(data: dict, schema_path: Path, where: str) -> list[str]:
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = []
    for err in jsonschema.Draft202012Validator(schema).iter_errors(data):
        path = "/".join(str(part) for part in err.absolute_path) or "(root)"
        errors.append(f"{where} does not match {schema_path.name} at {path}: {err.message}")
    return errors


def _script_errors(run: Path, verdicts: dict) -> list[str]:
    errors = []

    def check(verdict: str, script: str | None, kind: str | None, where: str) -> None:
        if verdict not in {"HOLDS", "FAILS"}:
            return
        if not script or kind in {None, "none"}:
            errors.append(f"{where} is {verdict} without check-script evidence")
            return
        path = (run / script).resolve()
        if run.resolve() not in path.parents and path != run.resolve():
            errors.append(f"{where} script escapes the run: {script}")
            return
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"{where} check script is missing: {script}")

    for claim in verdicts.get("claims") or []:
        evidence = claim.get("evidence") or {}
        check(
            str(claim.get("verdict")),
            evidence.get("script") if isinstance(evidence, dict) else None,
            evidence.get("kind") if isinstance(evidence, dict) else None,
            f"claim {claim.get('claim')}",
        )
    for item in verdicts.get("checks") or []:
        check(str(item.get("verdict")), item.get("script"), item.get("evidence"), f"check {item.get('check_id')}")
    return errors


def report_url_errors(html: str, where: str) -> list[str]:
    errors = []
    for raw in _URL.findall(html or ""):
        url = raw if "://" in raw else "https:" + raw
        host = urlparse(url).hostname or ""
        if host in _FONT_HOSTS:
            continue
        if host in _KATEX_HOSTS and (host == "katex.org" or "katex" in url.lower()):
            continue
        errors.append(f"{where} has external URL {raw}")
    return errors


def report_section_text(html: str) -> str:
    """Summary, judgement, and catch sections. The claims list is not included."""
    parts = []
    for heading, body in _HEADING.findall(html or ""):
        label = _TAG.sub(" ", heading)
        if _SECTION.search(label):
            parts.append(_TAG.sub(" ", body))
    return "\n".join(parts)


def _has_identifier(equations: dict, paper: dict, meta: dict | None) -> bool:
    if paper.get("source_url") or paper.get("doi"):
        return True
    if meta and (meta.get("arxiv_id") or meta.get("doi")):
        return True
    source = str(equations.get("source") or "")
    return bool(_ARXIV.search(source) or _DOI.search(source))


def _paper_by_slug(papers: list[dict], slug: str) -> dict | None:
    for paper in papers:
        if paper.get("slug") == slug:
            return paper
    return None


def validate_run(run: Path, paper: dict | None, activity: list[dict]) -> list[str]:
    """Errors for one run directory. `paper` is its papers.json row, if any."""
    slug = run.name
    where = f"runs/{slug}"
    errors = []
    equations_path = run / "equations.json"
    try:
        equations = load_json(equations_path)
    except json.JSONDecodeError as exc:
        return [f"{where}/equations.json is not JSON: {exc}"]
    errors.extend(_schema_errors(equations, EQUATIONS_SCHEMA, f"{where}/equations.json"))
    if equations.get("slug") not in {None, slug}:
        errors.append(f"{where} equations slug is {equations.get('slug')}")
    verdicts_path = find_verdicts(run)
    if verdicts_path is None:
        errors.append(f"{where} has no verdicts.json")
        return errors
    try:
        verdicts = load_json(verdicts_path)
    except json.JSONDecodeError as exc:
        return errors + [f"{verdicts_path} is not JSON: {exc}"]
    errors.extend(_schema_errors(verdicts, VERDICTS_SCHEMA, f"{where}/{verdicts_path.relative_to(run).as_posix()}"))
    errors.extend(_script_errors(run, verdicts))
    fails = failing_claims(verdicts)
    meta = None
    for meta_path in (run / "meta.json", run / "source" / "meta.json"):
        if not meta_path.is_file():
            continue
        try:
            meta = load_json(meta_path)
        except json.JSONDecodeError as exc:
            errors.append(f"{meta_path} is not JSON: {exc}")
            continue
        errors.extend(_schema_errors(meta, META_SCHEMA, str(meta_path)))
        subject, example = classify(meta)
        if meta.get("subject") != subject:
            errors.append(f"{meta_path.name} subject is {meta.get('subject')!r}, category maps to {subject!r}")
        if bool(meta.get("example")) != example:
            errors.append(f"{meta_path.name} example is {meta.get('example')}, expected {example}")
        errors.extend(summary_errors(str(meta.get("summary") or ""), fails, f"{where} summary"))
        errors.extend(summary_errors(str(meta.get("catch") or ""), fails, f"{where} catch"))
    if paper is None:
        errors.append(f"papers.json has no row for {slug}")
        return errors
    counts, _segments = tally(verdicts)
    got = paper.get("counts") or {}
    if got != counts:
        errors.append(f"papers.json counts for {slug} are {got}, verdicts are {counts}")
    errors.extend(summary_errors(str(paper.get("judgement") or ""), fails, f"{slug} judgement"))
    for line in (paper.get("telegram") or {}).get("lines") or []:
        errors.extend(summary_errors(line, fails, f"{slug} telegram"))
    for event in activity:
        if event.get("slug") != slug:
            continue
        errors.extend(summary_errors(str(event.get("event") or ""), fails, f"{slug} activity"))
        errors.extend(summary_errors(str(event.get("detail") or ""), fails, f"{slug} activity"))
    if not _has_identifier(equations, paper, meta) and not paper.get("example"):
        errors.append(f"{slug} has no arXiv id or DOI and is not marked example")
    site_report = run.parents[1] / "site" / "public" / "data" / slug / "report.html"
    for report in (run / "report.html", site_report):
        if report.is_file():
            html = report.read_text(encoding="utf-8")
            errors.extend(report_url_errors(html, str(report)))
            errors.extend(summary_errors(report_section_text(html), fails, f"{report.name} summary/catch"))
    return errors


def validate_repo(repo: Path | None = None) -> list[str]:
    repo = repo or REPO
    runs = repo / "runs"
    papers_path = repo / "site" / "public" / "data" / "papers.json"
    activity_path = repo / "site" / "public" / "data" / "activity.json"
    errors = []
    if not papers_path.is_file():
        return ["site/public/data/papers.json is missing"]
    try:
        papers = load_json(papers_path).get("papers") or []
    except json.JSONDecodeError as exc:
        return [f"papers.json is not JSON: {exc}"]
    activity = []
    if activity_path.is_file():
        try:
            activity = load_json(activity_path).get("events") or []
        except json.JSONDecodeError as exc:
            errors.append(f"activity.json is not JSON: {exc}")
    seen = set()
    if not runs.is_dir():
        return errors + ["runs/ is missing"]
    for run in sorted(path for path in runs.iterdir() if path.is_dir()):
        if not (run / "equations.json").is_file():
            continue
        seen.add(run.name)
        errors.extend(validate_run(run, _paper_by_slug(papers, run.name), activity))
    for paper in papers:
        slug = paper.get("slug")
        if slug not in seen:
            errors.append(f"papers.json lists {slug}, which has no runs/{slug}/equations.json")
    return errors


def main(argv: list[str] | None = None) -> int:
    errors = validate_repo(REPO)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"{len(errors)} guard error(s)", file=sys.stderr)
        return 1
    print("guard: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
