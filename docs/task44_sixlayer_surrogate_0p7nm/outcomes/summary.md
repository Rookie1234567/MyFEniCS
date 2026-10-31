# Task44 outcomes summary（代表点完成，精度资格待闭合）

## 当前状态

2026-10-31，四个冻结厚度点 A–D 均已用 P6、144 个贴体六面体、装配期静态凝聚和 MUMPS exact 完成正式三维计算。四场都通过完整离散算子相对真残差门（≤ `1e-6`）和体吸收能量闭合门（≤ `1e-5`），并保存了全级 DtN 端口 R/T 与场数据。它们是当前有限网格上的正式离散样本，不代表连续解精度，也尚未因空间稳定性核查而取得代理训练资格。

用户已要求等待另一条活动 direct solve 结束后，再按顺序运行四项稳定性对照。传播方向 y 加密曾启动一次，但 watchdog 因监控到的 service 进程身份未稳定而受控终止；该尝试没有进入矩阵组装或求解，没有数值结果，不能算作精度门失败。z 加密、DtN 倏逝模态扩展和顶部空气间距对照均为 `not_run`。训练数据扩充、GP、开发验证、盲测与标准尺寸仍未运行。

## 阶段与负结果

| 对象 | 模型 / 方法 | 状态与数据身份 | 结果和边界 | 证据 |
|---|---|---|---|---|
| 旧 A 全局 direct | A 厚度，P6，144 hex，`standard_full` | `controlled_stop`；物理结果 `not_run` | 8433.239279829897 s 后按用户要求停止；watchdog exit `-15`，cgroup 清空。旧 `run_summary.json` 保持 `launching / not_run / null`，不算求解器数值失败 | `benchmarks/artifacts/task44_native_services/task44-sample-a-dynamic2.service/user_controlled_stop.json` |
| 首次凝聚 A 缓存启动 | A 厚度，凝聚 direct | `worker_nonzero`；物理结果 `not_run` | 31.9605 s 后共享旧 FFCx C 文件 JIT 编译超时；未装配或求解。原共享缓存和 run 目录保留 | `benchmarks/artifacts/task44_native_services/task44-sample-a-condensed.service/` |
| 正式样本 A–D | 六层缩尺结构，P6、3×6×8、双 Floquet、完整自动传播 DtN、静态凝聚 + `mumps_exact` | `completed`；`official_result=true`；`measured` | 四场均通过真残差、能量闭合、MUMPS 控制读回、零任务 cgroup swap 和清场门。统一结果见下表；精度资格仍待四项对照 | 各输入和 run summary 见下表；service 记录位于 `benchmarks/artifacts/task44_native_services/task44-sample-{a,b,c,d}-condensed-cachefix.service/` |
| y 传播方向加密首次启动 | 以 B 为基线，网格从 `[3,6,8]` 改到 `[3,12,8]` | `MONITORING_FAILED`；数值结果 `not_run` | 21.729 s 后监控观察到 PID 4168233、4168234、4168235 的身份未稳定，整棵子树已清理。worker 建出 3×12×8、288 格网格并选择 MUMPS，但没有矩阵组装、解或 R/T/A。不是数值或容量失败；将以新 unit 重试 | `benchmarks/artifacts/task44_native_services/task44-sample-accuracy-yrefine.service/service_summary.json`、`watchdog/worker.log` |
| z 加密 / DtN 倏逝模态 / 顶部空气对照 | 以 B 为基线 | `not_run` | 三项仍需依次完成；每项都比较 `R_total`、`T_total`、`R00_total` 的绝对变化是否均 ≤ `2e-4` | [z 输入](../../../input/task44_accuracy_layer_z2_v1.dat)、[DtN 输入](../../../input/task44_accuracy_dtn_evanescent_shell_v1.dat)、[空气输入](../../../input/task44_accuracy_air_gap_1nm_v1.dat) |
| GP、训练 / 开发 / 盲测、标准尺寸 | 原任务后续阶段 | `not_run` | 四个代表点待精度资格；当前每个 worker 约 27.6–30.6 分钟，先完成对照并按实测成本决定训练规模 | 本 summary 的下一步决策 |

## A–D 统一数值结果

A–D 的六层厚度分别为全 0.5、全 0.75、全 1.0 nm 和交替 0.5/1.0 nm。静态凝聚在每个六面体内部消去不与邻单元共享的自由度，先解较小的全局迹与端口系统，再恢复完整电磁场；这样减少全局系统的行数，但增加局部矩阵处理、场恢复和全算子残差检查的工作。表中 `R_total`、`T_total` 来自全部传播 DtN 模态；`A_balance` 来自端口功率差，`A_volume` 来自材料体积吸收积分。`R00_s/p/total` 是反射零级的 S、P 分量及其和。

| 样本 / 六层厚度 (nm) | `R_total` | `T_total` | `R00_s` | `R00_p` | `R00_total` | `A_balance` | `A_volume` | full true residual | `R+T+A_volume−1` | 数据身份 / 证据 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A / 0.5×6 | 0.10377060655595945 | 0.8800846265279674 | 0.10376987725348902 | 6.570154036905706e-22 | 0.10376987725348902 | 0.01614476691607314 | 0.016144766075562058 | 7.584367086899987e-10 | -8.405111051601466e-10 | `measured`；[输入](../../../input/task44_sample_a_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_A_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T055027.974554Z/numerical_output/run_summary.json) |
| B / 0.75×6 | 0.0952190944953505 | 0.8831311299072778 | 0.0952186487281771 | 5.011182975657206e-24 | 0.0952186487281771 | 0.02164977559737169 | 0.02164977481611931 | 7.333002340121292e-10 | -7.812523961092666e-10 | `measured`；[输入](../../../input/task44_sample_b_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_B_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T063009.557323Z/numerical_output/run_summary.json) |
| C / 1.0×6 | 0.08581651094067945 | 0.8877015737613739 | 0.08581582462769617 | 3.901928348820551e-21 | 0.08581582462769617 | 0.026481915297946634 | 0.026481914592266717 | 6.580098648397804e-10 | -7.05679958912242e-10 | `measured`；[输入](../../../input/task44_sample_c_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_C_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T070135.788196Z/numerical_output/run_summary.json) |
| D / 0.5,1.0,0.5,1.0,0.5,1.0 | 0.09358123207431406 | 0.8803289446256277 | 0.09358070870418612 | 1.213549477479837e-23 | 0.09358070870418612 | 0.026089823300058268 | 0.026089822597639773 | 5.119574895162806e-09 | -7.024184567328007e-10 | `measured`；[输入](../../../input/task44_sample_d_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_D_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T073200.895421Z/numerical_output/run_summary.json) |

四个 `R_total/T_total/R00_total/A_volume` 都是非负有限值；端口吸收与体积分吸收相符，闭合误差绝对值都小于 `1e-9`，远低于 `1e-5` 门限。full true residual 使用恢复后的完整场：对迹/DtN 部分显式作用，并对被消去的单元内部空间用 matrix-free UFL 作用，连同完整 RHS 一并计算；没有把 MUMPS 内部状态或 `solver_residual_norm=0` 当作 true residual。

统一离散规模为 144 个 P6 六面体、99,894 个 Nédélec DoF、29,808 个独立迹行和 160 个 DtN auxiliary 行，共 29,968 个增广求解行。上下端口各 80 个模式，A–D 当前均为传播模式；使用矩阵 `NNZ` 为 A/B/D 的 24,315,568，C 的 24,315,748。MUMPS `preonly / lu / mumps` 的 ICNTL 读回在四个样本均通过。

### 时间、内存与 swap

| 样本 | worker wall (s) | service wall (s) | service watchdog 进程树 RSS 峰值 (B) | 专属 service cgroup memory 峰值 (B) | cgroup / 进程树 swap 峰值 (B) | 清场 |
|---|---:|---:|---:|---:|---:|---|
| A | 1653.708 | 1740.104 | 7,550,930,944 | 8,337,240,064 | 0 / 0 | `descendants_cleared=true` |
| B | 1738.079 | 1803.805 | 7,677,751,296 | 8,568,664,064 | 0 / 0 | `descendants_cleared=true` |
| C | 1679.951 | 1749.664 | 7,799,111,680 | 8,586,145,792 | 0 / 0 | `descendants_cleared=true` |
| D | 1836.503 | 1911.111 | 7,827,030,016 | 8,556,298,240 | 0 / 0 | `descendants_cleared=true` |

worker wall 与 systemd 全生命周期是不同口径，不相加。进程树 RSS 是 watchdog 在活动 PID 上采样的 RSS 总和；cgroup memory peak 是内核 cgroup 计数，二者不混称。`run_summary.json` 的 `total_peak_rss_mb` 是单 rank 历史峰值上界，不是同时峰值；PSS 在本 profile 中关闭。四个任务 cgroup 的 swap peak 均为 0，停止后后代已清理。C 的主机全局 swap 活动无法归因给 Task44，因此 `job_swap_activity` 标为 `UNRESOLVED`；但 C 的专属 cgroup 与进程树 swap 采样仍为 0，任务 swap Gate 通过。

### 缓存复用的范围

| 样本 | raw tensor 材料/几何类 | cell use | 同类重复复用 | 派生 kernel invocation | 独立 FFCx JIT cache root |
|---|---:|---:|---:|---:|---|
| A | 14 | 144 | 130 | 14 | `task44-sample-a-condensed-cachefix` |
| B | 17 | 144 | 127 | 17 | `task44-sample-b-condensed-cachefix` |
| C | 17 | 144 | 127 | 17 | `task44-sample-c-condensed-cachefix` |
| D | 17 | 144 | 127 | 17 | `task44-sample-d-condensed-cachefix` |

每场都使用自己的 `/tmp/myfenics-task44-native-cache-1000/<service-unit>/` 根，FFCx 子目录也由该 service 明确绑定；因此不能把 B/C/D 描述成复用了前一场的 warm JIT。raw tensor、局部 LU 和场恢复缓存只在本场建立与复用；没有跨样本复用数值矩阵、因子或端口相位。cell-form kernel invocation 数由“编译核 × 唯一材料/几何类”映射派生，不是动态 profiler 计数。每场还报告一个只读、按单元内部形状共享的 identity cache class。

### 精度对照状态

| 对照 | B 基线与唯一改变量 | 目标输出变化门 | 当前状态 | 证据 / 下一步 |
|---|---|---|---|---|
| 传播方向 y 加密 | `[3,6,8]` → `[3,12,8]`；网格 144 → 288 cells | `abs(ΔR_total)`,`abs(ΔT_total)`,`abs(ΔR00_total)` 均 ≤ `2e-4` | 首次启动 `MONITORING_FAILED`；数值 `not_run` | 保留旧 attempt；待 Task40 service 和进程树清空后用新 unit 重试 |
| 材料内部 z 加密 | `[3,6,8]` → `[3,6,16]`；网格 144 → 288 cells | 同上 | `not_run` | [输入](../../../input/task44_accuracy_layer_z2_v1.dat) |
| DtN 倏逝模态扩展 | B 的完整传播模式集加一圈手动阶次壳层，范围 `m=[-4,4]`,`n=[-8,8]` | 同上 | `not_run` | [输入](../../../input/task44_accuracy_dtn_evanescent_shell_v1.dat) |
| 顶部空气间距 | 0.5 → 1.0 nm；基底底面固定 `z=-0.5 nm` | 同上 | `not_run` | [输入](../../../input/task44_accuracy_air_gap_1nm_v1.dat) |

该 `2e-4` 门只说明已对照离散之间的工程稳定性，不是连续解误差保证。资格复算上限为 12 次；目前计入一次未进入求解的 y-refinement monitor attempt，后续四项仍在预算内。

## A 的材料吸收分布与主功率诊断补充

静态凝聚先在每个六面体内部消去不与邻单元共享的自由度，再组装较小的全局系统；解出后恢复完整 H(curl) 场。它减少全局矩阵规模，但增加局部凝聚、恢复与矩阵自由残差计算。DtN 端口的 auxiliary 模态作为额外未知量表示上下端口的出射波，因此 29,808 个独立迹行外还附加 160 行。

| 项目 | A 结果 | 判据 / 解释 |
|---|---:|---|
| 全算子相对真残差 | `7.584367086899987e-10` | ≤ `1e-6`，pass；残差范数 `9.79964835722215e-10`，RHS 范数 `1.2920851858750988` |
| 残差计算 | 显式迹/DtN 矩阵作用 + 对所有被消去单元内部测试空间执行 matrix-free UFL 作用，包含凝聚后的完整 RHS | `full_global_matrix_allocated_for_residual=false`；这不是只读 MUMPS 的内部收敛标志 |
| 主反射 `R_total` | `0.10377060655595945` | 主功率源 `dtn_port_modal_amplitudes` |
| 零级反射 | `R00_s=0.10376987725348902`；`R00_p=6.570154036905706e-22`；`R00_total=0.10376987725348902` | `R00_total=R00_s+R00_p`，从保存值重算一致 |
| 主透射 `T_total` | `0.8800846265279674` | 主功率源 `dtn_port_modal_amplitudes` |
| 端口功率平衡 `A_balance` | `0.01614476691607314` | 由端口模态的 R/T 得到 |
| 材料体吸收 `A_volume_total` | `0.016144766075562058` | 按材料虚部与电场强度平方，在六层与 Si 基底上积分；每层及基底状态均为 `ok` |
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
| service watchdog 进程树 RSS 采样峰值 | `7,550,930,944 B` | service summary 中活动进程树 RSS 总和；PSS profile 关闭 |
| 专属 cgroup memory peak | `8,337,240,064 B` | 内核 service cgroup memory 计数；不与 RSS 混称 |
| worker historical RSS 字段 | `4,484.82 MB` | `sum_rank_historical_peaks_upper_bound_not_simultaneous`，不是同时进程树峰值 |
| 任务 swap | `0 B` | 零 swap Gate 通过；service 结束后精确 PID 与 cgroup 均清空 |

端口模态是本样本的主 R/T/A 来源，且其 R/T 与 `A_volume` 闭合。两种额外采样算法仅是诊断：probe-EH Fourier 给出 `R=0.1195200182, T=0.7818715805, A=0.0986084013`（`A_probe−A_volume=0.0824636352`）；采样净通量给出 `R=0.2077451311, T=0.7789153558, A=0.0133395130`（`A_flux−A_volume=-0.0028052530`）。它们不是主要端口模态结果；当前证据没有把这两个差异归因到单一原因，后续精度检查仍须保留并解释这一边界。

## 启动器与证据身份

首个 condensed service 错误地继承共享默认 XDG 缓存，遇到旧 FFCx C 源编译超时；它在 PDE 装配前退出。最小修复为每个 service 绑定完整 unit 名称专属缓存根，将 `MYFENICS_TASK44_CACHE_ROOT` 显式传入 ABI preflight、正式 systemd unit 与 watchdog worker，并在 supervisor 中 fail-closed 验证 `XDG_CACHE_HOME` 和 FFCx 子目录。`task44-sample-cache-probe2.service` 的现有 smoke (`--dry-run`) 通过；没有修改 user-manager 全局环境，也没有清除旧缓存。修复提交为 `41867b8c0c64b8febe8a3cb230ccd84f00360af8`、`03ee03a51f9f7057376975fd43fd9d059dd9cd2b`。

A 的正式 service 为 `task44-sample-a-condensed-cachefix.service`，Invocation ID `6a2fb5670a684354b10a520e1021d94d`，MainPID/start ticks `4131351/335082125`，CPU affinity `[12]`，源码 SHA `03ee03a51f9f7057376975fd43fd9d059dd9cd2b`，输入 SHA-256 `8b320f279242f5dfa7183d2330647f5181c89343c4e01c5971e0ca06f1390f26`。专属 FFCx cache 根为 `/tmp/myfenics-task44-native-cache-1000/task44-sample-a-condensed-cachefix`。完整路径、逐文件 SHA 与 gate 复核见 ignored artifact [`official_A_review_v1.json`](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_A_review_v1.json) 及 [`official_A_artifact_hashes_v1.json`](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_A_artifact_hashes_v1.json)。

## 下一步

1. 等待 Task40 直接求解 service 变为非活动，确认其 systemd cgroup 和实际后代 PID 均清空；不向其发送信号，也不和它并发启动 Task44 数值算例。
2. 先用新 service unit 重试 y 加密，再依次运行 z 加密、DtN 倏逝壳层和顶部空气间距对照。每次重做 ABI、邻任务、CPU、宿主/祖先 cgroup、内存、swap 和 service 身份 Gate，并校验完整残差、能量闭合、R/T/R00 和清场。不得复用失败 y attempt 的 unit 或覆盖其证据。
3. 四个对照完成后，以 B 为基线比较三项输出绝对变化。若精度门未通过，在最多 12 次资格复算预算内最小调整网格/模态并保留旧负结果；不把未通过的标签混入同精度数据集。
4. A–D worker 实测为 1653.708–1836.503 s（27.6–30.6 min）；服务全生命周期为 1740.104–1911.111 s（29.0–31.9 min）。不预设批量性能已达到目标，也不因单样本较慢直接判断 GP 不可行。完成精度门后先按成本规划训练点数，训练、开发验证、最终盲测与标准尺寸目前仍为 `not_run`。
5. 当前 execution branch 保持显式凝聚 direct 研究路线，不改 ordinary solver default，不合并 `master`；结果与未运行范围进入下一轮 review。
