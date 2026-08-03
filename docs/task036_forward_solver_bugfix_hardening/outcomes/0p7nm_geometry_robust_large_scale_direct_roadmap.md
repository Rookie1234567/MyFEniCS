# Task036：面向几何微调的 0.7 nm / 2 TB 大规模直接法路线审计

## 0. 文档身份与结论边界

| 字段 | 值 |
|---|---|
| 文档性质 | 只读证据综合、路线评估与后续 Gate 设计 |
| 最新权威 | [Task036 Review Report V8](../review_report_v8.md) |
| Task036 状态 | `CLOSED_CONTROLLED_FAILURE_WITH_REUSABLE_POSITIVES`；禁止新的 Task036 PDE/direct-port research |
| 本文授权边界 | 技术备选与未来新任务输入；不是 Task036 执行授权 |
| 当前数值状态 | `0.7 nm / 2 TB = not_solved` |
| 本文 direct 技术分析范围 | direct factorization / direct Schur / direct backsolve；不表示当前获准运行 |
| 本文 direct-only 备选排除项 | FGMRES、GMRES、其他 Krylov 外迭代、以迭代法掩盖接口压缩失败 |
| 本文是否实现新 solver | 否 |
| 本文是否运行 PDE | 否 |
| 本文是否证明 0.7 nm 可在 2 TB 内完成 | 否 |

身份与授权边界以 V8 为准：本文保留 direct 技术分析，供未来新任务选型；在用户重新授权前，
不得据此继续 Task036 数值开发、direct-port research、actual candidate 或任何新 PDE。

本文回答一个比“把当前 13.5 nm 参数改成 0.7 nm”更严格的问题：如果结构几何还会做小幅
调整，在保持直接法的前提下，哪些压缩路线有机会把最终作业控制在 2 TB 内，哪些路线已经
被仓库证据否定或尚无资格放大，以及每条路线最小应该先做什么实验。

这里的 `direct-only` 允许：

- 稀疏或稠密 LU/LDL 类直接分解与回代；
- assembly-time static condensation、局部 Schur 消元和 block-Schur recursion；
- HSS/HODLR/H-matrix 等压缩矩阵的直接分解；
- 为构造端口空间而做的小型 SVD、QR、广义本征问题和固定批次 multi-RHS direct solve；
- 在原始未压缩 operator 上重算 full explicit residual。

它不允许：

- 把 global PDE 改成 FGMRES/GMRES/Krylov；
- 用 iterative refinement、动态放宽容差或自动重试把失败 factor 包装为成功；
- 只验证压缩矩阵自身 residual，而不回到原始 Maxwell operator；
- 因为某个 ROM 在训练 source 上闭合，就省略跨几何或跨 operator 验证。

> 总结：在当前证据下，最可信的 direct-only 组合不是单一算法，而是
> **局部高保真 3D FE 端部 + localized transfer-optimal joint-Cauchy port +
> 分布式中间 modal/RCWA core + 分层低秩直接分解 + 多级静态凝聚组织**。
> 若真实结构严格保持 y-invariant，则 2D/2.5D-RCWA 应前移为最高优先级分支。

---

## 1. 当前仓库已经证明和没有证明的内容

### 1.1 证据总表

| 结论 | 状态 | 数据身份 | 证据位置 |
|---|---|---|---|
| full FE-trace direct Hybrid 能处理 grazing/P | pass | measured，13.5 nm | `docs/task036_forward_solver_bugfix_hardening/response_v6.md:73-111` |
| A007-P exact Hybrid 比 Full3D 低约 7.08% wall、18.02% peak | pass | measured，同源码 watchdog | `docs/task036_forward_solver_bugfix_hardening/response_v6.md:83-98` |
| 原始 M120/M240 不能恢复全部通道 | controlled negative | measured，历史同源 direct | `docs/task036_forward_solver_bugfix_hardening/response_v6.md:115-129` |
| M120 selected core 内传播 action 正确 | retain | measured，exact FE 对照约 `2e-11` | `docs/task036_forward_solver_bugfix_hardening/outcomes/exact_cauchy_port_operator_audit.md:8-22,110-129` |
| 缺失空间主要在端部 joint-Cauchy，traction 比 electric 更差 | root-cause evidence | measured，frozen Full3D replay + exact weak conormal | `docs/task036_forward_solver_bugfix_hardening/outcomes/exact_cauchy_port_operator_audit.md:50-108` |
| B1 discrete-Bloch `d_port<=360` | controlled negative | measured，best-trial residual约 `8.89e-5` | `docs/task036_forward_solver_bugfix_hardening/response_v6.md:159-203` |
| C1 paired reachable-source POD | incomplete / cancelled；C1b `not_run` | pure fixture；live teacher授权已撤销 | `docs/task036_forward_solver_bugfix_hardening/review_report_v8.md:15-24,60-61` |
| C1 正结果可跨几何复用 | 未证明，且当前定义不支持该表述 | review decision | `docs/task036_forward_solver_bugfix_hardening/review_report_v7.md:792-824` |
| 0.7 nm modal planning floor | `16029 modes/direction` | derived，generic横截面传播级估算 | `docs/task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md:35-60` |
| 0.7 nm 当前机械布局 | 不可行 | predicted proxy，不是实测 RSS | `docs/task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md:75-97` |
| 2 TB 生产设计线 | whole-job约 `1.5 TiB`，2 TiB硬顶 | engineering budget | `docs/task036_forward_solver_bugfix_hardening/code_audit_and_0p7nm_roadmap_report.md:617-646` |

### 1.2 本轮 fresh 四算例证据

本轮在同一源码 `ff2227cac8a19bd3a4c66279a413f6a34d730098` 上重新运行了两个
Full3D direct 与两个原始 Hybrid M120 direct。这里“原始 Hybrid M120”指当前 selected
scalar-CG 原有 lane，不是更早 continuous-symbol 旧 bug 版。权威 artifact root 为：

`benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/`

Full3D与Hybrid runner冻结的live memory authority不同：Full3D使用
`max_process_tree_rss_mb`，Hybrid使用 `simultaneous_live_worker_rss_sum_bytes`，且
dedicated cgroup=false。因此下表内存高低只表示各runner冻结authority的配对比较，不得改写为
统一的process-tree或whole-job peak。

| case / direct run | frozen live authority / peak | 全通道对照 | 结论 |
|---|---:|---:|---|
| D005-S Full3D | `max_process_tree_rss_mb`: `20.352 GiB` | reference | fresh control reference |
| D005-S original Hybrid M120 | `simultaneous_live_worker_rss_sum_bytes`: `9.708 GiB` | M120下 `80/80` numerical/formal pass | `qualification.physical_field_gates_pass=true`；`qualification.integration_pass=true`；但 `qualification.mode_count_converged=false`、`qualification.physical_augmented_direct_pass=false`、`qualification.official_record=false`，状态为 `rank_pending_next_m`；M120物理场Gate通过，但相邻M与production资格未完成；按冻结authority配对低于Full3D |
| D001-P Full3D | `max_process_tree_rss_mb`: `18.790 GiB` | reference | fresh grazing/P reference |
| D001-P original Hybrid M120 | `simultaneous_live_worker_rss_sum_bytes`: `9.569 GiB` | `66/80` pass | 按冻结authority配对较低，但数值不合格 |

D001-P并不是“总量略有误差”这么简单：sampled physical interface-E relative error为
`0.18222`，signed energy closure为 `-1.3067e-5`；80个通道中有14个complex-amplitude
fail，其中8个同时power fail。这说明M120可以在ordinary control上工作，却不是对照明条件稳健的
通用端口；这两组fresh case本身也没有提供跨几何稳健性证明。因此后续不能用D005-S的80/80
外推几何微调，而必须采用**局部端口富化 + 预冻结的照明/几何全通道holdout**路线。

四次运行的完整口径、Gate与误述边界见
[四次运行主报告](./p6_h10_full3d_vs_original_m120_four_run_report.md)；160行Full3D-vs-Hybrid
通道比较保存在[逐通道CSV](./p6_h10_full3d_vs_original_m120_all_channels.csv)，登记入口见
[开发模型登记表](../../development_model_registry.md)。本文只引用结论，不复制逐通道记录。

### 1.3 最重要的物理与数值解释

完整 1200 维 FE trace-chain 在五个最担心的 grazing/P 点恢复 Full3D，说明以下对象已经通过
原则性验证：

```text
Maxwell 方程
    + Full3D/Hybrid 域分区
    + Floquet/orientation
    + direct Schur 消元
    + full field recovery / channels / R/T/A
```

因此问题不是“Hybrid 原理在掠射 P 偏振下失效”，而是**低维接口空间没有覆盖真实端部的
联合电场/磁牵引信息**。仓库证据同时表明：

- 中间 selected M120 core operator 已经健康；
- 端点 electric projection residual约为 `1e-6`，joint-Cauchy/traction约为 `1e-5`；
- 中心区域可下降到约 `1e-10`；
- M120 增到 M240 几乎不改善；
- 用另一批 discrete-Bloch 模式扩到总维数360仍只把 best-trial residual改善约5%。

这直接支持“中间 core 保留、额外富空间局部化到端部”的架构，也直接反对继续全局增加同类
QEP/Bloch 模式。

### 1.4 exact FE trace 为什么只能当老师算子

13.5 nm p5/h10 exact chain 具有：

```text
11 trace planes
1200 active rows / plane
13200 global trace rows
31 x 1200^2 = 44,640,000 stored complex block entries
```

它在 A007-P 上的 peak 从 Full3D 的 `9.398 GiB` 降到 `7.705 GiB`，只节省约18%。静态凝聚
减少了行数，却把 separator/trace block 变稠密。因此 exact chain 是正确性 oracle，不是把
横向 trace dimension机械放大到0.7 nm的生产方案。

---

## 2. 先区分“几何微调”和“大范围几何变化”

### 2.1 冻结定义

| 类别 | 允许变化 | 可以有条件复用 | 不得直接复用 |
|---|---|---|---|
| G0：同 operator 多 RHS | 几何、材料、波长、Floquet phase、mesh全部不变，只改变入射 source coefficient | 数值 factor、端口 basis、symbolic结构 | 无 |
| G1：几何微调 | 宽度、高度、sidewall angle、局部界面位置的小幅连续变化；拓扑、材料区数量、周期关系、端口定义不变 | reference mesh/ALE map、DoF拓扑、symbolic factor graph、cluster tree、source identity；通过验证后可复用 parameter-local port span | numerical LU factors、fixed global ROM、旧 joint-Cauchy metric 和旧 rank 结论 |
| G2：同拓扑中等变化 | 参数仍连续但跨越较大范围，可能显著改变共振、Rayleigh邻域或材料体积分数 | 代码架构、分区策略、参数训练流程 | 旧 basis、旧 rank、旧资源外推 |
| G3：大范围/拓扑变化 | 新孔洞/接触、材料区增删、周期或cell count变化、y-invariance被破坏、接口顺序变化 | 只有通用 solver和物理合同 | mesh map、cluster tree、port basis、ROM、数值 factor及大部分旧capacity结论 |

“变化幅度小”不自动等于 G1。在 Rayleigh 临界、grazing incidence、局部共振或吸收边附近，
很小的几何变化也可能引起大的相位、通道开闭或条件数变化；这种点在验证上按 G2 处理。

### 2.2 对研发路线的影响

- G0 可以从 fixed-operator ROM 或 factor reuse 中获得最大收益。
- G1 最适合复用 symbolic partition、H-matrix cluster tree和**局部参数化 port space**，但每个
  几何仍需数值 residual/observable资格化。
- G2 必须在参数训练之外冻结独立几何 holdout，并重新选择 rank。
- G3 必须视为新 operator family；不得把 G1 的 ROM 稍作插值就称为 reference solver。

---

## 3. 0.7 nm 量级估算及其正确解释

### 3.1 冻结假设

仓库现有 mechanical projection 使用：

```text
lambda                 = 0.7 nm
period Lx x Ly         = 50 nm x 25 nm
local thickness        = 20 nm
uniform h proxy        = 0.1 nm
mode safety multiplier = 3.7
MPI proxy              = 4
complex scalar         = complex128
```

它用于证明当前显式布局不可行，不是未来优化 solver 的内存预测，也不是 continuum convergence
证明。

### 3.2 derived 与 predicted 不得混称

| 数值 | 值 | 身份 | 含义/限制 |
|---|---:|---|---|
| generic reciprocal orders | `8014.3` | derived | `pi Lx Ly / lambda^2` |
| two-pol modes/direction floor | `16028.5`，取整约 `16029` | derived planning floor | 只含传播级量级，不含 evanescent buffer |
| mechanical retained modes/direction | `59306` | predicted stress illustration | floor乘13.5 nm历史倍率3.7；不是数学下界或converged M |
| internal modal amplitudes | `118612` | derived from stress illustration | `2M` |
| local FE rows | 约 `9.23e8` | predicted mechanical proxy | 由旧h3行数按 `h^-3` 与厚度机械缩放；未含可靠h/p自适应 |
| one stress-case complex `(2M)^2` | `225.10 GB`，约 `209.64 GiB` | derived payload | 只是一份稠密方阵，不含LU副本和workspace |
| four squares replicated over MPI4 | `3.60 TB` | predicted current layout | 暴露复制问题，不代表分布式新实现 |
| all-mode dense multi-RHS | `1,754,383,058,208,000 bytes`，约 `1595.6 TiB` | predicted payload proxy | `Nlocal x (2M+1) x 16 bytes`；排除factor、mesh和其他对象 |
| cumulative explicit-object volume | 约 `1611.3 TiB` | predicted volume | 对象未必同时存在；不得称为simultaneous RSS |

作为附加量级检查，若只采用 planning floor `M=16029/direction`，一份
`(2M)^2 complex128` 方阵约为：

```text
(2 x 16029)^2 x 16 bytes = 15.31 GiB
```

这说明**modal小系统在floor附近并非单独就超过2 TB**；真正致命的是：多份/每rank复制的
`M^2`、`Nlocal x M` 全模态 RHS/solution、十亿级 local LU、全局 mode payload和生命周期重叠。
因此新路线必须同时做到 distributed ownership、blocked/streamed actions、局部化富空间和
压缩直接factor，而不能只替换一个对象。

### 3.3 2 TB 口径

本文沿用仓库预算中的：

```text
preferred whole-job design line = about 1.5 TiB
hard ceiling                    = 2 TiB
swap                            = 0
```

2 TiB不能全部借给factor。约25%的余量需要覆盖OS、MPI、allocator波动、mesh/DoF、postprocess、
失败清理和采样误差。部署前还必须绑定机器给出的精确byte上限；若用户所说“2 TB”实际是十进制
2,000,000,000,000 bytes，则小于2 TiB，所有 Gate 必须按真实bytes重算。

---

## 4. direct-only 路线总览与优先级

### 4.1 推荐组合架构

```text
physical DtN / incoming channels
        |
local high-fidelity 3D FE endcap
        |
localized transfer-optimal joint-Cauchy port
        |
distributed modal or RCWA middle core
        |
localized transfer-optimal joint-Cauchy port
        |
local high-fidelity 3D FE endcap

all local/separator solves:
multilevel static condensation
        +
HSS/H-matrix compressed direct factorization where rank audit permits
```

### 4.2 优先级表

| 优先级 | 路线 | 当前证据强度 | 几何微调适配 | direct-only适配 | 决定 |
|---:|---|---|---|---|---|
| P0 | y-invariance / 2D/2.5D / RCWA symmetry Gate | 中；当前几何有潜在y不变性，尚无正式3D等价证明 | 若微调保持不变性则很高 | 是 | 先证明或否定；通过则升为第一主线 |
| P1 | local rich ends + retained middle core | 强；端部缺失、中间core健康已有实测 | 高，尤其变化局限在端部/局部材料 | 是 | 总体主架构 |
| P1 | localized operator-optimal/transfer port | 中；理论设计与根因吻合，尚无actual candidate | 中高；每几何重算或构造参数鲁棒局部space | 是 | 当前最值得做的最小rank实验 |
| P2 | HSS/HODLR/H-matrix/directional direct compression | 弱；仓库尚无空间块秩实测 | 中高；可复用cluster/symbolic tree | 是 | 先做rank audit，不先造完整framework |
| P2支撑 | domain decomposition / multilevel static condensation | 强于exactness，弱于scalability | 高；局部变化可限制re-factor范围 | 是 | 只作组织骨架，不能单独称压缩成功 |
| P3条件 | RCWA-FE coupling | 仓库无正式耦合证据 | 规则层状/挤出几何高；generic 3D低 | 是 | y-invariant时前移，否则作core/独立参考 |
| P4 | geometry-parametric offline/online local port | 无跨operator证据 | 仅G1/G2有条件适用 | online可direct | 单几何可扩展solver建立后再做 |
| 不推进 | fixed global C1 ROM作为几何通用solver | 明确边界反对 | 低 | direct reduced solve本身是，但offline不解决新几何 | 仅保留G0 multi-RHS诊断价值 |

---

## 5. P0：y-invariance / 2.5D / RCWA 条件分支

### 5.1 通俗解释

如果结构、材料和允许的几何微调沿 y 方向完全不变，就没有必要在 y 方向重复离散同样的物理。
2D/2.5D 或一维 Fourier harmonics 可以把三维体问题拆成更小的耦合截面问题。这不是“少算一点
网格”，而是消除一个空间维度，因而是最可能真正改变0.7 nm数量级的步骤。

但 `grating_width_y == period_y` 只能说明当前配置看起来可能y不变，不能自动证明：

- 入射相位、材料、粗糙度和未来微调都保持y不变；
- conical incidence 下 S/P 或 Fourier sectors按预期耦合；
- n=0 alias、traction、A_volume和所有传播衍射级与3D一致。

### 5.2 最小前置实验

| 项目 | 最小内容 |
|---|---|
| geometry contract | 冻结所有允许参数，逐项声明是否保持y-invariance |
| 13.5 nm anchor | 对一个基准和至少两个G1微调点做小型3D direct vs 2D/2.5D/RCWA对照 |
| channel contract | S/P、零级与全部显著非零级、R/T/A、`A_volume`、closure |
| interface contract | canonical E、weak traction、DtN power completeness |
| next scale | 只有13.5 nm通过后，做5 nm order-convergence和资源投影 |

### 5.3 通过 Gate

- y-dependent material/geometry coefficient在冻结合同下严格为零或有可证明的sector分解；
- 2D/2.5D 与3D anchor的full observable vector通过当前Task036通道合同；
- interface electric/traction/action error `<=1e-8`；
- energy closure `<=1e-5`，并包含全部传播级；
- RCWA/Fourier order收敛和Rayleigh warning均有明确记录；
- projected 0.7 nm whole-job peak `<=1.5 TiB`。

### 5.4 停止条件

- 任一目标微调破坏y-invariance；
- 只能对零级或展示通道闭合；
- Fourier order增加后traction/action不收敛；
- dense layer eigen/factor、matching或FE coupling预测越过1.5 TiB；
- 需要用人工S/P解耦或删除Rayleigh临界级才能通过。

### 5.5 预期产物

- `geometry_symmetry_contract`；
- 3D-vs-2.5D全通道表；
- Fourier/order convergence表；
- 13.5/5/2/1/0.7资源模型；
- 明确的 `symmetry_route_pass` 或 `generic_3d_required`。

---

## 6. P1：局部端部富空间 + 中间 core

### 6.1 为什么它最符合现有证据

实测缺失空间集中在 `z=10/110 nm` 附近，selected M120 core 在40/60/100 nm内部已与exact FE
operator一致约 `2e-11`。因此合理分工是：

- 中间规则区只保留所有真实传播模和必要长程衰减模；
- extra evanescent、材料边缘和几何敏感方向只存在于短端部buffer；
- 端部富空间在buffer/core接口被local Schur消元；
- global unknown不再包含完整端部trace或跨100 nm的global corrector。

0.7 nm时这里的“core”绝不再等于固定M120。每一级波长都必须重新确定全部传播级和M/rank，
`16029 modes/direction` 是generic planning floor，不是可随意压缩掉的对象。

### 6.2 几何变化适配

| 变化位置 | 处理原则 |
|---|---|
| 只改变bottom/top局部几何 | core可有条件复用；只重建受影响endcap和local port |
| 改变整个z-uniform横截面 | modal/RCWA core必须重建；架构可复用，数值basis不可直接复用 |
| 改变cell count/中间长度 | 传播factor和global composition重建；不得复用fixed-length C1 mode |
| 拓扑变化 | 新mesh、新operator family、新rank和资源qualification |

### 6.3 最小前置实验

1. 保留13.5 nm exact FE trace作为teacher，不修改M120 core propagation。
2. 构造bottom/core/top三段，额外方向只放在端部短buffer。
3. 对基准几何、至少三个预冻结G1微调和一个接近Rayleigh/共振的G2点验证。
4. 对每点报告endpoint和11 planes的E/traction/joint residual、full action residual、全部通道。
5. 实测cold setup、local factors、composition、backsolve、recovery和postprocess峰值。

### 6.4 通过 Gate

- full explicit residual `<=1e-9`；
- endpoint/11-plane electric、traction、joint-Cauchy和action error `<=1e-8`；
- 所有Task036固定通道、R/T/A/`A_volume`通过；
- extra corrector只在冻结buffer内存在；
- same-input whole-job peak `<=0.70 x Full3D`，wall不高于Full3D，zero swap；
- 波长continuation资源外推 `<=1.5 TiB`。

`0.70 x Full3D` 是工程目标；如果只达到 `0.70--0.80`，只能进入工程review zone，不称最终修复。

### 6.5 停止条件

- 通过所需端口维数接近完整 `N_Gamma`，资源退化回exact trace；
- corrector必须跨越整个中间区，无法证明localization；
- geometry holdout中任一点失败；
- extra rank随波长或参数样本近似按完整trace维数线性增长；
- 任何阶段预测peak超过1.5 TiB。

### 6.6 预期产物

- end/core/end block和ownership表；
- corrector decay/localization曲线；
- geometry holdout全通道矩阵；
- rows/NNZ/factor-fill/whole-job资源表；
- selective merge时production core与research teacher清单。

---

## 7. P1：localized operator-optimal joint-Cauchy ports

### 7.1 与失败的B1/C1有什么不同

| 路线 | basis来自哪里 | 是否局部 | 当前结论 |
|---|---|---|---|
| 原始M120/M240 | physical-QEP global modes | 否 | 受控失败 |
| B1 discrete-Bloch pool | one-cell Bloch right/adjoint columns | 设计上想局部，但实际trial capacity不足 | `d<=360`受控失败 |
| C1 paired response POD | fixed operator的96 source global responses | 否，两端共享系数并含11-plane extension | scaffold；即使正也只属fixed global ROM |
| transfer-optimal port | 短buffer source到core-facing joint-Cauchy的transfer operator | 是 | 根因吻合，尚未有actual candidate |

transfer-optimal port用一个问题选择basis：外部source经过短端部后，哪些联合E/traction方向最能
传到core-facing接口。它不按单个失败通道加专用mode，也不把任意one-cell Bloch mode当作有用
corrector。

### 7.2 最小前置实验

| 步骤 | 内容 |
|---:|---|
| T1 | 在13.5 nm frozen exact buffer上构造source metric和joint-Cauchy output metric |
| T2 | source覆盖全部传播incoming companions、必要evanescent buffer和冻结cut loads |
| T3 | 投影掉健康的middle core，计算complement transfer singular tail |
| T4 | rank在看holdout前冻结；报告 `r=0/20/40/...`，不运行后调参 |
| T5 | 同operator source holdout后，再做预冻结geometry/operator holdout |
| T6 | 仅当capacity通过，构造actual reduced direct candidate并重算full residual/observable |

实现可使用local direct factor、固定批次multi-RHS direct action和小型SVD/QR；不得因此引入global
Krylov PDE solver。

### 7.3 通过 Gate

- mass/Hermitian/SPD、bottom/top orientation、incoming direct term和weighted-adjoint identity通过；
- joint-Cauchy decoder、Gram和inf-sup通过冻结容差；
- singular tail、geometry holdout endpoint/action error均 `<=1e-8`；
- first passing rank明显低于完整trace并满足资源模型；
- local Schur后无global `M_total^2`、无resident `N_Gamma x r`大块；
- actual direct candidate满足第6.4节的full solver和资源Gate。

### 7.4 停止条件

- tail只有在接近完整端口rank时才到 `1e-8`；
- source/RHS Gram秩亏且不能在明确商空间中解释；
- geometry holdout需要把holdout重新加入basis才通过；
- inf-sup/Petrov rank退化；
- 端部mode不衰减或需要进入整个core；
- rank/resource外推超过1.5 TiB。

### 7.5 预期产物

- bottom/top singular spectrum和cumulative tail；
- first passing rank及其预冻结身份；
- core complement、Gram、inf-sup、decoder表；
- geometry/operator holdout误差矩阵；
- local Schur rows/NNZ/peak/wall ledger。

---

## 8. P2：HSS/HODLR/H-matrix/directional 分层直接压缩

### 8.1 通俗解释

exact Schur block虽然在数组上是稠密的，但相距较远的表面自由度之间的相互作用可能只需要少量
共同方向表示。如果这种off-diagonal rank明显小于block size，就可以只保存低秩因子，并对压缩
矩阵做近似LU，再用**原始未压缩operator**检查解。

这仍是直接法：一次压缩factor加一次backsolve；但factor是近似的，所以它只有通过原operator的
full residual和全部observable后才有资格称成功。

### 8.2 方法内部优先顺序

| 方法 | 角色 | 风险 |
|---|---|---|
| HODLR | 最快的binary rank probe或小型prototype | weak admissibility在高频下rank容易偏高；不建议直接当最终架构 |
| HSS | frontal matrix/trace block的nested basis | non-Hermitian pivoting和rank growth需实测 |
| geometry-aware H-matrix | 近场保留稠密、远场strong admissibility压缩 | 实现和并行factor复杂，但比纯HODLR更适合几何separator |
| directional H/H2或butterfly | 0.7 nm高频振荡下的后备 | 研发成本最高；仅在普通HSS/H-matrix rank audit失败但呈方向性可压缩时授权 |

### 8.3 最小前置实验

不运行新PDE，先复用现有 `1200 x 1200` exact trace/Schur blocks：

1. 按端面几何坐标构造cluster tree。
2. 对不同距离、方向和block层级报告 `1e-6/1e-8/1e-10` numerical rank。
3. 至少覆盖一个ordinary、一个grazing-P和一个几何微调operator。
4. 做一次compressed block-Schur/LU replay。
5. 用原始exact action重算backward error、full trace residual和全部通道。
6. 再增加一档横向分辨率，测rank随N和电尺寸增长，而不是只报固定N压缩比。

### 8.4 通过 Gate

- admissible ranks明显低于block size且随N次线性增长；
- 压缩存储和factor peak相对dense exact trace有可重复优势；
- original-operator full residual `<=1e-9`；
- operator/action compression error `<=1e-8`；
- grazing/P和geometry holdout通过完整observable contract；
- continuation外推peak `<=1.5 TiB`，zero swap。

### 8.5 停止条件

- rank/block-size比不下降，或rank近似随电尺寸线性增长；
- Maxwell非自伴pivoting破坏层次结构或导致不受控fill；
- 需要自动反复收紧容差/重试factor才通过；
- 只在压缩operator自身残差通过，原operator residual失败；
- 两档加密外推超过1.5 TiB；
- compression build wall超过未压缩direct且没有multi-RHS摊销场景。

### 8.6 预期产物

- spatial off-diagonal rank heatmap；
- rank-vs-N、rank-vs-wavelength、rank-vs-geometry表；
- compressed storage/factor/backsolve ledger；
- original-operator residual和通道对照；
- `standard_hierarchical_pass`、`directional_probe_needed`或`hierarchical_rank_not_demonstrated`。

---

## 9. 多级静态凝聚和域分解：只能作组织骨架

### 9.1 已有信用

仓库已证明 assembly-time static condensation与standard exact matrix等价，并证明full FE trace
domain decomposition能恢复Full3D。这给多级消元提供了正确性基础。

### 9.2 为什么它不能单独解决2 TB

静态凝聚消去体内部DoF后，会把相互作用推到separator。一级exact trace在13.5 nm已经表现为
`31 x 1200^2`稠密block，仅节省约18% whole-job peak。若0.7 nm只是增加更多子域但仍以dense
separator LU结束，内存问题只是从volume matrix转移到interface fronts。

### 9.3 最小前置实验与 Gate

| 项目 | 要求 |
|---|---|
| partition | 当前exact case做2/4/8子域或两级separator tree |
| measured | 每级separator rows、front NNZ、fill、factor peak、backsolve wall |
| equivalence | full/static/multilevel operator action `<=1e-10`，full residual `<=1e-9` |
| comparison | 同一partition分别测dense separator与HSS/H-matrix separator |
| geometry update | 一个局部微调点，报告真正需要re-factor的subtree范围 |

停止条件：separator fill随加密超线性失控、局部微调触发几乎全树重分解、或资源外推超过1.5 TiB。

预期产物：separator tree、ownership map、symbolic/numeric reuse边界、每层peak时间线，以及与分层
低秩组合后的资源模型。

---

## 10. RCWA-FE coupling：条件性高价值路线

### 10.1 适用场景

RCWA/Fourier modal core适合：

- z分层或规则extrusion；
- 横向周期材料能被Fourier convolution可靠表示；
- 几何微调主要是宽度、高度、层厚等参数；
- irregular 3D corner/endcap只占局部区域，并交给FE处理。

它的优势是参数变化通常不需要完整3D remesh，并天然组织大量衍射级。它的风险是：不连续高对比
材料的Fourier convergence、Rayleigh临界级、dense layer eigensolve和FE/RCWA traction matching。

### 10.2 最小前置实验

1. 先完成第5节y-invariance Gate。
2. 在13.5 nm和小型3D exact anchor上做RCWA order funnel。
3. 同时比较interface E、weak traction、power和全部通道，不只比较R00。
4. 对至少三个G1几何微调点重复order convergence。
5. 接入一个local FE endcap，验证FE-RCWA joint-Cauchy/action。
6. 只在13.5 nm通过后进入5 nm。

### 10.3 通过 Gate与停止条件

通过：所有传播级完整、Rayleigh专项通过、interface/action `<=1e-8`、observable contract通过、
direct layer factor和coupling整体外推 `<=1.5 TiB`。

停止：y-invariance或layer/extrusion假设不成立，Fourier order增长仍不收敛，dense eigen/matching
越过资源线，或FE-RCWA traction无法闭合。

预期产物：RCWA order spectrum、3D anchor对照、geometry funnel、coupling action residual和
direct factor资源表。若该路线失败，RCWA仍可保留为独立小模型参考，不得冒充generic 3D solver。

---

## 11. 几何参数化 offline-online：优先做 local port，不做 fixed global ROM

### 11.1 合理定位

参数化方法适合未来反演/优化中反复求解许多相近几何，但它不能在尚无可扩展0.7 nm reference
solver时凭空产生可靠训练数据。正确顺序是：先建立单几何可扩展direct solver，再研究如何摊薄
重复几何的成本。

建议对象是：

```text
parameter-robust localized port spaces
    + reusable symbolic/cluster structures
    + per-geometry compressed direct numeric factor
```

而不是一个覆盖整个bottom-to-top operator的共享global response basis。

### 11.2 最小前置实验

| 项目 | 最小内容 |
|---|---|
| parameter set | 1--3个真实G1几何参数，范围在运行前冻结 |
| mapping | common reference mesh/ALE和canonical trace identity |
| training | 5--9个预冻结geometry，分别构造local transfer-optimal modes |
| holdout | leave-one-geometry-out；不得把失败点加入basis后重报 |
| measurement | union rank、operator/action error、full residual、全部通道、offline/online资源 |
| topology | 一旦改变，立即转为新operator family |

### 11.3 通过 Gate

- holdout geometry的joint-Cauchy/action error `<=1e-8`；
- actual direct full residual `<=1e-9`；
- union rank随training geometries次线性增长并满足1.5 TiB模型；
- online无需重新生成full-orderglobal teacher；
- local factor/basis更新范围与几何局部性一致。

### 11.4 停止条件

- union rank近似随样本数线性增长并逼近完整trace；
- topology、Floquet sector或channel set变化；
- holdout需要在线追加snapshot才能通过；
- 每个新几何仍需完整0.7 nm Full3D/exact-trace factor；
- offline training总资源超过直接逐点求解且没有足够重复RHS/geometry摊销。

### 11.5 预期产物

- geometry parameter contract和training/holdout split；
- parameter-local port rank surface；
- cross-geometry operator/error matrix；
- offline build与online direct solve成本分解；
- topology-change fail-closed规则。

---

## 12. 为什么 fixed global ROM 不适合几何微调

### 12.1 当前C1对象的真实身份

Review V7曾把C1b的可能输出严格限定为：

```text
fixed_operator_fixed_length_paired_response_ROM
```

Review V8现已撤销该运行授权，C1b状态为 `cancelled/not_run`；以下只解释历史方案的对象身份，
不是当前诊断或执行计划。

它绑定：

- wavelength、material；
- `kx/ky` 与Floquet phase；
- p/h/Ny与trace row identity；
- `cell_count=10`和固定11个trace planes；
- bottom/top endcap、DtN、geometry和接口位置；
- source/order policy。

而且C1一列basis由bottom/top共享同一coefficient并包含完整11-plane harmonic extension，是
nonlocal paired response mode，不是可单独更新的bottom/top local corrector。

### 12.2 几何变化为什么产生旧source span之外的新方向

固定几何满足：

```math
K(\mu)u(\mu)=B(\mu)c.
```

几何变化后的参数敏感性包含：

```math
\frac{\partial u}{\partial\mu}
=K(\mu)^{-1}\left(
\frac{\partial B}{\partial\mu}c
-\frac{\partial K}{\partial\mu}u
\right).
```

即使旧96个source response完整覆盖固定 `K^{-1}B`，`K^{-1}(dK/dmu)u` 也不必在该span内。
grazing、Rayleigh和局部共振附近，这个新方向可能对很小的几何变化非常敏感。

### 12.3 固定global ROM的具体不足

| 不足 | 后果 |
|---|---|
| operator、source、metric、DtN和mesh map同时随几何变化 | 旧basis的orthogonality、decoder和residual信用失效 |
| global mode不可局部更新 | 一个局部几何微调也可能要求重建整个11-plane basis |
| 13.5 nm source rank不约束0.7 nm传播rank | 不能把 `r<=80/96` 外推到16029-mode floor |
| 新geometry仍需full-orderteacher/factor | 没有解决第一次0.7 nm求解的2 TB问题 |
| 无cross-operator estimator/canonical map | 训练误差不能转为正式Maxwell结果 |
| r等于training source rank时闭合是构造结果 | `r=80`或96训练通过不等于快速谱衰减 |

C1b已由V8撤销授权并冻结为 `cancelled/not_run`，当前不得作为诊断运行。若未来另一个新任务
独立授权同类fixed-operator多RHS诊断，则即使在 `r=20/40/60` 对预冻结holdout通过，也只说明
同一operator的source response有压缩潜力；若只在training ceiling `r=80`通过，则只获得固定
source-space信用，不获得几何鲁棒或localized-port信用。

---

## 13. 明确不应继续的 direct 路线

| 路线 | 判定 | 原因 |
|---|---|---|
| 当前whole-domain Full3D direct机械加密到0.7 nm | 不可行 | 数十亿DoF及direct fill预计进入数TiB至数十TiB |
| 当前exact FE-trace dense chain机械放大 | 不可行 | separator/Schur block为dense，13.5 nm只节省约18% |
| 当前Hybrid显式all-mode RHS和每rank复制M² | 不可行 | 1595.6 TiB payload proxy、复制方阵和owner集中 |
| 继续M120→M240→M480式global mode扩张 | 已有负证据，不推进 | M120→M240几乎不改善通道和主误差 |
| 继续B1同一v9 pool、改阈值或d>360 | 禁止 | best-trial lower bound已经失败，不是Petrov阈值问题 |
| static condensation单独作为2 TB答案 | 不成立 | 消去volume后把fill推到separator；必须叠加port/hierarchical compression |
| fixed global C1 ROM覆盖几何变化 | 不成立 | fixed operator/fixed length/nonlocal，缺少cross-operator信用 |
| zero-order DtN | 物理不完整 | 0.7 nm存在大量传播衍射级，代数收敛也不能代表开放边界正确 |
| OOC或单纯增加MPI ranks | 不解决算法复杂度 | 不能消除复制M²、all-mode RHS或十亿级local LU |

---

## 14. 逐级 continuation，而不是直接跳到0.7 nm

### 14.1 总流程

| 阶段 | 主要目的 | 必须重新冻结 | 允许的direct anchor | 进入下一阶段条件 |
|---:|---|---|---|---|
| 13.5 nm | 完成compressed direct Hybrid正确性与geometry holdout | port rank、H-rank、buffer、mesh、全部通道 | Full3D + exact trace | actual candidate全部Gate通过，peak目标满足 |
| 5 nm | 检查模式数、衍射级、材料和rank增长 | material、DtN orders、M/r、h/p、cluster ranks | 小型Full3D/2.5D/RCWA交叉参考 | measured+predicted peak有明显余量 |
| 2 nm | 验证高频hierarchical/directional必要性 | 同上，特别是off-diagonal rank | 缩小横向/简化几何direct anchor | rank/peak增长仍符合1.5 TiB envelope |
| 1 nm | 0.7 nm前最后资源校准 | 所有object lifecycle和factor fill | 仅资源允许的小anchor | projected 0.7 peak `<=1.5 TiB`且不靠乐观外推 |
| 0.7 nm | 正式目标 | canonical material/geometry/source/mesh/rank/factor合同 | 经过Gate的direct组合solver | full residual、全部传播级、R/T/A/volume、资源全部通过 |

### 14.2 每一级共同 Gate

1. 材料数据与波长绑定，禁止复用13.5 nm折射率。
2. 所有传播级、Rayleigh warning和evanescent buffer完整。
3. full explicit true residual `<=1e-9`。
4. interface E/traction/joint-Cauchy/action `<=1e-8`。
5. 全部显著与弱通道按同一合同通过。
6. R/T/A、`A_volume`、closure和passivity/reciprocity适用项通过。
7. 基准几何和预冻结G1/G2 holdout通过；不得运行后移动失败点。
8. simultaneous process-tree/cgroup peak、PSS/USS、swap、OOC scratch和阶段wall有权威记录。
9. factor前预测peak `<=1.5 TiB`；2 TiB为controlled-stop硬顶，zero swap。
10. ordinary default和迭代路径保持不变。

### 14.3 资源停止规则

- 任一中间波长已经预测超过1.5 TiB：不进入更短波长。
- 1 nm未形成可信rank/fill scaling law：不启动0.7 nm。
- factor setup峰值进入硬顶区：终止完整进程组，记 `controlled_stop`。
- factor仍存活时禁止同时生成全域DG/PyVista多份场；postprocess必须流式并单独Gate。
- 资源stop不等于数值方法失败，但也不能写成可行。

---

## 15. 最小实验计划、通过条件和预期产物

| ID | 实验 | 是否新PDE | 通过条件 | 失败后动作 | 产物 |
|---|---|---|---|---|---|
| E0 | geometry G0/G1/G2/G3与y-invariance合同 | 否 | 参数范围、拓扑、材料、Rayleigh风险可审计 | 合同不完整则停止所有0.7外推 | geometry contract |
| E1 | existing exact trace spatial rank audit | 否 | HSS/H-matrix ranks呈次线性、原operator replay通过 | 冻结普通HSS/HODLR，必要时只提directional probe | rank heatmap/ledger |
| E2 | localized transfer-optimal port capacity | 仅允许一次受控13.5 teacher/action批次 | geometry/source holdout、joint/action `<=1e-8` | rank近full或holdout失败则停止该family | spectrum/holdout/Schur ledger |
| E3 | actual 13.5 nm compressed direct candidate | 是，单heavy case后小型holdout矩阵 | full residual、全部通道、peak/wall通过 | 不调参重跑；写负结论并回到E1/E2审查 | solver record/whole-job resource |
| E4 | 2.5D/RCWA branch | 条件性小anchor | 3D等价、order convergence、geometry holdout通过 | symmetry失败则回generic 3D架构 | 3D-vs-RCWA authority |
| E5 | wavelength continuation | 每级最多一个主anchor加预冻结必要holdout | 当前波长全部数值/资源Gate通过 | 停在当前波长，不跳级 | per-wavelength qualification pack |
| E6 | parameter-local port offline/online | 仅在E3和至少一个短波长通过后 | leave-one-geometry-out通过，union rank次线性 | 冻结参数ROM，不影响single-geometry solver | parameter rank/error/cost surface |

所有实验都必须预先冻结输入、rank列表、holdout和stop条件。不得通过“运行失败→加入困难snapshot→
再宣布通过”的循环把研究变成无止境自动调参。

---

## 16. 推荐执行顺序

以下P0/P1/P2只是未来条件性顺序：只有用户在**新任务**中重新明确授权direct-only研究后才可
实施。当前所有步骤均不得启动，尤其不得在Task036运行teacher/direct-port research、actual
candidate或任何新PDE。

```text
P0-0  冻结0.7 nm材料、完整传播级和几何参数范围
P0-1  证明或否定y-invariance / 2.5D-RCWA
P1-0  用现有13.5 nm exact blocks做HSS/H-matrix rank audit
P1-1  做localized transfer-optimal joint-Cauchy capacity
P1-2  组合local rich ends + compressed direct separators + distributed core
P1-3  只做一个13.5 nm actual direct candidate和预冻结geometry holdout
P2    13.5 -> 5 -> 2 -> 1 -> 0.7 nm逐级资格化
P3    single-geometry路线稳定后，才做parameter-local offline/online
```

`C1b = cancelled/not_run`，不在该条件序列中；B1则已由best-trial负证据正式冻结，不再投入。

---

## 17. 最终判断

| 问题 | 当前回答 |
|---|---|
| 0.7 nm / 2 TB 是否已经解决 | **否** |
| 当前Full3D direct机械放大是否可行 | **否** |
| 当前显式Hybrid direct机械放大是否可行 | **否** |
| direct-only是否仍有条件路线 | **有条件的技术备选，但当前未授权；须在未来新任务重新授权并通过rank/geometry/continuation Gate** |
| 最优先的物理架构 | local rich 3D ends + middle core |
| 最优先的端口压缩 | localized transfer-optimal joint-Cauchy ports |
| 最优先的direct规模化审计 | geometry-aware HSS/H-matrix rank audit |
| 2.5D/RCWA角色 | y-invariance通过时升为最高优先级；否则为core或独立参考 |
| static condensation角色 | exact组织骨架，不是单独压缩答案 |
| fixed global ROM角色 | 同operator多RHS可用；几何微调主solver不适用 |
| 参数化路线 | local port + cross-geometry holdout；待单几何solver后启动 |
| 资源线 | 约1.5 TiB设计线，2 TiB硬顶，zero swap |
| V8 当前后续主线 | future Task037 matrix-free iterative planning；implementation尚未授权 |

若未来用户在新任务重新授权direct-only，首先应只用已有exact oracle回答两个便宜且决定性的问题：

1. 端部source→joint-Cauchy transfer在几何holdout下是否确实低秩；
2. exact Schur/front的空间off-diagonal block在高频增长前是否可被HSS/H-matrix稳定直接压缩。

只有这两个问题至少一个给出明确正结果，并在新任务另行授权的13.5 nm actual compressed direct
candidate上恢复全部通道，才有资格沿 `13.5→5→2→1→0.7 nm` 放大；当前不得启动该candidate。

按V8，当前后续主线是future Task037的matrix-free iterative planning，但Task037 implementation
尚未授权。本文direct路线只作为未来新任务备选，也不得用Task037规划追认当前direct压缩。
