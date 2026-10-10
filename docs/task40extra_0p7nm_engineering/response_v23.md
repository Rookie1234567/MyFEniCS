# Task40extra Response V23：原尺寸全模式支撑扫描完成，q tile 未完成

| 必答项 | 本轮结果 | 判定边界 |
|---|---|---|
| 原尺寸 B/D/H 扫描 | 32,060/32,060 个模式完成，bottom/top 各 16,030；checkpoint 已保存 | 完整模式支撑库存，不是全局 q 矩阵或 Maxwell 场求解 |
| 内部支撑 | 两级全局 1e-13 production 筛选后，B/D 的内部 m_c 在全部边界单元均为 0；保留模式行项只归入实际端口面 trace | 原始 component 仍有微小非零项，不能称原始积分严格为零 |
| compact/full 对照 | 24 个选样的行、mask、值、Bα、Dx 完全相同；wall 1.782 s 对 3.016 s | 约 1.69 倍仅适用于 24 个局部样本 |
| 真实 q tile | q 叶子先因 axes 接线 TypeError 失败；修复源码冻结后，数值截止已过，q-only 未运行 | TIME_BUDGET_NOT_SUFFICIENT / NOT_RUN |
| 完整求解 | q CSR 0/8，factor、KSP、完整场、PDE 和官方 R/T/A 均未运行 | 不代表数值算法失败，也不构成完整求解通过 |

目标是波长 0.7 nm、Ny=8 的三维非可分 Maxwell 模型。每个网格单元用六阶有限元近似场；y 周期方向预计有 8 个 q 相位子问题。本次逐模式检查边界算子 B、D、H 如何作用，并统计原有生产筛选后哪些有限元行仍被保留。这样可以判断内部自由度是否进入实际边界作用，以及紧凑边界候选域是否保持原有数值。模式扫描没有装配 8 个全局 q 矩阵，也没有因子分解或求解完整场。

## 身份与模型

| 项目 | 身份 |
|---|---|
| 执行分支 | task40extra_0p7nm_engineering |
| 完整扫描源码 | 1291aeef089e6c02c4b9e28125f60072aa769340 |
| 后续 q 修复源码 | 43588de8275a1014375ab8d5fdd1d835b0bcee55 |
| 输入 SHA-256 | 33cb569eb900f60100569a6659138589a9d26784a22e05d50c7fe63190bac4ff |
| 物理模型 SHA-256 | ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241 |
| 固定 V23 window SHA-256 | e77793e53542c6094da819456457910893b33c9be5ca3b548482be6bfc3dbdfb |
| 模式清单 SHA-256 | 52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d |
| 网格 / p6 空间 | 272×8×14 cells，共 30,464 cells；20,181,348 storage rows、19,897,344 independent rows |
| finalized MPC | 284,004 slave rows；coefficient SHA-256 9312e5f0ad152e517ffc5b7050951fe33ea75f2066bd2e6e7a40639e70366411 |

扫描运行绑定旧源码 1291aeef。完整模式库存和 B/D/H payload 完成后，流程继续进入 q 端口 tile 时发生普通接线错误。因此新源码 43588de8 仅用于后续修复与受限续跑入口，没有被说成扫描源码，也没有在固定数值截止后重跑。

## 支撑库存与其含义

每个边界相邻单元有 450 个内部行和 432 个 trace 行。周期 MPC 将 slave 项按复系数归并到 master 行；生产流程随后在 component 和加权组合阶段各应用一次全局相对阈值 1e-13，绝对 floor 为 0，阈值未改。

| 两侧各自的累计保留模式行项 | B | D |
|---|---:|---:|
| 实际端口面 trace | 2,429,660,672 | 2,429,660,672 |
| interior | 0 | 0 |
| other trace | 0 | 0 |
| slave / unknown | 0 | 0 |
| 内部 m_c=0 的边界相邻单元 | 2,176 | 2,176 |

这里的行项按模式累计，不是去重后的全局行数。m_c 表示一个边界相邻单元在多少个不同模式中至少有一个通过两级 production 筛选的 B 或 D 内部行；两侧 B、D 和并集的直方图都只有 0-bin。原始积分仍有 tiny nonzero 项：代表性局部 B witness 的 interior 最大绝对值约 8.92e-16，component 审计也记录了大量筛选前小项。因此结果是“当前生产筛选后没有保留内部支撑”，不是原始积分严格为零。旧字段 raw_interior_row_memberships_by_side 的计数来自 retained filtered functional，不应用作 raw-support 证书。

紧凑候选域有 3,177,132 行，约占 20,181,348 个 storage rows 的 15.7%。24 个同场、同 α 对照覆盖非平凡 MPC 行，compact/full 的 rows、masks、values、Bα 和 Dx 完全一致。wall 时间分别为 1.782056792 s 与 3.016087356 s；这不是全模式吞吐或端到端求解加速。没有构造完整 carrier，故没有声称节省假设性 77/155 GB 内存。

## q 叶子故障与收口

三次 V23 attempt 的原始负结果全部保留。第一次在几何 inventory 后报 KeyError: 0，0 个模式完成。第二次报 checkpoint identity ValueError，q 子项另报无法复用现有 MPI1 p6/MPC space，0 个模式完成。第三次在旧源码上完成全部 32,060 模式后，q helper 将 cell-count list [272, 8, 14] 当成 x/y/z coordinate mapping，并用字符串键访问，触发 TypeError。第三次 worker exit 4 是 q 叶子实现失败；全模式 checkpoint 仍是独立、完整的科学输出。

修复源码 43588de8 改为从 resolved discretization 读取 mesh_axis_x_values、mesh_axis_y_values、mesh_axis_z_values，并加入绑定旧 source/input/model/window/checkpoint metadata/payload 的受限 q-only selector。对真实旧 checkpoint 的身份绑定检查通过；route/probe 19 项、numeric-stage 3 项、q checker/readback 2 项定向测试通过，py_compile 和 diff 检查通过。固定数值 cutoff 为 2026-10-10T14:40:51Z；账本 sequence 34907 明确记为 closeout-only/no-q-launch。因此修复后的 q-only 没有运行，原来的 TypeError 也没有被改写为通过。

| 计时与资源 | 实测 | 口径 |
|---|---:|---|
| 完整模式扫描 wall | 8,817.046 s | 主控核验的扫描阶段 |
| full workflow monotonic / watchdog conservative | 8,866.383 / 9,703.518 s | 分列，不互相替代 |
| process-tree RSS peak | 3,060,957,184 B | subreaper 加全部后代的同时 RSS 采样峰 |
| dedicated cgroup memory peak / cap | 3,238,825,984 / 17,179,869,184 B | 与 RSS 不同口径；16 GiB cgroup |
| task process-tree / cgroup swap | 0 / 0 B | PSS disabled；descendants cleared |

固定窗口 T0 为 09:00:51Z，数值 cutoff 为 14:40:51Z，总 deadline 为 15:00:51Z，预留 1,200 s 收口。累计账本时间包括准备、修复、测试、失败尝试、扫描和收口，不能用总数差值倒推出单项工时。

现在已有完整 B/D 支撑与有限的紧凑域数值对照，但真实 q map/tile、块 nnz/bytes/time、q CSR/factor 成本、完整场和官方功率仍未知。8-q profile 数量是预期规模，不是已建矩阵。2 TB/48 h 目标仍未资格化。任何继续数值工作都需新 review 明确授权新的固定 window，并绑定保留的 V23 证据；当前过期 selector/window 不应被当成可直接启动的权限。


主控核验补充：本轮 m_c 计数器只覆盖每单元的 450 个内部行；包括端口面及其他 trace 的整单元 m_c_B/m_c_D/m_c_union、直方图与 Σm_c/Σm_c² 尚未记录，保持 UNKNOWN，不能拿内部的零直方图替代。target 的阈值后内部零支撑没有被直接迁移到 reference/twist/sector，未据此删除实际缓存。实际删除量为 0 B；若缓存全部筛选后值，B/D 各有 4,859,321,344 条、complex128 逻辑值载荷各 77,749,141,504 B，这些对象未分配，不能称为 RSS 节省。component cache unique backing 峰值 3,133,440 B 不包括全工作集。

watchdog 的旧 elapsed_seconds=8,866.260855726 s 是其旧计时字段，真实 conservative budget_seconds=9,703.518256644 s；UTC/monotonic 累计差 837.250885526 s 已保守计费，未缩小为 8,866 s。worker 原生对象释放仍 UNKNOWN，外部后代清场已通过，二者不混用。

## 选择性合并边界

| 依赖组 | 本轮内容 | 建议 |
|---|---|---|
| production numerical/core | 方程、离散、矩阵与 ordinary default 未变 | 不升级数值默认 |
| service/runner/checker | 受限 q-only selector、轴值接线与 raw contribution/readback checker | 审阅身份限制和失败语义；q-only 尚未运行 |
| compact evidence/docs | 四份 compact JSON、ledger snapshot、response、summary、test summary、run index | 可随执行分支审阅 |
| research-only | 原尺寸 support scan 与 q supplement 准入路径 | 保持研究/任务专用 |
| do-not-merge | 未批准分支整体、master、ordinary default 切换 | 等待后续 review 和授权 |

证据入口：[operator](outcomes/records/target_operator_probe_v23.json)、[support](outcomes/records/production_support_v23.json)、[performance](outcomes/records/performance_v23.json)、[q tile](outcomes/records/q_tile_v23.json)、[任务账本](outcomes/records/review_v23_incremental_workflow_ledger.json)、[run index](outcomes/records/run_index.json)、[outcomes summary](outcomes/summary.md)、[test summary](outcomes/test_summary.md)、[项目进展](../development_progress.md)。原始 run 与 checkpoint hashes 在 compact records 中；GitHub 渲染与最终远端 HEAD 待主控提交后核验。

## 行政收口时限

主控于 2026-10-10T15:06:15.543465+00:00 核验时，已超过原 15:00:51Z 总截止 324.543 s。数值 cutoff 后没有新的 FE、q tile 或 PDE；本次仅完成证据审核、文档和集中提交推送。原窗口未延长，新增行政费用已追加原账本。保留 ADMINISTRATIVE_CLOSEOUT_OVERRUN，不宣称整个工作包在六小时内完成；提交推送与最终回读的费用在同一原始账本继续记录，不刷新 T0。
