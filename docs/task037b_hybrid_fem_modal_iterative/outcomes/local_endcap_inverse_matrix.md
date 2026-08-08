# Task037b H5 local endcap inverse：矩阵与逐 RHS 证据

## 范围与通俗解释

H5 试验的是“把一个大端部矩阵拆成若干带重叠的小块，每个小块用 ILU(0) 近似求逆，再把各块结果按 partition-of-unity 权重相加”。这样做的目的，是在不形成全局直接因子和全局稠密矩阵的情况下，寻找可用于 Hybrid 细动作的低内存局部逆。它只验证本轮冻结的 local inverse family，不替代 exact Hybrid 或 Full3D authority。

本次 formal 的物理与身份完全冻结为：p6/h10、modal p6/h10、M120/candidate240、MPI8、S 偏振、10° grazing、bottom/top=10/110 nm、static-condensed、`full3d_uniform_cg`、`scalar_cg_discrete_derivative`、source SHA `216437c6f13b3a3bf46e74451f63779189453c6f`。Full3D pinned authority 与 preflight authority 沿用 H3/H4：

| authority | 路径 | SHA256 |
|---|---|---|
| pinned Full3D | `/home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json` | `b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3` |
| historical preflight | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json` | `96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8` |

## H5a exact local reference

H5a 先用每侧一个 direct factor 逐一求解 11 个 RHS。bottom/top 均为 11/11，通过显式 oracle residual 与 Matrix-free action residual；随后各侧 factor 均释放。结合 H1 source `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc` 的 whole-direct authority，这证明 exact local action/RHS 接线是可用的，但不替代 whole Hybrid authority，也不证明 ILU(0) local inverse 能够收敛。

| side | RHS | max direct true residual | max action true residual | max iterations | factor before→after |
|---|---:|---:|---:|---:|---:|
| bottom | 11/11 pass | `2.107282966996484e-12` | `2.0973803488508764e-12` | 1 | 1→0 |
| top | 11/11 pass | `2.1971754846774315e-12` | `2.1957548735380243e-12` | 1 | 1→0 |

## H5b frozen local inverse 配置

| 项目 | 实际值 |
|---|---|
| local mesh / partition | x-axis 6 slabs，overlap `0.125`，`partition` weights |
| coordinate axis | 0 |
| local solver | shifted ILU(0)，factor-only；无 direct fallback |
| outer solver | right FGMRES，restart=30，max_it=300，rtol=`1e-10`，atol=0 |
| one apply | 每次 PC apply 只有一次 ASM apply；`two_step_action_operator=None` |
| true residual Gate | `<=1e-8` |
| local active rows | 8424（bottom/top） |
| source matrix NNZ | 16481448（bottom/top） |
| factor NNZ | 16481448（每侧 raw record 的 recorded count，不是估算值） |
| factor CSR payload estimate | 329729680 bytes；这是按 `factor_nnz*(scalar_bytes+integer_bytes)+(factor_rows+16)*integer_bytes` 估算，scalar=16、integer=4 |
| assembly payload | max sender `2987712` bytes；max owner `23901696` bytes |
| setup wall | bottom `18.40562699502334 s`；top `18.08617060002871 s` |
| solve wall | bottom `149.78834724798799 s`；top `166.75850025296677 s` |
| apply wall范围 | bottom `0.1710509890690446–6.6959833888104185 s`；top `5.131579715292901–8.116204697289504 s`，逐 RHS 原值在 raw record |

factor NNZ 是每侧 raw record 记录的数量；329729680 bytes 是由该数量和公式得到的 CSR payload estimate，不是实测分配量。raw record 同时保留 formula 与 identity。

## H5b 逐 RHS 结果

`repeat error=0` 表示同一 RHS 的两次求解得到相同的解摘要；它证明 deterministic，不等于收敛。bottom 的唯一通过项是零 physical RHS，不能据此资格化局部逆。其余 bottom 10/11、top 11/11 均在 max_it=300 时返回 `reason=-3`。

| RHS | bottom reason/iter | bottom true residual | bottom repeat | bottom pass | top reason/iter | top true residual | top repeat | top pass |
|---|---:|---:|---:|---|---:|---:|---:|---|
| physical | 2 / 0 | 0.0 | 0.0 | P | -3 / 300 | 0.1509350829509824 | 0.0 | F |
| random_seed_3701 | -3 / 300 | 0.9422475005587448 | 0.0 | F | -3 / 300 | 0.9427702892133474 | 0.0 | F |
| random_seed_3702 | -3 / 300 | 0.9293220763689022 | 0.0 | F | -3 / 300 | 0.9280882312068575 | 0.0 | F |
| random_seed_3703 | -3 / 300 | 0.9369183669688806 | 0.0 | F | -3 / 300 | 0.9395882385188576 | 0.0 | F |
| random_seed_3704 | -3 / 300 | 0.930233925302435 | 0.0 | F | -3 / 300 | 0.9298949449605233 | 0.0 | F |
| modal_positive_lowest_propagating_or_lossy | -3 / 300 | 0.03484948799945204 | 0.0 | F | -3 / 300 | 0.03687099842604409 | 0.0 | F |
| modal_positive_proxy_abs_im_beta_gt_abs_re_beta | -3 / 300 | 0.02992103340490972 | 0.0 | F | -3 / 300 | 0.02988073009258503 | 0.0 | F |
| modal_positive_highest_retained_index | -3 / 300 | 0.020685386824231856 | 0.0 | F | -3 / 300 | 0.021991079812817848 | 0.0 | F |
| modal_negative_lowest_propagating_or_lossy | -3 / 300 | 0.03484948802751039 | 0.0 | F | -3 / 300 | 0.036870998420343234 | 0.0 | F |
| modal_negative_proxy_abs_im_beta_gt_abs_re_beta | -3 / 300 | 0.02832133649942693 | 0.0 | F | -3 / 300 | 0.030181589675220458 | 0.0 | F |
| modal_negative_highest_retained_index | -3 / 300 | 0.020833624410449787 | 0.0 | F | -3 / 300 | 0.022984199084265956 | 0.0 | F |

### 固定 apply 诊断

这是 `1/2/4/8` 次 stationary correction 的原始诊断，不是 H5 Gate，也没有用来调参或改变停止规则。

| RHS | bottom 1/2/4/8 | top 1/2/4/8 |
|---|---|---|
| physical | 0 / 0 / 0 / 0 | 2.504744457359676 / 3.034728166706868 / 11.837349977490438 / 2134.1980702679894 |
| random_seed_3701 | 6.687299776426495 / 6.187746534062544 / 29.152935634416863 / 5492.501949461884 | 6.687488110725847 / 5.963022173660356 / 17.086980315725075 / 3107.4365876964107 |
| random_seed_3702 | 6.3920434142931315 / 5.611206427631388 / 9.030170748651864 / 973.5922045717024 | 6.42803300529704 / 5.919154353397007 / 30.229886267980387 / 6097.209257007212 |
| random_seed_3703 | 6.6326509022690265 / 5.927067329516135 / 17.25154286913464 / 3131.044708946461 | 6.662901592707661 / 6.244293314756657 / 36.49698496355172 / 7043.905940844098 |
| random_seed_3704 | 6.429656780830415 / 5.713783663364073 / 13.80353964192453 / 2052.631784416835 | 6.441931177058457 / 5.912073931838743 / 23.578890440903592 / 4495.848131043982 |
| modal_positive_lowest_propagating_or_lossy | 2.024691365261517 / 2.8682149723854247 / 21.165780617173848 / 4135.401750180837 | 2.038114185839962 / 2.9867805220303003 / 18.762258778047592 / 3581.211361500439 |
| modal_positive_proxy_abs_im_beta_gt_abs_re_beta | 2.298559810208743 / 1.88579192621318 / 6.759898089540063 / 1174.408425824606 | 2.3317152683128994 / 2.3357798826137883 / 6.406305845418773 / 920.8121694069641 |
| modal_positive_highest_retained_index | 1.203015811503088 / 1.387974291963216 / 6.169611703458515 / 1228.6183270924203 | 1.2951973816613667 / 1.5166784562813989 / 3.165060480266349 / 383.39907455687256 |
| modal_negative_lowest_propagating_or_lossy | 2.0246913652783425 / 2.8682149724201225 / 21.16578061695967 / 4135.401750134916 | 2.038114185793324 / 2.9867805219938273 / 18.762258777293553 / 3581.2113613413353 |
| modal_negative_proxy_abs_im_beta_gt_abs_re_beta | 2.3127897123106966 / 1.9917424415423644 / 4.928490969485137 / 697.3354614877459 | 2.453953767161266 / 2.1794135445312817 / 9.772661555064103 / 1869.3396578725346 |
| modal_negative_highest_retained_index | 1.1564344798711095 / 1.257958935242231 / 3.1547669487538776 / 523.270239192082 | 1.2735665253108084 / 1.4127535689067698 / 3.5647096668757507 / 577.8802737533975 |

H5b 最大 direct-solution diagnostic relative error 为 bottom `0.9382154125402716`、top `0.9378651377201417`；该字段仅作诊断，没有另设通过阈值。两侧的 `repeat_solution_relative_error` 最大值均为 `0.0`。

## 生命周期与 operator 合同

| 项目 | 结果 |
|---|---|
| simultaneous factor count | 12 |
| bottom release remaining | 6 |
| top release remaining | 0 |
| action survives bottom/top release | true / true |
| bottom/top factors released | true / true |
| global operator | MatPython，matrix-free |
| global A、bottom/top F | false / false / false |
| explicit external C/D | 0 / 0 |
| candidate direct factor count | 0 |
| external mode count / Krylov auxiliary rows | 40 / 0（每侧） |

## 结论与边界

结合 H1 source `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc` 的 whole-direct authority，H5a exact/direct reference 通过说明 exact local action 与 RHS 接线没有失败；它不单独证明 whole direct Hybrid。冻结的 partition ASM + shifted ILU(0) local inverse 在 bottom/top 均无法资格化，正式分类为 `LOCAL_INVERSE_FAMILY_NEGATIVE`。这只否定本任务冻结的 local inverse candidate，不否定 Hybrid 模型，也不证明任何未经授权的新算法家族不可能。H5c、H6-H10 按任务停止规则未运行。

原始证据保留在 Git ignored 目录：[solver record](../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/solver_record.json)、[summary](../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8.json)、[timeline](../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_timeline.csv)、[stages](../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/memory_stages.jsonl)、[stdout](../../../benchmarks/artifacts/task037b/h5_local_inverse_216437c_mpi8/worker_stdout.txt)。

## V1 R1–R5 research closeout（与原 H5b 分开）

这一节记录 Review V1 的连续诊断链。R1–R5 使用同一冻结 p6/h10、modal p6/h10、M120/candidate240、MPI8、S 偏振、10° grazing、bottom/top=10/110 nm、static-condensed、full3d_uniform_cg/scalar_cg_discrete_derivative 身份；每一阶段均为一次正式 MPI8 watchdog 运行。以下 R5 是 DtN-aware whole-endcap local inverse 研究候选，不能与本文件前面的原 H5b 六-slab记录混称。

| 阶段 | source SHA | formal / numeric | status | 关键结论 |
|---|---|---|---|---|
| V1-R1 | e2e57675867dcb3476441f27b33eb45a0d90b040 | pass / pass | task037b_v1_r1_pass_awaiting_r2 | bottom/top 各 6 probes；分解 action error 与 component repeat 均 0；销毁 components 后 A 仍可用 |
| V1-R2 | a9ee7067503879ce082145430169acc8aeb48b7b | pass / negative | task037b_v1_r2_complete_awaiting_r3 | 六-slab F-only；bottom/top max F-only true residual=0.9482247431562106 / 0.9499229695708535，repeat=0 |
| V1-R3 | 31d30842f0bcf24edde2113217db7a6dfc1264c1 | pass / negative | task037b_v1_r3_complete_awaiting_r4 | whole-endcap ILU(0) 的 F-only 与 complete-A 两个 case 均完成且 finite，但均未达到 1e-8 |
| V1-R4 | 53faebb14960f8ddbaf88f54f8ceae511ccd7764 | pass / pass | task037b_v1_r4_complete_awaiting_r5 | exact F inverse + 40-mode Woodbury 与 exact A 一致；rank/condition、符号、ownership 和 factor 顺序均通过 |
| V1-R5 | 2a2ef3d37514e4ab30d50209065af84c1dafd59b | pass / negative | WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE | PC 线性、确定性、K、finite、生命周期与资源均合法；21 个非零 RHS 为 0/21 |

各阶段的 watchdog summary、solver record、memory stages、timeline 和 stdout 均保留在 Git ignored artifact 目录；完整路径与 SHA 见 Case101 compact record。

### R5 operator、资源与判定

R5 的实际 PC 是 whole-endcap ILU(0) base inverse 加上真实 40-mode Matrix-free DtN Woodbury correction。它没有物化 global F/A，也没有 direct fallback。两侧 K 均为 40 阶、rank=40、condition finite 且 bottom/top=3.0331668903694333 / 4.162687539173755；linearity 最大值=1.88588624470667e-15 / 3.0970882574272953e-15，determinism 最大值均为 0，arrays_finite=true。

| side | nonzero capacity | zero physical | max nonzero complete-A residual | max modal residual | max repeat | factor before→after |
|---|---:|---:|---:|---:|---:|---|
| bottom | 0/10 | 1/1 | 0.009555400179345386 | 0.00018386608677910615 | 0 | 1→0 |
| top | 0/11 | not applicable | 0.009190066519286536 | 0.0002041643360139555（physical=0.0008193612125815937） | 0 | 1→0 |

bottom 的 physical RHS 是零方程，只记录 zero_equation_pass，不计入 21 个非零 capacity。R5 全部 22 个 RHS 都 finite，repeat solution error 都为 0；这只证明重复求解 deterministic，不证明收敛。由于不满足 full，也不满足“所有 physical/modal <=1e-8 且所有 random <=1e-5 且至少一个 random >1e-8”的 borderline 条件，最终归入 WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE。severe_negative=false 只表示没有触发预定义 severe 子标签，不改变其余数值失败的 negative 结论。

### R5 bottom：11 个固定 RHS

| RHS | kind | first reason/it/residual | second reason/it/residual | repeat | pass |
|---|---|---:|---:|---:|---|
| physical | physical zero | 2 / 0 / 0 | 2 / 0 / 0 | 0 | true（zero only） |
| random_seed_3701 | random | -3 / 300 / 0.006890904871342775 | -3 / 300 / 0.006890904871342775 | 0 | false |
| random_seed_3702 | random | -3 / 300 / 0.009333916518280314 | -3 / 300 / 0.009333916518280314 | 0 | false |
| random_seed_3703 | random | -3 / 300 / 0.008790118723806585 | -3 / 300 / 0.008790118723806585 | 0 | false |
| random_seed_3704 | random | -3 / 300 / 0.009555400179345386 | -3 / 300 / 0.009555400179345386 | 0 | false |
| modal_positive_lowest_propagating_or_lossy | frozen modal | -3 / 300 / 0.0001838660867791061 | -3 / 300 / 0.0001838660867791061 | 0 | false |
| modal_positive_proxy_abs_im_beta_gt_abs_re_beta | frozen modal | -3 / 300 / 0.00008092229529467422 | -3 / 300 / 0.00008092229529467422 | 0 | false |
| modal_positive_highest_retained_index | frozen modal | -3 / 300 / 0.000049372365734227 | -3 / 300 / 0.000049372365734227 | 0 | false |
| modal_negative_lowest_propagating_or_lossy | frozen modal | -3 / 300 / 0.0001838660866969548 | -3 / 300 / 0.0001838660866969548 | 0 | false |
| modal_negative_proxy_abs_im_beta_gt_abs_re_beta | frozen modal | -3 / 300 / 0.00007451095946450286 | -3 / 300 / 0.00007451095946450286 | 0 | false |
| modal_negative_highest_retained_index | frozen modal | -3 / 300 / 0.00005624533952496862 | -3 / 300 / 0.00005624533952496862 | 0 | false |

### R5 top：11 个固定 RHS

| RHS | kind | first reason/it/residual | second reason/it/residual | repeat | pass |
|---|---|---:|---:|---:|---|
| physical | physical nonzero | -3 / 300 / 0.0008193612125815937 | -3 / 300 / 0.0008193612125815937 | 0 | false |
| random_seed_3701 | random | -3 / 300 / 0.009075322356907048 | -3 / 300 / 0.009075322356907048 | 0 | false |
| random_seed_3702 | random | -3 / 300 / 0.008611317809909208 | -3 / 300 / 0.008611317809909208 | 0 | false |
| random_seed_3703 | random | -3 / 300 / 0.008246260206763207 | -3 / 300 / 0.008246260206763207 | 0 | false |
| random_seed_3704 | random | -3 / 300 / 0.009190066519286536 | -3 / 300 / 0.009190066519286536 | 0 | false |
| modal_positive_lowest_propagating_or_lossy | frozen modal | -3 / 300 / 0.0002041643360139555 | -3 / 300 / 0.0002041643360139555 | 0 | false |
| modal_positive_proxy_abs_im_beta_gt_abs_re_beta | frozen modal | -3 / 300 / 0.0000871291034537535 | -3 / 300 / 0.0000871291034537535 | 0 | false |
| modal_positive_highest_retained_index | frozen modal | -3 / 300 / 0.00004873361547726218 | -3 / 300 / 0.00004873361547726218 | 0 | false |
| modal_negative_lowest_propagating_or_lossy | frozen modal | -3 / 300 / 0.0002041643359447555 | -3 / 300 / 0.0002041643359447555 | 0 | false |
| modal_negative_proxy_abs_im_beta_gt_abs_re_beta | frozen modal | -3 / 300 / 0.00008082290996470642 | -3 / 300 / 0.00008082290996470642 | 0 | false |
| modal_negative_highest_retained_index | frozen modal | -3 / 300 / 0.00005982074371481139 | -3 / 300 / 0.00005982074371481139 | 0 | false |

R5 的 random residual 约为 6.89e-3–9.56e-3，modal residual 约为 4.87e-5–2.04e-4，top physical residual 约为 8.19e-4。也就是说，DtN correction 把 complete-A 的结果拉回到 whole-endcap F-only 的量级，但 ILU(0) 对 fine-space 的逼近仍比 1e-8 高约 4–6 个数量级。R1 分解、R4 exact Woodbury 和 R5 数值负结论分别证明了不同层次的事实；不能把 R5 写成 Hybrid 模型错误或 Woodbury 公式失败。

### 五套 raw evidence

| 阶段 | summary | solver record |
|---|---|---|
| R1 | [summary](../../../benchmarks/artifacts/task037b/v1_r1_dtn_identity_e2e5767_mpi8.json) | [record](../../../benchmarks/artifacts/task037b/v1_r1_dtn_identity_e2e5767_mpi8/solver_record.json) |
| R2 | [summary](../../../benchmarks/artifacts/task037b/v1_r2_f_only_a9ee706_mpi8.json) | [record](../../../benchmarks/artifacts/task037b/v1_r2_f_only_a9ee706_mpi8/solver_record.json) |
| R3 | [summary](../../../benchmarks/artifacts/task037b/v1_r3_whole_endcap_31d3084_mpi8.json) | [record](../../../benchmarks/artifacts/task037b/v1_r3_whole_endcap_31d3084_mpi8/solver_record.json) |
| R4 | [summary](../../../benchmarks/artifacts/task037b/v1_r4_dtn_woodbury_53faebb_mpi8.json) | [record](../../../benchmarks/artifacts/task037b/v1_r4_dtn_woodbury_53faebb_mpi8/solver_record.json) |
| R5 | [summary](../../../benchmarks/artifacts/task037b/v1_r5_dtn_woodbury_local_inverse_2a2ef3d_mpi8.json) | [record](../../../benchmarks/artifacts/task037b/v1_r5_dtn_woodbury_local_inverse_2a2ef3d_mpi8/solver_record.json) |

R5 source 2a2ef3d37514e4ab30d50209065af84c1dafd59b 的正式结论是 research closeout、numerical negative；H6–H10 not_run，ordinary defaults unchanged，master merge 未授权。
