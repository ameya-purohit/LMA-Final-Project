"""The planted ground truth of CLAUDE.md §6.5, on the local backend AND in Docker."""

from tools.mutate import check_vacuous, mutate_and_run, mutate_group

REL = "toylib/core.py"


def by_desc(report, text):
    return [m for m in report.mutants if text in m.description]


def test_c1_decider_accepted_strict_default_rejected(toy_session, toy_probes, marks):
    p = toy_probes
    r88 = mutate_and_run(toy_session, REL, marks("decider"), p.c1_claim, [p.c1_control])
    assert r88.original_claim["type"] == "ValueError"
    assert r88.causal, r88.verdicts
    shift = by_desc(r88, "0 -> -1")[0]
    assert shift.flags["specific"] and shift.claim == {"kind": "return", "repr": "-1"}

    r12 = mutate_and_run(toy_session, REL, marks("strict_default"), p.c1_claim, [p.c1_control])
    assert len(r12.mutants) >= 1
    assert not any(m.flags["behavioural"] for m in r12.mutants), "no mutant of line 12 flips the claim"
    assert not r12.causal
    # Deleting line 12 breaks `from toylib.core import STRICT_DEFAULT` (ImportError): breakage, which the
    # lenient "any flip" rule would wrongly accept. This is the leniency A6 measures.
    deleted = [m for m in r12.mutants if m.operators == ["delete_statement"]][0]
    assert deleted.claim["type"] == "ImportError" and deleted.flags["breakage"]
    assert r12.verdicts == {"any_flip": True, "behavioural": False, "specific": False}


def test_c2_specificity_and_breakage(toy_session, toy_probes, marks):
    p = toy_probes
    ret = mutate_and_run(toy_session, REL, marks("return_result"), p.c2_claim, [p.c2_control])
    none = by_desc(ret, "return None")[0]
    assert none.flags["behavioural"] and none.flags["controls_changed"] and not none.flags["specific"]
    assert ret.verdicts["behavioural"] and not ret.causal, "rejected by specificity"

    limit = mutate_and_run(toy_session, REL, marks("limit"), p.c2_claim, [p.c2_control])
    up = by_desc(limit, "100 -> 101")[0]
    assert up.flags["specific"] and up.claim == {"kind": "return", "repr": "101"}
    assert limit.causal

    mn = mutate_and_run(toy_session, REL, marks("min_result"), p.c2_claim, [p.c2_control])
    deleted = [m for m in mn.mutants if m.operators == ["delete_statement"]][0]
    assert deleted.claim["type"] == "UnboundLocalError"
    assert deleted.flags["breakage"] and not deleted.flags["behavioural"]


def test_redundant_guards_need_group_mutation(toy_session, toy_probes, marks):
    p = toy_probes
    inline = mutate_and_run(toy_session, REL, marks("guard_inline"), p.div_claim, [p.div_control])
    helper = mutate_and_run(toy_session, REL, marks("guard_helper"), p.div_claim, [p.div_control])
    assert inline.mutants and helper.mutants
    assert not inline.causal and not helper.causal, "each guard alone looks non-causal"
    group = mutate_group(toy_session, [(REL, marks("guard_inline")), (REL, marks("guard_helper"))],
                         p.div_claim, [p.div_control], max_combinations=6)
    assert group.causal, [(m.description, m.flags) for m in group.mutants]
    assert any(m.claim["type"] == "ZeroDivisionError" for m in group.mutants if m.flags["specific"])


def test_operator_set_sensitivity_a11(toy_session, toy_probes, marks):
    p = toy_probes
    line = marks("compare_no_const")
    consts = mutate_and_run(toy_session, REL, line, p.ge_claim, [p.ge_control], operators=["constant"])
    assert not consts.causal  # falsely rejected: no constant on the line
    full = mutate_and_run(toy_session, REL, line, p.ge_claim, [p.ge_control])
    assert full.causal
    winners = {m.operators[0] for m in full.mutants if m.flags["specific"]}
    assert winners <= {"negate_condition", "swap_comparison"} and winners


def test_vacuous_probe_flagged(toy_session, toy_probes, marks):
    v = check_vacuous(toy_session, REL, marks("decider"), toy_probes.vacuous)
    assert v.vacuous and v.function == "clamp" and v.mutants_run > 5
    ok = check_vacuous(toy_session, REL, marks("decider"), toy_probes.c1_claim)
    assert not ok.vacuous and ok.flipped_by


def test_policy_blocks_unsafe_probe(toy_session, toy_probes, marks):
    r = mutate_and_run(toy_session, REL, marks("decider"), toy_probes.unsafe, [toy_probes.c1_control])
    assert r.blocked and r.violations[0]["detail"] == "system" and not r.mutants


def test_path_forms_and_bad_paths(toy_session, toy_probes, marks):
    p = toy_probes
    r = mutate_and_run(toy_session, "src/toylib/core.py", marks("limit"), p.c2_claim, [p.c2_control])
    assert r.causal
    bad = mutate_and_run(toy_session, "../../etc/passwd", 1, p.c2_claim)
    assert bad.error and not bad.mutants
