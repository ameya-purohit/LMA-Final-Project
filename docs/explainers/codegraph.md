# Explainer: code graph, slicing and hybrid retrieval (E2-E3)  · owner: Sunil

## Problem
To localize a fault you must first look in the right place. BM25 matches words, so it misses code that uses different
words than the issue. And once a suspect line is found, the lines that can *affect* it are a much smaller search
space than the whole file.

## How it works (plain words)
**Hybrid retrieval** (`retrieval/hybrid.py`). Each AST chunk (one function or method) is searched two ways: BM25
(word overlap, the existing index) and dense embeddings (a small sentence-embedding model, cosine similarity in
FAISS). The two rankings are merged by **reciprocal rank fusion**: each chunk scores 1/(60 + rank) in each list; the
sum orders the result, so no scores need calibrating. A **cross-encoder** then re-reads the question together with
each of the top 30 chunks and reorders them. Optionally (R5) the callers and callees of the top three hits are fused
in. Models run locally (fastembed, ONNX): no API, no quota. Embeddings are cached by text hash.

**Code graph** (`codegraph/graph.py`). From Python's `ast`: every function and method with its line range; a call
graph (resolved by name: `self.m()` to the same class, `f()` to the same file or an import, `obj.m()` only if at
most 3 methods have that name); per function, line-level *data* edges (assignment of a name -> a later read of it,
or anywhere in the same loop) and *control* edges (an `if`/`for`/`while`/`try`/`with` header -> each statement under
it); module constants read by a function.

**Slicing.** `static_slice(path, line)` walks those edges backwards: the lines that can affect the given line, nearest
first, plus the module constants they read. `codegraph/rank.py` intersects slices with what really ran: the sandbox
records which library lines each probe executed, and a line the reproduce probe ran but no control ran gets score 1,
a line also run by one control 0.71 (Ochiai: 1/sqrt(1 + c)).

## Worked example (toylib)
`static_slice("src/toylib/core.py", 88)` returns line 88, then line 87 (`strict = _effective_strict(strict)`, which
assigns the `strict` read on 88), then the `def` line (parameters). It does *not* contain line 12 (`STRICT_DEFAULT`),
because `clamp` never reads it directly; only `_effective_strict` does. If the reproduce probe `clamp(-1)` runs line
88's raise and the control `clamp(5)` does not reach line 90 differently, line 88 ranks first.

## Weaknesses
- Name-based call resolution guesses; dynamic dispatch and decorators confuse it.
- Slices are intra-procedural: a wrong value returned by a callee is only found through the call graph and spectra.
- The embedding model is general text, not code-specific (memory limit of the run machine).
- Spectra with one failing run are coarse: many lines tie.

## Viva Q&A
1. **Why RRF instead of adding scores?** BM25 and cosine scores live on different scales; RRF uses only ranks, has one
   constant (60, from the original paper) and nothing to tune.
2. **Why a cross-encoder after fusion?** A bi-encoder embeds question and code separately; a cross-encoder reads them
   together and is more accurate, but slow, so it only reorders the top 30.
3. **Is your slice sound?** No. It ignores aliasing, attributes across methods and calls. It is a heuristic to shrink and
   order candidates; the mutation check, not the slice, decides causality.
4. **Why not Joern or a full CPG?** It needs a JVM service; our questions need only "what can affect this line" and
   "who calls whom", which NetworkX handles in a few hundred lines we can explain.
5. **How do you know hybrid retrieval helps?** The retrieval study (R1-R5) measures hit@K, Recall@K, Precision@K and MRR
   on all 145 test questions against the fix lines, with paired tests; no LLM is involved.
