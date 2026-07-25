# Task035b 负结果与受控停止

所有 negative、formal failure 和 preflight stop 均保留；没有删除或改写为
通过。

| lane / record | 分类 | 主要原因 | 后续决定 |
|---|---|---|---|
| p4-trace p4/p6-interior h10 | `controlled_negative` | 88,994 DoF 成本通过；R00/R/T/A/orders/field 全失败 | p4 fixed-trace closed |
| p5-trace p4-low/p6-high N62 h10 | `controlled_negative_non_exact_sequence_space` | low space curl nullity 112 vs expected gradients 178 | preflight 禁止重复 |
| N62 postprocess failure | `formal_not_pass` | 历史正式失败 | 原样保留 |
| N62 wrong-control preflight | `formal_not_pass` | authority identity 错误 | 原样保留 |
| independent-condensation attempt | `formal_not_pass` | worker/result 缺失 | 原样保留 |
| global p6/h15 | `controlled_negative_full_same_error_gate` | scalar/field 通过；significant power 6/12、amplitude 8/12 | 不进 Hybrid |
| fixed p5-trace/p6-interior h15 | `controlled_negative` | preferred 74,890 DoF；significant power 6/12、amplitude 7/12 | 不进 Hybrid |
| first h15 channel-adjoint run | `formal_not_pass` | verification 仅 2/16 通过 | 原样保留；由 v2 修复验证 |
| p7/h10 preflight | `stopped_by_gate` | end-to-end Floquet/condensation 未资格化；预计 273,581 DoF | PDE 0 |
| h15 DtN q31 | `controlled_negative` | 6/12 power、7/12 amplitude 不变 | 关闭 quadrature lane |
| h15 unscaled buffer1 | `stopped_by_gate` | 最小 boundary phase `4.70e-84`，数值不安全 | PDE 0 |
| h15 scaled buffer1 | `controlled_negative` | 260 evanescent modes；仍 6/12、7/12 | 关闭 buffer lane |
| fixed h14 directional-z | `controlled_negative` | 7/12、9/12；有正信号但未全过 | 继续唯一 h13 点 |
| fixed h13 directional-z | `controlled_negative` | 89,740 DoF；10/12、10/12 | 当前最佳预算内；不进 Hybrid |
| h13 top2 z redistribution | `controlled_negative` | 同一 89,740 DoF；实际 8/12 power、8/12 amplitude | bounded z-node negative；只授权 exact-reverse 判别 |
| h14 exact-reverse h13 top2 | `controlled_negative` | 82,315 DoF；实际 7/12 power、8/12 amplitude | reverse negative；关闭 z-node lane |
| fixed h15 x-only | `controlled_negative` | 5/12、6/12，较 seed 回退 | 关闭 x lane |
| y-only global-p5 control | `controlled_negative` | 3/12、1/12，无材料性改善；不是 same-space y 排除 | 关闭指定 mechanism-control lane |
| h14 R5-slab bisect | `controlled_negative` | 5/12、9/12；新增 `R(-7,0)` power failure | 关闭预先指定 R5-slab split lane；其他 node distributions 未运行 |
| global p6/h14 | `controlled_negative_diagnostic_only` | 9/12、12/12；92,850 DoF 超限 2,850 | 只保留 same-mesh full-trace marginal signal |
| p6-trace/p5-interior preflight | `controlled_negative_non_exact_sequence_space` | 缺 101 gradient modes | PDE 0 |
| p6-trace/p4-interior preflight | `controlled_negative_non_exact_sequence_space` | 缺 149 gradient modes | PDE 0 |
| historical physical selective-trace gate | `capability_stop_not_run` | Review V1 时 physical Riesz/orbit/residual/DWR/numbering 未闭合 | 历史 stop 原样保留 |
| current physical selective-trace execution | `capability_only / formal_not_run` | actual expansion、exact sequence、Stage-4 与 MatShell 仅完成 fixture/correctness qualification | actual h14 DWR/PDE/candidate count 0 |
| historical condensed trace iterative gate | `capability_stop_not_run` | 当时无专用 factor-free provenance/history contract；HYPRE unavailable | 历史 stop 原样保留 |
| h15 GMRES + Jacobi | `controlled_negative_iterative_nonconvergence` | 200 iter；terminal 0.861662；true residual 0.861661 | official output 0；不进 Hybrid |
| h15 FGMRES + ASM/ILU(0) | `controlled_negative_iterative_nonconvergence` | 200 iter；terminal 0.999661；true residual 0.999659 | official output 0；关闭 legacy ASM lane |
| h15 FGMRES + z-slab ILU(0) + DtN trace | `controlled_negative_iterative_nonconvergence` | 200 iter；terminal 0.996265；true residual 0.996263 | official output 0；同 profile 不重复 |
| selected-p6 trace matrix-free PDE | `capability_only / not_run` | MatShell 仅通过 serial/MPI2 assembled-action oracle；无独立低存储 PC | formal PDE/memory result 0 |
| inversion-aware observable selection | `not_run` | 反演参数、噪声、仪器 authority 未冻结 | 保留全部 12 通道 |
| Task035 tetra final p6 | `controlled_negative` | vector control 通过，strict-R control 失败；167,784 DoF | 只作顺序竞争 |
| structured-hexa local-h | `stopped_by_gate` | hanging-node/transition conformity 未实现 | 不发明局部网格 |
| tetra selected local-p6 | `stopped_by_gate` | reduced selected-p6 implementation 为 hexa-only | 不重复 heavy p6 |
| h37.5 fixed-mesh p6 | `stopped_by_gate` | refined p5 已超预算，缺少 selected-p6 | 不运行 |
| best-candidate Hybrid/M funnel | `stopped_by_gate` | 无同误差候选 | 不运行 |
| 0.7 nm PDE / 2 TiB resource model v3 | `not_run` | Hybrid eligible candidate count 0；无 selected layout/accuracy authority | 不运行 |

## 两个连续成本/精度负信号的解释

fixed trace 的成本信号是真的：active rows、matrix/factor NNZ、peak memory 和
time 均下降。精度负结果也是真的，但 N62 后来被 exact-sequence audit
重分类，不能把它当作第二个独立、合格的 local-p accuracy negative。关闭
当前 lane 的依据是：

1. p4-trace exact-sequence 候选完整精度 Gate 失败；
2. p5-trace/p4-interior 本身结构不合格；
3. h15 global 与 fixed p5-trace/p6-interior 均在 significant channel Gate
   失败；
4. Review V1 的 z-direction 虽有正信号，但到 h13/89,740 DoF 仍只达到
   10/12 + 10/12；随后 h13 top2 与 h14 exact-reverse 的实际计数又分别
   回退到 8/8 和 7/8，不能把先验 projected count 写成 measured result；
5. full p6/h14 的 trace 正信号超预算，现有 proxy 不足以授权 physical
   selective-trace subset；当前新增能力仍只是 fixture/correctness
   qualification，actual h14 DWR 与 PDE 都为 0；
6. 三条 assembled iterative screen 均在 200 iterations 以
   `DIVERGED_MAX_IT` 停止，且 recovered true residual 仍为
   `8.62e-1`、`1.00e0` 与 `9.96e-1`，没有 official R/T/A/channel 输出。

## Review V2 negative evidence authority

| evidence | path |
|---|---|
| h13 top2 bounded negative | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json` |
| h14 exact-reverse bounded negative | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_exact_reverse_h13_top2_mpi8_v1.json` |
| Jacobi 与 ASM/ILU formal screens | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_factor_free_iterative_mpi8_v1.json` |
| physical z-slab/DtN formal screen | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json` |
| failed-output semantics correction | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/condensed_iterative_failed_output_caveat_v1.json` |
| historical physical trace stop | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_trace_lane_capability_gate.json` |
| historical iterative stop | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/condensed_trace_iterative_capability_gate.json` |

前两条 iterative screen 的旧 worker 曾在 common flow 拒绝未收敛 KSP 前写出
带 `status=ok` 的 diagnostic port 文件。caveat record 保留并 hash-bind
这些 artifact，但明确规定它们不是 official power、amplitude、field 或
Hybrid authority。第三条 screen 从运行时就跳过 postprocess。三条结果的
较低 RSS 都不能抵消残差失败，也不能称为 factor-free memory floor。

physical selective-trace correctness 能力已有独立 compact capability
record，但尚无 formal candidate record：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_selective_trace_execution_capability_v2.json`

- `src/test/test_147_task035b_actual_selective_trace_expansion.py`
- `src/test/test_153_task035b_physical_channel_dwr_trace_selection.py`
- `src/test/test_157_task035b_actual_physical_discrete_gradient_authority.py`
- `src/test/test_171_task035b_actual_selective_trace_stage4_wiring.py`
- `src/test/test_172_task035b_selective_p6_trace_matrix_free.py`
- `src/test/test_174_task035b_stage4_pre_release_capture.py`

## 非负结果

以下项目不能因任务整体没有成功候选而写成失败：

- exact assembly-time static condensation；
- Floquet slave elimination；
- solver-object release、heap trim、MPI tensor dedup 与 exact preallocation；
- same-mesh DWR R00/R/T；
- 252-cell physical smoothness signal；
- fail-closed classifier fixtures。
- significant channel reference v1 与 16/16 channel Hermitian adjoints；
- manufactured Rayleigh/port phase authority；
- h15→h14→h13 的方向性 z 正信号；
- global p6/h14 的 trace physics signal。
- h15/h13 canonical-orientation cold/warm setup authority；
- h15 MPI1/2/4/8 direct memory rank study；
- physical selective-trace 与 selected-p6 MatShell 的 fixture/correctness
  capability。

它们是可复用工程/研究正结果，但不单独构成 same-error hp 压缩或 0.7 nm
可行性证明。

setup-only authority 的 cold/warm 数字必须按其原始语义保留：

| setup-only pair | non-KSP build cold/warm | process-tree peak cold/warm | interpretation |
|---|---:|---:|---|
| h15 canonical | 19.242 / 6.141 s | 4.602 / 4.453 GiB | setup target pass；非 accuracy candidate |
| h13 canonical | 19.410 / 6.696 s | 5.030 / 5.016 GiB | setup target pass；非 12-channel candidate |

h15 direct rank study 的最低实测 RSS 是 MPI1 的 1.295 GiB；它推翻了
“5.8–6.4 GiB 是最低内存”的解释，但仍不是理论或 factor-free 下限。
对应 authority 为：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_direct_mpi1_2_4_8_resource_floor_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_memory_floor_factor_inventory_ledger_v2.json`
