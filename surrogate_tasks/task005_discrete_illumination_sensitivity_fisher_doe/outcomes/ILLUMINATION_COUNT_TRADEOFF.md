# Illumination-count tradeoff

The primary score is the robust M0/M1/N1/N2 worst-case minimum eigenvalue. The 5% fewer-illumination rule is applied explicitly to adjacent counts.

| comparison | fewer score / more score | ratio | within 5%? | action |
|---|---:|---:|---|---|
| 1 vs 2 | 12.882983 / 23.781704 | 0.541718 | False | retain_more_information |
| 2 vs 3 | 23.781704 / 34.768648 | 0.683999 | False | retain_more_information |
| 3 vs 4 | 34.768648 / 45.149335 | 0.770081 | False | retain_more_information |

Information-global-best set: `['A05', 'A06', 'A07', 'A09']` (size 4).
M4-nonlinearly-validated set: `['A05', 'A07', 'A09']`.
Recommended operational set: `['A05', 'A07', 'A09']`.

The operational triple is not called the global information optimum. The quad has materially higher Fisher score and is not within the 5% tie; the triple is retained because it is the best robust triple and the only set with the prescribed three-geometry nonlinear recovery evidence. It is a validated cost-information compromise for the next reviewed task.
