# Task44 执行响应 v1：启动资格与 CPU0 资源阻断

## 当前结论

| 项目 | 状态 | 证据 / 说明 |
|---|---|---|
| 实现分支 | 已提交并推送 | `task44_sixlayer_surrogate_0p7nm`；本轮启动与 smoke 的源码 SHA 为 `ba2b5c49f73682e28b37a8508ec3d8233ea08c3d`，该代码提交已推送至 upstream |
| CPU0/MPI1 ABI 启动路径 | 技术探针通过 | PETSc `complex128` / `int32`、MPI size 1、模块路径及 Task44 runtime controls 已 hash-bound；4 次 `sched_setaffinity` 都请求 `[0]` |
| systemd smoke | `COMPLETED` | 只运行公共 runner 的 `--dry-run`，15.7206 秒，未组装或求解 PDE |
| CPU0 资源 Gate | `not_passed` | Metrology 长期监督进程 PID `3893658`、start ticks `324107938` 仍占有 affinity `[0]`；等候用户对 CPU0 归属的裁决 |
| 正式样本 A | `not_run` | 未启动 PDE；没有数值通过、失败或负结果可报告 |

任务尚未完成。材料模型、A–D 资格、训练数据和 GP 结果仍待继续。

## 本轮改动与验证

Task44 activation 冻结两项任务局部启动设置：`HWLOC_COMPONENTS=-x86` 与 `OMPI_MCA_pml=ob1`。服务 preflight 和正式 service 仅接受精确 CPU0 affinity；service-side ABI probe 必须继承 `[0]`。环境 receipt 会记录这两个 control 值、模块路径、ABI probe exit code 与 facts digest。

可复现检查结果：

- `bash -n scripts/activate_task44_native.sh scripts/start_task44_native_sample.sh`：通过。
- Task44 隔离 runtime probe 与 CPU identity 定向测试：`10 passed`。
- Ruff 对本轮改动的 Task44 service 和测试文件：通过。对共享 launcher 的基础错误检查仍报原有 `src/runners/task038_launcher.py:4853` `Sequence` 未定义；该行不在本轮 diff 中。
- 完整 ABI probe：exit code `0`，PETSc `complex128` / `int32`，Open MPI 4.1.6，MPI size 1；`petsc4py`、`slepc4py`、DOLFINx、Basix 均来自同一 complex ABI 栈。记录的 runtime controls 为 `ob1` 与 `-x86`。
- ABI facts digest 为 `24dd72f71b0281536dfd3428d2a43504d7b9cf7c4c3d6596a08102098487c6bc`；strace SHA-256 为 `36b471168dd4cfc3535237c3e33565fd2b6e727ac3aa9368de8ba29605ff173f`，共记录 4 次 `sched_setaffinity`，每次均请求 `[0]`。该证据只说明探针进程的启动绑定留在其 CPU0 mask 内，不证明 CPU0 可与邻任务共享。
- smoke unit `task44-sample-smoke6.service`：PID `4035653`，start ticks `329933982`，Invocation ID `d26e456333de4851b7b14d481a181c38`，cgroup `/user.slice/user-1000.slice/user@1000.service/app.slice/task44-sample-smoke6.service`，affinity `[0]`。service classification 为 `COMPLETED`，leader exit 0，后代清空，remaining child PID 列表为空，cgroup swap peak 为 0。该 smoke 不产生 PDE 字段或物理结果。

## CPU0 资源冲突与采样误判

宿主快照在 15:25 曾显示 CPU0 忙度 100%。15:29 快照再次记录 CPU0 忙度 21.36%，并列出 PID `3893658`、start ticks `324107938`、affinity `[0]`、cgroup `/user.slice/user-1000.slice/session-4665.scope`。宿主监督侧随后确认该进程名为 `Metrology supervise_authorized_CPU_release_v3`，仍在运行，已持续约 16 小时。它是 CPU0 的长期监督占用；较低 CPU 使用率不等于它释放了 CPU0。

15:31 的 smoke 前采样报告 CPU0 忙度 7.77%、`cpu_affinity_claims=[]`。这份空列表不能作为 CPU0 空闲证据：当时快照脚本以 `taskset -c 8` 启动，因此 `os.sched_getaffinity(0)` 得到的是 `[8]`，而非宿主完整可用 CPU 集；它用 `len(process_affinity) < len(allowed)` 识别窄 affinity，于是单核 `[0]` 进程与单核 `[8]` 采样进程长度相等，被漏掉。此外，进程表的保留条件没有包含低 CPU 用量的 Metrology 监督进程，claim 列表也只收录 Task40 和 Maxwell。15:31 的点时扫描因此形成了错误的“CPU0 可用”结论。

因此，虽然 smoke6 的 service 自身身份、CPU affinity、cgroup 和 swap 记录一致，但无法证明它在 15.72 秒运行期间独占 CPU0；与监督进程短时争用不能排除。该 dry-run 没有执行 PDE，但这次 smoke 的资源记录不能替代正式样本所需的邻任务资源 Gate。

该误判已保留，不回写或覆盖旧 snapshot。临时宿主 snapshot helper 已改为要求真实主机 PID 1 为 systemd、从 PID 1 读取宿主允许 CPU 集，并将所有窄 affinity 进程（含 PID、start ticks、CPU 集和采集原因）纳入 claim，不按 worker 名称或瞬时 CPU 用量过滤。后续宿主准入必须从原生 host 视图执行；Codex sandbox 的 PID namespace 或被 `taskset` 收窄的自身 mask 不可代替宿主邻任务清单。

## 后续边界

CPU0 的技术启动路径已通过 probe 和 dry-run，但其邻任务资源 Gate 未通过。不得停止、迁移或与该监督进程共享 CPU0，也不得把这台机器的 CPU0/MPI1 资格外推到其他 CPU。正式样本 A 保持 `not_run`，等待用户明确裁决 CPU0 资源归属后再继续；此阻断不代表六层物理模型或求解器失败。

## 证据索引

本轮 smoke 使用的源码 SHA 为 `ba2b5c49f73682e28b37a8508ec3d8233ea08c3d`。本轮 ABI、smoke、原始 host snapshots 和邻任务审计均保存在 ignored artifact 目录：

`benchmarks/artifacts/task44_native_services/task44-sample-smoke6.service/`

关键文件包括 `preflight.json`、`service_identity.json`、`startup_affinity_check.json`、`service_summary.json`、`watchdog/resources.jsonl`、`watchdog/worker.log`、`task44-abi-probe-ba2b5c49.json`、`task44-abi-probe-ba2b5c49.strace`、`task44-abi-probe-ba2b5c49-receipt.json` 与 `cpu0_neighbor_conflict_audit.json`。原始采样文件保留为 `task44-qualification-host-snapshot-20261030.json`、`task44-qualification-host-snapshot-20261030-1529.json`、`task44-qualification-host-snapshot-20261030-1530.json`、`task44-qualification-host-snapshot-20261030-1531.json`；文件名中的时刻均为 2026-10-30 UTC。
