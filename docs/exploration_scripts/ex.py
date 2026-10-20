import pandas as pd
df = pd.read_parquet("legi.parquet")
m = df[df.texte_titre.str.strip().str.lower()=="code du travail"].set_index("article_num")
for num in ("L1221-14", "L1237-1", "L1232-3"):
    r = m.loc[num]
    if hasattr(r, "ndim") and r.ndim > 1: r = r.iloc[0]
    parts = [x.strip() for x in r.texte_contexte.split(">")]
    print("="*70); print("ARTICLE", num, "| id", r.article_id, "| start", r.date_debut)
    print("BODY:", r.article_contenu_text[:400])
    print("PATH LEVELS (%d):" % len(parts))
    for i,p in enumerate(parts,1): print(f"  {i}. {p}")
