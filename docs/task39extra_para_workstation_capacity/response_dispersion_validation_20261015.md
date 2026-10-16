# 0.7 nm 色散验证与候选 D 执行回应

> 2026-10-16补充：最新科学结果、BAL_H历次修复与尚未关闭的A4返回门，统一见[审阅交接](review_handoff_0p7nm_balh_20261016.md)。本文历史时点与原始失败分类保留。

日期：2026-10-16。执行分支：`task39extra_para_workstation_capacity`。本回应收口 V0/V1/V2 的既有离线证据，并记录随后获准的单场候选 D。V0 原始分类、V1/V2 输出和已归档计划均保留；本文不改写旧 run manifest、summary 或失败记录。

## 结论

实际 Basix/FFCx 参考单元计算与三个平层校准点共同支持“p6 横向离散色散在本近掠入射条件下是重要误差来源”。平层 R/T 从 Nx2 到 Nx8 明显稳定，但这不是原光栅的收敛证明。

随后执行的候选 D 是 47,200-cell、p6、572 通道的凝聚直接 MUMPS 全场。其本场 A6_n0 残差为 `1.3202759103785678e-7`（门限 `1e-6`），端口—体吸收差为 `4.915383655657024e-10`（门限 `1e-5`），数值/物理检查通过。D 的 R/T/A_volume 接近已有 RCWA 报告总量；但 D 同时改变 x 与 z 网格，而且源码 SHA 与旧 A 不同，所以只能作为 `CROSS_CHANGED_GRID_DIAGNOSTIC`，不能把吻合归因于 x 加密、z 粗化或网格收敛。

D 的 operator scope 仍是 `A6_n0`，状态为 `AUTHORITY_LIMITED` / `FULL_DTN_NOT_VERIFIED`。全 32,060 父模式中被省略的端口数值没有计算；RCWA 原始工程和校准文件也未独立复现。现有证据不构成全 DtN、连续精度或任意三维散射资格。

## V0：5 nm full600 provenance

V0 direct 小 summary 的全 A6 相对残差为 `9.59405650939179e-11`，端口—体能量差为 `-1.552757922240744e-12`。外层 `run_summary` 仍保留 `EVIDENCE_INCOMPLETE`：该运行的 source 是 `d0dd7f09`，运行期间授权的 docs-only commit 将 HEAD 移到 `37a76ecc`。补充记录逐一绑定 8 个文档路径，并核实 src 与 input tree OID 未变；不覆盖旧 manifest，不放宽 source provenance gate。

证据：[V0 source identity reconciliation](outcomes/dispersion_directional_validation_20261015/v0_source_identity_reconciliation.json)。

## V1：实际 FE 参考单元传播关系

V1 使用生产 Basix N1E 基函数及 FFCx 实际积分元数据。p6 的体积分 `q15` 对应每轴 8 点、共 512 个参考点；它不是每轴 15 点。生产表面端口仍按 q160。p6 无量纲色散量 `delta=(lambda-kx²)/k0²` 在 hx=.5、.25、.125 nm 分别约 `7.94e-6`、`2.58e-9`、`6.54e-13`（hz=.6 nm）；hx=.125 的数值接近该计算的舍入地板，不能据此宣称精确渐近阶。p7/p8 只做有界参考单元检查。

这支持 Hx，但该 V1 单元检查没有运行真实生产 Floquet MPC、整个网格方向集合或端口组装；这些范围保持 `NOT_RUN`，不能由 canonical-cell 结果替代。

证据：[V1 actual Basix/FFCx symbol record](outcomes/dispersion_directional_validation_20261015/v1_actual_n1e_ey_dispersion_symbol.json)。

## V2：同物理平层 Nx2/Nx4/Nx8

三场都用 p6、y=2、同一 z 网格/材料/入射/边界和精确相同的输出采样点，x 单独从 hx=.5 加密到 .25、.125 nm；每场 936/1,872/3,744 个单元及 540 个自动传播模式。R/T 在 Nx4 与 Nx8 间分别相差约 `2.45e-6`、`2.67e-6`，复 E/H 的无相位拟合相对 L2 差为 `6.50e-5`、`7.31e-5`。Nx8 对平面解析界面的 R/T/A 绝对差约 `2.04e-10`、`5.75e-10`、`3.71e-10`。

这是平面材料校准，不是原 50 nm 光栅参考。小场的矩阵/内存不能按单元数推到原光栅。旧外层分类不完整的 Nx2/Nx4/Nx8 记录保持不变；补充兼容测试只修分类器，不追写历史 summary，也不把全机 page-in 计作该任务 swap。

证据：[V2 comparison JSON](outcomes/dispersion_directional_validation_20261015/flat_calibration.json)、[per-order data](outcomes/dispersion_directional_validation_20261015/flat_modal_orders.csv)。

## 候选 D：实际原光栅对比

| 项 | 旧 A | 新候选 D | RCWA 报告 |
|---|---:|---:|---:|
| 网格单元 | 100×2×234=46,800 | 200×2×118=47,200 | — |
| x / z | hx=.5 nm；z=17/200/17 | hx=.25 nm；z=9/100/9 | — |
| R total | 0.08592253473181985 | 0.07028528534177456 | 0.0702787390763 |
| T total | 0.6522079390017288 | 0.6688236885790999 | 0.668830211715 |
| A_volume | 0.26186952633636734 | 0.260891026570664 | 0.260891048523 |
| 原 A6_n0 残差 | 7.427046290347574e-8 | 1.3202759103785678e-7 | — |
| R/T 与体吸收闭合差 | 6.991607293116431e-11 | 4.915383655657024e-10 | — |

候选 D 相对旧 A 的变化为 R `-0.0156372493900453`、T `+0.0166157495773711`、A_volume `-0.000978499765703`. 相对 RCWA 显示值则为 R `+6.54626543e-6`、T `-6.52313555e-6`、A_volume `-2.19523360e-8`。这些总量变化很明显，但 x 与 z 同时变动，不能用于分离二者贡献。

全部 143 个 `(m,0)`（m=-142…0）的 FE R/T 与 RCWA 报告功率均在 CSV 中。按三组数据的功率并集、`>=1e-8` 定义的 7 个显著级是 m=0、-1、-2、-4、-5、-7、-8；其余 136 级保留为尾部。

| m | R old A | R D | R RCWA report | T old A | T D | T RCWA report |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 8.58927332e-2 | 7.02517184e-2 | 7.02451724e-2 | 6.52181625e-1 | 6.68805472e-1 | 6.68811997e-1 |
| -1 | 2.84252733e-5 | 3.26344716e-5 | 3.26350961e-5 | 2.40983849e-5 | 1.56001057e-5 | 1.55974216e-5 |
| -2 | 8.53158841e-7 | 4.19212822e-7 | 4.19089946e-7 | 1.69201525e-6 | 2.16427198e-6 | 2.16442224e-6 |
| -4 | 1.13422810e-7 | 1.52837209e-7 | 1.52878203e-7 | 6.34496545e-8 | 2.54562690e-8 | 2.54592139e-8 |
| -5 | 2.31529841e-7 | 1.99419265e-7 | 1.99379178e-7 | 2.66157606e-7 | 2.49315300e-7 | 2.49307613e-7 |
| -7 | 9.83457696e-8 | 8.52515345e-8 | 8.51680217e-8 | 1.11006245e-7 | 1.03444276e-7 | 1.03444918e-7 |
| -8 | 3.95893710e-8 | 3.85668476e-8 | 3.86275542e-8 | 3.79887140e-8 | 3.09053298e-8 | 3.10263642e-8 |
| 其余 136 级功率和 | 4.02208860e-8 | 3.71961324e-8 | 3.64006341e-8 | 4.52586295e-8 | 4.27273608e-8 | 4.39353661e-8 |

候选 D 对 RCWA 的最大逐级绝对差出现在零级：R `6.54595e-6`、T `6.52434e-6`。CSV 同时列出 FE 的每级 top/bottom、s/p 复出射幅值与 D−A 幅值差；RCWA 来源只有显示精度功率，未提供对应复振幅。

旧 A 与 D 的两个小型复场档案具有完全一致的 x/y/z 和界面坐标。没有整体相位对齐时，4,000 个 air-side 点的相对 L2 差为 E `0.18568`、H `0.18515`、导出的 curl(E) `0.18515`；界面切向 E/H 为 `0.18860`/`0.23256`。这是不同离散/源码场之间的样本差，不是与解析光栅场的误差，也不是全域场范数。

D 的凝聚矩阵为 `9,374,972²`，`nz_used=7,553,047,842`、`nz_allocated=7,611,634,384`。矩阵装配 `4,829.26 s`；symbolic/numeric/solve 同矩阵生命周期 `39,664.86 s`；外层工作流 `52,726.35 s`。这些时间分别指不同边界，不能当成 solver kernel 的同一计时。

资源流只完整审计一次：`watchdog/resources.jsonl` 153,151 行、无坏行、所有状态均可读。顶层 process-tree RSS 峰值 `1,303,868,440,576 B`，低于硬线 `1,800,000,000,000 B`，但超过 advisory warning `1.17e12 B`。进程树采样 swap 峰为 0；全局 pswpin/pswpout 增量分别 +27/+72 页，无法归因到本任务，故不能宣称全机 zero-swap qualification。PSS/USS 按合同关闭。

源身份也不同：旧 A 是 `9a3c4a3fd9a41702fff4069280cb9507cefb163d`，候选 D 是 `b4db2b5436a6fb188cf81773577ab31c4cacb7c5`。因此这是受限的 A/D 输出诊断，不是仅更改网格坐标的同源收敛试验。R/T/A 接近报告值可作为下一步线索，不能提高 RCWA 或 D 的 authority。

证据：[candidate D compact](outcomes/records/v7_candidate_d_terminal_compact_20261016.json)、[143-order/field comparison](outcomes/dispersion_directional_validation_20261015/candidate_d_comparison.json)、[143-order CSV](outcomes/dispersion_directional_validation_20261015/candidate_d_orders_143.csv)、[reproducible extractor](outcomes/dispersion_directional_validation_20261015/compare_candidate_d_runs.py)。

## 最终范围

本轮完成 V0 provenance 补充、V1 实际参考单元符号、V2 三个平层直接场及候选 D 一场原光栅诊断。没有运行 B=93,600、C、p7/p8 全模型或其他后续 PDE。Hx 得到实际离散与平层校准支持；D 的 R/T 更接近显示精度 RCWA 总量，但其 x/z 同时变化且源不同，不能定位剩余差异。原光栅 z 网格收敛、完整 32,060 模式 DtN、RCWA 原始项目复现和任意三维精度均未验证。
