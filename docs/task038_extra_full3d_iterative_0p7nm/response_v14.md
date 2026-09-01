# Task038-extra Review V14 response

## 结论

V14 J5 v3 的唯一 formal 已完成冷 staging、physical setup 和至少到 checkpoint-1000 的真实测量；raw timeline 随后继续约 `3896 s`，并在 checkpoint-1500 前由用户因 numerical plateau 受控停止。实际停止迭代数 unavailable。最终分类为 `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED`。它不是 fixed-cap 20000-step failure，也不是完整 workflow memory PASS。

`same_mesh_hcurl_pmg_v1_requalified` 仍是 C1 四源 positive qualification 的 selected hierarchy；但这项正定辅助问题资格不能升级为 standalone physical Maxwell production qualification。

## 身份与证据

| 项目 | 值 |
|---|---|
| source SHA | `ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |
| input / physical / mode SHA | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` / `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` / `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| formal root | `/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |
| compact | [`j5_full_cold_staged_v3_controlled_stop_v14.json`](outcomes/records/j5_full_cold_staged_v3_controlled_stop_v14.json) |
| raw policy | parent JSONL、cache、markers 和 fields 留在 ignored root；1.02 GB raw 不追踪 |

## V14 phase status

| 阶段 | 当前状态 | 边界 |
|---|---|---|
| V11 S5 | frozen negative | 6→3 energy `0.04115402900674629 > 1e-9` |
| V12 | frozen historical negative | `selected_hierarchy=NONE`、identity/Route A/B/C2 negatives 不重分类 |
| V13 C1 | PASS | random/gradient/curl/checkerboard exact-input 四源通过；selected hierarchy 为 `same_mesh_hcurl_pmg_v1_requalified` |
| V13 P0 | FAILED_RESOURCE_HARD_STOP | cold setup peak `2,024,108,032 B`，超过 2 GB hard line `24,108,032 B` |
| V14 J4 | PASS | one-cycle P0R qualification；旧 evidence 保留 |
| V14 J5 v3 | `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED` | 最后权威 checkpoint=1000；之后继续运行并在 checkpoint-1500 前停止；exact stop iteration unavailable |
| J6 | `not_run_by_J5_eligibility` | 未到 20000 步，long-tail 条件不成立 |
| J7/J8 | `locked/not_run` | 没有 solve-complete/recovery 前置证据 |

## J5 实测结果

| 指标 | 值 |
|---|---:|
| raw samples | 334,915 |
| raw bytes / SHA256 | 1,020,808,306 B / `28c4044f3eebb72ca1991d1c71a67dd30637a7d550e798ffc7f536c28d969cf4` |
| raw first/last timestamp | `1788206276386617381` / `1788228581099334131`；window `22304.712716750 s` |
| solve start → last sample | `16477.100765097 s`；solve_started=`1788212103998569034` |
| full staged peak / swap | 1,450,262,528 B / 0 B |
| marker boundary | `035_solve_started`；共 36 个 marker |
| checkpoint-500 | residual `0.48387099430079733` |
| checkpoint-1000 | residual `0.4837947981092168` |
| 500→1000 relative drop | `0.000157472120623114`（约 `0.01575%`） |
| readability | RSS/status 334,915 个样本完整可读；PSS 有 6 个 precompile 退出/zombie 瞬时样本不可读 |
| records / stderr | parent、worker、partial record absent；worker stderr 0 B |

完整 checkpoint 文件与 hash 见 [`p6_physical_v14.md`](outcomes/p6_physical_v14.md) 和 [`jit_staging_physical_memory_v14.md`](outcomes/jit_staging_physical_memory_v14.md)。冷 staging 到停止点的 RSS 实测低于 2 GB，但因没有 solve-complete、release 或 recovery，不能称为 end-to-end memory PASS。

最后权威 checkpoint 为 1000；checkpoint-1000 manifest mtime 后 raw 仍持续约 `3896 s`，checkpoint-1500 不存在。worker/parent/partial record 缺失，因此 per-cycle residual history、actual stop iteration、matvec_count、pc_apply_count、ksp_destroy_count 和 driver elapsed_seconds 都 unavailable，不能由迭代数或代码公式推算。

## Official physics 与 authority

official complex E/H、near-field、R/T/A、`A_volume`、energy closure，以及同一 12 个 significant identities 的 12 power + 12 complex boundary-amplitude arrays 全部 `not_run`。J0 已确认的 direct authority 仍只有 scalar `R/T/A/A_volume`；缺少 E/H 与 12+12 raw arrays。该下游 blocker 仍保持 fail-closed，且不是 J5 本次停止的原因。

## 代码与历史边界

V14 J5 controlled stop 没有改变 Python、物理方程、selected hierarchy、ordinary default 或 master；V13 C1 positive、V13 P0 hard-stop、J5 v1/v2 negative 和 V11/V12 historical negatives 永久保留。没有把 1.02 GB raw artifact 加入 Git。

## 下一步：仅提出 V15 独立诊断（未授权、未实现）

V15 只能作为新的 review、新 source SHA 和新 artifact root 下的独立诊断候选，不能冒充 V14 J6 PASS：

1. 保留已经通过 positive qualification 且内存较低的 same-mesh p-MG。
2. 从 `checkpoint-1000` 在相同 exact `A/b` 上重建解，并直接计算 `r=b-Ax`。
3. basis 只能由物理 propagating + near-cutoff Floquet canonical inventory 预先确定；rank hard cap 为 32，禁止从 residual 拟合。
4. 先量测固定 basis 对 residual 的投影、可 deflatable work fraction、`P/P^H`、MPI identity 与附加内存；Gate 必须预先冻结，不扫描 rank、window 或 weights。
5. 只有诊断证明 plateau 主要落在该物理子空间，才在新 review/新 SHA/新 root 下实现一次 bounded correction。
6. 若解释不足，关闭 Floquet correction；后续候选应是 wave-aware domain decomposition，而不是重复运行普通正定 GenEO/BDDC。

V14 J6 本身仍为 `not_run_by_J5_eligibility`，没有任何新 proposal 被写成已授权实现或 PASS。
