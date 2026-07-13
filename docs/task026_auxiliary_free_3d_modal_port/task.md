# CODEX TASK 20260711：auxiliary-free 3D periodic modal port

## 0. 任务名称

```text
Task026: Auxiliary-free 3D periodic modal port
and matrix-free low-rank DtN for direct/iterative Maxwell solves
```

中文定位：

```text
保留现有 auxiliary DtN 作为参考实现，
通过精确静态凝聚构造无 auxiliary 的三维双周期模态端口，
先用直接法验证 h=5/h=2 的场与 official R/T/A 一致性，
再为 condensed matrix-free operator 开发新的低内存迭代求解器。
```

ChatGPT 不创建分支。Codex 如需执行分支，应自行从当前 Task025 已审查分支创建；不得修改 ordinary default solver。

---

## 1. 背景与核心判断

Task021–Task025 已证明，当前 auxiliary DtN 的主要工程瓶颈不是端口物理本身，而是选择 FE-block Schur / response-column 路线后必须近似：

```math
Q \approx A_{FE}^{-1}C.
```

h=2 下无法同时以低内存和高精度构造这些 response columns，导致完整 80-aux cached-Schur residual 停在约 `0.1185`。

当前 augmented system 写为：

```math
\begin{bmatrix}
A_{FE} & C\\
D & A_{aux}
\end{bmatrix}
\begin{bmatrix}
u\\a
\end{bmatrix}
=
\begin{bmatrix}
b_{FE}\\b_{aux}
\end{bmatrix}.
```

现有端口中 `A_aux` 是单位块或小型可逆 modal block。应改为消去 auxiliary unknown：

```math
a=A_{aux}^{-1}(b_{aux}-Du),
```

从而得到只含 FE unknown 的精确 condensed system：

```math
\boxed{
A_{cond}u=b_{cond}
}
```

其中：

```math
A_{cond}=A_{FE}-C A_{aux}^{-1}D,
```

```math
b_{cond}=b_{FE}-C A_{aux}^{-1}b_{aux}.
```

如果 `A_aux=I`，则：

```math
A_{cond}=A_{FE}-CD.
```

对于当前 modal trace 记号，它等价于有限秩端口算子：

```math
A_{cond}=A_{FE}+U\Lambda U^H,
```

但实现时必须优先从现有 `C,D,A_aux` 块进行凝聚，避免重新推导造成 s/p 偏振、上下端口符号、归一化、复导纳或 Floquet phase 不一致。

### 核心收益

该结构：

```text
- 保留与现有 auxiliary DtN 完全相同的端口物理；
- 不再增加 auxiliary global unknown；
- 不再构造 Q = A_FE^-1 C；
- 不再需要 approximate auxiliary Schur；
- 不再保存 80 列 FE response cache；
- matrix-free 时不显式形成端口稠密子块；
- 允许 PC 重新专注于稀疏 Maxwell FE block。
```

### 必须保留的参考实现

现有 auxiliary 路径必须完整保留，作为：

```text
physical reference
algebraic reference
official R/T/A reference
regression fallback
```

禁止删除、覆盖或重写现有 auxiliary solver 的默认行为。

---

## 2. 总体执行路线

必须按顺序执行：

```text
Stage 1：冻结 Task025，确定 selective-merge 边界；
Stage 2：二维 auxiliary 与二维 explicit condensed DtN 回归验证；
Stage 3：三维双周期 explicit condensed modal port；
Stage 4：同一三维端口的 matrix-free low-rank 实现；
Stage 5：h=5/h=2 直接法和物理一致性验证；
Stage 6：对 matrix-free condensed system 开发迭代求解器。
```

Stage 2、3、4 必须同步进行代码内存审计和优化，不允许等到 h=2 爆内存后再处理。

---

## 3. Stage 1：冻结 Task025 路线

### 3.1 保留并提交

```text
- Task025 task/review/outcomes/summary；
- 轻量 CSV/JSON 和理论文档；
- 通用且已验证的 complex p-transfer 修复；
- p1 AMS degree 修复；
- shifted FE sub-operator 通用支持；
- opt-in research runner，如其可复现且不影响 ordinary default。
```

### 3.2 不进入 production 默认

```text
- h=2 cached 80-response Schur profile；
- adaptive BDDC；
- 失败的 p/coarse/2D coarse 实验 profile；
- 未通过 gate 的 R/T/A 路径；
- 参数硬编码和失败配置。
```

失败代码可以留在 Task025 research branch 历史中，但不得 selective merge 到 production 主线。

输出：

```text
outcomes/task025_freeze_manifest.md
outcomes/task025_selective_merge.csv
```

---

## 4. Stage 2：二维 auxiliary 与 explicit condensed DtN 回归

当前二维端口代码已经包含：

```text
_add_fourier_port_operators_auxiliary(...)
_add_fourier_port_operators_explicit(...)
```

Stage 2 不新增物理模型。目标是证明：

```math
\text{2D auxiliary DtN}
\equiv
\text{2D explicit condensed DtN}.
```

### 4.1 统一输入

两条路线必须共享：

```text
mesh
Nedelec space
Floquet constraint
mode/order selection
trace projection vectors
modal beta/admittance
incident source
normalization
material
solver tolerance
postprocessing
```

不得分别维护两套模式筛选或功率归一化代码。

### 4.2 代数验证

从 auxiliary block 显式提取：

```text
A_FE, C, D, A_aux, b_FE, b_aux
```

构造：

```math
A_{cond}=A_{FE}-CA_{aux}^{-1}D,
```

并与现有 explicit outer-product 路径比较。

至少验证：

```text
1. matrix shape / dtype；
2. random-vector action equivalence；
3. condensed RHS equivalence；
4. direct solution equivalence；
5. modal amplitudes；
6. R/T/A 与 closure；
7. near-Rayleigh warning 和 mode list 一致。
```

### 4.3 Stage 2 Gate

建议门槛：

```text
relative matrix-action error <= 1e-12
relative field error <= 1e-9
|Delta R_m|, |Delta T_m| <= 1e-9
|Delta R_total|, |Delta T_total|, |Delta A| <= 1e-9
closure difference <= 1e-9
```

如现有二维实现只能达到较宽松误差，必须解释误差来源，不得静默放宽。

### 4.4 Stage 2 内存审计与代码优化

必须在以下检查点记录：

```text
mesh built
FE matrix assembled
Floquet reduced
trace bank built
explicit port triplets built
condensed matrix created
direct factor setup
solve complete
postprocess complete
```

每个检查点记录：

```text
RSS current / peak
PETSc matrix info
SciPy CSR bytes, if any
trace-bank bytes
number of temporary arrays
wall time
```

必须检查并优化：

```text
- 不同时长期保留 PETSc AIJ 与 SciPy CSR 两份完整矩阵；
- 不同时保留 auxiliary augmented matrix 与 condensed matrix；
- 能在 PETSc 中完成的操作不回退到 rank-0 SciPy；
- explicit COO/row/col/data 临时数组用完立即释放；
- trace vectors 使用 boundary-only compressed storage；
- 原生 complex128，不做不必要 real split；
- 先应用 Floquet/MPC reduction，再生成 condensed port block；
- 避免 Python per-entry/per-row object list；
- 强制 gc 与 PETSc destroy 只作为诊断，不依赖隐式回收。
```

输出：

```text
outcomes/two_d_aux_explicit_equivalence.csv
outcomes/two_d_action_equivalence.csv
outcomes/two_d_rta_equivalence.csv
outcomes/two_d_memory_audit.csv
outcomes/two_d_memory_optimization.md
```

只有 Stage 2 通过后才进入 Stage 3。

---

## 5. Stage 3：三维双周期 explicit condensed modal port

### 5.1 首选实现方式：从现有 3D auxiliary blocks 精确凝聚

不要首先独立重写一套 3D modal formula。必须复用当前 Stage4 auxiliary assembly 输出或重构其内部 API，使其提供：

```text
A_FE
C
D
A_aux
b_FE
b_aux
mode metadata
trace/modal normalization metadata
```

在 Floquet/MPC reduced FE space 中构造：

```math
A_{cond}=A_{FE}-CA_{aux}^{-1}D.
```

该路径是三维 explicit condensed port 的权威参考。

### 5.2 独立 modal 表达审计

在 algebraic condensation 通过后，整理三维端口物理元数据：

```text
mode = (m,n,polarization,side)
polarization in {s,p}
kx_m = kx0 + 2*pi*m/Lx
ky_n = ky0 + 2*pi*n/Ly
kz_mn = outgoing square-root branch
complex material index
propagating / evanescent classification
near-Rayleigh classification
modal admittance / impedance
power normalization
```

必须确保上下端口、s/p、复折射率和 outgoing branch 与 auxiliary 路径逐模态一致。

### 5.3 显式矩阵构造

显式端口矩阵仅用于 direct/reference：

```math
A_{port}=-CA_{aux}^{-1}D.
```

不得默认将边界 trace 的 dense outer product 逐模态展开为巨大 Python COO。

优先方案：

```text
- 使用 PETSc MatMatMult / MatProduct；
- A_aux^-1 作为 80 x 80 dense/sparse exact block；
- distributed local rows；
- 精确 preallocation；
- reduced FE numbering；
- 只在 direct-reference profile 中显式生成 A_port。
```

### 5.4 Stage 3 结构验证

至少检查：

```text
- auxiliary FE size vs condensed FE size；
- C/D/A_aux dimensions；
- A_aux conditioning；
- explicit A_port rank upper bound；
- boundary trace dof count；
- A_port nnz and row-density distribution；
- MPI1/MPI4 action consistency；
- s/p and top/bottom mode ordering；
- MPC orientation and phase consistency。
```

### 5.5 Stage 3 内存审计与代码优化

必须输出显式 condensed 矩阵的内存增长模型：

```text
N_FE
N_trace_top / N_trace_bottom
number of modes
nnz(A_FE)
nnz(C), nnz(D), nnz(A_aux)
nnz(A_port)
nnz(A_cond)
AIJ allocated / used bytes
estimated direct factor fill
```

必须检查并优化：

```text
- assembly 过程中不保留完整 augmented 和 condensed 两套大 AIJ；
- block extraction 使用 PETSc index sets，不复制全矩阵到 root；
- C、D 使用分布式稀疏存储；
- A_aux 使用小型 dense/sparse exact factor；
- MatProduct symbolic/numeric 阶段分离并记录内存；
- 端口矩阵加入 A_FE 后立即销毁中间 product；
- modal metadata 与数值 trace bank 分离；
- 不生成 N_FE x 80 的 dense global U；
- postprocess 不复制完整解向量到 rank 0；
- 所有临时 matrix/vector 明确 destroy。
```

输出：

```text
outcomes/three_d_condensation_design.md
outcomes/three_d_block_validation.csv
outcomes/three_d_mode_mapping.csv
outcomes/three_d_explicit_port_sparsity.csv
outcomes/three_d_explicit_memory_audit.csv
outcomes/three_d_explicit_memory_optimization.md
```

---

## 6. Stage 4：matrix-free low-rank condensed DtN

Stage 4 与 Stage 3 使用完全相同的物理端口和 blocks，不是另一种边界条件。

### 6.1 精确 matrix action

实现：

```math
y=A_{FE}x-C\left(A_{aux}^{-1}(Dx)\right).
```

如果 `A_aux=I`：

```math
y=A_{FE}x-CDx.
```

推荐 PETSc 结构：

```text
MatShell / MatPython / MatComposite for A_cond
explicit distributed A_FE
explicit sparse C and D
small exact A_aux solver
reusable auxiliary work vectors
```

不得构造：

```text
Q = A_FE^-1 C
80-response cache
approximate Schur of FE inverse
explicit dense boundary A_port
```

### 6.2 MPI apply 设计

一次 apply 应为：

```text
1. y = A_FE x
2. t_aux = D x
3. z_aux = A_aux^-1 t_aux
4. y = y - C z_aux
```

必须：

```text
- 保持 C/D 的 distributed ownership；
- 不 allgather FE trace；
- auxiliary vector 只有 80 维；
- 批量处理所有 modes，避免 80 次单独 MPI reduction；
- 预分配并复用 work vectors；
- 支持 PETSc KSP 所需的 mult / createVec / destroy lifecycle；
- 明确 complex scalar 与 conjugation 方向。
```

### 6.3 Action equivalence

在 h=5、h=2 上对以下向量比较：

```text
random FE vector
physical RHS-related vector
converged direct solution
selected near-cutoff modal trace vector
```

比较：

```math
\frac{\|A_{explicit}x-A_{mf}x\|}{\|A_{explicit}x\|}.
```

Gate：

```text
h=5 action error <= 1e-12
h=2 action error <= 1e-11
MPI1/MPI4 difference within reduction tolerance
```

### 6.4 Stage 4 内存审计与代码优化

必须与以下结构逐项比较：

```text
auxiliary augmented operator
explicit condensed operator
matrix-free condensed operator
Task025 cached-Q operator
```

记录：

```text
operator storage
C/D/A_aux storage
work-vector storage
PC storage
Krylov storage
peak RSS
MatMult time
communication time
```

重点优化：

```text
- C/D 不转为 dense N_FE x 80；
- trace bank 只存 boundary support；
- auxiliary solve factor 只建立一次；
- work vectors 在 apply 间复用；
- MatMult 中禁止临时 NumPy global arrays；
- 禁止 rank0-only collective；
- 对 80 模态使用单次 block reduction；
- 提供 restart/memory guard，防止 Krylov basis 吃掉节省的内存；
- 将 MatShell context 与 mesh/FunctionSpace 重对象解耦，避免生命周期泄漏；
- 提供 repeated-apply RSS stability 测试，至少 1000 applies 无持续增长。
```

输出：

```text
outcomes/matrix_free_port_design.md
outcomes/matrix_free_action_equivalence.csv
outcomes/matrix_free_mpi_consistency.csv
outcomes/matrix_free_memory_breakdown.csv
outcomes/matrix_free_apply_benchmark.csv
outcomes/matrix_free_rss_stability.csv
outcomes/operator_storage_comparison.csv
```

---

## 7. Stage 5：h=5/h=2 直接法与物理一致性验证

### 7.1 h=5 direct reference

使用完全相同的物理模型和 mode list，分别运行：

```text
A. existing auxiliary DtN + direct solver
B. explicit condensed DtN + direct solver
```

必须比较：

```text
full true residual
FE field relative error
selected point/line/plane field probes
modal amplitudes for all orders
R_m / T_m
R_total / T_total / A_volume
energy closure
matrix/factor memory
setup and solve time
```

h=5 Gate：

```text
both residuals <= 1e-9
relative FE field error <= 1e-8
per-mode power absolute difference <= 1e-8
R/T/A absolute difference <= 1e-8
closure difference <= 1e-8
```

同时使用 direct solution 验证 explicit vs matrix-free action。

### 7.2 h=2 direct attempt

目标是在可用物理内存和 swap/OOC 条件下尝试：

```text
A. auxiliary DtN + MUMPS direct/OOC
B. explicit condensed DtN + MUMPS direct/OOC
```

资源策略：

```text
- 原生 complex system；
- 不做 real split；
- 每条路线在独立进程运行；
- 不同时保留 auxiliary/explicit 两套矩阵；
- 允许 MUMPS out-of-core；
- 允许系统 swap，但必须记录 swap-in/out 和 wall time；
- 目标物理内存约 18 GB；
- 大型因子文件放 results/，不得提交 Git。
```

必须在 factorization 前输出：

```text
matrix rows / nnz
port-block nnz
symbolic ordering
estimated factor memory
available RAM/swap
OOC path and free disk
```

如果 h=2 某一 direct 路线因资源失败：

```text
- 记录准确失败阶段；
- 不宣称 h=2 field/RTA equivalence 已通过；
- 仍完成 algebraic/action equivalence；
- 不用宽松迭代结果冒充 direct reference。
```

h=2 成功时 Gate：

```text
both residuals <= 1e-8
relative FE field error <= 1e-7
per-mode/RTA absolute difference <= 1e-7
closure difference <= 1e-7
```

### 7.3 Stage 5 输出

```text
outcomes/h5_aux_vs_condensed_direct.csv
outcomes/h5_field_equivalence.csv
outcomes/h5_modal_rta_equivalence.csv
outcomes/h5_direct_resource.csv
outcomes/h2_aux_vs_condensed_direct.csv
outcomes/h2_field_equivalence.csv
outcomes/h2_modal_rta_equivalence.csv
outcomes/h2_direct_resource.csv
outcomes/h2_ooc_swap_log.md
outcomes/direct_reference_gate.csv
```

---

## 8. Stage 6：新的无 auxiliary 迭代求解器

只有以下条件通过后才进入：

```text
Stage 3 condensed algebra validated
Stage 4 matrix-free action validated
h=5 direct physical equivalence passed
```

最终 operator：

```math
A_{cond}=A_{FE}-CA_{aux}^{-1}D.
```

外层优先：

```text
PETSc FGMRES
right preconditioning
restart 50 / 100
explicit full true residual monitor
Krylov memory guard
```

manual FGMRES 只作验证，不进入 production API。

### 8.1 第一轮 PC profiles

首先比较：

```text
P0: Jacobi baseline
P1: shifted ASM/ILU0
P2: shifted ASM/ILU1
P3: existing COMSOL-inspired GMG prototype, only if independently valid
```

PC 默认只近似稀疏 `A_FE`，低秩端口项由 outer FGMRES 精确看见。

不得在第一轮使用：

```text
Woodbury requiring A_FE^-1 C
cached response columns Q
auxiliary Schur approximation
```

### 8.2 如果 FE-only PC 不足

按顺序尝试：

```text
1. propagating-mode deflation；
2. near-Rayleigh / near-cutoff mode enrichment；
3. local modal impedance approximation in PC；
4. topology-aware H(curl) patch / genuine h-GMG。
```

任何 modal correction 都不得重新引入全量 `A_FE^-1 C`。

### 8.3 Iterative Gate

h=5：

```text
true residual <= 1e-8
R/T/A vs direct <= 1e-8
peak RSS lower than auxiliary direct/reference
```

h=2 分级：

```text
minimum: at least 2x better than strict equal-budget baseline
strong: true residual <= 1e-2
engineering: true residual <= 1e-4
production-like: true residual <= 1e-6
```

最终成功条件：

```text
h=2 true residual <= 1e-6
official R/T/A passed
peak RSS < 14 GB
no auxiliary unknowns
no Q cache
MPI1/MPI4 consistency
```

参数角度/波长 sweep 只有在 h=2 production-like 后开启；Task026 本身只需准备 parameterized operator API 和 cache invalidation 规则。

输出：

```text
outcomes/iterative_profile_screen.csv
outcomes/iterative_true_residual_history.csv
outcomes/iterative_memory.csv
outcomes/iterative_rta.csv
outcomes/condensed_vs_auxiliary_solver_comparison.csv
outcomes/parameter_update_design.md
```

---

## 9. 统一代码与 API 要求

必须新增或重构清晰接口，命名可调整，但职责必须分离：

```text
build_modal_port_metadata(...)
assemble_auxiliary_port_blocks(...)
condense_auxiliary_port_blocks(...)
build_explicit_condensed_port(...)
build_matrix_free_condensed_port(...)
apply_condensed_port(...)
reconstruct_modal_amplitudes_from_fe_solution(...)
compute_official_modal_rta(...)
```

要求：

```text
- auxiliary/explicit/matrix-free 共用 mode metadata；
- auxiliary/explicit/matrix-free 共用 postprocessing；
- 不复制三套 mode-order/polarization 逻辑；
- 端口 side、order、polarization 使用稳定 key；
- 支持 complex refractive index；
- 支持 propagating/evanescent/near-Rayleigh 分类；
- 所有 solver profile opt-in；
- ordinary default 不改变；
- 每次运行记录 git SHA、container/image digest、PETSc/MUMPS version、MPI ranks、command line。
```

---

## 10. 必须测试

至少新增：

```text
1. 小型 synthetic block condensation 单元测试；
2. A_aux 非单位小矩阵 condensation 测试；
3. explicit vs matrix-free action 测试；
4. complex conjugation/sign 测试；
5. top/bottom and s/p ordering 测试；
6. MPI collective smoke；
7. repeated MatMult memory-stability 测试；
8. 2D auxiliary/explicit regression；
9. 3D h=5 auxiliary/explicit regression；
10. modal R/T/A regression。
```

必须通过：

```text
python -m py_compile <Task026 sources>
python -m <Task026 runner> --help
unit tests in complex mode
MPI=4 smoke tests
```

---

## 11. 必须输出

```text
outcomes/summary.md
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
outcomes/changed_files.md
outcomes/parameters.json

outcomes/task025_freeze_manifest.md
outcomes/task025_selective_merge.csv

outcomes/two_d_aux_explicit_equivalence.csv
outcomes/two_d_action_equivalence.csv
outcomes/two_d_rta_equivalence.csv
outcomes/two_d_memory_audit.csv
outcomes/two_d_memory_optimization.md

outcomes/three_d_condensation_design.md
outcomes/three_d_block_validation.csv
outcomes/three_d_mode_mapping.csv
outcomes/three_d_explicit_port_sparsity.csv
outcomes/three_d_explicit_memory_audit.csv
outcomes/three_d_explicit_memory_optimization.md

outcomes/matrix_free_port_design.md
outcomes/matrix_free_action_equivalence.csv
outcomes/matrix_free_mpi_consistency.csv
outcomes/matrix_free_memory_breakdown.csv
outcomes/matrix_free_apply_benchmark.csv
outcomes/matrix_free_rss_stability.csv
outcomes/operator_storage_comparison.csv

outcomes/h5_aux_vs_condensed_direct.csv
outcomes/h5_field_equivalence.csv
outcomes/h5_modal_rta_equivalence.csv
outcomes/h5_direct_resource.csv
outcomes/h2_aux_vs_condensed_direct.csv
outcomes/h2_field_equivalence.csv
outcomes/h2_modal_rta_equivalence.csv
outcomes/h2_direct_resource.csv
outcomes/h2_ooc_swap_log.md
outcomes/direct_reference_gate.csv

outcomes/iterative_profile_screen.csv
outcomes/iterative_true_residual_history.csv
outcomes/iterative_memory.csv
outcomes/iterative_rta.csv
outcomes/condensed_vs_auxiliary_solver_comparison.csv
outcomes/parameter_update_design.md
```

大型 matrix、factor、mesh、field 和 cache 只放 `results/`，不得提交 Git。

---

## 12. summary.md 必答问题

```text
1. 2D auxiliary 与 explicit condensed 是否逐值等价？
2. 3D condensed block 是否严格来自现有 auxiliary blocks？
3. explicit condensed 是否与 auxiliary 在 h=5 direct 下场与 R/T/A 一致？
4. h=2 两条 direct 路线是否完成；若失败，准确失败在哪一阶段？
5. matrix-free action 是否与 explicit action 达到机器精度一致？
6. Stage 2/3/4 分别发现并修复了哪些内存复制、临时数组或生命周期问题？
7. auxiliary、explicit、matrix-free、Task025 Q-cache 的 operator/peak memory 各是多少？
8. 新 matrix-free operator 是否彻底消除了 A_FE^-1 C 与 Q cache？
9. 哪个迭代 profile 在 h=5/h=2 上最好？
10. h=2 是否达到 production-like 与 official R/T/A？
11. 新路线是否值得继续做角度/波长/网格鲁棒性测试？
```

---

## 13. Merge strategy

```text
merge_docs: yes after review
merge_shared_modal_metadata: yes only after auxiliary regression
merge_condensation_utils: yes after unit/MPI tests
merge_explicit_port: opt-in only after h5 direct gate
merge_matrix_free_port: opt-in only after action and memory gates
merge_iterative_profile: no default until h2 production-like
remove_auxiliary_reference: never in Task026
production_default_change: no
```

---

## 14. 最终目标句

```text
是否已经在保留现有 auxiliary DtN reference 不变的前提下，
构造出与其代数和物理等价的 3D explicit condensed 与 matrix-free modal port，
在 Stage 2/3/4 中消除不必要的矩阵复制和临时内存，
并使无 auxiliary、无 Q-cache 的 h=2 matrix-free iterative system
在 14 GB 内达到 true residual <= 1e-6 和 official R/T/A？
```
