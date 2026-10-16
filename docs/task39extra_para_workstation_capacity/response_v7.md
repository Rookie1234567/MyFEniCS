# Response V7：0.7 nm 各向异性 N0 准确 p4 完整求解

> 2026-10-16补充：最新科学结果、BAL_H历次修复与尚未关闭的A4返回门，统一见[审阅交接](review_handoff_0p7nm_balh_20261016.md)。本文历史时点与原始失败分类保留。

本轮执行 [Review V7](review_report_v7.md)，优先取得一份可以分析的完整场。当前记录是启动前实现状态，**不是最终求解收口**。此前 530856-cell/p3 任务已按新授权停止，不等待其 factor 或 16 步，也不自动恢复。

| 阶段 | 当前事实 | 资格边界 |
|---|---|---|
| U0 | 旧 N0 run `20261012T065422.607789Z` 已受控停止；root、MPI、worker 与旧 guard 清场 | `USER_CONTROLLED_STOP`，不是收敛或数值失败 |
| U1 | 新增独立 q4/aniso/full profile、dat、实际网格 QA、N0 完整输出和 checker；联合 pure/接口检查 58/58 通过，独立 guard 纯测试 15/15 通过 | 未启动新 PDE，不借用旧网格 FE 缓存 |
| U2 / FULL | 尚未启动；正式入口为 `scripts/run_case.py`，新场须先冻结 clean source 并通过现场准入 | 预期 46800 cells，不冒称实际已生成；16/32/128 步只观测 |
| OUTPUT_AUDIT / Z | 尚未执行 | `FULL_DTN_NOT_VERIFIED`、`AUTHORITY_LIMITED`；48 小时目标尚未建立 |

## 旧任务与新任务的边界

旧场 source 为 `4de49260ab5663b57a466760281227ae3bac46e1`，终态完整 workflow 为 `11131.505397025961 s`，采样整树 RSS 峰 `333521260544 B`，任务 swap 峰 0。停止时仍在 `retained_forms_compiled/setup`，没有完成 numeric 或 KSP。2026-10-12 09:59:27 UTC 分别向核实的旧 guard 和旧 root 发一次 pidfd SIGTERM，由原监督器清场；未向邻项目发信号。[优先级切换记录](outcomes/records/v7_priority_switch.json)

旧 p6/p3 FE 泛函、DOF/MPC 映射、矩阵、因子和解不能用于新网格。本场只复用代码、纯模式 metadata 与符合身份的参考/JIT 缓存；不配置旧 functional store。旧结果、停止原因和费用全部保留。

## 本场实现合同

保持完整三维 p6 空间，单元内先消去内部自由度，在边界骨架和端口未知量上迭代；准确 p4 粗修正使用同样的单元凝聚及一份 MUMPS 因子，随后恢复内部场。BAL_H、P64/PH、快速 A6/A4/H6、原体积分和复 MPC 交叉项沿用已有路线，没有新增 PC 或弱化 p4 逆。

网格由既有精确轴计数入口生成 `[100,2,234]`，预期 46800 个六面体。名义 `mesh_target_nm=0.5` 不代表三个方向都为 0.5 nm；x 为 0.5，y 为 12.5，z 分段为 10/17、0.6、10/17 nm。正式 setup 内检查实际轴、材料面、周期面、每个单元的正 Jacobian、y 不变标签和实际行数，保存原始数组 hash；不冒用 R13 网格身份。

DtN 是上下开放边界的出射波表示。本场从完整 32060 项 metadata 中严格筛选 `n=0`，保留 m=-142…0、上下两侧与 s/p，共 572 项，筛选先于 FE 端口装配。p6/p4 共用 active 清单及原父清单 q160；不使用前 572 项切片，也不删除零级或 -1 级。新 p6 采用已有 prepared weighted 单 lane，p4 保留 native；未启用 p3 专属对角 Hp/Hlocal 存储优化。

完整求解采用 FGMRES32、zero start、max2048。每次完整 A4_n0 返回限值 1e-10、最多两次同因子精化；完整未凝聚 p6 独立 A6_n0 限值 1e-6，能量与体吸收一致性限值 1e-5。QA 与正式求解复用同一 factor。父 CPU9、worker CPU24、MPI1/math1、NUMA interleave0–1；RSS 硬线 1950000000000 B，PSS/USS 关闭，swap/预测/预计耗时仅观察。新 guard 从本场 p6 端口完成事件起计 24 小时，进入 solve 永久撤销。

## 输出及精度边界

通过求解残差后保存 E/H、curl、完整 FE 系数和映射、572 复振幅及 R/T/A_balance/A_volume。N0 后处理直接使用已构建 carrier，不再重建完整父清单 FE 泛函。多 y 位置复场在相同 x/z 上比较，不拟合相位；y 变化和交叉偏振泄漏只是诊断，1e-4 警戒值不成为新停机门。保存的 curl 样本明确为从导出 H 对应关系获得的 DG 插值样本，不能替代完整 FE 系数或网格收敛证据。

终点利用已有 572 项逐项作用计算 `delta20=||(A572-A84)u572||/||b572||` 和 `||b572-A84*u572||/||b572||`；A84 对应 m=-20…0 的 84 项，不另建矩阵、factor 或 PDE。分组功率覆盖 m=0、-1、[-20,-2] 及三个高阶尾部，`tail20_power` 按同一入射功率归一化。未来截断筛查不能成为本场通过条件。

本场 `A6_n0` 与完整 32060 通道 `A6_full` 分名。新网格没有兼容的全通道 FE 数据，因此当前完整 DtN 为 `FULL_DTN_NOT_VERIFIED`，省略项为 `NOT_COMPUTED`，不填实测零。没有同物理独立参考或 h/p 收敛证明时保留 `REFERENCE_NOT_AVAILABLE / AUTHORITY_LIMITED`。最终是否达到 48 小时和 2 TB 目标须由完整 workflow 和实测 RSS 判定。

运行、测试、阶段成本与最终 gate 将集中补入[本轮 outcome](outcomes/urgent_anisotropic_0p7nm_v7.md)，不将启动前合同写成结果。

## 启动前验证

最终 qualified PORD64 环境、CPU9/math1 下，六个必要 pure/fake/接口测试文件共 **58 passed / 2.70 s**。新 Python 文件 Ruff、12 文件 py_compile、修改既有文件的严重错误规则与 diff-check 通过；guard 当前内容已有 15 项纯测试通过。本轮未生成额外小模型、网格、PDE 或因子，也未运行全仓测试或 CI。[精确命令及源码文件 hash](outcomes/records/v7_prelaunch_interface_tests.json)。

实际输入解析、轴与完整/active 模式 metadata 核对见[启动合同](outcomes/records/v7_axis_mode_runtime_contract.json)：输入 `b914ec77ed991aa1bf0c0ae95ef89426a3798045bb33742a2443f993ed73502d`，resolved `4f9bd532ac2e7034ef28784cfd085f75b5419a190870a0c78d231a849128b24f`，physical `d394308fe4dfcc8e0c25cdaa707fb8ff4bf4a394c268a8702b4afa069b78681a`。实际 FE 网格 QA 和容量仍待正式 setup。
