"""Write tests/fixtures/code_travail_sample.json: about 20 real articles chosen for edge cases."""

import json
import sys
from pathlib import Path

from legalrag.sources import legi

PARQUET = Path("data/raw/legi_vincegx33_train.parquet")
OUT = Path("tests/fixtures/code_travail_sample.json")

# Edge cases: identical bodies, star number, padded number, carriage return in path, annexe,
# long articles (split), plain short ones.
WANTED = [
    "L1237-1", "L1232-3", "L1233-12", "L3121-27", "L1221-19", "L1221-13", "L3141-3", "L1232-2",
    "R*3231-4", "L1251-33-1", "L2152-1", "Annexe III", "L6123-5", "L5312-1", "R3132-5",
    "R1422-4", "L8113-6", "L1233-58",
]


def main() -> None:
    m = legi.read(PARQUET)
    num = m.article_num.str.strip()
    picked = m[num.isin(WANTED)]
    missing = set(WANTED) - set(num[num.isin(WANTED)])
    if missing:
        sys.exit(f"not found: {sorted(missing)}")
    # Several articles can share a number across versions; keep the first.
    picked = picked.assign(_n=num[picked.index]).drop_duplicates("_n").drop(columns="_n")
    OUT.write_text(json.dumps(picked.to_dict("records"), ensure_ascii=False, indent=1))
    print(f"{len(picked)} articles -> {OUT}")


if __name__ == "__main__":
    main()
