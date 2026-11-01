# B6 boundary-plane 参考面尝试：受控监控停止

## 结论

第 6/12 次 B 参考面精度尝试在 CPU 邻核监控失败后受控终止。它没有产出真残差、官方 R/T/A 或可用于精度比较的有限元结果；分类为 `controlled_stop / MONITORING_FAILED / not_run`，不是数值失败，也不是内存或 swap 停止。

| 身份 | 记录 |
|---|---|
| 执行分支 / source SHA | `task44_sixlayer_surrogate_0p7nm` / `005d248c915b156827bd38227b20fc905e47c1a0` |
| service / Invocation / CPU | `task44-sample-boundary-plane-b6-r1-20261101.service` / `3a4f9217a171488885c72792bb9f4bdc` / CPU 11 |
| 输入 / resolved config / physical model SHA-256 | `3755515c9789bdac27e3d453ca7eeed43116ccd30feb7275939d3baf79d76738` / `c2b547aaabe4bc7d2dc359b04db0f4259f758bc02a1ff71b7828eebff5bec935` / `d97fe809c536ba0c73439cef4da855c636dc41b8fc3805a95a9e81d21678b131` |
| 模型与方法 | B 的六层厚度、材料、P6、`[3,6,8]` 网格、MPI1、完整传播 DtN、160 模态（inventory hash `968eac1d2794d97b01b5757e6e9550bc54cb48249459b02fd5851f201b87df9f`）、静态凝聚与 MUMPS 保持不变；本对照只切换到 `boundary_plane` 参考面并使用唯一运行/输出身份 |
| 停止事件 | 资源样本 index 151（JSONL 第 152 行）、运行 `851.931390325 s`：`selected_cpu_neighbor_gate_failed`，子原因 `unexpected_narrow_selected_cpu_affinity_neighbor` |
| 邻核 claim | PID 189961，parent PID 189960，start ticks 342782816，affinity `[11]`，cgroup `/user.slice/user-1000.slice/session-4665.scope`；原始进程链为 `189959 → 189960 → 189961`。不对该进程来源作归因，也未干预该进程 |
| 退出与清场 | stop_event 记录 `grace_seconds=10`，但首个 SIGKILL 仅晚约 27 μs（monotonic 记录 `3427829.339804772 → 3427829.339832242`）；监控器对 Task44 子进程树执行 SIGKILL；worker leader exit `-9`，systemd `ExecMainStatus=1`；无自动重启，`descendants_cleared=true`，无遗留 child PID |
| 时间与资源 | service wall `868.732799189 s`；累计 CPU `855.593 s`；进程树同时 RSS 峰值 `5,052,604,416 B`；任务 cgroup memory peak `5,277,028,352 B`；任务 swap 峰值 `0 B`；无内存 warning / cap 事件 |
| 预算 | 计入 12 次精度预算，更新为 `6/12`；未因该停止增加或抹除运行成本 |

## 计算进度边界

worker 写出了网格、Floquet 约束和变分形式准备记录。最后的 progress 事件 `stage4_full3d_assembly_backend` 只报告后端选择，发生在约 6.44 s；worker stdout 的最后一行也是 `assembly_time_static_condensed` 后端已选定。它不是矩阵装配完成事件。

随后调用了 `fem.form(a)` 并进入 assembly-time condensation builder。该 service 专属 FFCx 缓存中留有同次编译的 208 MiB C 源和 42 MiB `.so`，证明 UFL/FFCx JIT 编译完成。builder 内没有逐阶段 progress，因此现有证据无法判断它停止在 raw tensor 评估、局部 LU/Schur 消元、PETSc `Mat.setValues` 插入或其他内部步骤。`stage4_dtn_base_matrix_assembled` 没有出现，builder 未返回；之后的最终全局 PETSc assembly、MUMPS 因子分解与 solve 均无到达证据。没有 residual、场、功率或结果 JSON。

run summary 仍是 `launching / not_run / exit_status=null`。运行目录仅包含 mesh、partition note 和 `progress_3d.jsonl`；没有 solver log、factor、solution、field 或 power 输出。B7 使用独立 service/cache 身份，不复制 B6 的矩阵、因子或运行中间对象。

## 原始证据入口与 SHA-256

| 文件 | SHA-256 |
|---|---|
| service summary | `4a48a4e2cbe0d8d812621a090783fb1b1e4ff6285818bfe7331532e19a0b54a3` |
| watchdog summary | `4119853fc4fca50080c063886fbfb9458b4151a00902cc54217b8240c3a44972` |
| watchdog resources JSONL | `ae0f1b7f364f8db66df11d9dbfdaa1d83447f7e2f4fb8840addf165ec073f846` |
| service identity | `32133164a13558fc00a02a17c1067e34996127d2e20682e3353695ecfd2ce76d` |
| outer run summary | `f422c9d864df26184f37c09392ca8f9ed1810da810b08218a0c0caf2ac43b81e` |
| run manifest | `2e10795bb01e27210892dda7b81f6cd9b1bedecb82db6260b8b3f6093ada13a8` |
| progress log | `7151277c0fe98704c7d176e4cd2cba56496bd962450380bd91a874f3a635dabb` |
| worker stdout | `8c234351e3cba376a378f614e70ec5e3066d8df632239cd99a54d1c84129d322` |

原始 service 文件位于 `benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b6-r1-20261101.service/`；运行目录为 `results/task44_boundary_plane_attempt6/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt6__full3d_direct__mpi1__Mna/20261101T025942.389901Z/`。
