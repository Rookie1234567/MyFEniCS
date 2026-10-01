# Task42extra NN-V3：学习迭代修正与神经预条件的独立对照研究

## 0. 任务身份、决定与授权

**本任务不再用坐标网络从零拟合一个场，也不恢复已关闭的全局 p4 强逆路线。主线是：学习一个有界成本、可重复调用的多层残差修正模块；用完全相同的冻结权重，分别检验不使用 Krylov 的学习迭代和右预条件 FGMRES。由真实精度与端到端成本决定去留，而不是预先宣布神经网络有效。**

网络负责建议“这一步该怎样改正错误”，原 Maxwell 方程负责检查建议是否有效。准备阶段可由网络生成与介质、网格和边界有关的系数，同一次求解中缓存这些系数。多层通道用于尝试保留传播方向与相位信息，不代表已经拥有准确粗逆。

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

用户本轮明确授权 ChatGPT 创建本分支、检索论文并写任务书，覆盖通常由 Codex 建分支的规则；选择上述冻结研究 SHA 覆盖默认从 master 创建的规则。继承源码不是批准整体合并研究代码。本笔记本的独立 clone 是这台机器本任务的 canonical repository，不要求访问工作站 common Git，也不要求建立工作站 linked worktree。

这是第三条独立研究线。旧两分支只读，不执行它们的待办，不恢复它们的 checkpoint，不继承它们的计时预算或远程路径。不得 SSH 操作其他机器，不改变其他任务的文件、分支、进程、环境、缓存和负结果。全部实现、review、response只推送本执行分支；master和其他分支均不写入。

## 1. 已核对现状与新任务差异

下表来自2026-10-01读取的远程记录，不是现场监控或新笔记本实测。

| 研究线与冻结 HEAD | 已记录结果，measured/recorded | 本任务不得重复的工作 |
|---|---|---|
| Task042；5b489b7264b75a9461577303ff0f6bc8907c19dd | Response V18；GPOLY-R 原Schur残差1.463077182e-4、散射E误差8.079990122e-5；GNN-R分别1.995563747e-4、1.001991308e-4；完整资格0/8 | 不把基空间LSQR后的GMRES/LGMRES校正重复执行并称NN-V3；不恢复已关闭p4低内存强逆 |
| Task42extra FEINN；47317bb648d5e2237657f8b6c75c239ab5bf55c5 | Response V9；5nm plain/phase GN 原残差约1.0285/1.0187，散射E误差约0.9989/0.4372；没有无标签准确求解 | 不再做坐标到场网络、完整矩FEINN、Riesz因子与全参数GN续算 |
| FEINN独立p5 reference | native约1.22906e-11；过程树峰约6.70GiB；p4/p5 curl/H仍存在超过1e-3的敏感性 | 参考成功不是NN成功；工作站内存/时间不能冒充笔记本实测 |

证据入口：[Task042 Response V18](https://github.com/Rookie1234567/MyFEniCS/blob/5b489b7264b75a9461577303ff0f6bc8907c19dd/docs/task042_neural_coarse_inverse/response_v18.md)、[Review V16（授权V19）](https://github.com/Rookie1234567/MyFEniCS/blob/5b489b7264b75a9461577303ff0f6bc8907c19dd/docs/task042_neural_coarse_inverse/review_report_v16.md)、[FEINN Response V9](https://github.com/Rookie1234567/MyFEniCS/blob/47317bb648d5e2237657f8b6c75c239ab5bf55c5/docs/task042extra_feinn_5nm/response_v9.md)、[Review V9](https://github.com/Rookie1234567/MyFEniCS/blob/47317bb648d5e2237657f8b6c75c239ab5bf55c5/docs/task042extra_feinn_5nm/review_report_v9.md)。已读接口是`src/solvers/neural_fe_action_packet.py`的ActionPacket，包括S/SH、恢复、未凝聚审核与Floquet pullback；其存在不证明新PC已资格化。

开始前读根AGENTS、docs/AGENTS、仓库原则、Markdown标准、本目录README/task/literature_review、以后出现的补充合同和最新review/response/summary，再读实际改动目录AGENTS。旧两任务的原task和最新response/review用于理解边界，不作为本支线运行队列。只选择性复用本base已有接口；不整体merge第二分支。

## 2. 文献选择与可证伪假设

完整比较见[literature_review.md](literature_review.md)。优先借鉴McMg（arXiv:2606.30495v2）的介质相关setup/残差线性apply分离与多通道层次修正，结合deep Maxwell multilevel solver（arXiv:2509.03622）的真实残差和Krylov外壳。Meta-MgNet、Wave-ADR-NS、Krylov-aware training是后续依据。本合同是研究设计，不是论文逐项复现；标量Helmholtz/结构化差分不能直接迁移为Nédélec/Floquet/DtN资格。

| 假设 | 通过需要的证据 | 不能替代它的证据 |
|---|---|---|
| H1：网络产生有用修正 | 未训练残差上，固定成本修正优于同结构非学习对照 | 训练loss下降、参数少 |
| H2：模块能成为求解器或PC | 独立迭代或FGMRES通过原方程、场/通道全部门限 | 内部预条件残差小、少数步下降、能量碰巧闭合 |
| H3：对单次新问题有价值 | 相同正确性，计入数据/训练/setup/求解/验证后有时间或内存收益 | 只比迭代数，或隐藏离线成本 |

首轮采用算子条件化、残差线性的小模块。自动选择求解器/周期数不作为首轮训练目标；必须先存在真正可用的候选动作。

## 3. 从空WSL目录独立启动

用户已选择的当前WSL空文件夹本身是仓库根，不嵌套MyFEniCS。Codex自行确定真实路径、检查WSL/Linux文件系统、owner/权限、symlink与目录内容。不使用工作站NN-Lab/NN-Lab-V2路径，不在`/mnt/c`、`/mnt/d`或Windows网络目录正式运行。路径不合格时只隔离这个阻塞，不强行搬移用户文件。

确认目录为空后用WSL内Linux git执行：

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

已是正确本任务工作树则核对upstream、ahead/behind及新合同后续接；非空未知目录、不同仓库、dirty或分歧时不reset/clean/stash/覆盖。认证失败报告AUTH_REQUIRED，不索取/输出密钥，不反复等待密码；继续不依赖远端且已经具备条件的工作。

Windows Codex客户端保持不变，实际git/python/mpiexec/FE/ML命令全部通过WSL执行，不要求换Linux Codex CLI。克隆、安装可隔离的必要依赖、接线和测试由Codex完成，不把能自行解决的步骤交回用户。

在本目录建立私有FE/ML activation、环境及ignored缓存。优先采用仓库已验证配方和现场兼容版本，不全局pip upgrade，不改其他环境、系统BLAS/MPI/CUDA/驱动/WSL配额/swap。必要依赖只装本任务私有前缀；需要提权或系统变更则停止相关安装。FE/ML优先分进程通过hash-bound packet交换，FE顶层不导入Torch。确认PETSc ScalarType为complex128、IntType及DOLFINx/Basix/FFCx/MPC/MPI ABI一致，记录实际解释器、模块及动态库路径。

代码和缓存不得通过symlink写到旧目录。准确推送命令：

```bash
git push origin HEAD:refs/heads/task42extra_NN-V3-learned-iteration
```

不创建近似分支、不merge/rebase master或其他活动分支、不amend/强推、不自动追随它们的HEAD。必要上游修复只作注明来源的最小移植并重测。

## 4. 笔记本资源与首轮预算

先记录WSL、CPU/物理核、有效RAM/cgroup限额、MemAvailable、磁盘、GPU/VRAM和驱动，不假设笔记本有独显或固定内存。首轮CPU-only、MPI1、数学线程1、Torch intra/inter-op1、DataLoader0。GPU不是启动前提，后续review再讨论加速，不能因此卡住研发。

设有效RAM为W、启动时MemAvailable为M，系统余量R=max(4GiB,0.20W)，本任务hard上限H=min(8GiB,0.40W,M-R)，warning=0.8H。H<2GiB时只做有界pure-array/代码/报告，不启动正式FE或训练。每个重型阶段重查M；至少保留15GiB磁盘自由量，artifact总量<=10GiB，不用OOM探容量。上述是规划上限，不是实测。

一次只运行一个重型进程树。采用实际可用cgroup或约0.5秒的轻量process-tree watchdog，区分采样峰和连续内核上限；记录全部后代、自身WSL swap、VRAM和退出清理。自身swap=0，禁止OOC。未监测Windows host pagefile时写UNKNOWN，不能由WSL swap0推为host pagefile0。触线只停止本任务后代，保存原因，不kill/暂停其他项目或扫描其大日志。

首轮新增数值/辅助/失败恢复累计上限**43200秒**，不是最低必须跑满，也不是目标解承诺。建议接口及本地reference7200s、两训练种子合计14400s、冻结评估14400s、扩展/证据7200s；可在总上限内调配，在设计commit预注册实际子预算。每个求解候选初始上限1800s；延长必须来自预注册剩余预算，不按reference误差挑选延长。跨会话继承已消耗时间，不能重开目录/会话刷新。另列实现/环境耗时和真实总日历时间。

单个工程故障不取消不依赖它的阶段；正常数值停滞不伪装成bug来无限重试。完成全部有条件且有预算的工作后收口，不只交环境安装。

## 5. 原算子与固定0.7nm micro

新clone不包含ignored的旧packet/参考/权重，必须使用已提交生成接口在本机重建。不得假设旧绝对路径可用，不访问工作站复制活跃数组。复用base原micro的完整非可分几何、材料和独立审核方法，不另造二维替代模型。

| 项目 | 固定anchor M0；不是最终目标规模 |
|---|---|
| 物理 | 真空0.7nm，grazing1度、azimuth0、s，原nonseparable三维缺口micro |
| FE | 原384hex、p3、h0.175nm、q15；完整自由度/约束布局与base一致 |
| 边界 | 双Floquet、layered background、原完整Fourier-DtN；不换PML或占位边界 |
| 规模 | full34050；trace18144；内部13824；slave2082；top20+bottom20 ports；retained18184=18144+40 |
| 材料 | input/materials/si_optical_constants_v1.json；Si n=0.999885140474+4.32477054e-6i；epsilon=n*n |
| 波长映射 | 已授权source0.699999988到nominal0.7的alias，不重索要、不随意插值 |
| 精度 | 原作用/审核complex128；ML float64实虚通道或complex128；禁隐式FP32/AMP/TF32 |

核对原physical/material hash。跨WSL/ABI重建允许数组byte hash不同，但必须保持schema/配置语义并通过作用、伴随、恢复身份检查；不能把新数组冒写旧hash。

按实现真实符号定义原凝聚分块，F已经包含代码中的负号，不能凭变量名猜符号：

```math
S=\begin{bmatrix}K&C\\F&H\end{bmatrix},\qquad
\bar S=K-CH^{-1}F,\qquad \bar b=b_t-CH^{-1}b_p.
```

```math
\alpha(t)=H^{-1}(b_p-Ft),\qquad
z(t)=\begin{bmatrix}t\\\alpha(t)\end{bmatrix}.
```

H必须是凝聚后的Hhat，不是uncondensed Hp。允许准确解micro小端口块，不允许把全局Maxwell LU藏进PC。所有候选从t0=0、alpha0=H^-1 bp共同初始状态出发，不冒称完整z全零；网络仅给独立trace修正，原方程恢复端口及全部FE系数。

barS的matrix-free作用及真正复伴随、S、未凝聚native/augmented和独立total方程都要配对验证。物理训练/求解禁止全局dense S、barS、A^H A、全局Riesz或Maxwell因子；小型authority的direct factor只在独立审核进程使用，单列成本。合成稠密小矩阵仅供单元测试，不冒充FE。

读取ActionPacket的原局部张量、MPC expansion/pullback、orientation/矩索引和几何元数据。Nédélec系数不是节点Ex/Ey/Ez，不能按一维编号reshape图像后卷积。残差是代数对偶量，latent映射必须明确，不把任意pooling称为兼容FE插值。测试含复内积伴随、自由度置换、局部orientation、Floquet相位、完整端口和内部恢复。

## 6. 一个小而明确的学习模块

### 6.1 setup与apply

数值核心进入`src/solvers/`可复用模块；建议新名`neural_multilevel_correction.py`、`neural_iteration.py`（计划名称，并非已实现）。runner为薄层，case参数单独配置，不复制多个task-numbered数值脚本。

采用**拓扑/单元图版McMg-inspired prototype**，不是直接复制结构化CNN。基于FE单元邻接与trace incidence建立固定层次；setup输入无量纲材料、kh、尺寸/方向、边界类型和Floquet信息，不输入准确场。非线性小网络生成各层局部系数，固定参数和算子下缓存复用。

残差apply只允许无bias的复线性通道混合、稀疏gather/scatter、固定聚合/延拓、有限次平滑和粗层局部更新。实虚通道实现复线性块结构，测试B(i r)=i B(r)及叠加性；仅实线性不得称复线性。禁止残差激活、残差依赖归一化/门控、跨apply隐状态、测试时更新权重。cached与uncached数值一致、参数更新后缓存失效，必须测试。

首个实现固定3层（含细层）、每层8个复latent通道、每层至多2次前/后局部平滑、最粗层固定4次局部更新，不做dense/global coarse factor。高阶trace矩在adapter明确，不把8个latent通道说成完整FE空间。保留廉价trace-local skip，防止全部误差只经过低维瓶颈，其固定非学习版进入对照。参数总量<=500000，限制图边/邻接度，不扫描深宽，不做全局attention或每自由度巨型独立权重。

记录原packet、参数、系数缓存、层次图、临时张量、batch/unroll激活同时峰值；参数少不代表总内存少。setup缓存不保留整训练图。若packet缺元数据，补最小exporter/schema，不猜坐标/方向。三层有工程障碍时允许两层接口资格，但记录偏差，不算三层试验完成，更不能改二维。

### 6.2 同一权重的两种用法

固定setup后的修正为B_theta，无Krylov候选N：

```math
r_k=\bar b-\bar S t_k,\qquad
d_k=B_\theta r_k,\qquad t_{k+1}=t_k+d_k.
```

这是学习固定点迭代，不是坐标PINN。固定复线性B下误差传播为I-B_theta barS；有限维精确算术谱半径<1可保证渐近收敛，但非正规瞬态、有限精度、目标谱均需验证，训练平均loss不能提供该保证。

另外用同一权重运行N-safe，不用Krylov或隐藏fallback，仅增加确定性的原残差步长：

```math
q_k=\bar S d_k,\qquad
\omega_k=\frac{q_k^H r_k}{q_k^H q_k},\qquad
t_{k+1}=t_k+\omega_kd_k.
```

分母为零/数值退化时记录无有效方向，不捏造更新。原完整残差复核接受；该保护不保证严格下降或收敛。它应称“带残差保护的学习迭代”，不说每个算术步骤都是NN。

候选P为**右预条件FGMRES32**求原barS方程，PC apply是同一冻结B_theta；同初始状态、精度、线程、门限和预注册预算。正确记录Arnoldi、原作用、restart、显式残差审核次数，不能把callback数当迭代数。首轮无自适应PC/在线回训；将来允许非线性或可变PC仍应采用匹配的灵活外层，不能默认为固定GMRES。

N/N-safe/P各自从共同初始状态独立开始，不把N末态当P免费warm start。N失败不阻塞P，因为独立固定点收敛和有效PC不是相同条件。P失败后保留等成本诊断，不无限换模型。

## 7. 不读取目标准确解的训练

只使用合法A/S作用、网格/材料/边界和人工向量。禁止原reference、旧GPOLY/GNN基、LSQR终态、FEINN监督权重、准确散射场或误差向量进入特征、训练、初始化或超参选择。

允许人工e与r=barS e的代数样本，身份明确为synthetic algebraic supervision，不冒称完全无标签或physical blind test。主损失是原方程4步展开：

```math
r_{j+1}=r_j-\bar S B_\theta r_j,\qquad
\mathcal L=\frac14\sum_{j=1}^{4}
\frac{\|r_j\|_2^2}{\|r_0\|_2^2}.
```

zero RHS单列，非零比值不靠大epsilon掩盖小分母。反向使用原barS的正确复伴随及实参数链式法则，先做有限差分/伴随测试。latent近似算子不能替代原barS计算训练或验收残差。

样本含随机、波长相位变化、低/高空间变化及合法无准确解迭代生成的困难残差；预先提交生成规则、seed、条数和train/validation/test切分。仅白噪声验证不代表后期Krylov困难误差已解决。最终保留未训练的真实轨迹/RHS测试。一个optimizer step含4步展开及反向，不当作一次solver迭代。

默认Adam、lr1e-3、batch2、展开4步、每种子最多1000updates，固定种子17/29；合计14400s或资源线先到则收口。先20步smoke再继续。按预注册validation residual-loss选checkpoint，reference审核前冻结；非有限梯度可诊断并作一次有记录尺度修复，不降FP32、不改物理。预算/失败数不重置。

M0算子可用于自适应训练，但标operator_seen_in_training=true并把训练计入冷启动。M0本已历史审阅，不称blind；未训练RHS与新算子transfer另列。至少完成一个同算子未训练RHS；M1按条件执行。teacher准确解训练不在首轮范围。

## 8. 实施矩阵、对照与条件扩展

| 阶段 | 必做工作 | 依赖失败时继续做什么 |
|---|---|---|
| F0 | Git/WSL/资源/ABI、旧线事实、设计/预算commit、私有环境 | FE不可用仍做有界pure-array、训练/线性性和接线，不冒称Maxwell |
| F1 | 本机M0 packet、作用/伴随/恢复/端口qualification、隔离reference | 超资源可做更小3D smoke，但M0记NOT_RUN_BY_RESOURCE，不以smoke替代 |
| F2 | 三层修正、缓存一致性/失效、复线性、adapter与复杂度测试 | 继续local-only对照、元数据和层次修复，不删除coarse问题 |
| F3 | 非学习对照、两训练种子，冻结模型/配置/hash | 单种子失败保留另一种子及未训练对照，reference不选点 |
| F4 | M0的N/N-safe/P及基线，冻结后独立审核、未训练RHS | 独立迭代失败继续P；无合格解只报等成本下降，不算虚假speedup |
| F5 | 条件transfer/尺寸、目标规模账、测试/证据和交付 | 无数值晋级仍交容量分析、代码测试、负结果和明确阻塞 |

| ID | 算法 | 用途 |
|---|---|---|
| C0 | 无PC FGMRES32 | 原方程基线，不称最优传统求解器 |
| C1 | trace-local skip/固定层次的非学习PC+FGMRES32 | 排除新增结构/缩放本身收益；明确系数和成本 |
| C2 | 同初始化但未训练B+FGMRES32 | 排除随机结构收益 |
| N/N-safe | 同一训练B，独立固定点及受保护迭代 | 回答不用Krylov能否求准 |
| P | 同一训练B+FGMRES32 | 回答PC是否更实用 |

C1可用已验证的对角/小块作用和固定几何传递；非正定Maxwell不保证Jacobi是好smoother，失败如实报告。不偷藏全局p4因子，不将弱C0推广为所有传统方法上限。同机器同精度同初始状态同门限，配对交错运行，冷/热缓存身份分列。

条件F5：至少一个学习候选M0完整通过并有同成本可重复信号后，用冻结模型测试**M1：原几何、0.7nm、s、grazing2度、azimuth0**。M1准确解训练前不可读；角度改变应重建Floquet/DtN和RHS，不仅替换b。最多再作一档同物理同p、较大网格/域规模测试，具体尺寸先资源预检和登记。M0未过时M1求解可不运行，但完成其配置/预检。一次尺寸transfer不证明mesh-independent或目标规模容量。

首轮不训练自动选择器；可定义固定菜单和特征schema。至少两个动作实际有效、收益可区分后再由review授权轻量选择，不做AutoML/强化学习大搜索或百万teacher样本。

## 9. 准确性与成本验收

最终状态先冻结再独立验证，完整记录total/scattered E/H/curl、复通道及逐级功率、体吸收。不用reference进行整体相位/幅值对齐后宣称求解误差合格。

| 项目 | 首轮要求 | 身份/边界 |
|---|---|---|
| 原S相对真残差 | <=1e-6；固定原物理b范数 | 非correction RHS或内部预条件norm |
| 未凝聚native/augmented、独立total equation | 各<=1e-6，保留各自原物理RHS定义 | 分子/分母分别保留 |
| 散射E与curl/H相对离散reference误差 | 各<=1e-4 | 同离散，不是continuum误差 |
| 完整复通道误差 | <=1e-4；近零通道预注册绝对尺度 | 不删弱通道 |
| R/T/A/A_volume和独立能量差 | <=1e-5；逐级功率绝对差<=1e-6 | 全部资格前为UNQUALIFIED_DIAGNOSTIC |
| 约束/方向/恢复与作用身份 | 沿用base对应严格阈值；新增纯数组复线性/伴随相对误差目标<=1e-10 | 不用solver宽门限掩盖接线错误 |
| 资源 | 不越H、不自身swap/OOC；全树及成本账 | measured/derived/predicted/unknown区分 |

小authority的原residual目标<=1e-10，并通过独立恢复/物理审核，否则只能做原方程诊断，不报可信reference场误差。reference进程与训练隔离，费用计入研究总账。最终没有direct reference的大模型，另需网格/阶次/端口收敛和独立物理验证合同。

```math
T_{\mathrm{cold}}=T_{\mathrm{data}}+T_{\mathrm{train}}+T_{\mathrm{setup}}
+T_{\mathrm{solve}}+T_{\mathrm{verify}}.
```

```math
T_{\mathrm{warm}}=T_{\mathrm{new\ setup}}+T_{\mathrm{solve}}+T_{\mathrm{verify}}.
```

研究总账另含全部失败、对照、reference、环境/辅助成本，不冒充一条成功单次求解。最终0.7nm/48h必须说明新问题的训练、准备、求解和验证，不能只拿warm通过；多个RHS摊销与单次冷启动分开。

首轮“神经加速正信号”：同精度下，相对同机最快已合格非学习对照，学习候选solver+setup至少节省20%，两个种子/重复配对不出现一致反向结论；同时报告cold全成本是否获益。20%是研究筛选阈值，不是数学定理。未合格的候选/基线不能作time-to-solution分母，只报同成本残差/场、censored时间和失败原因。cold未获益不得写单次加速通过。

## 10. 目标0.7nm容量分析

小波长micro成功不等于原几何目标规模成功。读取项目正式目标的物理尺寸、材料、h/p和端口要求；不能把任意非可分三维缩成二维截面或可分结构。笔记本负责原型和证据，不访问其他工作站完成最终大算例。

容量表包含N、内部消元、trace/packet、端口数量/缓存、各层图边/通道/系数、FGMRES V/Z、训练展开激活、checkpoint、MPI复制/通信、验证成本。complex128且restart=m时仅V/Z主向量理论下界约16N(2m+1)bytes，本任务m=32，尚不含其他向量/对象。不能由模型参数量估总内存；目标端口不能固定micro的40。

分列measured/derived/predicted/not_run、假设与最弱环节。三层局部模块不自动拥有大域全局传播能力，新增层级/通道/方向可能增加成本。约2TB为整机物理RAM，不是可全部用于单因子的净预算。cold/warm、单次/多次、实际micro/实际目标四种身份不得混写。

## 11. 自主修复、证据和交付

每个明确工程根因最多3次有假设/改动/测试/重试证据的修复，每路线最多2次故障恢复，全部费用和计数继承。允许修schema、符号/维度、API、计时、原子checkpoint、JIT缓存、复伴随及夹具；禁止改物理、容差、train/test边界或删除负结果造通过。恢复用完整已提交状态，不按reference挑最佳历史点；停滞进入诊断和其他独立阶段。

正式运行前提交干净实现，绑定actual run source SHA；最终文档HEAD另报。权重/矩阵/完整场/长轨迹ignored，Git留compact hash-bound records，单JSON建议<=200KiB。无Actions不称CI；源码改变后重跑最终最小回归。普通入口不改默认，所有新算法research-only且显式opt-in。

| 交付 | 必须包含 |
|---|---|
| response_v1.md、outcomes/summary.md | 表格优先的范围、方法、数值、资源、失败/not_run、是否继续；解释NN实际改哪一步 |
| outcomes/records/ | 环境/Git/source、配置/seed/切分、operator身份、model hash、运行索引、真残差历史、结果CSV、全成本/资源、repair log、验收重算 |
| outcomes/scalability.md | cold/warm及单次/多次成本、目标尺寸/内存/通信预测、不可外推项 |
| outcomes/tests.md、outcomes/changed_files.md | 最小/最终测试、compileall/lint范围、未运行项、依赖和selective merge分类 |
| 仓库级文档 | 本分支追加development_progress.md、development_model_registry.md，不覆盖旧事实 |

Markdown使用fenced math和列数一致表格；原始检查与GitHub rendered view视觉核验分开，无视觉证据写NOT_VERIFIED，不伪造截图。未运行不预填PASS。完成有条件且有预算的首轮后推送本分支，报告完整HEAD/base/upstream、工作树、实际命令/环境、最佳且合格或不合格状态、真残差、全成本、证据入口，然后停止等待review。不要只交“环境装好”，也不要把未求解成功等同于无可交付内容。
