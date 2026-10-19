# Task41extra Review V4：修复保存 checker 的只读 pivots 风险，以现有向量关闭完整作用差异

## 0. 决定与快照

**保留 V3 的 carrier、两列恢复及完整作用的原始证据；完整 action 仍不合格。下一步先修保存数据 checker，再对 141 个已保存数组做误差分解。不得重新生成 carrier，不重跑已通过恢复，不为诊断重复约66分钟端口遍历。只有定位、修复和相应资格闭合后，才继续200q/完整参考/FGMRES。**

| 项目 | 冻结身份与范围 |
|---|---|
| 仓库 / 唯一分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 结果 base / 审阅时 HEAD | `f57b987ae62d50adeb0fa18295a296402dbf7acf` |
| 科学源码 / attempt | `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` / `20261019T053402.514018Z` |
| 当前权威 | task.md、Review V3及本轮用户指令；目录列表未见独立补充任务书 |
| 当前 blocker | 保存checker崩溃及状态错配；两列P6/native一致性超原门，根因未定 |
| 本次允许修改 | 保存审核、状态绑定、由诊断证明必要的局部作用/RHS准确性修复与窄接续；不换PC、不改几何/网格/模式 |
| 角色 | ChatGPT只提交本review；Codex实现、定向验证、获准计算与response_v4；不改master或其他任务 |

沿用50×50 nm周期、17×20×120 nm居中Si主体、方位90°/掠角1°/S、0.7 nm、p6、10×200×14、64,120模式和200q。13.5 nm A1/A2继续有效；57个空端口q仍保留FE。最终原A6、物理、网格/mode精度、整机十进制2 TB和必要完整冷流程48h目标不变。

本次核对根规则、repository_work_principles、任务目录、response/compact/源码；当前task.md blob仍为`5b669c109006fa91fdeebba2a81d97ba17b640b0`。本地上传的完整Review V3与远端blob `e4b497b2fd5892caef96be7a82a7bd71a74c6485`一致，已读取。没有登录工作站或重算141个用户数组。另在Chat容器运行了一个独立2×2 SciPy只读pivot复现，范围见§2；不是项目测试或工作站验证。

## 1. V3 资格与负结果分别保留

| 指标 | 第一列 / top16030 | 第二列 / bottom48090 |
|---|---:|---:|
| 三次同LU后forward | 8.452404647964512e-14 | 8.462099738746788e-14 |
| 最终native体积残差相对值 | 5.198444248297799e-16 | 5.177707803722003e-16 |
| 原恢复门 / 修正上限 | 1e-11 / 3次 | 1e-11 / 3次 |
| 完整P6/native相对差，原门1e-11 | 3.042118678294192e-10 | 6.391893878204816e-10 |
| 保存向量独立重算的绝对差 | 6.770178089430204e-7 | 1.4225036541037535e-6 |
| 原比较分母约值 | 2225.4812534876287 | 2225.4807123031883 |
| 同分母允许绝对差，derived | 2.225481253487629e-8 | 2.225480712303188e-8 |

恢复见证的worker数值门已过，后续完整checker仍INCONCLUSIVE。完整action两列均FAIL；D映射误差0不能替代B/H、体积、凝聚RHS和状态一致性检查。原失败分类不改写，不能因checker修复就把原作用结果改成PASS。[R1] [R2]

141个NPY总计9,379,882,344 B已由执行端逐文件回读/hash核对。主manifest SHA为`f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465`，hash-index文件SHA为`332b9e5ed553916808cceccd92542b5086cbdbeaaa298d42d95d18916bb7ade3`。完整数组位于原run目录，不在Git。

workflow父段13,102.74539181916 s；端口作用子段3,961.9574313424528 s。tree RSS峰14,523,883,520 B、task cgroup峰23,537,336,320 B、task swap0、后代清场；父子不相加，宿主swapin/out177/0页不归因给任务。原始磁盘16 GiB准入与旧失败费用保留。无q/factor/完整参考/FGMRES/场/A6/official R/T/A资格。[R2] [R3]

## 2. checker：先修一处有直接复现的危险调用，再修两处确定的审核逻辑

### 2.1 只读 mmap pivots 被直接传入 lu_solve

现有路径是 `_task41_npy_artifact(..., mmap_mode="r")` → `np.asarray(...)` → `lu_pivots.astype(np.int32, copy=False)` → `scipy.linalg.lu_solve`。保存的pivots本来就是int32，后两步不保证复制，仍可能指向只读映射。[C1] [R3]

SciPy v1.17.0官方GETRS包装源码在调用前对pivots逐项加1，调用后减1，以转换C/Fortran索引；这会短暂写入pivot缓冲。`overwrite_b=False`只约束RHS，不保护pivots。SciPy接口规定pivot是0-based，不能因此手动永久加1。[S1] [S2]

本Chat容器（SciPy1.17.0、Python3.13）用独立2×2 complex128矩阵实测：

| 输入pivot所有权 | 子进程结果 | 范围 |
|---|---|---|
| NPY以r方式mmap，asarray/astype(copy=False) | returncode=-11，栈落在SciPy `_lu_solve` / GETRS调用 | 独立小复现，不是工作站原崩溃栈 |
| 同pivot显式复制为可写int32数组 | returncode=0，LU解单位阵误差2.498001805406602e-16 | 仅改变内存所有权，不改变LU/数值门 |

这是源码明确存在且已在独立环境复现的checker缺陷，与原信号高度吻合；工作站具体崩溃点仍须一次最小确认，不能提前冒称已拿到其原生栈。PETSc打印SEGV来自信号处理器，不证明崩溃一定发生在PETSc矩阵运算中。[S3]

**窄修：**在本函数和直接相关的saved-LU读取调用中，先验证shape/dtype/finite、pivot合法范围与生产者索引约定，再使用 `np.array(saved_pivots, dtype=np.int32, order="C", copy=True)`，确认OWNDATA/WRITEABLE；不对旧mmap设写权限、不用r+、不改旧文件。450项pivot只需1800 B数值副本。LU/RHS必要时仅复制当前小class块，不能把9.38 GB证据整体复制为常驻。

先在正确工作站native环境用同类2×2输入验证修复调用，然后对第一份真实小class调用前后落盘marker（array hash、flags、shape/strides、后端路径）。旧只读崩溃复现只在受监督子进程且确有必要时做一次，禁止让它杀掉整个审核进程。若复制后仍崩溃，用faulthandler/可用原生回溯定位该小调用；不盲目再跑三次完整checker、不重装ABI栈。[S4]

### 2.2 raw局部证据是初始态，不能与最后修正态比较

worker先对初始`recovered`生成`raw_cell_diagnostic`，再执行三次修正。checker却把raw `recovered_interior`与循环结束后的`final_storage`比较，并用final场构造对应trace。应绑定到`initial_storage`、`initial_action`、`initial_residual`，与原raw记录同一时点；最终态单独按其step=3文件核验。[C2] [C3]

这是一处确定的状态契约错误，但它本身不是已证明的SIGSEGV根因，也不是生产full-action数值差异的根因。修正读取者；旧raw数组不改名、不覆盖，不要求重生成局部证据。

### 2.3 FAIL的保存结果也必须真正重算并生成完整报告

当前checker在joint状态不为PASS时先抛异常，尚未读取p6/reduced RHS重算差异；顶层又将完整action未过混入整个恢复审核。这不适合诊断已有失败。[C1]

本轮提供现有checker的严格saved-audit路径：先验证身份/hash并读取现有数组，无论原status为PASS/FAIL都重算可用指标；分列`audit_completed`、`data_integrity`、`recovery_passed`、`joint_action_passed`、`official_result`。运行完整且重现FAIL，应有完整报告且数值状态仍FAIL/非零业务退出；不能写成official checker PASS，也不能把已知数学FAIL再次包装为INCONCLUSIVE。只有缺失数据、崩溃或尚未完成的核验才保持INCONCLUSIVE。

NumPy指标在小class SciPy调用前持久化；每列/每小class结束及时更新报告。先验证CSR indptr起点/单调/末端、indices范围、active/interior映射范围及pivot范围，再进入SciPy；不能指望C/Fortran层抛Python异常。正确activation/JIT使用正式run的配置，不再调用WSL activation；保存旧三次错误和真实消费命令。读取者源码与原run源码分列，不修改生产者身份。

## 3. 用现有数组把完整差异分解，保持原分母

总行5,752,120＝trace 5,688,000＋port 64,120；完整FE storage为18,501,024行。以manifest和数组实际shape核验，不只相信这些常数。[R2] [R3]

对每列保存 `d = p6_result - reduced_rhs`，原分母保持 `max(norm(p6_result), norm(reduced_rhs), tiny)`。先分trace/port，报告各块的绝对范数、在同一全量分母下的贡献、最大行和误差平方和；不得把分母换成约1e9的未凝聚RHS让它过门。

**无需任何新FE或全模式作用即可完成：**

1. 读回两份joint大数组、port RHS、known、各次native action/residual/恢复及active/slave表；重现两列原总误差与各块误差。按平方和核验总量，所有原始hash保持。
2. 对port块分别比较p6_port、reduced_rhs_port和保存port_rhs。Bi/Di精确零证书、固定trace以及现有D映射结果只提供可验证预期，不代替这三个数组的实际对照。
3. 用保存两个B帧与原alpha=0.7−0.4i构造同一B·alpha及其active编号，验证原`native_rhs = native_volume_rhs + B·alpha`。不能再次加B、再次做MPC回拉或改变D普通转置/负号/H。
4. 建立状态表：known、初始恢复、step1/2/3、对应RHS/action/residual各指向哪个文件。检查最终trace/slave不变，raw局部与初始态一致。worker当前源码中，修正返回局部变量`recovered`，joint阶段仍使用原`sources/full_fields/native_rhs`，没有显式把修正场写回这三者；实际hash与内存所有权也要核对，不能先认定joint误用了step3。[C3] [C4]
5. 从native_rhs的active行和已保存reduced_rhs反推出当前总凝聚修正项，列出各相减项的范数和所需精度。若差异集中在trace，再按saved active-original映射定位到实际行；现有3类局部包只能解释其覆盖，不冒充全域证明。

由现有标量可推得native体积RHS范数/最终比较分母约为3.02134e5、6.36195e5。它是**尺度比，不是条件数或舍入根因证明**；确实提示需要量出相减和局部消元误差。把最终差除以原始大RHS得到约1e-15也不能替代原1e-11门。

## 4. 区分恢复修正、凝聚RHS和Schur作用：使用可证伪的恒等式

设单元原始块为K=Vii、G=Vit、J=Vti、L=Vtt，E为local trace对全局active的展开，T=-J K^{-1}。当前已证Bi=Di=0时：

```math
S_c=L_c+T_cG_c,\qquad
s_t=\sum_c E_c^H S_c E_c t+B_t\alpha,\qquad
g_t=b_t+\sum_c E_c^H T_c b_{i,c}.
```

`recover_storage/refine_internal_storage_with_native_volume_residual`改变恢复内部场；`reduce_rhs`仍使用预存`trace_from_interior @ b_i`，P6作用仍使用预存Schur。这三个环节不是同一个计算，恢复修正通过不会自动修复另外两者。[C5]

对任意同trace/alpha的已保存恢复态u^(j)，用相同时点原生残差定义 r_i、r_t。当前零内部端口情况下，精确分块代数应满足：

```math
r_i^{(j)}=b_i-Ku_i^{(j)}-GE t,\qquad
r_t^{(j)}=b_t-\sum_c E_c^H(J_cu_{i,c}^{(j)}+L_cE_ct)-B_t\alpha,
\qquad (s_t-g_t)+r_t^{(j)}+\sum_c E_c^H T_c r_{i,c}^{(j)}=0.
```

这是用于归因的恒等式，非替代原验收门。先比较j=0和j=3，再需要时补中间态。检查该恒等式的缺陷能否解释保存d_t及其变化，区分native/local不同、T/S/R缓存不一致、重复约束、制造RHS/累加损失和状态接错。

现有raw包仅明确保存少量class的Vii/Vit/LU和选中cell映射，**不能据此声称已有全域J/L/T/S或全部cell展开**。尤其J不应未经验证就取G转置/共轭转置，T不能从错误对象倒推后自证。先在原artifact依赖中找现成对象；缺失时写清文件/块/用途及最低成本，才按§5补算。

同LU不增加到第4次，不修改已知输入/原RHS、不缩放门限、不用known误差或`new_rhs = old_p6_result`消除缺陷。若只补精度，先对保存小class原同一RHS比较标准与有界高精度累加，并保留原生/局部算子检查；诊断高精度不擅自改变正式complex128。若原双精度RHS量化成为可证下界，报告证据与门仍未过，不自行换测试或放行。

## 5. 最少补算与不重复端口扫描的修复资格

**首选完全保存数据审核。** checker修复和上述数组分解不需要carrier，也不需要任何FE、q因子或新恢复见证。

若准确归因确需缺失矩阵，允许一次有明细的volume-only提取：使用本场相同网格/材料/积分/方向/ABI，复用已有体积/局部凝聚内核，导出必要class的原J/L、实际T/S/R及所需cell展开。先做主导行相关class，只有全量闭合需要时才扩展到全部实际class；相同class共享，边读边归并，不保存每cell一份稠密矩阵。不得调用会先构建surface/global carrier的高层入口。核对fresh布局与保存active/slave/局部原矩阵的身份，不推定重建编号相同。

由保存vectors和必要体积数据重算**原**reduce_rhs/volume action，先重现旧差异，再应用已定位的最小修复。原实现回放不能闭合时，不跳过身份问题去调参数。

端口不变且已保存分块检查通过时，新联合验收可合法复用旧port输出，并仅用旧两个B帧重算非零B·alpha：新trace输出来自修复后的真实volume核心＋同一B·alpha，新reduced RHS来自修复后的真实reduce_rhs＋保存port_rhs，保持同一两列输入、原分母和1e-11门。无需重做64,120模式遍历。明确标为“未改端口证据继承＋受影响体积/RHS重新资格”，不是新的全模式再积分。

若端口接口、H或映射被改动，此继承不自动成立。必须准确说明哪份端口证据失效和最小补充范围；本轮不自动授权再跑整轮66分钟扫描。不能只让一小块PASS就授予全局作用资格，也不能用保存d直接修补输出。数学核心修复同时接入生产调用与checker，不能只修验收值。

P0/P1完成的负审核可以直接给出定位，不逐bug停审。只有两列完整action按原门重新资格、保存checker能完整独立复核后，才解锁现有target→200q CSR/native→准确因子驻留→完整参考→原尺寸pilot。真实求解所必需的新matvec不属于“为诊断重复旧遍历”，逐次计时；不能用端口测试时间或q0×200替代实际PC/冷流程账。

## 6. 窗口、资源及明确停止条件

V3结果已登记新的24h窗口，不能错误沿用已结束的V2截止：

| 合同 | 本轮接续保持 |
|---|---|
| V3 T0 | `2026-10-19T05:23:07.094241922Z` |
| 数值截止 | `2026-10-20T05:03:07.094241922Z`，新加坡10月20日13:03:07 |
| 总截止 | `2026-10-20T05:23:07.094241922Z`，新加坡13:23:07 |
| window SHA | `68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38` |
| 原生产contract SHA | `9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c` |
| 主机/目录 | 沿用`fenics-ws:/home/fenics/Projects/laptop_share`，现有Codex项目/对话不变 |
| cap / host reserve / task reserve | 1,649,267,441,664 B / 68,719,476,736 B / 0 B |
| 原始证据配额 / free-space floor | 保持已批准16 GiB / 2 GiB，新增文件按真实现有累计准入；不自动提配额 |
| ABI/资源 | complex128/int32、MPI1/math1、原exact MUMPS、任务swap0、原host/ancestor动态准入；PSS未采样保持null |

时间工具核对时为2026-10-19 20:02:16新加坡时间，V3尚未截止；这只是审阅快照，不能当运行余额。接收、冻结和启动时从原合同与实际UTC/monotonic/累计账读取更紧余额，不能沿用旧72,641秒，更不能刷新T0。按原准入在该窗口内执行本review的窄范围保存审核、必要最小补算与条件接续，不另等每个普通bug审批；若已到数值截止不启动heavy，总截止后不得复活旧窗，需另报精确断点及新窗申请。

新consumer contract/source与旧donor source/window/141文件身份分列，旧文件只读，新报告输出到新consumer目录。通过现有Task41 prepare/service/required-checker监督链，不裸跑长worker；saved-audit模式不以旧`full_action.status=PASS`作为读取前提，不掉回完整求解入口。受监督父进程保存子进程SEGV/abort及已完成产品，不能因没有终态footer就丢掉已完成审核。用户未授权修改系统库、迁移机器、升cap或关闭数值门。

## 7. 实施、测试与交付

只做三组定向验证：只读mmap pivot到GETRS的最小安全边界；初始raw与step3不同但各自正确的状态回归；完整FAIL数据仍可输出复算报告、保留原分母且不会启动FE/端口扫描的真实saved-audit路由。反例包括坏hash/越界pivot或CSR、非有限、故意端口/约束错误；拒绝发生在不安全native调用前。修复后冻结源码再执行，不默认全仓pytest、不增加新PC/缓存项目或目录重构。

交`response_v4.md`及现有outcomes/run_index/summary/test_summary/两级总账增量，先回答：checker是否完成且崩溃点如何验证；d_t/d_p各是多少；哪条状态/数值项解释了原差异；实际修改何处；两列原门是否关闭；完整求解实际推进到哪里。至少保存按原分母的误差分解、checker报告、精确依赖/hash、新旧身份、补算明细与作用比较。父/子计时不双计，已记录旧运行和未知冷准备成本不删除。一个任务分支，主控集中提交/push，不合并master。

## 8. 可直接发给 Codex

```text
继续Task41extra，完整读取review_report_v4.md。结果base为
f57b987ae62d50adeb0fa18295a296402dbf7acf，科学source为
afbe91e5947ed18fb74d7105097e129c1b8b4cc7，attempt为20261019T053402.514018Z。

本轮先消费141个现成NPY，不重建carrier、不重跑已通过恢复或66分钟端口遍历。
先修保存checker：load_array返回只读mmap，pivots.astype(int32,copy=False)仍只读；
SciPy GETRS包装可能原位转换pivot。Chat在SciPy1.17.0的2×2独立子进程已复现
只读pivot=-11、显式copy后通过。工作站先做同类小验证，原真实small-class调用
前后加marker；pivots明确复制为可写owned int32，验证范围，不改旧文件/r+或索引。
不能把本地复现冒称已取得工作站崩溃栈；若仍崩溃只定位该小调用，不再盲重跑全checker。

同时修两个已确认的审核逻辑：raw局部包对应初始恢复，应与initial_storage/action/
residual比较，不能与step3 final_storage比较；joint FAIL也要读数组并重算、写完整
报告，不按旧status提前退出。报告分开审核完成、恢复PASS、full-action FAIL和official。
正确native activation/JIT沿原运行，消费者身份与旧生产身份分开。

先离线按原分母max(norm(p6),norm(reduced_rhs),tiny)重算两列d并分trace/port；
检查p6_port/reduced_port/port_rhs，known和step0..3对应关系，保存B·alpha与原RHS，
active/slave和原模式身份。原数值差仍为FAIL，不用1e9原生RHS当新分母放行。
恢复修正不会自动改变reduce_rhs的预存T或Schur S，按review§4残差凝聚恒等式
区分状态/算子/相减/局部求解问题，不预设根因，不加第4次精化。

现有raw只有少量Vii/Vit/LU和局部映射，不假称已有全域Vti/Vtt/T/S/R。
确缺时列最小明细，允许一次同物理volume-only提取必要class/映射；不经surface
高层前缀、不做全carrier扫描或q/global factor。先重现旧volume/reduce结果，定位后
修最小生产核心。端口未改且保存分块检查通过，可继承旧port输出，读两个B帧，
只重新资格受影响volume/RHS并组回同一两列完整比较，原1e-11门不变。
不从保存差向量硬补结果、不更换输入/RHS或oracle，不只修测试。

只有checker完整复核与两列action资格都闭合后，继续现有target、200q（57个无端口
仍有FE）、ALL_Q_RESIDENT两RHS、完整参考及条件原尺寸pilot。新求解必要算子调用
照常计费，不以旧q0×200或测试时间冒充全场。

沿原V3窗口：T0=2026-10-19T05:23:07.094241922Z，数值截止
2026-10-20T05:03:07.094241922Z，总截止05:23:07.094241922Z。
读实际余额，不刷新T0，不套用旧V2已过期窗口。主机、1.5TiB cap、64GiB host
reserve、task reserve0、16GiB证据配额/2GiB磁盘余量、MPI1/math1、原ABI和swap0不变。
现有prepare/service接窄saved-audit及条件continuation，不复制一套V4框架。
只跑上述三个边界的相关回归，不全仓测试。普通bug同窗修复继续，真实资格/资源/
截止门停止受影响路径并保存成果。response_v4先报根因证据和新数值能力，再列测试；
保留旧失败/费用/UNKNOWN，只推本分支，不合并master。
```

## 固定来源

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/docs/task41extra_phi90_p50x50_g17x20/response_v3.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v3_full_action_failure_20261019.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v3_saved_vector_hash_index_20261019.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v3_offline_checker_invocation_failures.json
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/src/runners/task41_p0_checker.py#L1281-L1850
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/src/runners/task40_v10_worker.py#L350-L565
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/src/runners/task40_v10_worker.py#L1068-L1400
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/src/runners/task40_v10_worker.py#L1400-L1600
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/f57b987ae62d50adeb0fa18295a296402dbf7acf/src/solvers/p6_cell_condensed_action.py#L3023-L3390
[S1]: https://github.com/scipy/scipy/blob/v1.17.0/scipy/linalg/flapack_gen.pyf.src
[S2]: https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.lu_solve.html
[S3]: https://petsc.org/release/manualpages/Sys/PetscSignalHandlerDefault/
[S4]: https://docs.python.org/3/library/faulthandler.html
