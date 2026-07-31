# Task036 Review V3：strong trace-subspace Hybrid 实现结果

## 1. 最终状态

```text
strong_trace_implementation = fixture_pass
formal_anchor = A004-S measured negative
A049-P = not_run_due_to_A004_gate
A001-P = not_run_due_to_A004_gate
M160 = not_authorized
production_candidate = none
ordinary_default = unchanged
next_route = Full3D_static_condensed_iterative
```

实现与小型夹具已经通过；正式 A004-S 则因能量闭合和固定衍射通道未通过而按 Review V3
受控停止。这里的 `fixture_pass` 只说明新方程按设计装配、求解和恢复，不能解读为
Hybrid 已获得 production 资格。

## 2. 改了什么

### 2.1 通俗解释

旧 Hybrid 在上下两个有限元接口上保留全部 trace 自由度，只检查其中 `M` 个模态投影
坐标是否匹配。投影看不到的那部分 trace 仍可在矩阵中自由变化。

新实现不再保留这部分自由 trace。接口电场从一开始就只能由选中的物理波导模态生成：

```text
旧：D_s g_s = L_s a
新：g_s = R_s L_s a
```

- `g_s` 是真实 H(curl) 有限元接口 trace；
- `R_s` 把模态系数延拓成物理 trace；
- `L_s` 负责正、反向模态到该接口的传播；
- `a` 是保留的内部模态振幅；
- `D_s` 只用于验证 `D_s R_s = I`，不再作为旧式弱投影约束。

这样会真正删除 `ker(D_s)` 中的接口补空间，而不是把完整接口矩阵保留后置零。

### 2.2 trial/test space

| 部分 | trial unknown | test row |
|---|---|---|
| 非内部接口 FEM | 原 unknown | 原 FEM row |
| external DtN auxiliary | 原 unknown | 原 DtN row |
| 内部接口 trace | 删除独立 unknown，以 `R_s L_s a` 写入 | 删除原接口 FEM rows |
| 接口磁场/traction 平衡 | 无新增 multiplier | 以 normalized left modes 形成 `W_s^H residual = 0` |
| 中间传播区 | `2M` 个正、反向模态振幅 | `2M` 个方形 Petrov rows |

lossy、非自伴问题中 `W_s` 与 `R_s` 不相同。实现通过
`W_raw @ G^{-H}` 归一化 left columns，并用 `W_s^H` 装配 Petrov row；没有把
left test 偷换成 right trial 的共轭转置。

### 2.3 明确没有做的事

| 禁止项 | 实现结果 |
|---|---|
| 在旧 projection-only monolithic matrix 上打补丁 | 未使用 |
| penalty / Nitsche complement suppression | 未使用 |
| 显式 `R_s D_s` 或 `I-R_sD_s` | 未形成 |
| 全维 Lagrange multiplier | 未加入 |
| dense `N_gamma × N_gamma` interface square | 未形成 |
| 保留完整 trace 再把 complement 系数设零 | 未使用 |
| 静默替换普通 Hybrid 默认路径 | 未修改 |

`trace_complement_unknown_count` 在 dense fixture、standard fixture、static fixture 和
A004-S 正式运行中均为 `0`。

## 3. 实现结构

### 3.1 新数值核心

`src/solvers/hybrid_strong_trace_direct.py` 提供：

- `HybridStrongTraceInterfaceMap`：按实际 backend 建立接口行、保留行、`R_s` 和
  normalized `W_s`；
- `HybridStrongTraceLayout`：按 MPI ownership 生成方形 reduced layout；
- `build_hybrid_strong_trace_direct_system()`：直接装配 Petrov–Galerkin reduced system；
- `solve_hybrid_strong_trace_direct()`：MUMPS 求解、`R_sL_sa` trace 写回和四分量残差；
- `recover_hybrid_strong_trace_static_fields()`：先释放全局 factor，再恢复 cell interior；
- `evaluate_hybrid_strong_trace_solution()`：复用正式 R/T/A 和逐衍射级后处理。

没有复制 QEP、DtN、static-condensation 或 runner 主体。

### 3.2 standard/static backend-native row map

小型 MPI fixture 的实测映射如下：

| backend | local rows/side | original interface rows | independent interface rows | retained rows/side | removed slave rows/side | strong square rows |
|---|---:|---:|---:|---:|---:|---:|
| standard | 470 | 58 | 48 | 328 | 94 | 660 |
| assembly-time static | 304 | 58 | 48 | 256 | 0 | 516 |

static 路径使用 condensed active row identity，不把 full FE DoF id 当作 reduced row。
两种路径都：

- 使用 `PETSc.IntType=int32`；
- 保留 external DtN auxiliary rows；
- 不让 Floquet slave 重新成为独立 row；
- 检查 geometry row set 与 algebra row set 无缺失、无重复；
- 精确满足 `N = retained_bottom + retained_top + 2M`。

A004-S 的正式 static map 为：

```text
bottom original interface rows = 1250
top original interface rows    = 1250
bottom independent g_b         = 1200
top independent g_t            = 1200
retained rows per side          = 6528
modal rows                      = 240
strong square rows              = 6528 + 6528 + 240 = 13296
```

bottom/top geometry projection support 均实测为 `true`。

## 4. field recovery 与对象生命周期

求解后直接计算：

```text
bottom trace = R_bottom L_bottom a
top trace    = R_top    L_top    a
```

这两个 trace 被写入各自的 local carrier，再恢复 static-condensed cell-interior modes。
不会从旧 projection-only carrier 恢复出新的自由 complement。

正式 A004-S 生命周期为：

```text
strong monolithic factor/solution
-> 提取 retained local fields 与 modal amplitudes
-> 销毁 KSP/MUMPS factor 和 monolithic carrier
-> bottom/top static recovery
-> physical fields / port / volume postprocess
```

fixture 与正式 record 都确认：

```text
solver_release_before_field_output = true
full_global_matrix_allocated_for_recovery = false
full_trace_matrix_allocated_for_recovery = false
```

## 5. true residual 的四分量

新系统不再要求已被替换的全部接口 FE rows 为零。正式残差分为：

| 分量 | 含义 | Gate |
|---|---|---:|
| noninterface FE | 仍被保留的局部 FEM 方程 | `<=1e-9` |
| modal Petrov flux | `W_s^H(local residual + modal traction)` | `<=1e-8` |
| strong trace identity | `||g_s-R_sL_sa||` | `<=1e-10` |
| external DtN | 外端口 auxiliary 方程 | `<=1e-9` |

被删除的接口 FE rows仍作为 `raw_replaced_interface_fe_residual` 诊断保存，但不再冒充
新系统方程。

### 5.1 A004-S 暴露的齐次分区归一化缺陷

首个正式 artifact 中有两个约 `1e-12` 的舍入级绝对残差被错误除以自身，因而报告为
`formal_relative=1`：

| 分区 | absolute | 旧 formal relative | relative/global |
|---|---:|---:|---:|
| bottom noninterface | `1.6767e-12` | `1.0` | `1.2173e-11` |
| top external DtN | `1.1215e-12` | `1.0` | `1.3713e-12` |

根因是齐次分区没有独立的局部 RHS/traction 尺度；`A x` 本身就是待测 residual，不能
同时拿它作分母。提交
`a5b86a319af3cfc88d5de5801f2e8131f89a9be4` 改为：

- 有可分辨 local RHS/traction 的分区继续使用严格局部尺度；
- 齐次分区使用全局方程尺度；
- 原始 partition-relative 值仍作为 diagnostic 保留；
- `1e-9` Gate 没有放宽。

该修复只改变 residual telemetry，不改变 A004-S 的矩阵、解、场、R/T/A 或资源结果。
因此没有重跑 PDE；原始 artifact 保持不动，修正后的两个正式值由现有 raw 字段离线得到。

## 6. fixture 结果

### 6.1 dense lossy Petrov fixture

| 指标 | 实测 |
|---|---:|
| `D R - I` | `1.108e-14` |
| noninterface residual | `1.386e-15` |
| Petrov residual | `8.968e-16` |
| trace identity | `2.086e-16` |
| 非零 complement probe norm | `3.271` |
| `D q` | `2.704e-15` |
| reduced shape | `5 × 5` |
| complement unknown | `0` |
| dense interface square | `false` |

### 6.2 H(curl)/Floquet physical micro-fixture

- 同时包含 S mode 与带非零 `E_z` 的 P mode；
- P mode 的接口只取 H(curl) tangential trace；
- bottom/top local outward normal 分别为 `+z/-z`；
- 非平凡 Floquet phase 为
  `-0.6007411349 - 0.7994436120i`；
- 27 个 slave edges、10 个 slave faces 均一一匹配；
- corner phase、face transform 和 recovered field constraint residual 均为 `0`；
- Petrov-left 与 right prolongation 明确不同；
- standard/static modal amplitude 相对差为 `1.759e-14`；
- standard/static 的 R、T、A_balance 差均不超过 `2.23e-16`；
- static factor 在 recovery 前已释放。

compact record：
[strong_trace_exact_fixture_v1.json](../../../benchmarks/cases/099_strong_trace_hybrid_fixture/records/strong_trace_exact_fixture_v1.json)。

### 6.3 测试

| 测试 | 结果 |
|---|---|
| serial `test_199` | `6 passed` |
| MPI2 `test_199` | 每 rank `6 passed` |
| MPI8 `test_199` | 每 rank `6 passed` |
| affected serial suite（实现提交） | `40 passed` |
| broad related suite（实现提交） | `159 passed` |
| Ruff | pass |
| compileall | pass |
| `git diff --check` | pass |

`159 passed` 的 broad suite 在实现提交后运行；随后只有 residual telemetry 的局部修复，
最终源码又完成 serial/MPI2/MPI8 targeted rerun、Ruff、compileall 和 diff-check，没有
因这一纯报告修复重复运行约 35 分钟的无关历史 suite。

## 7. 修改文件

数值实现提交 `5b04a4398fe752083024487ca95eb00a09e646cc`：

- `src/solvers/hybrid_strong_trace_direct.py`
- `src/coupling/hybrid_internal_modes.py`
- `benchmarks/run_task032_phase6_augmented.py`
- `benchmarks/run_task033_memory_watchdog.py`
- `benchmarks/task035c_p6_h10_gates.py`
- `src/test/test_199_task036_strong_trace_hybrid.py`
- `src/test/test_181_task035c_p6_h10_runner_gates.py`
- `src/test/test_59_task033_memory_watchdog_contract.py`

telemetry 修复提交 `a5b86a319af3cfc88d5de5801f2e8131f89a9be4`：

- `src/solvers/hybrid_strong_trace_direct.py`
- `src/test/test_199_task036_strong_trace_hybrid.py`

ordinary Hybrid solver path、ordinary default 和 `master` 均未修改。

## 8. 能力边界

```text
strong_trace algebra / row map / recovery = pass
formal p5/h10/M120 physical qualification = fail
production promotion = forbidden
```

A004-S 已证明 strong restriction 能消除自由 trace complement，并保留约 25% 的 Full3D
峰值内存优势；但它没有修复已有的能量和固定衍射通道误差。历史 M240 也没有改善同一
能量缺口。只读算子审计没有发现可在本轮内修复的局部法向、共轭、traction beta、端口
功率或体吸收错误。

现有证据更指向低掠射 45° 下“逐模态、对角的 scalar-CG 轴向传播”不能重现 Full3D 的
cross-interface coefficient map。修复需要 matrix-valued axial propagation 或
Full3D-derived modal Schur，属于新的数值架构，不是 Task036 BUGFIX_ONLY 中的最小修补。
因此按 Review V3 fail closed，下一生产路线固定为 Full3D assembly-time static
condensation + iterative solver；本轮不开始该实现。
