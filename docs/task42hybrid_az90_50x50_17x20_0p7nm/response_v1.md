# Task42 执行回应 v1：A0 输入、A1终态与A2合同阶段

## 本阶段结论

| 项目 | 结果 | 状态和边界 |
|---|---|---|
| Task42 A0 | 公共输入、材料来源、dry-run、Floquet/外通道、边界拟合小网格和体积检查完成 | `passed_with_qualifications`；不代表Full3D方程求解或资源资格 |
| 13.5 nm直接参考 | 最近一次正式A1于2026-10-19启动；数值worker写出了残差、端口功率和场文件 | worker summary标记`official_result=true`，但整场因最后一次whole-job资源authority不完整而`refused`；不能把整场称为通过 |
| 0.7 nm | 两波长Si材料输入已冻结，外通道键可独立枚举 | `not_run`；本阶段没有建立0.7 nm网格、QEP或求解 |
| A2 full-K0 sizing（2026-10-20） | 4033×4033 full K0，MPI8每rank一次assembly；派生离线检查24份数组工件、CSR与identity | 单K0 sizing通过；原controller completion失败保留，未运行K1/K2/M、约化、PEP/QEP或物理求解；[离线核验](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_k0_summary_reconciliation_offline_20261020T121140Z/offline_k0_reconciliation.md) |
| ordinary默认 | 未改变 | Task42仍由显式model/profile身份进入 |

13.5 nm模型冻结为方位角90°、掠入射1°、s偏振、50×50 nm周期、居中17×20 nm光栅；光栅高120 nm，z域为−10到130 nm，接口位于10/110 nm，p6/h10。A0验证实际公共入口能解析该模型并给出一致的场与外通道配置。A0的真实边界拟合网格检查确认材料界面与网格平面对齐，并核对小网格上的材料体积。

## 正式A1尝试历史

| RUN时间 | 范围与实际进度 | 因子/求解 | parent wall与费用口径 |
|---|---|---|---|
| `20261016T121844.178539Z` | 原正式A1；资源authority拒绝的原始记录保持不变 | 已发生factor与solve | 仅沿原attempt收据记账；本表不重复追加或重算 |
| `20261019T034149.351129Z` | 必要重建尝试；authority为unknown，未通过分配前门 | 未进入factor/solve | `not_measured`；不补造wall |
| `20261019T062050.882932Z` | 最近一次额外正式A1；数值输出已写，终态为运行期资源authority拒绝 | 已发生factor与solve | `313.734830358 s`，唯一parent wall，已追加一次 |

`20261018T115039.812072Z`是旧packet恢复attempt，与正式A1 factor/solve分开记录；候选、ABI和public prelaunch gate也不是PDE。各自费用只沿原始有效收据保留，不从attempt间隔或候选时间推算。

## 材料来源

用户于2026-10-16明确本任务13.5 nm和0.7 nm的光栅、基底都使用Si。精确十进制输入、复折射率、相对介电常数和用户来源记录见[材料记录](materials/user_supplied_si_optical_constants.json)，文件SHA256为`19dd3e99663580bf3eb4076e90f55597054c6a7da8c177b02536a274fbf0ab65`。采用约定 `n=1-Delta+i*Beta`：

| 波长 | 用户给定Delta | 用户给定Beta | 推导复折射率n | 来源/用途 |
|---|---:|---:|---|---|
| 13.5 nm | 0.000998703763 | 0.00182646094 | 0.999001296237 + 0.00182646094i | `user_supplied_delta_beta`；用于本阶段A0与后续同身份阶段 |
| 0.7 nm | 0.000196346038 | 8.98053258E-06 | 0.999803653962 + 0.00000898053258i | `user_supplied_delta_beta`；已冻结，本阶段未运行PDE |

这两组值覆盖Task42 `task.md`中建立任务时的W材料段落；`task.md`本身和Task041历史均未改。它们不是外部数据库测量或实验资格。旧W候选原样保留，只作为已被本任务输入覆盖的历史材料。

## A0实现与检查

| 改动 | 证据 | 结论 |
|---|---|---|
| Task42输入/profile身份校验与材料记录SHA绑定 | `src/io/input_validation.py`及新输入文件 | 错方位、错误几何、旧Task041 Si值和旧Task041 packet入口均被拒绝 |
| 入射向量、偏振、Floquet相位及H/Poynting解析值核对 | `src/test/test_task42_physical_entry.py` | 对照独立公式；只涉及解析入射场，不是求解场 |
| 外通道与完整报告级次 | 同一测试 | 13.5 nm空气外通道空间键为42；报告范围固定m=3、n=7并覆盖实际合法键。该范围是报告设置，不改变DtN枚举 |
| 小型边界拟合网格/材料体积 | MPI2 selector | 两rank构建小型测试网格并核对边界平面、材料标记和体积；不是正式p6模型网格 |
| 0.7 nm外通道盘点 | pure key inventory | 得到16031个空间键；只枚举键，不建mesh、不算QEP，也不是数值资格 |

源文件中的材料路径SHA与实际JSON SHA一致。测试还实际调用`run_case`的`--validate-only`和`--dry-run`入口。`Path(__file__).resolve().parents[2]`实际解析到仓库根目录 `/home/fenics/Projects/MyFEniCS`。

## 测试与独立费用记录

真实运行收据位于ignored `results/task42hybrid_az90_50x50_17x20_0p7nm/`。表中的wall时间来自GNU `/usr/bin/time`记录，显示精度按其原记录保留至0.01秒；不称为高精度`CLOCK_MONOTONIC`，peak RSS也不冒充整棵进程树或cgroup峰值。

| Attempt | 命令范围/结果 | GNU time wall | GNU time peak RSS | 说明 |
|---|---|---:|---:|---|
| `20261016T082736Z` | 本地preflight checker在pytest前拒绝解释器symlink路径；pytest未启动 | 0 s pytest wall | not recorded | 收据将此归为本地路径断言错误；native activation的实际Python在后续ABI中核验通过 |
| `20261016T082837Z` | serial回归，首个失败是Poynting公式交叉核对容差；`-x`下其余未运行 | 2.43 s | 208284 KiB | 失败原始输出保留；观测的binary64公式差最大`1.68309811e-13`，修正交叉核对精度后重新运行 |
| `20261016T082953Z` | serial：A0文件及3个相关launcher/profile selector；12 passed | 11.72 s | 320268 KiB | 六个数学线程变量为1；native ABI为PETSc complex128、Int32；测试前后绑定源码不变 |
| `20261016T083132Z` | MPI2：仅boundary-fitted mesh/material-volume selector；rank 0/1均通过 | 1.47 s parent | 113944 KiB | rank CPU为4/12，rank-private basetemp；两rank均核验native complex128/Int32，源码前后稳定 |

本阶段实际启动的pytest父命令共3次，按上述GNU time显示值相加为15.62秒（由0.01秒精度记录相加）。preflight未启动pytest的082736Z不收费。serial与MPI2 ABI检查不作为pytest wall重复计费。完整独立Task42条目见[账目](outcomes/a0_test_ledger.json)；被保留的失败和未运行范围见[测试摘要](outcomes/test_summary.md)。

## A1最小接线方案（A0时的规划记录）

此表保留A0结束时的规划语境；Task42 opt-in后来已接入并在本回应后部记录了正式运行结果。普通Task038输入和默认行为保持原样。

| 接线点 | 最小方案 | 保留的边界 |
|---|---|---|
| soft 48 h目标 | Task42运行策略把48 h作为进度/冷运行目标；过时继续报告未达目标，不以elapsed触发terminate。仅Task42分支关闭时间强停 | CPU、内存、磁盘、OOM和异常退出保护仍有效；不改通用launcher默认 |
| 资源authority | 复用现有kernel MemAvailable、process-tree RSS、dedicated cgroup current及有限祖先headroom采样/authority；每次大分配前给出J、真实新增Delta和W | R=384 GiB；Cmax=min(1.5 TiB, MemTotal−R)；13.5 nm的C=min(256 GiB,Cmax)；W=max(8 GiB,0.05C)；要求J+Delta+W≤C、MemAvailable≥R+Delta+W、各有限祖先headroom≥Delta+W。未知量拒绝下一阶段分配；swap只观察 |
| 分级Gate | 在mesh、assembly、symbolic、numeric、recovery/输出各现有阶段边界调用同一authority；LU复用`petsc_lu_stage.py`的symbolic/numeric callback gate | J=max(进程树RSS,dedicated cgroup current)；已驻留对象不重复计入Delta；不能以启动时预留整个C替代逐阶段预算 |
| Full3D direct与快照 | 优先在现有direct `_solve_augmented_system` 接入可选stage gate/LU bridge，保持MUMPS direct身份；只有证实现有等价接口与官方快照合同兼容时才复用它 | `linear_solver_port`面向迭代/action，不能伪装direct；`dtn_port_3d._external_snapshot_allows_official_rta`当前要求`no_global_factor`成立，真正使用全局MUMPS factor时不能伪标。若direct路径进入该检查，须设计诚实保留direct身份的Task42快照核验。为Task42显式扩展pre-recovery packet identity，保留原A、RHS、解和原残差，恢复后重算原方程true residual |
| 正式输出 | 仅在原A残差及任务Gate通过后保留official场与R/T/A、A_volume、完整衍射级、参考面E/H、清理与identity | setup或单次LU成功不构成数值pass；所有阶段和清理费用按唯一Task42运行记录 |

## A1实际接线与合同边界

Task42显式opt-in现将输入`timeout_seconds=172800`解释为48小时软目标；到点写入状态但继续运行。ordinary Task038仍保留原超时行为。该接线不移除硬资源门。

| 项目 | 本轮结果 | 尚未证明 |
|---|---|---|
| 资源公式与whole-job authority | 启动/阶段门核对整作业J、实际新增Delta、W、kernel MemAvailable和有限适用祖先；运行期硬门检查J≤C、MemAvailable≥R，避免轮询重复扣W | 本次fresh MPI8准入和逐rank affinity已通过；终态轮询因进程树不完整拒绝，实际whole-job J未知，不能改判为超cap或通过 |
| direct factor路径 | 同一MUMPS factor完成symbolic→numeric→MatSolve→packet→destroy；同一新C bridge实际覆盖`ICNTL(14)=None`与显式40控制 | 仅8×8合同矩阵，不代表p6/H10因子表现 |
| 恢复与writer | full residual消费、pre-recovery packet、实际packet writer成功/本地写失败传播、active-trace gather驻留公式均有小型定向覆盖 | 本次正式run还实际写出pre-recovery packet、E/H场及R/T/A和衍射文件；见下节离线核验。整场仍因资源authority拒绝而未整体通过 |
| 时间口径 | Task42 48小时为soft target，不因时间单独terminate；普通Task038不变 | 长时运行效果未实测 |

Task42容量参数为R=384 GiB，Cmax=min(1.5 TiB,MemTotal−R)，C=min(256 GiB,Cmax)，W=max(8 GiB,ceil(0.05C))，warning=0.9C。阶段准入为`J+Delta+W<=C`、`MemAvailable>=R+Delta+W`、有限祖先headroom≥`Delta+W`；运行期使用硬界而不重复预留W。J=max(launcher进程树RSS、经authority证明适用的专属cgroup current)。

A1合同回归、历史失败保留和正式run终态见[测试摘要](outcomes/test_summary.md)、[结果摘要](outcomes/summary.md)及[本次只读审计收据](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/offline_terminal_audit.json)。本次fresh MPI8准入通过；最后一次运行期样本则缺少8个仍显示为`R`的rank进程的`VmRSS`/`VmSwap`，同PID/start_ticks复读仍缺字段，whole-job J因此未知。资源门fail-closed是本次整场的最终状态；不存在“已证实超C”的依据。

## A1 13.5 nm正式运行与终态（2026-10-19）

正式模型仍为13.5 nm用户指定Si，p6/h10、50×50 nm周期、17×20 nm光栅、高120 nm、z域−10..130 nm、方位90°、掠入射1°、s偏振、MPI8；输入SHA为`e14b7808f168b4f35f174ebc4ce37e5c9703826d6e7761dfd2cf6c85e31b5d06`，source HEAD为`12c360fc3bae647ad6e57d1b2d790f96640cbcf8`。[本次原RUN manifest](../../results/task42hybrid_az90_50x50_17x20_0p7nm/task42_az90_50x50_17x20_13p5_full3d_direct_p6h10_mpi8/task42_13p5_p6h10_full3d_direct_mpi8__full3d_direct__mpi8__Mna/20261019T062050.882932Z/run_manifest.json)及attempt未改写；文件、数组和哈希逐项只读复核见[审计收据](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/offline_terminal_audit.json)。

### 数值worker与整场状态分开记录

| 层次 | 记录 | 可得结论 |
|---|---|---|
| 数值worker summary | `case_status=completed`、`official_result=true`；完整原方程相对残差`9.306460504345312e-11`，finite=true | worker确实写出了数值结果；这个字段不替代外层Task42资源门 |
| 主DtN端口结果 | R=`0.2550072646379847`，T=`0.056598948040126884`，A_port=`0.6883937873218885` | 以DtN端口模态振幅计算；外参考面z=130/−10 nm，底部有损介质功率包含边界相位修正 |
| 体吸收 | A_volume=`0.6883937861128354`；A_port−A_volume=`1.2090530798758437e-9`；R+T+A_volume=`0.9999999987909469` | 吸收按`0.5*k0*Im(epsilon_r)*abs(E_total)^2`对Si物理材料单元积分，空气与PML排除 |
| 零级反射 | R00_s=`0.254974601609543`；R00_p=`4.5883121973545914e-24`；R00_total=`0.254974601609543` | s/p分别列出；R00与全168项反射总和是不同量 |
| 外层RUN / public / service | RUN exit 1、public driver rc 3、service ExecMainStatus 3，Invocation=`048a5d671150436f9c05cd1bfb5a9d29` | RUN最终分类为`task42_runtime_resource_gate_refused`；三层退出状态不能合并成数值失败或通过 |

### 场文件、packet与168个外通道

PVD列出8个rank VTU，全部可由原生VTK reader打开。每个rank文件都含E总场、入射端口E场的real/imag/abs以及H场的real/imag/abs；数值数组均有限，向量数组为每点3分量，幅值数组为每点标量，另有cell `domain_tag`。rank cell数合计504；rank间共享点使point数不可直接求和为全局唯一节点数。worker summary只列出了E数组，实际VTU还存有H数组。完整场样本NPZ内E/H为complex128、形状`(5,40,40,3)`，两个界面切片为`(2,40,40,2)`，均有限；其z平面是10/30/60/90/110 nm，档案SHA与metadata和worker summary一致。它是本次场的采样档案，不是解析精确解（summary中`exact_reference_available=false`）。

168项DtN输出含84个top、84个bottom，以及84个s、84个p；166项标记为propagating。输出中的`auxiliary_index`连续覆盖0–167，并按输出数组顺序排列。与RUN manifest中的168个external-mode key集合完全一致，但key顺序不同：manifest和输出表不能按两个数组位置直接配对，必须按每行side/m/n/polarization关联。逐行`power_ratio`独立求和得到R=`0.2550072646379845`、T=`0.05659894804012687`，与端口summary仅有末位舍入差。

pre-recovery packet含8个complex128 shard，每片实际存`solution`和`rhs`，数组长度与连续ownership range相等、值均有限；manifest identity hash及其中source/input/physical/resolved-config SHA与本RUN相符，8片文件SHA均匹配。Full-FE与active-trace canonical导出也各有8片，manifest及16片SHA均匹配；类型均为complex128，packet总数分别为341436和114636，本地重复数均为0。这两个canonical manifest本身不含独立RUN/input/source identity，身份来自其所在RUN目录及父manifest，且其extractor audit中的`hcurl_norm`与`trace_mass_norm`均为`not_qualified`。RUN中没有BP档案。

### 端口结果与探针诊断不能混算

正式端口R/T来自边界z=130/−10 nm上的DtN辅助模态振幅，并按入射功率归一。`power_metrics_3d.json`是另一种诊断：它在z=125/−5 nm均匀层探针面，以E/H Fourier最小二乘拟合传播方向（105个空间级、210个偏振通道）；拟合R=`0.2546430430395836`、T=`4.030194817781968e-5`、A=`0.7453166550122385`。同文件的采样净通量用探针面E及由有限元curl重建的H积分，不做衍射级分解，R=`0.25508219821040456`、T=`0.07257569600562415`、A=`0.6723421057839714`。两种探针诊断均以`incident_power_code_units=21.815508046604222`归一，但输出面和算法不同于端口模态；数值与DtN端口结果明显不同。top E/H拟合最大残差为`0.9980693005722018`，bottom为`2.0411909699601356e-10`。这里的拟合残差不是线性求解残差。差异的已知部分和仍缺证据部分见本文末尾的后续复核；不能拿探针诊断替代端口结果，也不能仅凭能量闭合称所有场/衍射诊断合同均通过。

### 资源拒绝、费用与sampler边界

最后一个完整runtime样本在elapsed `312.8408444840461 s`仍通过；elapsed `313.3017449709587 s`的下一样本拒绝。该样本列出10个进程（RUN root、mpiexec及8 ranks），但`all_status_readable=false`；8个rank两次读取均保持相同PID/start_ticks和状态`R`，`/proc/status`中`VmRSS`与`VmSwap`都缺失，bounded reread后仍为`refused_same_identity_status_still_incomplete`。因此whole-job J是unknown，不能填0、引用旧RSS或用专属cgroup current代替完整树。cgroup当时可读且current为`11119267840` bytes、直接`cgroup.procs` member_count=3；`MemAvailable=1859305144320` bytes、C=`274877906944` bytes。有限祖先硬限不适用。`member_count=3`与进程树10项只是同时记录的线索，无法证明进程退出竞态；最后读取状态仍为R。

原gate错误向量同时包含`whole_job_process_tree_is_incomplete_or_unreadable`和`runtime_whole_job_J_exceeds_Task42_C`。后续最小分类修复只改变错误标签，不改变fail-closed判定：只有完整整树J已知且实测J>C才标记超过C；J未知时仍拒绝，但标记`runtime_whole_job_J_is_unknown`。用原062050Z末样本逐字段重放后仍拒绝，错误向量现为`whole_job_process_tree_is_incomplete_or_unreadable`与`runtime_whole_job_J_is_unknown`，不再误报已超C。4个定向serial测试通过；原样本和费用不变，见本文末尾及[分类回归证据](../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/classification_error_vectors.json)。

public completion记录parent wall `313.734830358 s`，作为Task42本次正式attempt唯一费用，不乘MPI ranks、不叠加阶段采样；attempt的RUN exit1、public rc3、service rc3分别保留。最终进程组收到TERM后退出，未用SIGKILL。主控真实host终态读取确认Invocation的MainPID=0、ControlGroup为空、NRestarts=0、登记进程全缺席。此前`20261016T121844.178539Z`正式RUN的资源拒绝及`20261018T115039.812072Z`旧packet布局拒绝均保留原件；后者未产生新factor/solve。此parent wall已在[唯一费用append](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/task42_fee_append.json)记录一次；逐文件SHA见[审计收据](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/offline_terminal_audit.json)。本次额外正式A1额度已用完，本阶段不授权再跑A1。A2与0.7 nm仍按原task的前置资格和内部审核推进，目前均未启动、未获本阶段放行。后续sampler分类修正与探针/端口离线复核已完成，见下节；未申请或运行新的A1。

## 后续复核：错误分类与探针/端口差异

错误分类修复的源文件SHA为`4c2c86b57b6c0b98c5503d4c2542f0333dbe7f77e97e5e14ef242ea4835ecd2e`，对应测试SHA为`cdceb62251304c80b3e7bd318ad94d847053757dc6dfeb9032a540bcaf8ab8`。定向serial回归为4 passed；pytest报告`0.22 s`，独立parent monotonic wall为`0.505579699 s`，pytest PID未持久化（`not_persisted`）。以同一062050Z authority样本重放仍为拒绝/incomplete+unknown，没有追认通过；此修改不改变资源公式或门限。测试stdout、parent记录、重放前后错误向量与文件校验见[ignored收据目录](../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/)。

离线源追踪解释了底部探针透射差异的主要部分。底部Si中的零级s模态在探针记录里标为`propagating=false`，但DtN端口记录为`power_carrying=true`，其透射贡献为`0.056559356398515837`，几乎占端口`T=0.056598948040126884`的全部。探针E/H拟合按`bottom_propagating`筛选，漏掉了该项；DtN端口按`power_carrying`计功率。探针和端口平面相差5 nm；从存档传播常数得到的预期功率衰减比为`1.28258713`，实际净通量/端口透射比为`1.28227995`。这支持传播距离造成部分差异，但净通量与模态功率和的定义不同，不能据此证明它是唯一原因。

顶部反射差异仍未解释。top最大拟合残差`0.9980693005722018`对应倏逝级`(m=2,n=1,s)`，该级反射功率贡献为0，因此此高残差本身不能解释总反射差。原运行没有保存探针面z=125/−5 nm的24×24采样E/H；现存NPZ只含z=10/30/60/90/110 nm数据，不能拿这些内域参考数组替代。未重建网格/算子或重新求解，未修改存档诊断值和生产后处理；以上仅是离线解释，不构成物理资格结论。

证据清单更正：先前报告的`856e8089…`是通知收据加入前7项清单摘要，旧清单字节未留存；加入`main_notification_receipt.json`后，8项清单摘要为`8be9b3083fc11689ba0a59f96cca148c139e6850f4b5528e5d638587b299e162`。之后追加更正记录并重生当前10项清单，最终摘要及逐项校验见[分类证据SHA256SUMS](../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/SHA256SUMS.txt)；不声称保有旧7项清单副本。

## A2 Hybrid-direct合同阶段（2026-10-19）

### 实现身份与当前资格

A2是独立的Task42 Hybrid-direct profile，不借用Task039身份或Task041 packet。模型仍为用户指定13.5 nm Si、50×50 nm周期、17×20 nm光栅、高120 nm、z域−10..130 nm、接口10/110 nm、方位90°、掠入射1°、s偏振、p6/h10/M120、MPI8；传播使用`full3d_uniform_cg`，traction使用`full3d_one_cell_exact_schur`。实现提交为`44f671cefd9a3130897bfc898ba21cde8528fbe4`，parent为`ab1af4f263fc63ee7e6bc04499dc1ee366a7afb4`，包含21个源代码、测试和输入配置路径，不含本回应及其他文档。该合同阶段没有运行mesh、QEP、FE、MUMPS factor、MatSolve或正式A2。

A2输入完整原字节SHA为`42f486012a38f67a3d6cbdf84801c1bdf9e16e4733f8b1211f7f01f446b39c94`。独立预算basis SHA为`80c084655f67587c0616de782cf0a3e2e50cb41ea357bf4e09948cb0e7786332`；它从解析后的dat规范值计算，且仅移除`execution.phase_budget_manifest`与`execution.phase_budget_manifest_sha256`两个预算引用字段。basis不是dat原字节SHA。当前还没有涵盖所有阶段、绑定源码/输入/材料/MPI及rank/side sizing的完整phase budget manifest。mesh与mixed-space/collapse已有各自独立阶段测量和预算；MPC、QEP、两侧凝聚/traction、MUMPS与恢复等其余阶段仍为`pending-sizing`，因此profile继续fail-closed、不可启动。

静态调用链已贯通公共`run_case` → execution plan → Task038 launcher/worker → Task42 adapter → 共享Task032 Hybrid direct数值内核。Task42输出按实际`sample_x/y/z`确定数组形状，核验复E/H数组、完整外通道键和q索引映射、来源身份及canonical前缀。写文件由root执行；本地验证或写入拒绝先以一致结果传播，各rank不进入后续writer/求解操作。预算basis按MPI rank及bottom/top side分别精确绑定，不能用全rank共享字符串描述冒充局部实测basis。Task039原schema、shape检查和profile白名单保持原行为。

分配前拒绝的小型合同覆盖mesh/空间、QEP operator与求解、局部侧构造、耦合/增广矩阵、MUMPS setup、解算、恢复和导出边界。PETSc `KSP.setUp()`当前把MUMPS analysis与factorization合并；只能报告一个`direct_mumps_factor_setup`阶段，不能宣称symbolic/numeric已独立gate。源绑定对象预算仍待实际mesh/DoF/NNZ/填充证据，不把单个240×240数组或A1内存峰值当完整Delta。

### 合同测试结果与费用

最终serial attempt `a2_contract_native_serial_final2_20261019T092443Z`结果为32 passed、2 skipped；两个MPI2专属拒绝传播case在MPI2批次执行。MPI2 attempt `a2_contract_native_mpi2_20261019T092648Z`只运行4个指定collective selector，每个rank均报告4 passed，parent rc=0。动态rank map为rank0→CPU2、rank1→CPU10，实际affinity精确相等；PETSc complex128/Int32、default memory policy、full-node `Mems_allowed_list`及六线程变量也已核。MPI2确认root独写成功、单rank坏shape拒绝、root预存文件写失败一致传播，以及root资源拒绝发生在受保护分配之前。两次结果均是小数组/桩的合同资格，不是FE/A2数值资格。

上述pytest实际启动父进程的wall只按parent receipt计费：serial各尝试和MPI2最终attempt的累计为22.390668208秒，按attempt各计一次、不按rank数相乘；最终serial parent为3.295652662秒，最终MPI2 parent为2.878076813秒。最终serial的pytest显示时长2.93秒、MPI rank各自stdout时长均不作为费用。ABI parent另有收据，不并入pytest费用。早期失败保留；091322Z、091422Z、092019Z为pytest未启动的本地准备拒绝，不收费。逐次命令、错误与清场证据索引见[测试/费用摘要](outcomes/test_summary.md)与ignored `results/task42hybrid_az90_50x50_17x20_0p7nm/`。

### 下一阶段A2 sizing与外通道功率审查建议

下表是后续预算数据的取得顺序，不是本次已执行工作，也不授权启动实际mesh或QEP。Task42仍使用`C=min(256 GiB,Cmax)`、`R=384 GiB`、`W=max(8 GiB,0.05C)`及`warning=0.9C`；每个真实阶段先绑定input/source/MPI/side/rank对象表，并审核`J+Delta+W<=C`、`MemAvailable>=R+Delta+W`与有限祖先headroom。运行期继续使用`J<=C`和`MemAvailable>=R`，未知authority保持拒绝。

| 阶段 | 需实际取得的数据与计算依据 | 当前边界 |
|---|---|---|
| 边界拟合网格 | 先为Gmsh与分布式坐标、连接、标签及临时副本建立独立保守上界；获准后mesh-only读取实际cells/vertices/ghosts与每rank分布，释放临时对象并保存来源 | 只有纯fixture；尚无A2生产网格计数，mesh-only也须先有自身预算 |
| 2D空间与MPC | 由真实p6截面space取得全/局部DoF、owner范围、collapse map、Floquet slave/master映射和数据类型 | 数量未知；不可凭周期面积换算或A1全3D DoF猜测 |
| 全/约化QEP算子 | 为K0/K1/K2/M及full-to-reduced transform读取实际本地行、AIJ NNZ、同时存活矩阵和复制数；每个AIJ矩阵至少按`nnz*(ScalarType字节+PetscInt字节)+(本地行数+1)*PetscInt字节`计算稀疏主体，再加组装临时量 | 无真实NNZ；不能用单个稠密240×240数组作总预算 |
| QEP求解与模态 | 以实际PEP维度、`ncv/mpd`、保留候选数、左右/正负模态与重叠矩阵尺寸清点同时驻留向量和矩阵；对SLEPc后端工作区给出有依据范围或保持拒绝 | 后端工作区及模式保留量未知；尚未运行QEP |
| bottom/top凝聚与traction | 分rank、分side记录局部mesh、owned cells/rows、geometry classes、MPC、Schur NNZ、cell tensor/LU与recovery cache；核实`full3d_one_cell_exact_schur`所需10 nm轴向局部网格和实际traction轴向网格一致 | 上下侧basis不能共用；实际局部网格与traction计数未取得 |
| coupling、增广与解 | 按真实块shape/NNZ、完整双向外键、modal RHS、映射与同时驻留pack/copy算Delta；MUMPS阶段要有实际augmented NNZ、ordering/fill与工作区的可辩护预估 | direct `KSP.setUp()`合并analysis/factorization；其setup前无可用实测INFOG，未有可靠填充上界就不得放行该大分配 |
| recovery与输出 | 计数两侧局部恢复对象、真实全外通道数组、采样E/H、canonical vectors、collective gather和writer暂存；区分rank-local副本求和与全机总额重复报告 | 当前仅接口合同，没有A2数组尺寸或生命周期峰值 |

先前A1仍有独立资格缺口：数值worker残差/端口能量闭合/场文件存在不能覆盖外层whole-job资源unknown；A1的source与port独立一致性门、trace alias映射，以及canonical `hcurl_norm`/`trace_mass_norm`仍缺合格证据。以下段落是P1修复前的记录：Task42 A2的`_external_diffraction_order_rows`曾按`mode.propagating`决定行级R/T，而`dtn_port_3d._port_power_metrics`按正向功率判定；A1已知底部Si `(0,0,s)`存在`propagating=false`但仍`power_carrying=true`的情形。该行级待办已由下方P1公式fixture与最小生产修复处理；A2物理资格仍未建立。

## P1：Hybrid逐行衍射功率报告修正（2026-10-19）

生产提交为`6d9106b7e956d7c5f0b2ca950e19ba4c8ab3a6ed`，parent为`9d0a42d86ed9a30b4a82b9c1ebca2b80288434c5`；仅改`src/solvers/hybrid_fem_modal_augmented_direct.py`及其单selector合同测试。生产文件SHA256为`652d19a6540660d870ace9a81ef110fd40c82cd9ec0b541477f65cb55ab557e1`，测试文件SHA256为`f68c7c34e44ab684e2ded565872ee8bfe9faf4f0b3e6df32e7f1dd8423dcf444`。该源码提交完成时工作树clean且origin与HEAD相同；后续文档改动单独记录，不回写该源码提交身份。

修复只把`_external_diffraction_order_rows`的R/T纳入条件从`mode.propagating`改为复用`dtn_port_3d._mode_carries_outward_power`。这样一条通道即使被标记为非传播，只要在当前介质和参考面上确有正向功率，行级R/T便与端口总功率采用同一判据。`propagating`标签、`beta`、边界相位、入射场扣除、原始`power_ratio`、key集合/顺序和所有字段均未变；没有新增schema字段、阈值或钳零行为，端口总量公式和物理门也未改。

修复前的同一公式诊断用任意synthetic auxiliary幅度重现了差异：用户Si材料下底部零级s/p均为`propagating=false`但带正向功率，DtN端口分别贡献T=`0.25778898368788117`与`0.07047896142319664`，合计`0.3282679451110778`；旧row T总和为0。这个数仅用于报告公式合同，不是A1/A2物理透射率。修复后同一小fixture逐行和总量相等：row/port T均为`0.3282679451110778`。无损Si倏逝控制的原始浮点`power_ratio`约`3.82e-18`/`8.78e-18`，但正向功率判据贡献和T均为0；不把舍入小量强制清零。无损n=1.2传播s/p控制也逐行及总量相等；因aux幅度是人为指定，测试T约`10.5013458207>1`不代表物理能量通过。顶部入射极化扣除保持不变；正交p投影约`1e-31`只是数值近零控制。

静态消费者审计未发现旧测试依赖错误的`propagating`筛选：Task42共享输出按完整key inventory验证并原样保存行字段/q映射，不自行重算R/T；Task038/Task039消费者校验外通道key完整唯一及`power_ratio`、`beta`、projection、amplitude等字段有限，不以`propagating`推导或断言R/T。现有`test_14_stage4_dtn_modes.py`检查的是已采用同一正向功率口径的DtN端口writer，不是被修改的Hybrid行生成器。Task039旧schema/shape/字段不变。

最终selector为`test_task42_hybrid_rows_and_dtn_ports_report_power_classification_difference`，rc=0，parent monotonic wall=`3.038582487 s`，owned进程组清空；pytest显示时长不另计。最终收据及对照JSON见[`a2_p1_port_power_row_fix_retry2_20261019T101228Z/serial`](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_p1_port_power_row_fix_retry2_20261019T101228Z/serial/)；该合同测试不运行FE/QEP/factor/MatSolve，不构成A2数值资格。该attempt目录当前21项SUMS逐项校验通过；通知前19项与追加通知/pycache后的21项是不同清单版本，旧版本摘要不替代当前清单。P1所有历史失败、未启动尝试和parent费用见[测试/费用摘要](outcomes/test_summary.md)。

## A2 首阶段mesh-only候选预算（执行前预测，历史记录）

本候选只为之后取得真实二维截面cells/ownership提供一个有限的第一步预算；它不是完整A2 manifest或启动授权。身份绑定为当前HEAD `6d9106b7e956d7c5f0b2ca950e19ba4c8ab3a6ed`、A2 dat SHA256 `42f486012a38f67a3d6cbdf84801c1bdf9e16e4733f8b1211f7f01f446b39c94`、用户材料记录SHA256 `19dd3e99663580bf3eb4076e90f55597054c6a7da8c177b02536a274fbf0ab65`；相关源文件SHA256见本回应的静态预算记录。没有调用mesh/space/QEP构造取数。

根据冻结50×50 nm周期、居中17×20 nm光栅、`mesh_target_nm=10`和边界拟合源码：x轴由`0/16.5/33.5/50`分段，单段cell数按`ceil(length/10)`为`2+2+2=6`；y轴由`0/15/35/50`同样得6。二维截面因此为36个四边形、49个顶点、84条边。MPI8输入cell分配按现有`_rank_cell_ids`公式为`[4,5,4,5,4,5,4,5]`个输入cell/rank；DOLFINx graph partition和shared-facet ghost后的owned/ghost数量仍须实测，不能把输入分片数冒充最终ownership。z轴分段`−10/0/120/130`按10 nm目标得到`1+12+1=14`层；完整3D直角网格是504个hexahedra，但本mesh-only动作只建36个二维quad，不建完整3D网格。旧A1的504个3D cells只作几何轴线交叉核对，不当作2D内存校准。

可复查的源位置和SHA如下，均对应本节source HEAD：

| 文件 | SHA256 | 本预算使用的入口 |
|---|---|---|
| `src/geometry/mesh_builder_3d.py` | `a423f197bfe4eedfd2761738bfe518552d5357e80086b056491d052e32ee21d5` | `_subdivide_piecewise_axis`约219行；`_stage4_axis_plan`约414行；公开`stage4_axis_plan`约587行；`_rank_cell_ids`约657行 |
| `src/modes/cross_section_spaces.py` | `0bf8a74ea72705e06d13bf710cb542eed1b779ce853ee0938004701e81dc47b0` | `_structured_quad_mesh`约177行；`_cross_section_epsilon`约243行；`build_matching_cross_section`约280行；`build_cross_section_spaces`约357行 |
| `src/common/config_3d.py` | `ab58064f507bc1802d8cda0b2497ec6740eb8c07b4697672ef6263d0fadc460c` | 冻结周期、矩形边界、domain和mesh target字段来源 |
| `src/common/task42_phase_admission.py` | `a13db5302dcbe4ef05c022ff4a5e24bb97e544d344ec5fd6f728ffe9656ddd7a` | `qep_cross_section_mesh`分配前阶段入口 |
| `src/io/task42_hybrid_budget.py` | `3f2f7673637e16ced86b5b89eff268ddb39c2d7910560b4b8af3abb9bc8f1b27` | 输入/预算basis与阶段Delta合同，不提供本候选的实际mesh测量 |

预算按单rank同一阶段的保守同时驻留项清点：x/y/z轴规划与短暂数组/元数据暂按4 KiB；49个二维点的Python tuple/list暂存与784 B float64坐标数组约7 KiB；最多5个本地quad的Python cell-list及160 B int64连接数组约2 KiB；cell→vertex、cell→edge、edge→vertex、edge→cell稀疏索引主体按64位索引上算`(181+181+253+229)*8=6,752 B`；索引映射、局部计数与小型receipt暂按8 KiB。已知输入与拓扑payload预算按32 KiB/rank向上取整。另预留16 MiB/rank，覆盖DOLFINx C++ mesh/coordinate/index maps、graph partition、MPI元数据、allocator余量；这是明确的预测性库开销津贴，不是实测值、硬上界或数学保证。预计MPI8全作业新增Delta为`8*(16 MiB+32 KiB)=134,479,872 bytes=128.25 MiB`。构造`points`和`cells`时Python容器与NumPy输入阵列会重叠；`mesh.create_mesh`可能再保留/复制原生对象，之后拓扑连接另分配邻接结构。上述32 KiB源可枚举项与16 MiB未校准库津贴按阶段重叠预算相加；若后续测得实际峰或对象超出预算，必须在门内拒绝并重新审核预算，不能把该预测写作实测。

若C最终为256 GiB，则本候选W=`max(8 GiB,0.05C)=12.8 GiB`；实际运行前仍须新鲜核算C、整作业J、MemAvailable和有限祖先headroom。以上是2026-10-19 mesh-only执行前的预测记录；当时owned/ghost和测量尚未取得。随后实际mesh与p6空间阶段已完成，其实测与独立预算见下方最新小阶段收口；本历史段中的预测未被改写为实测。代码原路径的DG0 epsilon会继续构建材料函数空间，因此此次仅用获准的窄停止路径采集网格，之后另在mesh已驻留的阶段门下调用生产`build_cross_section_spaces`及collapse。该动作未创建DG0/MPC/QEP/traction/增广矩阵/factor/solve。

## A2 MPI8 p6截面空间与collapse sizing（2026-10-19）

本阶段用同一冻结几何和用户Si输入，重新构造36个二维四边形截面网格，然后调用生产N1curl(p6)×Lagrange(p6) mixed-space builder及两次collapse。通俗地说，mixed space把横向切向场和纵向标量场放在同一自由度表中；collapse为两类分量分别生成局部到全局编号，后续周期约束需要这些编号。本阶段只量得这些对象大小和分布，不创建约束或物理算子，也没有解Maxwell方程。

身份为分支`task42hybrid_az90_50x50_17x20_0p7nm`、HEAD `7e0529424199f63145e69fcc6064f26f571333c4`、input SHA `42f486012a38f67a3d6cbdf84801c1bdf9e16e4733f8b1211f7f01f446b39c94`、用户材料记录SHA `19dd3e99663580bf3eb4076e90f55597054c6a7da8c177b02536a274fbf0ab65`。本次新rank map为`[1,5,2,13,14,8,4,22]`，MPI8 ABI实际affinity与请求逐rank一致；PETSc为complex128/Int32，六类数学线程均为1，内存策略为default，`Mems_allowed_list=0-1`覆盖节点全部内存。正式候选→ABI→service链和源绑定见[本阶段closeout](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_space_only_mpi8_attempt_20261019T124500Z/space_only_closeout.md)。

| 观测 | 实测 | 解释与边界 |
|---|---:|---|
| 二维mesh | 36个quad、49个owned全局顶点、84条owned全局边 | 使用生产默认graph partitioner与shared-facet ghosts；rank ghost和是50个cell、106个vertex、149条edge的重复存储，不是新的全局实体。z轴仅保存stage4规划点，未建立3D mesh |
| N1curl p6 | 全局2664个scalar DoF；每cell 84项；entity DoF为0/6/60（vertex/edge/cell） | Basix实际family `N1E`，本次metadata中的coefficient表84×98；非公式外推 |
| Lagrange p6 | 全局1369个scalar DoF；每cell 49项；entity DoF为1/5/25 | 每个space使用新rank map的local-to-global、owned/ghost和cell DoF数组 |
| Mixed / collapse | Mixed全局4033；两个collapse map及rank NPZ均保存 | 8份rank NPZ重开后30个numeric arrays/rank均finite、无object dtype，name/shape/dtype/payload及文件SHA与summary相符 |
| Boundary inventory（离线） | 每侧Hcurl 36个、H1 37个边界DoF；周期slave候选72+73=145 | 由本次网格/实际cell maps/Basix entity DoF重新枚举；只生成候选inventory，没有构造MPC或constraint transform |

资源门沿Task42原合同执行：C=`274,877,906,944 B`（256 GiB）、R=`412,316,860,416 B`（384 GiB）、W=`13,743,895,348 B`。mesh前J=`880,795,648 B`、Delta=`134,479,872 B`，MemAvailable=`1,589,807,603,712 B`，要求值`426,195,235,636 B`；space/collapse前J=`920,141,824 B`、Delta=`2,147,483,648 B`，MemAvailable=`1,589,799,108,608 B`，要求值`428,208,239,412 B`。两阶段门均通过；释放对象后runtime J=`931,389,440 B`且MemAvailable=`1,589,796,442,112 B`，运行门通过。space阶段2 GiB Delta由八个`260,046,848 B` rank envelope（合计`2,080,374,784 B`）加`67,108,864 B`全局service/controller margin组成；每rank envelope中的可枚举项约1.31–1.35 MB，另含64 MiB未校准Basix/DOLFINx/PETSc/原生库与allocator津贴、1 MiB writer缓冲和剩余余量。它是本次小型mixed/collapse阶段的准入预测，不是实测峰或已证明上界，不可转给MPC/QEP/traction/factor。

space-only全作业J有三个独立快照：分配前`920,141,824 B`；分配后、释放前`928,604,160 B`，相对分配前增加`8,462,336 B`；释放后`931,389,440 B`，相对分配前增加`11,247,616 B`。这些是端点采样，不是连续峰；释放前最大rank VmHWM为`116,457,472 B`。候选开始至service终态/owned cleanup的唯一parent wall为`18.534567955 s`，其中systemd-run client到unit终态子包络`2.62739977 s`已包含，不另收费。Invocation `a176061c21da44dcb19322f47ef0953c`，unit `task42-a2-space-only-20261019T124500Z.service`以rc0结束，NRestarts=0；同Invocation live cgroup终态确认后，登记的8个rank及service-main共9个PID/start_ticks均缺席，清场核验通过。该费用独立记在[fee append](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_space_only_mpi8_attempt_20261019T124500Z/space_only_fee_append.json)，没有计入pytest账目、没有按rank倍增。

下一步MPC初始payload估计仅按145个候选slave关系、每关系两个int64编号和一个complex128系数、146个int64行偏移计算：`145×(8+8+16)+146×8=5,808 B/rank`；若八rank各保留完整映射则46,464 B。这个数只覆盖公式列出的数组主体，假定每个slave恰有一个master；它未包括PETSc/MPC原生对象、通信/ghost映射、Python容器和临时复制，且边界相位/符号配对尚未由实际MPC验证。它不是下一阶段完整Delta；必须在MPC分配前另行绑定并审核预算。现有space objects和mesh已释放。本段记录截至2026-10-19的空间/collapse边界；随后约束、transform与Bloch阶段更新见下节。

## A2 constraints、transform、Bloch与离线装配支持（2026-10-20）

同一完整50×50 nm横截面、用户Si材料和MPI8 p6布局已连续取得周期关系、PETSc constraint transform和Bloch插值的小阶段证据。周期关系实际有145条：transverse 72、longitudinal 73；早期raw summary中的两个零计数是rank 0本地结果，rank 0没有slave行，不能解释成全局无约束。八rank arrays和为145，原raw未修改。`C` transform形状4033×3888，保存CSR复核为4033个结构位置；`nz_allocated=24198`、`mallocs=0`是本次transform的MatInfo，不是物理算子内存数据。

保存映射重算的Bloch插值relative L2分别为transverse `6.256641475675839e-16`、longitudinal `6.606863190803519e-16`、combined `6.268518472563376e-16`，对应最大绝对误差为`2.3803347352315634e-14`、`5.320968983789313e-15`、`2.3803347352315634e-14`。旧离线closeout把纵向最大值转录为总体最大值；原17项工件未改，派生更正见[更正记录](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_bloch_interpolant_mpi8_attempt_20261020T073757Z/offline_operator_sparsity_20261020T074900Z/derived_correction_20261020T080656Z/metric_correction.md)。pre-Bloch资源gate为`pass`、`errors=[]`。这是边界配对/方向/相位检查，不是Maxwell残差。成功MPI8 service Invocation为`e2818a1a04a740d7b8fb3149f4225dd9`，transform与Bloch同一parent wall `3.16060316 s`，owned清场记录闭合。

离线脚本把每cell 133个mixed DoF产生的36×133²=`636,804`候选行列对排序、去重，得到full/reduced/`A*C`结构支持626,689/624,672/626,689，`C`和`Cᴴ`各4033。11对象结构payload模型为`113,392,100 B`，最大单rank`16,042,868 B`；这些只是稀疏数组payload，不是实际物理矩阵NNZ或内存Delta。pair分析的512 MiB阶段门通过，预计暂存增量`122,444,388 B`。当时的装配草案只列出可量化项：DG0系数payload预测`1,376 B`、单个`133×133` complex128局部张量条件尺寸`283,024 B`和11对象结构payload。它没有覆盖FFCx/JIT原生峰、实际物理矩阵预分配/stash/MPI、`CᴴAC`产品工作区、PEP、两侧Schur/traction或MUMPS fill，因此当时不能给完整装配Delta；随后已另行完成一次full-K0 sizing，见下节。

mesh、space、constraints、transform与Bloch的各阶段Delta、唯一parent wall、首次reshape/helper/schema失败均列于[Task42 A2 test/费用摘要](outcomes/test_summary.md)。五个pair数组、脚本、gate、SHA清单和完整预算索引见[A2离线closeout](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_bloch_interpolant_mpi8_attempt_20261020T073757Z/offline_operator_sparsity_20261020T074900Z/offline_operator_sparsity_closeout.md)。离线脚本不增加Task42费用条目；没有建立物理矩阵或运行QEP/PEP/KSP、factor或solve。A2仍`pending-sizing`且fail-closed。下一步建议另审一个有独立Delta门的tiny 36-cell p6装配测量，从DG0/FFCx与一个实际物理算子开始，取得rank-local MatInfo、stash和分配快照后再决定后续边界；本离线草案不自动放行任何物理算子分配。

## A2单个full-K0 sizing与离线reconciliation（2026-10-20）

本阶段复核的是同一36-cell、p6/g1、DG0/q16、MPI8的既有K0工件，不重跑数值。这里full表示未施加C约化前的截面QEP系数矩阵，不是完整3D Maxwell系统。Full K0为4033×4033，8个rank各assembly一次；独立checker核验24个rank数组工件的SHA、identity、finite值、CSR结构和完整连续row ranges。rank-sum `nz_used=nz_allocated=626,689`，CSR payload合计`12,549,944 B`，最大rank payload`1,787,860 B`。这只是一个full K0 sizing结果，不是K1/K2/M或约化NNZ，也不构成QEP/PEP或A2物理资格。

原始`k0_only_summary.json`为`passed`，service/ExecMainStatus为0；原`k0_only_completion.json`仍为`failed`，原controller把四个summary字段误当顶层字段读取。派生只读checker按真实嵌套schema验证，正例的24份工件通过、11类负例全拒绝；它不改写原completion、summary或postmortem v1/v2。v2中的`all_rank_CSR_preallocation_and_finite_checks_passed=true`实际只由`global_nz_used == 626689`生成，不代表它检查了allocated、hash或finite；独立checker另行重算了hash/finite/CSR/preallocation/row coverage及used/allocated一致性。

| 观测 | 字节/状态 | 边界 |
|---|---:|---|
| J：pre-UFL form | 1,022,046,208 B | 单独时间点 |
| J：compiled form后 | 1,035,526,144 B | 单独时间点；FFCx门通过 |
| J：K0 preallocation | 1,040,465,920 B | 单独时间点；K0门通过 |
| J：assembly后 | 1,073,405,952 B | 单独时间点 |
| J：destroy后 | 1,096,871,936 B | 单独时间点；快照不构成同步峰 |
| MatInfo memory | 0 | PETSc字段值，不是进程RSS为0 |

原completion中`k0_output_summary_present_and_valid=false`及controller failed分类继续保留；派生清场依据同Invocation身份审计、已登记PID/start_ticks缺席和cgroup directory removed。收据明确`cgroup_proven_empty=false`。Stop成功后unit被回收，随后reset-failed rc1 `Unit not loaded`不是另一次清场失败。

候选链、MPI8 ABI和service parent wall分别为`10.890860134 s`、`1.410828952 s`、`4.176308795 s`；K0嵌套stage wall `1.445850019 s`已包含在service中，不重复计费。离线checker parent wall `not_measured`，没有新增费用条目。FFCx cold/cache-hit、独立编译wall、独立assembly wall和同步峰均未测。

独立核验错误向量、每rank CSR、schema路径、原始completion保留和清场边界见[K0 reconciliation](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_k0_summary_reconciliation_offline_20261020T121140Z/offline_k0_reconciliation.md)及机器结果`offline_validation_results.json`。下一阶段K1及一次`Cᴴ K1 C`的来源、对象重叠、预测Delta和未知项见[预算草案v2](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a2_k0_summary_reconciliation_offline_20261020T121140Z/next_operator_reduction_sizing_proposal_v2.md)。该草案是离线建议，不是运行授权：K1/K2/M、约化以外对象、PEP/QEP、factor/solve与A2物理结果仍未运行；Task42资源门与fail-closed策略不变。
