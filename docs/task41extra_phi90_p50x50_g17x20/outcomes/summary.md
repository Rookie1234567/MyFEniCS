# Task41 阶段结果

本任务使用完整三维有限元，计算居中 17×20×120 nm Si 主体及 10 nm Si 基底。单胞横向为 50×50 nm，上入射掠角 1°、方位角 90°、S 偏振。**主案例没有额外 notch 或 air void。**

A1 用直接分解建立当前网格的比较基准：先在各单元内消去内部未知量，求解保留的边界与端口系统，再恢复全部场。它验证当前离散方程，不证明网格或模式截断已收敛。后续 A2 将用同条件参考预条件迭代解与它比较。

| 阶段 | 实际状态 | 范围与证据 |
|---|---|---|
| A1 首次启动 | FE 前工程失败，保留 | 旧 V29 环境标记误入 Task41；服务 1.563210294 s |
| A1 修复续作 | 完整场及独立 checker PASS | 原窗口续作；1400 单元、p6、168 模式 |
| A2 attempt7 / saved-output retry3 | A出口 PASS：A2原求解器6步且独立A6真残差通过；保存场续作完成A1/A2对照，checker-only retry3 PASS。原worker的`WORKER_FAILED`、`official_result=false`作为原始历史保留 | A6=`7.381572880480822e-08`（限`1e-6`）；checker通过不改写原worker分类，且没有重新组装FE算子；失败和资源口径见[a2_saved_output_checker_retry3.json](a2_saved_output_checker_retry3.json) |
| A2 P0 attempt6 | 十 q 数值与 CSR/native 资格通过后，V15 拒绝精确 Task41 profile；worker exit 4、official_result=false | 外层迭代未开始；无完整场、独立 A6 残差或 official R/T/A；工程准入故障，不是数值或资源门失败；见 [test_summary.md](test_summary.md) 与 [run_index.json](run_index.json) |
| A2 P0 attempt4 | q0/q5 的完整 CSR 与原生算子资格检查通过；随后 worker 因递归深度异常退出，official_result=false | 全流程未完成；没有完整迭代场、独立 A6 残差或 official R/T/A；0.7 nm 仍 NOT_RUN |
| B0 旧 inventory / P0 接线（历史状态） | 生产模式/q-sector与Stage-4轴规划已完成轻量清点；checker/profile capability 接线有定向测试；FE网格、Basix自由度、局部算子和求解均`NOT_RUN` | 64,120个`auto_propagating`端口模式；200个q、100个两胞sector；资源状态`NOT_YET_ADMITTED`，不是资源失败；原始清点的manifest未保存限制及本轮接线记录见[b0_07nm_computability_inventory.json](b0_07nm_computability_inventory.json)与[test_summary.md](test_summary.md) |
| 0.7 nm 完整场与离散精度 | NOT_RUN | 主控冻结源码及新单场合同/窗口后继续FE/dofmap、局部算子、端口投影与对象级资源测量 |

| A1 指标 | measured 值 | 解释 |
|---|---:|---|
| 独立原 A6 相对残差 | 1.7449656226232747e-10 | 因子释放后核验；限值 1e-6 |
| R / T | 0.25137919146306575 / 0.05712971752020276 | 全部已选端口模式的反射/透射功率 |
| 体吸收 A_volume | 0.6914910910199371 | 主体 0.6546758299465113，基底 0.0368152610734258 |
| 能量闭合绝对误差 | 3.205657961302677e-12 | 独立体吸收与端口平衡，限值 1e-5 |
| 凝聚增广系统 | 284568 行 / 234517208 NNZ | 全场 FE 自由度 934764 |
| 成功 service 全程 | 2064.867782874964 s（34.41 min） | 含 required checker；不是整项开发时间 |
| worker / checker | 2024.3355037230067 / 3.302761801984161 s | 都是父段内子项，不能再相加 |
| KSP setup / solve | 1296.680395565927 / 17.48903592606075 s | setup 含该路径 symbolic 与 numeric |
| 独立 A6 核验 | 71.65792042692192 s | 已包含于 worker 父段 |
| 同时进程树 RSS 峰值 | 62013505536 B | 独立 watchdog 采样，约 62.01 GB |
| 专用 cgroup 峰值 | 62582976512 B | 约 62.58 GB，含文件页等；与 RSS 不混称 |
| task tree / cgroup swap | 0 / 0 B | 宿主历史 swap 保留，本场宿主有 2 页 swapin，归因 UNKNOWN |
| PSS | null / 未采样 | 不沿用历史值或填零 |

用户已明确批准在资源合格时与邻项目并行，仍保留独立 cgroup、动态准入、至少 64 GiB host reserve 和任务零 swap；未停止或修改邻项目。A1 服务与 checker 后代均已清场。

成功科学 source：`4e46e524f1a5ebbc83218e615631c2477698347a`。原 T0 为 `2026-10-16T12:29:47.788292204Z`，修复未刷新窗口。首个失败及其间准备/修复成本保留；未记录的历史准备分项为 UNKNOWN。

详细路径、字节与哈希见 [a1_result_compact.json](a1_result_compact.json)，运行索引见 [run_index.json](run_index.json)，定向测试见 [test_summary.md](test_summary.md)。A1 的 probe/flux 诊断吸收与 official 值存在差异，原记录保留，不用于改判端口/体吸收资格。

A出口已通过：A1/A2 保存场同离散对照与 checker-only retry3 在定义范围内通过字段、模式、功率和 q-reference 检查；checker没有重新组装或施加有限元算子。原 A2 worker 的 `WORKER_FAILED` / `official_result=false` 是保留的原始 attempt 分类，不代表保存场验收仍失败。0.7 nm 完整场及网格/倏逝模式精度检查尚未运行，最终 2 TB/48 h 冷流程也未资格化；当前没有 merge approval。

## B0：早期可计算性清点（以下为历史状态）

轻量清点调用生产的端口模式生成器、有序模式manifest构造器、Task40 p6 q-sector映射器和Stage-4轴规划器；它没有建立DOLFINx有限元网格或自由度空间。实际轴计划为10×200×14、28,000个六面体单元，y步长0.25 nm，x/y/z材料界面均落在网格面上。`auto_propagating`生成64,120个传播端口模式，其中top/bottom为32,062/32,058，s/p各32,060；这只是传播模式清单，不是倏逝尾部精度资格。

实际映射覆盖200个q分支和100个两胞sector（每个sector配对q=t与q=t+100）。q1…q57没有传播端口，q0有8个，q58…q199均非空；100个sector仍全部非空，端口数范围524…816。空端口q不允许删掉其有限元参考sector，全部200个参考q仍属于后续完整算子资格范围。

生产manifest的规范字节SHA-256为`201e5d1675511dff30340596d60f78718f9cef812ddf939a56d81e12410dbcd7`，长度72,648,642字节。但首次命令没有将这些字节保存到ignored artifacts，q assignment向量也未落盘；UTC/monotonic起止没有采样。命令工具实测wall时间11.9秒已记为必要准备成本，不能重置或冒称有正式B0窗口。为遵守不重算已生成模式的要求，不会补跑同一清点；该原始manifest限制在compact证据中明确标记。源码HEAD当时为`0bf0dc38eab2cf61ca9feb5115323f78c68e6576`且工作树含未提交B0改动；相关源码/input文件bundle哈希`f7ed9b137ba30744f5a695e4d039aa86a3450d283b57b3fdd8d28dec35278d85`是在清点后由未变化的文件内容回算。

内存行数表仍是派生候选，不能当作B0 Basix/dofmap读回：全域独立行18,288,000、trace行5,688,000、每q局部行91,440、trace行28,440。p6全存储行直接按10×200×14网格的边/面/体拓扑计数为18,501,024；旧的按Ny比例缩放估值18,695,280保留作审计记录，但不再作为当前候选。以complex128计，一个独立全域向量候选约292,608,000字节，一个trace向量候选约91,008,000字节。200个q矩阵的结构非零数、数值数组、准确因子与工作区、所有驻留对象峰值、FGMRES工作向量和进程树峰值尚未测量，所以状态为`NOT_YET_ADMITTED_UNMEASURED_OBJECTS`。这表示尚无容量准入结论，不是已经测得超限；主控冻结源码及新的单场窗口后，安全的局部FE/dofmap、action和projection测量可继续，不应因全q因子峰值未知而一概停掉。

## A2 前置接线失败（原始记录保留）

两次启动均未进入 FE：首次错误拒绝输入解析器补入的两个 `false` 授权默认值；第二次 worker 使用的旧资源策略名称与 watchdog 不同。分别耗时 2.523650455987081 s、2.993759864009917 s，watchdog 同时树 RSS 峰值分别 233574400 B、248225792 B，任务 swap 均为 0、后代已清场。时间为 watchdog 父段，不冒充完整准备费用。

原 A2 T0=`2026-10-16T14:35:47.716727746Z`、window SHA=`d745147dbfc8640220701fa055ee101efbdd25a64c97ccfb5573ed864b2a124f` 保持；不重算 A1。详见 [a2_startup_failures.json](a2_startup_failures.json)。

第三次 source `05aa9739a6d27ddee91278dc827a7d7c70cbeef4` 已通过资源/窗口初始化，但 ABI gate 只登记旧 Task40 profile，仍在 FE 前退出。watchdog 父段 3.5461957671213895 s，树 RSS 287637504 B，任务 swap 0、后代清场；这属于 ABI 分派接线缺失，不能记作数值失败。原窗口继续，不重算 A1。

## A2 P0 第四次正式运行：q0/q5 校验通过，完整迭代工作流因软件异常失败

这里的 q0、q5 是 y 周期相位子问题。CSR（按行压缩存放的稀疏矩阵格式）只记录非零结构和值；“原生算子资格检查”用独立原生计算动作核对保存矩阵，确认这两个相位的准备结果可用，但它不等于完成完整有限元迭代求解。

| 条目 | 实测结果 | 含义与边界 |
|---|---|---|
| 身份 | source `48049161acb84f57b2d8248f67ea616fb837ccea`；run `20261016T151713.466294Z`；input SHA `dae9d625098692db1e707ef6e20e5352b03bc59215a083f698c47e79a6c48645` | 原 T0 `2026-10-16T14:35:47.716727746Z` 和 window SHA `d745147dbfc8640220701fa055ee101efbdd25a64c97ccfb5573ed864b2a124f` 未改 |
| q0 | `COMPLETE_CSR`、native `PASS`；矩阵 `28444×28444`，保存结构位置 `15323684`；最大误差 `5.76293983336288e-15`；CSR 内容 SHA `f37d3ba8dd2ef724e2f21c3a39c7547262caa3a6562100cc9a4908de01fb33c0` | 数组内容哈希已重算并匹配 manifest；结构位置数不冒称数值非零数 |
| q5 | `COMPLETE_CSR`、native `PASS`；矩阵 `28468×28468`，保存结构位置 `15390104`；最大误差 `8.175673078498892e-15`；CSR 内容 SHA `95368eb676cb536bc660e334e8032a2a8e499734f44bb76f91e13fb0bb6a4068` | 数组内容哈希已重算并匹配 manifest；结构位置数不冒称数值非零数 |
| 最终运行分类 | `WORKER_FAILED`；run summary `exit_status=4`、`official_result=false`；service receipt 的 `run_case_returncode=3`，`failed_raw_evidence_retained` | worker 记录 `Task38 Full3D iterative adapter failed: maximum recursion depth exceeded`；不是数值残差门失败 |
| 用时与资源 | 全流程 `1214.0498632008675 s`，时间门未超；进程树 watchdog RSS 峰值 `3058593792 B`；专用 job cgroup 峰值 `3777265664 B`；任务/cgroup swap `0 B`，后代已清理 | RSS 与 cgroup 是不同采样范围，分别报告，不相加或互换；无资源停止 |
| 未完成项 | 完整外层迭代、完整场、独立原 A6 残差及 official R/T/A 均 `NOT_RUN` | q0/q5 的通过只证明部分算子准备，不能把 A2 判为科学通过；这次也不是方法的数值负结果 |

**故障定位：**事件记录显示 q0 和 q5 的 native 检查完成，但 `task40_v17_p6_sector_ready` 事件为 0；worker 随后报递归深度超限。stderr 为空，保存工件没有 traceback。异常包装边界 [task038_input_worker.py](../../../src/runners/task038_input_worker.py#L265) 把异常压成字符串，因此没有现场调用栈。通过源码数据流和同结构 mock 定位到回执循环引用：`paired_witness_ready` 的 metadata 把可变 `native_stage_records` 字典直接放入 `stage_records`；持久化回调随后把刚生成的 `paired_witness_ready` 记录加回这个字典，形成“当前记录 → metadata.stage_records → 同一字典 → 当前记录”。对完整 sector audit 做 JSON 归一化时因此触发 `RecursionError`。保存的单项 JSON 没有循环，因为它们在当前记录加入该字典前已写完。

**最小修复与验证：**在 [task40_v30_selected_q_csr.py](../../../src/solvers/task40_v30_selected_q_csr.py#L1322) 写入 `stage_records` 时，对此前各项记录建立浅快照，切断当前记录与其容器之间的回指；CSR 数组、native 动作、误差限、物理身份和数值路径均未改。 [task40_v30_q_csr_integration.py](../../../src/test/test_task40_v30_q_csr_integration.py#L730) 的小型 mock owner 回归通过 worker 同形的 sector-ready 投影调用实际 `_jsonable` 序列化。定向命令在资格化 complex ABI 下结果为 `1 passed in 1.68s`；`git diff --check` 通过。没有重跑 FE/PDE，也未提交或推送；正式运行仍为 `WORKER_FAILED`、`official_result=false`，数值项保持 `NOT_RUN`。

**q0/q5 后续复用边界：**已保存的 q0/q5 `COMPLETE_CSR` 和 native `PASS` 保留 source `48049161acb84f57b2d8248f67ea616fb837ccea` 的生产身份。本次日志快照修复不改变相关数学或数组；按任务要求优先复用。当前 Task41 入口尚未接通这些保存结果，需最窄的 hash-bound 导入与当前物理、模式、映射和 CSR 身份核对，并分别记录旧生产者和新消费者；不得把旧 PASS 重署为新 source，也不能仅因接口缺失默认重算。必要的 live owner 仍需建立，完整参考逆、因子真残差和 target 检查仍按原门执行。
原始证据： [run summary](../../../results/task41extra_phi90_p50x50_g17x20/task41extra_g13_p6_phi90_iterative_a2__full3d_iterative__mpi1__Mna/20261016T151713.466294Z/run_summary.json)、[worker log](../../../results/task41extra_phi90_p50x50_g17x20/task41extra_g13_p6_phi90_iterative_a2__full3d_iterative__mpi1__Mna/20261016T151713.466294Z/watchdog/worker.log)、[事件记录](../../../results/task41extra_phi90_p50x50_g17x20/task41extra_g13_p6_phi90_iterative_a2__full3d_iterative__mpi1__Mna/20261016T151713.466294Z/task41_g13_a2_p6_y_orbit_reference_events.jsonl)、[service receipt](../../../benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2/service_source_48049161acb84f57b2d8248f67ea616fb837ccea/task41_p0_service_receipt.json)。q0/q5 manifest 和 native qualification 位于 `.../task41_a2_q_csr_native_qualification/q5_twist0/`；q0 的三个 CSR 数组在其同级 `q0_twist0/`，q5 数组在 `q5_twist0/`。完整工作流报错后这些部分结果仍保留。


## A2 attempt7 保存场对照与 checker-only retry3

A2 原求解器完成 6 次迭代，释放因子后独立 A6 真残差为 `7.381572880480822e-08`，低于 `1e-6`。原 worker 随后在 A1 保存场的 E/H 采样表示与 MPC 约束恢复检查处以 `WORKER_FAILED` 结束，`official_result=false`。保存场续作只重建必要的场表示与比较输出，没有重跑 q 装配、因子或 KSP。续作的 27 个输出身份检查及 A1/A2 字段、模式、功率比较通过；续作中 required checker 首次因 keyword-only 参数被按 positional 方式传入而触发 `TypeError`（约 3.42 s）。之后 checker-only retry2 才发现 schema 字段不一致：producer 使用 `q_indices`，checker 错读为 `global_q_indices`；两项工程失败均保留。

冻结 checker source `4c0af8c1e73a47337b497f3a5ccda64933d04591` 后，在同一不可变输入快照上以独立 checker-only retry3 完成：service exit 0、`required_checker_status=passed`、checker `PASS`、错误列表为空。它按记录中的原生 q 分组独立重算 saved-action 代数并校验映射数值、输出身份与物理比较；**没有重新组装或重新施加 FE 算子**，所以不声称这是新的一次 FE 解或重新组装复核。

| 同离散比较量 | A1参考 | A2保存场 | 实测绝对差/相对差 | 门限 |
|---|---:|---:|---:|---:|
| 全体积 E 相对 L2 | — | — | `6.83819901978217e-09`（绝对误差范数`2.6813167841674313e-06`） | `1e-4` |
| 全体积 scaled-curl 相对 L2 | — | — | `6.845781370112187e-09`（绝对误差范数`2.684726651356638e-06`） | `1e-4` |
| 端口总功率 R / T / A(balance) / A_volume | `0.25137919146306575 / 0.05712971752020276 / 0.6914910910167315 / 0.6914910910199371` | `0.2513791884968878 / 0.057129717215935225 / 0.691491094287177 / 0.6914910977829845` | `2.9661779699097224e-09 / 3.04267534778635e-10 / 3.2704455810161903e-09 / 6.763047344371387e-09` | 各项绝对差`1e-5` |
| 86 个显著正式模式的振幅/逐模式功率 | — | — | 最大相对振幅差`6.77415279387487e-06`；最大功率差`2.9583918648157237e-09` | `1e-4` / `1e-6` |

q-reference 审计覆盖 5 对 sector、q0…q9、40 个 CSR 动作、10 个配对 peer CSR 动作，以及 10 个 fresh-factor probe 和 10 个同因子第二 RHS probe；严格与 V15 reference 各 6 项通过。另有 `5×40×40×3` 场表示见证：由 `curl(E_FE)` 重构的 H 与 A1 原始 H 采样相对差 `9.444546333396517e-16`，这是场表示一致性见证，不是 A1/A2 的 H 场差。289 个空间衍射级/578 个偏振行是诊断库存，与 168 个正式 DtN 端口分开。

checker-only retry3 service 用时 `33.095924948807806 s`，watchdog `29.815508095081896 s`；进程树 RSS 峰 `1632485376 B`、专用 cgroup 峰 `682569728 B`，两者是不同口径；task/cgroup swap均为0，PSS未采样，后代已清场。固定 A2 窗口 T0 与SHA不变。原求解、续作、checker retry 的时间和资源不相互混加；完整身份、所有旧失败、输入/输出hash和分段计费见 [a2_saved_output_checker_retry3.json](a2_saved_output_checker_retry3.json) 与 [run_index.json](run_index.json)。0.7 nm 仍为 `NOT_RUN`。

## P0 冻结前 B0 入口阻塞收口

| Gate | 当前结果 | 判定边界 |
|---|---|---|
| A2/B0 ABI 身份 | 精确 profile→case/run 绑定；既有 native receipt、源码 clean 与 Task40 strict 隔离保留 | 本机 C1 测试通过，不等于工作站 native ABI 正向资格 |
| B0 runtime 入口 | 真实 DAT→`_V14Runtime`→候选合同 fixture 覆盖固定 T0/bootstrap、资源包和 dispatcher binding | 无 FE 网格、service 或 PDE |
| 两类模式核验 | 诊断表按 DAT 的578个 `(m,n,polarization)` 键；正式 DtN 表逐项匹配64,120个冻结键，top/bottom分别32,062/32,058 | 诊断库存不代替 official DtN 清单；缺项 fixture 被拒绝 |
| carrier 内存预检 | 两对 sparse arrays、MPC slave rows及全空间向量扫描/索引临时量已分列预算 | 从实际 dofmap 推导的**上界**，非实测峰值，不构成内域为零证据，也不改变任何 cap/停止门 |
| 最小定向回归 | 8 passed；py_compile 与 `git diff --check` 通过 | 未重跑V19宽批次、全仓、FE/PDE；本机仍没有满足正式入口的 native Linux receipt |

下一步由主控冻结这组源文件并在符合合同的 native Linux 环境执行正式 prepare/service。详细命令、身份、fixture 结果和内存口径见 [test_summary.md](test_summary.md)。

## B0 受控停止与端口生成修复（当前）

B0 已真实建立原尺寸 FE/MPC 并开始端口构建。旧方法对每个端口分量创建并扫描全场向量，实测早期约35秒/模式；这不是求解迭代卡住。用户批准受控停止后，保留94/64,120模式、540,115,008 B的完整提交前缀，服务及全部后代已退出。尚未开始因子或KSP，没有0.7 nm完整场。

| 实测口径 | 值 |
|---|---:|
| watchdog父时间 | 3501.76164272381 s |
| 同时进程树RSS峰值 | 4,020,916,224 B |
| 任务cgroup swap峰值 | 0 B |
| 分类 | USER_CONTROLLED_STOP；不是数值失败或时间门触发 |

本次修复复用已有边界面积分内核，仅在真实边界cell及MPC master闭包内累加，避免每个分量扫描整个场。保留实际几何/方向、编译积分规则、相位和原两级筛选。正式B0路径先用六个代表模式与旧FFCx全向量比较完整B/D/H及作用；通过才进入全模式构建。此时只有定向测试通过，真实网格速度和数值资格仍待运行，不能宣称已提速。

旧94模式绑定旧内核/source/context，不能直接混入新checkpoint；保留旧文件原字节，新attempt从新内核mode0开始，旧成本不清零。固定B0窗口仍为2026-10-17T05:43:44Z至2026-10-19T05:43:44Z，数值截止05:23:44Z，未刷新。细节见[b0_controlled_stop_native_surface_preparation.json](b0_controlled_stop_native_surface_preparation.json)。

### 新边界内核首模式资格负结果

冻结源码`611be2d2debedb60c53b3d2454b0374f5c82b3dd`在新attempt `20261017T095825.478498Z`完成真实网格和degree160积分身份检查，但首个top/(m=0,n=-71)/s模式支持集未一致，停止全量生成。这里“支持集”指经过原两次1e-13相对筛选后仍保留的行；误差小不自动证明这些行完全相同。

| 指标 | 实测 |
|---|---:|
| B/D支持集对称差 | 2000行；旧60000、新58000 |
| B/D完整功能向量相对L2差 | 约2.2032e-13（L2门1e-11已达，支持集门未达） |
| D_raw x相对差 / H差 | 5.316414382339111e-14 / 0 |
| 重构单模式DtN作用相对差 | 2.3047e-13；支持集仍未通过 |
| 两分量旧装配wall | 35.43899469124153 / 34.33610567031428 s |
| 两分量新装配wall | 0.06333467597141862 / 0.05248673399910331 s |
| watchdog父时间 | 244.77716858126223 s |
| 同时进程树RSS峰值 / task swap峰值 | 4,019,314,688 B / 0 B |

该速度只代表本次单模式两分量，不代表完整端口或求解加速；候选当前未获准进入全量构建。unit已退出且后代为空，未启动因子、KSP或完整物理输出。完整原事件及身份见[b0_native_surface_pairing_failure.json](b0_native_surface_pairing_failure.json)。事件只有counts/norm/cutoff等汇总，未保存逐行rows/values；不能声称已定位某个实体或证明只是舍入。正在有限局部诊断，不降低阈值、不原样重启整场。

### 局部根因与配对判定修正

对实际顶面两种宽度4.25/5.5 nm、原degree160、882局部行做独立检查：直接Basix积分与多项式积分相对差约1.1e-15，FFCx与它们约2.2e-13；内部自由度row557的顶面切向迹在全部积分点精确为零，而FFCx留下约4.82e-14残值，超过原组件global cutoff约2.50e-14。相位分解误差仅约1e-16，不能解释差异。局部机理与正式支持差高度吻合，但未回读全局2000个差异row ID，也不证明所有MPC/方向已通过。

主控复核task.md§4/6/7后，确认“两个不同积分实现筛后mask必须完全一致”是本轮额外加入的辅助hard gate，不是原任务数学门。因此修正该新判定，支持差仍完整披露，资格使用稀疏支持并集上的全部值差、原reference-L2≤1e-11与H≤1e-14；不改两个生产1e-13筛选、不删tiny、不改任何q/native/因子/target残差和物理门。旧611be2d2失败仍保留。下次实际代表配对需原子保存rows/values并通过原误差门，显著漏项与错误相位的反向fixture必须失败；之后才允许继续完整构建。

局部原始数组/脚本/metadata的路径、hash、费用和范围见[b0_surface_roundoff_diagnosis.json](b0_surface_roundoff_diagnosis.json)。这是局部原因诊断，不是新的完整B0成功。

### B0配对门修正与局部范围

对任务书逐项核对后，§4第107行要求以实际数据核实新case的B/D内部支持条件，§6第153行规定完整CSR/native作用误差≤1e-11；两处都没有要求两种积分实现经过阈值筛选后必须留下完全相同的行集合。逐行相等来自冻结实现中的额外辅助判断，而非Task41正式数学门。当前修正保留对称差数量、支持是否相等及完整row union值差；是否通过只由原reference-L2误差≤1e-11决定，H归一化≤1e-14、行域/唯一排序、实际MPC闭包、相位、积分身份及两次1e-13筛选均未改变。显著漏项或错误相位仍会因完整union误差超限而失败。

实现只作用于Task41 B0的FFCx与native代表模式配对检查。每个模式现在把两个component、D projection、B coupling的生产/候选稀疏rows与values，以及D_raw输入的非零稀疏描述，原子写入本attempt的`task41_b0_native_surface_pair_raw/`；模式事件记录NPZ路径、SHA-256和metadata路径。证据在gate异常抛出前保存，不包含完整稠密场。

本地C1定向回归为10 passed，覆盖tiny support差异仍通过原L2门、显著漏项和符号相位错误仍失败、失败前证据可读回及既有MPC/cutoff回归。旧attempt `20261017T095825.478498Z`仍按当时冻结源码的失败记录保留，不回溯改分类；它没有启动factor、KSP或完整场。当前代码仅完成本地测试，尚待主控冻结并部署到native Linux；未启动FE/PDE或正式B0续算。这一配对结果本身不证明整个B/D算子、全部MPC映射或0.7 nm计算已获资格。


## B0 0.7 nm 本次 resource-gate stop（2026-10-18）

本次 Task41 B0 确实进入 0.7 nm 新物理，按 p6、10×200×14（28,000 个六面体单元）、MPI1 启动。新端口清单有 64,120 个有序模式（top 32,062、bottom 32,058）；q_count=200，其中 143 个 q 有分配模式、57 个为空。端口 surface carrier 已完整提交 64,120/64,120 模式，文件 363,791,051,840 B。运行停在 assembly 阶段；没有完成 B0 全部 FE/P6 组装、q CSR/factor、KSP/FGMRES、完整场、独立 A6 或 official R/T/A/A_volume。运行证据没有保存精确 Python 指令游标，故不把候选代码热路径写成已测根因。

| 证据 | 实测 / 判定 |
|---|---|
| 运行身份 | source c52d0d3c0ec6b46c52c3bcf464ee53164308f1c5；input SHA a0c45d0475bd2b41d2d19589831086468a62f39fdca5b74734b62751df1485c1；execution contract SHA 5657d456d67f2b9e3b94aa19a0666a1b011dece6e7b6c7043eb929b45d711f5d；固定 window SHA 87dd4ec560a208122e9959987a392bf878162793c61582877969206686d922e6；完整 hash-bound 记录见 [B0 stop compact](b0_resource_controlled_stop_20261018.json) |
| 停止 | watchdog RESOURCE_CONTROLLED_STOP；2026-10-18T04:00:34Z；whole child tree 30 s grace 后 SIGKILL；完整工作流 62,890.80 s，time gate 未超限 |
| 直接资源样本 | process-tree RSS 1,271,718,285,312 B；task cgroup peak 1,580,571,795,456 / limit 1,649,267,441,664 B；task cgroup swap peak 0 B；专用 cgroup OOM kill 计数 0 |
| 64 GiB reserve 触发读数 | host available 854,915,547,136 B，扣一次 host reserve 后 786,196,070,400 B；task-cgroup remaining 68,698,267,648 B，task-cgroup reserve 0 B。通用 watchdog 将较小的 effective_available 与 host reserve 比较；此时有效余量仅比 64 GiB 少 21,209,088 B |
| 数值结果 | 没有完成场或 solver residual；分类是受控资源停止，不是 OOM、时间门或已证明的数学失败 |
| checkpoint / 清场 | 完整 carrier 与小型 checkpoint metadata 保留；原 watchdog summary 仍记 descendants_cleared=false。2026-10-18T04:16:04.696333+00:00 独立读回全部旧 PID 已退出、旧 cgroup 不存在；这条 later cleanup 另记，不覆盖原记录 |
| A1/A2 | 13.5 nm A1 与 A2 A出口 PASS 保持不变；本次 B0 不改变其证据 |

源码复核确认停止谓词存在分域不一致：benchmarks/subreaper_watchdog.py:1278 无条件检查 effective_available_bytes < reserve_bytes；其 effective_available 是 host 与 task/ancestor cgroup 可用量的最小值。分域策略下应分别检查 host available 是否低于 host reserve，以及 task-cgroup remaining 是否低于 task-cgroup reserve。触发时 host 余量远大于 64 GiB、task-cgroup 自有 reserve 为 0，因此正确的分域 reserve 谓词不会触发；当前通用 watchdog 却把 64 GiB host reserve 再套到 cgroup 剩余量上。这个发现要求修正代码和定向测试，但不构成放宽 reserve/cap 或立即重跑的许可。

carrier 到 P6 action 的源码也有具体内存风险但未被本次日志定位为实际触发点：worker 在 task40_v10_worker.py:8763 未传 bounded_direct_term_build，builder 默认走逐项 Python 展开；即使启用现有 bounded 分支，它仍逐行做 Python 映射并为每个 port 分配与输入规模相同的输出数组，不能单靠打开该布尔值消除重复 backing。下一步应先修正上面的 split-domain predicate；随后审查用可重复、file-backed carrier iterator 接入现有 one-mode provider、把行分类改为有界数值块并仅保留一份显式拥有的 direct B/D backing。checkpoint 的当前身份绑定 producer source/input/window/contract，且本次 cache_metadata_stable=false，所以完整生成只代表证据已保存，不能宣称已可跨新 source/window 安全复用。需要把 producer provenance 与完整数学 identity 分开，并在核实 manifest/字节稳定和数学身份完全一致后才准许新 consumer 重开。
