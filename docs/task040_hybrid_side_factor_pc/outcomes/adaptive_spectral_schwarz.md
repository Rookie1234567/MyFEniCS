# Adaptive spectral Schwarz outcome

## V9 current authority（Response v10）

| 项目 | 当前裁决 | 证据边界 |
|---|---|---|
| Stage A local | measured component pass | 630 patches、432 rows；local service Gate 通过，但 global true residual=`2.390497409724407` 不是完整求解结论 |
| Stage B/C | resource-gated stop | symbolic projected=`130502065136 B`，超过45 GiB；没有 source apply 或 outer residual |
| C0 | worker numerical no-signal measured；watchdog resource metadata gap | `rho_coarse=6.778773552009804`；watchdog raw resource classification仍保留，不推翻 numerical Gate，也不是 resource pass |
| C1 | `not_run_by_numerical_gate` | Review §5.5规定 C0 no-signal 后不实现同 basis matrix-free；旧 next 字段仅作审计事实 |

此处只补充当前裁决；原有 V1–V8 的实验记录和负结果全部保留，不整篇重写。

## 当前正式 authority

本路线先用局部边界服务产生 harmonic columns，再做 symbolic memory preflight；后者是判断能否安全分配分布式粗算子的资源闸门。它不是把局部 patch residual 直接当成完整 Maxwell 求解结果。

| 阶段 | 状态与事实 |
|---|---|
| Stage A local service | `V8_ADAPTIVE_STAGE_A_LOCAL_GATE_PASS`；630 patches，rows min/median/max=`432/432/432`，one overlap，POU error=`0`，shift=`0.1`；setup=`255.8505309909815s`，one apply=`3.498585887020454s` |
| Stage A residual语义 | local ratio median=`0`、p90=`2.955562184972804e-15`、max=`4.401656276000086e-15`；global true residual relative=`2.390497409724407`，不是 Stage-A Gate 失败，也不是 positive signal |
| exact B1 | root=`results/task040_v8_adaptive_stage_b1_mpi8_0e92079f_fix1`；`not_completed_at_10800s`；wall timeout=`10800s`；无 run summary/数值结果；允许转 economical variant，不是 numerical no-signal |
| Stage B/C | `ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE`；natural rc0，elapsed=`2504.0971691419836s`，peak=`19786649600 B`=`18.427753448486328 GiB`，swap=`0` |
| resource decision | baseline=`19658432512 B`；projected=`130502065136 B`=`121.539519295 GiB`（约121.540 GiB）；hard=`48318382080 B`=`45 GiB`；allocation=`false` |

BC 已形成 630 patches、160 modes/patch、100800 coarse DoF、570 factor classes、reuse saved=`60`、multi-RHS solves=`630`；factor nnz=`106375680`，owner loads=`[78,69,68,72,70,63,78,72]`。`factor_bytes_global=0` 是 release diagnostic matrices 后的字段，不是 factor-free 结果。由于 memory denial，P/P_H/FP/Ac/KSP、source vector、outer solver、one-apply 和 checkpoint 均为 `0/not_run`。cleanup complete 且 bare-F before/after hash 相同；详细 marker 与组件字节见 [response v9](../response_v9.md)。

### Raw Git identity

| 字段 | raw 值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| upstream_ref | `origin/codex/20260822-task40-hybrid-side-factor-pc` |
| upstream_sha / source_sha | `3564fe3ea491d1393e9e3d6741114fbbefc0ddc9` |
| ahead / behind | `0 / 0` |
| worktree | clean |

## C0 current formal raw ledger

这是 C0 explicit coarse-oracle formal 的 current raw 记录。`actual_global_memory_bytes=0`
只是 PETSc Mat info 字段，不能解释为矩阵不占内存；资源判断使用 process-tree RSS。

### Preflight 与资源边界

| observed MemAvailable (B) | minimum (B) | preferred / warning / hard (B) | swap | pass |
|---:|---:|---:|---:|:---:|
| 2137687257088 | 343597383680 | 171798691840 / 188978561024 / 206158430208 | 0 | true |

### C0 current marker table

| stage | phase wall (s) | formal wall (s) | RSS (B) | NNZ | raw Mat memory (B) | dimensions / details |
|---|---:|---:|---:|---:|---:|---|
| v9_c0_P_ready | 6.189266043016687 | 1425.4963794589858 | 20580634624 | 43545600 | 0 | `132300x100800` |
| v9_c0_P_H_ready | 2.0402458190219477 | 1427.7710560940322 | 21066231808 | 43545600 | 0 | `100800x132300` |
| v9_c0_FP_ready | 86.95330124703469 | 1514.9619506089948 | 38456442880 | 532627200 | 0 | `132300x100800` |
| v9_c0_Ac_ready | 770.295678836992 | 2285.7105018270086 | 86902804480 | 1247232000 | 0 | `100800x100800` |
| v9_c0_coarse_ksp_ready | 0.005946719960775226 | 2285.947907577036 | 86905307136 | 1247232000 | 0 | GMRES/Jacobi, restart32/max32; Ac NNZ/memory=`1247232000/0` |
| v9_c0_external_one_apply_begin | — | 2286.8933941480354 | 86933618688 | — | — | source norm=`78.95028494966374`; action/local=`0/0` |
| v9_c0_external_one_apply_end | — | 2527.8660635240376 | 86942371840 | — | — | apply wall=`239.8155699960189`; target norm=`42.937893107083006`; abs=`535.1861035404182`; rel=`6.778773552009804`; action/local=`1/2` |

以上各阶段 swap 均为 `0`。

### C0 factor inventory 与 cleanup

| class count / ready | reuse saved | owner loads | local rows | factor nnz global |
|---:|---:|---|---:|---:|
| 574 / 574 | 56 | `[71,66,75,76,72,78,70,66]` | 432 | 107122176 |

cleanup 时 factor ready 从 `574` 变为 `0`。不要把旧 Stage B/C 的 `570/60` 计数混入本
C0 formal。

C0 lifecycle raw 明确：coarse-ready 的 allocated_object_count 为
`P=1, P_H=0, FP=0, Ac=1, KSP=1`；matrix ownership 为 P transient、
`P_H/FP transient_until_Ac_ready`，Ac/coarse_ksp 为
`owned_by_coarse_action`。cleanup 时 `coarse_action_destroyed=true`、
`direct_work_released=true`、`source_vectors_destroyed=1`、
`outer_solver_created=false`，factor 从 `574` 变为 `0`。逐对象 destroy
细节若未序列化不补成 true。

## 历史预运行快照

## 状态

```text
status = NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE
```

Review V7 §10.3 的 wall/resource Gate 是独立停止边界；本轮 corrected moving-PML formal 在
第一个 source 的 one-apply/FGMRES 之前因 `wall_timeout` 达到该 Gate，因此 adaptive 未启动。
这不是 adaptive negative。若 moving-PML 得到 valid positive，按 Review 路由应进入
factor-free local service；本轮没有 valid PML signal。

V8 当时这不是 adaptive 的数值 negative，也不是 0.7 nm capacity 的否定；没有构造 local coarse、
没有运行 sweep、没有产生 residual、memory、factor 或 Full3D handoff 数据。依赖该路线的
factor-free local service、完整 Hybrid、h3、0.7 nm 和 arbitrary Full3D 均保持未运行/未资格化。

本轮 stop 的 resource evidence 见
[moving-PML outcome](moving_pml_sweep.md)：peak process-tree RSS=`40560816128 B`，swap=`0`，
elapsed=`21601.760233s`，硬线=`45 GiB`、wall=`21600s`。在新的 Review 决定前不启动
adaptive 或任何第三次 heavy formal。
