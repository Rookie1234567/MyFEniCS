# 3D MUMPS OOC / BLR direct fallback 教程

## 1. 功能与物理图景

OOC 把部分 MUMPS 因子写到磁盘以降低内存压力；BLR 用 block low-rank 压缩因子。两者仍是 direct/inexact factorization 路线，不是 matrix-free iterative solver。

## 2. 当前能力状态

```text
default = supported ordinary direct baseline
mumps_ooc = experimental direct fallback
mumps_blr = experimental compressed direct fallback
new target records in V3 = none
```

## 3. 运行前提

PETSc 必须实际链接 MUMPS；OOC 需要足够快且有空间的 scratch。先用 demo h5，不要把 preset 存在误认为 target production qualification。

## 4. Retained research/history presets

```text
`src.main --preset 3d_stage4b_demo_mumps_ooc` 或
`src.main --preset 3d_stage4b_demo_mumps_blr` 可显式 replay；没有无参默认。
```

名称包含 `demo`，因为当前配置不是 Case021 target。

## 5. `main.py` 修改位置

`Stage4GratingInputs3D.petsc_direct_solver_profile` 选择 `default`、`mumps_ooc` 或 `mumps_blr`；不要手改底层 solver 文件。

## 6. 参数块

```python
replace(
    STAGE4_GRATING_3D,
    petsc_direct_solver_profile="mumps_blr",
    petsc_ksp_view=True,
    petsc_log_view=True,
    petsc_extra_options=(("mat_mumps_cntl_7", 1.0e-5),),
)
```

## 7. 参数含义

| 参数 | 作用 |
|---|---|
| `mumps_ooc` | MUMPS out-of-core direct factor |
| `mumps_blr` | `ICNTL(35)=1` BLR activation |
| `mat_mumps_cntl_7` | BLR drop tolerance |
| `mat_mumps_icntl_14` | workspace growth |
| `petsc_ksp_view/log_view` | 配置和性能诊断 |

## 8. Qualification 边界

Case030 保持 `experimental/test_backed/historical`。没有新的 target OOC/BLR record，也没有证明对所有 MPI 数和矩阵稳定。

## 9. CLI 等价命令

PyCharm 的 retained replay 配置继续使用显式 `--preset`。

```text
python src/main.py --preset 3d_stage4b_demo_mumps_ooc
python src/main.py --preset 3d_stage4b_demo_mumps_blr
```

先用 `--list-presets --verbose` 查看资源身份。

## 10. 真实调用链

```text
main preset
-> run_3d_cases parser
-> SimulationConfig3D.petsc_direct_solver_profile_requested
-> common_3d_solve::_prepare_direct_lu_options_for_comm
-> PETSc KSP preonly + PC LU + MUMPS
```

## 11. 输出和诊断

`solver_log.txt`、KSP view、PETSc log 和 MUMPS 控制参数是主证据。OOC scratch 不进入 Git；记录 scratch 位置、factor/setup time、RSS 和磁盘峰值。

## 12. ParaView

OOC/BLR 只改变线性求解，不应改变同一问题的场。用相同色标对比 default 与 fallback，并以 R/T/A delta 和真残差为准。

## 13. 成功 Gate

```text
KSP = preonly, PC = lu, factor = mumps
true residual 通过
R/T/A 与 default 在阈值内
RSS/setup/OOC disk 被记录
BLR 参数完整
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| 说 BLR 迭代了 N 步 | 概念错误；它是因子压缩 |
| OOC 没降 RSS | 分析/因子阶段或 scratch 配置不匹配 |
| BLR residual 变差 | drop tolerance 太松 |
| preset 跑不动 | 镜像不含 MUMPS 或资源不足 |

## 15. 扩展到 target

先在 h5 target 上用独立 artifact 和 candidate record 对比 default/OOC/BLR；通过 residual、RTA delta、RSS、时间和 scratch Gate 后，才考虑提升 Case030 证据状态。

## 16. 链接

- 理论：[`../theory/direct_solvers_and_factorization.md`](../theory/direct_solvers_and_factorization.md)
- 代码：[`../reference/code_walkthrough/30_direct_solver_profiles.md`](../reference/code_walkthrough/30_direct_solver_profiles.md)
- Case030：[`../../benchmarks/cases/030_mumps_ooc_blr/README.md`](../../benchmarks/cases/030_mumps_ooc_blr/README.md)
