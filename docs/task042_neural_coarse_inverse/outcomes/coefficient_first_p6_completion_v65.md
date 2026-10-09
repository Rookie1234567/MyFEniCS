# V65：完整系数先保存，再完成独立原式与P6场

| 对象 | 实际结果 | 边界 |
|---|---|---|
| Q新系数积分 | 24单元、保存p5完整作用及P6两列通过 | 不改变弱式，不授整case加速 |
| K checkpoint | 323539200项，16成员/6507698292B，独立资格另存 | 未缩放完整体，不是factor或原尺寸许可 |
| P6完整场 | 981180行、828模式；formal 2.32584924e-10 PASS | 独立direct1e−10 FAIL |
| 物理功率 | R=0.0762185598、T=0.905665158、A_volume=0.0181162824 | 能量2.53652654e-12，单离散官方量 |
| B/P6全域散射E/H | 0.000405047017/0.000410694274 | 1e−4 FAIL；不能用total或能量替代 |
| 240点最大增量 | 0.00117438869 | 1e−4 FAIL |
| 本次成功链/prepared-start | 14748.453748/2508.029019s | q包/编译缓存口径明确，非完全fresh配平 |
| 当前 sampled树峰/gap | 88.523769GiB/1.369836s | 不是连续硬峰；最终全集见最终费用 |

系数先收缩把“逐几何变换整张基表”改成“先组合系数再变换场”，生产仍是标准UFL完整tetra弱式。本批全部内部进入全局系统，只压缩周期冗余，没有静态凝聚。保存体K使下游可恢复；本次只构建一次、numeric一次、完整求解一次，返回向量以后没有重factor。

## 互斥阶段明细

| 实测阶段 | 秒 |
|---|---|
| PREPARE/tetra_mesh_materials_full_periodic_space | 17.5609093 |
| PREPARE/checked_readonly_V64_q47_q63 | 19.7663586 |
| PREPARE/body_JIT_form | 0.00373008894 |
| PREPARE/body_PETSc_assembly | 12036.1879 |
| PREPARE/standard_UFL_FFCx_full_uncondensed_body | 12036.1943 |
| PREPARE/body_native_CSR_copy | 9.67456047 |
| PREPARE/body_MPC_Hermitian_pullback | 30.7953181 |
| PREPARE/atomic_unscaled_body_CSR_checkpoint_IO | 39.4026441 |
| SOLVE/tetra_mesh_materials_full_periodic_space | 19.4235068 |
| SOLVE/readonly_body_K_checkpoint_identity_and_reopen | 35.5101033 |
| SOLVE/checked_readonly_V64_q47_q63 | 20.2776726 |
| SOLVE/two_standard_UFL_PUBLIC_BASIX_operator_pairs | 75.6689622 |
| SOLVE/h_sparse_symbolic_capacity | 18.0280018 |
| SOLVE/h_bounded_numeric_factor | 1406.86804 |
| SOLVE/full_uncondensed_tetra_direct_solve | 46.1529939 |
| SOLVE/independent_COEFFICIENT_FIRST_PUBLIC_BASIX_body_q17_triangle63 | 50.3111879 |
| SOLVE/full_physical_E_H_curl_240_points | 0.948672742 |
| SOLVE/complete_tetra_volume_and_analytic_q23_q31 | 611.06856 |
| SOLVE/all828_complex_channel_powers_and_output | 0.388437758 |

其中 `standard_UFL_FFCx_full_uncondensed_body` 是JIT/form与PETSc assembly父段，与其子段不相加。准备矩阵IO、原子保存、共享MPC拉回、重开验证、symbolic/numeric、全部独立审核/场输出和清场都支付。本次完整成功链14748.453748s；含最终独立VERIFY的同P6账15023.402500s；V64失败15056.335016s保持。prepared-start不抵销新K准备费用，历史费用不清零。

## 完整增量与物理尺度

| 场 | 全域相对增量 | 240点相对增量 | 平方差 / P6平方范数 | 1e−4 |
|---|---|---|---|---|
| E_total | 5.81857645e-05 | 6.26211352e-05 | 1.31949836e-07 / 38.9740345 | PASS |
| H_total | 5.89962028e-05 | 0.000169896141 | 1.35626479e-07 / 38.9669459 | FAIL |
| curl_total | 5.89962028e-05 | 0.000169896141 | 1.09271812e-05 / 3139.49666 | FAIL |
| E_scattered | 0.000405047017 | 0.000432840746 | 1.31949836e-07 / 0.804262794 | FAIL |
| H_scattered | 0.000410694274 | 0.00117438869 | 1.35626479e-07 / 0.804094688 | FAIL |
| curl_scattered | 0.000410694274 | 0.00117438869 | 1.09271812e-05 / 64.784461 | FAIL |

完整828参考面复振幅3.92351323e-05、逐mode功率6.28022693e-08通过，RTA/体吸收最大差6.52493643e-08；两场能量通过，整体增量仍FAIL。共同原场分别积分、原分母不变、没有把散射误差除以更大的total范数。新场是有限参照候选，不假定真值或连续收敛。

## 成本目标和下一步

原尺寸0.7nm完整三维准确性、2TB/48h及NN20均未资格。本次没有NN训练或PC实验。当前体数值装配约81.61%成功链；factor+solve约9.85%，但该有限链不是最强同精度传统基线，不能据此直接安排网络或宣布20%机会。未来仍要证明完整正确性、全部新数据/训练/推理/清场审核成本及同时峰条件；本核只提供独立matrix-free作用的小接口，没有资格化全局迭代/可扩展PC。

唯一下一建议：以冻结B/P6逐cell差分为唯一新依据，设计并先核算一次有界相容局部h参照的实际闭合网格；在新的完整合同下判断未闭合的散射场分辨与跨阶差异，当前不启动新求解。

[完整回应](../response_v65.md) · [物理](records/complete_physics_v65.json) · [分子分母](records/paired_comparison_v65.json) · [分区](records/paired_regions_v65.json) · [K](records/body_checkpoint_v65.json) · [最终账](records/resource_costs_final_v65.json) · [source](records/source_bindings_v65.json) · [交付](records/delivery_index_v65.json)。不通知邻窗，不merge或自动下一轮。
