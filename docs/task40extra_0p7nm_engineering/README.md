# Task40extra：0.7 nm工程方法（笔记本起步）

**先取得真实0.7nm、三维非可分缩小模型的完整FE解；再以误差与资源证据决定面向约2TB目标规模的下一项工程方法。**

## 本机执行目录与平台身份

旧控制端入口位于 `/home/shenjh/Projects/MyFEniCSx_task37_extra`；Task40 实际执行 checkout 是同一 canonical clone 登记的 `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering`，分支为 `task40extra_0p7nm_engineering`。Task39 checkout 保持独立。

原 `native_linux` profile 仍拒绝 WSL。只有显式使用 `scripts/run_fresh_c1_p6_local_wsl.sh` 时才采用 `local_wsl2_authorized`；每次运行的 imports-only 收据记录 WSL2 平台、内核版本和 boot ID，后续 admission 必须匹配同一环境。该 profile 复用冻结的 Python/MPI/PETSc/DOLFINx ABI、数学模型、资源 Gate 和原始截止时间，不改变任务范围。

执行分支：`task40extra_0p7nm_engineering`。B线沿用既有远端分支，不创建新分支。该分支原始base为`95dacd01e86f0f7f1d29ee2d5e5a16039bb41871`，续作前远端HEAD为`ffd89005096590c106324b6bb39a8d17c96a87ff`；Task39收口提交`7bb3243e657cbeecfff974f985f09569bfa6e094`已作为第二父提交合并，成为祖先。完整关系记录在`branch_provenance.json`中。

| 先读什么 | 用途 |
|---|---|
| [Task39extra最终报告](../task039_extra_physical_multilevel/final_report.md) | 双凝聚准确p4推荐路线、速度/内存、负结果与适用边界 |
| [Task39extra收口review](../task039_extra_physical_multilevel/review_report_v30.md) | 父任务收口范围与证据资格边界 |
| [Task39extra收口response](../task039_extra_physical_multilevel/response_v34.md) | 实际离线对照和仍未具备的证据 |
| [本任务书](task.md) | N0–N6首批实施、0.7nm材料/几何/网格、真实PDE与Gate |

首批模型：0.7nm正式Si/air、双Floquet、完整Fourier-DtN、带三维缺口的解析单胞；G0计划336cells、G1计划880cells，均p6+同网格p4双凝聚。cell数为计划推导，正式实测另记。最多两场iterative和条件性一场G0直接reference，不重跑父13.5nm性能场。

首批执行只在笔记本；不改MUMPS参数，不删A4完整检查，不热改工作站，不自动开启Phase II或merge master。首个结果必须区分：离散方程解出、同离散reference、h/通道精度、目标尺度可扩展性。

本机现有路线是可靠起点，不是承诺全域p4因子能直接扩大到0.7nm目标尺寸。新任务总体生产方向是有界局部处理、多层全局波动纠错、分布式matrix-free和受控端口/缓存库存；具体下一候选由首批真实证据支持。

提交后生成的 `response_v1.md` 与 `outcomes/summary.md` 是新结果入口，文档尚未生成时不得链接虚构PASS或填写预计数值为实测。

## 本轮结果入口

| 文件 | 内容 |
|---|---|
| [Response V1](response_v1.md) | 原始 N0–N6 回答与 attempt4 失败分类（历史） |
| [Response V2](response_v2.md) | R0–R5 收口，含 G0/G1 与 same-discrete direct reference |
| [Identity recovery](outcomes/identity_recovery_v1.md) | 根因、精确几何修复、strict fresh runs 与 direct 对照 |
| [结果总结](outcomes/summary.md) | 阶段矩阵、数据、资源、负结果和选择性合并边界 |
| [精度与容量判断](outcomes/accuracy_and_capacity.md) | G0/G1/direct 状态、误差 Gate 与资源口径 |
| [测试摘要](outcomes/test_summary.md) | N2、修复 fixture 与文档检查结果 |



## Review V4 closeout

| 文件 | 用途 |
|---|---|
| [Review V4](review_report_v4.md) | 主线四角 x/z 对照及 dot 边界合同 |
| [Response V4](response_v4.md) | 逐项回应 V3-A/V3-B/V4，列出正负结果和停止项 |
| [V4 interface package](outcomes/records/review_v4_four_corner_interface_v1.json) | 完整物理身份、精确轴节点、reference plane/phase、unknown/recovery、mode 和 hash 接口 |
| [Updated run index](outcomes/records/run_index.json) | Gx/Gz 求解身份、源 SHA 修正、analysis artifacts 与资源口径 |
| [V4 outcomes](outcomes/summary.md) | 四角结果、Gate 决定和依赖组 selective-merge 边界 |
| [V4 test record](outcomes/test_summary.md) | targeted tests、工程 startup failure 分类及未运行范围 |

本轮确认 x-only refinement 比 z-only 更接近 F5 的三个预登记主要量，但 F3/F5 与 Gz/F5 的全体显著模式 1% 门、散射 E/curl 门仍未通过；功率门通过不能覆盖这些负结果。dot、原尺寸、workstation readiness 和 continuum convergence 均未验证，master merge 未授权。

## Review V2 closeout

| 文件 | 用途 |
|---|---|
| [Review V2 campaign与P7方案](outcomes/review_v2_campaign.md) | P1–P7完整过程、负结果、资源口径、下一阶段设计和全Review选择性合并manifest |
| [Response V3](response_v3.md) | 对Review V2逐项回应与证据索引 |
| [V2两级结果总账](outcomes/summary.md) | F1/F2/F3/F5/E1/E2、P1 M0体积/curl负结果、P4 M2体积/curl负结果及资源组成 |
| [Review V2运行索引](outcomes/records/run_index.json) | 正式source/input/physical/native mode身份、run_id、raw路径/sha与状态 |
| [P1原M0共同子单元体积/curl](outcomes/records/p1_m0_volume_h_agreement_v2.json) | M0跨网格散射场/curl超过1%的原始compact evidence |
| [P4 F3/F5同M2体积/curl](outcomes/records/volume_h_agreement_v2.json) | 340个共同M2 key下的saved-field场、curl与官方功率比较 |
| [历史R5固定坐标样本](outcomes/records/h_agreement_v1.json) | 独立的固定样本工程比较；其PASS不替代P1/P4共同体积/curl记录 |
| [修复、停止和成本账](outcomes/records/repair_ledger_v2.json) | 保留F2/F5/E2实现失败、容量停止、E2恢复次数和未知成本 |

Review V2的P1是M0共同子单元体积/curl负结果；P4是F3/F5的M2结果。旧R5 `h_agreement_v1.json`是另一项固定坐标样本比较，不能用它覆盖P1。F3使用源码SHA `a43f7f76a0df0f4440b77834846973b2de7ea3a8`；F5/E1/E2使用 `63dd2a7378153f2ab5094eb5e7a98d05758a39bf`。没有continuum-convergence或约2 TiB capacity结论，ordinary default未改变，未合并master。
