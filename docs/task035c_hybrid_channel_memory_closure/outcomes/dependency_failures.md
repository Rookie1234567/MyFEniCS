# Task035c 依赖失败与受控负证据

## 1. 为什么保留这些失败

这些记录区分了三种完全不同的问题：

1. 高阶约束能力原本只资格化到p4；
2. 理论为零的trace投影在p6出现接近机器精度的roundoff；
3. worker退出时的资源采样竞态。

后续成功不能把它们删除或改写为“从未失败”。它们分别约束高阶API、
fail-closed数值审计和资源authority的适用边界。

## 2. 失败、实际值、修复和authority

| ID | source / record | 实际失败 | 原因 | 修复 / superseding authority | 状态 |
|---|---|---|---|---|---|
| D1 | `c30fad7` standard M120 | `ValueError: ... p=1..4` | cross-section Floquet entity-DoF映射只硬编码Task033 p1–p4 | Basix quadrilateral entity_dofs + interval transforms；serial/MPI2/MPI8 p1–p6 tests | preserved capability failure |
| D2 | `b40644b` static M120 | eliminated interior/slave最大 `1.187e-12 > 1e-12` | 固定absolute cutoff把p6浮点累积误判为物理泄漏 | 引入active-scale-aware interior audit | preserved controlled negative |
| D3 | `eb8bf3b` static M160 | max `1.078e-12`，cutoff `1.032e-12`，active scale `9.075`；slave为0 | 512 eps比例仍略低于合法舍入 | slave保持strict `1e-12`；interior使用`max(1e-12,1024 eps × active scale)` | preserved controlled negative |
| D4 | `244b62e` static M120 first launch | 无solver record；`terminated_for_authority_unreadable=true` | MPI launcher/startup无可读worker authority | 同source unbuffered controlled retry `...retry1.json` formal pass | preserved dependency/launcher negative |
| D5 | MPI1 static Hybrid M120 | positive biorthogonality `1.1975997613e-6 > 1e-6`；negative `7.5248182035e-7` | rank-sensitive high-order QEP identity误差 | 不放宽Gate；记录为数值负结果 | rank lane negative |
| D6 | MPI2 static Hybrid M120 | numerical pass；末端 `job_swap_all_samples_readable=false`、drain excluded=0 | worker退出与launcher drain采样竞态 | 不追溯提升；MPI8保留为formal authority | resource-authority negative |

## 3. Roundoff审计为什么没有放宽真实泄漏Gate

active-trace projection中的两类“应为零”分量物理意义不同：

- Floquet slave entry若非零，说明周期owner消元可能错误，因此保持严格absolute
  `1e-12`；
- cell-interior entry来自分布式浮点装配和正交投影，合法舍入会随active vector
  量级增长，因此允许机器精度比例。

最终审计仍对以下情况立即失败：

```text
non-finite value
true slave leakage > 1e-12
interior leakage > max(1e-12, 1024 * eps * global_active_scale)
```

所以这不是把p6 failure“调大阈值直到通过”，而是把两类物理条件分开度量。
serial fixture和真实MPI2 cross-rank scale测试覆盖了这一语义。

## 4. Checker的两个证据合同修复

它们不改变PDE数值：

| 项目 | 旧行为 | 修复 |
|---|---|---|
| Full3D reference SHA | 错从watchdog launch顶层查找 | 读取`launch_gate.matching_full3d_reference.expected_sha256/observed_sha256` |
| complex amplitude | 使用未映射到physical boundary plane的`outgoing_amplitude` | 使用reference-v1冻结的`outgoing_amplitude_at_boundary` |

旧字段会把纯reference-plane传播相位错误地算成Hybrid误差。本轮修复保持12通道、
`1e-8` significance floor和`1e-3` relative tolerance不变，并在缺字段时
fail closed。

## 5. Evidence

- `benchmarks/cases/096_hybrid_channel_memory_closure/records/dependency_failures_v1.json`
- `benchmarks/cases/096_hybrid_channel_memory_closure/records/execution_ledger_v1.json`
- `benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_hybrid_standard_m120_mpi8_c30fad7.json`
- `benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_hybrid_static_m120_mpi8_b40644b.json`
- `benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_hybrid_static_m160_mpi8_eb8bf3b.json`
- `benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_hybrid_static_m120_mpi8_244b62e.json`
- `benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_hybrid_static_m120_mpi1_244b62e.json`
- `benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_hybrid_static_m120_mpi2_244b62e.json`

原始stdout/timeline位于ignored artifact目录。tracked compact record只保存
hash、失败字段和分类，不复制大型输出。
