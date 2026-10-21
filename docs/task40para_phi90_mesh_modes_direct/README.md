# Task40para｜phi90方向网格与模态截断

**执行分支：`task40para_phi90_mesh_modes_direct`。**

完整执行合同见[task.md](task.md)。本任务从父分支`task39extra_para_workstation_capacity@922466da9d7faff408cbb47b7882d179320bdc44`派生，仅继承代码，不继承旧物理/精度资格。分支来源见[branch_provenance.json](branch_provenance.json)。

| 项目 | 本任务固定选择 |
|---|---|
| 新几何 | x/y均50 nm周期；中心Si方柱17×20×120 nm；z=-10…130 nm |
| 入射 | 掠角1°，方位90°，s偏振 |
| 方法 | 三维p6 H(curl)，装配时单元凝聚，p6 trace/port MUMPS直接LU；不用p4/p3修正 |
| 顺序 | 13.5 nm方向网格 -> 5 nm方向网格 -> 5 nm二维BOX2截断对照 -> 有依据的0.7 nm完整计算 |
| 13.5 nm起点 | p6目标h10，材料拟合后预计504单元；是否足够由对照决定 |
| 5 nm起点 | p6目标h4，预计7020单元；先固定reference模式研究网格 |
| 三阶候选 | m,n各-2…2，25对级次；上下端口/两偏振，传播与倏逝分类保留 |
| 资源 | 0.7 nm实测同期整树RSS<=1.8e12 B；13.5/5 nm无用户固定cap，但保留主机安全 |
| 状态 | D13 的 B/X/Y/Z、Y2/Y3、X2 与 H15 B/X/Y/Z/YZ480 均有历史结果；同策略 Y2/Y3 和 Y2/Z2 对照已完成。Z2 `[6,24,28]` / 4032 cells 的端口、总量和保存样本与 Y2 接近，只支持当前两级有限 R13 z 敏感性。续行授权已恢复，当前下一场为同一 Y2 `[6,24,14]` 网格上的 R14 模式扩展（m=−5…5,n=−9…9，836 modes，q28）；不宣称 full DtN。canonical 方柱侧壁 trace 仍未验证 |

禁止沿用旧N0/572对称约简：新方柱沿x/y都变化。旧0.7 nm结果、RCWA比较和p4返回故障只作历史，不当本模型验收标准。全部新结果/response只写本分支；不改父任务、Hybrid或master。

当前 D13 比较与限制见[outcomes summary](outcomes/summary.md)、[relative-only Y2 response](outcomes/response_d13_relative_cutoff_followup.md)及[同策略 Y2/Z2 response](outcomes/response_d13_y2_z2_same_relative_only.md)。同策略 Y3 和 Z2 均已完成；续行授权与Z2精确轴计划见[2026-10-18 continuation response](outcomes/response_d13_z2_continuation_authorized_20261018.md)。


## 2026-10-21 执行状态更新

以下状态更新 supersedes 上述表格中“下一场为 R14”的旧指针；历史任务顺序和结果不作改写。D15-Y3-2 已自然结束，run `20261021T084703.634131Z` 的单场凝聚、独立 A6 与能量门通过，但 Y2→Y3-2 全通道 R 门以 `1.0804674384e-6` 略超 `1e-6`，Y3↔Y3-2 三组网格比较均失败。

按用户授权，当前准备三个同总量 y 分配，均以 Y3-2 `[2,6,2]` 为共同父方案、固定 x/z、612 模式、q28/q15 和 relative-only 算子身份，彼此不是累计细化：Y3-3 `[3,6,3]`、Y3-4 `[2,8,2]`、用户 Y4 组的独立标签 `Y4_4_4` `[4,4,4]`；三场均 `[6,12,6]` / 432 cells。静态轴、SHA、中点 tag 预测和主控对早期 tag 算术的更正见 `outcomes/records/d15_y3_2_siblings_static_axis_v2.json`；其独立 tag 为 Y3-3 `312/72/48`、Y3-4 `296/72/64`、Y4_4_4 `328/72/32`（air/substrate/grating）。这些是规划预测，不是 live mesh QA。三场按序 fresh/单场运行，每场均依全球量、全部612共同/功率承载通道、边界复幅和同坐标复场三组既定门比较；不通过时保留失败证据。

Y3-2 离线比较 v1 保留原样；v2 只纠正 Y2→Y3-2 全局差值字段的 case 标签，未重算数值。详情见 `outcomes/records/d15_y2_y3_y3_2_saved_output_comparison_20261021_v2.json`。`FULL_DTN_NOT_VERIFIED` 与 canonical sidewall `NOT_MEASURED` 继续有效。
