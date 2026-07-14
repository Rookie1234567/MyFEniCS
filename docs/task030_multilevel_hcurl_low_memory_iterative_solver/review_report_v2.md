# REVIEW REPORT V2：Task030 最终数值接受、可复现性加固与选择性合并边界

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260713-task30-multilevel-hcurl-low-memory-iterative
base = master@bfb6586e030efd5208ebd796c39fdc31301e1d6e
reviewed_implementation = 59b2f8f57b5d31e4e545186de711b4311f650621
reviewed_response = 75975426a75223b19df6651f792ffcc741467ec1
scope = Task030 implementation + response_v1 + Case060 + benchmark/provenance + docs
```

本轮重点确认：

```text
- Review V1 的 provenance、manifest、checker 与命名问题是否关闭；
- Task030 数值结果是否仍可信；
- dirty-working-tree artifact 是否可以直接作为 master canonical evidence；
- hcurl_multilevel.py 中 validated infrastructure 与 failed solver lanes 是否具有清晰合并边界；
- compact physical-slab profile 是否只能保持 experimental opt-in；
- 合并前是否需要重跑 h2；
- 项目文档应如何记录最终状态和下一任务。
```

---

# 2. 审查结论

```text
review_status = pass_with_two_required_hardening_items

task30_overall_classification = workstation_memory_success_with_qualifications
workstation_success = pass_for_frozen_target_experimental_opt_in
strong_workstation_success = no
ordinary_default_changed = no

hcurl_transfer_infrastructure = pass_with_scope_qualification
condensed_galerkin_infrastructure = pass
p_h_multigrid_solver = fail
patch_p_h_solver_family = fail
all_mode_woodbury = fail
compact_physical_slab_candidate = pass
h2_numeric_and_memory_gate = pass
h2_iteration_preference = fail

response_v1_naming_hardening = pass
manifest_integration = pass
case060_numeric_checker = pass
benchmark_summary_regeneration = pass
provenance_disclosure = pass
clean_commit_reproducibility = not_yet_pass
selective_merge_boundary = not_yet_fully_enforced

heavy_h2_rerun_required = no
clean_h5_h3_rerun_required = yes
new_solver_research_required_before_merge = no
master_merge = yes_after_R1_R2_response_v2_and_user_approval
```

准确结论保持不变：

> Task030 的成功求解机制仍然是 Task027-derived exact-condensed physical-slab Schwarz + 75D Floquet wave coarse。Task030 通过 symmetric pre/coarse/post、ILU0、subdomain-local shift、factor-only storage 和 restart90 将冻结 h2 target 的峰值从 13.080 GB 降至 9.375 GB。真正 p/h multigrid、patch+p/h 和 all-mode Woodbury 没有形成求解正反馈。

没有发现需要否定 h5/h3/h2 数值结果的新问题，也不要求再次运行 h2。合并前只需解决可复现性与 master 代码边界。

---

# PART I：Review V1 修正验收

## 3. 命名和技术定位已修正

Case060 与项目文档已经使用：

```text
compact physical-slab low-memory experimental opt-in
Task27-derived physical-slab + 75D Floquet wave coarse
```

并明确区分：

```text
hierarchy/transfer infrastructure = validated research infrastructure
p/h multigrid solver = negative
compact physical-slab profile = workstation memory success
```

接受该修正。不得再写成：

```text
successful p/h GMG
production multilevel solver
new ordinary iterative default
```

## 4. Manifest、summary 和数值 checker 已接入

以下三项已经加入 `benchmark_manifest.csv`：

```text
task030_compact_h5
task030_compact_h3
task030_compact_h2
```

`benchmark_summary.csv` 现在由 manifest 可重复生成，不再依赖手工追加行。

Case060 checker 已从“文件存在性”扩展到：

```text
- benchmark/profile identity；
- metadata/provenance；
- source artifact SHA-256 格式；
- n_aux = 80；
- reported/condensed/full residual；
- official R/T/A；
- energy closure；
- direct delta；
- h5/h3/h2 memory Gate；
- h3 relative reduction alternative Gate；
- workstation/strong-workstation classification；
- ordinary default unchanged。
```

Codex 报告最终 checker 为：

```text
203 / 203 passed
```

接受 Benchmark060 的结构化 Gate 设计。

## 5. 内存归因措辞已修正

文档已明确：

```text
Task27 ILU1 与 Task030 ILU0 的 recorded factor nnz 相同；
当前统计不能证明 ILU0 factor-nnz compression；
主要内存下降来自：
  - factor-only lifecycle；
  - subdomain-local shift，避免全局 shifted-F 副本；
  - 销毁 source submatrix / KSP / PC wrappers；
  - restart100 -> restart90，减少 Krylov basis。
```

接受该修正。

## 6. PETSc 生命周期边界已记录

`factor-only` 使用当前 PETSc 3.24.0 complex build 中的公开 factor matrix 引用和 solve 生命周期。当前 serial/MPI2/MPI4 action/lifecycle tests 通过。

接受其作为显式 opt-in 机制，但必须保留：

```text
validated PETSc version = 3.24.0 complex
cross-version qualification = required before claiming portability
ordinary default = unchanged
```

---

# PART II：已接受的最终数值结果

## 7. Task030 compact profile

```text
outer operator = exact matrix-free A = F - C H^-1 D
outer Krylov = right FGMRES restart90
coarse = fixed 75D Floquet z-hat wave coarse
subdomains = 16 complete physical z-slabs
overlap = 0.25
local factor = ILU0
composition = symmetric pre/coarse/post
shift = subdomain-local diagonal shift
storage = factor-only
n_aux identity = 80 before condensation
```

| h | iterations | full true residual | peak incl. R/T/A | reduction vs Task027 | max R/T/A delta vs direct |
|---:|---:|---:|---:|---:|---:|
| 5 | 855 | `9.9249054e-7` | 1.696136 GB | 14.82% | `5.438e-9` |
| 3 | 962 | `9.9038905e-7` | 3.807503 GB | 25.08% | `7.719e-10` |
| 2 | 1,873 | `9.9722284e-7` | 9.374729 GB | 28.33% | `6.561e-9` |

接受：

```text
- reported/condensed/full residual identity；
- 80 propagating modes；
- official R/T/A；
- energy closure；
- h2 no swap；
- h2 peak <=10 GB；
- h3 relative reduction >=25%；
- ordinary default unchanged。
```

h3 的 3.807503 GB 略高于 3.8 GB 绝对目标，但任务合同允许：

```text
peak <= 3.8 GB OR reduction >=25%
```

它依靠 25.08% relative-reduction Gate 通过，文档现已准确说明。

## 8. 分类边界

可以使用：

```text
workstation_success_experimental_opt_in
compact physical-slab low-memory candidate
frozen-target workstation result
```

不能使用：

```text
strong_workstation_success
production default
strict mesh-independent solver
successful p/h multigrid
parameter-robust solver
```

h2 的 1873 步高于 1200 偏好，也略高于 Task027 的 1804 步。该 profile 的价值是 RAM 降低，不是速度或迭代数。

---

# PART III：剩余两个必需加固项

## 9. R1：最终 evidence 必须绑定到可识别的 clean source

### 9.1 当前问题

当前 h5/h3/h2 lightweight records 已诚实记录：

```text
metadata.commit_sha = bfb6586e...
tracked_source_dirty = true
provenance = working_tree_source_artifact_recovered_without_rerun
```

这比伪装成 clean rerun 正确得多；artifact SHA-256 也能证明所引用输出文件没有被无声改写。

但 `bfb6586e` 是 Task030 分支创建时的 master base，并不包含 Task030 后续实现。也就是说：

```text
artifact hash identifies output bytes
but commit_sha does not identify the exact source tree that produced them
```

因此当前证据可以作为 reviewed historical artifact，但不能作为“最终 HEAD clean canonical rerun”。

### 9.2 必需修正

不重跑 h2。只在最终实现 HEAD 上，以 clean tracked source 重跑：

```text
h5 full compact profile
h3 full compact profile
```

原因：

```text
- h5 较轻，可验证 final code path；
- h3 决定 >=25% engineering Gate；
- 两者足以验证 final committed implementation 与历史 h2 candidate identity；
- h2 约 43 分钟，不需要为 provenance 再消耗一次。
```

clean h5/h3 records 必须包含：

```text
commit_sha = exact final implementation commit
branch
tracked_source_dirty = false
git_dirty = false before output write
exact command
timestamp_utc
container image + real digest
host_environment_id
profile identity
physical model identity
80 modes
reported/condensed/full residual
official R/T/A
peak including RTA
source artifact SHA-256 or canonical lightweight output hash
```

### 9.3 h2 的最终身份

h2 保持现有数值，不重跑，改成明确身份：

```text
reviewed_historical_dirty_worktree_reference
```

并要求：

```text
- 保留 artifact SHA-256；
- 保留 exact command 和 timestamp；
- 保留 tracked_source_dirty=true；
- 引用 clean h5/h3 final-HEAD equivalence；
- 不宣称 h2 是 clean final-HEAD rerun；
- checker 对这一 provenance 使用显式 exemption，而不是静默忽略。
```

若 clean h5/h3 与现有 records 在 residual/RTA/memory 上出现明显不一致，则停止合并并调查；否则不需要重跑 h2。

## 10. R2：选择性合并 validated infrastructure，失败 solver lanes 不进入 production API

### 10.1 当前风险

`src/solvers/hcurl_multilevel.py` 同时包含：

```text
- validated active/master nonmatching transfer；
- Hermitian restriction / MPI cache；
- condensed Galerkin infrastructure；
- patch/Jacobi/p-h candidates；
- all-mode Woodbury research components；
- 已证明求解性能为 negative 的 lane 实现。
```

如果整文件作为普通 solver API 合入，会使“基础设施通过”和“solver 成功”在代码层再次混淆。

### 10.2 允许的处理方式

二选一：

```text
A. 推荐：拆分
   src/solvers/hcurl_transfer.py
   src/solvers/hcurl_galerkin.py
   benchmarks/research/task030_multilevel_candidates.py

B. 最小改动：保留单文件，但必须
   - 明确 module-level experimental/research-only docstring；
   - 不从 src/solvers/__init__ 或 ordinary runtime 导出失败 candidates；
   - candidate constructors 只由 Task030 research runner 使用；
   - capability_matrix 标为 negative/research-only；
   - validated transfer/Galerkin public surface 明确列出。
```

不要求删除负结果代码，但不得把失败 p/h/Woodbury profile 作为 ordinary solver 能力合并。

### 10.3 `physical_slab_two_level.py` 可合并边界

可合并：

```text
- subdomain-local diagonal shift；
- factor-only storage；
- symmetric post-smooth explicit option；
- empty-owner collective synchronization fix；
- diagnostics and lifecycle tests。
```

必须保持：

```text
- defaults preserve Task027 ordinary behavior；
- all new controls explicit opt-in；
- factor-only requires local_ksp_iterations=1；
- PETSc version qualification documented。
```

---

# PART IV：选择性合并建议

## 11. 建议进入 master

### 11.1 核心代码

```text
physical_slab_two_level.py:
  - local shift
  - factor-only lifecycle
  - symmetric pre/post composition option
  - MPI empty-owner collective fix
  - diagnostics and cleanup

validated H(curl) infrastructure:
  - active/master map
  - nonmatching transfer
  - MPC/Floquet backsub + homogenize
  - Hermitian restriction
  - MPI CSR cache
  - exact condensed Galerkin action
```

### 11.2 Benchmark 与测试

```text
- Benchmark060 contract；
- manifest rows；
- numeric/provenance checker；
- clean h5/h3 records；
- reviewed historical h2 record；
- transfer/hierarchy contracts；
- serial/MPI2/MPI4 tests；
- factor lifecycle and empty-owner tests。
```

### 11.3 文档

```text
- Task030 task/outcomes/reviews/responses；
- complete negative results；
- development_progress；
- solver guide；
- capability matrix；
- benchmark docs；
- theory/walkthrough；
- PETSc 3.24 factor-only qualification。
```

### 11.4 Experimental profile

允许在 master 中保留一个明确命名、显式参数调用的：

```text
compact_physical_slab_low_memory_experimental_opt_in
```

它不能成为 ordinary default。

## 12. 不得提升或不得进入普通 production API

```text
- current 792D p1 p/h coarse solver profile；
- Jacobi/layer/column/cell/slab p-h candidate profiles；
- all-mode Woodbury profile；
- x-harmonic 225D coarse；
- restart80；
- unqualified AMS/HX；
- unqualified TFQMR/GCR/recycling；
- h2 attempt1 incomplete field/RTA；
- heavy artifacts, transfer cache, matrices, fields, histories, raw logs；
- any reduced-mode shortcut；
- any ordinary default change。
```

失败算法的文档和轻量负结果应进入 master；失败实现只留 research-only 路径。

---

# PART V：Codex Response V2 要求

## 13. Response 文件

在同一分支提交：

```text
docs/task030_multilevel_hcurl_low_memory_iterative_solver/response_v2.md
```

逐项回应：

```text
R1 clean h5/h3 final-HEAD rerun and h2 reviewed-reference provenance
R2 validated infrastructure vs failed-lane code boundary
D1 final document status synchronization
V1 final checker/test/clean-tree evidence
```

## 14. D1：最终文档同步

更新：

```text
README.md
docs/README.md
docs/development_progress.md
docs/capability_matrix.md
docs/solver_guide.md
docs/benchmark.md
benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md
notes/reference/current_version_boundaries.md
notes/reference/code_walkthrough/32_physical_slab_two_level_pc.md
notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md
```

统一写明：

```text
Task030 status = workstation_memory_success_with_qualifications
final solver = Task27-derived compact physical-slab profile
p/h multigrid solver = negative
H(curl) transfer/Galerkin infrastructure = validated research infrastructure
h2 = reviewed historical dirty-worktree reference, not clean final-HEAD rerun
h5/h3 = clean final-HEAD reruns after Response V2
ordinary default = unchanged
master merge = pending final review and user approval
```

## 15. V1：最终验证

```text
ruff changed Python
compileall
Task026/027/029/030 focused tests
serial + MPI2 + MPI4 targeted tests
full unit discovery
documentation/retrospective contracts
benchmark checker --no-write
manifest -> summary regeneration identity
JSON/CSV parse
git diff --check
tracked source clean before final report
```

Response V2 必须记录：

```text
final HEAD
clean h5 source SHA / command / results
clean h3 source SHA / command / results
h2 reviewed-reference classification
checker passed/total
full tests passed/skipped
ordinary default unchanged
no h2 rerun
```

---

# 16. 当前最终判断

```text
numerical result = accepted
physical/modal identity = accepted
memory improvement = accepted
p/h multigrid success claim = rejected
compact physical-slab experimental profile = accepted
benchmark hardening = substantially complete
clean source reproducibility = one lightweight step remaining
selective merge hygiene = one code-boundary step remaining
```

完成 R1/R2 后，Task030 可以进入最终审查，并在用户明确许可后选择性合并 master。
