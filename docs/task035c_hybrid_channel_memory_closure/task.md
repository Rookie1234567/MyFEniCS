# Task035c：Hybrid 逐通道精度与静态凝聚内存闭合

## 1. 上位权威

本任务的完整范围、诊断顺序、模型矩阵、成功 Gate 和停止规则由以下文件确定：

```text
docs/task035b_high_order_local_hp_resource_envelope/review_report_v4.md
```

Codex 开始前必须完整阅读：

- 根目录 `AGENTS.md`；
- `docs/AGENTS.md`；
- Task032/033 的最终 Hybrid summary/review；
- Task035b `review_report_v4.md`；
- Task035b `response_v5.md`；
- Task035b `outcomes/hybrid_static_condensation_h1.md`；
- Task035b `outcomes/summary.md`；
- `docs/development_model_registry.md`；
- Case095 README 与 `hybrid_static_condensation_h1a_mpi8_v1.json`。

## 2. 任务目标

只解决两个问题：

1. 定位并修复 Full3D 与 Hybrid 在12个显著衍射级功率和复振幅上的误差；
2. 解释并修复 static Hybrid 减少 rows/NNZ 但不降低峰值内存、且 modal coupling 明显变慢的问题。

不得用更大的 M、更多参数扫描或更重模型替代根因分析。

## 3. 强制模型

### Model A：p2/h5

用于低成本逐组件诊断，至少保留：

```text
Full3D standard
Full3D static
Hybrid standard M120/M160
Hybrid static M120/M160
```

### Model B：p3/h7.5

作为已有高阶等精度证据的强制 authority，重新执行同样四路比较，并使用本任务严格的12通道功率和12通道复振幅 Gate。

`p3/h7.5` 不是 continuum truth；需要同时对照 p6/h10/reference-v1 趋势。

### Conditional Model C

只有 p3/h7.5 已给出明确根因且资源预估安全时，才允许增加 p6/global-p 诊断点。

## 4. 执行顺序

1. 冻结 Full3D/Hybrid 完全相同的几何、材料、Floquet、DtN、入射场、reference plane、通道 indexing 和 normalization；
2. 证明 Full3D 与 Hybrid 恢复场使用同一个逐通道后处理；
3. 审计 QEP beta、mode shape、biorthogonality、flux normalization、forward/backward pairing 和传播相位；
4. 完成 Full3D interface trace 的 modal projection/reconstruction 与 oracle propagation；
5. 使用 channel adjoint/response matrix 定位失败通道的敏感接口模态和相位；
6. 建立 standard/static Hybrid 同时峰值对象账本；
7. 审计 cell-interior tangential trace 及 interior-to-modal coupling 是否理论上应为零；
8. 仅对数学上必要的 modal correction 做 classwise/batched、blocked/streamed 和生命周期优化；
9. 先通过 p2/h5 诊断闭环，再运行 p3/h7.5 正式 authority。

## 5. 精度成功 Gate

p3/h7.5 必须同时通过：

- standard Full3D ↔ static Full3D：12/12 powers + 12/12 amplitudes；
- standard Hybrid ↔ static Hybrid：12/12 + 12/12；
- corrected Full3D ↔ corrected Hybrid：12/12 + 12/12；
- R/T/A、Avolume、energy closure、full explicit residual；
- interface E/H 和 selected field planes；
- M120→M160；只有证据需要时才进入 M240。

不得放宽 Task035b reference-v1 tolerance。

p2/h5 必须 either：

- 修复后达到12/12 + 12/12；或
- 以跨 modal mesh/p 的定量收敛证明当前 basis 未解析，并在 independently converged modal basis 上达到12/12 + 12/12。

## 6. 内存与时间成功 Gate

以 p3/h7.5 为主要资源 authority，同物理、p/h/M、MPI和输出合同下：

```text
mandatory static-Hybrid peak reduction >= 15%
preferred static-Hybrid peak reduction >= 25%
modal-coupling time <= 1.25x standard
total time <= 1.35x standard
```

同时要求：

- rows、matrix NNZ 和 factor NNZ 有可测下降；
- fill 的变化有解释且不再抵消收益；
- 无长期 `N_FE × M` dense payload；
- 报告 RSS/PSS/USS/cgroup/swap 和峰值对象共存；
- ordinary default 仍为 `standard_full`。

## 7. 非目标

本任务不开展：

- h13 Hybrid h/p 自适应；
- 0.7 nm 资源外推；
- irregular geometry；
- tetra/mixed static condensation；
- production selective trace；
- 新 condensed iterative profile。

只有 Task035c 同时完成逐通道精度和内存闭合后，才重新开放上述后续工作。

## 8. 交付

必须维护：

- `outcomes/summary.md`；
- `outcomes/test_summary.md`；
- 根因诊断、对象生命周期和模型对照表；
- compact hash-bound records；
- `response_vN.md`；
- `docs/development_model_registry.md` 的 Task035c 条目。

一次只运行一个 heavy PDE。负结果、首次失败和未运行 Gate 必须保留。遇到源码身份、ABI、数值 Gate、资源 Gate 或依赖异常时停止并报告。
