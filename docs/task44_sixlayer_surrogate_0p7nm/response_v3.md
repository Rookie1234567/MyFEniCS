# Task44 执行响应 v3：A–D 代表点结果与精度核查排队

## 本轮范围和结论

本轮整理四个已经完成的 1/20 缩尺六层样本、轻量场文件读取检查和第一项精度对照的启动负结果。正式 PDE 的代码路线、材料模型和 solver default 没有变化。A–D 均来自 source SHA `03cc11c452f4f7a5cdfb800a84c87fdd4872410b`，用 P6、3×6×8、144 个六面体、静态凝聚、MPI1、MUMPS exact 和完整传播 DtN。

静态凝聚是在每个单元里先解掉不与邻单元共享的内部自由度，缩小全局联立系统；解出迹变量后再恢复完整场。它节省全局行数，但需要局部矩阵处理、恢复场和全算子残差计算。四场 full explicit true residual 均远低于 `1e-6`，`R_total + T_total + A_volume` 与 1 的差均小于 `1e-9`，MUMPS 控制项读回均通过。此结果只资格化当前离散解法的求解与功率闭合，不说明连续解精度，也不自动授予 GP 训练资格。

## 代表点正式结果

| 样本 | 六层厚度 (nm) | `R_total` | `T_total` | `R00_s / R00_p / R00_total` | `A_balance / A_volume` | full true residual | closure | 身份与证据 |
|---|---|---:|---:|---|---|---:|---:|---|
| A | 0.5×6 | 0.10377060655595945 | 0.8800846265279674 | 0.10376987725348902 / 6.570154036905706e-22 / 0.10376987725348902 | 0.01614476691607314 / 0.016144766075562058 | 7.584367086899987e-10 | -8.405111051601466e-10 | `measured`；[A run summary](../../../results/task44_sixlayer_0p7nm/sample_A_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T055027.974554Z/numerical_output/run_summary.json) |
| B | 0.75×6 | 0.0952190944953505 | 0.8831311299072778 | 0.0952186487281771 / 5.011182975657206e-24 / 0.0952186487281771 | 0.02164977559737169 / 0.02164977481611931 | 7.333002340121292e-10 | -7.812523961092666e-10 | `measured`；[B run summary](../../../results/task44_sixlayer_0p7nm/sample_B_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T063009.557323Z/numerical_output/run_summary.json) |
| C | 1.0×6 | 0.08581651094067945 | 0.8877015737613739 | 0.08581582462769617 / 3.901928348820551e-21 / 0.08581582462769617 | 0.026481915297946634 / 0.026481914592266717 | 6.580098648397804e-10 | -7.05679958912242e-10 | `measured`；[C run summary](../../../results/task44_sixlayer_0p7nm/sample_C_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T070135.788196Z/numerical_output/run_summary.json) |
| D | 0.5,1.0,0.5,1.0,0.5,1.0 | 0.09358123207431406 | 0.8803289446256277 | 0.09358070870418612 / 1.213549477479837e-23 / 0.09358070870418612 | 0.026089823300058268 / 0.026089822597639773 | 5.119574895162806e-09 | -7.024184567328007e-10 | `measured`；[D run summary](../../../results/task44_sixlayer_0p7nm/sample_D_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T073200.895421Z/numerical_output/run_summary.json) |

A–D 的 `R_total/T_total` 来自全传播 DtN 模态；`A_balance` 是端口平衡吸收，`A_volume` 是材料内体积积分吸收。零级反射的 P 分量仅约 `1e-21` 或更小。残差是恢复全场后对迹/DtN 矩阵显式作用并以 matrix-free UFL 作用覆盖被消去的 cell-interior 空间，包含凝聚 RHS；没有使用 PETSc/MUMPS 的内部收敛指示替代。

## 时间、资源、缓存与场文件

| 样本 | worker / service 时间 (s) | 进程树 RSS 峰值 (B) | cgroup memory 峰值 (B) | cgroup / 进程树 swap 峰值 (B) | 清场 |
|---|---:|---:|---:|---:|---|
| A | 1653.708 / 1740.104 | 7,550,930,944 | 8,337,240,064 | 0 / 0 | 是 |
| B | 1738.079 / 1803.805 | 7,677,751,296 | 8,568,664,064 | 0 / 0 | 是 |
| C | 1679.951 / 1749.664 | 7,799,111,680 | 8,586,145,792 | 0 / 0 | 是 |
| D | 1836.503 / 1911.111 | 7,827,030,016 | 8,556,298,240 | 0 / 0 | 是 |

`worker` 和 service 时间有不同边界，不相加；进程树 RSS 与内核 cgroup memory 是不同统计口径。run summary 中的 `total_peak_rss_mb` 是历史 rank 峰值上界，不是同时峰值。C 的主机全局 swap 活动归因不清，但专属 cgroup swap 与进程树 swap 采样均为 0，Task44 的 task-swap Gate 通过。

每个正式样本有不同的 FFCx cache 根，后续样本没有跨 service 的 warm JIT 资格。raw tensor 的同类复用发生在单个 case 内：A 是 14 个材料/几何类覆盖 144 次 cell use、同类重复使用 130 次；B/C/D 各是 17 类、144 次使用、127 次重复使用。kernel invocation 数按唯一类到编译核的映射派生，不能说成 profiler 实测。数值矩阵、MUMPS 因子、局部 LU/recovery 缓存和端口相位均未跨样本复用。

[A–D 场文件读取回执](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_AD_field_read_receipt_v1.json)检查了四个 NPZ 的记录哈希和全部数值数组有限性，并用 VTK 读取四个 VTU（每份 3,888 点、144 cells，数值数组有限）。E/H 的 BP 目录存在且已记录内容清单哈希，但当前 activation 环境没有 `adios2` Python module、`bpls` 命令或 VTK VTX reader，故 BP 内容没有独立解码；回执对此标为未解码，没有宣称已通过 BP 数值有限性检查。

## 精度对照和启动负结果

| 检查 | 设计 | 状态 |
|---|---|---|
| 传播方向 y 加密 | B 的 `[3,6,8]` → `[3,12,8]`，288 cells | 首次启动 21.729 s 后被 watchdog 分类为 `MONITORING_FAILED`；原因是三项 service PID identity 未稳定。网格已建立，但矩阵组装和求解未启动，R/T/R00 `not_run`。该 attempt 被保留，子进程已清理。 |
| 材料层内 z 加密 | B 的 `[3,6,8]` → `[3,6,16]`，288 cells | `not_run` |
| DtN 倏逝壳层 | B 自动传播集外扩到 `m=[-4,4]`,`n=[-8,8]` | `not_run` |
| 顶部空气距柱顶 0.5 → 1.0 nm | B 几何；底部面固定 `z=-0.5 nm` | `not_run` |

尚无任一 `abs(ΔR_total) / abs(ΔT_total) / abs(ΔR00_total) ≤ 2e-4` 的通过结果。第一次 y attempt 属于监控身份负结果，不是有限元数值失败或容量失败。当前 service identity verifier 遇到未稳定身份时会 fail closed；只有 idle-host 重试再次重现，才根据复现证据评估窄范围 retry 修复，不降低未知 PID、邻任务、内存、swap 或 service 身份门。

## 下一步和资格边界

Task40 direct solve 仍活动时，遵照用户指令与一次一个重算例规则，只观察其终态，不停止或修改它。待其 unit 非活动且 cgroup 和后代 PID 清空后，用新的 unit 重试 y 对照，再依次执行 z、DtN、空气距对照；每场独立跑完并检查后才启动下一场。该四项的通过只代表 B 周围所测离散的稳定性，不是连续解误差界。

GP、20/40/80 训练扩展、开发验证、最终盲测及标准尺寸均保持 `not_run`。A–D 的求解时间约 28–31 分钟/worker，成本高于 10 分钟批量提示，但不足以单独判定代理路线不可行。先闭合精度证据，再依据可复用数据数和实测成本决定是否启动训练。

本轮 execution branch 为 `task44_sixlayer_surrogate_0p7nm`，base SHA `db790f92a186988c5147f1828d15c07034e7c430`，计算 source SHA `03cc11c452f4f7a5cdfb800a84c87fdd4872410b`。当前任务未最终审查、未合并 master，ordinary solver default 未改变。
