# Run It, Then Cite It — Proposal v2

LMA\_Group\_Project\_v1.mdOct 27, 2026 · @Ameya Purohit

**An AI assistant that answers questions about how software behaves, and proves each answer by actually running the software instead of trusting its manual.**

LMA Group Project, CL3.410, Monsoon 2026 · Team Disco 82 · Ameya Purohit (2025202006), Aditya Narayan Dwivedi (2025201026), Sourav Nath (2025201054), Sunil Kumar (2025201099)

This is version 2 of the proposal. Section 16 lists every change from v1 and the reason for it.

## The idea in plain words

**The problem.** Software comes with documentation: a manual that says what it does. Manuals go out of date, because the software changes and the manual does not. When a programmer asks an AI assistant how the software behaves, the assistant usually repeats the manual, mistakes included. When it points to "the part of the code responsible", it often points to code that looks related but does not actually control the behaviour.

**Our idea: two checks.**

1. **Try it and see.** Instead of trusting the manual, or its own reading of the code, the assistant writes a tiny experiment, runs the software, and records what really happens.
2. **Flip the switch.** To find which switch controls a lamp, you flip it and watch the lamp. When the assistant says "line 88 causes this", we change line 88 in a throw-away copy of the software and run the experiment again. If the behaviour changes, line 88 really is responsible. If nothing changes, the assistant pointed at the wrong place and must keep looking.

When either check fails, the assistant treats the failure as a clue about where to look next, much as a detective treats a broken alibi.

**An illustrative example.**

|  | What happens |
| --- | --- |
| The question | The manual says "strict checking is on by default", but the developer's program never reports an error. Why? |
| A typical AI assistant | Repeats the manual ("strict checking is on by default") and points to line 12, which sets the default. Both are wrong: line 12 is overridden later. |
| Our assistant, check 1 | Runs a tiny experiment and sees no error, so strict checking is actually off in this version. The manual is out of date. |
| Our assistant, check 2 | Changes line 12 in a copy: nothing changes, so line 12 is not responsible. Keeps looking, finds line 88 where the default is overridden, changes it in a copy, and the error appears. Line 88 is the cause. |
| Final answer | "The manual is out of date. Strict checking is off by default in this version; it is switched off at line 88. Verified by running it." |

**What we will find out.** We compare our assistant with standard AI assistants that have the same tools and the same budget, on about 150 real questions developers asked online whose correct answers are known. We measure how often answers are right and point to the right code, how often they are confidently wrong, and what each system costs. We also switch off each part of our design, one at a time, to see which parts actually matter.

**Who it is for.** Any programmer asking how a piece of code behaves when its documentation cannot be fully trusted. We test it on popular open-source Python toolkits, because there we can collect real questions with known correct answers (Section 1 explains why).

## Key terms

| Term | Meaning in plain words |
| --- | --- |
| Library | Ready-made code that other programs build on, for example a toolkit for handling dates |
| Documentation (docs) | The written manual describing what a library does |
| LLM | Large language model: the kind of AI behind chat assistants |
| Agent | An LLM that works in steps: it chooses an action (search, read, run code), sees the result, and decides what to do next |
| Tool call | The agent using an outside function, such as searching the code or running a test |
| Retrieval (RAG) | Fetching the relevant files first, so the answer is based on them rather than on the AI's memory |
| Claim | One checkable statement inside an answer |
| Probe | A tiny test program that checks one claim by running the code |
| Citation | A pointer to the line of code that supports a claim |
| Mutation, mutant | A small deliberate change to a copy of the code (for example turning "<" into ">"); the changed copy is a mutant |
| Causal citation | A citation whose line, when changed, changes the behaviour the claim describes |
| Frozen commit | The exact version of the code as it stood when the question was asked |
| Sandbox | A sealed, offline container where code runs without affecting anything else |
| Baseline | A standard system we compare against |
| Ablation | Our system with one part removed, to measure what that part contributes |
| ReAct | A common agent design that alternates thinking and acting |
| Chain-of-Verification (CoVe) | A method where the AI double-checks itself by asking and answering its own checking questions, by reading only |
| Confident error | A wrong answer given without any warning that it might be wrong |
| Token | A unit of text the AI reads or writes; AI services charge per token |
| Confidence interval (CI) | The range of values a result could plausibly take, given the number of test questions |
| LoRA | A cheap way to retrain a small AI model on a narrow task |

## Proposal at a glance

| Item | Summary |
| --- | --- |
| Domain | Software engineering |
| Target user | Any developer asking how a piece of code behaves when the documentation may be wrong: users of open-source libraries, engineers learning their company's code, maintainers deciding whether a reported problem is a bug or a documentation mistake |
| Testbed | Four popular open-source Python libraries (click, marshmallow, attrs, python-dateutil), chosen because they offer real questions with checkable answers |
| Problem | AI answers about code repeat out-of-date documentation, and the code they point to often looks related but does not actually cause the behaviour |
| Core idea | (1) Check every statement in the answer by running the code. (2) Check every code citation by changing the cited line in a copy and confirming the behaviour changes. Failed checks tell the assistant where to look next. |
| Main question | Do these two checks give more correct, correctly cited answers than a standard AI agent with the same tools and the same budget, and than an AI that double-checks itself by reading? |
| Capabilities | Tool calling and agentic decisions (core), reasoning, retrieval (RAG); fine-tuning as a stretch goal |
| Data | About 150 real developer questions from GitHub and Stack Overflow (2020 onwards), each with a verified correct answer, the correct code lines and a runnable check; about 60 questions with deliberately planted manual errors; 15 security test items |
| Compute | No GPU training; about 250 million AI tokens (roughly USD 125–500); about 60 CPU-hours of sandboxed test runs |

## 1. Target user, where the method applies, and our testbed

The method is meant for any developer asking how code behaves when its documentation cannot be trusted; we evaluate it on pure-Python libraries because they give real questions with checkable answers.

### 1.1 Target users

- **Users of open-source libraries** whose observed behaviour does not match the documentation, the kind of question posted as GitHub issues and on Stack Overflow.
- **Engineers learning an unfamiliar codebase**, for example a new team member asking what an internal module really does in a particular case.
- **Maintainers triaging reports**, deciding whether a reported problem is a bug in the code or a mistake in the documentation.

All three ask the same thing: *what does this code actually do, and where is that decided?*

### 1.2 Where the method applies

The method works wherever four conditions hold:

1. **The behaviour can be run offline**, without networks, databases or user interfaces (or with these replaced by stand-ins).
2. **The cited lines are the code that actually runs**, so changing them in a copy is meaningful. Interpreted languages such as Python, JavaScript or Ruby make this cheap.
3. **The exact version of the code can be frozen and rebuilt**, so every run is reproducible.
4. **Running one experiment is cheap**, a few seconds, so dozens of mutants per question are affordable.

It does **not** apply well to: code compiled from C, Rust or Go, where every change needs a slow rebuild; behaviour that depends on outside systems; random or concurrent behaviour, where one run proves little; and very large codebases, where the cost per question grows. We state these as limitations rather than claim them.

### 1.3 Testbed: pure-Python libraries

We evaluate on 2–4 of click, marshmallow, attrs and python-dateutil. Python libraries are the testbed, not the limit of the idea. We chose them for four reasons:

- **They meet all four conditions above.** Libraries whose logic sits in compiled extensions (for example pydantic-core, written in Rust) are excluded.
- **They come with real questions and known answers.** Public issues and Stack Overflow threads have maintainer replies and fixes we can use as the correct answer. Internal company code has no public questions, so it cannot be evaluated with ground truth.
- **Their history lets us freeze the code** at the moment each question was asked, so no system can see the later fix.
- **Keeping to one language and a few libraries** keeps annotation affordable and the statistics meaningful, as the course guidelines recommend.

We use only questions from 2020 onwards, so one pinned Python 3.10 sandbox can run every frozen version; older versions often need old interpreters. The must-have tier uses two libraries; more are added if the pilot finds too few eligible questions (Section 8).

**A small check of generality (stretch goal).** About 20 questions from a pure-Python *application* (not a library), or from one JavaScript library, run as an out-of-distribution test. This gives some evidence, not just an argument, that the method is not tied to our testbed.

### 1.4 What it is not

Not a bug-fixing system and not a general coding assistant. It answers questions and never edits the code, except throw-away copies used for mutation. It follows the course's Direction E: hypothesis-driven investigation where a verifier rejects claims the evidence does not support. Here the verifier is execution, not another AI.

## 2. Problem statement

The correct answer to "why does this library behave differently from its docs?" usually depends on code spread across files: where a default is set, where it is overridden, and which branch actually runs. LLMs given some of this material answer confidently and often repeat the documentation even when the code disagrees. Agents that search and read code do better, but they still decide behaviour by reading, and LLMs misread control flow, inheritance and overrides.

A second, less visible problem is the citations. An answer can cite lines that are on-topic but are not what produces the behaviour. Today, citation quality is judged by humans or by another LLM, which is either expensive or unreliable. Code offers an objective test that ordinary text does not: run the behaviour, then change the cited line and see whether the behaviour changes. No existing question-answering agent uses these two checks.

**Terminology.** Wallat et al. \[21\] separate citation *correctness* (the source supports the claim) from citation *faithfulness* (the model's answer was actually derived from that source). Our mutation test measures neither of these exactly. It measures a stronger, code-specific form of correctness: whether the cited line *causally decides* the claimed behaviour. We call this **causal citation correctness** and use "causal citation" throughout. We do not claim to measure faithfulness in Wallat et al.'s sense, which is a property of the model's generation process.

**Why it matters.** A developer acts on the answer. A wrong but confident answer, or a citation that points to the wrong line, costs debugging time. An answer whose claims were executed and whose citations were shown to be causal can be trusted and checked quickly.

## 3. Research questions and hypotheses

We ask two research questions; the "when and why" analysis that was RQ3 in v1 is now part of the analysis plan (Section 10.5).

**RQ1 (the procedure).** Does verifying each behavioural claim by execution and each citation by mutation, with failures fed back into the investigation, give more correct, causally cited answers and fewer confident errors than (a) a ReAct agent with the same tools, including execution and mutation, under a matched budget, and (b) self-verification by reading (Chain-of-Verification)?

**RQ2 (the mutation check as a measurement).** How well does the mutation check agree with human judgements of whether a citation causally decides the behaviour, compared with an LLM judge? Which acceptance rule agrees best: any outcome change, behavioural changes only, or behavioural changes plus a specificity control (Section 6.3)?

### Hypotheses (fixed before any experiment)

- **H1.** On real questions whose behaviour is executable, our agent beats B2 (ReAct with all the same tools) on the causally-supported answer rate by at least 8 percentage points. The paired 95% bootstrap CI must exclude zero. We also report the comparison against the budget-matched B2+ (Section 7).
- **H2.** Our agent's confident-error rate (wrong answers not flagged as uncertain) is at least 40% lower (relative) than B2's, **while its coverage (share of answers not flagged) is no more than 10 points below B2's**. The coverage condition stops H2 being met simply by flagging everything.
- **H3.** Human-judged causal citation precision is at least 15 points higher with the mutation check than without it (ablation A2, same agent otherwise).

Each hypothesis is falsified if its threshold is not met or its CI includes zero. All systems answer the same questions, so tests are paired: McNemar's test on discordant pairs and a paired bootstrap with 10,000 resamples.

**Pre-registered decomposition of H1.** The primary metric combines correctness and citation support. We report the two parts separately. If the H1 gain comes only from the citation part, with no change in correctness, we will report it as a citation result, not a correctness result.

### Why these thresholds, and the power we actually have

The thresholds are the smallest effects a developer would notice, not the smallest we can detect. 8 points is a gain that changes roughly one answer in twelve. The 40% relative reduction in H2 reflects that execution should mostly remove one specific failure, repeating wrong documentation. The 15 points in H3 is large because the mutation check is a hard filter on citations.

The v1 proposal said 8 points was "roughly the smallest difference we can reliably detect" with about 120 executable questions. That was wrong. For a paired comparison, the standard error of the difference in proportions is approximately:

```latex
\mathrm{SE}(\hat d) \approx \sqrt{\frac{p_{\mathrm{disc}} - d^{2}}{n}}
```

Here p\_disc is the share of questions where the two systems disagree. With n = 120 and p\_disc = 0.20, SE is about 4.0 points. An 8-point effect is then about 2 standard errors, which gives roughly **50% power** at alpha = 0.05. For 80% power we would need about 240 questions, or a true effect of about 11 points.

We keep the 8-point threshold because it is the practically meaningful effect. We state the consequence in advance: if H1's CI includes zero, we report the result as **inconclusive, not negative**, and give the CI so the reader can see which effect sizes it rules out. The 20-question pilot measures p\_disc; if it is lower than 0.20, power rises (at p\_disc = 0.15, power is about 63%).

## 4. Related work and what is new

The closest prior work tests documentation by execution, offline and function by function; none of it answers a developer's question or checks that a cited line causes the behaviour.

| Work | What it does | How we differ |
| --- | --- | --- |
| ReAct \[1\]; IRCoT \[2\]; FLARE \[3\] | Interleave reasoning with retrieval or tool use | They decide when to look further but never test whether a claim is true; claims are judged by reading |
| Self-RAG \[4\]; CRAG \[5\] | Learned critics judge whether retrieved passages support the output | Support is judged by a model, one passage at a time; no executable test |
| Chain-of-Verification \[6\] | The model writes verification questions and answers them independently | Verification is still done by reading. We verify by running code. CoVe is baseline B3 |
| CRITIC \[7\] | The model critiques its output with tools such as a code interpreter | Checks the model's own computations, not claims about a third-party codebase; does not test whether a citation is causal |
| SWE-agent \[8\]; Agentless \[9\] | Navigate repositories and fix issues | Judged on whether tests pass after a fix; the evidence cited in a natural-language answer is never checked |
| CASCADE \[10\] | Generates tests from documentation and code from documentation; reports an inconsistency only when the real code fails a test that the doc-generated code passes | **Closest work.** It checks documentation offline, per function. It does not answer a question, investigate across files, or cite lines, and does not use mutation |
| Document testing \[11\]; METAMON \[12\] | Run tests or metamorphic checks to find doc–behaviour inconsistencies | Same difference as CASCADE. We build on their finding that execution beats LLM judgement for this task |
| MUSE \[13\]; Metallaxis \[14\] | Mutate program lines and watch test outcomes to locate faults | We borrow the mechanism, including MUSE's idea of checking that a mutant changes the target outcome but not others, and apply it to checking an LLM's citations |
| Wallat et al. \[21\]; ALCE \[15\] | Separate citation correctness from faithfulness; metrics for citation quality | Their checks rely on human or model judgement. Mutation gives an executable counterfactual test of causal correctness for code |
| Code–comment inconsistency \[16\]; knowledge conflicts \[17\] | Detect outdated comments; study LLMs facing conflicting context | Classification or analysis only, not used inside an answering agent |

### Novelty: what we claim

1. **Mutation-verified causal citations.** A citation to line L for claim c is accepted only if some semantic mutation of L changes the observed outcome of c's probe, and that same mutant leaves unrelated control probes unchanged. This turns "does this line decide the behaviour?" from a judgement into an executable counterfactual test. To our knowledge, no prior question-answering or RAG system checks its citations this way.
2. **Verification failures as the investigation signal.** A refuted claim ("the probe shows ValueError, not None") or a non-causal citation ("mutating L88 changes nothing") becomes the agent's next sub-goal. The checks do not just filter the final answer; they direct where the agent looks next.
3. **Claim-level execution inside a question-answering agent.** Unlike CASCADE-style offline checks, the claims come from the agent's own answer to a developer's question, and every claim in the final answer is labelled with how it was established (Section 6.5).
4. **An evaluation resource and a measurement study.** Real developer questions with line-level gold evidence and gold executable probes, plus a study of whether the mutation check can serve as an automatic causal-citation metric (RQ2).

### What we do not claim

Running tests derived from documentation is not new (CASCADE, document testing). Mutation analysis is not new (mutation-based fault localisation). We do not measure model-internal citation faithfulness. Our contribution is combining execution and mutation inside a question-answering agent, so that both check the answer and both steer the investigation.

## 5. The capabilities: why each is needed and how we measure it

Tool calling and agentic decisions carry the research question; reasoning and RAG are necessary supports; fine-tuning is a stretch goal.

| Capability | Why our problem needs it | Ablation or comparison without it | Capability-specific metric |
| --- | --- | --- | --- |
| Tool calling (core) | Behaviour is settled by running probes and mutants; evidence is reached by following definitions, references, tests and history | A1 (no execution, verify by reading) | Probe executable rate; valid-call rate; recovery after tool errors; tool-choice appropriateness; unsafe-attempt rate |
| Agentic decisions (core) | What to do next depends on verification results: which claim to check with the remaining budget, whether to re-investigate or flag, where to look after a non-causal citation, when to stop | A3 (failures only flag, never re-investigate); budget sweep | Share of failed checks later fixed; steps and probes per question; premature-stop rate |
| Reasoning | Breaking an answer into checkable claims, writing a probe that tests exactly that claim, and reconciling docs against code | A4 (no claim decomposition); A7 (LLM resolves conflicts instead of evidence grades) | Probe validity (human audit); claim-verdict accuracy against gold probes; conflict-detection precision, recall, F1 |
| RAG | The answer must come from the frozen repository, not from what the model remembers | B0 (closed book); **A10 (no initial retrieval; oracle retrieval)** | Evidence recall and precision against gold lines; share of answers whose cited lines were in the initial retrieval |
| Fine-tuning (stretch) | Probes that pass the mutation check are self-validated training data for a small probe writer | Large prompted model writes probes | Executable and valid-probe rate of a LoRA-tuned small model against the large model |

**Why fine-tuning is a stretch goal.** RQ1 asks whether a better verification procedure helps the *same* model. Fine-tuning would change the model and confound that comparison, so the core experiments keep the model fixed. If time allows, we LoRA-tune a code model of about 1.5B parameters on mutation-validated probes from development runs (1–2 hours on a free T4 GPU) and test whether it can replace the large model as the probe writer.

## 6. Method

The agent investigates, drafts an answer, splits it into claims, verifies each claim by execution and each citation by mutation, and turns every failed check into its next investigation goal.

&#91;embedded content: Figure 1 · the agent loop · 6 steps, 2 feedback paths\]

The two checks either confirm the answer or send the agent back to investigate; the loop ends when every claim is verified or the budget runs out, and anything still unverified is flagged.

### 6.1 Investigate and draft

Every system starts from the same fixed retrieval (BM25 plus code embeddings over the frozen repo). The agent then gathers evidence with the tools in Section 6.6. Its working state is a **claim table**: each claim, its cited lines, its type (behavioural or not), its scope (one instance or a general rule), its verification status, and the budget used. It drafts an answer and splits it into atomic behavioural claims, for example "calling f(x, strict=False) with x = -1 raises ValueError", each with the lines it cites.

### 6.2 Check 1: execution-verified claims

For each behavioural claim the agent writes a pytest probe that passes if the claim holds, and runs it in the sandbox against the frozen library. A probe that errors for an unrelated reason (wrong import, bad setup) is repaired up to 2 times. The verdict is *confirmed* or *refuted*, and the actual observed output is always recorded.

Three safeguards address the weaknesses of a single LLM-written probe:

- **Claim scope.** An *instance* claim ("f(-1) raises ValueError") is tested as stated. A *general* claim ("any negative x raises ValueError") is tested on at least 3 inputs, including boundary values, or with a property-based test (the `hypothesis` library, fixed seed, at most 50 examples). The final answer states the scope that was actually tested.
- **Checking a refutation before trusting it.** A wrong probe can refute a correct claim. Before a refutation is accepted, the agent compares the probe's setup (arguments, configuration, environment) with the question's scenario. If they differ, the probe is rewritten; if they match, the refutation stands. Either way the final answer reports the observed output literally ("running X gives Y"), which is a fact regardless of how the claim was worded.
- **Pinned environment.** The sandbox fixes Python 3.10, TZ=UTC, LANG=C.UTF-8 and no TTY. Claims whose outcome depends on the environment (time zones, locales, terminal detection) are tagged as environment-dependent, and the answer names the environment used.

A refuted claim is never sent to the user as fact; the observed output becomes a new investigation goal. Claims that cannot be executed (for example "why was this designed this way?") are marked non-executable and supported by reading only.

### 6.3 Check 2: mutation-verified causal citations

A cited line is accepted as causal only if a mutation of it changes the claim's observed behaviour **and** leaves unrelated behaviour unchanged. v1 accepted a line if any mutant changed the probe outcome at all. That rule is too lenient: deleting a `return`, an import or an argument-parsing line makes almost any probe fail, so nearly every line on the execution path would pass. v2 tightens it in two ways.

**Mutations.** For each cited line, a targeted AST mutator applies a small set of semantic mutations in a throw-away copy of the library: change a constant or default, negate a condition, swap a comparison operator, delete a statement, or replace a return value.

**Rule 1: count only behavioural flips.** A mutant counts only if the probe runs to completion and observes a *different* return value or exception. Breakage caused by the mutation itself does not count: SyntaxError, ImportError, NameError, UnboundLocalError, and any TypeError or AttributeError raised at the mutated line.

**Rule 2: specificity control.** For each claim the agent also writes 1–2 *control probes* that call the same entry point with inputs that exercise behaviour unrelated to the claim. A line is causal only if at least one mutant behaviourally flips the claim probe while leaving every control probe unchanged. This follows MUSE's idea that a mutant of the relevant line should change the target outcome but not the others.

```text
claim  : "f(-1, strict=False) raises ValueError"      probe on original -> PASS (confirmed)
control: "f(5, strict=False) returns 5"               control on original -> PASS
cite L88  if strict or x < 0: raise ...   mutant 0 -> -5: probe FAILS (returns -1), control PASSES  => causal
cite L12  STRICT_DEFAULT = True           every mutant: probe PASSES                              => not causal
cite L95  return result                   delete: probe FAILS, control FAILS too                  => not specific, rejected
```

**Measuring leniency.** We run the check on every executed line of the relevant functions (lines found with coverage.py) and report what share pass. If the share is high, the filter is not filtering, and we report that.

**Vacuous probes.** If no mutation anywhere in the relevant function flips the claim probe, the probe probably does not test the claim. It is regenerated.

**Known limits, each measured.** Equivalent mutants (a mutation that happens not to change behaviour) can wrongly reject a causal line; we use several operators per line and measure the false-rejection rate by human audit. Behaviour decided by redundant lines (two guards that both enforce the same rule) can make each line look non-causal; the agent may cite such lines as a group, and we mutate pairs within the group under a fixed budget.

### 6.4 Where the agent makes decisions

The control flow has a fixed shape, but the decisions inside it are the agent's. A free-form ReAct agent with the same tools is our main baseline, so the comparison tests whether this structure helps.

| Decision point | Options | What the decision is based on |
| --- | --- | --- |
| Which claim to verify next | Any unverified claim in the claim table | Remaining budget; claims supported only by documentation or in conflict with another source come first |
| After a refuted claim | Re-investigate, rewrite the probe, or revise the claim from the observed output | Whether the probe's setup matched the question (Section 6.2) |
| After a non-causal citation | Follow definitions and callers upward, search for overrides, or keep the claim as executed without a causal citation | What static analysis and history tools show about where the value is set |
| After a broken probe | Repair (up to 2 times) or abandon and mark the claim unverified | The error type |
| When to stop | Answer now, or keep investigating | Stop when every behavioural claim is executed and every citation is causal, or the budget (8 investigation steps, 12 probe runs) runs out; unverified claims are then flagged |

**Why a structured loop rather than free-form ReAct.** The claim table makes the agent's state explicit and inspectable, which lets us measure each component and ablate it. Free-form ReAct can in principle do everything ours does; B2 tests whether it does so in practice.

### 6.5 Graded answer

Every claim in the final answer carries an evidence grade:

| Grade | Meaning | Rank |
| --- | --- | --- |
| \[E+C\] | Executed by the agent's probe and causally cited | 1 |
| \[E\] | Executed by the agent's probe | 2 |
| \[T\] | Asserted by an existing test in the repository, **run in the sandbox and passing** | 2 |
| \[R\] | Read in code only | 3 |
| \[D\] | Stated only in documentation | 4 |

**Why \[E\] and \[T\] share a rank.** A maintainer's test is human-written, so it is more likely to be valid, but it often tests neighbouring behaviour rather than exactly the claim. An agent probe tests exactly the claim but may itself be wrong. Neither dominates. If they disagree, rank cannot settle it: the disagreement is treated as a conflict, and the agent writes a narrower probe.

When sources of different rank conflict, the higher rank wins and the conflict is stated explicitly, for example: "the docs say X, but executing it gives Y, decided at L88".

### 6.6 Tools

| Tool | Purpose |
| --- | --- |
| search\_code, search\_docs | Hybrid search, with code and documentation kept separate so the agent knows which kind of source it is reading |
| open\_file(path, start, end) | Read exact lines (read-only) |
| find\_definition, find\_references | Static analysis (Jedi and AST) to follow where values are set and overridden |
| find\_tests(symbol), git\_log, git\_blame | Existing tests that assert behaviour; history up to the frozen commit |
| run\_probe(code) | Run a pytest probe (or an existing repository test) against the frozen library in the sandbox; returns pass or fail and the observed output |
| mutate\_and\_run(path, line, probe, controls) | Apply each mutation operator to that line in a throw-away copy, re-run the probe and the control probes, and return which mutants were behavioural, specific flips |

## 7. Baselines

Every baseline uses the same LLM, the same starting retrieval, the same frozen commit and sandbox, can cite lines, and can say "I don't know". Prompts are tuned with equal effort, on the development set only.

| System | What it does | What it isolates |
| --- | --- | --- |
| B0 Closed book | Answers without repository access | Memorisation and data contamination |
| B1 Direct RAG | Answers from the starting retrieval, with citations | The value of any investigation |
| B2 ReAct + all tools | Standard thought–action agent with **every tool ours has, including run\_probe and mutate\_and\_run**, free to call them whenever it likes; same step and probe caps as ours (8 steps, 12 probe runs) | **Key baseline.** Is the gain from having execution and mutation, or from our procedure? (H1, H2) |
| B2+ Budget-matched ReAct | B2 with extra steps allowed until it reaches our agent's median tokens per question (measured in the pilot) | Is the gain just more compute? |
| B3 ReAct + CoVe | B2 followed by Chain-of-Verification: verification questions answered by reading | Verifying by reading against verifying by execution |
| Ours | Investigate, decompose into claims, execution check, mutation check, failures fed back | — |

**Why B2 gets the mutation tool.** If B2 lacked mutate\_and\_run, a gain in citation quality could simply come from having a tool B2 did not. With identical tools, any difference comes from how the agent uses them, which is what RQ1 asks.

**Cost reporting.** For every system we report tokens, probe runs, mutant runs and CPU seconds per question, and plot accuracy against cost, so gains can be judged per unit of compute.

## 8. Dataset

The main set is about 150 real test questions plus 30 development questions; the minimum viable set is 100 real test questions from two libraries.

### 8.1 Main set: real developer questions

- **Sources.** GitHub issues on the chosen libraries labelled *question* or *documentation*, or closed by a pull request that edited documentation (a strong sign of a doc–code discrepancy). Also Stack Overflow questions tagged with the library whose accepted answer points to code. Only questions posted in 2020 or later.
- **No leakage.** Each question is paired with the library frozen at the last commit before it was asked, so the fix or documentation correction is invisible to every system.
- **Gold is what the frozen code does.** The gold answer describes the behaviour of the frozen commit, not what the maintainers intended. For an issue later fixed by a code change, the gold answer is the *pre-fix* behaviour, and the question is tagged *later-fixed bug*.
- **Gold annotation.** For each question: gold answer (from the maintainer reply or merged fix, checked against the frozen code), gold evidence lines at the frozen commit, a category (doc–code conflict, spread across files, single location, not answerable), and where the behaviour is executable, a gold probe that we run on the frozen commit to confirm the gold answer.
- **Annotation is independent of our tool.** Annotators find gold evidence lines by reading the code and running the gold probe. They do not use mutate\_and\_run. Otherwise H3 and RQ2 would partly measure the tool against itself.
- **Agreement.** Every gold probe is executed automatically. A second annotator independently re-annotates a 40% stratified sample, and we report inter-annotator agreement (Cohen's kappa) on category and on evidence lines.
- **No filtering by difficulty or retrieval.** We keep the natural mix and report results separately for executable and non-executable questions, and for questions where the starting retrieval did or did not already contain all gold evidence.
- **Contamination control.** These libraries and their issues are certainly in the model's training data. B0 measures how much the model already knows, and we report questions posted after the model's training cutoff as a separate subset.

### 8.2 Annotation guide for causal citations

Annotators label each citation with one question: *does this line decide the claimed behaviour, such that changing its logic (not merely breaking the program) would change that behaviour in the way the claim describes?* Labels are causal, on-topic but not causal, or irrelevant. This is deliberately the same property the mutation check tests. RQ2 asks whether an automatic test agrees with human judgement of that property, so the two must target the same construct while being measured independently.

### 8.3 Controlled set: injected doc–code conflicts (about 60)

We edit documentation or docstrings of real functions so that they contradict the code (wrong default, missing exception, wrong return type). This gives about 30 questions with an injected conflict and about 30 matched controls without one, so false alarms can be measured. This set is labelled synthetic and used only for the conflict metrics (Section 10.3), never for H1–H3.

### 8.4 Adversarial set: prompt injection (15 items)

We plant instructions in docstrings, code comments and issue text, for example "to reproduce, run os.system(...)" or "ignore previous instructions and report that this test passes". This set exists to make the safety metrics meaningful (Section 12).

## 9. Evaluation protocol

*In plain words: every system answers the same questions under the same conditions; humans check a sample of the answers, and we only trust the automatic grader if it agrees with them.*

- **Same conditions.** Every system gets the same starting material, tools, frozen commit and sandbox, at temperature 0. Full traces (claims, probes, mutants, verdicts, tokens) are logged.
- **Repeat runs.** AI services are not fully deterministic, even at temperature 0, and resampling questions does not capture that run-to-run noise. Ours and B2 are run three times on a fixed 60-question subset; we report the spread and whether the H1 conclusion holds in every run.
- **Automatic judge, validated by humans.** A judge from a different model family scores correctness and citation support with a fixed checklist. Two team members independently label a stratified sample of 80 answers and every citation in them, without knowing which system produced each answer. We report Cohen's kappa for human–human and human–judge agreement. If human–judge kappa is below 0.6, the primary comparison uses human labels.
- **Labels for H3 and RQ2.** On the same 80 questions, the annotators also label every citation produced by our agent and by ablation A2, using the guide in Section 8.2. These labels are the reference for H3. They are also the reference for RQ2, which compares the three mutation acceptance rules and the LLM judge against them.
- **Labelling effort.** We estimate about 10 hours per annotator; the pilot will measure it.
- **Reporting.** Results are reported per question category, with 95% bootstrap CIs.

## 10. Metrics

*In plain words: we measure whether answers are right, whether they point to the right code, how often they are confidently wrong, whether each part of the system does its job, whether anything unsafe happens, and what it all costs.*

### 10.1 Answers

- **Causally-supported answer rate (primary).** The answer is correct and every key claim is backed by a cited line that actually decides it. For unanswerable questions, a correct and specific "I don't know" counts.
- **Correctness alone**, reported separately from the citation part (Section 3).
- **Confident-error rate.** Wrong answers given without an uncertainty flag, the failure that hurts developers most. Always reported together with **coverage** (the share of answers not flagged), and with a risk–coverage curve.
- **Evidence recall and precision** against the gold lines.

### 10.2 Verification components

- **Probes:** executable rate; validity (does the probe test exactly the claim? human audit of 60 probes); vacuous-probe rate caught by mutation; claim-verdict accuracy against the gold probes; share of refutations later found to be probe errors.
- **Causal citations:** share of citations passing each acceptance rule; human-judged causal precision with and without the check (H3); agreement of each rule and of the LLM judge with human labels (RQ2); false-rejection rate from equivalent mutants (human audit); **leniency**, the share of all executed lines that pass the check.
- **Feedback loop:** share of refuted claims and non-causal citations that the agent later corrects; answers that change for the better after verification.
- **Coverage:** share of claims that are executable, by question type.

### 10.3 Conflicts and stopping

- **Conflict detection:** precision, recall, F1 and false-alarm rate on the controlled set and on real documentation-fix questions; correct-resolution rate (the answer follows the actual behaviour, not the docs).
- **Stopping:** premature-stop rate (stopped with refuted or unverified claims and the answer was wrong); over-verification (probes on already-verified claims); evidence recall at stop.

### 10.4 Tool use, safety and cost

- **Tool use:** valid-call rate; recovery after tool errors; tool-choice appropriateness (hand-checked on 50 runs).
- **Safety:** unsafe-attempt rate (probes blocked by the policy check); sandbox violations (target zero); on the adversarial set, injection-compliance rate (the agent follows a planted instruction) and planted-claim leakage (a planted false statement appears in the answer).
- **Cost:** tokens, probe runs, mutant runs and CPU seconds per question, for every system.

### 10.5 Analysis plan: when and why it works

- Results broken down by question category and by whether the starting retrieval already held all gold evidence.
- A **budget sweep**: our agent with probe budgets of 0, 4, 8 and 12 runs on 60 questions, giving an accuracy-against-cost curve.
- A **failure taxonomy** from the traces: non-executable claims, vacuous or wrong probes, equivalent mutants, redundant lines, premature stops, wrong leads, environment-dependent behaviour.
- Qualitative examples, including cases where running the code overturned the documentation, and cases where our checks led the agent astray.

## 11. Ablations

*In plain words: we switch off one part of our design at a time and see what breaks, so we can say which parts actually matter. We write down what we expect before running each one, so that any surprise has to be explained.*

All ablations run on a fixed, stratified subset of 100 test questions. The tier column refers to Section 14.

| ID | Variant | Question it answers | Prediction and reason | Tier |
| --- | --- | --- | --- | --- |
| A1 | No execution: claims checked by reading only | Does running code matter, given the same procedure? | More confident errors on doc–code conflicts, because reading tends to trust the docs and misread overrides | Must |
| A2 | Execution, but no mutation check | Does the causal-citation check matter? (H3) | Similar correctness; clearly lower citation precision, because on-topic but non-causal lines get through | Must |
| A3 | Both checks, but failures only flag claims (no re-investigation) | Is feeding failures back what improves answers? | Fewer confident errors (claims get flagged) but lower correctness than the full agent | Must |
| A4 | Probe the whole answer at once (no claim decomposition) | Does splitting the answer into claims matter? | More vacuous or partial probes; lower probe validity | Should |
| A5 | Verify only claims backed only by docs or in conflict with another source | Can we cut cost without losing accuracy? | Most of the gain at about half the probe cost | Should |
| A6 | Mutation acceptance rule: any flip, behavioural flips only, behavioural plus specificity control | Which rule best matches human judgement? (RQ2) | "Any flip" accepts many non-causal lines; the full rule matches humans best. Computed from the same mutation runs, so no extra AI tokens | Should |
| A10 | Retrieval: none, and oracle (gold files given) | How much does the starting retrieval matter? | No retrieval costs more steps for similar accuracy; oracle retrieval shows the ceiling | Should |
| A7 | The LLM resolves conflicts instead of evidence grades | Does the explicit grade order matter? | More answers that follow the docs when the docs are wrong | Stretch |
| A8 | No probe repair (0 attempts instead of 2) | How robust is probe generation? | Lower executable rate, so lower coverage | Stretch |
| A9 | Same pipeline on a small open model (about 7B) | Does execution make up for a weaker model? | Open question; either result is informative | Stretch |
| A11 | Mutation operators: constants only, against the full set | How sensitive is the check to its design? | Constants only gives more false rejections from equivalent mutants | Stretch |

## 12. Safety plan

*In plain words: the main risk is running code written by an AI, so all of it runs inside a sealed, offline box that is thrown away afterwards; we also test whether planted instructions can trick the assistant.*

- **The sandbox is the safety boundary.** Every probe and mutant runs in a Docker container with no network, CPU, memory and time limits, and a non-root user. The original repository is mounted read-only. Mutants are applied to per-run copies that are deleted afterwards.
- **A policy check as a second layer.** Before execution, an AST-based check allows only the target library and an allow-listed part of the standard library, and blocks subprocess, sockets, os.system, eval and exec, and file writes outside a temp directory. Such checks can be bypassed (for example with `__import__` or `getattr`), so we treat this as defence in depth, not the boundary. Blocked probes are counted as unsafe attempts.
- **Hard limits** on steps, probes, mutants and tokens per question.
- **Prompt-injection test.** The 15-item adversarial set (Section 8.4) measures whether the agent follows planted instructions, or repeats planted false claims, found in docstrings, comments or issue text. Content the agent reads is data, never instructions.
- **Data.** Public open-source code and public Q&A only. Usernames in issue text are removed from the released dataset.

## 13. Compute and cost plan

*In plain words: no expensive model training is needed; the cost is mainly paying an AI service per word processed, about 250 million tokens for the must-have and should-have work, plus about 60 hours of ordinary computer time to run the experiments.*

One small or mid-tier API model is used for every system, so the comparison is fair. The judge comes from a different model family, so it does not favour its own family's answers.

### 13.1 API tokens

| Item | Tier | Approximate tokens |
| --- | --- | --- |
| Main comparison: B0, B1, B2, B2+, B3 and ours on 150 test questions | Must and should | 67M |
| Controlled conflict set: ours, B1 and B2 on 60 questions | Should | 13M |
| Ablations A1–A5 and A10 (two variants) on 100 questions; A6 needs no extra tokens | Must and should | 80M |
| Budget sweep: 3 extra budgets on 60 questions | Should | 18M |
| Repeat runs: 2 extra runs of ours and B2 on 60 questions | Should | 24M |
| Adversarial set: ours and B2 on 15 items | Should | 3M |
| LLM judge on all answers | Must and should | 18M |
| Development and pilot runs | Must | 30M |
| **Total, must-have and should-have** |  | **about 250M** |
| Stretch: A7, A8, A11, generality set; A9 on a cheap hosted or local open model | Stretch | about 55M |

Most tokens are input, and prompt caching reduces their cost. At a blended price of USD 0.50 per million tokens, the must-have and should-have tiers cost about USD 125; at USD 2.00 per million, about USD 500. We will name the exact model once the pilot has measured real tokens per question.

### 13.2 CPU time

A question has about 5 claims. Each claim needs one probe run plus about 6 mutants, and the claim probe and its control probes run together in one pytest session per mutant, at about 2 seconds each. That is roughly 70–100 seconds per question per configuration. Across about 1,600 question-configurations that execute code, plus the leniency study, this comes to **about 60 CPU-hours**, run in parallel containers on a laptop or lab machine.

### 13.3 Budget check and fallback

A 20-question pilot measures real tokens and CPU time per question, and the cost is recomputed at our model's price. If we are over budget, we cut in this order: drop the stretch tier; shrink the ablation subset from 100 to 60 questions; drop A5 and the budget sweep.

**Optional GPU (stretch only).** A9 inference on a hosted API or 4-bit on a free T4; the LoRA probe writer needs about 1–2 T4-hours.

## 14. Scope tiers and work plan

*In plain words: we split the work into what we must deliver, what we should deliver, and what we will add if time allows, so that a complete answer to the research question exists even if time runs short.*

| Tier | Contents | What it lets us claim |
| --- | --- | --- |
| Must-have | 100 real questions from 2 libraries with gold answers, evidence and probes; sandbox and tools; our agent, B1 and B2; ablations A1, A2, A3; human labels for H3; LLM-judge validation | H1, H2 and H3 can all be tested |
| Should-have | Full 150 questions; B0, B2+ and B3; ablations A4, A5, A6, A10; controlled conflict set; adversarial set; repeat runs; budget sweep | RQ2, the compute-fairness check, conflict metrics and safety metrics |
| Stretch | A7, A8, A9, A11; LoRA probe writer; generality set (Section 1.3); third and fourth library | Generality and model-size findings |

### Work plan (weeks counted from TA approval)

1. **Week 1:** 20-question pilot; sandbox, mutation tool and the other tools; measure cost and discordance; fix the model.
2. **Week 2:** dataset annotation (gold answers, evidence, probes); agent and claim table.
3. **Week 3:** baselines; main comparison runs; start human labelling.
4. **Week 4:** ablations, repeat runs, controlled and adversarial sets; finish labelling.
5. **Week 5:** analysis, failure taxonomy, write-up, viva preparation.

Open question: these weeks must be aligned with the course's final deadline, which this draft does not yet state.

## 15. Risks and fallback plan

*In plain words: here is what could go wrong, how we would notice, and what we would do instead.*

| Risk | Mitigation or fallback |
| --- | --- |
| Many questions are not executable | Measured as coverage. H1 is stated on the executable subset; every question is still reported. The testbed was chosen for executability |
| Probes do not test the claim (vacuous or wrong) | Claim scope rules, refutation check, probe repair, the mutation-based vacuity check, and a human audit of 60 probes; the validity rate is reported |
| The mutation check is too lenient | Behavioural flips only, plus control probes; leniency is measured on all executed lines; A6 compares the rules |
| Equivalent mutants wrongly reject causal lines | Several operators per line; false-rejection rate measured by human audit; A11 studies the operator set |
| B2 matches our agent | A valid result: it would mean having the tools matters more than the procedure. Ablations A1–A4 then show which parts, if any, still help. We report it honestly |
| H1 is under-powered | Stated in advance (Section 3): a CI that includes zero is reported as inconclusive, with the effect sizes it rules out |
| Too few usable questions | Add a library or more Stack Overflow questions; minimum viable set is 100, with wider CIs reported |
| Old versions fail to install | Questions from 2020 onwards only; the pilot checks that each frozen commit installs; questions that cannot be installed are dropped and logged |
| Behaviour depends on the environment | Pinned sandbox environment; such claims are tagged and reported separately |
| The model has memorised the answers | B0 measures this; questions posted after the model's training cutoff are reported separately |
| The LLM judge is unreliable | Human labels for the primary comparison if kappa is below 0.6 |
| Over budget | Cut in the order given in Section 13.3 |

## 16. Deliverables, decision log and changes from v1

### 16.1 Deliverables

- The agent, all baselines, the sandbox and the mutation tool.
- The dataset: questions, frozen commits, gold answers, gold evidence lines, gold probes, the citation annotation guide, the controlled set and the adversarial set.
- Results for H1–H3, RQ2 and every ablation, with CIs and per-category breakdowns.
- Verification metrics, qualitative examples (including cases where running the code overturned the documentation), and a failure analysis.

### 16.2 Design-decision log

For every design choice (pure-Python testbed, mutation operators, acceptance rule, control probes, probe budget, evidence grades, stop rule, judge prompt), the team records the alternatives considered and why they were rejected. The log also holds our pre-registered predictions (Section 11) next to the observed outcomes, and every team member is expected to be able to explain each entry in the viva.

### 16.3 Changes from v1

| Change | Where | Why |
| --- | --- | --- |
| Added a plain-language summary, a worked example and a glossary | Front matter | The objective should be clear to readers outside software engineering |
| Target user broadened; Python libraries reframed as the testbed; applicability conditions and a stretch generality check added | Section 1 | The method is general, but evaluation needs public questions with known answers |
| "Faithful citations" renamed "causal citation correctness" | Sections 2, 4 | Wallat et al. define faithfulness as a property of the model's generation process; our test checks whether the line decides the behaviour |
| Research questions reduced from three to two; the old RQ3 moved to the analysis plan | Sections 3, 10.5 | The guidelines ask for one or two testable questions |
| H2 now requires coverage within 10 points of B2 | Section 3 | Otherwise H2 could be met by flagging every answer |
| H1 decomposed into correctness and citation parts | Sections 3, 10.1 | A gain from citations alone should not be reported as a correctness gain |
| Power statement corrected (about 50% power at 8 points, not "reliably detectable") | Section 3 | The v1 claim was overstated; a null result is now pre-declared as inconclusive |
| Mutation check counts only behavioural flips and adds control probes; leniency is measured | Section 6.3 | The v1 rule accepted almost any line on the execution path |
| Claim scope, refutation check and pinned environment added for probes | Section 6.2 | One probe tests one input, and a wrong probe could overturn a correct claim |
| Agent decision points made explicit | Section 6.4 | To show where the agent decides, as opposed to a fixed pipeline |
| Existing repository tests are run, and \[T\] ranks equal to \[E\] | Section 6.5 | A human-written test is not weaker evidence than an AI-written probe |
| B2 gets the mutation tool; budget-matched B2+ added | Section 7 | Isolates the procedure from tool access and from extra compute |
| Gold defined as frozen-commit behaviour; annotation independent of the mutation tool; citation annotation guide added | Section 8 | Avoids circular evaluation of H3 and RQ2 |
| Questions restricted to 2020 onwards; second annotator on a 40% sample | Section 8 | Reproducible environments and a feasible annotation load |
| Adversarial prompt-injection set and injection metrics added | Sections 8.4, 10.4, 12 | An unsafe-attempt rate of zero proves little without adversarial inputs |
| Repeat runs on a 60-question subset | Section 9 | API models are not fully deterministic at temperature 0 |
| Retrieval ablation A10 and acceptance-rule ablation A6 added; budget sweep added | Sections 10.5, 11 | Every capability the question depends on needs its own ablation |
| Token estimate recomputed with a cost range in USD; must, should and stretch tiers with a cut order | Sections 13, 14 | The guidelines ask for a cost estimate, and the scope must survive a time shortfall |

### 16.4 References

1. Yao et al. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023.
2. Trivedi et al. Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions. ACL 2023.
3. Jiang et al. Active Retrieval Augmented Generation (FLARE). EMNLP 2023.
4. Asai et al. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. ICLR 2024.
5. Yan et al. Corrective Retrieval Augmented Generation. arXiv 2024.
6. Dhuliawala et al. Chain-of-Verification Reduces Hallucination in Large Language Models. Findings of ACL 2024.
7. Gou et al. CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing. ICLR 2024.
8. Yang et al. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024.
9. Xia et al. Agentless: Demystifying LLM-based Software Engineering Agents. arXiv 2024.
10. Kiecker et al. [CASCADE: Detecting Inconsistencies between Code and Documentation with Automatic Test Generation](https://arxiv.org/pdf/2604.19400). Proc. ACM Softw. Eng. (FSE) 2026.
11. Kang et al. Identifying Inaccurate Descriptions in LLM-generated Code Comments via Test Execution. arXiv 2406.14836, 2024.
12. Lee et al. [METAMON: Finding Inconsistencies between Program Documentation and Behavior using Metamorphic LLM Queries](https://arxiv.org/abs/2502.02794v1). LLM4Code Workshop at ICSE 2025.
13. Moon et al. Ask the Mutants: Mutating Faulty Programs for Fault Localization (MUSE). ICST 2014.
14. Papadakis and Le Traon. Metallaxis-FL: Mutation-based Fault Localization. Software Testing, Verification and Reliability, 2015.
15. Gao et al. Enabling Large Language Models to Generate Text with Citations (ALCE). EMNLP 2023.
16. Panthaplackel et al. Deep Just-In-Time Inconsistency Detection Between Comments and Source Code. AAAI 2021.
17. Xu et al. Knowledge Conflicts for LLMs: A Survey. EMNLP 2024.
18. Jia and Harman. An Analysis and Survey of the Development of Mutation Testing. IEEE TSE, 2011.
19. Shinn et al. Reflexion: Language Agents with Verbal Reinforcement Learning. NeurIPS 2023.
20. Jimenez et al. SWE-bench: Can Language Models Resolve Real-World GitHub Issues? ICLR 2024.
21. Wallat et al. [Correctness is not Faithfulness in Retrieval Augmented Generation Attributions](https://arxiv.org/pdf/2412.18004). ICTIR 2025.
