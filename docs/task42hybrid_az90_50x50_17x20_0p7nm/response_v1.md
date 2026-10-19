# Task42 执行回应 v1：A0 输入与 A1 正式运行终态

## 本阶段结论

| 项目 | 结果 | 状态和边界 |
|---|---|---|
| Task42 A0 | 公共输入、材料来源、dry-run、Floquet/外通道、边界拟合小网格和体积检查完成 | `passed_with_qualifications`；不代表Full3D方程求解或资源资格 |
| 13.5 nm直接参考 | 最近一次正式A1于2026-10-19启动；数值worker写出了残差、端口功率和场文件 | worker summary标记`official_result=true`，但整场因最后一次whole-job资源authority不完整而`refused`；不能把整场称为通过 |
| 0.7 nm | 两波长Si材料输入已冻结，外通道键可独立枚举 | `not_run`；本阶段没有建立0.7 nm网格、QEP或求解 |
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
| 体吸收 | A_volume=`0.6883937861128354`；A_port−A_volume=`1.2090530798758437e-9`；R+T+A_volume=`0.9999999987909469` | 吸收按`0.5*k0*Im(epsilon_r)*|E_total|^2`对Si物理材料单元积分，空气与PML排除 |
| 零级反射 | R00_s=`0.254974601609543`；R00_p=`4.5883121973545914e-24`；R00_total=`0.254974601609543` | s/p分别列出；R00与全168项反射总和是不同量 |
| 外层RUN / public / service | RUN exit 1、public driver rc 3、service ExecMainStatus 3，Invocation=`048a5d671150436f9c05cd1bfb5a9d29` | RUN最终分类为`task42_runtime_resource_gate_refused`；三层退出状态不能合并成数值失败或通过 |

### 场文件、packet与168个外通道

PVD列出8个rank VTU，全部可由原生VTK reader打开。每个rank文件都含E总场、入射端口E场的real/imag/abs以及H场的real/imag/abs；数值数组均有限，向量数组为每点3分量，幅值数组为每点标量，另有cell `domain_tag`。rank cell数合计504；rank间共享点使point数不可直接求和为全局唯一节点数。worker summary只列出了E数组，实际VTU还存有H数组。完整场样本NPZ内E/H为complex128、形状`(5,40,40,3)`，两个界面切片为`(2,40,40,2)`，均有限；其z平面是10/30/60/90/110 nm，档案SHA与metadata和worker summary一致。它是本次场的采样档案，不是解析精确解（summary中`exact_reference_available=false`）。

168项DtN输出含84个top、84个bottom，以及84个s、84个p；166项标记为propagating。输出中的`auxiliary_index`连续覆盖0–167，并按输出数组顺序排列。与RUN manifest中的168个external-mode key集合完全一致，但key顺序不同：manifest和输出表不能按两个数组位置直接配对，必须按每行side/m/n/polarization关联。逐行`power_ratio`独立求和得到R=`0.2550072646379845`、T=`0.05659894804012687`，与端口summary仅有末位舍入差。

pre-recovery packet含8个complex128 shard，每片实际存`solution`和`rhs`，数组长度与连续ownership range相等、值均有限；manifest identity hash及其中source/input/physical/resolved-config SHA与本RUN相符，8片文件SHA均匹配。Full-FE与active-trace canonical导出也各有8片，manifest及16片SHA均匹配；类型均为complex128，packet总数分别为341436和114636，本地重复数均为0。这两个canonical manifest本身不含独立RUN/input/source identity，身份来自其所在RUN目录及父manifest，且其extractor audit中的`hcurl_norm`与`trace_mass_norm`均为`not_qualified`。RUN中没有BP档案。

### 端口结果与探针诊断不能混算

正式端口R/T来自边界z=130/−10 nm上的DtN辅助模态振幅，并按入射功率归一。`power_metrics_3d.json`是另一种诊断：它在z=125/−5 nm均匀层探针面，以E/H Fourier最小二乘拟合传播方向（105个空间级、210个偏振通道）；拟合R=`0.2546430430395836`、T=`4.030194817781968e-5`、A=`0.7453166550122385`。同文件的采样净通量用探针面E及由有限元curl重建的H积分，不做衍射级分解，R=`0.25508219821040456`、T=`0.07257569600562415`、A=`0.6723421057839714`。两种探针诊断均以`incident_power_code_units=21.815508046604222`归一，但输出面和算法不同于端口模态；数值与DtN端口结果明显不同。top E/H拟合最大残差为`0.9980693005722018`，bottom为`2.0411909699601356e-10`。这里的拟合残差不是线性求解残差。现有证据不确定这些差异的成因，且top拟合残差很高，故不能拿探针诊断替代端口结果，也不能仅凭能量闭合称所有场/衍射诊断合同均通过。

### 资源拒绝、费用与sampler边界

最后一个完整runtime样本在elapsed `312.8408444840461 s`仍通过；elapsed `313.3017449709587 s`的下一样本拒绝。该样本列出10个进程（RUN root、mpiexec及8 ranks），但`all_status_readable=false`；8个rank两次读取均保持相同PID/start_ticks和状态`R`，`/proc/status`中`VmRSS`与`VmSwap`都缺失，bounded reread后仍为`refused_same_identity_status_still_incomplete`。因此whole-job J是unknown，不能填0、引用旧RSS或用专属cgroup current代替完整树。cgroup当时可读且current为`11119267840` bytes、直接`cgroup.procs` member_count=3；`MemAvailable=1859305144320` bytes、C=`274877906944` bytes。有限祖先硬限不适用。`member_count=3`与进程树10项只是同时记录的线索，无法证明进程退出竞态；最后读取状态仍为R。

原gate错误向量同时包含`whole_job_process_tree_is_incomplete_or_unreadable`和`runtime_whole_job_J_exceeds_Task42_C`。第二个标签并非已测超C证据：当前`task42_runtime_memory_gate_from_authority`在resident cap gate为false时不分J未知或已测超限，都会加该标签。建议只修错误分类，不改fail-closed判定：J已知且测得超过C时才写“超过C”；J未知时只写authority unknown/incomplete。主控审查前本阶段未修改生产代码；拟用完整样本正常通过、明确终止PID的边界、存活身份持续缺字段、PID复用、适用祖先缺失、已知J>C六类纯fixture核边界。

public completion记录parent wall `313.734830358 s`，作为Task42本次正式attempt唯一费用，不乘MPI ranks、不叠加阶段采样；attempt的RUN exit1、public rc3、service rc3分别保留。最终进程组收到TERM后退出，未用SIGKILL。主控真实host终态读取确认Invocation的MainPID=0、ControlGroup为空、NRestarts=0、登记进程全缺席。此前`20261016T121844.178539Z`正式RUN的资源拒绝及`20261018T115039.812072Z`旧packet布局拒绝均保留原件；后者未产生新factor/solve。此parent wall已在[唯一费用append](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/task42_fee_append.json)记录一次；逐文件SHA见[审计收据](../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/offline_terminal_audit.json)。本次额外正式A1额度已用完，本阶段不授权再跑A1。A2与0.7 nm仍按原task的前置资格和内部审核推进，目前均未启动、未获本阶段放行。下一步是sampler错误分类的最小修正及存档探针差异定位，不申请A1重算。
