# V9 source canonical bridge outcome

## 当前 authority

canonical source bridge 的作用是把外部耦合源绑定到当前有限元实体的物理 key；通俗地说，它防止把不同 MPI rank 的 raw row 编号误当成同一个物理量。它只解决 source identity，不自动证明完整求解器有效。

| 项目 | 结果 | 边界 |
|---|---|---|
| canonical identity / packet mechanism | measured component pass | key、packet、phase/roundtrip 证据成立 |
| source-only formal | `V9_SOURCE_CANONICAL_BRIDGE_PASS` | MPI8 resource pass；只完成 current-layout source identity |
| full-spectrum follow-up | `FULL_SPECTRUM_SWEEP_NO_SIGNAL` | 另一个 corrected root 已形成两源 numerical screen，不是 implementation failure |
| V9-E 作用 | entry measured | 与 C0 numerical no-signal共同构成双入口；不把 source bridge单独当 residual Gate |

## Formal evidence

| 项目 | 值 |
|---|---|
| root / source | `results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1` / `17cf5ae28ccdcf7b0a28548ec1296b9956390509` |
| classification | `V9_SOURCE_CANONICAL_BRIDGE_PASS` |
| watchdog | resource pass；wall=`165.91914472501958s`；peak RSS=`13773049856 B`；swap=`0` |
| duplicate audit | missing=`0`、extra=`0`、current duplicate=`0`、persisted duplicate=`0` |
| current/reconstructed norm | `78.95028494966387` / `78.95028494966385` |
| current canonical/owner/repeat/norm/static relative | `9.080958487276232e-15` / `9.080234675738409e-15` / `9.080234675738409e-15` / `1.7999751013264084e-16` / `0` |
| random0 norm | `363.73066958946424` |
| random0 canonical/owner-repeat/norm-static relative | `3.904495497056956e-15` / `9.485887296092138e-17` / `0` |
| phase semantics | phase applied once |

source-only raw inventory 明确记录：每个 source 的 C/D/H、factor、FGMRES、QEP 均为 `0`，
group factors=`0`，`numeric_allgather=false`。该 formal 不产生 physical solver factor 或
outer residual。

### Raw Git identity

| 字段 | raw 值 |
|---|---|
| branch | codex/20260822-task40-hybrid-side-factor-pc |
| upstream_ref | origin/codex/20260822-task40-hybrid-side-factor-pc |
| upstream_sha | 17cf5ae28ccdcf7b0a28548ec1296b9956390509（source SHA） |
| ahead / behind | 0 / 0 |
| worktree_porcelain | "" |
| checks | 全部 pass |

raw cleanup 明确记录 source_vectors_destroyed=true、
system_destroyed=true、bare_f_unchanged=true；只有逐 source packet/vector
ownership 与 packet release 的细节未分别序列化，因此不作更细生命周期推断。

## 双源 canonical raw audit

以下表格逐项保留 source-only raw 中的双源 key/value 证据。digest 是各自
current 与 persisted raw value-pair 的独立哈希；它们不要求 bitwise 相等，资格
来自物理 key 双射以及固定 `1e-12` 相对误差 Gate。

| common inventory 项目 | raw 值 |
|---|---|
| common key count | `141972` |
| missing / extra / current duplicate / persisted duplicate | `0 / 0 / 0 / 0` |
| global key set hash | `2aca3dc2150fe20f6e7e3c05751cd81ee2c6a4878918e9eee092ff24d41cca76` |
| edge / face orientation counts | `14352 / 127620` |
| phase_application_count / orientation_applied_once | `1 / true` |

7 个 relative 字段的顺序固定为：
`canonical / current-repeat / owner-roundtrip / reconstruction-repeat /
canonical-roundtrip / norm / static-condensed-repeat`。

| source | child manifest | current value-pair digest | persisted value-pair digest | current / reconstructed norm |
|---|---|---|---|---|
| external | `f60389e2e4dd1541046812588a9a7e09251e2b46a14face00eb57c953be3b98b` | `028469b0a479876da82f55c4111bd799af13e9b4a920087d4c04a40110f7e7ca` | `e09d22f64263a8b4facf83b52f0dffb370d076847b44bceecf65b1c16ac7c237` | `78.95028494966387 / 78.95028494966385` |
| random0 | `dfb2e68f5c33f2d4b9656471c97acf11bc8ffbc4d051c3f959dd3be6f82406e6` | `c50c7331df7e8fb55e2516ef25d4cab6582e79ef654af71fa01a3889596677ed` | `af10b71a88ae0e2ea70d8aa815bc3e9a63b9e70c1a6a58258829d475f9d33d29` | `363.73066958946424 / 363.73066958946424` |

| source | canonical / current-repeat / owner-roundtrip / reconstruction-repeat / canonical-roundtrip / norm / static-condensed-repeat |
|---|---|
| external | `9.080958487276232e-15 / 0 / 9.080234675738409e-15 / 9.080234675738409e-15 / 1.0414993922087005e-16 / 1.7999751013264084e-16 / 0` |
| random0 | `3.904495497056956e-15 / 0 / 9.485887296092138e-17 / 9.485887296092138e-17 / 3.903931854346923e-15 / 0 / 0` |

whole packet manifest 为
`98610d2826342b963e0243ff57dd53753a82d0379021c89130069a9a0900ebd0`。

## Exact raw worker command and identity

raw watchdog 中记录的 worker 命令为：

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/worker --source-sha 17cf5ae28ccdcf7b0a28548ec1296b9956390509 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/memory_stage_markers.raw.jsonl --v9-source-bridge-only --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
```

| identity | value |
|---|---|
| input / physical / resolved config SHA | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` / `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` / `f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883` |
| runtime | native marker=`1`；repository `.venv`；MPI8；threads=`1`；PETSc `complex128` / `int32` |

| 文件 | SHA256 |
|---|---|
| run/manifest | `98610d2826342b963e0243ff57dd53753a82d0379021c89130069a9a0900ebd0` |
| watchdog | `11502549903096c21a5c22e6d9b3bdbbd6aae0cd101c931d3aa7861b68efd99a` |
| markers | `83e179df5b271ad671ed936b86bae4aa0ac97c2bcbc23d95121429f86aa95ebc` |
| stages | `7ebfaa95df1ebc0159e4b9289026e153d19d4ec69be455aacd5fe10defa9988f` |
| process samples | `7b686664f7bfe6a80ee62d7c06763ca209e5ae507a1667a0a6c1c4a6b320d4ee` |

## Corrected full-spectrum formal

| 项目 | 值 |
|---|---|
| root / source | `results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1` / `4e857fcdf73caa94805cd255bf7aad44ea4f95f1` |
| classification | `FULL_SPECTRUM_SWEEP_NO_SIGNAL`；`executed=true` |
| transform | lower/upper=`7560+7560`；`72 × 105`；transform pass |
| external one/r8/r16/r32/r64 | `2.4925577678654536` / `1.0847758611958496` / `1.0337741915450838` / `1.0000192505910723` / `0.9969676750006529` |
| external 32→64 drop | `0.0013272830728985237` |
| random0 one/r8/r16/r32/r64 | `64.24596183468168` / `6.295285267481751` / `5.81369638252774` / `5.707565383934817` / `5.534173218910557` |
| random0 32→64 drop | `0.013398146942032231` |
| structure | `rhs_vectors_loaded=2`；`exact_output_vectors_loaded=0`为预期；action=`142`；PC=`130`；factors ready/simultaneous=`3`，cleanup=`0` |
| watchdog | natural；wall=`1013.0478316960507s`；peak RSS=`37884526592 B`；swap=`0`；resource completed |

两源 r64 均大于0.8且 32→64 drop 均小于0.10，因此这是 strict numerical no-signal。`exact_output_vectors_loaded=0` 是本轮禁止 exact-output producer 的设计值，不是 source integration failure。

## 与 C0/E 的关系

source bridge 的 measured pass 不是 V9-E 的 numerical entry。full-spectrum 后续两源 route
已经形成 one-apply 与 r8/r16/r32/r64，并以 `FULL_SPECTRUM_SWEEP_NO_SIGNAL` 收口；C0 worker
也确实完成了单次 external one-apply 并形成 numerical no-signal。C0 worker no-signal 与
watchdog resource authority gap 由 [response v10](../response_v10.md) 并列记录。

## 合并边界

该机制可作为后续 canonical source 审查的研究证据；它本身不是 production route、ordinary
default 或 master merge candidate。full-spectrum/C0 的 numerical 结论分别以各自 raw root 为准。
