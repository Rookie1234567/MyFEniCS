# Review V20：V22审阅、同一p1空间的原残差最小化与全空间校正

## 0. 审阅决定与本批blocker

**接受V22真实p1传递、粗矩阵/粗解资格及暖冷负结果；不授予完整有限元、神经加速或合并资格。下一批保持1248维T不变，先比较同一暖残差的Galerkin与原作用像最小残差粗校正，再在数值资格通过后执行固定的全空间右预条件暖/零trace对照。不再扩大p级、增加基维数、改变tau或延长旧配置来替代原因判别。**

本批针对的障碍是：当前低阶来源空间能表示大部分已有误差，却没有使完整原方程有效收敛。需要区分“粗校正的测试空间/目标不合适”与“同一空间和标量细层作用本来就不足”。这是一项有限机制试验，不保证收敛，也不是神经网络已经具备0.7nm求解能力的证明。最终目标仍为约2 TB整机内存内、48小时完成新的0.7nm非可分三维周期单胞；本批仍为384-cell micro、MPI1、16 GiB研究配额。

```text
repository                = Rookie1234567/MyFEniCS
execution_branch          = task42_neural_coarse_inverse
worktree                  = /home/fenics/Projects/NN-Lab
review_date               = 2026-10-02
reviewed_HEAD             = c9ee41f362669995908a55b57325e0fc06884599
reviewed_commit_UTC       = 2026-10-02T06:30:13Z
reviewed_commit_Singapore = 2026-10-02T14:30:13+08:00
original_base_SHA         = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review           = review_report_v19.md
previous_review_commit    = 4d14192e082117e69f76cd3a94c549557ce5693b
latest_response_reviewed  = response_v22.md
V22_solve_source          = 24fbbad55fbef07b75533e60fc1869749a2f8777
V22_verify_source         = 7a7a44ea567abfc119e4eeec474e3e1bea46b519
next_batch                = V23_P1_IMAGE_MINRES_COMPARISON
response_required         = response_v23.md
decision                  = ACCEPT_EVIDENCE_CONTINUE_BOUNDED_RESEARCH
old_p4_inverse_route      = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate       = NOT_QUALIFIED
master_merge              = NOT_APPROVED
```

ChatGPT审查远程最新合同、回应、紧凑原始记录与相关实现，没有SSH运行工作站、取得全部ignored数组或实测当前资源。历史数字是measured/recorded，公式与容量是derived，新队列是planned/not_run。旧task及规则中未变的内容继续有效，历轮明确覆盖的micro/受控共享安排不倒退；当前目录未见另命名supplement。研究设计已使用历史参考审核，不称全新blind test；本批求解仍禁止读取参考数组。

## 1. V22结果与审阅结论

依据：[Response V22](response_v22.md)、[完整结果](outcomes/p1_trace_galerkin_correction_v22.md)、[候选](outcomes/records/candidate_comparison_v22.csv)、[传递](outcomes/records/transfer_checks_v22.json)、[粗层](outcomes/records/coarse_identity_capacity_v22.json)、[离线误差](outcomes/records/offline_warm_error_v22.json)、[费用](outcomes/records/resource_costs_v22.json)。

| 原0.7nm/384hex/p3/q15/40端口；无量纲measured | N无PC暖校正 | P旧Galerkin PC暖校正 | Z旧PC零trace |
|---|---:|---:|---:|
| 原Schur起点 | 2.528117033e-6 | 2.528117033e-6 | 1 |
| 最终Schur；限1e-6 | 2.509882028e-6 | 2.514297762e-6 | 4.117262211e-3 |
| 最终native；限1e-6 | 9.733417414e-7 | 9.750541803e-7 | 1.596689855e-3 |
| 散射E相对误差；限1e-4 | 7.806924080e-5 | 7.797107067e-5 | 2.291184807e-2 |
| 最大逐通道功率差；限1e-6 | 1.706714441e-6 | 1.691290857e-6 | 2.660315336e-3 |
| 周期/Arnoldi步 | 4/1024 | 4/1024 | 32/8192 |
| S+SH / 监督wall秒 | 1060 / 142.75950 | 2106 / 361.33282 | 16778 / 2001.95491 |

三新候选0/3合格，包含旧暖点的独立审核0/4。P的原残差略高于N且成本更大；场误差单项略低不能替代方程和功率。Z从1降到0.004117属于实际进展，但不是合格零起点解；此前没有相同零初值无PC配对，不能单独据此量化p1带来的加速。T未准入不是转移失败。

真实T为18144×1248，CSR载荷4,418,500 B；T^H T接近I，完整p1→p3系数/场/curl独立插值配对最大约5.44e-15。Ac投影配对约6.44e-16，粗解最大相对残差约2.24e-15，cond1估计3704.08。故不应把当前失败归结为已经发现的传递或粗LU接线错误，也不应再用一轮工作重复495秒传递构造。

离线暖误差的trace投影保留98.992898%的平方范数，但补空间的齐次curl范数仍为完整误差的33.51%。两部分原A作用均约5.1175e-4，组合只有2.0902e-7，约2448倍的分项作用相互抵消。**99%是系数度量下的平方范数覆盖，不是99%物理精度，也不保证同空间能消去99%残差。** 原始交叉项和齐次恢复已配对；不能把强抵消单独解释为fine奇异、唯一根因或条件数。

正式监督wall3092.88721894秒，辅助实测130.337806194秒（其余交付计入总elapsed）；正式研发历史下界74063.4870035秒。采样同时树峰912175104 B，自身swap/VRAM0。它们不是单条成功解的部署时间，也不是目标模型容量；上游暖链的精确per-solution拆账仍unknown。原场/通道/功率及负结果不改判。

## 2. 本批改变什么，以及不改变什么

记A=barS为原p3方程消去40端口后的算子，T为V22已资格化的同一归一化传递。旧粗校正G使用T本身检查残差：

```math
A_c=T^HAT,\qquad c_G=A_c^{-1}T^Hr,\qquad G r=T c_G.
```

它令T^H(r-A G r)接近零，但不保证完整欧氏残差最小。新方案先计算T中每个方向在原方程中的作用，W=AT，并做薄QR：

```math
W=UR,\qquad U^HU=I,\qquad
c_M=R^{-1}U^Hr,\qquad J r=T c_M.
```

U是**方程作用像**的正交基，不是trace基T，也不是历史神经Q或物理端口C。新校正是在同一T空间中最小化原残差；MR指minimum residual，不是要求Hermitian矩阵的MINRES算法。实现用[经济型QR](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.linalg.qr.html)和三角求解，不形成W^H W，不显式求逆。

在精确算术、W满列秩时：

```math
A J r=UU^Hr,\qquad
\|r-AJr\|_2=\min_c\|r-ATc\|_2
\le\min\{\|r-AGr\|_2,\|r\|_2\}.
```

此不等式只比较**单次、相同空间和相同r**的残差，不保证场/功率更准或预条件迭代更快。若warm剩余残差几乎正交于range(AT)，即使已知场误差在T中占比大，单次MR也可能几乎无益。只重复同一投影不会继续消除其正交残差；禁止把粗投影循环次数当成求解路线。

本批没有hidden训练、监督标签或新的神经基。保留fine原方程、相同T/1248维、tau、40通道和全部fine校正；不把“更换测试空间”宣传成神经网络设计突破。

## 3. 冻结输入、读取权限与复用

| 项目 | 固定身份 |
|---|---|
| fine模型 | Full3D complex128；0.7nm，1度/azimuth0/s，原三维缺口/背景/RHS；双Floquet、Fourier-DtN |
| 离散 | 384hex/p3/h0.175nm/q15；full34050、trace18144、interior13824、slave2082；端口20+20，z18184 |
| canonical材料 | input/materials/si_optical_constants_v1.json；SI_OPTICAL_CONSTANTS_USER_20260929_V1；ready，离线读取，不再索要 |
| Si | n=0.999885140474+4.32477054e-6i；epsilon=n*n、mu=1；source0.699999988明确alias到nominal0.7 |
| physical SHA256 | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| material / modes SHA256 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 / 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| action NPZ SHA256 | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| T NPZ SHA256 | 22e21cd840efb51d2dc66e556d85587088f406dce3221f564109a27b7b096fd8 |
| Ac NPY SHA256 | d03304fba540afd66d63a00975b655158696d88301e4dd989cdf9e442674b6fc |
| Ac array SHA256 | fc36fbd1d1e74e05922d8a849273f4a03861c06439d972f52dcfba42ad2dcddd |
| warm原点 | V21 C-FINAL，NPZ 680f58e5e58704fc69f0b539c8c411131ce697b7811445eb9643bbf92a736072 |
| REF7 NPZ SHA256 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |

实际路径/成员hash从V22原manifest解析，文件hash与数组hash分别检查。T/Ac只读复用，不重新FE构造，不截列、改归一化、删小值或换p2。warm仍是V21 C-FINAL，不选V22略好的N/P末态，便于复用相同初值历史对照。新V23目录/预算独立，旧目录只读。

角色白名单：IMAGE_SETUP只读packet/T/Ac/标量身份；COARSE_COMPARE和WARM才可解压warm的trace/port/z/residual；ZERO不读取任何warm NPZ、网络/旧Q/循环方向；VERIFY在全部冻结后才读REF7。禁止读取OFFLINE_WARM_ERROR的e/q/c/Fe等数组来构造J或方向。读元数据不授权自动解压全部NPZ成员。参考审核曾参与研究设计的事实如实保留，不称新blind heldout。

## 4. S：一次原作用像构造、QR和数值资格

先从真实钟和旧manifest建立新预算，复用窄reader、class64和旧oracle。既有T/Ac身份缺失时阻塞依赖项，不重跑V22整个campaign补档案。预算允许的最小reader/shape修复可以执行，但没有数据时不猜造。

构造W时按1248个稀疏T列调用原class64 barS；每列按等效单向量作用计费。只能保存18144×1248的薄像矩阵，不能通过18144个单位向量重建fine A。以F-contiguous complex128做固定non-pivoting economic Householder QR；不扫描rank/ordering/regularization。释放可重建W，保留U/R/T；可存W文件便于独立重算但不常驻重复工作区。

只做以下有限资格：8个固定复系数见证（seed422301起）比较Ww、URw与旧oracle A(Tw)，运算尺度差<=1e-10；QR相对重构和U正交Frobenius/norm尺度缺陷<=1e-10；T^H W与旧Ac配对<=1e-10。R的svdvals只作用1248阶小块，用sigma_min/sigma_max>=1e-12判定安全数值满秩，记录实际值；不得截断列来通过。没有fine全局谱或SVD。

S只用固定随机见证核对U^H(r-AJr)的运算尺度缺陷<=1e-8、JATw=Tw配对<=1e-10；warm原r及其实际新状态残差与r-URc的差/norm(原完整b)<=1e-11，留到有warm读取权限的D阶段检查，不让IMAGE_SETUP读取warm NPZ。若后者超限，先分开检查QR、三角解和原作用，不能用较宽的运算尺度掩盖物理残差差异。零r返回精确零；复线性/重复性<=1e-10。R解采用固定一次三角求解；验证不通过时只允许定位明确实现问题，不自动加精化/shift。

经济型QR仍有显著全局存储。单张W或U载荷362,299,392 B（345.515625 MiB）；R载荷24,920,064 B；U+R共387,219,456 B，不等于RSS。登记GLOBAL_TALL_IMAGE_QR_PRESENT；G对照可另外复用一次旧Ac小LU。禁止N×N投影阵、正规方程、p3/p4全局LU/ILU。新增同时workspace规划<=2 GiB，完整同时RSS规划<=8 GiB，12/16 GiB监督及swap0不变；不宣称此薄矩阵能无界放大。

只构造一套W/QR，数值资格通过后保存hash-bound U/R供各独立进程复用。U^H乘向量采用无整阵反复复制的BLAS共轭转置，或一次有界只读缓存并如实计入内存，不能每次PC重新conj整个U。最多一次同配置QR重建仅限已定位、受损输出导致的修复并计费；不得为计时或元数据重复构造。

## 5. D：同一个残差的粗校正直接配对

固定warm r=barb-A*t_b；同时登记zero-trace原r=barb作为第二个无参考RHS。各只计算一次c_G和c_M，报告原||r||、两种校正后残差、T^H残差、U^H残差、校正trace范数、coefficient范数与全部费用。G用V22固定一次精化的RefinedCoarse，不改其算法；MR用新J。

两种warm粗校正都必须生成真正t_b+T*c并完整闭合端口、恢复内部和原audit，不能只报告薄预测。不能给整个恢复场乘一个系数，内部特解只保留一次。zero的单次投影只记录代数结果，不作为后续Z初值。两个修正的完整场只在最终统一验证时比较。

若MR违反上述最小残差不等式且超出实测作用误差及固定1e-11*norm(b)余量，应记IMAGE_MR_NUMERICAL_GATE_FAIL并定位，而不是称“MR算法数值负结果”。若满足不等式但收益极小，应如实记SAME_SPACE_ONE_SHOT_LIMITATION；不据此自动禁止下面安全的全空间首块。不要重复一次投影直到出现假进展。

## 6. M/Z：保持全部fine方向的作用像右预条件

只用J作为PC会丢掉大部分fine方向，禁止。冻结旧tau=0.13558083643793006（用同Ac公式复核，不调参），定义新候选：

```math
B_M r=\tau r+J(r-\tau A r).
```

这与V22的结构和tau相同，只将G替换为J；计算仍包含一次fine A、一次1248阶R三角解、U^H及稀疏T作用。其小解成本不同必须单列，不把所有时间差只归为收敛。

**满秩保护必须单独检查。** 在精确运算中JA是到range(T)的投影，U^H A B_M=U^H；但W满秩不自动保证B_M可逆。令D=U^H T，有：

```math
A_c=T^HUR=D^HR.
```

本例旧Ac可逆且R可逆时D可逆；若B_M x=0，则由(I-JA)可得x在range(T)，写x=Tq后有B_M x=T R^{-1}Dq，因此D可逆才排除非零核。真实构造D并核对D^H R=Ac，配对<=1e-10，svdvals(D)的sigma_min/sigma_max>=1e-12。此为小块稳定性Gate，不是fine条件数；D不安全时仅停止M/Z，保留可信的一次MR配对。禁止静默删列、伪逆或加shift。

小测试必须含一般复数非Hermitian A、非互伴C/F、非零40端口、JA T=T、U^H A B_M=U^H、B_M全秩与右侧求解；另用A=[[0,1],[1,0]]、T=[1,0]^T作反例：A和AT均满秩于各自尺寸而D=0、B_M奇异，证明Gate会拒绝，不能只测易收敛正例。

外层复用V22右PC的实际周期事务：LinearOperator(y -> A(B_M(y)))、SciPy GMRES M=None，restart256/maxiter1/callback_type=pr_norm、tol/rtol0、atol=1e-8*norm(原完整b)。[SciPy M是左预条件](https://docs.scipy.org/doc/scipy-1.11.4/reference/generated/scipy.sparse.linalg.gmres.html)，不能将J/B放入M后仍声称右预条件。每周期y0=0，原r重新计算，更新t_new=t+B_M y；先保存y/By/trace，再old close完整z/40port，再旧oracle原audit/commit。

M从同一V21 C-FINAL独立开始，不从D的单次MR状态开始；Z新进程零trace，端口和内部特解正常闭合，x0=0，不读warm/correction。数值资格通过即可分别尝试首4周期，不要求D先有效或M先成功。原界面不可信则隔离依赖项。Z仅称ZERO_TRACE_FROM_FROZEN_OPERATOR，不是完整geometry-to-solution fresh run。

| 路径 | 上限与分流 |
|---|---|
| S：image_setup | 原作用像/QR/小块/右PC资格<=1800秒；不重新FE传递 |
| D：coarse_compare | 两固定RHS、warm两真正校正；<=300秒 |
| M：image_mr_warm | 首4周期；每4周期原rho下降>=10%才续4；最多16周期/1800秒 |
| Z：image_mr_zero | 首4周期独立准入；每4周期原rho下降>=20%才续4；最多32周期/2400秒 |
| V：verify | 冻结后一次FE，<=10个去重状态/600秒 |

V22的N/P/Z作为同T、tau、起点、外层算法的历史控制，优先直接使用原周期CSV和hash；不重跑它们来换标签。比较共同4周期与共同fine作用次数的真实前缀，不插值；共享硬件wall只作有局限的比较。新配置完全不同源码但原公共行为未变时附ancestor/行为回归；若修复实际改变了旧数值语义，停止声称严格配对，不能用重跑整批掩盖。

每周期保存原b-Sz及细分计数。FIRST_EQUATION_PASS不可覆盖，同额度内最多再2周期到可选rho<=1e-8；最终资格仍是原1e-6，不把抛光目标改成强制门限。连续两次显著原rho上升时只复核一次；真实则收口该路线。M负结果不取消独立Z；没有实质进展不再自动增周期或加入另一PC。

## 7. 冻结后完整审核与因果边界

S/D/M/Z全部冻结并退出后，唯一VERIFY进程才读REF7。审核原warm、两个D校正、M/Z末态、各FIRST_PASS及各固定第4周期，去重<=10。包含V22参照只复用其已审核记录，不额外FE重算一轮。原作用、小RHS及零trace都不是参考标签；不得由参考功率选择头/停止/最佳点或做幅相校准。验证开始后不回算。

保持原门限：Schur/native/增广/规定端口<=1e-6，恢复/identity<=1e-10、slave-zero；total/scattered E/H/curl、selected复场、40复振幅<=1e-4；R/T/A/A_volume差<=1e-5，逐通道功率差<=1e-6，能量<=1e-5。native与独立total-native分开。原物理函数从复振幅导出通道功率时标derived，保存通道键/极化/reference plane，不能以系数欧氏范数替代场范数。

若D-MR显著降原残差却场变差，这是受限空间残差目标与场的折中，不改成PASS；若M或Z通过才可谈完整micro资格。若两种粗校正近似相同或MR只有微小收益，结合M/Z有限结果明确说明同一p1空间的左测试替换仍不足；不要再仅以99%投影覆盖提出重复实验。对当前固定p1空间+标量fine项的配置收口不等于所有multilevel/NN无效。

本批不再次做参考误差投影、全局谱、网络训练或旧V9区域/curl质量诊断。只增加一份基于已有误差与本轮真实残差的原因对照表，写明仍unknown的项。改善若来自J/确定性求解，不能称神经训练增量；暖解的旧神经基和长LSQR成本保留。最多WARM或ZERO_TRACE_MICRO_DISCRETE_PASS_ONLY，无p/h或目标规模/48小时资格。

## 8. 资源、时限与有限自行修复

从接手实时时钟UTC/monotonic/boot_id冻结4小时总窗口，3.5小时停止重负载，最后30分钟交付。实现、测试、设置、修复、等待、求解、验证都计入；每次上下文恢复/新stage/commit/push重新读取真实钟与ledger，未知间隔不扣除。队列退出立刻写最小数值/费用/response包，不能先花完额度再从零组织报告。总截止后仅必要清场/保存/交付，延迟如实报告。

全批原/新S+SH<=32000（含W的1248列）、新B_M<=15000、R三角解<=16000、原audit<=120、FE状态<=10；旧G比较仅一次Ac LU及有限固定精化，内部成本独立记录不伪造精确次数。原资格最多160个额外fine作用（W构造另计）。W/QR主构造1套；R/D各最多一次小SVD；新持久artifact<=2GiB。上限同时有效，子预算不相加扩容，每256周期按<=600个fine作用预留，kill保留上下界。QR/BLAS可能阻塞时独立watchdog仍有效，先保存可恢复身份，不依赖Python循环内才检查。

受控共享CPU保持：实际空闲物理核、避开忙SMT、MPI1、数学/Torch1、Loader0、GPU不用；规划同时RSS<=8GiB、warn12/hard16GiB、ownswap0；系统max(128GiB,10%effective total)、邻增长128GiB和本任务16GiB余量，diskfree>=50GiB。0.5秒整树监督，原PSI full avg10>=0.1百分数连续3次5秒保护不变；无cgroup不称kernel硬限额。只停止自身后代，不修改邻任务、共享Git配置、ABI/BLAS/CUDA/swap/亲和性/锁/watchdog。

资源停止后至少冷却120秒、最多观察600秒；full avg10<0.05持续60秒且其余Gate通过才重入，全批最多2次、累计等待<=1200秒，全部计时。缺一个输入/一条路线只隔离其依赖，不用新算法绕过安全。至多4个已定位根因最小修复，每次<=900秒、累计<=2400秒、同根因最多2次；普通不收敛、D不安全或空间无效不是bug。计划内实现计时但不占修复根因数。数值资格通过直接执行已授权M/Z，不逐小阶段等用户确认，不为跑满窗口重复失败。

## 9. 修改范围、正式入口与交付

复用p1_trace_galerkin/RefinedCoarse只作G对照，复用T/Ac、class64、旧ActionPacket oracle、PortBlocks/BarAction、cycle_commit、窄reader、watchdog和one-run框架。新增J/B_M核心进入src/solvers，配置差异进schema/dat；不要复制整套近千行runner/历史JSON。原普通默认、原物理方程及审核不变；新方法显式opt-in。旧task/review/response/raw及V20/V21历史限制保持。

先focused复数小测试、奇异反例、读取/事务/超时/schema回归，提交clean实现，再按Gate执行待创建入口：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v23_p1_image_setup.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v23_p1_coarse_compare.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v23_p1_image_mr_warm.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v23_p1_image_mr_zero.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v23_verify.dat
```

这些入口在report提交时尚未实现，不能提前宣称已可运行。每个slice是一项明确one-run，绑定input_original/resolved/manifest/input/physical/material/modes/action/backend/T/Ac/W/U/R/tau/parent/state成员hash、实际source/ABI/MPI/线程/run_summary与全过程资源。不要把review SHA当数值source；活跃受检运行期间不改变其HEAD。

提交计划：C1最小新核与复数/reader测试；C2正式接线及clean数值入口；C3冻结求解和独立审核；C4 response/证据/总账。仅新增当前review由ChatGPT完成，Codex不改写它。交付response_v23.md、outcomes/p1_image_minres_comparison_v23.md；紧凑records至少含identity/setup_QR/small_overlap_Gate、coarse_compare、cycle_history/candidate、完整field_channels/power、run/checkpoint、cost/deadline/repair、not_run。勿重复嵌套数千行上游JSON，引用其hash即可。同步README导航、summary/tests/changed_files、development_progress和development_model_registry。

Markdown用fenced math和一致表格；精确GitHub页视觉渲染未取得时如实NOT_VERIFIED，源码检查不等于视觉通过，不为页面访问启动新数值负载。仅推送git push origin HEAD:refs/heads/task42_neural_coarse_inverse；清场后报告精确HEAD/base/upstream/worktree/运行source、MR与G差异、全空间资格/暖冷结果、粗数据真实存储及全部成本、未运行原因和唯一下一建议，停止等待review，不merge master或其他分支。
