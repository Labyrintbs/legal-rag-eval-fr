"""Check the claim judge on the expert labels of ClaimRAG-LAW (English GDPR), with two ways to turn the triples into
sentences: the plain template and a model rewrite (`claim.rewrite.v1`). Spends model money (a few cents).
  uv run python scripts/claimrag_judge.py
"""

import argparse
import json
from pathlib import Path

from legalrag import claimjudge, claimrag, labelsheet

DATA = Path("data/claimrag")
OUT = Path("data/judge")


def two_classes(label: str) -> str:
    return "supported" if label == "supported" else "not supported"


def score(name: str, items: list[claimjudge.Item], verdicts: list[dict]) -> None:
    by_key = {v["key"]: v for v in verdicts if v.get("label")}
    pairs = [(i.human, two_classes(by_key[i.key]["label"])) for i in items if i.key in by_key]
    r = claimjudge.report(pairs)
    print(f"\n{name}: {r['n']} of {len(items)} claims judged; agreement {r['agreement']:.0%}, kappa {r['kappa']:.2f}")
    print(f"  expert Neutral or Contradiction caught: {r['errors_caught']} of {r['errors']}; "
          f"Entailment flagged: {r['good_flagged']} of {r['good']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--prompt", default="judge.v2")
    parser.add_argument("--run-cap", type=float, default=0.5)
    args = parser.parse_args()

    triples = claimrag.load_claims(DATA / "GDPR-CLAIM-LAW.json")
    print(f"{len(triples)} claims with an expert label: "
          + ", ".join(f"{label} {sum(t.label == label for t in triples)}" for label in claimrag.BINARY))
    rewrites_file = DATA / "rewrites.jsonl"
    if rewrites_file.exists():
        rewritten = [r["sentence"] for r in labelsheet.read_rows(rewrites_file)]
    else:
        rewritten = claimrag.rewrite_all(triples, args.model, args.run_cap, 8, "claimrag")
        rewrites_file.write_text("".join(json.dumps({"key": t.key, "sentence": s}, ensure_ascii=False) + "\n"
                                         for t, s in zip(triples, rewritten, strict=True)))
    print("\ntriple -> template -> rewrite (first 12):")
    for t, new in list(zip(triples, rewritten, strict=True))[:12]:
        print(f"  {' | '.join(t.parts)}\n    {claimrag.template_sentence(t.parts)}\n    {new}")

    variants = {"template": [claimrag.template_sentence(t.parts) for t in triples], "rewrite": rewritten}
    for name, sentences in variants.items():
        items = claimrag.to_items(triples, sentences)
        verdicts = claimjudge.run_judge(items, args.model, False, args.run_cap, 6, f"claimrag-{name}", args.prompt)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"claimrag-{name}.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts))
        score(name, items, verdicts)


if __name__ == "__main__":
    main()
