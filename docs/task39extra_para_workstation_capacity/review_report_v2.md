# Review V2：运行中进展归档与性能交接

审查日期：2026-09-20。结论：**PASS_FOR_PROGRESS_ARCHIVE_ONLY**。本次批准文档与轻量证据归档，不代表 2 nm 数值、物理或终态资源资格通过，也不批准 master 合并。

后续终态已补审，最新结论见第 5 节；第 1–4 节保留为停止前快照的审查记录。

## 1. 审查对象和运行隔离

审阅 [Response V4](response_v4.md)、[运行快照](outcomes/records/2nm_h1p5_measured_running_snapshot_v1.json)、本任务 summary/run_index 及项目总账/进展的新增内容。快照截至 2026-09-20 01:35:10 UTC，原始 run 为 `20260918T035017.294454Z`，运行源码固定为 `41caf5141493ad6c5d6c518a64ee74fda8d7a7db`。

归档采用同一 canonical bare 登记的独立 detached 文档 worktree。当前计算 worktree 的 HEAD、源码、输入、环境、CPU 绑定及监督配置不随文档提交更新。运行源码 SHA 与后续归档提交 SHA 必须分别报告；允许活动分支在运行期间落后于远端文档提交，不在运行中 pull、reset 或切换。

## 2. 证据核对与解释边界

主控独立核对了 stages.jsonl、run_manifest.json、guard.py 和 guard config.json 的 SHA-256；四项均与 compact 一致。相邻阶段时间由原始 monotonic marker 重算，与记录一致。Si 的复介电常数由所给折射率平方复核一致。

| 内容 | 审查结论 |
|---|---|
| p4 symbolic | 实际 INFOG(1)=0、INFOG(7)=4；确认成功，不能仅凭 complete marker 判断 |
| numeric 调用计数 | symbolic 时保存的 numeric_calls=0/solve_calls=0 只描述当时；当前 numeric 调用尚未返回，完成后计数才更新 |
| 进程与线程 | root/MPI/worker 是三个进程；worker 内实际观测 3 个 OS 线程，数学库配置线程数为 1 |
| 资源口径 | 末次整树 RSS 和 guard 接管后峰值分别说明；未聚合全程/分阶段峰值，不提前宣称 RESOURCE_PASS |
| 数值与物理 | 尚无本轮外迭代、完整真残差或 R/T/A；原门限保留 |
| 历史 | 5 nm 监督断档及 2 nm 历次失败继续保留，后续成功不能追溯覆盖 |

Response V4 和 compact 已按上述口径修正。提交前须将 outcomes/summary.md 中残留的“OS 线程观测为 root/MPI/worker 三个实体”同步改为三个进程、worker 内 3 个 OS 线程；只修改这一措辞，不扩大实现范围。

## 3. 性能交接判断

现有实测中，H6 setup 约 9.44 小时、p4 体装配约 29.33 小时；当前仍受单 MPI rank、数学库线程 1、CPU23、跨 NUMA 内存访问和全局 p4 因子路径共同影响，不能仅凭这些配置断言各项成本占比。

“34.36 天”来自假定迭代数相同、每步成本按网格单元数线性增长；“22.52 小时 LU”来自假定与 5 nm 相同运算吞吐。两者均缺少本轮完成后的实测支持，不作为确定 ETA。用户明确不能接受该工期，应将实测热点、单步成本、并行化可能性及粗层因子成本交后续 ChatGPT 评估；本归档不实施新的算法、MPI 配置或资源 Gate 变更。

## 4. 提交放行

上述 summary 措辞同步后，允许执行专用完成 JSON/链接/表格及 git diff 检查，将本次文档和本审查记录正常提交并推送 `HEAD:refs/heads/task39extra_para_workstation_capacity`。不得强推，不向其他分支写入，不上传矩阵、因子、缓存或全量资源日志。推送后核实完整远端 SHA、文档渲染和原 worker PID/start_ticks 仍匹配；无需增加用户确认或运行任何 PDE 测试。

归档的后续用途是性能讨论；当前有限元继续在既有监督和已授权资源门限下运行。

## 5. 后续终态补审：全局换页归因未决

同一 run 于 2026-09-20 04:46:37 UTC 触发原 watchdog 的 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`，04:47:15 UTC 完成收尾，exit=-9、descendants_cleared=true。接受 [终态 compact](outcomes/records/2nm_h1p5_measured_terminal_snapshot_v1.json) 的负结果分类；不自动重跑，不宣称 LU、outer 或物理 Gate 通过。

主控独立核对 run_summary、watchdog summary、stages、guard status/events 五个原始小文件哈希，并只读检查了 resources.jsonl 的末尾 4 MiB。首次停止样本记录全局 pswpout 从 2 到 73 页，任务树采样 swap=0，MemAvailable=836791996416 B，高于 reserve=324465062092 B。71 页按本机 4096 B 页大小为 290816 B（284 KiB）。这些数据确认旧全局计数规则触发，但不能确定换出页面属于哪个进程或为何被内核选中；不把当前 swappiness/NUMA 配置冒充历史因果证据。

原 watchdog 的同期整树 RSS 采样峰为 635625377792 B，另一个 1300 GB guard 的接管后峰为 640141377536 B；两者分别保留，不拼成一个采样峰。后者约晚 0.245 秒记录 worker RSS 不可读并收尾，时间顺序不支持把它当作最初全局换页事件。其 swap 字段只是末次样本，不额外创造没有累计记录支持的 swap 峰值。原 watchdog 的 `job_swap_activity=UNRESOLVED_global_activity_cannot_be_attributed` 必须原样保留。

按任务独立 cgroup v2、任务匿名内存禁止换出和任务级归因，是供后续讨论的资源监督修订方向。全机计数应如何保留诊断、实际 RSS/系统 reserve/OOM 保护如何衔接，须明确后再实施；本次只归档，不改系统、数值/物理门限或监督代码。

批准上述终态证据、索引与本文的文档提交正常推送同一执行分支，保留先前运行快照。活动源码仍固定为 41caf5141493ad6c5d6c518a64ee74fda8d7a7db；不把终态归档当成重跑授权。
