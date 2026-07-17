# Task033 高阶假设审计

> 阶段更新（2026-07-17）：p3/p4 高阶 Floquet 的实现假设已由 Case090 正式 PDE
> 覆盖；Phase A 已使 p3/p4 QEP component 资格化，legacy 全阶 aggregate 因 p1/p2
> 真实负结果仍未资格化。本文中 adaptive、
> variable-p 与 buffer 相关条目保留为延期审计，不再代表当前阶段阻塞项。

## 1. 审计身份

| 字段 | 值 | 数据身份 | 证据 |
|---|---|---|---|
| source snapshot | `ad4046d7f4a360f2b160b9c196e2f7b8990ac135` | measured static audit | `git rev-parse HEAD` before Task033 edits |
| scope | `src/`, Task032 benchmark runners and relevant tests | measured static audit | `rg` searches listed below |
| execution status | `historical_static_snapshot_superseded_by_stage1_runtime` | measured history | current runtime result见本文顶部与 `summary.md` |
| allowed dispositions | `remove`, `generalize`, `retain-with-reason`, `out-of-scope` | task contract | `../task.md` Phase 1 |

Search families included `degree == 2`, degree guards, fixed entity DoF counts,
`topological_trace_p2`, `N1curl`/`Lagrange` construction, quadrature, visualization,
orientation, pseudo-inverse probes, point ownership and gather operations. 下表是实现前静态
快照；它本身不是 p3/p4 通过证据，当前通过证据来自 Case090 与 QEP watchdog。

## 2. 实现前 confirmed assumptions and disposition（历史快照）

本表“当前状态”冻结在 source snapshot `ad4046d...`，不能覆盖 2026-07-17 的
runtime disposition。已实施结果以第 3 节 Gate routing 和 `summary.md` 为准。

| ID | 假设 / 静态发现 | 路径与符号 | 处置 | 当前状态 | 必须通过的 Gate | 数据身份 / 证据 |
|---|---|---|---|---|---|---|
| A01 | 3D Floquet `auto` only resolves p1 or p2; p3/p4 raise | `src/constraints/floquet_3d.py::_resolve_constraint_mode` | generalize | confirmed blocker | p1–4 dispatch; unsupported degree fails closed; ordinary p1/p2 regression | static source audit / `rg degree` |
| A02 | public mode names and validation are p1/p2-specific | `src/common/config_3d.py::floquet_constraint_mode_requested` | generalize | confirmed blocker | degree-generic sparse trace mode with legacy aliases preserved | static source audit |
| A03 | Stage4 hexa geometry explicitly rejects degree above 2 | `src/geometry/mesh_builder_3d.py::_validate_stage4_hexa_geometry` | generalize | confirmed blocker | allow p3/p4 only after the sparse trace path is available; invalid cells fail closed | static source audit |
| A04 | p2 validation assumes exactly 2 edge and 4 face-interior DoFs | `src/constraints/floquet_3d.py::_require_supported_topological_trace_p2` | generalize | confirmed p2 layout | query Basix entity DoFs for each degree; p1–4 entity coverage and round-trip | static source audit |
| A05 | face orientation transform is named and implemented as a p2-only 4-by-4 block | `src/constraints/floquet_3d.py::_face_transform_p2` and p2 context helpers | generalize | confirmed p2 table | Basix-verifiable entity-local transform for p2–4; orientation unit tests | static source audit |
| A06 | p1 helper assumes one N1curl DoF per edge | `src/constraints/floquet_3d.py::_build_topological_edge_context` | retain-with-reason | accepted p1 anchor | p1 behavior unchanged and remains independently tested | static source audit |
| A07 | legacy whole-plane dense/probe fitting is disabled loudly | `src/constraints/floquet_3d.py::_disabled_*` | retain-with-reason | desired guard | no boundary-size dense square and no diagnostic fallback on ordinary p3/p4 path | static source audit |
| A08 | periodic entities are paired by topology records plus rounded coordinate keys | `src/constraints/floquet_3d.py::_edge_match_key`, `_face_match_key` | retain-with-reason | candidate topology pairing | exact matching-mesh identity, pair error Gate, no nearest-neighbor fallback, topology cached once | static source audit |
| A09 | current 3D builders use communicator-wide metadata/map `allgather` | `src/constraints/floquet_3d.py` context, coverage and map builders | generalize | scalability warning | distributed sparse `C_p`; record communication volume; no full boundary DoF/field gather | static source audit |
| A10 | mixed QEP spaces already accept arbitrary transverse and longitudinal degree | `src/modes/cross_section_spaces.py::build_cross_section_spaces` | retain-with-reason | generic API present | assert 3D and QEP degree semantics match; instantiate p1–4 | static source audit |
| A11 | 2D cross-section Floquet obtains facet transforms from polynomial probes and `pinv` | `src/constraints/cross_section_floquet.py::_facet_probe_arrays` and transform build | generalize | formal p3/p4 blocker | replace/restrict to entity-local verifiable mapping; diagnostic fallback must never be ordinary path | static source audit |
| A12 | Task032 QEP/mode/trace/Hybrid runners explicitly call `transverse_degree=2` | `benchmarks/run_task032_phase2_qep.py`, `phase3_modes.py`, `phase5_trace.py`, `phase6_augmented.py` | retain-with-reason | historical p2 anchors | do not rewrite Task032 replay semantics; Task033 runners must parameterize p1–4 | static source audit |
| A13 | QEP forms rely on compiler-default quadrature | `src/modes/quadratic_beta_eigenproblem.py::_assemble_unconstrained_matrix` | generalize | policy not explicit | degree/coefficient/geometry-aware quadrature plus one raised-order comparison | static source audit |
| A14 | Hybrid internal surface load hard-codes quadrature degree 8 | `src/coupling/hybrid_internal_modes.py::_ReusableInterfaceSurfaceLoad` | generalize | confirmed fixed value | degree-aware policy; raised-order result comparison; record chosen degree | static source audit |
| A15 | external 3D DtN quadrature already scales with p and diffraction order | `src/solvers/dtn_port_3d.py::_dtn_surface_quadrature_degree` | retain-with-reason | generic candidate | p1–4 chosen degree recorded and one raised-order comparison passes | static source audit |
| A16 | visualization degree is configurable but ordinary defaults remain p1/p2 presets | `src/common/config_3d.py`, `src/main.py`, postprocessing modules | retain-with-reason | ordinary default boundary | Task033 runner sets and records visualization degree; ordinary defaults remain unchanged | static source audit |
| A17 | structured hexa coordinate element is linear | `src/geometry/mesh_builder_3d.py` coordinate `Lagrange` degree 1 | retain-with-reason | valid for planar fixtures | report geometry degree=1; do not call this curved high-order convergence | static source audit |
| A18 | arbitrary curved production geometry and high-order geometry mapping | repository has no qualified production path | out-of-scope | not implemented | document limitation; no curved-geometry success claim | task non-goal + static audit |
| A19 | existing high-order trace test fixes p2 entity counts | `src/test/test_17_3d_high_order_floquet_trace.py` | retain-with-reason | regression anchor | keep p2 assertions; add separate p3/p4 orientation and action tests | static source audit |
| A20 | ordinary Stage4 preset uses p2 | `src/main.py::STAGE4_GRATING_3D` | retain-with-reason | protected default | explicit opt-in only for Task033; default comparison unchanged | static source audit |
| A21 | modal trace extraction uses DOLFINx point ownership and interpolation | `src/coupling/modal_trace_projection.py` | retain-with-reason | matching-interface candidate | p1–4 trace/action/round-trip, no unresolved point, no full vector gather, no dense interface square | static source audit |
| A22 | internal mode lifting gathers only structured-axis/cell-key metadata, not fields | `src/coupling/hybrid_internal_modes.py::_DistributedCrossSectionEvaluator` | retain-with-reason | current matching-interface scope | p1–4 MPI result equivalence; field gather remains false; communication recorded | static source audit |
| A23 | removal of matching-interface metadata replication belongs to the scalable modal-core redesign | same coupling path; future Task034 boundary | out-of-scope | deferred | Task033 records scale and limitation; Task034 owns distributed modal-core redesign | task non-goal |
| A24 | variable-p cellwise H(curl) has no qualified native path in the audited code | config/mesh/space construction uses one degree per space | out-of-scope | fail-closed pending framework audit | only prototype if native sparse orientation-safe support is demonstrated; otherwise document fixed-p+h route | task contract + static audit |
| A25 | QEP default longitudinal degree equals transverse degree | `src/modes/cross_section_spaces.py::build_cross_section_spaces` | retain-with-reason | intended same-degree semantics | p1–4 records include both actual Basix degrees and DoF counts | static source audit |
| A26 | power-field DG reconstruction follows `nedelec_degree` | `src/postprocessing/power_metrics.py` | retain-with-reason | degree-aware candidate | p1–4 output finite; raised visualization/order comparison where relevant | static source audit |
| A27 | core 3D and QEP volume forms do not yet expose one unified high-order quadrature policy | `src/solvers/dtn_port_3d.py`, `src/modes/quadratic_beta_eigenproblem.py` | generalize | audit finding | record field/geometry/coefficient degree and chosen quadrature; raised-order comparison | static source audit |

## 3. Gate routing

| Gate | 进入条件 | 通过条件 | 失败处置 | 当前状态 |
|---|---|---|---|---|
| G1 framework/entity probe | Basix/DOLFINx complex image available | p1–4 entity DoFs and local transforms can be enumerated without private unsupported hacks | fail closed at the unsupported degree | pass |
| G2 sparse 3D Floquet algebra | G1 pass | round-trip `<=1e-12`; trace `<=1e-11`; action `<=1e-11`; no dense boundary square/full gather | repair mapping; do not enter Hybrid high order | pass，Case090 |
| G3 MPI identity | G2 serial pass | MPI1/2/4 result difference `<=1e-10`; ownership has no slave chain | repair ownership/communication | pass，Case090 |
| G4 analytic fixtures | G2/G3 pass | full true residual `<=1e-10`; plane-wave/Fresnel errors decrease reasonably | retain negative result; stop affected degree | pass，Case090 |
| G5 high-order QEP/trace | pure 3D degree passes | beta/residual/biorthogonality/trace Gates pass; near-degenerate block tracking; same degree semantics | pause Hybrid at failed degree | pass for p3/p4 QEP components；legacy p1/p2 negatives retained |
| G6 quadrature | each candidate assembled | raised-order comparison shows no material change within declared tolerance | increase order or stop qualification | pass for retained component records |
| G7 ordinary regression | implementation changes complete | existing p1/p2 and Case080 results unchanged within canonical Gates | fix before benchmark expansion | pass |

## 4. Audit boundary

本文件的静态表保留审计历史；当前 runtime 结论是：p3/p4 entity/Floquet、解析 PDE 与
MPI Gate 已通过，QEP p3/p4 components 与 selected MPI1/2/4 identity 通过；legacy 全阶
aggregate 因 p1/p2 未资格化，p3/p4 Hybrid 同阶
full3D 对照仍未运行。不得用历史表的 blocker 状态覆盖当前阶段证据，也不得把当前
组件通过外推成完整 Task033 通过。
