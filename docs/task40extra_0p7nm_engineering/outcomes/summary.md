# Task40extra 结果总结：0.7 nm 非可分三维 Maxwell 工程起步

> **2026-09-30 续算更新：** 用户已直接批准主控修复 Task40 续算入口。前述两次 G0 失败和 91.79305701722132 秒成本保留；本次仅增加一个绑定旧账本、输入和真实实现失败的 G0 attempt。字段修复已通过针对性检查，新增 4 项纯 mock/账本测试通过；正式续算尚未启动，未取得新数值结果。原数值/资源安全 Gate 不变，后续按原 N0–N6 条件执行。授权见 [增量记录](records/g0_user_authorized_continuation_v1.json)。下文失败收口为此次授权前的历史状态。

## 1. 最终状态

| 项目 | 结果 | 数据身份与边界 | 证据 |
|---|---|---|---|
| 首批官方目标 | **未得到** 0.7 nm、非可分三维 p6 完整 FE 解 | `official_0p7nm_nonseparable_p6_result=false`；不是数值不收敛结论 | `records/phase_I_results.json` |
| G0 / N3 | 两次 `WORKER_FAILED`，第二次使用唯一获准的实现错误重放；额度已耗尽 | 两次都是实现异常，未到外层 KSP、完整真残差或 official R/T/A | `records/g0_startup_bug_replay.json` |
| 最终代码 | `59bad0d977f0e23555098d923a95afbf2e9f5bf4` | 修复 G0 同网格层包装器丢失的矩形空气缺口审计字段；只有组件 fixture 证据，没有修复后 PDE 证据 | 同上；`records/run_index.json` |
| G1 / N4 | `not_run` | G0 没有合格解，且实现错误重放额度已耗尽 | `records/run_index.json` |
| G0 direct / N5 | `not_run` | 其前置对象 G0 迭代解未完成，直接法预检也未启动 | `records/run_index.json` |
| N6 / 总体 | `INCOMPLETE_WORKER_FAILED_REPLAY_BUDGET_EXHAUSTED` | 精度、h 变化、同离散参考及目标容量结论均未取得 | `records/phase_I_results.json` |
| 生产资格 | 未批准 | 不改 ordinary default，不合并 `master`；等待 review | 本表及下方选择性合并表 |

本轮是在 Task40 B 线 N0–N6 合同内完成的启动与失败证据收口。保留既有任务失败、资源口径和原始状态；没有把实现异常改写成数值失败或资源停止。

## 2. 任务目标与非目标

| 范围 | 内容 | 本轮边界 |
|---|---|---|
| 目标 | 用真实 0.7 nm Si/air 材料和具有有限 x/y/z 缺口的三维周期单胞，尝试在 G0 上求 p6 Maxwell 方程；随后以 G1、参考解和成本决定工程扩展方向 | G0 只完成了网格/空间/约束/端口准备的一部分；没有完成 p6 数值求解 |
| 求解流程 | 用单元内部消元减小重复求解规模，外层仍求原 p6 离散；p4 用作近似纠错 | 本轮没有建成 p4 全局因子，也未测得该方法的求解效果 |
| 非目标 | 证明 0.7 nm 目标尺寸可行、连续极限收敛或选出 Phase II 算法 | 均未得到证据；不启动工作站或大尺寸求解 |

这里的“单元内部消元”是在每个有限元单元内先处理不共享的内部自由度，再把剩余边界自由度交给全局问题，目的是缩小全局系统；代价是需要保存局部消元和恢复信息。它没有改变材料方程，但这次运行没到可评估该策略成本或收益的阶段。

## 3. 冻结物理身份与比较基线

| 身份项 | 值 | 身份/含义 | 证据 |
|---|---|---|---|
| 输入 | `input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4.dat`，SHA256 `8e00fb6495845902a8113d982242d39ad0f4999b563c2c8049ecc3750b82ac9c` | 冻结输入文件 | `records/run_index.json` |
| 波长与材料 | 真空波长 `0.7 nm`；Si 的求解器折射率 `0.9998851703688496 + 4.3236152269189515e-06i` | 由公开散射因子数据与密度推导，不是样品实测；时间约定与被动损耗符号见材料记录 | `records/material_identity.json` |
| 单胞 | x 周期约 `2.592593 nm`，y 周期约 `1.296296 nm`；z 域由解析平面 `-10s…130s` 界定，`s=7/135 nm` | 解析几何合同 | `records/geometry_plan.json` |
| 有限空气缺口 | x=`1.296296…1.737037 nm`，y=`0.324074…0.972222 nm`，z=`2.074074…4.148148 nm` | 缺口在三个方向都有有限边界，因此不是沿 y 均匀的二维挤出结构 | `records/geometry_plan.json` |
| 几何、材料、通道身份 | 几何 SHA `29b5839216ec96e4cdaaf7ffcf2418a6d61a0a61c731f387be2e4e3e33ec4d12`；材料模型 SHA `7d21c0c1f964c2fe2bf44d2e724fc62e0f68aa9ebc4352c1616e763e7fc11aea`；模式清单 SHA `40e80da12f352c80bf941aa5736c8910e69ea39e230afcf87737b2fbd92b8a78` | 分别绑定几何、材料模型和 80 模态身份 | `records/phase_i_physical_identity.json` |
| runner 物理 hash | `51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661` | `.dat` runner 身份字段的哈希方案，与上行 composite identity 的字段范围不同；不能互换 | `records/run_index.json` |
| 衍射模式 | 上下端口各 40 个有序模式，共 80 个；截断收敛未测 | `CHANNEL_TRUNCATION_UNQUALIFIED`，不能因小模型能量闭合就认定通道数充分 | `records/mode_inventory.json` |
| 网格计划 | G0 `6×4×14=336` cells，计划 SHA `d621678ed8f144246133a98a71a2805bf55d09104d3aa6ceeb55e3f16fb864f1`；G1 `10×4×22=880` cells，计划 SHA `2e7e0a76c2161bfc0651c89d8c5e6edfa2a1ed37d1e2b5a674e314c6c5f5c27d` | 两者均为解析平面导出的计划值；G0 实际构建了 336 cells，G1 没有构建 | `records/geometry_plan.json`、`records/run_index.json` |

## 4. 方法与必要修复

| 方法或改动 | 解决的问题 | 本轮验证到哪一步 | 证据与代价 |
|---|---|---|---|
| Task40 显式配置与几何计划 | 把 0.7 nm 材料、Floquet/DtN 模式、缺口平面和 G0/G1 网格绑定为单独物理身份 | N1 记录通过；G0 builder 实际得到 336 cells；G1 仍为 derived plan | 依赖 Task40 输入、mesh builder 与 inventory；尚无通用几何资格 |
| `1ee85bc` worker identity 修复 | 让 Task40 冻结 `run_id` 成为旧 V14 shared ledger 可接受的 batch identity，并用本例几何轴和实时 q4 类元数据估算容量 | 目标测试 3 passed；但唯一 G0 bug replay 随后在另一实现缺陷处失败 | 修复用于 Task40 profile；旧 V22 固定 B 身份保护保留 |
| `59bad0d` mesh metadata 修复 | 同网格 p6/p4 层包装器此前只保留 mesh/tag，丢掉缺口审计、坐标轴和材料面元信息 | targeted G0 mesh/FE/MPC fixture 1 passed；没有修复后 PDE | 不创建新全局因子；PDE 正确性仍未验证 |

## 5. 阶段与运行矩阵

| 阶段/运行 | 实际工作与结果 | 状态 | 数据身份与证据 |
|---|---|---|---|
| N0 | 保留用户指定的既有 `task40extra_0p7nm_engineering` 分支；绑定 Task39 收口来源与 canonical linked worktree | `complete` | 见 `branch_provenance.json` |
| N1 | 固定 0.7 nm Si、非可分解析几何、G0/G1 轴计划及模式清单 | `complete` | derived/input records，见 `records/material_identity.json`、`geometry_plan.json`、`mode_inventory.json` |
| N2 | 60-cell、p2 静态凝聚 tiny diagnostic；相同 0.7 nm 材料/几何身份的缩小诊断，不是 G0/G1 | `diagnostic_pass_only` | 测得残差 `1.772707454694957e-12`；不是 official G0/G1，见 `records/n2_tiny_static_condensed_diagnostic.json` |
| N3 / G0 attempt 1 | source `e694452f2f9287135f046af45592e3665f8b6c71`；3.896 s 后 `RuntimeError: parent ledger batch identity changed` | `WORKER_FAILED_IMPLEMENTATION_BUG` | 数值工作未开始；worker/run/watchdog SHA 见 `records/run_index.json` |
| N3 / G0 attempt 2 | source `1ee85bc2133b783da419d31dbe429643eb2c1191`；唯一 bug replay；建成 336-cell G0 并到达 cleanup 的几何审计输出，随后缺少 `rectangular_air_void_audit` 而抛 `AttributeError` | `WORKER_FAILED_IMPLEMENTATION_BUG_REPLAY_EXHAUSTED` | setup/native projection 有限证据；没有 p6 full matrix、p4 factor、KSP、残差或官方物理输出 |
| 修复后组件 fixture | source `59bad0d977f0e23555098d923a95afbf2e9f5bf4`；targeted G0 mesh/FE/MPC fixture 3.89 s 通过 | `component_pass_only` | 不构成修复后 PDE 证据 |
| N4 / G1 | 880-cell G1 未运行 | `not_run` | G0 没有合格解且 replay 用尽 |
| N5 / G0 direct | 没有做 symbolic/factor 预检或 direct 求解 | `not_run` | 前置 G0 iterative 未完成；不是资源 Gate 拒绝 |
| N6 | h 误差、同离散参考、容量汇总与唯一 Phase II 候选选择均未完成 | `incomplete` | 当前数据不足以选出新算法 |

## 6. 关键数值结果

| 模型/阶段 | cells / DoF | 残差与物理量 | 耗时 | 解释与对照身份 |
|---|---:|---|---:|---|
| N2 tiny p2 diagnostic | 60 cells；E DoF 1,840；active condensed DoF 1,256 | 相对线性残差 `1.772707454694957e-12`；Rtotal `0.999983627560756`；Ttotal `1.570950234381809e-05`；Abalance `6.629369001986763e-07`；Avolume `8.856354534342745e-08`；闭合差 `-5.743733547669549e-07` | solver `8.6081 s`；MUMPS setup `0.04802 s`，solve `0.001835 s` | 诊断成功；不作为 G0/G1 p6 official 结果，也不表明连续误差或通道截断已合格 |
| G0 attempt 1 | 数值装配前 | 无真残差、KSP 或 R/T/A | `3.8961 s` worker elapsed | ledger identity 实现异常 |
| G0 attempt 2 | 336 cells；p6 rows `229,680`；active trace `68,256`；slave `10,224`；interior `151,200`；q4 rows `69,856`；q4 trace `28,992`；q4 slave `4,576`；q4 interior `36,288` | 80 模态 manifest `c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a`；native AQ projection DtN 相对差 `9.584104029325266e-15`、volume 相对差 `2.7510630979502593e-15`，门槛 `1e-10`；没有 full explicit A6 | worker settled `87.89696 s` | 网格/FE/约束/投影 setup 的部分通过；不是求解通过 |
| G1 / direct reference | 未运行 | `not_run` | `not_run` | 无 h 或同离散参考结论 |

N2 表中的 `R/T/A` 仅是这个 tiny diagnostic 自己完成的输出；正式目标 G0 的 `R00_s`、`R00_p`、`R00_total`、各衍射级、E/H、`A_volume` 和能量闭合均 `not_run`。因此不存在 G0 物理量“未通过”的数值，准确状态是没有生成。

## 7. 数值正确性与 Gate

| Gate | 任务门槛 | G0 实际值 | 判定 |
|---|---:|---:|---|
| full explicit 原 A6 relative residual | `≤1e-6` | `not_run` | 未进入 KSP/残差阶段 |
| energy closure | `≤1e-5` | `not_run` | 没有正式场和 official power packet |
| G0–G1 场变化 | E/H/scaled-curl `≤1%` 目标 | `not_run` | G1 未运行 |
| G0–G1 R/T/A 变化 | 绝对差 `≤1e-3` 目标 | `not_run` | G1 未运行 |
| G0 与同离散 direct reference | 场差 `≤1e-4`、R/T/A `≤1e-5` 目标 | `not_run` | direct reference 未运行 |
| 模式截断 | 需独立 cutoff convergence | `CHANNEL_TRUNCATION_UNQUALIFIED` | 不可宣称通道资格 |

## 8. 资源与时间

| 运行 | 指标 | 实测/状态 | 口径 |
|---|---|---:|---|
| G0 attempt 1 | simultaneous process-tree RSS peak | `142,209,024 B` | watchdog 采样的进程树 RSS；数值阶段未开始 |
| G0 attempt 2 | simultaneous process-tree RSS peak | `1,538,707,456 B` | watchdog 322 个样本、identity coverage complete；PSS 按 profile 禁用 |
| G0 attempt 2 | active cgroup `memory.current` / `memory.peak` | `1,080,860,800 / 1,673,117,696 B` | cgroup 当前量及其 high-water，与 process-tree RSS 是不同会计口径，不相加 |
| 两次 G0 | swap / OOM / 清场 | swap `0`；OOM-kill `0`；后代已清场 | 不是资源停止；资源记录没有显示 watchdog 安全 Gate 触发 |
| N2 tiny | RSS `368.8008 MiB` | 历史各 rank peak 之和的上界 | 不是 simultaneous process-tree RSS，不能与 G0 watchdog 峰值直接比 |
| shared ledger | 两次共 `91.7931 s`；实现错误 replay `1/1` | `time_policy=observe_only` | 任务里的 `43,200 s` 是 reference/accounting 字段，不是 12 小时硬超时 |

这里更正先前口头表述：`1,538,707,456 B` 是 watchdog 同时进程树 RSS 峰值，不是 cgroup peak；活动 cgroup 的 `memory.peak` 单独记录为 `1,673,117,696 B`。二者不可互换。

## 9. 失败原因与根因解释

| 发生顺序 | 直接异常 | 根因与修复 | 结论边界 |
|---|---|---|---|
| attempt 1 | `RuntimeError: parent ledger batch identity changed` | Task40 runner 先前复用了与冻结 case `run_id` 不一致的 V14 ledger batch identity；`1ee85bc` 改用真实 case identity，并添加按 G0/G1 轴和实时 q4 类 metadata 计算的 profile capacity context | 这是启动实现错误，不是数值收敛失败 |
| attempt 2 | `'types.SimpleNamespace' object has no attribute 'rectangular_air_void_audit'` | same-mesh 层 wrapper 只复制 mesh 与 tags，漏掉新 Task40 air-void audit 和轴/材料对齐字段；`59bad0d` 让 wrapper 保留这些字段并补了 component fixture | 错误发生于 cleanup/audit 路径；全局矩阵、因子和 KSP 均未开始；最终修复未获 PDE 重放 |

因此主导瓶颈尚不清楚：这次没有建全局 p4 因子、完整端口/Krylov 工作向量或正式局部缓存峰值，无法判断 p4 factor、端口库存还是局部缓存哪项限制目标扩展。不能从 setup RSS 或 60-cell tiny run 推导 2 TB 容量。

## 10. 成功路线、失败路线与保留的负结果

| 对象 | 状态 | 可说的结论 |
|---|---|---|
| N1 材料/几何/mode inventory | complete/derived | 身份已冻结；公开 Si 数据不是样品实测 |
| N2 p2 tiny solve | `diagnostic_pass_only` | 小 fixture 的方程、凝聚与输出链可运行；不授予 p6 G0/G1资格 |
| N3 G0 attempt 1/2 | `WORKER_FAILED` implementation exceptions | 两种启动/metadata bug；不代表数学方法不收敛，也不代表资源不够 |
| `59bad0d` component fixture | `component_pass_only` | 缺失 metadata 的未来修复经小型 G0 mesh/FE/MPC fixture 验证；正式 G0 仍未验证 |
| N4/N5/N6 | `not_run` / `incomplete` | 没有 G1、独立 reference、h/容量或 Phase II 结论 |
| Task39 V31 首次 instrumentation failure | inherited evidence retained | Task39 原注释仍保留在其资源复审与选择记录；Task40 不重写该父任务失败历史 |

## 11. 代码与文档变化

| 依赖组 | 本分支代表文件 | 数值行为与测试 | fresh PDE 证据 |
|---|---|---|---|
| production numerical/core | `src/common/config_3d.py`、`src/geometry/mesh_builder_3d.py`、`src/geometry/task40_nonseparable_plan.py`、`src/io/input_schema.py`、`src/io/input_validation.py`、`src/runners/physical_dual_cell_condensed_lowmem_v20.py`、`src/runners/physical_p4_schur_v14.py`、`src/runners/task038_full3d_iterative.py`、`src/runners/task038_launcher.py`、`src/solvers/fullspace_same_mesh_hcurl_pmg_global.py` | Task40 profile、几何、capacity和 metadata 路径发生实现变化；ordinary default 有独立 guard，仍不应从代码存在推断 production 资格；见 `src/test/test_task40_nonseparable_geometry.py` | 当前分支没有修复后 G0 PDE 证据 |
| reusable runner/watchdog | `benchmarks/subreaper_watchdog.py`、`benchmarks/task038_full3d_jit_staging.py`、`scripts/run_case.py` | 编排、监控和入口变化；watchdog 资源字段有真实失败运行观测，非成功 solve 认证 | 没有通过数值/official-output Gate 的 formal workflow |
| checker/benchmark | `scripts/task40_n1_inventory.py`、`src/test/test_task40_nonseparable_geometry.py`、Task40 `.dat` 输入 | inventory 与验证数据；测试不等于 PDE | N1/N2 通过其各自有限范围；G0 official not_run |
| compact evidence/docs | Task40 的 `records/*.json`、`records/raw/si*`、`outcomes/*.md`、`README.md`、`docs/development_progress.md`、`docs/development_model_registry.md` | 保留输入、失败、测试和决策身份 | 仅文档/records 不改变数值算法资格 |
| research-only | Task40 双凝聚 profile 和其显式选择路径 | 保持显式、局限于本研究分支 | 未有完整 p6 解，不升级普通能力 |
| do-not-merge | 整个 Task40 分支、任何无白名单整体 cherry-pick、`master` 与 ordinary default | 未获最终 review 和 merge 授权 | 不进入生产 |

## 12. 最终决策、局限与下一步

| 决策项 | 当前决定 | 原因 |
|---|---|---|
| 本轮阶段状态 | `INCOMPLETE_WORKER_FAILED_REPLAY_BUDGET_EXHAUSTED` | 唯一 bug replay 已用尽，且仍无 G0 解 |
| 数值重跑 | 当前合同下不再运行 G0、G1 或 direct reference | 超出一次实现错误重放上限；任何续跑需 superseding review/authorization |
| Phase II 算法 | **未选择** | 无 official residual/RTA、h 差异或 p4 factor/容量证据，不能有依据地选唯一方案 |
| production/default/master | 不提升、不合并 | 没有成功的正式 G0；等待审阅 |
| 下一个可复核步骤 | 审查本收口文档；若需继续数值工作，由后续 review 明确新授权与范围 | 错误修复有 component fixture，但缺最终 PDE 资格 |

不得由本轮推出任意 0.7 nm 全尺寸求解不可行，也不得宣称它可行。能确认的只有：N2 小型 p2 诊断通过；G0 网格/FE/MPC/setup 建成部分事实；两次 G0 worker 因不同实现异常失败；后续 G1、direct 和精度/容量 Gate 均未运行。

## 13. 证据索引

| 证据 | 用途 |
|---|---|
| [`records/run_index.json`](records/run_index.json) | 输入、stage、尝试分类、raw artifact hashes、shared ledger 与最终代码修复索引 |
| [`records/phase_I_contract.json`](records/phase_I_contract.json) | 冻结物理/数值/资源/重放合同；G0/G1 网格计划 hash |
| [`records/phase_I_results.json`](records/phase_I_results.json) | 各阶段最终状态与 official-result 未生成事实 |
| [`records/g0_startup_bug_replay.json`](records/g0_startup_bug_replay.json) | 两次 G0 worker 异常、唯一重放和 ledger 封存 |
| [`records/material_identity.json`](records/material_identity.json)、[`records/geometry_plan.json`](records/geometry_plan.json)、[`records/mode_inventory.json`](records/mode_inventory.json) | N1 输入身份、几何计划及端口模式 |
| [`records/n2_tiny_static_condensed_diagnostic.json`](records/n2_tiny_static_condensed_diagnostic.json) | N2 的小型 p2 诊断数字、scope 与 artifacts |
| [`../task039_extra_physical_multilevel/final_report.md`](../../task039_extra_physical_multilevel/final_report.md)、[`../task039_extra_physical_multilevel/review_report_v30.md`](../../task039_extra_physical_multilevel/review_report_v30.md)、[`../task039_extra_physical_multilevel/response_v34.md`](../../task039_extra_physical_multilevel/response_v34.md) | 父任务技术边界、审阅和 B 线交接 |
| ignored raw results | `results/task40extra_nonseparable_0p7nm/.../20260929T122310.721505Z/` 与 `.../20260929T125016.481634Z/`；完整文件 SHA 摘要见 `records/run_index.json`，不提交重型结果 |

### 轻量证据 JSON 的文件 SHA256

| 记录 | SHA256 |
|---|---|
| `records/run_index.json` | `48207436ada07b04b5dd040536fe53329c356a58ea45c93ab2cb152bf7296e1c` |
| `records/phase_I_contract.json` | `0a396c42c33125e311088b637372792ff79c609460a7d2bf3374e8cadd01d135` |
| `records/phase_I_results.json` | `ff50d9235f1be8dadb8f577657392ecf470c22ba15da5de5fc6fdd471428eb45` |
| `records/g0_startup_bug_replay.json` | `91e80db308fe3be68e36a627770ab83c609320d8cd4eb6aafda1bbd06a505101` |

## 14. 选择性合并建议

| 顺序/依赖组 | 代表性文件 | 数值行为变化 | 对应测试 | fresh PDE 证据 | 建议 |
|---|---|---|---|---|---|
| 1. compact evidence/docs | 本 summary、response、test summary、材料/几何/容量说明、轻量 JSON、项目索引 | 无；仅记录现有证据 | JSON/static docs checks；不替代数值测试 | 不需要文档自身的 PDE；所记录 G0 是失败 | 可在本分支审阅；待 final review 后按白名单选择性归档 |
| 2. checker/benchmark | `scripts/task40_n1_inventory.py`、Task40 `.dat` 与对应测试 | inventory/输入校验；不是求解器资格 | Task40 N1/N2/targeted pytest，具体见 `test_summary.md` | N1/N2 有限证据；无 official G0 | 保持 Task40 scoped；审查后才决定是否单独抽取 |
| 3. reusable runner/watchdog | `scripts/run_case.py`、`src/runners/task038_launcher.py`、`benchmarks/subreaper_watchdog.py`、`benchmarks/task038_full3d_jit_staging.py` | 运行编排/资源记录改变，不应影响离散矩阵；仍须检查生命周期 | launcher/swap targeted tests；见 `test_summary.md` | 两次失败 workflow，不能证明完整成功运行监控闭环 | 暂留研究分支，不提生产 |
| 4. production numerical/core | Task40 mesh/config/io/solver/runner 文件，见第 11 节 | Task40 profile 会改变几何构造、身份和 PC 工作区；默认路径受 guard | geometry/identity/capacity/metadata fixtures | **无修复后 G0 fresh PDE** | 当前不合入；须经 review、依赖测试及获批的新数值资格 |
| 5. research-only | Task40 双凝聚显式 profile 与局部 capacity 估算路径 | 改变研究 profile 的内核路径，不改变 ordinary default | focused algebraic/mesh fixtures | G0 未到 full matrix/KSP | 仅留本分支，任何提升必须新审查 |
| 6. do-not-merge | whole branch、whole-tree merge、ordinary-default 切换、`master` | 范围过宽或无授权 | 不适用 | 无 | 不合并；等待 ChatGPT final review 与用户授权 |

## G0 第三次启动失败与继续修复

第三次启动已通过原先缺失的几何审计字段，随后因 Task40 新 worktree 不含 Task39 的相对 JIT 缓存目录而发生 `FileNotFoundError`。尚未分解或进入 KSP，不是数值 Gate。全部后代已清场，累计正式成本为 **138.62440517507468 s**，原 91.79305701722132 s 保留。用户已授权修复实现 bug 后继续；本次仅修正 Task40 的合格缓存位置，缓存不命中的新表单仍在正式监督和计时内编译。新结果尚未取得。详见 `g0_jit_path_failure.json` 和增量授权记录。
