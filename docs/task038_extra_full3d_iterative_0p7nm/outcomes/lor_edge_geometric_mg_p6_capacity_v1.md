# V11 S5：p6/h10 LOR hierarchy capacity audit

## 结论先行

S5 的资源与生命周期证据通过，但 6→3 transfer 的 rediscretized energy consistency 是真实数值 hard Gate 失败。因此本阶段不能分类为 `P6_LOR_EDGE_HIERARCHY_RESOURCE_PASS_WITH_COARSE_SOLVER_OPEN`，也不能称为 solver pass。准确分类是：

`S5_RESOURCE_PASS_BUT_ALGEBRA_GATE_FAILED__LOR_EDGE_GEOMETRIC_MG_CLOSED`

| Gate | 实测 | 限值/结果 |
|---|---:|---|
| 6→3 energy relative | `0.04115402900674629` | `<=1e-9`，FAIL，唯一 hard numerical failure |
| 3→1 energy relative | `2.7851655955739857e-15` | `<=1e-9`，PASS |
| cold process-tree peak | `1,207,476,224 B` | `<2,000,000,000 B`，PASS |
| retained-window process-tree peak | `1,207,476,224 B` | `<1,800,000,000 B`，PASS |
| process-tree/rank swap | `0 B` | PASS |
| other action/adjoint/linearity/repeat/smoother/fingerprint/lifecycle/provenance | all PASS | 不改变 6→3 failure |

S5 不是 PDE 运行：没有 physical Maxwell solve、长 Krylov、p6 exact factor、p1 direct factor 或 recovery。S6 在这个 Gate 后停止；S6 之后及任何 S5+ 扩展均 `not_run_by_gate`。

## formal 身份与命令

| 项目 | 事实 |
|---|---|
| source SHA | `2507a16d8f19df9b432319ae1625ea9b817d78f8` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| case | p6/h10/MPI1，13.5 nm，complex128/int32 |
| input | `input/templates/full3d_iterative_example.dat`，raw SHA `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| resolved input SHA | `78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad` |
| physical model SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| fixed level settings | `6 -> 3 -> 1`; Chebyshev degree 3; power 10; pre/post 1; reserve 21+4=25 |

Worker command was the absolute qualified Python command recorded in the fixed record:

```text
/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python -m benchmarks.run_task038_full3d_lor_hierarchy_capacity --stage s5 --case p6-h10-mpi1 --raw-dir benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_p6_capacity_v1/2507a16d8f19df9b432319ae1625ea9b817d78f8/s5-p6-h10-mpi1/worker_raw --record docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1.json --expected-source-sha 2507a16d8f19df9b432319ae1625ea9b817d78f8 --expected-mpi-size 1 --input /home/shenjh/Projects/MyFEniCSx_task37_extra/input/templates/full3d_iterative_example.dat
```

The outer command used the existing foundation watchdog with RSS hard limit `2,000,000,000 B`, no arbitrary wall timeout, and sibling watchdog artifacts. The independent checker was the pure-NumPy `benchmarks.task038_full3d_lor_hierarchy_capacity_checker` reading the fixed record and watchdog compact. It returned `rc=1` with `contract_errors=[]` and `gate_failures=["transfer 6-3 energy failed"]`.

## Levels, matrices and transfers

| level | rows=cols | NNZ | index bytes | numeric bytes | scope |
|---:|---:|---:|---:|---:|---|
| 1 | 1,067 | 37,253 | 153,284 | 596,048 | p1 coarsest sparse edge matrix |
| 3 | 23,073 | 783,083 | 3,224,628 | 12,529,328 | p3 refined raw sparse edge matrix |
| 6 | 173,802 | 5,825,468 | 23,997,084 | 93,207,488 | S2 foundation LOR matrix, counted once |

| pair | local edge map | edge NNZ / bytes | node map | node NNZ / bytes | structural projection |
|---|---:|---:|---:|---:|---|
| 6→3 | 882×144 | 26,136 / 2,032,128 B | 343×64 | 21,952 / 351,232 B | true; forbidden nnz after 0 |
| 3→1 | 144×12 | 324 / 27,648 B | 64×8 | 512 / 8,192 B | true; forbidden nnz after 0 |

The transfer path is owner-local/streaming. No global high-order AIJ, global dense transfer, numeric allgather, HX/PCGAMG hierarchy, p6 exact factor, p1 global direct factor, physical solve or recovery arrays were constructed; all corresponding raw architecture flags are false.

## Probe facts

| fact | 6→3 | 3→1 |
|---|---:|---:|
| adjoint work relative | `1.2865066317766304e-14` | `1.733756183951221e-15` |
| linearity relative | `3.0795110632853766e-16` | `1.3679388646656595e-16` |
| repeat relative | `0.0` | `0.0` |
| finite/input unchanged | true / true | true / true |
| coarse energy (real, imag) | `2674000223856.8975`, `4.842877388000488e-06` | `513619935.034483`, `-2.7066562324762344e-09` |
| fine energy (real, imag) | `2784046106633.5503`, `-0.0009012836962938309` | `513619935.03448445`, `1.1123120202682912e-09` |
| energy relative | `0.04115402900674629` **FAIL** | `2.7851655955739857e-15` PASS |

The probe used `coarse_primal_source="owner_roundtrip_reduced_primal"`; the checker bound stored energies to the raw arrays. All action and smoother identity probes were finite, repeatable and input-preserving. The fixed smoother facts were:

| level | lambda_power10 | lambda_hi | lambda_lo | degree / power |
|---:|---:|---:|---:|---|
| 3 | 2.451729321670397 | 2.6969022538374365 | 0.26969022538374365 | 3 / 10 |
| 6 | 4.033660535252619 | 4.437026588777882 | 0.4437026588777882 | 3 / 10 |

The reserve was 21 Krylov basis vectors plus 4 auxiliary vectors, 25 touched vectors total, `69,520,800 B` of local numeric storage. The p1 coarsest solver budget was only a derived estimate: matrix payload `749,332 B` plus eight fixed complex vectors `136,576 B` plus explicit PETSc overhead `0`, total `885,908 B`; no p1 solver or factor was constructed.

## Resource ledger and evidence

The combined known ledger was `296,345,065 B`. The record's retained ledger sample was `1,201,344,512 B` with `904,999,447 B` unattributed remainder. Separately, the external watchdog/checker retained-window and cold process-tree authority reported the peak `1,207,476,224 B`; these two measurements are not added or conflated. Mesh/space/MPC C++ allocations had no independent byte counter and remain in measured/unattributed runtime overhead. The non-dedicated `/init.scope` shared cgroup swap `13,799,424 B` is diagnostic only; formal process-tree/rank swap was zero.

| evidence | relative path | SHA256 |
|---|---|---|
| worker record | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1.json` | `2a2731325cc0fc75b5efb1445c812e0660b4987b96ad88de2a471d623887e181` |
| checker output | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1_checker.json` | `cb74710a144aac0db18741c6328fe4ec2b25e61c9535c6c0d4c1ec686f108221` |
| watchdog raw | `benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_p6_capacity_v1/2507a16d8f19df9b432319ae1625ea9b817d78f8/s5-p6-h10-mpi1/watchdog.raw.jsonl` | `a4915601a28ed81f0a4487912003d73f5d2e8bec8c2c87126b3547dbcc7cf66b` |
| watchdog compact | `benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_p6_capacity_v1/2507a16d8f19df9b432319ae1625ea9b817d78f8/s5-p6-h10-mpi1/watchdog.json` | `aab1304a2e4caaaaf496a3476c6a4bef001611b527980483be5c4f6464275b38` |
| worker log | `benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_p6_capacity_v1/2507a16d8f19df9b432319ae1625ea9b817d78f8/s5-p6-h10-mpi1/worker.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| probe facts NPZ | `.../s5-p6-h10-mpi1/worker_raw/probe_facts.npz` | `1f0ba8c9e5e2082330c1049446977640bc5f107789c893e5d50bcedcf4e05816` |

## Why the stage closed

The 3→1 map is an energy-consistent p1-level transfer. The 6→3 map is not: its `0.041154...` relative energy discrepancy is forty million times larger than the `1e-9` limit. Supplemental local diagnosis found that p3 and p6 GLL nodes are non-nested; a naive 2:1 tiled map also had composition defect `0.23558864802518256`. That evidence points to a different coarse-grid/operator architecture (for example a geometry-aware non-nested projection or a Galerkin coarse operator), not a runner, watchdog, tolerance, or record bug. This S6 closeout does not implement or authorize that change.

## Preserved earlier attempt

The ba40358 probe-domain-invalid attempt remains immutable and is not reclassified. Its archived compact hashes are:

| archived evidence | SHA256 |
|---|---|
| `lor_edge_geometric_mg_p6_capacity_v1_probe_invalid_ba40358.json` | `ad8bbc3dfd81ba489efd6a4b2c24530c43f68484facc43020f9c5044f3be2a3f` |
| `lor_edge_geometric_mg_p6_capacity_v1_checker_probe_invalid_ba40358.json` | `93423f917256edd40ac13727af2feac58e4dcc63dde29a229742e6b960f5aaa8` |

It was a checker rejection of an invalid energy probe domain, not a resource or numerical Gate, and it must not be rewritten as a pass.

## Decision boundary

S5 is `failed` at the 6→3 algebra Gate; S6 is documentation-only `complete`; S4/S1/S2 historical passes remain at their own scopes. No p6 physical Maxwell, p6/h5, 0.7 nm PDE, S5+ repair, or official physics result was run. The next coarse-solver question is not reached: the immediate blocker is 6→3 interlevel energy consistency.
