# Review V15 执行回应

## 整轮范围与结果

本回应覆盖 Review V15 的 P0–P5，包括已实施的数值合同、正式计算和离线收口。执行分支为 `task40extra_0p7nm_engineering`，V15 数值源码冻结 SHA 为 `40dbe138f53b9a2ee39399eac66dc4b0867a2d50`；原始分支 base、续作前远端 HEAD 和 Task39 第二父关系见 `branch_provenance.json`。固定 campaign window 沿用 T0 `2026-10-06T23:21:33.326800586Z`、deadline `2026-10-07T23:21:33.326800586Z` 和原 SHA；没有开启新窗口。代码按阶段冻结并运行：`3a737f3e57fc5eda6119fada77e734d656483d98`、`e77575f7df27154196a79819d7d9ed3044d4b62a`、`0201815c6b13f8456e9717ab93cc5023d4c946d1`、`40dbe138f53b9a2ee39399eac66dc4b0867a2d50`。B0 原正式求解使用 `0201815c`；B0 保存场恢复、Gx560 和 E1 使用 `40dbe138`。P5 只做离线证据/文档收口和定向合同检查，没有追加 FE/PDE 求解；执行者没有提交或推送，交由主控按既定分工处理。

| 阶段 | 做了什么 | 结果与边界 |
|---|---|---|
| P0 | 核对原 V14 失败证据、固定窗口、执行身份和既有数据；保留失败/停止分类 | 固定窗口不变。启动注册、ABI注册等工程失败独立记录，不混成 PDE 负结果 |
| P1 | 实现显式 `NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15` 近似参考 PC 合同、完整状态选择与最多一次修正；修复真实入口/源路由和 CSR 安全问题 | 既有分阶段测试分别为 103 passed、29 passed、41 passed、49 passed / 1 skipped；最终冻结源码上的 Task40 路由、恢复与增广修正定向套件为 61 passed。不同源码/套件分列，不能求和成一次测试。Ruff 未安装/未运行；全仓 pytest、MPI4、CI 未运行 |
| P2 | B0 80-cell、p6、532-mode 正式 target；失败后只对已保存场做恢复核验 | 原 worker 保留 exit 4 和 `WORKER_FAILED`：端口身份记录的负限值 `-1` 导致整组输出门失败；A6 单项残差通过不能覆盖该门。随后 saved-field recovery 在不建参考因子、不跑 KSP 的条件下通过 A6 重算、物理输出门和独立 checker |
| P3 | Gx560 560-cell、p6、340-mode 完整 target 和旧同离散场对照 | 新路线 target、物理门和保存场比较 PASS；reference PC 3 次。完整 workflow 比旧完整结果更长，故不宣称全流程提速 |
| P4 | E1 760-cell、p6、588-mode 新路线逐级资源资格 | 四个 q 的 symbolic 完成；总 RSS 与新增余量两个不等式都不通过，任何 numeric factor 前受控停止并清场。E1 numeric、KSP、新场与官方 R/T/A 均 `NOT_RUN`，不是数值算法失败 |
| P5 | 写入本回应、四份 compact、结果/测试/模型入口和 run index；做最终轻量检查 | 仅离线收口。此次 P5 没有重跑 FE/PDE、没有提交或推送 |

## 模型结果与成本

| 模型/阶段 | 网格、离散、规模 | 结果与物理量 | 时间与资源 | 判定 |
|---|---|---|---|---|
| B0 原运行 | 4×4×5 = 80 cells；p6；532 modes；4 q；full-storage 55,950 rows；q CSR rows 4,324/4,400/4,400/4,400，NNZ 合计 9,227,053 | A6 真残差 `1.6089774391665316e-8` 低于 `1e-6`，但负端口身份限值令完整输出 Gate 失败，没有正式输出包 | workflow `1052.750762 s`；watchdog `1052.528380 s`；tree RSS/cgroup 峰 `2,776,645,632 / 3,216,044,032 B`；swap 0 | 原始 `WORKER_FAILED`, exit 4 保留；不是仅凭 A6 通过就改判 PASS |
| B0 保存场恢复 | 同一 80-cell/532-mode 保存场；恢复源码 `40dbe138`；不重建参考因子，不运行 KSP | R/T/A_balance/A_volume=`0.9842736081 / 0.0142405181 / 0.001485873763 / 0.001485873846`；能量闭合 `8.28793e-11`；独立输出 checker PASS | workflow `10.718959 s`；tree RSS/cgroup 峰 `770,363,392 / 910,651,392 B` | saved-field postprocess recovery PASS；不覆盖原 exit 4 |
| Gx560 新路线 | 10×4×14 = 560 cells；p6；340 modes；4 q；full-storage 380,040 rows；q CSR rows 28,508/28,508/28,576/28,508，NNZ 合计 61,991,755 | A6 after release `4.7044013511e-9`；独立 native witness `4.7042570565e-9`；R/T/A_balance/A_volume=`0.07612406709 / 0.90576922010 / 0.01810671281 / 0.01810671258`；R00_s/p/total=`0.07612359351 / 7.36e-22 / 0.07612359351`；独立 checker PASS | workflow `2407.572416 s`；纯 KSP `155.863281 s`；3 次 outer iteration；tree RSS/cgroup 峰 `10,294,927,360 / 11,674,669,056 B`；swap 0 | 完整 target/物理 PASS；旧同离散场 comparison PASS；不是 continuum 收敛结论 |
| E1 新路线 | 10×4×19 = 760 cells；p6；588 modes；4 q；symbolic 实际总 rows 153,948、NNZ 84,935,314 | 四 q symbolic 完成；没有 numeric factors、KSP、field 或 official R/T/A | workflow `5671.918121 s`；watchdog `5671.578106 s`；UTC wall interval `6275.443430 s`；tree RSS/cgroup 峰 `12,234,416,128 / 12,346,351,616 B`；swap 0 | all-q symbolic 后资源受控停止；不属于 OOM 或数值 solver fail |

B0 saved-field 恢复只重新应用已保存场并重算输出，所以 `KSP_solve_count=0`、`reference_factors_built=false`。Gx560 与旧完整 p6 target+p4 correction 结果比较：outer iterations 171→3，但完整 workflow `1925.862866→2407.572416 s`，增加 `481.709550 s`（约 25.01%）；process-tree RSS 峰 `5,255,675,904→10,294,927,360 B`。因此迭代步数下降没有带来端到端速度或内存优势。这两份记录来自不同冻结源码的历史完整运行，没有同日交错控制缓存、供电和 CPU 状态；时间比例仅描述已记录的两次结果，不能据此给某项改动作因果归因。E1 旧路线已完成的 p6 target+p4 correction 记录仍是历史证据（A6 `9.781668526e-7`、R/T/A_volume 约 `0.06235654/0.91592648/0.02171695`、workflow `4580.375 s`、RSS 约 `10.65034 GB`）；它不代表 V15 新路线完成。

## 近似参考预条件器的通俗解释与合同

参考预条件器是在每次外层迭代中给主求解器一个修正方向的辅助计算。它不是最终 Maxwell 方程，也不是把精确参考逆改名为“通过”：以前的 strict exact-reference 失败仍保留。柔性 GMRES 可以使用有受控误差的辅助方向，但是否得到正确物理解，仍由原始 target 的完整 A6 真残差、场恢复和物理输出门裁决。

V15 不再只用参考局部块彼此是否像精确逆来决定能否开始 target solve，而是把所有分块差异映射回同一原 RHS 的全局方程并计算非抵消误差预算。令原载荷尺度 `S = ||f||₂ + ||B H_p⁻¹ g||₂`，并保持该尺度由原 RHS 冻结；预算为：

`eta_budget = (||d_b||₂ + Σ_s ||L_s e_s||₂ + ||d_A||₂ + ||B δalpha||₂) / S ≤ 1e-8`。

此外，独立 global native 消元 FE 残差与同一 `(u, alpha)` 的完整增广 FE 残差均须 `≤1e-8`；alpha closure `≤1e-9`；每次实际 q MatSolve 残差 `≤1e-8`。初始 factor admission probe 仍须 strict `≤1e-10`。mapping、全模式覆盖、伴随恒等式、RHS identity、internal/native recovery、Schur-port identity 和 saved-field representation 原门不变。一次 PC 最多进行一次完整增广修正，最多增加四次 q MatSolve；不新建 factor、不递归修正、不拼接不同候选的最好分量。详细定义见 [Review V15 §4](review_report_v15.md) 与 [native PC compact](outcomes/records/review_v15_native_pc_contract.json)。

Gx560 的三个 PC apply 都选中 candidate 0；每次四 q 外层 MatSolve 一次，无 correction。逐次最大 q 相对残差是 `1.5744074325e-10 / 1.6728992449e-10 / 1.2181831145e-11`；前三次中前两次没有达到旧 strict q 标签 `1e-10`，但均满足 V15 实际 q solve 的 `1e-8`。全程最大非抵消预算 `4.9656567445e-9`、消元 FE `2.4692342908e-9`、完整增广 FE `1.9232496879e-10`、alpha closure `1.7789327117e-11`，均通过 V15。startup reference q MatSolve 16 次、初始 factor probe 4 次、target PC 12 次，总计 32 次 q MatSolve；完整 PC 每次耗时没有独立单调时钟，native check 子阶段秒数不能冒充完整 PC 时间。

Gx560 已测 global CSR assembly 的最大子阶段是稀疏累加：sector 0 parent `230.155492 s`，projection `60.937886 s`、sparse accumulation `154.393760 s`、contribution generation `14.590967 s`、CSR 累加调用 2916 次；sector 1 parent `192.384544 s`，对应 `57.769324 / 121.442918 / 12.947970 s`、2372 次。父计时和子计时嵌套，不能相加；完整 workflow 增量仍未全部归因。旧 B0-only preallocated CSR 对照仅节省 `6.370516 s`，其 Gx 临时 staging `256 MiB` 上限没有资格化，不能算作 Gx 解决方案。下一项唯一工程焦点是 bounded-staging、Gx-safe global CSR accumulation candidate，逐 q 校验矩阵身份和结果，并比较完整 assembly 耗时与 staging 峰值；本轮不运行该候选。

四个 Gx560 factor 同时存活。factor setup parent `54.226915 s`；q numeric 子时间 `4.608882 / 9.844299 / 6.028945 / 13.550974 s`。INFOG9 raw q0–q3=`41320088/41253248/41789336/41269544`；没有合适依据把它们解码成 factor entries。INFOG19 allocated upper bounds 合计 `4.645 GB`、INFOG22 used upper bounds 合计 `4.080 GB`（十进制）。all-q 销毁前单独记录的 tree RSS 为 `10,189,733,888 B`。另一对同树清理样本中，root PID 1957605 和四个 PID/start-ticks 身份一致：`packet_v15_pc_last_apply_projected` 的 member RSS 总和为 `10,289,065,984 B`，factor-release-complete 后为 `4,354,420,736 B`，下降 `5,934,645,248 B`，两端 swap 均为0。采样代码将 rss_bytes 定义为成员 RSS 求和；这是整个 reference-PC cleanup 期间的观测，不能全部归因给 MUMPS，也不与 tree peak 相减。

## E1 资源门与未完成范围

E1 在四 q symbolic 之后的准入数据为：live tree RSS `12,064,264,192 B`，dynamic cap `12,474,302,464 B`，预估继续执行的 tree RSS `19,192,602,560 B`，可用内存 `544,256,000 B`，evidence reserve `134,217,728 B`。总 RSS inequality 和增量余量 inequality 均为 false；task/cgroup swap 峰均为 0，后代已清理。这是真实受控资源停止；投影值是预测，不是已分配 numeric 因子内存。四 q 实际 CSR rows/NNZ、symbolic estimates 与 hashes见 [formal results compact](outcomes/records/review_v15_formal_results.json)。INFOG(3) 等 MUMPS 字段不冒充 CSR NNZ，INFOG16/17 合计 `6.53 GB` 是 symbolic 估算，不是 numeric factor 实测。

原尺寸目标为 `50×25×140 nm`、波长 `0.7 nm`，目标资源限制是十进制 `2 TB = 2000000000000 B` 和 `48 h`。候选 15,232 cells 为 derived，32,060 模式为 measured inventory；当前仍未资格化。必须单独关闭的事项包括：y/z 精度和更一般 Ny orbit/mapping；任意 Ny 下 mode indexing/覆盖；目标 q CSR NNZ、indptr、全部 q factor fill/workspace 与同时库存；全局 NumPy/int32/MPI1 限制和分布式/int64 路线；`iter_reduced_contributions` 仍调用 `_materialize_Hhat()` 所带来的 mode² 中间存储；完整 AUTO 882-row 边界路线在本实现中的身份/索引/输出链资格（84-row 压缩没有资格化）；恢复、field 输出、释放和冷启动完整流程的生命周期及其 2 TB/48 h 实测。已知 Krylov、scratch 和一个稠密 H 的派生字节量不是同时 RSS，也不能证明容量可行或不可行。Gx560 成功与较少的外层步数不能代替这些目标资格。

## 历史 E2 结果与 V15 资格边界

旧 E2 记录是另一条已完成的历史路线：880 cells、700 个保留模式，使用 p6 target 与精确 p4 correction，源码为 `63dd2a7378153f2ab5094eb5e7a98d05758a39bf`。原 worker 在求解后因输出采样只有 24×24、未达到所需 25×7 而以 exit 4 失败，原失败和 `official_result=false` 保留。对已有保存场进行的 v3 离线输出恢复耗时 74.153920702 s，重新得到 native A6 `9.793073227317083e-7`；R/T/A_volume 为 `0.05116886160983426 / 0.9239410512847893 / 0.02489005360260621`。这不是 fresh PDE、KSP 或 factor 运行。旧路线 workflow 为 7692.028065771 s，树 RSS 峰为 11,349,196,800 B，仅作旧路线实测。完整身份和证据见 [electrical_size_v2.json](outcomes/records/electrical_size_v2.json)。

V15 的 E2 新参考 PC 路线仍为 `NOT_RUN`。E1 在 symbolic 后资源受控停止，不能继承旧 E2 的容量结论；旧 E2 的 Ny=4/700 模式也不授予 y 方向或 general-Ny 资格。

## 时间账与证据入口

固定 T0/deadline 没有刷新。E1 的协调中断 workflow `102.788224005 s` 是执行协调中断，不是用户要求停止，费用不退；随后 E1 新路线 workflow `5671.918121 s` 另计。E1 task/cgroup swap 峰均为0；同一原始收据还记录 WSL-global pswpin/pswpout 增量分别315/55203页，归属任务与否 `UNRESOLVED`，不能据任务/cgroup零值写成宿主没有 swap。campaign 累计政策费用、watchdog monotonic、run-summary monotonic 和 UTC wall interval分开记录。现存 `launcher_after_watchdog` 快照累计 charge `54973.270204 s`，是文档收口前观察，不是最终结算；最终窗口观察及仍未归属成本见 [cost/readiness compact](outcomes/records/review_v15_cost_and_readiness.json)。不能按两个时钟的差值给未知费用分摊到某阶段。

完整证据入口：[native PC 合同](outcomes/records/review_v15_native_pc_contract.json)、[失败与恢复 witnesses](outcomes/records/review_v15_failure_witness_and_repairs.json)、[正式结果与运行身份](outcomes/records/review_v15_formal_results.json)、[成本与目标 readiness](outcomes/records/review_v15_cost_and_readiness.json)、[run index](outcomes/records/run_index.json)、[结果总账](outcomes/summary.md)、[测试摘要](outcomes/test_summary.md)、[模型登记](../development_model_registry.md)、[进展账](../development_progress.md)、[任务 README](README.md)。原始执行身份、命令和可用 mode/mesh/field hash 由 compact/index 绑定；未记录项保持 `null` 或 unknown。
