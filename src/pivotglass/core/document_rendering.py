"""Safe, analyst-facing renderings of untrusted source documents.

This module is the single authority for turning stored or previewed source
bytes into something a browser may display. Threat reports are hostile
content, so every rendering obeys the same rules:

- no script, event handler, style attribute, form, or embedded object survives;
- nothing in a rendering can cause a network fetch (no ``src``, ``href``,
  ``srcset``, ``url()``, ``<link>``, ``<base>`` or ``<meta>``);
- links are inert labelled text; images become CSS-generated placeholders so
  their alt text never enters the DOM text that indicator anchoring searches.

Two anchoring contracts exist and the payload says which one applies:

``exact``
    The client renders ``output_text`` itself, so candidate ``start_char`` and
    ``end_char`` offsets locate the indicator exactly.
``ordinal``
    The rendering's visible text differs from ``output_text`` (Markdown syntax
    removed, HTML whitespace collapsed, PDF page layout). The client locates the
    n-th occurrence of the candidate's raw value, where n is that candidate's
    occurrence ordinal in ``output_text``. A value the rendering cannot locate is
    reported as not located, never guessed.

@decision DEC-DOC-RENDER-001
@title Render untrusted documents through one sanitizing authority plus a script-less sandbox
@status accepted
@rationale v1.2.0 never placed source bytes in the DOM, which kept the browser
           safe but left analysts reading a plain ``<pre>``. Indicator focus mode
           needs the document as the author laid it out. Sanitizing server-side
           with an allowlist, then displaying inside ``<iframe sandbox>`` without
           ``allow-scripts``, gives two independent barriers. PDF bytes are drawn
           by pdf.js 6 onto a canvas; that release has no eval code path and
           the document-scripting sandbox is never loaded, so PDF JavaScript
           and XFA forms do not run.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser
from typing import Literal

from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict

from pivotglass.core.document_ingestion import DocumentLimits, decode_text, email_body_parts

RENDERING_VERSION = "pivotglass-safe-render-1.0"
MAX_RENDERED_HTML_CHARS = 4_000_000

_ALLOWED_TAGS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "caption", "cite", "code", "dd", "del",
        "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5",
        "h6", "hr", "i", "ins", "kbd", "li", "ol", "p", "pre", "q", "s", "samp",
        "section", "article", "header", "footer", "main", "aside", "nav", "small",
        "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead",
        "title", "tr", "u", "ul", "var", "time", "mark",
    }
)
_VOID_TAGS = frozenset({"br", "hr", "img", "input", "meta", "link", "base", "source", "wbr"})
# Content of these elements is dropped entirely. The set matches the plain-text
# extractor in ``document_ingestion`` so the rendering's visible text stays in
# the same order as ``output_text``.
_DROP_CONTENT_TAGS = frozenset({"script", "style", "noscript", "template"})
_MEDIA_TAGS = frozenset({"img", "picture", "video", "audio", "svg", "canvas", "iframe", "object", "embed"})
_SPAN_ATTRIBUTES = frozenset({"colspan", "rowspan"})


class DocumentRendering(BaseModel):
    """Browser-safe presentation of one document."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["pivotglass-document-rendering-1.0"] = (
        "pivotglass-document-rendering-1.0"
    )
    renderer_version: str = RENDERING_VERSION
    kind: Literal["text", "html", "pdf"]
    anchoring: Literal["exact", "ordinal"]
    html: str | None = None
    notes: tuple[str, ...] = ()


class _Sanitizer(HTMLParser):
    """Re-emit an allowlisted, inert subset of untrusted HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._stack: list[str] = []
        self._drop_depth = 0
        self.media = 0
        self.links = 0
        self.removed: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.casefold()
        if name in _DROP_CONTENT_TAGS:
            self._drop_depth += 1
            self.removed.add(name)
            return
        if self._drop_depth:
            return
        if name in _MEDIA_TAGS:
            self.media += 1
            label = dict(attrs).get("alt") or dict(attrs).get("title") or name
            # Rendered through CSS ``attr()`` so the label is not DOM text.
            self.out.append(
                f'<span class="pg-media" data-label="{html.escape(label[:120], quote=True)}"></span>'
            )
            return
        if name == "a":
            self.links += 1
            href = dict(attrs).get("href") or ""
            self.out.append(f'<span class="pg-link" title="{html.escape(href[:2048], quote=True)}">')
            self._stack.append("a")
            return
        if name not in _ALLOWED_TAGS:
            if name not in _VOID_TAGS:
                self.removed.add(name)
            return
        if name in _VOID_TAGS:
            self.out.append(f"<{name}>")
            return
        kept = "".join(
            f' {key}="{value}"'
            for key, value in attrs
            if key in _SPAN_ATTRIBUTES and value and value.isdigit() and len(value) <= 3
        )
        if name == "title":
            self.out.append('<div class="pg-title">')
        else:
            self.out.append(f"<{name}{kept}>")
        self._stack.append(name)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in _VOID_TAGS and tag.casefold() not in _MEDIA_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name in _DROP_CONTENT_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if self._drop_depth or name not in self._stack:
            return
        while self._stack:
            open_tag = self._stack.pop()
            self.out.append(self._close(open_tag))
            if open_tag == name:
                break

    def handle_data(self, data: str) -> None:
        if not self._drop_depth:
            self.out.append(html.escape(data, quote=False))

    @staticmethod
    def _close(tag: str) -> str:
        return "</span>" if tag == "a" else "</div>" if tag == "title" else f"</{tag}>"

    def result(self) -> str:
        self.close()
        while self._stack:
            self.out.append(self._close(self._stack.pop()))
        return "".join(self.out)


def sanitize_html(source: str) -> tuple[str, tuple[str, ...]]:
    """Return inert HTML and analyst-facing notes about what was neutralized."""

    sanitizer = _Sanitizer()
    sanitizer.feed(source)
    rendered = sanitizer.result()
    notes: list[str] = []
    if sanitizer.media:
        notes.append(f"{sanitizer.media} embedded media item(s) shown as placeholders; nothing was fetched.")
    if sanitizer.links:
        notes.append(f"{sanitizer.links} link(s) are inert; hover shows the original target.")
    active = sorted(sanitizer.removed & {"script", "style", "iframe", "object", "embed", "form"})
    if active:
        notes.append("Removed active content: " + ", ".join(active) + ".")
    return rendered, tuple(notes)


_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable(
    ["table", "strikethrough"]
)


def render_document(
    data: bytes,
    *,
    media_type: str,
    output_text: str,
) -> DocumentRendering:
    """Build the safe rendering for one parsed document.

    ``data`` is used only for formats whose layout is lost in ``output_text``.
    Everything else renders from the parser output so offsets stay exact.
    """

    if media_type == "application/pdf":
        return DocumentRendering(
            kind="pdf",
            anchoring="ordinal",
            notes=("Pages are drawn by the built-in PDF viewer with document scripts disabled.",),
        )
    if media_type in {"text/markdown", "text/html"}:
        if media_type == "text/markdown":
            source = _MARKDOWN.render(output_text)
        else:
            source = decode_text(data, [])
        rendered, notes = sanitize_html(source)
        if len(rendered) > MAX_RENDERED_HTML_CHARS:
            return DocumentRendering(
                kind="text",
                anchoring="exact",
                notes=("Rendered layout exceeded the display limit; showing extracted text.",),
            )
        return DocumentRendering(kind="html", anchoring="ordinal", html=rendered, notes=notes)
    if media_type == "message/rfc822":
        return _render_email(data)
    return DocumentRendering(kind="text", anchoring="exact")


def _render_email(data: bytes) -> DocumentRendering:
    """Headers, then every body part in parser order (#28).

    Parts appear in the order ``output_text`` lists them, so ordinal anchoring
    holds: a ``multipart/alternative`` message shows its plain-text and HTML
    versions one after the other, each labelled. A message with no HTML part
    keeps the exact plain-text view.
    """

    headers, body, _warnings, _skipped = email_body_parts(data, DocumentLimits())
    if not any(media_type == "text/html" for media_type, _text in body):
        return DocumentRendering(kind="text", anchoring="exact")
    notes: list[str] = []
    pieces = ['<header class="email-headers"><dl>']
    for name, value in headers:
        pieces.append(f"<dt>{html.escape(name)}:</dt><dd>{html.escape(value)}</dd>")
    pieces.append("</dl></header>")
    for media_type, text in body:
        if media_type == "text/html":
            rendered, part_notes = sanitize_html(text)
            notes.extend(note for note in part_notes if note not in notes)
            pieces.append(f'<section class="email-part email-html">{rendered}</section>')
        else:
            pieces.append(f'<section class="email-part email-plain"><pre>{html.escape(text)}</pre></section>')
    rendered_message = "".join(pieces)
    if len(rendered_message) > MAX_RENDERED_HTML_CHARS:
        return DocumentRendering(
            kind="text",
            anchoring="exact",
            notes=("Rendered message exceeded the display limit; showing extracted text.",),
        )
    if sum(media_type == "text/html" for media_type, _text in body) and any(
        media_type == "text/plain" for media_type, _text in body
    ):
        notes.insert(0, "The message carries plain-text and HTML versions; both are shown in message order.")
    return DocumentRendering(kind="html", anchoring="ordinal", html=rendered_message, notes=tuple(notes))
