# Task39extra Review V13 response：P0通过，诊断部分证据受控停止

## 1. 收口结论

本轮状态为 `DECISION_DELIVERY_INCOMPLETE`，不是 `DIAGNOSIS_COMPLETE_WITH_SELECTED_NEXT_METHOD`，也不是 low-memory solver pass。三输入 P0–P4 没有完成：P0 身份和 metric equivalence 通过，A2R160/01 的 P1 真实右预条件方向和 P3 A-image packet 已保存并独立复核；在第一份输入的 P2/P3 生命周期仍未收口时，监督方基于新增诊断对象账本不完整请求 `USER_CONTROLLED_STOP`。A2R160/02、LIGHT448/09、完整 P2、P3 场/curl 和 official Maxwell 输出均保持 `not_run`。

唯一下一主项是 `IMPLEMENTATION_OR_METRIC_REPAIR`，修复必要性置信度高，生产方法选择仍不可判定。它只修诊断生命周期、checkpoint 和字节账本，不等于选择了生产 PC；具体接口、公式、预算和下一次验证顺序见 [决策记录](outcomes/records/next_method_decision_v13.json) 和 [蓝图](outcomes/next_method_blueprint_v13.md)。

## 2. 正式运行证据

正式 source 为 `e46fec48dc073a745e9b7e6c9186a147aefbc0a0`，物理模型和 ordered mode hash 分别为 `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` 和 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。三份冻结输入为 `A2R160_BAL_H_p4_01`、`A2R160_BAL_H_p4_02`、`LIGHT448_BAL_H_p4_09`。

首次 source `80d2fb35145ac4770040ec9bb4627dfbe8cc7e67` 的失败保留为负证据：direct mass 已完成一次，随后 inherited same-mesh P64 owner-row 检查得到 `2.4834738612237617e-09 > 1e-11`；没有 I4/B4，不能改写为数学失败。唯一授权修复重放完成了同一 42-block 构建，P0 metric packet、01 的 P1 packet 和 P3 response packet 落盘后受控停止。首次失败 conservative `355.6892665180153 s`，重放 conservative `592.4604761721841 s`，合计 `948.1497426901994 s`；不再重放。

停止记录的工具分类为 `USER_CONTROLLED_STOP`，leader exit `-15`，后代清场，swap `0`。process-tree sampled RSS peak `3125956608 B` 与 launch cap `9189265408 B` 分开报告；2.5 GiB 是局部库存政策，不把 RSS 写成该 cap 的违规。源码生命周期审计显示 P3 明确对象下界 `273571328 B`，高于诊断新增数组 cap `268435456 B`，且还漏计多类对象，因此诊断资源状态为 `DERIVED_UNCERTIFIED`。

按重放42份块记录汇总，MUMPS allocated 加保守 padding 为1,671,000,000 B，used 加同口径 padding 为888,000,000 B，实际 allocated CSR 为450,499,800 B；完整 C_U 后保守局部库存为2,180,383,916 B，小于2,684,354,560 B。used 没有替代 allocated 参与 Gate。

## 3. 结果边界

P0 direct/pullback mass 和 curl 输出相对差为 `1.8218700611567345e-15`、`2.9122511040234625e-15`；固定 D 有限且为正。01 的实际四列捕获有效秩为 4，重建相对误差 `2.873275164100603e-16`。其 actual 的 `rho/eta/eta_curl` 为 `0.9502310252350668/0.9647147926182198/0.9646390272009856`。

01 中 reference-only best-Z 的 `eta=0.23602989478833247` 但 `rho=126.80492969347596`，所以不能说这四个方向完全没有场逼近能力；它说明在此四维空间，两种最优目标得到差异很大的修正；未据此断言不存在折中解。固定 Z 的 D 候选 `eta=0.9602831778385792`，相对 actual 的 eta 比约 `0.9954`，没有达到至少减半的 strong-action 条件，故固定 Z 离线筛选为 false；这不否定未来改变搜索方向的 scaled Krylov。

01 的完整 48 列 A-image 残差空间有 derived `rho=0.9358770172082744`、rank 47；固定八个局部方向的 10 列 response-only `rho=0.9678905201139729`、rank 10。两者是原算子 rho，可以复核；因为 `a/t` 与完整 P2 packet 缺失，L 和 selected 的 eta/curl 是 `unknown`，不把这两个 rho 宣称为完整物理候选通过。其余两份输入没有产生方向记录，不能计算 strong-action signal。

主控首次离线复核 wall 为1.70 s；执行窗口复核 wall 为4.70 s。两次正式运行与这两次复核的已知合计为954.5497426901994 s，核心时间已包含于各自 wall，不重复计费。未保存的本次 I4/bare/metric 细分耗时保持 unknown；不以旧 V12 时长替代。

独立 checker 对保存的 01 raw 做 16 项 QR/SVD/残差复算，16/16 通过；核心时间 `1.6693295069999294 s`，外层 `/usr/bin/time` wall `4.70 s`，MaxRSS `198344704 B`，swap 0。审计不是新的 PDE、PC、factor、A4、M0 或 curl action。

工程时间另列：已知执行窗口从2026-09-11 15:28:40 UTC到首次正式运行16:52:42 UTC约5,042 s；首次结束到修复重放开始约514 s。这些日历间隔包含阅读、实现、测试、监督及等待，不是CPU时间，也不是全部工程工时。后续文档/索引收口未逐项计时，记为unknown；工程时间不从正式7200 s预算重复扣除。

## 4. 代码与测试

本轮代码实现了默认关闭的 counted-PC observer、有限维稳定 QR/SVD、非零 `r_ref` P2 image 保存字段、reference-free P3 选择入口和归一化 P0 probe；并修复了 F841 未用赋值和新 runner 的 lambda lint 问题。普通默认路径保持不变。

| 检查 | 结果 |
|---|---|
| `test_412_physical_p4_direction_diagnosis.py` + `test_410_physical_macro_dd4.py` | `16 passed`，qualified complex128/int32 MPI1 activation |
| input `--validate-only` | 通过，`run_id=p4_direction_diagnosis_v13` |
| `python -m compileall -q src scripts` | 通过 |
| split-git `diff --check` | 通过 |
| full repository pytest / CI / 新完整 p6 original/notch 求解 | `not_run` |

机器可读证据：[P4 compact](outcomes/records/p4_direction_diagnosis_v13.json)、[offline audit](outcomes/records/p4_direction_diagnosis_v13_offline_audit.json)、[memory liveness](outcomes/records/p4_direction_diagnosis_v13_memory_liveness.json)。大型 arrays、factor、cache 和 timeline 仍在 ignored artifact root，不进入 Git。

## 5. Git 与后续

本轮 review base 为 `1ebe076df8dc1052c5a7ec5ad3d391957ad6c94f`。没有重建全局参考、扩块/rank/内层步数、补R64或触及5nm线。诊断入口仍未完成资源资格，不能提升为生产默认或取得 merge approval。

正式运行 source clean SHA 是 `e46fec48dc073a745e9b7e6c9186a147aefbc0a0`。其前置实现提交为 `d4ff316aa4d22e5908bb55eab88d8adf26a5feac`、`80d2fb35145ac4770040ec9bb4627dfbe8cc7e67`、`39a9561` 和 `e46fec4`；本轮文档收口另行提交。外部 GitHub push 受当前会话的外发审批策略阻塞，未通过换命令或换窗口绕过；本地 split-git 分支保留全部提交和工作树状态。

只有在新的 review 明确授权并且修复后的完整诊断账本通过 256 MiB Gate 后，才可先验证 01、再继续 02/09；本轮不进入 original/conditional notch 或 official 物理恢复。
