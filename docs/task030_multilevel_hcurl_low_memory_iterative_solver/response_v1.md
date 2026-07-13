# RESPONSE V1：Task030 Review V1 更正回应

## 1. 当前身份

```text
review = review_report_v1.md at remote commit 3f0ff57
response_scope = P0-A ... P0-E
numerical_rerun = no
ordinary_default_changed = false
master_merge = wait_for_final_review
```

接受 Review V1 的核心判断：Task30 的数值与工作站内存结果在冻结目标上成立，但最终成功求解器不是 p/h GMG，而是 Task27-derived physical-slab + 75D wave-coarse 架构。统一名称为：

```text
compact physical-slab low-memory experimental profile
```

H(curl) transfer/Galerkin 被记录为 `validated_research_infrastructure`；五个 p/h multigrid solver 候选仍为 `negative`。

## 2. P0-A：正式记录 provenance

没有重跑 h5/h3/h2。直接从本地保留的原始重型 JSON 恢复实际运行 metadata，并计算 source artifact SHA-256：

| record | source commit | tracked dirty | timestamp UTC | artifact SHA-256 |
|---|---|---:|---|---|
| best_h5 | `bfb6586e030efd5208ebd796c39fdc31301e1d6e` | true | `2026-07-13T16:03:00.200672+00:00` | `2dc68e4001d3fb6b04d239ea3f7dbfb7e46a63f5afcb566e2065eb1e13815878` |
| best_h3 | `bfb6586e030efd5208ebd796c39fdc31301e1d6e` | true | `2026-07-13T16:00:18.839795+00:00` | `b76c991c72d30a4e8b575cfc077ad633ea2ea50dbead1ebc8f4626d9eb389331` |
| best_h2 | `bfb6586e030efd5208ebd796c39fdc31301e1d6e` | true | `2026-07-13T17:38:22.323888+00:00` | `63b49fc9addcff97aefed335fdb625468f91aa702c71128cf977d1ee138d4b5a` |

三份记录均写入实际 branch、完整命令、container image/digest、host id、artifact root、冻结物理模型、80 modes、75D coarse identity、`qualified_profile=false` 与具体 deviations。原运行以 `bfb6586e` 为 base，但 Task30 source 当时尚未提交，所以诚实标记：

```text
git_dirty = true
tracked_source_dirty = true
provenance = working_tree_source_artifact_recovered_without_rerun
```

不把当前 response commit 冒充数值运行 commit，也不宣称 clean-source provenance。

## 3. P0-B：Case060 真实数值 Gate

`check_benchmarks.py` 已为三份正式记录增加实际检查：

- benchmark/provenance metadata 完整性、source commit relation 和 artifact SHA-256；
- final solver identity、p/h negative disposition、显式 opt-in 和 ordinary default unchanged；
- 冻结物理模型、80 auxiliary modes 与 75D wave coarse；
- KSP positive reason、reported/condensed/full residual 及一致性；
- official R/T/A、energy closure 和重新计算的 direct delta；
- h3 `RSS <= 3.8 GB OR reduction >= 25%`、h3/h5 iteration ratio；
- h2 RSS、分类和 `strong_workstation_success=false`。

checker 当前为 203/203。h3 的实测 3.807503 GB 没有通过绝对分支，明确由 25.08% 相对降幅分支通过。

## 4. P0-C：manifest/summary 可再生

`benchmark_manifest.csv` 已加入 Task30 h5/h3/h2 三个 `iterative_experimental` entries，canonical record 指向 Case060 best records。normal checker 会从 manifest 重写 summary；连续两次 normal generation 的 summary/report 哈希保持一致，证明不是依赖手工追加行。

## 5. P0-D/P0-E：命名与文档

项目级文档、Case060、outcomes、理论和 walkthrough 已统一区分：

```text
hierarchy infrastructure = validated research infrastructure
p/h multigrid solver = negative
workstation memory result = success with qualifications
final successful solver = Task27-derived physical-slab/wave-coarse architecture
profile = compact physical-slab low-memory experimental profile
```

ordinary default、Task27 canonical records 和 Case031 均未修改。master 仍等待 final review。

## 6. factor nnz 与 PETSc 版本限定

Task27 ILU1 与 Task30 ILU0 的 `global_slab_factor_nnz` 完全相同：h5/h3/h2 分别为 7,046,752 / 30,329,104 / 95,617,608。该 PETSc factor-object 统计保持 `measurement_unresolved`，不能支持 ILU0 factor-nnz compression 声明。

已观测内存下降主要归因于：

- subdomain-local shift 不再保留完整 shifted-F；
- factor-only setup 后释放 source submatrix/KSP/PC wrapper；
- 逐块 factorization 限制对象同时驻留；
- FGMRES restart90 减少 Krylov basis。

ILU0 的角色是与 symmetric pre/post composition 配合并保持较低 setup/apply 成本，不是已证明的 factor-nnz compression。factor-only 生命周期只在 qualified local image 的 PETSc 3.24.0 complex build 验证；跨 PETSc/petsc4py 版本必须重跑 action/lifecycle 回归。

## 7. 验证

最终验证结果记录在 [`outcomes/test_summary.md`](outcomes/test_summary.md)。本次 Review V1 收口不运行新的 h5/h3/h2 重型数值计算。

## 8. 回应结论

```text
P0-A provenance = addressed with honest tracked-dirty qualification
P0-B numeric gates = addressed
P0-C manifest/summary reproducibility = addressed
P0-D accurate naming = addressed
P0-E documentation sync = addressed
ordinary default = unchanged
master merge = wait for final review
```
