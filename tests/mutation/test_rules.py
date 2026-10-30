"""Pure rule functions over serialized outcomes (no execution)."""

from tools.mutate import classify, is_breakage, outcome_changed, verdicts

RET5 = {"kind": "return", "repr": "5"}
RET6 = {"kind": "return", "repr": "6"}
VERR = {"kind": "raise", "type": "ValueError", "msg": "negative", "innermost_frame": "toylib/core.py:88"}
VERR_OTHER_FRAME = {**VERR, "innermost_frame": "toylib/core.py:40"}
UNBOUND = {"kind": "raise", "type": "UnboundLocalError", "msg": "x", "innermost_frame": "toylib/core.py:90"}
TYPEERR_AT = {"kind": "raise", "type": "TypeError", "msg": "bad", "innermost_frame": "toylib/core.py:88"}
TYPEERR_ELSEWHERE = {**TYPEERR_AT, "innermost_frame": "toylib/core.py:50"}


def test_outcome_changed():
    assert not outcome_changed(RET5, dict(RET5))
    assert outcome_changed(RET5, RET6)
    assert outcome_changed(RET5, VERR)
    assert not outcome_changed(VERR, VERR_OTHER_FRAME), "same type and message: same behaviour"
    assert outcome_changed(VERR, {**VERR, "msg": ""})


def test_breakage():
    assert is_breakage(UNBOUND, "toylib/core.py:89")
    assert is_breakage({"kind": "raise", "type": "SyntaxError", "msg": "", "innermost_frame": None}, "x:1")
    assert is_breakage(TYPEERR_AT, "toylib/core.py:88")
    assert not is_breakage(TYPEERR_ELSEWHERE, "toylib/core.py:88")
    assert not is_breakage(VERR, "toylib/core.py:88")
    assert not is_breakage(RET5, "toylib/core.py:88")
    assert is_breakage(TYPEERR_AT, ["toylib/core.py:10", "toylib/core.py:88"])


def test_classify_and_three_rules():
    specific = classify(VERR, [RET5], RET6, [RET5], "toylib/core.py:88")
    assert specific == {"claim_changed": True, "breakage": False, "controls_changed": False,
                        "any_flip": True, "behavioural": True, "specific": True}
    both = classify(RET5, [RET5], RET6, [RET6], "l:1")
    assert both["behavioural"] and not both["specific"]
    broken = classify(RET5, [RET5], UNBOUND, [UNBOUND], "toylib/core.py:89")
    assert broken["any_flip"] and not broken["behavioural"] and broken["breakage"]
    same = classify(RET5, [RET5], RET5, [RET6], "l:1")
    assert not same["any_flip"] and same["controls_changed"]
    assert verdicts([both, broken]) == {"any_flip": True, "behavioural": True, "specific": False}
    assert verdicts([both, specific])["specific"] is True
    assert verdicts([]) == {"any_flip": False, "behavioural": False, "specific": False}
