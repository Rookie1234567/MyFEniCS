# Task39extra Review V13 response：历史受控停止与续算当前收口

> 阅读顺序：第7节是本次续算的当前结论；第1–5节是初始 V13 受控停止的不可变历史快照，第6节是用户补充授权及续算前准入记录。旧 256 MiB 负结果、旧 compact packet 和旧失败记录均保留，未追溯改判为通过。

三输入已经完整补齐 actual、best-Z、scaled-Z、best-L、selected-L10 及 P2 分解；两个便宜候选的 strong-action signal 均失败，`PHYSICAL_INTERFACE_MULTILEVEL_REDESIGN` 仅是架构优先项，尚未成为 production PC。

## 1. 初始 V13 受控停止（历史快照）

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

## 7. 本次续算实际结果与当前收口

表内数值按9位有效数字显示，完整精度见续算compact。rho是近似解的原A4相对残差；eta和eta_curl分别是相对匹配参考的无材料质量积分误差和scaled-curl误差。固定scaled-Z重新计权原四个方向的残差；selected-L10从42个局部响应选至多8个，连同a和-t作原残差最小组合，仍须支付全部42个A像的构造费用。

本节是对第6节授权的实际执行结果。续算使用最终源码 `3457b5e2f54dec690fcb70deb1f387fe7f6d57cd`，状态为 `P4_DIRECTION_DIAGNOSIS_COMPLETED` 且诊断 gate 通过；这只表示三输入方向诊断和保存证据完成，不表示 official Maxwell 物理求解、生产 PC 或 R/T/A 已通过。

### 7.1 身份、费用和资源

| 项目 | 实际值与口径 |
|---|---|
| 输入 | `A2R160_BAL_H_p4_01`、`A2R160_BAL_H_p4_02`、`LIGHT448_BAL_H_p4_09` |
| ABI | MPI1，`complex128`，`int32`；p4 独立/存储 rows `48960/53084`，p6 `164592/173802` |
| 模型/ordered mode/input hash | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` / `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` / `86829433e2dd4412b5e6b1e7903255ed33a462dcf5afadffe56efa841e5e7692` |
| 续算正式费用 | 外层 supervisor 保守计费 `1204.47179 s`；worker 原始 clock `1201.56381 s` 仅作 raw diagnostic |
| 构建与输入阶段 | 一次必要 fresh 42-block 构建 `300.807805 s`；01/02/09 分析阶段 `216.48585 / 272.964772 / 272.377783 s` |
| 正式累计 | 历史已计费 `954.549743 s`；修正后正式累计 `2159.02153 s` |
| 续算审计追加 | continuation wall `1.09 s`、block-outside wall `0.17 s`、resource review wall `0.12 s`；截至资源复核累计 `2160.40153 s` |
| 监督状态 | leader exit `0`，descendants cleared，remaining children `[]`，分类 `COMPLETED` |
| 采样资源 | process-tree RSS `3287973888 B`，PSS `3254656000 B`，swap `0 B`；资源复核 `4252` 个样本、`34016/34016` 项通过 |
| 资源边界 | launch cap `9375555584 B`，reserve `4294967296 B`，resource-review 最小 available `10658832384 B`；新增诊断 workspace cap `536870912 B` |

正式费用采用外层 supervisor 口径；`1103.465745 s` 的 boottime workflow elapsed 与 `1204.470328471 s` 的 UTC elapsed 差约 `101.004583 s`，差异原样保留，不能用 worker clock 静默替代。RSS/PSS 是采样的进程树指标，`pswpin/pswpout` 是全局 WSL 诊断，不冒充专用 cgroup 测量。

历史 256 MiB 停止仍有效：旧 P3 liveness lower bound `273571328 B` 比旧 cap `268435456 B` 高 `5135872 B`；本次 512 MiB 是一次性续算工作区上限，不是对旧停止的追溯改判。局部库存也继续分开记录：allocated padded `1671000000 B`、used padded `888000000 B`、allocated CSR `450499800 B`，C_U 后 `2180383916 B`，local cap `2684354560 B`；allocated、used、liveness 估计和 RSS 不是同一指标，不能互相替代。

| 成本比较（秒） | `A2R160_BAL_H_p4_02` | `LIGHT448_BAL_H_p4_09` |
|---|---:|---:|
| 原 I4 基础内核（实测；新尺度化 Krylov 未运行） | `7.43339113` | `7.05866804` |
| selective lower：bare B4 + 42 个 `A p_i` + `A(-t)` + selector | `22.533772` | `22.7700278` |
| selective covered upper：加全部 dense QR/SVD（覆盖 final10 LS） | `22.9368437` | `23.1821034` |

上表只比较已测的嵌套诊断成本；01 的旧 I4/bare packet 细分时长仍为 unknown，不能填零。selective lower/upper 都不是完整未来外层 KSP 成本，fixed-D 的一次向量尺度乘法也未合成虚构秒数。

### 7.2 三输入统一结果

下面每个单元按 `rho / eta / eta_curl` 排列。`actual` 是实际四步 I4 返回的解；`best-Z` 使用参考场作 oracle，只能测量；`scaled-Z` 是固定 dual-mass 缩放；`best-L` 是带参考场的场最优 oracle；`selected-L10` 是不使用参考场的八方向加 `a,-t` 选择结果。它们是 P4 诊断指标，不是 official R/T/A。

| 输入 | actual | best-Z（reference-only） | scaled-Z | best-L（oracle） | selected-L10 |
|---|---:|---:|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `0.950231025 / 0.964714793 / 0.964639027` | `126.80493 / 0.236029895 / 0.338053121` | `1.02418642 / 0.960283178 / 0.960235435` | `86.688459 / 0.213419927 / 0.292679164` | `0.96789052 / 0.992583743 / 0.992554855` |
| `A2R160_BAL_H_p4_02` | `0.101264949 / 0.877757076 / 0.877371768` | `6.39136754 / 0.170914106 / 0.25953131` | `0.165361737 / 0.742969278 / 0.742565056` | `3.16286411 / 0.14613246 / 0.186722965` | `0.173007783 / 0.96992168 / 0.969507771` |
| `LIGHT448_BAL_H_p4_09` | `0.977895241 / 0.992817604 / 0.992802276` | `152.556741 / 0.221237812 / 0.310294927` | `0.997120938 / 0.995016514 / 0.995013927` | `110.065271 / 0.194652922 / 0.266357032` | `0.992461078 / 0.997122877 / 0.997112985` |

为避免把“场最优”与“残差最优”混在一起，compact 中另外保存的 residual-oriented 三元组如下：

| 输入 | `Z_residual` | `L_residual` |
|---|---:|---:|
| `A2R160_BAL_H_p4_01` | `0.950231025 / 0.964714793 / 0.964639027` | `0.935877017 / 0.962653537 / 0.962567851` |
| `A2R160_BAL_H_p4_02` | `0.101264949 / 0.877757076 / 0.877371768` | `0.0951039085 / 0.883431704 / 0.883038825` |
| `LIGHT448_BAL_H_p4_09` | `0.977895241 / 0.992817604 / 0.992802276` | `0.964794655 / 0.991134125 / 0.991113434` |

`best-Z` 的大 `rho` 与较小 `eta` 说明参考场可以作为“场逼近能力”的标尺，但不允许把参考解放进 PC、selector 或 initial guess。`scaled-Z` 在困难输入 01 的 eta 比为 `0.995405190426173`，没有达到至少减半的 hard 条件；因此 fixed-Z strong-action signal 为 false。`selected-L10` 也没有形成 strong-action signal，且它的细分成本不是完整外层 Krylov 成本。

### 7.3 P2 分解与身份检查

`P2_c_ref_zero_initial` 的零初始基线指近似解为 `0`、误差为 `c_ref`，故其 `rho/eta/eta_curl=1/1/1`，不是“参考场残差”。后续 P2 表的 `eta/eta_curl` 是误差 `c_ref-a`、`c_ref-a-d`、`c_ref-a-d+t` 的场/旋度误差；对应 `rho` 则分别来自近似解 `a`、`a+d`、`a+d-t` 的原方程残差。

| 输入 | `c_ref-a` | `c_ref-a-d` | `c_ref-a-d+t` |
|---|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `3.79457109 / 0.930671134 / 0.93065853` | `14.0889637 / 0.920132086 / 0.920020217` | `4.5683427 / 0.848992333 / 0.848835797` |
| `A2R160_BAL_H_p4_02` | `0.204475774 / 0.980973007 / 0.980587899` | `0.452118314 / 0.973784692 / 0.973376101` | `0.193949173 / 0.914617715 / 0.914280712` |
| `LIGHT448_BAL_H_p4_09` | `4.3922676 / 0.931661661 / 0.931677408` | `15.0118944 / 0.922746851 / 0.922690902` | `5.10196078 / 0.858182034 / 0.858122287` |

| 输入 | global `a` mass/curl | global `d` mass/curl | global `t` mass/curl | global `a+d-t` mass/curl | cancellation mass/curl |
|---|---:|---:|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | `12.348341 / 12.746971` | `3.09978418 / 4.85595853` | `11.6599294 / 12.0250054` | `25.2866486 / 25.5794836` | `0.932809418 / 0.86335695` |
| `A2R160_BAL_H_p4_02` | `0.485286352 / 0.751646126` | `0.335790096 / 0.568774661` | `1.48652132 / 1.52530266` | `2.10582078 / 2.20330231` | `0.912559723 / 0.774250326` |
| `LIGHT448_BAL_H_p4_09` | `24.7927491 / 25.5096754` | `5.54755991 / 8.57623536` | `21.9153509 / 22.5606821` | `48.887641 / 49.3810361` | `0.93554729 / 0.871738856` |

每个输入的 P2 初始闭合、feedback、`e_h-A` identity、全局 recomposition、PoU、local solve 和 remainder 检查均在保存包中；连续审计从原始字段独立重算 `219/219` 项并通过。该审计使用保存的 squared norms 检查 curl，没有重新施加 FE curl action；weighted-R field 检查使用保存的 measured metric factorization，这两个限制已绑定到审计日志。


全局重组误差的范数和已有粗修正的 closure 如下。closure 使用原物理粗限制的操作尺度，限值仍为1e-8；C_U不是M0正交投影。

| 输入 | d-e_h 的 M0 / curl 范数 | C_U initial / feedback closure | 局部回代最大相对误差 |
|---|---:|---:|---:|
| A2R160_BAL_H_p4_01 | 104.158699 / 104.295797 | 1.05622e-12 / 8.27729e-14 | 3.94086e-14 |
| A2R160_BAL_H_p4_02 | 18.4150544 / 18.4310214 | 9.46942e-15 / 9.14771e-14 | 1.70875e-14 |
| LIGHT448_BAL_H_p4_09 | 218.057181 / 218.306418 | 1.44038e-12 / 8.38784e-14 | 2.45856e-14 |

表中 cancellation 定义为同一M0或curl范数下 `norm(a+d-t)/(norm(a)+norm(d)+norm(t))`。它衡量向量合成时的抵消，不能解释为原因占比；重叠块范数也不能相加当作全局能量。

### 7.4 结构诊断、动作账与方法决策

结构清点完成：Gamma rows `13092`、I rows `35868`、合法 rows `48960`，coverage defect `0`；42 个 interface blocks 全部存在。shared macro-DOF rows `12108`、nonzero DtN support rows `1152` 有重叠，不能相加当作全局 rows；cross-volume cells/rows `0/0`，DtN entries `80`，coupling/projection NNZ `31968/31968`，最大局部 block `1944` rows。假设把 Gamma Schur 做成 dense matrix 会需要 `2742407424 B`。本批只清点 Gamma/I 结构，没有构造或施加新 Schur 算子；matrix-free Schur 是下一轮蓝图，当前已有资格的 A4 作用不等于新 S 已实现。

block-outside 审计只比较同一 block 内的操作项系数范数，不能解释为全局场能量或百分比。42-block 的 `||chi||/(||R_i A e_h||+||D_i R_i e_h||)` 中位数为 01/02/09：`0.99796865100185 / 0.9840960661566445 / 0.9961730504361788`；对应 `chi_norm` 中位数为 `18.084174988730773 / 4.392058047722505 / 42.93508393478842`，`ell_norm` 中位数为 `5.450596891409682e-16 / 9.69595278950643e-16 / 3.262991626739957e-15`。这是保存向量的 derived diagnostic，不是新 PDE action。

动作账保留旧复用与新测量的区别：A4 total `149`（旧 `49` 加新 `100`）；M0 direct degree4 `2`、pullback `211`；curl direct degree4 `1`、pullback `217`；P64 primal/adjoint `428/428`；I4 attempted/completed `3/3`，bare B4 attempted/completed `3/3`，B4 total `15`，其中 02/09 新增均为 `2/2`。01 复用合格的旧 I4/bare packet，旧细分时长仍为 unknown，不能填零。

因此当前决策为：

| 字段 | 当前值 |
|---|---|
| `primary_method` | `PHYSICAL_INTERFACE_MULTILEVEL_REDESIGN` |
| `decision_status` | `ARCHITECTURE_PRIORITY_SPECIFIED_UNQUALIFIED` |
| `confidence` | `medium`，仅针对 architecture priority |
| `performance_confidence` | `low` |
| production PC | 未选择；official physics `not_run` |
| fixed dual-mass strong-action | `false` |
| selective-L10 strong-action | `false` |

蓝图的具体下一步是：用 actual complex physical local Schur singular directions 加 nonzero DtN bilateral channels；每 patch 最多 `8` 个 verified directions、包含 verification 的等价 augmented actions 最多 `64`，最多 `32` 个 work vectors、每 patch 最多 `2048` rows，形成 `P^H S P`，用一个 fixed Vcycle，bottom 最多 `512` rows 且 allocated 最多 `64 MiB`；若超过则最多聚合 `8` 个邻居，不能严格 reduction 就停止。完整接口 PC 记为

```math
B_{4,\mathrm{new}}g=C_Ug+(I-C_UA_4)F_{\mathrm{interface}}(I-A_4C_U)g.
```

其中 `F_interface` 是“局部消元—固定 Vcycle—恢复”的接口 Schur 算子，本身不包含外包的 `C_U/A4`；每次动作除 `F_interface` 首层最多 `168` 个内部回代外，还必须计入 `2 C_U` 和 `2 A4` 的逻辑作用；`168` 不是完整 B4 action 总数。已有 P2 的 `8192` rows / `512 MiB` 限额不能增长。这些都是下一轮 review 的 proposal，尚未实现或性能资格化。

### 7.5 证据入口与交付边界

当前 compact、三份独立审计及 provenance 已按最终 source SHA 绑定：

- [续算 compact](outcomes/records/p4_direction_diagnosis_v13_continuation.json)
- [219 项 continuation audit](outcomes/records/p4_direction_diagnosis_v13_continuation_audit.json) 及 [日志](outcomes/records/p4_direction_diagnosis_v13_continuation_audit.log)
- [block-outside audit](outcomes/records/p4_direction_diagnosis_v13_block_outside_audit.json) 及 [日志](outcomes/records/p4_direction_diagnosis_v13_block_outside_audit.log)
- [resource review](outcomes/records/p4_direction_diagnosis_v13_resource_review.json) 及 [日志](outcomes/records/p4_direction_diagnosis_v13_resource_review.log)
- [统一 provenance](outcomes/records/p4_direction_diagnosis_v13_continuation_provenance.json)
- [当前 decision JSON](outcomes/records/next_method_decision_v13.json) 与 [下一方法蓝图](outcomes/next_method_blueprint_v13.md)

记录的 targeted tests、packet-lifetime tests、compileall 和 diff-check 通过；全仓 pytest、CI、official p6 Maxwell、生产 PC qualification 和 `F_interface` 性能 qualification 均为 `not_run`。旧 compact [p4_direction_diagnosis_v13.json](outcomes/records/p4_direction_diagnosis_v13.json)、旧 256 MiB liveness 和旧失败/受控停止证据继续保留。因而本轮已经完成“诊断收口 + 有边界的下一方法蓝图”，但没有完成“有效 production PC 选择”或“物理结果交付”。

### 7.6 主控最终文档检查与历史缺件

最后的文档/模型登记合同测试为20 passed、1 failed：旧Task038的 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2_checker.json` 缺失。主控从正式源码3457b5e的修改前登记表复查，失败完全相同，新增错误0；没有修改其他任务或伪造缺件。见[日志](outcomes/records/p4_direction_diagnosis_v13_documentation_tests.log)和[基线对照](outcomes/records/p4_direction_diagnosis_v13_documentation_baseline.json)。这属于文档工程验证，不是新PDE、PC、ABI或数值资格化；正式诊断费用仍为2160.401528466149 s。诊断本身与资源复核完成，完整新PC仍未资格化，等待ChatGPT统一审核，不合并master。
