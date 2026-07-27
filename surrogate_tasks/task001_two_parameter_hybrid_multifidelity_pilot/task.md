# Task001 任务书：两参数 Hybrid 多保真资格化与可辨识性 pilot

## 0. 权威、角色与硬边界

本任务由 ChatGPT 编写并审阅，Codex 在唯一执行分支上实施。开始前完整阅读：

1. 根目录 `AGENTS.md`；
2. `surrogate_tasks/AGENTS.md`；
3. `surrogate_tasks/task000_initialization/review_report_v1.md`；
4. Task000 `README.md`、`task.md`、`response_v1.md` 和全部 outcomes；
5. 本目录 `README.md` 与本任务书；
6. Case095/096 的显著通道、p6/h10 六路 authority 和 Hybrid runner 文档。

固定执行边界：

```text
branch = codex/only-one-13p5nm-surrogate-inversion
remote target = origin/codex/only-one-13p5nm-surrogate-inversion
hardware = local WSL2 laptop, nominal 16 GB host memory
max_parallel_forward_jobs = 1
bulk_generation = forbidden
surrogate_training = forbidden
production_inversion = forbidden
master / Task035d access = forbidden unless this task explicitly names a read-only tracked file
```

不得 merge/rebase/cherry-pick 其他分支，不得修改或运行工作站 Task035d 工作树，不得使用 Docker，不得通过 swap、MUMPS OOC、OOM kill 或放宽物理 Gate 强行完成高阶模型。

Task001 的任务不是“尽量多算”，而是回答五个问题：

1. 当前 clean source 上，哪一个本机 Hybrid 模型可作为 high fidelity？
2. 用户要求的 p6/h7.5 是否在安全内存内可完成？
3. 哪一个更便宜的 Hybrid 模型可作为 low fidelity？
4. 固定 13.5 nm 时，哪些角度、方位角和偏振能够把高度与宽度分开？
5. Task002 应生成哪些几何点、多少个物理 solve、保留哪些观测量？

---

## 1. 冻结物理问题与参数域

### 1.1 仅两个可反演参数

```text
h = grating_height_nm
w = grating_width_x_nm
```

名义点和第一版窄范围：

```text
h0 = 120.0 nm
w0 = 17.0 nm
h in [115.0, 125.0] nm
w in [16.0, 18.0] nm
```

所有输入必须使用 nm，并在 schema 中显式记录上下界、单位、默认值、是否可反演和 schema version。越界输入 fail closed，不得 clip。

### 1.2 固定物理量

```text
wavelength = 13.5 nm
period_x = 50 nm
period_y = 25 nm
grating_width_y = 25 nm
rectangular vertical sidewall
existing Si grating/substrate complex index
existing air/substrate extents and interface
Floquet x/y
no PML
auxiliary DtN, auto propagating
existing physical boundary-plane amplitude convention
```

Task001 不允许增加：侧壁角、上下宽度差、圆角、粗糙度、氧化层、材料折射率、波长、周期、入射强度尺度或其他反演参数。

### 1.3 候选照明

角度沿用当前代码约定：`incident_theta_deg` 是偏离向下法线的角度。

首轮候选：

```text
theta = [70.0, 80.0] degree
phi = [0.0, 90.0] degree
incident polarization = [s, p]
```

共 8 个 `(theta, phi, polarization)` 条件。只有在首轮没有任何组合通过可辨识性 Gate 时，才允许增加：

```text
theta = 75.0 degree
phi = [0.0, 90.0]
polarization = [s, p]
```

不得自动执行更密的角度扫描。

---

## 2. 固定模型候选

每个模型都必须调用现有 Hybrid/FEM 核心，不得在 `src/forward_data` 或 benchmark 中复制 Maxwell、QEP、modal coupling、DtN、静态凝聚、MUMPS 或后处理算法。

### 2.1 请求的 high-fidelity candidate：HF7P5

```text
model_id = hybrid_hf_p6_h7p5_m120
method = Hybrid static / memory-minimal Schur path used by Case096
Nedelec contract = p5 trace / p6 interior, nedelec_degree=6
mesh target = 7.5 nm
nominal structured plan expected from existing authority = [9, 4, 20]
modal count = M120
solver = qualified direct path
```

“p6/h7.5”在文档和用户界面中保留该简称，但正式 record 必须写清 `p5 trace / p6 interior exact-sequence` 的真实元素合同。

HF7P5 不是默认可运行模型。它必须先通过 M3 的资源预估；预估不安全时不得启动完整 PDE。

### 2.2 high-fidelity fallback：HF10

```text
model_id = hybrid_hf_p6_h10_m120
method = same Hybrid static / memory-minimal path
Nedelec contract = p5 trace / p6 interior, nedelec_degree=6
mesh target = 10.0 nm
nominal structured plan = [6, 3, 14]
modal count = M120
```

HF10 必须在当前 Task001 clean source 上重新运行 nominal formal sample，并与 Case096 tracked authority 比较。历史不同 source SHA 只能作为交叉参考，不能直接充当当前 formal sample。

### 2.3 primary low fidelity：LF4

```text
model_id = hybrid_lf_p4_h10_m120
Nedelec degree = 4
mesh target = 10.0 nm
modal count = M120
method = existing qualified Hybrid static/memory-minimal path when supported
```

如果现有 Hybrid static path 对 p4 不在明确资格范围内，则使用现有 Hybrid standard M120，并在模型身份中写明；不得为了强行得到 p4 static 而扩展未审阅数值核心。

### 2.4 fallback low fidelity：LF5

```text
model_id = hybrid_lf_p5_h10_m120
Nedelec degree = 5
mesh target = 10.0 nm
modal count = M120
```

只有 LF4 未通过 M4 的趋势/成本 Gate 时才运行 LF5 的完整 5 点资格化。

### 2.5 M160 的角色

M160 只允许作为 nominal modal-truncation cross-check，不是独立 fidelity，也不进入 Task001 pilot dataset。只有 M120 完整通过且仍有充足内存余量时才可运行一次 M160。

### 2.6 禁止的模型

- 不在本机运行 Full3D standard；
- 不在本机运行 Full3D static 作为数据生成主线；
- 不使用 p2/h5 tracked demo 冒充 low fidelity；
- 不混用 PML、zero-order-only、不同参考面或不同 DtN 语义；
- 不把不同 MPI 数、不同 source SHA 或不同 output schema 静默混入同一数据集版本。

---

## 3. 固定几何 pilot 点

使用以下 9 个参数点，保持固定编号和顺序：

| ID | h (nm) | w (nm) | 角色 |
|---|---:|---:|---|
| G00 | 120.0 | 17.0 | center |
| Gh- | 117.5 | 17.0 | height central difference minus |
| Gh+ | 122.5 | 17.0 | height central difference plus |
| Gw- | 120.0 | 16.5 | width central difference minus |
| Gw+ | 120.0 | 17.5 | width central difference plus |
| C-- | 115.0 | 16.0 | prior corner |
| C-+ | 115.0 | 18.0 | prior corner |
| C+- | 125.0 | 16.0 | prior corner |
| C++ | 125.0 | 18.0 | prior corner |

中心差分导数：

```text
dy/dh = [y(122.5,17) - y(117.5,17)] / 5.0 nm
dy/dw = [y(120,17.5) - y(120,16.5)] / 1.0 nm
```

四个角点用于检查非线性、h-w interaction、网格质量和低保真响应面的边界行为，不用于替代中心差分。

---

## 4. 衍射级与 observable 合同

### 4.1 不采用“每个点取功率最大的前 N 个”

禁止按每个样本的功率排序后动态选择通道。动态 top-N 会使同一列在不同样本代表不同 `(m,n)`，破坏代理模型和反演的物理身份。

采用固定 order identity。

### 4.2 compact 固定 9 个 x 向 order

只把下列 `n=0` order 放入正式 compact dataset：

```text
(m,n) =
( 0,0),
(-1,0),
(-2,0),
(-3,0),
(-4,0),
(-5,0),
(-6,0),
(-7,0),
(+1,0)
```

这是 Task001/Task002 的固定 `order_schema_v1`。对于某一照明/介质中不传播的 order，保留相同 identity，写：

```text
propagating = false
power = null
```

不得用 0 混淆“不传播”和“传播但功率接近 0”。

### 4.3 每个 order 保留的字段

对 top/reflection 和 bottom/transmission 两侧分别保留：

```text
m, n
side = reflection / transmission
incident_polarization
propagating
kx, ky, kz (complex JSON convention)
outgoing_s_amplitude_re/im
outgoing_p_amplitude_re/im
outgoing_s_power
outgoing_p_power
order_total_power
```

同时派生但不作为首版强制训练特征：

```text
amplitude magnitude
wrapped phase
```

不得在 Task001 中做跨参数相位 unwrap 后直接宣称可用于实验反演。复振幅主要用于同源数值审计；如果未来实验只能测强度，正式 likelihood 只能使用实验可测功率。

### 4.4 非零 n 的处理

因为 `grating_width_y = period_y`，物理结构沿 y 不变。`n != 0` 不进入训练向量，但每个 run 必须汇总：

```text
sum_propagating_power_n_nonzero_reflection
sum_propagating_power_n_nonzero_transmission
max_abs_amplitude_n_nonzero
```

这些值用于检查人工 y 周期、网格和投影泄漏。不得把每个高阶 n 通道扩展进 compact schema。

### 4.5 aggregate observables

每个 run 必须保留：

```text
R_total
T_total
A_balance = 1 - R_total - T_total
A_volume
energy_closure_error
full explicit true residual
```

### 4.6 Hybrid 数值质量

可用时保留：

```text
M
selected/passive mode counts
modal eigenproblem residual summary
upper/lower interface tangential E relative L2
upper/lower interface tangential H relative L2
middle-plane E/H comparison summary when a reference exists
M120/M160 observable difference at nominal cross-check
```

### 4.7 资源与 provenance

每个 run 必须保留：

```text
full source SHA and clean state
branch
parameter/order/observable schema versions
all config hashes
mesh topology identity and axis plan
cell count, DoF, rows, matrix NNZ, factor NNZ when available
MPI ranks and thread settings
wall time by stage
process-tree RSS/PSS/USS peak
process-tree swap peak and system swap delta
scratch peak
command and exit status
artifact hashes
status = measured / failed / controlled_stop / not_run
```

### 4.8 field artifact 策略

普通 pilot sample 不保存完整 3D field、VTK、PVD 或 matrix dump。仅允许以下点保存一个审计级场/plane artifact：

```text
selected high fidelity, G00, theta=80, phi=0, S
```

其他样本只保留结构化 summary、order table、必要 interface norms 和 compact records，避免本地磁盘被场文件占满。

---

## 5. Formal campaign 的 clean-source 规则

Task001 需要先实现 schema/adapter/watchdog/tests。实现完成后：

1. 运行 targeted tests；
2. 提交并推送一个明确的 `Task001 implementation baseline`；
3. 记录完整 SHA；
4. 确认工作树 clean；
5. 所有 formal FEM pilot 均绑定该 SHA。

formal campaign 开始后不得一边改代码一边继续追加数据。若发现实现 bug：

```text
停止 campaign
保存负证据
修复并提交新 SHA
明确哪些旧 record 失效
重新运行受影响的最小集合
```

文档或 checker 的无关改动不得无理由重跑已经 hash-bound 的昂贵 PDE。

---

## M0：Task000 接收、仓库与硬件审计

在任何修改或 PDE 前记录：

```text
repo root / git dir / origin / branch / upstream / HEAD / status
Task000 review and outcomes identity
Windows/WSL distribution and kernel
CPU cores / physical memory / WSL MemTotal / MemAvailable
swap total/free
Linux filesystem and free disk
qualified activation and ABI
MPI/PETSc/DOLFINx/MPC identity
```

重新运行 Task000 最小环境/adapter tests，确认没有环境回归。

M0 还必须只读审计：

- Case095 significant-channel reference；
- Case096 p6/h10 six-path authority；
- `benchmarks.run_task032_phase6_augmented` 的现有参数入口、MPI、static/memory-minimal、M120/M160 和输出字段；
- 当前 mesh builder 是否能在 h/w 变化时保持固定拓扑。

若现有 Hybrid runner 不支持参数化 geometry/illumination，M1 只允许增加薄配置入口；不得复制 runner 或重写 Hybrid 数值核心。

---

## M1：扩展参数化 ForwardModel v2

### M1.1 schema

将 Task000 v1 扩展为新的版本化 schema，至少包含：

```text
geometry.height_nm
geometry.width_x_nm
physics.wavelength_nm = 13.5 fixed
illumination.theta_deg
illumination.phi_deg
illumination.incident_polarization
fidelity.model_id
observables.order_schema_id
execution.mpi_ranks
execution.threads_per_rank = 1
```

保留 v1 dry-run/contract compatibility，不能静默改变旧 manifest 含义。

### M1.2 参数化 config

新增纯配置 factory 或薄 adapter，从 `target_stage4_config` 的单一物理权威出发覆盖：

```text
grating_height
grating_width_x
incident_theta_deg
incident_phi_deg
polarization_kind
selected fidelity settings
```

不得通过编辑 `src/main.py` 常量、临时替换源码或为每个样本生成一个 Python 脚本来传参。

### M1.3 长任务执行器

Task000 的短 `subprocess.run(capture_output=True)` 不足以承担高阶 Hybrid。Task001 应增加可审查的单作业执行器：

- 独立 process group；
- stdout/stderr 流式落盘；
- heartbeat 和阶段状态；
- 只终止自己创建的 process group；
- process-tree RSS/PSS/USS/swap 采样；
- timeout 与 memory controlled stop 使用独立退出码；
- 结束后确认无遗留 MPI/Python 子进程；
- 禁止 `pkill`、`killall`、`wsl --shutdown`。

### M1.4 MPI 冻结

优先资格化 MPI2。若 MPI2 不被当前 Hybrid 路径支持或显著增加峰值，可比较 MPI1，但同一 formal dataset version 最终必须冻结一个 MPI count。不得为了不同点的方便混用 MPI1/MPI2/MPI8。

S/P 在同一 geometry/theta/phi 下理论上可能共享矩阵。只有现有架构支持且 separate-solve 与 reused-factorization 的完整 observable vector 一致时，才允许多 RHS 优化；否则分别求解，不在 Task001 重构求解器。

### M1 Gate

- pure config/schema serialization tests；
- h/w/theta/phi/S/P 正负边界测试；
- v1 compatibility tests；
- dry-run command identity；
- watchdog dummy acquired/timeout/memory-stop/signal tests；
- order extraction synthetic tests；
- source dirty formal fail-closed test。

完成后提交 implementation baseline，再进入 formal PDE。

---

## M2：固定拓扑网格与 order extraction 资格化

### M2.1 固定拓扑

同一 fidelity 的所有 9 个几何点必须保持：

```text
相同 axis cell counts
相同 cell adjacency/topology hash
相同 material-region cell-count pattern
相同 Floquet entity pairing count
相同 element identity
```

只允许 grating x 边界和顶部 z 坐标随 w/h 连续移动。不得让 target-size rounding 在相邻参数点改变单元数量。

需要分别冻结：

```text
h10 topology plan
h7.5 topology plan (only if HF7P5 remains feasible)
```

在 9 个点上检查最小 Jacobian、最大 aspect ratio、正体积、材料 tag 和界面对齐。出现退化或拓扑变化立即停止。

### M2.2 order window

建立独立 extractor/checker，从 raw DtN order table按固定 identity提取 9 个 `n=0` order。检查：

- 不按功率排序；
- missing/nonpropagating 明确区分；
- outgoing S/P 和 total power 一致；
- 9 个 order 的功率和不冒充 R/T total；
- n-nonzero leakage 聚合从 raw table 独立重算；
- order convention、reference plane 和 complex amplitude字段绑定到 manifest。

### M2.3 轻量真实 smoke

先使用低阶/粗配置在至少两种照明上验证 order schema：

```text
80/0/S
70/90/P
```

该 smoke 只验证接口，不作为 fidelity 或训练数据。

---

## M3：high-fidelity 本机资源与数值资格化

### M3.1 安全内存规则

每次启动前动态计算：

```text
hard_process_tree_ceiling = min(10.5 GiB, 0.77 * WSL MemTotal)
launch_projection_ceiling = 0.90 * hard_process_tree_ceiling
minimum_headroom_before_launch = 1.0 GiB beyond hard ceiling
```

还要求：

```text
threads_per_rank = 1
one forward job only
process-tree swap peak = 0
no material system swap growth attributable to the run
free disk >= 20 GiB before high-fidelity attempt
```

达到 hard ceiling 时 watchdog 受控终止自己的完整 process group，并记录 `controlled_stop_resource_memory`。不得等待 OOM killer。

### M3.2 先资格化 HF10 nominal

在 G00、80/0/S 上运行当前 source 的 `hybrid_hf_p6_h10_m120`：

- clean SHA；
- 选定且冻结的 MPI count；
- residual/energy/interface/resource Gate；
- 提取固定 9-order vector；
- 对 Case096 的 12 个冻结显著功率/边界面复振幅做交叉比较；
- 比较 R/T/A/Avolume；
- 解释 source 改变造成的任何差异。

若 HF10 在本机也无法安全完成，Task001 立即 NO-GO：不得继续 p6/h7.5，也不得把 LF 冒充 high fidelity。

### M3.3 p6/h7.5 启动前预估

HF7P5 nominal 预估至少使用：

1. h10 与 h7.5 固定 cell plan：`[6,3,14]` 对 `[9,4,20]`；
2. Case095/096 已测 rows/NNZ/factor/peak；
3. 当前机器 HF10 实测；
4. p4/p5 已有不同 h 的规模趋势；
5. Hybrid local FEM、QEP、coupling 和 factorization 分阶段生命周期。

给出 optimistic / central / conservative 三档峰值。只有 central 预测不超过 `launch_projection_ceiling` 且 conservative 没有明显超过 hard ceiling时，才允许启动完整 HF7P5。

若预估已经不安全，状态写：

```text
HF7P5 = controlled_stop_resource_projection
PDE launched = false
```

这满足用户“内存过大就不算”的要求。

### M3.4 HF7P5 可运行时

只运行 G00、80/0/S、M120。全程 watchdog。完成后必须通过：

```text
full explicit true residual <= existing formal Gate
R/T/A closure
Avolume agreement
Hybrid interface E/H Gate
fixed order extraction
zero process swap
source stable from start to end
```

然后比较 HF7P5 与 HF10 的 9-order vector、Case096 significant channels、R/T/A 和成本。HF7P5 若完整通过，则成为 Task001 selected high fidelity；否则选 HF10。

M160 只有在 M120 峰值不超过 hard ceiling的 80%、磁盘和时间均有余量时才允许跑一次。M160 失败不否定 M120，但必须报告。

### M3 输出

`outcomes/fidelity_qualification.md` 必须明确：

```text
selected_high_fidelity
HF7P5 status and launch decision
HF10 formal identity
MPI count
M120/M160 status
rows/NNZ/factor/peak/time
all numerical Gate values
```

---

## M4：low-fidelity 选择

### M4.1 5 点 baseline 数据

在固定照明 `80/0/S` 上，对以下 5 点运行 selected high fidelity：

```text
G00, Gh-, Gh+, Gw-, Gw+
```

随后运行 LF4 同一 5 点。所有点必须使用同一 source SHA、MPI、order schema、物理参数和参考面。

### M4.2 比较指标

对 active numerical channels 定义 pilot active floor：

```text
max high-fidelity power over 5 points >= 1e-8
```

所有 9 个 order 仍被保存；floor 只用于资格化统计。

比较：

- R/T/A absolute discrepancy；
- 逐 order power 和 complex amplitude discrepancy；
- `dy/dh`、`dy/dw` 的方向和符号；
- LF-HF discrepancy随 h/w 是否平滑；
- runtime和peak memory reduction。

最低 low-fidelity Gate：

```text
finite and same physical/order identity
no propagation-set discontinuity caused by implementation
cosine(HF dy/dh, LF dy/dh) >= 0.85
cosine(HF dy/dw, LF dy/dw) >= 0.85
no sensitivity sign reversal in channels carrying top 80% HF Fisher contribution
LF wall time <= 0.5 * HF wall time OR LF peak <= 0.5 * HF peak
```

期望 Gate 为 cosine >= 0.90。低保真允许存在可学习 bias，因此不要求逐通道与 HF 完全接近，但不得改变主要灵敏度方向。

LF4 未通过时，运行 LF5 同一 5 点并用同样规则比较。选择成本更低且通过的模型。LF4/LF5 均失败时受控停止，不进行照明 pilot。

---

## M5：低保真照明与可辨识性筛选

### M5.1 运行集合

使用 selected low fidelity，在 9 个几何点上运行首轮 8 个照明条件：

```text
70/0/S, 70/0/P, 70/90/S, 70/90/P,
80/0/S, 80/0/P, 80/90/S, 80/90/P
```

最大物理 solve 数：

```text
9 geometries * 8 conditions = 72 solves
```

已经在 M4 完成且身份完全相同的 run 必须复用 hash-bound record，不重复计算。

每次只运行一个 forward job。失败点只允许一次由明确局部原因触发的重试；不得无限重跑。

### M5.2 compact power feature

可辨识性主分析只使用实验可能测得的功率，不使用 FEM residual、Avolume 或不可测复振幅充当额外观测。

分别分析：

1. reflection-only；
2. reflection + transmission。

对每个 illumination condition，候选 scalar features来自固定 9 orders 的：

```text
outgoing_s_power
outgoing_p_power
order_total_power
```

不得同时把 `s+p=total` 三者全部当作独立观测。根据实验定义选择独立集合。

每个 illumination condition 最终最多保留 8 个 scalar power channels。选择依据是 Fisher information增益和稳定性，不是单纯功率最大。

### M5.3 provisional noise models

实验噪声尚未冻结，因此同时报告：

```text
relative power noise = 0.5%, 1%, 2%
absolute power floor = 1e-8
sigma_j = sqrt((relative_noise * y_j)^2 + floor^2)
```

这些是设计假设，不得写成真实仪器不确定度。

### M5.4 Jacobian/Fisher

对每个 condition 和 condition subset 构造：

```text
J = [dy/dh, dy/dw]
Jw = Sigma^(-1/2) J
F = Jw^T Jw
C = pseudo/inverse(F) only when rank=2
rho_hw = C_hw / sqrt(C_hh*C_ww)
```

报告：

```text
rank(Jw)
singular values
condition number of Jw
log det(F)
rho_hw
provisional sigma_h and sigma_w
channel contribution
```

### M5.5 条件选择

在 8 个候选中枚举/贪心选择最小 condition subset，最多 4 个 `(theta,phi,pol)`，目标依次为：

1. rank=2；
2. `|rho_hw| <= 0.90` at nominal 1% noise；
3. `cond(Jw) <= 50` 为期望，`<=100` 为可接受；
4. 在 0.5%–2% noise 与 reflection-only/R+T 分析中不发生灾难性退化；
5. 条件数相近时优先较少物理 solves。

结果应至少包含一个 planar (`phi=0`) 和一个 conical (`phi=90`) 候选，除非数据明确证明其中一类没有信息增益。

如果 8 个条件中无组合通过，才运行 theta=75° 的 4 个补充条件，并重新筛选一次。仍不通过则 Task001 以 `two_parameter_identifiability_not_confirmed` 结束，不得用更多训练点掩盖不可辨识性。

### M5.6 四角点非线性

使用 4 个 corners 检查：

- 一阶局部模型对边界的误差；
- h-w interaction；
- channel power crossing；
- active channel identity 是否在参数域内改变；
- 是否存在局部共振/非光滑迹象。

若明显非线性，Task002 仍可使用 GP/多保真修正，但必须在计划中增加高保真 anchor，而不是提高全局多项式阶次来掩盖问题。

---

## M6：selected high-fidelity 可辨识性确认

### M6.1 运行范围

取 M5 选出的最小 condition subset，最多 4 个。在 5 个中心差分点上运行 selected high fidelity：

```text
G00, Gh-, Gh+, Gw-, Gw+
```

最大新增 high-fidelity solve 数为：

```text
5 * selected_condition_count <= 20
```

已经完成的 G00/80/0/S 或 M4 records 必须复用。

### M6.2 high-fidelity Gate

重新计算 high-fidelity J/F，并要求：

```text
rank(Jw) = 2
|rho_hw| <= 0.90 at nominal 1% design noise
no single channel contributes essentially all width and height information simultaneously
selected channels pass numerical residual/energy/order Gate at all 5 points
```

`cond(Jw)<=100` 作为可接受目标；若略高但仍满秩，必须报告狭长置信椭圆，不能宣称“已经精确确认”。

若 LF 推荐组合在 HF 上失败，允许基于已经计算的 LF candidate pool修订一次 condition subset，并只补算必要的 HF点。不得重新启动无边界角度搜索。

### M6.3 synthetic local recovery

在高保真 5 点数据上进行不冒充代理模型的局部线性/二次 sanity inversion：

- 中心点自回代；
- 至少两个小扰动 synthetic target；
- 加入 1% provisional power noise 的重复抽样；
- 报告 bias、spread、h-w correlation。

这只验证局部信息，不是 Task002 surrogate 或正式 Bayesian inversion。

---

## M7：冻结 Task002 多保真数据计划

Task001 不执行以下完整计划，只在 `outcomes/task002_dataset_plan.md` 冻结它。

### M7.1 low-fidelity design

在归一化 `[-1,1]^2` 上使用 7 x 7 Chebyshev-Lobatto tensor design：

```text
49 geometry points
```

每个 geometry point运行 M5/M6 选定的 condition bundle。文档必须同时报告：

```text
geometry design count = 49
physical solve count = 49 * condition_count
```

若 S/P multi-RHS reuse 已通过身份测试，可另报 factorization count，但不得把它与 solve count混淆。

### M7.2 initial high-fidelity anchors

固定 9 点：

```text
center
4 edge midpoints
4 prior corners
```

即本任务的 9 个 G/C 点，但 edge midpoint使用先验边界中点身份写清。每点运行相同 selected condition bundle。

### M7.3 adaptive high-fidelity budget

```text
6 to 10 additional geometry points
```

后续选择依据：

- multi-fidelity discrepancy uncertainty；
- PCE/GP disagreement；
- posterior/high-likelihood region；
- identifiability/Fisher information；
- corner/nonlinearity evidence。

### M7.4 independent validation

```text
6 to 8 high-fidelity geometry points
```

必须与训练/anchor/adaptive点不重合，直到模型冻结前不得用于拟合。

### M7.5 模型候选

Task002/后续拟合至少比较：

```text
low-order Chebyshev/PCE baseline
Gaussian Process baseline
multi-fidelity correction: y_H = rho*y_L + delta(h,w)
```

Task001 不训练这些模型。

---

## M8：记录、测试、文档与停止

### M8.1 benchmark case

建立：

```text
benchmarks/cases/110_surrogate_two_parameter_pilot/
    README.md
    config.json
    expected.json
    test_command.txt
    records/
```

`records/` 只提交轻量、hash-bound compact evidence。mesh、field、matrix、factor、完整 logs 和 bulk raw tables进入 ignored artifact目录。

### M8.2 必须测试

- parameter/schema boundary and serialization；
- fixed topology across 9 points；
- order extraction 9 identity、missing/nonpropagating、S/P/total consistency；
- n-nonzero leakage aggregation；
- watchdog dummy and process-group cleanup；
- dataset source/schema mixing rejection；
- low/high fidelity identity separation；
- Jacobian/Fisher/rank/rho synthetic unit tests；
- targeted serial/MPI tests；
- Ruff/compileall for changed modules；
- `git diff --check`；
- final clean source and artifact hash checks。

### M8.3 outcomes

生成：

```text
outcomes/summary.md
outcomes/test_summary.md
outcomes/fidelity_qualification.md
outcomes/illumination_identifiability.md
outcomes/task002_dataset_plan.md
response_v1.md
```

`summary.md` 表格优先，至少包含：

- selected HF/LF 与未选原因；
- p6/h7.5 是否启动、峰值预测、实际状态；
- 每个 formal model 的 p/h/M/MPI、rows/NNZ/factor/peak/time；
- 8 个候选照明的敏感度/Fisher 排名；
- selected condition subset；
- reflection-only 与 R+T 的 rank、cond、rho、provisional uncertainty；
- 9-order observable schema；
- 所有失败/controlled stop；
- Task002 geometry count与physical solve count；
- changed paths和数据身份。

### M8.4 最终停止

完成后：

1. 提交并推送唯一代理分支；
2. 报告完整 HEAD、upstream ahead/behind、clean status；
3. 不开始 49 点 low-fidelity bulk generation；
4. 不训练 PCE/GP；
5. 不执行正式反演；
6. 停止等待 ChatGPT Review V1。

---

## 6. 关键验收原则

Task001 的成功不等于 p6/h7.5 必须算成。以下两种结果都可能合格：

```text
A. HF7P5 安全完成并通过全部 Gate -> selected HF = p6/h7.5
B. HF7P5 在启动前或 watchdog 下受控停止 -> selected HF = same-source qualified p6/h10
```

不合格行为包括：

- 为了得到 p6/h7.5 而使用 swap/OOC/OOM；
- 用不同 SHA 的历史 record 冒充当前 formal data；
- 用 Full3D 或 p2 demo 偷换 Hybrid high/low fidelity；
- 按每个样本功率动态选择“前 N 个”不同 order；
- 把不传播 order写成零功率；
- 把复振幅、Avolume或 residual当作实验可测功率；
- 低保真未通过趋势 Gate就批量生成49点；
- 可辨识性不通过时仅靠增加训练点宣称问题解决。