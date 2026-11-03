"""Turning files and web pages into knowledge text (K-series): plain text, Markdown, HTML and PDF.

Only the visible text is kept. HTML loses its scripts, styles, navigation, headers and footers, forms and hidden elements; headings, lists and tables
become Markdown-style text so the passage splitter can keep a heading trail with each passage. A PDF contributes its text layer (a scanned PDF with no
text is refused rather than stored empty). Files are recognised by their content, not their name, and sizes are capped. The text is untrusted data like
everything else an agent reads: it reaches the model through the same output checks as any tool result.
"""
from __future__ import annotations

import asyncio
import html
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser

MAX_FILE_BYTES = {"pdf": 10 * 1024 * 1024, "html": 2 * 1024 * 1024, "text": 2 * 1024 * 1024, "docx": 10 * 1024 * 1024, "pptx": 10 * 1024 * 1024, "xlsx": 10 * 1024 * 1024}
OFFICE = ("docx", "pptx", "xlsx")
MAX_PART_BYTES, MAX_UNPACKED = 12 * 1024 * 1024, 40 * 1024 * 1024
MAX_SHEET_ROWS, MAX_SHEET_COLS = 3000, 60
MAX_PDF_PAGES = 300
PDF_TIMEOUT = 25.0
SKIP = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "object", "embed", "form", "select", "option", "button", "nav", "header", "footer", "aside", "dialog"}
VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
BLOCK = {"p", "div", "section", "article", "main", "ul", "ol", "table", "blockquote", "pre", "figure", "figcaption", "dl", "dt", "dd", "body"}
HIDDEN = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d])|opacity\s*:\s*0(?![.\d])", re.I)


class IngestError(ValueError):
    """The file or page could not be used. The message is safe to show."""


@dataclass
class Extracted:
    title: str
    text: str
    kind: str  # text | html | pdf | docx | pptx | xlsx
    links: list[str]


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.title = ""
        self.h1 = ""
        self.links: list[str] = []
        self._skip: list[str] = []      # stack of tags we are inside that hide their content
        self._tag_stack: list[str] = []
        self._in_title = False
        self._heading: int | None = None
        self._cell = False

    def _emit(self, s: str) -> None:
        if not self._skip:
            self.out.append(s)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "a" and a.get("href") and not self._skip:
            self.links.append(a["href"])  # (links inside navigation are still useful for crawling, so they are taken before the skip check below)
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in VOID:
            if tag == "br":
                self._emit("\n")
            elif tag == "hr":
                self._emit("\n\n")
            return
        hidden = tag in SKIP or "hidden" in a or a.get("aria-hidden") == "true" or bool(HIDDEN.search(a.get("style", "")))
        self._tag_stack.append(tag)
        if hidden:
            self._skip.append(tag)
            return
        if tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading = int(tag[1])
            self._emit("\n\n" + "#" * self._heading + " ")
        elif tag == "li":
            self._emit("\n- ")
        elif tag in ("td", "th"):
            self._emit(" | " if self._cell else "")
            self._cell = True
        elif tag == "tr":
            self._cell = False
            self._emit("\n")
        elif tag in BLOCK:
            self._emit("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID or tag not in self._tag_stack:
            return
        while self._tag_stack:  # close any unclosed children too
            top = self._tag_stack.pop()
            if self._skip and self._skip[-1] == top:
                self._skip.pop()
            if top == "title":
                self._in_title = False
            if top == tag:
                break
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading = None
            self._emit("\n\n")
        elif tag in BLOCK:
            self._emit("\n\n")

    def handle_data(self, data: str) -> None:
        if self._in_title and not self._skip:
            self.title += data
            return
        if self._skip:
            return
        if self._heading == 1 and not self.h1:
            self.h1 += data
        self._emit(data)


def _tidy(text: str) -> str:
    text = text.replace("\r", "").replace("\x00", "")
    text = re.sub(r"[ \t\f\v ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def from_html(raw: str, fallback_title: str = "") -> Extracted:
    p = _Page()
    try:
        p.feed(raw)
        p.close()
    except Exception as e:  # the parser is lenient; anything it still chokes on is not worth keeping
        raise IngestError("The page could not be read") from e
    text = _tidy("".join(p.out))
    title = html.unescape(re.sub(r"\s+", " ", p.title or p.h1 or fallback_title)).strip()[:200]
    if not text:
        raise IngestError("The page has no readable text")
    return Extracted(title or fallback_title or "Untitled", text, "html", p.links)


def _pdf_text(data: bytes) -> tuple[str, str]:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise IngestError("The PDF is password protected")
        pages = reader.pages
        if len(pages) > MAX_PDF_PAGES:
            raise IngestError(f"The PDF has more than {MAX_PDF_PAGES} pages; split it")
        out = []
        for page in pages:
            out.append(page.extract_text() or "")
        title = str((reader.metadata.title if reader.metadata else "") or "")[:200]
    except IngestError:
        raise
    except Exception as e:
        raise IngestError("The PDF could not be read") from e
    return "\n\n".join(out), title


async def from_pdf(data: bytes, fallback_title: str = "") -> Extracted:
    try:
        text, title = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, _pdf_text, data), PDF_TIMEOUT)
    except asyncio.TimeoutError as e:
        raise IngestError("The PDF took too long to read") from e
    text = _tidy(text)
    if len(text) < 20:
        raise IngestError("The PDF has no text to read (is it a scan? it needs text recognition first)")
    return Extracted(title.strip() or fallback_title or "Untitled", text, "pdf", [])


def sniff(data: bytes, name: str = "", content_type: str = "") -> str:
    """text | html | pdf, from the bytes (the name and type only break ties between text and Markdown)."""
    if not data:
        raise IngestError("The file is empty")
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return office_kind(data)
    for magic in (b"MZ", b"\x7fELF", b"\x1f\x8b", b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"Rar!", b"\xd0\xcf\x11\xe0"):
        if data.startswith(magic):
            raise IngestError("Only PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML, Markdown and plain text files can be imported")
    window = data[:4096]
    try:
        head = window.decode("utf-8", "strict")
    except UnicodeDecodeError as e:
        if e.start < len(window) - 3 or len(data) <= len(window):  # (a character cut in two by the end of the window is fine)
            raise IngestError("Only PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML, Markdown and plain text files can be imported") from None
        head = window[: e.start].decode("utf-8")
    if "\x00" in head:
        raise IngestError("Only PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML, Markdown and plain text files can be imported")
    lowered = head.lstrip().lower()
    if "html" in content_type.lower() or name.lower().endswith((".html", ".htm")) or lowered.startswith(("<!doctype html", "<html")) or ("<body" in lowered[:2000] and "</" in lowered):
        return "html"
    return "text"


def office_kind(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
    except (zipfile.BadZipFile, ValueError, RuntimeError):
        raise IngestError("This file could not be read as an Office document") from None
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if any(n.startswith("ppt/slides/slide") for n in names):
        return "pptx"
    raise IngestError("Only PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML, Markdown and plain text files can be imported")


def _part(z: zipfile.ZipFile, name: str) -> ET.Element | None:
    """One XML part, read with a size cap and without any entity or DOCTYPE (so it cannot expand or fetch anything)."""
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART_BYTES:
        raise IngestError("A part of this document is too large to read")
    with z.open(info) as f:
        raw = f.read(MAX_PART_BYTES + 1)
    if len(raw) > MAX_PART_BYTES:
        raise IngestError("A part of this document is too large to read")
    if re.search(rb"<!DOCTYPE|<!ENTITY", raw[:4096] + raw[-256:], re.I) or b"<!ENTITY" in raw:
        raise IngestError("This document uses features that are not accepted")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise IngestError("This document is damaged") from None


def _q(ns: str, tag: str) -> str:
    return "{" + ns + "}" + tag


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DC = "http://purl.org/dc/elements/1.1/"


def _title(z: zipfile.ZipFile) -> str:
    core = _part(z, "docProps/core.xml")
    t = core.find(_q(DC, "title")) if core is not None else None
    return (t.text or "").strip()[:200] if t is not None else ""


def _docx(z: zipfile.ZipFile) -> str:
    root = _part(z, "word/document.xml")
    body = root.find(_q(W, "body")) if root is not None else None
    if body is None:
        raise IngestError("The Word document has no text")

    def para(p: ET.Element) -> str:
        out = []
        for el in p.iter():
            if el.tag == _q(W, "t"):
                out.append(el.text or "")
            elif el.tag in (_q(W, "tab"),):
                out.append("\t")
            elif el.tag in (_q(W, "br"), _q(W, "cr")):
                out.append(" ")
        return "".join(out).strip()

    lines: list[str] = []
    for el in body:
        if el.tag == _q(W, "p"):
            t = para(el)
            if not t:
                lines.append("")
                continue
            style = el.find(f"{{{W}}}pPr/{{{W}}}pStyle")
            val = (style.get(_q(W, "val")) if style is not None else "") or ""
            m = re.fullmatch(r"(?:Heading|heading)\s?(\d)", val) or (re.fullmatch(r"(Title)", val) and None)
            if val == "Title":
                lines.append(f"# {t}")
            elif m:
                lines.append("#" * min(6, int(m.group(1))) + f" {t}")
            elif el.find(f"{{{W}}}pPr/{{{W}}}numPr") is not None:
                lines.append(f"- {t}")
            else:
                lines.append(t)
        elif el.tag == _q(W, "tbl"):
            for row in el.iter(_q(W, "tr")):
                cells = [" ".join(para(p) for p in c.iter(_q(W, "p")) if para(p)) for c in row.iter(_q(W, "tc"))]
                if any(cells):
                    lines.append(" | ".join(cells))
            lines.append("")
    return "\n".join(lines)


def _pptx(z: zipfile.ZipFile) -> str:
    slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))
    out = []
    for i, n in enumerate(slides[:300], 1):
        root = _part(z, n)
        paras = []
        for p in (root.iter(_q(A, "p")) if root is not None else []):
            t = "".join(x.text or "" for x in p.iter(_q(A, "t"))).strip()
            if t:
                paras.append(t)
        if paras:
            out.append(f"## Slide {i}: {paras[0][:120]}\n\n" + "\n".join(paras[1:] or [paras[0]]))
    return "\n\n".join(out)  # speaker notes are deliberately not read: they are often private


def _xlsx(z: zipfile.ZipFile) -> str:
    shared: list[str] = []
    ss = _part(z, "xl/sharedStrings.xml")
    if ss is not None:
        shared = ["".join(t.text or "" for t in si.iter(_q(S, "t"))) for si in ss.iter(_q(S, "si"))]
    wb = _part(z, "xl/workbook.xml")
    rels = _part(z, "xl/_rels/workbook.xml.rels")
    targets = {r.get("Id"): r.get("Target") for r in (rels if rels is not None else [])}
    out = []
    for sh in (wb.iter(_q(S, "sheet")) if wb is not None else []):
        if sh.get("state") in ("hidden", "veryHidden"):
            continue
        rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = (targets.get(rid) or "").lstrip("/")
        path = target if target.startswith("xl/") else "xl/" + target
        root = _part(z, path) if target else None
        rows = []
        for r_i, row in enumerate(root.iter(_q(S, "row")) if root is not None else []):
            if r_i >= MAX_SHEET_ROWS:
                rows.append("(more rows not read)")
                break
            vals = []
            for c in list(row)[:MAX_SHEET_COLS]:
                t = c.get("t")
                v = c.find(_q(S, "v"))
                if t == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                    vals.append(shared[int(v.text)])
                elif t == "inlineStr":
                    vals.append("".join(x.text or "" for x in c.iter(_q(S, "t"))))
                else:
                    vals.append((v.text or "") if v is not None else "")
            if any(x.strip() for x in vals):
                rows.append(" | ".join(x.strip() for x in vals))
        if rows:
            out.append(f"## {sh.get('name', 'Sheet')[:100]}\n\n" + "\n".join(rows))
    return "\n\n".join(out)


def from_office(data: bytes, kind: str, fallback_title: str = "") -> Extracted:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED or len(z.infolist()) > 5000:
                raise IngestError("This document is too large once unpacked")
            text = {"docx": _docx, "pptx": _pptx, "xlsx": _xlsx}[kind](z)
            title = _title(z)
    except IngestError:
        raise
    except (zipfile.BadZipFile, ValueError, RuntimeError, KeyError, OSError):
        raise IngestError("This file could not be read as an Office document") from None
    text = _tidy(text)
    if len(text) < 5:
        raise IngestError(f"The {kind} file has no text to read")
    if not title:
        first = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
        title = fallback_title or first[:200]
    return Extracted(title or "Untitled", text, kind, [])


async def extract(data: bytes, name: str = "", content_type: str = "") -> Extracted:
    kind = sniff(data, name, content_type)
    if len(data) > MAX_FILE_BYTES[kind]:
        raise IngestError(f"A {kind if kind != 'text' else 'text'} file can be at most {MAX_FILE_BYTES[kind] // 1024 // 1024} MB to import")
    fallback = re.sub(r"[_-]+", " ", re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name.rsplit("/", 1)[-1])).strip()[:200]
    if kind == "pdf":
        return await from_pdf(data, fallback)
    if kind in OFFICE:
        return await asyncio.get_running_loop().run_in_executor(None, from_office, data, kind, fallback)
    text = data.decode("utf-8", "replace")
    if kind == "html":
        return from_html(text, fallback)
    text = _tidy(text)
    if not text:
        raise IngestError("The file has no text")
    first = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
    return Extracted((first[:200] if text.lstrip().startswith("#") else fallback) or "Untitled", text, "text", [])
