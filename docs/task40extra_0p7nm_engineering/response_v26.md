# Task40extra Review V26 执行回应

**结论：selected q0 保存流消费者与完整结构位置检查通过；CSR 在实时内存准入门前受控停止，没有分配或数值填充。** worker exit 0 代表受监督 stage 正常停收，不代表求解成功。partial checker 26/26 项为真，且 `full_pass=false`；全 q、因子、KSP、PDE 与 official R/T/A 均未运行。

## 模型与冻结身份

Task40 的 parent target 是 `50×25×140 nm`、波长 `0.7 nm` 的非分离三维 Si/air Maxwell 模型，目标网格 `272×8×14=30,464` 个 p6 单元，含 x/y Floquet 周期与 z 向 Fourier-DtN 端口。q 是 y 周期相位子问题。

本轮 q0/q4 保存消费者和行结构实际使用去掉 notch/void 的 regular reference：`272×2×14=7,616` 个单元，每个 q 有 `773,568` trace rows，q0/q4 alias 分别为 `4,076/3,856`。record 中的 `physical_model_sha256=ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241` 绑定 parent target 身份；它不证明该 q0 stage 重新装配了完整 target。V26 仅完成 q0 消费者、q0 结构和 q4 配对对角/双向 leakage 检查，不是 Ny=8 全解。

最终冻结源码 `f9093c87f81d52b75fbc156e562b3745df45ccf4`；本轮输入 SHA-256 `134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b`；campaign window SHA-256 `ac533aaf3946c82fde961c77f002ff1b1b2a61401f2153507ff9462d472bc7f5`。运行采用已资格化 WSL ABI：PETSc complex128/int32、MPI1。

q0/q4 保存 producer 仍绑定旧 source `9d0f4dbfc730dd620b709d048e33e9da6c77520c`。其原始 `input_original.dat` 的真实 SHA-256 为 `7c7fcc172968bb291d6834bac6c4f2d3b71b3f1a1efb836129f5dfb872082407`，已独立复算并与 `input_sha256.txt` 相符。旧 legacy index 中长度 62 的畸形输入字段保留原样，但不作为实际文件 hash。旧 producer 的失败分类和原始记录均未覆盖。

## 保存流消费者结果

V26 从既有完整 producer 数据重载两组不同非零 q0 输入，与本批 09:36 attempt 保存的 hash-bound native 输出做只读比较；surface integrator 没有重跑。q0 两组 replay 相对误差为 `1.9111641039085683e-14` 和 `1.9037676533525363e-14`；volume 分量为 `1.9111718756701163e-14`；C、−D、Hhat 分量误差为 0。q4 对角相对误差为 `1.892511654260487e-14`。

| 跨 q 方向 | 泄漏比 | 对角响应尺度归一化误差 | 限值 | 结果 |
|---|---:|---:|---:|---|
| q0→q4 | `2.407288081764573e-16` | `3.313929355217115e-16` | `1e-11` | 通过 |
| q4→q0 | `2.3258027571170525e-16` | `3.273401604609453e-16` | `1e-11` | 通过 |

理论为零的跨 q 输出自身接近零；相对该极小输出的未缩放误差约为 1.25，不是判定门。按 review 规定以非零对角响应作尺度归一化后，两个方向均低于 `1e-11`。

本批第二个 V26 attempt（source `3a61e61caf638678d483b6fa06f36374abeef67d`）实际执行并保存了三组 native case；最终 attempt 没有重复 native action，而是对这批已保存结果做只读 recovery，状态为 `PASS_READONLY_THREE_CASE_RECOVERY`。第二 attempt 在结果记录遇到 `KeyError: minus_D`（live component key 实为 `-D`）后，没有持久化实测 native volume apply 数、provider sweep 数或 native 用时，分别记作 `NOT_RECORDED`、`NOT_RECORDED` 和 `UNKNOWN_NOT_PERSISTED_BEFORE_KEYERROR`。从该 source 静态派生的计数 6 和 9 不是实测值；缺失值不表示零调用或零秒。

## q0 结构和 CSR 资源 Gate

记录的是 CSR 预分配所需的**结构位置数**，不是已经填入的数值非零。regular reference 的 q0 增广块为 `777,644×777,644`，结构位置数 `577,061,168`。完整 `777,644` 个 int64 row counts 与 `777,645` 个 int64 wide offsets 校验一致，offset 末值等于结构位置数，相关数组哈希均通过回读。该结构计数可用 PETSc int32 索引；**数值 CSR 未构造**。按 int32 索引和 complex128 数值估计，纯 CSR payload 为 `11,544,333,940 B`，准入额外对象上界为 `11,570,765,788 B`。

| 准入口径 | 当时可供新增对象的空间 | 额外上界 | 缺口 | Gate |
|---|---:|---:|---:|---|
| host / 动态 process-tree | `4,833,513,472 B`（已扣 `134,217,728 B` 证据余量） | `11,570,765,788 B` | `6,737,252,316 B` | 未通过 |
| 专用 task cgroup | `4,996,231,168 B` | `11,570,765,788 B` | `6,574,534,620 B` | 未通过 |
| 磁盘 | 满足本阶段 reserve 后门限 | — | — | 通过 |
| 专用 task swap | `0 B` | 要求为 0 | `0 B` | 通过 |

两个内存缺口来自不同资源口径，**不能相加**。stage 在 `task40_v17_q_row_tile_csr_materialize/p0q0` 分配前以 `LIVE_RESOURCE_ADMISSION_BLOCKED` 受控停止。这不是矩阵数值失败，也不是求解器失败。CSR、factor、KSP、q4/其他 q CSR、PDE 和 official R/T/A 均 `NOT_RUN`。

## 时间、资源与保留的失败记录

最终服务为 `myfenics-case-20261011T110928-2306938.service`，InvocationID `64c3b109594c47f4bd7c756844bc80c4`，worker PID `2307069`；run_id `task40extra_0p7nm_target_original_ny8_operator_probe_v22`，attempt `20261011T111053.208174Z`。服务结束为 inactive，worker exit 0，partial checker 为 `PARTIAL_RECEIPT_CHECKED`，`full_pass=false`；worker 和 checker 后代都已清除。

| 时间口径 | 实测值 | 关系 |
|---|---:|---|
| q0 stage parent | `2352.2791069909 s` | 包含该 stage 子工作 |
| CSR 结构/准入 parent | `1556.4472410220187 s` | 嵌套在 q0 stage 内，不能再加一次 |
| worker watchdog monotonic | `2410.699863158865 s` | worker watchdog 生命周期 |
| run summary full workflow monotonic | `2410.891193368938 s` | receipt 自身的 worker 口径 |
| run summary conservative worker workflow | `2677.5253902958375 s` | worker/run-summary口径，不是 outer 总流程 |
| run_case parent monotonic / conservative | `2411.1156637850218 / 2677.939236291 s` | 一个外层子父区间 |
| required-checker parent monotonic / conservative | `7.356200500857085 / 10.968143618 s` | 与 run_case 分开的父区间 |
| outer nonoverlapping parent chain monotonic / conservative | `2419.7040153259877 / 2690.1395309491086 s` | 从 first recorded outer clock 到 parent finish，含 run_case 和 required-checker；互不重叠的 outer parent intervals 可相加 |
| systemd Starting→Consumed monotonic / UTC | `2497.689304 / 2775.330775 s` | 独立 service 生命周期，不与 outer parent chain 相加 |
| start marker→first outer clock monotonic | `75.95538928802125 s` | 内部归因 `UNKNOWN`；该区间已在 systemd service/campaign 总账内，不重复相加 |

最终 worker 的同时 process-tree RSS peak 为 `11,631,017,984 B`，专用 task cgroup memory peak 为 `12,059,959,296 B`，task swap 为 `0 B`。checker 自身 process-tree RSS peak 为 `911,728,640 B`；checker 与 worker 峰值属于不同生命周期，不相加。WSL 全局 swap 计数增加 `164` 页 in、`3,489` 页 out，是宿主级诊断，不能归因给本 task。host/tree 与 cgroup 的 CSR 缺口分别报告，也不能互相相加。

campaign 固定窗口 T0 为 `2026-10-11T07:10:58Z`，数值截止 `12:50:58Z`，总截止 `13:10:58Z`。required-checker supervision receipt 中 `campaign_closeout_reserve_seconds=600` 是旧 profile 标签；有效 window、campaign API 与 watchdog 使用 1,200 秒 reserve 和 20,400 秒数值 cutoff。主控在文档收口前读取到账本累计 `17,830.555934262644 s`、数值余量 `2,569.444065737356 s`；不可变前缀为 `19,597,736 B`，SHA-256 `5003d6deb26f0f6838778651bd7cf5595dfce874b8797d112dde6af30ac8b01a`。该快照未计入其后的文档收口、提交、推送与回读成本；后续成本继续追加到同一账本，不重置窗口。

V26 的早期 attempts 也原样保留：

- `20261011T085201.909343Z`：saved replay 已完成；随后整个 `task40_v25_selected_q0_pre_fe_and_surface_phase` 阶段因 `8,589,934,592 B` 的额外对象预留准入门未通过而停止，FE/surface phase 未启动。这是整阶段 pre-FE admission，不是第二个 CSR materialization Gate。原 partial checker 同时因 replay identity/inventory binding 缺失而失败；两项负结果均保留。
- `20261011T093646.477018Z`：本批 V26 的三组 native case 已实际执行并保存；随后记录代码访问 `minus_D`、而 live component key 为 `-D`，触发 `KeyError`。worker 失败分类保留，实测计数和 native 用时没有持久化。最终 attempt 对这三组已保存结果只读复用，没有重复 native action。
- 最终 attempt 修正 binding 后完成消费者和结构回读，再在真实资源 Gate 停止。V25 PETSc SEGV、序列化失败与 saved-data recovery 继续保留在原始记录中。

## 检查结果和下一步

测试按 source 分开记录：初始 source `5f47bd3f491b4bf485a5caca55da6cb61d8508c5` 定向组 11 passed、compileall 通过；中间 source `3a61e61caf638678d483b6fa06f36374abeef67d` 定向组 6 passed；执行者在最终冻结 source/diff `f9093c87f81d52b75fbc156e562b3745df45ccf4` 上、冻结前对应回执中报告 80 passed、1 skipped，主控认可该回执，并另行运行 resource-stop actual readback fixture（1 passed）。本轮在最终 source 上重跑 focused 组 22 passed in 0.58 s，文档合同 29 passed。独立 partial checker 26/26 项为真，但 `full_pass=false`，它核验的是部分 receipt 和受控停止，不是 PDE pass。详情见 [test summary](outcomes/test_summary.md)。

V26 授权范围完成到 regular-reference q0 保存流消费者与完整行结构。下一步由 Task40 主控在新的审查窗口内复用已保存的 q0 replay、row-count/offset checkpoint 和 partial receipt；先证明新环境可同时提供 `11,570,765,788 B` 额外对象上界及证据余量，再重评 CSR admission。只有 host/tree/cgroup 门都通过后，才构造 q0 CSR 并考虑条件性单 q factor 生命周期；无需重做 producer FE。完整 8-q、完整 target PDE、official R/T/A 与 2 TB/48 h 仍 `NOT_QUALIFIED`。本轮没有改变 ordinary default，也没有提交或推送。

机器记录见 [V26 operator compact](outcomes/records/target_operator_probe_v26.json)、[V26 time/resource ledger](outcomes/records/time_resource_accounting_v26.json)、[V26 incremental workflow ledger](outcomes/records/review_v26_incremental_workflow_ledger.json) 和 [V26 run index](outcomes/records/run_index.json)。主控最终科学回读 SHA-256 为 `ed7bb73f32be3adedd3ce3f1294a63370a2cf7f6ca968264b56e9c0a1e4411bb`。
