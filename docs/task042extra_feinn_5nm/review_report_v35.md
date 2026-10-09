# Review V35：修复未完成的神经空间审计，禁止原样重跑，形成明确去留结论

## 0. 裁决与本轮范围

**接受V35的A阶段：两份冻结神经空间的原方程最小残差已取得浮点数值资格，仍约0.143/0.144，不能达到1e-6。B阶段没有完成，不能将预算停止、930个暂选方向或缺失输出当成最佳场误差或表示能力的否定证明。上一轮要求交付的第二个数值答案尚未交付。本轮修复其算法成本与保全缺口，直接完成投影和独立验收；不原样再跑一次标量G-QR，不再做新的神经训练。**

当前“全局稠密波库＋单块回拟合”生产候选保持关闭。这项结论不依赖B必须给出坏结果，也不等于所有NN数学上无解。关闭不合算的方案和补齐尚未完成的科学归因，是两项不同决定。

```text
repository            = Rookie1234567/MyFEniCS
execution_branch      = task42extra_feinn_5nm
canonical_worktree    = /home/fenics/Projects/NN-Lab-V2
original_base_SHA     = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD  = 303982fcdc6b968b1af1abb0f471eac38cad5622
result_commit_time    = 2026-10-09T09:56:56Z / 2026-10-09 17:56:56 +08:00
review_date           = 2026-10-09 Asia/Singapore
previous_review       = review_report_v34.md
reviewed_response     = response_v35.md
next_campaign         = V36_BLOCKED_ORACLE_COMPLETION
required_response     = response_v36.md
new_continuous_cap_s  = 21600
new_training          = NOT_AUTHORIZED
ordinary_default      = UNCHANGED
merge                 = NOT_APPROVED
```

最终目标仍为真空0.7nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、x/y双Floquet、z Fourier-DtN，完整复E/H/衍射/体吸收；十进制2e12B是整机内存并须留余量，ownswap/OOC=0，单场必要准备至完整独立检查≤172800s。原50×25×140nm目标尚未通过。本批6h是有限研发上限，不是目标48h的成绩。

本支只做神经相关研究。本轮的投影核仅服务于已保存神经空间的可达精度检查，不发展通用Full3D求解器，不恢复W0/W1、全口面、模式恢复、主线接入、传统PC、存储系统或其他支线任务。不得修改Task42、主线、dot、master或其他工作树。

**明确覆盖旧合同的三点：**本轮是独立V36窗口，不再受已关闭V35的A/B共享7200s余量限制；允许下述等价分块QR及受条件控制的小型内积白化，不必等待另一份review；8列限制保留给文件读取/必要FE访问，但不再强加于所有稠密BLAS运算。旧失败与耗时不清零，科学门、物理和安全阈值不放宽。

## 1. 仓库快照与数值结论

审阅端实际读取branch、Response V35、summary、投入决定、A/B原始紧凑记录、根规则/仓库原则、任务身份和相关实现，核对上版review以来5次提交。上版完整审阅书从本会话挂载文件读取，并与远端目录的未变身份相衔接；原task及目录AGENTS沿未变blob继承，目录未发现新增独立补充任务书。未SSH、未在工作站运行FE/训练、未取得大型原始列库；以下是仓库measured，不是本端复测。

| M5/5nm/384hex/p3/31968独立复FE/40端口 | 学习冻结空间 | 确定性控制空间 | 判断 |
|---|---:|---:|---|
| 冻结列/块 | 1377/246 | 1377/246 | 不代表全FE空间 |
| A保留秩 | 1377 | 1377 | rcond=1e-12，全部列保留 |
| A最佳native原残差 | 0.143187704283 | 0.144406937790 | 相对1e-6门均FAIL |
| A归一化一阶最优性 | 2.36446e-11 | 1.95702e-11 | 通过1e-9门 |
| A完整/小系统作用配对 | 1.92207e-11 | 1.20826e-11 | 通过1e-10门 |
| A对应旧散射E误差 | 0.0180687044393 | 0.0196062878330 | 不是最佳G投影误差 |
| B最佳G误差/最终秩 | UNKNOWN/UNKNOWN | UNKNOWN/UNKNOWN | 不得由暂选930推断 |
| B实际新场及物理检查 | 未形成/未运行 | 未运行 | 不存在oracle PASS/FAIL场 |

依据：[Response V35](response_v35.md)、[summary](outcomes/summary.md)、[A最优性](outcomes/records/unlabelled_optimality_v35.json)、[B中断](outcomes/records/field_oracle_v35.json)、[投入决定](outcomes/neural_route_decision_v35.md)。A修复后的source为520cb681dc7c6b69f13caeaa11af98d3d90a7b4b，B元数据修复source为2c1546c2f195a9d6b89703b7e509e899e0db75dc；发布HEAD不能代替数值source。

A两份c/r逐位不变，复用V34完整场Gate合理。保存的AU小R奇异值比约1.10e9/1.84e8（derived），说明幅值反变换可能放大舍入误差；这不是原Maxwell矩阵条件数。满秩、配对及QR回代支持当前固定空间的数值最小残差结论，不是区间算术不可能性证明，也不是所有可学习q/kappa的全局最优。

B唯一尝试5110.947981953854s；最后日志930个暂选方向、G作用至少4167列，部分基/幅值未保存。A/B共享预算耗尽后，保存路径不存在又触发WORKER_FAILED；目录修复后只补了元数据，没有继续投影。原预算规则下不重置时钟是合规的，但**未完成科学目标仍是未完成，修好writer不能算完成B。**

## 2. 本次具体修复对象

[feinn_gqr.py](../../src/solvers/feinn_gqr.py)对每个选中列反复扫描剩余列、执行标量/窄块重正交；[neural_space_audit.py](../../src/solvers/neural_space_audit.py)将稠密处理块也固定为8，并调用同一路径处理1377列。源码可见大量重复列索引、拷贝、G作用和矩阵向量更新。其成本仍为至少O(Nm²)量级，但执行形态未利用大部分BLAS3机会。**这是源码级成本诊断，旧失败没有留下完整分段profile，不能捏造具体90%/加速倍数。**

另一个明确缺口是投影只有最后return后才保存：日志有930列，不等于可以从930列恢复。新方法必须按数值阶段落盘；不应再把整个昂贵投影放在一个不可恢复的函数调用里。

本轮不重建健康A/U/参考，不重跑V34两条训练，也不重新执行V35六组健康组合见证。只对新数值核和保全路径做定向资格。已完成A直接按hash复用；可额外从保存Q/r计算一次Q* r及勾股配对强化最优性摘要，但不得因此重放所有原A列。

## 3. 相同目标的分块算法，不改变神经空间

唯一待求量仍是各自冻结空间的最佳G场投影：

```math
 a_G=\arg\min_a (Ua-c_{\mathrm{ref}})^*G(Ua-c_{\mathrm{ref}}).
```

G为已保存的同M5正定H(curl)内积，ell=5nm；参考为同p3散射系数，SHA256固定0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7。q/kappa/窗口/T/原列掩码、材料、mesh/MPC、完整40端口和所有评价分母保持。参考不参与基的选择、秩截断或算法选择；数值方法的切换只由稳定性与实测成本决定。

### 3.1 首选：欧氏Householder预正交，再作小内积白化

通俗说，先把互相很接近的1377个函数换成数值更独立的坐标，再在这组坐标里衡量电场和curl。换坐标不改变它们能表示哪些场；大矩阵上的工作尽量交给块式线性代数，不能直接对病态原U形成U*GU后求逆。

取d_j=norm(U_j)_2，D=diag(d_j)，X=U D^{-1}。d_j必须有限且正；严格零列单列报告，不加epsilon造方向。对X作经济型Householder QR，保留原顺序与全部列：

```math
 X=Z R,\qquad Z^*Z\simeq I,\qquad H=Z^*GZ.
```

用已有SciPy/LAPACK，不升级环境。禁止full N×N Q。H只为1377×1377；原N×N的G不分解、不求逆。以32列执行稀疏G乘法并记录所有列数，稠密矩阵乘法允许连续64列或库内panel，不再做每8列的Python索引循环。

必须记录H的Hermitian缺陷、lambda_min/lambda_max及cond2。先要求相对Hermitian缺陷≤1e-12，且lambda_min>0、u*cond2(H)≤1e-8（u为float64机器epsilon）。条件不满足转§3.2，不加shift/ridge、不抹掉负特征值。小的舍入对称化只在原缺陷通过后允许且记录。

若H=L1*L1，L1为上三角，则用三角求解构造V1=Z L1^{-1}。重新用原G计算M1=V1*G V1，若G正交缺陷大于1e-9，允许且仅允许一次小型Cholesky再正交，得到V2=V1 L2^{-1}；必须仍通过正性/条件检查。更新每个基变换的顺序，得到：

```math
 X=V T,\qquad M=V^*GV,\qquad b=M^{-1}V^*Gc_{\mathrm{ref}},\qquad a_G=D^{-1}T^{-1}b.
```

这里M和T仅是小矩阵，所有逆符号都用solve实现。一次白化时T=L1 R，两次时T=L2 L1 R；也可保存三角因子链避免显式乘积，不能颠倒顺序。数值残差必须由实际U a_G和原G重算。

**这一路径确实形成正交坐标下的小投影Gram矩阵，不应谎称完全没有正规方程结构。** 本review特许的是先Householder预正交、再受条件控制的小内积求解；不允许直接对原病态U的U*GU求逆，亦不允许形成A*A。CholeskyQR2的文献改善稳定性不替代本例资格。

不得仅因为A的AU满秩就假设U的数值反变换无误。R/T的rcond=1e-12秩诊断与奇异值照实记录；任意实际丢列必须标为截断子空间。主路径不借改变归一化/门限静默丢方向。只有全部1377方向可稳定表示、完整映射和最优性通过，才能作满空间结论。

### 3.2 自动后备：确定性分块G重正交

若小H正性/条件、最终G正交或反变换资格不过，自动在同一空间启用32列panel的两遍G-正交化；保留原列顺序、原G、原目标和rcond。对新panel P及已保留V/GV，成块计算H_p=V*GP，P←P−V H_p，再用原G刷新，至少两遍；不对每个新列重新扫描全部剩余1377列。

panel内部用经独立白化例子验证的小型QR/受控Cholesky再正交；若局部近相关不能稳定处理，允许按32→16→8→4→2→1的确定顺序细分该panel，用原稳定标量内核仅完成困难panel。划分仅为数值实现，不是改变列集合/截断参数；每次切换和费用保存。

后备不是再次原样启动整套旧标量G-QR。普通实现错误在同批修复，真实数值秩不确定则如实报告；不为获得一个更好答案在两算法之间挑结果。两个方法对同一目标若显著不一致，应定位与交叉验证，而非选择较小误差。

### 3.3 必需的精度与成本资格

至少覆盖复数SPD内积、满秩/重复列、强相关/尺度悬殊列、非零复右端项，与小型独立G平方根后的Householder/SVD结果比较。测试包括列变换顺序错误、把原A当G、丢列后冒称满空间、错误共轭及恢复混身份的负控。

实际每个空间先用固定前128列做一个短前缀核验和计时，最多10分钟，不按标签选列。已通过的结果可作panel后备的完整checkpoint，首选全矩阵QR不能冒称可以从该前缀任意续接。记录加载、QR、G乘法、小因子、回代/映射、独立核验及落盘的互斥timer，不再只剩一个总timeout。

完整空间正交norm(V*GV−I)_F≤1e-9，归一化重构≤1e-10，最优性≤1e-9，原点值网络/producer重建≤1e-10，独立场积分配对≤1e-8。每项都保留分子和实际分母。局部合成例子的强相关反变换可能达不到1e-10，即使正交基本身很准；测试必须正确拒绝该输出，不把理想Vb冒充实际网络场。

预计收益只是假设，不能在运行前宣称加速。前缀计时若显示主路径不能在本空间预算内完成，先在同批改连续布局/内核与不必要复制，再选已资格化后备；不以换一份design为由重开时间窗。

## 4. 输出保全：保存真正的数值中间态

启动即创建所有per-space目录，并先验证stop→原子记录→重开路径。空秩、刚启动即触发deadline、半panel中断和写入失败必须有测试；停止处理器的mkdir或JSON错误不得掩盖原停止原因。

首选路径至少保存LOADED、EUCLIDEAN_QR、GRAM_REDUCED、G_BASIS_QUALIFIED、ORACLE_FIELD_FROZEN各完整边界；后备每完成panel就保存基/变换/下一列位置/G计数。原始U不重复存，GZ等可重算的派生量明确标记；临时文件fsync后原子替换，成功落盘后才发布committed事件。

中间基不是合格oracle场，不能把partial rank当最终秩。重启先识别原run/PID/start_ticks；原作业仍活跃就重附着，不启动副本。若被终止则从最近完整边界恢复，计时和费用继承；代码数学变化只使受影响层及后继失效，不连带重做健康U/A/旧参考。未保存的V35第930列状态不存在，禁止声称从它恢复。

现有writer目录修复直接复用。这里只改本数值阶段，不新建调度/传输/存储系统。真正难以中断的库QR调用前保存可复用输入，并根据实测工作量留出保存余量；不能宣称SIGKILL必能执行finally。

## 5. 两空间投影和独立完整验收连续进行

先处理学习冻结空间，再处理确定性空间；各自成功的oracle立即落盘并可独立验算，不等另一空间全部完成才保存。V35 A文件及原Gate只读复用，不再反复执行六组旧完整矩见证或全A刷新。

两个冻结V34输入按[unlabelled_optimality_v35.json](outcomes/records/unlabelled_optimality_v35.json)的source_identity定位：学习committed hash=bae90dbfbf9a6c0ac53e62eb125c130a5792b3618c4ac49ecb64cce39acbf134；控制hash=555b64c8207e0ac8db23bf099856800626f6438e808f0c7813facdd26e475e6e。不要误用V35包装后的新模型hash作为原波形身份，也不要取best/旧V32。

两份A已封存的聚合记录hash=f9a1381ebff9fde3186a0331e4175b043b77acd5235025123be2dff6a31150a4。B开始和结束都确认其未变。G/mesh/MPC/moments继续按V35 design绑定。只在索引列出的本任务副本恢复缺失数据，不通过重训或新MUMPS补标签。

新a_G写入独立diagnostic模型，实际q/kappa/窗口/T参数不变。允许围绕旧c0做等价差量幅值求解和complex128补偿累加，但最终完整幅值必须真的从点值路径生成对应c；不以c_ref覆盖输出。

永久标记：

```text
reference_used_for_coefficient_fit=true
reference_used_for_training=true
pde_only_solve=false
production_initialization_allowed=false
pde_only_solver_qualified=false
official_candidate_results=false
scope=FROZEN_NEURAL_SPACE_ORACLE_DIAGNOSTIC
```

独立ML q30/q60重建及FE compare-only完成：原native/增广/独立total、总/散射E/H/curl、六点复场、四类完整40模式复向量、R/T/A_balance/A_volume/R00_s/R00_p/R00_total、每级功率、材料/界面区域、MPC和恢复。旧场未变则复用，只有新场重新计算。

严格门不变：原方程各1e-6；场/六点/每类完整复通道向量1e-4；R/T/A/体吸收及独立能量1e-5；逐级功率1e-6；完整模型/MPC/恢复1e-10；求积1e-8。oracle即使某些/全部数值门通过，仍非无标签求解、非production初值。

最优性缺口按实际完整误差e=c_ref−Ua_G计算：

```math
 M=V^*GV,\quad s=V^*Ge,\quad
 E_{\min}^2=e^*Ge-s^*M^{-1}s.
```

不以两个近等的大能量之差替代直接形成e后的积分。报告最后一项、正交/映射/积分误差估计，以及距离1e-4门的余量。若rho=norm(M−I)_F<1，可用norm(s)^2/(1−rho)给出优化缺口上估计。必须同时控制实际映射误差；浮点估计不称严格区间证明。

只在完整空间保留且稳定性通过时，最佳G误差明显大于1e-4才能数值排除该冻结空间同时满足E/curl门。截断空间的最小误差是完整空间最小误差的上界，不能反向作排除；理想基很准但实际模型回写不可靠时，分别报告IDEAL_SUBSPACE_RESULT和MODEL_EXPORT_UNQUALIFIED。

## 6. 数值答案之后立即给出投入决定，不再循环猜网络变体

| 本轮实际结果 | 必须给出的判断 |
|---|---|
| 完整稳定G最优误差仍显著大于门 | 当前两份冻结波形表示不足；当前空间内继续幅值/loss扫描结束 |
| G最优场很好但A最小残差仍约0.14 | 场近似好不等于满足原方程；同空间换loss无法突破A已核实最小值，不自动复活该候选 |
| 后备仍无法稳定完成或实际模型映射不过 | 明确算法/表示导出受限，最佳场归因仍未知；不伪造数值负证，也不自动授权第三轮相同审计 |
| 任一oracle漂亮结果 | 仍是参考暴露，不授NN资源收益或0.7nm资格 |

不要求必须得到有利或不利的某个数值；要求给出真实完成状态及上述限定。当前生产停投决定不因B未知而无限推迟。

从现有证据最多给出一个下一神经机制的准入说明，且须明确改变表示空间或学习对象，删除哪项实测成本、单场N=1数据/训练费、同能力确定性控制、内存增长和最小否决试验。没有支持就保留NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE，不编名字、注册空0.7nm入口或启动新训练。完成补审不是向主线转移工作的理由。

本分支对0.7nm目标的诚实结论：目前没有合格的神经前向方案可承担原尺寸、2TB、48h交付。2TB不能修复近似空间误差；即使本oracle低误差，也没有N=1求解方法与成本突破。今后神经路线必须同时产生真实联合Gate和同精度完整成本收益，不能把解码/缓存小加速当目标可行。

原U/Q基础存储32Nm B；N=1e7、m1377为440640000000B，N=1e8为4406400000000B，均仅形状推导，非实际目标DoF/RSS。保留旧必要前缀10186.178641493432s、V34学习保守加载packet归属20728.120829955675s和V35失败费用。项目不重复计历史前缀，冷N=1和精确历史累计未知仍UNKNOWN。

## 7. 预算、安全与自主修复

新连续总窗21600s从首项准备起计，不沿用或重置旧run。软分配：实现/新核资格5400s、学习空间5400s、控制空间5400s、独立场验收与交付3600s、共享修复1800s；可以在总窗内显式转移未用额度，但最后至少保留1800s，不能再次用A/B旧卡阻止已准入B的正常执行。

数值投影各空间默认5400s包含前缀profile、失败、后备、恢复、落盘；允许利用另一项尚未用额度，须先登记且不侵占最终验收。达到稳定oracle后立即评分，不为“用满时间”增加诊断。若共享环境实质不安全则只停止自身数值树并保存；不能以“必须推进”为由降低门限。

CPU-only/MPI1/数学线程1，一个现场合格物理核；warn12/hard16GiB，含所有临时数组与库workspace保守规划≤12GiB，轻检查≤2GiB，ownswap/OOC0。稀疏G乘法32列、稠密panel最多64列均属numeric角色；矩阵批量不是MPI rank数或FE cell批量。G/QR缓存不跨两空间同时常驻。现有N=31968、m1377每份complex128列库704318976B（derived），程序仍须核对实际形状与生命周期，禁止照抄示意数或把数组bytes当RSS。

保留原系统余量max(128GiB,10%有效总内存)+384GiB邻增长+本任务预算、PSI60s/cpuset/SMT和新鲜样本规则。成功准入计总墙钟，不扣旧1200s观察池；真实拒绝后的额外前台等待≤900s，不后台抢跑。磁盘启动自由≥50GiB，本批新增artifact≤12GiB，不删历史健康数据；中间副本超过预算只按已登记派生对象回收，不删除原证据。

普通API/schema/导出/目录/数值角色/QR/保存错误同批定位→最小修复→targeted测试→健康边界继续，无“第几个bug交棒”次数规则。等价核后备已获授权，不另等review；真实数值不确定、不可恢复输入/ABI/权限、硬安全或总预算才可收口。没有无限尝试或必然PASS承诺。网页错误只影响视觉状态，不触发健康数值重算。

## 8. Git、入口与交付

开始先只读确认本任务无活跃run、branch/HEAD/worktree/锁；有合法活跃作业不随意改HEAD或kill。仅精确fetch/ff-only本分支，不新clone/分支，不reset/stash/amend/强推/merge其他分支。root、docs及任务AGENTS、仓库原则、task、Review V34、Response V35和本报告为必读。

新增核保持显式opt-in，进入合适src/solvers模块；复用原worker、saved checker及durable wrapper，仅做必要stage和依赖接线，不复制训练器或另造存储框架。先目标测试和clean实现commit，再逐项运行以下建议输入（尚未实现，不得直接塞入旧白名单）：

```text
input/task042extra_feinn_5nm/v36_oracle_kernel_checks.dat
input/task042extra_feinn_5nm/v36_learned_space_oracle.dat
input/task042extra_feinn_5nm/v36_learned_oracle_verify.dat
input/task042extra_feinn_5nm/v36_control_space_oracle.dat
input/task042extra_feinn_5nm/v36_control_oracle_verify.dat
input/task042extra_feinn_5nm/v36_neural_route_decision.dat
```

用已有`python scripts/launch_task42extra_durable.py <one-run.dat>`，包装选择对应纯数组/ML/FE环境并调用`scripts/run_case.py`。每项清场再下一项，不能一次并发启动所有命令。输入、resolved config、manifest、source、物理和artifact hashes及资源证据全部保存；发布HEAD与数值source分开。

建议提交：C1新核/故障路径tests；C2资格及学习空间结果；C3控制空间和完整验收；C4紧凑证据/裁决。健康阶段不因文档更新失效，不重复full pytest/重装或全仓hash。

必交response_v36.md、outcomes/oracle_completion_v36.md、outcomes/neural_route_decision_v36.md。紧凑records包含design、input_identity、kernel_checks、phase_profile、fallback_and_resume、oracle_metrics、rank_and_gap、actual_model_pair、joint_gates、cost_capacity、repair、run_index、tests。大基/场留ignored，只保留唯一紧凑索引，避免重复万行JSON。

README/summary当前导航必须同时写清：A数值最小残差已知；B完成后的实际数字或准确阻塞；当前生产族关闭；没有新的0.7nm/NN净收益。同本分支progress/模型总账/tests同步，历史不覆盖。审阅端只测小型代数，不得冒称工作站资格；浏览器有限补查新review和关键结果页，视觉未得证据如实保留。

完成整个有界包、真正数值归因和投入决定，或触发明确硬出口，才一次交棒。只推送`git push origin HEAD:refs/heads/task42extra_feinn_5nm`，报告完整HEAD、显式tracking/ahead-behind、clean和自身清场。不能用“修了writer”“代码已提交”“临时基有930列”代替交付。

## 9. 方法来源与验证边界

[LAPACK块Householder QR](https://www.netlib.org/lapack/lug/node69.html)解释矩阵块运算的结构；[Yamamoto等的非欧氏内积CholeskyQR2误差分析](https://www.jstage.jst.go.jp/article/jsiaml/8/0/8_5/_article)说明重复白化可改善稳定性，但存在条件限制；[Demmel等TSQR研究](https://arxiv.org/abs/0806.2159)给出减少数据移动的QR思路。本轮不移植分布式库、不宣称文献加速比在本工作站成立，也不读取论文PDF冒充逐页复现。complex128公式和实际模型均须本地资格。

本报告的实质任务是完成此前承诺却未算完的神经空间判别，以稳定、可恢复的同目标算法终止重复审计。它不是新的前向求解突破，不应该继续耗用本支数十轮版本来冒充0.7nm进展。
