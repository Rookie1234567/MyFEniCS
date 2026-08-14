# Task39 Review V1 执行回应

## 1. 总体状态

本回应把首轮 T3–T10 结论与 Review V1 extension 分开记录。首轮 negative records 不被
删除或改写；Review V1 只补充网格、H 场、M960 trace 和内存取证。

| 阶段 | Review V1 状态 | 证据入口 |
| --- | --- | --- |
| E0 | completed；继承审计通过 | [extension audit](outcomes/extension_inherited_audit.md) |
| E1 | completed；非侵入式 checker/telemetry focused contracts | [test summary](outcomes/test_summary.md) |
| E2 | h7.5 direct own authority pass | [h7.5 record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e2_h7p5_full3d_direct_result_v1.json) |
| E3 | h6 preflight 与 direct own authority pass | [h6 record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e3_h6_full3d_direct_result_v1.json) |
| E4 | `not_run_by_resource_policy`；h5 要求的 MUMPS symbolic/analysis 成功未满足：没有独立 analysis-only public path，因此未尝试 factorization/solve | [E4 h5 preflight record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e4_h5_full3d_direct_preflight_v1.json) |
| E5 | completed；Full3D reference 未建立 | [grid decision](outcomes/full3d_direct_grid_convergence_v2.md) |
| E6 | completed；`M480_H_DISCREPANCY_UNRESOLVED` | [H diagnostic](outcomes/m480_h_field_diagnostic.md) |
| E7 | family audit pass；唯一 M960 direct own authority pass | [M960 audit](outcomes/m960_trace_numerical_audit.md) |
| E8 | `not_run_by_review_v1_7p3_stop_after_m960_direct` | [iterative boundary](outcomes/m480_hybrid_iterative_solver_diagnostic.md) |
| E9 | `not_run_by_review_v1_7p3_stop_after_m960_direct` | [iterative boundary](outcomes/m480_hybrid_iterative_solver_diagnostic.md) |
| E10 | completed；global peak measured，stage attribution not_available | [memory forensics](outcomes/memory_lifecycle_forensics.md) |

E8/E9 的状态是 Review §7.3 的正常受控停止，不是 iterative solver 的 pass 或 fail。
首轮 T6、T7、T8 的 `not_run/blocked` 事实继续有效。

## 2. 主要科学结论

- Full3D h10、h7.5、h6 的 own direct solve 通过；h5 为
  `not_run_by_resource_policy`。相邻网格的 mandatory/strong observables、显著级和
  E/H 组合并未建立收敛 reference，最终分类为
  `FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_WITHIN_RESOURCE_BUDGET`。h6 只是
  best available discrete，不是 continuum/refined authority。
- M480 H 三路径比较的机器数值 Gate 通过，但因果证据不足，分类保持
  `M480_H_DISCREPANCY_UNRESOLVED`。native、curlE、Full3D 的共同平面、safe offset、
  flux/energy 和逐分量记录见 [E6 文档](outcomes/m480_h_field_diagnostic.md)。
- 四档 M120/M240/M480/M960 trace family audit 通过。M960 formal direct 的 residual、
  exact traction、projection、canonical backward error、R/T/A、closure、604 keys 均
  通过；`official_record=false` 只表示 M convergence/model qualification 尚待建立。
- E10 只有全局 process-tree peak authority；没有 stage-aligned snapshots，因此只确定
  `UNATTRIBUTED_RUNTIME_OR_ALLOCATOR_HIGH_WATER`，其余归因保持 not_established。
- 0.7 nm 仍只有 component-only feasibility；材料缺失、factor/cache、external
  DtN/Woodbury、internal modal Schur 和 convergence-risk 分类不变。没有完整 0.7 nm
  PDE、新 PC 或 modal matrix-free。

## 3. Review V1 commit 与证据索引

| 范围 | commits |
| --- | --- |
| 授权与 E0 | `2207a9c4`、`f0eed432` |
| E1–E4 implementation/preflight/result | `65f24874`、`e2ea6089`、`d6f96c82`、`e90cef8b`、`c44b0385`、`ba63bdac` |
| E5 grid decision | `caaf3eb8` |
| E6 H diagnostic | `5f3810c6`、`5c13e834`、`e6625b64`、`af75d8c7`、`442d0ab6` |
| E7 capture/family/direct comparison | `34bca037`、`697955b5`、`d66c3a64`、`aa26d25e`、`0e19ef7b` |
| E7/E10 compact evidence | `df8123fdcbb899fae29b08af2305008ebb1e6499` |

主要 compact records：

- [T3 direct](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t3_full3d_direct_mpi8_v1.json)
- [T4 negative](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t4_full3d_iterative_mpi8_negative_v1.json)
- [T5 M convergence](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)
- [E7 family](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_trace_family_v1.json)
- [E7 M960 direct](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e7_m960_direct_result_v1.json)
- [E10 memory](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_e10_memory_lifecycle_v1.json)

## 4. 检查、未运行项与环境边界

| 项目 | 状态 |
| --- | --- |
| Task39 focused suite | `86 passed`；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| MPI1/2/4 tiny DtN fixture | pass；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a`；不是 T6 numerical lane |
| Ruff check、31-file changed-Python format、compileall | pass；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| `check_benchmarks --no-write` | `302/302` pass；历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` |
| E6 focused/static | pass；implementation 与离线 compare 均完成 |
| repository full pytest | `cancelled / not_run`；用户成本覆盖，不是 pass 或 zero failures |
| 完整 0.7 nm PDE | not_run |
| E8/E9 iterative numerical lanes | not_run_by_review_v1_7p3_stop_after_m960_direct |

当前 docs-only closeout 的基线为 A commit `36c729f7ae197d08f92e044907d0cb723f9fd43c`；
最终文档提交仍为 pending，不在本文预写其 SHA。ordinary defaults、Python/config/schema、
`master` 和其他分支均未改变；没有创建新 branch/worktree。

### Review V1 final light Gate

以下是当前 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` 上的最终轻量 Gate；
它与上表中历史 T10 B1 parent `b737c62149186356a1c07c267f473e360274cc8a` 的结果分开，
全仓 repository pytest 仍为 `cancelled / not_run`。

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| ABI preflight | `pass` | qualified activation；`.venv`、complex128/int32、同一 Linux ABI |
| Task39 focused（8 个文件） | `132 passed, 1 skipped` | 当前 code parent `36c729f7ae197d08f92e044907d0cb723f9fd43c` |
| targeted `test_40`/`test_275` | `17 passed, 1 skipped` | 当前 code parent |
| MPI tiny DtN | `MPI1/MPI2/MPI4 pass` | ranks 1/2/4；tiny fixture |
| official dat validate/dry-run | `26/26 pass` | 13 个 dat × 2；未启动 worker/PDE |
| Ruff check/format-check | `24/24 pass` | changed Python |
| compileall | `pass` | `src`、`benchmarks`、`scripts` |
| `check_benchmarks --no-write` | `302/302 pass` | 无写入 |
| compact JSON | `17 parsed` | Task39 records |
| 文档合同 | `7/7 pass` | 相对链接、fenced math、表格列数 |
| `git diff --check` | `pass` | 当前工作树 |
| 全仓 repository pytest | `cancelled / not_run` | 用户成本覆盖；不声称 pass 或 zero failures |

## 5. 最终分类边界

```text
TASK039_5NM_FIXED_GRID_SOLVER_CAPACITY_QUALIFIED_ONLY
TASK039_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM
5NM_HYBRID_MODEL_NOT_ESTABLISHED_BY_M960_AT_P6H10
HYBRID_DIRECT_DIAGNOSTIC_FAIL
FULL3D_DIRECT_5NM_REFERENCE_NOT_CONVERGED_WITHIN_RESOURCE_BUDGET
M480_H_DISCREPANCY_UNRESOLVED
0P7NM_MATERIAL_INPUT_INCOMPLETE
0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET
0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN
0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN
0P7NM_CONVERGENCE_RISK_UNRESOLVED
```

禁止升级为 `TASK039_5NM_FULL3D_HYBRID_ACCURACY_AND_MEMORY_QUALIFIED`、
`TASK039_ITERATIVE_SOLVER_PASS_HYBRID_MODEL_FAIL_AT_5NM` 或
`CURRENT_ARCHITECTURE_PLAUSIBLE`。
