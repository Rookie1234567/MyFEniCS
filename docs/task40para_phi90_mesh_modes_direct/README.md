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

按用户授权，当前顺序执行三个同总量 y 分配，均以 Y3-2 `[2,6,2]` 为共同父方案、固定 x/z、612 模式、q28/q15 和 relative-only 算子身份，彼此不是累计细化。统一展示名与冻结内部 case/run 身份如下：Y4-1=`Y3_3` `[3,6,3]`、Y4-2=`Y3_4` `[2,8,2]`、Y4-3=`Y4_4_4` `[4,4,4]`；三场均 `[6,12,6]` / 432 cells。展示名映射及轴身份见 `outcomes/records/d15_y4_display_name_map_20261021.json`，完整静态轴与 SHA 见 `outcomes/records/d15_y3_2_siblings_static_axis_v2.json`。独立中点 tag 预测按 air/substrate/grating 分别为 Y4-1 `312/72/48`、Y4-2 `296/72/64`、Y4-3 `328/72/32`；这是计划预测，不是 live mesh QA。三场按序 fresh/单场运行，每场均依全球量、全部612共同/功率承载通道、边界复幅和同坐标复场三组既定门比较；不通过时保留失败证据。

Y3-2 离线比较 v1 保留原样；v2 只纠正 Y2→Y3-2 全局差值字段的 case 标签，未重算数值。详情见 `outcomes/records/d15_y2_y3_y3_2_saved_output_comparison_20261021_v2.json`。`FULL_DTN_NOT_VERIFIED` 与 canonical sidewall `NOT_MEASURED` 继续有效。

### 2026-10-21 后续：Y5/Y6 对照与 z-only 静态候选

上述 Y4 三场后，用户又授权 D15 的 Y5/Y6 方向研究。Y5-1 `[6,14,6]` 与 Y6-1/Y6-2 的三组保存结果比较均通过原三类差异门；因此当前将 Y5-1 暂作 y 方向工程候选，停止继续加密 y。它不证明当前 z 离散充分。现在只登记一个由真实 Y5-1 x/y 轴派生的 z-only 候选 `[6,14,8]` / 672 cells，z=`[-10,0,20,40,60,80,100,120,130]` nm，预期静态 tags air/substrate/grating=`516/84/72`。轴SHA、父run与静态标签依据见[response](outcomes/response_d15_y5_z_refinement_static_20261021.md)和[静态JSON](outcomes/records/d15_y5_1_z_refinement_static_plan_v1.json)。它尚未经过 live mesh QA 或 FE；需要另行审精确包与fresh，`FULL_DTN_NOT_VERIFIED`、canonical sidewall `NOT_MEASURED`仍保持。


## 2026-10-23 D15-Y3 模态截断结果

K1–K4（`m,n∈[-K,K]`）四个独立完整场已运行；与原有限 R13/612-mode Y3 参照的全局量、全通道 R/T、边界复幅及同坐标 E/H 比较均已记录。四场都未通过完整三组比较门：K2/K3 逐通道量虽通过，边界与 E/H 仍超 `1e-4`。见[详细结果](outcomes/response_d15_y3_modal_truncations_20261023.md)及其 JSON/CSV 机器记录。


## 2026-10-23 新授权：D5C 5 nm 粗网格序列

用户新授权的 5 nm 研究使用独立 `D5C` 名称，保留历史 D5 family 与全部旧结果。唯一基准 `D5C-B` 为 x/y/z 三轴各段 `2/2/2`（`[6,6,6]`，216 cells）；随后逐一从 B 只改变一个轴，顺序为 X1–X3、Y1–Y5、Z1–Z3。12 场完整坐标、轴 SHA、静态标签和逐轴比较关系见[D5C静态计划](outcomes/records/d5c_static_axis_plan_20261023_v1.json)及[响应记录](outcomes/response_d5c_coarse_5nm_plan_20261023.md)。D5C 采用旧 5 nm 的材料/入射和 R5 p6 direct 算子身份，不复用旧网格上的 FE 对象、因子或解。

该更新 supersedes 本 README 前文中“下一场为 R14”的运行指针，但不改写此前历史阶段与结果。当前只完成静态 planner、输入/profile/runner/worker 接线及定向接口验证；仍须逐场 fresh、实际 live mesh QA 和完整数值求解/比较。每场均保留全 3772 模态、q39 surface/q15 volume 与原三组比较门。

### 2026-10-24 D5C y-only continuation

在原 12 个 D5C 案例完成后，用户追加 Y6/Y7，并仅在三项指定比较未全部通过时追加 Y8。三者都直接以 D5C-B 为网格父；Y5 仅作比较参照。轴、hash、静态标签和条件顺序见[追加计划](outcomes/records/d5c_y6_y7_y8_static_axis_plan_20261024_v1.json)与[执行记录](outcomes/response_d5c_y6_y7_y8_20261024.md)。这一续行不改历史 12 场的输入、结果或原计划。
