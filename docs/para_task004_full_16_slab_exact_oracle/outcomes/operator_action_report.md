# Operator action report

| run | outer iterations | PC applies | condensed operator applies | one-level applies | global slab backend calls |
|---|---:|---:|---:|---:|---:|
| baseline two-step | 861 | 861 | 2,603 | 5,166 | 82,656 ILU |
| G4 two-step | 804 | 804 | 2,430 | 4,824 | 19,296 exact + 57,888 ILU |
| G8 two-step | 792 | 792 | 2,394 | 4,752 | 38,016 exact + 38,016 ILU |
| G16 two-step | 566 | 566 | 1,712 | 3,396 | 54,336 exact |
| G16 one-step | 1200 | 1200 | 3,629 | 2,400 | 38,400 exact |

相对 baseline，G16 two-step 的 condensed operator actions下降34.23%，one-level applies下降34.26%，与 outer iteration signal一致。

One-step 将每次PC所需的 one-level action减少，但平滑能力不足：outer iteration至少增加39.37%，condensed operator actions增加39.42%，并在1200步时 residual仍为`1.048e-5`。因此它不满足“operator actions至少下降25%且outer增加不超过10%”，也没有wall-time/numeric positive signal。
