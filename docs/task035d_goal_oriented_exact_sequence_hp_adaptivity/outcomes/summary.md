# Task035d Outcomes Summary

## 1. 集中结论

```text
task = Task035d
classification = PARTIAL_WITH_CONTROLLED_NEGATIVES
branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
branch_base = 9c2160d41382026352908d692ad479dc4508424d
formal_MPI = 8
geometry = Task034 fixed rectangular block grating
ordinary_default = unchanged
true_local_p = structurally and numerically implemented
true_local_h = structurally and numerically implemented
complete_combined_hp_accuracy = failed
production_hp_candidate = none
hybrid_phase_f = not_run_full3d_hp_gate_failed
```

Task035d 建立了同一 exact-sequence 离散架构中的真实 local-p 和 true
local-h。inactive p6 mode、hanging slave 和 Floquet slave 均不生成 global
row；局部细化使用 2:1 balanced axis-aligned affine hexa，H(curl) coarse/fine
切向约束与 H1 gradient commuting，并与 cell-interior static condensation、
DtN、完整场恢复和 MPI owner routing 组合。

资源压缩是真实且显著的。最小正式候选为 `76,205` active FE DoF、
`18,470` direct rows、`7.29866 GiB`；相对 p6/h10 static，rows、matrix
NNZ、factor NNZ 和 peak 分别下降 `63.98%/75.74%/85.46%/50.42%`。
最终 bounded left-grating 判别点也达到 `45.24%` peak reduction，并通过
exact-sequence、MPI、true residual 和资源 Gate。

但没有任何正式候选达到冻结的 `12/12 significant powers + 12/12
physical-boundary complex amplitudes`。最佳计数为 h15 top-air local-h 的
`6/12 + 6/12`；最终 left-grating 为 `4/12 + 6/12`。因此不能宣称
goal-oriented combined-hp success，也不能接入 Hybrid 给失败的 Full3D
候选补精度信用。

## 2. 任务书执行矩阵

| Phase / Gate | 实际完成 | 状态 |
|---|---|---|
| Phase 0 baseline | Case095/096 reference-v1、p6/h10 static、12通道和 M120 identity 冻结 | pass |
| Phase A active-space authority | p4/p5/p6 entity DoF、exact sequence、active expansion、local Schur、serial/MPI2 fixture | pass |
| Phase B true local-p | entity-degree map、真实减行、T30 与 physics-guard MPI8 PDE | capability pass；accuracy negative |
| Phase C true local-h | dyadic split、2:1/material/periodic closure、H(curl) hanging、compiled tensor、PETSc ownership、MPI1/2/8、MPI8 PDE | capability pass；accuracy negative |
| Phase D multi-goal | 36-real-goal nested-p DWR、36-goal selective-trace DWR、factorial attribution、cost-normalized location oracle | partial；actual local-h DWR unavailable |
| Phase E h/p decision | manual bounded discriminator sequence；stop rules applied | partial；automatic cycles 1–4 not completed |
| Phase F Hybrid M120 | Full3D hp Gate prerequisite failed | not run |
| ordinary default | standard production paths unchanged | pass |
| out-of-scope | irregular geometry、tetra static、mixed mesh、iterative、matrix-free、0.7 nm | not run |

## 3. 结构能力与受控实现失败

| 能力 | 权威结果 | 结论 |
|---|---|---|
| reference exact sequence | p4/p5/p6 与全部合法 edge/face/cell degree triples；`curl(grad)`、rank/nullity、orientation | pass |
| true local-p | inactive higher-order modes 不编号、不进入 NNZ/factor | pass |
| true local-h | 2-cell fixture `2→9` leaves，而 coordinate-plane control 为 12；physical exterior identity 完整 | pass |
| hanging restriction | p4/p5/p6 coarse-to-four-fine blocks `144×40 / 220×60 / 312×84`，full-rank/commuting | pass |
| D4 orientation | 6 hexa faces；每阶 `4×8×8=256` child/orientation combinations | pass |
| periodic+hanging | nontrivial x/y Floquet phase、corner closure、flattened chain、no slave row | pass |
| MPI identity | component 与 production authorities 均覆盖 MPI1/2/8 | pass |
| MPI2 owner routing | 首次 production integration 不完整 | preserved controlled failure；fixed |
| local-h field location | 首次 checker 不能唯一定位局部边界点 | preserved evidence failure；fixed without relaxing Gate |
| complete hp physics | 无 12/12+12/12 候选 | failed |

受控失败证据没有删除：

```text
records/local_h_production_mpi2_v3_integration_controlled_failure.json
records/h15_top_air_local_h_field_probe_evidence_failure_v1.json
records/h15_symmetric_top_air_remote_p5_interior_mpi8_residual_controlled_negative_v1.json
records/h15_left_grating_top_closure_p5fine_compact_checker_evidence_failure_v1.json
```

最后一项是证据完整性 fail-closed：在 full checker record 尚未 tracked 时，
compact generator 拒绝生成正式 compact。先提交 full record 后重新生成，
没有覆盖或删除失败证据。

## 4. 正式模型统一结果

p6/h10 static reference 是 best available discrete authority，不是 continuum
truth。所有 Task035d candidate 都是 MPI8 direct MUMPS、zero swap。

| Model | active FE DoF / rows | matrix / factor NNZ | residual | peak / total | R00 / R / T / Aclosure | power / amplitude | fields | status |
|---|---:|---:|---:|---:|---|---:|---|---|
| p6/h10 static reference | `173,802 / 51,272` | `41,989,040 / 212,343,992` | `3.092e-11` | `14.72176 GiB / 260.736 s` | `0.000753761 / 0.000762881 / 0.602701634 / 0.396535485` | `12/12 / 12/12` | pass | reference |
| T30 p-only | `87,600 / 28,990` | `15,253,176 / 63,564,300` | `1.410e-11` | `10.09287 GiB / 426.864 s` | `0.001023001 / 0.001034441 / 0.599801088 / 0.399164471` | `0/12 / 0/12` | fail | controlled negative |
| sidewall-z0 guard p-only | `89,870 / 31,064` | `16,490,572 / 76,721,484` | `7.559e-12` | `8.38265 GiB / 246.377 s` | `0.000875049 / 0.000884463 / 0.600835932 / 0.398279604` | `1/12 / 0/12` | fail | controlled negative |
| h15 top-air local-h | `82,925 / 18,470` | `10,186,108 / 30,865,200` | `5.740e-12` | `7.50068 GiB / 202.762 s` | `0.000756032 / 0.000765167 / 0.602685062 / 0.396549771` | `6/12 / 6/12` | pass | controlled negative |
| symmetric h + remote p5 interior | `84,240 / 20,060` | `11,176,430 / 32,658,700` | `2.124e-11` | `7.50883 GiB / 208.766 s` | `0.000758939 / 0.000768102 / 0.602613629 / 0.396618269` | `4/12 / 4/12` | pass | controlled negative |
| top-air h + remote p5 bridge | `76,205 / 18,470` | `10,186,108 / 30,865,200` | `3.433e-12` | `7.29866 GiB / 198.400 s` | `0.000758796 / 0.000767954 / 0.602613705 / 0.396618341` | `4/12 / 4/12` | pass | controlled negative |
| ten-face selective p6 trace | `83,125 / 18,670` | `10,406,108 / 32,683,000` | `1.287e-11` | `8.06898 GiB / 279.206 s` | `0.000753670 / 0.000762781 / 0.602686341 / 0.396550878` | `5/12 / 6/12` | pass | controlled negative |
| left-grating single-root | `88,915 / 21,650` | `12,382,332 / 37,250,750` | `3.267e-11` | `8.06120 GiB / 297.114 s` | `0.000755219 / 0.000764350 / 0.602685529 / 0.396550122` | `4/12 / 6/12` | volume max fail | controlled negative |

`total` 是 solver summary 的 elapsed time。`base matrix assembly` 和
`total build` 等内部计时有嵌套，不相加。最终 left-grating 的 base matrix
assembly、reported total build、MUMPS setup、backsolve 分别为
`256.515 / 68.972 / 13.524 / 0.041 s`。

### 4.1 任务书 §3.2 控制组统一对照

下表把历史控制与本任务候选放在同一账面中。`Task035 DWR` 使用 tetra
fixed-reference observable error，不具备 Case095 reference-v1 的 12 通道
口径；global p5 的 selected authority 也没有单独保存逐通道计数和单模型
process-tree peak。因此这两行只作控制，不把缺失字段推断为通过。

| Control / candidate | space / mesh | FE DoF / rows | matrix / factor NNZ | peak | power / amplitude | decision / authority |
|---|---|---:|---:|---:|---:|---|
| global p6/h10 reference | global p6，structured h10 | `173,802 / 51,272` | `41,989,040 / 212,343,992` | `14.72176 GiB` | `12/12 / 12/12` | best available discrete reference |
| global p5 same-mesh control | global p5，structured h10 | `101,815 / 35,000` | `20,140,928 / 101,062,900` | not separately recorded | historical 12-channel count not recorded | Task035b same-mesh p-control |
| Task035 DWR representative | p4→p5 tetra，theta `0.7`，one local-h cycle | `106,355 / not recorded` | not recorded | `8.080 GiB` | not evaluated in Case095 12-channel Gate | fixed-reference error `0.000538286`；Pareto, not same-error |
| Task035b fixed h15 | p5 trace / p6 interior，directional-z h15 | `74,890 / 16,880` | `9,195,812 / 27,916,600` | `5.803 GiB` | `6/12 / 7/12` | controlled negative |
| Task035b fixed h14 | p5 trace / p6 interior，directional-z h14 | `82,315 / 18,500` | `10,104,512 / 31,347,000` | `6.376 GiB` | `7/12 / 9/12` | positive z signal；controlled negative |
| Task035b fixed h13 | p5 trace / p6 interior，directional-z h13 | `89,740 / 20,120` | `11,013,212 / 36,273,200` | `6.411 GiB` | `10/12 / 10/12` | budget-in historical best；controlled negative |
| Task035d p-only best | sidewall-z0 guard | `89,870 / 31,064` | `16,490,572 / 76,721,484` | `8.38265 GiB` | `1/12 / 0/12` | controlled negative |
| Task035d h-only best | h15 top-air local-h；p6 interior | `82,925 / 18,470` | `10,186,108 / 30,865,200` | `7.50068 GiB` | `6/12 / 6/12` | strongest Task035d channel count；controlled negative |
| Task035d combined resource best | top-air h + remote p5 bridge | `76,205 / 18,470` | `10,186,108 / 30,865,200` | `7.29866 GiB` | `4/12 / 4/12` | resource best；no combined-hp accuracy credit |
| Task035d final discriminator | left-grating single-root；fine-child p5 | `88,915 / 21,650` | `12,382,332 / 37,250,750` | `8.06120 GiB` | `4/12 / 6/12` | volume max fail；controlled negative |

Task035d combined resource best 比 h-only best 少 `6,720` FE DoF、峰值低
`0.20202 GiB`，但通道从 `6/12 + 6/12` 退化到 `4/12 + 4/12`。因此它
没有满足“同精度下 hp 组合具有额外价值”的任务条件。

## 5. 资源压缩

| Candidate | rows reduction | matrix NNZ reduction | factor NNZ reduction | peak reduction | mandatory / preferred |
|---|---:|---:|---:|---:|---|
| T30 | `43.4584%` | `63.6734%` | `70.0654%` | `31.4425%` | mandatory pass |
| sidewall-z0 guard | `39.4133%` | `60.7265%` | `63.8692%` | `43.0595%` | preferred pass |
| h15 top-air local-h | `63.9764%` | `75.7410%` | `85.4645%` | `49.0504%` | preferred pass |
| symmetric h + p-down | `60.8753%` | `73.3825%` | `84.6199%` | `48.9950%` | preferred pass |
| factorial bridge | `63.9764%` | `75.7410%` | `85.4645%` | `50.4227%` | preferred pass |
| ten-face selective trace | `63.5864%` | `75.2171%` | `84.6085%` | `45.1901%` | preferred pass |
| left-grating | `57.7742%` | `70.5106%` | `82.4574%` | `45.2430%` | preferred pass |

所有候选均满足 `<=90,000` mandatory DoF。没有候选进入 `65,000–75,000`
preferred band；最接近的是 `76,205`，但它本身仅 `4/12 + 4/12`，不能用
DoF 接近 preferred band 掩盖精度失败。

最终 left-grating 的同一 timeline 遥测：

```text
process-tree peak authority = 8.061199188 GiB
simultaneous worker PSS peak = 6.926573753 GiB
simultaneous worker USS peak = 6.777557373 GiB
fully readable MPI8 smaps samples = 1008
swap = 0
```

container cgroup 不是 dedicated job cgroup，所以只保留诊断账本，不覆盖
simultaneous process-tree authority。

## 6. 物理 Gate 与失败通道

### 6.1 标量、能量和场

| Candidate | normalized R/T/Aclosure L2 | Avolume status | volume rel-L2 / max | interface rel-L2 / max |
|---|---:|---|---|---|
| T30 | `21.2138` fail | fail | `9.3372% / 0.11852` fail | `9.8836% / 0.11751` fail |
| sidewall-z0 guard | `13.2713` fail | fail | `3.7330% / 0.06308` fail | `4.0155% / 0.06036` fail |
| h15 top-air local-h | `0.129685` pass | pass | `1.1392% / 0.01771` pass | `0.8081% / 0.01751` pass |
| symmetric h + p-down | `0.623569` pass | pass | `1.1445% / 0.01927` pass | `0.8400% / 0.01748` pass |
| factorial bridge | `0.622427` pass | pass | `1.1446% / 0.01927` pass | `0.8401% / 0.01747` pass |
| ten-face selective trace | `0.108716` pass | pass | `1.1390% / 0.01766` pass | `0.8055% / 0.01766` pass |
| left-grating | `0.117446` pass | pass | `1.2294% / 0.04689` max fail | `0.7888% / 0.02209` pass |

left-grating 的 volume max tolerance 是 `0.04102079`，实测
`0.04688675`。其 `Aclosure-Avolume = 6.9983e-13`，能量闭合通过。

### 6.2 所有失败通道的身份

下表列出每个新 local-h/hp candidate 的全部失败通道，并给出最大超限项的
实际 error/tolerance；逐通道完整值在对应 compact/full checker 中。

| Candidate | power failures | amplitude failures | 最大 power error/tol | 最大 amplitude error/tol |
|---|---|---|---:|---:|
| h15 top-air local-h | bottom `-5,-4,-2`；top `-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `2.333561e-8 / 5.251003e-10` | bottom -4 `1.589564e-5 / 2.541658e-6` |
| symmetric h + p-down | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-1` | bottom -7 `1.008269e-7 / 2.158694e-9` | top -7 `2.285933e-5 / 7.995039e-7` |
| factorial bridge | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-1` | bottom -7 `9.977858e-8 / 2.158694e-9` | top -7 `2.371900e-5 / 7.995039e-7` |
| ten-face selective trace | bottom `-7,-5,-4`；top `-7,-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `2.221993e-8 / 5.251003e-10` | bottom -4 `2.051506e-5 / 2.541658e-6` |
| left-grating | bottom `-7,-5,-4,-2`；top `-7,-5,-4,-2` | bottom `-5,-4,-2`；top `-7,-5,-4` | bottom -4 `1.204267e-8 / 5.251003e-10` | top -4 `1.087300e-5 / 1.881525e-6` |

T30 和 sidewall-z0 guard 的 12 行完整 error/tolerance 表已保存在 Case097
README 与各 compact record；T30 为 `0/12 + 0/12`，guard 只有
`top(-1,0)` power 通过、全部 amplitude 失败。

### 6.3 Final left-grating 逐通道

| side/order | power error / tolerance | amplitude error / tolerance |
|---|---:|---:|
| bottom -7 | `5.617175e-9 / 2.158694e-9` fail | `2.550563e-6 / 1.216565e-5` pass |
| bottom -5 | `6.906912e-9 / 3.891273e-10` fail | `4.459072e-6 / 1.280646e-6` fail |
| bottom -4 | `1.204267e-8 / 5.251003e-10` fail | `1.418775e-5 / 2.541658e-6` fail |
| bottom -2 | `1.284216e-8 / 4.651045e-9` fail | `7.478303e-6 / 4.580806e-6` fail |
| bottom -1 | `1.638713e-8 / 1.114414e-7` pass | `4.142307e-6 / 1.272899e-5` pass |
| bottom 0 | `1.609820e-5 / 2.175766e-4` pass | `5.003714e-4 / 6.779629e-3` pass |
| top -7 | `2.836735e-9 / 1.249444e-9` fail | `1.978697e-6 / 7.995039e-7` fail |
| top -5 | `2.914386e-9 / 1.194302e-9` fail | `2.376892e-6 / 1.113206e-6` fail |
| top -4 | `5.355565e-9 / 1.086492e-9` fail | `1.087300e-5 / 1.881525e-6` fail |
| top -2 | `4.439407e-9 / 1.242282e-9` fail | `1.125110e-6 / 3.186491e-6` pass |
| top -1 | `1.114167e-8 / 5.111835e-8` pass | `3.256777e-6 / 7.413384e-6` pass |
| top 0 | `1.457720e-6 / 3.195287e-5` pass | `4.510204e-5 / 8.330267e-4` pass |

## 7. DWR、h/p 分类与信用边界

| Evidence | 实际证明 | 不允许声称 |
|---|---|---|
| nested-p DWR | 12 unit-channel / 36 real-goal residual closure；periodic p-down pair audit | 远端 p-down 安全 |
| periodic p-down audit | 16 对中 conservative budget 下无一 eligible；最大 endpoint delta `46.316×tol` | 继续 p-down 扫描 |
| selective-face DWR | independent checker `36/36` goal closure，十面 contribution 可重算 | 十面物理 endpoint 成功 |
| factorial bridge | local-h 与 remote-p5 的实际三点归因 | combined hp 获得精度信用 |
| bounded selection v2 | compact-DWR location oracle、完整 available single-root catalog、cost normalization | actual local-h DWR surplus |
| left-grating formal run | selected action 的真实结构、资源与物理结果 | goal-oriented selection success |

selective-face 首次 embedded checker 误把 semantic hashes 与 transfer-content
hashes 比较；独立 checker 修复后 `36/36` 通过，数值 kernel 未变。由于十面
是在 coarse/enriched endpoint 已知后做 attribution，
`posthoc_actual_action_attribution=true`，但
`goal_oriented_selection_credit=false`。

bounded single-root selection 明确保存：

```text
compact_dwr_location_oracle = true
actual_local_h_dwr_surplus = false
actual_channel_dwr = false
success_forecast = false
goal_oriented_selection_credit = false
complete_combined_hp_credit = false
```

## 8. Lane closure 与未运行项

| Lane / item | final status | 原因 |
|---|---|---|
| p-only | closed controlled negative | T30、guard 连续两个正式精度负信号 |
| remote p5 interior | closed controlled negative | combined 与 factorial 均从 6/12+6/12 退化到 4/12+4/12 |
| frozen ten-face selective trace | closed controlled negative | measured 5/12+6/12；32 subsets 无 12/12+12/12 预测 |
| whole top-port selective trace | incomplete not run | 其他 faces/orbits/edge modes 未被十面子集证伪 |
| bounded single-root top-air local-h | closed after two formal accuracy negatives | top-air 6/12+6/12；left-grating 4/12+6/12 |
| outer-periodic | not run by lane stop | oracle 比失败的 left-grating 更弱；不是 PDE failure |
| multi-seed | not evaluated by stop rule | 单 root lane 已关闭 |
| automatic cycles 1–4 | not completed | 没有 per-cycle authority；manual discriminator 不冒充 automatic loop |
| Hybrid M120/M160 | not run | Full3D hp Gate failed |

lane closure authority：

```text
benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/
  bounded_single_root_top_air_lane_closure_v1.json
```

重新开放该研究必须先在新 candidate space 上生成 actual per-channel local-h
或 trace-orbit DWR，再授权一个判别点。当前证据不支持 outer 或大量组合盲扫。

## 9. Evidence index

| 证据 | SHA256 / identity | 用途 |
|---|---|---|
| `reference_active_space_authority_v1.json` | manifest-bound | Phase A exact sequence |
| `local_h_attempt1_mpi_identity_v1.json` | `d341ad69...fe44` | dyadic/hanging/Floquet MPI identity |
| `local_h_attempt2_mpi_identity_v3.json` | record-bound | compiled tensor/action identity |
| `local_h_production_mpi_identity_v3_owner_gate_fix2.json` | record-bound | PETSc owner routing |
| `h15_top_air_local_h_nested_p_mpi8_controlled_negative_v2.json` | `9d4011e9...fa01` | first formal local-h negative |
| `h15_top_air_nested_p_dwr_mpi8_checker_v2.json` | raw report `86d8e482...eba` | 36-goal nested-p DWR |
| `hp_factorial_bridge_attribution_v1.json` | record-bound | h/p factorial lane closure |
| `selective_face_selection_compact_v1.json` | `3b843bba...4bc` | ten-face DWR and subset closure |
| `bounded_single_seed_top_air_hp_selection_v2.json` | `828d6db4...a23` | bounded action selection |
| `h15_left_grating_top_closure_p5fine_plan_v1.json` | `08e33b54...393` | final plan |
| `left_grating_top_closure_p5fine_mpi_identity_v1.json` | `ab6d4ab7...bd8` | MPI1/2/8 identity |
| final watchdog | `7d4c7a1...7165` | raw resource/numerical authority |
| final full checker | `1b9dd3cd...2492` | full physics and resource audit |
| final compact checker | `d6e03061...4225` | tracked controlled negative |

完整复现命令和 raw artifact paths 见 Case097 README。ignored VTU、timeline、
matrix/factor 和 stdout artifacts 未提交到 Git；tracked records 保存其 SHA。

## 10. 测试与收口回归

| Gate | Result |
|---|---|
| Task035d focused serial | `215 passed, 13 skipped` |
| MPI2 components | `80 passed, 10 skipped` |
| MPI8 representative | each rank `16 passed, 4 skipped` |
| affected Task032/033/035b Hybrid | pass |
| documentation contract | `14 passed` |
| full repository | `837 passed, 41 skipped` |
| Case097 / registry / Ruff / compileall / JSON / diff-check | pass |

第一次 full repository 发现 Hybrid 调用点没有向已要求 collective
communicator 的 `_combine_owned_entries` 传递 `comm`，以及 Case097 没有进入
active-research documentation contract。补齐两个 `comm=comm` 和 Case097
专属 config assertions 后，针对性与全库回归均通过。Task035d 正式 Full3D
PDE 不走该 Hybrid 路径，因此没有重跑 heavy PDE；Task035c 历史 records
仍绑定其原 numerical SHA。

## 11. 最终分类

```text
Task035d = PARTIAL_WITH_CONTROLLED_NEGATIVES
production_hp_candidate = none
complete_hp_success = false
ordinary_default_changed = false
master_merge = not_authorized_by_task
```

Task035d 的可复用产出是 exact-sequence variable-p/local-h 数值架构、MPI
owner routing、完整 residual/recovery、36-goal adjoint/DWR checker 和
fail-closed action-selection contract。其研究负结果同样是结论：在当前
p6/h10 reference Gate 下，仅靠这些 p5-trace、single-root local-h、
remote-interior p-down 和十面 selective-trace 动作不能恢复所有弱衍射通道。
