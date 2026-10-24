# Task41extra Review V13：用保存两cell包区分归因计算误差与生产缩减误差

## 0. 裁决、身份与本轮唯一目标

**接受V12两cell产品与独立保存复核：y9、g9分别精确重现。全域action仍FAIL，不批准再建owner、修改生产默认或进入200q。下一唯一包是对现有矩阵/向量做“逐操作误差账＋目标行敏感度分解”，给出具体生产函数的修复依据或明确否决，不再重复取证。**

要消除的blocker：目前把“计算误差的归因公式自身产生的余差”和“原RHS缩减中的误差”混在一起，尚不能确定应该修改哪一步。本包先把两者分开，再把内部误差转换为目标trace行上的有符号影响。只读约76 MB局部包、必要donor切片，并至多对保存LU做两次伴随回代；不需要FE、积分、矩阵重建或新分解。这是诊断，不是新的PC或更高精度生产求解器。

| 身份 | 冻结值 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 结果HEAD | `a6cde586698dc44d15b365ac8edd711768a229dd`，审阅时远端一致 |
| Producer source | `196aedecbef5d129588c629fc091682d7a2900f4` |
| Checker source | `9a6ccdcefc12119275f1ce1082f154af5a881241` |
| 前份review | `dfdfcf2d52c55e8897cb0f808f15e6a5c9e0b489` / `review_report_v12.md` |
| 日期 / 类别 | 2026-10-24，Asia/Singapore；数值稳定性、算子一致性、保存数据分析 |
| 目标保持 | 0.7 nm、50×50×140 nm域、居中17×20×120 nm Si、方位90°、p6/10×200×14；完整Full3D，十进制2 TB含余量、任务swap0、必要冷流程≤48 h |

审阅核对response/compact、producer和checker原件、summary/test记录、实际producer计算次序与生产same-LU核心；继承未变task、V12和根/docs治理。没有登录工作站、读取其NPY或运行项目测试。本Chat只提交本review；文中源码发现、远端实测和本地独立代数/标量复算分别标明。不同source不重新署名。[R1][R2][R3][R4][R5][C1][C2][C3]

## 1. 接受成果与继续锁定的门

| 对象 | 本次判定 |
|---|---|
| 两cell身份 | active87567→original250113，全部incident=[360,446]；本行各一个系数1+0j，保留其MPC覆盖边界 |
| 局部产品 | 198数组、76,009,104 B；producer确有必要mesh/space及两格构建，不能把整个V12说成无FE |
| 独立审核 | attempt06重算184项，y9/g9及状态分别精确重现；接受check_completed/data_integrity，不转成scientific PASS |
| 原全域action | 2.6749770637124364e-10、5.613598120039757e-10，高于1e-11；保持FAIL |
| 原candidate恢复 | V9仍NOT_RUN_ACTION_GATE_FAILED；V6初次恢复约1.98e-11仍FAIL；旧donor三次修正PASS不转授 |
| 覆盖 | 本行仅占全域误差能量约0.00627%/0.00664%；不能据本包局部改善解锁全域 |
| 后续 | 200q、准确因子、完整参考、FGMRES、完整场及最终精度均未资格化 |

producer worker148.448733087 s，其中prepare51.777025161 s、两cell3.444857046 s、12次GETRS0.029665038 s；checker watchdog34.299329 s嵌套于service39.979969599 s。attempts02–06已知service父合计510.8661423435005 s，不是全包成本，也不再加子阶段。工程等待、入口失败与UNKNOWN保留。tree/cgroup分列，task swap0，PSS未采样；小包峰值不外推完整容量。[R1][R2]

## 2. 确定的诊断问题：旧Equation2估计没有覆盖真实求值路径

实际producer使用：

```python
w = R @ t + z_b - z_r - u
left = K @ w
right = ((K @ R + G) @ t) - delta_i - r_b + r_r
estimate = gamma(16 * dimension) * max(1.0, max_abs(left), max_abs(right))
```

`delta_i=K@u+G@t-n_i`、`r_b=b_i-K@z_b`、`r_r=r_i-K@z_r`同样由独立浮点运算产生。输出相消后只有约1e-9，于是估计退化为3.1334934647118606e-12；但它没有传播`R@t`及加减误差经K的放大，也没有覆盖KR、Ku、Gt、Kz和大RHS相减的误差。**它不是这条完整计算链的可靠前向误差上界。**超过该数208–1047倍既不证明实现有数学错误，也不证明“只是舍入”。此前保留的经验估计在此澄清，不改旧记录，更不调整科学门。[C1]

另一个关键点：在精确算术且`r_i=b_i-n_i`时，Equation2对任意R、z_b、z_r都恒成立。它并不要求z_b/z_r是准确解。因此Equation2不闭合不能单独指控GETRS；Equation2闭合也不证明GETRS正确。必须另算同一存储K下的真实残差及其trace影响。

本Chat只对公开在R1/R2中的复数标量重做末级求和（分实虚math.fsum）：四组Equation1余差绝对值由约4.579e-11、1.230e-10、2.985e-10、2.933e-10变为4.828e-11、1.193e-10、2.755e-10、3.078e-10。**只改善最后一次全局求和不足以消除余差。**这不是NPY重算，也没有改变生产输出。独立4×4复数示例另验证下节符号账与伴随恒等式；不作为项目资格。

## 3. 唯一执行包A：按实际运算图解释八组Equation2余差

### 3.1 不再生成数据，复用并补齐微小中间量

从attempt03报告绑定的raw/oriented tensor、原I/T位置、R/T/S、LU/pivots、E映射、两列输入及j0/j3分项读取。K/G/J/L从同一oriented张量按真实分区取得，禁止连续切882行、candidate/reference混配或从LU反推K。

沿现有saved-array入口只新增所需分析，不重新执行整个184项审核、原12次GETRS、完整donor实验或全域比较。输入身份/字节/hash仍按实际消费核验一次。已存z_b/z_r固定不动。尚未单独保存的`w`、`KR+G`等只在这两个小矩阵上按原complex128次序重算，绑定既存left/right/difference；若重算节点不吻合，先查布局、BLAS/线程和状态，不能拿“约相等”掩盖身份问题。

将`delta_t`输出说明固定为`local_Ju_plus_Lt`；旧键和数组不改。全局native trace只在完成两cell组装后扣一次，不给每个cell各分配一份。

### 3.2 逐操作有符号账，而非增大gamma后宣布通过

下面所有无帽表达式均表示**以保存的二进制浮点输入为精确数**进行诊断求值；不是连续PDE真值。帽号表示原complex128计算所得节点。定义：

```math
\begin{aligned}
w_*&=Rt+z_b-z_r-u_i, & \chi&=b_i-n_i-r_i,\\
p_*&=(KR+G)t, & \delta_*&=Ku_i+Gt-n_i,\\
r_{b,*}&=b_i-Kz_b, & r_{r,*}&=r_i-Kz_r.
\end{aligned}
```

逐项求出以下误差，不用范数反推向量：

```math
\begin{aligned}
e_w&=\widehat w-w_*, & e_L&=\widehat L-K\widehat w,\\
e_p&=\widehat p-p_*, & e_\delta&=\widehat\delta-\delta_*,\\
e_b&=\widehat r_b-r_{b,*}, & e_r&=\widehat r_r-r_{r,*},\\
e_H&=\widehat H-(\widehat p-\widehat\delta-\widehat r_b+\widehat r_r), &
e_o&=\widehat\eta-(\widehat L-\widehat H).
\end{aligned}
```

这里`Lhat/Hhat`只是Equation2左右向量，不是局部trace块L。应验证：

```math
\boxed{\widehat\eta=K e_w+e_L-e_p+e_\delta+e_b-e_r-e_H+\chi+e_o.}
```

`chi`不能默认零：保存的r_i是一次浮点相减，严格诊断应保留它与精确`b_i-n_i`的差。由此即使高精度重组后不为零，也不先判算法错误。每组输出各有符号向量/最大分量、平方和及合计解释余差，并保持原1e-11冻结分母的旁列；这些是诊断，不新增或放宽科学阈值。

诊断实现先用已有实虚longdouble小块运算，报告真实mantissa位数。精度不足或项间强抵消时，只对每组最关键的1–3个分量用标准库Decimal精确接收float（`Decimal.from_float`），以两个精度级别确认符号/规模稳定；可复用已安装多精度库，但不安装新环境。`p_*`可用高精度`K(Rt)+Gt`计算以避免高精度完整矩阵乘矩阵，生产仍维持原`(KR+G)@t`，二者差正是要记录的求值误差。宽算术用于计量，不作为新生产答案或门限替代。

本层出口必须回答：八组余差分别由哪些实际操作解释、还剩多少。不能只再输出“在更大上界内”，不能用宽算术闭合直接宣称原action通过。

## 4. 执行包B：把内部误差映射为目标行影响

只看`r_b`或`E_R t`的范数，不能知道它对trace行影响的大小和正负。使用一次**伴随局部回代**建立该行的敏感度：它告诉我们内部哪个误差方向会被放大到这条trace行；每cell一份，对两列和j0/j3复用，不是另一个PC。

令q为该cell中目标active行对应的E列（当前为一个1，其余为0）。用保存同一LU求：

```math
h=J^Hq,\qquad K^H\lambda\simeq h,\qquad e_\lambda=h-K^H\lambda.
```

至多两次`lu_solve(..., trans=2)`，每cell一次；pivot沿既有安全函数复制为可写int32。不重新factor、不重新求原z_b/z_r。旧producer的12次GETRS保持原账；新两次明确标`ADJOINT_DIAGNOSTIC`，不算candidate恢复精化，也不写回原报告。伴随残差独立较宽求值；不能假设其为零。

在同一保存输入的诊断精确数语义下：

```math
\begin{aligned}
q^H J w_*={}&\lambda^H (KR+G)t-\lambda^H\delta_*
             -\lambda^H r_{b,*}+\lambda^H r_{r,*}
             +\lambda^H\chi+e_\lambda^H w_*.
\end{aligned}
```

这分别隔离R形成缺陷、local/native内部差、对原RHS的求解残差、对残差RHS的求解残差、r_i制造差以及伴随误差。再用包A的`w`求值误差与实际J乘法/投影误差，把它接回保存的`Jw`，不能只验证新的宽算术恒等式。

最后按原Equation1将local `Ju_i+Lt`、全局native项、`C_S t`、同LU残差缩减和这些贡献组装到原d。对两列×两状态输出有符号贡献及未解释余差。对`C_S t`另比较保存求值与同一存储S/L/J/R上的高精度`S t-L t-J(Rt)`；保存0不是精确代数缺陷必为0。j0/j3的trace相同，因此不把共同的`C_S t`单独当作状态差原因。

无需重新求解原散射场，也无需新reference张量。保留`g_prod`与用固定保存z_b、同一J及b_t作较宽乘加得到的`g_eval`的有符号差，直接区分末端J乘法/散射相消与上游求解/算子不一致。诊断`g_eval`不得替换保存g9，不能用已知d反推补偿量。

## 5. 本轮必须落到具体生产操作，不盲试第二方案

| 新证据指向 | 本轮结论及对应生产位置 |
|---|---|
| 仅归因节点或最终重组误差解释Equation余差 | 修诊断估计/说明与有符号分解；不声称修复action，不改生产数值 |
| `-lambda^H r_b`能解释目标行误差，且不是被同量级其他项抵消 | `hcurl_assembly_time_condensation.py::project_internal_rhs_same_lu`中的求解精度成为有依据的下一修复靶点；本轮给原残差、投影影响与代价，不自动增加修正次数 |
| 固定z_b时J乘法或global scatter的求值差占主导 | 指向该核心的J matvec或`P6CellCondensedAction.reduce_rhs`的累加；用现成局部包说明具体稳定求值改动，不能只换最后一个全局sum |
| native/local差、R/Schur形成缺陷主导 | 明确否决“仅改RHS求解即可”的方案；列出actual evaluator、局部消元或native接口中需核对的具体操作及确缺数据，不重建两cell或全域 |
| 状态/索引/符号错误被实际定位 | 同范围最小修复并在保存包复算；原负结果保留 |
| 多项近抵消、诊断精度或伴随残差仍不足 | 给出准确未分辨项和最低所需量；不能宣称唯一根因或按norm大小选赢家 |

本轮不授权串行尝试若干算法、生产精度升级、修改native、构造新RHS、增加第四次恢复或再次全域owner。允许修确定的状态/接口错误；对新的数值修复最多交付一个由上述账支撑的具体生产变更提案及需重验范围。若证据不支持单点修复，明确`NO_SUPPORTED_SINGLE_OPERATION_FIX`，不要把“继续研究”当结论。

本行误差能量覆盖很小；后续即使提出修复，仍需另行设计跨材料/方向的代表覆盖和原两列全域验收。本包不自动解锁这些计算，更不解锁200q或FGMRES。原1e-11 action/forward、native residual、恢复次数、PC、物理和资源门不变。

## 6. 接续与费用：不再为每个review重建入口

复用现有saved-array service、读取器与冻结NPY，新增本包分析函数即可。不要复制V13 runner/schema/watchdog，不重新做attempt06的完整184项复现作为前置。新分析只校验实际消费的身份/数组和相关原输出，继承旧资格与全部失败。producer和checker source各自保存；当前consumer另写receipt。

固定attempt03产品入口（工作站根`/home/fenics/Projects/laptop_share`）：

```text
results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_selected_trace_candidate_replay.json
```

报告SHA256=`2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876`；独立checker报告SHA256=`cdbd2a0a8d6ae62b61ad1a45b8bd4f62dae4c69ebb1f0f7923205ac85e4c3739`；service receipt SHA256=`0b28a0f2b57aa17d515627097978a5470c7787ca9c61b15c07a0d25b14ae217f`。数组从报告精确路径/hash解析，不按相似目录猜测。[R1][R3][R4]

当前V12窗T0=`2026-10-23T23:12:47Z`，数值截止=`2026-10-24T04:52:47Z`，总截止=`2026-10-24T05:12:47Z`，即新加坡今日12:52:47/13:12:47；window SHA=`4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6`。本轮属于该两cell保存分析范围，在实际授权/合同允许且实时余额足够时沿原窗连续完成；不抄旧12970秒余额、不刷新T0。代码修复、运行准备与等待按原口径计费。

若接收或准备完成时旧窗已截止，不启动新的工作站数值分析。备用新6h窗口21600/20400/1200秒仅为`PENDING_USER_APPROVAL`，使用现有窄合同实例，不自动延长。当前review不自行创建新窗口或扩大scope。

task cap1.5TiB、host reserve64GiB、task reserve0、原complex128/int32、MPI1/math1、task swap0、磁盘底线2GiB保持。分析工作集不得超过既有6GiB准入范围；新增局部证据目标≤16MiB且仍受原512MiB单包/16GiB累计额度制约。只保存必要小向量/标量及两个伴随向量，不复制76 MB原包或新全长差数组。没有新FE、form/JIT、积分、LU factor、carrier读取、全域扫描或candidate恢复。

只补两类小测试：含强相消、非零chi/不准确z的运算图账，及复MPC/伴随残差/输入污染的有符号投影；加一个现有saved入口到新分析的轻量调用测试。不得全仓pytest，不升级环境。检查器读取新增结果独立复算关键账，normal exit不等于scientific pass；只回读已保存的两个lambda，不再重复其求解。普通记录/接口bug修复后读回同一产品继续。

提交计划：先窄实现/定向测试，后一次保存分析及`response_v13.md`/compact，更新原run_index/summary和两级账。响应首屏给八组误差账、四组目标行有符号分解、唯一建议生产函数或否决依据、尚缺量及成本；不要再仅报告“审核完成”。主控集中提交同分支，不改master/Hybrid/其他Task，不删除负结果或覆盖旧SHA。

## 7. 给Codex的执行摘要

```text
按同分支review_report_v13.md继续；结果base=a6cde586698dc44d15b365ac8edd711768a229dd。
V12两cell及独立复核接受，y9/g9已分别精确重现；原全域action仍FAIL。
本轮只用198数组/既有donor切片，不重建FE、两cell、全域owner或factor。

原Equation2估计只用相消后left/right，未覆盖完整运算图；保留旧字段为历史
诊断，不能扩大上界制造PASS。Equation2对任意z都能恒成立，不是GETRS精度检验。
先固定保存z_b/z_r，按原complex128次序恢复所需小节点，核对旧left/right，
再按review有符号误差账分解Ke_w、各matvec/相减/重组误差及chi=b-n-r_i。
较宽计算只诊断，精度不够时仅对关键分量做双精度级别的Decimal核验；
不做高精度完整矩阵乘矩阵，不把宽算术结果替换原答案。

为把内部残差变成目标行影响，使用保存LU各做一次K^H lambda=J^H q，
总计至多2次ADJOINT_DIAGNOSTIC回代；无新分解，pivot可写复制。
保留伴随残差，不重复旧12次求解，不计成恢复精化。
两列×j0/j3分别投影R缺陷、local/native差、b/ri求解残差及制造误差，
连同伴随残差、J乘法、原MPC/全局累加余差接回保存d。
全局native项只扣一次，delta_t旧字段是local Ju+Lt，不单独当完整delta。
C_S保存0也要与同一存储矩阵的较宽求值区分。

本轮交具体生产函数的因果证据和一个修复提案，或明确否决；
不先认定舍入/GETRS，不尝试第二PC，不改输入、积分、精度、分母/门限，
不加恢复次数，不以局部闭合启动全域/200q/FGMRES。
复用现有saved服务及hash绑定；不重跑A1/A2、carrier、全模式或旧184项审核。
普通接口bug定向修复后只读既存结果继续，不新造V13框架。

当前V12数值/总截止为2026-10-24T04:52:47Z/05:12:47Z；
接收/冻结/启动读取真实余额，不抄旧快照、不刷新T0。
已过期时新6h窗需一次明确批准，review不自动授权新窗。
原主机/cap/reserve/ABI/线程/swap0和证据边界保持；新增小证据目标≤16MiB。
更新response_v13及原账/索引，只推同分支，不合并master，不报完整场通过。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/a6cde586698dc44d15b365ac8edd711768a229dd/docs/task41extra_phi90_p50x50_g17x20/response_v12.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/a6cde586698dc44d15b365ac8edd711768a229dd/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v12_saved_array_checker_closeout_20261024.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/a6cde586698dc44d15b365ac8edd711768a229dd/docs/task41extra_phi90_p50x50_g17x20/outcomes/v12_closeout/attempt03_candidate_replay_report.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/a6cde586698dc44d15b365ac8edd711768a229dd/docs/task41extra_phi90_p50x50_g17x20/outcomes/v12_closeout/attempt06_saved_array_check.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/a6cde586698dc44d15b365ac8edd711768a229dd/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/196aedecbef5d129588c629fc091682d7a2900f4/src/runners/task41_p0_v4_volume_only_audit.py#L4530-L4865
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/a6cde586698dc44d15b365ac8edd711768a229dd/src/solvers/hcurl_assembly_time_condensation.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/a6cde586698dc44d15b365ac8edd711768a229dd/src/solvers/p6_cell_condensed_action.py
