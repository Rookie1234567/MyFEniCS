# Task42 A0 阶段摘要

## 任务范围与结论

本阶段建立并核验Task42的13.5 nm Full3D direct输入身份、两波长Si材料来源、公共validate/dry-run入口、外通道/衍射报告范围，以及一份小型边界拟合网格。A0结论为 `passed_with_qualifications`：这些检查说明输入和轻量几何契约一致，不证明正式有限元方程、QEP、直接分解、资源门或物理输出通过。

| 项目 | 冻结值/结果 | 数据身份与边界 | 证据 |
|---|---|---|---|
| 分支与基线 | `task42hybrid_az90_50x50_17x20_0p7nm`；起点`94700f95f2bef02e2359e6ca89872c11e65978fb`；A0测试时HEAD `f870a9a1ac609f584c2ebde7b5f870fdf191b480` | measured source identity；Task041旧stash保持隔离 | Git history / ignored test receipts |
| 13.5 nm物理输入 | 方位90°、掠入射1°、s偏振；50×50 nm周期；居中17×20 nm Si光栅，高120 nm；z域−10..130 nm；Hybrid内部接口平面10/110 nm，Full3D外DtN端口位于z域边界；p6/h10 | frozen input, not a solved field | [`13p5nm_p6h10_full3d_direct_mpi8.dat`](../../../input/official/task42hybrid_az90_50x50_17x20_0p7nm/13p5nm_p6h10_full3d_direct_mpi8.dat) |
| 材料 | 两波长光栅和基底均Si；13.5 nm与0.7 nm的Delta/Beta由用户提供 | derived n/epsilon；来源`user_supplied_delta_beta`，非外部实验资格 | [用户常数记录](../materials/user_supplied_si_optical_constants.json)，SHA256 `19dd3e99663580bf3eb4076e90f55597054c6a7da8c177b02536a274fbf0ab65` |
| 外通道库存 | 13.5 nm空气侧42个空间键、每个s/p两种偏振；0.7 nm空气侧16031个空间键 | independent lattice enumeration + actual key inventory；0.7仅枚举，无mesh/QEP/PDE | `test_task42_air_order_inventory_matches_independent_lattice_and_actual_keys` |
| 衍射报告范围 | m=3、n=7覆盖当前13.5 nm所有合法外部键 | measured from actual enumerated keys and reporting-order generator；仅报告范围，不改变DtN keys | `test_task42_public_validate_and_dry_run_bind_the_13p5_si_case` |
| 小型网格 | boundary-fitted；空气/基底/光栅体积分别284200/25000/40800 nm³ | measured on the small test mesh; not the production p6 model mesh | MPI2 `test_task42_builds_the_boundary_fitted_material_mesh_with_expected_volumes` |
| A0阶段的完整Full3D求解 | 当时未运行 | A0只证明输入和小网格边界；之后A1于2026-10-19启动正式MPI8 direct并写出worker数值summary、packet、E/H及端口文件，但外层最终因whole-job资源authority不完整而拒绝 | 当前A1终态见下文及[response_v1](../response_v1.md) |

## 实施和测试矩阵

| Attempt | 范围 | 结果 | 耗时/内存口径 | 决策 |
|---|---|---|---|---|
| `082736Z` | serial native preflight wrapper | pytest未启动；本地解释器路径检查错误地把venv symlink解析路径当作错误解释器 | pytest wall 0 s；不计pytest费用 | 保留原收据；后续activation ABI实证通过 |
| `082837Z` | serial A0及3个相关公共入口/profile selector | 1 failed；Poynting解析公式比较容差小于观察到的binary64运算差，`-x`使余项not_run | GNU time wall 2.43 s，peak RSS 208284 KiB | 原失败保留；放宽的是独立公式交叉核对精度，不是物理门 |
| `082953Z` | A0测试文件及3个相关selector | 12 passed | GNU time wall 11.72 s，peak RSS 320268 KiB | 通过；serial ABI complex128/Int32、线程变量全1、source前后不变 |
| `083132Z` | MPI2 boundary-fitted mesh/volume selector | rank 0、rank 1均通过 | GNU time parent wall 1.47 s，parent记录peak RSS 113944 KiB | 通过；rank CPU 4/12、私有pytest临时目录、两rank ABI及source一致 |

耗时来自GNU `/usr/bin/time`记录，按GNU time输出精度保留到0.01秒，不是高精度单调时钟测量。peak RSS是对应计时命令收据中的GNU time值，不是Task42作业进程树/cgroup总峰。3个实际pytest parent attempt的记录值合计15.62秒；被preflight拦截的082736Z未启动pytest，计0秒。分项收据及精确argv见[测试摘要](test_summary.md)与ignored `results/task42hybrid_az90_50x50_17x20_0p7nm/`。

## A1最小接线方案（A0时的规划记录）

以下记录保留A0结束时对A1的计划状态；A1后来已经接线。最近一次正式计算及历史顺序见本摘要末尾。

| 后续项 | 最小路径 | 当前状态 |
|---|---|---|
| Task42显式软48 h策略 | `run_case`→`task038_launcher._run_worker`→Full3D direct；仅Task42 opt-in不因elapsed terminate，普通Task038行为保持 | 已实现并经过合同验证；正式运行未因48h时间目标停止 |
| 分阶段资源门 | 复用kernel MemAvailable、process-tree/cgroup/有限祖先样本和既有authority；mesh、assembly、symbolic、numeric、recovery/输出前分别核实际Delta | 已实现；本次终态因进程树样本字段缺失拒绝，J未知，不是已证实超过C |
| direct LU接线 | 在direct `_solve_augmented_system`使用stage gate/LU bridge；保留MUMPS direct身份 | 小型8×8 native factor生命周期合同已通过；本次正式p6/h10 worker完成数值阶段并写出输出 |
| 残差与完整输出 | packet保存解/RHS及身份，重算full true residual，通过后写R/T/A、A_volume、E/H和完整衍射级 | 本次运行有有限full residual及输出文件；整场仍因资源拒绝未整体通过，端口与探针诊断存在未解释差异 |

Task42 §7的初始与分阶段预算使用R=384 GiB、Cmax=min(1.5 TiB, MemTotal−R)、13.5 nm的C=min(256 GiB,Cmax)、warning=0.9C、W=max(8 GiB,0.05C)。大分配前要求`J+Delta+W<=C`、`MemAvailable>=R+Delta+W`及每个有限祖先cgroup的headroom至少`Delta+W`，其中J=max(process-tree RSS,dedicated cgroup current)，Delta只记当阶段新分配。48小时是成功目标，不是强杀线；不能仅通过改dat文本声称此策略已经接入。A0阶段当时尚未申请或消耗大型计算额度，也未启动正式Full3D；后续A1状态见本摘要末尾。

## A1实现与小型合同验证状态

Task42 opt-in现在将输入`timeout_seconds=172800`作为48小时软目标：达到时记录软目标状态并继续，不因elapsed本身终止worker；ordinary Task038保留既有超时。硬资源保护继续按整作业J=max(process-tree RSS、已证明适用的dedicated cgroup current)、kernel MemAvailable和有限祖先状态执行。大分配前使用`J+Delta+W<=C`、`MemAvailable>=R+Delta+W`和祖先headroom≥`Delta+W`；运行期硬门检查`J<=C`、`MemAvailable>=R`，不重复预留W。当前参数为R=384 GiB、Cmax=min(1.5 TiB,MemTotal−R)、C=min(256 GiB,Cmax)、W=max(8 GiB,ceil(0.05C))、warning=0.9C。

| 已接线路径 | 证据与边界 |
|---|---|
| `run_case`→Task038 launcher→Task42 Full3D direct | 软时间目标和启动/运行资源合同有定向测试；ordinary Task038控制保持原语义 |
| Task42阶段authority→mesh/function-space/assembly→MUMPS symbolic/numeric→recovery | whole-job root与阶段Delta沿现有callback贯通；小型resource contract批次最终12 passed，但其parent wall未测 |
| 同一MUMPS factor的symbolic→numeric→MatSolve→pre-recovery packet→destroy | 8×8 native serial/MPI2合同通过；同C bridge、同artifact覆盖`ICNTL(14)=None`默认分支和显式40控制 |
| full residual、writer与active-trace Delta | 小型原方程packet/恢复残差边界、writer成功与本地写失败同步拒绝、rank-local gather驻留公式均有定向回归；无正式p6场 |

可计费的17个pytest parent monotonic wall合计32.796723016秒，不按MPI rank数倍增。资源fixture三次pytest parent wall为`not_measured`，其pytest-reported 0.56/0.36/0.41秒不充当parent费用；MPI2 wrapper在pytest启动前失败的attempt不计pytest费用。完整attempt状态、失败保留路径和当前15项source manifest见[A1机器记录](a1_contract_validation.json)及[测试摘要](test_summary.md)。

本次A1正式运行已有fresh MPI8准入与rank affinity核验；终态资源样本拒绝的原因和不确定性见下节。此前轻量MPI2没有采集每rank真实`sched_getaffinity`，不因此改写其测试边界。


## A1正式13.5 nm运行与离线终态核验

2026-10-19正式运行使用冻结的13.5 nm Si、p6/h10、50×50 nm周期、17×20 nm光栅、高120 nm、az90/grazing1°/s、MPI8。数值worker summary标记`case_status=completed`、`official_result=true`，完整原方程相对残差为`9.306460504345312e-11`。端口模态计算得到R=`0.2550072646379847`、T=`0.056598948040126884`、A_port=`0.6883937873218885`；材料单元体积分得A_volume=`0.6883937861128354`，差`1.2090530798758437e-9`，`R+T+A_volume=0.9999999987909469`。`R00_s=0.254974601609543`、`R00_p=4.5883121973545914e-24`，总和`R00_total=0.254974601609543`。这说明worker记录的残差和主端口能量平衡数值存在；不能据此覆盖外层资源拒绝。

PVD列出8个rank VTU，全部可读；每个文件实际含E和H的real/imag/abs数组，向量为3分量、幅值为标量，所有数值均finite。完整场样本NPZ中的E/H为complex128、`(5,40,40,3)`，界面切片为`(2,40,40,2)`。pre-recovery packet的8个solution/RHS shard以及full-FE和active-trace canonical导出的16片均逐项hash匹配；packet identity与本RUN一致。两份canonical manifest没有独立嵌入RUN identity，其`hcurl_norm`与`trace_mass_norm` audit项均为`not_qualified`。RUN中没有BP档案。168个DtN项的key集合与manifest inventory相等，但有序列表不同；输出auxiliary index 0–167连续。完整布局、字段和逐项SHA见[只读终态审计](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/offline_terminal_audit.json)。

端口R/T由边界z=130/−10 nm的DtN模态振幅得到。另一个`power_metrics_3d.json`记录的是探针z=125/−5 nm的诊断：E/H Fourier拟合R/T/A=`0.2546430430395836/4.030194817781968e-5/0.7453166550122385`，采样净通量R/T/A=`0.25508219821040456/0.07257569600562415/0.6723421057839714`，均按同一incident power code units归一。top E/H拟合最大残差`0.9980693005722018`，bottom为`2.0411909699601356e-10`；拟合残差不是线性求解残差。离线追踪发现底部零级s模态虽标为`propagating=false`仍`power_carrying=true`，其端口透射贡献`0.056559356398515837`被探针的`bottom_propagating`筛选漏掉；这解释探针E/H拟合透射很小的主要部分。5 nm传播差的预期功率比`1.28258713`与实测净通量/端口比`1.28227995`接近，只支持传播差可能贡献，不能证明唯一成因。顶部最大拟合残差`0.9980693005722018`来自反射功率为零的倏逝级`(m=2,n=1,s)`，仍不能解释总反射差。原z=125/−5探针24×24 E/H样本未保存；不能用现存内域NPZ代替。完整边界、缺项和定义见[response_v1](../response_v1.md)及[离线复核记录](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/probe_port_offline_review.json)；这些诊断不改正式结果或构成物理资格。

最后一个完整runtime样本elapsed`312.8408444840461 s`通过；下一样本elapsed`313.3017449709587 s`拒绝。它看到10个进程，但8个worker rank两次都保持相同PID/start_ticks、状态`R`，缺`VmRSS`和`VmSwap`，故完整process-tree J未知。可读dedicated cgroup current=`11119267840` bytes、直接member_count=3；`MemAvailable=1859305144320` bytes、C=`274877906944` bytes。cgroup值不能代替缺失的整树；raw中的`runtime_whole_job_J_exceeds_Task42_C`曾是错误标签，不能证明J>C。后续分类修复后，原样本仍拒绝/incomplete+unknown，错误向量不再含超C标签；已知完整整树J>C仍保留超限标签。该修复不改变门的通过/拒绝、公式或采样顺序，4个定向serial测试通过，细节见[测试摘要](test_summary.md)和[分类回归收据](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/classification_error_vectors.json)。

### 正式A1历史与额度

| RUN时间 | 范围与实际进度 | 因子/求解 | parent wall与费用口径 |
|---|---|---|---|
| `20261016T121844.178539Z` | 原正式A1；资源authority拒绝，保留原记录 | 已发生factor与solve | 沿原attempt收据记账；不在此重复追加 |
| `20261019T034149.351129Z` | 必要重建尝试；authority unknown | 未进入factor/solve | `not_measured`；不补造wall |
| `20261019T062050.882932Z` | 最近一次额外正式A1；数值输出已写，运行期资源authority拒绝 | 已发生factor与solve | `313.734830358 s`，唯一parent wall，已追加一次 |

`20261018T115039.812072Z`旧packet恢复是另一类attempt，没有新增factor/solve；CPU候选、ABI和public prelaunch gate也不算PDE。费用只按各自原始收据保留，不推算缺失wall。额外正式A1额度已用完，本阶段不授权再次运行A1；A2与0.7 nm仍按原task前置资格及内部审核推进，目前未启动、未获本阶段放行。sampler错误分类修正及存档探针差异离线复核已完成；没有A1重算。原RUN、packet、raw与stash均保留。[费用append和审计收据](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/a1_terminal_offline_audit_20261019T064123Z/task42_fee_append.json)已记录该wall一次。

### 后续分类回归与探针/端口离线核验

4个定向serial资源合同测试通过。原062050Z authority重放仍拒绝且`J`为incomplete/unknown；错误向量不再误标`J>C`。分类修复不改变资源公式或门的拒绝行为。pytest报告`4 passed`、`0.22 s`，唯一parent monotonic wall为`0.505579699 s`；pytest PID为`not_persisted`。源码SHA为`4c2c86b57b6c0b98c5503d4c2542f0333dbe7f77e97e5e14ef242ea4835ecd2e`，测试SHA为`cdceb62251304c80b3e7bd318ad94d847053757dc6dfeb9032a540bcaf8ab8`。原样本重放与逐项校验见[分类回归证据](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/classification_error_vectors.json)及[SHA256清单](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/SHA256SUMS.txt)。

底部探针E/H拟合按`bottom_propagating`筛掉了一个`propagating=false`但`power_carrying=true`的Si零级s模态；DtN端口该项透射贡献为`0.056559356398515837`，解释探针E/H拟合T远低于端口T的主要部分。5 nm平面差的预期功率比`1.28258713`、实测净通量/端口比`1.28227995`相近，只支持传播差可能贡献。顶部最大拟合残差`0.9980693005722018`属于反射功率为0的倏逝级`(m=2,n=1,s)`，仍不能解释总反射差。原24×24探针面E/H未存，现存内域NPZ不能替代；未改旧诊断值或生产后处理，也未据此判定物理资格。完整细节见[response_v1](../response_v1.md)与[离线复核记录](../../../results/task42hybrid_az90_50x50_17x20_0p7nm/runtime_gate_error_classification_20261019T070922Z/probe_port_offline_review.json)。
