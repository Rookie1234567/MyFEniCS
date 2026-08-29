# Task038-extra Review V13 current authority summary

## 一句话结论

V13 的 C1 exact-input p6/h10 positive hierarchy 已由 random、gradient、curl、checkerboard 四源全部通过，当前 selected_hierarchy 是 same_mesh_hcurl_pmg_v1_requalified。随后唯一的 P0 p6/h10 physical Maxwell MPI1 workflow 在 cold setup 阶段达到 2,024,108,032 B，超过 2,000,000,000 B hard line 24,108,032 B（约 1.2054%），被 watchdog 受控终止。因此 P0 是 FAILED_RESOURCE_HARD_STOP；没有 Krylov、PDE residual 或 official physics failure，也没有 physical PASS。

positive source 资格的含义是：预条件器在正定辅助算子上能压低固定诊断误差。P0 physical 才是含波动、双 Floquet 和 streaming Fourier-DtN 的真实散射 workflow。两者分开记录。

## V13 当前阶段表

| 阶段 | 当前权威状态 | 关键事实 |
|---|---|---|
| A0 Route A | CLOSED_BY_VECTOR_OR_STABLE_ADJOINT_GATE | 已实际运行 6 probes；gradient pairwise-vs-compensated=2.7478465599487806e-12 > 1e-13；MPI2/A1 not_run_by_A0_gate，随后进入 C0 |
| C0 canonical source | C0_CANONICAL_SOURCE_PASS_MPI1_MPI2 | source SHA 4dc9b55cd3519a03b23c9d27779c0379cef84f66；p3→p1；owner/phase/input Gate 通过 |
| C1 positive | C1_P6_POSITIVE_PASS_MPI1 | 四源 exact-input v4 全部通过；selected_hierarchy=same_mesh_hcurl_pmg_v1_requalified |
| P0 physical | FAILED_RESOURCE_HARD_STOP / controlled termination | source SHA a05e93af6edb097c1f0ebf0f65e201698db27381；peak 2,024,108,032 B；swap=0；仅 paths_ready |
| P1 | locked/not_run_by_resource_gate | P0 未进入 solve，未满足 long-tail 条件 |
| P2 | locked/not_run_by_resource_gate | P0 未完成 MPI1 physical residual 与 official physics |
| G/D | not_run_by_selected_C1 | C1 positive 已选层级，未进入其它候选路线 |
| 0.7 nm PDE / ordinary default | not_run / unchanged | 没有完整 0.7 nm PDE；ordinary default、master 未改变 |

## C1 四源 positive 结果

| source | source SHA | iterations | final true residual | peak / retained | swap | status |
|---|---|---:|---:|---:|---:|---|
| random | 0da00e98c0423ade6cea38cabc3c8415ea32510e | 200 | 5.550975220267439e-9 | 1,517,903,872 / 772,497,408 B | 0 | PASS |
| gradient | 82c56d92ac80ddf84071a6e1eff6d28e3513af7e | 220 | 2.7889793119815017e-9 | 1,516,544,000 / 770,650,112 B | 0 | PASS |
| curl | 48866f2990a12113a28e556e6956104625b3da34 | 180 | 5.6105046279899595e-9 | 1,536,192,512 / 790,028,288 B | 0 | PASS |
| checkerboard | 80b0d8d36364007f4dda941d7770a307eee15dd4 | 200 | 7.760965317017376e-9 | 1,533,190,144 / 786,751,488 B | 0 | PASS |

所有四案都绑定 exact input SHA 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41、physical model SHA 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f、grazing=1°、theta=89°、phi=0°、13.5 nm、p6/h10。每案的 source SHA、worker record、watchdog compact、checker compact 和 ignored root 均独立绑定。

四案的 matvec/PC/KSP destroy/action total 分别为 random 209/210/10/223、gradient 230/231/11/245、curl 188/189/9/201、checkerboard 209/210/10/223；natural exit、no orphan、readability、swap=0 和 checker Gates 全部通过。完整结果见 p6_positive_v13.md。

## P0 resource hard stop

P0 使用 selected_hierarchy、exact matrix-free Maxwell volume、streaming Fourier-DtN、physical RHS、right GMRES restart20/max_it20000、replacement20、checkpoint500。外部 watchdog 覆盖 cold setup，poll=0.25 s，hard RSS=2,000,000,000 B，process-tree swap=0。

最后 elapsed=5167.201565908967 s，20,518 个 raw samples，首次 warning 是 1,813,069,824 B at 5165.438371994998 s。peak=2,024,108,032 B。差值 24,108,032 B 仍是严格 FAIL，不能按四舍五入或“只超一点”放行。returncode=-15、stop_reason=process_tree_rss_limit、natural_exit=false、no_orphan=true；只有 paths_ready marker，没有 worker record、checkpoint、residual、recovery 或 physics output。完整证据见 p6_physical_v13.md。

P0 tracked evidence 只包括原字节复制的 watchdog compact 与 paths_ready marker：

- records/same_mesh_hcurl_pmg_p0_physical_v1_watchdog.json，SHA 0705e170a1835999aece82dfe43d3ff5ccd3cf98800b79a013341b54ed2955e5；
- records/same_mesh_hcurl_pmg_p0_physical_v1_paths_ready.json，SHA 4f22fd62136515693ebebef4fbfe551e84e46223a0685054dcb9ad1a65108415。

没有创建假的 worker/checker record。raw SHA 为 51e8e531500e733c21f558d44be0a4d8d7a76fe9454800ebc9cb8ad06ab19566；原始 ignored root 永久保留。

## 历史事实与状态边界

V11 S5 的 6→3 energy=0.04115402900674629 > 1e-9 是冻结的 algebra Gate negative；V12 的 selected_hierarchy=NONE、C1 identity negative、Route A global adjoint failure、Route B/C2 negative 及相关资源边界也均为历史冻结事实，不被 V13 重分类。V13 A0 是新增的真实负结果：六 probe 已运行，gradient pairwise-vs-compensated Gate 失败；其 MPI2/A1 后续按固定分支 not_run_by_A0_gate。C0 v4 的 MPI1/MPI2 canonical source PASS 见 same_mesh_canonical_source_v1.md；V13 C1 结果见 p6_positive_v13.md；V13 P0 controlled stop 见 p6_physical_v13.md。

因为 C1 已经提供 qualified positive hierarchy，V13 的 Z0 条件“所有 A/C/G/D 都没有 positive hierarchy”不成立，所以不创建 next_pc_architecture_after_v13.md。G/D 不是被证明失败，而是 not_run_by_selected_C1。

official E/H、R/T/A、A_volume 和 12 个显著通道的 12 个 power Gate 加 12 个 complex boundary-amplitude Gate 均为 not_run_by_resource_gate。没有 direct observable-vector qualification；不能以 C1 auxiliary evidence 代替。

当前 tracked direct authority 只有 scalar R/T/A/A_volume；缺少 E/H 与 12+12 raw arrays。该 downstream comparison blocker 因 P0 先在 cold setup 停止而未触达，不是本次停止原因。

## 0.7 nm / 2 TiB 边界

| 口径 | 当前事实 |
|---|---|
| measured | C1 p6/h10 四源 process-tree peak 为 1.5165–1.5362 GB；P0 13.5 nm cold setup peak 为 2.024108032 GB，并在 2 GB hard line 失败 |
| derived | P0 超出 hard line 24,108,032 B，约 1.2054%；这是当前 P0 resource Gate 结论，不是物理数值结论 |
| predicted | 完整 0.7 nm PDE 的 live-set、DoF、JIT、MPI/physical observable 仍未知，不能从上述 13.5 nm peak 外推通过或容量 |

因此 0.7 nm/2 TiB 仍是未闭合的 capacity boundary；没有创建 feasibility_v5，也没有运行完整 0.7 nm PDE。

## selective merge boundary

| 分类 | 当前内容 | 合入边界 |
|---|---|---|
| reusable audit/canonical/resource helper candidates | src/solvers/fullspace_lor_stable_adjoint.py；src/solvers/hcurl_canonical_vector.py；src/solvers/hcurl_canonical_vector_dolfinx.py；benchmarks/task034_wsl_resources.py | 仍需最终 selective review；不等于 ordinary default |
| research-only pending physical qualification | src/solvers/fullspace_same_mesh_hcurl_pmg.py、fullspace_same_mesh_hcurl_pmg_global.py、fullspace_same_mesh_hcurl_pmg_p6.py、fullspace_same_mesh_hcurl_pmg_runtime.py、fullspace_same_mesh_hcurl_pmg_setup.py、fullspace_same_mesh_hcurl_pmg_physical.py，以及对应 Task038 same-mesh C0/setup/positive/P0 runners/checkers | C1 positive 已通过，但 P0 resource hard stop；不得提升为 production |
| do-not-promote/do-not-merge as production numerical candidate | Route-A 6→3 candidate integration：src/solvers/fullspace_lor_interlevel_spectral_dolfinx.py 及对应 interlevel runner/checker；旧 Route-B/C2/HX 等已冻结失败路线 | 不提升为 production numerical candidate；stable-adjoint audit helper 不属于此类 |
| evidence/docs | 本轮 A0/P0 negative compact、outcomes 文档与 response_v13.md | 永久保留，可作为文档/证据选择性合入；提交负证据不代表把失败 solver 合入 production |

## 证据与文档入口

| 内容 | 入口 |
|---|---|
| C0 canonical source | same_mesh_canonical_source_v1.md |
| C1 positive | p6_positive_v13.md |
| P0 physical resource stop | p6_physical_v13.md |
| Route A boundary | route_a_stable_adjoint_v1.md |
| 逐项 response | ../response_v13.md |
| V11 historical closeout | ../response_v11.md、V11 outcome files |
| V12 historical closeout | ../response_v12.md、V12 outcome files |

ordinary default、master、full0.7nm PDE 和 P1/P2/G/D formal 均未被本次 docs closeout 改变或启动。
