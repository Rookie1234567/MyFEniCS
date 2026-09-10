# Task39extra Review V11：局部MUMPS分配与生命周期修正，继续完成V10数值验证

## 0. 身份、结论与权限

```text
repository         = Rookie1234567/MyFEniCS
branch             = task39extra
review_date        = 2026-09-10
reviewed_HEAD      = a2ef03f90137e172ef78fd73649dc7455117cba0
original_task_base = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_materials = review_report_v10.md / response_v11.md
execution          = N0 -> N1(memory calibration) -> N2(complete M1)
                     -> N3(V10 M2) -> conditional N4(V10 M3) -> N5(closeout)
new_profile        = physical_macro_dd4_v11
memory_policy      = SYMBOLIC_SIZED_LOCAL_MUMPS_V11
response_required  = response_v12.md
ordinary_default   = unchanged
master_merge       = NOT_APPROVED
```

**本轮消除的blocker：42个局部物理逆尚未构建完成，多实例MUMPS分配与局部常驻预算不匹配，因而p4质量、框架和restart尚无新结果。先以同一矩阵验证更合适的工作空间分配，再连续完成V10已经定义的数值试验；不是再换PC，也不是只修内存报表。**

接受V10的`PARTIAL_WITH_CONTROLLED_NEGATIVES`及其局部正证据，不改判为收敛失败或系统OOM。保留V5准确p4逆的原始/notch成功、V6–V9全部负结果。本轮只有一个内存实现策略，不恢复实体/recycling参数搜索。5 nm已由另一条线推进；本机只处理既有13.5 nm模型，不等待、不重复、不操作另一线的分支、目录、进程或预算。

用户授权在同一任务分支新增本review并继续。本文**只对新profile**覆盖V10停止后的重新执行许可、局部MUMPS工作配额及可核验的生命周期记账方式，并重新授权其未运行的M1–M3。2 GiB局部常驻预算、1 GiB临时预留、整机安全线、局部数学问题、四步I4和最终精度不放宽。旧profile行为不变；不重写旧task/review或旧负记录。最新目录盘点未见独立补充task或更深AGENTS；发现新的权威冲突时只停止受影响部分并报告。

最终目标仍为约2 TB整机内存内的0.7 nm、complex128、Nedelec H(curl)、双Floquet、Fourier-DtN、任意非可分三维周期单胞散射。本轮资源修正不改变直接分解的增长规律，也不证明该PC的波长鲁棒性。

## 1. 接受的证据及不能推出的结论

下表为V10第二次M1的已提交记录。B为字节，GB为十进制，GiB为二进制；不同口径不互作加速或内存节省百分比。

| 对象 | 记录 | 数据身份 / 解释 |
|---|---:|---|
| 正式源码 | b0df7457c0c4b33c66abda16862926da3426bb7d | clean-source launch；交付HEAD另列 |
| 已处理局部块 | block 0–7进入numeric；全体42块未完成 | measured partial；I4/B4均0次 |
| 保存的局部回代 | block 0–6共14次，最大相对残差2.00028e-15 | measured；不是整个p4精度 |
| native限制核查 | 两个代表块6次，最大8.24392e-16 | measured subset；不替代完整cached/native bridge |
| 当前块分解前累计策略量 | 1,982,365,908 B | 已含block 7矩阵和全部indices/support |
| block 7新增allocated策略量 | 261,000,000 B | 分解期间后端分配量加取整余量 |
| 累计策略量 / 上限 | 2,243,365,908 / 2,147,483,648 B | derived policy，超95,882,260 B |
| 同期process-tree RSS峰 | 1,107,648,512 B | measured simultaneous RSS；不是上述policy |
| 8块矩阵CSR载荷 | 107,655,760 B | derived storage |
| 8块estimated / allocated / used | 234 / 2090 / 212 MB | 后端字段加记录中的取整余量，均非factor-only RSS |
| 框架、restart、original/notch | not_run | 不能据此否定BAL_H、ONE_C或新DD |

来源：[Response V11](response_v11.md)、[V10中心结果](outcomes/physical_macro_inverse_v10.md)、[V10 compact](outcomes/records/physical_macro_inverse_v10.json)。第一次代表块选择失败保留为工程负结果；已有窄修不再重复。block 7回代未持久化、完整macro identity尚未闭合、完整准备/修复成本unknown等限制保留。

代码依据：`BoundedP1Factor`目前从512 MiB单实例预算扣除matrix budget后设置ICNTL(23)，macro又累计各实例reported allocation。**较大配额可能影响内部工作数组大小，这是待检验的实现假设，不把全部allocated/used差额预先认定为浪费、泄漏或单一根因。** 本轮须记录实际安装版本、控制值和行为。

## 2. 数学与数值身份保持不变

完整继承[Review V10](review_report_v10.md)第2–7节，除本review明确覆盖之处外不改门槛或分流。

| 范围 | 冻结内容 |
|---|---|
| 原始模型 | 13.5 nm、1度grazing、azimuth0、s；50×25 nm周期，z=-10到130 nm，原Si/air和损耗 |
| physical SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| ordered mode SHA | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| fine/coarse空间 | p6/h10、252 cells；p6独立164592，p4独立48960；存储行173802/53084 |
| 局部模型 | 原42组、全部p4独立坐标、每块总行不超过2600；完整支撑、Floquet和适用DtN限制 |
| 局部组合 | 输出端1/multiplicity加权；不加输入权重，不改分组/重叠/顺序 |
| 物理作用 | 原A6/b、native A4、相容传递、80模式与quadrature；保留实际C_U及S/p2 |
| 精度和算法 | complex128、局部准确LU；I4最多4次新B4、无复用池；H6及V10框架/重启选择规则不变 |
| 缺口 | V5冻结8个cell keys与实际材料实体，独立物理身份、因子和参考；不复用错误材料数据 |
| 环境 | 现有合格Linux ABI、MPI1、线程1；不升级DOLFINx/PETSc/MUMPS/SciPy |

局部仍为原物理主子矩阵及原全局纠错：

```math
D_i=R_iA_4R_i^H,\qquad
M_D=\sum_i R_i^H W_iD_i^{-1}R_i.
```

```math
B_4^{DD}=C_U+(I-C_UA_4)M_D(I-A_4C_U).
```

所有真实规模动作通过`python scripts/run_case.py input/path/to/case.dat`。新dat明确stage、profile、memory_policy、solver和预算并绑定新input SHA；physical SHA不因内存控制变化而伪造。补齐V10尚未实现的通用M2/M3/ONE_C/正式runner接线属于继续原授权，不得因为当前`outer_execution_enabled=false`仅完成builder便收口；也不得声称仅打开标志就已经实现这些阶段。

## 3. 唯一分配策略：每块依据symbolic需求给配额

### 3.1 先核对本机，不假定在线最新版即运行版本

N0记录实际加载的PETSc/MUMPS库、版本、整数宽度、complex128、库路径/包信息和可用的公开getter/setter。确认ICNTL(23)、INFOG16–22的本版本单位与阶段含义。保持原ordering、scaling、pivot阈值、refinement、ICNTL(14)、线程、in-core和full-rank设置；不把调整工作配额变成数值参数扫描。

优先为现有`BoundedP1Factor`增加显式策略参数，由新macro profile传入；默认调用及S/p2、V5等其他路径不变。扩展`_MumpsFactor`时只调用已核对的PETSc/MUMPS接口，不按猜测地址读写私有Fortran结构，不在进程内换ABI。unknown/unsupported必须显式报告。

### 3.2 固定配额公式，不从剩余512 MiB反推

MPI1、相同symbolic配置下，令E_i为INFOG16/17中较大值的向上取整字节估计（沿现有每字段加1个十进制MB规则）。两者应与MPI1语义一致；异常值或无法解释的差别先核查。令Q_i为本轮唯一请求配额：

```math
E_i=10^6\bigl(1+\max\{\mathrm{INFOG}(16),\mathrm{INFOG}(17)\}\bigr),
```

```math
Q_i=10^6\left\lceil\frac{\max\{32\,\mathrm{MiB},\ 2E_i+8\,\mathrm{MiB}\}}{10^6}\right\rceil.
```

在numeric前设置`ICNTL(23)=Q_i/1_000_000`，回读核对。系数2、8 MiB余量和32 MiB下限是一次固定工程策略，不是理论最优值；E_i为估计，不保证无额外填充。若本机版本的字段语义与上述公式不兼容，登记`MEMORY_POLICY_UNSUPPORTED`，不静默换字段或单位。

Q_i与该实例原matrix/转换/对象策略预算合计必须不超过512 MiB，并通过全局资源和第4节分阶段检查；超出则停止，不能裁低Q_i凑数或提高cap。若出现内存不足后端返回（如-9/-19，按本机手册解释），记录`LOCAL_WORKSPACE_LIMIT`并终止本候选，不自动扩大Q_i、ICNTL(14)、块大小或重跑不同参数。symbolic只做一次；不得为了较小估计而换ordering。

### 3.3 仅在实际支持时收缩分解工作数组

本机文档、头文件与加载库一致且接口可用时，固定使用`ICNTL(49)=1`，在numeric前设置：允许分解结束时收缩主要工作数组，同时尊重ICNTL(23)。这不是BLR近似压缩、不是删除因子，也不应改变所求局部方程。额外复制/重分配的峰值必须计入临时和全树预算，依据见第10节S1/S2。

不支持时明确记`COMPACTION_UNSUPPORTED`，只执行3.2的定额策略；**不因此自动取消后续数学验证，只要未收缩实现仍通过预算。** 支持但返回警告/未执行时保留警告和未收缩账，不改成`49=2`、不将`23=0`取消限制、不升级库。设置成功不等于实际释放成功。

ICNTL(49)只针对主要工作数组，并不自动释放所有辅助对象。没有版本相符的证据时，不把INFO(39)、INFOG(9/10)、factor entries或used字段当作完整的分解后常驻查询。

## 4. 内存账：实际减少分配，不用更小的字段绕过Gate

### 4.1 默认保守算法及允许的唯一抵扣

保持两本账：一份为named对象及后端分配的策略账，一份为同期process-tree/cgroup实测。RSS、PSS、VmSize、allocator保留区与后端字节分别报告；不相互代替。

**默认继续累计新运行的allocated保守量。若降低配额后这份账已在2 GiB内，直接进入后续验证，不强迫开发一个新的factor-only测量接口。** 这是优先路径。

只有本机版本的公开信息或最小、版本绑定的可审计分配观测，能够明确证明某实例在numeric后实际释放了特定工作数组字节时，才允许从其历史allocation envelope中抵扣这部分；原始allocated/used始终保留，列出抵扣的对象、字节、时点、证据和剩余辅助预留。不授权编译/替换求解库或通用malloc追踪工程。无法得到可靠证据时不抵扣，不猜常驻，也不因此反复诊断。

禁止用`min(allocated,used)`、单次RSS差、factor_nnz×16或`INFO(39)×16`代替完整常驻账。allocator未把释放的页立即退还OS时，不假称RSS已下降；保守地保留实际峰值与未解释的保留区。相同内存别名只计一次，但没有共享所有权证据不得任意去重。

### 4.2 分阶段预算和所有权

局部构建顺序执行；第j块的同时工作集模型为：

```math
M_{\mathrm{peak}}=\max_j\left(M_{\mathrm{base}}+M_{\mathrm{retained},<j}
+M_{\mathrm{matrix},j}+M_{\mathrm{numeric},j}+M_{\mathrm{temporary},j}\right).
```

这是生命周期表达式，不是已经测得的上界。已释放的workspace不永久累加；未释放的每个实例空间必须累加。每块numeric后、所有块首次回代周期后都重新检查局部常驻策略量不超过2 GiB；构建临时预算另为1 GiB，绝不能被解释为多给1 GiB长期库存。numeric前分别预审：现有常驻、当前矩阵、Q_i、非MUMPS临时量及整树余量；使用Q_i作为本次请求工作包络，不只检查较小的E_i。新运行仍保存与V10累计allocated同口径的shadow账，以解释差异。

保留必要的矩阵、因子和回代接口；优先释放一次性CSR提取副本、局部贡献/哈希临时数组和无用工作向量。**不要求先销毁仍被`BoundedP1Factor.matrix`借用的矩阵；未改清引用和模板前不得提前释放。** 单块异常和清场必须幂等；不得在block字典与局部变量中留下同一已销毁句柄并二次destroy。

回代结果和native witness在判定下一Gate之前落盘，使超预算的块也能保留已完成阶段；硬资源停止优先，未落盘仍标未取得。整个42块构建过程中记录local数目、矩阵/因子/索引/缓存所有权、实际RSS及后端返回，不把前8块线性外推当最终42块实测。

## 5. N0–N2：短校准后完成原M1，不逐项停审

### N0：预检、接口与原始证据核对

读取根/docs AGENTS、工作原则、当前task、V10及本review、Response V11和最新summary。核对canonical worktree、branch/HEAD/upstream/clean、环境ABI、当前材料、mesh/map/mode、可见RAM/cgroup、MemAvailable、swap、disk和父watchdog。相同blob的未变旧检查不重跑。

确认V10 source与交付HEAD分开，旧push受阻文字是历史状态：本review已从远端读取a2ef03f90137e172ef78fd73649dc7455117cba0，新response须报告真实当前同步状态，不再要求用户为已存在的push重复配凭据。旧未知成本不填零、不用reserved追认。

### N1：最多三个代表块，一次旧/新分配对照

沿V10修正后的实际DtN/材料代表选择，最多三个distinct块；允许用最大实际行数块补足代表性，按canonical key确定并在运行前冻结。矩阵CSR结构/值、支撑、映射、材料和mode哈希必须相同。没有完整旧block packet时只重建这些局部矩阵，不建立p4/fine全局参考。

每个代表块至多一次旧策略基线和一次新策略，共最多6次numeric；基线可复用确有相同指标的旧raw。两种因子顺序创建/释放，不同时常驻；只保存少量比较向量。除3.2/3.3外的参数完全一致；无目标参数网格。N1计算不超过900秒，失败按确切阶段收口，不重新开一天内存研究。

每个保留因子至多16次回代：覆盖原两个D_i w探针、一个独立固定种子复数RHS，以及重复调用检查。分别记录冷/热回代时间、最大RSS、native/局部残差与旧/新解差；不根据参考答案修改因子。两策略局部相对残差均不超过1e-10，同输入解差不超过1e-10；近零解另报绝对差，误差大时标数值敏感/不等价，不能只凭小残差放行。

记录装配、symbolic、numeric（含compaction）、重复solve、destroy各时点；保存请求/回读ICNTL、INFO/INFOG、warning和整数/数值factor载荷。不得把某个退出内存字段称为所有阶段精确常驻。校准之后不要求最低节省百分比；真正准入是实现等价、资源账合法且完整库存有可审计的分阶段计划。

### N2：完成全部42块、实际p4作用与框架对照

校准合法即连续构建42块，复用同进程、同数值与内存策略身份的已验证对象；旧大配额因子不得混入新库存。每块保留V10的两个回代检查，代表native witness不重复无关旧测试。首轮完整回代后检查是否出现新分配或缓慢增长；不能只看numeric结束瞬间。

完成尚未执行的`build_w_transfer`、recursive map verification、cached/native A4 bridge、C_U及完整DD作用。用于notch的通用材料生成路径必须可用，不硬搬original专用packet。实现问题明确修复、提交新SHA后只重测受影响部分，数学失败不能当bug重试。

随后严格执行V10第4.1–4.3节：最多六个已有g1/g2检查p4真实残差和匹配场误差；最多三个已有q比较共享前缀的BAL_H/ONE_C，共至多12次新I4。参考只在评价端，缺匹配参考时标`REFERENCE_UNAVAILABLE`并继续独立合法检查，不重建全局LU；归一化和Ae关系核对。

框架选择阈值仍用V10第4.3节，不因内存修正重新发明准入。不得要求裸PC单次残差下降或每个I4达到1e-4才进入真实试跑。四步I4、25秒安全返回请求/30秒费用线不变。连续两次非零输入无合法修正或持续内部费用越线按原规则停止。

## 6. N3–N4：继续V10框架/restart/真实三维检验

**内存工作通过不是本批完成。** 若无正确性/资源/费用阻断，必须连续执行下面的已授权数值流程；不得仅提交`MUMPS memory PASS`后再等下一份review。

| 阶段 | 继承规则 | 数量/终点 |
|---|---|---|
| N3，对应V10 M2 | 选定同一框架与DD4；零外层初值、空状态；FGMRES32与64各最多64步；前32步核对一致性 | 最多两个真实original probe，各solve2400秒/workflow3600秒 |
| restart选择 | 两者到64时，R64/R32残差比不高于0.50、时间比不高于1.25且资源合格才选64，否则32 | 不扫描其他restart；未到节点不插值，限制按V10第5节 |
| N4 original，对应V10 M3 | 冻结一次框架/restart/I4设置，从零初值；每8步真实残差、每32步checkpoint | 最多一次fresh original；1800秒rho>0.10停止，5400秒rho>1e-3停止；否则solve10800秒/workflow14400秒、max2048 |
| N4 notch | 第一个完整original成功后，同配置、相同块定义、自己的材料/因子/参考、零初值 | 最多一次；不为缺口调参 |

两probe都在2400秒内未达48步，按V10的`WHOLE_PC_COST_NOT_VIABLE`停止，不再追加fresh长跑。某probe已达到完整目标时直接补齐合格输出并进入notch，省去其余重复运行。其他情况的缺参考、未到64与选择规则完整继承V10，不根据结果临时放宽。

工件只复用合法的算子/矩阵构建数据；若没有已资格化的因子序列化路径，新的独立运行应重新构建并记入fresh费用，不开发另一套持久化后端，也不把重建成本写成零。两个restart probe之间不共享解、Krylov基或历史池。所有新数值接线必须在真实运行前提交clean SHA，继续使用统一runner/checker。

## 7. 精度与资源Gate

| Gate | 门槛 / 解释 |
|---|---|
| 局部限制、回代 | V10局部/native尺度1e-10；所有42块与代表作用完整记录 |
| cached/native A4 | 沿V10相对1e-11；输入、约束和相位一致 |
| 框架记账 | BAL的eps1-eps2、ONE的eps1-g2沿操作尺度1e-8闭合；另报实际不平衡大小 |
| 原始p6真实残差 | norm(b-A6x)/norm(b)不超过1e-6；不是辅助残差 |
| 匹配场 | L2/scaled-curl相对差不超过1e-4；selected复E/H、近场同坐标，不拟合整体相位 |
| 功率与吸收 | R/T/A/A_volume对各自同结构参考绝对差不超过1e-5；独立守恒/体吸收闭合1e-5 |
| 全部80模式 | 复幅值向量相对差不超过1e-4；逐通道功率最大绝对差1e-6 |
| 局部库存 | 2 GiB常驻策略上限，构建临时预留1 GiB；二者均进入整树安全检查，不冒称测得RSS |
| S/p2 | 仍最多8192总行、matrix/factor/转换/workspace预审512 MiB；其默认分配策略本轮不改 |
| 整机 | reserve=max(4 GiB,15% effective_total)；launch cap不高于min(12,000,000,000 B,effective_available-reserve)，按V10当前可见RAM/cgroup取值 |
| 运行安全 | 一次一个heavy，全过程process-tree/cgroup、余量、job/global swap、磁盘和全部后代；硬安全优先 |

每块numeric前保留临时余量，不能因为ICNTL(23)小就取消父watchdog。未知MUMPS开销由保守账和系统监测共同约束；新调配不是运行内存必然够用的保证。swap/OOM、policy stop、数值不合格与证据缺口分别分类。

未过p6真实残差只允许diagnostic场误差，不发布official R/T/A。成功后保存最小recovery packet，释放KSP/PC/因子和无用矩阵，记录RSS再恢复输出；所有恢复也在同一安全范围。先前V5参考448页系统换出归因缺口保留。

## 8. 费用、实现范围与停止条件

新批次从N0开始独立记账，不把V10未完整记录的3738秒nominal余量拿来当新授权，也不重跑历史计算补账。父流程与子阶段是包含关系，不重复计费；prepared reserve、实测、unknown分别报告。记录实现/修复/测试与运行可获得的真实时间，缺失即unknown，不自动卡住无关数学结论。

| 新批次范围 | 上限（投入边界，非预计完成时间） |
|---|---|
| N0–N2全部准备/测试/校准/构建/有限控制 | 7200秒；含N1校准900秒、N2局部构建3600秒、有限数值控制1200秒 |
| N3两个probe | 各workflow3600秒，solve2400秒 |
| N4 original与条件notch | 各workflow14400秒，solve10800秒 |
| 新批次累计 | 43200秒；任一更小的阶段/安全线先到先停 |

只允许相同MUMPS后端的局部工作配额、条件compaction、明确的临时对象释放、阶段记账及V10剩余接线。禁止新PC、ILU/BLR、mixed precision、OOC、外部存储换页、后端替换、参数搜索、改变42块/2600行、提高2 GiB、增加I4步数、无限restart或新增5 nm/0.7 nm计算。不得为节省库存每次PC重新分解42块；本轮保留一次setup、多RHS回代。

失败分流是固定的：接口不支持23或同ABI无法核验则`MEMORY_POLICY_UNSUPPORTED`；49不支持本身仅是可选功能缺失。局部矩阵/解差异常为`LOCAL_NUMERICAL_EQUIVALENCE_FAIL`；请求配额不足为`LOCAL_WORKSPACE_LIMIT`；完整常驻仍超预算为`LOCAL_INVENTORY_RESOURCE_BLOCKED`。不因这些情况重开多组配额或另一后端。每个失败保留原始状态和未运行项，退出后集中交N5。

## 9. N5交付、测试与commit计划

提交`response_v12.md`，中心建议为`outcomes/macro_memory_lifecycle_v11.md`与对应轻量compact。更新summary、run_index、test_summary、development_progress/model_registry、handoff及按依赖分组的selective manifest。旧V10 docs/response中的历史push/成本状态不抹除，在最新总账明确时间和当前状态即可。不要在summary中继续堆叠相互矛盾的“当前”授权。

新增focused tests覆盖：新策略opt-in及旧默认不变、十进制MB换算/向上取整、同MPI字段校验、硬cap与warning、不支持49的回退、重复回代、共享对象不重复计账、失败前证据、无double-destroy、cached/native与ONE/BAL接口。最后改动后重跑相关测试、Ruff/compileall或py_compile及Markdown合同检查，保存raw stdout/stderr和SHA；整理摘录另标，不称CI或全库通过。

每个block记录矩阵身份、symbolic估计、Q_i请求/回读、实际控制值、allocated/used原字段与单位、可核验释放字节、常驻保守账、numeric/solve时间、局部/native残差和阶段RSS；每个完整模型给同步数与同时间节点比较、I4/B4/local/S/A4/A6次数、框架/restart选择依据、完整输出与资源。诊断正确性PASS不替代solver PASS。

标准provenance必须齐全：`input_original.dat`、`resolved_config.json`、`run_manifest.json`、`input_sha256.txt`、`physical_model_sha256.txt`、`source_sha.txt`、`run_summary.json`及ABI/MPI/线程、实际mesh/map/mode/矩阵/因子策略、artifact hash。旧ignored raw不删除、不上传大数组。

commit计划：显式内存策略与focused测试 -> clean-SHA N1校准证据 -> 补齐剩余通用接线并以clean SHA完成N2 -> 两个有界probe及条件original/notch -> compact/docs/response。正常阶段连续执行，不逐步停审；修好内存不能当最终交付。ChatGPT只新增review；Codex不改review、不amend、不强推、不合并master，不擅自merge/rebase另一活动分支。

最终按证据给出唯一优先下一步：若新策略已通过保守allocated预算，明确实际工程收益；若必须抵扣，逐项说明依据；若仍装不下，只关闭本实现而不宣称子域算法不收敛；若完成数学试验，分别评价p4质量、BAL/ONE反馈、restart损失与总成本。即便双模型通过，底层规模、MPI复制、DtN存储和0.7 nm鲁棒性仍另列。

## 10. 来源与适用范围

- [S1：MUMPS 5.9.1官方手册](https://mumps-solver.org/doc/userguide_5.9.1.pdf)：第5.12节工作空间，第5.24节ICNTL(49)，第7节统计，第8节warning。此在线版本不是本机版本或升级许可；Codex必须核对实际链接版本文档。[本轮只借用工作空间与统计语义，不引入新的数值求解算法。]
- [S2：PETSc MATSOLVERMUMPS接口](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)：MUMPS控制入口，在线文档不证明当前ABI具有所有接口。
- [V10执行合同](review_report_v10.md)、[V10结果](outcomes/physical_macro_inverse_v10.md)、[V10 compact](outcomes/records/physical_macro_inverse_v10.json)、[Response V11](response_v11.md)。
- 相关源码：`src/solvers/physical_macro_dd4.py`、`fullspace_bounded_mumps.py`、`fullspace_v17_p3_oracle.py`及已有macro runner。本review依据a2ef03f90137e172ef78fd73649dc7455117cba0只读核对，不声称重新执行了PDE。

**本轮不是用更宽松的账把失败改成通过，而是减少不必要的分配，保持相同局部物理问题和精度；预算满足后，让已经定义的完整三维方法真正得到检验。**
