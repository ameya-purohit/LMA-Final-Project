"""annotation/sample.py: a seeded, stratified 20% sample, dealt evenly to the four members."""

from collections import Counter

from annotation import sample as S


def _qs(n_click=146, n_marsh=24):
    return [{"qid": f"click-{i}", "library": "click"} for i in range(n_click)] + \
           [{"qid": f"marshmallow-{i}", "library": "marshmallow"} for i in range(n_marsh)]


def test_sample_is_twenty_percent_stratified_and_seeded():
    qs = _qs()
    picked = S.stratified_sample(qs, 0.2, 82)
    assert len(picked) == 34 and len({q["qid"] for q in picked}) == 34
    assert Counter(q["library"] for q in picked) == {"click": 29, "marshmallow": 5}
    assert [q["qid"] for q in picked] == [q["qid"] for q in S.stratified_sample(list(reversed(qs)), 0.2, 82)]
    assert [q["qid"] for q in picked] != [q["qid"] for q in S.stratified_sample(qs, 0.2, 83)]


def test_assignment_is_even_complete_and_mixes_libraries():
    picked = S.stratified_sample(_qs(), 0.2, 82)
    shares = S.assign(picked, ["sunil", "ameya", "aditya", "sourav"], 82)
    sizes = sorted(len(v) for v in shares.values())
    assert sizes == [8, 8, 9, 9]
    assert sorted(q["qid"] for v in shares.values() for q in v) == sorted(q["qid"] for q in picked)
    assert sum(any(q["library"] == "marshmallow" for q in v) for v in shares.values()) >= 3


def test_members_come_from_ownership_in_push_order():
    assert S.members_in_order() == ["sunil", "ameya", "aditya", "sourav"]


def test_gold_links_point_at_the_frozen_commit():
    q = {"frozen_commit": "abc123", "gold_evidence": [
        {"path": "src/click/core.py", "line_start": 10, "line_end": 12, "kind": "changed"},
        {"path": "src/click/core.py", "line_start": 40, "line_end": 40, "kind": "anchor_for_insert"}]}
    links = S.gold_links(q, {"owner": "pallets", "repo": "click"})
    assert links[0]["url"] == "https://github.com/pallets/click/blob/abc123/src/click/core.py#L10-L12"
    assert links[1]["url"].endswith("core.py#L40") and links[1]["kind"] == "anchor_for_insert"


def test_record_carries_only_dataset_facts():
    q = {"qid": "click-1", "library": "click", "category": "single_location", "issue_url": "i", "question_text": "why?",
         "fix_pr_url": "p", "fix_pr_number": 2, "frozen_commit": "f", "fix_merge_commit": "m", "fail_to_pass": ["t"],
         "observed_before": [{"test": "t", "status": "failed", "message": "boom"}], "gold_answer": "g",
         "gold_evidence": [{"path": "a.py", "line_start": 1, "line_end": 1, "kind": "changed"}]}
    config = {"data": {"libraries": {"click": {"owner": "pallets", "repo": "click"}}}}
    rec = S.record(q, "sourav", config, diff_fn=lambda q, spec, cfg: "diff --git a/a.py b/a.py\n-x\n+y\n")
    assert rec["member"] == "sourav" and rec["source_diff"].startswith("diff --git")
    assert rec["observed_before"][0]["message"] == "boom" and rec["gold_evidence"][0]["url"].endswith("a.py#L1")
