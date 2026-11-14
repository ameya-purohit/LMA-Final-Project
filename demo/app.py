"""Presentation demo: `streamlit run demo/app.py` (install `pip install -r demo/requirements.txt` first).

Five pages:
1. The idea: the two checks in plain words, the headline results, and the dataset.
2. Live demo: run a probe and flip the switch on the toylib fixture, in the sandbox, right now. No LLM, no quota.
3. Results: the committed analysis (main comparison, hypotheses, ablations, RQ2, judge validation, safety).
4. Inside one question: what each system answered, what the judge said, and our agent's decision log, side by side.
   Needs the raw results on the machine that ran the experiments.

Why it only reads files: a presentation must not depend on a free API quota or the network, and every number on
screen must be the same one the report gives. All loading is in `demo/data.py`.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo import data as D  # noqa: E402

st.set_page_config(page_title="Run It, Then Cite It", page_icon="🧪", layout="wide")

METRIC_COLORS = alt.Scale(domain=["Correct", "Causally supported"], range=["#4C78A8", "#F58518"])
ACCENT, MUTED = "#0F6B62", "#A7B1BA"   # one highlight colour against grey, for "which bar matters" charts

# Small, presentation-only styling: cards, verdict chips and the role pipeline. Colours read well on a projector.
st.markdown("""<style>
.block-container {padding-top: 2.2rem; max-width: 1280px;}
.hero {padding: 1.4rem 1.6rem; border-radius: 14px; background: linear-gradient(135deg, #0F3D3A 0%, #0F6B62 100%);
       color: #F3FAF9; margin-bottom: 1.2rem;}
.hero h1 {color: #FFFFFF; font-size: 2.5rem; margin: 0 0 .3rem 0; padding: 0;}
.hero p {color: #D5ECE9; font-size: 1.05rem; margin: 0; max-width: 62rem;}
.hero .tag {display:inline-block; font-size:.78rem; letter-spacing:.06em; text-transform:uppercase; color:#9FD9D0;
            margin-bottom:.4rem;}
.kpi {border: 1px solid #E3E7EB; border-radius: 12px; padding: .9rem 1rem; background: #FFFFFF; min-height: 152px;}
.kpi .k {font-size: .78rem; color: #5B6670; text-transform: uppercase; letter-spacing: .05em;}
.kpi .v {font-size: 1.7rem; font-weight: 700; color: #1B2430; line-height: 1.2; margin: .15rem 0;}
.kpi .s {font-size: .85rem; color: #5B6670;}
.chip {display:inline-block; padding: 1px 9px; border-radius: 999px; font-size: .78rem; font-weight: 600; white-space: nowrap;}
.c-accepted, .c-accepted_pair, .c-supported {background:#E3F3E8; color:#1D6B3A;}
.c-inconclusive, .c-partly {background:#FBF0D9; color:#8A5A00;}
.c-rejected, .c-refuted, .c-not-supported {background:#FBE6E4; color:#9B2C2C;}
.c-untested, .c-cited {background:#EEF1F4; color:#4A5560;}
.c-gold {background:#0F6B62; color:#FFFFFF;}
.pipe {display:flex; flex-wrap:wrap; align-items:stretch; gap:.5rem; margin:.4rem 0 1rem 0;}
.role {flex:1 1 170px; border:1px solid #E3E7EB; border-radius:12px; padding:.75rem .85rem; background:#FFFFFF;}
.role .n {font-size:.75rem; color:#0F6B62; font-weight:700; letter-spacing:.05em;}
.role .t {font-weight:700; font-size:1rem; margin:.1rem 0 .25rem 0; color:#1B2430;}
.role .d {font-size:.85rem; color:#4A5560; line-height:1.35;}
.arrow {align-self:center; color:#A7B1BA; font-size:1.3rem;}
table.ht {border-collapse:collapse; width:100%; font-size:.9rem;}
table.ht th {text-align:left; color:#5B6670; font-weight:600; border-bottom:2px solid #E3E7EB; padding:.35rem .5rem;}
table.ht td {border-bottom:1px solid #EEF1F4; padding:.35rem .5rem; vertical-align:top;}
table.ht code {font-size:.82rem;}
</style>""", unsafe_allow_html=True)


def chip(label: str, kind: str | None = None) -> str:
    """A small coloured pill; `kind` picks the colour (accepted, rejected, inconclusive, supported, refuted, ...)."""
    k = (kind or label).replace(" ", "-").lower()
    return f"<span class='chip c-{html.escape(k)}'>{html.escape(label)}</span>"


def kpi(col, key: str, value: str, sub: str) -> None:
    col.markdown(f"<div class='kpi'><div class='k'>{html.escape(key)}</div><div class='v'>{html.escape(value)}</div>"
                 f"<div class='s'>{html.escape(sub)}</div></div>", unsafe_allow_html=True)


def highlight_bars(df: pd.DataFrame, label: str, value: str, highlight: set[str], *, fmt: str = ".0%",
                   domain: list[float] | None = None, title: str | None = None) -> alt.Chart:
    """Horizontal bars, one colour for the rows that matter and grey for the rest, with the value printed."""
    df = df.assign(_hl=df[label].isin(highlight))
    x = alt.X(f"{value}:Q", title=None, axis=alt.Axis(format=fmt, grid=True),
              scale=alt.Scale(domain=domain) if domain else alt.Undefined)
    base = alt.Chart(df, title=title or alt.Undefined).encode(
        y=alt.Y(f"{label}:N", sort=list(df[label]), title=None, axis=alt.Axis(labelLimit=280, labelFontSize=12)),
        x=x, tooltip=[label, alt.Tooltip(f"{value}:Q", format=fmt)])
    bars = base.mark_bar(cornerRadiusEnd=4).encode(
        color=alt.condition("datum._hl", alt.value(ACCENT), alt.value(MUTED)))
    text = base.mark_text(align="left", dx=5, fontSize=12, color="#333").encode(text=alt.Text(f"{value}:Q", format=fmt))
    return (bars + text).properties(height=alt.Step(30))


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def rate_chart(rows: list[dict], title: str) -> alt.Chart:
    """Correct and causally-supported rate per system, as grouped horizontal bars on one 0–100% axis."""
    long = [{"System": r["label"], "Metric": m, "Rate": r[k]}
            for r in rows for m, k in (("Correct", "correct"), ("Causally supported", "causally_supported"))]
    df = pd.DataFrame(long)
    order = [r["label"] for r in rows]
    base = alt.Chart(df, title=title).encode(
        y=alt.Y("System:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
        yOffset=alt.YOffset("Metric:N", sort=["Correct", "Causally supported"]),
        x=alt.X("Rate:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", grid=True), title=None),
        color=alt.Color("Metric:N", scale=METRIC_COLORS, legend=alt.Legend(orient="top", title=None)),
        tooltip=["System", "Metric", alt.Tooltip("Rate:Q", format=".1%")],
    )
    bars = base.mark_bar(cornerRadiusEnd=3)
    text = base.mark_text(align="left", dx=4, fontSize=12, color="#333").encode(text=alt.Text("Rate:Q", format=".0%"))
    # One band of 44 px per system, split between the two metrics by the yOffset channel.
    return (bars + text).properties(height=alt.Step(44))


# ====================================================================== page 1
def page_idea() -> None:
    st.title("Run It, Then Cite It", anchor=False)
    st.markdown(
        "<div class='hero'><div class='tag'>LMA Group Project · Team Disco 82</div>"
        "<h1>Don't trust the docs. Run the code, then flip the switch.</h1>"
        "<p>Developers ask how a library behaves when its <b>documentation may be wrong</b>. AI assistants tend to repeat "
        "the docs and cite lines that <i>look</i> related but don't decide the behaviour. Our agent checks its own answer "
        "twice: by <b>executing</b> every claim, and by <b>mutating</b> every cited line.</p></div>",
        unsafe_allow_html=True)
    k = st.columns(4)
    kpi(k[0], "Real developer questions", "170", "GitHub issues of click and marshmallow, gold from the merged fix")
    kpi(k[1], "Ours vs single-call RAG", "+18.6 pts", "correct and causally cited, 95% CI [+10.3, +26.9]")
    kpi(k[2], "Ours vs ReAct, same tools", "−9.7 pts", "pre-registered H1 not supported: an honest negative result")
    kpi(k[3], "Unsafe actions executed", "0", "every probe runs in a no-network, read-only Docker sandbox")
    st.write("")
    st.markdown("#### How the agent answers")
    c1, c2, c3 = st.columns(3)
    with c1, st.container(border=True):
        st.markdown("#### 1 · Draft")
        st.markdown("Investigate the frozen repository with tools (search, open, definitions, references, git history), "
                    "then write an answer split into **atomic claims**, each citing code lines.")
    with c2, st.container(border=True):
        st.markdown("#### 2 · Run it")
        st.markdown("Test each behavioural claim with a tiny generated **probe**, executed in an offline Docker sandbox "
                    "against the library frozen *before* the fix. A refuted claim becomes the next investigation goal.")
    with c3, st.container(border=True):
        st.markdown("#### 3 · Flip the switch")
        st.markdown("**Mutate** each cited line in a throw-away copy. Accept it as *causal* only if the claim's outcome "
                    "changes **and** a control probe does not. A rejected citation sends the agent looking for the real line.")

    st.divider()
    st.subheader("The dataset: real GitHub issues, answer key from the developer's own fix")
    st.markdown("An issue is the question; the merged fix and its test are the answer key (the SWE-bench recipe). "
                "The fix's test, run on the frozen code, shows the old behaviour; the lines the fix changed are the gold "
                "evidence. **No LLM touches the gold.**")
    m = st.columns(5)
    m[0].metric("Closed PRs mined", "3,303")
    m[1].metric("Validated by running", "176")
    m[2].metric("Questions", "170", help="click 146, marshmallow 24")
    m[3].metric("Test set (locked)", "150", help="SHA-256 recorded in PREREGISTRATION.md before any test run")
    m[4].metric("After human spot check", "145", "-5 invalid", delta_color="off")
    st.caption("Systems compared: B0 closed book · B1 one-call RAG · B2 ReAct with **all the same tools** · ours · "
               "ablations A1 (no execution), A2 (no mutation), A3 (flag only), A10 (no / oracle retrieval). "
               "Same model (gemini-3.1-flash-lite), same budget (25 requests/question), same sandbox.")
    st.caption("Page 5 shows the exploratory multi-agent extension: five specialised roles, hybrid retrieval, a code graph "
               "and smarter experiments, aimed at finding the exact line that causes a bug.")


# ====================================================================== page 2
def page_live() -> None:
    st.title("Live: run it, then flip the switch")
    st.markdown("**toylib** is a tiny library with planted ground truth. Its docstring says *strict is on by default, so "
                "negatives raise*, but an override turns it off, so **the docs are wrong**. Here the probes are hand-written "
                "(no LLM, no quota); the real agent writes them itself.")
    claims = D.toylib_claims()
    source = D.toylib_source()
    if "docker_ok" not in st.session_state:  # checked once per browser session: `docker image inspect` takes a moment
        st.session_state["docker_ok"] = D.docker_ready()
    if "use_docker" not in st.session_state:
        st.session_state["use_docker"] = st.session_state["docker_ok"]

    left, right = st.columns([1.15, 1])
    with right:
        names = [c["name"] for c in claims]
        ci = st.selectbox("Claim to verify", range(len(claims)), format_func=lambda i: names[i])
        claim = claims[ci]
        options = [p["line"] for p in claim["planted"]]
        labels = {p["line"]: f"line {p['line']} · {p['mark']}  (planted: {'causal' if p['causal'] else 'not causal'})"
                  for p in claim["planted"]}
        pick = st.radio("Cited line to check", options + ["other"], format_func=lambda v: labels.get(v, "another line…"))
        line = st.number_input("Line number", 1, len(source), 88) if pick == "other" else pick
        st.toggle("Use the Docker sandbox", key="use_docker", disabled=not st.session_state["docker_ok"],
                  help="Off: the trusted local runner (allowed only for these hand-written toylib probes). "
                       "On: the same no-network container the experiments used.")
        with st.expander("Show the claim probe and the control probe"):
            st.code(claim["claim"].strip(), language="python")
            st.code(claim["control"].strip(), language="python")

    with left:
        lo, hi = max(1, int(line) - 9), min(len(source), int(line) + 9)
        rows = []
        for i in range(lo, hi + 1):
            text = html.escape(source[i - 1])
            style = "background:#FFE8B3;font-weight:600;" if i == int(line) else ""
            rows.append(f"<div style='{style}white-space:pre;font-family:monospace;font-size:13px;'>"
                        f"<span style='color:#888;'>{i:4d}  </span>{text}</div>")
        st.markdown("**toylib/core.py**")
        st.markdown(f"<div style='border:1px solid #ddd;border-radius:6px;padding:8px;overflow-x:auto;'>{''.join(rows)}</div>",
                    unsafe_allow_html=True)

    st.divider()
    b1, b2 = st.columns(2)
    run_probe = b1.button("① Run it: execute the claim and control probes", width="stretch")
    run_mut = b2.button("② Flip the switch: mutate the cited line", type="primary", width="stretch")

    if run_probe or run_mut:
        with st.spinner("Running in the sandbox…"):
            session = D.toylib_session(bool(st.session_state.get("use_docker")))
            try:
                if run_probe:
                    res = session.run_probes([("claim", claim["claim"]), ("control", claim["control"])])
                    st.session_state["probe_result"] = res
                    st.session_state.pop("mutation", None)
                else:
                    from analysis.toylib_ablations import REL
                    from tools.mutate import mutate_and_run
                    st.session_state["mutation"] = (int(line), mutate_and_run(session, REL, int(line), claim["claim"], [claim["control"]]))
            finally:
                session.cleanup()

    if run_probe and "probe_result" in st.session_state:
        res = st.session_state["probe_result"]["results"]
        cols = st.columns(2)
        for col, r, label in zip(cols, res, ("Claim probe", "Control probe")):
            ok = r["status"] == "pass"
            col.markdown(f"**{label}:** {'✅ pass' if ok else '❌ ' + r['status']}")
            col.code(D.describe_outcome(r["outcome"]), language=None)
        if res[0]["status"] == "pass":
            st.success("The claim holds on the frozen code. Next: is the cited line what *decides* it?")
        else:
            st.error("The claim is refuted: the agent would re-investigate with this observed output as its goal.")

    if "mutation" in st.session_state and st.session_state["mutation"][0] == int(line) and not run_probe:
        _, rep = st.session_state["mutation"]
        planted = {p["line"]: p["causal"] for p in claim["planted"]}
        st.markdown(f"#### Mutants of line {int(line)}  ·  original claim outcome: `{D.describe_outcome(rep.original_claim)}`")
        if rep.mutants:
            table = pd.DataFrame([{
                "mutant": m.description,
                "claim outcome": D.describe_outcome(m.claim),
                "control outcome": D.describe_outcome(m.controls[0] if m.controls else None),
                "claim changed": "yes" if m.flags["claim_changed"] else "",
                "breakage": "yes" if m.flags["breakage"] else "",
                "control changed": "yes" if m.flags["controls_changed"] else "",
                "specific flip": "✅" if m.flags["specific"] else "",
            } for m in rep.mutants])
            st.dataframe(table, hide_index=True, width="stretch")
        v = st.columns(4)
        for col, rule, help_ in zip(v, ("any_flip", "behavioural", "specific"),
                                    ("any outcome change", "a change that is not mere breakage",
                                     "behavioural, and the control is unchanged (used by the agent)")):
            col.metric(rule, "accept" if rep.verdicts[rule] else "reject", help=help_)
        if int(line) in planted:
            right_ = rep.verdicts["specific"] == planted[int(line)]
            v[3].metric("planted truth", "causal" if planted[int(line)] else "not causal",
                        "agent's rule is right" if right_ else "agent's rule is wrong", delta_color="normal" if right_ else "inverse")
        if rep.causal:
            st.success(D.explain_verdict(rep))
        else:
            st.warning(D.explain_verdict(rep))


# ====================================================================== page 3
def page_results() -> None:
    st.title("Results")
    res = D.analysis("main_test")
    if not res:
        st.error("results/summary/analysis_main_test/analysis.json is missing. Run `python -m analysis.make_all --run-id main --split test`.")
        return
    st.markdown("**145 locked test questions** (150 minus 5 removed by the human spot check). Pre-registered hypotheses; "
                "paired tests (McNemar, bootstrap 95% CIs).")
    tabs = st.tabs(["Main comparison", "Hypotheses", "Ablations", "Does mutation find causal lines?", "Judge vs humans", "Safety"])

    with tabs[0]:
        rows = D.summary_rows(res)
        main = [r for r in rows if r["system"] in ("b0", "b1", "b2", "ours")]
        c1, c2 = st.columns([1.3, 1])
        c1.altair_chart(rate_chart(main, "Judge labels · 145 questions"), width="stretch")
        hrows = D.human_rows(res)
        if hrows:
            c2.altair_chart(rate_chart([r for r in hrows if r["system"] in ("b1", "b2", "ours")],
                                       "Human labels · 12 questions (primary, by the kappa rule)"), width="stretch")
        st.dataframe(pd.DataFrame([{
            "System": r["label"], "Correct": pct(r["correct"]), "Causally supported": pct(r["causally_supported"]),
            "Fix-location recall": pct(r["fix_location_recall"]), "Confident errors": r["confident_errors"],
            "Coverage": pct(r["coverage"]), "Requests / q": f"{r['requests']:.1f}", "Tokens / q": f"{r['tokens']:,.0f}",
        } for r in rows]), hide_index=True, width="stretch")
        st.info("**Reading:** tools matter enormously (B0 → B1 → B2), but our extra checks did **not** beat a ReAct agent "
                "given the same tools, and cost 40% more requests.")

    with tabs[1]:
        h = res["hypotheses"]
        cols = st.columns(3)
        h1 = h["H1"]["comparison"]
        with cols[0], st.container(border=True):
            st.markdown("**H1** · ours beats B2 on causally-supported answers by ≥ 8 points")
            st.markdown("### ❌ Not supported")
            st.markdown(f"Judge, 145 q: {pct(h1['a_rate'])} vs {pct(h1['b_rate'])}  \n"
                        f"Δ {100 * h1['diff']:+.1f} pts, CI [{100 * h1['ci_low']:+.1f}, {100 * h1['ci_high']:+.1f}]  \n"
                        "Humans, 12 q: 25.0% vs 41.7%")
        h2 = h["H2"]
        with cols[1], st.container(border=True):
            st.markdown("**H2** · ≥ 40% fewer confident errors than B2, coverage ≤ 10 pts lower")
            st.markdown("### ➖ Inconclusive")
            st.markdown(f"{pct(h2['confident_error_ours'])} vs {pct(h2['confident_error_b2'])} confident errors  \n"
                        f"relative reduction {pct(h2['relative_reduction'])}; coverage {pct(h2['coverage_ours'])} vs {pct(h2['coverage_b2'])}")
        h3 = h["H3"]["comparison"]
        with cols[2], st.container(border=True):
            st.markdown("**H3** · mutation raises human-judged citation precision by ≥ 15 pts (vs A2)")
            st.markdown("### ❌ Not supported")
            st.markdown(f"Humans: {pct(h3['a_precision'])} with mutation vs {pct(h3['b_precision'])} without  \n"
                        f"Δ {100 * h3['diff']:+.1f} pts, CI [{100 * h3['ci_low']:+.1f}, {100 * h3['ci_high']:+.1f}]")

    with tabs[2]:
        rows = {r["system"]: r for r in D.summary_rows(res)}
        abl = [rows[s] for s in ("ours", "a1", "a2", "a3") if s in rows]
        st.altair_chart(rate_chart(abl, "Removing one part of the procedure (judge labels, 145 questions)"), width="stretch")
        st.dataframe(pd.DataFrame([{"System": r["label"], "Correct": pct(r["correct"]), "Causally supported": pct(r["causally_supported"]),
                                    "Confident errors": r["confident_errors"], "Coverage": pct(r["coverage"]),
                                    "Requests / q": f"{r['requests']:.1f}"} for r in abl]), hide_index=True, width="stretch")
        st.markdown("- **A1, no execution:** more confident errors (53 vs 43), same correctness.\n"
                    "- **A2, no mutation:** same correctness, *better* citations by humans (44.1% vs 30.6%).\n"
                    "- **A3, flag only:** a third fewer confident errors (29 vs 43, p = 0.004) at equal correctness: "
                    "re-investigation did not pay off.")
        sub = D.analysis("sub50_test")
        if sub:
            srows = D.summary_rows(sub)
            st.altair_chart(rate_chart([r for r in srows if r["system"] in ("ours", "a10none", "a10oracle")],
                                       "A10: what the agent starts with (47 questions)"), width="stretch")
            st.caption("Correctness does not depend on the starting material; without retrieval, fix-location recall drops "
                       "from 59.6% to 44.7% (p = 0.016). Handing it the right files (oracle) does not help.")

    with tabs[3]:
        r = res["rq2"]
        st.markdown(f"Our agent ran **{r['checks']} mutation checks** on test. How well do the verdicts agree with "
                    "(a) the lines the developer actually changed and (b) two human labellers?")
        kdf = pd.DataFrame([{"Rule": rule, "Reference": ref, "Kappa": v}
                            for rule in ("any_flip", "behavioural", "specific")
                            for ref, v in (("vs developer fix lines", r["rules"][rule]["kappa_vs_fix_lines"]),
                                           ("vs human labels", (r.get("human") or {}).get(rule, {}).get("kappa")))
                            if v is not None])
        enc = alt.Chart(kdf).encode(
            x=alt.X("Rule:N", sort=["any_flip", "behavioural", "specific"], title=None, axis=alt.Axis(labelAngle=0, labelFontSize=13)),
            xOffset="Reference:N", y=alt.Y("Kappa:Q", scale=alt.Scale(domain=[-0.2, 1]), title="Cohen's kappa"),
            color=alt.Color("Reference:N", scale=alt.Scale(range=["#4C78A8", "#F58518"]), legend=alt.Legend(orient="top", title=None)),
            tooltip=["Rule", "Reference", "Kappa"])
        # Values are printed because the kappas against fix lines are about 0, so their bars are nearly invisible.
        label = alt.Text("Kappa:Q", format="+.2f")
        bars = (enc.mark_bar(cornerRadiusEnd=3)
                + enc.mark_text(dy=-9, fontSize=13).encode(text=label).transform_filter("datum.Kappa >= 0")
                + enc.mark_text(dy=12, fontSize=13).encode(text=label).transform_filter("datum.Kappa < 0"))
        good = alt.Chart(pd.DataFrame({"y": [0.6]})).mark_rule(strokeDash=[4, 4], color="#2E7D32").encode(y="y:Q")
        zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color="#555").encode(y="y:Q")
        st.altair_chart((bars + good + zero).properties(height=320), width="stretch")
        st.caption("Dashed line: kappa 0.6, our pre-registered bar for good agreement. Zero means chance.")
        sp = r["rules"]["specific"]
        st.warning(f"The rule the agent uses (`specific`) accepted only {pct(sp['recall_vs_fix_lines'])} of the developers' fix "
                   "lines it checked, and agreed with humans *worst* of the three rules. That is the mechanism behind H1 and H3.")

    with tabs[4]:
        ag = D.agreement()
        if ag:
            k = ag["kappa"]
            c = st.columns(4)
            c[0].metric("Humans vs humans · answers", f"{k['answer']['human_human']:.2f}")
            c[1].metric("Judge vs humans · answers", f"{k['answer']['consensus_judge']:.2f}", "below 0.6", delta_color="inverse")
            c[2].metric("Humans vs humans · citations", f"{k['citation']['human_human']:.2f}")
            c[3].metric("Judge vs humans · citations", f"{k['citation']['consensus_judge']:.2f}", "below 0.6", delta_color="inverse")
            st.markdown("Two members labelled 72 answers and 204 citations separately and blind to the system. The LLM judge "
                        "(gpt-oss-120b) was **too lenient on citations**, so by our pre-registered rule the human labels "
                        "decide the primary comparison.")

    with tabs[5]:
        tu = res["tool_use"]
        st.dataframe(pd.DataFrame([{"System": D.SYSTEM_NAMES.get(s, s), "Tool calls": t["tool_calls"],
                                    "Valid calls": pct(t["valid_call_rate"]), "Probes": t["probes_submitted"],
                                    "Blocked unsafe attempts": t["unsafe_attempts"], "Unsafe actions executed": t["unsafe_executed"]}
                                   for s, t in tu.items() if t["tool_calls"] and s in ("ours", "b2", "a2", "a3")]),
                     hide_index=True, width="stretch")
        adv = D.adversarial()
        if adv:
            st.markdown("**Prompt injection (15 planted instructions):**")
            st.dataframe(pd.DataFrame([{"System": D.SYSTEM_NAMES.get(s, s), "Exposed": f"{v['by_kind']['all']['exposed']}/15",
                                        "Obeyed when exposed": f"{v['by_kind']['all']['complied_when_exposed']}/{v['by_kind']['all']['exposed']}",
                                        "Unsafe actions executed": v["by_kind"]["all"]["unsafe_executed"]}
                                       for s, v in adv.items() if isinstance(v, dict) and "by_kind" in v]),
                         hide_index=True, width="stretch")
        st.success("No system executed an unsafe action: every probe runs in a no-network, read-only container behind an AST policy.")


# ====================================================================== page 4
def page_question() -> None:
    st.title("Inside one question")
    qs = D.questions("test")
    removed = D.spot_check_removed()
    have = D.answered("main", "ours") & D.answered("main", "b2")
    qids = sorted(q for q in qs if q in have and q not in removed)
    if not qids:
        st.warning("The raw answers are not on this machine (`results/main/` is not in git). This page works on the "
                   "machine that ran the experiments; the Results page works everywhere.")
        return
    featured = [q for q in D.FEATURED if q in qids]
    default = featured[0] if featured else qids[0]
    qid = st.selectbox("Question", featured + [q for q in qids if q not in featured], index=0 if featured else qids.index(default),
                       format_func=lambda q: f"⭐ {q}" if q in D.FEATURED else q)
    if qid in D.FEATURED:
        st.info(D.FEATURED[qid])
    q = qs[qid]
    with st.container(border=True):
        st.markdown(f"**{q['library']} · issue #{q['issue_number']}** · category `{q['category']}`")
        st.markdown(q["question_text"][:1500] + ("…" if len(q["question_text"]) > 1500 else ""))
    with st.expander("Answer key (built from the developer's fix; never shown to any system)"):
        st.markdown(q["gold_answer"])
        for e in q["gold_evidence"]:
            st.markdown(f"- [{e['path']} lines {e['line_start']}–{e['line_end']}]({D.github_link(q, e['path'], e['line_start'], e['line_end'])}) ({e['kind']})")

    systems = [s for s in D.ORDER if qid in D.answered("main", s)]
    c = st.columns(2)
    picks = [c[0].selectbox("Left", systems, index=systems.index("ours"), format_func=D.SYSTEM_NAMES.get),
             c[1].selectbox("Right", systems, index=systems.index("b2"), format_func=D.SYSTEM_NAMES.get)]
    cols = st.columns(2)
    for col, s in zip(cols, picks):
        ans, j = D.answer("main", s, qid), D.judgement("main", s, qid)
        with col:
            verdict = (j or {}).get("correctness", "not judged")
            icon = {"correct": "🟢", "partial": "🟡", "incorrect": "🔴"}.get(verdict, "⚪")
            st.markdown(f"### {D.SYSTEM_NAMES.get(s, s)}")
            st.markdown(f"{icon} **Judge: {verdict}**" + (f": {j.get('reason')}" if j and j.get("reason") else ""))
            if ans.get("flagged_uncertain") or ans.get("abstained"):
                st.caption("⚑ flagged as uncertain" if ans.get("flagged_uncertain") else "⚑ abstained")
            st.markdown(ans.get("answer_text", ""))
            labels = [x.get("label") if isinstance(x, dict) else x for x in (j or {}).get("citations", [])]
            i = 0
            for n, cl in enumerate(ans.get("claims", []), 1):
                with st.container(border=True):
                    st.markdown(f"**Claim {n}** `{cl.get('grade') or '—'}`: {cl.get('text', '')}")
                    for cit in cl.get("citations", []):
                        gold = D.in_gold(cit["path"], cit["line"], q["gold_evidence"])
                        lab = labels[i] if i < len(labels) else None
                        i += 1
                        tags = (["🎯 in the developer's fix"] if gold else []) + ([f"judge: {lab}"] if lab else []) + \
                               (["mutation: causal"] if cit.get("causal") is True else ["mutation: not causal"] if cit.get("causal") is False else [])
                        st.markdown(f"`{cit['path']}:{cit['line']}`  " + " · ".join(tags))
                        snip = D.frozen_snippet(q, cit["path"], cit["line"])
                        if snip:
                            with st.expander("code at the frozen commit"):
                                st.code(snip, language=None)
            m = st.columns(3)
            m[0].metric("Requests", ans.get("requests", "–"))
            m[1].metric("Probe runs", ans.get("probe_runs", 0))
            m[2].metric("Mutant runs", ans.get("mutant_runs", 0))
            if s in ("ours", "a2", "a3", "a1") and ans.get("decisions"):
                with st.expander("Decision log (what the agent did, step by step)", expanded=(s == "ours")):
                    for step in D.timeline(ans):
                        st.markdown(f"{step['icon']} **{step['title']}**" + (f"  \n<span style='color:#666'>{html.escape(step['detail'])}</span>"
                                                                             if step["detail"] else ""), unsafe_allow_html=True)


# ====================================================================== page 5
ROLES = [
    ("1 · LLM", "Bug Investigator", "Reads the code with tools; states expected vs actual behaviour and 2–4 competing hypotheses."),
    ("2 · LLM", "Probe Engineer", "Writes a probe that reproduces the behaviour, plus controls; runs them in the sandbox."),
    ("3 · LLM", "Code Analyst", "Ranks the lines most likely to decide the behaviour (from E3, helped by the code graph)."),
    ("4 · code", "Experiment Engineer", "Mutates candidate lines: accepted, inconclusive or rejected. Pairs (E4), information gain (E5)."),
    ("5 · LLM", "Causal Verifier", "Judges each hypothesis, writes the answer and a one-line patch, which code re-validates."),
]


def page_extension() -> None:
    st.title("Multi-agent extension: where is the bug?", anchor=False)
    st.markdown("Can **specialised agents**, **hybrid retrieval**, a **code graph** and **smarter experiments** find the "
                "line that causes a reported behaviour better than one agent? Pre-registered separately after the main "
                "study, run on **47 test questions**; exploratory. No agent framework: typed hand-offs in "
                "`multiagent/orchestrator.py`.")
    parts = []
    for i, (n, t, d) in enumerate(ROLES):
        if i:
            parts.append("<div class='arrow'>→</div>")
        parts.append(f"<div class='role'><div class='n'>{n}</div><div class='t'>{t}</div><div class='d'>{d}</div></div>")
    st.markdown(f"<div class='pipe'>{''.join(parts)}</div>", unsafe_allow_html=True)
    st.caption("E1 the five roles · E2 + hybrid retrieval (BM25 + dense, RRF, rerank) · E3 + code graph (call graph, "
               "dependences, slices, Ochiai spectra) · E4 + pair mutation · E5 + information-gain experiment order · "
               "E6 = E5 with its tools behind an MCP server. Same model, sandbox and mutation code as the main study.")

    ext, ret = D.extension(), D.retrieval_study()
    if not ext:
        st.error("results/summary/extension.json is missing. Run `python -m analysis.extension --run-id ext`.")
        return
    rows = D.ext_rows(ext)
    tabs = st.tabs(["Walk through one question", "Localization", "Retrieval study", "Cost and verification",
                    "Predictions vs outcomes"])

    with tabs[0]:
        _ext_walkthrough()

    with tabs[1]:
        k = st.columns(4)
        by = {r["system"]: r for r in rows}
        kpi(k[0], "Best extension, line Top-3", pct(by["E2"]["line_top3"]), "E2 roles + hybrid retrieval")
        kpi(k[1], "ReAct baseline, line Top-3", pct(by["B2"]["line_top3"]), "no significant difference (p = 0.51)")
        kpi(k[2], "Adding the code graph", "−19.1 pts", "E3 vs E2, p = 0.035: refuted prediction")
        kpi(k[3], "Right function in Top-3", f"{min(r['fn_top3'] for r in rows):.0%}–{max(r['fn_top3'] for r in rows):.0%}",
            "the exact line is the hard part")
        st.write("")
        df = pd.DataFrame([{"System": r["label"], "Line Top-3": r["line_top3"]} for r in rows])
        st.altair_chart(highlight_bars(df, "System", "Line Top-3", {D.EXT_NAMES["E2"]}, domain=[0, 1],
                                       title="Is a developer's fix line among the top 3? (47 questions)"), width="stretch")
        st.dataframe(pd.DataFrame([{"System": r["label"], "Line Top-1": pct(r["line_top1"]), "Line Top-3": pct(r["line_top3"]),
                                    "Line MRR": f"{r['line_mrr']:.3f}", "Function Top-3": pct(r["fn_top3"]),
                                    "Correct (judge)": pct(r["correct"])} for r in rows]), hide_index=True, width="stretch")
        st.info("**Why the graph lowered Top-3:** it adds candidates (rankings grow from about 3 to about 8 lines), most come "
                "out *inconclusive*, and the final ranking puts them above the developer's lines that the mutation check "
                "had *rejected*. The graph exposed the same weakness as the main study: mutation rejects most real fix lines.")

    with tabs[2]:
        if ret:
            t = ret["table"]
            df = pd.DataFrame([{"Mode": D.RETRIEVAL_NAMES[m], "hit@5": t[m]["hit@5"]} for m in D.RETRIEVAL_NAMES if m in t])
            c1, c2 = st.columns([1.4, 1])
            c1.altair_chart(highlight_bars(df, "Mode", "hit@5", {D.RETRIEVAL_NAMES["R3"]}, domain=[0, 1],
                                           title=f"Relevant code in the top 5 ({ret['n_questions']} questions, no LLM)"),
                            width="stretch")
            with c2:
                kpi(st, "Fusion (RRF) vs BM25", "+7.7 pts", "hit@5, 95% CI [+1.4, +14.1], p = 0.035: the clear win")
                st.write("")
                kpi(st, "Adding the reranker", "−11.3 pts", "p = 0.009: a web-trained cross-encoder hurts on code")
            st.caption("E2–E6 kept the reranker, as pre-registered: switching after seeing test results would be tuning on test.")

    with tabs[3]:
        ext_only = [r for r in rows if r["system"] in ("E0", "B2", "E1", "E2", "E3", "E5")]
        c1, c2 = st.columns(2)
        c1.altair_chart(highlight_bars(pd.DataFrame([{"System": r["label"], "Requests per question": r["requests"]} for r in ext_only]),
                                       "System", "Requests per question", {D.EXT_NAMES["E1"], D.EXT_NAMES["E2"]}, fmt=".1f",
                                       title="API requests per question"), width="stretch")
        c2.altair_chart(highlight_bars(pd.DataFrame([{"System": r["label"], "Tokens per question": r["tokens"]} for r in ext_only]),
                                       "System", "Tokens per question", {D.EXT_NAMES["E1"], D.EXT_NAMES["E2"]}, fmt=",.0f",
                                       title="Tokens per question"), width="stretch")
        acc = [{"System": r["label"], "Lines": which, "Accepted": r[key]} for r in rows
               if r["system"] in ("E1", "E2", "E3", "E5") for which, key in
               (("developer's fix lines", "acceptance_on_gold"), ("other lines", "acceptance_on_other"))]
        chart = alt.Chart(pd.DataFrame(acc), title="How often mutation accepts a tested line").encode(
            y=alt.Y("System:N", title=None, sort=[D.EXT_NAMES[s] for s in ("E1", "E2", "E3", "E5")],
                    axis=alt.Axis(labelLimit=280, labelFontSize=12)),
            yOffset="Lines:N", x=alt.X("Accepted:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1]), title=None),
            color=alt.Color("Lines:N", scale=alt.Scale(range=[ACCENT, MUTED]), legend=alt.Legend(orient="top", title=None)),
            tooltip=["System", "Lines", alt.Tooltip("Accepted:Q", format=".1%")])
        st.altair_chart((chart.mark_bar(cornerRadiusEnd=4) + chart.mark_text(align="left", dx=4, fontSize=12, color="#333")
                         .encode(text=alt.Text("Accepted:Q", format=".0%"))).properties(height=alt.Step(26)), width="stretch")
        st.markdown("- **Roles are efficient:** half the requests of E0 (7.6 vs 14.9) and a sixth of the tokens, correctness "
                    "statistically unchanged.\n"
                    "- **Pairs (E4):** 95 pair checks, none accepted.  **Information gain (E5):** mutant runs 15.2 → 11.4 per "
                    "question with the same Top-3.  **MCP (E6):** identical answers to E5 on 47 of 47.\n"
                    "- **The bottleneck is the causal test:** only about 1 in 5 of the developers' own lines is accepted.")

    with tabs[4]:
        body = "".join(f"<tr><td>{i}</td><td>{html.escape(p)}</td><td>{chip(s)}</td><td>{html.escape(o)}</td></tr>"
                       for i, (p, s, o) in enumerate(D.EXT_PREDICTIONS, 1))
        st.markdown("<table class='ht'><tr><th>#</th><th>Prediction (written before any test run)</th><th>Status</th>"
                    f"<th>Outcome</th></tr>{body}</table>", unsafe_allow_html=True)
        st.caption("Two supported, two partly, one not supported, one refuted. Exploratory: on 47 questions, differences under "
                   "about 15 points cannot be told apart from noise.")


def _ext_walkthrough() -> None:
    """One question through the five roles, from the stored E1-E6 answers (local runs only)."""
    systems = [s for s in ("E5", "E2", "E3", "E1", "E4", "E6") if D.ext_answered(s)]
    if not systems:
        st.warning("The extension's raw answers are not on this machine (`results/ext/` is not in git). The other tabs "
                   "work everywhere.")
        return
    qs = D.questions("test")
    c1, c2 = st.columns([1, 2])
    system = c1.selectbox("Configuration", systems, format_func=lambda s: D.EXT_NAMES.get(s, s))
    have = sorted(q for q in D.ext_answered(system) if q in qs)
    featured = [q for q in D.EXT_FEATURED if q in have]
    qid = c2.selectbox("Question", featured + [q for q in have if q not in featured],
                       format_func=lambda q: f"⭐ {q}" if q in D.EXT_FEATURED else q)
    a, q = D.ext_answer(system, qid), qs[qid]
    gold = q["gold_evidence"]
    if qid in D.EXT_FEATURED:
        st.info(D.EXT_FEATURED[qid])
    with st.container(border=True):
        st.markdown(f"**{q['library']} · issue #{q['issue_number']}**")
        st.markdown(q["question_text"][:900] + ("…" if len(q["question_text"]) > 900 else ""))
        st.caption("Developer's fix (hidden from every agent): " + ", ".join(
            f"`{e['path']}` {e['line_start']}–{e['line_end']}" for e in gold))

    inv = a.get("investigation") or {}
    with st.expander("① Bug Investigator: expected vs actual, competing hypotheses", expanded=True):
        st.markdown(f"**Expected:** {inv.get('expected_behaviour', '—')}  \n**Actual:** {inv.get('actual_behaviour', '—')}")
        verdicts = {h["id"]: h for h in (a.get("verdict") or {}).get("hypotheses", [])}
        for h in inv.get("hypotheses", []):
            v = verdicts.get(h["id"], {}).get("verdict")
            locs = ", ".join(f"`{x['path']}:{x['line']}`" if isinstance(x, dict) else f"`{x}`"
                             for x in h.get("locations", [])[:4])
            st.markdown(f"**{h['id']}** {chip(v) if v else ''} {html.escape(h['statement'])}  \n"
                        f"<span style='color:#5B6670;font-size:.85rem'>suspects: {locs or '—'}</span>", unsafe_allow_html=True)

    probes = a.get("probes") or {}
    with st.expander(f"② Probe Engineer: probe status **{a.get('probe_status', '—')}**"):
        st.code(a.get("observations") or "no observations", language=None)
        if probes.get("reproduce"):
            st.code(probes["reproduce"].strip(), language="python")

    cands = a.get("candidates") or []
    with st.expander(f"③ Code Analyst: {len(cands)} candidate lines"):
        st.markdown(" ".join(f"`{c}`" + (" " + chip("developer's fix", "gold") if D.loc_in_gold(c, gold) else "")
                             for c in cands[:16]), unsafe_allow_html=True)

    ex = a.get("experiments") if isinstance(a.get("experiments"), dict) else {}
    with st.expander("④ Experiment Engineer: mutation checks", expanded=True):
        rows = []
        for x in ex.get("experiments", []):
            loc = " + ".join(f"<code>{html.escape(l)}</code>" for l in x["locs"])
            fix = " " + chip("developer's fix", "gold") if any(D.loc_in_gold(l, gold) for l in x["locs"]) else ""
            rows.append(f"<tr><td>{loc}{fix}</td><td>{x['kind']}</td><td>{chip(x['verdict'])}</td>"
                        f"<td>{x.get('n_mutants', len(x.get('mutants', [])))}</td><td>{html.escape(x.get('reason', ''))}</td></tr>")
        if rows:
            st.markdown("<table class='ht'><tr><th>Line(s)</th><th>Check</th><th>Verdict</th><th>Mutants</th><th>Why</th></tr>"
                        + "".join(rows) + "</table>", unsafe_allow_html=True)
        if ex.get("stop"):
            st.caption(f"Stopped early: {ex['stop']}")

    with st.expander("⑤ Causal Verifier: answer and patch", expanded=True):
        st.markdown((a.get("verdict") or {}).get("answer_text") or a.get("answer_text") or "—")
        pv = a.get("patch_validation")
        if pv:
            st.markdown(chip("patch validated", "supported") if pv.get("validated") else chip("patch not validated", "rejected"),
                        unsafe_allow_html=True)

    st.markdown("#### Final ranking (computed in code)")
    body = "".join(
        f"<tr><td>{i}</td><td><code>{html.escape(r['path'])}:{r['line']}</code></td><td>{chip(r['class'])}</td>"
        f"<td>{chip(chr(10003) + ' in the fix', 'gold') if D.in_gold(r['path'], r['line'], gold) else ''}</td></tr>"
        for i, r in enumerate(a.get("ranking", [])[:10], 1))
    st.markdown(f"<table class='ht'><tr><th>Rank</th><th>Line</th><th>Verdict</th><th>Developer's fix?</th></tr>{body}</table>",
                unsafe_allow_html=True)


PAGES = {"1 · The idea": page_idea, "2 · Live: run it, flip the switch": page_live,
         "3 · Results": page_results, "4 · Inside one question": page_question,
         "5 · Multi-agent extension": page_extension}

with st.sidebar:
    st.markdown("## 🧪 Run It, Then Cite It")
    # `?page=live` (or idea, results, question, extension) opens a page directly: handy for bookmarks.
    keys = {"idea": 0, "live": 1, "results": 2, "question": 3, "extension": 4}
    page = st.radio("Page", list(PAGES), index=keys.get(st.query_params.get("page", ""), 0), label_visibility="collapsed")
    st.divider()
    st.caption("LMA Group Project · Team Disco 82  \nAmeya Purohit · Sunil Kumar · Aditya Narayan Dwivedi · Sourav Nath")
    st.caption("[GitHub repository](https://github.com/ameya-purohit/LMA-Final-Project)")
    st.caption("Everything here is read from saved results or run on toylib: no LLM calls, no API quota.")

PAGES[page]()
