"""Reader for the GDPR (Regulation (EU) 2016/679) XHTML from the Publications Office."""

import re
import warnings
from pathlib import Path

import numpy as np
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
from tokenizers import Tokenizer

from legalrag.models import Article
from legalrag.text import content_hash, normalize_text

CELEX = "32016R0679"
PARAGRAPH_SEP = "\n\n"  # between numbered paragraphs; single "\n" separates points inside one

_ART = re.compile(r"^art_\d+$")
_RCT = re.compile(r"^rct_\d+$")
_CPT = re.compile(r"^cpt_[IVX]+$")
_SCT = re.compile(r"^cpt_[IVX]+\.sct_\d+$")
_ODD = re.compile("[\u200b-\u200f\u00a0\u00ad]")  # zero-width, bidi, no-break space, soft hyphen


warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)  # XHTML parsed with lxml's HTML parser


def load(path: Path) -> BeautifulSoup:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    # Footnote markers such as "(19)" are dropped; the note texts sit outside articles.
    for a in soup.find_all("a"):
        if a.find(class_="oj-note-tag"):
            a.decompose()
    return soup


def _text(el: Tag) -> str:
    return normalize_text(el.get_text(""))


def _cell_lines(cell: Tag) -> list[str]:
    lines = []
    for child in cell.find_all(True, recursive=False):
        if child.name == "p":
            if t := _text(child):
                lines.append(t)
        elif child.name == "table":
            lines += _table_lines(child)
        elif child.name == "div":
            lines += _cell_lines(child)
    return lines


def _table_lines(table: Tag) -> list[str]:
    """One line per point; a 'label | content' row becomes 'label content'."""
    lines = []
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cells = tr.find_all("td", recursive=False)
        if len(cells) == 2:
            label = _text(cells[0])
            content = _cell_lines(cells[1])
            if content:
                content[0] = f"{label} {content[0]}".strip()
            lines += content
        else:
            for c in cells:
                lines += _cell_lines(c)
    return lines


def _article_groups(art: Tag) -> list[str]:
    """Numbered paragraphs (with their points) and definition rows, each as one group."""
    groups = []
    for child in art.find_all(True, recursive=False):
        if child.name == "p" and "oj-ti-art" in child.get("class", []):
            continue
        if child.name == "div" and "eli-title" in child.get("class", []):
            continue
        lines = _cell_lines(child) if child.name in ("div", "td") else []
        if child.name == "p":
            lines = [_text(child)] if _text(child) else []
        elif child.name == "table":
            lines = _table_lines(child)
        if lines:
            groups.append("\n".join(lines))
    return groups


def _heading(container: Tag, soup: BeautifulSoup) -> str:
    label = _text(container.find("p", class_="oj-ti-section-1"))
    title_div = soup.find(id=f"{container['id']}.tit_1")
    title = _text(title_div) if title_div else ""
    return f"{label} : {title}" if title else label


def parse(path: Path, lang: str) -> list[Article]:
    soup = load(path)
    url = f"https://eur-lex.europa.eu/legal-content/{lang.upper()}/TXT/?uri=CELEX:{CELEX}"
    articles = []
    for art in soup.find_all("div", id=_ART):
        n = art["id"].split("_")[1]
        title = _text(soup.find(id=f"{art['id']}.tit_1"))
        levels = []
        if cpt := art.find_parent("div", id=_CPT):
            levels.append(_heading(cpt, soup))
        if sct := art.find_parent("div", id=_SCT):
            levels.append(_heading(sct, soup))
        body = PARAGRAPH_SEP.join(_article_groups(art))
        articles.append(
            Article(
                uid=f"rgpd:{lang}:{art['id']}",
                source_code="rgpd",
                lang=lang,
                kind="article",
                native_id=art["id"],
                article_num=n,
                title=title,
                section_path=" > ".join(levels),
                body_text=body,
                content_hash=content_hash(body),
                source_url=url,
            )
        )
    for rct in soup.find_all("div", id=_RCT):
        body = "\n".join(_table_lines(rct.find("table")))
        # the first cell is the label "(4)"; _table_lines already merged label and text
        body = re.sub(r"^\(\d+\)\s*", "", body)
        articles.append(
            Article(
                uid=f"rgpd:{lang}:{rct['id']}",
                source_code="rgpd",
                lang=lang,
                kind="recital",
                native_id=rct["id"],
                article_num=rct["id"].split("_")[1],
                section_path="",
                body_text=body,
                content_hash=content_hash(body),
                source_url=url,
            )
        )
    return articles


def _pct(a: np.ndarray) -> dict[int, int]:
    return {k: int(np.percentile(a, k)) for k in (50, 90, 95, 99)}


def profile(fr_path: Path, en_path: Path, tokenizer_path: Path) -> str:
    tk = Tokenizer.from_file(str(tokenizer_path))

    def n(s: str) -> int:
        return len(tk.encode(s, add_special_tokens=False).ids)

    lines = ["# Data profile: GDPR (Regulation (EU) 2016/679)", "",
             "Generated by `legalrag.sources.gdpr.profile`.", ""]
    parsed = {}
    for lang, path in (("fr", fr_path), ("en", en_path)):
        raw = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
        arts = parse(path, lang)
        parsed[lang] = arts
        only = [a for a in arts if a.kind == "article"]
        rct = [a for a in arts if a.kind == "recital"]
        nums = sorted(int(a.article_num) for a in only)
        tb = np.array([n(a.body_text) for a in only])
        tr = np.array([n(a.body_text) for a in rct])
        groups = np.array([a.body_text.count(PARAGRAPH_SEP) + 1 for a in only])
        tags_art = sum(len(x.find_all(class_="oj-note-tag")) for x in raw.find_all("div", id=_ART))
        tags_rct = sum(len(x.find_all(class_="oj-note-tag")) for x in raw.find_all("div", id=_RCT))
        no_par = sum(1 for x in raw.find_all("div", id=_ART)
                     if not x.find("div", id=re.compile(r"^\d{3}\.\d{3}$")))
        wide = [x["id"] for x in raw.find_all("div", id=_ART)
                if any(len(t.find_all("td", recursive=False)) > 2 or t.find("table")
                       for t in x.find_all("table"))]
        under_sct = sum(1 for a in only if " > " in a.section_path)
        chapters = {a.section_path.split(" > ")[0] for a in only}
        sections = {a.section_path for a in only if " > " in a.section_path}
        odd = sum(1 for a in arts if _ODD.search(a.body_text))
        lines += [
            f"## Language: {lang}",
            f"- File size: {path.stat().st_size:,} bytes",
            f"- Articles: {len(only)}; ids contiguous 1..99: {nums == list(range(1, 100))}",
            f"- Recitals: {len(rct)}; chapters: {len(chapters)}; sections: {len(sections)}; "
            f"articles under a section: {under_sct}",
            f"- Articles without a title: {sum(1 for a in only if not a.title)}; "
            f"empty bodies: {sum(1 for a in arts if not a.body_text)}",
            f"- Articles without numbered-paragraph blocks (single paragraph or definitions): {no_par}",
            f"- Articles with nested or wide tables (definitions with sub-points): {wide}",
            f"- Footnote markers removed: {tags_art} in articles, {tags_rct} in recitals",
            f"- Paragraph groups per article: median {int(np.median(groups))}, max {groups.max()}",
            f"- Article body tokens (bge-m3): {_pct(tb)}, max {int(tb.max())}; "
            f"over 512: {int((tb > 512).sum())}; over 1,024: {int((tb > 1024).sum())}; "
            f"over 2,048: {int((tb > 2048).sum())}",
            f"- Recital body tokens: {_pct(tr)}, max {int(tr.max())}; over 512: {int((tr > 512).sum())}",
            f"- Bodies with zero-width, non-breaking or soft-hyphen characters: {odd}",
            "",
        ]
    fr_ids = {a.native_id for a in parsed["fr"]}
    en_ids = {a.native_id for a in parsed["en"]}
    lines += ["## Both languages", f"- Same ids in FR and EN: {fr_ids == en_ids}", ""]
    return "\n".join(lines)
