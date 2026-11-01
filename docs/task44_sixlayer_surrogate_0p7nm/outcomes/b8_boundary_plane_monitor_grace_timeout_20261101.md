# B8 boundary-plane 参考面对照：邻核复核超时后受控停止

第 8/12 次资格尝试沿用 B 的六层模型、P6 `[3,6,8]` 网格、160 个 DtN 模态、装配期静态凝聚与 MUMPS exact，只采用 `boundary_plane` 相位参考面和新的 run/output/service/cache 身份。CPU 邻核 Gate 在首次发现一个稳定占用所选 CPU22 的外部进程后进入 15 秒复核等待；复核未在期限内确认释放，watchdog 以 `MONITORING_FAILED` 清理 Task44 子树。本次没有形成有限元数值结果，不能将其判为数值失败或参考面比较通过。

| 身份 | 记录 |
|---|---|
| 分支 / 正式源码 SHA | `task44_sixlayer_surrogate_0p7nm` / `774e2baa8003ece9c5208218e7f258680c949805` |
| service / Invocation / MainPID / start ticks | `task44-sample-boundary-plane-b8-r1-20261101.service` / `3b4cb0827df14a7491356a6c31508585` / `216341` / `343268603` |
| 绑定 CPU / service cgroup | CPU `22`；`/user.slice/user-1000.slice/user@1000.service/app.slice/task44-sample-boundary-plane-b8-r1-20261101.service` |
| run ID / input SHA-256 | `sample_B_boundary_plane_20261101_attempt8` / `0ce455e7e41cb5da9de110b45b9ec057d72147b58a8c8f68d7afe8f4890e0ad5` |
| 物理模型 SHA / resolved config SHA-256 | `d97fe809c536ba0c73439cef4da855c636dc41b8fc3805a95a9e81d21678b131` / `f7beaadf54bc69fda7ed6e73b593f70a2ae8d6abd17e2bbd4f475a543d8441f3` |
| service 资源合同 | MemoryMax `137438953472 B`；swap max/current `0 B`；`Restart=no`；`KillMode=control-group`；同 affinity `sched_setaffinity` 被 seccomp 拒绝 |
| 启动资源 / ABI Gate | CPU22 两段 busy 最大 `8.3333%`，启动邻核 Gate pass；host `MemAvailable=1,926,678,315,008 B`、扣除 reserve/cap/buffer 后余量 `1,368,332,566,528 B`、Task44 cgroup headroom `1,780,649,426,944 B`；PETSc complex128/int32、MPI1/OpenMPI 4.1.6 |

## 首个冲突与复核期限

`watchdog/resources.jsonl` 第 202 行（零起始索引 201）是首次邻核冲突样本，elapsed `1171.671913704 s`。被观察进程 PID `222707`、parent `222706`、start ticks `343385335`、命令 basename `recovery_diagnosis.py`、affinity `[22]`，cgroup 为 `/user.slice/user-1000.slice/session-4665.scope`。记录把 PID/start/PPID、命令、cgroup 和 affinity 作为同一进程身份复核，邻核 Gate 唯一 failure 为 `unexpected_narrow_selected_cpu_affinity_neighbor`；当时 Task44 service 自身身份、cgroup 和 affinity Gate 通过，内存与 swap Gate 未触发。

首个冲突 monotonic 时间为 `3433860.599532437`，明确的复核 deadline 为 `3433875.599532437`，两者恰差 15 秒。watchdog 随后在 elapsed `1177.916782 s`、`1184.176022 s` 继续观察；在 elapsed `1187.944892 s` 记录 `review_timeout`、`stop=true` 和 `selected_cpu_neighbor_review_timeout`，外层分类为 `MONITORING_FAILED`。该 timeout 样本比首次冲突样本晚约 `16.273 s`，说明复核期限后的采样有延后。

stop event monotonic 为 `3433876.896376408`，首个整棵子树 SIGKILL 为 `3433876.896472875`，二者相差约 `96.5 μs`。stop event 中 `grace_seconds=10.0` 是通用终止事件字段；本次实际邻核复核使用的 deadline 是上面的 15 秒，SIGKILL 紧随 timeout stop event，而没有再等待 10 秒。从首次冲突到首个 SIGKILL 实测约 `16.297 s`，即比 15 秒期限晚约 `1.297 s`；这是 watchdog 采样与处理时序的实测偏差，不能写成硬实时 15 秒终止。Task44 子树最终清空，`descendants_cleared=true`、`remaining_child_pids=[]`。

超时后的 elapsed `1194.123318 s` 样本再次看到同一 PID/start identity，但 affinity 已变为 `0-47`；随后 elapsed `1199.792198 s` 记录邻核状态 clear。该事后 mask 变化不反证 timeout 时保存的 `[22]`，也不能证明该进程的任务归属或追认先前 Gate 为误报。

## 运行结果与资源边界

| 项目 | 实测 / 状态 | 解释 |
|---|---|---|
| 整场非隔离标记 | `performance_not_isolated=true`（运行期 grace/release 记录）；启动回执为 `false` | 启动时未见共享 claimant；运行期 grace 中出现共享 CPU 声明。原始启动回执和 `service_summary.json` 的启动状态保留，不回写；整场结论按运行期资源轨迹判为 true。 |
| service/watchdog 生命周期 | `1206.285363 s`；systemd `CPUUsageNSec=1194323877000`（`1194.323877 s`） | service wall、CPU 累计和 worker run summary 是不同时间口径，不相加。 |
| 同时进程树 RSS 采样峰值 | `4,901,117,952 B` | watchdog 对活动进程采样 RSS 总和；PSS 未启用。 |
| service cgroup memory peak / swap peak | `5,288,030,208 B` / `0 B` | 内核 service cgroup 计数；不与进程树 RSS 混称。 |
| 终态 | watchdog `MONITORING_FAILED`；systemd `ActiveState=failed`、`MainPID=0`、`ExecMainStatus=1`；子树清空 | 受控监控停止，不是求解器数值失败。 |

worker progress 共 19 个事件，最后一项为 `stage4_full3d_assembly_backend / end`，实际路径 `assembly_time_static_condensed`。没有矩阵完成、MUMPS solve、full true residual、official R/T/A 或 `result.json`。外层 `run_summary.json` 保持 `launching / not_run`、`exit_status=null`；官方物理结果未运行。历史 progress 中的宿主 swap 读数不是 Task44 service swap；任务专属 cgroup swap 全程记录为 0。

该 B8 消耗第 8 次资格 attempt，预算剩余 4/12。B6、B7、B8 都没有参考面数值差，因此不改变已有 y/空气间距超限、z 单方向通过、DtN 未判定的精度结论；A–D 仍为 `gp_eligible=false`。在用户/主控决定新的邻核并发处置策略前，不自动启动 B9；不改变 15 秒复核设置，也不触碰 Task40。

## 原始证据 SHA-256

| 文件 | SHA-256 |
|---|---|
| service identity | `3e24bd2e99e257ed81483cf9f0a76acb88f7b721ac44598e723b1591b0bc735b` |
| service summary（含启动期状态） | `64ad749b528fbb734b08f114bfd912d5896bfe64efd62f9e89e815d313618381` |
| watchdog summary | `2d4240e3e0739c7cffee3725923a099e41857d66ee336602793885802343522c` |
| watchdog `resources.jsonl` | `0208e6d404290b0ab96c9c5e20e14a7bcc56d75cbb88f2a1ff4358ee2b4cebbe` |
| service log | `0fdf6017067697f39e21e668a5b360ec5cf3922fe3551a74e23e04c9bd09953e` |
| outer `run_summary.json` | `8500420587a3dcaded14925660755af6a9774e8649aad78f09eae86e0983c326` |
| `run_manifest.json` | `4f0e7a89804435ac12a74d744a5f80edf1839f3a272065368714fdf398066b0e` |
| `resolved_config.json` | `f7beaadf54bc69fda7ed6e73b593f70a2ae8d6abd17e2bbd4f475a543d8441f3` |
| `progress_3d.jsonl` | `6f9da47a6a81e3b912884cb259fbb2517ffba3b53359dea0e71da2534986303b` |

service 原始目录：`benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b8-r1-20261101.service/`。run 原始目录：`results/task44_boundary_plane_attempt8/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt8__full3d_direct__mpi1__Mna/20261101T043453.843242Z/`。
