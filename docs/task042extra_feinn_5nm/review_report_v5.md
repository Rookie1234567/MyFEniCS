# Review V5：固定特征的场投影已完成，核清原方程残差下限后停止末层续扫

## 0. 审阅决定、身份与要消除的 blocker

**接受 Response V5 的稳定线性投影、真实网络回写及独立复验。固定隐藏层的 G 拟合子问题已经求好，不应再把它描述为线性优化未完成；整个网络与原 Maxwell 求解仍未合格。下一批只授权一次同特征空间的原 native 方程最小残差读出，并与 V5 最佳场拟合对照。完成后关闭本轮固定隐藏层的末层诊断，不继续扫描范数、截断或末层优化器。**

本批消除的具体不确定性是：V5 按场范数取得最优末层而原方程变差，那么**同一组隐藏特征在最有利的末层组合下，究竟能把原方程残差压低到什么程度**？这是表示空间与方程兼容性的有界诊断，不是一次押注求解成功的长训练。已有场误差限制意味着，当前冻结特征并不具备完整验收资格；本批不把这一已知限制忽略掉再追求伪 PASS。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42extra_feinn_5nm
worktree                  = /home/fenics/Projects/NN-Lab-V2
review_date               = 2026-09-30
reviewed_HEAD             = b5be93b130a6102d89511a345cbaf54341cd345d
latest_commit             = docs(task42extra): bind V5 GitHub view and completed resource ledger
original_base_SHA         = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review           = review_report_v4.md @ 28fabffd41f042c8a4bdda6339810bb1f98a887d
latest_response_reviewed  = response_v5.md
V5_numerical_source       = a6ac769027384525e406537f3069607043bc4a67
next_batch                = V6_FROZEN_FEATURE_NATIVE_RESIDUAL_DIAGNOSTIC
new_route                 = FEINN-FROZEN-FEATURE-RESIDUAL-READOUT
response_required         = response_v6.md
solver_qualification      = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

最终目标仍是约 2 TB 整机物理内存内、0.7 nm、周期单胞内任意非可分三维 Maxwell 的准确计算。本批只涉及原 5 nm M5 的冻结特征，不是目标尺寸资格，不替代通用 Full3D 的分布式、matrix-free、可扩展 iterative 主线。

本次审阅读取远程最新目录、review/response/summary、对照 CSV、run/resource 索引、readout 与 G-QR 源码，并核对前次 review 后的4个提交。任务及规则的未改动身份与既有全文对应；目录未见新补充任务书。没有 SSH 重跑、没有访问现场全部 ignored 数组。下文 measured 指仓库记录，公式及推论为 derived；新试验 not_run。先读根/目录 AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、Review V1–V4、[Response V5](response_v5.md)、[summary](outcomes/summary.md)及本报告。本报告仅覆盖本次有限原方程读出与标签角色的例外，其余约束保留。

## 1. V5 事实与更明确的解释

依据：[对照 CSV](outcomes/records/readout_comparison_v5.csv)、[详细报告](outcomes/frozen_hidden_readout_v5.md)、[投影记录](outcomes/records/readout_projection_v5.json)、[run index](outcomes/records/run_index_v5.json)。误差均无量纲，功率为入射功率归一。

| measured 指标 | V4 final | V5 实际网络 | 审阅解释 |
|---|---:|---:|---|
| G 场相对误差 | 0.0138716912975 | 0.0115909576376 | 范数下降约16.44%，不是下降30.18% |
| 散射 E L2 相对误差 | 0.0132512476647 | 0.0139354062682 | 变差，严格要求1e-4 |
| 散射 scaled-curl 相对误差 | 0.0138870027008 | 0.0115255720568 | 改善但未合格 |
| native / augmented 相对残差 | 1.60884472011 | 1.97790914967 | 变差，严格要求1e-6 |
| 独立体吸收能量闭合绝对差 | 0.00118398995593 | 0.00131611018570 | 变差，严格要求1e-5 |
| 最大逐通道功率绝对差 | 0.000351344847336 | 0.000626436218627 | 变差，严格要求1e-6 |

V5 消除的是 V4 剩余 **G 误差平方/能量的30.180006%**。接受195/195数值秩、无截断、G 正交缺陷约2.32e-13、实际网络最优性约1.39e-13、回写与理想投影配对约1.60e-13的已测证据。小 R 奇异值不是全局 Maxwell 的奇异值；这些测试也不是整个网络类不可表示的证明。

在本次已分辨、完整195维固定特征空间内，V5 数值上实现了 G 最佳逼近，剩余误差约1.1591%。同一离散的 G 范数满足以下正权重恒等式。令 N_E 为参考散射场的 L2 范数平方，N_C 为其 scaled-curl 范数平方；ell=5nm，k0=2pi/5nm：

```math
 E_G^2=\frac{N_E E_{L^2}^2+(\ell k_0)^2N_C E_{\mathrm{curl}}^2}
 {N_E+(\ell k_0)^2N_C},\qquad \ell k_0=2\pi.
```

这是原 G 定义的推导，不是新 loss。只要范数身份和积分一致，若 L2 与 curl 两项都不超过1%，则 E_G 也必不超过1%。因此，**在 V5 的数值最优性及范数一致性证据范围内，仅修改这份隐藏层的末层已不足以同时达到原1%部分表示门限，更不能达到严格物理门限。** 不得把该结论扩大到改变隐藏参数后的网络。它也不是带区间误差界的严格数学下界证书；数值误差/范数身份出现矛盾时先复核。

V5 主阶段完整 launcher 单调 wall 364.272690s、采样整树峰1,673,396,224B、自身swap0；新增 Gsolve/Gram factor/Maxwell factor 均为0。V5 的短计时测试与实际准入/保存余量支持新协议，V4 原120s偏差仍保留，不追认旧运行通过。无必要再做一轮长训练或全面运行保全重构。

## 2. 本批方法：同一个空间，直接最小化原方程残差

### 2.1 改变什么，不改变什么

V5 已得到固定特征矩阵 Phi，大小31968×195，完整 FE 系数为 c=Phi a。使用已保存的 G 正交基 Q_g=Q_eff；其195列完全由相同隐藏特征、G 和固定分解规则产生，不含参考误差补充方向。复用它只是改善坐标表示，不增加可表达的场。

本批用原未凝聚全 FE native 算子 A 和原非零散射载荷 f：

```math
 B=AQ_g,\qquad \widehat B=B/\|f\|_2,\qquad \widehat f=f/\|f\|_2,
 \qquad y_R=\arg\min_y\|\widehat B y-\widehat f\|_2,
 \qquad c_R=Q_g y_R.
```

A 必须继续是原体项、MPC 和完整 DtN 准确消元后的 **native 全 FE** 作用；不是凝聚 trace 算子，不改材料、符号、人工吸收或端口库存。不形成全局 A、A* A 或195维正规方程逆。只建立31968×195的受限作用 B，不是对全部 FE 自由度建立逆。

固定特征下，最小残差求解是一个线性最小二乘问题，不需要 Adam、L-BFGS 或新的预条件器。这不同于原无标签神经优化，也不同于 V5 的标签场拟合。经济型带主元 QR 和小矩阵 SVD 的接口依据见 [SciPy QR](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.qr.html)及 [SciPy least squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.lstsq.html)。只使用当前已安装合格版本，不为文档版本差异升级环境。

### 2.2 为什么仍然是参考已暴露诊断

读出右端项仅为原 f，不读取 c_ref 来构造 y_R；但是隐藏特征源自监督训练，不能把整个方法重新标成盲解。所有新 manifest/checkpoint/result 保留五项旧标签，并增加角色字段：

```text
reference_used_for_training = true              # 整条特征学习血缘
features_reference_exposed = true
readout_rhs_uses_reference = false              # 仅当前195维线性步骤
pde_only_solve = false
production_initialization_allowed = false
pde_only_solver_qualified = false
official_candidate_results = false
```

准确参考只在独立 T2 评价阶段加载。禁止用旧 `load_anchor/load_problem` 的通用入口意外在主阶段加载标签；只拆分最小的无标签数据加载 helper，不重构其他路线。旧无标签 V1/V2 的负结果、V3 中断和 V4/V5 监督身份全部保留。

## 3. 冻结数据、空间和复用范围

物理冻结为原 M5：5nm Si/air、1° grazing/phi0/s、384hex、h1.25nm、p3/q15、双 Floquet、原 layered background/Fourier-DtN；全部31968独立复 FE，边3744/面14400/内部13824，2082slave，40端口。FE 为 complex128，网络实参数 FP64；隐藏8576实参数、390实末层参数的布局不改。

以下是已经读取记录中的文件字节 SHA256，现场按 V1/V5 run index 复核，不把这里写的 hash 当作新测量：

```text
qualified columns = 03bb974a41d8043bc5f0c9add72d615bbff9467c4ec0d51b01975fab6943a0ed
V5 projection     = 80e28887f2d77e6900514d4f09d57ac22baf8e1beb700b1b4461687ab0f6705d
V5 network NPZ    = 2d166478509bbf14638c7beb0afcff321a5330b37f34f72c2e8737477d9cd58c
V5 model-only PT  = 9d81e01df9aab13bd4e03dfb2ceebbd0e9ba7b459365356ec5ca4abcaf6909eb
native packet     = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
Gram              = 2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9
moments q15       = 0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e
reference T2 only = 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7
material table    = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
```

从 projection 文件只按白名单读取 `Q_eff/Q/R/left/vh/singular_values/permutation/scales`；不加载或使用 `delta_ideal/delta_columns/delta_a` 作为方向、标签或右端项。数值秩必须与 V5 的195/195吻合。复用 Phi/Q，不重新计算隐藏列或 G-QR，不增补参考场、误差、POD、A逆或新carrier列。数据缺失/损坏标 ARTIFACT_BLOCKED，不重新求参考或重训填补。

## 4. T0：最小资格检查，最多10分钟

核对 source、branch、hash、master/模式顺序、hidden/buffer 及末层布局，确认本任务没有其他活跃 run。复用 V5 的 Piola/MPC/完整矩、计时和保全证据，只测试本次新增的受限 A 作用和坐标还原。

小型复数非 Hermitian A 的例子覆盖满列秩、重复列、近秩亏和不同列尺度；用独立小矩阵 SVD 与新经济 QR/小R路径比较残差与生成的场。合成例子允许小型显式矩阵，不以全零例子代替检查。

真实 M5 用固定 seed421601 的3个非零复向量，验证已保存 Q_g 与 Phi/SVD反变换代表同一完整场；其中含纯虚/三分量混合。最多额外12次 A 作用（不含主阶段195列构造），A*最多6次，用于 dot/action 检查，不做谱扫描或旧算例重跑。真实 B 构造后的随机组合配对在 T1 完成；T0 不重复构造 B。

原 G 正交性和 QR 证书按相同 source/artifact 复用，必要随机向量 G 范数交叉核对即可。FE 进程不得顶层 import Torch；PT 仅从本任务已核 hash 的文件加载，禁止任意外部 pickle。

## 5. T1：唯一原方程线性读出，最多30分钟

按列应用原 A 得到 B，每次一个195列中的向量；允许等价有界小批，但不得一次展开195份全cell张量。每个 B 列都计一次 A，包含临时张量、复制和hash成本。B 数值 payload 为99,740,160B（derived），不是 RSS；Q/Phi/经济QR及小SVD的工作区也必须计账。

用 `qr(Bhat, mode='economic', pivoting=True)` 的复数 Householder 路径，再对最多195×195的 R_B 作 SVD；rcond固定1e-12，不扫描、不加ridge、不对正规方程求逆。保留的左奇异向量定义残差投影空间 Z_eff。报告全部奇异值、秩、截断及实际QR重构误差；这些是受限算子的量，不是全局 Maxwell 谱。

把 y_R 变回原输出层系数。V5 已保存的分解记为 U_G Pi_G=Q R_G、R_G=L_G Sigma_G V_G*、Q_g=Q L_G；本轮195方向均保留时：

```math
 a_R[\pi_G]=\frac{V_G\Sigma_G^{-1}y_R}{s[\pi_G]}.
```

除法逐元素执行，使用保存的置换和列尺度；也可用同一已验证小R分解实现完全等价反变换。不能混用新 B 的主元置换和旧 G-QR 置换。将 a_R 按原三分量实虚两两配对写入末层权重和bias，重新运行原网络及完整矩映射取得实际 c_net；只有这个场进入最终评价。

| 新实现 Gate | 要求 |
|---|---|
| B作用/坐标配对 | 3个非零复组合的 B y 与 A(Q_g y) operation-relative≤1e-10；Q_g与原Phi回写配对沿V5门限 |
| 经济QR | 相对重构差≤1e-10，Z*Z−I的F范数≤1e-10；不创建31968平方的full Q |
| 最小残差最优性 | norm(Z_eff* rhat_R)≤1e-9；另报所有原列的归一化残差相关性 |
| 不增性 | 完整rank195时 rho_R≤min(1,rho_V4,rho_V5)+1e-9；仅保留子空间时不冒称覆盖所有旧场 |
| 残差投影配对 | abs(1−rho_R²−norm(Bhat y_R)²)≤1e-8；残差由直接减法计算，不靠1减投影能量推算小残差 |
| 真实网络回写 | 欧氏系数差≤1e-10，G归一化场差≤1e-9；原A作用下与线性投影残差之差除norm(f)≤1e-9 |
| 冻结身份 | hidden/buffer逐位hash不变，只改390实末层参数；未调用optimizer/逆算子 |

若 B 的数值秩不足195，只能报告所保留可分辨子空间的最小残差，不能断言整个195维空间的下限。若回写/抵消放大让实际网络偏离投影，标 READOUT_RECONSTRUCTION_UNSTABLE；不得交付一个不能由网络再现的理想场。残差接近门限且与数值误差同量级时标 NUMERICAL_SPAN_UNRESOLVED，不报严格下限。不得改变截断来追求通过。

本批只允许一次真实 B 构造/投影启动。完成的 B、分解和参数原子保存并绑定hash；不混装V4优化器历史。主阶段不加载参考解、G逆或任何 Maxwell factor。

## 6. T2：独立物理复验，并结束当前固定特征诊断

冻结新末层/model/c/hash后，独立 ML 做 q15/q30 重建，FE compare-only 才加载 V1 准确参考。旧 V4/V5结果按身份复用；不新建 MUMPS symbolic/numeric/solve，不做p4。

先核对第1节的 G 与 L2/curl 范数恒等式：使用已有参考范数和原 ell/k0，不能用四舍五入的误差反推权重代替原量。若已有标量不足，允许在本次后处理复用同一参考积分，不新建Gram。报告 L2 与curl的参考能量权重，解释G下降而L2可上升；不据此改变G。

比较三种场：V4联合训练终态、V5 G最佳读出、新的native残差最佳读出。至少包括 E_G、total/scattered E/H/curl、原/出射/scattered四类完整40通道及实际分母、R/T/A_balance/A_volume、独立能量闭合、逐级功率和原材料/界面区域误差。新增检查：

```math
 \frac{\|c_R-c_{\rm ref}\|_G^2}{d_{\rm ref}}
 \simeq \frac{\|c_G-c_{\rm ref}\|_G^2}{d_{\rm ref}}
       +\frac{\|c_R-c_G\|_G^2}{d_{\rm ref}}.
```

其中 c_G 是 V5 实际网络场。以1e-8归一化绝对缺陷审核；该投影恒等式通过，才能用 V5 场误差限制解释新场代价。新场显著低于V5 G最优值时，先查身份/映射/范数，不宣布突破。

| 结果 | 分类及解释 |
|---|---|
| rank195且全部线性/回写检查通过 | FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED：取得此离散、此冻结特征的数值最小残差；不是整个网络下界 |
| rho_R>1e-6且分辨误差远小于超出量 | 固定特征不能达到本次原残差门限；停止只调末层，下一次要改变隐藏特征或表示 |
| rho_R≤1e-6而场仍不合格 | RESIDUAL_ONLY_NOT_FIELD_PASS；检查场与残差关系，不自动改变验收或称稳定求解 |
| rank截断/回写/原方程配对不合格 | RESOLVED_SUBSPACE_ONLY 或 NUMERICAL_SPAN_UNRESOLVED；不作完整特征空间不可能结论 |
| 任何物理量达到严格门限 | 单列该项事实；标签血缘使 PDE-only/official 仍固定false |

原严格门限保持：native/augmented/total各1e-6，场/复通道1e-4，功率/吸收/能量1e-5，逐级功率1e-6，MPC/恢复1e-10；q30/q15≤1e-8。研究表示门限仍为三项1e-3正见证、1e-2部分见证，不事后放宽。

**本轮结束后不再提出在同一冻结特征上继续换loss/末层超参的自动续扫。** 交付一个后续建议：需要改变hidden/波动表示，还是先解释异常残差—场关系。此建议只作设计，不能自动开始hidden训练、VarPro、PDE微调、参考误差补列或更大模型。

## 7. 资源、执行和提交

本批总新增有载及有界辅助 **≤1h**，T0≤10min、T1≤30min，T2/检查/发布使用其余；同时受原16h剩余约束。V5最终保守累计44815.22461795143s，剩12784.775382048567s，现场补计后续费用，旧失联3284s及重放成本不删除。

所有直接 A/A*调用按作用列数统计：A≤256、A*≤8（构造/测试/验证合计），完整native审核另列且≤12次；G作用列数≤512，不用matmat隐去工作量。新Gsolve、Gram factor、Maxwell factor、非线性optimizer step均为0。复用数组准备和准确参考的新实耗为0，历史从零归属保留，不能称6分钟等于整条神经求解时间。

原生Linux，CPU-only、MPI1、数学/Torch线程1，现场空闲物理核；数值树warn12/hard16GiB、自身swap0，轻测试及浏览器≤2GiB。系统保留max(128GiB,10% effective_total)＋邻任务增长至少384GiB＋自身预算；disk free≥50GiB、artifacts≤20GiB。不得动其他项目、全机swap/BLAS/CUDA或安全策略。缺安全窗口就完成可做轻工作并交付，不无限等待或后台抢跑。

复用已资格化的持久launcher/watchdog及原子保存，launcher单调时钟包含导入/加载；主阶段150s前停止新增长工作，预留至少120s。无cgroup委派则如实使用约0.5s采样，tmux管理开销单列，不声称零干扰/连续内核限额。持久执行不脱离监督；客户端断开先核对同一作业，不重复启动。

实现应选择性复用 `feinn_readout.py`、`feinn_gqr.py` 的只读数据/反变换、原 native action及compare-only；新原方程读出必须明确opt-in，不改变V5数学或普通默认。不得为了读取固定特征再次触发标签拟合或隐藏层前向全量重建。需要拆开含Torch的helper时保持FE环境独立。只跑必要targeted tests，不full pytest、不重装环境、不为文档重复PDE。

建议新one-run输入，Codex先实现stage/白名单再执行，每阶段等待实际收尾后才下一阶段：

```text
input/task042extra_feinn_5nm/v6_operator_readout_checks.dat
input/task042extra_feinn_5nm/v6_frozen_feature_residual.dat
input/task042extra_feinn_5nm/v6_residual_readout_reconstruct.dat
input/task042extra_feinn_5nm/v6_residual_readout_compare_only.dat
```

正式入口仍为 `python scripts/run_case.py <one-run.dat>`；可使用现有 `scripts/launch_task42extra_durable.py <one-run.dat>` 包装，让它按spec切换独立ML/FE activation并调用正式入口，不能绕过入口启动裸worker。

先clean实现commit再run；建议 C1预登记/只读特征加载及定向测试，C2唯一受限作用与验证，C3轻量证据/Response V6。新index不覆盖V1–V5。交付 `response_v6.md`、`outcomes/frozen_feature_residual_v6.md` 及 `records/residual_readout_design_v6.json`、`residual_readout_checks_v6.json`、`residual_readout_projection_v6.json`、`residual_readout_comparison_v6.csv`、`run_index_v6.json`、`resource_costs_v6.json`、`gate_decisions_v6.json`；大矩阵/模型留ignored，不提交无关文件。

summary追加V6保留历史，同步本分支progress/模型总账/tests/changed_files。状态区分 measured/derived/diagnostic/not_run/failed/controlled_stop/blocked，不将数值最优性等同于物理资格。只检查新review及必要新文档的GitHub rendered view；无法访问如实blocked，不虚构视觉PASS，不重复批量渲染历史。

只安全fetch/fast-forward同分支，共享origin.fetch不覆盖本分支时用命令级精确refspec和显式tracking ref；不新clone/分支，不reset/stash/amend/强推，不merge master或其他任务。仅推送 `HEAD:refs/heads/task42extra_feinn_5nm`，报告精确运行source与交付HEAD、upstream核对、工作树、实际停止原因后等review。前置Gate通过后连续完成本批，不逐小步请示；任何结果均不授权p4、目标尺寸5nm或0.7nm启动。
