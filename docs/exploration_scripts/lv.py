import pandas as pd
df = pd.read_parquet("legi.parquet")
m = df[df.texte_titre.str.strip().str.lower()=="code du travail"]
parts = m.texte_contexte.fillna("").str.split(" > ")
print("levels distribution:", parts.str.len().value_counts().sort_index().to_dict())
print("elements containing '>':", sum(any(">" in x for x in p) for p in parts))
print("empty path:", int((m.texte_contexte.fillna("")=="").sum()))
print("separator exactly ' > ' everywhere:", bool((m.texte_contexte.str.count(">") == parts.str.len()-1).all()))
print("first level values:", parts.str[0].value_counts().to_dict())
print("last level starts with:", parts.str[-1].str.extract(r"^(\w+)")[0].value_counts().head(8).to_dict())
