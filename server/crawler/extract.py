"""Conservative HTML content extraction; no JavaScript execution."""
import re
from bs4 import BeautifulSoup, Comment, NavigableString


def clean_text(text: str) -> str:
    """Collapse horizontal whitespace and remove blank lines without changing punctuation."""
    return "\n".join(line for raw in text.splitlines()
                     if (line := re.sub(r"[^\S\n]+", " ", raw).strip()))


def extract_content(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.title.get_text()) if soup.title else ""
    for node in soup.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()
    for node in soup.select("script, style, noscript, nav, aside, footer, head, iframe, svg, template, form, [role='navigation'], [hidden], [aria-hidden='true']"):
        if node.parent is not None:
            node.decompose()
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup.body or soup
    if not title:
        heading = root.find("h1")
        title = clean_text(heading.get_text()) if heading else ""
    blocks = {"p", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "blockquote", "table", "tr"}

    def render(node):
        if isinstance(node, NavigableString):
            return re.sub(r"\s+", " ", str(node))
        if node.name == "pre":
            # Keep indentation and literal spaces inside code blocks.
            code = node.get_text().replace("\r\n", "\n").replace("\r", "\n")
            return "\n" + "\n".join(line for line in code.splitlines() if line.strip()) + "\n"
        if node.name == "br":
            return "\n"
        content = "".join(render(child) for child in node.children)
        if node.name in blocks:
            return "\n" + content + "\n"
        return content + (" " if node.name in {"td", "th"} else "")

    # Clean prose separately so preformatted code is not flattened.
    preserved = {}
    for number, node in enumerate(root.find_all("pre")):
        marker = f"\ue000BINDAL_PRE_{number}\ue001"
        while marker in html:
            marker += "_"
        preserved[marker] = render(node).strip("\n")
        replacement = soup.new_tag("p")
        replacement.string = marker
        node.replace_with(replacement)
    text = clean_text(render(root))
    for marker, code in preserved.items():
        text = text.replace(marker, code)
    return title, text
