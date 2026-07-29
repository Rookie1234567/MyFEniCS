# Task002 M2B Solver Routing Map

## 冻结决定

选择 **Route 4：暂停 Hybrid，要求 Full3D static fidelity hierarchy**。这不是立即授权生成数据；
M3 仍为关闭状态，等待 Review V3 决定是否追加 Full3D p4/h7.5 的完整角域资格化。

| 候选 route | M2B disposition | 原因 |
|---|---|---|
| Route 1：统一 Hybrid 多保真 | rejected | p4 仅 39/80 formal pass；p6 在 45° 有 mode-basis failure |
| Route 2：统一升级 LF=p5 | rejected for now | p5 same-p 很好，但 p6 尚无独立 p6 reference 且 45° biorthogonality 失败 |
| Route 3：角域分区 | not selected | 失败不只局限 0.5°，p6 在 0.5°/1°/10° 的 45°均失败 |
| Route 4：Full3D static | selected, M3 blocked | 独立、稳定、资源可行；但 p4/h7.5 只有 A--D anchors |

## 当前已资格化与未资格化边界

```text
已资格化诊断能力：
  Full3D p5/h10 -> A--D + 20 点正式高阶选择（另有 1 个预选点）
  Full3D p4/h7.5 -> A--D，确认 p5 分支
  double Floquet constraints -> p1--p6, MPI1/2, 4 个 probe

未资格化为数据生成路由：
  Hybrid p4/h10 -> 41/80 Gate failures
  Hybrid p6/h10 -> 45° near-degenerate block split
  Full3D p4/h7.5 -> 尚无 80-angle domain map
```

## 若 Review V3 授权继续

推荐最小下一步是：

1. 将候选 LF 改为 `Full3D static p4/h7.5`，候选 HF 为 `Full3D static p5/h10`；
2. 先对 p4/h7.5 做中心几何 80-angle qualification，不进入训练 dataset；
3. 在误差峰值和边界复用现有 p5 records，必要时只补缺少的 p5 reference；
4. 只有新 hierarchy 的 residual、energy、资源和 p-reference map 经 review 批准，才恢复 M3；
5. 每个未来样本必须保存 `solver_route_id`，不得与旧 Hybrid LF4/HF10 静默混源。

在 Review V3 前：

```text
bulk_generation_allowed = false
surrogate_training_allowed = false
angle_doe_allowed = false
inversion_allowed = false
```
