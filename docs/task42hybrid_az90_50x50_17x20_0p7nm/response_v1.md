# Task42 执行回应 v1：A0 输入与几何入口

## 本阶段结论

| 项目 | 结果 | 状态和边界 |
|---|---|---|
| Task42 A0 | 公共输入、材料来源、dry-run、Floquet/外通道、边界拟合小网格和体积检查完成 | `passed_with_qualifications`；不代表Full3D方程求解或资源资格 |
| 13.5 nm直接参考 | 已注册输入 `13p5nm_p6h10_full3d_direct_mpi8.dat` | `not_run`；待A1资源与时间策略接线 |
| 0.7 nm | 两波长Si材料输入已冻结，外通道键可独立枚举 | `not_run`；本阶段没有建立0.7 nm网格、QEP或求解 |
| ordinary默认 | 未改变 | Task42仍由显式model/profile身份进入 |

13.5 nm模型冻结为方位角90°、掠入射1°、s偏振、50×50 nm周期、居中17×20 nm光栅；光栅高120 nm，z域为−10到130 nm，接口位于10/110 nm，p6/h10。A0验证实际公共入口能解析该模型并给出一致的场与外通道配置。A0的真实边界拟合网格检查确认材料界面与网格平面对齐，并核对小网格上的材料体积。

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

## A1最小接线方案

当前dat中的`timeout_seconds=172800`会沿`task038_launcher._run_worker`的普通Full3D分支触发terminate，因此不能直接把A0输入交给正式PDE。A1应在现有`run_case`→`task038_launcher`→Full3D direct adapter路径增加显式Task42 opt-in策略；普通Task038输入和默认行为不变。

| 接线点 | 最小方案 | 保留的边界 |
|---|---|---|
| soft 48 h目标 | Task42运行策略把48 h作为进度/冷运行目标；过时继续报告未达目标，不以elapsed触发terminate。仅Task42分支关闭时间强停 | CPU、内存、磁盘、OOM和异常退出保护仍有效；不改通用launcher默认 |
| 资源authority | 复用现有kernel MemAvailable、process-tree RSS、dedicated cgroup current及有限祖先headroom采样/authority；每次大分配前给出J、真实新增Delta和W | R=384 GiB；Cmax=min(1.5 TiB, MemTotal−R)；13.5 nm的C=min(256 GiB,Cmax)；W=max(8 GiB,0.05C)；要求J+Delta+W≤C、MemAvailable≥R+Delta+W、各有限祖先headroom≥Delta+W。未知量拒绝下一阶段分配；swap只观察 |
| 分级Gate | 在mesh、assembly、symbolic、numeric、recovery/输出各现有阶段边界调用同一authority；LU复用`petsc_lu_stage.py`的symbolic/numeric callback gate | J=max(进程树RSS,dedicated cgroup current)；已驻留对象不重复计入Delta；不能以启动时预留整个C替代逐阶段预算 |
| Full3D direct与快照 | 优先在现有direct `_solve_augmented_system` 接入可选stage gate/LU bridge，保持MUMPS direct身份；只有证实现有等价接口与官方快照合同兼容时才复用它 | `linear_solver_port`面向迭代/action，不能伪装direct；`dtn_port_3d._external_snapshot_allows_official_rta`当前要求`no_global_factor`成立，真正使用全局MUMPS factor时不能伪标。若direct路径进入该检查，须设计诚实保留direct身份的Task42快照核验。为Task42显式扩展pre-recovery packet identity，保留原A、RHS、解和原残差，恢复后重算原方程true residual |
| 正式输出 | 仅在原A残差及任务Gate通过后保留official场与R/T/A、A_volume、完整衍射级、参考面E/H、清理与identity | setup或单次LU成功不构成数值pass；所有阶段和清理费用按唯一Task42运行记录 |

本方案是待实现的A1最小接线，不是已完成的资源资格或运行授权收据。正式Full3D direct PDE、QEP、assembly、symbolic/numeric factor、recovery、物理输出和48小时目标均为`not_run`。下一步由主控审核此接线并派发A1静态实现/回归；完成资源和软时间策略前不启动PDE。
