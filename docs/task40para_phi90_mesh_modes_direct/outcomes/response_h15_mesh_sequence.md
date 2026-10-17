# H15 四场网格序列与 X2/Y2 同策略对照

状态：H15 输入/profile/轴计划及定向接口检查已完成；尚未启动 H15 FE。首次执行包待主控技术快审和运行前 fresh 准入。

## X2 与 Y2

X2 已自然结束并通过其单场原数值门。与同为 relative-only policy 的 Y2 离线比较使用已保存的 612 模态复幅值、R/T、样本场和小型 summary；没有重跑 FE、factor、读取大 VTU 或重扫资源流。比较脚本、JSON 和逐模 CSV 见本目录 `analysis/compare_d13_same_policy_y2_x2.py`、`records/d13_y2_x2_same_policy_comparison_v1.json` 与 `records/d13_y2_x2_same_policy_all_612_modes_v1.csv`。

X2/Y2 的总 R、R00,s、总 T、A_balance、A_volume 差分别为 `-2.4442e-8`、`-2.4439e-8`、`-1.5891e-9`、`+2.6031e-8`、`+2.6037e-8`。612 个物理边界 outgoing 复幅值相对 L2 差为 `5.8143e-8`，最大逐模绝对差 `2.9526e-8`，位于 top `(m=0,n=0,s)`。共同坐标已保存样本场的 E/H/Et/Ht 相对 L2 差依次为 `4.091e-6 / 5.366e-7 / 3.988e-6 / 1.587e-6`。X2 与 Y2 只有 x 轴不同，source SHA 不同；两者仍是相同模式、积分与 relative-only 算子合同下的比较。倏逝模 raw outgoing 系数受指数尺度影响，不能与 boundary phase 缩放后的物理边界幅值混为一谈。此比较只覆盖有限 R13 模态及已保存采样，不证明 full DtN 或 canonical 方柱侧壁迹。

X2 终态 `run_summary.json` 报告 `finished/exit0/descendants_cleared`，elapsed `20980.17355 s`，任务树 peak RSS `308907405312 B`，swap peak `0 B`。runtime 最低 available-memory 没有保存的聚合值，记为 `UNKNOWN_NOT_AGGREGATED`。`2126305861632 B` 是 launch envelope 的启动准入快照，`68719476736 B` 是 host-floor 门槛；二者都不是运行期最小值。既有样本曾约 `1.85 TB`，但不把该单个样本提升为最低值，也不为此重扫 resources。

## H15 四场合同

H15 是候选较粗基准，不预先宣称精度充分。四场顺序运行、每次只一个重计算：

| 场 | 网格 cells | 轴变化 | cells 总数 | 材料段单元数 x/y/z |
|---|---:|---|---:|---|
| H15-B | `[6,4,10]` | 实际 boundary-fitted H15 基准轴 | 240 | `[2,2,2] / [1,2,1] / [1,8,1]` |
| H15-X | `[12,4,10]` | 只将 B 的每个 x 区间二分 | 480 | `[4,4,4] / [1,2,1] / [1,8,1]` |
| H15-Y | `[6,8,10]` | 只将 B 的每个 y 区间二分 | 480 | `[2,2,2] / [2,4,2] / [1,8,1]` |
| H15-Z | `[6,4,20]` | 只将 B 的每个 z 区间二分 | 480 | `[2,2,2] / [1,2,1] / [2,16,2]` |

按柱体实际 x/y 覆盖区间与 z 材料区间的单元中点分类，H15-B 的 air/substrate/grating 标签数为 `184/24/32`；H15-X/Y/Z 均为 `368/48/64`。这些是轴计划上的独立几何计数期望，正式场仍须由 live mesh QA 再核。

四场保持同一 Si 几何、材料、入射、边界、p6 精确局部凝聚直接法、612 个 R13 有限矩形模态、surface q28、volume q15/default、relative-only `1e-13` 稀疏提取、原凝聚/A6/能量门和最多两次同因子校正。每个细化只从 B 的实际坐标逐区间二分，另两轴 SHA 必须逐位相同。四个 `.dat` 的 input/physical/resolved SHA、轴 hash、plan SHA 和细节见 `records/h15_mesh_sequence_contract_v1.json`。正式 setup 仍需检查实际 mesh/tag/mode 身份；静态轴计划不冒充 live mesh QA。

本轮完整场总上限按用户补充为 13：之前已完成 8 场、D13-X2 1 场、H15 B/X/Y/Z 4 场。此补充只解释新方向的总数上限，不覆盖早期文档中的历史预算或更改其历史记录。完成 H15 后，评估 z 粗化仅使用 B 与 Z 的全模式、复 E/H、逐级功率、R/T/A/A_volume 和原数值门；两级接近只说明当前两个离散接近，不证明更粗网格充分。第 14 场未获授权，不自动启动。5 nm 与 0.7 nm 目前只做固定 cell 预算的非均匀网格静态设计，不启动额外 FE，也不把相位缩放的大网格当启动方案。

H15 每场启动前独立执行真实 fresh/host-floor/共享 heavy-lock/邻任务/重复进程/ABI/磁盘准入。保持 parent CPU9、worker CPU24、MPI1、math threads1、NUMA interleave 0-1、PSS/USS off、无固定 RSS cap、swap observe-only；数值预测不能替代实测。不得跨网格复用 FE 向量或 factor。
