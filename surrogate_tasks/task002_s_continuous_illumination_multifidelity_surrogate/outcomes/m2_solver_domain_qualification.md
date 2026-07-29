# Task002 M2B：中心几何求解器域鲁棒性资格化

## 1. 结论

M2B 已完成，但结论是 **solver domain 未通过统一 Hybrid 路由资格化**。这是一项受控负结果，
不是把失败状态改名为通过：现有 Gate、容差、S 偏振和 0.5° 下限均未改变。

当前证据支持以下判断：

1. `p4/h10` 在低掠射区欠分辨。独立 Full3D `p4/h7.5` 与 `p5/h10` 选择同一响应分支；
2. 同阶 Hybrid p5 与 Full3D p5 高度一致，因此 p4→p5 的大跳变不是 Hybrid 耦合或 axial
   mapping 制造的；
3. continuous 与 discrete axial route 的最大 R/T/A/volume 差仅 `3.30e-7`，也不是大跳变根因；
4. 双 Floquet 约束的 48 个实际 probe 全通过；
5. Hybrid p6 在 45° 方位仍有 biorthogonality 失败，根因定位为相邻 near-degenerate blocks
   被错误拆分；
6. Hybrid p4 的 80 点 formal map 只有 39 点通过，不能继续作为统一 LF；
7. 因而选择 Route 4：暂停 Hybrid，后续若获 Review V3 授权，应先资格化 Full3D static
   fidelity hierarchy。M3 仍关闭。

全部正式 PDE 绑定 clean source
`673c66ddee116e683a21b7ea8a90dc158cac2069`，均为 MPI2、每 rank 一线程、watchdog、零 swap。

## 2. 完成范围

| 诊断 | 完成量 | 用途 |
|---|---:|---|
| Full3D p3/h10 | A--D 4 点 | 观察低阶分支 |
| Full3D p4/h10 | 80 点 | 独立 same-p 角域 reference |
| Full3D p5/h10 | 21 点（20 点正式选择 + 1 个预选边界） | 可信高阶分支与误差峰值 |
| Full3D p4/h7.5 | A--D 4 点 | h-refinement 判别 p4 欠分辨 |
| Hybrid p4 Route B | 80 点 | formal Gate 与 same-p error map |
| Hybrid p5/p6 Route B | 各 12 点 | 低掠射全方位、峰值和边界 |
| Hybrid Route A/B | p4/p5/p6 × 15°/45° | axial model A/B |
| 双 Floquet probe | p1--p6 × 4 点 × MPI1/2 = 48 | x/y/corner、slave rows、`C^H A C` |

这些是中心几何 solver qualification records，不是训练数据；没有写入 Task002 dataset。

## 3. 独立 p/h reference

下表列出四个强制点的独立 Full3D R/T/A。`p4/h7.5` 与 `p5/h10` 的接近说明粗
`p4/h10` 的分支跳变来自空间欠分辨，而不是提高 p 后出现了错误解。

| 点 (grazing/azimuth) | p3/h10 R/T/A | p4/h10 R/T/A | p5/h10 R/T/A | p4/h7.5 R/T/A |
|---|---|---|---|---|
| A 0.5°/15° | 0.996916 / 0.000015 / 0.003068 | 0.818608 / 0.001415 / 0.179977 | 0.631656 / 0.005904 / 0.362441 | 0.634389 / 0.005815 / 0.359796 |
| B 0.5°/45° | 0.949061 / 0.000087 / 0.050851 | 0.649408 / 0.005348 / 0.345245 | 0.621729 / 0.006239 / 0.372032 | 0.623374 / 0.006184 / 0.370443 |
| C 2°/15° | 0.986648 / 0.000062 / 0.013290 | 0.325438 / 0.015546 / 0.659015 | 0.081682 / 0.042411 / 0.875907 | 0.083440 / 0.042032 / 0.874527 |
| D 10°/45° | 0.003837 / 0.586317 / 0.409846 | 0.000828 / 0.602164 / 0.397008 | 0.000769 / 0.602592 / 0.396638 | 0.000773 / 0.602567 / 0.396660 |

四点 `p4/h7.5` 对 `p5/h10` 的最大 R 差分别为 `2.733e-3`、`1.645e-3`、
`1.758e-3`、`3.357e-6`。所有 Full3D full residual 小于 `1.36e-10`。p5 实测最大
RSS 约 4.00 GiB；p4/h7.5 最大约 4.93 GiB；swap 均为 0。

## 4. Axial route A/B

Route A 使用 `continuous_beta + continuous_qep_beta`；Route B 使用
`full3d_uniform_cg + scalar_cg_discrete_derivative`。两者最大 observable 差如下：

| p | 15° | 45° |
|---:|---:|---:|
| 4 | 3.30e-7 | 9.83e-8 |
| 5 | 1.63e-8 | 2.96e-9 |
| 6 | 2.51e-10 | 5.71e-11 |

所以 p4→p5 的 O(1e-1) 响应变化不可能由 axial mapping 的 O(1e-7) 影响解释。
两条 route 共享相同 QEP mode basis，p6/45° biorthogonality 失败也不会因切换 axial route 消失。

## 5. 双 Floquet probe

48/48 个实际 probe 通过：

- 最大解析 quasi-periodic reconstruction residual：`1.898e-15`；
- 最大随机自由向量 slave-row residual：`0`；
- 最大显式 `C^H A C` action error：`1.517e-16`；
- MPI1/2 的相位、空间维数、slave/横向/纵向约束计数全部一致。

原始全局向量字节 SHA 在 MPI1/2 不相等，因为 DOLFINx 全局 DoF 编号随分区变化；它被保留为
事实但不作为物理 Gate。分区无关的约束计数、相位和代数 residual 才是 deterministic identity。

## 6. Mode continuity 与 p6/45° 根因

对 grazing=0.5°、10 个方位角、p4/p5/p6 均保存了完整 beta、左右 polynomial residual、
biorthogonality、near-degenerate groups、reciprocal pairs 和 selected identity，并用实际 full-vector
overlap 做 Hungarian matching 与子空间角计算。匹配显示所选 120 模态子空间随方位存在强烈交换，
不能把独立 magnitude sorting 后的第 j 个模式当成连续物理身份。

p6/0.5°/45° 的最坏项为：

```text
worst row       = 115
worst column    = 117
worst row sum   = 1.7765586e-6  > 1e-6 Gate
worst entry     = 1.0381412e-6
beta[115]       = 0.0002277315 + 0.5908874968 i /nm
beta[117]       = 0.0002274275 + 0.5908881316 i /nm
polynomial residuals = 1.67e-16, 1.94e-16
```

模式 115 位于 block `[114,115]`，模式 117 位于相邻 block `[116,117]`。两组 beta 实际近乎
重合，但 clustering 将它们拆开，block 内 normalization 各自通过，block 间 cross-overlap 却超过
Gate。因此根因归类为 `near_degenerate_block_partition_split`，不是 PDE residual、reciprocal beta
配对或 candidate pool 数量不足。相同 Gate 还在 p6 的 1°/45° 和 10°/45° 失败。

## 7. 子域能量 identity

新增 ledger 将 bottom local FEM、top local FEM、middle modal 和 external DtN 分开。代表点中：

- bottom local normalized balance 最坏约 `1.72e-7`；
- top local normalized balance 最坏约 `2.81e-6`；
- external auxiliary modal power sum 与记录的 R+T 差不超过 `8.7e-17`；
- p4/45° whole-domain volume closure 仍为 `-3.299e-4`；
- p5/45°为 `1.882e-5`；p6/45°为 `8.771e-7`。

这说明外部 DtN auxiliary power identity 与 local FEM balance 并非主误差源；主要缺口随 p 降低，
集中在把局部与 middle volume absorption 合成 whole-domain ledger 的离散/后处理精度。原 `1e-5`
Gate 未放宽，所以 p4 失败仍保留。

## 8. 80 点角域图

Hybrid p4 formal Gate 为 39 pass / 41 fail。same-p Hybrid-vs-Full3D p4 的最大 R/T/A
绝对差为 `3.4566e-4`，出现在 1°/45°。失败不是 solver crash；主要是原 volume closure Gate。

12 点高阶集合中：

- Hybrid p5：10/12 formal pass；same-p Full3D p5 最大 R/T/A 差 `1.853e-5`；两个失败仍是
  volume closure；
- Hybrid p6：9/12 formal pass；三个失败均为 45° biorthogonality；相对 Full3D p5 的最大差
  `1.499e-2`，但本机没有 mandatory Full3D p6 reference，不能把 p6 宣称为已独立资格化 HF。

## 9. Evidence

权威 compact records 位于
`benchmarks/cases/114_task002_solver_domain_robustness/records/`：

- `full3d_p_reference.json`
- `axial_model_ab.json`
- `floquet_probe.json`
- `mode_continuation.json`
- `energy_identity.json`
- `angle_robustness_map.json`
- `solver_routing_map.json`

checker：`benchmarks/check_case114_task002_m2b.py`。raw artifacts 保留在 ignored
`benchmarks/artifacts/cases/114/m2b/`，包括一次人工暂停产生并隔离的 p6 半成品目录；它未进入任何
完成计数或 compact record。
