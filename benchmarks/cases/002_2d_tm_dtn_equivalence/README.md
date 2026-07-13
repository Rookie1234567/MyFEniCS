# 002：2D TM DtN 等价性

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `002_2d_tm_dtn_equivalence` / manifest `l1_2d_zero_contrast` |
| 2. 证明 | 同一离散问题的 explicit 与 auxiliary 完整 solve 在场、R/T/A 和残差上等价 |
| 3. 不证明 | MPI nonlocal DtN、任意高 order 或真实材料收敛 |
| 4. 物理问题 | 2D 零材料对比 total-field port |
| 5. 几何 | period 10 nm，air/substrate 各 5 nm，虚拟 grating 5x2 nm |
| 6. 材料 | 三个区域 n=1 |
| 7. 波长/角度/偏振 | 13.5 nm、默认 15 度、TM |
| 8. 边界 | x-Floquet；上下 Fourier-DtN |
| 9. FE/网格 | N1curl p1，h2 nm |
| 10. PyCharm preset | `2d_tm_dtn_auxiliary_smoke` 可交互运行；canonical 对比用本目录 `run.sh` |
| 11. 参数表 | [`config.json`](config.json) 与 [`expected.json`](expected.json) |
| 12. 精确命令 | `SOURCE_COMMIT=<sha> IMAGE_DIGEST=sha256:<digest> sh benchmarks/cases/002_2d_tm_dtn_equivalence/run.sh` |
| 13. 调用链 | run_cases -> solve_port_maxwell -> auxiliary DtN -> power_metrics |
| 14. 理论 | `dtn_modal_ports_and_condensation.md` |
| 15. 求解器 | serial constrained sparse/direct |
| 16. RTA 恒等式 | `R+T=1`；auxiliary 与 trace R/T 差接近舍入误差 |
| 17. 输出 | Level1 artifact + lightweight record |
| 18. Gates | residual、Floquet error、R+T、aux/trace difference |
| 19. Canonical 结果 | field relative delta `2.771e-15`，R/T/A 最大差 `1.221e-15` |
| 20. Records | [`records/explicit.json`](records/explicit.json)、[`records/auxiliary.json`](records/auxiliary.json)、[`records/comparison.json`](records/comparison.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/cases/002/` ignored |
| 22. 限制 | 证明当前 serial p1 零对比离散等价，不外推 MPI、任意 order 或物理收敛 |

## 物理问题

在 10 x 10 nm 单胞中令 air/substrate/grating 全部 `n=1`，使用 13.5 nm、15 度 TM 入射和上下 Fourier-DtN。两次运行共享网格、函数空间、Floquet 约束和 RHS，只改变 `port_dtn_assembly`。

## 参数说明

`config.json` 是 canonical harness 的唯一输入。`expected.json` 冻结 residual、field relative difference、R/T/A absolute difference 和 lossless closure 容差。任何几何、阶次、h 或 order 改动都应生成 candidate artifact，不能覆盖本目录 records。

## PyCharm

单次 auxiliary 调试可选择 `2d_tm_dtn_auxiliary_smoke`。要复现完整对比，在 PyCharm 新建 Module 配置 `benchmarks.run_2d_canonical`，参数为 `--case 002`，Working directory 设为仓库根目录；输出目录先指向 `benchmarks/artifacts/cases/002/candidate_records`。

## CLI 或测试

```text
SOURCE_COMMIT=<sha> IMAGE_DIGEST=sha256:<digest> sh benchmarks/cases/002_2d_tm_dtn_equivalence/run.sh
python benchmarks/check_benchmarks.py --no-write
```

runner 通过 in-memory observer 比较 full FE coefficient array，避免 ParaView 插值掩盖差异。

## 代码路径与理论

```text
run_2d_canonical -> solve_port_maxwell::run_port_case (explicit)
                 -> solve_port_maxwell::run_port_case (auxiliary)
                 -> power_metrics boundary/auxiliary RTA
```

矩阵关系见 [`../../../notes/reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md`](../../../notes/reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md) 和 [`../../../notes/theory/dtn_modal_ports_and_condensation.md`](../../../notes/theory/dtn_modal_ports_and_condensation.md)。

## 当前证据

| 指标 | explicit | auxiliary |
|---|---:|---:|
| FE/aux DoF | 139/0 | 139/2 |
| matrix rows/nnz | 139/727 | 141/673 |
| reduced rows/nnz | 133/721 | 135/667 |
| true residual | 2.168e-15 | 1.867e-15 |
| elapsed/s | 8.334 | 2.811 |

两者 `R=0.0004776548`、`T=0.9995223452`，各自 lossless closure 为机器精度。

## 结果解释

这里的核心 Gate 是 full field 和 R/T/A 同时一致。仅比较 auxiliary 与 trace 的功率不够，因为矩阵或 RHS 错误可能在同一错误场上产生相似后处理。

## 限制

该 case 是小型 serial algebra/physics bridge，不证明 auxiliary 对所有高阶或近 Rayleigh order 都优于 explicit，也不证明网格收敛。
