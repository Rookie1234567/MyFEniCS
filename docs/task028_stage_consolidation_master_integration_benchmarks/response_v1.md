# Codex Response V1

## 1. 总体回应

| 项目 | 状态 |
|---|---|
| branch | `codex/20260712-task28-stage-consolidation` |
| review baseline | `review_report_v1.md` |
| implementation commits | `d708c63`, `3b3abf0` |
| P0 closed | 6/6 |
| automatic benchmark gates | 58/58 pass |
| environment decision | `pass_with_environment_qualification` |
| ordinary default changed | false |
| master merge | 等待 V2 审查和用户同意 |

Task28 core solver 数值逻辑没有改变。Review V1 后唯一重新运行的 workstation case 是 h=5，用于验证新配置、metadata、qualification 和 artifact root；它仍为 1201 次迭代且 R/T/A 逐位一致。

## 2. P0-1 Benchmark Output Root

| 必需字段 | 回应 |
|---|---|
| issue | canonical 参数和 direct records 把历史 `results/` 写成 benchmark 证据，实际边界不清 |
| root_cause | runner 与 scripts 缺统一 output-root contract；历史 source run 和 canonical artifact 没分开 |
| files_changed | `run_cases.py`、`run_3d_cases.py`、workstation runner、config、L1/L3 scripts、manifest、records、schema |
| tests_or_commands | Level1；h=5 MPI4 workstation clean rerun；ordinary contract test |
| evidence | 2D/3D 写 `benchmarks/artifacts/level1/`；h5 写 `benchmarks/artifacts/iterative/task028_response_v1_h5_clean` |
| remaining_limitations | h3/h2 heavy artifacts未为目录变化重跑；records明确标记历史source provenance |

ordinary CLI 新增可选 `--results-root`，但缺省仍为 `<repo>/results`。benchmark scripts 全部显式传 `benchmarks/artifacts/...`。h2 direct 仍为 Task008 reviewed reference，不伪装成 Task28 clean artifact。

## 3. P0-2 Scripts 与 Manifest

| 脚本 | 修正后行为 | 状态 |
|---|---|---|
| `run_level1.sh` | compileall、full unittest discovery、显式2D manual DtN、显式3D Stage1 MPI2 | pass |
| `run_level2_mpi.sh` | MPI1 focused、MPI4 focused、automatic checker | pass |
| `run_level3_direct.sh` | 默认h5/h3；h2只有flag或env显式允许；独立artifact root | pass |
| `run_level3_iterative.sh` | h5/h3/h2全部运行；records/artifacts分离；末尾checker | pass |

manifest 新增 `required`、`resource_class` 和 `artifact_policy`，与脚本实际执行范围一致。h2 direct 的 20.53 GB 风险不再被默认触发。

## 4. P0-3 Automatic Benchmark Checker

新增 `benchmarks/check_benchmarks.py`。它从 manifest 和 canonical JSON 重新计算，而不是信任手工 CSV。

| 自动检查 | 当前观察值 | Gate | 结果 |
|---|---:|---:|---|
| h5/h3/h2 records存在且同profile | 3/3 | 3/3 | pass |
| max full residual | 9.99738e-7 | <=1e-6 | pass |
| max reported/condensed relative difference | 1.46e-9 | <=1e-8 | pass |
| iteration ratio | 1.816717 | <=2.0 | pass |
| h2 all-rank peak RSS | 13.080257 GB | <=14 GB | pass |
| h5 direct/iterative max RTA delta | 3.46e-9 | <=1e-8 | pass |
| h3 direct/iterative max RTA delta | 7.82e-9 | <=1e-8 | pass |
| h2 official R/T/A | present | required | pass |
| metadata | 8/8 canonical records complete | required | pass |
| total | 58/58 | all | pass |

checker 更新 `benchmark_summary.csv` 和 `records/benchmark_gate_report.json`；任一 Gate 失败返回非零 exit code。h2 direct 被明确识别为 `reviewed_reference_not_rerun_in_task028`。

## 5. P0-4 Environment

| 必需字段 | 回应 |
|---|---|
| issue | Task28 依赖本机 `latest` 镜像，且2D/3D使用不同环境 |
| root_cause | complex DOLFINx/MPC 是本地双构建镜像，没有进入仓库的公开构建来源 |
| files_changed | `docker/Dockerfile.stage4`、`docker/STAGE4_ENVIRONMENT.md`、`benchmarks/environment.json` |
| tests_or_commands | `docker build -f docker/Dockerfile.stage4 -t myfenics-stage4:task28 .`；容器import/complex assertion；Level1/2/h5 |
| evidence | built digest `sha256:08c61b...`; dolfinx 0.10.0.post2; gmsh 4.15.2; PETSc complex128 |
| remaining_limitations | base `code-dolfinx-mpc@sha256:4f9c...` 无公开pull source，因此不是完全clean-machine reproducible |

环境状态诚实限定为 `qualified_local_image`。文档给出 `docker save/load`、SHA-256、重建和重新qualification流程；只有基础镜像Dockerfile或公开OCI digest可获得后，才能升级为 `reproducible`。

`environment.json` 已补 CPU、logical cores、RAM、WSL/kernel、Docker、MPI、DOLFINx、PETSc、mpi4py、SciPy、gmsh、镜像digest和source commit。

## 6. P0-5 文档

| 文档 | 新增内容 | 状态 |
|---|---|---|
| Quick Start | PowerShell build/mount、完整2D/3D/direct/iterative命令、目录、RTA、ParaView、时间/RSS、错误处理 | pass |
| Capability Matrix | 2D/3D逐能力列出，统一8种状态枚举 | pass |
| Code Walkthrough | 2D/3D/Task28调用链、数据结构、生命周期、sm2、可信度链 | pass |
| Solver Guide | auxiliary direct、explicit condensed、MUMPS OOC/BLR、matrix-free profile与资源边界 | pass |
| Current Boundaries | official/diagnostic、direct/iterative、benchmark、环境、参数域外 | pass |
| Architecture/Schema | output contract、所有权、internal dependency、metadata与Gate report | pass |
| Development Progress | 保留Task000-Task028总览并更新V1 response状态 | pass |

README 与 docs 索引中由审查方新增的 repository principles 和 development progress 链接均保留，保护测试通过。

## 7. P0-6 Production sm2 Tests

新增测试直接覆盖最终 production 分支：

| 测试 | 覆盖 | MPI1 | MPI4 |
|---|---|---:|---:|
| explicit small reference | 两步GMRES对角两特征值问题精确解 | pass | pass |
| sm1 vs sm2 | 一步不精确、两步达到reference | pass | pass |
| repeated apply | 连续4次结果稳定 | pass | pass |
| MPI action consistency | all-rank误差与显式解一致 | pass | pass |
| action requirement | sm2缺action时拒绝 | pass | pass |
| destroy lifecycle | 幂等destroy并清空inner context | pass | pass |

第一次MPI测试高CPU并非solver deadlock，而是测试的rank-local assertion导致部分rank提前退出。改为allreduce全局误差后，MPI4每个rank的7个physical-slab tests约0.06秒完成。

## 8. 重跑结果

### Level1/Level2

| 项目 | 结果 |
|---|---|
| full suite | 91 passed, 10 skipped |
| focused MPI1 | 14 passed |
| focused MPI4 | 每个rank 14 passed |
| 2D manual auxiliary DtN | residual 1.867e-15, R+T=1 |
| 3D Stage1 MPI2 | residual 1.395e-16, total RSS 0.520 GB |
| h5 direct isolated artifact | residual 5.225e-12, total RSS 2.293 GB, R/T/A unchanged |
| automatic checker | 58/58 pass |

### h5 Workstation Output-root Qualification

| 指标 | V1前 canonical | Response V1 clean rerun |
|---|---:|---:|
| iterations | 1201 | 1201 |
| reported residual | 9.839489934e-7 | 9.839489934e-7 |
| full residual | 9.839489937e-7 | 9.839489937e-7 |
| R | 0.0890216032196 | 同值 |
| T | 0.4425882751985 | 同值 |
| A_volume | 0.4683901190309 | 同值 |
| total peak RSS | 1.9866 GB | 1.9912 GB |
| total time | 127.3 s | 130.8 s |
| qualified_profile | 旧record无字段 | true |
| artifact root | 历史source不清 | `benchmarks/artifacts/iterative` |

h3/h2 production solver 数值逻辑未改变，因此按review要求没有重复重型计算。h2 direct也未在14 GB环境冒险运行。

## 9. P1 处理状态

| P1 | 状态 | 处理/技术债 |
|---|---|---|
| private internal functions | partially_closed | architecture与walkthrough明确边界，full/import/smoke保护；公开facade迁移留债 |
| `SmallDenseInverse` explicit inverse | open_nonblocking | 当前H小且良态；为避免无必要改变三网格数值路径，本轮不改，后续改LU需重新qualification |
| double config source | closed | JSON为canonical defaults，CLI仅override，record保存resolved config |
| unqualified parameters | closed | warning + `qualified_profile=false` + deviation list |
| metadata incomplete | closed | canonical records补齐；新runner自动生成完整metadata |
| fresh coarse error 0.0 | closed | fresh改为`null/not_applicable`，cached才给认证误差 |
| exception cleanup | open_nonblocking | 正常路径和destroy测试通过；统一try/finally及failure-stage record留债 |

## 10. 最终 Gate

```text
core_integration_gate = pass
numerical_gate = pass
benchmark_output_boundary = pass
benchmark_scripts_match_manifest = pass
benchmark_automatic_gates = pass
documentation_refresh = pass
production_sm2_test_coverage = pass
environment_reproducibility = pass_with_qualification
task028_overall = pass_with_environment_qualification_pending_v2
master_merge = blocked_until_v2_and_user_approval
```

建议 V2 重点核查 checker 的失败退出语义、h5 新record metadata、ordinary `--results-root` 默认、Docker环境限定是否足够诚实，以及文档链接。Task29 未启动。
