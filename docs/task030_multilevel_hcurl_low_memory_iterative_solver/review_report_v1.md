# REVIEW REPORT V1：Task030 多层 H(curl) 探索与 compact physical-slab 低内存结果审查

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260713-task30-multilevel-hcurl-low-memory-iterative
base = master@bfb6586e030efd5208ebd796c39fdc31301e1d6e
reviewed_head = 59b2f8f57b5d31e4e545186de711b4311f650621
scope = Task030 implementation + Case060 + outcomes + project documentation
```

本轮重点审查：

```text
- Task030 是否真正实现并验证了 H(curl) hierarchy/transfer/Galerkin infrastructure；
- p/h multigrid、patch、Woodbury 等 lane 是否出现求解正反馈；
- 最终 h5/h3/h2 成功候选是否实际上延续 Task027 的求解框架；
- h2 约 9.37 GB、1873 步、full residual 与 official R/T/A 是否可信；
- 内存下降究竟来自什么对象和生命周期；
- h2 解锁和资格复跑是否符合任务 Gate；
- Benchmark060、lightweight records、provenance 和 checker 是否达到可合并标准；
- 哪些基础设施可进入 master，哪些 solver profile 必须保持 research/explicit opt-in。
```

---

# 2. 审查结论

```text
review_status = changes_required

task30_overall_classification = workstation_memory_success_with_qualifications
workstation_success = pass_for_frozen_target_experimental_opt_in
strong_workstation_success = no
ordinary_default_changed = no

hcurl_transfer_infrastructure = pass_with_scope_qualification
condensed_galerkin_infrastructure = pass
p_h_multigrid_solver = fail
patch_p_h_solver_family = fail
all_mode_woodbury = fail
expanded_wave_coarse = no_positive
compact_physical_slab_candidate = pass
h2_numeric_and_memory_gate = pass
h2_iteration_preference = fail

benchmark_case_contract = pass
benchmark_numeric_gate_integration = fail
benchmark_provenance = fail
benchmark_summary_regeneration_safety = fail
documentation_accuracy = pass_with_required_wording_hardening

heavy_h5_h3_h2_rerun_required = no
new_solver_research_required_before_response = no
master_merge = blocked_pending_response_v1
```

准确的技术结论是：

> Task030 尝试了多种新多层路线，但真正产生完整 h5/h3/h2 正结果的仍然是 Task027 的 exact-condensed + physical z-slab Schwarz + 75D Floquet wave coarse 框架。Task030 的工程突破来自对该框架的对称 pre/post smoothing、ILU0、subdomain-local shift、factor-only storage 和 FGMRES restart90 优化，而不是真正 p/h multigrid 求解器的成功。

这不是对 Task030 的否定。Task030 同时取得了两类独立成果：

```text
A. infrastructure success：
   nonmatching H(curl) transfer、MPC/Floquet-aware active mapping、Hermitian restriction、
   MPI cache 和 exact condensed Galerkin action 得到验证；

B. workstation memory success：
   冻结 h2 target 在保持 80 modes、true residual 和 official R/T/A 的前提下，
   峰值从 13.080 GB 降至 9.375 GB。
```

但必须避免把 A 写成“GMG 已成功”，也避免把 B 写成“全新 multilevel solver”。

---

# PART I：已接受的数值结果

## 3. Task027 基线身份

Task027/Case031 canonical baseline：

| h (nm) | FE DoF | iterations | full true residual | peak incl. R/T/A |
|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | `9.8394899e-7` | 1.991173 GB |
| 3 | 198,438 | 993 | `9.9326487e-7` | 5.082275 GB |
| 2 | 615,108 | 1,804 | `9.9973780e-7` | 13.080257 GB |

其核心结构为：

```text
exact matrix-free condensed A = F - C H^-1 D
+ right FGMRES restart100
+ 16 complete physical z-slabs
+ overlap0.25
+ shifted local ILU1
+ two shifted-F smoothing steps
+ fixed 75D Floquet z-hat wave coarse
```

Task030 的最终成功候选没有替换这套全局慢误差机制。

## 4. Task030 最终 compact 候选

最终候选：

```text
coarse = fixed 75D Floquet z-hat wave coarse
subdomains = 16 complete physical z-slabs
overlap = 0.25
local factor = ILU0
composition = symmetric pre/coarse/post
shift = subdomain-local diagonal shift
storage = factor-only
outer = right FGMRES restart90
outer operator = exact condensed A
n_aux identity = 80 before condensation
ordinary default = unchanged
```

正式结果：

| h | iterations | full true residual | peak incl. R/T/A | memory reduction vs Task027 | max R/T/A delta vs direct |
|---:|---:|---:|---:|---:|---:|
| 5 | 855 | `9.9249054e-7` | 1.696136 GB | 14.82% | `5.438e-9` |
| 3 | 962 | `9.9038905e-7` | 3.807503 GB | 25.08% | `7.719e-10` |
| 2 | 1,873 | `9.9722284e-7` | 9.374729 GB | 28.33% | `6.561e-9` |

接受以下结论：

```text
- h5/h3/h2 reported、condensed true、full augmented true residual 一致；
- official R/T/A 与 direct reference 一致到约 1e-9–1e-8；
- 全部 80 个传播 modes 保持；
- h2 无 swap；
- h2 峰值低于 10 GB；
- ordinary default 未改变。
```

## 5. h2 的分类边界

h2 通过：

```text
RSS <= 10 GB
full true residual <= 1e-6
same 80 modes
official R/T/A pass
energy closure pass
```

但未通过：

```text
preferred iterations <= 1200
strong target iterations <= 800
preferred RSS <= 8 GB
```

所以只能使用：

```text
workstation_success_experimental_opt_in
```

不得使用：

```text
strong_workstation_success
mesh-independent multigrid
production-default multilevel solver
```

h2 相对 Task027 的迭代数从 1804 增加到 1873，增加约 3.8%；solve time 也略有增加。该 profile 的价值是内存，不是速度。

---

# PART II：真正 p/h multigrid 路线的审查

## 6. H(curl) transfer/Galerkin 基础设施通过

当前 MPI4 target transfer：

```text
fine full / active DoF = 44,698 / 40,800
coarse full / active DoF = 1,067 / 792
transfer shape = 44,698 x 792
transfer nnz = 145,998
zero columns = 0
adjoint identity relative error = 1.586e-15
fresh/cache action relative error = 6.410e-15
```

接受以下基础设施成果：

```text
- active/master DoF mapping；
- nonmatching N1curl interpolation data；
- MPC slave back-substitution；
- Floquet homogenization；
- corner/periodic trace handling；
- Hermitian restriction P^H；
- MPI CSR cache；
- exact condensed Galerkin A_c = P^H(F-C H^-1D)P；
- 全部 80 modes 进入 coarse action。
```

但当前通过的 correctness 范围是：

```text
interpolation/action/adjoint/constraint consistency
```

尚未证明：

```text
- 严格 commuting projection；
- discrete de Rham sequence compatibility；
- gradient/near-null-space preservation；
- 多层 h-GMG convergence theory；
- 任意 PETSc/DOLFINx 版本兼容性。
```

因此应定位为 `validated research infrastructure`。

## 7. 当前 p/h solver 明确失败

五个正式 h5/100-step 候选：

| candidate | true residual | ratio vs Task027 h5 baseline | disposition |
|---|---:|---:|---|
| Jacobi + 792D p/h coarse | 0.680155 | 264.27x | stop |
| layer patch + p/h coarse | 0.374864 | 145.65x | stop |
| vertical column + p/h coarse | 0.513599 | 199.55x | stop |
| cell patch + p/h coarse | 0.512730 | 199.22x | stop |
| slab ILU0 + p/h coarse | 0.561064 | 218.00x | stop |

相同 slab smoother：

```text
without p/h coarse, 20-step residual = 0.381817
with 792D p/h coarse              = 0.685751
```

所以结论不是“transfer 有 bug”，而是：

> 当前 h5/p2 → h10/p1 的 792D coarse space 未捕获该高频 Maxwell/Floquet/DtN target 的梯度近核、grazing-wave 和 wave-coherent 慢误差，并在当前 additive/multiplicative composition 中主动伤害了已有 wave coarse 机制。

## 8. 不得过度推广负结论

当前主要验证的是一次非常激进的：

```text
h5/p2 active 40,800 DoF
→ h10/p1 active 792 DoF
```

尚未完整验证：

```text
h5/p2 -> h5/p1 -> h7.5/p1 -> h10/p1
真正多级 p/h hierarchy
commuting projection
explicit gradient/near-null auxiliary spaces
shifted p1 AMS/HX integrated hierarchy
level-dependent robust smoother
```

因此文档必须写：

```text
current 792D p/h coarse failed as solver
```

不得写：

```text
p/h multigrid is impossible
H(curl) GMG has been disproven
```

## 9. all-mode Woodbury 失败

接受以下负结果：

```text
weak p/h FE inverse:
  residual 0.676603 -> 0.657702

Task027 PC:
  smoke residual about 0.033745 -> 0.036275
```

small Schur conditioning 不是主要问题；主要问题仍是 `M_F^-1` 的 FE response quality。该 lane 不得提升。

---

# PART III：最终内存优化机制

## 10. 对称 pre/post 是主要收敛正反馈

Task027-style ILU1 配合 symmetric pre/post：

```text
100-step residual = 1.273503e-3
ratio vs canonical h5 baseline = 0.4948
```

这是本轮唯一明确的强收敛正反馈。

随后：

```text
ILU0 symmetric pre/post:
  100-step residual = 1.865566e-3

factor-only + local shift:
  same residual, lower retained RSS

restart90:
  100-step residual = 1.992945e-3
  last point passing weak-positive Gate

restart80:
  ratio = 0.8905
  rejected
```

接受 Codex 按正反馈漏斗继续推进和及时停止 restart80。

## 11. factor-only 生命周期优化通过

实现逻辑：

```text
factor = pc.getFactorMatrix()
factor.incRef()
destroy KSP
destroy source submatrix
retain factor + rhs + solution only
apply via factor.solve(...)
```

并且：

```text
serial/MPI2/MPI4 action equivalence ≈ 2e-12
lifecycle/destroy tests pass
```

接受该机制作为显式 opt-in 可复用组件。

### 必须保留的限定

该路径依赖当前 PETSc 3.24/petsc4py 对 `PC.getFactorMatrix()`、引用计数和 factor matrix lifetime 的公开/实际语义。合并文档必须明确：

```text
validated environment = PETSc 3.24.0 complex build in qualified local image
cross-version compatibility = requires regression
```

## 12. factor nnz 口径不能支持 ILU0 fill 降低声明

当前 memory breakdown 中 Task027 ILU1 与 Task030 ILU0 的：

```text
global slab factor nnz
```

完全相同：

```text
h5 = 7,046,752
h3 = 30,329,104
h2 = 95,617,608
```

所以当前 evidence **不能证明** ILU0 的 stored factor nnz 比 ILU1 更少。

Codex 必须在 response 中说明：

```text
- `global_slab_factor_nnz` 当前可能反映 PETSc factor object 的有限统计口径；
- 不能据此宣称 ILU0 fill 显著减少；
- 已观测内存下降主要归因于 factor-only lifecycle、subdomain-local shift、
  被释放的 source submatrix/KSP/PC wrapper，以及 restart90 Krylov basis reduction；
- ILU0 的角色是保持较低 setup/apply 成本并与 symmetric composition 配合，
  不是已证明的 factor-nnz compression。
```

如能从 PETSc factor matrix 获得可信 `nz_used` 差异，可补充；否则保持 `measurement_unresolved`，不要求重跑 h2。

---

# PART IV：h2 解锁与资格复跑

## 13. 解锁过程通过

h5/h3 满足：

```text
h5 full numeric Gate pass
h3 full numeric Gate pass
h3 memory reduction = 25.08%
h3/h5 iteration ratio = 1.1251
same 80 modes
no swap
ordinary default unchanged
```

注意：

```text
h3 observed RSS = 3.807503 GB
```

略高于 3.8 GB absolute target，但任务书允许以下二选一：

```text
RSS <= 3.8 GB
OR
memory reduction >= 25% vs Task027
```

因此 h3 是通过第二个 Gate，而不是通过 3.8 GB 绝对 Gate。文档必须明确这一点。

独立 h2 prediction：

```text
affine central = 9.5298 GB
power-law central = 7.0337 GB
conservative upper = 10.9593 GB
```

允许唯一 h2 candidate 运行。

## 14. attempt1 与 qualification rerun 处理正确

首次 h2：

```text
max_it = 1800
true residual = 1.461130e-6
peak RSS = 9.342113 GB
classification = memory pass / residual fail
official R/T/A = not produced
```

随后资格复跑：

```text
same PC
same restart
same physics
same modal set
only max_it 1800 -> 2100
common monitor points identical
converged at 1873
```

接受这次资格复跑为同一 candidate 的 continuation，不是新的 h2 参数搜索。

---

# PART V：P0 合并前修正

## 15. P0-A：补齐 Task030 lightweight record provenance

当前：

```text
records/best_h5.json
records/best_h3.json
records/best_h2.json
```

缺少仓库正式 benchmark 通常要求的完整 metadata。

每个正式 Task030 lightweight record 至少增加：

```text
benchmark_id
metadata.commit_sha
metadata.branch
metadata.git_dirty
metadata.tracked_source_dirty
metadata.command
metadata.timestamp_utc
metadata.container_image
metadata.container_digest
metadata.host_environment_id
metadata.provenance
metadata.actual_source_artifact_root
metadata.source_artifact_sha256（若 artifact 仍可访问）
physical_model
qualified_profile / qualification_deviations
modal order identity / n_aux
coarse identity
```

要求：

```text
- 使用实际重型运行时的 source commit，不得写最终文档 commit 冒充；
- 若当时 tracked source clean，应明确 tracked_source_dirty=false；
- 若无法证明，诚实标记 provenance qualification，不得伪造 clean；
- h2 不要求重跑；优先从 source artifact/run log 补充。
```

## 16. P0-B：将 Case060 接入真正数值 Gate

当前 `benchmark checker 150/150` 对 Case060 主要检查文件存在。需要为 Case060 增加实际 Gate，至少验证：

```text
best_h5/best_h3/best_h2 benchmark_id
metadata completeness
source commit relation
tracked-source clean/provenance qualification
ordinary default unchanged
same n_aux = 80
h5/h3/h2 KSP reason > 0
reported/condensed/full residual <= 1e-6
reported/true residual consistency
R/T/A complete
energy closure
R/T/A delta vs direct
h3 relative memory reduction >=25% OR RSS <=3.8 GB
h3/h5 iteration ratio <=2
h2 RSS <=10 GB
h2 classification does not claim strong success
```

同时加入：

```text
p/h solver disposition = negative
final solver identity = compact physical-slab profile
```

防止后续文档把 hierarchy infrastructure 错写成 successful GMG。

## 17. P0-C：修复 benchmark manifest/summary 的可再生性

当前 `benchmarks/benchmark_summary.csv` 手工增加 Task030 三行，但 `check_benchmarks.py` 会根据 manifest 重写整个 summary；而本分支没有同步把 Task030 三个正式 record 加入 manifest。

必须选择一种一致方案：

### 推荐方案

```text
- 在 benchmark manifest 中加入 Task030 h5/h3/h2 experimental entries；
- canonical_record 指向 Case060 lightweight records；
- checker 根据 manifest 可重复生成完全相同的 summary；
- 运行 checker 非 --no-write 后 git diff 应为空。
```

不得保留“手工 summary 中有 Task030，但重新生成会消失”的状态。

## 18. P0-D：统一准确命名

项目级文档、Case060 和 outcomes 必须统一使用：

```text
compact physical-slab low-memory experimental profile
```

或等价明确名称。

必须明确：

```text
Task30 hierarchy infrastructure = success
Task30 p/h multigrid solver = failed
Task30 workstation memory result = success
final successful solver = Task27-derived physical-slab/wave-coarse architecture
```

避免使用可能误导的：

```text
successful multilevel H(curl) solver
successful p/h GMG
GMG workstation profile
```

任务目录名称可以保留历史任务身份，但结果分类必须准确。

## 19. P0-E：文档同步

Codex 应在 response 中同步检查并修正：

```text
docs/development_progress.md
docs/README.md
docs/capability_matrix.md
docs/solver_guide.md
docs/benchmark.md
benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md
notes/theory/iterative_solver_and_preconditioner.md
notes/reference/code_walkthrough/32_physical_slab_two_level_pc.md
notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md
notes/reference/current_version_boundaries.md
```

`development_progress.md` 必须清楚说明：

```text
1. 为什么尝试真正 p/h multigrid；
2. transfer/Galerkin 做到了什么；
3. 五类 p/h solver 为什么判定失败；
4. 最终正反馈为何来自 Task27 框架；
5. symmetric pre/post、factor-only、local shift、restart90 各自作用；
6. h5/h3/h2 数值与内存对比；
7. h2 1873 步的限制；
8. 最终合并边界；
9. 下一步不能简单继续扫当前 792D coarse。
```

---

# PART VI：可合并与不可提升的内容

## 20. 建议合并的通用组件

P0 完成并复审后，可考虑合并：

```text
- active/master-aware nonmatching H(curl) transfer；
- MPC/Floquet-aware backsubstitution/homogenization；
- Hermitian restriction；
- MPI CSR transfer cache；
- exact condensed Galerkin infrastructure；
- transfer/action/adjoint tests；
- subdomain-local diagonal shift；
- factor-only subdomain storage；
- symmetric pre/post two-level composition explicit option；
- uneven owner collective fix；
- Case060 benchmark contracts、轻量 records、negative evidence；
- documentation and retrospective updates。
```

## 21. 最终 compact profile 的合并身份

可以作为：

```text
explicit experimental opt-in workstation profile
```

前提：

```text
- 命令完整记录；
- ordinary default 不变；
- profile 名称不含成功 GMG 暗示；
- frozen-target scope 明确；
- h2 1873-step limitation 明确；
- provenance 和 checker Gate 完成。
```

## 22. 不得提升

```text
- current 792D p/h coarse solver；
- Jacobi/layer/column/cell/slab p/h profiles；
- all-mode Woodbury candidate；
- 225D x-harmonic coarse；
- expanded z coarse；
- no-overlap pre-only；
- restart80；
- AMS/HX、TFQMR、GCR、GCRO-DR 未完成 target qualification 的路线；
- h2 attempt1 incomplete result；
- heavy transfer/matrix/field/history/log artifacts；
- any reduced-mode shortcut；
- any ordinary-default change。
```

---

# PART VII：下一步技术判断

## 23. Task30 后不建议继续微调当前单点 profile

当前 compact profile 已达到约 9.37 GB，但 1873 步仍较高。继续只扫描：

```text
restart 85/88/92
ILU relaxation
minor overlap fractions
small post-smooth weights
```

很可能只得到单点微调，不能解决未来千万 DoF 的架构问题。

## 24. 下一阶段建议

建议下一任务优先做：

```text
parameter robustness + automatic fallback qualification
```

至少覆盖：

```text
- incidence angle；
- wavelength/material loss；
- MPI partition/rank count；
- mode count changes induced by physics；
- h5/h3 representative parameter matrix；
- compact profile failure detector；
- fallback to Task27 profile or direct reference。
```

同时可保留一个独立长期研究 lane：

```text
commuting H(curl) multigrid
+ explicit gradient/near-null auxiliary spaces
+ intermediate p1 levels
+ shifted-level AMS/HX
```

但该方向应作为新的基础理论/架构任务，不应继续扩大当前 792D coarse 参数扫描。

---

# PART VIII：Response 要求

## 25. Codex Response V1

在同一分支新增：

```text
docs/task030_multilevel_hcurl_low_memory_iterative_solver/response_v1.md
```

逐项回应：

```text
P0-A provenance
P0-B Case060 numeric checker Gates
P0-C manifest/summary regeneration
P0-D naming and classification
P0-E documentation synchronization
factor-nnz interpretation
PETSc factor-only version boundary
```

## 26. 最低验证

```text
ruff changed Python
compileall
Task026/027/030 focused tests
MPI1/MPI2/MPI4 focused tests
full src/test discovery
documentation/retrospective contracts
benchmark checker --no-write
benchmark checker normal write then git diff clean
JSON/CSV parse
git diff --check
tracked source clean
```

不要求重新运行：

```text
h5 full
h3 full
h2 full
```

除非 Codex 无法从原 source artifact 恢复任何可信 provenance；即使如此，也应先说明缺失，不得默认重跑 h2。

---

# 27. 最终状态

```text
Task030 numerical result = ACCEPTED WITH QUALIFICATIONS
Task030 compact memory result = ACCEPTED
Task030 p/h multigrid claim = REJECTED
Task030 infrastructure = PROVISIONALLY ACCEPTED
Task030 benchmark/provenance = CHANGES REQUIRED
Task030 ordinary default = UNCHANGED
Task030 master merge = WAIT FOR RESPONSE V1 AND FINAL REVIEW
```

一句话总结：

> Task30 试了很多新方向，但当前真正成功的仍是 Task27 的物理 slab + Floquet 波动粗空间框架；Task30 的贡献是把它改造成一个约 9.37 GB 的 compact experimental profile，并建立了未来真正 H(curl) multigrid 所需的 transfer/Galerkin 基础设施。