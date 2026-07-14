# REVIEW REPORT V3：Task030 最终验收与 Task031 启动许可

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260713-task30-multilevel-hcurl-low-memory-iterative
base master = bfb6586e030efd5208ebd796c39fdc31301e1d6e
final implementation commit = 5b81359daee0874793c44b019d9c914b334db483
reviewed response = response_v2.md
```

本轮复核 Review V2 要求的：

```text
R1 clean final-implementation h5/h3 rerun
R2 validated infrastructure / failed candidate API boundary
D1 final documentation wording
V1 final tests, checker and reproducibility
```

---

# 2. 最终结论

```text
review_status = pass_for_selective_merge

task030_status = workstation_memory_success_with_qualifications
compact_physical_slab_profile = accepted_as_experimental_opt_in
strong_workstation_success = no
ordinary_default_changed = no

h5_clean_final_head = pass
h3_clean_final_head = pass
h2_historical_reference = accepted_with_explicit_provenance_qualification
p_h_multigrid_solver = negative
hcurl_transfer_galerkin_infrastructure = accepted_as_research_infrastructure
research_candidate_api_boundary = pass
benchmark_and_checker = pass
project_documentation = pass

master_merge = allowed_after_user_explicit_approval
Task031_start = allowed_only_after_Task030_selective_merge_to_clean_master
```

没有发现新的数值、物理、模态、MPI 或对象生命周期阻塞问题。

准确结论保持不变：

> Task030 的成功求解机制仍是 Task027-derived physical-slab Schwarz + fixed 75D Floquet wave coarse。Task030 通过 symmetric pre/coarse/post、ILU0、subdomain-local shift、factor-only storage 和 restart90 显著降低内存。真正 p/h multigrid、patch+p/h 和 all-mode Woodbury 没有成功。

---

# 3. Clean final-implementation evidence

clean rerun 绑定：

```text
commit = 5b81359daee0874793c44b019d9c914b334db483
git_dirty = false
tracked_source_dirty = false
verified_clean_sha = same full SHA
container digest = sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d
```

正式结果：

| h | iterations | full true residual | peak incl. R/T/A | status |
|---:|---:|---:|---:|---|
| 5 | 855 | `9.924905377e-7` | 1.687653 GB | clean final-head pass |
| 3 | 962 | `9.903890492e-7` | 3.792912 GB | clean final-head pass |
| 2 | 1873 | `9.972228402e-7` | 9.374729 GB | reviewed historical reference |

h5/h3 clean records reproduce iterations, all residuals, 80 modes and official R/T/A. h3 now independently passes both:

```text
absolute RSS <= 3.8 GB
relative reduction >= 25% vs Task027
```

The final implementation commit is followed only by records, checker, documentation and contract-test changes. No solver source changed after the clean h5/h3 reruns.

---

# 4. h2 provenance decision

h2 was not rerun and remains explicitly marked:

```text
reviewed_historical_dirty_worktree_reference
```

This is accepted because:

```text
- original heavy artifact SHA-256 is fixed;
- original command, image and dirty-source status are preserved honestly;
- candidate, physical and modal identities match clean h5/h3;
- clean final-head h5/h3 reproduce the historical numerical behavior;
- checker applies an explicit h2 exemption rather than silently treating it as clean;
- h2 remains experimental and ordinary default stays unchanged.
```

This qualification must remain visible after merge. It must not be rewritten as a clean final-head h2 rerun.

---

# 5. API and merge boundary

## 5.1 Approved for selective merge

### Production-safe opt-in components

```text
src/solvers/physical_slab_two_level.py
```

Approved additions:

```text
- subdomain-local diagonal shift;
- factor-only subdomain storage;
- symmetric post-smoothing option;
- empty-owner collective synchronization;
- cleanup/lifecycle and MPI tests.
```

All remain explicit opt-in. Existing Task027/ordinary defaults must remain unchanged.

### Validated research infrastructure

From `src/solvers/hcurl_multilevel.py`, only the declared validated infrastructure surface is accepted:

```text
ActiveDofMap
NonmatchingTransfer
CondensedGalerkinCoarse
build_active_dof_map
build_nonmatching_active_transfer
save/load transfer cache
validate transfer action
build condensed Galerkin coarse
```

The module-level `__all__`, docstring and API-boundary tests correctly prevent ordinary `src.solvers` from presenting failed candidates as supported solvers.

### Benchmark, records and documents

Approved:

```text
- Case060;
- manifest and reproducible benchmark summary;
- Task030-specific numeric/provenance gates;
- clean h5/h3 records;
- explicitly qualified historical h2 record;
- positive/negative outcomes;
- serial/MPI2/MPI4 tests;
- development progress, capability matrix, solver guide, theory and walkthrough updates;
- Task031 task book.
```

## 5.2 Must not be promoted

The following remain research-negative or unqualified:

```text
- current 792D p1 p/h coarse solver;
- Jacobi/layer/column/cell/slab p-h profiles;
- all-mode Modal Woodbury profile;
- x-harmonic enlarged coarse;
- restart80;
- AMS/HX, TFQMR, GCR or other unqualified Krylov profiles;
- any claim that p/h GMG succeeded;
- any claim that ILU0 factor-nnz compression was proven;
- heavy transfer caches, matrices, fields, histories and logs.
```

---

# 6. Verification accepted

```text
Ruff = pass
compileall = pass
serial focused = 47/47
MPI2 targeted = 27/27 per rank
MPI4 targeted = 27/27 per rank
full tests = 161 passed, 10 skipped
documentation contracts = 19/19
benchmark checker = 203/203, no-write and normal
manifest -> summary regeneration = stable
tracked JSON/CSV parse = pass
git diff --check = pass
final tracked source = clean
```

The checker now validates real Task030 fields: provenance, artifact hashes, solver identity, explicit opt-in status, frozen physical/modal identity, three residuals, R/T/A, energy closure, direct delta, h3 memory gate, h2 memory gate and non-strong classification.

---

# 7. Merge and Task031 instruction

The user may now authorize Codex to:

```text
1. selective merge Task030 approved files into master;
2. run lightweight master release checks;
3. record the Task030 merge SHA;
4. create codex/20260714-task31-compact-pc-memory-optimization from that clean master;
5. read Task031 task.md and start execution.
```

Task031 must not be created from the Task030 research branch and must not inherit unmerged failed-lane code accidentally.

No Task030 heavy rerun is required before Task031. The historical h2 qualification remains an explicit limitation, while Task031 will generate its own clean-source records for any new best profile.

---

# 8. Final decision

```text
Task030 final technical review = PASS
selective merge = RECOMMENDED
ordinary default change = FORBIDDEN
Task031 execution after clean-master merge = APPROVED
```
