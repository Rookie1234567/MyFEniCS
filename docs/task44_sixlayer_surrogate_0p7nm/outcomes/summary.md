# Task44 outcomes summary（A–D 已完成，y 门未通过、z 门通过）

## 当前状态

2026-10-31，四个冻结厚度点 A–D 均已用 P6、144 个贴体六面体、装配期静态凝聚和 MUMPS exact 完成正式三维计算。四场都通过完整离散算子相对真残差门（≤ `1e-6`）和体吸收能量闭合门（≤ `1e-5`），并保存了全级 DtN 端口 R/T 与场数据。它们是当前有限网格上的正式离散样本，不代表连续解精度，也尚未因空间稳定性核查而取得代理训练资格。

用户允许 Task44 与 Task40 同时运行；Task44 只监控自身 service 与资源，不停止或修改 Task40。四项精度对照仍由 Task44 一次运行一个。传播方向 y 加密第一次启动因 service 子进程身份未稳定而受控终止，没有进入矩阵组装或求解，保留为 `MONITORING_FAILED / not_run`；retry 的残差与能量闭合通过，但相对 B 的 `R_total/T_total/R00_total` 变化均超过 `2e-4`，所以 y 方向稳定性门失败。材料内部 z 加密已完成：残差与能量闭合通过，三项主输出相对 B 的变化均约 `1e-10`，低于 `2e-4`。z 对照只表明该设置下加密结果稳定；y 对照仍未通过，因此 A–D 仍不得取得 GP 训练资格。DtN 倏逝模态扩展和顶部空气间距对照尚未运行。

固定 seed `440731` 的首轮设计已冻结为 20 training / 10 development / 10 blind test，见 [`sample_design_v1.json`](../sample_design_v1.json)。训练候选含 A–D 和 16 个六维分层覆盖点；A–D 标签仍为 `gp_eligible=false`。40 个几何输入字节、解析物理模型和离散签名哈希已登记，未求解候选的结果保持 `null`。开发和盲测几何均不与训练重合；盲测样本没有标签字段。GP 软件已通过 9 项定向测试和 40 点设计校验；有限元训练、模型选择、开发评估、盲测和标准尺寸仍为 `not_run`。

## 阶段与负结果

| 对象 | 模型 / 方法 | 状态与数据身份 | 结果和边界 | 证据 |
|---|---|---|---|---|
| 旧 A 全局 direct | A 厚度，P6，144 hex，`standard_full` | `controlled_stop`；物理结果 `not_run` | 8433.239279829897 s 后按用户要求停止；watchdog exit `-15`，cgroup 清空。旧 `run_summary.json` 保持 `launching / not_run / null`，不算求解器数值失败 | `benchmarks/artifacts/task44_native_services/task44-sample-a-dynamic2.service/user_controlled_stop.json` |
| 首次凝聚 A 缓存启动 | A 厚度，凝聚 direct | `worker_nonzero`；物理结果 `not_run` | 31.9605 s 后共享旧 FFCx C 文件 JIT 编译超时；未装配或求解。原共享缓存和 run 目录保留 | `benchmarks/artifacts/task44_native_services/task44-sample-a-condensed.service/` |
| 正式样本 A–D | 六层缩尺结构，P6、3×6×8、双 Floquet、完整自动传播 DtN、静态凝聚 + `mumps_exact` | `completed`；`official_result=true`；`measured` | 四场均通过真残差、能量闭合、MUMPS 控制读回、零任务 cgroup swap 和清场门。统一结果见下表；精度资格仍未通过，y 加密对照变化超限 | 各输入和 run summary 见下表；service 记录位于 `benchmarks/artifacts/task44_native_services/task44-sample-{a,b,c,d}-condensed-cachefix.service/` |
| y 传播方向加密首次启动 | 以 B 为基线，网格从 `[3,6,8]` 改到 `[3,12,8]` | `MONITORING_FAILED`；数值结果 `not_run` | 21.729 s 后监控观察到 PID 4168233、4168234、4168235 的身份未稳定，整棵子树已清理。worker 建出 3×12×8、288 格网格并选择 MUMPS，但没有矩阵组装、解或 R/T/A。不是数值或容量失败；后续 retry 结果见下一行 | `benchmarks/artifacts/task44_native_services/task44-sample-accuracy-yrefine.service/service_summary.json`、`watchdog/worker.log` |
| y 传播方向加密 retry | 以 B 为基线，`[3,6,8]` → `[3,12,8]`；P6、288 hex、MPI1、CPU8、static condensation + MUMPS | 求解和闭合 `pass`；空间稳定性 `failed` | `R/T/R00` 绝对变化分别为 `9.8002e-4 / 9.2275e-4 / 9.8001e-4`，均超过 `2e-4`。保留 measured 结果，不把 B 的 GP 标签标成 eligible | [run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_propagation_y2_20261031__full3d_direct__mpi1__Mna/20261031T091904.310578Z/numerical_output/run_summary.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-yrefine-retry1.service/service_summary.json) |
| 材料内部 z 加密 | 以 B 为基线，`[3,6,8]` → `[3,6,16]`；P6、288 hex、MPI1、CPU29、static condensation + MUMPS | 求解、闭合、z 稳定性 `pass` | 三项主输出相对 B 的绝对变化均约 `1e-10`，远小于 `2e-4`；该比较不证明 y 方向或连续解已收敛 | [run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/numerical_output/run_summary.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-zrefine1.service/service_summary.json) |
| DtN 倏逝模态扩展 | B 的完整传播模式集加一圈手动阶次壳层，范围 `m=[-4,4]`,`n=[-8,8]` | 同上 | `not_run`；仍需比较 `R_total`、`T_total`、`R00_total` 的绝对变化是否均 ≤ `2e-4` | [输入](../../../input/task44_accuracy_dtn_evanescent_shell_v1.dat) |
| 顶部空气间距 | 0.5 → 1.0 nm；基底底面固定 `z=-0.5 nm` | 同上 | `not_run`；仍需比较 `R_total`、`T_total`、`R00_total` 的绝对变化是否均 ≤ `2e-4` | [输入](../../../input/task44_accuracy_air_gap_1nm_v1.dat) |
| GP与样本设计软件 | 20/10/10 固定划分；Matérn 5/2 ARD三输出 GP、均值和线性基线 | 软件 `verified`；有限元 GP `not_run` | 40个几何互不重复；A–D等待精度资格；未求解候选结果为空；开发/盲测没有标签泄漏 | [`sample_design_v1.json`](../sample_design_v1.json)、`src/studies/task44_surrogate.py`、`src/test/test_task44_surrogate.py` |
| 有限元训练扩充 / 开发评估 / 最终盲测 / 标准尺寸 | 原任务后续阶段 | `not_run` | A–D尚无空间稳定性资格；四个正式 worker 用时约27.6–30.6分钟，先完成有限核查与合法缓存成本证据，再按实测调整批量 | 本 summary 的下一步决策 |

## A–D 统一数值结果

A–D 的六层厚度分别为全 0.5、全 0.75、全 1.0 nm 和交替 0.5/1.0 nm。静态凝聚在每个六面体内部消去不与邻单元共享的自由度，先解较小的全局迹与端口系统，再恢复完整电磁场；这样减少全局系统的行数，但增加局部矩阵处理、场恢复和全算子残差检查的工作。表中 `R_total`、`T_total` 来自全部传播 DtN 模态；`A_balance` 来自端口功率差，`A_volume` 来自材料体积吸收积分。`R00_s/p/total` 是反射零级的 S、P 分量及其和。

| 样本 / 六层厚度 (nm) | `R_total` | `T_total` | `R00_s` | `R00_p` | `R00_total` | `A_balance` | `A_volume` | full true residual | `R+T+A_volume−1` | 数据身份 / 证据 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A / 0.5×6 | 0.10377060655595945 | 0.8800846265279674 | 0.10376987725348902 | 6.570154036905706e-22 | 0.10376987725348902 | 0.01614476691607314 | 0.016144766075562058 | 7.584367086899987e-10 | -8.405111051601466e-10 | `measured`；[输入](../../../input/task44_sample_a_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_A_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T055027.974554Z/numerical_output/run_summary.json) |
| B / 0.75×6 | 0.0952190944953505 | 0.8831311299072778 | 0.0952186487281771 | 5.011182975657206e-24 | 0.0952186487281771 | 0.02164977559737169 | 0.02164977481611931 | 7.333002340121292e-10 | -7.812523961092666e-10 | `measured`；[输入](../../../input/task44_sample_b_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_B_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T063009.557323Z/numerical_output/run_summary.json) |
| C / 1.0×6 | 0.08581651094067945 | 0.8877015737613739 | 0.08581582462769617 | 3.901928348820551e-21 | 0.08581582462769617 | 0.026481915297946634 | 0.026481914592266717 | 6.580098648397804e-10 | -7.05679958912242e-10 | `measured`；[输入](../../../input/task44_sample_c_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_C_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T070135.788196Z/numerical_output/run_summary.json) |
| D / 0.5,1.0,0.5,1.0,0.5,1.0 | 0.09358123207431406 | 0.8803289446256277 | 0.09358070870418612 | 1.213549477479837e-23 | 0.09358070870418612 | 0.026089823300058268 | 0.026089822597639773 | 5.119574895162806e-09 | -7.024184567328007e-10 | `measured`；[输入](../../../input/task44_sample_d_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_D_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T073200.895421Z/numerical_output/run_summary.json) |

四个 `R_total/T_total/R00_total/A_volume` 都是非负有限值；端口吸收与体积分吸收相符，闭合误差绝对值都小于 `1e-9`，远低于 `1e-5` 门限。full true residual 使用恢复后的完整场：对迹/DtN 部分显式作用，并对被消去的单元内部空间用 matrix-free UFL 作用，连同完整 RHS 一并计算；没有把 MUMPS 内部状态或 `solver_residual_norm=0` 当作 true residual。

### B 的 y 加密结果：内部求解通过，空间稳定性未通过

这项计算只把传播方向 y 的单元数从 6 增至 12，其余物理模型、P6、DtN 模态、MPI1、静态凝聚和 MUMPS 设置沿用 B。网格由 144 增至 288 个贴体六面体。求解器将完整场的显式相对真残差控制在 `1.275136723e-9`，低于 `1e-6`；端口功率与材料体吸收的闭合误差为 `-3.946687421e-11`，低于 `1e-5`。但与 B 相比，三个主输出变化都超出 `2e-4`，说明当前离散选择还没有在 y 方向达到任务要求的稳定程度。这个差异不能归因于残差或能量不守恒，也不能据此宣称更细的网格已收敛。

| 对照 | `R_total` | `T_total` | `R00_s / R00_p / R00_total` | `A_balance / A_volume` | 相对 B 的有符号差值 | 判定 |
|---|---:|---:|---|---|---|---|
| B，`[3,6,8]` | 0.0952190944953505 | 0.8831311299072778 | 0.0952186487281771 / 5.011182975657206e-24 / 0.0952186487281771 | 0.02164977559737169 / 0.02164977481611931 | 基线 | measured；基线 solve/closure pass |
| B 的 y 加密，`[3,12,8]` | 0.09619911407616114 | 0.8822083809416161 | 0.09619866247638499 / 1.0699952159268371e-21 / 0.09619866247638499 | 0.02159250498222276 / 0.021592504942755907 | `ΔR=+9.800195808e-4`；`ΔT=-9.227489657e-4`；`ΔR00=+9.800137482e-4` | 三项绝对变化均大于 `2e-4`；空间稳定性失败，不能据此将 B 标签标为 `gp_eligible` |

R/T 和 `R00` 取自完整 DtN 端口模态主结果；场上的 Fourier 和采样通量只作诊断，不代替主功率。加密 run 的输入 SHA-256 为 `272312c4e0b997fbf40649c4d3be678a9cd38efe229f3b3d61fddc5fa0656269`，物理模型 SHA-256 为 `b16f8d783eb85069c530194e246ea88c691d011411892771f93a0c6111224886`，source SHA 为 `5a89ca1652fbe721f4d0ecf8cef9fc7ea276d92a`。完整自由度数为 `197,994`；独立迹行 `59,616`，加上 160 个 DtN auxiliary 行后，实际求解系统为 `59,776` 行。该 run summary 未记录凝聚矩阵的最终 NNZ，故不估算或补写 NNZ。

### B 的 z 加密结果：求解与 z 稳定性通过

该对照只把材料内部的 z 网格段数从 8 增至 16，其他材料、几何、端口条件、P6、静态凝聚和 MUMPS 设置沿用 B。单元数从 144 增至 288；完整 DtN 端口模态仍作为 R/T 主结果。输入配置比较确认，唯一的物理数值设置变化是 z 网格段数。该试验检查材料层厚度方向的离散敏感性，不是连续解精度证明。

| 数值量 | B：`[3,6,8]` | z 加密：`[3,6,16]` | z−B 有符号变化 | 判定 |
|---|---:|---:|---:|---|
| `R_total` | 0.0952190944953505 | 0.0952190943990193 | -9.633120690e-11 | `abs(Δ)≤2e-4` |
| `T_total` | 0.8831311299072778 | 0.8831311298228821 | -8.439571264e-11 | `abs(Δ)≤2e-4` |
| `R00_total` | 0.0952186487281771 | 0.09521864862777846 | -1.003986477e-10 | `abs(Δ)≤2e-4` |
| `R00_s / R00_p`（z 加密） | — | 0.09521864862777846 / 9.543330210210267e-23 | — | `R00_total=R00_s+R00_p` |
| `A_balance / A_volume`（z 加密） | — | 0.021649775778098568 / 0.02164977501620309 | — | 端口吸收与体积分吸收闭合 |
| 全显式算子相对真残差 | — | 4.64908820597943e-10 | — | `≤1e-6`，pass |
| `R+T+A_volume−1` | — | -7.61895435630322e-10 | — | `≤1e-5`，pass |

三项功率变化均远小于任务门限，表示 z 向加密对这三个输出没有可见影响。它不能解释 y 对照的大变化，也不能把 A–D 提升为 GP 合格样本；`gp_eligible=false` 继续有效。

| 身份 / 成本项 | 记录 |
|---|---|
| Run / service / Invocation | `task44_accuracy_layer_z2_20261031` / `task44-sample-accuracy-zrefine1.service` / `2328dc0df7f94e16a4305010eaccb054` |
| CPU / service cap / 输入 SHA-256 / 物理模型 SHA-256 / source SHA | CPU 29 / 137,438,953,472 B（128 GiB）/ `6c55c599439fee0963f529025873549c9418fd08884767d4a14109d920660c0e` / `21f035163b3f875f916f9560bdfc778f871c56f0b2875023a8211825ac085f19` / `a10ece015bb311489d0dc4a977a197e1da2df90f` |
| 网格 / 自由度 / 实际系统 | 288 hex，P6；198,438 个完整 Nédélec DoF；58,320 个迹行 + 160 个 DtN auxiliary 行 = 58,480 行 |
| 矩阵 NNZ | 48,157,036 used NNZ（run summary 记录） |
| numerical run summary / service 全生命周期 | 1,651.694 s / 1,716.819 s；worker wall 未单独记录 |
| Stage 4 / DtN build / direct solve / full residual | 1,620.108 s / 1,262.984 s / 0.862 s / 114.007 s |
| process-tree RSS 峰值 / cgroup memory 峰值 | 10,121,396,224 B / 10,965,905,408 B；分别为同时进程树 RSS 采样与内核 cgroup peak |
| swap / 监控 / 清场 | cgroup 与进程树 swap 峰值均为 0；resource authority 4,670 次采样且无 warning；1,346 次身份采样完整；`descendants_cleared=true` |
| 关键证据 SHA-256 | numerical run summary `a37e4b03cba2e9752e3146c320e21b0520d7e56f865c0f1b6cddb89314caada8`；DtN power metrics `1e66d971db95cb15740c2874859c9fce14c26d229a962ddb7e76c146eb159c0c`；service summary `a1cf9cde125a0b680f8b46af493544bbac85729538f0c65842091aae9a643696` |

此任务运行标记 `official_result=true` 表示 worker 的完整离散求解和数值门结果可用；同时 `physical_benchmark_candidate=false`、`validation_role=numerical_sanity_only`，所以不把 z 对照当作新训练标签。MUMPS 控制读回与 service completion receipt 通过。详情见 [`response_v5.md`](../response_v5.md)、[run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/numerical_output/run_summary.json) 和 [service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-zrefine1.service/service_summary.json)。

GP 的 Matérn 5/2 ARD 核把相近的六层厚度组合视为更可能产生相近功率结果，并为六个厚度分别拟合影响范围；这样可以表达某一层厚度比另一层更敏感的情况。代价是要从有限训练点估计多个尺度参数，预测标准差仍只是模型内部的不确定度，不是真实误差上界。输入使用冻结的 `[0.5,1.0] nm` 范围归一化；输出均值和尺度只从训练数据取得。实现同时保留训练均值和线性拟合基线，并把误差还原到原始功率比单位。

统一离散规模为 144 个 P6 六面体、99,894 个 Nédélec DoF、29,808 个独立迹行和 160 个 DtN auxiliary 行，共 29,968 个增广求解行。上下端口各 80 个模式，A–D 当前均为传播模式；使用矩阵 `NNZ` 为 A/B/D 的 24,315,568，C 的 24,315,748。MUMPS `preonly / lu / mumps` 的 ICNTL 读回在四个样本均通过。

### 时间、内存与 swap

| 样本 | worker wall (s) | run summary elapsed (s) | service summary elapsed (s) | stage4 端口装配与求解 (s) | DtN/base build (s) | 进程树 RSS 峰值 (B) | cgroup memory 峰值 (B) | cgroup / 进程树 swap 峰值 (B) | 清场 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A | 1653.708 | — | 1740.104 | 1613.084 | 1161.224 | 7,550,930,944 | 8,337,240,064 | 0 / 0 | `descendants_cleared=true` |
| B | 1738.079 | — | 1803.805 | 1708.840 | 1381.071 | 7,677,751,296 | 8,568,664,064 | 0 / 0 | `descendants_cleared=true` |
| C | 1679.951 | — | 1749.664 | 1647.064 | 1317.490 | 7,799,111,680 | 8,586,145,792 | 0 / 0 | `descendants_cleared=true` |
| D | 1836.503 | — | 1911.111 | 1802.634 | 1424.319 | 7,827,030,016 | 8,556,298,240 | 0 / 0 | `descendants_cleared=true` |
| B 的 y 加密 | — | 3347.793 | 3417.755 | 3313.561 | 2851.534 | 12,487,163,904 | 13,289,373,696 | 0 / 0 | `COMPLETED`；9,262 次 watchdog 采样，子树清理 |
| B 的 z 加密 | — | 1651.694 | 1716.819 | 1620.108 | 1262.984 | 10,121,396,224 | 10,965,905,408 | 0 / 0 | `COMPLETED`；1,346 次身份采样，子树清理 |

worker wall、run summary elapsed 与 systemd service 全生命周期是不同口径，不相加。y 的 `3347.793 s` 与 z 的 `1651.694 s` 来自各自 numerical `run_summary`；`3417.755 s` 和 `1716.819 s` 是对应 service 全生命周期，不能把前者记作 worker wall。进程树 RSS 是 watchdog 在活动 PID 上采样的 RSS 总和；cgroup memory peak 是内核 cgroup 计数，二者不混称。`run_summary.json` 的 `total_peak_rss_mb` 是单 rank 历史峰值上界，不是同时峰值；PSS 在本 profile 中关闭。四个 A–D、y 和 z 的任务 cgroup 与进程树 swap peak 均为 0，y/z 子树已清理。C 的主机全局 swap 活动无法归因给 Task44，因此 `job_swap_activity` 标为 `UNRESOLVED`；但 C 的专属 cgroup 与进程树 swap 采样仍为 0，任务 swap Gate 通过。

### 缓存复用的范围

| 样本 | raw tensor 材料/几何类 | cell use | 同类重复复用 | 派生 kernel invocation | 独立 FFCx JIT cache root |
|---|---:|---:|---:|---:|---|
| A | 14 | 144 | 130 | 14 | `task44-sample-a-condensed-cachefix` |
| B | 17 | 144 | 127 | 17 | `task44-sample-b-condensed-cachefix` |
| C | 17 | 144 | 127 | 17 | `task44-sample-c-condensed-cachefix` |
| D | 17 | 144 | 127 | 17 | `task44-sample-d-condensed-cachefix` |

每场都使用自己的 `/tmp/myfenics-task44-native-cache-1000/<service-unit>/` 根，FFCx 子目录也由该 service 明确绑定；因此不能把 B/C/D 描述成复用了前一场的 warm JIT。raw tensor、局部 LU 和场恢复缓存只在本场建立与复用；没有跨样本复用数值矩阵、因子或端口相位。cell-form kernel invocation 数由“编译核 × 唯一材料/几何类”映射派生，不是动态 profiler 计数。每场还报告一个只读、按单元内部形状共享的 identity cache class。

#### 跨样本编译缓存的只读核查

FFCx 把变分形式和编译选项组合成模块名；同名缓存命中时会导入已生成的 Python 扩展模块。该身份键包含 FFCx 表单选项、C 编译参数和 Python ABI，但自身不含完整 Task44 源码 SHA。因此，为跨样本复用还需额外绑定源码及完整软件栈，并验证缓存文件完整，不能只凭文件名认定安全。A–D 当前都是每 service 独立缓存，没有使用跨样本 warm JIT。

| 缓存对 | 记录到相同模块名 | `.o` / `.so` 完全相同 | `.c` 完全相同 | 结论 |
|---|---:|---:|---:|---|
| B → C | 30 个模块 | 30/30，合计约 603.15 MB | 2/30 | 存在部分可复用的二进制，但不能从模块名或 C 源文件推断整库等价；未复制或启动复用 |
| C → D | 30 个模块 | 10/30，合计 337,440 B | 需进一步证据 | 仅有少量相同二进制，尚无可据此宣称的端到端加速 |

B/C/D 记录的源码 SHA 相同，preflight 的 Python 路径、complex128、PETSc int32、MPI1/OpenMPI4.1.6、DOLFINx/Basix/PETSc/SLEPc 模块路径一致。`.cached` sidecar 含原绝对 cache 路径，内容在不同 service 间不同；当前实现没有经资格化的 sidecar 迁移流程。后续只考虑以源 SHA、ABI、FFCx/UFL/Basix版本、编译器/flags和文件内容哈希共同建身份的只读种子路径，并继续为每个样本保存独立结果与服务回执。矩阵、MUMPS 因子、数值端口相位等几何相关对象不跨样本复用。

### 精度对照状态

| 对照 | B 基线与唯一改变量 | 目标输出变化门 | 当前状态 | 证据 / 下一步 |
|---|---|---|---|---|
| 传播方向 y 加密 | `[3,6,8]` → `[3,12,8]`；网格 144 → 288 cells | B 为基线：`abs(ΔR_total)=9.8002e-4`、`abs(ΔT_total)=9.2275e-4`、`abs(ΔR00_total)=9.8001e-4`；三项阈值均 `2e-4` | 求解 residual 与能量闭合 pass；三个空间差值均超限，判 `accuracy_gate_failed`，不更新 GP 标签 | 首次 attempt 的监控失败保留；retry unit `task44-sample-accuracy-yrefine-retry1.service`、Invocation `27c2f1ed195943a8a494bd87c788c70f`；[run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_propagation_y2_20261031__full3d_direct__mpi1__Mna/20261031T091904.310578Z/numerical_output/run_summary.json) |
| 材料内部 z 加密 | `[3,6,8]` → `[3,6,16]`；网格 144 → 288 cells | `abs(ΔR_total)=9.6331e-11`、`abs(ΔT_total)=8.4396e-11`、`abs(ΔR00_total)=1.0040e-10`，均 ≤ `2e-4` | full true residual 与能量闭合 pass；本项 z 对照 pass。y 门失败仍有效，样本资格不改变 | [输入](../../../input/task44_accuracy_layer_z2_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/numerical_output/run_summary.json) |
| DtN 倏逝模态扩展 | B 的完整传播模式集加一圈手动阶次壳层，范围 `m=[-4,4]`,`n=[-8,8]` | 同上 | `not_run` | [输入](../../../input/task44_accuracy_dtn_evanescent_shell_v1.dat) |
| 顶部空气间距 | 0.5 → 1.0 nm；基底底面固定 `z=-0.5 nm` | 同上 | `not_run` | [输入](../../../input/task44_accuracy_air_gap_1nm_v1.dat) |

该 `2e-4` 门只说明已对照离散之间的工程稳定性，不是连续解误差保证。资格复算上限为 12 次；当前登记 3 次 attempt：两次 y attempt（一次未进入求解的 monitor failure、一次数值求解完成但空间稳定性失败）和一次 z 求解。DtN 与空气对照各运行一次后，预算还剩 7 次，可用于针对性跟进；不得把 z 单方向通过扩大解释为总精度通过。

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

1. Task44 与 Task40 并行已获用户明确授权。Task44 只观测自己的 service 和资源，不发送信号或修改 Task40；Task44 的重型对照仍一次运行一个。
2. y 加密 retry 已完成并作为空间稳定性负结果保留；z 加密三项输出均在 `2e-4` 门内。下一步依次运行 DtN 倏逝壳层和顶部空气间距对照。每次启动前重新检查 ABI、邻任务、CPU、宿主/祖先 cgroup、内存、swap 和 service 身份；每次运行后校验完整残差、能量闭合、R/T/R00 和进程清场。
3. 四项对照结束后，以 B 为基线比较三项输出并综合 y、z、DtN、空气的证据。若精度门未通过，在剩余资格复算预算内最小调整网格/模态并保留旧负结果；不把未通过的标签混入同精度数据集。
4. A–D worker 实测为 1653.708–1836.503 s（27.6–30.6 min）；服务全生命周期为 1740.104–1911.111 s（29.0–31.9 min）。不预设批量性能已达到目标，也不因单样本较慢直接判断 GP 不可行。完成精度门后先按成本规划训练点数，训练、开发验证、最终盲测与标准尺寸目前仍为 `not_run`。
5. 当前 execution branch 保持显式凝聚 direct 研究路线，不改 ordinary solver default，不合并 `master`；结果与未运行范围进入下一轮 review。
