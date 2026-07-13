# 001：2D TM PML + Floquet

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `001_2d_tm_pml_floquet` |
| 2. 证明 | TM Nedelec scattered-field、x-Floquet、上下 PML 可联合运行 |
| 3. 不证明 | 任意 PML 参数、EUV 光栅网格收敛或生产迭代 |
| 4. 物理问题 | 二维周期矩形光栅散射场 |
| 5. 几何 | preset 中 600 nm 周期、850/350 nm air/substrate |
| 6. 材料 | air 1、substrate/grating 1.45，默认无损 |
| 7. 波长/角度/偏振 | 633 nm、15 度、TM |
| 8. 边界 | x-Floquet；y 上下 PML |
| 9. FE/网格 | N1curl p1，target h80 nm，triangle |
| 10. PyCharm preset | `2d_tm_pml_floquet_smoke` |
| 11. 参数表 | [`../../../notes/quick_start/10_2d_pml_floquet.md`](../../../notes/quick_start/10_2d_pml_floquet.md) |
| 12. 精确命令 | `python src/main.py --preset 2d_tm_pml_floquet_smoke` |
| 13. 调用链 | main -> run_cases -> solve_vector_maxwell -> power_metrics |
| 14. 理论 | Maxwell、Floquet、PML 三篇规范理论 |
| 15. 求解器 | serial manual reduction + SuperLU（preset） |
| 16. RTA 恒等式 | 无损目标检查 `R+T`；PML 不计入 A_volume |
| 17. 输出 | ordinary `results/` summary/log/VTU/power JSON |
| 18. Gates | complex mode；residual；Floquet mismatch；PML 扫描；R/T 稳定 |
| 19. Canonical 结果 | 当前未冻结 machine-readable record |
| 20. Records | 无；晋级时新增 `records/2d_tm_pml_floquet.json` |
| 21. Artifact 规则 | `benchmarks/artifacts/001/`，不提交 |
| 22. 限制 | 当前 `test-backed`；不能用 preset 存在宣称生产精度 |

## 物理问题

这是二维 x 周期矩形结构的 TM scattered-field smoke。未知量为面内 `(E_x,E_y)`，左右边界满足 Bloch 相位，上下空气/基座延拓为 PML。背景场与目标材料之差只在物理 cell 形成体源。

## 参数说明

`config.json` 冻结教程用几何、材料、波长、角度、N1curl p1 和 h80 nm。`expected.json` 声明该 case 是 `test_backed`，重点是 complex build、残差、Floquet mismatch 和 PML 路径；它没有冻结 R/T 精度值。

PML 参数改变会同时影响吸收强度、离散误差和计算域尺寸。用户自定义 case 时应一次只改厚度、`pml_alpha` 或 h，并观察物理区场和 R/T 是否稳定。

## PyCharm

打开 `src/main.py`，选择 `2d_tm_pml_floquet_smoke`。Working directory 必须是仓库根目录，解释器必须是 complex DOLFINx 环境。普通单进程 Run 与本 case 的 serial manual 身份一致。

## CLI 或测试

```text
sh benchmarks/cases/001_2d_tm_pml_floquet/run.sh
python src/main.py --preset 2d_tm_pml_floquet_smoke
```

`run.sh` 把完整场写入 gitignored `benchmarks/artifacts/cases/001`，不会生成或覆盖 canonical record。

## 代码路径与理论

```text
main -> run_cases -> solve_vector_maxwell::run_case
-> floquet_constraint::build_floquet_constraints
-> pml::top_pml_tensors/bottom_pml_tensors
-> power_metrics::compute_power_metrics
```

弱式、约束和 PML 张量分别见 [`../../../notes/theory/maxwell_strong_weak_and_fem.md`](../../../notes/theory/maxwell_strong_weak_and_fem.md)、[`../../../notes/theory/floquet_periodicity.md`](../../../notes/theory/floquet_periodicity.md) 与 [`../../../notes/theory/pml_robin_and_open_boundaries.md`](../../../notes/theory/pml_robin_and_open_boundaries.md)。

## 当前证据

当前没有 machine-readable physical record。代码路径由单元测试、Quick Start 和 case-contained command 支持；这证明入口、装配和输出契约可运行，不证明 h80 nm 或默认 PML 已对目标物理量收敛。

## 结果解释

先检查 `reduced_linear_residual` 和 `floquet_mismatch_total_dof`，再看 PML 区场是否向外衰减。`A_volume` 只积分物理有损材料，不把 PML 数值耗散当作材料吸收。

## 限制

晋级为 recorded case 前，需要至少三组 h 与两组 PML 厚度/强度，冻结 R/T 稳定性和物理区场差。当前目录存在不等于该参数组可用于工程结论。
