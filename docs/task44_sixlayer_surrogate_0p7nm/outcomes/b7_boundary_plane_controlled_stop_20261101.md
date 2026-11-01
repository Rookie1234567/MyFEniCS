# B7 boundary-plane 参考面对照：受控监控停止

第 7/12 次资格 attempt 沿用 B 的六层结构、P6、`[3,6,8]` 网格、160 个 DtN 模态、静态凝聚与 MUMPS，仅使用 `boundary_plane` 相位参考面及独立 run/output/service/cache 身份。CPU 邻核 Gate 在 assembly-time condensation 路径中触发 `MONITORING_FAILED`，分类为 `controlled_stop / not_run`；没有 full true residual、official R/T/A 或参考面差值。这不是数值失败或通过。

| 身份 | 记录 |
|---|---|
| 分支 / source SHA | `task44_sixlayer_surrogate_0p7nm` / `a12c7b4ea624ec7340cd747e4e1c2ec24d260011` |
| service / Invocation / MainPID / start ticks | `task44-sample-boundary-plane-b7-r1-20261101.service` / `661af54c0d474613ae0713d631d20b06` / `194921` / `342846007` |
| CPU / service cgroup | CPU `17`；`/user.slice/user-1000.slice/user@1000.service/app.slice/task44-sample-boundary-plane-b7-r1-20261101.service` |
| input SHA / run ID | `902f590bc137b515818d689a2bdc9e2b89d5f5e2997333366d3c642b48cf6e09` / `sample_B_boundary_plane_20261101_attempt7` |
| physical model SHA / resolved config 文件 SHA | `d97fe809c536ba0c73439cef4da855c636dc41b8fc3805a95a9e81d21678b131` / `660f8b18bddb3e9ce119e9c104705b60935f07b6ffad449daf1c272f52db481b` |

## 首个 stop 原因

`watchdog/resources.jsonl` 第 186 行、elapsed `1125.154486490 s` 是首个 `external_guard.stop=true` 样本。唯一 Gate failure 为 `selected_cpu_neighbor_gate_failed`，子因为 `unexpected_narrow_selected_cpu_affinity_neighbor`。claim 是 PID `201653`、parent `201652`、start ticks `342958624`、状态 `R`、命令 basename `run_convergence.py`、affinity `[17]`、cgroup `/user.slice/user-1000.slice/session-4665.scope`。样本无 unreadable process；Task44 unit/invocation/main PID/start ticks/exact cgroup 和四个服务进程 affinity `[17]` 均通过。内存、swap、时间 Gate 均未触发。

当前 `_numerical_processes()` 每个 watchdog sample 用一次 `ps` 建候选快照；`_proc_cpu_claim()` 对窄 claim 在同一次同步调用里读取前后 `/proc` stat、affinity 和 cgroup，并检查 PID/start ticks/PPID/comm/affinity/cgroup 与快照一致。它没有延时重扫完整邻居列表；单个稳定 claim 返回后，外层立即将邻核 Gate 作为 stop。成功 claim 记录只持久化一份摘要身份，没有保存两份 identity-before/after 原始对象，因此原始 JSONL 只能证明代码路径认定身份稳定，不能逐字段审阅两份底层读取。

主控在停止后从真实 host 观测到相同 PID/start ticks 后来仍为运行态，但 affinity 已变为 `0-47`，parent `201652` 也为 `0-47`。此派生观察只说明 mask 后来改变，不能反证 stop 时 `[17]` claim、推断任务归属或认定监控误报。

watchdog 的运行中 sample 间隔为 5 s。`stop_event` 记录 `grace_seconds=10`，但配置为 `hard_stop_immediate=true`；首个 SIGKILL 仅晚约 `44.9 μs`，没有实际等待 10 s。

## 计算边界与成本

最后一个 progress 事件为 `stage4_full3d_assembly_backend / end`，worker elapsed `9.694071 s`，实际 backend `assembly_time_static_condensed`。之后无矩阵完成、MUMPS factor/solve、残差或 official R/T/A 事件；外层 run summary 保持 `launching` / `official_results=null`，无数值结果文件。不能从现有 progress 记录定位凝聚 builder 的内部子阶段。

| 成本或状态 | 实测 |
|---|---:|
| watchdog/service elapsed | `1143.094710 s` |
| systemd CPU time | `18 min 49.771 s` |
| 同时进程树 RSS 采样峰值 | `5,056,647,168 B` |
| 专属 cgroup memory peak / swap peak | `5,282,217,984 B` / `0 B` |
| worker leader / systemd exit | `-9` / `ExecMainStatus=1` |
| 子树清理 | `descendants_cleared=true`；`remaining_child_pids=[]` |

预算计入第 7 次，已用 `7/12`，剩余 5 次。

## 原始证据 SHA-256

| 文件 | SHA-256 |
|---|---|
| service identity | `ec4f93a523a8091d4478d96575d397844096bd8bae01b9920140409036f0c9f9` |
| service summary | `db10e70e784c756de111a121360fa55f8bc3570e8cd10c7e46cb0db89dc9f44c` |
| watchdog summary | `4bf14c5a44530b5b59f5ba3ccd03f52737aae8ba24a57f2b4a66c85f1f8433b8` |
| watchdog `resources.jsonl` | `c61b90065c7dd97b79c07e7b337a05ef414ce35cb855c7922d6098259bf9de2d` |
| service log | `130f0e97fa9956369df5fb04e78dea2beaa96b66c9b00b18f83e454d97e679f0` |
| outer `run_summary.json` | `f071773f2891a9e3047021ad11811a0184c9ccd144c474e7445f125c8244d45d` |
| `progress_3d.jsonl` | `7cd3c64aa40f914f1010498415fbd99c36eb09d09ea91aa3cabb078792142c91` |
| `worker_stdout.txt` | `1d6fb3b3e262a03d1fef1e971ab9cf29cc226d64238d181af1980894135b1392` |

原始 service 目录：`benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b7-r1-20261101.service/`。原始 run 目录：`results/task44_boundary_plane_attempt7/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt7__full3d_direct__mpi1__Mna/20261101T032428.130026Z/`。
