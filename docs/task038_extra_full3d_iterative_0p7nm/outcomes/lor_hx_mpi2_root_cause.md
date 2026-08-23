# M0 MPI2 根因诊断与 V8 hard stop

## 先说结论

M0 用一个很小的 p2/h50 正定测试，检查高阶场在 MPI1 与 MPI2 分区后是否仍代表同一个代数问题。它不是 PDE，也不是 p6/h10 设置；它只回答“分区、边方向和周期约束是否把同一个向量送进同一个 LOR/HX 代数路径”。

结论是：边方向放置问题可以被独立识别并修正，但修正后仍存在远程 MPC 主从关系与 owner 路由不一致。梯度右端在临时 owner-consistent 元数据下可以闭合，节点解和后续分量仍不能闭合。因此不能把这组问题压缩成一个已验证的 production fix。Review V8 §12 hard stop 已触发，M1–M7 不运行。

## 两次正式 M0 attempt

| attempt | source SHA | MPI1/MPI2 worker | individual checker | pair checker | 结论 |
|---|---|---:|---:|---:|---|
| attempt1 | f76a30e843dcc1e3e25aee6a73df6aca12222f10 | rc=0 / rc=0 | 各自完成；pair contract 暴露 8 个节点 key-set 差异 | rc=1，30 个 exact/identity 失败 | edge orientation placement + exact-nodal MPI negative |
| attempt2 | 9f44464eda27590492dcfe0432129a126625b5cc | rc=0 / rc=0 | contract_errors=[]，单案事实检查完成 | rc=1，32 个 exact-nodal Gate 失败 | orientation placement 已验证修复；exact-nodal pair 仍失败 |

两次 raw root 都保留。tracked record/check/pair 副本位于 outcomes/records，副本与 ignored 源逐字节相同。

## attempt2 的可复核数值

| 对象 | MPI1/MPI2 canonical relative |
|---|---:|
| high source before | 1.417734557397384e-15 |
| high residual | 1.6029978812022376e-15 |
| low input | 1.6864438658655413e-15 |
| exact edge correction | 1.5658061021293675e-15 |
| exact edge action | 1.7783413648977776e-15 |
| exact edge-pre result | 1.2841132186933526e-15 |
| exact nodal output | 0.03757191918203578 |
| exact outer final action, MPI1↔MPI2 canonical vector relative | 9.283829676136373e-09 |
| exact outer final solution, MPI1↔MPI2 canonical vector relative | 1.142232152655208e-07 |
| exact outer true-residual vector, MPI1↔MPI2 canonical relative | 0.9557368639478777 |

以上三个数都是 MPI1↔MPI2 canonical vector 的 relative difference，不是任一 case 的 residual norm；两边各自的 final true residual norm 约为 1e-8。残差/解向量仍不是同一个 canonical 结果。edge-pre 已在约 1e-15 闭合；失败从 exact gradient 开始，gradient.rhs=0.36157950436833775，随后各分量也明显超过 1e-10。exact nodal component 的 representative relative 如下：

| component | rhs | nodal delta | edge delta | result |
|---|---:|---:|---:|---:|
| gradient | 0.36157950436833775 | 0.2949106829240065 | 0.1894457691797068 | 0.020169732344255478 |
| Pi_x | 0.5009990665333411 | 0.46374607727504064 | 0.23077652244801045 | 0.0638917565026212 |
| Pi_y | 0.6397955141738358 | 0.6820555170002124 | 0.4911468670395767 | 0.07786760176186892 |
| Pi_z | 0.2215262303239109 | 0.3452914346376906 | 0.06252388820138048 | 0.05576217631355618 |
| post | — | — | 0.10359865245332464 | 0.03356471572091377 |

outer diagnostic history 不是 M0 qualification Gate。production PC 在两次 20-step replacement 周期后于 MPI1/MPI2 都达到显式 true residual 约 1e-8；exact-nodal diagnostic 需要 82/84 步才达到约 1e-8。完整 scalar history 和 checkpoint 状态仍在两案 worker record/raw 中。

| path | cycles / iterations | first explicit pass | final explicit true residual | reason | matvec / solver PC / monitor PC / total PC |
|---|---:|---:|---:|---:|---:|
| production, MPI1 | 4 / 62 | 62 | 9.276247638965869e-09 | 2 | 65 / 66 / 4 / 70 |
| exact nodal, MPI1 | 5 / 82 | 82 | 9.510953881688309e-09 | 2 | 86 / 87 / 4 / 91 |
| production, MPI2 | 4 / 62 | 62 | 9.431179719931108e-09 | 2 | 65 / 66 / 4 / 70 |
| exact nodal, MPI2 | 5 / 84 | 84 | 9.713792528761725e-09 | 2 | 88 / 89 / 4 / 93 |

## orientation placement diagnosis

MPI1 没有负向 raw edge 引用；MPI2 有 92 个负向 cell-edge reference，地图中对应 208 个 minus factors。用实际 cell permutation 和 p1 edge Tt 构造的 orientation-aware placement 结果：

| metric | MPI1 current | MPI1 fixed oracle | MPI2 current | MPI2 fixed oracle |
|---|---:|---:|---:|---:|
| owner packet roundtrip | 0.0 | 0.0 | 0.5849607443002511 | 2.060948712431624e-17 |
| first edge-pre comparison | 0.0 | 0.0 | 0.2898861945930992 | edge-pre closes |

orientation-aware rectangular maps 的 adjoint work identity 在 MPI2 的 gradient/Pi_x/Pi_y/Pi_z 分别为 2.5037197364122333e-16、2.08990182089594e-16、4.2142852883030456e-18、5.862316766423091e-16；raw row mismatch=0。这验证了 9f 的 edge orientation placement 窄修，但不支持“边方向就是全部错误”。

## MPC/owner remaining boundary

| 诊断 | 实测值 |
|---|---:|
| phase rows | 220 |
| actual slave rows | 220 |
| phase/slave mismatch | 0 |
| remote relation inconsistency | 37 |
| sign-only corrected gradient.rhs | 0.20630212828353248 |
| owner-consistent ghost relation gradient.rhs | 2.396070826157907e-15 |
| owner-consistent gradient nodal delta | 0.11660480519091415 |
| fixed lattice node_matrix action | 0.08847380943557186 |
| direct nodal residual | MPI1 5.310854724390275e-16；MPI2 4.602617923986701e-16 |

节点直接解的 residual 约 5e-16，说明本次剩余失败不能简单归因于 direct backend 没收敛。owner-consistent relation 只闭合 gradient RHS；它没有闭合 nodal delta、Pi 分量或最终结果。也就是说，transfer、MPC metadata、owner algebra 仍有组合性缺口，无法由单一修复证据关闭。

## 资源与生命周期边界

attempt2 的 /usr/bin/time -v 仅是单进程或 MPI launcher 观察，不是 process-tree/cgroup authority：

| case | wall | maximum RSS | GNU time Swaps | scope |
|---|---:|---:|---:|---|
| p2-mpi1 | 12.88 s | 194732 KiB = 199405568 B | 0 | direct Python process |
| p2-mpi2 | 7.42 s | 192496 KiB = 197115904 B | 0 | mpiexec launcher observation |

系统 baseline 约 16625664 B swap 不等于 worker swap；本次 GNU time worker/launcher Swaps=0。markers 从 paths_ready 到 cleanup_end 完整，worker 自然退出且 no orphan。资源数值不能被写成 p6/2GB qualification。

## hard stop 与证据入口

V8 §12 的 hard stop 是 transfer/MPC/owner algebra mismatch 无法通过单一修复关闭。故 M1 memory-first small、M2 p6 setup、M3 positive longrun、M4 physical longrun、M5 MPI2、M6 h5 scaling、M7 0.7nm/2TiB feasibility 全部 NOT_RUN_BY_M0_HARD_STOP。

tracked evidence：

| attempt | record / check / pair SHA256 |
|---|---|
| f76 MPI1 | 47b5eb320bcfd5723c443bc803d0dcbcca2b8ce794a25fe7ee36fab2132d1876 / 7924db27543e6d8d65a97de463a8761c1dade70b853b7f0677d5c310bde37064 |
| f76 MPI2 | 47c8f9d5f5594cca3b00111cf8efb0824a0c47f4d408c6496ea4d4358cc0ff84 / 110695004b7bdb5889a1812c935ce2f822dd6a01f97d59e433ce7bece72d0043 |
| f76 pair | 94c54ac2d6c77b33c5c1dbbe6b0e6da739b585ab9a3f7fccf94e00d46fa1bf52 |
| 9f MPI1 | 5c038d233afefb45020f33ad2feb5b16b673a47541fcbc0e57f017522975daf5 / 50807c4916867b15051fdec6eba695f9e1123415b7542a236c6e577d1dec4841 |
| 9f MPI2 | 1b2545ccc3a042e201b09f3f55f4290035abd6bcd5cdc213d5490ad677fa5f6d / f26e43134610cb55eb528eab2b035f08e00c7318d6e602759ff01409eb9935e1 |
| 9f pair | bc5e52ca753ebfb04ee17f0196c41b4f4c3df5739549de918dd5b43732e93098 |

9f raw manifests 为 MPI1 a3f60e350573c612492d75cf322b7434718c7cd1743a40a9da2da6c8bfde2d34、MPI2 329b58469117099cdfe2941bdde5ac18b018990a3e21ce598de0c1b2dd7e23b；markers 为 MPI1 807f2f30d1b6c3e0d783eae9b4294b3815a511e2aeb6010fdb77ec4e4ca6da77、MPI2 rank0 813290e11b7534b3dac9bfa980f48d0b0cecc81061aef0b12d7c57ef7951a862、rank1 d685dfe4b4c55a7a3377cfe91fe4418f5118b3a670f292566967be91f47a5819。

临时诊断脚本和 NPZ 没有复制进 Git；其 SHA 与关键数值汇总记录在 m0_postfailure_diagnostic_v1.json。它们是诊断证据，不是 formal pass。
