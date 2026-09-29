# Task42extra：5 nm 三维 compatible FEINN 独立支线

## 0. 身份、授权与要消除的 blocker

本任务检验：**完整 Nédélec 插值的神经场，加上正确的弱残差度量，能否从零求得一个真实 5 nm 三维 Maxwell 有限元解；若可以，完整训练、辅助求解和验算成本是否值得扩大规模。** 当前只授权小型真实三维试验与目标尺寸容量设计，不把小模型通过等同于目标规模通过。

```text
task_id                  = Task42extra
repository               = Rookie1234567/MyFEniCS
execution_branch         = task42extra_feinn_5nm
upstream                 = origin/task42extra_feinn_5nm
base_branch              = task42_neural_coarse_inverse
base_SHA                 = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
base_latest_commit       = docs(task42): review V7 and authorize bounded scaling and execution calibration
base_latest_review       = docs/task042_neural_coarse_inverse/review_report_v5.md
base_latest_response     = docs/task042_neural_coarse_inverse/response_v7.md
execution_root           = /home/fenics/Projects/NN-Lab-V2
task_directory           = docs/task042extra_feinn_5nm
created_date             = 2026-09-29
status                   = PLANNED_NOT_RUN
response_required        = response_v1.md
master_merge             = NOT_APPROVED
```

用户本轮明确要求 ChatGPT 新开分支并写入任务书，故本次分支创建是通常由 Codex 建分支规则的一次性覆盖。用户仅创建空目录；Codex 负责 Git 检出、独立环境、实现、运行和交付。不要要求用户手工完成 clone、worktree、依赖安装或任务接线。

这是与 Task042 并行的新任务，不是其 V8 的另一个执行目录。冻结 base 是为了复用已检查的 FE/ML 接口、材料表和负结果教训，不代表研究代码获准整体合并 production。旧 Task042 的任务书、后续 review、response 和所有结果只读；其运行命令、超参禁令、剩余计时预算和材料历史阻塞不成为本支线的待办。新任务按本合同执行，普通 solver 默认不变。

最终主线仍是约 2 TB 物理内存内求解 0.7 nm、任意非可分三维周期单胞。这里属于**神经表示与残差优化的受控研究**，针对“正确插值和残差度量是否改善训练”这一 blocker；不是 0.7 nm/48h 已通过，也不替代通用 Full3D 的分布式、matrix-free 与可扩展求解研究。

## 1. 必读依据及方法边界

读取根 AGENTS、docs/AGENTS、仓库原则、Markdown 标准、本目录 AGENTS/README/task，以及以后本目录的补充任务书、最新 review/response/outcomes。代码改动前读取对应 src 子目录 AGENTS；不得依据旧聊天或仅凭分支名称执行。

| 依据 | 应取得的信息 |
|---|---|
| [论文 v2](https://arxiv.org/html/2411.04591v2)，Badia、Li、Martín，Compatible finite element interpolated neural networks | §2.2.1、§2.3–2.5、§2.7、§2.9、§3.1、§3.2.2；兼容插值、弱残差、Riesz 度量、假设及实验限制 |
| [Task042 最新 review](../task042_neural_coarse_inverse/review_report_v5.md)、[response](../task042_neural_coarse_inverse/response_v7.md)、[summary](../task042_neural_coarse_inverse/outcomes/summary.md) | 旧粗逆关闭；真实 trace 接口成立但三候选未合格；停机事务与前反向成本教训 |
| [Task042 原任务](../task042_neural_coarse_inverse/task.md) 及 Review V1–V4 | 历史范围和明确覆盖关系；只读，不重跑历史 |
| [5 nm 工作站证据](../task39extra_para_workstation_capacity/outcomes/summary.md) | F5 是其他离散/算法的 authority；其 RSS 和时间不是新 FEINN 的预测 |
| [Si 材料表](../../input/materials/si_optical_constants_v1.json) | 已授权 5 nm 数值、复数约定、十进制字符串和 provenance |
| `src/solvers/neural_trace*.py`、`neural_fe_action_packet.py`、`neural_fe_optimization.py`、相应 runner/tests | 现有矩、Piola、orientation、MPC、原方程、复数 VJP 与资源接口；只选择性复用 |

论文研究的 Maxwell 模型是正质量项的 H(curl) 内积问题。其正定性、误差理论及数值收益不能直接搬到高频、有损、开放的散射方程。论文部分实验使用 FEM 数据初始化；本支线主要正问题禁止读取目标准确解进行训练或初始化。论文的 surface Trace-FEINN 也不等于本仓库的单元边界 trace 参数化。

本轮采用论文的**兼容插值＋弱残差最小化＋离散对偶范数**，但不声称逐项复现。为保持与原 FE authority 完全相同的离散方程，首轮使用同一个 p3 试探/测试空间；论文的低阶细网格 linearised test space、AMR、反问题和 FEM 监督预训练暂不实现。测试空间改变将产生不同离散，须另行资格化，不能偷偷替换后仍声称同矩阵求解。

## 2. 从用户空目录建立唯一 Git 工作树

### 2.1 唯一目标路径

`/home/fenics/Projects/NN-Lab-V2` 本身就是仓库根，禁止再嵌套 `MyFEniCS/`。用户只执行 mkdir，目录预期为空。首次写入前检查 owner/权限、真实路径、是否 symlink、目录内容和已有 Git 登记。非空且并非本任务已登记 worktree 时停止，不删除、覆盖或强行修复。重复启动须识别正确 worktree 并续接，不重复创建。

既有 canonical common Git directory 记录为 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，必须现场只读确认其 origin、worktree list 与路径，不把聊天路径当实测。原 `/home/fenics/Projects/NN-Lab` 可只读用于查找登记，禁止在其中执行 checkout/switch/reset/stash/clean/pull、安装包或运行本任务。

首选从该 common Git directory **仅 fetch 本分支**，然后登记 linked worktree。非交互认证先验，失败报告 AUTH_REQUIRED，不索取/回显 secret，不等待密码。可使用如下命令骨架，但必须先完成条件检查，不能直接盲贴：

```bash
env GIT_TERMINAL_PROMPT=0 git --git-dir="$COMMON" -c gc.auto=0 fetch \
  --no-auto-maintenance --no-write-fetch-head --no-tags origin \
  refs/heads/task42extra_feinn_5nm:refs/remotes/origin/task42extra_feinn_5nm

git --git-dir="$COMMON" worktree add --track -b task42extra_feinn_5nm \
  /home/fenics/Projects/NN-Lab-V2 origin/task42extra_feinn_5nm
```

若本地同名分支存在，先核对 SHA、upstream、worktree 占用；未占用且身份一致才可直接 worktree add，不加 `-b`。已在其他目录检出、分歧或同名冲突则停止相关 Git 步骤，禁止 `--force`、reset、prune 旧登记。只允许设置本新分支必要 upstream；不改共享 origin、core.sshCommand、user identity、全局 Git 配置或运行 gc/repack。

canonical 库确实不存在时，先检查可读登记，不全盘扫描、不臆造新路径。只有确认没有可用 canonical 库，才允许在本空目录直接 clone 本分支（不创建嵌套目录），并明确登记新的 canonical 身份；若发现既有但无法访问的 canonical 库，则报告访问阻塞，不另建竞争权威。不要复制旧 `.git`、虚拟环境或活跃大数组来冒充检出。

检出后必须确认：repo origin 正确、branch 精确匹配、base SHA 为祖先、任务文件确实存在、无意外 dirty 文件、upstream 正确、ahead/behind 有记录。用户指令中的任务发布 SHA 应为祖先；远端已新增同任务后续提交时读取新合同，不 reset 回旧 SHA。不存在且不可读的分支不能用近似拼写替代。

所有实现、review、response 均留本分支。提交/推送固定使用：

```bash
git push origin HEAD:refs/heads/task42extra_feinn_5nm
```

不 merge/rebase master 或其他活动分支，不 amend/强推，不删负结果。不因 Task042 后续更新自动追随其 HEAD；需要复用修复时按冻结文件/提交说明依赖，并在本分支独立测试。

### 2.2 原生 Linux、环境与缓存

执行端是**工作站原生 Linux**，不是笔记本 WSL，也不要求改变用户 Windows Codex/SSH 客户端。每条执行命令在一个 shell 中包含 cd、task-local activation 与实际操作；不依赖前一个 shell 的临时变量。

先只读核对既有 DOLFINx/Basix/FFCx/MPC/PETSc/mpi4py 栈与 CPU PyTorch。允许复用已经验证的只读原生 library prefix，但本项目源码必须从 NN-Lab-V2 导入。FE 与 ML 使用本任务独立 activation/环境，优先分进程、通过 schema/hash 绑定的数据包通信；不得让 Torch 的 MPI/BLAS 依赖污染 FE 进程。

不在旧 `.venv`、系统 Python 或共享 prefix 中安装/升级，不修改 CUDA、驱动、BLAS alternatives、swap、governor、WSL/Docker/BMC。无现成 ML 环境时仅在本目录独立环境准备固定版本最小 CPU 依赖；需要系统级变更则报告，不提权改旧运行环境。

正式 FE 前确认 complex128、PETSc IntType 和同 ABI；ML 使用 float64 实虚双通道，禁用隐式 FP32/TF32/AMP。独立的 results、TMPDIR、JIT/FFCx、Torch、Python bytecode 和绘图缓存全部位于本工作树 ignored 路径，禁止写回旧工作树或通过 symlink 隐藏共享写入。

## 3. 三个既有项目运行时的新增负载边界

用户已选择工作站并行支线。本合同只对**以下有界小型试验**授权受控共享 CPU，不改变其他任务的资源合同，也不授权第四项不设上限的 heavy 运行。存在其他项目不是自动拒绝所有工作；资源无法证明安全时仍可交付代码/轻测试，数值阶段标 RESOURCE_WINDOW_UNAVAILABLE。

| 阶段 | 本任务资源上限（规划上限，不是实测） |
|---|---|
| Git、文档、pure-array 轻测试 | 1 空闲物理核，数学线程 1，整树 RSS 不超过 2 GiB |
| 本轮小 FE、Gram setup、训练和参考，内部串行 | MPI1，数学/Torch intra/inter-op 1，DataLoader0，1 空闲物理核；整树 hard16 GiB/warn12 GiB |
| 加速器 | CPU-only；GPU/VRAM 0，不争用既有 GPU 任务 |
| 存储 | 启动时自由至少 50 GiB；本支线 artifacts 上限 20 GiB；不使用 OOC |
| 时间 | 本轮所有新数值有载及有界辅助检查累计最多 16 h；每条候选最多 3 h，均为停止预算而非 ETA |

每阶段现场检查活跃项目的 root PID/start_ticks、阶段、affinity、实际线程、RSS、邻任务增长预留和系统压力；只读轻量文件/短日志，不重复扫邻任务巨型资源日志或 smaps/PSS。选择未被邻 worker/监督器/加载线程使用的物理核心，避开忙碌 SMT 同胞；CPU 编号现场确定，不照搬旧任务 CPU0/12 等编号。

取 effective_total/effective_MemAvailable 为宿主和可用 cgroup 限额中保守值。启动前至少保留 max(128 GiB, effective_total 的10%) 系统余量，加上邻任务规划增长（至少128 GiB；已有记录更大则取更大），再加本任务16 GiB预算。无法核实邻任务的明显增长风险时，不启动 factor/长训练。不要把整机2TB当本任务可占满的RSS。

本任务自有 nonblocking lock，内部一次只运行一个数值阶段；不得获取后永久占用或改写其他任务锁。全部子进程继承本任务 affinity、数学线程与较低优先级（nice10/idle I/O，仅在可用时）；编译也单线程。资源限额必须覆盖 launcher、FE/ML服务、编译器和全部后代，不只是 Python 主 PID。

复用低扰动 cgroup/watchdog；有已授权委派时使用任务级限制，无委派就如实采用约0.5s同时进程树RSS采样与安全停止，不冒称内核连续限额。任务自身 swap=0；全机 swap 变化仅作系统诊断，不直接归罪本任务，不改邻任务策略或关闭全机swap。自身换页、RSS硬线、磁盘耗尽或持续监督失效时停止自身后代。系统持续压力时安全停止本任务，绝不 kill/暂停/改亲和性其他项目。

没有安全窗口时完成其余独立可做工作、保存 checkpoint/原因并交付；不创建无限等待、定时后台启动或无人看管的抢资源循环。共享运行不能宣称零干扰，性能标 shared-workstation。目标尺寸正式计算不在当前并行配额内。

## 4. 冻结首轮 5 nm 物理与离散

### 4.1 M5：小型真实三维缺口单胞

这是新建的**小型 5 nm 资格模型**，不是把 Task042 的 0.7 nm 文件只改标签，也不是已有50/25/120nm级目标的完成。下列尺寸都是 nm，全部界面对齐网格。

| 项目 | 冻结设计值（not_run，实际数值/身份由 Codex 核验） |
|---|---|
| 波长/入射 | 真空5；grazing1°、azimuth0、s、幅值1；沿用原入射约定 |
| 周期/计算域 | x=[-5,5]，y=[-3.75,3.75]，z=[-1.25,8.75]；周期10/7.5 |
| 基底 | z<0 为Si |
| 光栅块 | x=[-2.5,2.5]、全y、z=[0,7.5] 为Si |
| 空气缺口 | 块内 x=[0,2.5]、y=[-1.25,1.25]、z=[2.5,5] 改为air |
| 网格/FE | h=1.25，8×6×8=384 hexa；Nédélec 第一类p3；原FE积分degree15 |
| 物理边界 | x/y双Floquet；z两侧原layered-background Fourier-DtN；不换PEC/PML/零反射近似 |
| 精度 | FE complex128、网络FP64；不改物理质量项符号，不添加人工吸收 |
| 条件离散对照 | 相同几何/网格的p4准确参考一次，仅在本轮p3候选资格通过后准入 |

实际 tags 必须显示 y/z 材料变化，并报告非可分结构见证。该设计沿用已知网格拓扑尺度比例，预计 FE34050、periodic slave2082、独立全FE31968、独立trace18144、内部13824；这些数量只作 **derived 预检**，不能当本支线实测。训练保留全部独立 FE 未知量，不仅保留trace。

### 4.2 材料不可再猜填

唯一材料记录为 `input/materials/si_optical_constants_v1.json`，ID=`SI_OPTICAL_CONSTANTS_USER_20260929_V1`。冻结base中的内容SHA256为 `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`，运行时重新核对。

5 nm Si：Delta=0.00603145547，Beta=0.00435380777，n=0.99396854453+0.00435380777i，epsilon_r=n*n；十进制检查值为0.9879545118729884805480+0.0086550959446206099962i。substrate/grating/background/下端口使用同一条目；air n=1，mu_r=1，时间约定exp(-iωt)。保留来源字符串及hash，不以原数据库版本缺失再次阻塞已授权数据。

重新计算实际上下端口 key、极化、归一化、传播/截止分类及库存hash；不得套用旧40/80/600通道。载荷必须非零，不能把弱对比问题按零散射处理。网格、材料、背景、MPC及实际端口一起形成新的 physical_model_sha256。

### 4.3 目标尺寸不被小模型替代

本任务近期目标是向已有50nm/25nm周期、120nm高度级别的5nm结构推进，并保留真正非可分几何。E5阶段必须给出目标几何候选、准确网格需求、原生FE/端口/Gram/网络容量和需要解除的blocker，不能只用小模型一张PASS表结项为全部成功。

本轮不启动目标尺寸PDE、不盲用旧p6/h4精度、不默认其矩或参考适用于新缺口。目标精确几何和网格在后续review冻结；当前只建立可审计的晋级路线，不假装目标身份已经完整。

## 5. 方法：完整有限元插值，而不是 trace 粗逆

### 5.1 网络及完整场

首轮固定一个坐标MLP：3→64→64→64→6，tanh，seed=421001，float64；6个实输出组成三分量复**散射电场**。网络输入按域中心和各半宽归一化至[-1,1]。隐藏层采用固定seed初始化，末层置零；不可全层零初始化。记录实际参数总数（该架构推导为8966），不加每自由度embedding、carrier、Fourier特征、材料标签网络或多seed扫描。

选择普通坐标MLP是为了首先检验论文式完整插值与残差度量；它未必能紧凑表示最终高频场。不把有限负结果归结为全部神经表示不可能。后续波动特征/分片网络需新review，不在本轮边跑边改。

用完整 Nédélec 边、面、内部矩，从网络取得全部独立FE系数。使用原 Piola pullback、orientation 与唯一entity owner；双Floquet从自由度仅通过原MPC复相位展开，不重复乘相位。每个p3 cell的36边矩、72面矩、36内部矩全部保留。共享切向场由FE保证，不对材料界面施加多余法向连续惩罚；原网络光滑可能带来的表示局限需如实分析。

```math
c(\theta)=\mathcal I^{\rm curl}_{h,\rm MPC}E_\theta,\qquad
E_{h,\theta}^{\rm total}=E_h^{\rm bg}+\sum_j c_j(\theta)\phi_j.
```

背景仅是已知layered解析背景的原FE仿射换元，不是目标解。保持原rhs定义并检查它与总场方程等价。z开放边界不套用论文的全边界零切向Dirichlet lifting。这里没有独立训练节点值，也**不通过局部物理恢复代替网络的内部矩**；否则变回Task042，必须停止并报告范围偏离。

### 5.2 只解析消去 DtN 辅助变量，保留全部 FE 未知量

为避免把体内H(curl) Gram错误套在混合单位的port残差上，本轮在**原native全FE方程**上定义loss。用下列通用分块说明符号，代码须从本仓库实际增广方程核对各块和符号：

```math
\begin{bmatrix}A_v&B_p\\C_p&D_p\end{bmatrix}
\begin{bmatrix}c\\\alpha\end{bmatrix}
=\begin{bmatrix}f_v\\g_p\end{bmatrix},\qquad
A=A_v-B_pD_p^{-1}C_p,\quad f=f_v-B_pD_p^{-1}g_p.
```

```math
\alpha(c)=D_p^{-1}(g_p-C_pc),\qquad r(\theta)=A c(\theta)-f.
```

只有原DtN端口块允许做已有的准确小块solve；不得形成其显式逆或静默截断端口。证明其适用性、可逆性和原归一化；不合格标 PORT_ELIMINATION_NOT_QUALIFIED，不加shift凑可逆。该消元不删物理通道、不消去单元内部FE未知量，也不是全局Maxwell逆。

A/Aᴴ用原局部未凝聚体张量＋MPC＋完整端口作用；候选不常驻global A CSR，不形成AᴴA。显式大耦合块的bytes和临时对象仍要计账。每次正式审核恢复全部port，并独立检查未凝聚增广方程、native体方程和端口closure。训练中Aᴴ是共轭转置作用，不是伴随方程求逆。

### 5.3 两种loss与明确的 Riesz 成本

普通欧氏对照：

```math
L_E(\theta)=\frac{r(\theta)^*r(\theta)}{2f^*f}.
```

Riesz版本的测试空间就是相同MPC约束后的全FE p3空间。取固定长度ell=5nm，在与原几何相同单位下定义正定、与损耗材料无关的Gram：

```math
G_{ij}=\int_\Omega \overline{\phi_i}\cdot\phi_j
+\ell^2\overline{\nabla\times\phi_i}\cdot(\nabla\times\phi_j)\,d\Omega,
\qquad G=C^*G_{\rm full}C.
```

上式第一项表示约束前/后对应基的同一内积；实现只组装一次约束投影，不把C重复应用。质量项和curl项都为正，G不是不定Maxwell矩阵A，也不是旧p4粗逆。ell用于一致量纲，不按结果扫描。采用维度无关单位时必须给出变量和残差的准确换元，不能只改Gram而漏掉坐标/积分缩放。

```math
d_G=f^*G^{-1}f,\qquad Gq=r,\qquad
L_D(\theta)=\frac{r(\theta)^*q}{2d_G}.
```

d_G和f*f从固定原载荷一次计算；零载荷只走专门解析测试，正式case不允许靠epsilon分母掩盖。不能用norm(G^-1 r)^2冒充该对偶范数，也不能把逐单元残差平方和当组装后的全局残差范数。

**小模型允许准确稀疏全局Gram factor，必须标 RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR。** 它就是实际辅助求解成本，不得宣称整条路线无全局因子。禁止global Maxwell A factor参与训练、禁止dense G/dense inverse。Gram setup先symbolic/容量Gate，预计超过预算即停止该路线；不依赖OOM。固定一次factor用于同一路线所有loss/梯度，解Gq=r真实相对残差目标1e-11；G必须Hermitian正定。setup/solve、常驻因子RSS、Gram CSR与释放全部记账，不能只报网络参数内存。

欧氏路线不加载G因子。DUAL与FREE-DUAL分别从同一无解数据准备其所需辅助factor，基准成本中各计完整setup；可另外报告可复用成本，不把摊销当单次加速。使用G逆后仍可能训练停滞，不据正定G宣称不定A已波长鲁棒。

### 5.4 梯度与分块实现

对实网络参数、固定G，梯度应满足：

```math
\nabla_\theta L_D=\operatorname{Re}\{J_c(\theta)^*A^*q\}/d_G,
\qquad J_c=\partial c/\partial\theta.
```

欧氏版本令q=r、分母f*f。利用VJP，不显式存储全Jacobian；验证复共轭、实虚布局、MPC拉回和norm的1/2因子。不得把不精确、随迭代变化的G求解当准确固定逆而不检查梯度。

插值/反传按最多8个owner-cell批量并重算图，先估算峰值，不建立全网格自动微分图。允许缓存固定坐标、Piola、方向和矩映射，但必须与独立逐单元版本配对；只删除对完整矩严格零贡献的采样。不能删内部矩、face高阶矩或改变FE积分以求低内存。NN矩求积按预登记15→30→60做一次有界非零配对，满足1e-8后冻结；不按结果持续加阶。

## 6. 执行顺序与有界试验

前置Gate通过后可连续完成E0–E5，不逐小步请求确认；真实安全/权限/算子/数值失败按其影响范围停止，完成其他独立可做部分并交付。旧Task042的fail不是本支线的自动禁令，也不是重跑旧负结果的理由。

### E0：Git、环境、资源与预登记

建立本目录登记与轻量 `outcomes/summary.md`，写出文献方法与本轮改动、物理/离散/材料/通道设计、尺寸与全过程内存模型、阶段预算和三路线顺序。只读确认canonical、依赖和既有负载，不要求完整重装/F0重跑。将首次数值实现commit后再正式运行，tracked worktree需clean。

### E1：兼容插值、真算子与Riesz资格

先pure-array复数非Hermitian代数测试，再8-cell单位立方体、p3的正定curl-curl＋质量项制造解检查（解析场和边界已知，只作实现诊断，不叫5nm结果；本项最多30min）。随后只构造M5真实算子和插值，完成下表Gate。不因正定smoke通过就跳过真实散射检查。

| 接口Gate | 必测内容与限值（dimensionless，operation-scaled） |
|---|---|
| 完整矩/映射 | 非零复多项式、方向翻转、共享entity、内部矩与独立DOLFINx插值；相对差1e-10；包含非零slave相位 |
| native/端口消元 | 原独立FE作用、A/Aᴴ dot test、增广与native等价；1e-10；至少3个非零复向量及非零port/内部载荷 |
| Gram | Hermitian缺陷1e-12；正性与约束独立性；实际Gsolve残差1e-11；报告基数/NNZ/factor成本 |
| 完整梯度 | 至少3个非零实参数方向，h=1e-4/1e-5/1e-6中心差分，稳定区相对1e-5；不得仅零初始化检查 |
| 批量/求积 | batch1/8全系数、loss、VJP和一次克隆更新差1e-10；q规则差1e-8；近零另报绝对值 |

接口见证允许固定seed421002的小非零参数扰动，但不得成为候选训练初值或包含参考解。记录固定f、G、MPC、矩packet、模式顺序的hash。所有shape、dtype和NaN检查必须明确。

### E2：同一M5上的三条独立路线

| 路线 | 参数化/loss | 用途 |
|---|---|---|
| FEINN-EUC | 完整网络插值；L_E | 给对偶残差提供同网络、同方程对照 |
| FEINN-DUAL | 相同网络/seed；L_D | 本支线的主要论文思想迁移候选 |
| FREE-FE-DUAL | 全部独立FE系数实虚分量直接优化；L_D | 区分Riesz/优化器收益与神经表示收益 |

路线按表格顺序串行、独立进程、散射全系数初值零、互不warm start，端口用原公式恢复。主要路线不使用旧Task042状态、准确目标解、teacher、POD基或监督数据。每条路线开始前重新确认资源，结束释放后才进入下一条。

三条统一先Adam500更新（lr1e-3、无weight decay），再L-BFGS（history20、lr1、strong-Wolfe）；全部loss＋gradient closure至多4000且wall至多3h，取先达到者。每次线搜索试探也计closure/A/Aᴴ/Gsolve，记录外层与内层次数；不能用小梯度或优化器success代替方程通过。超参是预登记起点，不保证适宜；本轮不扫描lr、宽度、seed、carrier或loss权重。

每25个closure及最终，对明确标注状态做全原方程检查；轻量loss逐步记录。预算预留最后审核与保存，不用15s/30s外层timeout误杀正常阶段。对L-BFGS设置事务边界：外层step正常返回才提交状态，closure异常恢复最近完整已提交参数；同时保存last_trial，费用照计。需要声称可续训时同时保存一致optimizer state，否则标parameter-only不可续训。

失败路线保存原数值后继续其余独立路线，不把一个优化负结果当接口错误。不得为了让新方法通过而给FREE设置更弱预算。报告各自初始尺度、loss/原残差/场误差历史；L_E与L_D的数字不能直接当同一种误差比较。

### E3：冻结后独立5nm准确参考与物理验收

所有候选终止并冻结checkpoint/hash后，才单独建立同mesh/p3准确参考。可用MUMPS等小规模全局A因子，仅为独立authority，训练进程不可读取；它是reference，不是部署隐藏fallback。symbolic/内存Gate先行，参考失败不重跑候选，也不伪造参考。

参考残差目标1e-10；保存最小恢复/场packet，销毁KSP/PC/全局因子和无用矩阵，确认RSS下降后再完整后处理。参考可采用准确凝聚求解，但必须回到与候选相同的完整原FE方程配对。首次实际无参考时必须报告not_run，不把旧5nm其他mesh结果当同离散reference。

主要交付场为完整插值FE场，不是网络的任意点云。独立计算total/scattered复E/H、scaled curl、全衍射复幅与逐级功率、R/T/A/A_volume。训练loss降低、R+T+A接近1或total场被背景主导均不能替代准确散射。原始网络场仅作为额外diagnostic单列，不宣称论文式超收敛。

### E4：条件p4离散检查一次

至少一条p3候选通过同离散方程与物理资格且预算允许时，才运行同mesh/p4准确参考一次。只用于p误差对照，不重新训练p4网络，不用于回训p3；不能反复加密直到过关。未通过则标 DISCRETIZATION_NOT_QUALIFIED，仍保留p3代数解的有限资格。

### E5：资源、神经增量与目标尺寸晋级设计

给出每条路线从零准备的setup＋训练＋完整审核＋恢复/输出总成本；参考验证成本单列并同时给出研究全账。列网络/矩/Gram solve/A/Aᴴ/VJP/优化器/IO的互斥timer，不能重复加父子时间。统计峰值全过程树RSS、swap、factor与payload、临时激活、optimizer历史；数组bytes不当RSS。

输出目标尺寸5nm的几何候选与FE/通道/Gram及可能的multilevel或matrix-free Riesz成本模型。小模型的准确全局Gram因子不可直接外推为可扩展PC；如瓶颈转移到G就明确报告。若小模型只给方法负结果，分析已排除/未排除的表示、优化、离散、端口或资源因素，不任意宣布唯一根因。

结束后提交并等待review，不启动更大几何/更多波长、不自动用剩余16h反复调参。正式目标0.7nm/48h始终not_run/not_qualified。

## 7. 数值、物理与研究判断

下面都是预登记标准，不是已测结果。近零规则在E0冻结：向量误差使用范数分母max(norm(reference),1e-12×本量的非零自然参考尺度)，并同时报告绝对误差与实际分母；selected点用同一个预登记入射E/H尺度，不能事后调分母或拟合全局复相位。

| Gate | 标准及意义 |
|---|---|
| 完整原方程 | native全FE及完整未凝聚增广相对残差各≤1e-6，固定各自原RHS；不能用G加权loss代替 |
| 端口/周期 | port绝对范数除完整RHS≤1e-6，operation-relative≤1e-6；MPC/消元恢复缺陷≤1e-10，有限值且slave存储合同通过 |
| 同离散场 | 全FE total/scattered E的L2、scaled-curl、selected复E/H、完整ordered复通道相对差≤1e-4；分别报告，不能只看total |
| 功率与吸收 | R/T/A/A_volume绝对差≤1e-5；每通道功率差≤1e-6；能量闭合与A_balance/A_volume差≤1e-5 |
| p差异 | E/H/curl及完整通道差异目标≤1e-3；只是一次p检查，不称连续极限或任意几何保证 |
| loss度量收益 | 同准确性下DUAL相对EUC端到端时间或RSS改善≥20%且另一项合规，或DUAL资格通过而EUC预算内失败，才记本pilot正信号 |
| 神经增量 | DUAL须与FREE-DUAL同准确性/同完整成本比较；只有合格且时间或RSS改善≥20%才记神经增量；共享不可比时inconclusive |
| 目标/生产资格 | 小模型pass不等于目标尺寸5nm，更不等于0.7nm任意三维、2TB或48h通过；不merge |

允许状态：INTERFACE_PASS_ONLY、FEINN_DISCRETE_PASS、FEINN_OPTIMIZATION_NEGATIVE、DISCRETIZATION_NOT_QUALIFIED、RIESZ_RESOURCE_BLOCKED、RESOURCE_WINDOW_UNAVAILABLE、CONTROLLED_STOP、BLOCKED。数值/物理/资源/神经贡献各自判定，不合成一个误导性PASS。

同离散训练失败只能说明本固定配置/预算的结果，不证明FEINN普遍无效；同样，16h训练没有成功也不是任意延长运行的理由。明确实现错误允许一次最小修复及受影响阶段重放，失败费用照计；正常停滞不是bug。

## 8. 允许/禁止修改、证据与提交

数值核进入合适 `src/solvers/`、物理/插值辅助进入对应模块，runner只做参数化编排。优先复用既有general接口，新增full-FE/Riesz明确opt-in，不把新数值方法仅写在benchmark脚本。不要复制每个case一套大runner或把Task042原函数改成不同数学含义。

允许新增本支线独立activation、full-FE interpolation/action/Riesz/optimization adapter、targeted tests、one-run输入和轻量checker。禁止旧PC/ILU调参、global Maxwell因子训练、AMR/linearised-test扩展、数据集扫参、目标解监督、跨任务环境修改、普通默认改变、全仓清理或无故full pytest。若base尚未包含Task042的停机修复，在本支线实现最小独立修复并测试，不等待或修改旧分支。

所有正式FE阶段通过：

```bash
python scripts/run_case.py input/task042extra_feinn_5nm/<one-run>.dat
```

一个dat只表示一次明确的geometry/operator/stage。三训练路线分别三个dat；制造解、Gram准备、reference也有明确stage，不伪装成一次物理campaign。必要dispatcher新增不能触发旧Task042流程。

每个run保存 `input_original.dat`、`resolved_config.json`、`run_manifest.json`、`input_sha256.txt`、`physical_model_sha256.txt`、`source_sha.txt`、`run_summary.json`，以及branch/environment/MPI/threads、材料/网格/模式/矩/Gram/初始化/checkpoint hashes和整树资源记录。运行source不等于后续文档HEAD；活跃受检run中不为写文档改变它的工作树HEAD。

Codex至少交付本任务 `response_v1.md` 和以下轻量文件；未运行项也要保留原因，不先填假结果：

```text
outcomes/summary.md
outcomes/method_and_paper_mapping.md
outcomes/environment_and_isolation.md
outcomes/accuracy_performance_memory.md
outcomes/target_5nm_scale_plan.md
outcomes/test_summary.md
outcomes/changed_files.md
outcomes/records/design_v1.json
outcomes/records/run_index_v1.json
outcomes/records/interface_gates_v1.json
outcomes/records/route_comparison_v1.csv
outcomes/records/gate_decisions_v1.json
outcomes/records/resource_costs_v1.json
```

大矩阵、模型、场和完整history留ignored目录。summary用表格呈现模型/参数/参考/单位/实际数值/失败项/资源/合并边界，区分measured、derived、predicted、diagnostic、not_run、failed、controlled_stop、blocked。同步本分支 `docs/development_progress.md`，正式FE/资源运行后更新 `docs/development_model_registry.md` 的新Task42extra小节；不覆盖旧Task042记录。

建议提交：C1 Git/环境/预登记/最小tests；C2完整插值/native/Gram及梯度；C3三路线与停机；C4独立验证和条件p检查；C5证据/response/晋级设计。每阶段先clean实现commit再run，局部修复另commit，不amend、不强推。测试采用pure→真实小FE→同算例接口→三路线→独立物理；复用相同source/artifact已通过的检查，不反复重装环境或重跑旧heavy。

文档遵守fenced math、表格列数和链接规则，实际检查GitHub rendered view；无法访问时如实记render检查blocked，不伪造截图或PASS。新task/review由ChatGPT维护，Codex通过response提出更正，不删除/改写任务书。仅推送本执行分支，不通过master中转，无最终review与用户授权不得merge。

## 9. Response V1 必须首先回答

先报告准确branch、HEAD、base、upstream、canonical/common Git、worktree状态；说明是原生Linux本机计算，不是笔记本或旧NN-Lab。接着交代实际执行E0–E5哪几步、三个既有项目只读核查及本任务资源边界。

随后明确：网络是否生成完整内部/边/面矩；loss是否真为r*G^-1r；Gram因子实际成本；端口消元是否准确；同5nm三路线是否同物理/离散/初值；原残差、散射场、R/T/A与p差异是否通过；新方法的改善属于度量还是神经表示；既有任务的影响是否可判断；目标尺寸5nm及最终0.7nm还有哪些未验证项。

即便被资源窗口阻塞，也交付已完成的Git/代码/测试和准确停止原因，不无限等待。完成本轮后只给一个有证据的下一最小建议，并停止等待review，不自行扩大研究范围。
