"""Offline tests for arXiv id parsing and the category map. No network."""

import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fetch_paper import (
    ASTRO_GR,
    api_url,
    build_meta,
    classify,
    fetch_paper,
    parse_entry,
    parse_spec,
    pdf_url,
    slug_for,
    src_url,
    subject_for_category,
)

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>https://arxiv.org/abs/1234.56789v2</id>
    <title>A  Fixture
Title</title>
    <summary>Line one.
Line two.</summary>
    <author><name>A. One</name></author>
    <author><name>B. Two</name></author>
    <arxiv:primary_category term="gr-qc" scheme="http://arxiv.org/schemas/atom"/>
    <arxiv:doi>10.1000/fixture.1</arxiv:doi>
    <arxiv:journal_ref>J. Fixture 1 (2024) 1</arxiv:journal_ref>
  </entry>
</feed>
"""


@pytest.mark.parametrize("spec, kind, ident, version", [
    ("2410.11128", "arxiv", "2410.11128", None),
    ("2410.11128v1", "arxiv", "2410.11128", "v1"),
    ("https://arxiv.org/abs/2410.11128v2", "arxiv", "2410.11128", "v2"),
    ("arXiv:2410.11128v1", "arxiv", "2410.11128", "v1"),
    ("https://doi.org/10.48550/arXiv.2410.11128", "arxiv", "2410.11128", None),
    ("10.1140/epjc/s10052-025-14303-w", "doi", "10.1140/epjc/s10052-025-14303-w", None),
])
def test_parse_spec(spec, kind, ident, version):
    assert parse_spec(spec) == (kind, ident, version)


@pytest.mark.parametrize("category, subject", [
    ("astro-ph.HE", ASTRO_GR),
    ("astro-ph", ASTRO_GR),
    ("gr-qc", ASTRO_GR),
    ("physics.chem-ph", "Chemistry"),
    ("chem-ph", "Chemistry"),
    ("math.AG", "Mathematics"),
    ("math", "Mathematics"),
    ("quant-ph", "Quantum physics"),
    ("cond-mat.str-el", "Condensed matter"),
    ("hep-th", "Physics"),
    ("physics.optics", "Physics"),
    ("math-ph", "Physics"),
    (None, "Physics"),
])
def test_category_map(category, subject):
    assert subject_for_category(category) == subject


def test_no_identifier_is_an_example():
    assert classify({"arxiv_id": None, "doi": None, "primary_category": None}) == ("Examples", True)
    assert classify({"arxiv_id": "1234.56789", "primary_category": "quant-ph"}) == ("Quantum physics", False)


def test_export_urls_stay_on_the_export_host():
    assert api_url("arxiv", "2410.11128", "v1") == "https://export.arxiv.org/api/query?id_list=2410.11128v1"
    assert api_url("doi", "10.1000/foo", None).startswith("https://export.arxiv.org/api/query?search_query=doi:")
    assert pdf_url("2410.11128", "v1") == "https://export.arxiv.org/pdf/2410.11128v1"
    assert src_url("2410.11128", None) == "https://export.arxiv.org/src/2410.11128"
    for url in (api_url("arxiv", "1.2", None), pdf_url("1.2", None), src_url("1.2", None)):
        assert "://arxiv.org/" not in url


def test_atom_fixture_builds_meta_without_network():
    entry = parse_entry(ATOM.encode())
    meta = build_meta(entry, "2026-11-19T00:00:00Z")
    assert meta["title"] == "A Fixture Title"
    assert meta["abstract"] == "Line one. Line two."
    assert meta["authors"] == ["A. One", "B. Two"]
    assert meta["arxiv_id"] == "1234.56789"
    assert meta["version"] == "v2"
    assert meta["primary_category"] == "gr-qc"
    assert meta["doi"] == "10.1000/fixture.1"
    assert meta["journal_ref"] == "J. Fixture 1 (2024) 1"
    assert meta["slug"] == "arxiv-1234-56789"
    assert meta["subject"] == ASTRO_GR
    assert meta["example"] is False
    assert slug_for("2410.11128") == "arxiv-2410-11128"


def test_fetch_writes_source_from_an_opener(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Title")
    page.insert_text((72, 120), "Abstract")
    page.insert_text((72, 150), "A short abstract.")
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    pdf = buffer.getvalue()
    seen = []

    def opener(url):
        seen.append(url)
        assert url.startswith("https://export.arxiv.org/")
        if "api/query" in url:
            return 200, ATOM.encode()
        if "/pdf/" in url:
            return 200, pdf
        if "/src/" in url:
            return 200, b"\x1f\x8bnot-a-real-member"
        raise AssertionError(url)

    dest = fetch_paper(
        "1234.56789v2",
        tmp_path,
        opener=opener,
        now=datetime(2026, 11, 19, tzinfo=timezone.utc),
    )
    assert dest == tmp_path / "runs" / "arxiv-1234-56789" / "source"
    assert (dest / "paper.pdf").read_bytes().startswith(b"%PDF")
    assert (dest / "source.tar.gz").read_bytes().startswith(b"\x1f\x8b")
    assert (dest / "preview.png").stat().st_size > 100
    meta = (dest / "meta.json").read_text(encoding="utf-8")
    assert '"fetched_at": "2026-11-19T00:00:00Z"' in meta
    assert all(url.startswith("https://export.arxiv.org/") for url in seen)
    assert Path(dest / "preview.png").suffix == ".png"
