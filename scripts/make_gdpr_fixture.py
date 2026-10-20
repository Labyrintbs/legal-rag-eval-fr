"""Write tests/fixtures/gdpr_fr_excerpt.xhtml: a few real units that cover the layout cases."""

import copy
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

SRC = Path("data/raw/gdpr_fr.xhtml")
OUT = Path("tests/fixtures/gdpr_fr_excerpt.xhtml")


def heading_parts(soup, container_id):
    box = soup.find(id=container_id)
    return [box.find("p", class_="oj-ti-section-1"), soup.find(id=f"{container_id}.tit_1")]


def main() -> None:
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    soup = BeautifulSoup(SRC.read_text(encoding="utf-8"), "lxml")
    out = BeautifulSoup("<html><body><div class='eli-container'></div></body></html>", "lxml")
    root = out.find("div")

    def add(parent, tag):
        parent.append(copy.copy(tag))

    # Recital with a footnote marker, plain recital.
    for rid in ("rct_3", "rct_4"):
        add(root, soup.find(id=rid))
    # Chapter I: Article 4 (definitions with nested points, footnote marker).
    cpt1 = out.new_tag("div", id="cpt_I")
    for part in heading_parts(soup, "cpt_I"):
        add(cpt1, part)
    add(cpt1, soup.find(id="art_4"))
    root.append(cpt1)
    # Chapter II: Article 5 (paragraphs and points), Article 10 (single paragraph).
    cpt2 = out.new_tag("div", id="cpt_II")
    for part in heading_parts(soup, "cpt_II"):
        add(cpt2, part)
    for aid in ("art_5", "art_10"):
        add(cpt2, soup.find(id=aid))
    root.append(cpt2)
    # Chapter III, Section 1: Article 12 (article under a section).
    cpt3 = out.new_tag("div", id="cpt_III")
    for part in heading_parts(soup, "cpt_III"):
        add(cpt3, part)
    sct = out.new_tag("div", id="cpt_III.sct_1")
    for part in heading_parts(soup, "cpt_III.sct_1"):
        add(sct, part)
    add(sct, soup.find(id="art_12"))
    cpt3.append(sct)
    root.append(cpt3)
    OUT.write_text(str(out), encoding="utf-8")
    print(f"{OUT.stat().st_size} bytes -> {OUT}")


if __name__ == "__main__":
    main()
