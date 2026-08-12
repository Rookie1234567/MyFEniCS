# M2 high-complement patch oracle：正式数值负结果

## 结论先行

M2 已完成一次正式 p6/h10 high-complement patch oracle。它把一个完整的 `882×882` 局部 row-complete patch 分成低阶 `QL`（300 维）和高阶 `QH`（582 维），只对高阶部分做一次正式 factor/solve；`rho` 是校正后 patch residual 与原 patch RHS 的相对范数。该方法通过了执行、资源、rank、factor 和 action closure Gate，但 checkerboard source 的正式 `rho` 超过 Review V11 的 `0.70` 限值，因此 M2 是正式数值失败。

| 项目 | 结果 |
|---|---|
| M2 状态 | `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED` |
| 唯一正式失败 | checkerboard/high-frequency `rho_star=0.7319752447810908 > 0.70` |
| watchdog | `PASS`，stage/online worker 均 `RC=0` |
| checker | `RC=1`，`status=gate_failed`，compact machine problem 为 `source_gate` |
| 资源 | stage peak `1,296,175,104 B`；online peak `848,654,336 B`；swap `0` |
| M3–M6 | `not_run_by_gate`；不进入 M3 |

用户明确授权继续突破 Review V11 的 formal-count 限制，用于定位和必要复跑；该授权没有放宽数值、RSS、swap、物理、provenance 或 full-space 架构 Gate。此次结果是数值负结果，不属于可再包装的 execution-fix。

## 正式输入与身份

| 字段 | 实测/固定值 |
|---|---|
| raw | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1` |
| source | `b4c1c6c76d667dac78e5dc384b302026379cb8d2`，worker start/end 相同且 clean |
| scope | 252 cells、173,802 global rows、9,210 constraints、central cell `3`、class `3`、19 touching cells |
| operator | restricted-global row-complete `B_P`，patch rows `882`；未形成 global matrix、global constraint matrix、Schur、slab 或 KSP |
| rank | `rank(QL)=300`、`rank(QH)=582` |
| Q orthogonality | `9.257892486599041e-16` |
| split reconstruction | `9.637068547580966e-16` |
| retained transform | `12,446,784 B`；单份 dense `QL+QH`，未保留 per-neighborhood QH |
| factor values+pivots | `5,421,912 B` |
| factorization residual | `5.725553567915199e-16` |
| representative solve residual | `6.773813153765502e-13` |
| stage elapsed / online elapsed | `35.527295590989524 s` / `2207.712309387003 s` |

## 五类 source 的正式测量

| source | low energy | high energy | formal rho | action closure | 结论 |
|---|---:|---:|---:|---:|---|
| gradient-dominated | `0.7476937969517845` | `0.25230620304821527` | `0.6501331033379294` | `3.731727295429185e-14` | PASS |
| curl-dominated | `0.6568811348518978` | `0.34311886514810186` | `0.5370997972508667` | `4.765947835467422e-14` | PASS |
| mixed | `0.7350021241367845` | `0.26499787586321516` | `0.6350618866926864` | `3.9933950843220025e-14` | PASS |
| checkerboard/high-frequency | `0.6666666666666659` | `0.3333333333333332` | **`0.7319752447810908`** | `1.1012012738647016e-13` | **FAIL，超过 `0.70`** |
| physical-RHS-like | `0.6338129814899229` | `0.3661870185100772` | `0.5038880312320936` | `4.8627220733002086e-14` | PASS |

因此 M2 的失败边界是 checkerboard 的正式 source Gate，而不是 timeout、JIT、API、RSS、swap、factor residual 或架构禁止项。

## 固定离线耦合诊断

以下两份诊断都只读取冻结 raw 的 injection、patch、QL/QH、factor 和 source arrays；均标为 `BEST_CASE_DIAGNOSTIC_ONLY / not_formal_pass`，不改写 M2 结论。

| 诊断 | 脚本 SHA | JSON SHA | 固定结果 |
|---|---|---|---|
| row-complete low→high / exact sanity | `177d8e38188d9bd19a1fe504073dc9d297bed79d2fb8093cb350dd261e3d7d21` | `7d5e511377801efd4473ae795a6a09ab9394adcf39527d4f799d5dfd6afcde52` | checkerboard low→high `0.7365588632365486`；exact patch sanity `2.1656111107723205e-12` |
| fixed A/B/C/D coupling diagnostic | `e74f8528c25eda0e86acb8754c7705fffb1c7bcb103d59f117fbfa52713ef5fc` | `ad900db41005e3540e4c3088b59145e5991290a71f3e8ca76667c267f9f3485e` | joint2 `0.7314868062038236`；symmetric LHL `0.7318570005704766` |

第二份诊断的固定结构是：

- A：exact row-complete `BLL` low solve、`omegaL`，再对 `r1` 做 exact `BHH` high correction、`omegaH`；
- B：保持 A 产生的两个 action directions，解一次固定 `2×2` complex least-squares；
- C：在 A 的 `r2` 上再做恰好一次 low correction，总 action 数为 3；
- D：只计算 `BLH` coupling 与 checkerboard direction geometry，不做 SVD、shift、tolerance 或参数选择。

checkerboard 的 `BLH` coupling ratio 为 `0.21835354278513708`；A 中两条 q direction 的 Gram condition 为 `199.32174544507896`。固定 joint2 和 LHL 都仍高于 `0.70`，所以该诊断排除了“只补 low 阶段即可恢复 M2”的解释，但不能据此声称任何 M3/M4 资格化通过。

正式 element-class low operator 未运行：冻结 authority 没有同时提供可独立闭合的 R2 class=3 operator、row map、orientation 和 MPC coefficient binding；未把 R2 LU double-constrain 成 element-low operator。

## 早期执行失败链的边界

这些失败均已保留为历史 raw，不得与本次正式数值失败混写：

| raw/阶段 | 分类 | 原因边界 |
|---|---|---|
| `m2_4b521af_qualification_run1` | execution failure | `_build_b0_form` NameError |
| `m2_c787060_execution_fix_run1` | resource/lifecycle failure | JIT compiler descendants 与 online 对象同驻，触发资源生命周期问题 |
| `m2_6fa53b8_form_reuse_run1` | execution/provenance failure | fresh form 的 nested tuple/list 形态导致 `forms_match` 失败 |
| `m2_f4ec2fd_normalized_form_run1` | execution timeout | 原 `1800 s` 小于已知正常 P0/M2 工作量 |
| `m2_44fc277_timeout3600_run1` | API mismatch | `local_apply` 的 `cell_info` 必须是 keyword-only |
| `m2_e3be3c1_api_fix_run1` | API mismatch | residual callback 的一参/二参契约不一致 |
| `m2_5f8981f_action_adapter_run1` | telemetry execution defect | stage exit/`exit_mm` 竞态造成误终止；后续 statm 语义修复保留资源 Gate |

这些历史问题不构成本次 checkerboard 数值失败的替代解释；本次最终 raw 已完整进入 factor/rho/source measurement。

## 证据索引与后续锁定

| 证据 | SHA |
|---|---|
| final raw worker summary | `3db16f4d2709c9839bbdec88366c0f740da1f7cd871981992c71c758adc74f73` |
| final raw watchdog summary | `bad3879a32d11434caf2bb5d4c235b05a91ffd7c210a4add496be958fd6d7425` |
| final raw form reuse | `7f90385c16534e79c81df8b36103c2ddfe52c6afcc7759ef9ec493e2fd1c27e9` |
| final compact v2 | `benchmarks/cases/101_task37_extra_development/records/m2_high_complement_patch_oracle_v2.json`；file SHA `ebd512aa0e4b6823d5d95c5f816cc6e898c9fd97392af4f7346c83ba3ac4e31f` |
| compact embedded evidence | `59e0af2e187be4bc593db25a81b5c685fdbbeac5d45633687ae35863a12843a5` |
| initial M2 negative compact | `m2_high_complement_patch_oracle.json`；SHA `bfb59f5b2f0c75e1863a78cd58bb951f2b3dbd30a7f3b2bd4526f8c77ae57023` |

`m2_high_complement_patch_oracle_v2.json` 的 machine status 为 `gate_failed`、`pass=false`、`problems=["source_gate"]`；它保留 worker/raw 的完整数值字段，不能改写为 PASS。M3、M4、M5、M6、H2B-K、H2D、H4、PDE、RTA 和 full PDE process-tree RSS 均 `not_run_by_gate`/`not_measured`。因此最终 `<2,000,000,000 B` full PDE 目标尚未测量，更不能用 M2 stage/online 峰值替代 PDE 峰值。

本结果不改变 ordinary default；不引入 global matrix、static condensation、trace slab、local Krylov 或参数扫描。后续如要研究 checkerboard，必须取得新的监督边界；不得把上述 BEST_CASE 诊断直接升级为 M3。
