# Task44 outcomes summary（执行中）

## 当前状态

六层材料与输入实现已通过定向验证。P2 成对求解验证了装配期静态凝聚的场恢复、R/T 和体吸收与完整矩阵路径一致，但它不是 P6/MUMPS 资格。P6 凝聚直接求解样本 A 已完成，残差与能量闭合门通过，场文件可读且数值有限。A 的主 R/T 来自完整 DtN 端口模态；另两种采样诊断和主结果有明显差异，已逐项保留，不能当作主结果或静默抹去。

B/C/D 的同路线输入已生成并通过公共 adapter 的 `--validate-only`，尚未启动 PDE。A–D 完成后还需进行有限的网格、倏逝模态和上方空气间距对照。正式训练集、开发验证集、盲测集和 GP 均未运行；A 单样本约 29 分钟，批量样本规模必须结合实测成本重新判断。

## 样本与阶段账

| 对象 | 模型 / 方法 | 状态 | 数值与边界 | 证据 |
|---|---|---|---|---|
| 旧正式 A | 六层全 0.5 nm，P6，144 hex，双 Floquet / auto-propagating DtN，`standard_full` | `controlled_stop`；结果 `not_run` | 8433.239279829897 s 后按用户要求停止；watchdog exit `-15` 且 cgroup 清空。systemd `failed/exit-code/status1` 保留。没有 residual、R/T/A 或 `A_volume`，不算数值失败 | `benchmarks/artifacts/task44_native_services/task44-sample-a-dynamic2.service/user_controlled_stop.json` |
| 凝聚实现 sanity | 同六层模型但 P2、3×6×8；完整矩阵 direct 对照装配期静态凝聚 direct | 两个 case 均 `completed / official_result=true`；分类 `numerical_sanity_only` | 独立 full `Ax-b` 相对 residual `2.4258989122760487e-12`；R `0.9994596016861909/0.9994596016861921`；T `0.000540279641313905/0.0005402796413138561`；总 `A_volume` `1.184079724682327e-7/1.1840797246823236e-7`。factor profile 是 PETSc `default`，不是 MUMPS qualification | ignored `benchmarks/artifacts/task44_condensed_direct_validation_20261031/` 下 P2 evidence JSON、run summaries 与字段 NPZ |
| A，P6 正式样本 | 六层全 0.5 nm，144 hex，双 Floquet、完整 auto-propagating auxiliary DtN；装配期静态凝聚 + `mumps_exact` | `completed`；`official_result=true`；残差与 closure gate 通过 | 详见下方统一结果表。该点是 0.7 nm 缩尺代理样本，不证明连续解精度、标准尺寸或 GP 可预测性 | [A 输入](../../../input/task44_sample_a_condensed_direct_v1.dat)；[hash-bound 审阅记录](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_A_review_v1.json)；[数值输出](../../../results/task44_sixlayer_0p7nm/sample_A_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T055027.974554Z/numerical_output/run_summary.json) |
| 首个 cache-fix 启动 | 同一 A 输入，旧共享 FFCx 缓存根 | `worker_nonzero`，不是 PDE 数值失败 | 31.9605 s 后 JIT 报告缓存中的 C 文件编译超时；没有组装矩阵或进入求解。原共享缓存和 run 目录均保留 | `benchmarks/artifacts/task44_native_services/task44-sample-a-condensed.service/`；对应时间戳 run 目录下 `worker_stdout.txt` |
| B/C/D 输入 | 六层分别全 0.75 nm、全 1 nm、交替 0.5/1 nm；均为 P6 / 凝聚 direct / MUMPS exact | `valid`，PDE `not_run` | 仅厚度、由总厚度推导的 `z_max_nm`/`air_height_nm`、总柱高和 run ID 不同；材料、波长、入射、网格划分数、DtN 与求解器设置相同 | [B](../../../input/task44_sample_b_condensed_direct_v1.dat)、[C](../../../input/task44_sample_c_condensed_direct_v1.dat)、[D](../../../input/task44_sample_d_condensed_direct_v1.dat) |

## A 的统一数值结果

静态凝聚先在每个六面体内部消去不与邻单元共享的自由度，再组装较小的全局系统；解出后恢复完整 H(curl) 场。它减少全局矩阵规模，但增加局部凝聚、恢复与矩阵自由残差计算。DtN 端口的 auxiliary 模态作为额外未知量表示上下端口的出射波，因此 29,808 个独立迹行外还附加 160 行。

| 项目 | A 结果 | 判据 / 解释 |
|---|---:|---|
| 全算子相对真残差 | `7.584367086899987e-10` | ≤ `1e-6`，pass；残差范数 `9.79964835722215e-10`，RHS 范数 `1.2920851858750988` |
| 残差计算 | 显式迹/DtN 矩阵作用 + 对所有被消去单元内部测试空间执行 matrix-free UFL 作用，包含凝聚后的完整 RHS | `full_global_matrix_allocated_for_residual=false`；这不是只读 MUMPS 的内部收敛标志 |
| 主反射 `R_total` | `0.10377060655595945` | 主功率源 `dtn_port_modal_amplitudes` |
| 零级反射 | `R00_s=0.10376987725348902`；`R00_p=6.570154036905706e-22`；`R00_total=0.10376987725348902` | `R00_total=R00_s+R00_p`，从保存值重算一致 |
| 主透射 `T_total` | `0.8800846265279674` | 主功率源 `dtn_port_modal_amplitudes` |
| 端口功率平衡 `A_balance` | `0.01614476691607314` | 由端口模态的 R/T 得到 |
| 材料体吸收 `A_volume_total` | `0.016144766075562058` | 六层与 Si 基底上的 `Im(epsilon_r)|E|²` 积分；每层及基底状态均为 `ok` |
| 能量闭合 `R+T+A_volume−1` | `-8.405111051601466e-10` | 绝对值 ≤ `1e-5`，pass；端口 A 与体积分 A 差 `8.405110808740179e-10` |
| KSP/PC/MUMPS | `preonly` / `lu` / `mumps`；`CONVERGED_ITS`，1 iteration | `mumps_control_readback.pass=true`，六项 ICNTL 的读回与要求一致 |

| 材料区域 | `A_volume` |
|---|---:|
| 第 1 层 Si | `0.0005378736956743745` |
| 第 2 层 Si₀.₇Ge₀.₃ | `0.004907296097588378` |
| 第 3 层 Si | `0.0005303344631520798` |
| 第 4 层 Si₀.₇Ge₀.₃ | `0.004767875461961016` |
| 第 5 层 Si | `0.0005076530103900762` |
| 第 6 层非晶 SiO₂ | `0.0009462386109519906` |
| Si 基底 | `0.0039474947358441445` |

场文件 `airbox_fields_3d_scientific.npz` 含 3,888 个 owned points、144 个 cells；E、H、坐标、Poynting 和 tag 等全部数值数组有限，保存文件 SHA-256 为 `1ed94284404da165b1829fbdfe2cf2cca20fceab87064a668ef7f67d3ea38a15`。最大场值为 `|E|=1.345827044339094 V/m`、`|H|=0.003573012615621154 A/m`。

### 网格、凝聚和直接因子规模

| 指标 | A 读回值 |
|---|---:|
| 网格 | `3×6×8=144` 个贴体六面体；P6；所有 z 层边界与材料对齐 |
| 物理 Nédélec 自由度 | `99,894` |
| 被消去的 cell-interior modes | `64,800` |
| 独立迹行 / 凝聚后 FE 行 | `29,808` |
| DtN auxiliary 行 | `160`（上下各 `80`） |
| 全局求解系统 | `29,968` rows，`24,315,568` used nnz |
| MUMPS 因子 nnz | `108,289,136` |
| cell kernel 结构计数 | `14` 个唯一原始材料/几何类对应的派生核调用，覆盖 144 cell；该数字由 compiled-kernel 映射推导，不是动态 profiler 计数 |

### 成本与诊断差异

| 资源 / 输出 | 实测 | 口径 |
|---|---:|---|
| Worker elapsed | `1653.708 s` | 公共 runner 从启动到写完结果 |
| Service elapsed | `1740.104 s` | systemd service 全生命周期 |
| Stage-4 组装与求解 | `1613.084 s` | worker 分阶段计时；子阶段存在嵌套，不应相加成总时间 |
| MUMPS factorization / solve | `41.037 s` / `0.860 s` | MUMPS 日志中的 driver 时间 |
| Matrix-free full residual | `181.518 s` | 恢复完整场后对全算子的显式作用检查 |
| 进程树同时 RSS 峰值 | `7,282.69 MB` | watchdog 采样的 process-tree RSS |
| cgroup memory peak | `8,337,240,064 B` | 专属 service cgroup |
| Memory authority peak | `7,948.01 MB` | watchdog 资源权威口径；与 process-tree RSS/cgroup memory 不混称 |
| 任务 swap | `0 B` | 零 swap Gate 通过；service 结束后精确 PID 与 cgroup 均清空 |

端口模态是本样本的主 R/T/A 来源，且其 R/T 与 `A_volume` 闭合。两种额外采样算法仅是诊断：probe-EH Fourier 给出 `R=0.1195200182, T=0.7818715805, A=0.0986084013`（`A_probe−A_volume=0.0824636352`）；采样净通量给出 `R=0.2077451311, T=0.7789153558, A=0.0133395130`（`A_flux−A_volume=-0.0028052530`）。它们不是主要端口模态结果；当前证据没有把这两个差异归因到单一原因，后续精度检查仍须保留并解释这一边界。

## 启动器与证据身份

首个 condensed service 错误地继承共享默认 XDG 缓存，遇到旧 FFCx C 源编译超时；它在 PDE 装配前退出。最小修复为每个 service 绑定完整 unit 名称专属缓存根，将 `MYFENICS_TASK44_CACHE_ROOT` 显式传入 ABI preflight、正式 systemd unit 与 watchdog worker，并在 supervisor 中 fail-closed 验证 `XDG_CACHE_HOME` 和 FFCx 子目录。`task44-sample-cache-probe2.service` 的现有 smoke (`--dry-run`) 通过；没有修改 user-manager 全局环境，也没有清除旧缓存。修复提交为 `41867b8c0c64b8febe8a3cb230ccd84f00360af8`、`03ee03a51f9f7057376975fd43fd9d059dd9cd2b`。

A 的正式 service 为 `task44-sample-a-condensed-cachefix.service`，Invocation ID `6a2fb5670a684354b10a520e1021d94d`，MainPID/start ticks `4131351/335082125`，CPU affinity `[12]`，源码 SHA `03ee03a51f9f7057376975fd43fd9d059dd9cd2b`，输入 SHA-256 `8b320f279242f5dfa7183d2330647f5181c89343c4e01c5971e0ca06f1390f26`。专属 FFCx cache 根为 `/tmp/myfenics-task44-native-cache-1000/task44-sample-a-condensed-cachefix`。完整路径、逐文件 SHA 与 gate 复核见 ignored artifact [`official_A_review_v1.json`](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_A_review_v1.json) 及 [`official_A_artifact_hashes_v1.json`](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_A_artifact_hashes_v1.json)。

## 下一步

1. 用当前凝聚 direct + MUMPS exact 路线逐个运行 B、C、D；每个 service 重新做 ABI、邻任务、CPU、宿主/祖先 cgroup、内存和零 swap Gate，使用新的唯一 cache root 与唯一 run ID。
2. A–D 完成后，做有限的主传播方向网格、层内 z、DtN 倏逝模态和上方空气间距对照。每次保留 R/T/R00 与诊断差异；不把 A 的闭合门误当为空间精度门。
3. 当前样本实际约 29 分钟，已超过 README 的 10 分钟单样本成本提示。完成 B–D 和有限数值诊断后先评估总成本，不铺开 20/40/80 点库；代理、开发验证、最终盲测和标准尺寸目前均为 `not_run`。
