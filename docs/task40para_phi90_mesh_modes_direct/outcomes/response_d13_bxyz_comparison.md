# D13 B/X/Y/Z 对照更正

这份离线记录只比较已完成的四个 finite-R13 直接解，不重跑求解。B 与 X/Y/Z 的 612 个有序端口 mode key、分支/材料身份、上下参考面及逐模式 `boundary_phase` 完全一致。四场实际 surface quadrature 均为 q28，来源是各自 `p6_condensed_direct_summary.json` 的 `production_port_mpc_witness.dtn_quadrature_degree`，不是 `operator_identity` 的空字段。

完整数值、样本坐标与输入/输出哈希见 [`d13_bxyz_comparison.json`](records/d13_bxyz_comparison.json)，SHA256 `767f81643bf0d5fdc5dd4a37091e21354a3dfe28756e67158abe4bdafc297aa7`。保存场的侧壁节点提取见 [`d13_bxyz_sidewall_comparison.json`](records/d13_bxyz_sidewall_comparison.json)，SHA256 `31b4c2e6618a4ea5d910df7602635fb5df6fff8673d009ce96a91b986e45c673`。

## 全局量与同坐标场差

| 相对 B | ΔR | ΔT | ΔA_balance | ΔA_volume | 采样 E 相对 L2 | 采样 H 相对 L2 |
|---|---:|---:|---:|---:|---:|---:|
| X（只细化 x） | 1.393e-8 | 2.186e-9 | 1.611e-8 | 1.339e-8 | 2.809e-6 | 5.073e-7 |
| Y（只细化 y） | 3.464e-3 | 4.812e-4 | 2.982e-3 | 2.982e-3 | 4.786e-3 | 5.181e-3 |
| Z（只细化 z） | 1.292e-8 | 6.252e-10 | 1.354e-8 | 1.372e-8 | 1.865e-6 | 2.366e-6 |

字段比较在完全相同的 saved sample coordinates 上逐复数计算，未拟合整体相位；这些是指定样点上的诊断量，不是全域场范数。B/X/Y/Z 的同一输入采样坐标为 x/y/z 网格（40×64×5），坐标数组逐位相同。

## 功率通道口径

四场各有 612 个模式，其中 `propagating` 为 166 个，`power_carrying` 为 390 个。先前通知中的 Y `max |ΔT|=2.35762611e-8` 只统计了 `propagating` 子集。全部 390 个有功率贡献的通道（包括有损下端口中 `propagating=false` 的衰减通道）最大逐级差为：

- `max |ΔR| = 3.46360665e-3`，top `(m,n)=(0,0)`, `s`；
- `max |ΔT| = 4.81097749e-4`，bottom `(m,n)=(0,0)`, `s`。

该最大 T 差也出现在 all-612 统计中。Y 的总 R/T/A_volume 差为 `3.46356288e-3 / 4.81198224e-4 / 2.98233515e-3`。因此 B→Y 仍明显未达到 D13 的方向对照精度目标；继续 Y2 是必要的。不能只按布尔 `propagating` 筛掉有损底端的功率通道。

## 模态系数与边界幅值

原始 `outgoing_amplitude`（与本记录中的 `auxiliary_amplitude_total_projection` 同量级）保留，不从记录中删除；其对 B 的 no-phase-fit 相对 L2 差为 X `0.68216`、Y `0.98289`、Z `0.01142`。这些系数位于端口内部参考坐标，含强衰减模式；虚数 β 对应的边界相位因子会按参考面间距指数衰减，不能把内部系数差直接当成边界物理幅值差。

各场均采用同一端口参考定义：top `z=130 nm`、bottom `z=-10 nm`；对全部 612 模式逐项核对后，`boundary_phase` 完全一致。使用代码已经输出的 `outgoing_amplitude_at_boundary`（不额外拟合相位）比较，no-phase-fit 相对 L2 差为 X `5.31954e-7`、Y `7.55271e-3`、Z `8.40654e-8`。原始内部系数和参考面相位后的幅值两种口径均保留；Y 的边界幅值变化仍不可忽略。X/Z 的 R、T 接近本身不能证明全部场量或无限 DtN 已通过。

## 水平面与几何侧壁

现有 `full3d_reference_samples.npz` 中 `interface_plane_indices=[0,4]` 对应 z=`10/110 nm`，切向分量为 x/y。这是中间端口区的水平面采样，**不是**柱体 x/y 侧壁，也不是 z=`0/120 nm` 材料界面。其 Et/Ht 差继续作为水平面样点诊断记录，但不称为侧壁 Gate。

另对已有完整场 VTU fallback 做了离线、无插值节点提取：只选已存 DG6 几何节点上严格落在方柱四个 x/y 侧面且避开 z=0/120 和侧壁角点的点；没有可视化插值、没有整体相位拟合，也没有新 FE。该数据确认含 finite 的 E/H、cell tag 和 343 个 DG6 六面体节点/单元，但同一次导出中重复单元面节点的切向分量 spread 并非微小（跨 case 最大 E_t 约 `8.7e-5…1.66e-4`、H_t 最高约 `5.47e-5`）。因此只作为保存 DG6 表示的侧壁诊断，状态是 `NOT_MEASURED_AS_CANONICAL_HCURL_TRACE_GATE`，不能据此宣布侧壁 Gate 通过。

## 范围限制与后续

B 的原 run 使用旧的 `task40_D13_B_R13_finite_rectangle` operator-scope 命名；X/Y/Z 使用当前 `task40_phi90_D13_*_R13_finite_rectangle` 命名。比较绑定各自真实 source/input/physical/resolved 与模式身份，没有假称这些 source SHA 相同。四个解仍是有限 R13 结果：`FULL_DTN_NOT_VERIFIED`、`AUTHORITY_LIMITED`。下一场按授权从实际 D13-Y 轴逐段二分生成 Y2，保持 x/z 轴、612 模式 SHA 和 q28 不变；不重跑 B/X/Y/Z。
