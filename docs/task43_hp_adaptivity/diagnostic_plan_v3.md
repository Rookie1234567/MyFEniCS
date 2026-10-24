# Task43 V3 有限整改与 q 诊断计划

本计划只冻结 Task43 V2 review 第 10 节允许的两项有限 q 诊断和相应留证整改。完整 machine contract 在 [`outcomes/records/diagnostic_plan_v3_contract.json`](outcomes/records/diagnostic_plan_v3_contract.json)。V3 代码显式 opt-in；旧 V1/V2 结果、合同、失败记录、accepted9 选择和 production 默认均保持不变。

q19/q32 增加体积分和入射/端口积分所用的采样点，用来检查积分近似是否影响当前离散结果；同因子额外回代复用已分解矩阵，检查求解误差对输出的影响，代价是额外计算并让大型因子在恢复输出和采样期间继续占内存。这些检查不改变网格，不能证明网格精度或连续解收敛。

## 固定额度、顺序和停机条件

此前已正式 dispatch 三次：A1_q attempt1、A2_q attempt1、A2_q attempt2；三次均为工程启动/运输失败，未形成可资格化端点。V3 最多新增 A1_q attempt2 一次和 A2_q attempt3 一次，故最多 5/6。旧 A1_R 槽只转给 A1_q2，旧 B 槽只转给 A2_q3；A1_R、A2_R、B、C 均保持关闭，C 槽封存，未用名额不再分配。任何 worker dispatch 都耗用唯一名额，网格前失败、ABI/预检失败、资源停止或计算失败均不能自动重试。

| 分支 | 唯一允许的新诊断 | reference → test | 计划空间及 FE | 当前门 |
|---|---|---|---|---|
| A1 | A1_q attempt2 | 原 R10 q15/q28/R13 → 同 R10 空间 q19/q32/R13 | Task43 variable-p、180 cells、全 p6，FE 118800 | 等待 G0–G4 独立复核和该分支 READY |
| A2 | A2_q attempt3 | 原 Y6_1 native P6 q15/q28/R13 → 同 native 空间 q19/q32/R13 | 576 cells，FE 380160=`120960 trace+259200 interior` | 等待 A1 终态、G0–G4 独立复核和该分支 READY |

两项均保留各自的正常 correction 策略、R13、MUMPS/原 native route、独立 A6、残差和物理门。A1 正常 correction 固定一次；A2 仍采用 native `max_same_factor_corrections=2`，最多两次常规修正，记录实测次数。每端点最多再做一次独立 extra correction，必须严格区分 normal 和 extra；主 q 比较用正常修正结束、extra 开始前的场，不从两场中挑较好者。

原冻结硬门及输出扰动门不放宽：完整 active transformed residual≤`1e-8`、返回的凝聚系统 residual≤`1e-9`、独立原方程 A6≤`1e-8`、能量闭合≤`1e-5`；端口和体输出沿用 V2 各逐项值、四组复幅和全/散射 E/H/G 的 floors。normal correction 和 extra correction 的原向量、同 RHS 范数及 factor 计数由 raw evidence 核验，不只信 status 标签。q8 是稳健性副比较，q10 是主要比较；不做相位拟合。

## primary 留证和异常关闭

primary 状态在正常 correction 后立即封存、在 extra 前形成。A1 与 A2 都保存同一已算出来的系数/空间身份、完整 RHS、解和残差、独立 A6、凝聚 residual、normal correction 及计数；不为留证重新组装或求解。每完成 q8 或 q10 采样，就立即原子保存独立样本文件与 SHA；采样失败时，已完成样本和 primary 包仍可读且字节不变。

A2 的 primary R13/Av 输出和每阶样本在 extra 前生成；A1 在 extra 前封存 primary 核心包并及时写出已完成的 q8/q10 样本，而 A1 R13/Av 仍沿用现有 same-LU recovery/output 顺序。额外回代、广播、恢复或采样发生异常时，端点被标记 `FAILED/INCOMPLETE`、数据为 `measured/partial`，完整 run summary 和 Task43 endpoint authority 均降为非 official、非 pass，所有后续 continuation=false。A2 对 native runner 返回后的 summary 写入、比较和再次写盘整个后处理范围使用同一个 fail-closed 守卫；这避免只保护比较器却留下 official summary。两个 route 的测试均注入实际 callback 失败并重读磁盘包核 SHA。

留证和 primary 输出在同一个已经分解的 MUMPS 因子仍存活时完成。因此 V3 的同时 RSS 峰值和 whole-watchdog wall 必须实测，不能借用旧的“先释放 factor、后输出”生命周期估计。发生异常不覆盖历史 attempt，也不把部分结果回填为旧尝试的 pass。

## quadrature 与 `A_volume`

旧 Y6_1 配置是 automatic，并非历史显式 q15。root 已对同一 hash-bound Y6 场完成纯后处理：automatic 和 q15 的 `A_volume=0.6915175267821607`，q19 为 `0.6915175267821573`，最大绝对差 `3.4416913763379853e-15`；当前 FFCx 对吸收积分的实际 automatic degree 为 15，独立常数区域体积积分 degree 为 3。证据副本为 [`old_y6_av_support__old_y6_av_three_rules.json`](outcomes/records/v3_root_pre_pde_audit/old_y6_av_support__old_y6_av_three_rules.json)（SHA256 `6f9835c893ac2b3ab8b39aeb1297ea0968667c336bc1e4179bf74fa738bb87dc`），watchdog summary SHA256 `a4716977b1129986dca673ff4071d50ee2c7fd25ec39ab8ce9acf1128a1bd708`。这只是旧场积分复核，不改写旧配置或端点。

A1 同空间配置的 `stage4_volume_quadrature_degree=19` 会由现有吸收积分代码转成 UFL quadrature metadata；新端点应记录已解析配置和实际逐材料 `A_volume`，没有独立输出的 form metadata 时不声称已实测它。A2 native opt-in 将 q19 实际送入物理 volume forms、独立物理 action 和凝聚使用的同一 form，并把 incident/port q 设为 32。A2 的 `recover_p0_outputs` 体吸收积分仍读取 native 配置中的 `stage4_volume_quadrature_degree`；该入口保持 automatic，不能把 volume-form override 误写成 `A_volume` 的显式 q19。当前 qualified FFCx 对旧场 automatic 吸收积分实际采用 degree 15，这是同一 hash-bound 旧场的支持性观察，不是新端点的 form metadata。A2 新端点应记录 cfg automatic 状态、`A_volume` 实测值，并将 effective degree 标为沿用旧场支持证据/未在新端点单独测量。

## 前置 Gate 和可复用实证

合同中的 G0–G4 逐门独立复核。根已完成的 G0 目录审计、三次正式失败的资源/源码/输入重核、G2 watchdog tiny-child、G3 原场比较/模式和 Av 复核均引用既有 raw audits；执行端不重跑这些读取和后处理。引用只证明审计中明确覆盖的范围，不会替新代码或新 solver route 取得资格。

| Gate | 固定证据及范围 | 当前状态 |
|---|---|---|
| G0 | [`v3_root_pre_pde_audit/index.json`](outcomes/records/v3_root_pre_pde_audit/index.json) 及其 byte-identical 原件副本；全 Task43 dispatch 枚举、三个实际 terminal、source/input 和资源字段 | root 已完成；hash 见 machine contract |
| G1 | 本轮真实 primary-before-extra、已完成样本立即落盘、广播/extra/sampler/后处理故障注入和端点 authority demotion | 需最终 focused 结果及 root 独立源码审查 |
| G2 | [`g2_watchdog_cli_component.json`](outcomes/records/v3_root_pre_pde_audit/g2_watchdog_cli_component.json)：真实 watchdog CLI、绝对 phase 路径、父 PID、WorkflowLedger、cleanup、CPU/ABI/thread 和 dynamic capacity 公式；另由 A2 adapter fixture 实际走 attempt3 CLI 到 fake native boundary，不创建 mesh | 通用 watchdog 组件已通过；A2 fixture 待最终日志/root 复核 |
| G3 | [`g0_g3_frozen_comparison_inputs.json`](outcomes/records/v3_root_pre_pde_audit/g0_g3_frozen_comparison_inputs.json) 和 [`g3_saved_mode_physics.json`](outcomes/records/v3_root_pre_pde_audit/g3_saved_mode_physics.json) 绑定旧解、完整 612 模态和 q8/q10 同点场；[`old_y6_av_support__old_y6_av_three_rules.json`](outcomes/records/v3_root_pre_pde_audit/old_y6_av_support__old_y6_av_three_rules.json) 绑定旧场 auto/q15/q19 积分 | root 已完成，复用列明的 bounded evidence |
| G4 | 固定 contract/plan 字节、最终源/test hashes、实际 argv 与唯一 artifact 根、Scoped tests、动态 CPU1/ABI/resource preflight、root 独立 READY | 本计划和源码冻结后由 root 独立审；目前没有任何 READY |

阶段 1 的导入/collection、SLEPc 环境 blocker 和已通过组件证据保留原范围；V3 的新增 native opt-in 不继承旧 66-file overlay closure 或旧 PDE 资格。不要运行整仓 pytest 代替本次 targeted Gate，也不为本次整改重跑正式 PDE。

## 环境、输出和精确 worker argv

每次 dispatch 前都要用原资格化入口 `source scripts/activate_task40_phi90_pord64.sh`，在 host 检查当时 CPU1 affinity/占用、没有正在运行的 Task43 worker、MPI=1、math threads=1、native marker、Python/PETSc `complex128/int64`、MUMPS，以及实际 available/total memory。不得干扰其他用户任务；CPU1 合同不变。使用 `task43_hp_adaptivity_resource_v1` 按当时内存计算 reserve、launch cap 和 planning cap；同时 process-tree RSS 硬上限 192 GiB，task VmSwap=0，whole watchdog 每项最多 7200 s，绝不延长。preflight 或容量门失败时不得进入 runner；dispatch 后任何失败均不重试。

以下是 contract 冻结的 worker argv，不是 dry-run 命令。完整 watchdog 外层命令、环境变量、绝对 phase 路径、supervisor 父子关系和 detach 组织另见 [`diagnostic_plan_v3_launch_preparation.json`](outcomes/records/diagnostic_plan_v3_launch_preparation.json)。路径唯一：A1 `benchmarks/artifacts/task43/v3_diagnostics/A1_q_attempt2/`，A2 `.../A2_q_attempt3/`；均要求此前不存在，runner 输出固定为各自 `run/`，supervisor/watchdog 位于各自 `watchdog/`。正式启动还必须由 root 对相应 phase 单独写 READY、完成新鲜动态资源/ABI preflight，并保持所有源码和输入 hashes 匹配。

**A1_q attempt2：**

```text
python -u -m benchmarks.task43_hp_adaptivity.h100_anchor --case round1_candidate_mpi1 --run-root /home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v3_diagnostics/A1_q_attempt2/run --candidate-plan /home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/round10_p_only_authority_attempt1/plan_output/plans/round10_p_up.json --candidate-id round10_p_up --candidate-acceptance-contract /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json --candidate-parent-selection-record /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json --same-lu-solve-residual-correction --direct-factor-backend mumps --same-lu-tightening --v2-diagnostic-phase A1_q --v2-contract /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json --v2-contract-sha256 33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc --v3-failure-evidence --v3-contract /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json --v3-plan /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/diagnostic_plan_v3.md
```

**A2_q attempt3：**

```text
python -u -m benchmarks.task43_hp_adaptivity.a2_native_p6_diagnostic --phase A2_q --attempt 3 --v3-contract /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json --v3-plan /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/diagnostic_plan_v3.md
```

root 的 phase READY 及完整 watchdog identity、worker argv、source/input 前后 hash、terminal、peak resource/swap/cleanup 必须保存在相应 attempt 根；不允许测试 fixture 触碰正式目录。

## 结论边界

五项能力继续是空间 `PARTIAL`、选择 `PARTIAL`、精度 `NOT_PASSED`、同精度全过程成本 `NOT_ESTABLISHED`、迭代 `NOT_RUN/NOT_QUALIFIED`；0.7 nm 未运行。完整合并仍 `NOT_APPROVED`。G0–G4 审核和对应 root READY 只允许各自一次 q 诊断 dispatch；运行后的完整端点、q 和 extra 门决定该端点资格，即使 q 通过也不自动解锁 R、B、C、cost campaign 或 iteration。
