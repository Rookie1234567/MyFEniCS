# Task41 阶段结果

> **当前最新阶段：Task41extra Review V6；28,000 个 actual 几何键已构建，完整两列作用未通过原数值门。** 八个局部代表键均通过 `1e-11`；最终保存证据 checker 审计完成、数据完整，但 top/bottom 完整作用冻结分母相对误差为 `1.7183209126709868e-10` / `3.6180522433957604e-10`，均高于 `1e-11`，所以 `official_result=false`。按照 Review V6 停止，不启动 200q、factor、KSP/FGMRES、完整场、A6 或 official R/T/A。入口：[V6 response](../response_v6.md)、[V6 compact](b0_v6_actual_qmetric_full_action_failed_20261021.json)、[174项数组哈希索引](b0_v6_actual_qmetric_hash_index_20261021.json)、[测试记录](test_summary.md)、[run index](run_index.json)。

## Task41 B0 V6：候选构建成功，完整作用门失败

此模型仍是三维 p6 Maxwell 有限元：28,000 个单元用实际 mesh 坐标生成局部张量；共享参考基函数表并把矩阵乘加分块，是为了减少逐键重复计算。该组织方式加快了实际候选构建，但没有改变最终验收标准，也没有产生完整场。

| 阶段 / 指标 | 实测结果 | 成功/失败的具体含义 |
|---|---|---|
| 候选身份 | source `210fbbf271faa14c62ac30153b80332d0e645982`；geometry `mesh_actual_exact`；evaluator `actual_qmetric_blocked_gram`；28,000 raw / 28,000 oriented keys | 候选生产路径完成；此前 V5 的时间准入拒绝仍是历史结论，V6 已在新固定窗口中实施 |
| 八键局部资格 | raw/oriented 最大相对 Frobenius 差 `1.925763134488738e-15` / `1.925763134488735e-15`；K/G/J/L 最大差 `1.9351592008775263e-15` / `1.5612961744873414e-15` / `1.5663200066212496e-15` / `1.616229241762263e-15`；R/T/S 最大差 `8.726871992808957e-13` / `6.821847465821295e-14` / `1.047234456910219e-14` | 八键全部低于各自 `1e-11` 局部门；局部通过不代表完整两列通过 |
| 构建时间 | evaluator 19,641.249084575567 s / 28,000 keys，平均 `0.7014731815919845 s/key`，最大 `5.322032446041703 s/key`；owner 24,777.34818448685 s，worker 28,381.330578941852 s，service parent 28,555.90928376885 s | 边界不同，父子不重复求和；阶段明细见 response/compact |
| 新候选数组 | 174 个数组，声明 payload `4,514,199,336 B`；donor 的 141 个数组 `9,379,882,344 B` 原样复用且未复制 | 大数组保留在 ignored results；Git 中只新增 compact/hash 索引 |
| 完整 p6/native action | top absolute L2 `3.824090978625035e-7`，冻结分母 `2225.481253487629`，相对差 `1.7183209126709868e-10`；bottom absolute L2 `8.051905483782545e-7`，冻结分母 `2225.4807123031883`，相对差 `3.6180522433957604e-10` | 两列均超过 `1e-11`；真实 full-action FAIL，`official_result=false` |
| 候选恢复 | forward 相对差 `1.981377497384616e-11` / `1.979023053583157e-11`；native volume residual `1.4373046679706224e-15` / `1.436540888080939e-15` | forward 限值 `1e-11` 未过；native residual 限值 `1e-10` 通过；额外 same-LU 修正数为 0，未耗尽三次额度 |
| 归因 | closure absolute L2 约 `198.18` / `198.16`，相对冻结分母约 `0.0890506791` / `0.0890404748` | `DIAGNOSTIC_ONLY`；没有证明舍入误差或其他单一根因 |
| 同时资源 | build tree RSS `367,708,164,096 B`；task cgroup `366,622,593,024 B`；task tree/cgroup swap `0 B`；宿主全局增量 +31 swap-in / +58 swap-out 页 | 宿主页不是任务归因；RSS/cgroup 与宿主计数分开，不能称宿主零 swap；PSS未采样 |
| 最终 checker | source `89e1e42114870ba1db752dfaf6d893ad13f923d6`；checker COMPLETE、data integrity true；受监督 service 重算全部 174 条数组记录内容 SHA，checker 重开并重算 action/recovery/attribution 必需数组；service 180.8804526119493 s、watchdog 131.0202877856791 s | checker 审核成功完成而数值资格失败；top-level donor recovery PASS 不属于 V6 candidate |
| 停止阶段 | global volume matrix未物化；200q、factor、KSP/FGMRES、full field、A6、R/T/A、A_volume均 `NOT_RUN` | 按 Review V6 的 full-action FAIL 出口停止；不把未运行写成通过 |

固定窗口 SHA `ea6b38c3bc791ace068c75188a562023cae197f7016f110b0b86970891c46c8d` 未刷新；T0=`2026-10-20T10:21:59.261754681Z`，数值 cutoff=`2026-10-21T10:01:59.261754681Z`，总 deadline=`2026-10-21T10:21:59.261754681Z`。最终 audit SHA 为 `5ebdc364416a5ba8eed34506fd232eae22e9c92f0968924d1064f70d1fb03460`；完整身份、数组与原始失败回执见 [V6 compact](b0_v6_actual_qmetric_full_action_failed_20261021.json) 和 [hash index](b0_v6_actual_qmetric_hash_index_20261021.json)。

## 历史阶段记录：A1/A2 与较早 B0/V2/V3

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

## Task41 P0 Review V2：require-existing donor 续作与三次正式尝试（2026-10-18）

Review V2 修复 watchdog 的分域资源谓词，并沿现有 Task41 prepare/service 路径使用 require-existing donor：缺失或身份不符时失败关闭，不静默重新生成。host reserve 只对 host 可用量检查，task/ancestor cgroup reserve 只检查各自域；原 1.5 TiB cap、64 GiB host reserve、task reserve 0、time cutoff、swap 和采样门均保留。此前误停样本的 host 可用量为 854,915,547,136 B、host reserve 为 68,719,476,736 B；task cgroup 可用量为 68,698,267,648 B、task reserve 为 0 B。旧比较产生 21,209,088 B 的跨域假短缺，按分域语义不构成停止。

续作对旧 producer source c52d0d3c0ec6b46c52c3bcf464ee53164308f1c5 的 64,120 模式、363,791,051,840 B donor 执行完整 require-existing 检查。已核对的 committed-prefix SHA-256 为 2595b9518e2422bfadbc2f1a6640e619d60501525b07bda48a068a8ec478a10e；offset index 有 64,121 项、512,968 B，SHA-256 为 2a59fd6a2504ac0b0b8c675325dcaf517ec7bc5dc87b8cb496b96b413b592453。新模式生成数为 0。fresh Task41 B0 support certificate 记录 boundary B/D 各 9,094,725,000 rows、cell-interior nonzero values 为 0；这不是从 Task40 搬来的内部零证明。consumer 继续使用现有 P6/native action、RHS reduce 与 storage recovery 接口，没有建立第二套数值算子。

| attempt / source | 父 workflow 时间 | 结果与修复证据 | 同次资源读数 |
|---|---:|---|---|
| 20261018T090832.301793Z / ab9e14dd00b2f1a94acd7ced5949e940caa724e6 | 4,266.0541681298055 s | WORKER_FAILED：original trace row 被当作 independent active row 传给 MPC row mapper。下一源码按 cell-interior、active-original 与 slave 分类：只映射 active rows，保留 interior 值，slave 不做第二次 pullback。donor validation 已通过，父流程后续仍失败。 | process-tree RSS 9,186,394,112 B；job cgroup peak 79,297,404,928 B；task swap 0 B；time gate 通过；失败时固定窗口约余 68,645.49 s。口径保持分列。 |
| 20261018T104243.408669Z / 6c31c5be468ebe6b50102a9beaaa701f48107b4d | 4,223.6894003856 s | WORKER_FAILED：mode 16030 的 saved nonzero P6 B/D gate 失败。raw-field 诊断发现 B 检查把近零 mode wave number 当成非零 B witness alpha；修复后 B witness 使用 [0.7, -0.4]。raw B relative error 为 3.7431e-14；raw D 对照为 5.3164e-14 / 1.5943e-14。失败 attempt 未保存实际 P6 D 值，离线 raw 结果不构成 fresh P6 requalification。 | process-tree RSS 9,185,849,344 B；job cgroup peak 9,326,239,744 B；task swap 0 B。systemd exit 后峰值另有不同读数，未归因或相减。 |
| 20261018T121210.548690Z / 53243cd6766b564fed17668753e9fdbb7cab1129 | 9,364.070864045061 s | WORKER_FAILED，V2 数值结论为 NUMERICAL_GATE_FAILED、根因未闭合：mode 16030 的首列 RHS recovery 相对误差 2.0454083899234283e-11 > 1e-11；第二列和 condensed RHS 比较未到达。 | process-tree RSS 11,411,648,512 B；task cgroup peak 11,872,563,200 B；task swap 0 B；后代已清场；resource/time gate 均未触发，最后窗口余额约 52,529 s。 |

第三次运行完成 64,120/64,120 saved-surface applications，用时 4,257.863887676038 s；校验后读取 363,795,691,904 B，frame parse 子计时 93.11829357547686 s。full RHS action/recovery 没有独立子阶段计时，记为 UNKNOWN。父 workflow 包含这些子阶段，不能再把 4,257.86 s 或 93.118 s 加到 9,364.07 s 上。第三次 11.87 GB 的 task-cgroup peak 与此前 carrier-build resource stop 的 1.58 TB peak 来自不同阶段、不同工作量，不代表同 scope 内存下降。宿主全局 swapin/out 13/0 页不能归因到 task（归因 UNKNOWN）；PSS、各数组/持有 backing 峰值及 full RHS action/recovery 子阶段时长 UNKNOWN。

两个所选模式 16030/48090 的 saved B/D consumer receipts PASS，但不能代替完整 action/recovery 门。共享 P6/native 调用链实际到达 volume action、RHS reduction 和 storage recovery；已知输入 recovery 在首列失败，因此完整 target action 未闭合。q CSR/factor、KSP/FGMRES、完整场、独立 A6、official R/T/A 与 A_volume 均 NOT_RUN，official_result=false。原始 run receipt 的 WORKER_FAILED 分类和前两次失败保留；不把此次运行归因到 LU、MPC、行映射或浮点舍入。A1/A2 13.5 nm 结果保持原样。

测试包含 以 ab9e 为基线、随后提交为 6c31 的 row-map/recovery 修复 fixtures 2 passed in 0.55 s；以 6c31 为基线、随后提交为 53243 的 alpha/action 修复 fixtures 2 passed, 13 deselected in 0.34 s，另一次 whole-file 批次 12 passed、3 failed（未改动 regular-inverse fixtures，未重跑 baseline）；本机相关套件 16 passed in 0.88 s，绑定 source-tree HEAD 5e82225427d91d2ec4650169e558b6da29e75a8e 与 tracked-diff SHA 9c8707fc9541087d1d7523edfa1eb10f18842845ed8b4ead70a97369561b98e7。1 项 B0 service-contract fixture 在 imports/preflight/pytest 前被 ABI receipt profile/host/boot mismatch 阻塞，不计通过。Ruff 不可用，未运行全仓测试。测试和执行边界见 [test summary](test_summary.md) 与 [V2 adoption/action/performance compact](p0_v2_adoption_action_performance_20261018.json)。

证据索引：[row-map attempt](p0_v2_raw_probe_rowmap_repair.json)、[B witness attempt](p0_v2_alpha_probe_field_diagnostic.json)、[local final evidence](p0_local_final_evidence_20261018.json)、[adoption/action/performance compact](p0_v2_adoption_action_performance_20261018.json)、[final recovery failure](b0_full_rhs_recovery_gate_failure_20261018.json) 和 [run index](run_index.json)。下一步由 ChatGPT 依据数值门失败与向量未保存的取证缺口审阅后续处置；本阶段没有自动重跑。

主控补充：在最终冻结源码 `53243cd6766b564fed17668753e9fdbb7cab1129` 部署后，使用工作站既有 native complex activation 执行新 B-action 振幅 fixture 与 two-input borrowed-buffer fixture，结果 `2 passed, 13 deselected in 0.56s`，随后才启动 `121210` 正式 attempt。该记录来自主控部署命令回执，不能抹去此前本机旧 ABI receipt 的阻塞记录。科学 source 与本次文档结果 HEAD 分开；最终结果 HEAD 由集中推送后回读提供。
## Task41 P0 Review V3 与获授权 16 GiB 续作：恢复 PASS、full action FAIL（2026-10-19）

V3 continuation 保留原 fixed-window T0，并按用户明确授权把新 B0 execution contract 的原始证据配额从 8 GiB 提升至 16 GiB。8 GiB 时的旧 attempt 因预测 11,882,448,300 B 超过 8,589,934,592 B 而资源停止；新合同仍保留 2 GiB free-space floor、内存与 host reserve、task swap0 和全部数值门。最终运行的磁盘准入通过，随后运行抵达 full-action 数值门并失败。数值失败不是配额失败。

| 阶段 / 身份 | 实测结果 | 数据身份与证据 |
|---|---|---|
| 获授权磁盘合同 | cap 17,179,869,184 B；投影新文件 11,683,674,525 B；累计 11,886,541,965 B；准入时剩余 2,027,809,583,104 B，投影后 2,016,125,908,579 B；free-space floor 2,147,483,648 B | measured admission；[V3 compact](b0_v3_full_action_failure_20261019.json) |
| 最终运行身份 | attempt 20261019T053402.514018Z；service myfenics-case-20261019T053359-2096871.service；source afbe91e5947ed18fb74d7105097e129c1b8b4cc7；状态 WORKER_FAILED，official_result=false | measured receipt；[run index](run_index.json) |
| 首次 8 GiB attempt | attempt 20261019T025658.545020Z；source 1366d64b8479139355e70897392f9bfed18347a9；旧 cap 8,589,934,592 B，预测 11,882,448,300 B，恢复见证未运行 | 已有资源停止记录；本次没有重读旧目录或服务 |
| 固定窗口 | T0 2026-10-19T05:23:07.094241922Z；总计 86,400 s、数值 85,200 s、收口 1,200 s；最后 watchdog 样本后余额分别约 72,641.876 s 与 71,441.876 s | measured cumulative + derived remainder；不是当前余额 |

### 已知输入 RHS recovery

Recovery 的 forward relative error 限值为 1e-11，native volume residual relative 限值为 1e-10，每列最多 3 次同 LU 校正。两列初次 forward 相对误差分别为 2.0454083899234283e-11 和 2.0406316710458895e-11，高于门限；各自 native residual 初值都远低于 1e-10。按合同完成三次同 LU 修正后，最终 forward 相对误差为 8.452404647964512e-14 和 8.462099738746788e-14，最终 native residual 相对值为 5.198444248297799e-16 和 5.177707803722003e-16。两列 trace identity 与 slave-zero 都通过，saved recovery manifest 状态为 PASS。这个 PASS 限定于已保存的 recovery witness。

### two-input full action

| 检查项 | top / mode 16030 | bottom / mode 48090 | 原门限 / 结论 |
|---|---:|---:|---|
| p6 action 对 native reduced RHS 相对误差 | 3.042118678294192e-10 | 6.391893878204816e-10 | 每列 1e-11；两列 FAIL |
| 已保存向量独立 NumPy 重算 | 3.0421186782950535e-10 | 6.3918938782065652e-10 | 与运行门只差浮点求和顺序；确认失败 |
| D 相对误差 | 0.0 | 0.0 | 限值 1e-11；PASS |
| 输入数组与 full action 输出 | 形状 (5,752,120, 2)，各 184,067,968 B | 端口 RHS (64,120,2)，2,051,968 B | 数组身份和逐文件 SHA-256 见 [saved-vector index](b0_v3_saved_vector_hash_index_20261019.json) |

因此 recovery 的 PASS 没有关闭 full-action gate。现有数组重算复现了误差，但不能定位其源码或数值根因；不归因于 LU、MPC、行映射或浮点舍入。offline checker 调用遇到 PETSc signal 11 / MPI_Abort 59，没有输出报告，状态为 INCONCLUSIVE_SIGSEGV，不能计作 checker PASS，也没有据此宣称代码缺陷。

### 成本、资源、未运行项与决定

| 指标 / 项目 | 数值或状态 | 数据身份 / 范围 |
|---|---|---|
| 父 workflow | 13,102.74539181916 s；watchdog parent 13,102.588685457129 s | measured；不同计时口径分开记录 |
| saved surface application | 64,120/64,120；3,961.9574313424528 s | measured 子计时；包含在父计时内，不叠加 |
| process-tree RSS peak / task cgroup peak | 14,523,883,520 B / 23,537,336,320 B | measured，不混作同一峰值口径 |
| task swap / 清场 | peak/current 0 B；descendants cleared；无剩余 child PID | measured |
| resource/time gates | 均未触发 | measured；运行因 full-action 数值门结束 |
| q CSR、q factor、KSP/FGMRES、完整场、独立 A6 | NOT_RUN | 当前 full action 不合格，未进入这些阶段 |
| official R/T/A、A_volume、2 TB / 48 h | NOT_RUN / 未资格化 | 没有 official field |
| root cause / ordinary default / master | 根因未闭合；default 未变；不合并 | 结果决策 |

在最后 watchdog 样本 2026-10-19T09:12:25.213291Z 时，总窗口派生剩余约 72,641.876 s，数值窗口约 71,441.876 s；这是当时余量，不是当前余额。宿主全局 swapin/out 差值为 177/0 页，无法归因到任务，归因保持 UNKNOWN。所有 141 个 manifest-listed .npy 共 9,379,882,344 B，逐文件大小和 SHA-256 与 recovery manifest 一致；见 [hash index](b0_v3_saved_vector_hash_index_20261019.json)。主证据和各 event SHA 见 [V3 compact](b0_v3_full_action_failure_20261019.json)。

下一断点是由主控审阅已保存 recovery/full-action 向量并给出可证伪诊断；在失败根因和后续合同重新冻结前，不继续 q/factor/solve，不降低门限、不增加校正次数、不重跑 PDE。16 GiB 配额只解决本次 raw-evidence admission，不构成数值资格。详细逐项回应见 [response_v3.md](../response_v3.md)。

## Task41 P0 Review V4：volume-only 几何归因仍未关闭 full-action 门（2026-10-20）

V4 继续保留 V3 的真实数值失败：two-input full-action relative errors 仍为 `3.042118678294192e-10` 和 `6.391893878204816e-10`，高于未改变的 `1e-11`；`official_result=false`。这轮完成了保存数组审核、三类 volume-only 数据提取以及一对 cell 的 actual/canonical 几何对照，但没有进行全域 action requalification，也没有启动 200q、factor、KSP/FGMRES 或完整场。

| 阶段 / 身份 | 方法与实测 | 结论 / 边界 | 证据 |
|---|---|---|---|
| required saved-evidence checker；geometry consumer source `02523b3d…` | 报告 `audit_completed=true`、`data_integrity=true`、`recovery_passed=true`；重算保留 `joint_action_passed=false`、`official_result=false` | checker 完成；不把恢复通过等同 full-action 通过 | [V4 saved-audit report](b0_v4_volume_only_attribution_20261020.json)；外部 report SHA `427af9ffb5f41a129250a513eaa908c13efe79ac10d2bbf5468d1a69fa0113b8` |
| volume-only extraction；consumer source `d883c1f…`、contract SHA `9012ffc0…` | 28,000 owned cells、3 canonical local classes，保存体积块和所需 maps `1,299,043,104 B`；service 父 `1,638.8259056420065 s`，worker 子 `1,571.1404369487427 s` | 不重扫 surface modes、不建 global q factor；子时间已含于父时间 | 外部 report SHA `09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5`，见 [V4 compact](b0_v4_volume_only_attribution_20261020.json) |
| geometry-pair probe；source `02523b3d…` | cells 26762/26897 共用 canonical key `(1, 5.5, 0.25, 10.0, 0)`；42 arrays、`49,929,712 B`；worker `235.811 s`，service 父 `306.000 s` | selected-pair attribution only；不能外推为 full-domain gate | 外部 report SHA `a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031` |
| saved-only local elimination | canonical fresh K/G/J/L and T/S exactly match saved class; actual blocks differ from canonical by `9.37e-16`–`1.22e-15` relative. On active row 5458716, canonical q reproduces old d within `3.64e-12`; actual q norms are `6.04e-10` and `1.04e-9` | Coordinate-dependent floating path is a supported local contributor; actual q remains nonzero and this is not a full action pass | [V4 attribution compact](b0_v4_volume_only_attribution_20261020.json) |
| full-action error decomposition | 原分母 `2225.481253487629` / `2225.4807123031883`；trace L2 `6.770178089430243e-7` / `1.4225036541037616e-6`；port差异两列均精确为 `0` | 保存分解把差异定位到 trace rows；原 worker full-action 门仍失败 | [V4 attribution compact](b0_v4_volume_only_attribution_20261020.json) |
| cache-sharing feasibility | existing actual-coordinate records include only the selected pair; full 28,000-cell exact-coordinate key count was not saved. A hypothetical per-cell T/R/S/LU/pivots cache is at most about `348,560,352,000 B` (`324.6 GiB`) from the stored class payload estimate | derived worst case, not measured; do not assume 28,000 actual keys or adopt per-cell caching without a separate gate | [V4 attribution compact](b0_v4_volume_only_attribution_20261020.json) |
| next stages | global action requalification, q200/factor/KSP/FGMRES/full field/A6/R/T/A | `NOT_RUN`; original full-action gate remains failed | [run index](run_index.json) |

The first local diagnostic output is preserved but invalid because it subtracted the already global `b_t` once per cell; its SHA-256 is `b9dd5bf9b5dd906fa3dcd7485e11190101067fe2f552caed92f9e96f5046a955`. The corrected saved-only script adds `b_t` once, takes 5.046 s, has no RSS sample, and does not rebuild a mesh/carrier, scan ports, change a threshold, or form a global q factor. Neither report is used to edit the saved V3 d vector.

No safe full-domain production fix is established by two cells. The next bounded step is to freeze one candidate interface that aligns production volume geometry semantics with an independent native volume action, then requalify both complete columns using the saved input/RHS and original denominator and limit. Do not add actual coordinates to every cache key by default, claim a global pass, or resume a solver stage before that gate closes. Full response, exact identities, costs, limitations and resource scope are in [response_v4.md](../response_v4.md).
*** End of File

## Task41extra Review V5：actual-key 清点完成，完整候选受固定时间门拒绝（2026-10-20）

本轮唯一候选为 mesh_actual_exact：rank-2 局部张量直接使用原 mesh coordinate dofs；同一张量进入局部 LU 和 R/T/S。这样做是让生产凝聚路径使用与 native 作用相同的真实几何坐标；代价是旧 3 个 canonical 类扩展为 28,000 个 exact keys。两个工程字段/导入问题修复后，主控冻结 source 179cf7369e6bc5894fa87af6b74cf5c73938b6d4；volume-only worker 完成 inventory 与构建前缀，但 owner 没有完整建成。

| 项目 | 实测或推导 | 资格边界 |
|---|---|---|
| exact-key inventory | raw/oriented 各 28,000 个 key；清单 16,224,652 B，SHA-256 147ab6347e6b0059ea97627a48802a970e8450d20e832a716bcd60d95233c | 实际键数清点，不表示 28,000 份数值块已分配 |
| 两格 actual 对照 | cells 26762/26897 的坐标及 K/G/J/L 块均 bitwise_equal=true；参考报告 SHA-256 a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031 | 局部重放通过；不等于全域 two-column action 通过 |
| 8 项 prefix | kernel 总计 419.1692760037258 s，均值 52.39615950046573 s，范围 51.93273649–52.97407951 s | cache-miss 实测；其他 phase 独立记录，不把父服务时间归为 kernel |
| 时间准入 | 余量 712.8634632226167 s；剩余 class-build 上界 1,488,176.122617107 s；含 1,803 s post-build parent reserve 和 300 s termination reserve 后需 1,490,279.122617107 s；缺口 1,489,566.2591538844 s | CANDIDATE_NOT_ADMITTED；不是数值门失败 |
| 完整对象内存 | retained numeric 上界 348,561,972,000 B；metadata 上界 53,760,000 B；condensation/key 上界 348,615,732,000 B | derived projection；全域候选没有构建，因此 full-candidate peak NOT_MEASURED |
| 本次已运行阶段资源 | tree RSS peak 6,674,780,160 B；task-cgroup peak 6,830,514,176 B；tree/cgroup swap 0；host pswpin/out delta 0；PSS null；后代已清场 | 仅 inventory/prefix attempt，不能外推为 full candidate peak |
| 后续数值阶段 | 全域两列、checker、200q、factor、KSP/FGMRES、完整场、A6、R/T/A | NOT_RUN；V3 full-action FAIL 与 V4 saved-audit 结论原样保留 |

三次正式 service parent 总计 622.824231967 s；准备和入口费用没有同口径的合格计时，记 UNKNOWN。各次 source、失败/准入分类、watchdog 子段与 raw receipt hash 见 [V5 response](../response_v5.md)、[V5 compact](b0_v5_mesh_actual_exact_not_admitted_20261020.json) 和 [run index](run_index.json)。16 GiB 证据上限、2 GiB free-space floor、1.5 TiB task cap、64 GiB host reserve、task swap 0、数值阈值和 T0 均未更改；没有新窗口或重跑 V5。 补充 component/documentation validation 原始结果为32通过、3失败；主控复核后仅修正三个测试替身，三项定向重跑3通过（0.90 s），production source未改；修复前负记录与 fixture差异见 test_summary。主控已核验17个本地原件的路径/bytes/SHA，属于证据完整性核验，不是candidate checker。
