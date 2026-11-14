"""analysis.extension.ranking_diagnosis: where the first gold line sits in a multi-agent ranking, and its verdict."""

from analysis.extension import ranking_diagnosis

GOLD = [{"path": "src/click/core.py", "line_start": 10, "line_end": 12}]


def test_first_gold_hit_gives_length_class_and_rank():
    a = {"ranking": [{"path": "src/click/core.py", "line": 50, "class": "inconclusive"},
                     {"path": "click/core.py", "line": 11, "class": "rejected"}]}
    assert ranking_diagnosis(a, GOLD) == (2, "rejected", 2)


def test_no_gold_hit_and_single_agent_answers():
    assert ranking_diagnosis({"ranking": [{"path": "src/click/core.py", "line": 1, "class": "accepted"}]}, GOLD) == (1, None, None)
    assert ranking_diagnosis({"claims": []}, GOLD) == (None, None, None)
