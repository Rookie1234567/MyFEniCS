# Task041 最终证据响应 v1

本响应以文档收口基线 746c0ffdc3a7a18eb80dde8d93bb3b7c660c65af 记录可复核的轻量结果。原始 packet、marker、telemetry 和失败 root 均保留在 ignored results 目录；本文件不把 candidate 提升为 official。

## 最终结论

最终状态为 3NM_COMPLETED_NOT_GRID_CONVERGED。3 nm p6/h3 的 M800 与 M1200 都完成了求解和 recovery mechanics，但各自 own physics Gate 都失败：

| case | 结论 | 关键数值 |
|---|---|---|
| M800 consumer-only retry | candidate physics negative | abs(A_balance-A_volume)=1.9160032445286745e-5 > 1e-5 |
| M1200 consumer-only retry | candidate physics negative | abs(A_balance-A_volume)=1.8704745773062692e-5 > 1e-5 |

因此没有合法的 M-convergence pair，不能选择最小合格 M，也不能把相近的 R/T/A 标量解释为 physics pass。M1600、3 nm h2.5/h2、全部 2 nm 和后续 MPI1 均未运行；原任务 §12.2 的停止边界仍有效。M1200 是用户后来批准的受控续跑，不会追溯改变 M800 的 negative 结论。merge approval: NO。

## 3 nm 证据

### M800

20260907T111441.388055Z 是 fresh producer+consumer attempt，最终在 consumer_exit(solution_snapshot_destroyed) 以 IMPLEMENTATION_FAILURE 结束。它不是 formal authority；但 marker 中有独立 diagnostic solve checkpoint：reported/global/bottom/modal/top residual =
7.246419845266236e-10 / 6.711767430501667e-10 / 6.842952026951734e-12 / 7.252171978674087e-11 / 6.339676899706935e-10。consumer summary 的 formal_result/gates/physics 仍为 null，不能升级为 formal 或 physics pass。

producer/consumer/workflow wall 分别为 18000.658898 / 22215.056788 / 40216.175178 s；对应 producer RSS/PSS/USS 为 16.784275055 / 15.785678864 / 15.674812317 GiB，workflow RSS/PSS/USS 为 255.465618134 / 253.694432259 / 253.435222626 GiB，swap 为 0。bottom/top corrected factor NNZ 为 3.259e9 / 3.716e9，MUMPS factor-only、ICNTL14=40。

20260908T001027.090767Z 是复用该 packet 的 consumer-only retry，不是新的 producer+consumer workflow。它的 solve/recovery mechanics 通过，但 authority 为 measured_candidate_physics_negative，official RTA 和 canonical/grid authority withheld。候选 R/T/A/A_volume =
0.8048686830648746 / 0.0002839834330554354 / 0.19484733350206998 / 0.19486649353451532；residual reported/global/bottom/modal/top =
1.0614289127347946e-09 / 1.3530838051427825e-09 / 9.525482983090863e-12 / 5.059125745287973e-11 / 1.278144562727163e-9，均低于 5e-9。其 cgroup/process diagnostic peak 为 229028663296 B = 213.299564362 GiB，wall 17047.323762 s，swap 0；direct memory_stages PSS/USS 不存在，故不猜。

### M1200

producer root 为 results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260908T083844.269710Z/producer。它完成了 positive/negative 1200/1200 delivered packet，packet pass=true；manifest SHA 为 c7a36ab977e5fc11505ad27a6e8044fc9e909b42fd37a8ea1abeb72b6e49d71b，packet identity canonical SHA 为 cef2de437f0b0a247791acc8e4b865d1fd51082b181617ab6621cb9a95ba5d00，packet directory bytes 1370082162，write max-rank 1.167526111 s。source=c3a5bf4a424405c1f1de5cd6ac96be8db576f7b3。producer wrapper 仍有 terminal sample race，所以这是可复用 packet 证据，不是完整 supervisor PASS。

producer compute wall 15386.145391 s；assembly/positive-right/positive-adjoint/negative-right/negative-adjoint/reciprocal-pairing 分别为 1.063395 / 3329.204712 / 4214.234450 / 3512.904907 / 4243.992494 / 81.190811 s。这些是 raw diagnostic measured timing。parent telemetry 的 producer RSS/PSS/USS peak 为 28.318450928 / 27.452210427 / 27.341518402 GiB，swap 0。

consumer-only retry source 为 c72b3e0d1540a5a891f5906fb0d75dc9146fefd2，worker wall 15750.067281 s。solve 为 right GMRES/restart10、1 iteration、reason=2；五个 residual 为 5.733598076322987e-10 / 5.650904282024035e-10 / 2.5112691971837548e-11 / 6.142421244928043e-11 / 5.337481450973294e-10，均通过 5e-9。recovery mechanics 通过，但 own physics negative，candidate R/T/A/A_volume =
0.8048682104336213 / 0.000285259036006279 / 0.19484653053037237 / 0.19486523527614544。official RTA、canonical/grid authority withheld；consumer_summary.json 的外层 bookkeeping failure 是 terminal resource-authority transition 不完整，不是 OOM、swap、solve crash。

consumer stage duration（由 raw marker 相减，不能相加为另一个 workflow authority）为：system_ready 5487.2902 s；bottom factor 1156.0337 s，bottom Woodbury 593.0278 s；top factor 824.6716 s，top Woodbury 519.5425 s；modal Schur 6706.2121 s；outer solve 271.4981 s；recovery 148.1433 s；cleanup 1.057 s。process-tree RSS/PSS/USS peak 为 250.271244049 / 248.480698 / 248.221230 GiB，cgroup peak 251.563114 GiB，hard line 余量约 4.437 GiB，swap 0。bottom/top factor corrected NNZ 为 3.646e9 / 3.135e9；MUMPS factor-only、ICNTL14=40、modal rank=2400、batch=32、每侧75 batches。

## 5 nm 与等价性边界

Task039 inherited record benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json 的 source=9e31ecf189081afcb8ca27b0374ec89af0094e2d、input hash=4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811，peak 80.0258560180664 GiB、wall 10126.231902 s、swap 0，solve/recovery/physics/integrated checker 均通过。tracked record 中 physical/resolved hash 为 NA，不能猜。

Task041 本机 MPI8 reproduction 是独立 root task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf，source=def547cfd139b6377b0cae2ba1736ec3591814b0，input/physical/resolved 分别为 4e60924b...f1811 / 8391d461...d527c / d6f9de27...7798；peak 80.2187461853 GiB、elapsed 8357.347033 s、swap 0，solve/recovery/physics 通过。它相对 inherited baseline 为 +0.192890167 GiB (+0.2410%)、快 1768.885 s (17.47%)，不能混称为原 record。

5 nm MPI1 的完整资格等价性未建立。最后 attempt 的 consumer solve/recovery/physics 和候选 RTA 通过，但 external key binding false（600 keys 数量相同、hash 不同）；外层又因 terminal process-tree sample unreadable 分类为 task041_resource_sample_failure，所以没有 qualified consumer/workflow memory authority。该结果不是“数值不等价”。

## 资源、优化和停止边界

本次运行的用户后续安全合同为：workflow warning/hard 224/256 GiB、hard 274877906944 B、envelope 39600 s、swap 0；producer 176/192 GiB、phase cap 18000 s；consumer 224/256 GiB、phase cap 21600 s。shortwave timeout 按 phase elapsed，producer 完全退出后才启动 consumer，workflow peak 取不重叠两阶段的 max，不相加。MemAvailable floor 仍为 1869169767220 B。这是一份更严格的本次尝试合同，不删除或静默改写 task.md 原有 1.50 TiB 规划历史。

P1 固定8列 sampled direct relift；它保持完整 2M operator sources 和全行 canonical transfer，只减少 row-identity reference。M1200 两侧 projection 约 17.80/17.77 s，旧观察值 5119.43 s；这是跨 source 工程对比，不是新的 formal authority。P2 将 smaps 变为 0.25 s RSS/swap authority 加 30 s sparse PSS/USS diagnostic，未取得 post-P2 heavy speed 隔离。P3 用已算 singular values 计算 condition，避免第二次 dense SVD；当前 full-ready 到 Schur 的 138.2211 s 尚含旧路径，未测精确节省。

结论为 merge approval=NO；M800/M1200 own physics negative 永久保留，而非资源失败或 pass。M1600、h2.5/h2、2 nm 和 post-gate MPI1 均不运行，统一原因为 NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE；M1600 另有 no valid own-pass M pair / task.md §12.2 true Gate 说明，详见 outcomes/summary.md 与 compact v2。

## 求解器身份

Task039 inherited 5 nm 使用 GMRES/restart10；final 5 nm MPI1 inner 使用
FGMRES/restart90/1 iteration；3 nm M800 与 M1200 consumer 使用
right GMRES/restart10/1 iteration。exact block-LDU 在一迭代时没有触及
restart 上限，但这些是不同 run 的身份字段，不能合并或互换。
本机 Task041 local MPI8 reproduction 的有效求解器身份同样是
GMRES/restart10/1 iteration；input 中的 restart90 不是该 formal path
的有效 solver identity。

## 十问直答

| 问题 | 答案 |
|---:|---|
| 1. 5 nm equivalence | EQUIVALENCE_NOT_ESTABLISHED；不是 inequivalence。 |
| 2. 5 nm MPI1 peak | raw diagnostic producer/consumer/workflow RSS peak=2.46059799194 / 43.2886276245 / 43.2886276245 GiB；workflow 为 phase-separated max，不相加；outer 未资格化。packet directory=357120347 B。 |
| 3. 诊断节省 | 相对 80.025856018 GiB 减少 36.737228394 GiB = 45.9067%；不能写 qualified PASS。 |
| 4. minimum qualified M | NA。 |
| 5. 3 nm h3 | M800/M1200 candidate complete 但 not accuracy-qualified；h2.5/h2 not_run。 |
| 6. 2 nm | M/grid 均 NA，全部 not_run。 |
| 7. 未运行边界 | M1600、h2.5/h2、2 nm、post-gate MPI1：NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE。 |
| 8. 最细完成对象 | 3 nm p6/h3 M1200 candidate；accuracy-qualified frontier=NA，不是 capacity preflight stop。 |
| 9. 主导内存 | 两侧同时驻留的 exact-side MUMPS LU factors。 |
| 10. 0.7 nm | 仍需 factor-free/scalable architecture；这是基于 213–255 GiB factor-dominated evidence 的工程推断，不是正式外推。 |

## 最终分类合同

task.md 最终枚举中唯一适用的是 3NM_COMPLETED_NOT_GRID_CONVERGED。
5nm 三个枚举均不能诚实采用：不是 5NM_MPI1_EQUIVALENCE_PASS；因
external identity/outer authority 缺口也不满足
5NM_MPI1_OWN_PASS_REFERENCE_ARRAYS_PARTIAL；inner physics 未失败，故
不能写 5NM_MPI1_NUMERICAL_OR_PHYSICS_FAIL。故以 evidence boundary
记录 EQUIVALENCE_NOT_ESTABLISHED；CONTROLLED_STOP_AT_3NM_PHYSICS_GATE
仅为说明性状态。

5 nm MPI1 的 packet identity 也需保留边界：packet directory
357120347 B，manifest SHA=e5c754446e3fb9c8117608fbf610ec95749dc4b052bedae099ec268b57d8a85，
packet_identity file SHA=24fff61befe8946db6ea76187bd59d38d5c476d58d81a0f03582e3b8aa5a5ea9，
canonical identity SHA=7d496291c6ab2593673ff11ddaf456f208e78635c376afbc13e58dab645c0a85。
