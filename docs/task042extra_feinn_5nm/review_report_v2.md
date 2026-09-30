# Review V2：停止对角缩放续扫，转入固定网络的参考场表示诊断

## 0. 决定、身份与本批 blocker

**接受 Response V2 为一次有效实施但结果为负的尺度诊断；不授予 solver、生产或合并资格。关闭“继续给同一 FREE＋Adam/L-BFGS 换对角尺度”的增量扫描。下一批只授权：复用准确参考的有限误差/残差诊断，以及一个固定网络、固定 M5 的监督表示试验，随后用独立 FE 代码审核。**

这项工作要区分：当前网络能否表示这个已知正确的有限元场，与从 Maxwell 残差训练该网络是否有效。不能再把“FREE 必须先成为强求解器”设为研究网络的无限前置任务。监督试验有参考标签，**不是无标签 Maxwell 求解，不产生 5 nm solver PASS，更不是 0.7 nm/48h 成功**；它只消除表示能力与残差优化混在一起的不确定性。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42extra_feinn_5nm
worktree                  = /home/fenics/Projects/NN-Lab-V2
review_date               = 2026-09-30
reviewed_HEAD             = 01a092ffc0cea8a62c26e4dd6f872ba2c2efc6ea
original_base_SHA         = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review           = review_report_v1.md @ 0b61816c0189a2c05812044ab8e1d1513ef0407d
latest_response_reviewed  = response_v2.md
V2_diagnostic_solve_src   = 19c725efd27ae5daedba8e77d2ad98375711bb71
V2_compare_only_src       = bfff1458a389b2c4a4d57112cc771bb33847c20a
V1_accurate_reference_src = 7a79b3007d92a9b699e0451d0c8b6dfdacee7ad9
review_decision           = ACCEPTED_WITH_LIMITATIONS_NOT_SOLVER_QUALIFIED
next_batch                = V3_REFERENCE_EXPOSED_REPRESENTATION_DIAGNOSTIC
new_route                 = FEINN-REFERENCE-FIT-G
response_required         = response_v3.md
target_5nm_and_0p7nm      = NOT_RUN_NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

最终目标仍为约 2 TB 整机物理内存内、0.7 nm、任意非可分三维周期单胞的合格 Maxwell 解；48h 是未来目标模型的端到端预算。当前属于**神经表示/优化诊断**，不修改物理目标、不启动更大模型。

本次审阅实际读取远程最新目录、task/review/response、summary、原始对照与资源记录、网络和复验代码；核对前一 review 后的5个提交。没有 SSH 重跑，也未重新下载工作站 ignored 数组。因此下文 measured 指仓库记录，公式是代数推导；新试验均 not_run。本报告是本批唯一新执行合同，不改旧 task、Review V1 和 V1/V2 证据。

## 1. V2 结果及审阅结论

依据：[Response V2](response_v2.md)、[详细诊断](outcomes/scaling_diagnostic_v2.md)、[原始对照](outcomes/records/scaled_route_comparison_v2.csv)、[run index](outcomes/records/run_index_v2.json)、[资源账](outcomes/records/resource_costs_v2.json)。误差无量纲，时间为监督秒数，RSS 为同时进程树采样。

| 同一 M5 / measured | V1 FREE | V2 Gram-diag FREE | 解释 |
|---|---:|---:|---|
| 完整 closure / A / Aᴴ / Gsolve | 4000/4002/4000/4003 | 4000/4002/4000/4003 | 工作计数相同，均预算停止 |
| 对偶 loss | 0.1038990913 | 0.0990052598 | 只改善约4.7%，不是场资格 |
| native 与 augmented 相对残差 | 0.5969144472 | 0.6077719288 | 略变差，远超1e-6 |
| scattered E L2 相对差 | 0.9919248991 | 0.9542085842 | 仍约95.4%，远超1e-4及研究0.5 |
| scattered scaled-curl 相对差 | 0.9917554916 | 0.9541184551 | 没有准确场 |
| 独立体吸收能量闭合绝对差 | 0.4200670879 | 0.3951074149 | 远超1e-5 |
| 候选监督 wall / s | 2901.9062 | 2539.8103 | shared-workstation，不能归因提速 |
| 候选同时树 RSS / B | 1366249472 | 1365712896 | 自身swap0；不是容量耗尽 |

缩放、复数导数和原端口恢复检查支持本次对照有效；它没有达到预登记的残差十倍改善加散射误差≤0.5。接受 `SCALING_DIAGNOSTIC_NEGATIVE`。该结论只排除了这个固定 D/优化器组合，不证明所有预条件、网络或更一般的坐标处理无效。两个 FEINN 方案在 V2 没有重新训练，无新神经增量。

| 其他证据 | 审阅处理 |
|---|---|
| D0 四状态；Adam500参数/optimizer未保存 | 接受 NOT_RETAINED，不为补历史重放 |
| G 对角归一误差约4.44e-16，dot test约3.15e-15，Gsolve约1.66e-13 | 接受所测接口范围；不提升为全面无bug保证 |
| 已有同p3参考重复使用，compare-only无新MUMPS求解 | 接受其复验范围；不是新几何/盲测试 |
| 第一次FE进程误导入Torch，第二次本机MPI socket被执行沙箱拒绝 | 保留两次失败及一次最小接线修复；不是物理失败，不改安全策略掩盖 |
| 原total port/真出射/scattered port分母区分 | 认为V1模糊表头已由V2解释；新表继续精确区分，不改V1数字 |
| task唯一公式宏修复，Review V1/task渲染记录 | 数学不变；接受已记录的浏览器检查。本次新review另作渲染检查 |
| p4 | 实际not_run，不是已测p4精度失败；本批仍不运行 |

## 2. 为什么现在改做表示诊断

原损失在自由系数 c 中的二次型含 A 的作用；已知场拟合则可直接衡量场误差。设 c_ref 为已保存同p3的**散射**系数，二者为：

```math
r=Ac-f,\quad d_G=f^*G^{-1}f,\quad L_D=\frac{r^*G^{-1}r}{2d_G},
\qquad H_c=\frac{A^*G^{-1}A}{d_G}.
```

```math
e=c(\theta)-c_{\rm ref},\quad d_{\rm ref}=c_{\rm ref}^*G c_{\rm ref},
\qquad J_{\rm fit}(\theta)=\frac{e^*G e}{2d_{\rm ref}}.
```

后者去掉了物理残差中的 A，但保留原网络、完整 FE 插值与正定场范数，仍是非凸参数优化。拟合成功提供“存在可用参数表示该场”的实证；拟合失败仍可能是表示或优化受限，**不能宣称数学上不可表达**。也不能按8966网络参数小于63936自由实系数，就推断某一个特定解必然无法表示。

论文依据：[Compatible FEINNs v2](https://arxiv.org/html/2411.04591v2)，尤其§2.5、§2.7、§3.2.2。论文正质量项 H(curl) 模型不同于本不定开放散射；部分实验使用FE数据预训练。本批借用监督拟合作为独立诊断，**不复刻其后续预训练权重接PDE训练链**，不引用论文给本模型作收敛保证。

本 review 明确、仅对下述 P0/P1/P2 放开原 task 和 Review V1 的“不得读目标准确解/不得监督拟合”限制。原来 V1/V2 的无标签声明保持真实；以后数据污染必须按这次明确接触记录，不能把新结果重新包装为盲解或fresh泛化。其余禁止扩大网络、物理、全局Maxwell逆和自动合并的规则继续有效。

## 3. 冻结对象与数据隔离

| 对象 | 本批固定值 |
|---|---|
| 方程/几何 | 原M5，5 nm Si/air，384 hex，h1.25nm，p3/q15，1°/phi0/s；原双Floquet与layered Fourier-DtN |
| 未知量 | 31968复FE：边3744、面14400、内部13824；2082slave；完整40端口准确恢复 |
| 网络 | 原3→64→64→64→6、tanh、8966实参数、FP64、seed421001；坐标归一化及完整矩映射不变 |
| 场约定 | c是散射场独立master顺序系数；背景不训练，禁止把total/含slave存储直接当标签 |
| G | 原MPC后同p3 Gram、ell5nm；不改范数权重，不使用V2的D作为新训练变量 |
| 标签 | 原V1准确reference_state.npz中的c；其alpha仅供完整性核验，不训练额外端口网络 |
| 数据角色 | REFERENCE_EXPOSED_DIAGNOSTIC_ONLY；非目标解生成器、非数据集campaign |

文件字节身份应与原run index核对；下列是已读取记录中的hash，不是本次工作站复测：

```text
native / physical packet = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
Gram file               = 2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9
moments q15             = 0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e
reference_state         = 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7
material table          = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
```

从本任务V1/V2 index取得实际路径，不复制邻任务、不猜路径。核对c_ref shape/dtype/master顺序、native/G/模式/背景身份、保存alpha与原恢复关系。只做必要参考残差重验，不调用exact_solve或任何MUMPS symbolic/numeric/solve。必需标签损坏/缺失时标 ARTIFACT_BLOCKED，不重新求参考来填补。已验证环境与FE接口按source/hash复用，不重复整套E0/E1或安装环境。

P1必须使用独立、名称含reference_fit的artifact目录与stage；checkpoint、manifest、summary写入 `reference_used_for_training=true`、`pde_only_solve=false`、`production_initialization_allowed=false`。不将该checkpoint接回原三路线，不复制到其latest/default模型路径，不把它用于随后0.7nm求解或当前Task042的初始化。以后真要研究预训练必须有新授权及从零成本账。

## 4. P0：有限的已知误差与残差关系检查

这一段不更新参数、不生成新的求解路线。固定池为零态、V1 FREE最终committed、V2 scaled FREE最终实际c、V1 FEINN-DUAL最终committed，最多4态。只读取已有状态；缺旧状态则该项not_run，不重放训练。P0不通过某一诊断假设不阻止独立P1，只要共同算子/数据身份仍合格。

对每态计算 e_s=c_s-c_ref、r_s=Ac_s-f、r_ref=Ac_ref-f，检查 `A e_s = r_s-r_ref`，operation-scaled差≤1e-10；**不能把参考残差直接设零**。报告相对G场误差、相对G对偶误差残差：

```math
E_s=\sqrt{\frac{e_s^*G e_s}{d_{\rm ref}}},\qquad
R_s=\sqrt{\frac{(A e_s)^*G^{-1}(A e_s)}{d_G}}.
```

另报告原native残差、系数梯度g_s=A*G^-1 r_s/d_G的范数，以及负梯度与参考误差修正方向(c_ref-c_s)的欧氏实内积夹角。非零分母才计算cos；近零明确absolute/undefined。E_s和R_s的比值只是固定状态的归一化方向性诊断，不是全局条件数、最小奇异值或inf-sup常数。

仅对两个FREE终态，可各做一次沿**原负系数梯度**的解析最优实步长见证。设v=-g_s、w=Av、q=G^-1r_s、p=G^-1w：

```math
t_*=-\frac{\mathrm{Re}(w^*q)}{\mathrm{Re}(w^*p)}.
```

分母须finite且正，接近舍入不确定区则标inconclusive。离线评价c_s+t_*v的原loss、native与G场误差，不递推、不加入优化器、不用参考误差方向当更新，不把该见证作为训练初值。这检查原梯度方向尚能带来多少下降，**不代表所有方向的最优改进**。

P0整段A/Aᴴ各≤24次、Gsolve≤24次、wall≤1200s；一个诊断进程最多建立一次原稀疏G因子，记录 `RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR` 及完整setup/solve/RSS，结束销毁。禁止新谱扫描、global Hessian/Jacobian、SVD、CG/LSQR/PC研发。保留原Gsolve真实相对残差≤1e-11。使用原对偶loss只用于这些有限观察，不重新训练FREE。

## 5. P1：一次 FEINN-REFERENCE-FIT-G

### 5.1 新目标与梯度

用§2的J_fit拟合**完整 FE 插值场**，不是节点值、点云或只拟合边界。令J_c为实参数到复系数的Jacobian，梯度为：

```math
g_c^{\rm fit}=\frac{G(c(\theta)-c_{\rm ref})}{d_{\rm ref}},\qquad
\nabla_\theta J_{\rm fit}=\mathrm{Re}\{J_c^*g_c^{\rm fit}\}.
```

这部分只有稀疏G乘法，不需要G^-1，不新建Gram因子，也不在每次训练closure里应用A/Aᴴ。G已存在的装配费用可作历史归属单列，不能再次计算或混入本批新增实耗。d_ref>0且finite，不能用total背景范数弱化scatter误差；零参考场按数据错误处理。

复用CoordinateField、CompleteMomentMap和其8-cell重算VJP，保留全部边/面/内部矩、Piola、方向和MPC。初值仍seed421001、隐藏层原初始化、仅末层零，不能从V1/V2权重warm start，不能把c_ref直接覆盖网络输出。只允许一种架构/一个seed/一个目标；不加carrier、Fourier特征、per-DoF embedding、分片网络或调范数权重。

### 5.2 开始训练前的最小检查

先在小型复数数组例子验证J_fit、解析梯度和e=0时的目标/梯度；随后在真实网络的一个固定非零测试副本上做3个非零实方向，h=1e-4/1e-5/1e-6中心差分，连续稳定步长相对≤1e-5。测试副本不用作训练初值。保留batch1/8的c/loss/梯度配对1e-10；首次真实DOLFINx G变分配对可复用V1证据，不重装配G。

确认fit闭包没有读取native参考求逆或调用Gsolve；reference只读，source/初始化/hash入档。拟合与FE后处理依赖保持分环境：禁止为复用一个函数让FE进程顶层import Torch，再重复V2已发现的接线错误。预算/非有限/异常恢复与committed/trial分离复用现有事务方案，新增目标不能绕过。

### 5.3 固定执行与记录

唯一训练从零散射初始化开始：Adam500、lr1e-3、无weight decay；随后L-BFGS lr1/history20/strong-Wolfe/max_iter20/max_eval25/tolerance_grad1e-7/tolerance_change1e-9。最多4000完整fit loss＋gradient closure，训练进程wall最多10800s，含加载、检查点和至少120s最终保存余量，先触者停止。小梯度/tiny step按原停止语义记录，不在外面不断重启同一优化器。

每25closure记录fit loss、E_G=sqrt(2J_fit)、实参数梯度/更新范数和真实计数；每100closure只在最近完整committed参数上做一次native审核并写明对应closure，不把线搜索试探点提升为已提交态。完整native审核次数≤45含起末；检查不参与优化目标或挑选不同架构。所有Gmatvec/NN前后向和审核时间计入，从label加载到最终冻结的时间也是训练成本。

保存zero、Adam500结束（若完成）、final committed三个参数checkpoint，另存last_trial。声明parameter-only不可续训，除非同时保存且核验了一致optimizer state。本批不授权续训，即使保存可恢复状态也不自动使用。训练停止可以是达到预登记fit阈值、原优化器停滞、预算/非有限/安全停止；不得为了凑4000次反复重启。

当一次完整committed检查点E_G≤1e-3，可提前冻结并进入P2；这只是表示诊断的早停，不是solver pass。正式无标签PDE精度不因它放宽。若该阈值未到也照样冻结并做P2，得到失败或部分进展的真实证据。

## 6. P2：独立复验，禁止把标签拟合升级为求解成功

冻结训练结果、参数/c/hash和计数之后，使用已有compare-only后处理能力对照原c_ref。只重建必要的网格、局部FE与后处理对象；不重算准确解、不建立global Maxwell CSR/factor、不执行p4。验证参数经完整矩映射确实得到所保存c，独立重新计算G误差与原native/增广/port。

至少报告：scattered与total E的L2、scaled-curl、selected复E/H、各类完整复通道、R/T/A_balance/A_volume、独立能量闭合，全部沿用原分母与近零规则，不能拟合相位。另按原材料cell/几何标签报告air/substrate/grating和靠近材料界面的局部场误差诊断，复用同一FE场积分，不引入新的训练权重；界面邻接单元固定为至少一个内部面两侧介电常数不同的单元；区域定义与集合hash入档，不用漂亮切片代替误差。

这是**参考已暴露的同离散重构审核**，不是held-out/fresh/blind验证。独立代码不等于独立数据。q30对完整网络矩的最终一次复核可作为求积检查，不能称跨网格泛化；相对差≤1e-8才接受已冻结q15表示身份，失败记录QUADRATURE_DRIFT而不重训或改q15来隐藏结果。

现有field_physics会按数值门限生成official_candidate_results/qualified；新路线必须通过显式diagnostic策略分离：保留真实 `numerical_equation_pass`、`field_reconstruction_pass`、`power_check_pass`，同时固定 `pde_only_solver_qualified=false`、`official_candidate_results=false` 和reference标签。即使所有数值量达标，只能说监督重构与该FE参考一致，不能回写旧无标签路线为通过。

| 本批研究分流（预登记，非物理Gate） | 允许结论 |
|---|---|
| E_G≤1e-3且独立scattered E L2、scaled-curl均≤1e-3 | REPRESENTATION_WITNESS_POSITIVE：找到该固定网络表示本参考的实证；不是无标签求解 |
| 三项均≤1e-2但未满足上行 | PARTIAL_REPRESENTATION_WITNESS：有显著拟合信号，仍未证明原精度可达 |
| 未满足前两行（含停滞或预算终止） | REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED；不能断言容量不足或普遍不可行 |
| 拟合场好而原native仍不合格 | 说明该近似误差经A作用仍不可接受；结合P0，不能把一个方向比值称条件数 |
| 原native及场/功率全部达到旧严格门限 | SUPERVISED_DISCRETE_RECONSTRUCTION_PASS；pde-only solver仍false，旧路线仍负结果 |
| 数据/求积/实现/资源不合格 | 对应blocked/failed/controlled_stop，不得按网络数学失败汇总 |

正式原方程1e-6、同离散场/通道1e-4、功率/能量1e-5、逐通道功率1e-6、MPC/恢复1e-10继续作为独立诊断表列出，并不由上述1e-3研究阈值取代。下一建议基于这些分开的结果，不自动进入PDE残差微调、更大网络、Riesz多层或新Krylov路线。

## 7. 资源、Git 与最小实现边界

工作站原生Linux、同一canonical worktree、独立FE/ML环境/cache/锁，内部阶段串行。CPU-only/MPI1/全部数学与Torch线程1/DataLoader0，现场空闲物理核并避开忙碌SMT；只降低自身优先级。数值树warn12GiB/hard16GiB、自身swap0、无OOC；轻测试/浏览器树≤2GiB。系统余量max(128GiB,effective_total的10%)＋邻增长至少384GiB（必要时更多）＋本任务16GiB；磁盘自由≥50GiB，artifacts累计≤20GiB。未知/不足时完成仍可做的独立部分并交付，不抢占邻任务。

本批全部新增有载及有界辅助最多4h，同时受原16h剩余额度约束。V2资源账保守V1＋V2基数为29225.912270474248s，距57600s尚余28374.087729525752s；启动时加上其后未入账真实费用，不能反复重置。P0≤20min、P1训练≤3h，其余真实检查/后处理/发布使用剩余额度；所有阶段总额仍≤4h。都是停止上限，不是ETA或成功承诺。

P0准确G因子属研究成本；P1不需要因子，禁止把前阶段因子隐藏常驻并声称低内存。监督峰、数值峰、浏览器峰分别保留，同一时刻树RSS不是阶段峰之和；实耗与历史from-zero归属分开。无cgroup委派继续约0.5s采样监督，不冒称连续内核限额。紧急资源停止仅终止自身后代，不为final audit越线。

更新前确认无活跃本任务run、工作树clean；仅安全fetch/fast-forward本分支，不clone、不新建分支、不rebase/merge其他活动分支、不amend/强推。V2已经说明共享origin.fetch未映射本分支：使用精确命令级refspec和显式 `refs/remotes/origin/task42extra_feinn_5nm` 核对，不将未解析的 `@{upstream}` 误报通过，也不为此改共享remote配置。不要让此可处理的元数据差异成为重建repo/运行环境的理由。

改动限新增reference-exposed诊断目标、必要stage/input/记录与compare-only策略；复用矩映射、原算子、G与事务管理。数值核进src，runner只编排；旧route默认目标和结果字段含义不变。只做targeted tests，不全仓清理/full pytest，不重装环境/改BLAS/CUDA/安全策略。执行器拒绝本地MPI socket时按已有合法执行权限机制处理或报告，不修改系统/沙箱策略绕过。

## 8. 交付、检查及 Response V3

建议commit顺序：C1预登记/标签边界/P0诊断；C2fit目标/梯度/事务与隔离测试；C3唯一拟合与独立复验；C4compact证据/response/总账。每个真实运行前clean实现commit，记录实际source；文档HEAD不是运行source，活跃run内不切HEAD。

所有固定算子、fit和FE审核仍走one-run dat主入口；新增stage/index不得覆盖V1/V2：

```bash
python scripts/run_case.py input/task042extra_feinn_5nm/<one-run>.dat
```

建议新文件名为 `v3_error_geometry.dat`、`v3_fit_checks.dat`、`v3_reference_fit.dat`、`v3_fit_compare_only.dat`，实际实现后才可运行；这些不是本review已经提供的可执行文件。每个dat只对应一个明确定义阶段。

至少新增 `response_v3.md`、`outcomes/representation_diagnostic_v3.md` 及 compact 的 `representation_design_v3.json`、`error_residual_geometry_v3.json`、`reference_fit_checks_v3.json`、`representation_comparison_v3.csv`、`reference_exposure_v3.json`、`gate_decisions_v3.json`、`run_index_v3.json`、`resource_costs_v3.json`。manifest保存input/resolved config/source/物理/材料/网格/模式/Gram/标签/初始化/模型/资源hash。结果量全部区分measured/derived/predicted/diagnostic/not_run/failed/controlled_stop/blocked。

summary追加V3并原样保留V1/V2；更新本分支development_progress、development_model_registry、tests/changed_files。测试需证明诊断checkpoint不会被旧production入口自动加载、诊断参考曝光不会被checker升级为pde-only pass。不删除负结果，也不要求用完预算才交付。

只检查新review与新增文档的Markdown和GitHub渲染，已通过的旧task/Review V1不再全套渲染。本review使用math fence和 `\mathrm{Re}`；发布端若不能取得实际浏览器视图，记录未核验，Codex用已有低扰动工具补查，失败计费且不伪造PASS。不要改写本review，澄清写response。

Response V3首先给准确branch/HEAD/base、run sources、worktree/显式remote ref身份和实际阶段。随后直接回答：P0中误差与残差/梯度是否表现不一致；网络拟合是否找到可用表示；独立L2/curl/native各如何；哪些结果因用了参考不能算求解；是否出现求积漂移；完整资源与失败费用；目标尺寸5nm和0.7nm还缺哪些证据。只给一个由本批证据支持的下一最小建议。

仅推送 `git push origin HEAD:refs/heads/task42extra_feinn_5nm`，然后停止等review。不续训旧网络、不再扫描D、不新建Maxwell因子/CG/LSQR/PC、不做p4/大5nm/0.7nm，不merge master。
