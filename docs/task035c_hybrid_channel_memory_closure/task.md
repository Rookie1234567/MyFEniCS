# Task035c：Hybrid 逐通道精度与静态凝聚内存闭合

## 1. 上位权威

完整范围、诊断顺序、成功 Gate 和停止规则由以下文件确定：

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

1. 定位并修复 Full3D 与 Hybrid 在 12 个显著衍射级功率和复振幅上的误差；
2. 解释并修复 static Hybrid 减少 rows/NNZ 但不降低峰值内存、且 modal coupling 明显变慢的问题。

不得用更大的 M、参数盲扫或 h13 自适应替代根因分析。

## 3. 强制模型

### Model A：p2/h5

用于低成本逐组件诊断：

```text
Full3D standard
Full3D static
Hybrid standard M120/M160
Hybrid static M120/M160
```

### Model B：p6/h10

Task035c 不计算 `p3/h7.5`。强制高阶 authority 为：

```text
Full3D standard p6/h10
Full3D static p6/h10
Hybrid standard p6/h10 M120/M160
Hybrid static p6/h10 M120/M160
```

`p6/h10` 是当前 FEniCS best available global-p discrete reference，并与 COMSOL 高阶趋势接近，但仍不是 continuum truth。最终相关修改后，必须在同一 final source 上重新运行必要 anchor。

历史 p6/h10 资源记录只用于预检：full-matrix 峰值约 35 GiB，assembly-time static 约 16–20 GiB。p6/h10 是强制模型，不能仅以“模型较重”为由跳过；一次只运行一个 heavy case并启用 watchdog。

旧版条件 p6 Model C 已取消。只有 p6/h10 诊断明确需要时，才允许增加 M240、modal cross-section 加密或更高 modal basis order。

## 4. 执行顺序

1. 冻结 Full3D/Hybrid 完全相同的几何、材料、Floquet、DtN、入射场、reference plane、通道 indexing 和 normalization；
2. 证明 Full3D 与 Hybrid 恢复场使用同一个逐通道后处理；
3. 审计 QEP beta、mode shape、biorthogonality、flux normalization、forward/backward pairing 和传播相位；
4. 完成 Full3D interface trace 的 modal projection/reconstruction 与 oracle propagation；
5. 使用 channel adjoint/response matrix 定位失败通道的敏感接口模态和相位；
6. 建立 standard/static Hybrid 同时峰值对象账本；
7. 审计 cell-interior tangential trace 及 interior-to-modal coupling 是否理论上应为零；
8. 仅对数学上必要的 modal correction 做 classwise/batched、blocked/streamed 和生命周期优化；
9. 先完成 p2/h5 根因闭环，再运行 p6/h10 正式精度与资源 authority。

## 5. 精度 Gate

p2/h5 必须做到以下之一：

- 修复后达到 12/12 powers + 12/12 amplitudes；或
- 以 modal mesh/p 的定量收敛证明原 basis 未解析，并在独立收敛 basis 上达到 12/12 + 12/12。

p6/h10 必须在同一 p/h/M 与 final source 下通过：

- standard Full3D ↔ static Full3D：12/12 + 12/12；
- standard Hybrid ↔ static Hybrid：12/12 + 12/12；
- corrected Full3D ↔ corrected Hybrid：12/12 + 12/12；
- R/T/A、Avolume、energy closure、full explicit residual；
- interface E/H 和 selected field planes；
- M120→M160；只有证据需要时进入 M240。

不得放宽 Task035b reference-v1 tolerance。

## 6. 内存与时间 Gate

以 p6/h10 为主要资源 authority，同物理、p/h/M、MPI和输出合同下：

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
- 至少比较合理的两个或三个 MPI 规模；
- ordinary default 仍为 `standard_full`。

## 7. 非目标

本任务不开展：

- `p3/h7.5`；
- h13 Hybrid h/p 自适应；
- 0.7 nm 资源外推；
- irregular geometry；
- tetra/mixed static condensation；
- production selective trace；
- 新 condensed iterative profile。

只有 Task035c 同时完成逐通道精度和 p6/h10 内存闭合后，才重新开放后续自适应研究。

## 8. 交付

必须维护：

- `README.md`；
- `outcomes/summary.md`；
- `outcomes/test_summary.md`；
- 根因诊断、对象生命周期和模型对照表；
- compact hash-bound records；
- `response_vN.md`；
- `docs/development_model_registry.md` 的 Task035c 条目。

一次只运行一个 heavy PDE。负结果、首次失败和未运行 Gate 必须保留。遇到源码身份、ABI、数值 Gate、资源 Gate 或依赖异常时停止并报告。