import pandas as pd, numpy as np
from tokenizers import Tokenizer
tk = Tokenizer.from_file("bge_tokenizer.json")
df = pd.read_parquet("legi.parquet")
m = df[df.texte_titre.str.strip().str.lower()=="code du travail"].copy()
def n(s): return len(tk.encode(s, add_special_tokens=False).ids)
body = m.article_contenu_text.tolist()
tb = np.array([n(s) for s in body])
def path_tail(p, k):
    parts = [x.strip() for x in (p or "").split(">")]
    return " > ".join(parts[-k:])
h1 = [f"Code du travail, article {a}." for a in m.article_num]
h2 = [f"Code du travail, article {a}. {path_tail(p,2)}." for a,p in zip(m.article_num, m.texte_contexte)]
h3 = [f"Code du travail, article {a}. {p}." for a,p in zip(m.article_num, m.texte_contexte)]
t1 = np.array([n(s) for s in h1]); t2 = np.array([n(s) for s in h2]); t3 = np.array([n(s) for s in h3])
def pct(a): return {k: int(np.percentile(a,k)) for k in (50,90,95,99)}
print("body tokens", pct(tb), "mean", int(tb.mean()), "max", int(tb.max()))
for lim in (256,512,1024,2048,8192):
    print(f"body > {lim} tokens: {(tb>lim).sum()} ({(tb>lim).mean()*100:.1f}%)")
print("header tokens: H1", int(np.median(t1)), "H2", int(np.median(t2)), "H3", int(np.median(t3)), "(medians); H3 p99", int(np.percentile(t3,99)))
print("header share of total text (median): H1 %.2f H2 %.2f H3 %.2f" % tuple(np.median(h/(h+tb)) for h in (t1,t2,t3)))
for lim in (512,1024):
    print(f"with H2, > {lim}: {((tb+t2)>lim).sum()}; with H3: {((tb+t3)>lim).sum()}")
print("short bodies <30 tokens:", int((tb<30).sum()), "; <60:", int((tb<60).sum()))
print("total tokens body (one embedding pass):", int(tb.sum()), "with H2:", int((tb+t2).sum()), "with H3:", int((tb+t3).sum()))
print("tokens per word median:", round(float(np.median(tb/ m.article_contenu_text.str.split().str.len())),2))
