# Task035c Response V1：逐通道与高阶内存闭合

## 1. 集中结论

```text
response_status = HYBRID_CHANNEL_AND_MEMORY_CLOSURE_SUCCESS
review = Task035b review_report_v4.md + Task035c task.md
branch = codex/20260726-task35c-hybrid-channel-memory-closure
numerical_source = 244b62e1fb4f299a468363cf90a2dd548dc34ff6
formal_MPI = 8
p2_h5_root_cause = closed
p6_h10_six_paths = complete
significant_powers = 12/12
significant_boundary_plane_complex_amplitudes = 12/12
static_hybrid_M120_peak_reduction = 31.8919%
static_hybrid_M160_peak_reduction = 29.4977%
mandatory_15pct_memory_gate = pass
preferred_25pct_memory_gate = pass
user_50pct_memory_target = not_achieved
user_50pct_memory_target_status = open_engineering_gap
pss_uss_backfill = qualified_from_original_mpi8_smaps_rollup
pss_uss_inferred_from_rss = false
formal_relative_memory_authority = simultaneous_process_tree_live_worker_rss
modal_time_hard_gate = removed_by_user
ordinary_default = standard_full
ordinary_default_changed = false
p3_h7p5 = out_of_scope_by_user / not_run
```

Task035c 已关闭 Task035b 留下的逐通道根因：旧 Hybrid 中间段使用连续
QEP相位和traction，而Full3D在z方向使用scalar CG(p)有限元链的离散相位和
离散端点导数。两个符号统一后，p2/h5和正式p6/h10均达到12/12功率与
12/12 physical-boundary-plane复振幅。

static Hybrid也取得实测高阶资源正结果。M120/M160峰值分别下降31.89%和
29.50%，通过Review的15% mandatory、25% preferred和1.35×总时间Gate。
但用户希望的50%没有达到；这部分明确保留为工程缺口。

Task035c 原始 MPI8 timeline 实际保存了逐 rank
`/proc/<pid>/smaps_rollup`。本次只重建 compact PSS/USS ledger，没有重跑
PDE，也没有从 RSS 推算：只有 rank 0–7 在同一采样时刻全部可读的样本才参与
峰值。M120 standard/static 的 PSS 为 `9.440656/5.769862 GiB`
（下降 `38.8828%`），USS 为 `9.200600/5.491413 GiB`
（下降 `40.3146%`）。正式 Task035c 相对内存 Gate 仍以原 campaign 的
simultaneous live-worker RSS 为 authority。

## 2. Review执行矩阵

| Review / task要求 | 实际执行 | 结论 |
|---|---|---|
| p2/h5先定位 | trace rank、M判别、Full3D trace oracle、phase-only和traction组合 | root cause closed |
| p6/h10正式六路 | Full3D standard/static；Hybrid standard/static M120/M160，全部MPI8 | complete |
| p3/h7.5不得运行 | 0 PDE | compliant |
| 12/12 powers + amplitudes | reference-v1 boundary-plane checker独立重算 | pass |
| R/T/A/Avolume/residual/field | 六路径完整保存 | pass |
| static Hybrid peak至少15% | M120 31.89%，M160 29.50% | pass |
| total <=1.35× | M120 0.3426×，M160 0.3881× | pass |
| modal time | 用户取消硬限制；仍报告1.0757×/1.0763× | report-only |
| 至少合理的rank点 | MPI1、MPI2、MPI8；前两点出现两个独立负信号 | lane stopped，MPI4 not run |
| 负证据保留 | p6约束、roundoff、launcher、MPI1/2记录均保留 | complete |
| ordinary default | `standard_full` | unchanged |

## 3. 高阶主结果

| path | rows | matrix/factor NNZ | peak | total | physical status |
|---|---:|---:|---:|---:|---|
| Full3D standard | 173,882 | 210,353,168 / 438,050,956 | 34.041210 GiB | 2581.549788 s | 12/12+12/12，all gates |
| Full3D static | 51,272 | 41,989,040 / 212,343,992 | 14.721756 GiB | 260.736180 s | 12/12+12/12，all gates |
| Hybrid standard M120 | 52,292 | 60,434,236 / 141,010,528 | 11.076893 GiB | 942.026047 s | 12/12+12/12，all gates |
| Hybrid static M120 | 17,168 | 12,313,232 / 45,293,792 | 7.544262 GiB | 322.781788 s | selected；12/12+12/12 |
| Hybrid standard M160 | 52,372 | 60,434,236 / 141,010,528 | 11.247025 GiB | 1014.706182 s | 12/12+12/12，all gates |
| Hybrid static M160 | 17,248 | 12,313,232 / 45,293,792 | 7.929413 GiB | 393.840814 s | 12/12+12/12；costlier |

M120→M160最大逐通道相对差仍低于`2e-10`，没有M240信号。M160相对M120
峰值增加5.11%、coupling增加38.91%、总时间增加22.01%，因此选择M120。

## 4. 50%内存目标为何未达到

M120 static的modal-coupling stage peak约5.756 GiB，最终peak为7.544 GiB。
最高点出现在`record_and_release`，此时local factor/native solver objects、
field recovery、middle-plane samples和record builder仍共存。因此当前缺口
主要是对象生命周期，不是modal Schur本身，也不是只需继续减少rows即可解决。

下一步如获授权，优先做：

1. factor/KSP在compact observables生成后立即销毁；
2. middle field逐plane、逐mode streaming；
3. incremental record serialization；
4. per-rank PSS/USS和native-object release ledger；
5. QEP/projection cache分批驻留。

当前结果不能写成Hybrid内存理论下限。

M120的50%阈值为`5.538446 GiB`，而static路径在后处理前的coupling和
factor/Schur阶段已经分别达到`5.756237/6.817 GiB`。因此仅提前销毁
record/postprocess对象不能达到50%；必须重构coupling分块驻留和上下factor
错峰生命周期。该改动会改变正式资源路径，并要求六路同源码重跑。本轮没有以
简单`del/gc`为理由重复整批heavy authority。

## 5. Rank lane

MPI1的Full3D static通过，但Hybrid positive QEP biorthogonality为
`1.1975997613e-6 > 1e-6`；MPI2的Hybrid numerical chain通过，但worker
退出时资源sampler发生terminal-drain race，`3.141788 GiB`不能提升为formal
authority。两个连续成本/数值负信号后关闭lane，不运行MPI4。MPI8继续作为本轮
正式authority。

## 6. 实现与证据

主要实现：

- scalar-CG discrete propagation/traction opt-in；
- p1–p6 exact cross-section Floquet constraints；
- scale-aware、slave/interior分离的static trace audit；
- p6 source/reference/preflight gates；
- channel/resource independent checker；
- Case096 compact evidence generator与hermetic tests。

正式适用范围限于 fixed rectangular block grating、structured tensor-product
mesh、axis-aligned first-order affine hexahedra、modal middle region 均匀 z
分段、单一 axial h、p1–p6、complex128、Floquet、sparse auxiliary DtN 以及
direct standard/static Full3D/Hybrid。nonuniform z、local-h/hanging hexa、
curved/distorted/high-order geometry、tetra/mixed mesh、不规则几何和
production automatic hp adaptivity 均未资格化；离散 phase/traction 端口对此
必须 fail closed。

权威证据：

- [`outcomes/summary.md`](outcomes/summary.md)
- [`outcomes/p6_h10_channel_closure.md`](outcomes/p6_h10_channel_closure.md)
- [`outcomes/object_lifecycle_and_rank_study.md`](outcomes/object_lifecycle_and_rank_study.md)
- [`outcomes/dependency_failures.md`](outcomes/dependency_failures.md)
- [`outcomes/test_summary.md`](outcomes/test_summary.md)
- [`../../benchmarks/cases/096_hybrid_channel_memory_closure/README.md`](../../benchmarks/cases/096_hybrid_channel_memory_closure/README.md)

最终本地closeout：

```text
Task035c focused = 29 passed
documentation + Case096 = 19 passed
Task034 numerical-blob hardening = 13 passed
full repository = 616 passed, 28 skipped in 452.07 s
Case096 raw regeneration = pass
Ruff / compileall / JSON parse / git diff --check = pass
```

没有修改ordinary default，没有运行p3/h7.5、h13 adaptive、0.7nm、不规则
几何、tetra/mixed static、production selective trace或新iterative profile。
Review V2 已授权在 M0–M4 完成后选择性整合到 master；本 response 中的数值
结论仍绑定 `244b62e1...`，文档、PSS/USS compact 回填和 manifest 不改变该
numerical authority。

## 7. Review V2 M0–M4 receipt

```text
task035c_closeout_source = 900260556ba9a74bc631e8295b08fc1487bd5abc
integration_base = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
task035c_manifest_files = 69
integration_hygiene_files = 1
final_selective_diff_files = 70
focused_serial = 180 passed, 10 skipped
mpi2_components = 21 passed per rank
mpi8_components = 17 passed, 4 skipped per rank
full_repository = 619 passed, 28 skipped
tracked_json = 898 parse pass
numerical_blob_checker = pass
task035c_authority_kernel_blobs = 10/10 byte-identical
p6_h10_heavy_pde_rerun = no
```

额外 1 个 integration hygiene file 只删除 Case095 复现命令中对历史
`do_not_merge` 测试的陈旧引用，不涉及 numerical kernel。最终 master SHA
由 fast-forward 和远程 push 成功后在 Git handoff 中报告，不在提交内自引用。
