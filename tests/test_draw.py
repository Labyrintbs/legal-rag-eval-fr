import random
from collections import Counter

from legalrag import draw

CT = draw.CODE_DU_TRAVAIL


def sheet(*article_nums, group=CT):
    return {"sections": [{"references": {group: {"articles": [{"fmt": n} for n in article_nums]}}}]}


def test_sheet_counts_count_an_article_once_per_sheet_and_only_for_the_code_du_travail():
    sheets = [
        sheet("L1237-1", "L1237-1", "L1221-19"),
        sheet("L1237-1"),
        sheet("L9999-1", group="LEGITEXT000006073189"),
        {"sections": [{"references": {}}]},
    ]
    assert draw.sheet_counts(sheets) == Counter({"L1237-1": 2, "L1221-19": 1})


def test_part_is_the_first_digit_after_the_letter():
    assert [draw.part_of(n) for n in ("L1237-1", "R4412-1", "D3141-1")] == ["1", "4", "3"]


def test_the_same_seed_gives_the_same_draw():
    weights = {f"L{p}00{i}-1": 1.0 for p in range(1, 9) for i in range(5)}
    first = draw.draw(random.Random(7), weights, 6, Counter(), 2)
    assert first == draw.draw(random.Random(7), weights, 6, Counter(), 2)
    assert len(set(first)) == 6


def test_a_part_never_exceeds_its_cap_even_across_two_draws():
    weights = {f"L{p}00{i}-1": 1.0 for p in (1, 2) for i in range(10)}
    taken = Counter()
    chosen = draw.draw(random.Random(1), weights, 3, taken, 2)
    chosen += draw.draw(random.Random(2), {k: 1.0 for k in weights if k not in chosen}, 3, taken, 2)
    assert len(chosen) == 4  # parts 1 and 2 hold two each; the rest is skipped, not forced
    assert Counter(draw.part_of(a) for a in chosen) == Counter({"1": 2, "2": 2})


def test_the_weight_steers_the_draw():
    weights = {"L1000-1": 1000.0, "L2000-1": 1.0}
    firsts = [draw.draw(random.Random(s), weights, 1, Counter(), 2)[0] for s in range(30)]
    assert firsts.count("L1000-1") >= 27
