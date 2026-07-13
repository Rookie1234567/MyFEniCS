# 031：工作站 MPI4 迭代生产档

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `031_workstation_iterative` / manifest `l3_iterative_h5/h3/h2` |
| 2. 证明 | target p2 h5/h3/h2 在 14 GB WSL2 限定环境完整收敛并输出 official RTA |
| 3. 不证明 | h1.5、任意角度/材料/几何、严格 mesh-independent |
| 4. 物理问题 | 与 case021 相同 3D EUV Si block grating |
| 5. 几何 | 50x25x140 nm；17x25x120 nm block |
| 6. 材料 | air + complex Si substrate/grating |
| 7. 波长/角度/偏振 | 13.5 nm；80/0 度；s |
| 8. 边界 | 双 Floquet + auto-propagating auxiliary DtN |
| 9. FE/网格 | N1curl p2，h5/h3/h2，MPI4 |
| 10. PyCharm preset | 无；通过 PyCharm External Tool 显式启动 Docker/WSL `mpiexec -n 4` |
| 11. 参数表 | [`../../configs/workstation_p2.json`](../../configs/workstation_p2.json) |
| 12. 精确命令 | 各 record 的 `canonical_rerun_command`；批量 `sh benchmarks/scripts/run_level3_iterative.sh` |
| 13. 调用链 | iterative runner -> stage4_runtime -> condensation -> two-level PC -> RTA |
| 14. 理论 | iterative PC、DtN condensation、RTA |
| 15. 求解器 | right FGMRES(100)+75D coarse+16 shifted slabs+sm2 |
| 16. RTA 恒等式 | full residual 后 `R+T+A_volume≈1`，h5/h3 对 direct |
| 17. 输出 | parameters/progress/record + ignored full RTA artifacts |
| 18. Gates | qualified、reason>0、三残差、coarse、condition、RSS、RTA、identity |
| 19. Canonical 结果 | h5 1201 iter；h3 993；h2 1804；h2 RSS 13.080 GB |
| 20. Records | [`h5`](../../records/workstation_p2_h5_mpi4.json)、[`h3`](../../records/workstation_p2_h3_mpi4.json)、[`h2`](../../records/workstation_p2_h2_mpi4.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/iterative` ignored |
| 22. 限制 | 资格严格等于 physical_model+resolved_config；任何偏离 experimental |

## 物理问题

与 Case021 完全相同的 3D EUV target，但先把 80 个 DtN auxiliary unknowns 精确凝聚，随后用 MPI4 right FGMRES + physical-slab two-level PC 求解 44k 至 615k FE unknowns。

## 参数说明

[`../../configs/workstation_p2.json`](../../configs/workstation_p2.json) 冻结 4 ranks、16 slabs、overlap 0.25、shifted-F ILU1、sm2、75D coarse、restart 100、rtol `1e-6`。本目录 `config.json` 只描述 case wrapper；runtime 会把任何偏离写入 `qualification_deviations` 并标为 experimental。

## PyCharm

普通 Python Run 的 MPI size=1 不具资格。推荐 External Tool：

```text
Program: Docker/WSL shell executable
Arguments: mpiexec -n 4 python -m benchmarks.run_workstation_iterative
           --config benchmarks/configs/workstation_p2.json
           --h-nm 5 --record benchmarks/artifacts/cases/031/candidate_records/h5.json
Working directory: repository root
Environment: qualified complex DOLFINx image
```

不要把 candidate record 路径指向顶层 canonical record。完整 Windows/PyCharm 字段见 [`../../../notes/quick_start/40_3d_workstation_iterative.md`](../../../notes/quick_start/40_3d_workstation_iterative.md)。

## CLI 或测试

```text
sh benchmarks/cases/031_workstation_iterative/run.sh h5
sh benchmarks/cases/031_workstation_iterative/run.sh h3
sh benchmarks/cases/031_workstation_iterative/run.sh h2
```

本 Task28 只审计既有 h5/h3/h2 records，没有重跑 h2。

## 代码路径与理论

`run_workstation_iterative -> stage4_runtime -> condensed_dtn -> physical_slab_two_level -> FGMRES -> auxiliary recovery -> official RTA`。对象尺寸与生命周期见 [`../../../notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md`](../../../notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md)。

## 当前证据

| h/nm | FE DoF | iterations | full residual | total peak RSS | time/s |
|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | 9.839e-7 | 1.991 GB | 130.8 |
| 3 | 198,438 | 993 | 9.933e-7 | 5.082 GB | 411.8 |
| 2 | 615,108 | 1,804 | 9.997e-7 | 13.080 GB | 2,538.8 |

三个 reference 文件用 SHA-256 固定顶层 records；checker 同时验证 config、coarse rank/condition、三残差、RTA、RSS 和 h5/h3 direct delta。

## 结果解释

`ksp_reason>0` 只是第一关；reported、condensed true 和 full augmented residual 必须一致。RTA 只在 full residual 通过后计算。RSS 使用所有 rank 的总 peak 字段，不拿单 rank RSS 代替工作站需求。

## 限制

当前 production level 只属于 frozen target、MPI4 和该 PC 参数。h1.5、角度/材料扫描、不同 rank 数与 mesh-independent convergence 都未资格化。
