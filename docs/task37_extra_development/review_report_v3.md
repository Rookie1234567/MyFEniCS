# Task037-extra Review Report V3：Candidate H H1.2 超时审阅与 action 内核重构指令

## 0. 审阅身份与最终决定

```text
review                         = Task037-extra Review Report V3
working_branch                 = codex/20260806-task37-iterative-extra-development
create_new_branch              = forbidden
pull_request                   = forbidden
merge_to_master                = permanently_not_planned
ordinary_default_change        = forbidden
review_v1_G2_decision          = accepted_and_not_reopened
review_v2_candidate_H          = retained_as_bounded_oracle_only
reviewed_implementation_sha    = f7591aa9a2ae581d748e97ec607ea6edb51d1b14
reviewed_response              = docs/task37_extra_development/response_v2.md
H0                             = accepted_capability_only
H1_1                           = accepted_tiny_fixture_pass
H1_2_measurement               = accepted_controlled_timeout_evidence
H1_2_numerical_qualification   = unavailable
H1_2_current_kernel_scalability = rejected
H2                             = not_run_and_remains_locked
H3                             = not_run_and_remains_locked
H4                             = not_run_and_remains_locked
new_authorized_stage           = H1R_action_kernel_diagnostic_and_redesign
full_PDE                       = prohibited
```

本审阅接受当前分支对 H0、H1.1 和 H1.2 受控停止的记录方式：

- H1.1 的 p2/p3 tiny assembled-vs-action 与 MPI identity 证据有效；
- H1.2 在冻结的 1800 s timeout 下安全终止，未发生 swap 或内存越界；
- worker 未写出 `run_summary.json`，因此 exact p6 action error、determinism、payload 和
  completed-run peak 均必须保持 `unavailable`；
- H2 没有绕过 H1.2 Gate，治理边界正确。

但是，代码审阅发现当前 p6 action 实现存在一个与最终 p6/h1 目标直接冲突的结构问题：
它虽然不保存 global matrix，却在**每一次 MatMult、每一个单元上重新生成并定向完整
`882 x 882` 稠密单元矩阵，然后执行稠密矩阵向量乘法**。因此当前实现属于
`dense-cell-tensor reassembly action`，不是面向高阶大规模问题的 tensor-product
partial assembly / sum-factorized action。

所以本审阅的决定是：

```text
不得延长 timeout 后原样重跑 H1.2；
不得启动 MPI2、H2、H3、H4 或任何 full PDE；
只允许执行 H1R：阶段定位、单元内核微基准和 action 内核重构。
```

---

## 1. 被审证据

### 1.1 文档与 raw 边界

审阅对象包括：

```text
docs/task37_extra_development/response_v2.md
docs/task37_extra_development/outcomes/h0_fullspace_mg_audit.md
docs/task37_extra_development/outcomes/h1_fullspace_matrix_free_action.md
docs/task37_extra_development/outcomes/h2_coercive_block_smoother.md
benchmarks/run_task037_extra_candidate_h.py
src/solvers/fullspace_matrix_free_hcurl.py
src/solvers/mpc_form_action.py
src/test/test_271_task037_extra_fullspace_mf_action.py
src/test/test_272_task037_extra_fullspace_mf_mpi.py
src/test/test_276_task037_extra_candidate_h_runner.py
```

H1.2 正式 raw 身份为：

```text
source SHA              = f7591aa9a2ae581d748e97ec607ea6edb51d1b14
MPI                     = 1
timeout                 = 1800 s
RSS hard limit          = 1.25 GiB
controlled stop         = timeout
wall                    = 1801.0560716170585 s
incomplete observed peak = 0.36053466796875 GiB
swap                    = 0
worker summary          = absent
canonical directory     = absent
```

`0.3605 GiB` 只是在未完成运行中的已观察峰值，不是 H1 memory Gate PASS。

### 1.2 正结果

| 项目 | 审阅结论 |
|---|---|
| H0 ABI/API/lifecycle audit | 接受，范围仅为 capability-only |
| p2 assembled-vs-action error | `5.180892903724677e-16`，接受 |
| p3 assembled-vs-action error | `8.360695796841576e-16`，接受 |
| p2 canonical dual MPI error | `1.985978336928787e-16`，接受 |
| p3 canonical dual MPI error | `3.3576744854094875e-16`，接受 |
| fail-closed timeout | 接受；没有将 summary 缺失写成算法通过或算法发散 |
| H2 gating | 接受；H1.2 未资格化后没有启动 H2 |

### 1.3 尚未得到的结论

以下全部仍是 `unavailable` 或 `not_run`：

- p6/h10 exact action relative error；
- p6/h10 candidate action wall；
- p6/h10 reference action wall；
- p6/h10 repeat determinism；
- completed-run retained payload；
- completed-run process-tree peak；
- MPI1/MPI2 canonical identity；
- H2 block class count、factor payload 和 contraction；
- H3 two-grid capacity；
- 原始时谐方程的收敛和 official R/T/A。

---

## 2. 代码级关键发现

## 2.1 当前 action 的真实计算路径

`FullSpaceMatrixFreeHcurlAction.mult()` 对每个 cell 执行：

```text
_tabulate_cell_tensor(cell)
local_input = input_values[cell_dofs]
local_result = dense_cell_tensor @ local_input
scatter-add local_result
```

而 `_tabulate_cell_tensor(cell)` 每次都会：

1. 将唯一 scratch tensor 清零；
2. 调用 FFCx cell kernel生成完整局部双线性矩阵；
3. 对完整局部矩阵施加 H(curl) orientation transformation；
4. 随后才做局部 dense GEMV。

该实现满足：

```text
global matrix retained = 0
cell matrix cache       = 0
cell Schur cache        = 0
```

但它不满足长期所需的：

```text
no dense p6 cell tensor generation per apply
sub-quadratic local action complexity
sum-factorized/tensor-product partial assembly
```

## 2.2 p6/h10 的工作量量级

p6 hexa N1curl 的局部维数为：

```math
n_{loc}=882.
```

完整局部 tensor 的条目数为：

```math
n_{loc}^2=882^2=777924.
```

一个 complex128 scratch tensor 为约：

```math
777924\times16\ \mathrm{bytes}
\approx11.87\ \mathrm{MiB}.
```

h10 有 252 个 cells，因此一次 candidate action 至少要生成、定向并在 dense GEMV 中
处理约：

```math
252\times777924=196036848
```

个局部复数矩阵条目。

正式 runner 对每个 source 执行：

```text
1 reference form action
2 candidate actions
canonical packet extraction
```

共有 4 个 sources，因此 candidate 路径本身至少重复 8 次上述 cell-tensor action，尚未计入
reference form action、MPC backsubstitution、canonical packet extraction 和 Python 循环成本。

从 h10 到 h1，cell 数量量级增加约 `10^3`。如果继续采用同一局部算法，则一次 action
需要处理约 `1.96e11` 个 dense local tensor entries。即使 H1.2 最终通过数值 identity，
这种 action 也不能作为 p6/h1 主线。

## 2.3 timeout 目前不能精确归因

runner 的 `_action_record()` 顺序是：

```text
reference_context.mult
candidate action #1
candidate action #2
canonical extraction/export
```

当前 raw 只有 mesh 文件，没有首个 source canonical 目录；但 worker 没有在上述细分阶段写
progress marker。因此不能判断 1800 s 主要消耗在：

- high-order function-space/MPC/form setup；
- `MpcFormActionContext` reference apply；
- candidate cell-tensor action；
- repeat candidate apply；
- canonical extraction。

代码检查只证明 candidate 内核本身存在不可扩展结构，不能从现有 raw 冒充精确 wall
分解。

## 2.4 reference action 也不是长期性能结论

`MpcFormActionContext.mult()` 每次通过：

```text
ufl.action(bilinear_form, field)
+ dolfinx_mpc.assemble_vector
```

计算 reference action。它适合作为独立代数 authority，但仍包含每次 form assembly、MPC 和
通信开销；不能未经计时就被当作 p6/h1 的最终 partial-assembly 内核。

---

## 3. 当前分类

| 范围 | V3 分类 |
|---|---|
| H0 | `ACCEPTED_CAPABILITY_ONLY` |
| H1.1 | `ACCEPTED_TINY_ALGEBRA_PASS` |
| H1.2 raw | `ACCEPTED_CONTROLLED_TIMEOUT_EVIDENCE` |
| H1.2 exact p6 algebra | `NOT_QUALIFIED` |
| H1.2 completed memory | `NOT_QUALIFIED` |
| current dense-cell-tensor action | `REJECTED_FOR_H_REFINEMENT_SCALABILITY` |
| Candidate H overall | `REDESIGN_REQUIRED_BEFORE_H2` |
| H2 | `LOCKED` |
| H3 | `LOCKED` |
| H4/full PDE | `PROHIBITED` |

这里的 `REJECTED_FOR_H_REFINEMENT_SCALABILITY` 不是说 p6 action 数值上错误，而是说当前
每次作用重建完整稠密单元矩阵的算法不具备 p6/h1 资格。

---

# 4. 唯一授权的下一步：H1R action 内核诊断与重构

H1R 不是延长 timeout，也不是进入 multigrid。它只回答：

> 能否在当前 FEniCS/Basix/FFCx 技术栈中，将 full-space p6 action 改造成不在每次作用中
> 生成 `882 x 882` dense cell tensor 的低存储、低复杂度 action？

## H1R.0：加入可审计阶段 marker

在 worker 和 action 中加入 compact、立即 flush 的 progress 事件。至少覆盖：

```text
mesh_build_started / ready
function_space_started / ready
floquet_mpc_started / ready
form_compile_started / ready
candidate_build_started / ready
reference_build_started / ready
source_interpolation_started / ready
reference_apply_started / ready
candidate_apply_1_started / ready
candidate_apply_2_started / ready
canonical_export_started / ready
worker_summary_started / ready
```

每个 marker 至少记录：

```text
elapsed wall
rank
RSS/PSS/USS if available without nested sampler
source label
apply count
cell count
local/global rows
```

要求：marker 本身不能创建 FE-sized Python arrays，不能改变 action 数值结果。

H1R.0 只做 focused tests，不直接重复原 1800 s run。

## H1R.1：p6 单元/单类 microbenchmark

建立一个不运行 PDE/KSP 的 microbenchmark，对同一个 p6 affine hexa cell/class 比较：

```text
A. current: kernel tabulation + full tensor orientation + dense GEMV
B. diagnostic only: exact class-cached dense tensor + dense GEMV
C. direct action kernel: local coefficients -> local residual, no dense tensor output
```

其中 B 只用于分离“tensor tabulation/orientation”与“dense GEMV”的时间，不得作为 p6/h1
最终方案。C 可以是：

- FFCx 直接线性-form action kernel；或
- 基于 Basix tensor-product factorization 的 partial assembly / sum-factorized kernel。

每条路径至少记录：

```text
setup seconds
first apply seconds
median repeated apply seconds
bytes retained
bytes touched/estimated
finite/deterministic
relative error vs exact dense cell authority
```

测试阶次固定为：

```text
p2, p3, p4, p6
```

目的不是拟合一个漂亮指数，而是证明 C 的局部成本没有继续按完整 `n_loc^2` dense tensor
路径增长。

### H1R.1 Gate

```text
C relative error <= 1e-11
C finite and deterministic
C does not materialize a dense n_loc x n_loc tensor per apply
C p6 repeated apply < 0.25 * A p6 repeated apply
C retained payload per exact class <= 16 MiB
```

若当前环境不能生成或实现 C，Candidate H 关闭；不得用 B 冒充 scalable action。

## H1R.2：单 source p6/h10 action-only Gate

只有 H1R.1 通过，才允许一次 p6/h10、MPI1、单 source 运行：

```text
source = seed_17037
reference apply = 1
candidate apply = 2
canonical export = disabled in timing phase
KSP = 0
DtN = 0
```

先比较 distributed Vec：

```math
\frac{\|A_{ref}x-A_{cand}x\|_2}
{\|A_{ref}x\|_2}
\le10^{-11}.
```

数值 Gate 通过后，允许在同一完成运行的末尾做一次 canonical packet audit；不得在 action
计时前执行 canonical export。

### H1R.2 Gate

```text
completed within 600 s
candidate apply finite/deterministic
relative error <= 1e-11
candidate repeated apply <= 2 * reference apply wall
candidate retained payload <= 0.50 GiB
completed-run process-tree peak <= 1.25 GiB
no global A
no condensed Schur
no dense cell tensor generated per apply
no slab/per-cell growing factor
```

若 reference apply 本身超过 300 s，但 redesigned candidate apply满足上述结构和数值 Gate，
允许将 reference authority移动到一次离线 assembled/class-cached comparison；必须单独记录其
peak，不能把 reference 低效冒充 candidate 失败。

## H1R.3：恢复正式 H1.2

只有 H1R.2 完整通过，才恢复 Review V2 的四 source H1.2：

```text
3 deterministic sources
1 physical-RHS-like source
MPI1 complete
MPI2 complete
canonical compare
```

H1R.3 必须生成完整 `run_summary.json` 和 payload inventory。H1R.3 通过后，才允许下一次
review 决定是否解锁 H2；Codex 不得自行启动 H2。

---

# 5. 实现边界

## 5.1 长期允许保留的数据

允许按 exact class 保留：

- 一维/低维 basis evaluation tables；
- derivative tables；
- quadrature weights；
- affine Jacobian/class coefficients；
- orientation/permutation metadata；
- bounded work buffers；
- tiny diagnostic counters。

这些 class 数必须由 material、geometry、orientation 和 boundary identity审计，且在规则
refinement fixture 上不得随 cell 数线性增长。

## 5.2 禁止作为最终 action 的结构

- 每个 cell 保存一份 dense tensor；
- 每次 action 重新输出完整 `882 x 882` tensor；
- 每个 cell 一个 Python object/factor；
- global assembled full matrix；
- static-condensed Schur；
- 16-slab factor；
- LOR-HX hierarchy；
- 20--90 步 local Krylov；
- 通过延长 timeout 掩盖 action 复杂度；
- 在 action Gate 前运行 KSP、H2、H3 或 official R/T/A。

## 5.3 diagnostic dense class cache 的边界

允许 H1R.1 的 B 路径按 exact class临时缓存 dense cell tensor，用于时间分解和代数 authority。
它必须标记：

```text
diagnostic_only = true
h_refinement_scalability = not_claimed
eligible_for_H2 = false
```

不得因为 class-cached B 能完成 h10，就绕过 C 路径进入 H2。

---

# 6. 必须新增的测试与输出

建议新增：

```text
src/test/test_277_task037_extra_candidate_h_progress.py
src/test/test_278_task037_extra_p6_cell_action_microbenchmark_contract.py
src/test/test_279_task037_extra_partial_action.py
src/test/test_280_task037_extra_h1r_single_source_runner.py
```

测试编号如已占用，使用下一个空闲编号并记录映射。

输出固定为：

```text
docs/task37_extra_development/outcomes/h1r_action_kernel_diagnostic.md
docs/task37_extra_development/outcomes/h1r_partial_action.md
docs/task37_extra_development/response_v3.md
benchmarks/cases/101_task37_extra_development/records/h1r_*.json
```

重型 raw 继续放在 ignored artifact 目录，不得提交 canonical shards、mesh、timeline 或大矩阵。

---

# 7. 第一轮 Codex 执行边界

下一次执行只允许：

```text
H1R.0
H1R.1
```

不得直接执行 H1R.2。第一轮 `response_v3.md` 必须回答：

1. 1800 s 运行在首个 source 前的各阶段时间分布能否被准确观测；
2. current A 路径中，tensor tabulation、orientation 和 dense GEMV 各占多少；
3. diagnostic B 路径能改善多少，但为什么不能作为最终 scalable path；
4. 是否成功实现 C 路径；
5. C 在 p2/p3/p4/p6 上的误差、时间和 retained bytes；
6. 是否具备进入 H1R.2 的资格。

第一轮结束后提交并推送当前分支，等待下一次审阅，不得自动继续重型运行。

---

# 8. Hard stop

以下任一项触发即关闭 Candidate H：

- 无法实现不生成 dense cell tensor 的 C 路径；
- C 在 p6 单元上 relative error `>1e-11`；
- C p6 repeated apply 不能达到 A 的至少 4 倍加速；
- C 仍按 cell 数保留 dense tensor/factor；
- class count 随规则 refinement 近似线性增长；
- 需要新建分支、修改 ordinary default 或安装未经授权的新依赖；
- 需要延长原 H1.2 timeout而没有 action 内核结构变化；
- 试图在 H1 未资格化时启动 H2/H3/H4。

触发后写明 capability/implementation stop，不得将其改写为 full-space multigrid的普遍数学
不可能性。

---

## 9. 最终裁决

当前结果证明：

- full-space action 的小型代数原型是正确的；
- 当前 p6/h10 正式实现没有在 1800 s 内形成 action 资格记录；
- 当前每 cell、每 apply 重建 `882 x 882` dense tensor 的内核不适合 p6/h1；
- 因而 H2/H3 不能启动。

下一步唯一有研究价值的工作不是“再等更久”，而是：

```text
将 full-space p6 action 从 dense-cell-tensor reassembly
改造成 direct local residual / tensor-product partial assembly，
并先在 p6 单元微基准上证明速度、误差和存储。
```

Review V1 的 G2_FAIL、Review V2 的 bounded-oracle原则和本分支永久隔离规则继续有效。
