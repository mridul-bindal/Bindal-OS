"""Extract typed blocks directly from HTML and a plain-text view for storage."""
import re
from bs4 import BeautifulSoup, Comment, NavigableString


def clean_text(text: str) -> str:
    return "\n".join(line for raw in text.splitlines()
                     if (line := re.sub(r"[^\S\n]+", " ", raw).strip()))


def extract_structured_content(html: str) -> tuple[str, str, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.title.get_text()) if soup.title else ""
    for node in soup.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()
    for node in soup.select("script, style, noscript, nav, aside, footer, head, iframe, svg, template, form, [role='navigation'], [hidden], [aria-hidden='true']"):
        if node.parent is not None:
            node.decompose()
    # Prefer explicit article-body markup over broad layout containers.
    root = (soup.select_one('[itemprop="articleBody"]') or soup.find("article")
            or soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup)
    # Some publishers use unsemantic divs for their article and sidebars.
    # Generic fallback: choose an H1-containing container with substantial prose
    # and low link density, preferring the deepest eligible container.
    if root is soup or root is soup.body:
        heading = root.find("h1")
        if heading:
            for parent in heading.parents:
                if parent is soup:
                    break
                length = len(parent.get_text())
                link_length = sum(len(a.get_text()) for a in parent.find_all("a"))
                if length > 300 and len(parent.find_all("p")) >= 2 and link_length / length < .3:
                    root = parent
                    break
    for node in root.select('[role="complementary"], [role="contentinfo"], .sidebar, .table-of-contents, .toc, .breadcrumb, .breadcrumbs'):
        if node.parent is not None:
            node.decompose()
    if not title:
        heading = root.find("h1")
        title = clean_text(heading.get_text()) if heading else ""

    def inline(node):
        if isinstance(node, NavigableString):
            return re.sub(r"\s+", " ", str(node))
        if node.name == "br":
            return "\n"
        return "".join(inline(child) for child in node.children)

    blocks = []
    def add(kind, value, **metadata):
        value = value.strip("\n") if kind == "code" else clean_text(value)
        if value.strip():
            blocks.append({"kind": kind, "text": value, **metadata})

    def walk(node):
        if isinstance(node, NavigableString):
            add("paragraph", str(node))
            return
        if node.name in {"h1", "h2", "h3"}:
            add("heading", inline(node), level=int(node.name[1]))
        elif node.name == "pre":
            code = node.get_text().replace("\r\n", "\n").replace("\r", "\n")
            add("code", "\n".join(line for line in code.splitlines() if line.strip()))
        elif node.name in {"ul", "ol"}:
            items = node.find_all("li", recursive=False)
            add("list", "\n".join(inline(li) for li in items), ordered=node.name == "ol")
        elif node.name in {"p", "h4", "h5", "h6", "blockquote"}:
            add("paragraph", inline(node))
        elif node.name == "table":
            add("list", "\n".join(" | ".join(inline(cell) for cell in row.find_all(["td", "th"]))
                                    for row in node.find_all("tr")))
        else:
            # Accumulate inline siblings without losing spaces or punctuation.
            pending = []
            for child in node.children:
                if isinstance(child, NavigableString) or child.name in {"a", "span", "b", "strong", "em", "i", "code", "br"}:
                    pending.append(inline(child))
                else:
                    add("paragraph", "".join(pending))
                    pending = []
                    walk(child)
            add("paragraph", "".join(pending))
    walk(root)
    return title, "\n".join(block["text"] for block in blocks), blocks


def extract_content(html: str) -> tuple[str, str]:
    """Compatibility view for callers needing only title/text."""
    title, text, _ = extract_structured_content(html)
    return title, text
