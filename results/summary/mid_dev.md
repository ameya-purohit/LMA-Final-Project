Questions completed per system: {'a1': 14, 'a2': 14, 'a3': 14, 'b0': 20, 'b1': 20, 'b2': 14, 'ours': 15}. All systems are compared only on the 14 questions every one of them completed; judge-based columns use the 7 of those judged for every system.

| System | n run | n judged | Correct | Partial | Correctness | Causally supported | Fix-location recall | Confident errors | Confident-error rate | Coverage | Requests/q (mean) | Requests/q (max) | Tokens/q (mean) | Probe runs/q | Mutant runs/q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b0 | 14 | 7 | 1 | 0 | 14.3% | 0.0% | 0.0% | 2 | 28.6% | 50.0% | 1.0 | 1 | 1571 | 0.0 | 0.0 |
| b1 | 14 | 7 | 2 | 2 | 28.6% | 28.6% | 35.7% | 4 | 57.1% | 92.9% | 1.0 | 1 | 5334 | 0.0 | 0.0 |
| b2 | 14 | 7 | 6 | 1 | 85.7% | 57.1% | 64.3% | 1 | 14.3% | 100.0% | 10.6 | 25 | 129220 | 4.6 | 0.6 |
| ours | 14 | 7 | 4 | 1 | 57.1% | 28.6% | 57.1% | 3 | 42.9% | 100.0% | 14.2 | 25 | 177228 | 4.1 | 10.9 |
| a1 | 14 | 7 | 5 | 1 | 71.4% | 42.9% | 50.0% | 2 | 28.6% | 100.0% | 7.3 | 11 | 70548 | 0.0 | 0.0 |
| a2 | 14 | 7 | 5 | 1 | 71.4% | 42.9% | 57.1% | 2 | 28.6% | 100.0% | 8.9 | 13 | 94742 | 3.7 | 0.0 |
| a3 | 14 | 7 | 5 | 1 | 71.4% | 28.6% | 50.0% | 2 | 28.6% | 71.4% | 7.9 | 12 | 81225 | 3.4 | 4.3 |

Each system on every one of the 14 common questions it has a judgement for (n judged differs by system, so compare rows with care):

| System | n run | n judged | Correct | Partial | Correctness | Causally supported | Fix-location recall | Confident errors | Confident-error rate | Coverage | Requests/q (mean) | Requests/q (max) | Tokens/q (mean) | Probe runs/q | Mutant runs/q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b0 | 14 | 7 | 1 | 0 | 14.3% | 0.0% | 0.0% | 2 | 28.6% | 50.0% | 1.0 | 1 | 1571 | 0.0 | 0.0 |
| b1 | 14 | 14 | 6 | 5 | 42.9% | 28.6% | 35.7% | 7 | 50.0% | 92.9% | 1.0 | 1 | 5334 | 0.0 | 0.0 |
| b2 | 14 | 14 | 10 | 4 | 71.4% | 42.9% | 64.3% | 4 | 28.6% | 100.0% | 10.6 | 25 | 129220 | 4.6 | 0.6 |
| ours | 14 | 14 | 7 | 4 | 50.0% | 35.7% | 57.1% | 7 | 50.0% | 100.0% | 14.2 | 25 | 177228 | 4.1 | 10.9 |
| a1 | 14 | 12 | 7 | 4 | 58.3% | 33.3% | 50.0% | 5 | 41.7% | 100.0% | 7.3 | 11 | 70548 | 0.0 | 0.0 |
| a2 | 14 | 14 | 9 | 3 | 64.3% | 35.7% | 57.1% | 5 | 35.7% | 100.0% | 8.9 | 13 | 94742 | 3.7 | 0.0 |
| a3 | 14 | 14 | 8 | 5 | 57.1% | 28.6% | 50.0% | 6 | 42.9% | 71.4% | 7.9 | 12 | 81225 | 3.4 | 4.3 |
