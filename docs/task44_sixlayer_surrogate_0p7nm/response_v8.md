# Task44 执行响应 v8：fresh5 监控证据与残差前快照

## 本轮结论

fresh5 是一次 `global_z` phase-gauge selector 诊断。它完成 27 个六面体、P6、420 个端口模态对应系统的组装、MUMPS 因子分解和线性求解；CPU 邻居监控随后因候选编译进程 `/proc/51758/stat` 返回 `ENOENT` 而受控停止。归档没有保存旧 Gate 对该 PID 目录的后续检查结果，因而无法确认当时确为自然退出竞态。该停止发生在完整真残差和数值结果输出之前，没有 `result.json`、official R/T/A 或完整残差；这不是已证实的数值失败，也不是内存门触发。fresh5 是独立 selector 诊断，不计入正式精度复算预算，计数仍为 `5/12`。

本轮修正 CPU 邻居 Gate：对已归属 Task44 cgroup 的旧进程快照，只有直接 `stat(/proc/PID)` 明确返回 `ENOENT` 才记录为“快照确认已退出”并允许继续；目录仍存在、权限错误、procfs 读取错误及其他身份不确定情况仍按 fail-closed 处理。另增加可选的残差前诊断快照：在构造 matrix-free UFL 完整算子作用前，保存当时的凝聚解与右端、恢复后的完整有限元解、完整右端，以及可获得的凝聚系统 `Ax-b`。这给已完成的因子与线性解留下一份可审阅材料，以便定位后续全算子残差问题；它复制少量诊断向量、消耗少量内存和磁盘，因此默认关闭。预测的整场峰值增量上限为 32 MiB，包含残差临时向量、捕获副本、写入期间同时存活的副本和有界输出缓冲；这不是额外 16 GiB。写入前还会实时读取任务 cgroup 整场用量 `J` 和 host/ancestor 余量，拒绝会越过整场 warning、controlled-stop、cap，或侵占既有 reserve/buffer 的快照。当前 16 GiB 诊断 cap 对应 warning 14.4 GiB、controlled-stop 15.2 GiB、cap 16 GiB；保留 host 384 GiB reserve 与任务 `max(8 GiB, 5% cap)` buffer。快照不是 checkpoint，不能恢复运行，也不代表真残差或 official 结果。

## fresh5 记录

| 项目 | 记录 | 含义 |
|---|---|---|
| 网格和空间 | `3×3×3`，27 个六面体；P6；19,494 个 FE DoF | selector 诊断规模，不是六层精度样本 |
| 约束与凝聚系统 | 1,350 个 Floquet 约束；6,414 行；4,935,930 used NNZ | 静态凝聚先消去单元内部未知量，缩小直接求解系统 |
| 直接因子 | MUMPS 因子 14,236,514 entries | 因子分解已完成 |
| 求解状态 | 线性系统求解完成；矩阵组装 762.830 s，KSP setup 817.162 s，worker 至停止约 877.933 s | 这些时间来自该诊断记录，不包含完整残差 |
| 停止原因 | `/proc/51758/stat` 返回 `ENOENT`；旧记录没有保存之后的直接 PID 目录检查 | 自然退出竞态只是可能解释，不能追认成已确认 |
| 资源 | cgroup memory peak `3,584,311,296 B`；swap `0 B`；停止前内存峰值低于门限 | 不是内存停止；service 已清场 |
| 数值输出 | full true residual、official R/T/A、`result.json` 均未产生 | 不能将线性求解完成写成数值 Gate 通过 |
| 资格计数 | `5/12`，本诊断不计数 | 正式精度复算预算未改变 |

原始文件与逐文件 SHA-256 见 [fresh5 紧凑记录](outcomes/fresh5_controlled_stop_20261031.json)；对应原始目录为 `/tmp/task44-phase-gauge-global-z-fresh5-20261031`。

## 实现边界

- 监控修正只把有直接 `ENOENT` 证据的精确 PID 目录消失视作过期快照。PID 目录仍存在但 `/stat` 缺失、PID 身份变化或任意权限/IO 错误都会留下未验证证据并使 Gate 失败。
- 快照由 `MYFENICS_TASK44_PRE_RESIDUAL_SNAPSHOT=1` 显式启用，默认关闭；`--smoke` 强制关闭。`MYFENICS_TASK44_DIAGNOSTIC_PHASE_GAUGE` 只接受 `global_z` 或 `boundary_plane`，只记录诊断坐标标签；该标签本身不会改变或声称改变弱式、矩阵或边界相位公式。临时 p6 gauge runner 的残差包装器需显式转交快照身份，才会让两种诊断路径实际经过 snapshot hook。
- 快照绑定 run/source/input/物理模型与解析配置身份、网格和 tag 数组、逐 cell DoF 映射、凝聚维度、端口模态和相位信息。目录和文件采用独占创建并保存 hash；身份不完整、实时整场资源 authority 不可读、`J+Δ` 越过既有阈值或 32 MiB 小额 allowance 超限时，在复制向量和启动 UFL 完整残差作用前停止，不写 official 结果。写入成功后立即释放捕获的 `Ax-b` 临时副本；原求解向量只读且不改写。
- 所有快照内容仅供诊断读取。没有新求解器、重启入口或 production default 变化；本轮没有运行 PDE 或 MPI。

## 快照预算和真实 cgroup smoke

fresh5 网格为 27 个六面体、P6，输入向量维度为 6,414 个凝聚行和 19,494 个恢复 FE DoF。按 complex128 字节数计算，四个待保存向量共 829,056 B；残差临时 PETSc 向量、捕获副本及写入期间的第二副本共计 307,872 B；NPZ/manifest 工作缓冲上界 1 MiB。因此这组诊断的预测峰值增量为 **2,185,504 B**（约 2.09 MiB），低于固定的 **32 MiB** 小额 allowance。预算还会随每次实际向量长度重算，不以这个样本估算替代运行时检查。

获准的原生 host owned-service smoke 以 16 GiB `MemoryMax`、零 swap 和单核 affinity 运行了 0.54 s，没有 FE 组装、FFCx/JIT 或 solve。运行中由现有 `cgroup_snapshot` 和 `memory_envelope` 读取 service cgroup 的整场 `J=42,270,720 B`、host 384 GiB reserve、ancestor cgroup 余量和 8 GiB task buffer；小向量快照的 `Δ=1,049,088 B`，故 `J+Δ=43,319,808 B`，低于 14.4 GiB warning、15.2 GiB controlled-stop 和 16 GiB cap。四个 PETSc Vec 与 `reduced Ax-b` 写入、hash 和读回全部一致。随后 PID 136811 (`sleep`, start ticks `341793002`) 自然退出；监控以 Invocation ID `69f1969d75414cbfa077835b3106b6a3` 识别精确 owned service，并将该旧快照分类为 `stale_snapshot_confirmed_gone`，Gate 通过。首个 smoke 只在组装回执时因从 `_unit_facts` 读取不存在的 `main_start_ticks` 键而退出；修正为直接读取仍存活 MainPID 的 `/proc` 身份后，第二次短 smoke 全部通过。两次 service 都由 systemd 清场，未触碰邻任务。

真实 smoke 的轻量结果和哈希记录保存在 `/tmp/task44_owned_snapshot_smoke_20261101.json`；成功 service 为 `task44-sample-snapshot-smoke-20261101-136782.service`。临时 p6 gauge runner 的 fake-call 合同另确认 `global_z` 和 `boundary_plane` 两个 wrapper 都把 snapshot identity 送入原 residual 入口，且发生在后续独立 UFL 审计之前；runner 文件 SHA-256 为 `0685c5948ef6d4c204838075a6c3fb44b8092a68308fa239b25d51705a776fce`，合同结果保存在 `/tmp/task44_gauge_snapshot_wrapper_contract_20261101.json`。标签只登记诊断坐标，未据此声称改变实际弱式或相位公式。

## 验证

测试使用仓库原生 activation：`MYFENICS_NATIVE_COMPLEX_ENV=1`，Python `/home/fenics/Projects/MyFEniCS/.venv/bin/python`，PETSc `complex128` / `int32`，MPI size 1。测试源码从临时 clone 导入，基线 Task44 HEAD 为 `e26e2a6b24fc6c89d637dcb2420bfaff8e2036f7`。

| 检查 | 结果 |
|---|---|
| CPU 邻居 Gate 与残差前快照定向测试 | `41 passed`，1.41 s；命令为 `python -m pytest -q src/test/test_task44_cpu0_neighbor_gate.py src/test/test_task44_pre_residual_snapshot.py` |
| 回归覆盖 | 真实退出竞态、PID 目录仍在但 stat 缺失、PID reuse、权限错误；32 MiB allowance、P6/fresh5 实际 DoF 规模预算、整场 warning 边界与 host/ancestor reserve 拒绝、身份绑定、在 UFL 前写入和失败顺序 |
| 真实 owned-service smoke | 16 GiB cgroup、零 swap、实读 `J` 和 host/ancestor authority、PETSc Vec 写入/读回、短命子进程自然退出；通过，无 FE/JIT/solve |
| 临时 p6 gauge wrapper 合同 | `global_z` 和 `boundary_plane` fake-call forwarding 与事件顺序均通过；未运行有限元或 UFL action |
| Ruff | 新快照模块与新增测试通过；修改文件的 undefined-name 规则通过。`dtn_port_3d.py` 整文件已有 lint 问题，因此不宣称全文件 Ruff 通过 |
| 语法和补充检查 | `py_compile`、启动脚本 `bash -n`、JSON parse、`git diff --check` 均通过 |
| 首次测试结果 | `32 passed, 2 failed`；发现并修复 PermissionError fallback 和测试 fake UFL 边界缺少 `mpc` 的问题，完整记录保留在 compact JSON 指定的日志中 |
| PDE、多 rank MPI、全仓 pytest、CI | 本轮未运行 |

最终定向测试日志 SHA-256 为 `631a9ee4f80a3ff049bdc693723697461436cbf19b22a53f94d327a986993482`；此前首轮失败测试日志 SHA-256 为 `70d83558296d8fb8c3e158d31f3370dadb6f9db1540a934002a4af7fcfdabc00`。真实 smoke 结果 SHA-256 为 `29e5413a1fcb9242f24cab91455d3ac7034bcd3c4acfdbab72f93abdcc8e6a9b`；完整 follow-up 命令、日志路径和静态检查摘要也追加到 fresh5 紧凑记录。

本轮文件仍是基于 Task44 执行分支 HEAD `e26e2a6b24fc6c89d637dcb2420bfaff8e2036f7` 的未提交工作树改动；尚未提交或推送，等待主任务审核。fresh5 原始受控停止保留为负面执行证据，不改写为通过。
