import pandas as pd
df = pd.read_parquet("legi.parquet")
print(df.shape); print(df.dtypes)
ct = df[df.texte_titre.str.contains("Code du travail", case=False, na=False)]
print("titles with 'Code du travail':", ct.texte_titre.value_counts().head(8).to_dict())
main = ct[ct.texte_titre.str.strip().str.lower()=="code du travail"]
print("exact 'Code du travail' articles:", len(main), "of", len(ct))
s = main.article_contenu_text.fillna("")
w = s.str.split().str.len()
print("empty:", (w==0).sum())
print(w.describe(percentiles=[.5,.75,.9,.95,.99]).round(1).to_dict())
for t in (200,400,700,1000):
    print(f">{t} words:", int((w>t).sum()))
print("dup article_id:", main.article_id.duplicated().sum(), "dup text:", s.duplicated().sum())
print("sample article_num:", main.article_num.head(8).tolist(), main.article_num.tail(5).tolist())
print("nature:", main.texte_nature.value_counts().to_dict())
print("contexte sample:"); 
for i in (0, 500, 9000):
    r = main.iloc[min(i, len(main)-1)]
    print("-", r.article_id, "|", r.article_num, "|", repr(r.texte_contexte)[:300])
    print("  text:", repr(r.article_contenu_text)[:200])
print("longest:"); 
top = main.assign(w=w).sort_values("w", ascending=False).head(3)
print(top[["article_id","article_num","w"]].to_string())
# repeated-boilerplate check: very short articles
short = main.assign(w=w)[w<8]
print("articles <8 words:", len(short)); print(short.article_contenu_text.head(8).tolist())
