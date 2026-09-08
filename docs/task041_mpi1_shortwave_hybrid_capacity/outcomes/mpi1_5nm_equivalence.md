# 5 nm MPI1 等价性

结论为 EQUIVALENCE_NOT_ESTABLISHED，不是“数值不等价”。5 nm 的 Task039 inherited record、Task041 本机 MPI8 reproduction 和四次 MPI1 attempt 必须分开；不同 source/input/authority 不能拼成一个 run。

求解器身份也必须分开记录：Task039 inherited 5 nm 为 GMRES/restart10；
final 5 nm MPI1 inner 为 FGMRES/restart90/1 iteration；3 nm M800/M1200
consumer 为 right GMRES/restart10/1 iteration。exact block-LDU 一迭代时
未触及 restart 上限，但不能因此把 10 与 90 视为同一 run。

## 已通过或可复核的 5 nm 证据

| evidence | source/hash | result | resource |
|---|---|---|---|
| Task039 inherited | record benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json；source 9e31ecf189081afcb8ca27b0374ec89af0094e2d；input 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 | solve/recovery/physics/integrated checker pass；五 residual 3.506501655137575e-10 / 2.8691974587254726e-10 / 1.7320410009968165e-11 / 5.776295396906669e-11 / 2.6600353255738315e-10 | peak 80.0258560180664 GiB，wall 10126.231902 s，swap0；physical/resolved hash in tracked record=NA |
| Task041 local MPI8 | task041_5nm_mpi8_v7_exact_side_reproduction_mumps40_targetzero_fast_socket_def547cf；source def547cfd139b6377b0cae2ba1736ec3591814b0；input/physical/resolved 4e60924b...f1811 / 8391d461...d527c / d6f9de27...7798 | solve/recovery/physics pass；五 residual 2.754064024849399e-10 / 2.333030625515312e-10 / 3.75139448357935e-11 / 1.7973588584102126e-11 / 2.164825043210854e-10 | peak 80.2187461853 GiB，elapsed 8357.347033 s，swap0 |

本机 reproduction 相对 inherited record 为 +0.192890167 GiB (+0.2410%)、快 1768.885 s (17.47%)。这是用户授权的独立本机复现，不是 inherited run 的改写。

## MPI1 attempts

| root/time | source | outer result | inner evidence |
|---|---|---|---|
| 20260902T230819.318085Z | 812118af... | task041_resource_sample_failure，wall 13659.649299 s | 未形成合格等价性 authority |
| 20260904T101800.303093Z | def547cf... | task041_producer_failure，wall 3301.179332 s | producer 阶段失败 |
| 20260904T112637.063178Z | 24392bf... | task041_resource_sample_failure，wall 13316.443166 s | 未形成合格 authority |
| 20260904T152109.607989Z | d6c71401a7105d2c67e22596e40461354cfda21f | outer task041_resource_sample_failure，wall 49346.574875 s | inner solve/recovery/physics 与 candidate RTA pass；external binding false；terminal sample unreadable |

最后一次 MPI1 的 source/input/physical/resolved 为 d6c71401a7105d2c67e22596e40461354cfda21f / 5a6a87882828ae768c92d4f14b45dbcb5f90c0bf141b982b106e52dba2b4c5c0 / 65bb1e2947604a7efe54b2d6450a63a583714341505c207241f4278bd25b22a4 / 536d0ccb93f6c7bf00c42a12f60ea58bfe44436725da7070af2230fad305dc73。其 raw telemetry 有 61912 个 consumer samples，全部 readable=true、swap0；consumer RSS/PSS/USS peak 为 43.2886276245 / 43.2520036697 / 43.2368469238 GiB，producer 为 2.46059799194 / 2.42841053 / 2.41315460 GiB，workflow diagnostic peak 取 max=43.2886276245 GiB，phase walls 12285.1455821 / 37058.1461057 / 49346.574875 s。它们是 raw diagnostic measured，不是 supervisor-qualified resource PASS。

该 attempt 的 consumer solve/recovery/physics pass，候选 R/T/A/A_volume 为 0.7331842733878213 / 0.0002200986957195755 / 0.2665956279164591 / 0.266596272621591，closure 约 6.447051319e-7；五 residual 如上。唯一明确的数值身份缺口是 external_key_binding_pass=false：600 keys 数量相同但 identity hash ba431ec... 与 authority hash 849cbc... 不同。外层另有 terminal process-tree unreadable，故没有合格 consumer/workflow memory authority，不能声明 5NM_MPI1_EQUIVALENCE_PASS。

## packet 与 source-only 语义

最后 MPI1 packet directory bytes=357120347；manifest file SHA e5c754446e3fb9c8117608fbf610ec95749dc4b052bedae099ec268b57d8a85f；packet_identity file SHA 24fff61befe8946db6ea76187bd59d38d5c476d58d81a0f03582e3b8aa5a5ea9；manifest canonical identity SHA 7d496291c6ab2593673ff11ddaf456f208e78635c376afbc13e58dab645c0a85。

source-only root task041_s1_source_only_p6h4_m480_mpi1_6ae90799 的 keys/roundtrip/repeat 通过，但 current_vs_persisted=3.826978841496932e-9 > 1e-12，source SHA 为 6ae907991ceb3323c06b351d13a9557685e4d713。其正式分类是 REFERENCE_SOURCE_SEMANTICS_CHANGED；旧 MPI8 authority 保留，corrected MPI1 不能声明完整 MPI equivalence。
