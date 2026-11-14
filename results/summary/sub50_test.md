Questions completed per system: {'a10none': 50, 'a10oracle': 50, 'b2': 50, 'ours': 50}. All systems are compared only on the 50 questions every one of them completed; judge-based columns use the 50 of those judged for every system.

| System | n run | n judged | Correct | Partial | Correctness | Causally supported | Fix-location recall | Confident errors | Confident-error rate | Coverage | Requests/q (mean) | Requests/q (max) | Tokens/q (mean) | Probe runs/q | Mutant runs/q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b2 | 50 | 50 | 32 | 9 | 64.0% | 52.0% | 62.0% | 18 | 36.0% | 100.0% | 9.7 | 25 | 107082 | 4.3 | 0.3 |
| ours | 50 | 50 | 27 | 13 | 54.0% | 36.0% | 60.0% | 18 | 36.0% | 86.0% | 15.1 | 24 | 187061 | 4.3 | 9.0 |
| a10none | 50 | 50 | 28 | 12 | 56.0% | 34.0% | 46.0% | 18 | 36.0% | 86.0% | 14.5 | 21 | 131364 | 3.9 | 8.9 |
| a10oracle | 50 | 50 | 27 | 13 | 54.0% | 38.0% | 56.0% | 19 | 38.0% | 84.0% | 13.9 | 23 | 269764 | 4.0 | 6.8 |
