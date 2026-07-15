# Task033：高阶 Floquet 与 Hybrid h/p 自适应入口

## 当前状态

```text
status = task document ready
execution = not started
base requirement = Task032 selective merge accepted by Review V2
ordinary default = unchanged
```

Task033 的正式任务书见：

- [`task.md`](task.md)

## 执行前置条件

1. Codex 先读取 Task032 `review_report_v2.md`；
2. 按 Task032 `selective_merge_manifest.csv` 将验证组件选择性合入 clean `master`；
3. 在 `master` 运行轻量回归与 Case080 checker；
4. 记录 Task032 selective-merge SHA；
5. 在本地库 `C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal` 更新 clean `origin/master`；
6. 由 Codex 创建独立执行分支：

```text
codex/20260715-task33-high-order-floquet-hybrid-hp
```

不得直接在 Task032 research branch 上实现 Task033。

## Task033 的两级主线

| 阶段 | 主要目的 |
|---|---|
| 高阶资格化 | 在 10 nm 纯 3D 空气盒和 air–Si 平坦界面上验证 p=1–4 Nédélec、双 Floquet、orientation、Fresnel 和 MPI |
| Hybrid h/p 可行性 | 在当前 13.5 nm 光栅 Hybrid 模型上比较 p1–4、h5/h3/h2.5/h2/h1.5、分级 h 网格、p3/p4 等精度效率和接口缓冲厚度 |

## 关键边界

- 主求解路径为 `modal-schur-memory-minimal`；
- `augmented direct` 仅用于小规模代数 reference；
- 14 GiB 是硬资源边界，大组合必须通过预测 Gate；
- 不使用 swap 强行完成大算例；
- Task033 不新增最终 Hybrid 迭代法；
- Task033 不重构 Task034 的 scalable modal core；
- 当前结构简单不等于未来结构 y 不变；
- 上下复杂 3D FEM 仍是未来目标架构的必要部分；
- p2 h-adaptive 的 3 倍压缩是 stretch，不是最低通过线；
- combined h/p/interface 的 3 倍是工程目标，5 倍是强目标；
- 公式和表格必须按 [`../markdown_rendering_standard.md`](../markdown_rendering_standard.md) 正确渲染。

## 预期 Benchmark

```text
Case090 = high-order 3D Floquet H(curl) qualification
Case091 = Hybrid h/p adaptivity feasibility
```

Task033 完成后，Codex 必须提供表格化 `outcomes/summary.md`、完整运行矩阵、14 GiB launch/not-run 决策、DoF/NNZ/RSS/time 对比、负结果和选择性合并清单。