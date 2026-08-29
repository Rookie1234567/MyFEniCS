# Route A stable/compensated adjoint outcome

## 读者先知道

Route A 用固定 probe 检查候选传递的伴随关系。它回答的是局部/全局代数是否可信，不是 physical Maxwell 散射结果，也不是 ordinary default 的批准。

## V13 A0 实际运行结论

A0 已实际运行：source SHA 为 a05a5e33a524bb89ba7c22de3efef0882bbc7464，p6/h10、MPI1、same 6 probes 和 6→3 transfer。worker 与独立 checker 的分类为 CLOSED_BY_VECTOR_OR_STABLE_ADJOINT_GATE，passed=false，contract_errors=[]。

| probe | ordinary relative | pairwise-vs-compensated | compensated-work | vector adjoint | ordinary abs defect | forward-error bound |
|---|---:|---:|---:|---:|---:|---:|
| random | 1.325290726135586e-14 | 5.221119180681054e-16 | 3.4687227818657926e-16 | 0 | 5.693268669984462e-7 | 0.21471124180753007 |
| gradient | 2.8964367576123248e-11 | 2.7478465599487806e-12 | 5.527844447606805e-13 | 0 | 6.419432276774822e-8 | 0.03265692601604265 |
| curl | 1.1945918306872908e-13 | 7.101959816797345e-15 | 8.347968140964517e-15 | 0 | 4.6421549285134685e-8 | 0.02832165192397101 |
| checkerboard | 3.854526613333027e-13 | 2.5735515917179632e-14 | 8.000096607002947e-14 | 0 | 1.3692487050577552e-7 | 0.28444156832375467 |
| physical_component_derived | 1.2611959839185316e-15 | 4.836465818702122e-16 | 9.67293163740424e-16 | 0 | 2.399963341663627e-10 | 0.00018036841970458148 |
| r3_long_tail_derived | 3.7456675108670225e-15 | 5.575114506837729e-16 | 5.652016270719098e-16 | 0 | 7.508562643358995e-8 | 0.05012076254499549 |

V13 primary failure 是 gradient 的 pairwise-vs-compensated relative=2.7478465599487806e-12 > 1e-13。六 probe 的 compensated-work 最大值为 5.527844447606805e-13 ≤ 1e-12，vector-level 最大值为 0 ≤ 1e-11；ordinary absolute defect 均远小于对应的 4×forward-error bound。checker 中 random 与 checkerboard 的 energy_imag flags 原样保留，但不是建立 V13 closure 所必需的额外合同；gradient pairwise Gate 已足以关闭 A0。

## A0 资源与生命周期

| 项目 | 实测事实 |
|---|---|
| watchdog | 1,464 samples；natural_exit=true；no_orphan=true；all samples readable |
| process-tree resource | peak 1,420,718,080 B；swap=0 |
| downstream branch | MPI2/A1 not_run_by_A0_gate；随后按固定分支进入 C0 |

## 证据入口

ignored artifact root 为：

benchmarks/artifacts/task038_extra_full3d_stable_adjoint_a0_v1/a05a5e33a524bb89ba7c22de3efef0882bbc7464/p6-h10-mpi1

原始 raw 文件为 watchdog_raw.jsonl，SHA256 为 611ba9986e3176a8d34885ac0365cd5bd56b9c58615820b592842c8e9587bfee。tracked compact evidence 为：

| 文件 | SHA256 |
|---|---|
| records/route_a_stable_adjoint_a0_v1.json | fbbe1b29ee7a046248cc45f93e6d46490a2c4423cfb246da8aa752ac577706d5 |
| records/route_a_stable_adjoint_a0_v1_checker.json | c19b0bc50219013ef17a375652dc885cb05d3d087fae314077c444c721e8adcc |
| records/route_a_stable_adjoint_a0_v1_watchdog.json | 263a5b931f8ac109b30d15cbe66b4dccad7fd6be9ea3d39e4a623181087a690e |

V12 的 ordinary Route A failure 仍冻结，不被 A0 新 evidence 重分类；V13 A0 是真实负结果，不是未测量项。
