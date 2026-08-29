# Task038-extra Review V13 response

本 response 先给通俗边界：C1 positive 资格只是证明一个固定预条件器在正定辅助问题上能够压低误差；P0 才是把它接到真实波动 Maxwell、双 Floquet 和 streaming Fourier-DtN 散射流程中。P0 在 cold setup 超过严格 2 GB process-tree hard line，因此后续 physical observables 没有被运行。

## 1. Route A 的 ordinary、pairwise、compensated 和 vector-level adjoint 分别是多少？

V13 A0 已实际运行 6 probes。下表依次给出 ordinary relative、pairwise-vs-compensated、compensated-work、vector adjoint、ordinary absolute defect 和 forward-error bound：

| probe | ordinary relative | pairwise-vs-compensated | compensated-work | vector adjoint | ordinary abs defect | forward-error bound |
|---|---:|---:|---:|---:|---:|---:|
| random | 1.325290726135586e-14 | 5.221119180681054e-16 | 3.4687227818657926e-16 | 0 | 5.693268669984462e-7 | 0.21471124180753007 |
| gradient | 2.8964367576123248e-11 | 2.7478465599487806e-12 | 5.527844447606805e-13 | 0 | 6.419432276774822e-8 | 0.03265692601604265 |
| curl | 1.1945918306872908e-13 | 7.101959816797345e-15 | 8.347968140964517e-15 | 0 | 4.6421549285134685e-8 | 0.02832165192397101 |
| checkerboard | 3.854526613333027e-13 | 2.5735515917179632e-14 | 8.000096607002947e-14 | 0 | 1.3692487050577552e-7 | 0.28444156832375467 |
| physical_component_derived | 1.2611959839185316e-15 | 4.836465818702122e-16 | 9.67293163740424e-16 | 0 | 2.399963341663627e-10 | 0.00018036841970458148 |
| r3_long_tail_derived | 3.7456675108670225e-15 | 5.575114506837729e-16 | 5.652016270719098e-16 | 0 | 7.508562643358995e-8 | 0.05012076254499549 |

primary V13 failure 是 gradient pairwise-vs-compensated=2.7478465599487806e-12 > 1e-13。compensated-work 最大值为 5.527844447606805e-13 ≤ 1e-12，vector-level 最大值为 0 ≤ 1e-11；ordinary absolute defect 均远小于 4×forward-error bound。V12 的 ordinary failure 与局部 10 material-class 事实仍冻结。checker 中 random/checkerboard energy_imag flags 原样保留，但不是建立 V13 closure 所必需的额外合同。

## 2. Route A 是否被新身份重新开放？旧 V12 FAIL 是否完整保留？

A0 确实运行，但没有重新开放 Route A。其 gradient pairwise Gate 已关闭 A0，MPI2/A1 为 not_run_by_A0_gate，随后按固定分支进入 C0；V12 Route A global adjoint failure、source 和阈值完整保留，未被 C0/C1/P0 结果覆盖。

## 3. C1 canonical-key input 在 MPI1/MPI2 是否先达到完全一致？

是。C0 v4 在 source SHA 4dc9b55cd3519a03b23c9d27779c0379cef84f66 下完成 MPI1/MPI2；physical canonical key set、source primal/dual、projected/adjoint canonical identity 和 phase/owner facts 均通过。C0 记录为 C0_CANONICAL_SOURCE_PASS_MPI1_MPI2。V12 旧 C1 identity negative 的 primal/dual cross-MPI mismatch 仍作为历史负证据，不被这次 C0 重分类。

## 4. A 或 C 是否完成 p6 四源 positive 资格？

完成的是 C1 exact-input p6/h10 same-mesh positive lane，不是 Route A。random、gradient、curl、checkerboard 四案均为 C1_P6_POSITIVE_PASS_MPI1，selected_hierarchy=same_mesh_hcurl_pmg_v1_requalified。各案独立 source SHA、root、worker/checker 和 watchdog 证据见 outcomes/p6_positive_v13.md。

## 5. 若进入 G0，为什么它与 Task027 GenEO 不同？理论公式和 threshold 如何在看谱前冻结？

本轮没有进入 G0，状态为 not_run_by_selected_C1。因而没有新增 G0 理论、谱计算或 threshold，也没有把 Task027 GenEO 的结果移植成 V13 结论。Review 要求的“先冻结公式和阈值再看谱”仍是未来若获授权的前置合同；本轮没有产生可报告的 G0 数值。

## 6. G0 的 gradient/coarse rank、local factor 和完整 live-set 预算是否闭合？

没有测量，状态为 not_run_by_selected_C1。没有创建 G0 rank、local factor、coarse basis 或完整 live-set；不能用 C1 positive 的 p3/p1 sparse 对象代替 G0 budget。

## 7. GenEO 小型与 p6 各 source 的 true residual、迭代数、RSS 和 swap 是多少？

GenEO 小型没有运行，因此没有 residual、iterations、RSS 或 swap。p6 C1 positive 的四源事实如下，但它们不是 GenEO：

| source | final true residual | iterations | peak RSS / retained RSS | swap |
|---|---:|---:|---:|---:|
| random | 5.550975220267439e-9 | 200 | 1,517,903,872 / 772,497,408 B | 0 |
| gradient | 2.7889793119815017e-9 | 220 | 1,516,544,000 / 770,650,112 B | 0 |
| curl | 5.6105046279899595e-9 | 180 | 1,536,192,512 / 790,028,288 B | 0 |
| checkerboard | 7.760965317017376e-9 | 200 | 1,533,190,144 / 786,751,488 B | 0 |

## 8. 若进入 D0，为什么新 BDDC/FETI-DP 没有重复 Task025 的 12.78 GB 失败架构？

本轮没有进入 D0，也没有实现或运行 BDDC/FETI-DP。Task025 的 12.78 GB 历史边界继续保留；不能把没有运行写成“没有重复”。V13 的 selected positive hierarchy 来自 C1，不是新 BDDC/FETI-DP。

## 9. 是否获得 selected hierarchy 并运行 physical Maxwell？

获得了 selected_hierarchy=same_mesh_hcurl_pmg_v1_requalified，因为 C1 四源通过。随后确实启动了一个 P0 physical Maxwell MPI1 formal，但它在 cold setup 触发 process-tree RSS hard stop，只有 paths_ready；没有进入 solve。因此“selected hierarchy 已获得”和“physical workflow 已完成”是两个不同结论。

## 10. official E/H、R/T/A、A_volume 和 channels 是否来自通过 true residual Gate 的场？

没有。P0 没有 worker record、true residual、recovery packet 或恢复场；official E/H、R/T/A、A_volume，以及同一 12 个显著通道的 12 个 power Gate 和 12 个 complex boundary-amplitude Gate 均为 not_run_by_resource_gate。当前 tracked direct authority 只有 scalar R/T/A/A_volume，缺少 E/H 与 12+12 raw arrays；该 downstream comparison blocker 因 P0 先在 cold setup 停止而未触达，不是本次停止原因。C1 auxiliary vectors 不被冒充为 physical fields。

## 11. complete workflow peak、swap、release-before-recovery 是否通过？

没有。P0 watchdog 在 cold setup 达到 2,024,108,032 B，超过 2,000,000,000 B hard line 24,108,032 B，约 1.2054%，所以 resource Gate 严格失败；process-tree swap=0、no_orphan=true，但这些通过事实不能抵消 RSS hard stop。没有进入 recovery，因而没有 release-before-recovery observation。P0 现场没有被解释为数值或 physics failure。

## 12. 0.7 nm / 2 TiB 还有哪些 measured、derived、predicted blocker？

| 口径 | 结论 |
|---|---|
| measured | C1 四源 p6/h10 peak 为 1.5165–1.5362 GB；P0 13.5 nm cold setup peak 为 2.024108032 GB，swap=0，但超过 2 GB hard line |
| derived | 当前 P0 resource Gate 超出 24,108,032 B，约 1.2054%；没有 residual、official physics 或 recovery data |
| predicted | 0.7 nm 完整 PDE 的 DoF、JIT、MPI live-set、physical fields 和 total capacity 未测量；不能把 13.5 nm peak 外推为 0.7 nm/2 TiB 通过 |

因此 feasibility_0p7nm_2tib_v5 没有创建，完整 0.7 nm PDE 也没有运行。

## 13. 哪些代码是 reusable、research-only、do-not-promote 和 evidence/docs？

| 分类 | 文件/范围 | 边界 |
|---|---|---|
| reusable audit/canonical/resource helper candidates | src/solvers/fullspace_lor_stable_adjoint.py；src/solvers/hcurl_canonical_vector.py；src/solvers/hcurl_canonical_vector_dolfinx.py；benchmarks/task034_wsl_resources.py | 仍需最终 selective review；不等于 ordinary default |
| research-only pending physical qualification | src/solvers/fullspace_same_mesh_hcurl_pmg.py；src/solvers/fullspace_same_mesh_hcurl_pmg_global.py；src/solvers/fullspace_same_mesh_hcurl_pmg_p6.py；src/solvers/fullspace_same_mesh_hcurl_pmg_runtime.py；src/solvers/fullspace_same_mesh_hcurl_pmg_setup.py；src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py；对应 Task038 same-mesh C0/setup/positive/P0 runners/checkers | C1 positive 已通过，但 P0 resource hard stop；不得提升为 production |
| do-not-promote/do-not-merge as production numerical candidate | Route-A 6→3 candidate integration：src/solvers/fullspace_lor_interlevel_spectral_dolfinx.py 及对应 interlevel runner/checker；旧 Route-B/C2/HX 等已冻结失败路线 | 不提升为 production numerical candidate；stable-adjoint audit helper 不属于此类 |
| evidence/docs | 本轮 A0/P0 negative compact、outcomes 文档与 response_v13.md | 永久保留，可作为文档/证据选择性合入；提交负证据不代表把失败 solver 合入 production |

## 当前未触达项

G/D、P1、P2、physical MPI2、h5、0.7 nm PDE、official physics 和 ordinary-default change 均为 not_run_by_selected_C1 或 not_run_by_resource_gate。未创建未触达阶段的伪 outcome 文件；C0、C1、P0 的证据入口和边界分别见 outcomes/same_mesh_canonical_source_v1.md、outcomes/p6_positive_v13.md、outcomes/p6_physical_v13.md。
