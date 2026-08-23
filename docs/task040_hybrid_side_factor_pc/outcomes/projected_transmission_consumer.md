# V2-B projected transmission consumer

## 结论

V2-B 在冻结的 5 nm / 1° / phi=0 / S / p6h4 / M480 / MPI8 配置下完成了一次 fresh
packet consumer formal。它把 producer 保存的人工截面信息重新分发到当前 MPI owner，再构造
三组 projected transmission action，并运行同一套 physical zero-map、one-apply 和五源
right-FGMRES screen。这样可以直接检查“截面信息能否稳定传回三分区”，而不把 producer 的
诊断包或局部峰值误称为完整 Hybrid 结果。

独立 checker 重算后，身份、canonical remap、生命周期和资源证据通过；但五个非零 source
在 16 步后仍全部接近原始残差，未满足数值 Gate。因此最终分类是
`THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`，不是资源失败，也不是实现失败。

## 身份与证据

| 项目 | 值 |
|---|---|
| consumer source SHA | `40b25d3281d9ce1707f6069607bfdbbf6a3ab48d` |
| telemetry/checker fix SHA | `0919ed2fa3bd1541f543057721fff84fa110f3d4` |
| producer source SHA | `942c43881e4162085348c48b09c79fbbdac18cd9` |
| formal root | `results/task040_v2_projected_packet_consumer_mpi8_40b25d32` |
| process-sample wall | `1077.3351624270435 s`（raw timeline 最后一行） |
| packet manifest SHA256 | `19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0` |
| input / physical SHA256 | `4e60924b...f1811` / `8391d461...527c` |
| selected / probe / spool SHA256 | `2dddaf7a...3067` / `7a03b2cf...baad` / `a2a7fb6f...c0384` |
| RHS / exact-output loading | `6` RHS；`0` exact-output vectors；metadata/hash validation only |
| QEP / PDE | `0` / `not_run` |

完整 64 位身份值和 raw hash 见 [V2-G compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v2_projected_transmission_consumer_v1.json)。

## Canonical owner remap

producer 与 fresh consumer 的 DOLFINx owner 分区不同，所以 consumer 先按 canonical key
做小型 metadata 对齐，再用 numeric all-to-all 发送 owner-row U/V；没有把 FE 数值向量聚集到
rank0，也没有复制完整 basis。

| group | source local rows | target local rows | sent / received | global Gamma rows | span | roundtrip max |
|---|---:|---:|---:|---:|---:|---:|
| group0 | 1902 | 912 | 1902 / 912 | 7560 | 296 | 0 |
| group1 | 1902 | 1842 | 1902 / 1842 | 15120 | 776 | 0 |
| group2 | 0 | 930 | 0 / 930 | 7560 | 480 | 0 |

三组 source/target key bijection、local/collective roundtrip error 均通过；
`basis_global_replicated=false`、`numeric_allgather=false`、`fe_numeric_allgather=false`。

## One-apply 与 FGMRES

one-apply 的实现子集通过：physical source 是严格 zero-map，action identity、repeat、
linearity 和 factor inventory 均通过；apply 计数为 formal source/repeat/linearity
`6/6/1`，总 action delta 为 `13`。下表中的 `original rho` 和 `rho*` 是从 raw
`BHB/BHY/YHY` contractions 独立重算；它们不是 FGMRES 的最终 Gate。

| source | original rho | rho* | correlation magnitude |
|---|---:|---:|---:|
| modal+ | 22.245838903738115 | 0.9991091942837925 | 0.04219973812230144 |
| modal- | 23.852050340849885 | 0.999200083877325 | 0.039989903470087636 |
| external | 24.75394731434479 | 0.99926210606036 | 0.03840889730015213 |
| random0 | 22.552067871720634 | 0.9990697662027437 | 0.04312310586675284 |
| random1 | 22.454089855846412 | 0.9990604725869423 | 0.043337883131914334 |

五源 FGMRES 的 true residual 如下；checkpoint 0 是统一的 1.0：

| source | 4 | 8 | 16 |
|---|---:|---:|---:|
| modal+ | 0.9969577454690055 | 0.9956464719287812 | 0.9936534709381595 |
| modal- | 0.9985179851860166 | 0.9979287889899702 | 0.9964222027809813 |
| external | 0.9970453221588145 | 0.9957918044671856 | 0.9939467693618661 |
| random0 | 0.9978618914017243 | 0.9973369628027956 | 0.9963350357187821 |
| random1 | 0.9977513488058687 | 0.997255994079295 | 0.9964721803565209 |

所有 checkpoint finite，但五个 `r16` 都 `>=0.9`，所以 32 步没有授权；首个 preferred
checkpoint 为 `null`。这满足 Review 的停止条件：consumer 资源通过而 projected
transmission 的三分区 mode subspace/sweep 数值 Gate 未通过。没有调 beta、sign、sweep、ILU
或 mode span。

## 资源与生命周期

| 项目 | raw / 独立重算值 |
|---|---:|
| watchdog raw exit | natural exit, rc=0 |
| process-sample wall | `1077.3351624270435 s`（raw timeline 最后一行） |
| raw sample / authoritative / excluded | 2137 / 2136 / 1 |
| raw process-tree peak | `34,846,629,888 B = 32.453453064 GiB` |
| derived peak | 同上；与 summary 精确匹配 |
| PSS / USS | `not_recorded_not_available`；不从 RSS 推算 |
| swap | `0 B`；derived authority readable |
| hard line | `45 GiB`，未触发 |
| base / projected factors ready | `3 / 3` |
| cleanup 后 base / projected | `0 / 0` |
| simultaneous factor maximum | `3` |
| exact/full-side/global/nested | `0 / 0 / 0 / 0` |

这里的 `factor_count_ready=3` 与 `projected_inverse_factor_count=3` 是同一组三个 group
factor 的两种 inventory 视图，不是两套同时驻留的 3+3 个 factor；实际 simultaneous
maximum 始终为 `3`。

原始 watchdog summary 的 `all_status_readable=false` 和 `swap_authority_readable=false` 是
最后一个 cleanup-complete teardown sample 的退出竞态，不是运行中 unreadable sample。原始
timeline 保持不变；独立 legacy lifecycle recalculation 绑定其 timeline SHA，验证
`2137=2136+1`、此前 2136 行可读且 swap 为零、summary peak 匹配，才得到
`resource_pass=true`。原始 checker 输出没有被覆盖，原 raw 与独立重算文件都保留在 formal
root。

这里的资源结论只说明这个 staged consumer component 在 45 GiB 内完成。它不是完整
workflow saving tier，也不是 production side inverse 或 0.7 nm qualification。

## Gate 后边界

V2-C analytic mode-aware、V2-D bounded patch Level B、V2-E bottom/top/both/full Hybrid 和
V2-F h3 scaling 全部为 `not_run_by_gate`。本轮没有证明 bounded local patch 失败，也没有
证明 coarse space、完整 Hybrid 或 0.7 nm 不可行。若未来继续，下一轮应重新审议三分区之外
的 coarse、long-range 或 nonlocal transmission mechanism，而不是继续调当前 beta、sweep、
ILU 或 selected span。

## Evidence

- [consumer run summary](../../../results/task040_v2_projected_packet_consumer_mpi8_40b25d32/worker/run_summary.json)
- [watchdog summary](../../../results/task040_v2_projected_packet_consumer_mpi8_40b25d32/watchdog_summary.json)
- [immutable checker output](../../../results/task040_v2_projected_packet_consumer_mpi8_40b25d32/checker_recomputed.json)
- [legacy lifecycle recalculation](../../../results/task040_v2_projected_packet_consumer_mpi8_40b25d32/checker_recomputed_legacy_lifecycle.json)
- [memory stage markers](../../../results/task040_v2_projected_packet_consumer_mpi8_40b25d32/memory_stage_markers.raw.jsonl)
- [memory stages](../../../results/task040_v2_projected_packet_consumer_mpi8_40b25d32/memory_stages.jsonl)
- [worker stdout](../../../results/task040_v2_projected_packet_consumer_mpi8_40b25d32/worker_stdout.txt)
- [producer packet outcome](interface_schur_packet_producer.md)
