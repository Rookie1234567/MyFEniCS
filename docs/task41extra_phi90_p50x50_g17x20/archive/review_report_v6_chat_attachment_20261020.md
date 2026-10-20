# Task41extra Review V6：保留 actual 几何，以共享参考表和 blocked Gram 降低张量生成成本

## 0. 决定、范围与快照

**接受 V5 的 exact-key 清点、8 个实测样本和受控拒绝结论。原 FFCx rank-2 逐键调用的约17.224天构建方案不予长跑；本轮只选择一个加速候选：`actual_qmetric_blocked_gram`。保持 `mesh_actual_exact` 坐标身份，复用原积分点上的参考表，每个单元仍计算与冻结 FFCx 路径一致的 actual 几何因子，然后用有界分块矩阵乘法生成完整局部张量。不是新PC，不恢复canonical共享，不改变native、原RHS、积分或门限。**

本报告的候选名是待实现的 opt-in evaluator 身份，不是已存在CLI或已通过数值资格。完整候选必须先通过局部对照和实际成本门，随后才构建全域并验收原两列。旧恢复/端口资格不重跑，改变后的局部数据仅做必要的受影响验证。

| 冻结项 | 值 |
|---|---|
| 仓库 / 唯一分支 | `Rookie1234567/MyFEniCS` / `task41extra_phi90_p50x50_g17x20` |
| 审阅结果 HEAD | `dcc2737a9166e6c9185223ac084f811d5068ad4b` |
| V5 scientific source | `179cf7369e6bc5894fa87af6b74cf5c73938b6d4` |
| 上一 review / V4结果 | `0560dbe95d9f568adc219fecd1ed835bbdfd65ea` / `f66857f2a6b0ebd0415165adce164dbc2f04cc04` |
| 模型 | 0.7 nm、50×50 nm周期、居中17×20×120 nm Si，方位90°/掠角1°/S、无缺口，p6、10×200×14 |
| 模式与q | 64,120模式、200q；57个无端口q仍保留FE |
| 本轮消除的blocker | actual局部张量生成成本过高，阻止全域作用/RHS资格；不是已进入的KSP收敛问题 |
| 权限与角色 | ChatGPT写review；Codex实现、定向验证及获准计算。仅本分支，不改master、Task40、Task39para或Hybrid |

已核对本轮response/compact/summary/run_index/test_summary、根与docs规则、任务书、上传的完整Review V5及相关源码。scientific source到结果HEAD只有一笔收口提交，修改文档和测试替身，没有再改生产数值源码。任务书的物理、原门和冷流程目标保持。没有登录工作站、重读其大数组或执行项目数值测试；本报告的测量来自远端证据，推导与建议分列。[R1][R2][R3][R4][R5]

## 1. V5的正确结论

| 项目 | 实测或派生值 | 本次裁决 |
|---|---:|---|
| exact-key清点 | raw/oriented各28,000；inventory 16,224,652 B | 接受真实库存，不把它当已构建28,000套缓存 |
| 8次原kernel | 合计419.1692760037258 s；平均52.39615950046573 s；51.93273649–52.97407951 s | kernel调用边界确实主导；其内部细分尚未测得 |
| 同8项LU/solve、Schur | 0.49611899768933654 s / 0.0661380747333169 s | 不是当前主要瓶颈；不靠增加精化或换LU提速 |
| 两actual单元 | 26762/26897坐标及K/G/J/L与V4保存块逐位一致 | 局部输入/积分重放通过，不代表全域修复 |
| 剩余构建 | 1,488,176.122617107 s，约17.224天 | 样本分项最大值外推，不是全域实测 |
| 全部剩余准入需求 | 1,490,279.122617107 s；当时余额712.8634632226167 s | CANDIDATE_NOT_ADMITTED，不是新数值FAIL或内存PASS |
| 最后service / 三次service父段合计 | 518.8423959072679 s / 622.82423196733 s | 不再叠加其worker或kernel子段；工程准备仍有UNKNOWN |
| tree RSS / task-cgroup峰值 | 6,674,780,160 B / 6,830,514,176 B | 仅前缀，两个口径不相加 |
| task swap / host增量 / 清场 | 0；本次host pswpin/out均0；后代为空 | PSS未采样；不外推整机历史swap |
| 全局作用 / 后续 | 旧两列仍3.042118678294192e-10、6.391893878204816e-10；原门1e-11 | 完整候选、200q、factor、FGMRES、场均未资格化 |

V5八样本为26762、26897、0、1、2、5、6、7505，按保存prefix核对，不凭旧聊天重建名单。样本matrix/LU是否落盘以实际artifact inventory为准：当前回应明确没有复制一套八样本数值大数组，不能把timing JSON当可复用LU。[R1][R2]

## 2. 为什么不能只打开现有快速开关

源码已经有两类可利用的积累，但均不能未经修改直接替代本次 actual kernel：[C1][C2]

| 现有实现 | 可以复用 | 不能直接沿用的内容 |
|---|---|---|
| `Task39ExtraP6RawTensorCandidate` | 原form积分分析、B/C参考表组织、blocked Gram及evaluator协议 | `_affine_jacobian`用顶点差构造一个常量J；每键重复tabulate；原tag/default约束须按B0真实form核对 |
| `AffineIsotropicMaxwellTensorFactory` | 共享参考积分数据的思路 | 使用自己的quadrature选择和widths常量metric；六个已积分Gram不能替代本次可能随积分点变化的actual几何求值 |
| actual装配分支 | exact-key/逐键释放、原LU/R/T/S、前缀准入 | 当前直接调用`_tabulate_raw_tensor_class`，没有把evaluator接入该分支；只在canonical分支设置evaluator不会生效 |

**本轮共享的是与物理单元位置无关的参考基函数/导数表，不是把不同actual单元的物理矩阵重新合并。**28,000个坐标身份继续分开，除非后续另有严格、独立的等价证明；本包不开展矩阵近似去重。

## 3. P0：把52秒拆到真实调用边界，但不单开长profiling项目

在实现候选前读取本场冻结的FFCx生成C/IR、实际compiled module和编译选项，记录完整form及kernel身份、default/tag覆盖、curl/mass各自实际积分点/权重/顺序/hash、坐标元素及FE布局。不能拿端口degree160当体积规则，也不能假定curl和mass必用同一规则。

检查52秒所含的原kernel调用次数、单次输出尺寸882×882、基函数对/积分点循环、几何因子计算位置及精确零表优化；生成C中已经静态tabulate的表，不误报为运行时Basix tabulation。现有phase包括raw张量创建/累加，不把总量都写成“某段标量循环实测”。

需要新增计时时，将它嵌入本轮第一个缺失oracle样本：分开各实际kernel与外层清零/累加。不得无修复重跑8个旧慢kernel只为再次得到52秒，也不先运行全域或安装profiling工具。既有生成C/IR和编译选项的静态检查，加最多一次必要分项样本，足够进入这个已选定候选的实现；不以收集更多profile拖延构建。

## 4. 唯一候选：actual几何因子＋共享参考表＋blocked Gram

### 4.1 固定接口和输入

在现有raw-tensor模块实现一个窄的evaluator分支，复用原`raw_tensor_evaluator`调用协议。几何policy仍为`mesh_actual_exact`，另记evaluator身份/源码/表hash；不新建V6 runner体系。改变返回张量的实现，必须改变新数值cache身份，旧coordinate inventory保留，旧缓存不得以相同名字冒充新值。

每个cell输入仍为原`mesh.geometry.x[mesh.geometry.dofmap[cell]]`的float64字节与原排列。输出仍为原DoF序下完整、连续complex128的882×882 raw张量。原`_orient_cell_tensor`只作用一次；原strict LU、R/T/S构造保持，不切Schur公式，不把J块假定为G的共轭转置。

### 4.2 几何不能偷换成边长公式

本轮几何实现明确选用**冻结FFCx kernel中的实际坐标几何/pullback因子计算**。从本场生成代码/IR取出该form所需的几何表达式与坐标导数表，封装为一个profile限定的小helper；保留原坐标乘加顺序、det/inverse表达式和编译浮点规则。不开发通用FFCx改写器，不用正则盲替任意kernel。

若原kernel在积分点上求值，就逐点求值；若合法地在循环外求一个常量，则保留该实际求值方式。不得用`ptp/widths`、先减origin、强制对角J、丢小off-diagonal、跨点平均或近似metric类替换它。坐标仍actual不等于几何求值自动相同。

在保留原kernel的一个有界校验副本中输出其几何中间量，比较helper的J、det、inverse/pullback因子。此处是新增加速器的oracle取证，不改变独立native或原基准。保留原表达式时预期可以逐位重放；不能逐位时先查运算/编译/表身份，记录实际差并证明几何语义未被简化，不能直接把“1e-15很小”当资格。完整张量及后续作用仍受下面原数值门约束。

### 4.3 参考表只建一次，逐单元做几何与矩阵乘法

复用原form分析得到的各积分规则，建立参考值、必要导数/curl及坐标导数表；按元素/hash/DoF顺序/积分规则hash去重。优先复用原FFCx使用的表；通过Basix构表时，核对相同点序、布局和原生成表的值/结构，不能因新的tabulation顺手变更原积分或阈值。不同规则分别保留；非零default/tag项完整相加，不能关闭原验证器来掩盖不支持的form。[C1][B1]

原B0的实标量几何、各向同性材料下，记映射后的形函数与curl表为Phi/C（行是积分点×分量，列是DoF），每块的体积贡献为：

```math
A_c=\sum_b\left[\mu_r^{-1}C_{c,b}^{H}W_{c,b}C_{c,b}
-k_0^2\epsilon_{r,c}\Phi_{c,b}^{H}W_{c,b}\Phi_{c,b}\right].
```

W含原积分权重和实际体积因子。参考表到物理表的Piola/curl映射必须沿原pullback依赖，若生成表达式含额外几何导数则完整保留；上式不是允许忽略那些项。test/trial左右约定与原UFL一致，复材料系数不取共轭，不把最终复矩阵强制Hermitian，不只算半矩阵再镜像。

用现有`_flat_and_weights`/Gram组织作块矩阵乘法；首版沿point block 32，所有位置共享只读参考表。允许一次有实测依据的块尺寸增大，但属于同一算法并须重新通过相同局部数值检查，不做参数扫描。精确参考表零可按原结构跳过，不能再加数值筛选。每个cell只保留当前块物理表、weighted缓冲、Gram scratch和输出；不保存全域积分点×基函数×基函数数组。

这样改变的是大批乘加的组织与参考表复用，不是积分精度或数学PC。由于求和顺序改变，不要求新张量与旧张量bitwise相等；这项有限变更由本review明确授权，并以独立比较约束。它也**不保证**actual候选一定解决旧全域差异。

### 4.4 生产接线只做必要薄改动

actual构造循环须实际调用该已验证evaluator，再沿同一方向/LU/R/T/S路径生成缓存；默认原FFCx仍保留为oracle及旧case路径。`geometry_policy`、evaluator与table身份同时进入capacity/audit、native绑定与持久化，不能拿候选计时套在仍执行慢kernel的正式入口。

若复用`assembly_time_geometry_class_counts`，先修actual分支引用不在其参数/作用域内的`allocation_gate/raw_tensor_evaluator/materialize_global_matrix`；或直接使用已保存V5 inventory和已有正确metadata路径。此源码问题不是V5耗时原因，不另开治理任务。新增evaluator在主builder中要显式资格，不能全局取消未知evaluator拒绝逻辑。[C3][C4]

## 5. 局部资格与成本：只有必要样本，不重建大模型找错误

首先消费V4两cell完整actual块和V5 inventory/prefix。V5记录的是8次计时，不证明8套raw/LU仍存在；读取实际manifest确认。两cell旧块可组合成完整原张量；R/T/S用这些独立原块及原消元公式计算。剩余样本若缺oracle，只补相同冻结FFCx的必要局部张量，每键一次保存，不重跑旧FE/PDE。

基准集合限定为V5八个代表键，包含两cell实际坐标、所有实际材料/方向覆盖。缺失oracle最多补其余6个；第一个这样的调用同时提供§3/§4的几何和计时信息。若实际inventory有新未覆盖布局，报告后只补该布局一个必要样本，不扩大为新网格研究。

| 层次 | 必须比较与保存 | 准入意义 |
|---|---|---|
| 输入/表/几何 | actual字节、point/weight/table、kernel、系数及DoF/方向；原FFCx几何helper输出 | 不允许归一化几何或漏积分 |
| 完整局部张量 | raw、oriented及K/G/J/L的绝对、相对Frobenius、最大项误差；与独立FFCx actual比 | 新加速器局部筛查上限1e-11；近零块同时报绝对值，不靠大块掩盖小块 |
| 消元 | 原formula所得R/T/S各自相对差≤1e-11、原strict LU门及KR+G/TK+J缺陷 | 同一张量一致性；不是全域门替代 |
| 保存场局部作用 | 两cell的known/j0/j3原局部作用、原失败行的全部incident contributions；全局b_t只一次 | 检查矩阵小相对差是否在消元和相减后显著放大，不用候选造RHS自验 |
| 实测成本 | 一次reference/geometry helper准备；每键geometry、pullback、Gram、orientation、LU/solve、Schur、observer/hash/释放 | 与V5排他phase同口径，不把startup移到计时外 |
| 内存 | shared表nbytes、当前块与BLAS复制、输出、保留cache、tree/cgroup峰 | 理论scratch和实测峰分别报告 |

局部1e-11只是进入全域的必要筛查，不表示如此大小的张量误差在全域必然可接受。必须披露ULP/绝对差与缺陷传播；不能用它放宽最终两列门。错误相位、错误材料、几何平移、漏非零积分的反向fixture须拒绝；不要求跑全部历史测试。

按同一次native ABI/MPI1/math1测候选八键。第一次准备与后续steady开销分列，原始FFCx baseline与候选不叠加计作候选生产时间。条件通过后，这批新候选缓存直接留在本次owner继续；旧进程中的LU/owner已经退出，不能假称复用其内存。

## 6. 全域准入不是“比52秒快一些即可”

沿用V5已测28,000 exact keys，不再根据widths合成三类。新evaluator身份改变的是数值生成法，不自动改变坐标库存。

```math
T_{\rm need}=T_{\rm prepare,remaining}
+(28000-n_{\rm ready})\,t_{\rm key,guarded}
+T_{\rm two\ columns}+T_{\rm checker}+T_{\rm cleanup}.
```

`t_key,guarded`沿V5已用的各排他phase最大值求和，使用本轮实测；reference表/JIT总准备只计一次。保留分阶段终止余量，取实际UTC/monotonic/账本更紧余额。post-build reserve包含其checker子段就不再次叠加。全域运行中按实际完成前缀更新预测并节流保存，不能到了截止才发现吞吐不足。

工程目标是将完整每键阶段争取压到约1 s量级，28,000键约7.8 h（算术情景，不是预测或新增数学硬门）。硬准入仍由完整实际预算决定：即使快10倍，旧17.2天也仍约41.3h，几乎没有给其他必要阶段留时间；不能据此宣布48h有希望或直接长跑。不要只给加速比，应给本轮全构建及两列检查的预算。

存储第一版仍保留独立actual R/T/S/LU；348,561,972,000 B只是已有完整cache派生值，另计metadata、shared参考表、FE/maps、native向量、临时BLAS与输出。raw/oriented逐键消元后释放，不形成第二份全域raw库存。本候选主要解决构建时间，不承诺降低那约348.56 GB缓存。后续200q/PETSc/factor/Krylov必须另做完整共驻准入，不用小前缀6.83GB外推。

证据累计16GiB不变。旧141数组和映射原地只读，样本/表只保存必要见证及hash，不把约349GB生产cache写进16GiB证据区。新scratch/输出在分配前过原资源门；time/RSS/cgroup/task swap及2GiB free-space floor继续有效。

## 7. 一次全域原两列重验与明确出口

局部正确性、时间和内存均准入后，在现有volume-only/生产构造链完成28,000键；P6 action、reduce_rhs与恢复共用同一新R/T/S/LU。已实现的原局部消元公式、最多三次同LU上限均不变。

复用原两列known、native volume RHS和native RHS；端口身份没改，读取两个已保存B帧，继承原port输出，不扫描64,120模式。把受影响的完整trace作用和凝聚RHS重新算出，替换全部对应分块后做原完整两列比较；不得用旧误差向量修补新答案。原全局b_t只处理一次，原MPC及E^H只施加一次。

仍要求原`max(norm(action),norm(reduced_rhs),tiny)`和冻结D0=2225.481253487629、D1=2225.4807123031883两个尺度下都≤1e-11。trace/port平方和、D/B/H及行域完整性保持。旧输入/原native仍是oracle；新R/LU只做必要受影响恢复核验，forward≤1e-11、原native体积残差≤1e-10，三次上限不变。不重新运行旧V3整个见证或改变已接受A1/A2。

沿V5已有残差凝聚恒等式记录geometry/native项、局部消元缺陷及相减余项：K/G/J/L、R/T/S由同一候选产生，初始与最终态分清；不用两个cell的改善代替全向量门。新向量在判门前保存，已修checker独立重算；完成审核与数值PASS分列。

| 触发结果 | 连续执行或停止要求 |
|---|---|
| 局部tensor/R/T/S或原几何语义不通过 | 留下最小oracle/candidate差；同一算法的索引、表、系数或生命周期bug定向修复再测，禁止上全域试运气 |
| 只是更快，但完整时间/内存不能准入 | `CANDIDATE_NOT_ADMITTED`，给实测phase、完整缺口和产物；不批准17天/偷偷扩窗、增线程或提cap |
| 全域两列仍超1e-11 | 保留全域数值FAIL及缺陷分解；加速成功不等于旧正确性问题解决。停止200q依赖，不盲目再跑完整模型或转第二PC |
| 两列通过但接口/checker有普通错误 | 数值产品独立保全，最小修复后只补受影响读回；不重新生成已完成张量/端口 |
| 两列、checker及生产绑定都通过 | 同一实际live owner优先连续target/200q/准确因子/完整参考；资源和窗口允许再进入FGMRES/pilot，不能逐阶段停审 |

后续57空端口q保留FE；各真实sector的新几何/算子/q/native资格不可省，不能移植旧Task40 q0。原q两RHS≤1e-10、完整reference strict/V15分列、target原A6≤1e-6、物理≤1e-5和最终网格/mode精度均保持。未来必要端口作用照常计费，但不能用其名义重跑本轮已经可继承的64120模式诊断遍历。

## 8. 新窗口提案与交付

原窗口数值截止`2026-10-20T05:03:07.094241922Z`、总截止`05:23:07.094241922Z`。审阅工具在2026-10-20 13:26:02（Asia/Singapore）确认两者均已过去；不使用旧712秒或其他历史余额。旧T0及费用永久保留。

**新固定窗口提案：总86,400 s、数值85,200 s、收口1,200 s；状态PENDING_USER_APPROVAL。**本报告不是自动授权延长旧窗。先完成窄实现、实际入口/最小fixture和准备包；用户一次批准后，从本包第一项必要正式运行准备（含imports/ABI/hash/JIT/table准备）冻结新T0，再连续执行局部资格/成本及条件全域，不在每个阶段重新申请。开发/fixture另列真实工程账；新研究窗不清零最终必要冷流程成本。

沿用`fenics-ws:/home/fenics/Projects/laptop_share`、cap1,649,267,441,664 B、host reserve68,719,476,736 B、task reserve0、原complex128/int32、MPI1/math1、exact MUMPS、task swap0、证据16GiB及free floor2GiB；现场更紧的host/ancestor约束优先。无需重新迁移、换项目、装库或重问已知主机。

只做三组相关回归：原积分/actual几何及tensor对照；新evaluator实际进入actual生产构造且R/T/S共用；保存审计/条件continuation/资源时间门。当前scope中的未定义变量和import等工程问题在冻结前由这些真实分支测试发现，修好继续；不跑全仓pytest、不追加旧波长或大型重构。

交`response_v6.md`和现有outcomes/run_index增量：先回答每键成本降到多少、完整张量/R/T/S差多少、全域原两列是否通过、真实峰值及新增数值能力；后列测试。保留负结果、原始17份回执及UNKNOWN。每段只报实际scope，父子不双计。已退出的owner不称为live，未运行的全q、场、最终精度、2TB/48h不写PASS。

建议提交一笔候选/必要接线与相关测试，再一笔实际数值/费用/收口证据；同一任务分支，主控集中冻结提交推送，执行者不自行push，不amend/强推，不修改master。

## 9. 给Codex的执行文本

```text
继续Task41extra，按review_report_v6.md。
分支task41extra_phi90_p50x50_g17x20；结果base dcc2737a9166e6c9185223ac084f811d5068ad4b；科学base 179cf7369e6bc5894fa87af6b74cf5c73938b6d4。

V5是CANDIDATE_NOT_ADMITTED，不是新数值FAIL或修复PASS。
不批准17天长跑，不重跑A1/A2、carrier、64120模式诊断遍历或旧恢复见证。
本轮唯一候选actual_qmetric_blocked_gram：保留mesh_actual_exact，
原参考点/权重/表共享一次，每键按冻结FFCx真实坐标几何/pullback求值，
用有界blocked Gram代替慢张量累加。原native、RHS、材料、方向和门不改。

先读取冻结生成C/IR和实际kernel调用，核真实quadrature/default/tag、
布局与编译身份，不把端口degree160当体积规则。必要内部计时嵌入第一个
缺失oracle样本，不另跑完整profiling或8个旧慢case。
复用Task39ExtraP6RawTensorCandidate的积分分析/Gram/evaluator协议，
但不能直接用其边差常量J，也不能启用widths六Gram替代actual几何。
原几何因子封装为profile限定helper，不平移/round/snap，不丢小off-diagonal，
不跨点平均，不改native，不开发通用FFCx重写器。

参考表按原元素/DoF/积分hash去重，原非零积分完整保留；complex材料系数
不取共轭，不强制Hermitian。actual主循环必须真的调用新evaluator，
方向只一次，原LU/R/T/S公式和精化上限不变，新数值缓存绑定evaluator身份。
旧geometry inventory只读继承；别拿老canonical或老FFCx数值缓存冒充新值。

先比较V4两个保存actual块，再用V5八代表键资格化。缺少原数值oracle
的键最多补其余6份原FFCx局部张量，各一次保存；不是重跑旧PDE。
完整raw/oriented/KGJL和R/T/S相对差均须满足review局部筛查1e-11，
原strict LU和保存局部作用也检查；局部PASS不替代全域原门。
测reference准备、geometry/pullback/Gram/方向/LU/Schur/保存等排他成本及scratch。
按实际每键成本和全部剩余阶段准入，目标约1s/键是工程目标不是预测。
不能只报加速几倍便上全域。原348.56GB缓存仍另算，全部raw临时块逐键释放。

准入后一次构建全域，复用原141数组和全maps；仅读两个B帧、继承未改port。
新trace作用和reduce_rhs必须走生产核心，原b_t只一次、MPC只一次，
完整两列原max分母及冻结约2225尺度均<=1e-11；受影响恢复forward<=1e-11，
native体积残差<=1e-10，不用候选自己制造RHS或用保存差向量补答案。
checker通过后连续200q/准确因子驻留/完整参考/条件target；57空端口q保留FE。
不通过就保存完整差异和具体停止原因，同候选工程bug最小修复继续，
不盲目重启整场、不转新PC。

旧窗口已截止。新24h窗仅为待用户一次明确批准提案：86400/85200/1200秒。
先完成窄准备及真实命令，获准才冻结新T0，含必要ABI/hash/JIT/表准备；
旧T0和全部费用保留，不把研究续作当冷流程48h通过。
主机/cap/reserve/任务swap0/ABI/MPI1/math1/MUMPS/16GiB证据上限全部不变。
不全仓测试、不重构、不新建项目；主控集中提交本分支，保留负结果与UNKNOWN。
```

## 来源（固定结果HEAD；外部文档仅说明API，不替代本场版本核验）

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/response_v5.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v5_mesh_actual_exact_not_admitted_20261020.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/summary.md
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/run_index.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/docs/task41extra_phi90_p50x50_g17x20/outcomes/test_summary.md
[C1]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/task39extra_p6_raw_tensor.py
[C2]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/hcurl_affine_isotropic_tensor.py
[C3]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/hcurl_assembly_time_condensation.py#L1350-L1620
[C4]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/hcurl_assembly_time_condensation.py#L3030-L3290
[C5]: https://github.com/Rookie1234567/MyFEniCS/blob/dcc2737a9166e6c9185223ac084f811d5068ad4b/src/solvers/task41_v4_volume_only_audit.py
[B1]: https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.finite_element.html
