# 010：3D Stage 1 空气盒

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `010_3d_stage1_airbox` / manifest/record `l1_3d_stage1` |
| 2. 证明 | 3D H(curl)、解析平面波、MPI2 direct 和并行输出可运行 |
| 3. 不证明 | Floquet、PML、Fresnel、DtN、光栅 |
| 4. 物理问题 | 均匀空气盒平面波 |
| 5. 几何 | 10x10x10 nm smoke |
| 6. 材料 | n_air=1 |
| 7. 波长/角度/偏振 | runner Stage1 normal 默认 |
| 8. 边界 | 解析场边界；无 Floquet/PML |
| 9. FE/网格 | N1curl p1，h5 nm，MPI2 |
| 10. Task38 input | [`input/official/stage1_airbox_smoke_mpi2.dat`](../../../input/official/stage1_airbox_smoke_mpi2.dat)（benchmark MPI2） |
| 11. 参数表 | record metadata + quick start 20 |
| 12. 精确命令 | `python scripts/run_case.py input/official/stage1_airbox_smoke_mpi2.dat` |
| 13. 调用链 | run_3d_cases -> Stage1 wrapper -> common flow |
| 14. 理论 | Maxwell 强/弱式与 Stage ladder |
| 15. 求解器 | MPI2 PETSc/MUMPS direct |
| 16. RTA 恒等式 | 不作为 Stage1 Gate；检查 Poynting 方向 |
| 17. 输出 | E/H error、residual、RSS、fields |
| 18. Gates | residual、relative E/H error、direction cosine |
| 19. Canonical 结果 | residual `1.3947e-16`，direction cosine 1 |
| 20. Records | [`../../records/3d_stage1_mpi2_smoke.json`](../../records/3d_stage1_mpi2_smoke.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/level1/3d_stage1` ignored |
| 22. 限制 | 极粗网格 smoke，E/H error 不代表收敛阶研究 |

## 物理问题

均匀空气盒中规定解析平面波边界，求解 3D H(curl) Maxwell 方程并与解析 E/H 比较。该最小 case 隔离 mesh、Nedelec、complex PETSc、MPI direct 和并行场输出，不引入 Floquet、PML 或端口。

## 参数说明

`config.json` 冻结 10 x 10 x 10 nm、p1、h5 和 MPI2。`expected.json` 给出 residual、E/H error 与 Poynting direction Gate。粗网格的绝对误差只用于检测回归，不是收敛阶结论。

## PyCharm

本 case 使用显式的 [`input/official/stage1_airbox_smoke_mpi2.dat`](../../../input/official/stage1_airbox_smoke_mpi2.dat)，其中保留 canonical benchmark 所需 MPI2。不要依赖 `src/main.py` 的无参行为；MPI2 命令通过本目录 `run.sh` 或上面的 public command 运行。

## CLI 或测试

```text
python scripts/run_case.py input/official/stage1_airbox_smoke_mpi2.dat
sh benchmarks/cases/010_3d_stage1_airbox/run.sh
python benchmarks/check_benchmarks.py --no-write
```

## 代码路径与理论

```text
run_3d_cases -> run_stage1_airbox_3d_case
-> run_prepared_3d_case_flow
-> common_3d_forms::_build_variational_forms
-> common_3d_solve direct
-> postprocess_3d::save_airbox_3d_fields
```

强式、弱式和 Nedelec 原因见 [`../../../notes/theory/maxwell_strong_weak_and_fem.md`](../../../notes/theory/maxwell_strong_weak_and_fem.md)。

## 当前证据

`records/canonical_reference.json` 用 SHA-256 指向顶层 `3d_stage1_mpi2_smoke.json`，防止 case 文档与 canonical record 漂移。记录 residual 为 `1.3947e-16`，Poynting 方向余弦为 1，并保存 MPI2/容器 provenance。

## 结果解释

先看真残差，再看 E/H relative error 和方向余弦。方向正确但幅值误差较大通常是粗网格；residual 小但方向错误则是相位、curl/H 重构或边界符号回归。

## 限制

Stage1 不产生可用于光栅的 R/T/A；它只证明基础 3D 离散和运行环境。新增后端应先通过本 case 再进入 Floquet/端口阶段。
