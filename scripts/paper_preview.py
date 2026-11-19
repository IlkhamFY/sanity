"""First page and flagged-equation crops from a paper PDF.

The preview is the top of page 1. An equation crop is written only when the
printed label, such as ``(4.4)``, can be found on the page. If it cannot,
nothing is invented.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path


PREVIEW_WIDTH = 1200
PREVIEW_FRACTION = 0.45
CROP_WIDTH = 1200
USER_AGENT = "sanity-publish/1.0 (mailto:ilkhamfy@gmail.com)"


def arxiv_id(source: str) -> str | None:
    """Return ``2410.11128v1`` from an abs URL or an ``arXiv:`` label."""
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", source or "")
    if not match:
        return None
    if "arxiv" not in source.lower() and not source.lower().startswith("arxiv:"):
        return None
    return f"{match.group(1)}{match.group(2) or ''}"


def arxiv_pdf_url(source: str) -> str | None:
    identifier = arxiv_id(source)
    if not identifier:
        return None
    return f"https://arxiv.org/pdf/{identifier}"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        dest.write_bytes(response.read())


def _save_webp(pix, dest: Path) -> None:
    from PIL import Image

    dest.parent.mkdir(parents=True, exist_ok=True)
    mode = "RGBA" if pix.n >= 4 else "RGB"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if mode == "RGBA":
        image = image.convert("RGB")
    image.save(dest, "WEBP", quality=82, method=4)


def preview_clip(page):
    """Title, authors, and the abstract lead, without the blank margin or a side stamp."""
    import pymupdf

    blocks = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        box = pymupdf.Rect(block["bbox"])
        if box.y0 < 36:
            continue
        # A tall thin box is the vertical arXiv stamp, not the title block.
        if box.width < 48 and box.height > 80:
            continue
        blocks.append(box)
    if not blocks:
        height = page.rect.height * PREVIEW_FRACTION
        return pymupdf.Rect(page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y0 + height)
    title_top = min(box.y0 for box in blocks)
    body = [box for box in blocks if box.y0 < page.rect.height * 0.7]
    left = min(box.x0 for box in body)
    right = max(box.x1 for box in body)
    cut = title_top + 48
    heading = None
    for hit in page.search_for("Abstract"):
        if title_top < hit.y0 <= page.rect.height * 0.55:
            heading = hit
            break
    if heading is not None:
        cut = heading.y1 + 8
        stop = False
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                box = pymupdf.Rect(line["bbox"])
                if box.y0 < heading.y1 - 1 or box.y0 > page.rect.height * 0.8:
                    continue
                text = "".join(span["text"] for span in line["spans"]).strip()
                if not text or text == "Abstract":
                    continue
                cut = box.y1 + 14
                # A line that actually ends the sentence. Mid-line periods keep going
                # so the crop does not stop on "systems. We propose".
                if text.endswith((".", "!", "?")):
                    stop = True
                    break
            if stop:
                break
    clip = pymupdf.Rect(left - 16, title_top - 18, right + 16, cut)
    return clip & page.rect


def render_preview(pdf_path: Path, dest: Path, width: int = PREVIEW_WIDTH) -> None:
    """Write the top of page 1 at ``width`` pixels."""
    import pymupdf

    document = pymupdf.open(pdf_path)
    try:
        page = document[0]
        clip = preview_clip(page)
        zoom = width / clip.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
        _save_webp(pix, dest)
    finally:
        document.close()


def _tag_hit(page, claim: str):
    """The equation tag ``(claim)`` if it sits in the right-hand number column."""
    import pymupdf

    label = f"({claim})"
    hits = page.search_for(label)
    if not hits:
        return None
    margin = page.rect.x0 + page.rect.width * 0.68
    top = page.rect.y0 + page.rect.height * 0.06
    bottom = page.rect.y1 - page.rect.height * 0.045
    tags = [hit for hit in hits if hit.x0 >= margin and top <= hit.y0 <= bottom]
    if not tags:
        return None
    return tags[0]


def _equation_clip(page, hit):
    """A short band around the tag, wide enough for a displayed equation."""
    import pymupdf

    left = page.rect.x0 + 42
    right = min(page.rect.x1 - 28, hit.x1 + 18)
    clip = pymupdf.Rect(left, hit.y0 - 30, right, hit.y1 + 8)
    return clip & page.rect


def render_equation(pdf_path: Path, dest: Path, claim: str, width: int = CROP_WIDTH) -> int | None:
    """Crop the printed equation. Return the 1-based page, or None if not found."""
    import pymupdf

    document = pymupdf.open(pdf_path)
    try:
        for index, page in enumerate(document):
            hit = _tag_hit(page, claim)
            if hit is None:
                continue
            clip = _equation_clip(page, hit)
            if clip.is_empty or clip.height < 8 or clip.width < 40:
                return None
            zoom = min(width / clip.width, 4)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
            _save_webp(pix, dest)
            return index + 1
    finally:
        document.close()
    return None


def safe_claim(claim: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", claim).strip("-") or "claim"
