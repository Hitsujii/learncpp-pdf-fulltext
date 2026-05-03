import html as html_lib
import typing as ty

from selectolax.lexbor import LexborHTMLParser, LexborNode

from book.config import frozen
from book.errors import HTMLParsingError


PRINT_CSS = """
@page {
  size: A4;
  margin: 13mm 12mm 15mm 12mm;
}

html,
body {
  background: #ffffff !important;
  color: #242938 !important;
  font-family: DejaVu Sans, Liberation Sans, Arial, sans-serif !important;
  font-size: 10.5pt !important;
  line-height: 1.45 !important;
}

body {
  margin: 0 !important;
  padding: 0 !important;
}

* {
  box-sizing: border-box !important;
  text-shadow: none !important;
  animation: none !important;
  transition: none !important;
}

main.pdf-document {
  width: 100% !important;
  max-width: 100% !important;
  margin: 0 auto !important;
  padding: 0 !important;
}

article,
.entry-content,
.post,
.page,
.site-main,
.content-area {
  width: auto !important;
  max-width: none !important;
  margin: 0 !important;
  padding: 0 !important;
  border: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
}

h1,
h2,
h3,
h4,
h5,
h6 {
  color: #242938 !important;
  font-family: DejaVu Sans, Liberation Sans, Arial, sans-serif !important;
  font-weight: 700 !important;
  line-height: 1.25 !important;
  page-break-after: avoid !important;
  break-after: avoid !important;
}

h1 {
  font-size: 22pt !important;
  margin: 0 0 8mm 0 !important;
}

h2 {
  font-size: 17pt !important;
  margin: 9mm 0 3mm 0 !important;
}

h3 {
  font-size: 14pt !important;
  margin: 7mm 0 2.5mm 0 !important;
}

h4,
h5,
h6 {
  font-size: 12pt !important;
  margin: 5mm 0 2mm 0 !important;
}

p,
li,
dd,
dt,
blockquote,
td,
th {
  font-size: 10.5pt !important;
}

p {
  margin: 0 0 3.5mm 0 !important;
}

ul,
ol {
  margin: 0 0 4mm 6mm !important;
  padding-left: 5mm !important;
}

li {
  margin: 0 0 2mm 0 !important;
  padding-left: 1mm !important;
}

a {
  color: inherit !important;
  text-decoration: underline !important;
  overflow-wrap: anywhere !important;
}

img,
svg {
  max-width: 100% !important;
  height: auto !important;
  page-break-inside: avoid !important;
  break-inside: avoid !important;
}

table {
  width: 100% !important;
  border-collapse: collapse !important;
  margin: 4mm 0 !important;
  page-break-inside: auto !important;
  break-inside: auto !important;
}

tr {
  page-break-inside: avoid !important;
  break-inside: avoid !important;
}

td,
th {
  border: 1px solid #d8d8d8 !important;
  padding: 2mm !important;
  vertical-align: top !important;
}

blockquote {
  margin: 5mm 0 !important;
  padding: 4mm 6mm !important;
  border-left: 3px solid #cfcfcf !important;
  background: #f7f7f7 !important;
  page-break-inside: avoid !important;
  break-inside: avoid !important;
}

pre,
code,
kbd,
samp,
pre *,
code * {
  font-family: DejaVu Sans Mono, Liberation Mono, Consolas, monospace !important;
  font-variant-ligatures: none !important;
  text-rendering: optimizeLegibility !important;
}

code,
kbd,
samp {
  font-size: 9.5pt !important;
  background: #f2f2f2 !important;
  border-radius: 2px !important;
  padding: 0.2mm 0.8mm !important;
}

pre {
  display: block !important;
  width: 100% !important;
  max-width: 100% !important;
  margin: 4mm 0 !important;
  padding: 3mm !important;
  white-space: pre-wrap !important;
  overflow: visible !important;
  word-break: normal !important;
  overflow-wrap: anywhere !important;
  color: #111111 !important;
  background: #f6f6f6 !important;
  border: 1px solid #d6d6d6 !important;
  border-radius: 3px !important;
  page-break-inside: avoid !important;
  break-inside: avoid !important;
}

pre code {
  display: inline !important;
  padding: 0 !important;
  background: transparent !important;
  border: 0 !important;
  white-space: inherit !important;
}

.entry-meta,
.post-meta,
.byline,
.author,
.published,
.updated {
  color: #444444 !important;
  font-size: 8.5pt !important;
  margin-bottom: 5mm !important;
}

hr {
  border: 0 !important;
  border-top: 1px solid #d8d8d8 !important;
  margin: 5mm 0 !important;
}

.prevnext,
.comments-area,
.comment-respond,
.sharedaddy,
.jp-relatedposts,
.yarpp-related,
.post-navigation,
.navigation,
.nav-links,
.sidebar,
.widget-area,
#secondary,
#comments,
#respond,
.cryout,
.adsbygoogle,
.ad,
.advertisement,
.toolbar,
.copy-code-button,
.copy-the-code-button,
.code-copy,
.enlighter-btn-raw,
.enlighter-toolbar,
button {
  display: none !important;
}

[class*="line-numbers-rows"],
[class*="copy"],
[class*="toolbar"] {
  display: none !important;
}

@media print {
  body {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
}
"""


@frozen
class Post:
    _REMOVE_ELEMENTS: ty.ClassVar[list[str]] = [
        "script",
        "noscript",
        "style",
        'link[rel="stylesheet"]',
        "header.cryout",
        ".entry-content > .prevnext",
        ".comments-area",
        ".comment-respond",
        ".sharedaddy",
        ".jp-relatedposts",
        ".yarpp-related",
        ".post-navigation",
        ".navigation",
        ".nav-links",
        ".sidebar",
        ".widget-area",
        "#secondary",
        "#comments",
        "#respond",
        ".adsbygoogle",
        ".ad",
        ".advertisement",
        ".toolbar",
        ".copy-code-button",
        ".copy-the-code-button",
        ".code-copy",
        ".enlighter-btn-raw",
        ".enlighter-toolbar",
        "button",
    ]

    name: str
    root: LexborNode

    @property
    def html(self) -> str:
        assert self.root.html
        return self.root.html

    def remove_elements(self) -> None:
        for selector in self._REMOVE_ELEMENTS:
            for node in list(self.root.css(selector)):
                node.decompose()

    def _first(self, selectors: tuple[str, ...]) -> LexborNode | None:
        for selector in selectors:
            node = self.root.css_first(selector)
            if node is not None:
                return node
        return None

    @property
    def title(self) -> str:
        node = self._first(
            (
                "h1.entry-title",
                "article h1",
                "main h1",
                "h1",
                "title",
            )
        )
        if node is None:
            return self.name
        title = node.text(strip=True)
        return title or self.name

    @property
    def article_html(self) -> str:
        node = self._first(
            (
                "article",
                "main article",
                ".site-main article",
                ".content-area article",
                ".entry-content",
                "main",
                "body",
            )
        )
        if node is None or not node.html:
            return self.html
        return node.html

    def to_pdf_html(self, *, base_url: str) -> str:
        title = html_lib.escape(self.title, quote=True)
        base_href = html_lib.escape(base_url.rstrip("/") + "/", quote=True)

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <base href="{base_href}">
  <title>{title}</title>
  <style>
{PRINT_CSS}
  </style>
</head>
<body>
  <main class="pdf-document">
    {self.article_html}
  </main>
</body>
</html>
"""

    @classmethod
    def parse_html(cls, *, name: str, text: str) -> "Post":
        root = LexborHTMLParser(text).root
        assert root
        return cls(name=name, root=root)  # type: ignore


@frozen
class Chapter:
    no: str
    title: str
    link: str

    @property
    def filename(self) -> str:
        no = self.no.replace(".", "_").replace(" ", "_")
        return f"{no}.html"

    @classmethod
    def from_node(cls, chapter_node: LexborNode) -> "Chapter":
        number_node = chapter_node.css_first("div.lessontable-row-number")
        title_node = chapter_node.css_first("div.lessontable-row-title")

        if number_node is None or title_node is None:
            raise HTMLParsingError("Invalid chapter row")

        chapter_no = number_node.text(strip=True)
        title = title_node.text(strip=True)

        link_node = title_node.css_first('a[href^="https://www.learncpp.com/cpp-tutorial/"]')
        if link_node is None:
            raise HTMLParsingError(f"Missing link for chapter {chapter_no}: {title}")

        link = link_node.attributes.get("href")
        if not link:
            raise HTMLParsingError(f"Invalid link for {title}: {link}")

        return cls(no=chapter_no, title=title, link=link)  # type: ignore


@frozen
class ChapterTable:
    "A group of chapters, e.g. Chapter 28.*"

    name: str
    chapters: tuple[Chapter, ...]

    @classmethod
    def from_node(cls, table_node: LexborNode) -> "ChapterTable":
        table_name_node = table_node.css_first('div.lessontable-header > a[name*="Chapter"]')
        if table_name_node is None:
            raise HTMLParsingError("Missing chapter table name")

        table_name = table_name_node.attributes.get("name")
        if not table_name:
            raise HTMLParsingError(f"Invalid table name: {table_name}")

        chapter_nodes = table_node.select("div.lessontable-row").matches
        chapters = tuple(
            Chapter.from_node(chapter_node) for chapter_node in chapter_nodes
        )

        return cls(name=table_name, chapters=chapters)  # type: ignore


@frozen
class OutLinePage:
    root: LexborNode

    def content_tables(self):
        tables = self.root.select("div.lessontable").matches
        for table in tables:
            yield ChapterTable.from_node(table)

    @classmethod
    def parse_html(cls, text: str) -> "OutLinePage":
        outline_dom = LexborHTMLParser(text)
        if not outline_dom.body:
            raise HTMLParsingError("Failed to parse the html of the outline page")

        content_nodes = outline_dom.body.select("div.entry-content").matches
        if not content_nodes:
            raise HTMLParsingError("Failed to find div.entry-content in outline page")

        return cls(root=content_nodes[0])  # type: ignore