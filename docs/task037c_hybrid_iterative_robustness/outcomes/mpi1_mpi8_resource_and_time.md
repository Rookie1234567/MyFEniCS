# Task037c MPI8 资源、用时与 MPI1 边界

## 资源口径

RSS 是同时存活 MPI 进程树的峰值；PSS/USS 是同一 watchdog 的诊断峰值，不能与历史
per-rank 峰值相加。swap 只记录实际使用量，Swap device 存在不等于 swap 使用。

## R2 Full3D direct（MPI8）

| phi | RSS MiB | PSS MiB | USS MiB | swap MiB | total wall s | status |
|---:|---:|---:|---:|---:|---:|---|
| 0° | 15332.5 | 13280.2 | 12966.1 | 0 | 236.2486949579 | measured authority pass |
| -5° | 15325.1 | 13273.2 | 12958.6 | 0 | 267.5699258649 | measured authority pass |
| +5° | 15080.4 | 13026.5 | 12712.3 | 0 | 234.1900649510 | measured authority pass |

这些是 Full3D direct 的实测资源，不能套用 Hybrid iterative 的 6 GiB preferred 分类。

## R3 Hybrid direct（MPI8）

| phi / M | RSS MiB | total wall s | swap | status |
|---|---:|---:|---:|---|
| 0 / 120 | 7317.2 | 338.64 | 0 | own direct pass；iterative 6 GiB Gate not_applicable |
| 0 / 160 | 7765.4 | 416.82 | 0 | own direct pass；iterative 6 GiB Gate not_applicable |
| -5 / 120 | 7169.9 | 313.85 | 0 | own direct pass；iterative 6 GiB Gate not_applicable |
| -5 / 160 | 7665.0 | 377.42 | 0 | own direct pass；iterative 6 GiB Gate not_applicable |
| +5 / 120 | 7151.2 | 312.85 | 0 | own direct pass；iterative 6 GiB Gate not_applicable |
| +5 / 160 | 7628.0 | 379.51 | 0 | own direct pass；iterative 6 GiB Gate not_applicable |

Hybrid direct 只报告实测 RSS、时间与 swap，未套用仅适用于 Hybrid iterative 的 6 GiB
preferred 资源 Gate；这些 direct 运行不是 formal iterative authority。

## R4 allowed solver-vs-direct diagnostic（MPI8）

| phi / M | RSS MiB | PSS/USS MiB | swap | watchdog stage | linear wall / solver wall s | resource分类 | numerical分类 |
|---|---:|---:|---:|---|---:|---|---|
| -5 / 160 | 6711.6 | not_available（carrier字段为0，不作为实测） | 0 | setup | 332.13 / 274.00 | resource_unqualified, preferred=false | linear negative |
| +5 / 160 | 6714.6 | not_available（carrier字段为0，不作为实测） | 0 | setup | 323.89 / 267.24 | resource_unqualified, preferred=false | linear negative |

两次 diagnostic 的 watchdog 总时长约 641 s 和 629 s；记录中的 process-tree peak elapsed
约 308.05 s 和 303.05 s，二者不是同一字段。两次都自然退出、process group clean、swap=0，
没有资源终止。bottom/top true residual 在 `1e-4`--`1e-5`，modal residual 约`1e-15`，
说明瓶颈在 fixed endcap/FEM preconditioned convergence。

## 阶段耗时（R2/R3 measured records）

以下阶段值逐条取自各 JSON timing carrier，不是由 wall time 估算；Hybrid direct 的资源
字段仍只作 direct 实测对比，不能套用 iterative preferred Gate。

| 方法 / phi / M | stage4 assembly+solve / QEP | bases | local FE-DtN | modal coupling | primary build | postprocess / physical reconstruction | total wall / recorded total s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full3D / 0° | 219.335199 | not_applicable | not_applicable | not_applicable | not_applicable | 9.132969 | 236.248695 |
| Full3D / -5° | 249.792659 | not_applicable | not_applicable | not_applicable | not_applicable | 7.916975 | 267.569926 |
| Full3D / +5° | 215.246425 | not_applicable | not_applicable | not_applicable | not_applicable | 8.953008 | 234.190065 |
| Hybrid / 0° / M120 | QEP 0.824423 | 50.053914 | 162.570459 | 47.710957 | 28.461989 | 24.264035 | 338.640490 |
| Hybrid / 0° / M160 | QEP 2.679890 | 97.050630 | 163.719861 | 66.271922 | 29.797753 | 30.919383 | 416.815373 |
| Hybrid / -5° / M120 | QEP 2.442246 | 39.500598 | 163.452226 | 47.576589 | 17.105868 | 24.503548 | 313.854632 |
| Hybrid / -5° / M160 | QEP 0.833061 | 76.175254 | 161.772480 | 66.452507 | 19.007682 | 31.341285 | 377.416392 |
| Hybrid / +5° / M120 | QEP 3.001537 | 39.801125 | 161.041952 | 47.562409 | 17.458091 | 23.897224 | 312.851019 |
| Hybrid / +5° / M160 | QEP 3.117193 | 75.348622 | 162.332849 | 66.245286 | 20.211088 | 30.829970 | 379.512395 |

## 同 phi 的方法资源与总时间

这是跨方法的实测对照表，不是把不同方法的资源阈值混成一个资格 Gate。Hybrid direct
只报告实测 RSS、时间与 swap；Hybrid iterative 的 6 GiB preferred Gate 对 direct
为 `not_applicable`。两条 iterative diagnostic 虽然 RSS 较低，但都在 linear Gate
失败，不能被解释为合格的内存节省；其 PSS/USS carrier 的0值也不是实测值。

| phi | 方法 / M | RSS MiB | total wall s | swap | numerical/resource status |
|---:|---|---:|---:|---:|---|
| 0° | Full3D direct | 15332.5 | 236.248695 | 0 | authority pass; direct resource only |
| 0° | Hybrid direct / M120 | 7317.2 | 338.640490 | 0 | own direct pass; iterative 6 GiB Gate not_applicable |
| 0° | Hybrid direct / M160 | 7765.4 | 416.815373 | 0 | own direct pass; iterative 6 GiB Gate not_applicable |
| 0° | Hybrid iterative / M160 | not_run | not_run | not_run | not_run_by_R3_gate |
| -5° | Full3D direct | 15325.1 | 267.569926 | 0 | authority pass; direct resource only |
| -5° | Hybrid direct / M120 | 7169.9 | 313.854632 | 0 | own direct pass; iterative 6 GiB Gate not_applicable |
| -5° | Hybrid direct / M160 | 7665.0 | 377.416392 | 0 | own direct pass; iterative 6 GiB Gate not_applicable |
| -5° | Hybrid iterative / M160 diagnostic | 6711.6 | 641 approx | 0 | numerical fail; iterative preferred resource fail |
| +5° | Full3D direct | 15080.4 | 234.190065 | 0 | authority pass; direct resource only |
| +5° | Hybrid direct / M120 | 7151.2 | 312.851019 | 0 | own direct pass; iterative 6 GiB Gate not_applicable |
| +5° | Hybrid direct / M160 | 7628.0 | 379.512395 | 0 | own direct pass; iterative 6 GiB Gate not_applicable |
| +5° | Hybrid iterative / M160 diagnostic | 6714.6 | 629 approx | 0 | numerical fail; iterative preferred resource fail |

## MPI1

| phi | MPI1 Hybrid iterative | RSS | PSS/USS | swap | 结论 |
|---:|---|---:|---:|---:|---|
| -5° | not_run_by_R3_gate | not_run | not_run | not_run | M_robust未建立 |
| 0° | not_run_by_R3_gate | not_run | not_run | not_run | M_robust未建立 |
| +5° | not_run_by_R3_gate | not_run | not_run | not_run | M_robust未建立 |

不得用 MPI8 或 diagnostic 结果估算 MPI1 的 1.5 GiB preferred、2.0 GiB engineering 或
6 GiB hard-stop 边界。MPI1 既没有 numerical identity evidence，也没有资源实测。
