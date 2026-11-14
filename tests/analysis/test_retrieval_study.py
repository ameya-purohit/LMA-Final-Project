"""analysis.retrieval_study: per-question retrieval metrics by hand."""

from analysis.retrieval_study import per_question_metrics, relevant


def test_metrics_by_hand():
    m = per_question_metrics([False, True, False, True, False, False, False, False, False, False], n_relevant=4)
    assert m["hit@1"] == 0 and m["hit@5"] == 1 and m["mrr@5"] == 0.5 and m["mrr@1"] == 0
    assert m["recall@5"] == 0.5 and m["precision@5"] == 0.4 and m["recall@10"] == 0.5


def test_relevance_is_overlap_with_a_gold_range():
    gold = [{"path": "src/p/a.py", "line_start": 10, "line_end": 12}]
    assert relevant("src/p/a.py", 1, 10, gold) and relevant("p/a.py", 12, 40, gold)
    assert not relevant("src/p/a.py", 13, 40, gold) and not relevant("src/p/b.py", 1, 99, gold)
