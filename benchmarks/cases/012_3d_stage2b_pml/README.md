# 012：3D Stage 2B PML

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `012_3d_stage2b_pml` |
| 2. 证明 | z-PML tensor 与双 Floquet/3D flow 可组合运行 |
| 3. 不证明 | 任意 PML 参数的低反射或 Stage4 production 精度 |
| 4. 物理问题 | 周期空气盒 correction + 上下 PML |
| 5. 几何 | Stage2 preset，PML 各 250 nm |
| 6. 材料 | air continuation |
| 7. 波长/角度/偏振 | 633 nm，normal smoke |
| 8. 边界 | x/y Floquet，z PML |
| 9. FE/网格 | N1curl p1，h300 nm smoke |
| 10. Task38 input | [`input/smoke/3d_stage2b_pml_smoke.dat`](../../../input/smoke/3d_stage2b_pml_smoke.dat) |
| 11. 参数表 | quick start 22 |
| 12. 精确命令 | `python scripts/run_case.py input/smoke/3d_stage2b_pml_smoke.dat` |
| 13. 调用链 | Stage2B -> pml_3d/common_3d_forms -> common flow |
| 14. 理论 | `pml_robin_and_open_boundaries.md` |
| 15. 求解器 | ordinary direct |
| 16. RTA 恒等式 | PML 不计 A_volume；本 case 主要看衰减/误差 |
| 17. 输出 | PML tag/field decay/reference error |
| 18. Gates | PML tensor unit test、decay、physical-region error、parameter scan |
| 19. Canonical 结果 | 尚无冻结 record |
| 20. Records | 无 |
| 21. Artifact 规则 | `benchmarks/artifacts/012/` ignored |
| 22. 限制 | experimental；旧 Stage2 数据有精度限制，能力矩阵不得写 recommended |

## 物理问题

在 Stage2A 双 Floquet 空气盒的 z 上下增加 complex-coordinate PML，验证变换张量、材料延拓、边界组合和并行装配可联合运行。

## 参数说明

`config.json` 采用 633 nm、p1、粗 h300 nm 和上下各 250 nm PML。这个参数组是 smoke，而非低反射最优值。`expected.json` 明确状态 `experimental/not_verified_accuracy`。

## PyCharm

使用 [`input/smoke/3d_stage2b_pml_smoke.dat`](../../../input/smoke/3d_stage2b_pml_smoke.dat)。修改时同时记录 physical height、PML thickness、`pml_alpha` 和 h；否则无法判断衰减变化来自物理长度还是离散。

## CLI 或测试

```text
sh benchmarks/cases/012_3d_stage2b_pml/run.sh
python scripts/run_case.py input/smoke/3d_stage2b_pml_smoke.dat
python -m unittest src.test.test_02_pml_tensor src.test.test_07_pml_airbox_decay
```

## 代码路径与理论

```text
Stage2B wrapper -> build_airbox_mesh_3d
-> floquet_3d::build_double_floquet_mpc
-> pml_3d::z_pml_tensors
-> common_3d_forms::_build_variational_forms
```

公式见 [`../../../notes/theory/pml_robin_and_open_boundaries.md`](../../../notes/theory/pml_robin_and_open_boundaries.md)。

## 当前证据

PML scalar/diagonal tensor 有单测，路径与场衰减有 smoke；当前没有冻结跨 h/PML 参数的 machine-readable record，因此 capability 保持 experimental。

## 结果解释

同时检查真残差、physical/PML cell tags、PML 区场包络、物理区解析误差和参数变化稳定性。PML 数值耗散不计入 `A_volume`。

## 限制

单次场向外减小不等于反射足够小。晋级需要 PML 厚度、alpha 和网格三维扫描，并对物理区场/R/T 设稳定阈值。
