"""Tries the English translation of an answer (step 0f, part 4) on answers that exist: the answers of the example cards.
Prints each French line with its English line, and checks by program that the citation numbers are kept in the same
places. Spends a few tenths of a cent of DeepSeek money.
  uv run --env-file .env python scripts/answers/translate_answers_check.py
"""

import json
import os
import re
from pathlib import Path

from llama_index.core.llms import ChatMessage
from llama_index.llms.deepseek import DeepSeek

from legalrag.evaluation.questiongen import load_prompts

ROOT = Path(__file__).parents[2]
MODEL, PROMPT_ID = "deepseek-flash", "translate_answer.v2"
CARDS = [  # answers that exist: dev answers of the cards, and the real-model answers of the new cards
    ("data/pilot/answers_flash-v3.jsonl", "smoke-04"), ("data/pilot/answers_flash-v3.jsonl", "sheet-19"),
    ("data/pilot/answers_flash-v3.jsonl", "mw-004"), ("data/pilot/answers_flash-v3.jsonl", "smoke-17"),
    ("data/pilot/answers_flash-v3.jsonl", "hw-07"), ("data/pilot/answers_flash-v3.jsonl", "sheet-24"),
    ("data/pilot/stress_cards.json", 0), ("data/pilot/stress_cards.json", 1), ("data/pilot/stress_cards.json", 2),
    ("data/pilot/stress_cards.json", 4),
]


def answer_lines(text: str) -> list[str]:
    """The sentences of a rendered answer, each with its citation numbers, without the list of passages."""
    return [line for line in text.split("\n\n[1]")[0].splitlines() if line.strip()]


def load(path: str, key) -> list[str]:
    if path.endswith(".jsonl"):
        rows = {json.loads(line)["id"]: json.loads(line) for line in (ROOT / path).read_text().splitlines()}
        return answer_lines(rows[key]["text"])
    return answer_lines(json.loads((ROOT / path).read_text())[key]["text"])


def markers(line: str) -> list[str]:
    return re.findall(r"\[\d+\]", line)


def main() -> None:
    prompt = load_prompts(ROOT / "prompts" / "translate_answer.yaml")["prompts"][PROMPT_ID]
    llm = DeepSeek(model=MODEL, api_key=os.environ["DEEPSEEK_API_KEY"], temperature=0, max_tokens=prompt["max_tokens"],
                   additional_kwargs={"extra_body": {"thinking": {"type": "disabled"}}})
    kept = total = 0
    for path, key in CARDS:
        french = load(path, key)
        reply = llm.chat([ChatMessage(role="system", content=prompt["system"].strip()),
                          ChatMessage(role="user", content=prompt["user"].format(text="\n".join(french)))])
        english = [line for line in (reply.message.content or "").splitlines() if line.strip()]
        print(f"\n## {path.split('/')[-1]} {key}: {len(french)} French lines, {len(english)} English lines")
        for fr, en in zip(french, english, strict=False):
            total += 1
            kept += markers(fr) == markers(en)
            print(f"  FR {fr}\n  EN {en}" + ("" if markers(fr) == markers(en) else "\n  !! citation numbers differ"))
    print(f"\ncitation numbers kept on {kept} of {total} lines")


if __name__ == "__main__":
    main()
