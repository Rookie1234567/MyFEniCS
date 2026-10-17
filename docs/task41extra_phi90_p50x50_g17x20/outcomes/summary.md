# Task41 阶段结果

本任务使用完整三维有限元，计算居中 17×20×120 nm Si 主体及 10 nm Si 基底。单胞横向为 50×50 nm，上入射掠角 1°、方位角 90°、S 偏振。**主案例没有额外 notch 或 air void。**

A1 用直接分解建立当前网格的比较基准：先在各单元内消去内部未知量，求解保留的边界与端口系统，再恢复全部场。它验证当前离散方程，不证明网格或模式截断已收敛。后续 A2 将用同条件参考预条件迭代解与它比较。

| 阶段 | 实际状态 | 范围与证据 |
|---|---|---|
| A1 首次启动 | FE 前工程失败，保留 | 旧 V29 环境标记误入 Task41；服务 1.563210294 s |
| A1 修复续作 | 完整场及独立 checker PASS | 原窗口续作；1400 单元、p6、168 模式 |
| A2 P0 attempt4 | q0/q5 的完整 CSR 与原生算子资格检查通过；随后 worker 因递归深度异常退出，official_result=false | 全流程未完成；没有完整迭代场、独立 A6 残差或 official R/T/A；0.7 nm 仍 NOT_RUN |
| 0.7 nm | NOT_RUN | A1/A2 通过后按资源门推进 |

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

尚未通过 A1/A2 同离散比较、0.7 nm 工程场、网格/倏逝模式精度及最终 2 TB/48 h 冷流程资格。当前没有 merge approval。

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
