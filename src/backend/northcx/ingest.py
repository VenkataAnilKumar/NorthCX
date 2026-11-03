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
from dataclasses import dataclass
from html.parser import HTMLParser

MAX_FILE_BYTES = {"pdf": 10 * 1024 * 1024, "html": 2 * 1024 * 1024, "text": 2 * 1024 * 1024}
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
    kind: str  # text | html | pdf
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
    for magic in (b"MZ", b"\x7fELF", b"PK\x03\x04", b"\x1f\x8b", b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"Rar!", b"\xd0\xcf\x11\xe0"):
        if data.startswith(magic):
            raise IngestError("Only PDF, HTML, Markdown and plain text files can be imported")
    window = data[:4096]
    try:
        head = window.decode("utf-8", "strict")
    except UnicodeDecodeError as e:
        if e.start < len(window) - 3 or len(data) <= len(window):  # (a character cut in two by the end of the window is fine)
            raise IngestError("Only PDF, HTML, Markdown and plain text files can be imported") from None
        head = window[: e.start].decode("utf-8")
    if "\x00" in head:
        raise IngestError("Only PDF, HTML, Markdown and plain text files can be imported")
    lowered = head.lstrip().lower()
    if "html" in content_type.lower() or name.lower().endswith((".html", ".htm")) or lowered.startswith(("<!doctype html", "<html")) or ("<body" in lowered[:2000] and "</" in lowered):
        return "html"
    return "text"


async def extract(data: bytes, name: str = "", content_type: str = "") -> Extracted:
    kind = sniff(data, name, content_type)
    if len(data) > MAX_FILE_BYTES[kind]:
        raise IngestError(f"A {kind if kind != 'text' else 'text'} file can be at most {MAX_FILE_BYTES[kind] // 1024 // 1024} MB to import")
    fallback = re.sub(r"[_-]+", " ", re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name.rsplit("/", 1)[-1])).strip()[:200]
    if kind == "pdf":
        return await from_pdf(data, fallback)
    text = data.decode("utf-8", "replace")
    if kind == "html":
        return from_html(text, fallback)
    text = _tidy(text)
    if not text:
        raise IngestError("The file has no text")
    first = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
    return Extracted((first[:200] if text.lstrip().startswith("#") else fallback) or "Untitled", text, "text", [])
