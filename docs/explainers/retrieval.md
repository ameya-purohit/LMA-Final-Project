# Explainer: retrieval

Owner: Sunil Kumar. Files: `retrieval/chunker.py`, `retrieval/index.py`, tests in `tests/retrieval/`.

## Problem

An answer must come from the frozen repository, not from what the model remembers. Every system also needs the same
starting point, or differences in results could come from what each was shown. And since docs can be wrong, the agent
must always know whether it is reading code or documentation.

## How it works (plain words)

- **Chunking.** Code is cut along real boundaries using the AST: each function, each method, each class header, and
  each run of top-level statements (constants often decide behaviour). Docs are `.rst` and `.md` sections split at
  headings, plus docstrings. Every chunk keeps its file path and exact line range, so it can be cited.
- **Tokenizing.** Identifiers are split, so `is_eager` matches a search for "eager" or for "is_eager".
- **BM25.** A classic ranking formula: a chunk scores high if it contains the query's rare words often. Code and docs
  have **separate indexes**, cached per (library, commit), because a frozen tree never changes.
- **Starting material.** The top 5 code chunks and top 3 doc chunks for the question, identical for every system.

## Worked example

On toylib, the question "why does `clamp(5)` not raise an error?" finds `clamp` and `_effective_strict` in the code index
and the "clamp" section of `usage.md` in the doc index. Code chunks are shown with real line numbers:
`   88      if strict or x < 0: raise ValueError("negative")`, so the model can cite line 88 directly.

## Weaknesses

- **Words, not meaning.** BM25 misses a question that describes a behaviour in different words from the code.
  Embeddings are left out of the must-have tier, a logged deviation.
- **Tests are not in the index.** The `find_tests` tool searches them instead, so that search results stay about the
  library itself.
- **Long functions are cut** at 120 lines in a chunk; the model must use `open_file` for the rest.

## Viva Q&A

1. **Why keep code and docs in separate indexes?**
   Our research is about docs being wrong. Separate indexes mean the agent always knows which kind of source it holds,
   and a claim can be marked as supported only by documentation.
2. **Why BM25 rather than embeddings?**
   It is deterministic, cheap and easy to explain, and it costs no API requests. Ablation A10 (no retrieval, oracle
   retrieval) shows how much better retrieval could help, which tells us if embeddings would be worth adding.
3. **Why chunk by AST rather than by fixed-size windows?**
   A whole function is a complete, citable unit with exact line numbers. A fixed window can cut through a function
   and separate a condition from what it controls.
4. **Why did you add the "shares a query word" filter?**
   A test found a real problem: BM25 gives a word in exactly half of a small corpus a score of zero, so a matching chunk
   disappeared. Requiring at least one shared word, whatever the score, keeps it.
5. **How do you know all systems get the same material?**
   One function builds it, deterministically, and a test checks that two builds give identical text.
