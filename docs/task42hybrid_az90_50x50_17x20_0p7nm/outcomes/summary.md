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
| 完整Full3D求解与官方输出 | 未运行 | `not_run`：无正式assembly、QEP、p6 MUMPS factor、恢复、R/T/A或完整场 | A1小矩阵/资源合同已接线；正式入口待fresh MPI8审核，见[response_v1](../response_v1.md) |

## 实施和测试矩阵

| Attempt | 范围 | 结果 | 耗时/内存口径 | 决策 |
|---|---|---|---|---|
| `082736Z` | serial native preflight wrapper | pytest未启动；本地解释器路径检查错误地把venv symlink解析路径当作错误解释器 | pytest wall 0 s；不计pytest费用 | 保留原收据；后续activation ABI实证通过 |
| `082837Z` | serial A0及3个相关公共入口/profile selector | 1 failed；Poynting解析公式比较容差小于观察到的binary64运算差，`-x`使余项not_run | GNU time wall 2.43 s，peak RSS 208284 KiB | 原失败保留；放宽的是独立公式交叉核对精度，不是物理门 |
| `082953Z` | A0测试文件及3个相关selector | 12 passed | GNU time wall 11.72 s，peak RSS 320268 KiB | 通过；serial ABI complex128/Int32、线程变量全1、source前后不变 |
| `083132Z` | MPI2 boundary-fitted mesh/volume selector | rank 0、rank 1均通过 | GNU time parent wall 1.47 s，parent记录peak RSS 113944 KiB | 通过；rank CPU 4/12、私有pytest临时目录、两rank ABI及source一致 |

耗时来自GNU `/usr/bin/time`记录，按GNU time输出精度保留到0.01秒，不是高精度单调时钟测量。peak RSS是对应计时命令收据中的GNU time值，不是Task42作业进程树/cgroup总峰。3个实际pytest parent attempt的记录值合计15.62秒；被preflight拦截的082736Z未启动pytest，计0秒。分项收据及精确argv见[测试摘要](test_summary.md)与ignored `results/task42hybrid_az90_50x50_17x20_0p7nm/`。

## A1最小接线方案（A0阶段规划，实际状态见下节）

| 后续项 | 最小路径 | 当前状态 |
|---|---|---|
| Task42显式软48 h策略 | `run_case`→`task038_launcher._run_worker`→Full3D direct；仅Task42 opt-in不因elapsed terminate，普通Task038行为保持 | 待实现；当前dat的172800秒仍是硬停风险，不可启动正式PDE |
| 分阶段资源门 | 复用kernel MemAvailable、process-tree/cgroup/有限祖先样本和既有authority；mesh、assembly、symbolic、numeric、recovery/输出前分别核实际Delta | 待实现；不要求启动时空置整个cap |
| direct LU接线 | 优先在`_solve_augmented_system`连接可选stage gate/LU bridge，并使用`petsc_lu_stage.py` symbolic/numeric callback；不把MUMPS direct伪装成action接口 | 待静态接线设计和定向回归 |
| 残差与完整输出 | 以Task42 opt-in packet保存原A、RHS、解、原残差和身份；恢复后重算full true residual，通过后才产official R/T/A、A_volume、E/H和全报告衍射级 | 未实现、未运行 |

Task42 §7的初始与分阶段预算使用R=384 GiB、Cmax=min(1.5 TiB, MemTotal−R)、13.5 nm的C=min(256 GiB,Cmax)、warning=0.9C、W=max(8 GiB,0.05C)。大分配前要求`J+Delta+W<=C`、`MemAvailable>=R+Delta+W`及每个有限祖先cgroup的headroom至少`Delta+W`，其中J=max(process-tree RSS,dedicated cgroup current)，Delta只记当阶段新分配。48小时是成功目标，不是强杀线；不能仅通过改dat文本声称此策略已经接入。A0未申请或消耗任何大型计算额度，也没有启动正式Full3D作业。

## A1实现与小型合同验证状态

Task42 opt-in现在将输入`timeout_seconds=172800`作为48小时软目标：达到时记录软目标状态并继续，不因elapsed本身终止worker；ordinary Task038保留既有超时。硬资源保护继续按整作业J=max(process-tree RSS、已证明适用的dedicated cgroup current)、kernel MemAvailable和有限祖先状态执行。大分配前使用`J+Delta+W<=C`、`MemAvailable>=R+Delta+W`和祖先headroom≥`Delta+W`；运行期硬门检查`J<=C`、`MemAvailable>=R`，不重复预留W。当前参数为R=384 GiB、Cmax=min(1.5 TiB,MemTotal−R)、C=min(256 GiB,Cmax)、W=max(8 GiB,ceil(0.05C))、warning=0.9C。

| 已接线路径 | 证据与边界 |
|---|---|
| `run_case`→Task038 launcher→Task42 Full3D direct | 软时间目标和启动/运行资源合同有定向测试；ordinary Task038控制保持原语义 |
| Task42阶段authority→mesh/function-space/assembly→MUMPS symbolic/numeric→recovery | whole-job root与阶段Delta沿现有callback贯通；小型resource contract批次最终12 passed，但其parent wall未测 |
| 同一MUMPS factor的symbolic→numeric→MatSolve→pre-recovery packet→destroy | 8×8 native serial/MPI2合同通过；同C bridge、同artifact覆盖`ICNTL(14)=None`默认分支和显式40控制 |
| full residual、writer与active-trace Delta | 小型原方程packet/恢复残差边界、writer成功与本地写失败同步拒绝、rank-local gather驻留公式均有定向回归；无正式p6场 |

可计费的17个pytest parent monotonic wall合计32.796723016秒，不按MPI rank数倍增。资源fixture三次pytest parent wall为`not_measured`，其pytest-reported 0.56/0.36/0.41秒不充当parent费用；MPI2 wrapper在pytest启动前失败的attempt不计pytest费用。完整attempt状态、失败保留路径和当前15项source manifest见[A1机器记录](a1_contract_validation.json)及[测试摘要](test_summary.md)。

本轮不证明正式8-rank资源资格：轻量MPI2记录未采集每rank真实`sched_getaffinity`；Task42正式路径还需fresh核验rank实际affinity、default/unbound与全正常RAM节点scope，并提供OOM/disk保护的实际宿主证据。13.5 nm正式assembly/QEP/MUMPS全规模分解、场恢复、R/T/A、衍射输出均为`not_run`，需主控另行审核正式fresh MPI8入口。
