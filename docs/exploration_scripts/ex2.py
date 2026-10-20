import pandas as pd
from tokenizers import Tokenizer
tk = Tokenizer.from_file("bge_tokenizer.json")
n = lambda s: len(tk.encode(s, add_special_tokens=False).ids)
df = pd.read_parquet("legi.parquet")
m = df[df.texte_titre.str.strip().str.lower()=="code du travail"].set_index("article_num")
def parts(num): return [x.strip() for x in m.loc[num].texte_contexte.split(">")]
r = m.loc["L1233-12"]; print("L1233-12 path:", parts("L1233-12")[-3:]); print("body:", r.article_contenu_text[:120])
for num in ("L1237-1","L1221-14"):
    p = parts(num); body = m.loc[num].article_contenu_text
    styles = {
     "H0 none": "",
     "H1 code+number": f"Code du travail, article {num}.",
     "H2 +last 2 levels": f"Code du travail, article {num}. {' > '.join(p[-2:])}",
     "H3 full path": f"Code du travail, article {num}. {' > '.join(p)}",
    }
    print("\n#####", num, "body tokens:", n(body))
    for k,h in styles.items():
        print(f"[{k}] header tokens={n(h) if h else 0}\n   {h}")
