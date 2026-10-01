# Task42extra NN-V3：学习迭代修正与神经预条件的独立对照研究

## 0. 任务身份、决定与授权

**本任务不再用坐标网络从零拟合一个场，也不恢复已关闭的全局 p4 强逆路线。主线是：学习一个有界成本、可重复调用的多层残差修正模块；用完全相同的冻结权重，分别检验不使用 Krylov 的学习迭代和右预条件 FGMRES。由真实精度与端到端成本决定去留，而不是预先宣布神经网络有效。**

通俗地说，网络负责建议“这一步该怎样改正错误”，原 Maxwell 方程负责检查建议是否真的有效。准备阶段可由网络生成与介质、网格和边界有关的系数；同一次求解中缓存这些系数，避免每步重复昂贵的非线性特征提取。多层通道用于尝试保留传播方向与相位信息，不代表已经拥有准确粗逆。

```text
task_id                 = Task42extra_NN-V3
repository              = Rookie1234567/MyFEniCS
execution_branch        = task42extra_NN-V3-learned-iteration
upstream                = origin/task42extra_NN-V3-learned-iteration
task_directory          = docs/task042extra_nn_v3_learned_iteration
base_branch             = task42_neural_coarse_inverse
base_SHA                = 5b489b7264b75a9461577303ff0f6bc8907c19dd
created_date            = 2026-10-01
execution_machine       = third independent laptop, WSL Linux
execution_root          = user-selected current empty WSL directory
initial_status          = PLANNED_NOT_RUN
first_response          = response_v1.md
production_merge        = NOT_APPROVED
final_target            = fresh 0.7 nm nonseparable 3D periodic Maxwell FEM solve
final_target_budget     = approximately 2 TB physical RAM, end-to-end <=48 h
```

用户本轮明确授权 ChatGPT 创建本分支、检索论文并写任务书。本次创建覆盖通常由 Codex 建分支的规则；选择上述冻结研究 SHA 覆盖默认从 master 创建的规则。继承源码不是批准整体合并研究代码。本笔记本的独立 clone 是这台机器本任务的 canonical repository，不要求访问工作站 common Git，也不要求把第三台机器登记为工作站 linked worktree。

这是第三条独立研究线，旧两分支只读。本任务不执行它们的待办、恢复它们的 checkpoint、继承它们的计时预算或远程路径。不得 SSH 操作其他机器，不改变其他任务的源文件、分支、进程、环境、缓存和负结果。所有实现、review、response 只推送本执行分支；master、其他分支均不写入。

## 1. 已核对的现状与新任务的差异

以下是 2026-10-01 已读取的远程记录，不是当前现场监控或在新笔记本重新测得的结果。

| 研究线与冻结 HEAD | 已记录结果，measured/recorded | 本任务不得重复的工作 |
|---|---|---|
| Task042；5b489b7264b75a9461577303ff0f6bc8907c19dd | Response V18；GPOLY-R 的原 Schur 残差 1.463077182e-4、散射 E 误差 8.079990122e-5；GNN-R 分别 1.995563747e-4、1.001991308e-4；完整资格 0/8 | 不把基空间 LSQR 后的 GMRES/LGMRES 校正再执行一遍并称 NN-V3；不恢复已关闭 p4 低内存强逆 |
| Task42extra FEINN；47317bb648d5e2237657f8b6c75c239ab5bf55c5 | Response V9；5 nm plain/phase GN 的原残差约 1.0285/1.0187，散射 E 误差约 0.9989/0.4372；没有无标签准确求解 | 不再做坐标到场网络、完整矩 FEINN、Riesz 因子与全参数 GN 续算 |
| FEINN 独立 p5 reference | native 约 1.22906e-11；过程树峰约 6.70 GiB；p4/p5 的 curl/H 仍存在超过 1e-3 的敏感性 | 参考成功不是 NN 成功；工作站内存/时间不能冒充笔记本实测 |

证据入口：

- [Task042 Response V18](https://github.com/Rookie1234567/MyFEniCS/blob/5b489b7264b75a9461577303ff0f6bc8907c19dd/docs/task042_neural_coarse_inverse/response_v18.md)；[Review V16（授权 V19）](https://github.com/Rookie1234567/MyFEniCS/blob/5b489b7264b75a9461577303ff0f6bc8907c19dd/docs/task042_neural_coarse_inverse/review_report_v16.md)。
- [FEINN Response V9](https://github.com/Rookie1234567/MyFEniCS/blob/47317bb648d5e2237657f8b6c75c239ab5bf55c5/docs/task042extra_feinn_5nm/response_v9.md)；[Review V9](https://github.com/Rookie1234567/MyFEniCS/blob/47317bb648d5e2237657f8b6c75c239ab5bf55c5/docs/task042extra_feinn_5nm/review_report_v9.md)。
- 已读接口：`src/solvers/neural_fe_action_packet.py` 的 `ActionPacket`，包括 S/SH、恢复、未凝聚方程审核和 Floquet pullback。它的存在不证明新 learned PC 已资格化。

先读根 AGENTS、docs/AGENTS、仓库原则、Markdown 标准、本目录 README/task/literature_review、以后出现的补充合同和最新 review/response/summary；再读实际改动目录的 AGENTS。两个旧任务的原 task/latest response/review 用于了解边界，不作为本支线的运行队列。只选择性复用本 base 已有接口；不得为取得 FEINN 代码整体 merge 第二分支。

## 2. 文献选择与可证伪假设

完整文献比较见 [literature_review.md](literature_review.md)。本合同是研究设计，不是论文逐项复现。

优先借鉴 McMg（arXiv:2606.30495v2）的“介质相关 setup 与残差线性 apply 分离、多通道层次修正”；结合 deep Maxwell multilevel solver（arXiv:2509.03622）的真实残差和 Krylov 外壳。Meta-MgNet、Wave-ADR-NS 和 Krylov-aware training 是备选依据。McMg 的标量 Helmholtz 及结构化差分实验，不能直接转成 Nédélec/Floquet/DtN 的三维资格。

三个独立问题必须分别回答：

| 假设 | 通过需要的证据 | 不能替代它的证据 |
|---|---|---|
| H1：网络产生有用修正 | 未参与训练的残差上，固定成本修正优于相同结构的非学习对照 | 训练 loss 下降、网络参数更少 |
| H2：修正模块能成为求解器或 PC | 独立迭代或 FGMRES 达到原方程及场/通道全部门限 | 预条件残差小、少数迭代下降、能量恰好闭合 |
| H3：对单次新问题有实际价值 | 正确性相同，计入数据、训练、setup、求解、验证后时间/内存有收益 | 只报告迭代数或把训练全部隐藏为免费离线成本 |

首轮采用“算子条件化、残差线性”的轻量实现，防止网络频繁运行或缓存膨胀吃掉收益。自动选择求解器/周期数属于后续条件分支，不是先训练大型策略网络的理由。

## 3. 空 WSL 目录初始化与隔离

用户已选好的当前 WSL 空文件夹本身就是仓库根，不再嵌套 MyFEniCS。Codex 自行识别当前目录的真实路径，检查 WSL、Linux 文件系统、owner、权限、symlink 和目录内容。不得把工作站 `/home/fenics/Projects/NN-Lab` 或 `NN-Lab-V2` 用作本机路径。不得在 `/mnt/c`、`/mnt/d` 或 Windows 网络目录执行正式数值工作；路径不合格时只隔离这个阻塞，不强行搬移用户文件。

确认目录为空后，使用 WSL 内 Linux git，非交互 clone：

```bash
GIT_TERMINAL_PROMPT=0 git clone --single-branch \
  --branch task42extra_NN-V3-learned-iteration \
  https://github.com/Rookie1234567/MyFEniCS.git .

git branch --show-current
git remote get-url origin
git rev-parse HEAD
git merge-base --is-ancestor 5b489b7264b75a9461577303ff0f6bc8907c19dd HEAD
git status --short --branch
```

已经是正确本任务工作树时核对身份、upstream 和 ahead/behind 后续接；有未提交文件、不同仓库、分歧或非空未知目录时不 reset/clean/stash/覆盖。认证失败报告 AUTH_REQUIRED，不索取或输出密钥、不反复等待密码。可继续不依赖远端的已取得文档/纯数组工作。

Windows Codex 客户端可以保持不变，所有 git/python/mpiexec/FE/ML 命令实际通过 WSL 执行，不要求用户改用 Linux Codex CLI 或换前端。环境安装、源码接线由 Codex 完成，不把能够自行解决的初始化步骤丢回用户。

只在本目录建立独立 FE/ML activation、环境和 ignored 缓存。优先使用仓库已验证的安装配方及现场兼容版本；不得全局 pip upgrade、改系统 BLAS/MPI/CUDA/驱动、改 WSL 配额/swap 或升级其他环境。FE 与 ML 优先不同进程，通过哈希化 action packet 交换，FE 顶层不导入 Torch。必要依赖仅装入本任务私有前缀；需要提权或改变系统配置时停止相关安装，保留其余可做工作。

提交后明确推送：

```bash
git push origin HEAD:refs/heads/task42extra_NN-V3-learned-iteration
```

不新建相近执行分支，不 rebase/merge master 或另外两条活动分支，不 amend、不强推、不自动追随其他分支 HEAD。必要上游修复只允许在本支线说明来源后最小移植并重测。

## 4. 笔记本资源与首轮预算

不要假设第三台笔记本有 CUDA、独显、16 GiB 或工作站级内存。先记录 WSL 版本、CPU/物理核、有效 RAM/cgroup 限额、MemAvailable、磁盘、GPU/VRAM及驱动、Python/库身份。GPU 不作为启动前提；首轮 CPU-only，MPI1、数学线程1、Torch intra/inter-op1、DataLoader0。确认资源与 ABI 后，后续 review 再决定 GPU 性能试验，首轮不为 GPU 卡住研发。

规划上限不是实测。设有效 RAM 为 W，启动时 MemAvailable 为 M，系统余量 R=max(4 GiB,0.20W)，本任务 hard 上限 H=min(8 GiB,0.40W,M-R)。warning=0.8H。H 小于 2 GiB 时不运行正式 FE/训练，只完成小数组接口、代码和资源报告。每个重型阶段重新检查 M，不能沿用启动时余量。至少保留 15 GiB 磁盘自由量，artifact 总量上限 10 GiB；不会用 OOM 探索容量。

一次只运行一个重型进程树。使用实际可用的 cgroup 或轻量 process-tree watchdog，约 0.5 秒采样；区分采样峰和连续内核限额。监控本任务所有子进程、WSL 内自身 swap、VRAM和退出清理；自身 swap 必须为0，不用 OOC。Windows host pagefile 未监测时写 UNKNOWN，不由 WSL swap0推出 host pagefile0。触及资源线只停止本任务后代，保存可审计原因；不 kill、暂停或扫描其他项目的大日志。

首轮新增数值/辅助/失败恢复累计预算 **43200 秒**，不是最少必须跑满，更不是保证得到目标解。建议上限：接口及本地 reference 7200s，两个训练种子合计14400s，冻结评估14400s，扩展/证据7200s；未使用预算可在总额内分配，设计 commit 记录实际子预算。时钟和失败成本跨会话恢复继承，不能通过重新开会话或换文件夹刷新。每个求解候选初始上限1800s，有限延长必须在预注册预算内，不能按 reference 误差择优延长。

实现/环境耗时与数值耗时分列，并报告真实总日历经过时间。短暂调试/检查后继续执行有依赖条件满足的阶段，不因单个脚本失败直接结束整轮；正常数值停滞也不能伪装成工程 bug 来无限重试。

## 5. 原算子、固定 micro 与有限元一致性

先复用 base 中原 0.7 nm micro 的物理定义、材料表、真实非可分三维缺口和独立验算方法。新 clone 不包含 ignored 的旧 packet/参考/权重；必须由已提交的生成接口在本机重建，不假设旧绝对路径可用、不从工作站复制活跃数组。

| 项目 | 固定 anchor M0；不是最终目标规模 |
|---|---|
| 物理 | 真空波长0.7 nm，grazing1度、azimuth0、s；原 nonseparable micro |
| FE | 原384 hex、p3、h0.175 nm、q15；完整自由度/约束布局与 base 对应 |
| 边界 | 双 Floquet，layered background，原完整 Fourier-DtN；不换成 PML/周期占位边界 |
| 规模 | 原 full34050、trace18144、内部13824、slave2082；20+20 ports；184? 不使用估算，完整 retained 必须18184 |
| 材料 | `input/materials/si_optical_constants_v1.json`；Si n=0.999885140474+4.32477054e-6i；epsilon=n*n |
| 名义波长映射 | source0.699999988 到 nominal0.7 的已授权 alias；不重新索要、不随意插值 |
| 精度 | 原 action/审核 complex128；ML float64 实虚通道或 complex128，禁隐式 float32/AMP/TF32 |

上述规模行中的完整 retained 值为 **18184=18144+40**，实施不得以任何近似维数接线。物理/material hash 与旧已记录值配对核查；WSL 重建浮点数组允许不同 byte hash，但必须保持 schema/配置语义并通过作用、伴随、恢复的数值身份检查，不能把跨 ABI bitwise 不同自动写成同一个 hash。

令凝聚原方程按真实符号组成如下分块；下面 F 已包含实现中的负号，不能按变量名猜符号：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\qquad
\bar S=K-CH^{-1}F,\qquad \bar b=b_t-CH^{-1}b_p.
```

```math
\alpha(t)=H^{-1}(b_p-Ft),\qquad z(t)=\begin{bmatrix}t\\\alpha(t)\end{bmatrix}.
```

H 是 **凝聚后的 Hhat**，不是 uncondensed Hp。允许准确解这个 micro 的小端口块，不允许把全局 Maxwell LU 藏到 learned PC 内。所有候选均从 t0=0、alpha0=H^-1 bp 出发，这是共同的消元初始状态，不冒称完整 z 全零。网络只产生独立 trace 修正，端口通过原方程恢复，最终恢复全部 FE 系数。

barS 的原矩阵自由作用、其真正复伴随、S、未凝聚 native/augmented/total residual 都需交叉验证。物理训练/求解期间不得构造全局 dense S、barS、A^H A 或全局 Riesz/Maxwell 因子；小型 authority 独立进程的 direct factor 只作验证，成本单列。小合成稠密矩阵可以用于单元测试，不可冒充 FE 运行。

读取 ActionPacket 的局部张量、MPC 稀疏 expansion/pullback、orientation/局部矩索引及真实几何元数据。Nédélec 系数不是节点上的 Ex/Ey/Ez，不能把一维编号 reshape 成规则图像后卷积。残差是代数对偶量，latent 映射必须明确定义，不把任意 pooling 叫作兼容 FE 插值。最小测试包括复数内积伴随、随机置换、单元局部 orientation、跨 Floquet 面相位、完整端口和内部恢复。

## 6. 学习模块：先做一个小而明确的候选

### 6.1 算子相关 setup，残差线性 apply

计划新增可复用核心模块于 `src/solvers/`，建议名称 `neural_multilevel_correction.py`、`neural_iteration.py`；名称是计划，不代表已存在。runner 保持薄层，case 参数进入独立配置，不能复制大量 task-numbered 数值脚本。

首轮采用 **拓扑/单元图版本的 McMg-inspired prototype**，不是直接复制结构化 CNN。基于原 FE 单元邻接和 trace incidence 建立固定层次；输入特征包含无量纲局部材料、kh、局部尺寸/方向、边界类别和 Floquet 信息。训练与测试各自用自己的合法算子特征，不能输入准确场。

非线性小网络在 setup 产生各层局部作用系数。残差路径仅使用无 bias 的复线性通道混合、稀疏 gather/scatter、固定聚合/延拓、有限次平滑与粗层局部作用。实虚双通道必须实现复线性块结构，测试 B(i r)=i B(r)；只满足实线性时不能声称复线性。禁止残差路径激活函数、依赖当前残差的归一化/门控、隐状态跨 apply 延续或测试中更新权重。

第一个实现固定 3 个层级（含细层）、每层8个复 latent 通道、每层至多2次前/后局部平滑、最粗层固定4次局部更新，不做 dense/global coarse factor。单元 trace 的高阶矩通道必须在 adapter 中明确，不把8个 latent 通道误称完整 FE 空间。保留廉价 trace-local skip，避免所有误差都被压入低维瓶颈；其固定非学习版本作为对照。先做该架构，不扫描网络深宽。

允许 operator-conditioned 复系数，参数总量上限500000。限制图边数与每层邻接度；禁止全局 attention、每个自由度独有的巨型权重矩阵或依赖全局准确解的基。setup 缓存只保存当前固定参数下必要的数值，不把整个训练 autograd 图常驻。记录参数、系数缓存、层次图、临时张量、batch/unroll 激活和原 packet 的同时峰值；“参数少”不是“总内存少”。

若已提交的 packet 缺少几何/邻接元数据，先在本分支补最小 exporter 和 schema；不猜坐标、不用旧参考场替代。若构造三层确有几何障碍，允许退为两层完成接口资格并记录架构偏差，但它不算完成三层数值比较，也不得悄悄把目标模型变为二维。

### 6.2 同一权重的两种用法

记固定 setup 后的修正模块为 B_theta。无 Krylov 候选 N：

```math
r_k=\bar b-\bar S t_k,\qquad
d_k=B_\theta r_k,\qquad t_{k+1}=t_k+d_k.
```

这是学习到的固定点迭代，不等于坐标 PINN。对固定复线性 B，误差传播矩阵为 I-B_theta barS；有限维精确算术下其谱半径小于1可保证渐近收敛，但非正规瞬态、有限精度和目标模型的实际稳定性仍须验证，不能由训练平均 loss 推出。

同一权重另外运行 N-safe，不使用 Krylov 或隐藏 fallback，但允许原残差一维最小化：

```math
q_k=\bar S d_k,\qquad
\omega_k=\frac{q_k^H r_k}{q_k^H q_k},\qquad
t_{k+1}=t_k+\omega_kd_k.
```

分母为零/数值退化时明确记录无有效方向，不能捏造更新。用原完整残差复核接受；这只提供当前方向上的保护，不保证严格下降或收敛。它含确定性的步长运算，应称“带残差保护的学习迭代”，不宣传每个算术步骤都是神经网络。

候选 P 使用 **右预条件 FGMRES**，预条件 apply 为同一个冻结 B_theta；restart固定32，初始状态、算子、门限、线程和正式预算与对照相同。正确记录 Arnoldi/实际 matvec/restart 数，不能把 callback 次数当迭代数。首轮禁止残差依赖自适应 PC 和在线回训；未来若允许变化或非线性，仍需 FGMRES 而不能默认为固定线性 GMRES。三种候选都从同一个共同初始状态独立开始，不能把 N 的末态当 P 的免费 warm start。

N 或 N-safe 失败不阻塞 P：独立固定点收敛与成为有效预条件器不是同一个条件。P 若依然失败，完成等成本残差比较和失败分析，不重启无限超参搜索。

## 7. 不依赖目标准确解的训练

训练数据只使用允许的 A/S 作用、网格/材料/边界与人工生成的向量。原 reference、旧 GPOLY/GNN basis、旧 LSQR 终态、FEINN 监督权重、准确散射场、误差向量都不进入模型、特征、初始化或超参选择。

允许生成 e 并令 r=barS e，得到合成代数样本；这是 **synthetic algebraic supervision**，不能冒称全无标签或物理 blind test。主要训练用短展开残差损失：

```math
r_{j+1}=r_j-\bar S B_\theta r_j,\qquad
\mathcal L=\frac14\sum_{j=1}^{4}
\frac{\|r_j\|_2^2}{\|r_0\|_2^2}.
```

非零初始残差才计算该比值，zero RHS 单独处理，不用任意大 epsilon 掩盖极小分母。反向通过原作用使用正确复伴随和实参数链式法则；先做 finite-difference/adjoint tests。不能用 approximate latent operator 来代替原 barS 计算训练/验收残差。

训练残差要包含随机、按波长相位变化的代数向量、低/高空间变化及合法零标签迭代中收集的困难残差。生成规则、seed、切分和条数在实验前提交。只用白噪声的验证不能证明能修正 Krylov 后期误差；最终保留独立真实轨迹验证。每次训练的4步展开均计成本，不把一个 optimizer step 当一次 solver iteration。

首轮默认 Adam、学习率1e-3、batch2、展开4步、每种子最多1000 updates，两个固定种子17/29；以总计14400s和资源上限先到者收口。先进行20步 smoke，再继续。checkpoint 只按预注册的 validation residual-loss 选择；reference 审核前冻结。非有限梯度允许工程诊断及一次有记录的数值尺度修复，不能靠降到 float32 或任意改物理解决。

允许把原 micro 的算子用于自适应准备/训练，但必须标 `operator_seen_in_training=true`，其必要训练成本计入单次冷启动；它本来也已被历史审阅，不称 blind。至少一个同算子未训练 RHS 和一个新算子的 transfer 测试要与它分开。监督 teacher 路线不在首轮范围内。

## 8. 首轮实施矩阵与不要轻易中断的执行顺序

| 阶段 | 必做工作 | 依赖失败时继续做什么 |
|---|---|---|
| F0 | Git/WSL/资源/ABI；旧线事实摘录；设计与预算 commit；准备私有环境 | FE 不可用仍做 pure-array 接口、训练/线性性测试与源码接线，不冒称 Maxwell |
| F1 | 本机重建 M0 原 packet、作用/伴随/恢复/端口 qualification；隔离的小 authority | 超内存可做更小3D smoke，但记录不同 case，M0=NOT_RUN_BY_RESOURCE，不替代 M0 |
| F2 | 实现 fixed operator-conditioned 三层模块、cached/uncached 一致性、复线性和复杂度测试 | 层次失败可完成 local-only 对照与 adapter 修复，不能因此删除 coarse 问题 |
| F3 | 同预算非学习对照及两个训练种子；冻结模型/配置/hash | 一种子失败保留另一种子及未训练对照；reference 不参与选择 |
| F4 | 在 M0 运行 N、N-safe、P 和对应基线；冻结后独立 FE 审核；至少独立 RHS 测试 | 某独立迭代失败仍运行 P；没有任何准确解时保留等成本下降表，不计算虚假 speedup |
| F5 | 条件 transfer/尺寸试验；目标规模成本与阻塞分析；全部证据及交付 | 数值 Gate 不足仍完成容量账、代码测试和明确负结果，不能用“不成功”代替报告 |

F3/F4 最少对照集合：

| ID | 算法 | 用途 |
|---|---|---|
| C0 | 无 PC 的 FGMRES32 | 直接原方程基线；不能称最优传统求解器 |
| C1 | 相同 trace-local skip/固定层次的非学习 PC + FGMRES32 | 排除收益仅来自新增数值结构或缩放；实施中明确定义系数 |
| C2 | 同初始化、未训练 B + FGMRES32 | 排除随机结构已提供主要收益；训练与未训练的输入/算子一致 |
| N/N-safe | 同一训练模型，独立固定点及受保护迭代 | 回答能否不用 Krylov 求合格解 |
| P | 同一训练模型 + FGMRES32 | 回答学习模块作为 PC 是否更实用 |

C1 若需要一个稳定的非学习版本，可采用已验证的 trace-local 对角/块作用加固定几何传递；非正定 Maxwell 不保证 Jacobi 能平滑，实际失败如实报告。不得为了做“强基线”偷偷恢复全局 p4 factor，也不得把弱 C0 当作所有传统方法的上限。每个候选同机器、同精度、同初始状态、同停止门限；对候选运行顺序做配对交错，记录冷/热缓存身份。

条件 F5：至少一个学习候选在 M0 通过完整 Gate，且相同实际预算下有可重复信号后，使用冻结模型测试 **M1：原几何、0.7nm、s、grazing2度、azimuth0**；训练前不得读取 M1 准确解。此项测试同时改变算子和 RHS，需按新角度重建 Floquet/DtN，不仅改 b。最多再做一档同物理、同 p、稍大网格/域的规模试验，具体尺寸必须先经过资源模型并登记；一次跨尺寸不证明目标规模 mesh-independent。若 M0 未通过，M1 求解可以不运行，仍完成 M1 配置/预检及总量预测。

首轮不执行自动求解器选择训练。可以写一个固定菜单接口和可用特征 schema，待至少两个动作有有效、可区分收益后，再由 review 授权轻量选择器。没有可用候选时，让网络“选择哪个”不能消除原求解障碍。不得转向 AutoML、强化学习大搜索或百万 teacher 样本生成。

## 9. 准确性 Gate、训练成本与晋级

全部最终判断用冻结迭代状态独立计算。原始总场/散射场、E/curl/H、每级复通道与功率、体吸收均保留；不得对齐 reference 的整体相位/幅值后宣称求解误差合格。

| 项目 | 首轮门限/要求 | 身份 |
|---|---|---|
| 原 S 相对真残差 | <=1e-6；固定原物理 b 的范数 | measured；不是 correction RHS 或内部 preconditioned norm |
| 未凝聚 native/augmented 与独立 total equation | 各 <=1e-6，沿用其原物理 RHS 定义 | measured；分别保留分子/分母 |
| 散射 E 与 curl/H 相对离散 reference 误差 | 各 <=1e-4 | measured；同一离散，不是 continuum error |
| 完整复通道误差 | <=1e-4；接近零通道使用预注册绝对尺度 | measured；不可删除弱通道 |
| R/T/A/A_volume 与独立能量差 | <=1e-5；逐级功率绝对差<=1e-6 | candidate 合格前全为 UNQUALIFIED_DIAGNOSTIC |
| 约束、方向、端口/内部恢复与数学作用身份 | 严格沿用 base 对应测试阈值；新纯数组复线性/伴随相对误差目标<=1e-10 | 不用 solver residual 宽松阈值掩盖接线错误 |
| 资源 | 不越 H，不自身 swap/OOC；完整过程树和开销账 | 采样/预测/未观测明确区分 |

自建离散 reference 的 residual 必须比候选门限显著更严格（目标<=1e-10），并通过独立恢复和物理审核；否则只能做原方程诊断，不能声称 reference 场误差可靠。reference 生成不可反哺训练。为首轮检验发生的 reference 成本计入研究总账；最终没有 exact reference 的大模型验证需要另行制定网格/阶次/端口收敛与物理验证合同。

分别报告：

```math
T_{\mathrm{cold}}=T_{\mathrm{data}}+T_{\mathrm{train}}+T_{\mathrm{setup}}
+T_{\mathrm{solve}}+T_{\mathrm{verify}}.
```

```math
T_{\mathrm{warm}}=T_{\mathrm{new\ setup}}+T_{\mathrm{solve}}+T_{\mathrm{verify}}.
```

研究全过程还要另外包含所有失败、对照、reference、环境/辅助费用，不能把多路线总时钟冒充某条成功单次求解。最终0.7nm/48h主张针对一个新目标，必须指出预训练是否已有以及取得该模型的成本，不能仅拿 warm 指标达标。多个新 RHS 的摊销收益与单次冷启动收益分开。

首轮“神经加速正信号”要求：P 或 N 对同机最快已合格非学习对照，在同样精度下 solver+setup 实测至少节省20%，且两个种子/重复配对不出现一致反向结论；同时报告 cold 全成本是否真正获益。20%是本任务研究筛选阈值，不是数学结论。不合格对照或不合格候选不能作为 time-to-solution 分母；只可给同成本残差/场表、censored 时间和待解原因。冷启动未获益时不得写单次目标加速通过。

## 10. 面向0.7nm大模型的容量说明

小波长 micro 成功只回答局部算法问题，不代表原几何和最终规模通过。首轮必须输出目标可行性表：从当前项目正式物理定义读取实际目标尺寸、材料、网格/p和端口截断要求；任意非可分单胞能力不能退化为二维截面或可分结构。

表中包括 N、单元内部消元存储、trace/原作用 packet、原端口数量及缓存、各层图边/通道/系数、FGMRES V/Z 基、训练展开激活、checkpoint、MPI复制/通信及验证成本。固定 restart32 的复双精度 FGMRES，仅 V/Z 主向量理论下界约为16N(2m+1) bytes（m=32），不包括其他向量/对象；不能把网络参数量当全部内存。目标端口数量必须重新估算，不能固定 micro 的40。

分列 measured / derived / predicted / not_run，给出预测假设和最薄弱环节。3层固定局部算子并不自动保持跨大域的传播能力；更深层次、更多通道、跨方向通信可能增加训练、setup与内存。约2TB是目标整机物理内存，不是可全部分给某个因子的净预算。笔记本仅承担原型和受控证据，不访问或占用其他工作站完成目标大算例。

## 11. 自主修复与交付

每个明确工程根因最多3次有假设/改动/测试/重试记录的修复，全部成本保留。允许修 schema、符号/维度、兼容 API、计时、原子 checkpoint、目录/JIT缓存、复数伴随和测试夹具；禁止改物理/容差/训练测试边界以制造通过。同一数值路线最多2次故障恢复；用原完整状态和已消耗预算续接，不能选择 reference 误差最小的旧状态。正常停滞进入诊断和其他独立阶段，不自动触发重训。

正式数值入口前提交干净实现，记录 actual run source SHA 与最终文档 HEAD；二者不能混用。权重/矩阵/完整场/长轨迹放 ignored，Git只留 compact hash-bound records。单JSON建议<=200KiB，完整历史保留文件hash与实际路径。

交付至少包括：

| 文件/范围 | 内容 |
|---|---|
| `response_v1.md`、`outcomes/summary.md` | 表格优先的范围、方法、数值、资源、失败/not_run、下一步和是否值得继续；通俗解释网络到底做哪一步 |
| `outcomes/records/` | environment、Git/source、固定配置/seed/切分、operator身份、model hash、运行索引、真实残差历史、结果CSV、成本/资源、repair log、验收重算 |
| `outcomes/scalability.md` | 冷/热成本、单次与多次区别、最终0.7nm尺寸/内存/通信预测及不可外推项 |
| `outcomes/tests.md`、`outcomes/changed_files.md` | 最小及最终回归、compileall/lint范围、未运行项、组件依赖与 selective merge 分类 |
| 仓库级文档 | 本支线内追加 `docs/development_progress.md`、`docs/development_model_registry.md`；不覆盖旧任务事实 |

没有 GitHub Actions 不称CI通过。Markdown用 fenced math、列数一致表格；原始文本检查和 GitHub rendered view 视觉确认分列，未取得视觉证据写 NOT_VERIFIED，不伪造截图。未运行不得预填 PASS。新求解器显式 opt-in，普通入口默认不变，全部 research-only。

首轮完成所有可做且有预算的工作后，推送本分支，报告完整 HEAD、base、upstream、工作树、实际命令与环境、最好且合格/不合格状态、原真残差、全成本、证据入口，再停止等待 review。不要只交“环境装好”，也不要把没有成功写成“没有可交付内容”。
