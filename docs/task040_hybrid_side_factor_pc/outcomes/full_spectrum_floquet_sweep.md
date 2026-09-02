# Full-spectrum Floquet sweep outcome

## V9 current authority（Response v10）

| 项目 | 当前裁决 | 证据边界 |
|---|---|---|
| canonical transform | measured pass | lower/upper=`7560+7560`，`72 channels × 105 harmonics`；`numeric_allgather=false` |
| 两源 full-spectrum screen | `FULL_SPECTRUM_SWEEP_NO_SIGNAL` | `executed=true`；两源均形成 one-apply 与 r8/r16/r32/r64 |
| 数值含义 | measured strict no-signal | 两源 r64 均大于0.8且 32→64 drop 小于0.10；不是 implementation failure |
| 资源 | completed | natural exit；wall=`1013.0478316960507s`；peak RSS=`37884526592 B`；swap=`0` |
| 后续 | V9-E entry available | C0 也已形成 numerical no-signal；C1 按数值 Gate 不运行 |

本节是 Response v10 的当前 authority；下方 V1–V8 历史、失败 root 和原始命令保持不变。

## V9 corrected formal result

本路线的作用是把有限元 trace 行转换到完整的 Floquet channel/harmonic 网格，再开始两源 screen。转换身份检查和两源数值 screen 均已形成；结果是严格 no-signal，而不是实现失败。

| 项目 | 当前事实 |
|---|---|
| root / source | `results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1` / `4e857fcdf73caa94805cd255bf7aad44ea4f95f1` |
| classification | `FULL_SPECTRUM_SWEEP_NO_SIGNAL`；`executed=true` |
| transform | identity `PASS`；actual lower/upper=`7560+7560`，`72 channels × 105 harmonics`；`numeric_allgather=false`；`full_plane_numeric_replica=false` |
| watchdog | natural rc0；elapsed=`1013.0478316960507s`；peak=`37884526592 B`；swap=`0`；resource completed |
| source/checkpoint | `rhs_vectors_loaded=2`；`exact_output_vectors_loaded=0`为预期；两源均有 one-apply/r8/r16/r32/r64 |

raw watchdog 中记录的精确 worker 命令为：

```text
mpiexec -n 8 /home/fenics/Projects/MyFEniCS/.venv/bin/python -m benchmarks.task040_level_a --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1/worker --source-sha 4e857fcdf73caa94805cd255bf7aad44ea4f95f1 --memory-stages /home/fenics/Projects/MyFEniCS/results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1/memory_stages.jsonl --memory-markers /home/fenics/Projects/MyFEniCS/results/task040_v9_full_spectrum_mpi8_4e857fcd_native_fix1/memory_stage_markers.raw.jsonl --v8-full-spectrum-only --v9-source-packet-root /home/fenics/Projects/MyFEniCS/results/task040_v9_source_bridge_mpi8_17cf5ae2_native_fix1/worker --v9-source-packet-manifest-sha256 98610d2826342b963e0243ff57dd53753a82d0379021c89130069a9a0900ebd0 --watchdog-hard-stop-bytes 48318382080 --watchdog-enabled --bottom-route-only
```

对应身份为 input SHA=`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`、
physical SHA=`8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c`、resolved
config SHA=`f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883`；运行时为
native marker=`1`、repository `.venv`、MPI8、threads=`1`、PETSc `complex128` / `int32`。

### Corrected numerical checkpoints

| source | one | r8 | r16 | r32 | r64 | 32→64 drop |
|---|---:|---:|---:|---:|---:|---:|
| external | `2.4925577678654536` | `1.0847758611958496` | `1.0337741915450838` | `1.0000192505910723` | `0.9969676750006529` | `0.0013272830728985237` |
| random0 | `64.24596183468168` | `6.295285267481751` | `5.81369638252774` | `5.707565383934817` | `5.534173218910557` | `0.013398146942032231` |

两源均满足 `r64>0.8` 且 `32→64 drop<0.10`，故当前 classification 为
`FULL_SPECTRUM_SWEEP_NO_SIGNAL`。对应 run/watchdog/markers/stages/samples SHA 分别为
`e5b6db01b84344f70b29f0e129aae67b9b80202b1efde36f61e7aa4e08816af2`、
`ed02b43b723acc881fec7746af6293de90c420453aed1d62f2f07fcd69a5fc19`、
`ebcab72d0bbaa1d4d263f6368121b30686a023053a3a1ff13903040b63f31008`、
`7e0966ef750b7a2b14ac694a599ca0830f0cba3724621fe27beb39fbe9b234d0`、
`813924a7f8382d79d3dfc02617731b9fe82a2cb697f2f7bac6b11bdaa33eb357`。

### Raw Git identity

| 字段 | raw 值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| upstream_ref | `origin/codex/20260822-task40-hybrid-side-factor-pc` |
| upstream_sha / source_sha | `4e857fcdf73caa94805cd255bf7aad44ea4f95f1` |
| ahead / behind | `0 / 0` |
| worktree | clean |

## V9 current marker/resource/factor ledger

下表只属于 V9 corrected current formal；下方的 V8 表仍是独立历史记录。
RSS 是 process-tree raw resource 口径。

| stage | wall (s) | RSS (B) | swap (B) | action / PC |
|---|---:|---:|---:|---:|
| v8_full_spectrum_system_ready | 108.24802727304632 | 13007302656 | 0 | `0:0` |
| v8_full_spectrum_group0_factor_ready | 81.1873611700139 | 18066894848 | 0 | `0:0` |
| v8_full_spectrum_group1_factor_ready | 66.73523696203483 | 22356369408 | 0 | `0:0` |
| v8_full_spectrum_group2_factor_ready | 88.78320016397629 | 28041728000 | 0 | `0:0` |
| v8_full_spectrum_lower_transform_ready | 230.41364218504168 | 36745965568 | 0 | `0` (action0; PC 未报告) |
| v8_full_spectrum_upper_transform_ready | 90.70982092199847 | 36745969664 | 0 | `0` (action0; PC 未报告) |
| v8_full_spectrum_symbol_ready | 0.126716758008115 | 36745969664 | 0 | `0` (action0; PC 未报告) |
| v9_full_spectrum_source_packet_validated | 63.31240836495999 | 37224861696 | 0 | `0:0` |

source packet validated：wall=`63.31240836495999` s，RSS=`37224861696` B，
swap=`0`，action/PC=`0/0`，parent manifest=
`98610d2826342b963e0243ff57dd53753a82d0379021c89130069a9a0900ebd0`；两个
child manifest 分别为 external 的
`f60389e2e4dd1541046812588a9a7e09251e2b46a14face00eb57c953be3b98b` 与
random0 的 `dfb2e68f5c33f2d4b9656471c97acf11bc8ffbc4d051c3f959dd3be6f82406e6`。

| owner-vector-ready source | wall (s) | residual_max | RSS (B) | swap (B) | apply / PC |
|---|---:|---:|---:|---:|---:|
| v9_full_spectrum_external_owner_vector_ready | 63.427104757982306 | 7.753799030829772e-15 | 37224861696 | 0 | `0/0` |
| v9_full_spectrum_random0_owner_vector_ready | 63.54283763398416 | 1.6240915557578603e-15 | 37224861696 | 0 | `0/0` |

source marker 的 `action/PC` 计数如下；同一表内已将 raw 省略值展开为
`37230436352` B，避免把省略号误读成未知值。

| source / marker | wall (s) | RSS (B) | swap (B) | action / PC |
|---|---:|---:|---:|---:|
| v8_full_spectrum_external_one_apply_begin | 0 | 37224861696 | 0 | `0:0` |
| v8_full_spectrum_external_one_apply_end | 4.059700915997382 | 37224906752 | 0 | `1:1` |
| v8_full_spectrum_external_r8 | 19.59672143100761 | 37230436352 | 0 | `11:9` |
| v8_full_spectrum_external_r16 | 18.822397398995236 | 37230436352 | 0 | `20:17` |
| v8_full_spectrum_external_r32 | 31.95981600700179 | 37230436352 | 0 | `37:33` |
| v8_full_spectrum_external_r64 | 61.54732198297279 | 37230436352 | 0 | `71:65` |
| v8_full_spectrum_random0_one_apply_begin | 0 | 37230436352 | 0 | `71:65` |
| v8_full_spectrum_random0_one_apply_end | 4.643271095003001 | 37230436352 | 0 | `72:66` |
| v8_full_spectrum_random0_r8 | 20.07654752896633 | 37230436352 | 0 | `82:74` |
| v8_full_spectrum_random0_r16 | 18.257576933014207 | 37230436352 | 0 | `91:82` |
| v8_full_spectrum_random0_r32 | 32.67625262698857 | 37230436352 | 0 | `108:98` |
| v8_full_spectrum_random0_r64 | 62.30187107803067 | 37230436352 | 0 | `142:130` |
| v8_full_spectrum_cleanup_complete | 0.3879850030061789 | 37213806592 | 0 | `142:130`; factors `3→0` |

| MUMPS research factor inventory | rows | nnz | estimated bytes |
|---|---:|---:|---:|
| group0 | 41580 | 146855520 | 3524865128 |
| group1 | 34020 | 122101416 | 2930706152 |
| group2 | 41580 | 154341504 | 3704528744 |

三个 MUMPS research exact factors 均为 each one；它们不是最终 factor-free
candidate 的 retained factor 证据。

lifecycle raw 明确 `rhs_vectors_loaded=2`、`exact_output_vectors_loaded=0`；raw
cleanup 明确 `action_destroyed=true`、`matrix_destroyed=true`、
`system_destroyed=true`，factor 从 `3` 变为 `0`。逐 source vector destroy
字段未单独序列化，因此不作该层面的生命周期推断。

### V8 historical formal result

| 项目 | V8 历史事实 |
|---|---|
| root / classification | `results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1` / `FULL_SPECTRUM_IMPLEMENTATION_FAILURE` |
| transform | `PASS` |
| source/orchestration | 两个 source entries/orchestration 已形成，但 owner-vector load failure；无 source begin/end、one-apply 或 FGMRES checkpoint；apply=`0` |
| resource | historical stage-time wall=`1533.1877332139993s`；peak RSS=`38975795200B`；swap=`0`；未形成可审计 numerical screen |

该表只保留 V8 的 source/integration failure 事实；它不覆盖当前 corrected root 的两源 numerical
no-signal 结论。

### V8 historical marker snapshot

下表属于旧 V8 预运行快照，仅保留历史 marker 追踪，不代表当前 corrected formal root。

| raw marker | stage wall (s) | RSS (B) | swap | PC/action apply |
|---|---:|---:|---:|---:|
| `v8_full_spectrum_preflight` | `0.0` | `1641885696` | `0` | `0/0` |
| `v8_full_spectrum_system_ready` | `370.97334908600897` | `12480098304` | `0` | `0/0` |
| `v8_full_spectrum_group0_factor_ready` | `207.90935626099235` | `17674514432` | `0` | `0/0` |
| `v8_full_spectrum_group1_factor_ready` | `182.9128659699927` | `21893591040` | `0` | `0/0` |
| `v8_full_spectrum_group2_factor_ready` | `241.10231349102105` | `28171911168` | `0` | `0/0` |
| `v8_full_spectrum_lower_transform_ready` | `348.30305793098523` | `38749306880` | `0` | `0/0` |
| `v8_full_spectrum_upper_transform_ready` | `144.6964194290049` | `38749315072` | `0` | `0/0` |
| `v8_full_spectrum_symbol_ready` | `0.13321249099681154` | `38749315072` | `0` | `0/0` |
| `v8_full_spectrum_cleanup_complete` | `17.90213303899509` | `38874349568` | `0` | `0/0` |

该历史表与旧几何 extent、empty-local probe、token/layout 失败记录一并保留；当前 corrected formal
的 numerical 结论以上方 checkpoints 和 current root 为准。V8 failure roots 见本节及
[route ledger](route_signal_ledger.md)。

## 历史预运行快照

## 结论边界

全频谱路线先把 H(curl) trace 的 canonical channel 映射到完整的 15×7 harmonic 网格，再做
Floquet/FFT 传播，避免把 PETSc raw row 顺序误当空间顺序。tiny serial/MPI2 regression 通过
canonical block、phase-once、FFT/DFT、coverage 和 dual pairing；MPI8 formal 没有形成可审计
sweep 数值；该段是 V8 历史快照，不覆盖上方 `FULL_SPECTRUM_SWEEP_NO_SIGNAL`。

## 实际历程

### 第一次 MPI8 root：几何 extent 假设

root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_e7fee3c2_native`。
实际命令为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_e7fee3c2_native --source-sha e7fee3c2f7af8110698276a1789c8435fbc5db48 --v7-scale-normalized-identity --watchdog-enabled --bottom-route-only
```

该命令由 watchdog 以 MPI8/threads1 worker 执行，资源配置为 45 GiB、21600 s。

scale identity raw/checker 在该 root 已完成并给出 D0/D1 candidate；随后 continuation 抛出：

```text
ValueError: full-spectrum metadata failed: Gamma entity extent is not one periodic cell
```

根因是第一版 trace metadata 以浮点 uniform step 解释实际 entity geometry，而不是使用离散
canonical point-level inventory；watchdog `natural_exit`、worker return `1`，elapsed
`773.3814081490054 s`，peak RSS `36689285120 B`，swap `0`，authoritative samples `1329`，
没有 run summary。关键 SHA：watchdog
`0f64f8daf23ae1644c90b390c4b3d83fe60dc51cc3c258eae7cb9cab7824fbbc`，worker stdout
`c065334908ed21a46c6ba9c0848255bca4a96f70d71b02dde0d0ccac90358659`，markers
`fe3314aa5390ef058f6242c4571ddd60cfed96b2c2f800726cd7879e00ac5233`。

### 量化 level 修复后的 root：empty-local probe divergence

root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_ab51cad1_native`，
source SHA=`ab51cad19f25b1853d0b9ed479a3350dfdf24f4b`。实际命令为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_ab51cad1_native --source-sha ab51cad19f25b1853d0b9ed479a3350dfdf24f4b --v7-scale-normalized-identity --watchdog-enabled --bottom-route-only
```

x/y 坐标改为离散 level inventory 后，
formal 在 `_canonical_probe` 抛出：

```text
ValueError: canonical full-spectrum probe is invalid
```

部分 rank 合法持有 empty local rows，却被 rank-local 判为 invalid；其他 rank 继续 collective，
形成 rank divergence。该 root 没有 watchdog summary；worker stdout SHA
`af84db4a21b49f8bd5353596d9bb152a95a262459cfda835d67e9b265543f634`，markers SHA
`902b10a0319e84fd2ef751dce0f3003885a0da0d9dc79a313be8e658d605c9c7`，stages SHA
`20731b117a7b95affb324733dc4cb92821ef08086ba90e633e0312bf20c5c13f`。

随后 `a2acb934` 仅将 empty-local 情形改成 collective-safe 判定：所有 rank 对 finite 用
LAND、对“至少一个非零 local payload”用 LOR，再统一继续或统一失败；serial/MPI2 targeted
regression 通过。按 Review 的 corrected formal 额度和“不得第三跑”纪律，没有把 targeted
修复夸大成 MPI8 formal pass。

## V8 当时的关闭理由（已被 V9 corrected formal supersede）

本节只记录 V8 root `089bf8a1` 前后的历史关闭理由：当时的 formal 证据在
metadata/probe 实现层未闭合，随后 moving-PML 又达到真实 wall/resource stop，因此 V8
只能记为 `FULL_SPECTRUM_IMPLEMENTATION_FAILURE`。那一轮没有形成可审计的 symbol、两源
screen 或 Krylov checkpoint；这句话只适用于 V8 历史，不适用于当前 V9 corrected formal。

V9 已在本页顶部以同一物理身份形成 Floquet transform、两源 one-apply 与 r8/r16/r32/r64，
并以 `FULL_SPECTRUM_SWEEP_NO_SIGNAL` 收口。该 V9 当前结论覆盖 V8 的关闭理由，但不删除
V8 raw history，也不表示 0.7 nm 已被证明不可行。旧 V6-2 absolute negative 保持独立有效，
见 [full-interface identity](full_interface_schur_identity.md)。
