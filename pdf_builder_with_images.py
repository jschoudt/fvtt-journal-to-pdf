# pdf_builder_with_images.py  (V1.6 background options)
# - Supports app_with_dividers.py API: build_pdf(out_path=..., title=..., journals=..., selection=Selection(items=...), divider_pages=...)
# - Supports journals as Journal objects OR legacy tuples
# - Supports page model with page.headings -> heading.blocks (ContentBlock.kind: html/p/img/table) OR legacy page.blocks
# - Renders HTML paragraphs (kind "html" or "p"), images (PNG/WebP/SVG), and tables (ReportLab Table)
# - TOC: dotted leaders, indentation, clickable, multi-page
# - Back-to-TOC: drawn once at top+bottom of content pages; skipped on cover+TOC page; internal destination (no Acrobat file:// warning)
# - Sanitizes Foundry HTML into ReportLab-friendly inline markup
# - Backgrounds: path + mode (fill/fit/stretch/tile) + opacity + first-page-only

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple
import io
import os
import re
import hashlib

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    PageBreak,
    Spacer,
    Image as RLImage,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

# Optional SVG support
try:
    import cairosvg  # type: ignore
except Exception:
    cairosvg = None

# Pillow for WebP reliability and background processing
try:
    from PIL import Image as PILImage  # type: ignore
except Exception:
    PILImage = None


# -----------------------------
# UI Selection model (must match app)
# -----------------------------
@dataclass
class Selection:
    """
    app_with_dividers.py passes Selection(items=[(journal_title, page_title, heading_or_none), ...])
    heading_or_none is a string path/id OR None for selecting whole page.
    """
    items: List[Tuple[str, str, Optional[str]]] = field(default_factory=list)
    # Back-compat / optional programmatic selection
    selected_pages: set[Tuple[int, int]] = field(default_factory=set)
    selected_headings: set[Tuple[int, int, str]] = field(default_factory=set)


# -----------------------------
# HTML sanitization
# -----------------------------
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_STRIP_RE = re.compile(r"</?(div|span|section|figure|article|header|footer|nav|main)(\s[^>]*)?>", re.IGNORECASE)

def sanitize_html(s: str) -> str:
    """
    Make Foundry-ish HTML safe for ReportLab Paragraph.

    ReportLab Paragraph supports a limited set of inline tags. Foundry exports often include block tags
    (<p>, <ul>, <li>, <strong>, <em>, etc.). We normalize those into inline-friendly markup and <br/>.
    """
    if not s:
        return ""

    s = s.replace("&nbsp;", " ")

    # Some modules export self-closing or empty anchors like <a href="..."/> or <a href="..."></a>.
    # ReportLab requires proper <a>...</a> pairs. Convert these into clickable links with visible text.
    def _fix_anchor(m: re.Match) -> str:
        attrs = m.group(1) or ""
        href_m = re.search(r'href\s*=\s*"(.*?)"', attrs, re.IGNORECASE)
        href = href_m.group(1) if href_m else ""
        if not href:
            return ""
        safe_text = href
        return f'<a href="{href}">{safe_text}</a>'

    # Self-closing <a .../>
    s = re.sub(r"<\s*a\b([^>]*)/\s*>", _fix_anchor, s, flags=re.IGNORECASE)
    # Empty <a ...></a>
    s = re.sub(r"<\s*a\b([^>]*)>\s*</\s*a\s*>", _fix_anchor, s, flags=re.IGNORECASE)

    # Convert semantic tags to ReportLab tags
    s = re.sub(r"</?\s*strong[^>]*>", lambda m: "</b>" if m.group(0).startswith("</") else "<b>", s, flags=re.IGNORECASE)
    s = re.sub(r"</?\s*em[^>]*>",     lambda m: "</i>" if m.group(0).startswith("</") else "<i>", s, flags=re.IGNORECASE)

    # Paragraphs -> line breaks
    s = re.sub(r"<\s*p[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"</\s*p\s*>", "<br/><br/>", s, flags=re.IGNORECASE)

    # Lists -> bullets
    s = re.sub(r"<\s*(ul|ol)[^>]*>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"</\s*(ul|ol)\s*>", "<br/>", s, flags=re.IGNORECASE)
    s = re.sub(r"<\s*li[^>]*>", "• ", s, flags=re.IGNORECASE)
    s = re.sub(r"</\s*li\s*>", "<br/>", s, flags=re.IGNORECASE)

    # Normalize breaks to ReportLab-friendly self-closing
    s = _BR_RE.sub("<br/>", s)

    # Strip container tags
    s = _TAG_STRIP_RE.sub("", s)

    # Strip attributes, but keep href on <a>
    def _strip_attrs(m: re.Match) -> str:
        tag = m.group(1)
        attrs = m.group(2) or ""
        is_self_closing = attrs.strip().endswith("/")

        if tag.lower() == "a":
            href_m = re.search(r'href\s*=\s*"(.*?)"', attrs, re.IGNORECASE)
            href = href_m.group(1) if href_m else ""
            return f'<a href="{href}">'

        sc = "/" if is_self_closing else ""
        return f"<{tag}{sc}>"

    s = re.sub(r"<([a-zA-Z0-9]+)([^>]*)>", _strip_attrs, s)

    # Re-normalize <br/>
    s = _BR_RE.sub("<br/>", s)

    # Balance anchor tags to avoid ReportLab parse errors on malformed HTML exports.
    # If there are more opening <a ...> than closing </a>, close them at the end.
    opens = len(re.findall(r"<\s*a\b[^>]*>", s, flags=re.IGNORECASE))
    closes = len(re.findall(r"</\s*a\s*>", s, flags=re.IGNORECASE))
    if closes > opens:
        # Drop stray closing tags
        diff = closes - opens
        for _ in range(diff):
            s = re.sub(r"</\s*a\s*>", "", s, count=1, flags=re.IGNORECASE)
    elif opens > closes:
        s += "</a>" * (opens - closes)

    return s


# -----------------------------
# Helpers
# -----------------------------
def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]

def _normalize_journals(journals: Any) -> List[Any]:
    if journals is None:
        return []
    if isinstance(journals, list):
        return journals
    return [journals]

def _get_journal_parts(j: Any) -> Tuple[str, List[Any], Optional[str]]:
    # Journal dataclass/object
    if hasattr(j, "title") and hasattr(j, "pages"):
        return (getattr(j, "title") or "Journal", list(getattr(j, "pages") or []), getattr(j, "assets_dir", None))
    # Legacy tuple (title, pages, assets_dir?)
    if isinstance(j, (tuple, list)):
        title = j[0] if len(j) > 0 else "Journal"
        pages = j[1] if len(j) > 1 else []
        assets_dir = j[2] if len(j) > 2 else None
        return (title or "Journal", list(pages or []), assets_dir)
    return ("Journal", [], None)

def _resolve_asset_path(assets_dir: Optional[str], src: str) -> Optional[str]:
    if not src:
        return None
    if os.path.isabs(src) and os.path.exists(src):
        return src
    if not assets_dir:
        return None

    # Try direct join
    cand = os.path.join(assets_dir, src)
    if os.path.exists(cand):
        return cand

    # Strip leading assets/ or Assets/
    src2 = re.sub(r"^(assets|Assets)[/\\]", "", src)
    cand = os.path.join(assets_dir, src2)
    if os.path.exists(cand):
        return cand

    # Basename fallback
    base = os.path.basename(src2)
    if base:
        cand = os.path.join(assets_dir, base)
        if os.path.exists(cand):
            return cand

    return None

def _svg_to_png_bytes(svg_path: str) -> Optional[bytes]:
    if cairosvg is None:
        return None
    try:
        return cairosvg.svg2png(url=svg_path)
    except Exception:
        return None

def _image_flowable(path: str, max_w: float, max_h: float, hinted_w_px: Optional[float] = None) -> Optional[RLImage]:
    ext = os.path.splitext(path)[1].lower()

    # SVG -> rasterize
    if ext == ".svg":
        png = _svg_to_png_bytes(path)
        if not png:
            return None
        bio = io.BytesIO(png)
        img = RLImage(bio)
    else:
        # WebP -> Pillow -> PNG bytes is most reliable
        if ext == ".webp" and PILImage is not None:
            try:
                pil = PILImage.open(path)
                out = io.BytesIO()
                pil.convert("RGBA").save(out, format="PNG")
                out.seek(0)
                img = RLImage(out)
            except Exception:
                img = RLImage(path)
        else:
            img = RLImage(path)

    # Apply width hint (px -> pt approx 0.75 at 96dpi)
    if hinted_w_px and hinted_w_px > 0:
        target_w = hinted_w_px * 0.75
        scale = target_w / float(img.drawWidth)
        img.drawWidth *= scale
        img.drawHeight *= scale

    # Clamp to available area
    try:
        img._restrictSize(max_w, max_h)  # type: ignore[attr-defined]
    except Exception:
        if img.drawWidth > max_w:
            s = max_w / float(img.drawWidth)
            img.drawWidth *= s
            img.drawHeight *= s
        if img.drawHeight > max_h:
            s = max_h / float(img.drawHeight)
            img.drawWidth *= s
            img.drawHeight *= s

    return img

def _selection_empty(sel: Selection) -> bool:
    return (not sel.items) and (not sel.selected_pages) and (not sel.selected_headings)

def _page_selected(sel: Selection, j_idx: int, p_idx: int, j_title: str, p_title: str) -> bool:
    if (j_idx, p_idx) in sel.selected_pages:
        return True
    return (j_title, p_title, None) in sel.items

def _heading_selected(sel: Selection, j_idx: int, p_idx: int, j_title: str, p_title: str, h_key: str) -> bool:
    if (j_idx, p_idx, h_key) in sel.selected_headings:
        return True
    return (j_title, p_title, h_key) in sel.items


# -----------------------------
# DocTemplate for TOC/bookmarks
# -----------------------------
class _Doc(SimpleDocTemplate):
    def __init__(self, *args, toc: TableOfContents, **kwargs):
        super().__init__(*args, **kwargs)
        self._toc = toc

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            bk = getattr(flowable, "_bookmarkName", None)
            lvl = getattr(flowable, "_tocLevel", None)

            # Always create a named destination if requested
            if bk:
                self.canv.bookmarkPage(bk)

            # Only register TOC entries when a level is provided
            if bk and lvl is not None:
                txt = flowable.getPlainText()
                if lvl == 0:
                    txt = f"<b>{txt}</b>"
                self.notify("TOCEntry", (lvl, txt, self.page, bk))


def _draw_back_to_toc(canvas, doc, toc_page: int = 2):
    # Skip cover (1) and TOC page (2)
    if doc.page <= toc_page:
        return

    canvas.saveState()
    canvas.setFont("Helvetica", 9)

    dest = "_TOC_TOP"  # internal named destination

    top_y = doc.pagesize[1] - 0.6 * inch
    bot_y = 0.55 * inch
    x = doc.leftMargin
    w = 180

    canvas.drawString(x, top_y, "Back to Table of Contents")
    canvas.linkRect("", dest, (x, top_y - 2, x + w, top_y + 10), relative=1, thickness=0)

    canvas.drawString(x, bot_y, "Back to Table of Contents")
    canvas.linkRect("", dest, (x, bot_y - 2, x + w, bot_y + 10), relative=1, thickness=0)

    canvas.restoreState()


def _safe_alpha(alpha: float) -> float:
    try:
        return max(0.0, min(1.0, float(alpha)))
    except Exception:
        return 1.0


def _normalize_background_mode(mode: Optional[str]) -> str:
    mode = (mode or "fill").strip().lower()
    return mode if mode in {"fill", "fit", "stretch", "tile"} else "fill"


def _set_canvas_alpha(canvas, alpha: float) -> None:
    try:
        canvas.setFillAlpha(alpha)
    except Exception:
        pass
    try:
        canvas.setStrokeAlpha(alpha)
    except Exception:
        pass


def _background_reader_with_pillow(
    background_path: str,
    page_w: float,
    page_h: float,
    mode: str,
    opacity: float,
) -> Optional[ImageReader]:
    if PILImage is None:
        return None

    try:
        with PILImage.open(background_path) as raw:
            src = raw.convert("RGBA")
            target_w = max(1, int(round(page_w)))
            target_h = max(1, int(round(page_h)))
            page = PILImage.new("RGBA", (target_w, target_h), (255, 255, 255, 0))

            if mode == "stretch":
                placed = src.resize((target_w, target_h), PILImage.LANCZOS)
                page.alpha_composite(placed, (0, 0))

            elif mode == "tile":
                tile = src
                # Keep huge source images from creating a single giant tile.
                max_tile_w = max(1, target_w)
                max_tile_h = max(1, target_h)
                if tile.width > max_tile_w or tile.height > max_tile_h:
                    ratio = min(max_tile_w / float(tile.width), max_tile_h / float(tile.height))
                    new_size = (
                        max(1, int(round(tile.width * ratio))),
                        max(1, int(round(tile.height * ratio))),
                    )
                    tile = tile.resize(new_size, PILImage.LANCZOS)
                for y in range(0, target_h, max(1, tile.height)):
                    for x in range(0, target_w, max(1, tile.width)):
                        page.alpha_composite(tile, (x, y))

            else:
                src_ratio = src.width / float(src.height)
                page_ratio = target_w / float(target_h)

                if mode == "fit":
                    if src_ratio > page_ratio:
                        draw_w = target_w
                        draw_h = max(1, int(round(draw_w / src_ratio)))
                    else:
                        draw_h = target_h
                        draw_w = max(1, int(round(draw_h * src_ratio)))
                    placed = src.resize((draw_w, draw_h), PILImage.LANCZOS)
                    x = (target_w - draw_w) // 2
                    y = (target_h - draw_h) // 2
                    page.alpha_composite(placed, (x, y))

                else:  # fill
                    if src_ratio > page_ratio:
                        draw_h = target_h
                        draw_w = max(1, int(round(draw_h * src_ratio)))
                    else:
                        draw_w = target_w
                        draw_h = max(1, int(round(draw_w / src_ratio)))
                    placed = src.resize((draw_w, draw_h), PILImage.LANCZOS)
                    x = (target_w - draw_w) // 2
                    y = (target_h - draw_h) // 2
                    page.alpha_composite(placed, (x, y))

            opacity = _safe_alpha(opacity)
            if opacity < 1.0:
                alpha_band = page.getchannel("A")
                alpha_band = alpha_band.point(lambda px: int(px * opacity))
                page.putalpha(alpha_band)

            out = io.BytesIO()
            page.save(out, format="PNG")
            out.seek(0)
            return ImageReader(out)
    except Exception:
        return None


def _draw_page_background(
    canvas,
    doc,
    background_path: Optional[str],
    *,
    background_mode: str = "fill",
    background_opacity: float = 1.0,
    background_first_page_only: bool = False,
) -> None:
    if not background_path:
        return
    if background_first_page_only and getattr(doc, "page", 1) != 1:
        return

    try:
        page_w, page_h = doc.pagesize
        mode = _normalize_background_mode(background_mode)
        opacity = _safe_alpha(background_opacity)

        processed = _background_reader_with_pillow(background_path, page_w, page_h, mode, opacity)
        if processed is not None:
            canvas.saveState()
            canvas.drawImage(
                processed,
                0,
                0,
                width=page_w,
                height=page_h,
                preserveAspectRatio=False,
                mask="auto",
            )
            canvas.restoreState()
            return

        # Fallback path if Pillow is unavailable or preprocessing fails.
        img = ImageReader(background_path)
        img_w, img_h = img.getSize()
        if not img_w or not img_h:
            return

        canvas.saveState()
        if opacity < 1.0:
            _set_canvas_alpha(canvas, opacity)

        if mode == "stretch":
            canvas.drawImage(
                img,
                0,
                0,
                width=page_w,
                height=page_h,
                preserveAspectRatio=False,
                mask="auto",
            )

        elif mode == "fit":
            scale = min(page_w / float(img_w), page_h / float(img_h))
            draw_w = img_w * scale
            draw_h = img_h * scale
            x = (page_w - draw_w) / 2.0
            y = (page_h - draw_h) / 2.0
            canvas.drawImage(
                img,
                x,
                y,
                width=draw_w,
                height=draw_h,
                preserveAspectRatio=True,
                mask="auto",
            )

        elif mode == "tile":
            tile_w = img_w
            tile_h = img_h
            if tile_w > page_w or tile_h > page_h:
                scale = min(page_w / float(img_w), page_h / float(img_h))
                tile_w = max(1.0, img_w * scale)
                tile_h = max(1.0, img_h * scale)
            y = 0.0
            while y < page_h:
                x = 0.0
                while x < page_w:
                    canvas.drawImage(
                        img,
                        x,
                        y,
                        width=tile_w,
                        height=tile_h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                    x += tile_w
                y += tile_h

        else:  # fill
            scale = max(page_w / float(img_w), page_h / float(img_h))
            draw_w = img_w * scale
            draw_h = img_h * scale
            x = (page_w - draw_w) / 2.0
            y = (page_h - draw_h) / 2.0
            canvas.drawImage(
                img,
                x,
                y,
                width=draw_w,
                height=draw_h,
                preserveAspectRatio=True,
                mask="auto",
            )

        canvas.restoreState()
    except Exception:
        # Backgrounds are optional polish; never fail the export because of one.
        return


def _decorate_page(
    canvas,
    doc,
    *,
    background_path: Optional[str],
    background_mode: str = "fill",
    background_opacity: float = 1.0,
    background_first_page_only: bool = False,
    toc_page: int = 2,
    include_back_to_toc: bool = True,
):
    _draw_page_background(
        canvas,
        doc,
        background_path,
        background_mode=background_mode,
        background_opacity=background_opacity,
        background_first_page_only=background_first_page_only,
    )
    if include_back_to_toc:
        _draw_back_to_toc(canvas, doc, toc_page=toc_page)


# -----------------------------
# Public API
# -----------------------------
def build_pdf(
    *,
    journals: Any,
    out_path: str,
    title: str = "FVTT Journals",
    selection: Optional[Selection] = None,
    divider_pages: bool = True,
    page_size=letter,
    background_path: Optional[str] = None,
    background_mode: str = "fill",
    background_opacity: float = 1.0,
    background_first_page_only: bool = False,
    **kwargs,
):
    journals_list = _normalize_journals(journals)
    if selection is None:
        selection = Selection()

    include_all = _selection_empty(selection)

    styles = getSampleStyleSheet()
    Body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        spaceAfter=6,
        splitLongWords=1,
        wordWrap="CJK",
    )
    Title = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        alignment=TA_LEFT,
        spaceAfter=18,
        splitLongWords=1,
        wordWrap="CJK",
    )
    H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, leading=20, spaceBefore=14, spaceAfter=8, splitLongWords=1, wordWrap="CJK")
    H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, leading=16, spaceBefore=12, spaceAfter=6, splitLongWords=1, wordWrap="CJK")
    H3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, leading=14, spaceBefore=10, spaceAfter=4, splitLongWords=1, wordWrap="CJK")

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC0", fontName="Helvetica-Bold", fontSize=12, leftIndent=0, firstLineIndent=0,
                       spaceBefore=8, spaceAfter=6, leading=14, splitLongWords=1, wordWrap="CJK"),
        ParagraphStyle("TOC1", fontName="Helvetica", fontSize=10, leftIndent=18, firstLineIndent=0,
                       spaceBefore=2, spaceAfter=2, leading=12, splitLongWords=1, wordWrap="CJK"),
        ParagraphStyle("TOC2", fontName="Helvetica", fontSize=9, leftIndent=36, firstLineIndent=0,
                       spaceBefore=1, spaceAfter=1, leading=11, splitLongWords=1, wordWrap="CJK"),
        ParagraphStyle("TOC3", fontName="Helvetica", fontSize=9, leftIndent=54, firstLineIndent=0,
                       spaceBefore=1, spaceAfter=1, leading=11, splitLongWords=1, wordWrap="CJK"),
    ]

    doc = _Doc(
        out_path,
        pagesize=page_size,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        toc=toc,
        title=title or "FVTT Journals",
    )

    story: List[Any] = []

    # Cover
    cover_title = title or "FVTT Journals"
    if len(journals_list) == 1:
        cover_title = _get_journal_parts(journals_list[0])[0] or cover_title
    story.append(Paragraph(sanitize_html(cover_title), Title))
    story.append(PageBreak())

    # TOC page
    toc_anchor = Paragraph('<a name="_TOC_TOP"/>', Body)
    toc_anchor._bookmarkName = "_TOC_TOP"
    toc_anchor._tocLevel = None
    story.append(toc_anchor)
    story.append(Paragraph("Table of Contents", H1))
    story.append(Spacer(1, 0.15 * inch))
    story.append(toc)
    story.append(PageBreak())

    # Content
    for j_idx, j in enumerate(journals_list):
        j_title, pages, assets_dir = _get_journal_parts(j)

        if divider_pages and len(journals_list) > 1:
            p = Paragraph(sanitize_html(j_title), Title)
            p._bookmarkName = f"j_{j_idx}_{_sha1(j_title)}"
            p._tocLevel = 0
            story.append(p)
            story.append(PageBreak())

        for p_idx, page in enumerate(pages):
            p_title = getattr(page, "title", f"Page {p_idx+1}")
            include_page = include_all or _page_selected(selection, j_idx, p_idx, j_title, p_title)

            ph = Paragraph(sanitize_html(p_title), H1)
            ph._bookmarkName = f"p_{j_idx}_{p_idx}_{_sha1(p_title)}"
            ph._tocLevel = 1 if len(journals_list) > 1 else 0
            story.append(ph)

            headings = getattr(page, "headings", None)
            legacy_blocks = getattr(page, "blocks", None)

            if headings:
                for h in headings:
                    h_title = getattr(h, "title", "Section")
                    h_level = int(getattr(h, "level", 2) or 2)
                    h_path = getattr(h, "path", None) or getattr(h, "id", None) or f"{h_level}:{h_title}"
                    h_key = str(h_path)

                    if not (include_page or _heading_selected(selection, j_idx, p_idx, j_title, p_title, h_key)):
                        continue

                    style = H2 if h_level <= 2 else H3
                    hh = Paragraph(sanitize_html(h_title), style)
                    hh._bookmarkName = f"h_{j_idx}_{p_idx}_{_sha1(h_key)}"
                    hh._tocLevel = min(3, max(2, h_level))
                    story.append(hh)

                    blocks = getattr(h, "blocks", []) or []
                    _append_blocks(story, blocks, Body, assets_dir, doc)

            elif legacy_blocks:
                _append_blocks(story, legacy_blocks, Body, assets_dir, doc)

            story.append(Spacer(1, 0.15 * inch))

    doc.multiBuild(
        story,
        onFirstPage=lambda c, d: _decorate_page(
            c,
            d,
            background_path=background_path,
            background_mode=background_mode,
            background_opacity=background_opacity,
            background_first_page_only=background_first_page_only,
            toc_page=2,
            include_back_to_toc=False,
        ),
        onLaterPages=lambda c, d: _decorate_page(
            c,
            d,
            background_path=background_path,
            background_mode=background_mode,
            background_opacity=background_opacity,
            background_first_page_only=background_first_page_only,
            toc_page=2,
            include_back_to_toc=True,
        ),
    )


def _append_blocks(story: List[Any], blocks: Iterable[Any], Body: ParagraphStyle, assets_dir: Optional[str], doc: SimpleDocTemplate):
    max_w = doc.width
    max_h = doc.height * 0.85

    for block in blocks:
        kind = getattr(block, "kind", None)
        if kind is None and isinstance(block, dict):
            kind = block.get("kind")

        if kind in ("p", "html"):
            txt = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
            if txt and str(txt).strip():
                story.append(Paragraph(sanitize_html(str(txt)), Body))

        elif kind == "img":
            src = getattr(block, "src", None) or (block.get("src") if isinstance(block, dict) else "")
            hinted_w = getattr(block, "width", None) if not isinstance(block, dict) else block.get("width")
            resolved = _resolve_asset_path(assets_dir, src) if assets_dir else None
            if not resolved:
                story.append(Paragraph(sanitize_html(f"[Missing image: {src}]"), Body))
                continue
            img = _image_flowable(resolved, max_w, max_h, hinted_w_px=hinted_w)
            if not img:
                story.append(Paragraph(sanitize_html(f"[Missing image: {src}]"), Body))
                continue
            story.append(img)
            story.append(Spacer(1, 0.08 * inch))

        elif kind == "table":
            rows = getattr(block, "rows", None) or (block.get("rows") if isinstance(block, dict) else None)
            if not rows:
                continue
            table_data = []
            for r in rows:
                row = []
                for cell in r:
                    row.append(Paragraph(sanitize_html(str(cell)), Body))
                table_data.append(row)
            t = Table(table_data, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.12 * inch))

        else:
            # legacy string fallback
            if isinstance(block, str) and block.strip():
                story.append(Paragraph(sanitize_html(block), Body))
