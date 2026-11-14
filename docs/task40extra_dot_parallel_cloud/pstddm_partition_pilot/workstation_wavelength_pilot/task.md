# 工作站波长续试：PSTDDM 小光栅

## 范围与优先级

本文件记录用户在旧 PSTDDM pilot 完成后的新续试指令。它只增加 `workstation_wavelength_pilot` 子任务，不改写既有 `task.md`、V1/V2 response、review 或 outcomes。旧 pilot 的 0.7 nm、120-cell 结果继续作为历史证据，不能代替本续试的材料、几何、参考场或资源结果。

用户本轮指令覆盖父任务中的 cloud-only 和旧波长执行顺序：只允许在 `fenics-ws` 上工作，且所有任务专属输入、输出与临时文件限制在 `/home/fenics/Projects/laptop_share` 下主控指定的独立目录。写入远端或启动正式数值运行前，须由主控确认专用目录、冻结 source、资格化 Linux ABI、watchdog/cgroup 资源门和认证状态。本地准备不代表远端运行许可。执行者负责本地实现、最小测试、获准运行与证据，不 commit/push；主控负责冻结 source 并集中 commit/push。不改其他任务工作树。

## 要回答的问题

在固定三维有限宽度小光栅上，局部 PML 与累计弱形式源转移能否在原始 Floquet–DtN 系统下工作；分区数增加是否减少同一任务的完整进程树峰值内存和总时间。波长按 `13.5 nm → 通过且总预算允许时 5 nm → 条件性 0.7 nm` 推进。几何保持绝对尺寸不变；这些小型 p2 网格用于同离散算法/资源试验，不作为材料、网格或连续物理收敛证明。

## 固定三维几何与首轮网格

周期单胞为 `50 × 50 nm`，竖直计算区为 `z = [-10, 130] nm`。Si 基底为 `[-10,0] nm`；居中的有限 Si 长方体占 `x=[16.5,33.5] nm`、`y=[15,35] nm`、`z=[0,120] nm`，即宽 `17 × 20 nm`、高 `120 nm`。其余区域为空气。x/y 两方向均保留 Floquet 周期边界；光栅在 x、y 均有真实有限宽度，不把 y 延拓成二维线栅。

13.5 nm 首轮使用 p2 和一张冻结的 boundary-fitted hexahedron 网格：

| 方向 | 面坐标（nm） | 每段细分 | 全轴 cell 数 |
|---|---|---:|---:|
| x | `0, 16.5, 25, 33.5, 50` | 每段 1 | 4 |
| y | `0, 15, 25, 35, 50` | 每段 1 | 4 |
| z | `-10, 0`；`0..120` 等分 14 段；`120,130` | 基底 1、光栅 14、顶层空气 1 | 16 |

总计 256 个六面体；材料面和居中光栅边界均落在网格面上。z 的 16 层可合法切成 N=2/4/8，每个分区分别含 8/4/2 个物理层；首轮正式候选固定为 direct reference、N=2、N=4，N=8 只有在主控重新准入且共享预算仍足够时才考虑。p2 独立 FE 行的结构化计数派生值为 6,272，含 DtN 的总行数须由实际模式 inventory 再计算；`4*n^2*16 B` 只作为保守 factor planning allowance，不是实测内存或因子大小。不得以此网格宣称物理精度。

## 材料、入射和通道

材料为 Si 基底和 Si 光栅，`mu_r=1`，空气 `n=1`。每个波长都必须以同一份可追溯的 Si 原始光学数据重新得到复折射率并冻结材料 identity；优先复用仓库内已保存的 CXRO/Henke `si.nff` 原始表，记录其 SHA、目标光子能量、实际 bracket 行、插值公式、密度、`n`/`epsilon`、时间谐波符号。0.7 nm 的既有材料值只可作为独立交叉核验，不能直接代入其他波长；缺少可靠 bracket 时须报告 material blocker，不外推或伪称实测值。

保留既有 PSTDDM pilot 入射：`theta=89°`、`phi=90°`、s 偏振、单位幅值。每个波长根据当前材料、波矢和周期重新生成传播模式；DtN inventory 包含全部传播通道，并在 m、n 各方向扩一阶固定矩形倏逝包络。实际输入应使用代码生成的精确 `auto_max_m/n + 1`，记录有序模式、传播/倏逝数量、cutoff 警告及完整 C/D identity，不能沿用旧 836 模式清单或只改 `lambda0`。首轮 13.5 nm 的规划边界为 m=±4、n=±8（共 612 个 top/bottom、两偏振 auxiliary 模式；须由冻结材料下的代码 inventory 再确认）。

## 算子与局部辅助问题

原始全局问题保持真实材料、双 Floquet 和 Fourier–DtN，不在全局方程加入吸收。使用完整未凝聚 `[A,C;D,I]` 系统及 full explicit true residual；先求 direct reference，再运行 PSTDDM initial sweep 和原系统右 FGMRES。候选门槛沿用旧 pilot：direct true residual `<=1e-10`，最终候选 `<=1e-8`，E/H 同离散场误差分别 `<=1e-4/1e-3`。使用已有合格后处理时，入射功率归一化后的总功率量与参考绝对差门为 `<=1e-4`，并报告候选/reference 能量缺口；每个 R/T/通量吸收/体吸收/模式量都注明后处理资格。未资格的量保留为 diagnostic，不能据此宣称物理通过，也不能因标为 diagnostic 而跳过已资格项目的门槛。

局部 PML 只在内部人工切面使用：每侧物理厚度 10 nm、两层、宽度比 1.25、二次 z stretch `s(t)=1+i*sigma*(t/10)^2`，`sigma=3*ln(100)/(k0*sin(1°)*10)`。此公式与厚度/单元/名义衰减目标跨波长固定；系数依 `k0` 自动变化。局部材料沿相邻真实横截面延拓，人工外端施加零切向场；触及全局 z 端点时不放局部 PML，保留对应原始 DtN 块。全局 A、局部 PML 张量和缓存身份必须分开记录。保留原实现的 L2 lifting、`curl(beta E)=beta curl(E)+grad(beta)×E` 弱形式交换项、双向累计源和连续 H(curl) 重构；不得改回 Schwarz 的 `r -= A delta` 循环。

## 预算、资源和停止条件

整段波长续试共用原独立预算：MPI1、数学线程变量均为 1；最多 10 个 attempt，累计数值/JIT/setup/恢复/输出时间不超过 21,600 秒，每案不超过 1,800 秒。正式运行只允许一个 heavy case 同时活动。进程树 RSS 受 `8,000,000,000 B` 和现场可用动态预算中的较小者限制，另留至少 512 MiB 阶段余量。任务自身 cgroup swap 必须为 0；宿主已有 swap 与其他项目进程须按实际 cgroup/PID 归属记录，不能把邻项目资源或约 400 GB 的可用余量视为本任务额度。主控需在启动前现场核验宿主保留线和邻项目安全余量（暂按至少 400 GiB host reserve 计划），持续读取 MemAvailable、进程树 RSS、cgroup memory/swap、磁盘和 wall time；触发门时受控终止本任务完整进程组。

顺序为：13.5 nm 完整 direct + N=2/N=4 两个候选；只有 source/ABI/资源门通过、direct 与至少一个候选数值门通过且共享预算足够时，才评估 5 nm 同一物理几何；0.7 nm 仅当 5 nm 有正结果、模式/因子 admission 和动态安全预算证明可运行时进入，否则保存阻塞依据。任何失败、controlled stop 或未运行项均原样保留；不增加损耗、不删模式、不扫网格/PML、不把资源停止说成算法数值失败。

## 本地准备状态

当前阶段只完成配置/算法接口准备与最小相关软件检查；不得在未获主控冻结前开始正式 PDE。`response_v1.md` 记录可审阅的准备结果、测试、尚未运行项和远端准入缺口。最终 summary 需分波长列 source/input/physical SHA、完整 mode inventory、direct/candidate 原残差、场误差、局部/全局自由度、因子生命周期、全过程 RSS/swap/wall time，以及正负结论。
