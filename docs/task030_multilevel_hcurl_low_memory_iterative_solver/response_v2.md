# RESPONSE V2：Task030 clean evidence、研究边界与最终验收

## 1. 回应结论

```text
review = review_report_v2.md
review_status = pass_with_two_required_hardening_items
Task030 status = workstation_memory_success_with_qualifications
final implementation HEAD = 5b81359daee0874793c44b019d9c914b334db483
final solver = Task27-derived compact physical-slab profile
p/h multigrid solver = negative
H(curl) transfer/Galerkin = validated research infrastructure
ordinary default changed = false
h2 rerun = no
master merge = pending final review and user approval
Task31 started = no
```

R1、R2、D1 与 V1 均已完成。Task030 可以进入最终审查，但本回应不自行合并 master，也不在当前 research branch 启动 Task31。

## 2. R1：clean h5/h3 与 historical h2

### 2.1 clean source 绑定方式

Windows host 在运行前验证 tracked source clean，并把 exact 40 位 full SHA 通过 `BENCHMARK_VERIFIED_CLEAN_SHA` 传给容器。runner 要求该 SHA 与 mounted container HEAD 完全相同，否则 fail closed；成功 record 同时写：

```text
commit_sha = 5b81359daee0874793c44b019d9c914b334db483
git_dirty = false
tracked_source_dirty = false
tracked_source_verification = host_git_clean_attestation
verified_clean_sha = 5b81359daee0874793c44b019d9c914b334db483
container_image = myfenics-stage4:task28
container_digest = sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d
host_environment_id = SK-20260601OSDE-docker-task30
```

一次错误的绝对脚本入口因 `ModuleNotFoundError: src` 在装配前立即停止；随后改用仓库根目录的 module entry。它不是数值尝试，也没有产生候选结果。

### 2.2 h5 clean final-HEAD rerun

```bash
mpiexec -n 4 /dolfinx-env/bin/python -m benchmarks.run_workstation_iterative --h-nm 5 --post-smooth --subdomain-local-shift --factor-only-storage --num-slabs 16 --overlap-layers 0.25 --ilu-levels 0 --restart 90 --max-it 1200 --rtol 1e-6 --rta-threshold 1.1e-6 --monitor-stride 90 --case-label task030_response_v2_clean_h5 --record /work/benchmarks/artifacts/cases/060/response_v2_clean/task030_response_v2_clean_h5.json --results-dir /work/benchmarks/artifacts/cases/060/response_v2_clean/h5
```

```text
timestamp_utc = 2026-07-14T00:53:26.067709+00:00
iterations / reason = 855 / 2
reported residual = 9.92490536958393e-7
condensed/full residual = 9.92490537712896e-7
n_aux = 80
peak incl. R/T/A = 1.687652587890625 GB
solve / total = 85.204035 / 109.166012 s
R/T/A = 0.089021603472 / 0.442588273219 / 0.468390122172
closure = -1.13728138018132e-9
heavy JSON SHA-256 = 2be05820cf69db67ba72b257c44624c08e15f7f7ceeae6e479eed2a9e68523f3
```

### 2.3 h3 clean final-HEAD rerun

```bash
mpiexec -n 4 /dolfinx-env/bin/python -m benchmarks.run_workstation_iterative --h-nm 3 --post-smooth --subdomain-local-shift --factor-only-storage --num-slabs 16 --overlap-layers 0.25 --ilu-levels 0 --restart 90 --max-it 1100 --rtol 1e-6 --rta-threshold 1.1e-6 --monitor-stride 90 --case-label task030_response_v2_clean_h3 --record /work/benchmarks/artifacts/cases/060/response_v2_clean/task030_response_v2_clean_h3.json --results-dir /work/benchmarks/artifacts/cases/060/response_v2_clean/h3
```

```text
timestamp_utc = 2026-07-14T01:01:53.083903+00:00
iterations / reason = 962 / 2
reported residual = 9.90389049160905e-7
condensed/full residual = 9.90389049239313e-7
n_aux = 80
peak incl. R/T/A = 3.7929115295410156 GB
reduction vs Task27 = 25.36981493490897%
absolute <=3.8 GB Gate = pass
relative >=25% Gate = pass
solve / total = 407.026776 / 453.372687 s
R/T/A = 0.004613032179 / 0.583653357750 / 0.411733611730
closure = 1.65917057870502e-9
heavy JSON SHA-256 = 48c9bb51b89a99b7ba1653f8c95f8450e7917f987274c1aef631464484275232
```

clean h5/h3 的 iterations、三残差、80 modes 与 official R/T/A 均与历史结果一致，内存没有出现反向漂移；因此无需触发 h2 调查或重跑。

### 2.4 h2 最终身份

h2 没有重跑。原 record 保留：

```text
commit_sha = bfb6586e030efd5208ebd796c39fdc31301e1d6e
git_dirty = true
tracked_source_dirty = true
provenance = working_tree_source_artifact_recovered_without_rerun
evidence_identity = reviewed_historical_dirty_worktree_reference
heavy JSON SHA-256 = 63b49fc9addcff97aefed335fdb625468f91aa702c71128cf977d1ee138d4b5a
iterations = 1873
full residual = 9.972228402e-7
peak incl. R/T/A = 9.374729 GB
```

record 另写 clean final-HEAD equivalence：implementation SHA、clean h5/h3 artifact hashes、candidate identity match 与 physical/modal identity match。checker 对 historical h2 使用显式 exemption，不静默忽略 dirty provenance，也不宣称 h2 是 clean final-HEAD rerun。

## 3. R2：validated infrastructure 与失败 lane 的代码边界

采用 Review V2 允许的最小改动方案 B：

- `src/solvers/hcurl_multilevel.py` module docstring 明确 research-only，不能推导 p/h GMG production capability；
- `VALIDATED_INFRASTRUCTURE_API` 与公共 `__all__` 只包含 active DoF、nonmatching transfer/cache/validation 和 condensed Galerkin；
- Jacobi、Galerkin multilevel PC、Modal Woodbury 等列入 `RESEARCH_ONLY_CANDIDATE_API`；
- 普通 `src.solvers` 不导出失败 candidates；
- 只有 `benchmarks.run_task030_multilevel_hcurl` 与模块 tests 直接导入 research candidates；
- API boundary tests 验证 ordinary package 不暴露失败 profile。

`physical_slab_two_level.py` 的 local shift、factor-only、post-smooth 与 empty-owner synchronization 保持显式 opt-in；默认参数继续保持 Task027 行为。factor-only 仍要求 `local_ksp_iterations=1`，且只资格化 PETSc 3.24.0 complex build。

## 4. D1：最终文档状态

Review 指定的 10 份项目文档以及 Task030 outcomes 已统一写明：

```text
Task030 status = workstation_memory_success_with_qualifications
final solver = Task27-derived compact physical-slab profile
p/h multigrid solver = negative
H(curl) transfer/Galerkin = validated research infrastructure
h5/h3 = clean final-HEAD reruns
h2 = reviewed historical dirty-worktree reference
ordinary default = unchanged
master = pending final review and user approval
Task31 = only after selective merge, from clean master
```

## 5. V1：最终验证

| 检查 | 结果 |
|---|---|
| Ruff changed Python | pass；9 files |
| `compileall src benchmarks` | pass |
| serial Task026/027/029/030 focused | 47/47 |
| MPI2 Task026/027/030 targeted | 每 rank 27/27 |
| MPI4 Task026/027/030 targeted | 每 rank 27/27 |
| full unit discovery | 161 passed，10 skipped |
| documentation + retrospective contracts | 19/19 |
| benchmark checker `--no-write` | 203/203 |
| benchmark checker normal | 203/203 |
| manifest -> summary twice | stable |
| summary SHA-256 | `71d4d3d6dd2be1e41f47d52b8b110caefa62f14342a67763479f5ccf27d9e99e` |
| Gate report SHA-256 | `ba657ab0979f6de80c3669e2e3552e1c9bdc62818cbe0820c97d327c546524ed` |
| tracked JSON / CSV parse | 757 / 354 pass |
| `git diff --check` | pass；仅 Windows line-ending warnings |
| tracked source after final commit | clean；用户本地 ignored/untracked scope 未纳入提交 |

全量测试首轮唯一失败是 Task retrospective contract 仍要求旧分类字符串 `workstation_success`。将其更新为 Review V2 的精确状态后，全量 161/161 通过；没有数值或实现回归失败。

## 6. 最终边界与下一步

Task030 的数值、物理/modal identity 与工作站内存改进已接受；限定来自 h2 historical provenance、1873 步高于 1200 偏好、单一冻结目标与 PETSc 版本范围。最终成功机制不是 p/h GMG，ordinary default 没有改变。

本分支现在只请求 final review。只有 final review 通过并获得用户明确许可后，才按 review 的 selective merge 边界合入 master；Task31 随后从该 clean master 新建独立分支。
