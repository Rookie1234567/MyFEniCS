归档说明：以下是 2026-10-02 的源码方案，runtime_tests=not_run。原文中的“本次未修改分支”描述方案创建时的动作；本检查点仅归档文档。不可自动导入的草稿片段未纳入此文档交付。

# Public petsc4py LU/MUMPS 后端：有界源码方案

状态：**NEW_UNQUALIFIED_SOURCE / source plan only**。日期：2026-10-02 UTC。这是替换私有 FFI 的接口设计和不可自动导入的源码片段；没有安装、PETSc/FEniCS import、矩阵创建、分析、因子或 PDE 执行，没有修改恢复的 publishedV15、canonical 源码或任何分支。

目标仍为完整三维原尺寸 50×25×140 nm、λ=0.7 nm 的规则基线，以及以后真实非可分三维缺口。资源合同是**整机 decimal 2,000,000,000,000 B、172,800 s、swap=0**，含系统、JIT、装配、所有因子、原空间 outer、恢复和输出。本方案不提供可行性、时间或精度承诺。当前 Python3.12/NumPy2.3.5/SciPy1.17 环境缺少 PETSc/FEniCS；旧 complex 环境和 raw artifacts 不可用。

## 1. 接线位置与最小接口

LU 因子是把一个稀疏块预先分解，再对很多右端做回代；公开接口让 PETSc 自己处理 ABI、排序和内部数据布局。代价是不能沿用旧私有代码的逐阶段暂停方式。

| 恢复源 | 当前作用 | 后续最小改动 |
|---|---|---|
| `src/solvers/fullspace_v17_p3_oracle.py:165` | `_MumpsFactor` 用 ctypes、手写 `MatFactorInfo` 和裸句柄执行 symbolic/numeric/solve | 新后端单独进入 reusable `src/solvers`；不要重用加载器、结构体或假定 C integer 宽度 |
| `src/solvers/y_orbit_two_cell_inverse.py:62` | `FourBranchFactors` 通过公开 SciPy `splu` 保留每个 actual q | 保留该已记录路线；新增显式 opt-in 后端工厂，重新资格化每个 q 的 residual/repeat/linearity |
| 同文件 `:164` 与 `y_orbit_quotient_condensed.py` | 完整 dual fold、interior recovery、primal lift、全部 alias | 后端仅换块求解；原三维方程、全部 q 和所有恢复项仍由已有组件持有 |
| `src/solvers/y_orbit_direct_probe.py:147–166` | 在任何 q factor 前完成原始算子与 carrier 比较 | 保留这个顺序；当前 `prefactor` 返回点与完整比对不能被新工厂跳过 |

接口：一个适配器拥有一个 assembled AIJ `PETSc.Mat A`、一个 `PETSc.PC` 和从 `getFactorMatrix()` 获得的 Python `Mat` 引用。调用者把 A 的所有权明确转移，不能再销毁/改值；不为所有权复制 A。`solve_repeated(rhs: PETSc.Vec, solution: PETSc.Vec) -> None` 使用既有因子，无新 KSP、无重分析/重因子、无 L/U 导出。rhs/solution 由调用者持有，必须不别名，匹配 A 的尺寸、分布和 communicator；后端不销毁它们。

目前 inverse 的 `solve(q, numpy_rhs)` 不是上述 Vec 接口。后续需要一个单独的、计入资源的 bridge，预创建每 q 两个 Vec，明确输入/输出 NumPy copy 的生命周期；不能宣称本源码片段是现成替换。初次资格只采用串行 AIJ/COMM_SELF 小块；MPIAIJ 和跨 rank 分布必须另做对应资格。实际 q 因子同时保留时，总成本按真实存活数量计入，不能从串行 factor 顺序推断只占一个因子。

## 2. 公开 API 的真实阶段顺序

1. 在任何 PETSc allocation 前检查 source/environment/ABI/integer/资源证据；再把已 assembled square complex AIJ A 转移给适配器。按 nonsymmetric LU 准入，不能把 q block 标签为 symmetric/Hermitian/SPD，也不选择 Cholesky；小型资格矩阵需包含确实不对称、非 Hermitian 的 complex 项。
2. `pc = PETSc.PC().create(comm=A.getComm())`；`pc.setType('lu')`；`pc.setOperators(A)`；`pc.setFactorSolverType('mumps')`；使用唯一 options prefix，拒绝未审核的同 prefix options。
3. `pc.setFactorSetUpSolverType()` 创建因子对象；`F = pc.getFactorMatrix()` 获得其公开包装。它**不是 symbolic analysis**。[PCFactorSetUpMatSolverType](https://petsc.org/release/manualpages/PC/PCFactorSetUpMatSolverType/)
4. 对 F 用 `setMumpsIcntl` / 必要的 `setMumpsCntl` 设置已审核控制。这些 API 若没有 MUMPS 可能被忽略，因此必须先验证 solver selection、backend build 和公开方法可用性。[MatMumpsSetIcntl](https://petsc.org/release/manualpages/Mat/MatMumpsSetIcntl/)
5. 一次 `pc.setUp()` 执行 symbolic **随后** numeric；成功后检查 PC failure 和 MUMPS status，再标记 ready。重复求解只调用 `F.solve(rhs, solution)`。[公开 petsc4py PC API](https://petsc.org/release/petsc4py/reference/petsc4py.PETSc.PC.html)；[Mat.solve/MUMPS API](https://petsc.org/release/petsc4py/reference/petsc4py.PETSc.Mat.html)

这是公开 PC API 和官方 PCLU 源码交叉检查后的顺序。PCLU 第一次 setup 调用 `MatLUFactorSymbolic`，检查失败，再调用 `MatLUFactorNumeric`；PETSc 管理 `MatFactorInfo` 与排序。当前公开 petsc4py Mat API只有 in-place `factorLU`，没有这里所需的独立 out-of-place symbolic/numeric 方法。[官方 PCLU 实现](https://petsc.org/release/src/ksp/pc/impls/factor/lu/lu.c.html)

**关键缺口：纯公开 petsc4py 路线不能在 symbolic 完成、numeric 开始前回到 Python 做准入。** 不得把 factor-object-created 写成 analysis-pass，也不得填旧 `symbolic_calls=1/numeric_calls=1`。记录 `factor_object_created` 和 `combined_setup_calls`，symbolic/numeric 分段统计为 null。若后续合同要求读取 analysis INFOG 后批准 numeric，这个后端保持 held；另行审核一个严格使用安装版公开 C headers/API 的编译扩展，或等待正式公开绑定支持。此处不提供、不编译该扩展。保守整机 Gate 可以保护 combined setup 的小型资格运行，但不能替代所要求的阶段 Gate。

## 3. Integer 与 ABI 准入必须分层

- 记录精确 PETSc/petsc4py/MUMPS/MPI/BLAS/scalar build 身份。正式数学栈需 complex128；Python3.12 或 NumPy2.3.5 本身不证明 PETSc/FEniCS ABI 合格。
- 在 narrowing、CSR 导入和 factor creation **前**，用 Python wide integer 记录并核验 rows/cols、global/local NNZ、row offsets、最大索引和 PETSc 转为 MUMPS 一基坐标后的最大值。每项分别对 PETSc 和后端范围检查；不得先 `astype(PETSc.IntType)` 再检测。
- `PETSc.IntType=int64` 只说明 PETSc 索引宽度。官方文档区分 MUMPS **selective64** 与 **full64**：PETSc 的 `--download-mumps` 默认 selective64，可以接 int32 或 int64 PETSc，但 rows/cols 仍必须小于 2^31；full64 还要求依赖库对应 ABI。[PETSc MUMPS integer modes](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)
- manifest 必须给 `backend_integer_mode`、矩阵索引位宽、NNZ/offset 位宽、安装版 PETSc→MUMPS 转换证据、build flags/依赖库身份。unknown 一律拒绝；不能由 int64 PETSc、Python int、一个小矩阵成功或某个 soname 推断 full64。selective64 的大 NNZ 支持也必须绑定安装版转换实现，不能把现代 release 行为假定给旧版。
- 不使用 ctypes、CDLL、raw `.handle`、自行推断 `_MatFactorInfo`、手写 C prototypes；这些问题由 public petsc4py/PETSc bindings 和它们的构建栈负责。

## 4. 控制与低成本 scalar 证据

| 控制/信息 | 用途与限制 |
|---|---|
| ICNTL(14) | workspace relaxation；记录实际值，任何调整属于新 profile，不能当作整机硬限 |
| ICNTL(22)=0、ICNTL(23)>0 | in-core 与每 working process 的 MUMPS 内部 workspace 限额；MB 为 decimal 10^6 B，不能涵盖 PETSc/NumPy/JIT/系统/其他 q 因子 |
| ICNTL(10)=0、(31)=0、(32)=0 | 首次固定回代 profile 无内部 refinement，保留因子、不绑定 factor-time RHS；实际取值需读取核实 |
| ICNTL(35)=0、(37)=0、(47)=0 | 在安装版支持且 semantics 已核验时保持 full-rank、无 contribution-block compression、无 single-precision factorization；BLR、单精度、null-pivot 修复不属于本方案 |
| INFO/INFOG(1),(2) | 原始状态/错误附加值；失败时保存，不用“无异常”替代 status gate |
| INFOG(16),(17)；(18),(19)；(21),(22) | 分别保存 analysis estimate、numeric allocated、numeric effectively used 的 max/sum scalar；标记阶段和 MB 单位 |

上述 workspace controls 与信息定义依据 [MUMPS 5.9.1 guide §5.12、§5.16–17、§7](https://mumps-solver.org/doc/userguide_5.9.1.pdf)。这些是 MUMPS 内部口径，不是 RSS/cgroup 或整机 simultaneous peak；估计值不能当成 hard bound。此 PC 路线在 setup 返回后只能回读保留的 analysis estimate，不能事后补造 analysis 前准入。

所有 optional 控制/INFO index 按**安装版 MUMPS guide + public 方法 + frozen profile**准入；未支持写 null/unavailable，不用猜测值，不以 `hasattr` 单独认定后端支持。缺 mandatory memory/control/status API时拒绝 setup。初始资格记录精确版本 tuple→已核验 public 方法及 control/index semantics；其他 tuple held，不能向旧版静默回退为 ctypes 或忽略 mandatory memory cap。旧版没有某个 optional feature 时，只有安装版证明确无该功能才能省略相应关闭控制。当前官方 release 页返回混合 3.25.5/3.26.0 页面，文献检查不代表本机安装资格，也不声明支持任意旧 PETSc。

MUMPS 会在 symbolic 阶段读取 factor prefix 的 options。审核并隔离相关 options 是前置条件，setup 后读回 controls 是额外核验，不能用后者补救一次已越界的 allocation。[官方 MUMPS 实现](https://petsc.org/release/src/mat/impls/aij/mpi/mumps/impl/imumps.c.html)

不读取 `.L/.U`，不创建 dense factor/copy/CSR statistics。整数与实数 INFO scalar 原样存储，复杂 packed count 不未经安装版手册解释。ICNTL(49) compaction 不属于基线；以后如用，不能无条件选择可能绕开 memory constraint 的模式。swap=0 与 OOC 是独立项，本候选两者均禁用。

## 5. 清理、资源与后续资格

destroy 幂等；按 factor Python reference、PC、owned A 的顺序尝试清理，异常路径也继续释放其余 owned 对象；不销毁 caller Vec。所有 MPI collective 销毁按一致次序进行。关闭后拒绝 apply，禁止 Python finalizer承担正确性。输入 A 不再改值、不重复 `setOperators`，否则 ready 资格无效；新矩阵采用新 adapter。

整机监督必须在解释器/JIT/assembly 前开始，采集同时存活的进程树或 cgroup、系统占用、swap、outer/恢复/输出阶段和单一 wall-clock；保存实际口径，不把各阶段历史 peak 累加成 simultaneous peak。外部监督完整 process group，资源超限/超时保留 controlled_stop；MUMPS cap 不能防止 analysis、输入转换、MPI buffers 或系统开销超限。下一 q 的准入包含所有既有 factors/caches，不沿用 V15 的128MiB/q为容量预测。

后续获准并具备 complex 环境后：先公开 API/manifest 检查，再 tiny complex nonsymmetric AIJ 单块资格（原 A 显式 residual、重复、线性、输入不变、failure/cleanup）；之后逐 actual q + NumPy bridge，再已有 full3D regular/notch 同离散资格。容差依据冻结任务合同；小矩阵不能证明大整数安全。任何数值/后端变更都需要 fresh identity-bound evidence，旧 V15 PASS 不授予新后端资格。

| 本次 deliverable | 状态 |
|---|---|
| 恢复源码与公开 API 阅读 | source-reviewed |
| 新方案与 `.py.fragment` | NEW_UNQUALIFIED_SOURCE |
| import/API/ABI/component/PDE/MPI/resource/runtime 验证 | not_run |
| immutable publishedV15/canonical/remote 修改 | none |
| 目标场精度、AUTO ports、原尺寸2TB/48h | unknown / not qualified |
