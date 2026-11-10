"""Run a claim judge prompt on the expert labels of ClaimRAG-LAW (English GDPR): the claim triples as template
sentences, the source chunk as the passage, two classes (Entailment against the rest). The claims are split by
question into a dev half and a test half (`claimrag.half`): tune a prompt on dev, then run test once.
Spends model money (a few cents per half).
  uv run python scripts/claimrag_judge.py --prompt judge.v3 --half dev --tag v3-dev
"""

import argparse
import json
from pathlib import Path

from legalrag import claimjudge, claimrag

DATA = Path("data/claimrag")
OUT = Path("data/judge")


def two_classes(label: str) -> str:
    return "supported" if label == "supported" else "not supported"


def score(items: list[claimjudge.Item], verdicts: list[dict], triples: dict[str, claimrag.Triple]) -> None:
    by_key = {v["key"]: v for v in verdicts if v.get("label")}
    judged = [i for i in items if i.key in by_key]
    r = claimjudge.report([(i.human, two_classes(by_key[i.key]["label"])) for i in judged])
    print(f"{r['n']} of {len(items)} claims judged; agreement {r['agreement']:.0%}, kappa {r['kappa']:.2f}")
    print(f"expert Neutral or Contradiction caught: {r['errors_caught']} of {r['errors']}; "
          f"Entailment flagged: {r['good_flagged']} of {r['good']}")
    for label in claimrag.BINARY:
        kept = [i for i in judged if triples[i.key].label == label]
        print(f"  expert {label}: judge supported {sum(by_key[i.key]['label'] == 'supported' for i in kept)} of {len(kept)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--prompt", default="judge.v2")
    parser.add_argument("--half", choices=("dev", "test", "all"), default="all")
    parser.add_argument("--chunk", choices=("claim-file", "rag-file"), default="claim-file",
                        help="which source chunk the judge sees; rag-file keeps only the questions the two files share")
    parser.add_argument("--matching-only", action="store_true", help="with claim-file: the same questions as rag-file")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--run-cap", type=float, default=0.5)
    args = parser.parse_args()

    triples = claimrag.load_claims(DATA / "GDPR-CLAIM-LAW.json")
    if args.chunk == "rag-file" or args.matching_only:
        longer = {t.key: t for t in claimrag.with_rag_chunks(triples, DATA / "GDPR-RAG-LAW.json")}
        triples = [longer[t.key] if args.chunk == "rag-file" else t for t in triples if t.key in longer]
    triples = [t for t in triples if args.half in ("all", claimrag.half(t.key))]
    items = claimrag.to_items(triples, [claimrag.template_sentence(t.parts) for t in triples])
    verdicts = claimjudge.run_judge(items, args.model, False, args.run_cap, 6, f"claimrag-{args.tag}", args.prompt)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"claimrag-{args.tag}.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts))
    print(f"model {args.model}, prompt {args.prompt}, half {args.half}")
    score(items, verdicts, {t.key: t for t in triples})


if __name__ == "__main__":
    main()
