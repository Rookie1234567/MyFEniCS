# Task40extra Review V25 执行回应

**结论：V25 完整原尺寸体积作用已由保存数据恢复并通过独立回读；selected-reference-q0 的完整消费者未完成，真实 worker 以 PETSc SIGSEGV 失败。** 已修复一个与崩溃相符的 PETSc 向量所有权错误并通过定向测试，但修复后没有重新运行 native operator，因此不把该次 q0 运行或 ownership 修复写成数值通过。完整求解器、全 q、PDE、官方 R/T/A、2 TB/48 h 仍未资格化。

## 实际科学结果

| 主线 | 实际结果 | 能支持的结论 | 未完成项 |
|---|---|---|---|
| 完整 target volume | `RECOVERED_SAVED_WITNESS_PASS`；以原始保存数据做 post-process，没有重跑 FE。覆盖 30,464 cells、29 个唯一 raw tensor class、60 个有方向 Schur class；6,188,544 active trace rows、20,181,348 full storage rows、284,004 MPC slave rows。 | 两组完整域 volume action、MPC-dual RHS、恢复和 native residual 见证通过；独立 saved-witness checker 11/11 条件为真。case 0 residual 相对值 `6.0913e-14`、action/RHS 误差 `2.8919e-14`、恢复前向误差 `2.0242e-12`。case 1 action/RHS 误差 `1.61698e-13`；首次恢复误差 `1.6168e-11` 超过 `1e-11` 限值；复用同一 LU 做一次修正后为 `1.2502e-13`，native residual `1.4135e-15`，通过。 | 这是 S-only 体积与恢复，不含完整 A6、q 矩阵、factor、KSP、PDE 或官方结果。原始 worker 的首次失败仍保留。 |
| selected reference q0 producer | frozen source `9d0f4dbfc730dd620b709d048e33e9da6c77520c` 已写出 11,230,840,064 B surface functional stream、226,645,122 B volume-class stream、local H、original-to-active 映射及 q0/q4 maps。全部原始数据 hash 列在 [V25 operator compact](outcomes/records/target_operator_probe_v25.json) 和 ignored run 中的 failure artifact index。 | 完整 producer 数据已落盘，可以保留作后续恢复的输入。当前 probe 对应 q0 与配对 q4 reference branch。 | 在持久化 stream consumer replay 及 native 对照输出前发生 SIGSEGV；没有 complete-stream manifest、两组 replay 输出或 native witness。故完整行列/端口数值消费者、双侧 q 投影、CSR 和 native qualification 均未通过或未运行。 |

保存数据恢复不是新的一次 FE 运行。首次完整体积尝试曾因 class coverage 字段不匹配而以 `ValueError` 失败；第二次正式 worker 在两组科学向量已保存后遇到 `mappingproxy` 序列化失败；首次保存数据恢复又因缺少 NumPy 导入失败。两项失败均留档；只对已保存 witness 做修复后的读取和独立验证，没有覆盖原 run 的失败分类。完整记录和原始 hash 见 [V25 operator compact](outcomes/records/target_operator_probe_v25.json) 与主控 [independent audit](../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_v25_wsl/main_result_audit_v25.json)。

q0 worker 的首个可见 native 错误为 PETSc signal 11（SEGV），随后 MPI rank 0 以 code 59 abort。主控定位到 `_native_volume_apply` 销毁了由 `FullspaceSplitVolumeAction.apply` 持有并跨调用复用的输出 Vec。修复现在复制数值并仅销毁本函数创建的 source Vec。该 ownership bug 与崩溃相符，但 worker 没有 native stack trace，不能声称已证明它是唯一触发点。冻结修复源码为 `ed83343df52f7c46df52d9daf4e4a3a28c8cdb5b`；其测试没有重新完成 q0 native qualification。

没有安全的现成命令可从本次 ignored run 单独恢复并受监督地调用 persisted consumer；consumer 私有 helper 仍需绑定 frozen mode selection、实际 alias/row identity 和原生参考 action。数值剩余窗口不足以另建恢复入口或重做 FE/11.23 GB stream，因此恢复 replay 与 native witness 均记 `NOT_RUN`。下一步应在现有监督路径中提供一个只读 saved-stream consumer route，明确绑定原 run source 与新的 replay source；先完成两组不同非零输入的 stream readback，再以独立 native action 建立对照。不得用 stream 自己产生的输出充当 native 参考。

## 时间与资源

V25 固定窗口没有刷新：T0 为 `2026-10-11T00:38:41Z`，数值 cutoff 为 `06:18:41Z`，总截止为 `06:38:41Z`，campaign window SHA-256 为 `a8ee7ab9970ece892d85f9313180438e88561f0bfc63b68acdb11f536400def7`。最后一次 q0 watchdog_end 记录为 sequence 14616、累计 `19398.5879813012 s / 20400 s`，该样本时剩余 `1001.4120186988 s`；这只是 worker-end 的账面快照，不含之后的结项时间。

q0 worker watchdog monotonic elapsed 为 `1281.4088 s`，campaign conservative workflow elapsed 为 `1422.1191 s`，time gate 上限 `2429.3084 s` 且通过。process-tree 同时 RSS 峰为 `11,709,558,784 B`；专用 cgroup memory peak 为 `13,548,032,000 / 17,179,869,184 B`。专用 task cgroup swap 峰值为 0，zero-swap gate 通过。WSL 全局 swap 计数增加 1,087 页入、15,780 页出；这是 host-wide 诊断，不能归因于本任务。watchdog 曾记录 `warning=true`，但没有 stop event，结束分类仍为 `WORKER_FAILED`；所有 descendants 已清理。两种内存峰值、task swap 与全局 swap 分开记账，详见 [V25 time/resource ledger](outcomes/records/time_resource_accounting_v25.json)。

## 测试与边界

ownership 修复的定向 q0 文件测试为 **11 passed**；`compileall` 与 `git diff --check` 通过。Ruff 未安装，因此 `NOT_RUN`。保存体积 checker 的 11/11 是原始 saved-witness 数据回读，不是完整 PDE；更广 route suite 为 17 项通过。另一组宽测试记录 74 passed、1 skipped、6 failed；失败来自已过期 campaign fixture 和缺失 `closeout_seconds`，保留为 fixture/合同负结果，不记作回归通过。全仓 pytest、MPI2/4、CI、q0 fresh native、完整 q CSR、factor、KSP、PDE 与 R/T/A 均 `NOT_RUN`。

本轮仅覆盖 V25 指定的原尺寸体积与 q0 研究入口。无 2 TB / 48 h 能力结论，不推进 production default，也不合并 master；由主控按 Task40 规则统一提交和推送。


## 完整父区间和保留的失败

下表分开列完整运行父区间；不能将生成、native 见证、文件保存和子调用相加当成另一份总时间。旧父阶段细分没有成功保存的保持 UNKNOWN。

| 范围 | watchdog 单调钟 / 保守全流程 | 同时整树 RSS / cgroup peak | 边界 |
|---|---|---|---|
| 完整体积第二次运行 | 1804.2103085159324 / 1990.0629695745781 s | 7,449,296,896 / 11,029,651,456 B | 两组完整向量已保存；随后收据写出失败。任务 swap=0；宿主页入+1、页出0。 |
| q0 最新运行 | 1281.4087936370634 / 1422.1191073599744 s | 11,709,558,784 / 13,548,032,000 B | producer 完成后 SEGV，非时间或资源停止；consumer/native 未完成。 |

完整体积采用独立原生 volume callback 冻结 RHS：返回借用 buffer 后先复制，保持 slave-zero storage，`rhs_is_mpc_dual=True`、`expand_trace=False`，没有由候选 S 生成 RHS。第二组包含全部 30,464 cells 的非零内部状态及内部 RHS。体积 class build、maps、packing、各次作用/恢复与文件输出的完整互斥子计时未成功保全，暂不猜测热点。

| attempt 时间目录 | 实际终态 |
|---|---|
| 20261011T021931.764590Z | coverage 读取字段错误；ValueError，未取得完整见证。 |
| 20261011T024026.570042Z | 科学见证已保存，mappingproxy 写出失败；原 WORKER_FAILED 保留。 |
| saved recovery 20261011T033232.003722Z | checker 缺 NumPy 导入；仅保存数据读回失败。 |
| saved recovery 20261011T033624.351783Z | 复用原始数据恢复，独立 checker 通过；未重跑 FE。 |
| 20261011T044935.108281Z | 四字段 ordered-key digest 与附 original-index 表示混用；入口 ValueError。 |
| 20261011T045836.730136Z | degree160 巨型 FFCx 面表编译触发 RESOURCE_CONTROLLED_STOP；单调钟156.6194014530629 s，整树13,439,320,064 B、cgroup13,480,509,440 B，task swap0；宿主页入+71、页出+16,023。保留原失败，后续采用有界已有积分见证，没有降低积分规则。 |
| 20261011T053811.673002Z | 保存两类全流及映射后 PETSc SEGV；ownership 修复仅经定向测试。 |

截至主控收口快照 sequence14617，累计收费 **20674.0876186442 s**，数值余额为0；固定总窗当时剩余925.9123813558 s。这覆盖此前实现、测试、等待和运行，后续审校、提交、推送仍在同一窗口计费。不可变账本前缀16,875,657 B、SHA-256 `fcfc08881b123a80961c7fe7704af5f9f6c46f3939475a56d9976edc9b7bf972`；快照收据 SHA-256 `704c0b63f1feae3873d03602422d9401652fc7c81074f6aecac596a101733fc4`。旧窗口费用及未知准备成本未清零。

q0 的冻结结构库存为773,568 trace rows、4,076 port aliases，对应增广777,644×777,644；配对q4保留3,856 aliases。这些是映射/结构信息，**不是完整数值消费者通过**。当前仅保存 regular-reference 的完整 producer streams，完整CSR、两输入重放和独立原生作用未完成，solve-ready=false。新存储策略每次 PC 可能重复 conversion、symbolic、numeric、fresh probe、solve 和 eviction，初始化还需全部q的symbolic preflight；以上原尺寸实测成本、真实迭代数、最大单q因子填充、冷JIT及完整恢复/输出/checker仍缺，因此不能由小模型三次迭代或32模式缓存倍数推算48小时。
