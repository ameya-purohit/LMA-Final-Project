# Exploratory extension: multi-agent localization (not pre-registered as a primary result)

Questions answered by every system shown: 47 (of the 47 `sub50` test questions). Gold = lines the developer's fix changed; every rate is a lower bound (a causal line outside the fix counts as a miss).

## Localization

| System | Line Top-1 | Line Top-3 | Line MRR | Line P / R / F1 | Fn Top-1 | Fn Top-3 | Fn MRR | Fn F1 |
|---|---|---|---|---|---|---|---|---|
| E0 | 48.9% | 59.6% | 0.532 | 38.5% / 34.6% / 31.7% | 63.8% | 72.3% | 0.670 | 53.8% |
| B2 | 46.8% | 61.7% | 0.539 | 42.9% / 34.8% / 33.5% | 70.2% | 78.7% | 0.745 | 60.5% |
| E1 | 34.0% | 48.9% | 0.401 | 31.8% / 30.4% / 27.8% | 61.7% | 76.6% | 0.684 | 55.0% |
| E2 | 40.4% | 55.3% | 0.479 | 34.1% / 34.2% / 28.3% | 66.0% | 72.3% | 0.684 | 55.0% |
| E3 | 31.9% | 36.2% | 0.358 | 10.4% / 30.7% / 12.2% | 53.2% | 61.7% | 0.586 | 44.6% |
| E4 | 31.9% | 36.2% | 0.358 | 10.4% / 30.7% / 12.2% | 53.2% | 61.7% | 0.586 | 44.6% |
| E5 | 31.9% | 36.2% | 0.352 | 10.6% / 26.9% / 12.0% | 59.6% | 66.0% | 0.631 | 44.2% |
| E6 | 31.9% | 36.2% | 0.352 | 10.6% / 26.9% / 12.0% | 59.6% | 66.0% | 0.631 | 44.2% |

## Single-location vs multi-location faults

| System | Single: n, line Top-3, fn Top-3 | Multi: n, line Top-3, fn Top-3, ≥2 gold ranges in top 5 |
|---|---|---|
| E0 | 14, 71.4%, 78.6% | 33, 54.5%, 69.7%, 30.3% |
| B2 | 14, 64.3%, 85.7% | 33, 60.6%, 75.8%, 24.2% |
| E1 | 14, 50.0%, 71.4% | 33, 48.5%, 78.8%, 30.3% |
| E2 | 14, 57.1%, 71.4% | 33, 54.5%, 72.7%, 24.2% |
| E3 | 14, 28.6%, 57.1% | 33, 39.4%, 63.6%, 21.2% |
| E4 | 14, 28.6%, 57.1% | 33, 39.4%, 63.6%, 21.2% |
| E5 | 14, 28.6%, 71.4% | 33, 39.4%, 63.6%, 21.2% |
| E6 | 14, 28.6%, 71.4% | 33, 39.4%, 63.6%, 21.2% |

## Causal verification (mutation-checked lines)

| System | Lines tested | Acceptance on fix lines | Acceptance on other lines (upper bound on false acceptance) | Inconclusive |
|---|---|---|---|---|
| E0 | 182 | 50.0% (24/48) | 25.4% (34/134) | 17.6% |
| B2 | 7 | 66.7% (4/6) | 100.0% (1/1) | 0.0% |
| E1 | 136 | 19.6% (9/46) | 10.0% (9/90) | 47.1% |
| E2 | 130 | 20.9% (9/43) | 8.0% (7/87) | 37.7% |
| E3 | 434 | 22.9% (11/48) | 6.7% (26/386) | 51.6% |
| E4 | 434 | 22.9% (11/48) | 6.7% (26/386) | 51.6% |
| E5 | 321 | 23.3% (10/43) | 5.8% (16/278) | 51.7% |
| E6 | 321 | 23.3% (10/43) | 5.8% (16/278) | 51.7% |

E0 records yes/no verdicts; its 'no' includes flips that also changed a control, which E1-E6 call inconclusive, so E0's inconclusive rate counts only untestable lines.

## Correctness (judge) and cost per question

| System | Correct (judged) | Coverage | Requests | Tokens | Mutant runs | Probe runs | Wall s | Patch validated |
|---|---|---|---|---|---|---|---|---|
| E0 | 53.2% (n=47) | 87.2% | 14.9 | 187,823 | 9.1 | 4.2 | 46 | – (n=0) |
| B2 | 61.7% (n=47) | 100.0% | 9.9 | 109,529 | 0.3 | 4.5 | 2 | – (n=0) |
| E1 | 48.9% (n=47) | 27.7% | 7.6 | 32,031 | 3.3 | 2.3 | 61 | 43.5% (n=23) |
| E2 | 57.4% (n=47) | 25.5% | 7.8 | 33,678 | 3.4 | 2.3 | 62 | 45.5% (n=22) |
| E3 | 55.3% (n=47) | 34.0% | 8.0 | 35,393 | 9.9 | 2.4 | 68 | 36.0% (n=25) |
| E4 | 57.4% (n=47) | 29.8% | 8.0 | 35,527 | 15.2 | 2.4 | 86 | 32.0% (n=25) |
| E5 | 55.3% (n=47) | 31.9% | 8.0 | 35,337 | 11.4 | 2.4 | 65 | 42.3% (n=26) |
| E6 | 55.3% (n=47) | 31.9% | 8.0 | 35,337 | 11.4 | 2.4 | 62 | 42.3% (n=26) |

## Paired comparisons

| Comparison | n | Line Top-3 diff [95% CI], McNemar p | Fn Top-3 diff [95% CI], p | Line MRR diff [95% CI] | Correct (judged) diff [95% CI], p |
|---|---|---|---|---|---|
| E1 vs E0 | 47 | -10.6 [-23.4, +2.1], p=0.180 | +4.3 [-6.4, +14.9], p=0.688 | -0.131 [-0.238, -0.035] | -4.3 [-14.9, +6.4], p=0.727 (n=47) |
| E1 vs B2 | 47 | -12.8 [-25.5, +0.0], p=0.109 | -2.1 [-12.8, +8.5], p=1.000 | -0.138 [-0.238, -0.043] | -12.8 [-25.5, +0.0], p=0.109 (n=47) |
| E2 vs E1 | 47 | +6.4 [+0.0, +14.9], p=0.250 | -4.3 [-10.6, +0.0], p=0.500 | +0.079 [+0.001, +0.163] | +8.5 [-4.3, +21.3], p=0.344 (n=47) |
| E3 vs E2 | 47 | -19.1 [-34.0, -4.3], p=0.035 | -10.6 [-23.4, +2.1], p=0.227 | -0.122 [-0.254, +0.008] | -2.1 [-17.0, +12.8], p=1.000 (n=47) |
| E4 vs E3 | 47 | +0.0 [+0.0, +0.0], p=1.000 | +0.0 [+0.0, +0.0], p=1.000 | +0.000 [+0.000, +0.000] | +2.1 [-6.4, +10.6], p=1.000 (n=47) |
| E5 vs E4 | 47 | +0.0 [+0.0, +0.0], p=1.000 | +4.3 [+0.0, +10.6], p=0.500 | -0.005 [-0.017, +0.006] | -2.1 [-10.6, +6.4], p=1.000 (n=47) |
| E6 vs E5 | 47 | +0.0 [+0.0, +0.0], p=1.000 | +0.0 [+0.0, +0.0], p=1.000 | +0.000 [+0.000, +0.000] | +0.0 [+0.0, +0.0], p=1.000 (n=47) |
| E5 vs E0 | 47 | -23.4 [-38.3, -8.5], p=0.007 | -6.4 [-19.1, +6.4], p=0.508 | -0.180 [-0.323, -0.040] | +2.1 [-10.6, +14.9], p=1.000 (n=47) |
| E2 vs E0 | 47 | -4.3 [-17.0, +8.5], p=0.727 | +0.0 [-10.6, +10.6], p=1.000 | -0.052 [-0.166, +0.060] | +4.3 [-10.6, +19.1], p=0.791 (n=47) |
| E2 vs B2 | 47 | -6.4 [-19.1, +6.4], p=0.508 | -6.4 [-17.0, +4.3], p=0.453 | -0.060 [-0.162, +0.043] | -4.3 [-19.1, +10.6], p=0.774 (n=47) |

## Ranking diagnosis (E1-E6)

Final rankings sort lines by verdict: accepted, accepted pair, cited, inconclusive, untested, rejected. A gold line the mutation check rejected therefore reaches the top 3 only when few lines are ranked.

| System | Mean lines ranked | Gold line in top 3, by its verdict class | Gold line not ranked |
|---|---|---|---|
| E1 | 2.9 | inconclusive 8, accepted 8, rejected 7 | 24 |
| E2 | 2.8 | rejected 12, accepted 8, inconclusive 6 | 20 |
| E3 | 8.1 | accepted 9, inconclusive 7, rejected 1 | 22 |
| E4 | 8.1 | accepted 9, inconclusive 7, rejected 1 | 22 |
| E5 | 8.1 | accepted 9, inconclusive 7, rejected 1 | 24 |
| E6 | 8.1 | accepted 9, inconclusive 7, rejected 1 | 24 |
