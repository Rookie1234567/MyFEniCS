# Task041 outcomes summary

## 总结判定

| 字段 | 最终值 |
|---|---|
| final classification | 3NM_COMPLETED_NOT_GRID_CONVERGED |
| 说明性停止状态 | CONTROLLED_STOP_AT_3NM_PHYSICS_GATE |
| merge approval | NO |
| 范围 | 3 nm p6/h3 M800、M1200；5 nm inherited/local MPI8/MPI1 evidence |
| authoritative result | M800/M1200 均 candidate physics negative；official RTA/canonical/grid withheld |

solve/recovery mechanics pass 不等于 own physics pass。以下表格保留每个
独立 evidence/run 的身份、资源 authority 和失败边界；NA 是对应 raw record
没有可可靠提取的字段，不是猜测的零值。

## 正式模型与证据表

| status | 完整 source SHA | input / physical / resolved SHA | active rows | external keys | M delivered | iterations / restart / KSP | 五 true residual（reported/global/bottom/modal/top） | R / T / A / A_volume | grid / M comparison | producer / consumer / workflow RSS/PSS/USS（authority） | wall | swap | factor inventory | classification | 完整 evidence path |
|---|---|---|---:|---:|---|---|---|---|---|---|---|---:|---|---|---|
| failed fresh attempt | 48f56ad46c49519de363b90695d1ed219236c662 | 5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782 | 268272 | 1748 | 800/800（producer packet） | NA（consumer formal fields null） | 7.246419845266236e-10 / 6.711767430501667e-10 / 6.842952026951734e-12 / 7.252171978674087e-11 / 6.339676899706935e-10（diagnostic marker only） | NA（consumer formal fields null） | NA；diagnostic only，不能作 M comparison | producer 16.784275055/15.785678864/15.674812317；consumer/workflow 255.465618134/253.694432259/253.435222626（workflow process-tree summary） | producer 18000.658898；consumer 22215.056788；workflow 40216.175178 s | 0 | bottom/top corrected NNZ 3.259e9/3.716e9；MUMPS factor-only；ICNTL14=40；global direct/coarse/OOC=0 | IMPLEMENTATION_FAILURE at consumer_exit(solution_snapshot_destroyed)；diagnostic marker only | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260907T111441.388055Z |
| candidate retry complete | 2dbe7ff76d734c7689740a656ba7c0fdb5ceadcb | 5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782 | 268272 | 1748 | 800/800（旧 packet 复用） | 1 / 10 / right GMRES | 1.0614289127347946e-09 / 1.3530838051427825e-09 / 9.525482983090863e-12 / 5.059125745287973e-11 / 1.278144562727163e-9 | 0.8048686830648746 / 0.0002839834330554354 / 0.19484733350206998 / 0.19486649353451532 | M800；无合法 M pair，physics negative | producer NA（consumer-only）；consumer 213.299564362/NA/NA；workflow 213.299564362/NA/NA GiB（raw cgroup/process diagnostic；direct PSS/USS NA） | producer NA；consumer/workflow 17047.323762 s | 0 | bottom/top corrected NNZ 3.304e9/2.861e9；MUMPS factor-only；ICNTL14=40；global direct/coarse/OOC=0 | TASK041_CONSUMER_NUMERICAL_FAILURE；measured_candidate_physics_negative；official withheld | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260908T001027.090767Z/consumer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m800/task041_3nm_p6h3_m800_mpi8__hybrid_iterative__mpi8__M800/20260908T001027.090767Z/numerical_output/v3_7_hybrid_authority.json |
| linked candidate stages complete | producer c3a5bf4a424405c1f1de5cd6ac96be8db576f7b3；consumer c72b3e0d1540a5a891f5906fb0d75dc9146fefd2 | dab4209d2094d8640deaa61d5b6948a37d50362dc6b304762f93feff515b45c0 / 0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81 / 077624826a392f1ed83e11d3c55bd462ae631a6c2ddcb01e2e2d1daa080d62e0 | 268272 | 1748 | producer 1200/1200；consumer 1200/1200（packet reuse） | 1 / 10 / right GMRES | 5.733598076322987e-10 / 5.650904282024035e-10 / 2.5112691971837548e-11 / 6.142421244928043e-11 / 5.337481450973294e-10 | 0.8048682104336213 / 0.000285259036006279 / 0.19484653053037237 / 0.19486523527614544 | M800→M1200 scalar diff R/T/A/A_volume = 4.726312532454813e-7 / 1.275602950843622e-6 / 8.029716976054591e-7 / 1.2582583698850236e-6；仍无合法 convergence pair | producer 28.318450928/27.452210427/27.341518402（parent telemetry diagnostic）；consumer 250.271244049/248.480698/248.221230（process-tree/control telemetry）；workflow同不重叠 max，不相加 | producer compute 15386.145391；consumer 15750.067281；workflow NA（linked sum 31136.212672 s，非 uninterrupted） | 0 | consumer bottom/top 3.646e9/3.135e9；MUMPS factor-only；ICNTL14=40；modal rank2400、batch32、75/side；producer为QEP packet phase | TASK041_CONSUMER_NUMERICAL_FAILURE + outer bookkeeping_failure；不是 uninterrupted supervisor PASS；measured_candidate_physics_negative | /home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260908T083844.269710Z/producer/producer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260908T083844.269710Z/producer/selected_mode_packet/manifest.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry/consumer_summary.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry/numerical_output/v3_7_hybrid_authority.json；/home/fenics/Projects/MyFEniCS/results/task041_3nm_exact_side_hybrid_iterative_p6h3_m1200/task041_3nm_p6h3_m1200_mpi8__hybrid_iterative__mpi8__M1200/20260909T170009.909055Z_p1_consumer_retry.control/phase_failure.json |
| inherited reference complete | 9e31ecf189081afcb8ca27b0374ec89af0094e2d | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 / NA（tracked record无 physical hash） / NA（tracked record无 resolved hash） | NA（record） | NA（record） | NA（record） | 1 / 10 / GMRES（record） | 3.506501655137575e-10 / 2.8691974587254726e-10 / 1.7320410009968165e-11 / 5.776295396906669e-11 / 2.6600353255738315e-10 | NA（tracked record） | NA；Task039 inherited，不作为 Task041 M comparison | producer NA；consumer NA；workflow 80.0258560180664/NA/NA GiB（tracked process-tree peak） | producer/consumer NA；workflow 10126.231902 s | 0 | NA（tracked record未提供 factor inventory） | Task039 inherited full numerical/recovery/physics pass；不等于 Task041 MPI1 equivalence | /home/fenics/Projects/MyFEniCS/benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json |
| local reproduction complete | def547cfd139b6377b0cae2ba1736ec3591814b0 | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 / 8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c / d6f9de274db352e7b11eafed6867e6535edb7872af3547fa7fd958d02997798 | 132300 | 600 | 480/480 | 1 / 10 / GMRES | 2.754064024849399e-10 / 2.333030625515312e-10 / 3.75139448357935e-11 / 1.7973588584102126e-11 / 2.164825043210854e-10 | 0.7331842733894981 / 0.00022009869572663576 / 0.26659562791477526 / 0.2665962726231523 | NA；独立 5 nm MPI8 reproduction，不与 inherited 合并 | producer/consumer/workflow RSS/PSS/USS=NA/NA/NA；仅有 workflow peak 80.2187461853 GiB（compact authority unspecified） | producer/consumer NA；workflow 8357.347033 s | 0 | MUMPS factor-only；corrected factor NNZ=NA | Task041 local MPI8 solve/recovery/physics pass；不证明 MPI1 equivalence | /home/fenics/Projects/MyFEniCS/results/task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf |
| final MPI1 inner complete, outer unqualified | d6c71401a7105d2c67e22596e40461354cfda21f | 5a6a87882828ae768c92d4f14b45dbcb5f90c0bf141b982b106e52dba2b4c5c0 / 65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4 / 536d0ccb93f6c7bf00c42a12f60ea58bfe44436725da7070af2230fad305dc73 | 132300 | 600 | 480/480 | 1 / 90 / FGMRES | 1.9141387966716752e-10 / 1.914124454116583e-10 / 8.551881036770462e-12 / 1.489643628946544e-11 / 1.7761587180860387e-10 | 0.7331842733878213 / 0.0002200986957195755 / 0.2665956279164591 / 0.266596272621591 | NA；external key identity mismatch prevents equivalence | producer 2.46059799194/2.42841053/2.41315460；consumer 43.2886276245/43.2520036697/43.2368469238；workflow max=43.2886276245/43.2520036697/43.2368469238 GiB（raw telemetry diagnostic） | producer 12285.1455821；consumer 37058.1461057；workflow 49346.574875 s | 0 | MUMPS factor-only；corrected NNZ=NA（compact evidence未提供） | inner solve/recovery/physics/candidate RTA pass；external_key_binding_pass=false；outer task041_resource_sample_failure | /home/fenics/Projects/MyFEniCS/results/task041_5nm_exact_side_hybrid_iterative_p6h4_m480/task041_5nm_p6h4_m480_mpi1__hybrid_iterative__mpi1__M480/20260904T152109.607989Z |

M1200 producer packet 的 manifest SHA 为 c7a36ab977e5fc11505ad27a6e8044fc9e909b42fd37a8ea1abeb72b6e49d71b，canonical identity SHA 为 cef2de437f0b0a247791acc8e4b865d1fd51082b181617ab6621cb9a95ba5d00，packet directory bytes=1370082162，32 shards，write max-rank=1.167526111 s。M1200 producer 与 consumer 是 hash-bound linked evidence，不是 uninterrupted supervisor PASS。

## 最终分类合同

task.md 的最终枚举中，本次唯一适用的是 3NM_COMPLETED_NOT_GRID_CONVERGED。
5nm 的三个枚举均不能诚实采用：

1. 不是 5NM_MPI1_EQUIVALENCE_PASS，因为 external identity binding 和 outer
   resource authority 尚未闭合；
2. 不是 5NM_MPI1_OWN_PASS_REFERENCE_ARRAYS_PARTIAL，因为该条件要求的
   reference identity/authority 仍不完整；
3. 不是 5NM_MPI1_NUMERICAL_OR_PHYSICS_FAIL，因为 final MPI1 inner
   solve/recovery/physics 并未失败。

因此另以 evidence boundary 记录 EQUIVALENCE_NOT_ESTABLISHED，而不伪造
task.md 枚举。CONTROLLED_STOP_AT_3NM_PHYSICS_GATE 只是说明性状态，不是
task.md 的替代枚举。

## M 与未运行项

M800 与 M1200 的 energy failure 分别为
abs(A_balance-A_volume)=1.9160032445286745e-5 和
1.8704745773062692e-5，均大于 1e-5。虽然 scalar absolute difference
较小，但两个 M 都没有 own pass，故不存在合法 convergence pair。

| item | result | final reason |
|---|---|---|
| 3 nm p6/h3 M1600 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE；no valid own-pass M pair，task.md §12.2 true Gate |
| 3 nm h2.5/h2 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |
| all 2 nm | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |
| post-gate MPI1 | NOT_RUN | NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE |

M1200 是用户后来明确授权的 controlled continuation，不能用上述 reason
暗示它未运行。最细已完成对象是 3 nm p6/h3 M1200 candidate；它未
accuracy-qualify，minimum qualified M 和 accuracy-qualified frontier 均为 NA。

## 资源语义

用户后续指定的本次运行合同为 workflow warning/hard=224/256 GiB、
hard=274877906944 B、envelope=39600 s、swap0；producer=176/192 GiB、
18000 s；consumer=224/256 GiB、21600 s。shortwave timeout 按 phase
elapsed，producer 完全退出后才启动 consumer；workflow peak=max，不相加。
MemAvailable floor=1869169767220 B。该合同不改写 task.md 原 1.50 TiB
规划历史。
