import re, warnings, numpy as np
warnings.filterwarnings("ignore")
from bs4 import BeautifulSoup
from tokenizers import Tokenizer
tk = Tokenizer.from_file("bge_tokenizer.json"); n = lambda s: len(tk.encode(s, add_special_tokens=False).ids)
soup = BeautifulSoup(open("gdpr_fr.html", encoding="utf-8").read(), "lxml")
ids = [t.get("id") for t in soup.find_all(id=True)]
print("section/subsection id examples:", [i for i in ids if "sct" in i][:6])
print("id examples in art_5:", [t.get("id") for t in soup.find(id="art_5").find_all(id=True)][:8])
clean = lambda s: re.sub(r"\s+"," ",s).strip()
rows = []
for a in soup.find_all(id=re.compile(r"^art_\d+$")):
    num = a["id"].split("_")[1]
    title = clean(a.find(class_="oj-sti-art").get_text(" ")) if a.find(class_="oj-sti-art") else ""
    # ancestors
    anc = [p for p in a.parents if p.get("id")]
    ch = next((p for p in anc if re.match(r"cpt_[IVX]+$", p["id"])), None)
    sc = next((p for p in anc if re.match(r"cpt_[IVX]+\.sct_\d+$", p["id"])), None)
    def head(x):
        if x is None: return ""
        h = x.find(class_=re.compile("oj-ti-section")); 
        return clean(h.get_text(" ")) if h else ""
    paras = [clean(p.get_text(" ")) for p in a.find_all(class_="oj-normal")]
    body = " ".join(paras)
    rows.append((int(num), title, head(ch), head(sc), len(paras), n(body)))
print("articles parsed:", len(rows))
tok = np.array([r[5] for r in rows]); par = np.array([r[4] for r in rows])
print("article tokens: median", int(np.median(tok)), "p90", int(np.percentile(tok,90)), "max", tok.max(), "| >512:", int((tok>512).sum()), ">1024:", int((tok>1024).sum()), ">2048:", int((tok>2048).sum()))
print("paragraph blocks per article: median", int(np.median(par)), "max", par.max())
print("with section heading:", sum(1 for r in rows if r[3]), "| chapters:", len({r[2] for r in rows}))
for r in rows[:1]+rows[4:5]+rows[14:15]+rows[16:17]: print(r)
rc = [clean(t.get_text(" ")) for t in soup.find_all(id=re.compile(r"^rct_\d+$"))]
rt = np.array([n(x) for x in rc]); print("recitals:", len(rc), "tokens median", int(np.median(rt)), "p90", int(np.percentile(rt,90)), "max", rt.max()); print("recital sample:", rc[3][:200])
