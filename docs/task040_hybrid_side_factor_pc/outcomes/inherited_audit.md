# T40-0 继承基线审计

## 审计范围与身份

本文件是 Task40 的 T40-0 inherited audit。它只核对已经存在的 Task39/V7/Task038-extra 证据，不运行 PDE、QEP、MPI heavy 或任何新的数值路线，也不改变输入、代码、阈值和 ordinary defaults。

| 项目 | 已核对值 |
|---|---|
| 执行分支 | codex/20260822-task40-hybrid-side-factor-pc |
| HEAD / upstream | 37923935d9378bcb10d4f28f859762e7a8711b8f / 同值 |
| ahead / behind | 0 / 0 |
| 工作树 | clean |
| Task40 task.md SHA256 | b09af10f19e5b380aac74c5b5be2e39cd8756d0a23727afc5bd1b853bf833ec7 |
| Task40 inherited base SHA | 9dc9ac58e05e5422498dade503046f9ae87d13d9 |
| Task39 frozen input | input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat |
| input SHA256 | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 |
| resolved configuration SHA256 | f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883 |
| selected-mode packet manifest | results/task039_v4_h4_m480_shared_packet_eaad0f94/manifest.json |
| selected-mode packet manifest SHA256 | 2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067 |
| response packet manifest SHA256 | 1f4e8acaf278bde0d0d14a2a096335049ee988cdbc1b406bca4197918ff64a0e |
| exact-response spool catalog SHA256 | a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384 |
| V7 exact-side authority | results/task039_v7_h4_exact_side_full_formal_mpi8_9e31ecf1 |
| V7 modal NPZ / array SHA256 | 7107e54e47498d7b493076dee3bbab0fc94e06db76f20e67e254fbeb46a8a8c2 / c386d3f97180de5879006209091a3e2743709857065d3aa4dfffd320f6962ce4 |
| V7 active-trace manifest SHA256 | fae8e3654e5f21ac81f23080de6f1763e99bb2b12ba28d0ddd1814d24e01d765 |
| Task39 V11 source for inherited evidence | 677ab26dcfef79f0f754b88f2cfb8832edac4285 |

The physical model identity is the frozen Task39 resolved identity, physical_model_sha256=8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c. The selected packet, response packet, exact spool, and V7 authority are referenced by measured or hash-bound identities above; no new packet or spool is produced in T40-0.

## Qualified environment snapshot

The read-only probe used scripts/activate_myfenics_wsl.sh in the canonical Linux checkout.

| Probe | Result |
|---|---|
| _MYFENICS_WSL_QUALIFIED_ACTIVATION | 1 |
| interpreter | /home/Projects/MyFEniCS/.venv/bin/python |
| PETSc scalar | numpy.complex128 / complex128 |
| PETSc integer | numpy.int32 / Int32 |
| MPI target | MPI8 for the formal case; probe process size 1 |
| threads | OMP_NUM_THREADS=1, MKL_NUM_THREADS=1, OPENBLAS_NUM_THREADS=1 |
| MemAvailable at probe | 240528228352 B |
| swap | 34359738368 B configured, 0 B used |
| filesystem available | 815071784960 B on /home/Projects/MyFEniCS filesystem |
| concurrent heavy work | none observed in the process snapshot |

This is an environment snapshot, not a formal MPI8 qualification. A later formal phase must repeat the ABI and MPI8 checks in the same activated shell before starting any worker.

## What is inherited

Task40 inherits the following measured or hash-bound evidence:

- direct full workflow peak: 93.377006531 GiB;
- exact-side iterative full-workflow peak: 80.025856018 GiB;
- the sequential stage envelope: 23.195 GiB, 49.313 GiB, 79.464 GiB, and 80.025856018 GiB;
- the Task39 V11 response-packet component result and its negative bottom algebra classification;
- V7 exact-side full formal as the canonical physical/trace baseline, not as a replacement for the new scalable candidate.

The prior response packet is an inherited research artifact. Task40 may reuse its identity and relevant source conventions, but must not rerun its producer, rebuild the response packet, or treat response compression as a qualified side inverse.

## T40 gates and stop rules

The candidate must preserve the frozen 5 nm, 1 degree grazing, phi=0, S-polarized, p6h4, M480, MPI8 physical case. No QEP, M, dynamic DtN, global action, recovery, response packet, Full3D, 0.7 nm, direct full-side, V7 exact-side full rerun, J1-alone, SN2, ordinary ILU/BLR, sweep, concurrent heavy job, new branch, worktree, or master write is in scope.

The staged route is conditional. T40-3 Level A uses subdomains [0,1], [2,3], [4,5], first-order tangential impedance, and the fixed forward/backward order 0→1→2→1→0. Cross-section exact factors are oracle-only and cannot be the scalable formal result. Level B is blocked unless the six mandatory bottom sources satisfy the rho and residual/resource gates in task.md. Task40's later Level B, bottom A, top, both-side setup, full Hybrid, and conditional h3 scaling stages remain not_run until their preceding gates pass.

At every stage, a real numerical, resource, lifecycle, or identity failure is preserved as evidence and classified at the first failed gate. An implementation defect may receive only the minimum local repair and focused regression required by task.md. No parameter, threshold, sign, physical input, or difficult column may be changed to obtain a pass.

## T40-0 status

T40-0 is complete as a docs-only inherited audit. No new numerical result, code change, input change, configuration change, or raw artifact was created. The next allowed phase is the static T40-1/T40-2 architecture and tiny-oracle implementation work.
