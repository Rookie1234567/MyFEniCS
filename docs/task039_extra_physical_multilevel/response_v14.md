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

## 6. 2026-09-12 用户补充授权与续算身份

第1–5节保留上次停止时的结论和限制。其后文档与证据已推送至同一 `task39extra` 分支，远端和本地一致的续算 base 为 `07b77c49e65f725f2b8bf00189777ef7f833f1c2`；第5节的外发阻塞是历史状态，用户明确允许后已解除。本次按下列用户补充授权继续现有诊断，不改写 Review V13 或追溯改变旧停止分类。

> 本条作为Review V13的用户补充授权：请在task39extra分支补齐现有p4方向诊断，不再另开PC试验。本批仅将“新增诊断数组与工作区”上限从256 MiB一次性调整为512 MiB（536870912 B），通过显式配置贯穿检查和记录；2.5 GiB局部因子库存、原临时预留、整机reserve、process-tree watchdog及zero-swap要求全部不变，不允许无上限运行，也不追溯改判旧停止结果。先消除明显的重复数组、释放不再使用的metric对象，并核对包括QR/SVD临时副本在内的保守工作集；只做必要修复，不开发新的通用内存审计平台。必须调整保存顺序：P1、P2完成后立即原子保存完整向量、恒等式、计数和时间，再进入P3，避免中途停止丢失已完成证据。复用01已保存且身份合格的Z/AZ等结果，仅补缺失或受修复影响的项目，然后顺序完成冻结的A2R160/01、A2R160/02、LIGHT448/09；正常路径最多一次必要的fresh宏块构建，复用到全部输入完成，不重做未受影响的ABI、MUMPS和metric资格检查。保持最多48列、原四步I4及原动作预算，不新增全局参考、不扩rank/步数、不补R64、不启动p6长跑，不影响5nm线；正式预算累计既有费用、不清零或自动延期，工程修复时间单独记录。最终补齐三输入的actual、best-Z、scaled-Z、best-L、selected-L10之残差/场误差/旋度，以及C_U—局部响应—反馈分解，按V13交付一个有证据支持的优先改进方法和可执行蓝图；证据不足须指出具体缺口，不强行宣称已选出有效PC。将本条授权、续算身份、资源及结果追加到response_v14和对应outcomes/decision/blueprint，保留旧负结果，提交并推送同一分支后统一等待ChatGPT审核，不合并master。

| 续算合同 | 明确边界 |
|---|---|
| 新增诊断数组与工作区 | 本批显式配置 `536870912 B`；旧 `268435456 B` 停止仍为旧负结果 |
| 其他资源 | 局部库存 `2684354560 B`、临时预留 `1073741824 B`、原 reserve/watchdog/zero-swap 均不变 |
| 既有正式费用 | 两次运行 `948.1497426901994 s` 加两次只读复核 `6.4 s`，已知累计 `954.5497426901994 s`；新费用继续累计到原 `7200 s` 上限 |
| 复用边界 | 01 的合格 P1、Z/AZ、42 个局部响应及其 A 像按原 hash 复用；补缺项须单列实际作用与成本，不重复调用 01 I4 |
| 完成边界 | 本次续算结果及独立审核尚待记录；授权本身不构成数值或资源通过 |

本节记录用户原文及实施合同；后续实际 source、输入、工作集估计、P1/P2保存身份、动作账、三输入结果和方法决策须由新证据追加，不能使用授权替代测量。

### 6.1 续算前工程审核

已将 `execution.p4_diagnosis_workspace_cap_bytes=536870912` 接入输入、检查及记录。01 复用包与冻结源码、模型、映射和已提交的 NPZ/P0 JSON hash 直接核对；P1/P2 在 P3 前原子发布。P1 包包含 I4 实际事实和费用，旧未记录耗时仍为 unknown。metric6 不再构造未使用的单元积分基表；L/AL 采用两份按列连续的数组，局部列使用视图，阶段结束释放其拥有者。QR/SVD、最多10列的选择器和 metric/P64 缓冲均进入现有工作集保守检查，没有新增通用内存平台。

主控在允许 MPI 本地 socket 的同一资格化环境运行 `test_410`：10 passed，pytest 1.03 s、外层 wall 1.34 s。其余相关测试14 passed；最后的局部修正后 test_412/packet lifetime 为7 passed。compileall、diff-check通过；Ruff 0.11.13 对12个变更 Python 文件的基线/当前均为82条历史诊断，新增0，不能表述为全仓 Ruff 通过。初次 `python -m ruff` 发现环境未安装该模块，随后复用已存在的资格化本地 Ruff 可执行文件，未安装依赖。

工程协调窗口可确认自执行任务派发 `2026-09-12 04:43:56 UTC` 至主控代码审核 `06:01:53 UTC`，UTC窗口4677 s，包含实现、测试、监督及等待；它不是CPU工时，完整细分工时仍 unknown，并与正式预算分开。具体工程证据暂存于 ignored `benchmarks/artifacts/task39extra/p4_direction_diagnosis_v13/continuation_engineering/`，其中 `root_review_admission.json` 绑定最终实现文件hash、测试日志和本次仅一次构建的准入条件。原正式费用954.5497426901994 s继续计入7200 s；源码准入不构成数值通过。
