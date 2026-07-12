# 3D Stage 4B 光栅 direct

PyCharm 可从小型演示 preset 起步：

```bash
python src/main.py --preset 3d_stage4b_grating_direct_h5
python src/main.py --preset 3d_stage4b_grating_direct_h3
```

这些 `main.py` preset 是易用起点，不等于工作站迭代 benchmark 的 50 x 25 x 140 nm、80 度 target case。正式 target direct 命令冻结在 [`../../benchmarks/cases/021_3d_stage4b_direct/README.md`](../../benchmarks/cases/021_3d_stage4b_direct/README.md)。

## 调用链

`run_3d_cases` -> `solve_maxwell_3d_stage_4b_block_grating` -> `common_3d_case_flow` -> `dtn_port_3d` -> direct PETSc/MUMPS -> `rta_3d`/`postprocess_3d`。

## 运行顺序

1. h=5 先验证几何标签、传播级数量、残差与 RTA。
2. h=3 比较 R/T/A 和近场，不只看残差。
3. h=2 direct 在 14 GB 环境不是默认动作；优先 MPI4 迭代生产档。
4. 任何几何、角度、材料、p、MPI 或 DtN policy 改动都新建记录，不能继承旧资格。

`stage4_dtn_order_policy=auto_propagating` 会覆盖手工过小的 m/n 可视范围，以免漏掉传播级。`diffraction_compute_modal_diagnostic` 默认关闭，因为 official 功率来自 DtN 系统幅值。
