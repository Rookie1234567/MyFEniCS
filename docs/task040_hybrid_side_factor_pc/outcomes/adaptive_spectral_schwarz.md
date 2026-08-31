# Adaptive spectral Schwarz outcome

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

## 历史预运行快照

## 状态

```text
status = NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE
```

Review V7 §10.3 的 wall/resource Gate 是独立停止边界；本轮 corrected moving-PML formal 在
第一个 source 的 one-apply/FGMRES 之前因 `wall_timeout` 达到该 Gate，因此 adaptive 未启动。
这不是 adaptive negative。若 moving-PML 得到 valid positive，按 Review 路由应进入
factor-free local service；本轮没有 valid PML signal。

这不是 adaptive 的数值 negative，也不是 0.7 nm capacity 的否定；没有构造 local coarse、
没有运行 sweep、没有产生 residual、memory、factor 或 Full3D handoff 数据。依赖该路线的
factor-free local service、完整 Hybrid、h3、0.7 nm 和 arbitrary Full3D 均保持未运行/未资格化。

本轮 stop 的 resource evidence 见
[moving-PML outcome](moving_pml_sweep.md)：peak process-tree RSS=`40560816128 B`，swap=`0`，
elapsed=`21601.760233s`，硬线=`45 GiB`、wall=`21600s`。在新的 Review 决定前不启动
adaptive 或任何第三次 heavy formal。
