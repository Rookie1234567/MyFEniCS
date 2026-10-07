# Task40extra Review V16 当前结果：Gx560 完整求解通过，E1 未获预构建准入，P4 组件门失败

V16 的 BOUNDED_STAGING_CSR_V16 路线在 560-cell Gx560 上完成了 p6 target 求解：3 次外层迭代，A6 真残差 `4.704430002e-9`，native witness `4.704309876e-9`，均低于 `1e-6`。与 V15 保存场的同离散场、模式和功率比较通过。这个结果支持 Gx560 离散解，不表示连续收敛或目标尺寸资格。

| 模型/阶段 | 实测或派生规模 | 结果 | 成本/资源 | 分类 |
|---|---|---|---|---|
| Gx560 V16 正式 target | 实测 560 cells（10×4×14），p6，340 modes，4 q；q rows 28508/28508/28576/28508；NNZ 15457680/15483524/15600060/15483524，总计 62024788 | A6 4.704430002e-9；native 4.704309876e-9；R/T/A_balance/A_volume = 0.07612406709/0.90576922010/0.01810671281/0.01810671258；R00_s/p/total = 0.07612359351/7.34e-22/0.07612359351；三步；独立 checker PASS | worker monotonic 2274.267 s；tree RSS/cgroup 10.205/11.908 GB；task swap 0；PSS 未启用 | target 与物理输出 PASS；不是 continuum 或目标尺寸证明 |
| Gx560 V16 对 V15 保存场 | 560 个共同子单元；340 ordered modes；物理/网格/MPC/载体身份相同 | 最大 E/H/curl 相对差 1.632e-12；全模式功率差 2.368e-13；11 个冻结显著模式最大振幅差 1.258e-10；R/T/A/A_volume 差均低于 2.72e-13 | 离线比较另用 29.976 s，不计为 worker 内时间 | same-discrete field comparison PASS；输入文件 SHA 不同，物理离散身份相同 |
| E1 V16 | 原路线 760 cells、588 modes | 未创建网格/矩阵；numeric、KSP、field、R/T/A 均 not_run | 总投影 19.193 GB，高于当前 dynamic cap 13.432 GB 达 5.760 GB；6.994 GB 的未来对象合计只通过 prebuild arithmetic estimate。历史 V15 symbolic stop 后 reserve headroom 410,038,272 B，原 incremental Gate 失败；V16 post-symbolic Gate 未运行 | NOT_ADMITTED_PREBUILD，不是本轮 RESOURCE_CONTROLLED_STOP |
| P4 目标端口向量组件 | 复用 W11/S2/S5 arrays；两个保存边界面；每面16,030 modes、全序列32,060 keys、每面882 local rows | Hhat 向量作用完成；raw vector readback 一致、端口子门通过，但 S2 非零 RHS 前向恢复 top 2.203e-11、bottom 2.424e-11 均超过 1e-11 原限值 | component 8.005 s；watchdog 9.723 s；tree RSS/cgroup 0.770/0.844 GB；task swap 0 | COMPONENT_GATE_FAIL；不是 full Hhat matrix 或 target PDE |

## 构建与成本

四 q 的 bounded CSR pattern/累加在 Gx560 实测可用：sector parent 总计由 V15 的 `422.540 s` 变成 V16 `408.214 s`；sparse accumulation 子阶段由 `275.837 s` 降到 `16.777 s`，新 pattern construction 另用 `110.582 s`。父/子计时有嵌套，剩余 parent time 变化没有归因。V16 worker monotonic workflow 比 V15 少 `133.305 s`（约 5.54%），但 worker 外的 checker 和场比较未全部包括在内，完整单场关键路径仍 unknown。

进程树 RSS 峰由 V15 `10,294,927,360 B` 降到 V16 `10,204,880,896 B`，减少 `90,046,464 B`；cgroup 峰值却从 `11,674,669,056 B` 增至 `11,907,702,784 B`，四 q MUMPS allocated 上界也增加 `47,000,000 B`。因此不能宣称同时内存已有净减少。PSS 未启用，任务 cgroup swap 为零，WSL-global swap 归属 unknown。

两类缓存要分开看。原 V12 transform bank 按 Basix/方向状态复用 p6 cell-interior payload，edges/faces 沿用旧路径。新增 `share_identity_cache` 只缓存 450×450、float64 的只读单位阵 I，local inventory 为 `1,620,000 B`；target condensation system 与两个 local sector system 分别启用，不存在横跨三套 system 的共用 I owner，更没有共享 Schur/LU/恢复数据。55 个局部类别仍保留各自局部对象；释放参考因子的 RSS 节省不能归因给某类对象。

pattern 限制仍重要：一个 q block 的 uint8 bitset 存储量是 `rows × ceil(columns/8)`，另加 32 MiB reserve，仍随矩阵维度平方增长。256 MiB 限额给出的纯方阵 bitset 理论边界约 43,344 行，support slice/解码/CSR 会让实际边界更低。Gx560 上最大 q-pattern support staging 为 `137,113,676 B`；目标候选的保留行约 3.13 million，不能据此声称全域 pattern 已具备目标规模 row-tile 能力。当前只有 projection 和 numeric accumulation 使用有界 staging。


### Gx560 求解器与 q 因子

KSP-only monotonic solve 为 148.349809164 s；retained outer solve 到终端快照为 158.978736877 s，二者口径不同。三次完整 PC 父调用为 67.115958898 / 17.492464560 / 9.798304339 s；均选择 correction candidate 0、未应用增广修正。q0–q3 numeric 子阶段合计 18.6509655 s，仅为 numeric 子阶段，不是 setup 总时间。四个 factor 在销毁前同时 live。rows、NNZ、CSR SHA-256、INFOG19/22 上界、INFOG9 原值及未知项见[正式结果记录](records/review_v16_formal_results.json)。

## E1 与目标 readiness

E1 本轮 `NOT_ADMITTED_PREBUILD`：保守总投影 `19,192,602,560 B` 比当前动态 cap `13,432,152,064 B` 高 `5,760,450,496 B`，这一个失败条件足以保持 HELD。未来 symbolic/bank/vector 估算 `6,994,120,640 B` 小于当前 reserved headroom `13,432,152,064 B`，只是预构建估算，不表示 post-symbolic 第二 Gate 已经通过；该 Gate 本轮 `NOT_RUN/UNKNOWN`。6.53 GB 是 INFOG16/17 派生的未来 numeric 保守估算，不是已分配/使用因子。旧 V15 E1 symbolic 后资源停止及仅有 `410,038,272 B` headroom 的记录仍作为历史。

目标候选 272×4×14、15,232 cells、10,228,620 p6 rows 是派生清单；32,060 AUTO 模式清单已有保存身份，但不是最终截断资格。P4 helper 没有分配 32,060² 方阵，但没有证明全部 production path 都不生成此类中间块；目标 q CSR/NNZ/indptr 和 int32 offset 没有实测。Ny8 只是候选 global Ny，实际 K 必须由 global/local orbit 关系推导，mapping、完整 q 覆盖和 H/RHS/alpha normalization 未验证。十进制 2 TB、48 h 以及 y/z 精度均仍 `NOT_QUALIFIED`。

P4 使用已存在的 W11/S2/S5 保存数组，而不是因旧 function-hash 诊断阻塞在“缺数组”。历史 V11 S2 保存的精化合格状态 `5.35e-14/5.14e-14` 与本轮未精化直接 LU 前向重验都来自同一 S2 arrays SHA `d656ff94…`，不能把差异解释为输入或范围不同；前者是保存的 refined state，后者在同一组 `Vii/fi/trace/Bi/known` 数据上不做 refinement 得到 `2.20e-11/2.42e-11`，差异尚未归因。S5 Balpha 对 S2 Bi/Bt 的完整 882 项比较 `1.13e-13/1.04e-14` 是独立通过项，不覆盖 S2 前向门失败。下一具体阻塞是在不放宽 `1e-11` 门槛的前提下定位两次重验差异。

证据见 [Response V16](../response_v16.md)、[构建与内存](records/review_v16_build_and_memory.json)、[正式结果](records/review_v16_formal_results.json)、[目标组件](records/review_v16_target_components.json)、[成本与 readiness](records/review_v16_cost_and_readiness.json)、[测试摘要](test_summary.md) 与 [run index](records/run_index.json)。V15 及更早历史段落保留在下方。

## P5 文档与 ABI 验证

限定 preflight 为 Python 3.12、PETSc 3.25.6 complex128/int32、MPICH 5.0.1、MPI1，且 MUMPS 可用；preflight 仅作 runtime/API 检查；Gx560 的独立 C1 输出 checker 已通过，本次 P5 文档 suite 不含 FE/PDE。四个定向文档/登记测试得到 29 passed、134 subtests passed（0.24 s，pytest 报告值）。全仓 pytest、MPI4、Ruff 和 CI 未运行。

## V16 选择性合并分组与顺序

| 依赖组 | 候选与数值行为 | 依赖、测试和 fresh PDE 证据 | 建议顺序与边界 |
|---|---|---|---|
| production numerical/core | V16 bounded-staging q 构建改变稀疏累加实现/顺序，保留相同 q 数学贡献；共享身份缓存只影响只读单位阵 I 的复用。 | 核心路径包括 `src/solvers/task40_v10_p6_yorbit.py`、`src/solvers/task40_v10_p6_mumps.py`、`src/runners/physical_p4_schur_v14.py` 与 worker 接线；P1 69 项定向测试，source `54b98a8` 的 Gx560 完整 PDE、A6、物理和 V15 同离散场比较通过。全 shape bitset 仍是 O(N²)，无目标尺寸 row-tile fresh run。 | 先审代码/对象生命周期及各 q 原始身份；有独立批准后才迁移。维持 opt-in，不提升 ordinary default。 |
| reusable runner/watchdog | 输入 schema、校验、ABI、dispatch 和 worker 路由用于显式 Task40 profile；可能改变可运行入口，不改方程。 | 依赖 `scripts/run_case.py`、`src/io/input_schema.py`、`src/io/input_validation.py`、`src/runners/task40_v10_abi.py`、`src/runners/task40_v10_worker.py` 与 Task038 调用层；路由 targeted tests 和 Gx560 实际入口通过，E1 未启动。 | 在 core 前单独确认通用性和旧 profile 兼容；E1 资源不据此判通过。 |
| checker/benchmark | 独立输出核验与轻量记录只重算证据状态，不替代求解器。 | `src/runners/task40_v10_output_checker.py` 的 C1 检查 Gx560 官方输出通过；保存场比较独立对照 V15。P4 readback 和端口检查通过，但恢复组件整体失败。 | 与输入/记录 schema 同步审查；不能把 P4 向量组件升级成完整 production checker 资格。 |
| compact evidence/docs | V16 四份 compact、response、summary、test summary、run index、README、项目回顾和模型登记不改变数值行为。 | P5 限定文档合同测试将在最终文件更新后执行；所有正/负记录需与原始 hash/path 逐项一致。 | 优先审查证据层，再审 runner/core；保持原始负结果和 not_run 分类。 |
| research-only | P4 Hhat 向量 helper、目标端口恢复实验和未资格化一般 Ny 路径。 | helper/test 源 hash 在 build/target compact 中；3 项 targeted tests pass，但实际 P4 component 因 S2 前向误差 `2.20e-11/2.42e-11 > 1e-11` 为 COMPONENT_GATE_FAIL，无目标 q CSR/PDE。 | 独立保留，不升 production default；先解决保存数组上的恢复门。 |
| do-not-merge / do-not-claim | 不合并 master，不改变 ordinary default；不把 E1 预估、保存模式清单或 helper 成绩称为目标规模 pass。 | E1 `NOT_ADMITTED_PREBUILD`；目标 NNZ/indptr/int32 中间 offset、最终模式截断、y/z 精度、numeric 因子及 2 TB/48 h 全流程均未关闭。 | 等待主控审查和任务要求的明确批准；不做整体分支合并。 |

# Task40extra Review V15 当前结果：Gx560 完整求解通过，E1 资源受控停止，目标未资格化

本节更新当前状态；V14 和更早结论保留在下方。V15 的四个冻结源码阶段依次为 `3a737f3e`、`e77575f7`、`0201815c`、`40dbe138`。B0 正式运行对应 `0201815c`；B0 保存场恢复、Gx560 与 E1 对应 `40dbe138`。P5 只补离线证据、文档和最终定向合同检查，不追加 FE/PDE。固定窗口和所有历史失败/停止均保留。

## V15 统一结果表

| 模型 | 模型与方法 | 实际结果 | workflow / 资源 | 状态与原因 |
|---|---|---|---|---|
| B0 原运行 | 80 cells（4×4×5），p6、532 modes、4 q；小模型用于检查新参考 PC 和完整 target | A6 真残差 `1.608977439e-8`；q CSR rows `4324/4400/4400/4400`，NNZ 合计 `9,227,053` | workflow `1052.751 s`；watchdog `1052.528 s`；tree RSS/cgroup peak `2.777/3.216 GB`；swap 0 | 原 worker `WORKER_FAILED`、exit 4。负端口身份限值为 -1，导致完整输出门失败；保留原分类 |
| B0 保存场恢复 | 同一网格/模式；只恢复已有场和重算输出，没有新 factor 或 KSP | R/T/A_balance/A_volume=`0.9842736081/0.0142405181/0.001485873763/0.001485873846`；能量闭合 `8.29e-11` | workflow `10.719 s`；tree RSS/cgroup peak `0.770/0.911 GB` | postprocess recovery 与独立 checker PASS；不覆盖原 exit 4 |
| Gx560 V15 | 560 cells（10×4×14），p6、340 modes、4 q；三维非可分缺口模型 | full-storage 380,040 rows；q CSR rows `28508/28508/28576/28508`、NNZ 合计 `61,991,755`。A6 after release `4.704401351e-9`；独立 native witness `4.704257056e-9`。R/T/A_balance/A_volume=`0.07612406709/0.90576922010/0.01810671281/0.01810671258`；R00_s/p/total=`0.07612359351/7.36e-22/0.07612359351` | workflow `2407.572416 s`；纯 KSP `155.863281 s`；3 次 outer iteration；tree RSS/cgroup peak `10.295/11.675 GB`；swap 0 | target、物理门、独立输出 checker和旧同离散场比较 PASS；不是 continuum convergence |
| E1 V15 | 760 cells（10×4×19），p6、588 modes、4 q；比 Gx560 电尺寸更大的诊断模型 | symbolic 完成；真实 q CSR rows `38424/38508/38508/38508`，NNZ 合计 `84,935,314`；数值因子、KSP、field、正式 R/T/A 均未运行 | workflow `5671.918121 s`；watchdog `5671.578106 s`；UTC wall `6275.443430 s`；tree RSS/cgroup peak `12.234/12.346 GB`；task/cgroup swap 0；WSL-global pswpin/pswpout `+315/+55203` 页、归属未知 | symbolic 阶段后资源门停止并清场；不是 OOM，也不是 solver 数值失败 |
| 原尺寸目标 | `50×25×140 nm`、0.7 nm；15,232 cells 是 derived 候选，32,060 modes 是 measured inventory；目标限制 2 TB 十进制和 48 h | 目标 q NNZ/factor、完整解、官方 R/T/A 和精度均无实测 | Krylov/scratch/Hhat 等已有单对象数字是派生 payload，不是同一时刻 RSS | `NOT_QUALIFIED`；不是数学上不可能的结论 |

B0 代表小模型；Gx560 与 E1 改变网格和物理电尺寸，所以彼此不能作为单变量 p/h 收敛试验。Gx560 的旧同离散 p6 target+p4 correction 保存场是匹配比较基线：340 个模式功率最大绝对差 `2.2270624789e-8`；11 个冻结显著模式最大相对振幅差 `8.6046720745e-7`，限值 `1e-4`。共同子单元的八类场对照、各自输入和 mode/mesh/field identities 见正式结果 compact。

## Gx560 成本、因子与参考 PC

| 项目 | 实测与口径 |
|---|---|
| 新旧整体比较 | outer iteration 171→3；workflow `1925.862866→2407.572416 s`，增加 `481.709550 s`（约 25.01%）；tree RSS peak `5.256→10.295 GB`。迭代减少不等于全流程加速，workflow 增量尚未完全归因 |
| 因子同时库存 | 四个 q 因子同时 live；setup parent `54.226915 s`；numeric q0–q3 `4.608882/9.844299/6.028945/13.550974 s`。INFOG9 raw=`41320088/41253248/41789336/41269544`，无依据解码为 factor entries；INFOG19/22 十进制 upper bounds 合计 `4.645/4.080 GB` |
| factor release 口径 | all-q 销毁前另测 tree RSS `10,189,733,888 B`；同 root、同四 PID/start-ticks 的 cleanup 配对样本 member RSS 总和从 `10,289,065,984` 降至 `4,354,420,736 B`，下降 `5,934,645,248 B`。这是 whole reference-PC cleanup 观测，不全归因于 MUMPS，也不和 peak 相减 |
| assembly sector 0 | parent `230.155492 s`；projection `60.937886 s`；sparse accumulation `154.393760 s`；contribution generation `14.590967 s`；CSR accumulation calls 2916 |
| assembly sector 1 | parent `192.384544 s`；projection `57.769324 s`；sparse accumulation `121.442918 s`；contribution generation `12.947970 s`；CSR accumulation calls 2372 |

assembly 子阶段嵌在父计时内，不能把父和子重复求和；也不能把全 workflow 的 `+481.709550 s` 全归因到稀疏累加。四 q startup reference 共 16 次 MatSolve，factor strict probes 4 次，3 次 target PC 共 12 次，修正 0 次，总计 32 次 q MatSolve。三次 apply 都选 candidate 0；前两次 q solve 最大残差 `1.5744e-10` 和 `1.6729e-10` 未达到旧 strict `1e-10`，但都低于 V15 实际调用的 `1e-8`。全程最大 eta `4.9656567445e-9`，消元 FE `2.4692342908e-9`，完整增广 FE `1.9232496879e-10`，alpha closure `1.7789327117e-11`，均满足 V15。完整 PC wall-time 没有独立计时；native evaluation 子时间不能代替完整 PC。

已测最大 assembly 子阶段为 `LEGACY_GLOBAL_CSR_SUM` 的 sparse accumulation。旧 B0-only preallocated CSR 配对比较只节省 `6.370516 s`，且 Gx 256 MiB staging cap 未资格化。唯一下一工程对象建议是 bounded-staging、Gx-safe global CSR accumulation candidate：逐 q 检查矩阵身份/结果，测端到端 assembly 时间和 staging 峰值；本轮没有运行该候选。

## E1 资源 Gate 和时间分类

| Gate 输入 | 数值 |
|---|---:|
| live process-tree RSS | 12,064,264,192 B |
| dynamic total cap | 12,474,302,464 B |
| projected process-tree RSS（预测） | 19,192,602,560 B |
| physical available memory | 544,256,000 B |
| evidence reserve | 134,217,728 B |
| 总 RSS 与增量余量不等式 | 均不通过 |
| task/cgroup swap peak；descendant cleanup | 0 B；完成 |

真实 CSR rows/NNZ 与 symbolic estimate 分开记录。INFOG16/17 合计 `6.53 GB` 是 symbolic estimate，不是数值因子实测；INFOG3 等 raw 字段不能冒充 actual CSR NNZ。协调中断 workflow `102.788224005 s` 单独保留：它不是用户要求停止，费用不退。随后 E1 正式 workflow `5671.918121 s`、watchdog `5671.578106 s`、UTC wall `6275.443430 s`分列。

## 目标边界与后续工程

目标精度与容量仍有具体未闭合项：

- y/z 精度和 general-Ny orbit/索引/mapping 尚未资格化；现有 p6 路径锁定 Ny=4、local Ny=2。
- 目标 q CSR NNZ、indptr 安全性、四 q 因子 fill/工作区和同时 live 库存没有实测；当前全局 NumPy、int32 与 MPI1 假设也没有分布式/int64 资格。
- reference assembly 仍调用 `_materialize_Hhat()`，mode² 中间对象的真实生命周期未被目标规模测量。
- 完整 AUTO 882-row 选定模式边界路线在本实现中的映射、索引和输出身份没有闭合；84-row 压缩路线未资格化，不能声称可替代。
- recovery、field 输出、factor release 与 checker 的冷启动完整流程没有在 2 TB 十进制/48 h 条件下实测。

下一主线只有 Gx560 的 bounded-staging CSR 累加候选；y/z、general-Ny 和目标级容量属于并行保留的资格缺口，不由该候选自动解决。已有 Krylov `3.70 GB`、scratch `4.43 GB` 和单个 32,060² complex128 H `16.45 GB` 是派生对象大小，不代表同时 RSS，也不单独证明目标可行或不可行。

## 依赖组与证据边界

| 依赖组 / 建议顺序 | 数值行为 | 主要依赖文件 | 对应测试 | fresh PDE / 证据 | 合入建议 |
|---|---|---|---|---|---|
| reusable runner/watchdog（先满足入口依赖） | 不改变离散或方程；修正 profile/ABI 注册、正式入口与受控资源生命周期 | `scripts/run_case.py`；`src/runners/task038_launcher.py`、`task038_full3d_iterative.py`、`task038_input_worker.py`、`task40_v10_abi.py`；`src/io/input_schema.py`、`input_validation.py`；`src/geometry/task40_nonseparable_plan.py`、`physical_intermediate_profile.py` | 按源分列 103、29、41、49 pass/1 skip；见 V15 test summary 与各 source-freeze receipt | B0 original、Gx560、E1 由相应冻结 source 启动；E1受控停止，不能外推为 runner 的目标容量资格 | 先核对身份/schema/watchdog 依赖，再合入数值核心；不单独改变默认策略 |
| production numerical/core（第二顺序，仍需审批） | 加入独立增广 FE 预算和 V15 PC 选择；不改真实 target A6 与物理模型；保持 opt-in | `src/solvers/augmented_reference_correction.py`、`task40_v10_p6_mumps.py`、`task40_v10_p6_yorbit.py`、`task40_v10_p6_periodic_profile.py`；`src/runners/physical_p4_schur_v14.py`、`task40_v10_worker.py` | source `40dbe138` 的 `test_task40_v15_routes.py` 和 `test_task40_augmented_reference_correction.py` 属于 61-pass suite | B0 原输出门失败但恢复通过；Gx560 完整 target/physics/comparison PASS；E1止于 symbolic | 作为独立显式研究策略审查；不提升 ordinary default |
| checker/benchmark（第三顺序） | 不求解/不改矩阵；从 saved packet 重算输出、身份和比较 | `src/runners/task40_v10_output_checker.py`、`task40_v10_saved_output_recovery.py` | `test_task40_v10_output_checker.py`、`test_task40_v10_saved_output_recovery.py`；纳入 source `40dbe138` 的 61-pass suite | B0 saved-field 独立输出 checker PASS；Gx560 独立输出 checker 与同离散比较 PASS | 与 runner/core 对齐后合入；保留原 exit 4 负结果 |
| compact evidence/docs（第四顺序） | 不改变数值行为 | 本节链接的四份 compact、`response_v15.md`、README、summary、test summary、progress、model registry、run index | 最终文档合同 29 passed / 134 subtests | 报告中的 B0/Gx560/E1 结果绑定原 run 和 checker hashes；无新 PDE | 作为一组保持 hash/link 一致后合入 |
| research-only（独立研究分组） | 四 q p6 native augmented residual PC；尚未实施的 bounded-staging CSR candidate | V15 数值 core 依赖；候选 CSR 尚无实现、测试或 fresh run | PC 合同测试与 Gx560 run 仅资格化现有策略；CSR 新候选 `NOT_RUN` | Gx560完整PASS但workflow +25%；E1资源停止；无 CSR 候选证据 | 只留显式 opt-in / research；bounded-staging candidate 需后续单独审查 |
| do-not-merge / do-not-claim | 不改阈值、MUMPS参数或普通默认；不把预测写成测量 | 目标 readiness 与成本 compact 中的 unknown 项 | full repository pytest、MPI4、Ruff、CI、target-scale tests 均未运行 | E1 numeric/KSP/field NOT_RUN；原尺寸 2 TB/48 h 未资格化；continuum 未证明 | 不以本轮证据合入/宣称生产默认或全流程加速 |

详细解释见 [Response V15](../response_v15.md)、[Review V15](../review_report_v15.md)、[test summary](test_summary.md)、[README](../README.md)、[development model registry](../../development_model_registry.md)、[development progress](../../development_progress.md) 和 [run index](records/run_index.json)。四份 compact 为 [native PC contract](records/review_v15_native_pc_contract.json)、[failure witnesses](records/review_v15_failure_witness_and_repairs.json)、[formal results](records/review_v15_formal_results.json)、[cost/readiness](records/review_v15_cost_and_readiness.json)。

---

# Task40extra Review V14 历史结果：Gx560 物理作用身份门失败，目标仍未资格化

本节更新当前状态；V12、V11 与更早历史原样保留在下方。冻结源码为 6ac8cf7fd4697e575a4bf47a862c560ae290076b。V14 完成 Gx560 四个 p6 q 因子和参考 RHS 检查，但物理 RHS 的独立 action identity 为 1.6834572689277185e-11，超过严格 1e-11 门槛，因此 Full3D target solve 未启动。V14 没有 Gx560 官方 R/T/A；Gx784 未运行。固定窗口未刷新。

## V14 统一结果表

| 模型 | 网格、方法和原因 | 结果与指标 | 时间与资源 | 状态边界 |
|---|---|---|---|---|
| B0 | 4×4×5、80 cells、p6、532 modes、四 q；提供小模型完整 anchor | 已归档 R/T/A = 0.9842736080926642 / 0.014240518143990319 / 0.0014858737633455053；A_volume=0.0014858738462134112；能量闭合 8.286793473644138e-11；释放后真残差 1.6089762312332008e-8 | 原 workflow monotonic 1340.82869785605 s；RSS/cgroup 峰 3,248,488,448 / 4,484,915,200 B | 复用既有 PASS；V14 未重跑，也不改写原始 worker 历史分类 |
| Gx560 | 10×4×14、560 cells、p6、340 modes、四 q；真实三维缺口参考问题 | 总行 380,040；独立周期行 365,760；内部行 252,000；每 q 行 28,508 / 28,508 / 28,576 / 28,508；NNZ 15,451,743 / 15,479,361 / 15,581,290 / 15,479,361，总计 61,991,755。四 q 严格真残差均通过；物理 action identity 1.6834572689277185e-11 > 1e-11。R/T/A 未生成 | 完整 workflow 2220.8270128549775 s；policy charge 2420.165726454603 s，分开记；树 RSS/cgroup 峰 10,168,500,224 / 11,207,577,600 B；swap 0 | NUMERICAL_GATE_FAILED_BEFORE_TARGET_SOLVE；不是资源/时间停止 |
| Gx784 | 14×4×14、784 cells、p6、340 modes；条件网格扩展 | 无 V14 数值或物理测量 | 未运行 | NOT_RUN：Gx560 必需数值门未通过 |
| 原尺寸目标 | 50×25×140 nm、0.7 nm；既有候选 272×4×14=15,232 cells，模式清单 32,060 | 网格计数为 derived；模式数为 measured inventory。真实 NNZ、CSR indptr、目标解和 R/T/A 均未知 | 四 q 同时因子工作区、目标 KSP、恢复输出、2 TB 与 48 h 端到端资格未知 | NO_GO / NOT_QUALIFIED；不是数学不可能性证明 |

本轮没有受控 p/h 收敛对照：三个有效或尝试中的模型均为 Full3D iterative、p6、MPI1；B0 与 Gx560 的网格、几何和模式数不同，不能把它们的差当成单独 h 或 p 效应。Hybrid、direct reference、其他 M、其他 MPI 数均未比较。

运行身份：复用 B0 source 0a442ba11a66525d5010d1b6cd6384d0de8d8eab、input SHA256 dfe7535c03da661c458ec746af6e4dd25c8d0b402fd0573b4bc4e0620dbb4f63；V14 Gx560 source 6ac8cf7fd4697e575a4bf47a862c560ae290076b、input SHA256 5306827b5bd212faca41c8606eb0d9ace40cc81608a283d56dbddaa161b6ae42、physical model SHA256 d1ba222b0fe8989f6f8758f4f7a776506691e393f596f41ed02d25d0a9781d98。正式结果、完整 run paths 与 artifact identities 见 V14 formal results 和 run index。

## Gx560 因子、修正、装配和资源

四个 q 因子同时存活。MUMPS INFOG 原始字段解码得到的 allocated 与 used 保守上界总和分别为 4,645,000,000 B 与 4,080,000,000 B；INFOG9 原始整数保留，因缺少有依据的单位解释，不推算因子条目数或填充量。每个 q 的 CSR 哈希及 INFOG 明细见 [V14 formal results](records/review_v14_formal_results.json)。

| q | 行数 / NNZ | 严格真残差 | allocated / used 上界 | numeric 时间 |
|---|---:|---:|---:|---:|
| 0 | 28,508 / 15,451,743 | 3.986719346e-11 | 1,158,000,000 / 1,017,000,000 B | 4.298435826 s |
| 1 | 28,508 / 15,479,361 | 1.591872870e-12 | 1,151,000,000 / 1,011,000,000 B | 4.954547766 s |
| 2 | 28,576 / 15,581,290 | 8.624700464e-13 | 1,170,000,000 / 1,028,000,000 B | 4.526408245 s |
| 3 | 28,508 / 15,479,361 | 2.813498243e-12 | 1,166,000,000 / 1,024,000,000 B | 4.703848838 s |

数值修正把完整参考残差再交给同一组四 q 因子求解，并同时更新场与 port 系数；一次修正最多四次额外 q 求解。通用完整 RHS 和全内部行见证各修正一次，共 8 次额外 q MatSolve；计数器记录 4 个初始 startup witness callback 加 2 个 correction callback，raw augmented inverse 调用合计 6 次，target PC 调用 0 次且未运行。两次完整 raw augmented inverse callback 合计 16.055923939 s，纯 MatSolve 秒数未知。内部见证的 complete_augmented_FE 残差为 4.431933190549465e-12，full_regular 残差为 4.431934540620194e-12；q0 strict 失败但处于已授权有界不精确范围。物理 RHS 的 twist1 原始分母为 5.288411619304687e-16、相对残差为 165.55965111916072，逐扇区 1e-8 有界门也失败；全局完整/合并值较小不能覆盖该逐扇区门。

预分配 CSR 在 B0 配对组件比较中省下 6.370516 s，但未验证 Gx 的整体 setup 或暂存峰值，故 V14 选择已授权的 LEGACY_GLOBAL_CSR_SUM，保持参考 PC 不变。Gx 两扇区装配分别为 252.601001339 s 和 192.365708545 s；四 q setup 30.428798860 s、numeric 合计 18.483240675 s 均是完整 workflow 的子阶段，不能重复相加。动态 launch cap 13,286,932,480 B；树 RSS 峰 10,168,500,224 B，cgroup 峰 11,207,577,600 B；PSS profile 禁用。资源门和时间门均通过。

| 原尺寸候选量 | 当前证据与边界 |
|---|---|
| 网格与电尺寸 | 272×4×14 与 15,232 cells 是计数推导；名义均值 h_x=0.1838 nm、h_y=6.25 nm、h_z=10 nm，不是已生成网格的单元尺寸。自由空间 k0L 与 phase-per-cell 仅为诊断，不证明 FE 精度或材料相位 |
| 模式与行数 | 32,060 AUTO 模式是已测 inventory；p6 full-storage rows 10,228,620。候选行数低于 int32 范围不代表实际 NNZ/CSR indptr 安全 |
| 内存与时间 | Krylov、scratch、单个稠密 H 的已知数是派生 payload，不是同时 RSS；目标实际 NNZ、q 因子 fill、生命周期、KSP 和总时间 unknown |
| 资格 | 原尺寸没有 FE mesh、matrix、factor、PDE、官方结果或 2 TB / 48 h 端到端实测 |

## V14 下一步与选择性合并

下一单一电尺寸候选是保持波长 0.7 nm 的 E1 q1.25，计划轴计数 10×4×19=760 cells，输入 SHA256 5c0aa01d1bb327f1331b69cfe359c6f775961398d316c2f88d3aeaff978af8fd。它保持 HELD、未运行；模式、实际网格和资源成本未知。当前 V13 case allowlist 没有 E1 的完整 reference-PC 路由，V14 不扩大 allowlist。下一审查须先处理 Gx560 的物理 action identity 问题，并另行审查 E1 路由与目标 y/z h/p 依据。

| 依赖组 | 建议 | 依赖、测试与 fresh PDE 证据 |
|---|---|---|
| production numerical/core | 不设为默认 | Gx560 没有通过物理 action identity，也没有 target solve；需修复并获得新的匹配数值证据后再评估 |
| reusable runner/watchdog | 保留通用监督、身份、资源门与已审查输入路由 | E1 source-ready 46 passed；后续 6ac NameError 修复另有 4 focused pass，分开记录；validate-only 对 B0/Gx560/Gx784 均 valid；不代表 PDE 资格 |
| checker/benchmark | 保留按原始字段重算和分开的见证分类 | 覆盖 strict pass、bounded-inexact 与结构失败；无 target 场 checker 输入 |
| compact evidence/docs | 可供主控审查后提交本响应、summary、target bridge、run index 与紧凑 records | 三个文档合同测试 24 passed、134 subtests passed；不含 PDE |
| research-only | 保留 V13 参考修正、legacy CSR 选择和四 q Gx560 库存 | 只在研究配置中；无 Gx560 完整 target pass |
| do-not-merge / do-not-claim | 不放宽 identity 门、不扩大 E1 allowlist、不宣称 Gx784 或原尺寸资格 | Gx784、原尺寸 PDE、MPI4、full repository pytest、Ruff、CI 未运行 |

证据入口：[Response V14](../response_v14.md)、[接续记录](records/review_v14_execution_handoff.json)、[参考与装配记录](records/review_v14_reference_and_assembly.json)、[正式结果](records/review_v14_formal_results.json)、[成本与修复账](records/review_v14_cost_and_repairs.json)、[目标桥接包](v14_engineering_to_target.md)、[run index](records/run_index.json)、[测试摘要](test_summary.md)。此前 V13 B0 pass 与 Gx560 pre-numeric resource stop 均保留；attempt 1 NameError、V14 物理 action gate failure 与所有 NOT_RUN 项分别登记。

---

# Task40extra Review V12 结果总览：共享变换实测，Gx560参考逆 Gate 失败

本节是当前状态；下方 V11、V10及更早结果保留为历史。V12冻结source为`6d2c54389fe885ecf24d474a8782166ff31f9154`。p6单元内部共享变换实际进入Gx560并减少了named-view重复指向独立backing的字节账；Gx560完整regular-inverse witness有三项阈值失败，worker在进入Full3D FGMRES前退出。资源/time gate通过；R5 Gx784、官方Gx560 R/T/A和原尺寸路线均未运行/未资格化。

## V12模型和证据状态

| 模型 | 网格/方法/输入 | 数值或物理结果 | 时间/内存 | 状态和边界 |
|---|---|---|---|---|
| B0 首次启动尝试 | source `696383d39b60143a2881b753f19659c05bf6769d`；run 目录 `20261006T120744.861717Z`；NameError 在数值求解前终止 | 没有 PDE 数值结果 | worker workflow monotonic `1107.2371964480262 s`；watchdog policy `1207.4370952185634 s`；tree/cgroup峰=`2,749,452,288 / 3,135,488,000 B`；swap0 | 启动修复的独立负结果；后代已清理。worker 与 watchdog 时钟范围不同，不相加；对应修复测试8 passed |
| B0 fresh reference | 80 cells、p6、532 modes（每侧266）、四q、原两单元缺口；输入SHA `d4d72a4288aa0313432f7bea668543c60a2716144ce9c8333b2c271367d8f73e`；worker source `c08c135f0e60198475525cd1c761cb0ba686d948` | A6 true residual `1.6089774391665316e-8`，solver/residual通过；worker在物理输出门exit4，official=false。`6d2c543`离线保存场复核得到R/T/A_balance/A_volume=`0.9842736080926772 / 0.014240518143988908 / 0.001485873763333926 / 0.00148587384621333`，能量差`8.287925901129256e-11` | workflow/watchdog/KSP=`1068.533 / 1068.487 / 4.583` s；tree/cgroup RSS峰=`2,796,560,384 / 3,199,516,672 B`；swap0 | fresh求解和offline saved-output revalidation是两层证据；保留原exit4和official=false。完整FE系数/MPC身份byte-equal，E/H/curl零差是代数推导，本轮无新积分 |
| Gx560 V12 | 10×4×14、560 cells、p6、340 modes、四q、原非可分缺口；输入SHA `50c8691446cbc24533ee31ae945c75806c29a0a06d002287723f814372ba44a9`；source `6d2c54389fe885ecf24d474a8782166ff31f9154` | 原参考方程`2.0058682739535859e-10 > 1e-10`；两局部原方程合并`1.4183642641040464e-10 > 1e-10`；alpha/port closure`1.1770163447864681e-11 > 1e-11`。q探针、内部恢复、扇区动作及port equation各自通过 | workflow/watchdog/policy observation=`2089.323 / 2088.777 / 2320.812` s；tree峰`10,181,664,768 B`；cgroup峰`10,708,639,744 B`；task/cgroup swap0 | `WORKER_FAILED`, exit4，派生分类`REGULAR_P6_INVERSE_GATE_FAILED`；不是资源/time stop。KSP、最终A6、官方R/T/A和同离散p4场均`NOT_RUN` |
| Gx784 V12条件阶梯 | 14×4×14、784 cells、p6、340 modes；输入 `input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_y_orbit_v12.dat`，SHA256 `56d9b05bf157a213d608da93e42fdd1dad6377aa9fad96cdd962d3f6086abdd5`，格式校验通过 | 无本轮残差或物理结果 | 无本轮资源读数 | `INPUT_FROZEN_BUT_NOT_RUN`；Gx560 Gate未通过，因此未启动 |
| 原尺寸目标 | 约15,232 cells / 32,060 full-AUTO modes；50×25×140 nm、0.7 nm目标 | 没有目标级四q factor共存、Full3D迭代、输出与目标精度证据 | 2 TB / 48 h未知、未资格化 | `NO_GO / NOT_QUALIFIED`；不是数学不可行证明 |

## 四q因子、共享存储与资源

Gx560的四个p6 q矩阵rows/NNZ分别为28,508/15,451,743、28,508/15,479,361、28,576/15,581,290、28,508/15,479,361。每个numeric factor probe residual都低于`1e-10`；q因子在销毁前同一快照同时live。raw INFOG19/22合计4,641/4,076 decimal MB；加1 MB/项解码后allocated/used保守上界为`4,645,000,000 / 4,080,000,000 B`。同一四因子快照tree RSS为`10,021,572,608 B`；整场tree/cgroup峰分开报告，不能相加。factor INFOG条目数不是byte数。

预symbolic bank event实测6个状态、1个basis、1个matrix template、6次builder调用、1,120次matrix请求、1,114次cache hit、builder`0.066425 s`；一个3,240,000-byte matrix backing供1,121个视图共享，范围只覆盖cell-interior。整个named-allocation inventory logical view bytes含alias为3,843,915,904 B，unique backing owners为215,115,904 B；差值3,628,800,000 B是inventory字节账，不是测得的RSS节省。owner总数15,047含全局/局部、edge/face和索引等所有对象，不能读作bank大模板数量。bank-ready时inverse build/request为0，不外推成整场inverse计数。设计来源为 dot 冻结 source `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、blob `ff40105bd9139a856b09987596c961458f84ab0e`、原文件 SHA256 `9ece954f962dc6bab18a02f6b48b53998219fba3f611647a44404757f219b66f`；这是 p4 bank source 到 p6 cell-interior 的适配沿革，不是84-row压缩资格或本轮对 dot 的访问。

| 阶段/量 | 实测或派生值 | 口径 |
|---|---:|---|
| MUMPS reference-PC builder constructor | `29.169 s` | 输入矩阵已存在后的CSR/四q factor-builder及probe计时，不是全setup |
| 四q symbolic / numeric timer和 | `0.992421 / 18.096982 s` | per-q子阶段，不与总计时重复相加 |
| 全局/sector实体与物理局部张量构建 | `unknown` | 未有独立完整计时 |
| Gx560 worker workflow / watchdog / policy gate | `2089.323 / 2088.777 / 2320.812 s` | 三种时间范围不同，不相加 |
| Gx560 tree/cgroup peak | `10,181,664,768 / 10,708,639,744 B` | 不同内存口径，不相加；PSS禁用 |
| 原尺寸全q fill、冷JIT、outer iteration、输出内存/时间 | `unknown / NOT_RUN` | 不线性外推 |

每个q raw INFOG、CSR SHA、factor entries、探针残差、per-q tree RSS和销毁前live snapshot详见[formal results](records/review_v12_formal_results.json)与[memory lifecycle](records/review_v12_memory_lifecycle.json)。

## 选择性合并与下一步

| 分组 | V12建议 | 限制 |
|---|---|---|
| production numerical/core | 本轮不建议把Gx560 bank/regular inverse路径设为生产默认 | Gx560 required reference-inverse gates失败；source仅研究profile实际证据 |
| reusable runner/watchdog | 沿用当前已有运行器和进程树/时间/资源Gate | 本轮未验证新runner；Gx560不是resource stop |
| checker/benchmark | 保留B0输出范围回归与独立saved-output checker证据 | 离线saved-field pass不能改写原fresh worker exit4 |
| compact evidence/docs | 本轮新增V12 response、结果/成本/transfer记录 | 由主控审核后集中提交；执行者未Git写入 |
| research-only | 共享p6内部变换、局部恢复与四q参考逆完整残差修正候选 | 下一唯一建议为一次完整reference residual correction，尚未授权/执行，耗时和临时内存`unknown` |
| do-not-merge / do-not-claim | Gx560完整solver pass、Gx784、全尺寸AUTO/2TB/48h、84-row压缩或dot资格 | 均未通过或未运行 |

详细解释及转交边界见[Response V12](../response_v12.md)、[工程收口报告](review_v12_shared_transform_engineering.md)、[原尺寸 readiness](v12_transfer_and_target_readiness.md)、[test summary](test_summary.md)与[run index](records/run_index.json)。主控在 R6 precommit observation 中记录累计 campaign charge `17395.54872271069 s`、numerical remaining `68404.4512772893 s`，证据 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w12_wsl/main_v12_r6_precommit_campaign_observation.json`（SHA256 `67c1065bfbdd27f42e5e40cbc5ce9302e0d422e82c23a16096d23cd79120994a`）。该观察覆盖到自己的时间戳；之后的文档/测试/Git收尾仍在原窗口中，由主控推送后写最终 terminal receipt，不将该观察冒充最终结算。

---

# 历史：Task40extra Review V11 保存场复核与组件动作通过，Gx560 停在数值因子化前

## Review V11 历史结果

本节记录V12之前的状态；下方 V10 与更早内容仍为历史。S1–S2 的正结果来自既有保存数据，S5 是两个代表面的边界分块动作，均不是新的 PDE。V11的Gx560在四q symbolic后因资源Gate受控停止；V12正式R4已在本文件上方更新为四q numeric完成、但reference-inverse Gate失败。旧V11停止原因与原始数值保留。

| 阶段 | 模型 / 方法 | 结果 | 状态与范围 |
|---|---|---|---|
| S0 | B0：80 cells、p6、真实两单元三维缺口、y 向四 q | true residual `1.6089774391665316e-8`、native witness `1.6089791915820923e-8`；旧能量闭合 `6.581916436299018e-5` | residual pass；旧物理负结果保留。四 q 在销毁前同时存活，逐 q MUMPS 原始审计见综合报告 |
| S1 | 同一 B0 保存场的 gauge-aware 端口功率 | R/T=`0.9842736080926772 / 0.014240518143988908`；A_balance/A_volume=`0.001485873763333926 / 0.00148587384621333`；能量差`8.287925901129256e-11` | 独立 checker PASS；仅 saved-field 后处理，不是新 PDE |
| S2 | 原尺寸上/下两个 p6 局部块 | forward error=`5.35e-14 / 5.14e-14`，局部原方程误差`4.77e-16 / 6.41e-16` | 局部 repair candidate；全 q60 行重检与全目标 volume MPC 未运行 |
| S3 | B0 可选 direct reference | `NOT_RUN_AUTHORITY_LIMITED_OPTIONAL_REFERENCE` | G0 witness/map 与 B0 gauge、RHS合同不匹配；不是容量或 ABI 失败，也不是缺少用户授权 |
| S4 | Gx560：560 cells、p6、340 modes、四 q | 四 q symbolic 完成；projected tree RSS `15,205,944,640 B` 超过 effective finite cap `13,462,286,336 B` | `RESOURCE_CONTROLLED_STOP_BEFORE_NUMERIC`；numeric、KSP、场均`NOT_RUN`。Gx784因条件未满足未运行 |
| S5 | 上下代表面完整 882 行、32,060 模态 Bα/Dx 动作 | 两面 full checker PASS；最大 Bα/Dx差分别为 top `1.13e-13 / 3.86e-14`、bottom `1.04e-14 / 3.91e-15` | 仅两个代表面；84行替代方案未资格化；本轮主线未重跑压缩，S5使用882行；非全局MPC或PDE |
| S6 | 资源与可推广性判断 | seq8089旧快照保留；主控交付观察 seq8090（`2026-10-06T09:14:00.836725318Z`）：累计 charge `28609.104986536724 s`、推导 numerical remaining `57190.895013463276 s` | 窗口未刷新，`final_settlement=false`；Git/测试尾段由主控在同一账本后续计入。下一项唯一优先工作是调查 Gx560 数值阶段前 `10,295,283,712 B` live RSS 的对象所有权与生命周期；目标规模尚未资格化 |

### 资源数字的口径

| 数据 | 测量 / 推导 | 边界 |
|---|---:|---|
| B0 销毁前四 q MUMPS 内部数据 | INFOG19/22逐 q为123/110、125/112、124/111、125/112 MB；四因子同时 live | MUMPS内部读数，不是 RSS；INFOG29是因子项数，不是字节 |
| Gx560 | gate时 tree RSS `10,295,283,712 B`；全程tree peak `10,418,892,800 B`；cgroup peak `10,930,950,144 B`；swap 0 | current/projected/cap、process-tree峰和cgroup高水位分开；数值阶段未启动 |
| S2 | 单 Python 进程 `ru_maxrss=634,454,016 B` | 不是 process-tree 或 cgroup 峰 |
| S5 四阶段共享服务 | wall `15.182 s`、CPU `11.481 s`、共享 cgroup peak `546,459,648 B`、swap 0 | 一个 cgroup 串行承载四阶段；逐阶段 RSS另列，不能相加 |

V11 最终文档与源码 HEAD `223f602b84761eb99631e7a61a784c3d6c857c04`。详细结果、选择性交接和证据边界见 [Response V11](../response_v11.md)、[综合工程报告](review_v11_engineering.md)、[test summary](test_summary.md)、[run index](records/run_index.json) 与 [V11 manifest](records/review_v11_manifest.json)。五个 hash-bound compact records：

- [gauge/power](records/review_v11_gauge_power.json)
- [local recovery](records/review_v11_local_recovery.json)
- [engineering results](records/review_v11_engineering_results.json)
- [cost and repairs](records/review_v11_cost_and_repairs.json)
- [manifest](records/review_v11_manifest.json)

---
# Task40extra 结果总览：Review V10 B0物理解未通过能量门；V9及更早历史保留

## Review V10 综合结果

B0 是 80-cell、真实三维两单元 void 的周期小模型。p6 预条件方法只在预条件背景填回缺口，用 y 方向四个相位分支的完整 p6 准确 LU 为不变的缺口 target 与 RHS 提供修正方向；四个 factor 同时保留，完整恢复36,000个内部未知量，因此增加setup与内存成本。三步残差通过仍不等于物理能量通过。A 的 q60 表示边界积分分辨率；B0 的四个 q 表示 y 周期相位分支，两者不是同一指标。

### 一级账：模型、方法和物理/数值结果

| 对象 | 模型与方法 | 可比结果及物理量 | 状态与原因 |
|---|---|---|---|
| A有限边界 / p4、p6局部恢复 | 保存场重检与V2上下边界续算；q60为积分分辨率 | q60五类有限见证通过，冻结saved_q60_apply分母为`5118.679535729753`、relative action error `9.063390130105725e-15`、n0最大逐模相对值`3.3410810842083564e-15`；历史Git blob/path入口保留在`records/review_v9_w1_closeout_v1.json`。p4 top/bottom已知场前向恢复误差`4.071005827429115e-13` / `3.318404914520256e-13`；p6为`2.202932653970648e-11` / `2.42442721473547e-11`；限值`1e-11` | p4 PASS；p6为受控负结果。p6超限量是已知内部场恢复前向误差，不是方程残差；原方程残差门`≤1e-10`通过。A当前不资格化仅因p6恢复门。A代表边界链的完整32,060个B/D行、generic complex输入、nonzero port RHS见证已覆盖；不代表B0全局逆算子的B/D逐行资格。旧q30失败不自动否决q60 |
| B0 p6逆算子组件 | 4×4×5 cells，真实三维两单元缺口，p6，4个y相位q | 全端口532（top/bottom各266）；存储/独立行55,950/52,992；内部/trace行36,000/16,992；每q增广trace+port行为4324、4400、4400、4400；q真残差最大`7.493923678060789e-12` | B0所列RHS/行集合检查通过（不包含A代表边界的B/D逐行资格）；regular reference抽样原方程残差`1.465060265308628e-11≤1e-10`。不是缺口target残差，也不构成物理模型资格 |
| B0 p6物理候选 | 同80-cell模型；全p6准确LU仅作预条件器背景；MPI 1 | 3步；显式target真残差`1.6089774391665316e-8`；post-release native A6 witness `1.6089791915820923e-8`；求解限值`1e-6` | 数值残差PASS；能量闭合`6.581916436299018e-5>1e-5`，因此`official_result=false`，无official R/T/A |
| B0 p4控制 | 求同一个p6 target，只改变preconditioner | 2048步，KSP reason `-3`，A6真残差`0.966131083707469>1e-6` | 控制不通过；不是成功速度对照，不支持宣称p6更快 |
| C及目标尺度 | C/Gx560、完整15,232-cell、自动全尺寸与原尺寸A链global MPC/target-scale mapping | 未产生official R/T/A或目标容量证据 | `HELD_NOT_RUN` / `NO_GO_NOT_QUALIFIED`；不表示其它实现或资源条件下数学上不可能。B0小模型已有native/MPC身份 |
| Campaign账本 | 原固定窗口SHA `0052698cbfd8034c82f1c471b1f2ed29a2cb2e5f7601d317166f251e0c7e794a` | seq25175 A程序末快照`63514.15687973229 s`；seq25176提交前收口快照`67613.8129036653 s`；收据`benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl/supervisor_v10_precommit_closeout_receipt.json` SHA-256 `f813029a331c50e2079e6f63cb64301c2315c352c543a6f19137f881c5c4aa9d` | commit/push仍待执行并在同一窗口继续计费；两者均非最终结算且不重置账本。V9总费用仍`UNKNOWN_NOT_SETTLED`，已知下界`≥3617.121945417 s`单独保留；policy charge不是FE时间 |

B0 p6保存场只有诊断量，不是official R/T/A：R=`0.984273608092677`、T=`0.014174698896746551`、A_balance=`0.0015516930105763937`、A_volume=`0.00148587384621333`。R00_s/R00_p/R00_total、DoF和NNZ未由本轮证据确定，记为unknown；不得将R诊断值冒充R00或官方量。运行使用MPI1；此处PETSc scalar/int身份的紧凑记录为unknown/null。

### 二级账：资源构成、阶段时间与修复成本

| 工作/阶段 | 已知时间 | 进程树RSS峰 | cgroup峰 | swap | 归属与限制 |
|---|---:|---:|---:|---:|---|
| p4控制全worker | 1646.287435149 s | 2,377,383,936 B | unknown | 0 B | 同一p6 target、仅preconditioner不同；残差门失败 |
| p4控制KSP phase | 1519.454145885 s | unknown | unknown | unknown | full worker中的KSP阶段 |
| p6 B0全worker流程 | 1051.699122267 s | 3,713,953,792 B | 4,101,464,064 B | 0 B | solve已完成；输出阶段缺`pyvista`导致worker exit 4 |
| p6纯`ksp_solve_phase` | 4.899454752 s | unknown | unknown | unknown | 纯KSP计时 |
| p6父级solve phase | 6.441171838 s | unknown | unknown | unknown | 含外围动作，不是纯KSP |
| p6父级solve phase | 6.441171838 s | unknown | unknown | unknown | 含外围动作，不称纯KSP |
| 保存输出恢复全流程 | 33.431334133 s | 1,193,611,264 B | unknown | 0 B | 不含新PDE求解 |
| A原始W1 worker | 57.269548678 s | unknown | unknown | unknown | worker elapsed |
| A原始W1 watchdog | 71.495064558 s | 762,998,784 B | 916,602,880 B | 0 B | supervisor wall，非worker elapsed |
| A V1底部目录守卫失败 | 22.413856058 s | 716,390,400 B | 742,473,728 B | 0 B | 工程失败，底部数值工作未开始 |
| A V2底部续算watchdog | 83.070806061 s | 744,566,784 B | 928,624,640 B | 0 B | 322次采样，后代清理 |
| 更早工程前缀尝试 | 1198.994425458 / 1029.516402189 / 1093.389170074 s | unknown | unknown | unknown | 原因依次为旧错误1e-11 gate并缺独立内部见证、缺sector_action_vectors参数、MappingProxy序列化失败；子阶段时钟unknown |

恢复子阶段restore/native build/operator rebuild/output/native/checker分别为7.318348325/3.301424436/3.401562392/20.304540596/0.463208863/0.018299836 s，watchdog为33.397827992 s；子阶段不与全流程或彼此相加。factor allocated/used、setup及factor阶段时间均unknown/null，不从父子耗时差推导。释放后inventory `used/peak=0`只表示采样时对象已释放，不代表四个q的实时并发factor内存。tree RSS、cgroup peak、factor库存和swap为不同资源口径。

W0旧worker `200.87894401792437 s`保留为历史成本，与上述V10 A程序预算快照、V9已知下界及未知总额分开。

### 选择性合并分组与下一步

| 依赖组 | V10内容及数值行为 | 依赖 / 测试 / fresh evidence | 合入顺序与边界 |
|---|---|---|---|
| production numerical/core | 未将p6候选提升为production default；official物理结果未产生 | 依赖能量门修复和完整目标资格；当前fresh B0结果是能量负结果 | 暂不合入为production方法；先修能量闭合并由新审查授权新anchor |
| reusable runner/watchdog | bottom continuation输出目录守卫修复；不改变物理方程 | 依赖V2 runner；a4源码输出目录fixture 3项通过 | 可先审查工程修复；需保留V1失败证据与V2续算产物 |
| checker/benchmark | A冻结尺度重检、底部续算独立checker及B0 p6恢复检查 | 依赖保存场、原checker、V1 recheck和V2产物；30项b2测试单独记账 | 在文档/compact之后审阅；不得覆盖旧checker的p4 top误判原件 |
| compact evidence/docs | Response V10、综合p6报告、两级summary、5份compact、test summary与run index | 依赖上述raw/report和source/input identity；定向文档合同待本地运行 | 最后收拢，路径和hash写入run index；不将诊断值称official |
| research-only | B0四q全p6准确LU预条件候选和本地cost记录 | 依赖p6 component/inverse与物理恢复记录；no official energy pass | 保持研究证据，不能设为production default |
| do-not-merge | 未资格化的全尺寸路径、C/Gx560运行结论、释放后0 factor inventory、任何伪official R/T/A | 证据均为not_run、unknown或energy-gate failure | 不合入为通过结论；master/default不由本summary改变 |

最终源、运行输入与诊断/负结果索引见[Response V10](../response_v10.md)、[Integrated p6](review_v10_integrated_p6.md)及`records/review_v10_*.json`。

---

## Review V9历史：W1保存数组参考审计与时间停止

W1检查的是代表表面上有限元切向场与32,060个外部模式之间的边界作用。q30和q60是表面积分的两种分辨率；高精度解析矩提供独立比较，用来判断原离散积分是否可信。本轮只审计既存数组，没有生成新网格或解Maxwell PDE。

| 核验项 | 实测与解释 | 状态 |
|---|---|---|
| q30独立参考 | 32,060个模式的最大恢复相对误差`5.705909332719913`，限值`1e-10`，最差`[top,-67,-34,s]`。原q30/q60差`5.705909332721303`原样保留。 | 诊断超限，参考整体尚未资格化；不能用较小完整作用差替代逐模式门 |
| q60独立参考 | 既存保存投影的最大恢复相对误差`4.033933451217359e-12`，低于`1e-10`；原H和分母不变。 | 通过有限范围的标量诊断；不是完整V9参考资格 |
| V2完整作用及误差界 | 缺少实际`n=0`见证；相对误差分母取新参考范数而非冻结的`saved q60_apply`范数；`gamma_256`没有覆盖全部构造、投影和scatter运算；缺少完成时三钟样本。 | 正式门未闭合。V2旧`gate_complete=true`字段仅作为历史原件保留 |
| 本地模式身份 | 32,060项；无索引key SHA`03c1965c…e95dec`、有索引key SHA`08d7464c…00899`、physics SHA`44c7bdc5…c3b8`。 | 本地身份桥可复核；dot完整raw不可用，跨来源逐值比较`NOT_RUN` |
| 本轮FE与官方输出 | FE worker启动0；p6未启动；production runner未重跑；无官方R/T/A。 | `REFERENCE_NOT_QUALIFIED`，原因是归因`TIME_STOP`，不是Maxwell数值求解失败 |
| V2 raw持久性与目录 | 2,084,777 B；只读fsync/重开SHA、10个ZIP成员CRC和NPY头部shape目录通过 | 仅证明保存文件的字节/容器结构，不读取数值或充当数学checker |

### 费用、时钟和资源口径

T0的UTC记录为`2026-10-04T23:31:43Z`，但该瞬间的monotonic、boottime和boot ID没有采样；deadline固定为`2026-10-05T03:31:43Z`，未刷新。clock结束时刻到后来三钟样本的UTC、monotonic、boottime增量分别为`3617.121945417`、`3296.706236768`、`3296.706236127 s`。取这段端点增量的最大值，得到已知保守费用下界`≥3617.121945417 s`，超过3600秒阶段上限至少`17.121945417 s`。它足以触发停止，但不是从T0逐段累计的完整费用；完整累计仍为`UNKNOWN_NOT_SETTLED`。此前只按双单调钟写出的303.293763秒剩余记录原样保留，现仅不再用于停止判定。

| 分项 | 可用记录 | 未知与边界 |
|---|---|---|
| 命令/activation修正 | ENOENT准备调用、activation参数及import path错误均记为准备事件；首次保存checker计算后因输出目录缺失退出，命令elapsed`1.223 s` | 准备与修复没有完整相邻三钟，分别保持`UNKNOWN`；不当作0或FE启动 |
| clock服务 | cap冲突启动拒绝`0.046 s`；observe-only阶段`61.162 s`单调/`67.386 s`保守实时时钟；enforce阶段`61.390 s`单调/`67.690 s`保守实时时钟 | 父/子服务计时不相加。两段都是clock-only，不是FE；observe-only不是强制阶段门 |
| 研究脚本与依赖 | mpmath 1.3.0使用同一合格prefix和本地wheel；负实轴球Bessel分支、V2 einsum维度均有修正事件 | 安装及两项修复耗时未知；测试历史为6项通过/4.29秒，收尾未重跑 |
| 分析、readback、cleanup | V2文件mtime为`2026-10-05T00:54:38.944557Z`；稍后的三钟样本不等于完成样本 | 归因结束、readback和cleanup独立区间均`UNKNOWN`；归因/整窗RSS、swap与峰值未采样，保持`UNKNOWN` |

enforced clock service自己的进程树RSS峰`33,574,912 B`、tree swap峰`0 B`、global swap页增量`0`只描述clock阶段；不外推为归因任务或整窗资源结果。旧V0–V8已结算费用、负结果和unknown均不改。详细事件、时钟端点、源文件哈希和依赖分组见[Response V9](../response_v9.md)及[机器收口记录](records/review_v9_w1_closeout_v1.json)。两份参考构造分析脚本和本地identity bridge以原字节保存于records，供审阅误差公式及身份编码。

新的资格化窗口若获批准，最小后续是补真实`n=0`见证、用冻结`saved q60_apply`尺度重判完整作用、补全浮点误差界并在落盘时采集三钟；全部通过后才由新review决定是否开始p6-only。当前窗口不续开。
原尺寸50×25×140 nm、λ0=0.7 nm目标仍为NO-GO（整机十进制2 TB、swap 0、完整流程48小时未资格化）；AUTO/全q公共后端没有新规模准入。dot仅以只读基准7580f5a48407a5c984aaf9311dc3733060d79f08引用，本收口没有执行或修改dot。

---

## Review V8历史结果：W0组件闭合；W1代表探针数值门失败并受控停止；V7–V4

## Review V8 后续：W0组件与保存数据独立检查通过（无PDE）

本次续作修复的是保存数据独立 checker 的文件描述符容量：首次 checker-only 在 carrier port 210 收到 `EMFILE`（errno 24）；第二次仅把这一个 user service 的 `LimitNOFILE` 设为4096后通过。随后对原 raw 目录只读打开并 fsync、重开哈希、逐数组重算SHA；没有再次运行 worker、没有重生成32,060通道库存、没有复制 raw。该结果关闭 W0 组件与独立保存数据核验门，允许进入 W1 源接线阶段；它不表示 Maxwell PDE、full A6、官方 R/T/A 或原尺寸能力通过。

| 阶段 | 方法与实测 | 结论与边界 |
|---|---|---|
| W0 attempt4 component worker | 80-cell p6 component、532 modes；`797.629 s`；进程树 RSS `2,204,782,592 B`；树 swap `0 B` | component controls pass；`PDE_solved=false`、official outputs false |
| 独立保存数据 checker | 从不可变 worker report/raw 重算955个指标；80 cells、29 classes、1,602成员、3,287角色；native制造态原方程相对残差 `1.077949573325129e-15 <= 1e-10`，最差恢复相对误差 `1.4966004617481827e-12 <= 1e-11`；checker `18.994 s`、树RSS `478,863,360 B` | `W0_FULL_COMPONENT_AND_INDEPENDENT_CHECK_PASS_NO_PDE`；是组件代数/恢复闭合检查，不是 Maxwell 正式解或物理精度证据 |
| raw持久性 | 1,602成员、`604,158,016 B`；fsync + reopened file SHA 1,602/1,602；post-fsync array SHA 1,602/1,602 | raw字节及成员元数据未变，没有 archive/raw 副本；`durable_archive_verified=false` 保留 |
| 文件描述符失败与修复 | 首次 checker-only errno24，6.205 s，树RSS 351,285,248 B；仅重试服务限制4096；fixture测得24个mmap FD增量、预计总FD 2,118/limit 4,096，余量1,978 | service范围限制；direct checker leaf `/proc` limit未采样，不伪造读数；其他失败/成本均保留 |
| 资源/时间 | worker和checker树VmSwap峰均0；有记录的 global `pswpin/out` 区间增量0，基线/末值783/3167页；checker RSS见上；窗口T0=`2026-10-04T13:04:57Z`，deadline=`2026-10-04T17:04:57Z` | 不宣称整机swap为零。checker完成时UTC推导elapsed `7515 s`，不是monotonic或费用；整窗准备/空档/charge仍unknown |

完整哈希和非合并边界见[W0 compact record](records/review_v8_w0_component_closeout_v1.json)、[W0增量账](records/review_v8_w0_incremental_workflow_ledger.json)、[run index](records/run_index.json)及[Response V8](../response_v8.md)。此前attempt2和attempt3的worker phase分别为`44.26769974210765 s`和`113.90223937504925 s`，attempt4自动checker失败为`3.137978855986148 s`；RSS及原失败记录路径见W0增量账，这些是独立phase wall值而非总费用。W1代表面FE组件探针已执行但未完成要求集；唯一7200秒窗口已冻结为T0=2026-10-04T15:24:35.195396Z、deadline=2026-10-04T17:24:35.195396Z。Task042两模块接线、定向测试、源码提交准备/主控审查、资源准入、代表面q30/q60和最大支持内部修正探针、checker及清理均计入本窗，不刷新、不排除已花时间；32,060有序keys必须原样复用，正式探针使用主控审查提交的clean source。W2、dot保持HELD，原尺寸仍NO-GO。

---

## Review V8 W1：边界Gate数值负结果、局部p4通过、p6受控中断

q30/q60表示同一表面作用的两种积分分辨率；这个对照用于发现表面积分是否敏感，不把q60当作已证明精确。此次只覆盖top/bottom代表面和两个p4单元，不含原尺寸体网格、全局MPC映射或完整Maxwell解。

| 对象/方法 | 实际结果 | 状态与边界 |
|---|---|---|
| 两代表面、32,060有序keys | 最大逐key相对差`5.705909332721303`（限值`1e-10`），worst key `top,-67,-34,s`；完整作用相对差`8.663088994999783e-3`；最大component差/原分母`4.1493038268067535` | 边界数值Gate **FAILED**；q重构误差0、adjoint差`2.8212630862997643e-14`通过，但不覆盖积分一致性失败 |
| p4 top/air一单元 | 300 native行（108内部、192边界）；制造态恢复差`4.071005827429115e-13`；原/约化trace方程差`3.161602089999998e-15` / `3.7390795564108086e-14`；port身份差`1.7404941472212574e-17` | 独立checker局部PASS；是制造态的局部方程一致性 |
| p4 bottom/Si一单元 | 制造态恢复差`3.318404914520256e-13`；原/约化trace差`2.8169686807005053e-15` / `4.9473670429170724e-14`；port身份差`2.6701384118827724e-17` | 独立checker局部PASS；不是任意场或全局MPC资格 |
| p6 top/bottom | 严格timebase watchdog触发前没有数组checkpoint | `INTERRUPTED_NOT_RUN`，不是数值失败 |
| raw/checker与监督 | NPZ 104成员、38,026,664 B；独立hash/key/方程重算完成；checker `SAVED_ARRAYS_PARTIAL_OR_CONTROLLED_NEGATIVE`, `pass=false`；readback确认NPZ/checker一致 | W1要求集不完整；任务树RSS峰`1,221,480,448 B`、tree swap 0、global页delta 0 |

timebase首个越限样本monotonic `37.343951652 s`、UTC `43.621839933 s`，相差`6.277888281 s`，超过5 s门槛；整树监督monotonic耗时`38.649290134 s`后清理。原因未知，分类为时钟监督受控停止；不是solver或内存失败。第一次worker服务因包路径导入错误未启动；checker首服务因预创建目录未启动；两者均独立保留。成功checkpoint checker监督`2.047160180 s`、RSS峰`306,634,752 B`、swap 0。

固定T0/deadline=`2026-10-04T15:24:35.195396Z` / `2026-10-04T17:24:35.195396Z`。到checker readback UTC端点推导elapsed `5932.425425 s`、remaining `1267.574575 s`，不是费用；两段可测supervised monotonic interval合计`40.69645031413529 s`，准备/错误命令/服务启动和空档未全量测得，整窗charge仍`UNKNOWN_NOT_SETTLED`。事件只追加，旧历史费用不变。证据：[Response V8](../response_v8.md)、[checkpoint closeout](records/review_v8_w1_boundary_checkpoint_closeout_v1.json)、[增量费用账](records/review_v8_w1_incremental_workflow_ledger_v1.json)、[run index](records/run_index.json)。W2/dot保持HELD，原尺寸NO-GO，官方R/T/A未生成。

---

## Review V8：W0 身份门停止与 W1 清单只读核验（首次状态快照；历史保留）

W0 在完整 p6 FE setup 前的 532 模式物理身份门停止：异常为 `ValueError: fresh C1 requires the independently regenerated ordered literal532 physical inventory`，不是 PDE 数值失败或资源停机。worker phase 实测 1.5594090659869835 s，任务树采样 RSS 峰 200,359,936 B、swap 0 B；没有 checker、科学 raw 或 official result。W0 未完成。本机 Task40 artifacts 的有界文件名/大小核对未找到旧冻结的 532 行 gold；唯一其他既存模式 manifest 是 80-mode direct-reference 文件，不能替代。新 W0 与旧 WSL 诊断清单均不匹配冻结 hash，因此该身份 blocker 保留。

| 阶段 | 对象与方式 | 当前证据 | 裁决 |
|---|---|---|---|
| W0 正式 worker | 80 cells、p6-only、532 modes、φ=5°、MPI1；本机独立 WSL2 ABI | 当前窗口第 1 次 worker 在 `fresh_p6_cold_setup_begin` 前停止；后代清空；global swap 页增量 0 | `INCOMPLETE / IDENTITY_GATE_FAILURE`；非 FE、solver、PDE 或资源失败 |
| W1 清单身份 | 对原有 32,060 AUTO 清单及 repair 副本分块 hash、逐行重算有序 keys | 两文件均 36,244,923 B、SHA256 `52d7ec…15490d`；ordered-key SHA `03c196…e95dec`；索引 0–32059 连续 | 只读库存身份 `PASS`；未运行生成器或保留全部 mode rows |
| W1 Task042 移交 | 固定 commit `f3bf7942…1794ee59` 的 V38/V39 boundary/native adapter | 记录精确 blob 身份、材料/网格差异、MPC slave 失败及 volume 未资格 | 只读最小依赖说明；未拷贝代码或继承数值资格 |
| W1 FE/q30–q60、W2、dot | 后续数值阶段 | 当前 W0 未完整通过；没有新面片结构积分、体积作用、C1c raw 或 p6 对照 | `HELD / NOT_RUN` |

原件和 repair 的目标物理身份 canonical SHA256 均为 `a855565b…79eaf1f`，组合 inventory identity 均为 `39b457c3…d0c12`。主线 bottom-Si 折射率为 `0.9998851703688496+4.3236152269189515e-6i`，Task042 为 `0.999885140474+4.32477054e-6i`。Task042 每侧 73×36 面片；主线 272×4×14 只是计数候选，所以其 q30 资格不能当作主线误差证明。最小可复用候选是方向边界核与 `E/Eᴴ` native adapter；adapter 的 Task042 direct-carrier helper 需绑定主线接口。

旧三次 worker 已知小计 200.87894401792437 s、`6bbc` 历史准备费用 unknown、V6 settled debit 5428.582333962078 s 均未更改。V8 固定窗口 T0=`2026-10-04T08:55:26.395534Z`、deadline=`2026-10-04T12:55:26.395534Z`；截至 `2026-10-04T11:33:35.805415Z`，按 UTC 边界推导 elapsed=`9489.409881 s`、remaining=`4910.590119 s`。这不是 monotonic elapsed 或收费；整段准备与 W0 总费用仍 `UNKNOWN_NOT_SETTLED`。worker 启动为 1/4；修复额度为 2/3（event 15 原 `NOT_INFERRED` 快照保留）：`4b780d8` 是固定 deadline/控制入口修复，`8553a22` 是用户另行授权的 local WSL2 profile 资格化（保守计为一轮源级变更）；后续无源身份诊断不计修复。

详见 [Response V8](../response_v8.md)、[W1 清单身份与最小依赖记录](records/review_v8_w1_identity_audit_v1.json)和[运行索引](records/run_index.json)。V7、V6 及更早各节继续作为历史记录保留。

---

## Review V6：Gx784 单次运行与保存场后处理收口

V6 按 review 授权只新增一张 14×4×14（784 单元）Gx784 小网格，复用 340 个端口模式和 p6 完整场/p4 校正流程。p6 产生实际完整电磁场；p4 在迭代中校正 p6 误差，收益是保留 p6 输出，成本是另装配和使用 p4 系统。本轮没有第二张网格、AUTO 重生成、dot 执行或原尺寸计算。

| 模型与方法 | 完整残差与官方结果 | 对照和资源 | 当前裁决 |
|---|---|---|---|
| Gx784；784 cells；Full3D p6 + exact p4 correction；340 ordered modes；MPI1 complex128；p6 full rows 530,400；p4 condensed rows/NNZ 67,988 / 26,295,924 | explicit/post-release A6 9.692115162625173e-7（限值 1e-6）；R/T/A_balance/A_volume=0.07612656490058632 / 0.9057668832851113 / 0.01810655181430232 / 0.018106531117781374；能量闭合 2.0696520941498875e-8 | Gx→Gx784 与 F5→Gx784 八项场差最大 0.06420% 与 0.06420%；11 个冻结显著模式复振幅差最大 0.00803% 与 0.00815%；四类功率绝对差均 <1e-3。全 workflow monotonic 3431.623 s，任务进程树 RSS 峰 7,782,744,064 B、swap 0 B，watchdog 3431.201 s | 离散求解/恢复一致性通过但 AUTHORITY_LIMITED（无同离散 direct reference）；配对比较 tested_x_agreement_pass；不构成 continuum/y 收敛或原尺寸资格 |

R/T 是端口模式功率比，A_balance 是功率平衡吸收，A_volume 是材料体积分吸收。Gx784 的 R00_s/R00_p/R00_total 为 0.07612609133082268 / 1.819475255892784e-21 / 0.07612609133082268。两场配对的场误差分母固定为 F5 同一物理量 L2 范数；显著模式复振幅按各配对首场归一。比较在共同物理坐标子单元上进行，checker 从原始字段独立重算并与保存结果完全一致。

| 时间/预算 | 已结算值 | 口径 |
|---|---:|---|
| Gx784 workflow monotonic / conservative-realtime interval | 3431.622642 / 3812.914413 s | 两种时钟分列；后者受 UTC 偏差影响 |
| Q4 shared-ledger debit | 3812.953841 s | conservative-realtime 收费，不称为 monotonic |
| postprocess attempt2 watchdog / ledger debit | 1442.152566 / 1601.004417 s | 离线保存场比较，不包含 PDE |
| 账本总 used / remaining | 5428.582334 / 167371.417666 s | 总预算 172,800 s；active reservation 为空；含旧扣费、policy debit 与 10 s allowance |
| Gx784 进程树 RSS/swap | 7,782,744,064 / 0 B | 13,507 个采样，身份覆盖完整，后代清空；PSS disabled；全局 swap delta 不归属单个任务 |
| postprocess 进程树 RSS/swap | 946,765,824 / 0 B | 5,680 个采样，身份覆盖完整，后代清空；PSS disabled |

首次保存场 preflight 的分类错配错误和后续两项最小源码修复均保留；首次失败没有进入比较 worker、预算预留或 PDE/factorization，时钟缺样所以 elapsed 为 unknown、未收费。original/repair AUTO 清单身份相同：SHA256 52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d，32,060 个有序 key，digest 03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec；V6 各读取一次，未运行生成器。已有单个 H 对角/稠密矩阵 512,960 / 16,445,497,600 B、p6 单元张量/内部 LU 形状 12,446,784 / 3,240,000 B、trace Schur/单份耦合项 2,985,984 / 3,110,400 B；272×4×14 候选为 15,232 cells、p6 full/interior 10,228,620 / 6,854,400 行，74 个 outer vectors 3,701,577,088 B、retained/full scratch 4,428,003,200 B。这些是 derived 载荷/计数，不是实测峰值。目标尺寸生命周期仍缺冷 JIT、C/D、H/Hhat 同存、恢复/投影缓存与数量、全部 q 因子填充和 workspace、完整迭代与输出时间等实测；不同阶段不能简单相加为同时峰值。原尺寸仍 NO-GO，2 TB 容量未证明；dot、workstation 与 master 状态不变。

详细边界、checker 数值、失败保留和证据链接见 [Response V6](../response_v6.md) 与 [V6 compact closeout record](records/review_v6_gx784_postprocess_closeout_v1.json)。V5/V4 与更早负结果继续保留如下。





---


## Review V5：Gx784 工程失败与后处理安全预检

Gx784 worker 在数值预检和有限元工作前因 enforce-time/旧 observe-only 合同冲突退出，官方场、真残差和 R/T/A 均未生成；这属于工程失败，不是数值失败。修复后的 V5 后处理先重算 solver/recovery Gate，当前旧记录未过 Gate，因此生成 held 对照并停止在 worker、预算预留与 FE 导入之前。唯一 bug replay 已使用，不据此启动第二次正式运行。

| 结论项 | 当前证据 |
|---|---|
| worker 与 Gate | WORKER_FAILED_PRE_NUMERICAL_ENGINEERING_ERROR_NO_OFFICIAL_RESULT；field/residual evidence unavailable，paired field/mode/power HELD / NOT_RUN |
| 记账 | 172800 s 上限；工程保守预算扣时 4.619253995631944 s；active attempt=null；bug replay=1；不是数值求解耗时 |
| 修复与验证 | source 969b4086320b844d44fb0b67092ffe5af2d760b1；47 项相关测试通过；另有文档合同检查见 test summary |
| 边界 | original 与 repair AUTO 清单/ledger 均已存在；本次 closeout 未重生成，旧生成成本 unknown；候选容量仍 unknown；dot HELD / NOT_RUN；master 未合并 |

Held 对照、独立 checker、账本、双份 target/resource ledger hashes 及分项 known/unknown 见 [Response V5](../response_v5.md)、[紧凑 V5 closeout record](records/review_v5_execution_closeout_v1.json) 与 [run index](records/run_index.json)。32,060 通道的大清单保留在 ignored artifact；tracked 记录仅保留路径、SHA、计数和 unknown 容量结论。

---

## Review V4：交叉网格与四角离线结果

本节追加 V4 实际执行结果；后面的 V2、R5 和更早阶段记录保留原样。G00=F3、G10=Gx560、G01=Gz528、G11=F5。p6 是求解实际电磁场的高阶离散；同网格准确 p4 校正用于迭代中近似修正 p6 误差，收益是保留完整 p6 解和输出，代价是还要组装/使用 p4 全局矩阵。四角均使用同一 0.7 nm 物理模型、M=8/N=2 的 340 个有序端口模式和 MPI1/threads1。因为原 F3→F5 同时改变 x 与 z，Gx 只把 x 节点改为 10×4×14、Gz 只把 z 节点改为 6×4×22，以隔离方向影响；y、材料和边界不变。

| 角点 | 网格轴单元 | cells | p6 完整行数 | p4 界面矩阵 rows / NNZ | full A6 真残差 | KSP 秒 | 同时进程树 RSS 峰值 B / swap B | 结果 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| G00 / F3 | 6×4×14 | 336 | 229,680 | 29,332 / 11,293,034 | 7.5936104e-7 | 823.922 | 4,006,539,264 / 0 | official，残差门通过 |
| G10 / Gx560 | 10×4×14 | 560 | 380,040 | 48,660 / 18,782,900 | 9.7334769e-7 | 1,499.305 | 5,255,675,904 / 0 | official，残差门通过 |
| G01 / Gz528 | 6×4×22 | 528 | 359,904 | 45,460 / 17,879,806 | 9.7452954e-7 | 1,522.376 | 5,434,322,944 / 0 | official，残差门通过 |
| G11 / F5 | 10×4×22 | 880 | 595,512 | 75,540 / 29,765,186 | 8.7353225e-7 | 1,797.975 | 7,754,170,368 / 0 | official，残差门通过 |

这里的残差是完整 p6 原系统 `||A6 x-b6||₂/||b6||₂`，限值 1e-6；RSS 是一次运行同时存活进程树峰值，swap 为任务进程树峰值。PSS 未采样。p4 矩阵 NNZ 使用 owned-row `getRow` stored-entry 口径；它不是 p6 外层自由度，也不能直接代表分解填充。

Gx560 与 Gz528 的正式运行另有各自独立的 shared workflow ledger。Gx 的 settled conservative-realtime debit 为 2,141.819255361028 s（2 次尝试：早期 parent 故障 0.024069007951766253 s，正式运行 2,141.795186353076 s；unique bug replay=1）；Gz 为 2,129.84311068633 s（1 次尝试，bug replay=0）。两个 ledger 的 `active_attempt` 均为 `null`。这些数是账本的 conservative-realtime debit，不是纯 monotonic 全流程时长；`run_summary` 的 full-workflow monotonic 值分别为 1,925.862865802017 s 和 1,917.8436222969322 s，KSP-only 分别为 1,499.305480348 s（171 步）和 1,522.375745824 s（202 步）。watchdog elapsed 字段是更窄的进程监控区间。没有精确 setup 分项，故不从总时长相减推算。逐 run 路径及 ledger SHA 见 [run_index](records/run_index.json)，原始 ledger 保持独立文件。

| 角点 | R_total | T_total | A_balance | A_volume | R00_s / R00_p / R00_total |
|---|---:|---:|---:|---:|---:|
| G00 / F3 | 0.075651901996 | 0.906206870522 | 0.018141227482 | 0.018141268088 | 0.075651427914 / 7.2332e-17 / 0.075651427914 |
| G10 / Gx560 | 0.076124070594 | 0.905769197829 | 0.018106731577 | 0.018106711773 | 0.076123597014 / 1.2442e-16 / 0.076123597014 |
| G01 / Gz528 | 0.075651879550 | 0.906206808259 | 0.018141312192 | 0.018141266669 | 0.075651405471 / 4.0495e-20 / 0.075651405471 |
| G11 / F5 | 0.076124071271 | 0.905769239817 | 0.018106688912 | 0.018106713068 | 0.076123597691 / 3.5618e-17 / 0.076123597691 |

相对 F5 的 `|ΔR|/|ΔT|/|ΔA_balance|/|ΔA_volume|` 分别为：G00 `4.72169e-4/4.37631e-4/3.45386e-5/3.45550e-5`；G10 `6.77011e-10/4.19879e-8/4.26649e-8/1.29529e-9`；G01 `4.72192e-4/4.37568e-4/3.46233e-5/3.45536e-5`。每项均小于 1e-3。四角分别检查 `|R_total+T_total+A_volume_total-1|` 和 `|A_balance-A_volume|`；两项均小于 1e-5，实际最大约 4.56e-8。功率门通过不替代复场门。

| 物理域量；误差分母固定为 G1/F5 同量 L2 范数 | x 方向：G10→G11 | z 方向：G01→G11 | x/z 交互量 `(G11-G10-G01+G00)`，相对 G1 |
|---|---:|---:|---:|
| Fresnel 背景下的散射 E | 1.375971e-6 | 2.6118624e-2 | 1.05444e-6 |
| curl(E_scattered)/k0 | 8.788076e-7 | 2.7503537e-2 | 3.93253e-6 |
| top `(0,0,s)` 复模态振幅 | 3.234128e-7 | 1.5507592e-2 | 见全 340 模式记录 |
| 总 E | 1.976082e-7 | 3.7509897e-3 | 见四角记录 |
| 总 H | 1.262070e-7 | 3.9498291e-3 | 见四角记录 |

这里 `curl(E_scattered)/k0` 的计算是先从保存的总电场直接计算 curl，扣除 `layered_fresnel` 背景的解析 curl 得到 `curl(E_scattered)`，再除以 `k0`。散射 E 与该 scaled-curl 的预登记方向假设均得到支持：x-only 细化接近 F5，z-only 细化仍接近 F3。完整物理域场表还包括总/散射 E、H、原始 curl、scaled curl、x/z 增量和交互项；逐材料区数据保存在 volume artifact。该比较只跨 x、z 两轴，不能推出 y 或 continuum convergence。

| 冻结 11 个显著模式的最大复振幅差；各 comparison 按其首角幅度归一化 | 最大值 | 1% 门 |
|---|---:|---|
| G00→G11 | 1.555605% | 失败 |
| x increment G00→G10 | 1.555637% | 失败 |
| z increment G00→G01 | 0.010781% | 通过 |
| G10→G11 | 0.010866% | 通过 |
| G01→G11 | 1.555591% | 失败 |

因此“x 比 z 更接近 G1”的三项主要预登记观测均成立，但 F3→F5 与 Gz→F5 的整体显著模式门仍失败；不能把 overall 1% 模式 Gate 写成通过。旧失败通道也完整保留：`bottom(-1,0,s)` 的 F3→F5 首幅值归一化差为 1.274430%，`top(0,0,s)` 为 1.555605%；Gx→F5 分别为 2.34773e-5 和 3.23413e-7，Gz→F5 分别为 1.260666% 和 1.550759%。各角复振幅、全部 340 行和五种比较均见 mode artifact。

| 检查 / 证据身份 | 结果与边界 |
|---|---|
| 公共体积 | 1,344 子单元（形状 12×4×28），每轴 7 阶求积；物理体积 24.3966874968 nm³，材料标签错配 0 |
| 轴并集 | x/y/z 节点数 13/5/29；仅合并完全相同节点，完整有序节点列在接口包 |
| 模式清单 | 340 ordered modes，80 propagating、210 power-carrying；`power_carrying` 表示有限端口单位振幅的实能流 `mode.power_per_unit_amplitude > 0`，并非传播通道数；四角 manifest digest 相同；保留全部 340 对照行及冻结 11 键 |
| volume 离线分析资源 | 864.838 s；同时进程树 RSS 934,637,568 B、swap 0 B、PSS 未采样；subreaper leader exit 0 且后代清空 |
| 模式离线分析 | 读取已校验保存包；没有场恢复、PDE、矩阵装配或因子化；未单独采样同时进程树资源 |
| 紧凑接口包 | [`review_v4_four_corner_interface_v1.json`](records/review_v4_four_corner_interface_v1.json)，SHA256 `44a878f85c6e50f5aa5c6b53f58addf1350041c33593cf72ea8cb6b961f29e43`；物理参数、精确网格节点、参考面、相位、unknown/recovery、残差、全部物理域字段指标、模式键、功率和资源边界均在其中 |
| 原始离线结果 | [volume artifact](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_volume_v1.json)，SHA256 `5f8004f51cb7d9543730281ace16f296cdc47b0358c66038302bf4f39ac40c17`；[mode artifact](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_modes_v1.json)，SHA256 `e723cf5fd6dc761e3642582af12b921c05453c581903eaf47abac07816d17df2` |
| 求解/输入来源 | G00 source `a43f7f76a0df0f4440b77834846973b2de7ea3a8`；G10/G01 `9fd295624444cf16b6ba393a0a7c3522f0070f73`；G11 `63dd2a7378153f2ab5094eb5e7a98d05758a39bf`；run/input/physical hashes 在接口包和 [run_index](records/run_index.json) |
| F3 源码索引修正 | `run_index.runs` 中旧 F3 SHA `63dd2a...` 更正为 run manifest 实证的 `a43f7f...`；旧值和修正依据保留在同一 F3 项的 `source_sha_correction`，未变更求解输出 |
| V3-A / V3-B / V4 范围 | 复用已接受的 paired-background attribution，不重算 A；完成预登记 Gx560、Gz528 与四角比较；没有新网格、背景扫描、相位拟合或删除模式 |
| dot / 原尺寸 / 工作站 | dot 仍 `HELD / NOT_RUN`，旧 checker `UNKNOWN`；没有改 dot 或 workstation，没有原尺寸计算，不建立 workstation readiness 或 continuum claim |

## V4 选择性合并分组与下一步

| 依赖组 | 数值行为与依赖 | 测试 / fresh evidence | 决策与顺序 |
|---|---|---|---|
| production numerical/core | 本轮新增 Gx/Gz 输入参数与 `src/geometry/task40_nonseparable_plan.py` 交叉几何/预算登记；`src/io/physical_intermediate_profile.py` 和 `src/runners/task038_launcher.py` 有 parent-FE import/launcher 最小修复；`src/postprocessing/diffraction_3d.py` 是输出后处理调整；另新增 `src/postprocessing/task40_saved_field_h_comparison.py`，恢复已保存场、直接求 curl 并在公共子单元上做离线比较。以上改变研究配置、入口和后处理；生产 Maxwell 方程、有限元离散、矩阵/约束数学及普通 solver default 未变，离线算法明确登记在 `src/` 中 | 四角 official PDE 的 solver source 与原残差/R/T/A 绑定 run_index；新增 comparator 只分析已保存场，不触发 PDE | 新增代码仍属 Task40 研究与离线分析支撑；不作为 production default，未来拆分复用前另行 review |
| reusable runner/watchdog | `benchmarks/postprocess_task40_review_v4_directional_cross.py`、`benchmarks/postprocess_task40_review_v4_modes.py` 与 `src/postprocessing/task40_saved_field_h_comparison.py`；仅读已保存场/模式，依赖既有 `subreaper_watchdog`，不改 watchdog | 三个目标测试文件共 8 passed；V4 volume/mode artifacts 各自绑定 source/artifact SHA；runner 不触发 PDE | 保持 Task40 research/evidence 工具，先经审阅；没有宣称替代通用 runner或可设为默认 |
| checker/benchmark | 本轮无新的独立 checker 或 benchmark case/schema | targeted tests 校验方向量和冻结模式规则；不是 solver checker qualification | 无 checker/benchmark 文件待迁移 |
| compact evidence/docs | `response_v4.md`、V4 summary/test-summary 段、interface JSON、run_index source correction 与新增 Gx/Gz identities | 4 个 JSON 可解析，hash 与索引一致；保留全部 positive/negative/not_run 边界 | 审阅后按文档依赖组迁移；完整历史 records 不改写 |
| research-only | Gx/Gz 输入参数、Task40 交叉几何/预算登记与 launcher/parent import 最小路径修复、`src/postprocessing/task40_saved_field_h_comparison.py` 离线算法、两个 task-scoped postprocessor、M2 crossed-grid 解释与四角数据；无 continuum/y/目标尺寸证据 | 两项离线 artifact；F3/F5 与 Gz/F5 的显著模式 1% Gate 仍失败 | 这些实现只支持本轮研究入口和保存场离线分析；不升 production、不改 ordinary default；方向结果只作后续实验优先级依据 |
| do-not-merge | dot 分支源码、workstation 操作、原尺寸/Phase II solver、任何未经 Review 的 master 变更 | dot `HELD / NOT_RUN`、旧 checker `UNKNOWN`，无新环境 fixture | 本轮无授权或证据，不迁移、不合并 master |

本批结论限定为 Review V4 指定的小尺寸离散模型与已保存场的四角对比。功率一致和 residual 通过说明这四场具有可审查的求解与能量证据；模式/散射场 Gate 的负结果仍然有效。由方向对照可将后续网格投入优先放在 x，但不得把当前证据外推为最终工程精度或原尺寸可运行。


## 一级账：模型结果与campaign状态

| 模型/阶段 | 正式身份 | full A6 residual / Gate | 官方量与比较 | workflow / KSP；同时树RSS / swap | p4 factor rows / NNZ / INFOG29 | 结论 |
|---|---|---:|---|---|---|---|
| F1 G1 M0 | `task40extra_0p7nm_nonseparable_g1_reference_metric_f1_v1`；880 cells；M80 | 8.648911990579289e-7；同离散G1 M0参考通过 | R/T=`0.07612407122165808/0.9057692393459813`；A_volume=`0.018106713007727038` | 2252.535 / 1674.835 s；6,891,311,104 B / 0 B | 75,280 / 28,705,330 / 182,769,024 | 仅资格化G1 M0；不能代替G0 M2 reference |
| F2 G0 M1 | `task40extra_0p7nm_nonseparable_g0_manual_m1_f2_v1`；336 cells；M180 | 9.572475880327875e-7通过；worker exit4 | raw/offline R/T/A_volume=`0.07565188084569026/0.9062068016471507/0.018141266883419625`；worker `official_result=false` | 1123.500 / 809.586 s；3,867,545,600 B / 0 B | 29,172 / 11,033,364 / 55,305,544 | 保存DtN/体积值用于P3 offline比较；未重新发布official result |
| F3 G0 M2 | `task40extra_0p7nm_nonseparable_g0_manual_m2_f3_v1`；336 cells；M340 | 7.593610432084708e-7通过 | R/T=`0.0756519019957502/0.9062068705222379`；A_volume=`0.018141268088495303` | 1174.947 / 823.922 s；4,006,539,264 B / 0 B | 29,332 / 11,293,034 / 56,763,048 | 离散与一致性通过，authority-limited |
| F5 G1 M2 | `task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1`；880 cells；M340 | 8.735322490524255e-7通过 | R/T=`0.07612407127067708/0.9057692398169153`；A_volume=`0.018106713068250728` | 2448.071 / 1797.975 s；7,754,170,368 B / 0 B | 75,540 / 29,765,186 / 186,881,032 | 离散与一致性通过；M2跨网格场/curl工程门未通过 |
| E1 q=1.25 | `task40extra_0p7nm_nonseparable_e1_manual_m2_growth_v1`；760 cells；M588 | 9.781668525522113e-7通过 | R/T=`0.06235653736791684/0.9159264755357902`；A_volume=`0.021716951725654188` | 4580.375 / 3722.193 s；10,650,341,376 B / 0 B | 65,708 / 26,681,978 / 164,865,416 | 固定波长的电尺寸增长诊断，不是h收敛序列 |
| E2 q=1.5原run | `task40extra_0p7nm_nonseparable_e2_manual_m2_growth_v1`；880 cells；M700 | 9.793073227317083e-7通过；worker exit4，official false | 原worker无official output；v3保存场恢复R/T=`0.05116886160983426/0.9239410512847893`，A_volume=`0.02489005360260621` | 7692.028 / 6776.587 s；11,349,196,800 B / 0 B | 75,900 / 31,287,060 / 182,925,800 | 原失败保留；v3只做离线输出恢复 |
| P1 G0/G1 M0体积/curl | 原G0/G1 M0保存场；1344共同子单元 | 不是新solve | 总场E/H=`0.3750%/0.3949%`通过；散射E=`2.6113%`、散射H/scaled-curl=`2.7498%`失败；官方ΔR/ΔT/ΔA_volume均过0.001 | offline 436.518 s；self RSS 620,851,200 B；无PDE/operator/factor/KSP | 不适用 | P1真实负结果；SHA-bound record在`records/p1_m0_volume_h_agreement_v2.json` |
| P4 F3/F5 M2体积/curl | 共同340个M2 key；G0/G1保存场 | 不是新solve | 总场E/H约`0.3751%/0.3950%`通过；散射E=`2.6119%`、散射H/scaled-curl=`2.7504%`失败；official ΔR/ΔT/ΔA_volume=`0.0004721693/0.0004376307/0.0000345550`通过 | offline 597.979 s；RSS 621,101,056 B；无PDE/operator/factor/KSP | 不适用 | M2场/curl h工程门失败，不能由功率接近覆盖 |

### 零级反射与p6空间维数

| 模型/身份 | R00_s | R00_p | R00_total | 来源/状态 |
|---|---:|---:|---:|---|
| F1 G1 M0 | 0.07612359764215308 | 3.4597741445267834e-17 | 0.07612359764215311 | 正式DtN；F1同离散reference |
| F2 G0 M1 | 0.07565140676565715 | 2.0048467438900223e-17 | 0.07565140676565717 | raw DtN/offline用于P3；worker official_result=false |
| F3 G0 M2 | 0.07565142791421035 | 7.233241618502243e-17 | 0.07565142791421042 | 正式DtN |
| F5 G1 M2 | 0.076123597691134 | 3.5617837904198074e-17 | 0.07612359769113404 | 正式DtN |
| E1 q1.25 | 0.062356105023958414 | 6.083759436e-16 | 0.062356105023959024 | 正式DtN |
| E2 q1.5 v3 output recovery | 0.05116727309447169 | 7.978116094818559e-19 | 0.05116727309447169 | saved-field recovery only；原worker仍失败 |

F1/F3/F2的G0类p6空间为full229,680、active68,256、interior151,200、trace78,480；F1/F5的G1 p6空间为full595,512、active177,120、interior396,000、trace199,512。E1为full514,710、active153,360、interior342,000、trace172,710；E2为full595,512、active177,120、interior396,000、trace199,512。完整有序模式与各显著衍射级见run_index绑定的`dtn_port_diffraction_orders_3d.json`及hash，不把诊断Fourier值混入官方DtN结果。

workflow、独立watchdog、KSP、p6 build和postprocess是不同边界，不相加。E2的KSP事实为已保存阶段记录；其原postprocess独立边界unknown。PSS为null。F1 p4完整存储行是180,240，而实际凝聚factor只有75,280。目录timestamp不是run_id。完整source/input/physical/native ordered-mode SHA及raw字段路径+SHA见`records/run_index.json`、`records/electrical_size_v2.json`和`records/resource_components_v2.json`。F3源码SHA=a43f7f76a0df0f4440b77834846973b2de7ea3a8；F5/E1/E2=63dd2a7378153f2ab5094eb5e7a98d05758a39bf。

## 二级账：资源组成

| 组件 | 证据 | 解释与限制 |
|---|---|---|
| mesh/MPC | G0 336 cells；p6全空间229,680 DOF；单元维数882 | P6构造真实mesh/space，没有构造全局物理operator |
| p6局部LU/Schur/恢复 | 三种tag各取一个单元；内部450×450，trace432×432；非零RHS closure为1.43e-11至2.35e-11 | 真实局部闭合通过1e-10；不代表全域因子容量 |
| p4矩阵/MUMPS | F1 full storage180,240、factor75,280/28,705,330 NNZ；F2 full storage69,856、factor29,172/11,033,364；F3 29,332/11,293,034；F5 75,540/29,765,186；E1 65,708/26,681,978；E2 75,900/31,287,060 | INFOG29依次182,769,024、55,305,544、56,763,048、186,881,032、164,865,416、182,925,800；INFOG16/17是symbolic估计最大/和，18/19是allocated最大/和，22是used进程和，均以decimal MB报告；INFOG29是条目数。matrix payload、ICNTL23受限工作内存限额记录与process-tree RSS另列；全局因子仍是目标尺寸风险 |
| ports/Krylov P6压力 | M=80/340/3904，batch=16；M3904每真实tag双遍约3.739–3.773 s | synthetic/resampled压力，不是完整高M物理端口模型；无M×M矩阵 |
| 同时进程树RSS | F3 4.007 GB；F5 7.754 GB；E1 10.650 GB；E2 11.349 GB | watchdog同时树峰值 |
| inventory/workspace | F3 4.894/1.753 GB；F5 7.876/1.992 GB；E1 10.429/6.031 GB；E2 11.544/6.092 GB | 两者分别是对象账与workspace，不等于RSS，也不相加 |
| JIT/postprocess | P6 form compile=0.00724 s；F3/F5/E1 post=7.176/19.152/19.712 s | E2原post边界unknown；E2 v3离线恢复单列 |

P6知道的numpy backing下界38,432,904 B，显式数组情景上界40,542,856 B；后者不含不透明BLAS/LAPACK工作区。P6自身RUSAGE RSS峰455,610,368 B，task swap未独立采样，不能把两次VmSwap=0监控快照写成峰值零。本轮没有从小模型或对象账外推2 TB容量，也没有调整工作站cap。

## 误差、负结果和下一步

- P1是原G0/G1 M0公共子单元体积/curl比较：总场E/H为0.3750%/0.3949%（过1%），散射E=2.6113%、散射H与scaled-curl=2.7498%（未过1%）；official ΔR/ΔT/ΔA_volume均低于0.001。记录SHA `9d72efd7f21771c7fd0cc779b7cfb0f9272734fe9cbe1757a014d127e4422925`。这不同于R5旧固定坐标样本`h_agreement_v1.json`的`H_AGREEMENT_PASS_ENGINEERING_ONLY`。
- P3显著规则M0 power_ratio≥1e-8是在查看探索性all-80差异后固定；报告保留此事后规则披露，不称预注册。按该有限规则选择M2，M3未触发。
- P4是F3/F5 G0/G1同M2的保存场比较：340 keys相同；总场E/H变化约0.3751%/0.3950%过1%；散射E=2.6119%、散射H/curl=2.7504%、显著模式1.555605%、固定样本最大2.743612%超过1%。官方ΔR=0.0004721693、ΔT=0.0004376307、ΔA_volume=0.0000345550通过0.001。负结果是场/导数误差门未过，不是方程没有离散解。
- E1是一次更大电尺寸诊断点；E2原worker因sample配置后处理检查失败，离线恢复保留其失败分类。
- P6支持三种真实局部块闭合和固定批次synthetic动作可行性；不证明生产端口稀疏度、完整高M或TB容量。
- P7只提出下一阶段设计。原端口块`H_p`经精确消去/trace映射后成为同维增广接口+port贡献`Ĥ_ℓ`并且只计一次；粗层选`R_ℓ=P_ℓ^H`，这不要求物理左右块`D=B^H`，也不把非Hermitian算子变成Hermitian。`ΣT_j^H W_jT_j=I`只约束近似PC patch组合。提案封顶4层、终层≤20,000维/≤200步、外层≤2,048步；见review_v2_campaign.md。
- ordinary default不变；Phase II和master merge都未进行。

## 选择性合并分组

| 依赖组 | 全V2范围 / 数值行为 | 测试与fresh evidence | 建议顺序 |
|---|---|---|---|
| production numerical/core | Task40显式profile/reference-metric候选及其`src/common`、`src/geometry`、`src/io`、`src/postprocessing`、`src/runners`、`src/solvers`改动；部分可能影响数值行为 | reference-metric、M1 authority、geometry、P1/P3/P6 targeted tests；F1只资格化G1 M0；P1/P4保留负结果 | 第一组逐依赖review；不升级ordinary default |
| reusable runner/watchdog | v29 p6 pair runner、subreaper watchdog、E2 saved-output recovery入口 | runner/watchdog/recovery targeted tests；E2 v3不是PDE/factor证据 | 第二组仅迁移经审查通用部分 |
| checker/benchmark | Task40 P1/P3/P6/P2 checker和bounded diagnostic entrypoints | P1 M0与P4 M2已保存结果；P6 fixture2、P4 helper fixture4 | 第三组与相应schema/tests同行 |
| compact evidence/docs | run index、P1/P4/P3/E1/E2/P6 records、summary、test_summary、README、response与项目登记 | JSON/doc/hash/link与diff检查 | 第四组保留到执行分支供review |
| research-only | synthetic M3904压力、Task40显式profile以及P7未实现设计 | 不构成高M完整物理模型、TB容量或Phase II qualification | 保持research-only |
| do-not-merge | e174b91历史`/dev/null`hook绕行、放宽冻结Gate、删除P1/P4 negative、把E2原worker失败改写为成功、普通默认切换 | `repair_ledger_v2.json`保留偏差 | 禁止 |

## V2证据索引

Review V2 campaign见review_v2_campaign.md；执行回应见response_v3.md。机器可读记录包括review_v2_plan.json、p1_m0_volume_h_agreement_v2.json、volume_h_agreement_v2.json、reference_metric_tensor_v2.json、channel_study_v2.json、electrical_size_v2.json、resource_components_v2.json、repair_ledger_v2.json、p6_local_block_inventory_v2.json与run_index.json。旧R5总结紧随本文之后保留，不覆盖。


---

# 历史结果摘要（V1 / R5；原文保留）

# Task40extra B 线 N0–N6 结果总结：0.7 nm 非可分三维 Maxwell

## 当前结果（R5，2026-09-30）

N0–N6 的当前阶段状态是：strict identity 修复后 G0、G1 正式离散解通过；G0 same-discrete direct comparison 通过；G0–G1 fixed-sample/power engineering agreement 通过。N2 与 attempts 1–4 仍按原范围和原分类保留。

| 正式对象 | 方法、模型规模 | Gate / official output | watchdog 资源与时间 |
|---|---|---|---|
| G0 review_v1 | 336 cells；p6 完整场 229,680 rows、active trace 68,256；p6 trace+port 68,336 rows；q4 凝聚因子 29,072 rows / 10,912,592 NNZ；80 modes；FGMRES 152步 | A6 9.798664008005796e-7；identity 1.520588963522625e-11；R/T/A_balance/A_volume=0.0756519645/0.9062068564/0.0181411791/0.0181412571 | simultaneous tree RSS 3,776,098,304 B；swap 0；workflow/KSP 1204.018/787.135 s |
| G1 review_v1 | 880 cells；p6 完整场 595,512 rows、active trace 177,120；p6 trace+port 177,200 rows；q4 凝聚因子 75,280 rows / 28,705,330 NNZ；80 modes；FGMRES 127步 | A6 9.901397191660007e-7；identity 3.2542694546811876e-11；R/T/A_balance/A_volume=0.0761240621/0.9057692206/0.0181067174/0.0181067127 | simultaneous tree RSS 6,855,741,440 B；swap 0；workflow/KSP 4097.994/3135.913 s |
| G0 direct reference | 同 G0 几何/物理；MUMPS 因子作用于 p6 trace+port 的 68,336 rows；229,680 rows 是恢复完整场的存储维数；80 appended modes | direct residual 5.055376131651821e-11；MATCHED_REFERENCE_PASS；R/T/A_balance/A_volume=0.0756519637/0.9062067814/0.0181412550/0.0181412550 | simultaneous tree RSS 11,505,573,888 B；swap 0；watchdog/charged 1647.527/1801.467 s；PSS disabled |

### 零级 s/p 通道与能量闭合

| 模型 | R00_s | R00_p | R00_total | T00_s | T00_p | T00_total | A_volume grating / substrate | R+T+A_volume−1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| G0 iterative | 0.07565149041679828 | 2.7428991838613296e-18 | 0.07565149041679828 | 0.9062066000865279 | 1.4515667553444104e-18 | 0.9062066000865279 | 0.013925879883210604 / 0.004215377168498715 | 7.799209567060927e-8 |
| G1 iterative | 0.07612358848843093 | 7.987426377936068e-16 | 0.07612358848843173 | 0.9057689645333413 | 4.2210952517070463e-16 | 0.9057689645333417 | 0.013893418210626729 / 0.0042132945191538694 | -4.630012484518886e-9 |
| G0 direct reference | 0.07565148957274329 | 2.5940427852720315e-23 | 0.07565148957274329 | 0.9062065250155358 | 3.476815891411563e-23 | 0.9062065250155358 | 0.013925878172457823 / 0.004215376818162912 | 1.6774137634456565e-11 |

各s/p数值是端口模态功率比。G0–G1变化最大的衍射通道为 top (0,0,s) 的 R 增加 0.0004720981 与 bottom (0,0,s) 的 T 减少 0.0004376359；其余被比较的80-mode功率变化小于 3.0e-10。完整排序与所有模式见 [h-agreement record](records/h_agreement_v1.json)。

正式 G0/G1 source SHA=b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672；inputs 分别为 6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e / 989a351fb27fe5320942ca2392d0e7e872909f0354509e5d59c8c25e43061c86。direct source SHA=393e5c0dddb933848945ab2e18edb73cf69cc224，direct input SHA=c80c921834cb268a9251459795fbda5acf4e9f25347d16ee24dec3b9d85c6c56。direct 规范化 physical sections SHA 与 G0 的 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661 一致；原始 identity 差异只有 assembly backend。mode SHA=c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a。

R/T 来自 DtN 端口模态功率，A_volume 来自材料区域体积分吸收。q4 行数和 NNZ 是预条件器的独立 q4 凝聚因子规模，不是 p6 外层维数。direct reference 的完整场 residual 用保存的 b 与 Ax 独立复算，记录值完全一致；详细字段、输入/source 与 artifacts hash 见 [identity recovery compact](records/identity_recovery_v1_results.json)。

同离散比较的 FE L2 / scaled-curl 相对误差为 1.0644e-7 / 1.0590e-7；固定坐标场与界面迹最大相对差 4.9591e-7；80-mode outgoing amplitude 向量整体相对差 1.3374e-7；每模功率最大绝对差 7.5071e-8；R/T/A/A_volume 最大总量差 7.5915e-8。所有 applicable Gate 通过。

G0 到 G1 的共同坐标总场变化约 0.374%（E）与 0.393%（H），总功率各绝对差低于 0.000473，过本任务 1% / 0.001 工程 Gate。这仅表示两张网格在固定样本和当前输出上相符，不是连续极限证明；80-mode channel cutoff 仍未资格化。约 2 TB 目标容量仍 UNKNOWN。

| 其他阶段成本 | 实测 / 近似时间 | 解释 |
|---|---:|---|
| R1 full p6 operator diagnosis | 14,039.107309384039 s | 没有全局 p4 factor；诊断阶段 |
| v1 builder 主动停止 | 约101 s | 近似；审查修正后停止，原分类保留 |
| v2 exact-geometry replay | 198.79226663301233 s | 保存向量的离线复核，无 fresh PDE/KSP |
| attempt1–4 shared ledger累计 | 530.8867869906425 s | 历史 ledger scope，与后续 review_v1 分开 |

### Setup、求解和后处理时间

| 模型 | setup | outer adapter | KSP-only | final native / release checks | official postprocess | 主内存对象记录 |
|---|---:|---:|---:|---:|---:|---|
| G0 | 373.096 s | 798.552 s | 787.135 s | 2.045 / 8.730 s | 11.707 s | worker inventory peak 4,429,493,610 B；workspace peak 1,731,541,832 B；Krylov workspace upper 80,909,824 B；同时树RSS峰 3,776,098,304 B |
| G1 | 908.009 s | 3150.090 s | 3135.913 s | 4.890 / 15.448 s | 14.035 s | worker inventory peak 6,627,841,642 B；workspace peak 1,970,721,416 B；Krylov workspace upper 209,804,800 B；同时树RSS峰 6,855,741,440 B |
| G0 direct | setup/factor阶段无可独立确认的 wall-time 切分 | 不适用 | 不适用 | recovery 0.632 s；其余检查独立阶段时间 unknown | 包含在总 charged 时间内，未独立计时 | PETSc 输入矩阵 MatInfo nz_allocated/nz_used=56,834,000/55,984,880 项；MUMPS INFOG16/17=7,932/7,932 decimal MB、INFOG18/19=8,277/8,277 decimal MB、INFOG22=6,798 decimal MB、INFOG29=346,831,808因子项；同时树RSS峰 11,505,573,888 B，峰值worker stage fine_reference_residual_completed |

outer adapter 已包含 KSP-only；这些时长不能相加当作独立阶段总耗时。direct 计时只报告 watchdog elapsed 1647.527 s 与 launch charged 1801.467 s，不从二者差值分配 symbolic、numeric 或 solve 阶段耗时。NNZ 是矩阵非零项数，不是字节；7,932 MB 是准入估计，不是 RSS 峰值。

direct reference 启动时未使用要求的 user-service wrapper，观察到 cgroup /init.scope。发现偏差后未重启或迁移这唯一运行；独立 subreaper watchdog 完成了后代身份跟踪与清场。该流程偏差在 [execution-context 记录](records/r5_execution_context.json) 中单独保留。

下轮唯一建议候选是任务书 §8.1 的有界局部问题加多层全局波动纠错，重点是新传播/接口/粗空间机制与有界总因子预算；不是重做旧 42 宏块 complete-PC。需在下一 review 冻结机制和准确 p4 对照顺序后再决定是否实施。R5 未执行 Phase II；没有新增 PDE。

## 先前 N6 快照（review_v1 正式运行前）

以下 N0–N6 表和 attempt4 指标是 R4 运行前的历史快照。其当时将 G0/G1/direct 标为未运行，不能解释为当前状态；attempt4 的失败数值与分类仍有效并完整保留。

## attempt4 当时的 N6 状态

G0 attempt4 已真实建立 p6/q4 空间并进入外层迭代。 这里的恢复/native identity 检查，是把凝聚后求出的未知量恢复成完整场后，核对它代回原始方程的作用是否与凝聚代数一致。第 8 步，原 A6 相对真残差为 0.16667295750232392（要求 ≤1e-6），native recovery identity 为 3.0748104980683956e-10（要求 ≤1e-10）。worker 原始 summary 分类为 V20_RELEASE_GATE_FAIL。根据每 8 步检查的源码规则，这是恢复/native identity Gate 停止；raw KSP status/reason 未保存，因此具体 callback/reason 属于源码推导。它不是资源停止，也不是 max_it=2048 后仍未收敛的结论。

| 阶段 | 状态 | 证据边界 |
|---|---|---|
| N0 | complete | B线执行分支和 canonical worktree 已绑定 |
| N1 | complete | 0.7 nm 材料、有限三维缺口、G0/G1 计划、80-mode 清单已冻结 |
| N2 | diagnostic_pass_only | 60-cell p2 tiny 残差 1.772707454694957e-12；不是 G0/G1 p6 |
| N3 / G0 | V20_RELEASE_GATE_FAIL | 前三次实现异常保留；attempt4 进入8步 outer solve 后停止于 identity Gate |
| N4 / G1 | NOT_RUN | 没有 h-refinement 或跨网格比较 |
| N5 / G0 direct | NOT_RUN | 没有合格 iterative subject，direct reference 未运行 |
| N6 | closed_limited | 保存受限数值结果、成本和边界；没有精度/容量资格通过 |

p6 高阶有限元用较高次多项式表示复杂电磁场；路线先处理每个单元内部未知量以缩小全局问题，再用 q4/p4 操作纠正解。这样能减少外层未知量，但必须检查恢复后的全场是否仍满足原始 A6 方程和恢复恒等式。小型 p2 诊断、mesh audit 与投影检查仅验证各自环节，不能替代 p6 release Gate。

## attempt4 历史模型与结果

| 项目 | attempt4 实测 | 解释 |
|---|---:|---|
| 输入 SHA256 | 8e00fb6495845902a8113d982242d39ad0f4999b563c2c8049ecc3750b82ac9c | 冻结 G0 p6/q4 输入 |
| source SHA | de44f5bb4da48cd076df2b295ef6fe08b83d52fa | 实际运行源码身份 |
| physical model SHA256 | 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661 | runner物理模型身份 |
| G0 mesh / spaces | 336 cells；p6 229,680 rows；q4 69,856 rows；80 modes | 几何 audit 和 native AQ projection setup checks 通过 |
| solver | FGMRES，restart=32，max_it=2048；实际8步 | numerical Gate 提前停止，不是迭代上限 |
| official result | false | diagnostic field/error packet 保存；official R/T/A、A_volume 和能量闭合未生成 |

第 8 步 native identity 公式为 e_FE - B*H_p^-1*e_p。主控对已保存数组离线复核，difference 向量等于 native residual 减 derived native residual；范数 1.0129916171163611e-9 除以 operation scale 3.29448470971699 得 3.0748104980683956e-10。超过门槛约 3.07 倍。本记录不把它先验称作 roundoff，也不能由单次 Gate 单独确定其更深根因。

| 指标 | 实测 | 限值 | 状态 |
|---|---:|---:|---|
| 原 A6 full explicit true residual | 0.16667295750232392 | ≤1e-6 | 未通过 |
| native identity relative | 3.0748104980683956e-10 | ≤1e-10 | 未通过 |
| internal residual relative | 6.4490341352469694e-18 | ≤1e-10 | 通过 |
| port closure relative | 1.4794093427202804e-15 | ≤1e-8 | 通过 |
| Schur-port identity relative | 1.3094474052481446e-29 | ≤1e-10 | 通过 |
| final release packet A6 relative | 0.16667295750232333 | ≤1e-6 | 下游释放检查仍未通过 |

源码在 iteration 8 snapshot 中先检查物理残差，再检查 recovery/native/Schur identity。按保存数值可推导 callback 将其记为 RECOVERY_IDENTITY_GATE_FAIL，并返回 DIVERGED_BREAKDOWN；这两个字段均不是 raw KSP 记录。release packet 原生记录 V20_RELEASE_GATE_FAIL。外层 launcher 另外记 exit 4 / WORKER_FAILED；该 wrapper 状态不表示资源停机。完整证明、源码路径和 artifacts hash 见 [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)。

## 三次实现错误与第四次 Gate

| 运行 | 结果 | 含义 |
|---|---|---|
| attempt1 | parent ledger batch identity 不一致；3.896 s | 数值工作未开始，implementation bug |
| attempt2 | same-mesh wrapper 缺 rectangular_air_void_audit；87.897 s | 实际建成336-cell mesh并通过 native projection 检查，随后 cleanup 实现失败；未进入 outer KSP |
| attempt3 | 新 worktree 缺 Task39 相对 JIT cache 源路径 | FileNotFoundError；单次耗时未独立持久化，implementation bug |
| attempt4 | V20_RELEASE_GATE_FAIL | 进入真实迭代后因恢复/native identity Gate 受控停步；不是前三次 bug 的重分类 |

attempt3 的独立 elapsed 和必要人工修复工时都是 unknown，不能由共享 ledger 的时间差倒推。全部四次 worker、source、artifact SHA 与 ledger 在 [run index](records/run_index.json)。

## Setup、KSP 与资源成本

| 统计 | 值 | 口径 |
|---|---:|---|
| p6 / p4 condensation cold JIT | 58.575 / 18.047 s | 各自compiler event |
| compiler events | 11 | 包含多角色及缓存命中/未命中；不是单一setup时长 |
| qualified JIT hardlinks | 104 files / 1,400,533,851 B | 缓存文件字节，不是驻留内存 |
| p6 build audit | 15.216 s | 原记录 build timer |
| x1 setup-check | 22.907 s | setup-check timer，不表示完整全流程装配 |
| retained outer clock through terminal snapshot | 54.222 s | 保存的 outer elapsed；KSP-only elapsed 未持久化 |
| outer iterations | 8 matvec / 8 PC apply | KSP外层动作计数 |
| setup-inclusive inventory | bridge 13 / p4 26；terminal native 6 / Schur 11 / Hp solve 44 | 原字段各有范围，不能折算成8次outer PC |
| launcher workflow monotonic | 356.929 s | monotonic时间 |
| conservative realtime workflow | 392.257 s | 与monotonic差35.330 s |
| shared ledger | 本次 debit 392.262 s；累计 530.887 s | 账本口径，不是KSP-only时间 |
| process-tree RSS peak | 2,954,866,688 B | watchdog sampled simultaneous process-tree peak |
| swap / PSS | 0 B / disabled | 没有资源 Gate stop；PSS按profile禁用 |
| process cleanup | descendants cleared；identity coverage complete | watchdog 1,397 samples |

共享 ledger、conservative realtime 与 monotonic 是不同观测范围，不相减推造 KSP 或工程工时。cgroup memory peak 未在本次 compact run 记录中报告；不补值。

## attempt4 当时的精度、网格与容量边界

| 问题 | 当前结论 |
|---|---|
| official R/T/A、A_volume、energy closure | NOT_RUN；A6及identity release Gate 未通过 |
| G0–G1 h agreement | NOT_RUN；G1 未运行 |
| G0 same-discrete direct authority | NOT_RUN；direct preflight/factor/solve 未运行 |
| 80-mode channel truncation | CHANNEL_TRUNCATION_UNQUALIFIED |
| 2 TB target feasibility | unknown；一次 G0 RSS 不能外推目标规模 |
| 主导容量对象 | unknown；缺少通过 accuracy Gate 后的容量闭环 |
| Phase II PC | none selected；本批没有候选获得精度/有效性资格 |

没有 best-available discrete reference，也没有工程网格或连续极限结论。N2 tiny 诊断结果不作为 G0 的替代。N6 收口保存失败值和缺失值，不再运行 G1、direct 或其他 PDE。

## 选择性合并建议

| 依赖组 | 代表内容 | 当前建议 |
|---|---|---|
| production numerical/core | Task40 config、geometry、solver/runner profile | 数值 Gate 未通过；不升级 ordinary default |
| reusable runner/watchdog | run_case、JIT staging、watchdog | 保留工作流证据；不是 solver pass |
| checker/benchmark | N1 inventory、geometry fixtures、N2 diagnostic | 只支持各自范围 |
| compact evidence/docs | attempt4 record、run index、summary、response、测试摘要、模型总账 | 可随分支审阅 |
| research-only | 显式 Task40 p6/q4 双凝聚 profile | 保持研究用途，未资格化 |
| do-not-merge | 整体分支、master、ordinary default 切换 | 等待 review/merge approval |

## 证据入口

- [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)
- [运行索引](records/run_index.json)
- [阶段状态](records/phase_I_results.json)
- [精度与容量](accuracy_and_capacity.md)
- [测试摘要](test_summary.md)
- ignored raw attempt4 artifacts 位于 run index 所列 results 路径。

## Review V7 W0 实际补充执行收口（待审，目标未实现）

本次补充执行已在时间与实现失败边界收口，等待审阅；不自动继续 W1/W2。W0 进入 p6-only setup，生成 8 门 `PASS_COMPONENT_ONLY` same-live receipt 后，worker 在 tuple/list mode identity guard 处 exit 1，未到 full p6 component worker/raw export。修复版 public validator 在 native 主机上对保存 JSON 的 list、tuple 身份形式都通过；主线仅捕获并 hash-check 了 stdout。没有 p6 科学 tensor/场数组、independent tensor/CSR checker、full A6 residual 或 official R/T/A。目标尺寸继续 **NO-GO**。

| 阶段/对象 | 结果 | 数据身份与边界 |
|---|---|---|
| W0 p6-only setup | `FE_REACHED; eight component gates PASS_COMPONENT_ONLY` | 80 cells（4×4×5），degree `{6}`、532 ordered modes、φ=5°；输入文件名中的 `q4` 配置标签未由本 probe 执行为四个 q 或因子 |
| W0 worker | `WORKER_FAILED`, exit 1 | tuple/list ordered-mode identity guard；wall `196.762108860 s` / per-worker limit `199.490712881 s`；不是 time/resource/solver failure |
| 收据 validator | native list/tuple 两次 PASS | same-live JSON 的纯身份/字段重验；非本地主机执行，非 worker replay，FE/JIT 未运行 |
| full p6 worker / scientific raw | `NOT_REACHED` / `NOT_CREATED` | `raw_member_count=0`；p6 tensor/FE field arrays 未生成，独立 tensor/CSR checker 未运行 |
| W1 / W2 | `NOT_RUN` | 本次补充执行不会自动继续；W0 full qualification 未完成，W2 另缺 C1c 与完整 p6 链 |
| 原尺寸 full solve | `NO-GO` | AUTO 接线、全部 q 因子、完整恢复、精度与端到端成本未闭合 |

### 保存组件纯校验结果

| 组件门 | 重算最大 defect/ratio | 限值 | 结果 |
|---|---:|---:|---|
| C/D/H 与 raw action 等价 | `3.5931818134322393e-14` | `1e-10` | PASS |
| 532-mode full-DOF rank-one bound | `2.4672054282185927e-13` | `1e-10` | PASS |
| 五状态 action/recovery/output | `3.099637928778201e-14` | `1e-10` | PASS |
| 物理 FE RHS literal defect | `1.7324712509441664e-14` | `1e-10` | PASS |
| 非零端口 mode equation defect | `1.8654147652106162e-14` | `1e-10` | PASS |
| transform gate ratio | `3.4637921787560976e-6` | `1` | PASS |

这是保存组件收据的重算，不是全域方程 residual 或物理 R/T/A。求积数据是 4 个 facet identity records（两侧 × 两分量、相同节点）与 8 个独立身份比对，不表示执行四个 q cases。

### 资源、历史 attempt 与时间

- 当前 worker 的同时进程树 RSS peak 为 `1,408,434,176 B`，采样间隔约 `0.25 s`；PSS disabled/null；task swap `0 B`。native host preexisting swap `21,600 KiB`，不构成整机 zero-swap 资格。8 GiB raw-export 上界 `6,900,030,936 B` 是导出预算，不是 RAM/RSS。
- 两次 pre-FE worker fail 分别耗时 `2.026239892 s`（missing `src`，RSS `287,481,856 B`）及 `2.090595266 s`（live subreaper identity gate，RSS `290,197,504 B`）；当前 worker `196.762108860 s`。三次 worker elapsed 小计 `200.87894401792437 s`，不包含 `preflight_6bbc` shell/activation blocker，其耗时/收费 unknown。完整准备与 W0 总收费仍 null。
- 四小时 policy cutoff `06:41:49Z` 与 FE 启动 deadline `10:07:14Z` 分开；FE 在启动 deadline 前开始，worker 在 policy cutoff 前退出且 time gate false。policy 窗是派生 allowance，不是实测准备时间；现已到期，不启动新 FE。V6 debit `5,428.582333962078 s` 不变。

native 侧 36 份支持收据 `5,757,491 B` 有逐文件 SHA 和 copy/fsync/readback；原 35-member 包 `47,078 B` 是日志/ABI/资源/测试收据，不是 tensor/场数据。worker 在 raw 导出前失败，科学 p6 tensor/场原始数据没有生成；收据跨窗传输受限是另一项事实。native JIT 64 files、`1,220,807,231 B` 留在原路径。细节见 [actual-run record](records/native_w0_actual_run_v1.json)、[test summary](test_summary.md) 与 [response V7](../response_v7.md)。

5f74 提交中的完整旧 pre-FE ledger 与旧完整 response 均有独立、hash-bound 原文快照：[ledger snapshot](records/review_v7_prefe_snapshot_5f74e15.json)（10,566 B，SHA256 `e89103312f52f5717a3219d7ca01f5ea0c1ff41b178321ba43a62c259eae2f20`）及[旧 response snapshot](../response_v7_prefe_snapshot_5f74e15.md)（12,983 B，SHA256 `922f6efc5e75e63e480025eef60294c70d999d20b0aa96958beaa256244a8bd5`）。旧 response 中目标/AUTO/W1/H 成本账与历史负结果保留完整；早期 source authorization/no-PID/held 仅属历史时点。

本地文档合同 suite 使用 `scripts/activate_myfenics_wsl.sh` 的 `.venv`、PETSc 3.19/Open MPI 4.1.6 旧栈；最终输出见 test summary，不代表 native W0 ABI 或 PDE。native focused `40 passed, 10 skipped` 与两次 public validator PASS 均是已有 native 回执，不代表 PDE 或 raw checker 通过。数值代码仍以 `5f74e15fae6e01e4361325db162806a7319ba3f4` 为基线；主控审核后统一提交推送并回读最终 HEAD。
