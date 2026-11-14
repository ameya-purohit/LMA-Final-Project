# Retrieval study (exploratory extension, no LLM)

Test questions with at least one relevant code chunk: 142 (skipped 3 whose fix lines fall in no code chunk, e.g. only new files).

| Mode | hit@1 | hit@5 | hit@10 | Recall@5 | Recall@10 | Precision@5 | MRR@10 |
|---|---|---|---|---|---|---|---|
| R1 BM25 | 35.9% | 64.1% | 74.6% | 46.3% | 57.3% | 18.2% | 0.476 |
| R2 dense | 36.6% | 65.5% | 76.1% | 47.6% | 59.1% | 19.6% | 0.486 |
| R3 BM25+dense (RRF) | 47.2% | 71.8% | 78.2% | 54.1% | 62.6% | 21.8% | 0.573 |
| R4 RRF + rerank | 26.8% | 60.6% | 74.6% | 42.0% | 56.0% | 17.9% | 0.413 |
| R5 R4 + call graph | 20.4% | 57.7% | 73.2% | 39.4% | 55.5% | 16.9% | 0.357 |

Paired comparisons (hit@5: exact McNemar and bootstrap 95% CI of the difference; MRR@10: bootstrap CI).

| Comparison | hit@5 diff | 95% CI | p | MRR@10 diff | 95% CI |
|---|---|---|---|---|---|
| R2 vs R1 | +1.4 pts | [-6.3, +9.2] | 0.864 | +0.010 | [-0.068, +0.089] |
| R3 vs R1 | +7.7 pts | [+1.4, +14.1] | 0.035 | +0.097 | [+0.036, +0.155] |
| R4 vs R1 | -3.5 pts | [-12.0, +4.9] | 0.522 | -0.063 | [-0.135, +0.009] |
| R4 vs R3 | -11.3 pts | [-19.0, -3.5] | 0.009 | -0.160 | [-0.222, -0.097] |
| R5 vs R4 | -2.8 pts | [-7.7, +2.1] | 0.388 | -0.056 | [-0.108, -0.004] |

hit@5 by library: click: R1 64%, R2 64%, R3 70%, R4 61%, R5 58%; marshmallow: R1 65%, R2 75%, R3 85%, R4 55%, R5 55%
