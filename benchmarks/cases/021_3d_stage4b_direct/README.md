# 021：3D Stage 4B Target Direct

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `021_3d_stage4b_direct` / manifest `l3_direct_h5/h3` |
| 2. 证明 | target p2 h5/h3 MPI4 MUMPS direct 可解并给出 official RTA |
| 3. 不证明 | h2 在 14 GB 可 direct、h1.5 或任意几何 |
| 4. 物理问题 | 3D EUV 周期 Si block grating |
| 5. 几何 | period 50x25 nm；block 17x25x120；air 130；substrate 10 |
| 6. 材料 | air + complex Si substrate/grating |
| 7. 波长/角度/偏振 | 13.5 nm；theta 80、phi 0；s |
| 8. 边界 | x/y Floquet；auto-propagating auxiliary DtN |
| 9. FE/网格 | N1curl p2；h5/h3；MPI4 |
| 10. PyCharm preset | `3d_target_grating_direct_h5` / `3d_target_grating_direct_h3`，与 canonical target 工厂对齐 |
| 11. 参数表 | [`config.json`](config.json)、record metadata、`config_3d::target_stage4_config` |
| 12. 精确命令 | `sh benchmarks/cases/021_3d_stage4b_direct/run.sh h5` 或 `h3` |
| 13. 调用链 | run_3d_cases -> Stage4B -> common flow -> dtn_port_3d |
| 14. 理论 | Stage ladder、DtN、direct solver、RTA |
| 15. 求解器 | MPI4 PETSc preonly+LU+MUMPS |
| 16. RTA 恒等式 | `R+T+A_volume≈1`；h5/h3 与迭代交叉 |
| 17. 输出 | full fields/artifact + lightweight direct record |
| 18. Gates | residual、RTA closure、direct/iterative delta、RSS |
| 19. Canonical 结果 | h5 RSS 2.293 GB；h3 RSS 8.18 GB，数值见 records |
| 20. Records | [`direct_p2_h5_mpi4.json`](../../records/direct_p2_h5_mpi4.json)、[`direct_p2_h3_mpi4.json`](../../records/direct_p2_h3_mpi4.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/direct` ignored |
| 22. 限制 | h2 direct 仅 reviewed historical reference，非 Task28 rerun |

## 物理问题

目标模型是 50 x 25 x 140 nm EUV 单胞，17 x 25 x 120 nm complex-Si block，13.5 nm、theta 80 度、phi 0、s polarization。x/y 双 Floquet，z 上下使用 auto-propagating auxiliary DtN。

## 参数说明

`src/common/config_3d.py::target_stage4_config(degree=2,h_nm=...)` 是 target 的唯一物理配置来源。Case021 `config.json`、main target presets、Case031 iterative runtime 和 tests 都引用或逐字段校验它。demo presets 的 100 x 100 nm 几何不得与本 case records 比较。

## PyCharm

普通 PyCharm Python Run 只能单进程，不是 canonical MPI4。可用 target preset做参数/入口检查；正式复现应创建 External Tool，Program 指向 Docker/WSL shell，Arguments 调用本目录 `run.sh h5` 或 `h3`，Working directory 为仓库根。

`h3` 属于高资源 direct；运行前检查 WSL/Docker 内存。脚本明确禁止 h2，防止在 14 GB 环境误启动已知超预算 direct factorization。

## CLI 或测试

```text
sh benchmarks/cases/021_3d_stage4b_direct/run.sh h5
sh benchmarks/cases/021_3d_stage4b_direct/run.sh h3
python benchmarks/check_benchmarks.py --no-write
```

## 代码路径与理论

`run_3d_cases -> Stage4B wrapper -> common_3d_case_flow -> dtn_port_3d -> MUMPS direct -> rta_3d`。配置身份见 [`../../../notes/reference/code_walkthrough/01_main_and_runner_dispatch.md`](../../../notes/reference/code_walkthrough/01_main_and_runner_dispatch.md)，direct 生命周期见 [`../../../notes/reference/code_walkthrough/30_direct_solver_profiles.md`](../../../notes/reference/code_walkthrough/30_direct_solver_profiles.md)。

## 当前证据

| h/nm | 身份 | peak RSS | 备注 |
|---:|---|---:|---|
| 5 | canonical MPI4 direct | 2.293 GB | 与 iterative 交叉 |
| 3 | canonical MPI4 direct | 8.18 GB | 与 iterative 交叉 |
| 2 | reviewed reference | 约 20.533 GB | 本 Task28 未重跑 |

本目录三个 reference JSON 用 SHA-256 固定顶层 records，checker 会检测漂移。

## 结果解释

除真残差外必须检查 R/T/A closure、物理模型 metadata、MPI/factor backend 和 total peak RSS。direct/iterative h5/h3 差异同时通过 Gate，才说明凝聚迭代器没有改变物理解。

## 限制

本 case 只资格化 frozen target 的 h5/h3 direct。h2 direct 在当前资源上不是生产入口；OOC/BLR 也不会自动获得同等资格。
