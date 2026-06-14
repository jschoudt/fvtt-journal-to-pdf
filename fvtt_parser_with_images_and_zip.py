# fvtt_parser_with_images_and_zip.py
# System-agnostic Foundry Journal export parser (ZIP or journal.json)
# Produces a stable model used by the desktop exporter app.

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union


# -----------------------------
# Models
# -----------------------------

@dataclass
class ContentBlock:
    kind: str                  # "html" | "img" | "table"
    text: Optional[str] = None # for kind=="html"
    src: Optional[str] = None  # for kind=="img" (relative path like "assets/image001.png")
    width: Optional[int] = None
    height: Optional[int] = None
    rows: Optional[List[List[str]]] = None  # for kind=="table"


@dataclass
class HeadingNode:
    title: str
    level: int
    blocks: List[ContentBlock] = field(default_factory=list)

    @property
    def path(self) -> str:
        # stable identifier for GUI selection
        return f"h{self.level}:{self.title}"


@dataclass
class PageNode:
    title: str
    sort: int = 0
    headings: List[HeadingNode] = field(default_factory=list)


@dataclass
class Journal:
    title: str
    pages: List[PageNode] = field(default_factory=list)
    assets_dir: Optional[str] = None   # absolute path to extracted assets directory
    root_dir: Optional[str] = None     # absolute temp extraction root (optional)


# -----------------------------
# HTML helpers
# -----------------------------

# Allow hyphenated attributes (data-export-src, etc.)
_ATTR_RE = re.compile(r'([:\w-]+)\s*=\s*"([^"]*)"')
_IMG_RE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
_HEADING_RE = re.compile(r"<h([2-6])\b[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)

_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _html_to_text(s: str) -> str:
    s = _TAG_STRIP_RE.sub("", s)
    s = s.replace("&nbsp;", " ")
    s = _WS_RE.sub(" ", s).strip()
    return s


def _parse_attrs(attr_text: str) -> dict:
    return {k.lower(): v for k, v in _ATTR_RE.findall(attr_text or "")}


def _pick_img_src(attrs: dict) -> Optional[str]:
    # Prefer export-mapped paths (inside ZIP assets folder)
    for k in ("data-export-src", "data-export-original-src", "data-src", "src"):
        v = attrs.get(k)
        if v:
            return v
    return None


def _extract_tables(table_html: str) -> List[List[str]]:
    rows: List[List[str]] = []
    # crude but works for typical Foundry exports
    for tr in re.findall(r"<tr\b.*?</tr>", table_html, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<t[dh]\b.*?</t[dh]>", tr, flags=re.IGNORECASE | re.DOTALL)
        row = [_html_to_text(c) for c in cells]
        if row:
            rows.append(row)
    return rows


def _blocks_from_html(section_html: str) -> List[ContentBlock]:
    """
    Convert a chunk of HTML into ordered blocks:
      - html paragraphs (as raw-ish HTML)
      - images
      - tables
    """
    blocks: List[ContentBlock] = []
    s = section_html or ""
    i = 0

    # scan for next img or table
    while i < len(s):
        next_img = _IMG_RE.search(s, i)
        next_tbl = _TABLE_RE.search(s, i)

        # pick earliest
        cand = [m for m in (next_img, next_tbl) if m]
        if not cand:
            tail = s[i:].strip()
            if tail:
                blocks.append(ContentBlock(kind="html", text=tail))
            break

        m = min(cand, key=lambda mm: mm.start())

        # text before
        if m.start() > i:
            chunk = s[i:m.start()].strip()
            if chunk:
                blocks.append(ContentBlock(kind="html", text=chunk))

        if m is next_img:
            attrs = _parse_attrs(m.group(1))
            src = _pick_img_src(attrs)
            w = attrs.get("width")
            h = attrs.get("height")
            try:
                w_int = int(float(w)) if w else None
            except Exception:
                w_int = None
            try:
                h_int = int(float(h)) if h else None
            except Exception:
                h_int = None
            if src:
                blocks.append(ContentBlock(kind="img", src=src, width=w_int, height=h_int))
        else:
            table_html = m.group(0)
            rows = _extract_tables(table_html)
            if rows:
                blocks.append(ContentBlock(kind="table", rows=rows))

        i = m.end()

    return blocks


def _split_into_headings(page_html: str) -> List[HeadingNode]:
    """
    Split the page HTML by headings (h2-h6). Each heading becomes a HeadingNode with blocks.
    Content before the first heading becomes an implicit h2 "Content" heading.
    """
    html_src = page_html or ""
    matches = list(_HEADING_RE.finditer(html_src))
    headings: List[HeadingNode] = []

    def add_heading(title: str, level: int, content_html: str):
        title_text = _html_to_text(title) if "<" in title else title.strip()
        node = HeadingNode(title=title_text or "Untitled", level=level)
        node.blocks = _blocks_from_html(content_html)
        headings.append(node)

    if not matches:
        add_heading("Content", 2, html_src)
        return headings

    # preface
    pre = html_src[:matches[0].start()].strip()
    if pre:
        add_heading("Content", 2, pre)

    for idx, m in enumerate(matches):
        level = int(m.group(1))
        title_html = m.group(2)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html_src)
        section = html_src[start:end]
        add_heading(title_html, level, section)

    return headings


# -----------------------------
# ZIP / JSON loading
# -----------------------------

def _extract_zip_to_temp(zip_path: str) -> Tuple[str, Optional[str]]:
    root = tempfile.mkdtemp(prefix="fvtt_export_")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(root)
    # locate assets dir (assets or Assets)
    assets_dir = None
    for name in ("assets", "Assets"):
        p = Path(root) / name
        if p.exists() and p.is_dir():
            assets_dir = str(p)
            break
    return root, assets_dir



def _find_manifest_json(root_dir: str) -> Optional[str]:
    cand = Path(root_dir) / "manifest.json"
    if cand.exists():
        return str(cand)
    for p in Path(root_dir).rglob("manifest.json"):
        return str(p)
    return None

def _find_journal_json(root_dir: str) -> str:
    # Prefer a top-level journal.json, otherwise search
    cand = Path(root_dir) / "journal.json"
    if cand.exists():
        return str(cand)
    for p in Path(root_dir).rglob("journal.json"):
        return str(p)
    raise FileNotFoundError("journal.json not found in ZIP export")


def parse_journal(path: str) -> Union[Journal, List[Journal]]:
    """
    Accepts:
      - ZIP created by Foundry export module (contains journal.json + assets/)
      - journal.json directly (for dev/testing)
    Returns:
      - Journal (single export)
      - List[Journal] (folder export where journal.json contains multiple journals) [not used in this sample json]
    """
    p = Path(path)
    assets_dir = None
    root_dir = None
    json_path = str(p)

    if p.suffix.lower() == ".zip":
        root_dir, assets_dir = _extract_zip_to_temp(str(p))
        try:
            json_path = _find_journal_json(root_dir)
        except FileNotFoundError:
            # Folder export: manifest.json at root + journals/*.json
            manifest_path = _find_manifest_json(root_dir)
            if not manifest_path:
                raise
            json_path = manifest_path

    data = json.load(open(json_path, "r", encoding="utf-8"))
    # If this is a folder export manifest, load individual journal json files from /journals
    if isinstance(data, dict) and data.get("type") == "folder-export" or (isinstance(data, dict) and (Path(json_path).name.lower() == "manifest.json")):
        journals_dir = Path(root_dir or Path(json_path).parent) / "journals"
        journal_files: List[Path] = []

        # Try to follow manifest entries if present
        entries = data.get("journals") if isinstance(data, dict) else None
        if isinstance(entries, list):
            for ent in entries:
                if isinstance(ent, str):
                    ent_norm = ent.replace("\\", "/")
                    journal_files.append((Path(root_dir or "") / ent_norm) if root_dir else Path(ent_norm))
                elif isinstance(ent, dict):
                    for k in ("file", "path", "json", "href"):
                        v = ent.get(k)
                        if isinstance(v, str) and v.lower().endswith(".json"):
                            v_norm = v.replace("\\", "/")
                            journal_files.append((Path(root_dir or "") / v_norm) if root_dir else Path(v_norm))
                            break

        # Fallback: glob any jsons in journals/
        if not journal_files and journals_dir.exists():
            journal_files = sorted(journals_dir.glob("*.json"))

        if not journal_files:
            raise FileNotFoundError("manifest.json found but no journals/*.json found in ZIP export")

        out: List[Journal] = []
        for jf in journal_files:
            try:
                jd = json.load(open(jf, "r", encoding="utf-8"))
                if isinstance(jd, list):
                    out.extend([_parse_journal_dict(x, assets_dir=assets_dir, root_dir=root_dir) for x in jd])
                elif isinstance(jd, dict):
                    out.append(_parse_journal_dict(jd, assets_dir=assets_dir, root_dir=root_dir))
            except Exception:
                # ignore broken journal jsons but continue
                continue
        if not out:
            raise ValueError("No journals could be parsed from folder export")
        return out


    # Two shapes:
    # 1) single journal dict: {name, pages:[...]}
    # 2) folder export list: [{name, pages:[...]}, ...]
    if isinstance(data, list):
        return [_parse_journal_dict(d, assets_dir=assets_dir, root_dir=root_dir) for d in data]

    return _parse_journal_dict(data, assets_dir=assets_dir, root_dir=root_dir)


def _parse_journal_dict(d: dict, assets_dir: Optional[str], root_dir: Optional[str]) -> Journal:
    title = d.get("name") or "FVTT Journal"
    pages_raw = d.get("pages") or []
    pages: List[PageNode] = []

    for pr in pages_raw:
        ptitle = pr.get("name") or "Page"
        sort = int(pr.get("sort") or 0)
        # Foundry sometimes stores text as string, but in this export it's {"content": "..."}
        text_obj = pr.get("text") or {}
        if isinstance(text_obj, dict):
            html_src = text_obj.get("content") or ""
        else:
            html_src = str(text_obj)

        headings = _split_into_headings(html_src)
        pages.append(PageNode(title=ptitle, sort=sort, headings=headings))

    pages.sort(key=lambda x: x.sort)

    return Journal(title=title, pages=pages, assets_dir=assets_dir, root_dir=root_dir)
