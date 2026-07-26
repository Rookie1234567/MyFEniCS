# Task035b Review V4：任务闭合与 Task035c Hybrid 精度/内存专项授权

> 本版已按用户最新决定修订：Task035c 不再运行 `p3/h7.5`，强制高阶模型改为 `p6/h10`。

## 1. 审阅结论

```text
review_status = TASK035B_CLOSED_WITH_CONTROLLED_NEGATIVES
reviewed_branch = codex/20260726-task35b-high-order-local-hp-resource-envelope
reviewed_response = response_v5.md
reviewed_numerical_source = 148729c28c3f9aefec8e5646cc644c5c4e2332da
master_baseline = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
Task035b_completion = complete_by_scope_and_stop_rules
Task035b_final_scientific_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
Task035b_second_master_merge = not_authorized
Task035c = authorized
Task035c_branch = codex/20260726-task35c-hybrid-channel-memory-closure
Task035c_scope = Hybrid channel accuracy root cause + static-Hybrid memory/time closure
Task035c_mandatory_models = p2/h5 + p6/h10
p3_h7p5 = not_in_Task035c_scope
ordinary_default_changed = false
```

Task035b 可以闭合。

这里的“闭合”不表示 Task035b 找到了满足全部目标的最终自适应模型，而是表示：

1. 高阶 p/h、静态凝聚、资源包络、setup/cache、direct rank study、迭代筛选、Hybrid 接入和停止规则均已执行到可审查终点；
2. 正结果、负结果、未运行项和能力边界均有正式 evidence；
3. H1-A 已把剩余问题分解为两个独立问题；
4. 继续在 Task035b 中叠加更重模型，只会把尚未解释的 Hybrid 误差和资源瓶颈带入下一层，不能提高结论可信度。

Task035b 的最终身份为：

```text
高阶与静态凝聚基础设施：成功
预算内 same-error h/p 最终候选：未获得
static Hybrid 代数实现：成功
Full3D–Hybrid 严格逐通道闭合：失败，原因未定位
static Hybrid 内存/时间收益：未获得
任务执行：按 Gate 正确停止并闭合
```

剩余两项拆分为 Task035c：

- 为什么 Full3D 和 Hybrid 在总 R/T/A、残差和场范数接近时，弱衍射级功率与复振幅仍有显著误差；
- 为什么 Hybrid 减少了 rows 和 matrix NNZ，峰值内存却没有下降，时间反而接近翻倍，以及怎样真正把内存降下来。

---

## 2. Task035b 已达到可闭合状态

### 2.1 已进入 master 的主线能力

Task035/035b 已完成文件级选择性合并：

```text
master = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
```

已进入 master 的主要能力包括：

- 原始完整矩阵 direct 路径，ordinary default 不变；
- 统一用户端口 `standard_full / assembly_time_static_condensed`；
- p5/p6 Nédélec、高阶 orientation、双 Floquet 与 MPI identity；
- Full3D assembly-time cell-interior static condensation；
- Floquet slave 在全局插入前消除；
- 完整场恢复、full explicit residual 和正式 R/T/A/衍射级；
- tensor/class reuse、exact preallocation、bulk insertion、cold/warm cache；
- periodic tetra、DWR 和 p5/p6 research-grade 基础设施；
- 模型总账、Case094/095 精简权威 evidence 和治理规则。

### 2.2 最强预算内 h/p 候选仍是受控负结果

```text
fixed p5 trace + p6 cell interior
directional-z h13
Full3D-equivalent DoF = 89,740
active rows = 20,120
significant powers = 10/12
significant complex amplitudes = 10/12
```

未通过：

```text
T(-4,0) power
R(-4,0) power
r(-4,0)
r(-5,0)
```

后续固定 DoF 的 z-node 判别继续退化；selective p6 trace 尚无正式 PDE；部分 regionwise/inverse p 空间存在 exact-sequence 失败。因此 Task035b 没有得到 12/12 + 12/12 的最终候选，但已经形成可信的负结论。

### 2.3 static Hybrid 的代数实现已经证明正确

H0 已证明：

- Full3D standard ↔ Full3D static：12/12 功率、12/12 复振幅等价；
- Hybrid standard ↔ Hybrid static：M120、M160 均为 12/12 + 12/12；
- static Hybrid M120→M160：12/12 + 12/12 收敛；
- full operator residual、被消去 interior 方程残差和完整场恢复均通过。

这说明当前问题不是静态凝聚把方程做错了。

### 2.4 新暴露的 Hybrid 逐通道问题

同一 p2/h5 离散下：

```text
static Full3D vs static Hybrid M160
Task033 relative gate = 3/12 powers + 2/12 amplitudes
strict absolute gate = 2/12 powers + 2/12 amplitudes
```

M120 增至 M160 后几乎不变，不能简单归因于 M 不足。总 R/T/A、残差和场范数接近，也不能覆盖多个 `10^-6`–`10^-8` 量级弱通道的相位和功率误差。

### 2.5 新暴露的 static Hybrid 资源问题

p2/h5 Hybrid M160：

| metric | standard | static | change |
|---|---:|---:|---:|
| total rows | 14,052 | 10,000 | -28.84% |
| local matrix NNZ pair | 1,454,248 | 976,400 | -32.86% |
| factor NNZ pair | 6,390,216 | 5,986,184 | -6.32% |
| factor fill | 4.394 | 6.131 | +39.52% |
| process-tree peak | 3.285 GiB | 3.308 GiB | +0.71% |
| total time | 96.28 s | 186.36 s | +93.56% |
| internal modal coupling | 11.72 s | 110.62 s | +843.7% |

当前瓶颈不是 MUMPS，而是 static left/right modal correction 及其与 local Schur、recovery、QEP/mode 和 coupling 数据的生命周期重叠。

---

# 3. Task035c 正式授权

## 3.1 任务与分支

```text
Task035c：Hybrid significant-channel accuracy and static-condensation memory closure
branch = codex/20260726-task35c-hybrid-channel-memory-closure
```

Task035c 直接依赖尚未进入 master 的 H0 static-Hybrid 实现，所以从包含本 Review 的 Task035b 最终提交继续。Task035b 分支在本 Review 后冻结。

独立目录：

```text
docs/task035c_hybrid_channel_memory_closure/
```

必须维护 `README.md`、`task.md`、`outcomes/summary.md`、`outcomes/test_summary.md`、compact records、`response_vN.md` 和模型总账 Task035c 条目。

## 3.2 Task035c 只解决两个问题

### 问题 A：Hybrid 逐衍射级精度

必须区分并量化：

- Full3D/Hybrid 物理与后处理合同是否完全相同；
- modal cross-section 离散误差；
- QEP 特征值和特征向量的物理误差；
- biorthogonal/flux normalization；
- matching-trace projection；
- 中间段传播相位；
- forward/backward pairing；
- interface E/H 传递；
- Rayleigh/Fourier 后处理、参考平面和相位原点。

### 问题 B：static Hybrid 内存和时间

必须解释并修复：

- rows/NNZ 已减少约 30%，factor 只减少约 6%；
- fill 增长约 40%；
- 峰值内存不降；
- internal modal coupling 慢约 9.4 倍。

目标是在同物理精度下真正降低 simultaneous peak memory，并把额外耦合时间压到合理范围。

Task035c 不开展 h13 Hybrid 自适应、0.7 nm 外推、不规则几何、tetra/mixed static condensation、production selective trace 或新的 condensed iterative profile。

---

# 4. 强制模型

## 4.1 Model A：p2/h5 诊断模型

用途：低成本逐组件复现和隔离当前误差，不作为最终高阶 authority。

必须保留：

```text
Full3D standard
Full3D static
Hybrid standard M120/M160
Hybrid static M120/M160
```

## 4.2 Model B：p6/h10 强制高阶 authority

Task035c 不再计算 `p3/h7.5`。强制高阶模型改为：

```text
Full3D standard p6/h10
Full3D static p6/h10
Hybrid standard p6/h10 M120/M160
Hybrid static p6/h10 M120/M160
```

`p6/h10` 是当前 FEniCS 的 best available global-p discrete reference，并与 COMSOL p4–p6 高阶趋势接近。它仍不是 continuum truth，但比 p3/h7.5 更适合作为本任务的逐通道精度与资源 authority。

最终相关代码修改后必须在同一 final source 上重新运行必要 anchor，不能只引用旧总量。历史 p6/h10 记录可用于资源预估和启动 Gate，不替代最终逐通道闭合。

### 4.2.1 p6/h10 资源预检

历史 authority 显示：

- full-matrix p6/h10 峰值约 35 GiB；
- assembly-time static p6/h10 独立峰值约 16 GiB；
- 最新投影/预分配批次约 20 GiB。

因此 p6/h10 是强制模型，但每条重型路径仍需先做 rows/NNZ/factor/peak 预估、一次只运行一个 heavy case，并保留 watchdog。只有新的安全预测超过明确硬上限时才允许受控停止，不能用一般性的“可能较重”跳过该模型。

## 4.3 不再设置独立的条件 p6 模型

旧版的“条件 Model C：p6/global-p”已删除，因为 p6/h10 现在就是强制 Model B。只有在 p6/h10 内部诊断明确需要时，才允许增加：

- M240；
- 更细的 modal cross-section mesh；
- 更高的 modal basis order；
- 同一 p6/h10 物理下的 oracle/phase 隔离点。

不得再用 p3/h7.5 替代 p6/h10 completion Gate。

---

# 5. Hybrid 精度根因诊断顺序

## 5.1 P0：冻结完全相同的比较合同

逐项 hash-bound：几何、材料、波长、角度、偏振、Floquet、DtN order set、incident/reference field、port normalization、衍射级 indexing、reference plane、传播相位、功率归一化、复振幅 convention 和 MPI-independent identity。

发现不一致时先修复合同，不能解释为 Hybrid 近似误差。

## 5.2 P1：统一逐通道后处理

必须证明 Full3D 与 Hybrid 恢复场在同一物理平面调用同一 Rayleigh/Fourier 后处理，并使用相同 basis、normalization、phase origin 和 flux。改变参考平面只能产生可预测相位，不能改变功率。

## 5.3 P2：QEP 与 modal basis 的物理误差

M120→M160 稳定只说明当前离散 basis 内截断稳定，不说明 basis 本身准确。必须报告：

- QEP polynomial residual；
- beta 跨 modal mesh/p 的收敛；
- biorthogonality 和 flux normalization；
- forward/backward pairing 与 mode tracking；
- interface trace completeness；
- p2/h5 与 p6/h10 的 beta、mode shape 和传播相位差。

重点检查：

```text
phase error ≈ Δbeta × middle_length
```

## 5.4 P3：interface projection 与 oracle 实验

至少完成：

1. Full3D interface trace → modal projection/reconstruction；
2. Full3D interface trace → modal propagation → 同一通道后处理；
3. Hybrid interface trace → Full3D-compatible reconstruction。

借此区分接口解、modal basis、传播和输出投影误差。

## 5.5 P4：channel-sensitive diagnosis

对主要失败通道使用已有 channel adjoint/response-matrix 基础设施，定位敏感 interface modes、beta/phase、trace components、local side 和后处理投影。不得只继续提高 M。

---

# 6. static Hybrid 内存与时间根因

## 6.1 M0：同时峰值对象账本

对 p2/h5 和 p6/h10 的 standard/static Hybrid 分阶段记录：

- mesh/function-space；
- raw local tensors；
- `Aii` LU；
- local Schur/recovery；
- external DtN；
- modal right/left vectors；
- interface projection；
- left/right modal correction；
- Hybrid matrix；
- MUMPS factor；
- field recovery 与 postprocess。

同时报告 process-tree RSS、rank PSS/USS、cgroup、swap、NumPy retained bytes 和 PETSc matrix/factor inventory，并指出峰值时刻共存对象。

## 6.2 M1：审计 interior-to-modal coupling

H(curl) cell-interior basis 的切向 trace 理论上应在 cell boundary 上为零。必须审计：

```text
B_i = interior-to-modal coupling
C_i = modal-to-interior coupling
```

若纯界面耦合下理论上应为零，则证明数值接近零并删除无意义 correction。若 volume lifting 使其非零，则写清弱式来源，证明必要性，并与纯 trace formulation 做等价测试。

## 6.3 M2：优化数学上必要的 modal correction

优先使用 classwise/batched 计算、一次 LU 多 RHS、M 分块 streaming、factorized/low-rank coupling、共享 modal/projection cache、避免 Python 逐 cell/逐 mode 小循环，并缩短 raw tensor、QEP workspace、local factors 和 recovery cache 的存活区间。

不得长期形成 `N_FE × M` dense payload。

## 6.4 M3：rank 与生命周期

p6/h10 至少比较 MPI1/2/4/8 中合理的两个或三个点。Hybrid 全局系统较小，过多 rank 的进程复制可能抵消凝聚收益；不得默认 MPI8 是最低内存点。

---

# 7. Task035c 成功 Gate

## 7.1 p2/h5 诊断 Gate

必须做到以下之一：

1. 修复后 Full3D ↔ Hybrid 达到 12/12 powers + 12/12 amplitudes；或
2. 定量证明 p2/h5 modal cross-section 未解析，并在 independently converged modal basis 上达到 12/12 + 12/12。

不能只写“p2/h5 太粗”。

## 7.2 p6/h10 高阶精度 Gate

同一 p/h/M 和 final source 下必须通过：

- standard Full3D ↔ static Full3D：12/12 + 12/12；
- standard Hybrid ↔ static Hybrid：12/12 + 12/12；
- corrected Full3D ↔ corrected Hybrid：12/12 + 12/12；
- Rtotal/Ttotal/Aclosure/Avolume；
- full explicit residual；
- interface E/H；
- selected field planes；
- M120→M160；只有证据需要时进入 M240。

不得放宽 Task035b reference-v1 tolerance。

## 7.3 p6/h10 内存与时间 Gate

p6/h10 是主要资源 authority。在相同物理、p/h/M、MPI和输出合同下：

```text
mandatory static-Hybrid peak reduction >= 15%
preferred static-Hybrid peak reduction >= 25%
modal-coupling time <= 1.25x standard
total time <= 1.35x standard
```

同时要求 rows、matrix NNZ 和 factor NNZ 有可测下降；fill 不得无解释恶化；不保留 full `N_FE × M` dense payload；无 swap 或按 watchdog 受控停止。

若 p2/h5 因固定开销收益不明显，但 p6/h10 达到上述 Gate，可以判定高阶 Hybrid 内存成功，但必须保留并解释低阶结果。

## 7.4 最终分类

只有精度和内存 Gate 同时通过，才允许：

```text
Task035c = HYBRID_CHANNEL_AND_MEMORY_CLOSURE_SUCCESS
```

只定位根因未修复：`PARTIAL_ROOT_CAUSE_IDENTIFIED`。

精度成功但资源失败：`PHYSICS_SUCCESS_RESOURCE_NEGATIVE`。

只降内存但逐通道失败仍为失败，不得进入 h13 adaptive Hybrid。

---

# 8. 后续关系与合并

只有 Task035c 完整成功后，才重新开放：

- fixed p5-trace + p6-interior directional-z h13 Hybrid；
- Hybrid h/p 自适应；
- 0.7 nm / 2 TiB resource model v3；
- static Hybrid 的第二次 master 选择性合并审查。

当前 Task035b H0/H1-A 不批准第二次 merge master。Task035c 完成后统一审查 Hybrid 精度修复、资源优化和是否选择性合并。ordinary default 始终为 `standard_full`。

---

## 9. 最终决定

```text
Task035b = CLOSED_WITH_CONTROLLED_NEGATIVES
Task035b reusable high-order/static-condensation infrastructure = yes
Task035b final same-error hp candidate = no
Task035b physically qualified memory-saving static Hybrid = no
Task035c = AUTHORIZED
Task035c mandatory models = p2/h5 + p6/h10
p3/h7.5 = removed from Task035c
Task035c primary completion gate = 12-channel physics + measured p6/h10 memory reduction
```

Codex 读取本 Review 后，在 Task035c 分支连续执行。任何 heavy PDE 前先完成物理身份、后处理身份、QEP/trace 诊断和内存对象账本；不得用更大的 M、p3/h7.5 或 h13 参数扫描替代根因分析。