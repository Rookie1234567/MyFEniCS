# V2-6：同网格 h5 Hybrid direct 对照与内存归因

## 1. 范围与结论

本节只读取已经完成的 h5 Full3D direct 与 h5 Hybrid direct M480 raw run，执行一次离线
比较；没有启动新的 PDE、MPI 或求解。两边自己的 residual、traction、projection、R/T/A、
closure、604 keys 和字段导出均已通过各自 own Gate，但同网格的 primary modal-order
比较失败，因此正式分类是 **`H5_M480_HYBRID_MODEL_FAIL`**。这表示当前证据没有证明两种
离散模型给出相同的物理结果，不表示任一 raw solve 自身失败。

本次是一次经授权的 checker 修复后离线重算：新增的 per-plane field Gate 与 physical
model identity Gate 均按实际 raw 重新裁决；初次负结论保留，数值分类未改变。

本结果不改变 Review V2-3 的网格收敛负结果，也不把 h5 Hybrid 提升为 production
physical authority。按用户后续授权，V2-7 的条件为
`overridden_by_user_for_diagnostic_only`：它可以继续做诊断，但不能把 h5 Hybrid direct
宣称为通过或 accuracy-qualified。

| 项目 | Hybrid h5 M480 | Full3D h5 direct | 口径 |
| --- | --- | --- | --- |
| raw root | [Hybrid raw](../../../results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h5_mpi8__hybrid_direct__mpi8__M480/20260814T113034.312872Z) | [Full3D raw](../../../results/task039_5nm_full3d_direct/task039_5nm_full3d_direct_p6h5_mpi8__full3d_direct__mpi8__Mna/20260814T062500.154546Z) | 已完成 run；只读 |
| physical SHA | `e35907c72ab97069d9ab66958fd00787f98dea08dce1aa6f64c053b7bda46cdb` | 同左 | exact |
| source commit | `e58dfc6cc8d01c39e83f20cafdb52669809d50a9` | `048b9937b4ecdc2c6db87663735718e8525bb926` | source 不同，物理身份相同 |
| dynamic inventory | 604 unique；bottom/top `300/304` | 604 unique；bottom/top `300/304` | exact key set |
| selected planes | `[10,30,60,90,110]` nm | 同左 | coordinates exact |

完整 compact record、worst modal keys、分母和 artifact 身份见
[V2-6 same-grid record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_full3d_same_grid_v1.json)。本次 comparator 输出的
临时 JSON 为 `45388` bytes，SHA256=`5b3e0b6467ad6792ba80baa0410c138770287ae87b8ee786262d72ce4648ef74`；
初次输出 `45125` bytes、SHA256=`14fe7f6e534aeaf522c5312ee6d787a60b5b7522fc7b1abf67a378a6fd306c8a` 仍保留在
record 的 evidence 中。record 只保留摘录，不复制 604 行或 field/matrix 大数组。

## 2. V2-6 Gate 摘要

| Gate | actual | limit | status |
| --- | ---: | ---: | --- |
| physical model identity (Hybrid vs Full3D) | exact SHA `e35907c7...46cdb` | exact equality | pass |
| `R/T/A_balance/A_volume` maximum absolute delta | `4.468492344700259e-06` | `<=1e-5` | pass |
| Hybrid closure absolute | `2.8415027533146286e-06` | `<=1e-5` | pass |
| Full3D closure absolute | `1.3919976282750213e-12` | `<=1e-5` | pass |
| selected E overall relative L2 | `7.299949125251706e-04` | `<=5e-3` | pass |
| selected H overall relative L2 | `6.429897172818461e-04` | `<=1e-2` | pass |
| maximum per-plane E relative L2 | `1.5682443351365644e-03` | `<=1e-2` | pass |
| maximum per-plane H relative L2 | `1.3271949009123452e-03` | `<=5e-2` | pass |
| normal-flux aggregate | `3.518722953879656e-06` | `<=1e-4` | pass |
| all-channel power-weighted aggregate | `8.685769179308791e-05` | `<=1e-4` | pass |
| primary modal-order rows | `9` total; `5` failed | power/amplitude each `<=1e-3` | fail |
| weak modal-order rows | `30` total; `29` failed | diagnostic only | fail / non-veto |
| below weak floor | `565` counted | `<1e-8` | counted only |

The primary set is `max(hybrid_power,full3d_power)>=1e-6`; the weak set is
`1e-8<=max(power)<1e-6`. The all-channel power aggregate uses all 604 keys, including
weak rows:

```math
P_{\mathrm{weighted}} =
\frac{\sum_k |p_{H,k}-p_{F,k}|}
{\sum_k \max(p_{H,k},p_{F,k})}.
```

For each row, power and complex-amplitude relative errors use their own maximum-norm
denominator with `1e-30` floor. The weak set does not veto the primary result; it is retained
because it shows where the order-level discrepancy is concentrated. The primary failure is
therefore the reason for the model-fail classification, while the aggregate itself passes.

## 3. Failed modal gates and worst channels

The table uses `hybrid` and `full3d` labels explicitly. Complex amplitudes are
`[real,imag]`. `abs(delta)` is the numerator; `relative` is the numerator divided by the
listed denominator. These are the worst rows in each failed category, not hand-selected
examples.

| failed category | modal key | hybrid power | Full3D power | power abs / rel (limit) | hybrid amplitude | Full3D amplitude | amplitude abs / rel (limit) |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| primary power | `top,-4,0,s` | `2.277457427053757e-06` | `2.399090101156873e-06` | `1.2163267410311607e-07 / 5.06995023006694e-02` (`<=1e-3`) | `[-2.1999040082677657e-04,-6.626773195301087e-04]` | `[-1.1982354950917974e-04,-7.065531263263072e-04]` | `1.0935485597322696e-04 / 1.5259353501780965e-01` (`<=1e-3`) |
| primary amplitude | `top,-4,0,s` | `2.277457427053757e-06` | `2.399090101156873e-06` | `1.2163267410311607e-07 / 5.06995023006694e-02` (`<=1e-3`) | `[-2.1999040082677657e-04,-6.626773195301087e-04]` | `[-1.1982354950917974e-04,-7.065531263263072e-04]` | `1.0935485597322696e-04 / 1.5259353501780965e-01` (`<=1e-3`) |
| weak power | `bottom,-8,0,s` | `1.4017587020035848e-09` | `2.4467416032725386e-07` | `2.432724016252503e-07 / 9.942709164705881e-01` (`<=1e-3`) | `[7.985501495704993e-06,-1.4657015487872997e-05]` | `[4.006668809420057e-05,-2.1684808153630126e-04]` | `2.0472036958585086e-04 / 9.283585953095696e-01` (`<=1e-3`) |
| weak amplitude | `top,-9,0,s` | `5.351979540282816e-09` | `1.5714511884073508e-08` | `1.0362532343790692e-08 / 6.59424385376558e-01` (`<=1e-3`) | `[6.345928560119753e-06,2.9873917902622752e-05]` | `[2.969369787308809e-05,-4.309230962375788e-05]` | `7.661063040677275e-05 / 1.4639281142714806` (`<=1e-3`) |

The failed primary counts are `5/9`; weak counts are `29/30`. The full-channel order flag is
false, but it is not used to rewrite the primary classification. No selected-field or flux
failure is hidden by the modal-order result.

## 4. Memory and linear-algebra comparison

RSS/PSS/USS below are independent measured process-tree peaks and may occur at different
samples. They are not summed, and object capacities are not added to them. `factor NNZ` for
Full3D h5 is the corrected telemetry value `2597000000`; the raw signed-int32 values remain
negative in the raw record and are not repaired here.

| run | rows | matrix NNZ used / allocated | factor NNZ | RSS / PSS / USS (MiB) | setup/factor (s) | solve (s) | recovery (s) | total numerical (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full3D h5 formal | `337564` | `283210150 / 298136764` | `2597000000` corrected telemetry | `92491.328 / 90440.785 / 90103.539` | `4748.209038` | `2.743420` | `0.840932` cell-condensation recovery; field split not_available | `5330.290272` |
| Hybrid h5 M480 formal | `105244` | `98315590 / 98315590` | `576288232` | `86744.543 / 85040.239 / 84748.199` | `619.352819` | `0.548409` | `0.267349` bottom+top recovery | `3556.791949` |
| Full3D h10 historical | `51796` | `43283050 / 47719324` | `217041864` | `15965.453 / 13932.459 / 13611.352` | `129.608784` | `0.199135` | not_available | `283.036048` |
| Hybrid h10 historical M480 | `18412` | `18261318 / 18261318` | `60473536` | `22785.680 / 21028.330 / 20747.875` | `26.942421` | `0.050998` | `0.051213` bottom+top recovery | `1500.079148` |

The historical h10 rows are resource anchors only. h10 remains
`historical_underresolved_stress_anchor_only`; it is not a Full3D reference, Hybrid physical
authority, accuracy-qualified model, or mesh-scaling basis. The h5 Full3D row is a discrete
authority from V2-2, but V2-6 does not establish h6/h5 convergence or Hybrid equivalence.

## 5. Attribution boundary

“Memory attribution” here means identifying what the records actually measured, not assigning
the whole resident peak to whichever object has the largest byte estimate. A stage marker gives
a lifecycle boundary; it is not itself a stage RSS peak.

| component | evidence status | conservative statement |
| --- | --- | --- |
| QEP / mode basis | measured timing and mode/object records where present; resident causal share not_available | basis and QEP work exist, but no unique RSS/PSS/USS ownership is proven |
| P/T coupling | Hybrid h5 P/T rows/NNZ and matrix estimates measured; Full3D split not_available | do not add P/T estimates to process-tree peak |
| external DtN | assembled rows/NNZ measured in each raw; isolated DtN resident share not_available | matrix identity is known; separate high-water attribution is not |
| augmented matrix | Hybrid h5 rows `105244`, NNZ `98315590`; Full3D assembled rows/NNZ measured | object capacities are evidence, not simultaneous RSS |
| MUMPS | factor NNZ and solver telemetry measured; Full3D h5 signed-int32 overflow retained with corrected display | runtime factor memory ownership is not independently decomposed |
| field recovery | Hybrid h5 bottom/top recovery sum measured; Full3D h5 cell-condensation recovery measured; h10 Full3D not_available | timing is not a memory attribution |
| lifecycle overlap | not_available as a dominant cause | aligned stage rows and raw samples show boundaries, but overlapping allocations cannot be uniquely separated |
| unattributed high-water | global peaks measured; dominant cause not_established | only `UNATTRIBUTED_RUNTIME_OR_ALLOCATOR_HIGH_WATER` is a safe taxonomy label; no stage is declared dominant |

The h5 Hybrid formal artifacts preserve the 18-stage markers, `8968` process-tree samples and
the compact object ledger: [memory stages](../../../results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h5_mpi8__hybrid_direct__mpi8__M480/20260814T113034.312872Z/numerical_output/memory_stages.jsonl),
[process-tree samples](../../../results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h5_mpi8__hybrid_direct__mpi8__M480/20260814T113034.312872Z/numerical_output/process_tree_samples.jsonl),
and [object ledger](../../../results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h5_mpi8__hybrid_direct__mpi8__M480/20260814T113034.312872Z/numerical_output/memory_object_ledger.json).
The h5 Hybrid global peak was RSS/PSS/USS=`86744.543/85040.239/84748.199 MiB`, swap=`0`;
the Full3D h5 global peak was `92491.328/90440.785/90103.539 MiB`, swap=`0`. Neither peak
is reclassified as an object sum.

## 6. Stage and next-step boundary

V2-6 is complete and negative only for the same-grid model comparison. V2-7 is not run in this
turn. Its execution condition is explicitly
`overridden_by_user_for_diagnostic_only`; that override permits the diagnostic continuation,
but cannot convert this record's `H5_M480_HYBRID_MODEL_FAIL` into a Hybrid physical pass.
