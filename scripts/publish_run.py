"""Copy a Writer run into the public index.

One command turns ``equations.json``, ``verdicts.json``, and any report into
a row on ``site/papers.html``. Running it again updates that row in place.

While a run is still open, ``--event`` appends one line to the activity feed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "site" / "public" / "data"
LOGOS = REPO / "site" / "public" / "logos"
EQUATIONS_SCHEMA = REPO / "docs" / "schemas" / "equations.schema.json"
VERDICTS_SCHEMA = REPO / "docs" / "schemas" / "verdicts.schema.json"

COUNT_KEYS = ("holds", "fails", "unchecked", "error")
VERDICT_KEY = {"HOLDS": "holds", "FAILS": "fails", "UNCHECKED": "unchecked", "ERROR": "error"}
TOOL_ORDER = ("sympy", "lean", "python")
TOOL_LOGO = {"sympy": "sympy.svg", "lean": "lean.svg", "python": "python.svg"}
TOOL_NAME = {"sympy": "SymPy", "lean": "Lean", "python": "Python"}
ROLES = ("reader", "verifier", "writer")
ATOM = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate(data: dict, schema_path: Path, name: str) -> None:
    if not schema_path.is_file():
        return
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(part) for part in exc.absolute_path) or "(root)"
        raise SystemExit(f"{name} does not match {schema_path.name} at {where}: {exc.message}")


def find_verdicts(run: Path) -> Path | None:
    for candidate in (run / "verdicts.json", run / "verify" / "verdicts.json"):
        if candidate.is_file():
            return candidate
    return None


def judgement_of(telegram: str | None, report: str | None, slug: str) -> str | None:
    """The Writer's one sentence, if the run actually has one."""
    if telegram:
        for line in telegram.splitlines():
            line = line.strip()
            if not line:
                continue
            prefix = f"{slug}:"
            if line.lower().startswith(prefix.lower()):
                line = line[len(prefix):].strip()
            return line or None
    if report:
        match = re.search(r"(?im)^judgement:\s*(.+)$", report)
        if match:
            return match.group(1).strip() or None
    return None


def source_url_of(equations: dict, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    source = str(equations.get("source") or "")
    match = re.search(r"arXiv:(\d{4}\.\d{4,5})(v\d+)?", source, re.I)
    if match:
        return f"https://arxiv.org/abs/{match.group(1)}{match.group(2) or ''}"
    if source.startswith("http://") or source.startswith("https://"):
        return source
    return None


def tally(verdicts: dict) -> tuple[dict, list[str]]:
    counts = {key: 0 for key in COUNT_KEYS}
    segments: list[str] = []
    for claim in verdicts.get("claims") or []:
        verdict = str(claim.get("verdict") or "UNCHECKED")
        if verdict not in VERDICT_KEY:
            verdict = "UNCHECKED"
        segments.append(verdict)
        counts[VERDICT_KEY[verdict]] += 1
    by_claim = {claim.get("claim"): index for index, claim in enumerate(verdicts.get("claims") or [])}
    for check in verdicts.get("checks") or []:
        if check.get("verdict") != "ERROR" or check.get("role") != "claim":
            continue
        index = by_claim.get(check.get("claim"))
        if index is None:
            counts["error"] += 1
            continue
        previous = segments[index]
        if previous != "ERROR":
            counts[VERDICT_KEY[previous]] -= 1
            counts["error"] += 1
            segments[index] = "ERROR"
    return counts, segments


def flags_of(verdicts: dict, equations: dict) -> list[dict]:
    lines = {str(item.get("number")): item.get("line") for item in equations.get("equations") or []}
    flags = []
    for claim in verdicts.get("claims") or []:
        if claim.get("verdict") != "FAILS":
            continue
        flag = {"claim": str(claim.get("claim"))}
        line = lines.get(flag["claim"])
        if isinstance(line, int):
            flag["line"] = line
        correction = claim.get("correction") or {}
        if correction.get("latex"):
            flag["correction_latex"] = correction["latex"]
        flag["corrected"] = bool(correction.get("verified"))
        flags.append(flag)
    return flags


def tools_of(verdicts: dict, logos: Path) -> list[dict]:
    found = []
    blobs = list(verdicts.get("claims") or []) + list(verdicts.get("checks") or [])
    for blob in blobs:
        evidence = blob.get("evidence")
        engine = blob.get("engine")
        if isinstance(evidence, dict):
            engine = evidence.get("engine") or engine
        if engine in TOOL_LOGO and engine not in found:
            found.append(engine)
    found.sort(key=lambda name: TOOL_ORDER.index(name) if name in TOOL_ORDER else len(TOOL_ORDER))
    tools = []
    for name in found:
        logo = TOOL_LOGO[name]
        if (logos / logo).is_file():
            tools.append({"name": TOOL_NAME[name], "logo": logo})
    return tools


def is_epjc(journal_ref: str | None, doi: str | None) -> bool:
    if doi and "10.1140/epjc/" in doi.lower():
        return True
    text = (journal_ref or "").lower()
    return any(
        needle in text
        for needle in (
            "european physical journal c",
            "european journal of physics c",
            "eur. phys. j. c",
            "epjc",
        )
    )


def marks_of(source_url: str | None, journal_ref: str | None, doi: str | None, logos: Path) -> list[dict]:
    marks = []
    if source_url and "arxiv.org" in source_url and (logos / "arxiv.svg").is_file():
        marks.append({"name": "arXiv", "logo": "arxiv.svg", "href": source_url})
    if is_epjc(journal_ref, doi) and (logos / "springer.svg").is_file():
        href = f"https://doi.org/{doi}" if doi else source_url
        marks.append({"name": "Springer", "logo": "springer.svg", "href": href})
    return marks


def telegram_lines(text: str | None) -> list[str]:
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def fetch_arxiv(source_url: str) -> dict:
    """Authors, journal-ref, and DOI from the arXiv API. Empty if the request fails."""
    match = re.search(r"(\d{4}\.\d{4,5})", source_url)
    if not match:
        return {}
    url = f"https://export.arxiv.org/api/query?id_list={match.group(1)}"
    request = urllib.request.Request(url, headers={"User-Agent": "sanity-publish/1.0 (mailto:ilkhamfy@gmail.com)"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    except OSError as exc:
        print(f"arXiv record unavailable: {exc}", file=sys.stderr)
        return {}
    root = ET.fromstring(payload)
    ns = {"a": ATOM, "x": ARXIV_NS}
    entry = root.find("a:entry", ns)
    if entry is None:
        return {}
    authors = [name.text.strip() for name in entry.findall("a:author/a:name", ns) if name.text]
    journal = (entry.findtext("x:journal_ref", default="", namespaces=ns) or "").strip()
    doi = (entry.findtext("x:doi", default="", namespaces=ns) or "").strip()
    record = {}
    if authors:
        record["authors"] = authors
    if journal:
        record["journal_ref"] = journal
    if doi:
        record["doi"] = doi
    return record


def count_phrase(counts: dict) -> str:
    parts = []
    for key, word in (("holds", "hold"), ("fails", "fails"), ("unchecked", "unchecked"), ("error", "error")):
        if counts.get(key):
            parts.append(f"{counts[key]} {word}")
    return ", ".join(parts)


def events_from_run(run: Path, slug: str, verdicts: dict | None, sentence: str | None) -> list[dict]:
    """Events that have a timestamp in the run. Nothing is backfilled."""
    events = []
    if verdicts and verdicts.get("generated_at"):
        counts, _segments = tally(verdicts)
        fails = [f"Eq. ({claim.get('claim')}) FAILS" for claim in verdicts.get("claims") or [] if claim.get("verdict") == "FAILS"]
        detail = count_phrase(counts)
        if fails:
            detail = f"{detail}. {'; '.join(fails)}" if detail else "; ".join(fails)
        event = {
            "time": verdicts["generated_at"],
            "slug": slug,
            "role": "verifier",
            "event": "recorded verdicts",
        }
        if detail:
            event["detail"] = detail
        events.append(event)
    status_path = run / "status.json"
    report_path = run / "REPORT.md"
    if status_path.is_file() and report_path.is_file():
        status = load_json(status_path)
        when = status.get("updated_at")
        if when:
            event = {
                "time": when,
                "slug": slug,
                "role": "writer",
                "event": "published the report",
            }
            if sentence:
                event["detail"] = sentence
            events.append(event)
    return events


def _entry_key(event: dict) -> tuple:
    return (event.get("time"), event.get("slug"), event.get("role"), event.get("event"))


def merge_events(path: Path, fresh: list[dict]) -> None:
    current = load_json(path) if path.is_file() else {"events": []}
    events = list(current.get("events") or [])
    seen = {_entry_key(event) for event in events}
    for event in fresh:
        if _entry_key(event) in seen:
            continue
        events.append(event)
        seen.add(_entry_key(event))
    events.sort(key=lambda event: str(event.get("time") or ""))
    write_json(path, {"events": events})


def upsert_paper(path: Path, entry: dict) -> None:
    current = load_json(path) if path.is_file() else {"papers": []}
    papers = list(current.get("papers") or [])
    for index, paper in enumerate(papers):
        if paper.get("slug") == entry["slug"]:
            papers[index] = entry
            break
    else:
        papers.append(entry)
    write_json(path, {"papers": papers})


def _local_pdf(run: Path) -> Path | None:
    found = sorted(run.glob("*.pdf"))
    return found[0] if found else None


def attach_images(entry: dict, run: Path, dest: Path, pdf_url: str | None, skip: bool) -> None:
    if skip:
        return
    from paper_preview import download, render_equation, render_preview, safe_claim

    pdf = _local_pdf(run)
    temporary = None
    if pdf is None and pdf_url:
        temporary = dest / "_source.pdf"
        try:
            download(pdf_url, temporary)
        except OSError as exc:
            print(f"PDF unavailable: {exc}", file=sys.stderr)
            temporary.unlink(missing_ok=True)
            return
        pdf = temporary
    if pdf is None:
        return
    try:
        render_preview(pdf, dest / "preview.webp")
        entry["preview"] = f"{entry['slug']}/preview.webp"
        for flag in entry.get("flags") or []:
            name = f"eq-{safe_claim(flag['claim'])}.webp"
            page = render_equation(pdf, dest / name, flag["claim"])
            if page is None:
                continue
            flag["crop"] = f"{entry['slug']}/{name}"
            flag["page"] = page
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_entry(run: Path, subject: str, title: str | None, url: str | None, example: bool, logos: Path, network: bool) -> tuple[dict, dict | None, str | None]:
    equations_path = run / "equations.json"
    if not equations_path.is_file():
        raise SystemExit(f"no equations.json in {run}")
    equations = load_json(equations_path)
    validate(equations, EQUATIONS_SCHEMA, equations_path.name)
    slug = str(equations.get("slug") or run.name)
    verdicts_path = find_verdicts(run)
    verdicts = None
    if verdicts_path is not None:
        verdicts = load_json(verdicts_path)
        validate(verdicts, VERDICTS_SCHEMA, verdicts_path.name)
    report = (run / "REPORT.md").read_text(encoding="utf-8") if (run / "REPORT.md").is_file() else None
    telegram = (run / "telegram.md").read_text(encoding="utf-8") if (run / "telegram.md").is_file() else None
    sentence = judgement_of(telegram, report, slug)
    source = source_url_of(equations, url)
    record = fetch_arxiv(source) if network and source and "arxiv.org" in source else {}
    meta_path = run / "meta.json"
    meta = load_json(meta_path) if meta_path.is_file() else {}
    entry: dict = {
        "slug": slug,
        "title": title or equations.get("title") or slug,
        "subject": subject,
        "status": "checked" if verdicts else "checking",
    }
    authors = record.get("authors") or equations.get("authors") or meta.get("authors")
    if isinstance(authors, list) and authors and all(isinstance(name, str) for name in authors):
        entry["authors"] = authors
    if source:
        entry["source_url"] = source
    journal = record.get("journal_ref") or meta.get("journal_ref")
    if journal:
        entry["journal_ref"] = journal
    doi = record.get("doi") or meta.get("doi")
    if doi:
        entry["doi"] = doi
    if example:
        entry["example"] = True
    if verdicts and verdicts.get("generated_at"):
        entry["checked_at"] = verdicts["generated_at"]
    if verdicts:
        counts, segments = tally(verdicts)
        entry["counts"] = counts
        entry["segments"] = segments
        entry["flags"] = flags_of(verdicts, equations)
        tools = tools_of(verdicts, logos)
        if tools:
            entry["tools"] = tools
    else:
        pending = len(equations.get("equations") or [])
        entry["counts"] = {key: 0 for key in COUNT_KEYS}
        entry["segments"] = ["PENDING"] * pending
    if sentence:
        entry["judgement"] = sentence
    lines = telegram_lines(telegram)
    if lines:
        entry["telegram"] = {"role": "writer", "lines": lines}
    marks = marks_of(source, entry.get("journal_ref"), entry.get("doi"), logos)
    if marks:
        entry["marks"] = marks
    return entry, verdicts, sentence


def publish(run: Path, subject: str, title: str | None, url: str | None, example: bool, data_dir: Path, logos: Path, preview: bool, network: bool) -> dict:
    if not subject:
        raise SystemExit("--subject is required")
    entry, verdicts, sentence = build_entry(run, subject, title, url, example, logos, network)
    dest = data_dir / entry["slug"]
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run / "equations.json", dest / "equations.json")
    verdicts_path = find_verdicts(run)
    if verdicts_path is not None:
        shutil.copy2(verdicts_path, dest / "verdicts.json")
    if (run / "REPORT.md").is_file():
        shutil.copy2(run / "REPORT.md", dest / "REPORT.md")
    if (run / "report.html").is_file():
        shutil.copy2(run / "report.html", dest / "report.html")
        entry["report"] = f"{entry['slug']}/report.html"
    pdf_url = None
    if entry.get("source_url"):
        from paper_preview import arxiv_pdf_url

        pdf_url = arxiv_pdf_url(entry["source_url"])
    attach_images(entry, run, dest, pdf_url, skip=not preview)
    upsert_paper(data_dir / "papers.json", entry)
    merge_events(data_dir / "activity.json", events_from_run(run, entry["slug"], verdicts, sentence))
    return entry


def record_event(data_dir: Path, slug: str, role: str, message: str, detail: str, when: str) -> dict:
    if role not in ROLES:
        raise SystemExit(f"role must be one of {', '.join(ROLES)}")
    if not slug or not message:
        raise SystemExit("--slug and --message are required with --event")
    event = {
        "time": when or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "slug": slug,
        "role": role,
        "event": message,
    }
    if detail:
        event["detail"] = detail
    merge_events(data_dir / "activity.json", [event])
    return event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a Sanity run on the public index.")
    parser.add_argument("run", nargs="?", type=Path, help="Run folder with equations.json")
    parser.add_argument("--subject", help="Section on the index, such as Physics")
    parser.add_argument("--title", help="Used when equations.json has no title")
    parser.add_argument("--url", help="Source URL, when it is not an arXiv id in the data")
    parser.add_argument("--example", action="store_true", help="Mark the row as an example note")
    parser.add_argument("--no-preview", action="store_true", help="Skip the PDF preview and equation crops")
    parser.add_argument("--no-network", action="store_true", help="Do not fetch the arXiv record or PDF")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--logos-dir", type=Path, default=LOGOS)
    parser.add_argument("--event", action="store_true", help="Append one activity line and exit")
    parser.add_argument("--slug")
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--message", help="Event text, for example: Eq. (4.4) FAILS")
    parser.add_argument("--detail", default="")
    parser.add_argument("--time", default="", help="ISO-8601 time for --event; default is now")
    args = parser.parse_args(argv)
    if args.event:
        record_event(args.data_dir, args.slug or "", args.role or "", args.message or "", args.detail, args.time)
        return 0
    if args.run is None:
        parser.error("a run folder is required")
    publish(
        args.run,
        args.subject or "",
        args.title,
        args.url,
        args.example,
        args.data_dir,
        args.logos_dir,
        preview=not args.no_preview and not args.no_network,
        network=not args.no_network,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
