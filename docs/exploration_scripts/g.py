import re, collections
from bs4 import BeautifulSoup
for L in ("fr","en"):
    html = open(f"gdpr_{L}.html", encoding="utf-8").read()
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    txt = soup.get_text(" ", strip=True)
    print("="*60, L, "| size", len(html), "| title:", title[:100])
    print("lang attr:", soup.html.get("lang") or soup.html.get("xml:lang"))
    ids = [t.get("id") for t in soup.find_all(id=True)]
    kinds = collections.Counter(re.sub(r"[\d_.]+.*$", "", i) for i in ids)
    print("id prefixes:", dict(kinds.most_common(12)))
    classes = collections.Counter(c for t in soup.find_all(class_=True) for c in t.get("class"))
    print("top classes:", dict(classes.most_common(14)))
    print("sample ids:", [i for i in ids if i.startswith(("rct","art","cpt","tit"))][:10], [i for i in ids if i.startswith("art")][-3:])
    arts = [i for i in ids if re.fullmatch(r"art_\d+", i)]; rcts = [i for i in ids if re.fullmatch(r"rct_\d+", i)]; cpts = [i for i in ids if re.fullmatch(r"cpt_[IVX]+", i)]
    print("articles:", len(arts), "recitals:", len(rcts), "chapters:", len(cpts), cpts)
    print("words:", len(txt.split()))
    # article 5 text
    a5 = soup.find(id="art_5")
    if a5:
        print("ART5 container:", a5.name, "| text start:", re.sub(r"\s+"," ",a5.get_text(" ",strip=True))[:450])
        print("ART5 child classes:", collections.Counter(c for t in a5.find_all(class_=True) for c in t.get("class")).most_common(6))
    c2 = soup.find(id="cpt_II")
    if c2: print("CPT_II text start:", re.sub(r"\s+"," ",c2.get_text(" ",strip=True))[:200])
