# Task40 V10 执行回应

## 结论

V10 已实际运行 B0 候选与边界工作；本次文档收口未追加 PDE 或数值求解。

- A 有限边界诊断及 p4 上下边界控制通过；p6 top/bottom 误差均高于门限，保留为受控负结果。
- A 的 V1 完整边界复核未资格化；V2 补齐底部产物但不改变 p6 负结果。
- B0 p6 周期逆算子分量检查通过，不代表整体物理模型已资格化。
- B0 p6 线性求解残差通过，能量闭合门失败，因此没有 official R/T/A。
- 按 Review V10 §5，C 为 `HELD_NOT_RUN`。原 50×25×140 nm 目标仍为 `NO_GO`、未资格化；这不表示数学上不可能。

未运行项保持 not_run，工程失败与数值失败分开；负结果和原始产物均予保留。

## 窗口和源码身份

| 项目 | 记录 |
|---|---|
| Review base（Git SHA） | `d15554af7da49040565dab015dc09a16c1b18dde` |
| 最终源码冻结（Git SHA） | `a4ac46a8d796f9c101a0b4b9364bf01e9101dd50` |
| Campaign 起点 / 固定截止 | `2026-10-05T02:22:47.493693330Z` / `2026-10-06T02:22:47.493693330Z` |
| 固定窗口 SHA-256 | `0052698cbfd8034c82f1c471b1f2ed29a2cb2e5f7601d317166f251e0c7e794a` |
| A 程序末预算快照 | seq `25175`；累计保守计费 `63514.15687973229 s` |
| 提交前收口快照 | seq `25176`；累计保守policy charge `67613.8129036653 s`；收据`benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl/supervisor_v10_precommit_closeout_receipt.json` SHA-256 `f813029a331c50e2079e6f63cb64301c2315c352c543a6f19137f881c5c4aa9d` |
| V9 总 expense | `UNKNOWN_NOT_SETTLED`，沿用原状态 |

seq 25175 是 A 程序结束时的历史预算快照；seq 25176 是上述提交前收口快照，收据保存在 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl/supervisor_v10_precommit_closeout_receipt.json`。待执行的 commit/push 仍沿用同一 campaign 窗口继续计费；不重置账本，也不把提交前快照称为最终结算。两项累计值都是 campaign policy charge，不是 PDE/有限元运行时间；V9旧总费用继续为 `UNKNOWN_NOT_SETTLED`。最终源码冻结 SHA 不替代各 run source：

| 运行对象 | Git run source SHA（40位；非 SHA-256） |
|---|---|
| B0 p4 控制 | `cd9716dd3cb950c72b70487e7aa537d3b7381581` |
| B0 p6 物理候选 | `c439ed40768de4745131b43fc0312bb8be8d9d50` |
| 保存输出恢复 | `f9a64e025e0656f5863bcc5367602a74f1806520` |

## A：边界与局部 p6

原始 A 目录：`benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl/w1_v10_a_20261005T185348Z`。原始保存场含 88 个数值数组，NPZ 为 `46608954 B`；producer report、checker 和数组均保留。原 worker/report 的 p4 top 结果通过；旧 checker 因 32,060/16,030 通道数混淆误判 p4 top 为 FAIL，原 FAIL 保留。V1 recheck 后纠正为 PASS；p6 top 仍 FAIL，q60 见证通过，原始 bottom 未运行。

V1 frozen-scale recheck 位于上述目录的 `w1_v10_a_extension_checker_recheck_v1.json`，SHA-256 为 `9626b1500e0b2c6eebadcb2dca31ae88b0438848391a67d549b9f29c7aba63c5`。冻结q60旧compact入口[`review_v10_boundary.json`](outcomes/records/review_v10_boundary.json)在Git SHA `a4ac46a8d796f9c101a0b4b9364bf01e9101dd50`中的blob为`7420124f261d8bc638254d7fedc2db4501987e9b`，文件SHA-256 `1c619be21ec6ef0c757916fdeac0fa7a5863718beb0c3fd8f4068d3173895cec`；更早V9历史记录亦保留。saved_q60_apply分母`5118.679535729753`、relative action error `9.063390130105725e-15`和n0最大逐模相对值`3.3410810842083564e-15`均保留。q60 有限保存动作和 per-mode 门通过，5 类有限 q60 见证均通过，包括真 n0 见证及高精度解析/直接矩对照。旧 q30 最差误差 `5.705909332721303` 高于 `1e-10`，但该 q30 负结果不自动否决 q60。

完整 A 仍未资格化，当前失败原因是 p6 已知内部场恢复门未通过；A代表类的完整 32,060 个 B/D 行见证、通用复数输入和非零端口 RHS 已覆盖；这不是 B0 全局逆算子的 B/D 逐行资格。完整浮点定理是边界限制，不是 V10 前置门。旧 q30 负结果不自动否决已通过的 q60；旧 checker 的 p4 top FAIL 也已由新复核纠正，不能回写或删除旧记录。

V1 底部续算因 `output/watchdog` 目录已存在而被 runner 拒绝，数值底部工作未开始。这是输出目录守卫触发的工程失败。耗时 `22.413856058 s`，tree RSS 峰值 `716390400 B`，cgroup 峰值 `742473728 B`，swap 为 0，后代已清理。

V2 底部续算状态为 `BOTTOM_CONTINUATION_COMPLETE`，复用原数组、不重算 q60/top；保存 166 个数值成员，NPZ 为 `73103486 B`。

| 检查 | 已知内部场恢复前向相对误差 | 门限 | 结论 |
|---|---:|---:|---|
| p4 top | `4.071005827429115e-13` | `1e-11` | PASS |
| p4 bottom | `3.318404914520256e-13` | `1e-11` | PASS |
| p6 top | `2.202932653970648e-11` | `1e-11` | controlled negative |
| p6 bottom | `2.42442721473547e-11` | `1e-11` | controlled negative |

V2 watchdog `83.070806061 s`；tree RSS peak `744566784 B`，cgroup peak `928624640 B`，swap 0，322 次采样且后代已清理。p6两侧超限值是已知内部场恢复前向误差，并非原方程残差；原方程残差门`≤1e-10`通过。checker 的总体非通过由 p6 负结果造成，不抹除 p4 两侧通过。证据入口为同目录的 V2 report、checker、watchdog 记录及 `outcomes/records/review_v10_boundary.json`。

## B0：周期逆算子和物理候选

候选模型为 4×4×5 单元网格、真实三维两单元 void、y 方向四个 q 分支；没有证据支持删除任一分支。这里只在 preconditioner 背景中填回缺口，用四个 y 相位分支的完整 p6 准确 LU 为真实三维缺口 target 提供修正方向；target 与 RHS 保持不变。四个 factor 同时保留，并完整恢复 36,000 个内部未知量，带来额外内存和 setup 成本；三步求解残差通过仍不代表物理能量门通过。A 的 q60 是边界积分分辨率，B0 的四个 q 是 y 周期相位分支，二者不是同一指标。

| p6 周期模型规模 | 数量 |
|---|---:|
| 全端口通道 | 532（top 266、bottom 266） |
| 存储 / 独立行 | 55,950 / 52,992 |
| 内部 / trace 行 | 36,000 / 16,992 |
| 各 q 增广 trace+port 行 | 4324、4400、4400、4400 |

通用 RHS、36,000 个内部行、全模态端口 RHS、物理规则 RHS 的逆算子分量检查均通过。记录中的 q 真残差最大 `7.493923678060789e-12`（门限 `1e-10`）；regular reference 问题的抽样原方程残差最大 `1.465060265308628e-11`，低于 `1e-10`。这不是 B0 缺口 target 的原生 A6 残差；后者为 `1.6089791915820923e-8`。这是分量级证据，不是整体物理模型资格化。详见 `outcomes/records/review_v10_p6_inverse.json`。

p6 输入 `input/task40extra_0p7nm_engineering/b0_p6_y_orbit_reference_v10.dat` 的 SHA-256 为 `2f7e9cf51a3d1ecc73e5cb6f670bac32f769584bda11d778dbeaee5be6562780`；物理模型 SHA-256 为 `250c26f25d85c0ff68abb0454a6c7640bf8d3af3e6f96bbf599a8cf7c925ae73`。

| B0 p6 求解量 | 实测值 | 判定 |
|---|---:|---|
| KSP 迭代 / reason | 3 / `2` | — |
| 显式 true residual | `1.6089774391665316e-8` | `<1e-6`，PASS |
| 释放后原生 A6 witness | `1.6089791915820923e-8` | `<1e-6`，PASS |
| 纯 `ksp_solve_phase` | `4.899454752 s` | KSP 阶段计时 |

regular reference 问题的原方程残差已通过（抽样最大值 `1.465060265308628e-11`，低于 `1e-10`）；这不同于 B0 缺口 target 的原生 A6 残差 `1.6089791915820923e-8`，也不同于已知内部场恢复前向误差。保存输出恢复后的能量闭合误差为 `6.581916436299018e-5`（门限 `1e-5`），吸收一致性误差为 `6.581916436306369e-5`。因此 `official_result=false`，不能把以下值作为 official R/T/A：

| 诊断量 | 数值 |
|---|---:|
| R / T | `0.984273608092677` / `0.014174698896746551` |
| A_balance / A_volume | `0.0015516930105763937` / `0.00148587384621333` |

能量门失败是 C 按 Review V10 §5 保持 `HELD_NOT_RUN` 的原因；详见 `outcomes/records/review_v10_physical_comparison.json` 和 `postprocess_recovery_record.json`。

p4 控制求解同一个 p6 target，区别仅在 preconditioner。它迭代 2048 次，KSP reason `-3`，A6 true residual `0.966131083707469`（限值 `1e-6`），KSP-only 用时 `1519.454145885 s`。它不是已资格化的匹配性能对照，不能据此声称 p6 更快。

## 成本、资源与工程修复

| 工作项 | 已知耗时 | 资源 / 状态 |
|---|---:|---|
| p4 控制全 worker | `1646.287435149 s` | tree RSS `2377383936 B`；swap 0；残差门失败 |
| p4 控制 KSP | `1519.454145885 s` | KSP-only phase |
| p6 B0 worker 全流程 | `1051.699122267 s` | tree RSS `3713953792 B`；cgroup `4101464064 B`；swap 0 |
| p6 纯 KSP phase | `4.899454752 s` | 3 步，residual 门通过 |
| p6 父级 solve phase | `6.441171838 s` | 包含外围动作，不称纯 KSP |
| 保存输出恢复 | `33.431334133 s` | tree RSS `1193611264 B`；cgroup unknown |
| A 原始 W1 worker | `57.269548678 s` | worker elapsed；不等于 supervisor wall |
| A 原始 W1 watchdog | `71.495064558 s` | tree RSS `762998784 B`；cgroup `916602880 B`；swap 0 |
| A V1 目录守卫失败 | `22.413856058 s` | tree RSS `716390400 B`；数值底部工作未开始 |
| A V2 底部续算 | watchdog `83.070806061 s` | tree RSS `744566784 B`；cgroup `928624640 B` |

恢复子阶段为 restore `7.318348325 s`、native build `3.301424436 s`、operator rebuild `3.401562392 s`、output `20.304540596 s`、native `0.463208863 s`、checker `0.018299836 s`；watchdog `33.397827992 s`。子阶段不与全流程时间或彼此重复累计。

p6 worker 在输出阶段因缺少 `pyvista` 以 exit 4 结束，原分类 `WORKER_FAILED` 保留。后续恢复读取已保存数据，但恢复发现的物理能量门失败也须保留。

三个更早工程前缀耗时为 `1198.994 s`、`1029.516 s`、`1093.389 s`；阶段归属 unknown，不并入物理求解时间。setup 子边界、native factor allocated/used 和分阶段时间均为 unknown，不从父子时长差推断。

释放后 inventory `used/peak=0` 只说明采样时对象已释放，不能代表求解中四个 q 分支的并发 factor 内存。tree RSS、cgroup peak、factor allocated、factor used 是不同口径，不得互换。

## 未运行范围和证据入口

本轮未运行 C/Gx560、完整 15,232 单元模型、自动全尺寸路径，也未完成完整 cold-flow 端到端资格化。仅原尺寸 A 链的 global MPC/target-scale mapping 为 `not_run`；B0 小模型已有 native/MPC 身份。以上未运行项不是数值失败。50×25×140 nm 目标仍为 `NO_GO`/未资格化，结论仅是本轮未取得达到目标门槛的证据，不能外推为其它实现或资源条件下不可计算。

分类须区分 `measured`、`derived`、`not_run`、`failed` 和 `controlled_negative`。求解残差通过不等于物理能量门通过；分量逆算子或有限边界通过也不等于整体模型通过。源码或数值核心若变化，对应 evidence 可能失效，应按任务合同重跑相关 anchor。

测试记录按源码版本分列，不合并计数：原 A 源码 `45a388fa12afb69a29afaa0240a72018a0069967` 的 44 项测试；checker 源码 `b2c5ae94ebec1394e4b659dd6b8aef26866b5b38` 的相关代码/checker 30 项通过（2.96 s）；源码冻结 `a4ac46a8d796f9c101a0b4b9364bf01e9101dd50` 的输出目录守卫 fixtures 3 项通过（0.52 s）。相关 Python 编译及文档空白检查通过；这些是本地定向检查，不代表全仓库 pytest 或 CI。本次文档收口未新增数值测试或 PDE。

主要证据入口：

- A 原始与 V1 记录：`benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl/w1_v10_a_20261005T185348Z`；
- A V2：`benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl/w1_v10_a_bottom_continuation_v2_20261005T195949Z`；
- B0 p4/p6：`results/task40extra_nonseparable_0p7nm/` 下对应 `b0_p4_balh_control_v10` 与 `b0_p6_y_orbit_candidate_v10`；
- B0 输出恢复：p6 run 目录中的 `postprocess_recovery_record.json`；
- compact 证据：`outcomes/records/review_v10_boundary.json`、`outcomes/records/review_v10_p6_inverse.json`、`outcomes/records/review_v10_physical_comparison.json`、`outcomes/records/review_v10_cost_and_repairs.json`。

未知值保留为 unknown 并绑定证据来源、单位和口径；campaign policy charge 不属于求解耗时，诊断 R/T/A 不属于 official R/T/A。
