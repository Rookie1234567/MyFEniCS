# Task038-extra Review V11：最终 S6 response

## 结论先行

S1、S2 和 S4 在各自合同范围内通过；S5 的内存/生命周期证据通过，但固定的 6→3 interlevel energy Gate 失败：

```text
energy_6_to_3 = 0.04115402900674629 > 1e-9
energy_3_to_1 = 2.7851655955739857e-15 <= 1e-9
```

因此 `lor_edge_geometric_mg_v1` 在 S5 关闭，不能写成 S5 solver pass。S6 只做文档与 compact evidence 收口；没有重跑 S4/S5，也没有运行 p6 physical Maxwell、p6/h5、0.7 nm PDE 或 official physics。

## 1. 身份、ABI 与工作树

| 字段 | S6/正式证据事实 |
|---|---|
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| formal S5 source / HEAD | `2507a16d8f19df9b432319ae1625ea9b817d78f8` |
| base merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| upstream | `origin/codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| pre-closeout commit snapshot ahead/behind | `27/0`；这是 S6 closeout commit 前的 measured snapshot，最终提交/push 状态由 handoff 报告 |
| formal source tree | worker start/end 均 clean、branch/source SHA exact |
| pre-closeout review snapshot / S6 delta | 当时仅有规定的 docs/compact delta；没有 Python 或 numerical-core 修改 |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | qualified `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python`，3.12.3 |
| ABI | PETSc 3.19.6、DOLFINx 0.10.0.post2、Basix 0.10.0、SLEPc 3.19.2、mpi4py 同栈 |
| scalar/index | `complex128` / `int32` |
| MPI/threads | S1/S2/S5 为 MPI1；`OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1` |

S6 没有把文档修改后的未提交状态回写成 formal source identity；formal record 内的 source start/end 仍是 2507 SHA、clean=true。

## 2. 永久保留的旧结论

| evidence | status | exact boundary |
|---|---|---|
| V10 Q0 Reference E | `controlled_negative` | 500-step explicit true residual `4.2034233790900783e-4 > 1e-8` |
| foundation-E | `pass` | p3/h50/MPI1/random/exact LOR edge，3020 步 `9.260562270838936e-9` |
| old global spectral audit | `controlled_negative` | fixed smallest GHEP `reason=-1`, `converged=0`，spectrum not established |
| HX/PCGAMG | `closed` | current inverse quality不足；V11 禁止参数扫描/第三变体 |
| ba40358 S5 probe attempt | `controlled_negative evidence` | probe domain invalid；原始 root 与 compact archive 不覆盖、不重分类 |

Q0 record/checker 的 relocated hashes 仍是 `2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82` 与 `be70e0e559fea32023dfde58e4ede11009574c18f51e4b914d9b5034832a35ea`。foundation-E 的 exact direct residual 为 `9.13154427545479e-16`，但这是基础代数/迭代路线证据，不是 production inverse。

## 3. S1 global transfer/rank/spectral audit

S1 formal source 为 `d19848e6f5484835a84186d13e349ae30fc8d56d`。它只在 p2/p3 小模型中允许 assembled high-order audit AIJ、explicit sparse transfer 和 temporary dense rank copy；这些对象没有进入 p6 或 ordinary default。

| case | full/slave/independent | rank | singular endpoints | lambda endpoints | condition |
|---|---:|---:|---:|---:|---:|
| p2/h50/MPI1 | 988/220/768 | 768 | 0.25262199571308525 … 1.1728839979271446 | 0.07953013700040465 … 4.2447253801431595 | 53.37253952072989 |
| p3/h50/MPI1 | 3018/480/2538 | 2538 | 0.35955933841154997 … 3.7874131839018776 | 0.019970670477800642 … 283.0573385017638 | 14173.652247500142 |

Smallest/largest eigen residuals were p2 `1.1083766402470227e-13 / 2.7133854271858805e-15` and p3 `2.0408235169191283e-11 / 6.039533107090146e-15`; work, Hermitian, SPD and rank Gates passed. S1 process-tree peak was `788,987,904 B`, swap `0 B`. S1 compact record/checker SHA are `8ffa8f1e74392bbd062314e0656d56c3bc464520c541d3a4668a52fad0a2ab09` and `acec3b84f2e8001335bf362aa509e5a809657d5af11b33a847e51fd63cf1a5e3`.

## 4. S2 p6/h10 foundation resource qualification

S2 source was `12adebdf0e5e78de33818e97fd35cd870fef3a4e`, p6/h10/MPI1/13.5 nm. The retained foundation live set included matrix-free high action, streaming DtN, level-6 LOR matrix/transfer metadata and restart20 reserve; it did not include HX/PCGAMG, scalar node matrix, p6 exact factor, high-order global AIJ, global dense transfer, direct coarse or recovery arrays.

| item | measured |
|---|---:|
| high/low rows | 173,802 / 173,802 |
| `B_L` NNZ | 5,825,468 |
| index/numeric payload | 23,997,084 / 93,207,488 B |
| transfer retained | 8,302,080 B |
| restart reserve | 21 basis + 4 auxiliary = 25 vectors; 69,520,800 B |
| known retained total | 249,126,201 B |
| cold peak | 983,363,584 B `<1.8 GB` |
| external retained peak | 983,363,584 B `<=1.55 GB` |
| headroom to 2 GB / 1.55 GB | 1,016,636,416 / 566,636,416 B |
| repeated growth / swap | 0 B / 0 B |

The shared `/init.scope` cgroup swap was non-dedicated diagnostic only; process-tree/rank swap was zero. S2 record/checker hashes are `70f8f865a8943297364fdb2fdcbcbf164ceb4f56af8c48285bcca5f8af196a24` and `4f6834a02948fb8d86031ce609d467889a70bef3f143cb1c2f2c1af78cc5605a`.

S1 PASS + S2 PASS selected the S4 branch. This was a staged authorization, not a claim that a p6 solver already existed.

## 5. S4 small oracle: all 16 cases

The immutable aggregate checker is bound at:

```text
benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_v1/2b2df645418ee28c68681832661e58993897166d/aggregate_check.json
SHA256 = 56b7eec1435abc69a38c38af056d8803e8f62a3ff6768b87faa594670c916c4e
```

Its result is `contract_errors=[]`, `gate_failures=[]`, 16/16 individual pass and 8/8 MPI pairs within the original dynamic bound. The first four p2-MPI1 cases use source `ca5171ac3bd6dd6ab333619cd76fd771524520e6`; the remaining 12 use `2b2df645418ee28c68681832661e58993897166d`. The latter source change was watchdog MPI launch lifecycle only; aggregate provenance still matched input/operator/physical identities.

| case/source | iterations | final true residual rho | peak B | swap |
|---|---:|---:|---:|---:|
| p2-mpi1/random | 60 | 3.9948626309604484e-9 | 141017088 | 0 |
| p2-mpi1/gradient | 60 | 3.25310382535185e-10 | 141168640 | 0 |
| p2-mpi1/curl | 60 | 5.091224143942273e-10 | 141119488 | 0 |
| p2-mpi1/checkerboard | 60 | 3.417129297272225e-09 | 140943360 | 0 |
| p2-mpi2/random | 60 | 4.136064677452021e-09 | 264179712 | 0 |
| p2-mpi2/gradient | 60 | 3.2856679620394e-10 | 264032256 | 0 |
| p2-mpi2/curl | 60 | 5.130698689690218e-10 | 263917568 | 0 |
| p2-mpi2/checkerboard | 60 | 3.5462840455740654e-9 | 264196096 | 0 |
| p3-mpi1/random | 2000 | 9.891883798422905e-9 | 154349568 | 0 |
| p3-mpi1/gradient | 2220 | 9.58588584878323e-9 | 154468352 | 0 |
| p3-mpi1/curl | 2560 | 8.8655645455621e-9 | 154873856 | 0 |
| p3-mpi1/checkerboard | 2340 | 9.074003354422413e-9 | 154214400 | 0 |
| p3-mpi2/random | 1880 | 9.933358713345764e-9 | 286695424 | 0 |
| p3-mpi2/gradient | 2500 | 9.372360341341475e-9 | 284643328 | 0 |
| p3-mpi2/curl | 2960 | 9.844698995593758e-9 | 286298112 | 0 |
| p3-mpi2/checkerboard | 2220 | 9.618468797692642e-9 | 285081600 | 0 |

The maximum S4 process-tree peak was `286,695,424 B`. The compact S4 manifest/checker summaries are `outcomes/records/lor_edge_geometric_mg_oracle_v1.json` (SHA256 `5d132e21915c1a3fb1fa9af0c1fe3a4b711005b8bdedac08e04ee56b96b1cfb6`) and `..._checker.json` (SHA256 `8e2b552fbc773bda94d2605a5a8184e1d3ee35929964e84903a80c1fa39bb38b`); they are deterministic summaries, not reruns.

## 6. S5 formal and exact failed Gate

S5 source SHA was `2507a16d8f19df9b432319ae1625ea9b817d78f8`; the fresh root was:

```text
benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_p6_capacity_v1/2507a16d8f19df9b432319ae1625ea9b817d78f8/s5-p6-h10-mpi1
```

Worker rc was 0 and independent checker rc was 1. The checker returned no contract error and exactly one algebra Gate failure: `transfer 6-3 energy failed`.

| level | rows | NNZ | index/numeric bytes |
|---:|---:|---:|---:|
| 1 | 1,067 | 37,253 | 153,284 / 596,048 |
| 3 | 23,073 | 783,083 | 3,224,628 / 12,529,328 |
| 6 | 173,802 | 5,825,468 | 23,997,084 / 93,207,488 |

| pair | edge local map / NNZ / bytes | node local map / NNZ / bytes |
|---|---|---|
| 6→3 | 882×144 / 26,136 / 2,032,128 | 343×64 / 21,952 / 351,232 |
| 3→1 | 144×12 / 324 / 27,648 | 64×8 / 512 / 8,192 |

| probe | 6→3 | 3→1 |
|---|---:|---:|
| adjoint work | 1.2865066317766304e-14 | 1.733756183951221e-15 |
| linearity / repeat | 3.0795110632853766e-16 / 0 | 1.367938864665659e-16 / 0 |
| energy relative | **0.04115402900674629 (FAIL)** | 2.7851655955739857e-15 (PASS) |
| finite / input unchanged | true / true | true / true |

Smoother metadata remained fixed: degree 3, power 10, one pre and one post; `lambda_power10` was 4.033660535252619 at level 6 and 2.451729321670397 at level 3. The reserve was 25 touched vectors / `69,520,800 B`. The p1 budget `885,908 B` was only a derived payload estimate; no p1 solver/factor was constructed.

The external watchdog/checker resource authority reported cold and retained-window peak `1,207,476,224 B`, swap `0 B`, and all status readable. The record ledger separately reported a retained sample of `1,201,344,512 B`, known total `296,345,065 B` and unattributed `904,999,447 B`; the two measurement fields are not conflated. `/init.scope` shared swap `13,799,424 B` was non-dedicated diagnostic only.

The fixed S5 evidence hashes are:

| evidence | SHA256 |
|---|---|
| watchdog raw | `a4915601a28ed81f0a4487912003d73f5d2e8bec8c2c87126b3547dbcc7cf66b` |
| watchdog compact | `aab1304a2e4caaaaf496a3476c6a4bef001611b527980483be5c4f6464275b38` |
| worker record | `2a2731325cc0fc75b5efb1445c812e0660b4987b96ad88de2a471d623887e181` |
| checker | `cb74710a144aac0db18741c6328fe4ec2b25e61c9535c6c0d4c1ec686f108221` |
| empty worker log | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| probe_facts.npz | `1f0ba8c9e5e2082330c1049446977640bc5f107789c893e5d50bcedcf4e05816` |

The ba40358 invalid-probe archive remains immutable: record `ad8bbc3dfd81ba489efd6a4b2c24530c43f68484facc43020f9c5044f3be2a3f`, checker `93423f917256edd40ac13727af2feac58e4dcc63dde29a229742e6b960f5aaa8`.

The failure is not a resource or runner defect. Supplemental pure-local diagnosis found non-nested p3/p6 GLL nodes; a naive 2:1 tiled composition defect was `0.23558864802518256`. Fixing this would require a different non-nested geometric projection or Galerkin coarse architecture. Review V11 did not authorize that repair, so no tiled proposal was implemented.

## 7. Commands and provenance

The S1 and S2 commands were the fixed qualified worker/watchdog forms in their immutable outcomes. The S5 worker argv was:

```text
/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python -m benchmarks.run_task038_full3d_lor_hierarchy_capacity --stage s5 --case p6-h10-mpi1 --raw-dir benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_p6_capacity_v1/2507a16d8f19df9b432319ae1625ea9b817d78f8/s5-p6-h10-mpi1/worker_raw --record docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1.json --expected-source-sha 2507a16d8f19df9b432319ae1625ea9b817d78f8 --expected-mpi-size 1 --input /home/shenjh/Projects/MyFEniCSx_task37_extra/input/templates/full3d_iterative_example.dat
```

The existing foundation watchdog supplied the external process-tree sampling with RSS hard limit `2,000,000,000 B`; the independent pure-NumPy checker read the fixed record and watchdog compact. No S6 command reran a worker or checker.

## 8. Required classification and answers

| category | V11 status |
|---|---|
| pass | S1 structure; S2 resource; S4 small oracle; foundation-E at its p3 scope |
| failed | S5 6→3 energy algebra Gate; `0.04115402900674629 > 1e-9` |
| controlled_negative | Q0 500-step; old SLEPc global spectrum; ba40358 invalid probe archive |
| not_run / not_run_by_gate | S5+ repair, p1 distributed coarse solver, p6 physical Maxwell, p6/h5, 0.7 nm PDE, official R/T/A |

The next blocker has **not** converged to “p1 distributed coarse solver”: the first blocker is 6→3 interlevel energy consistency. Ordinary default was not changed; `master` was not modified or merged; the full 0.7 nm PDE was not run. The historical HX/PCGAMG closure remains unchanged.

## 9. Tests and changed files

The tests belong to the already-qualified implementation evidence; S6 did not rerun them because no Python, transfer, matrix construction or checker code changed.

| verification | result |
|---|---|
| `test312` | 20 passed / 350.31 s |
| `test313` | 22 passed |
| related `test294` | 3 passed / 91.97 s |
| compileall / AST duplicate-key / diff-check | pass |
| Ruff | unavailable; no installation attempted |
| CI | not claimed |

S6 creates/updates only the requested documentation and compact evidence paths: S4 outcome + two S4 summaries, S5 outcome, `outcomes/summary.md`, `docs/development_progress.md` and this `response_v11.md`. The two final S5 JSONs were preserved byte-for-byte. No source code, ordinary default, master, artifact root or historical negative evidence was modified.
