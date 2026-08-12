# 013：3D Stage 2C Fresnel

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `013_3d_stage2c_fresnel` |
| 2. 证明 | 平界面材料 tag、Fresnel background、incident-scattered 与 PML 可运行 |
| 3. 不证明 | Stage4 多模 DtN 或高精度 p2 Fresnel |
| 4. 物理问题 | air/substrate 平界面 |
| 5. 几何 | Stage2 盒，interface z=0 |
| 6. 材料 | air 1，substrate 默认 1.45 或显式 complex |
| 7. 波长/角度/偏振 | 633 nm normal smoke；代码支持 s/p oblique |
| 8. 边界 | x/y Floquet、z PML |
| 9. FE/网格 | N1curl p1，h300 nm smoke |
| 10. Task38 input | [`input/smoke/3d_stage2c_fresnel_smoke.dat`](../../../input/smoke/3d_stage2c_fresnel_smoke.dat) |
| 11. 参数表 | quick start 23 |
| 12. 精确命令 | `python scripts/run_case.py input/smoke/3d_stage2c_fresnel_smoke.dat` |
| 13. 调用链 | Stage2C -> analytic_fields_3d -> incident-scattered flow |
| 14. 理论 | Maxwell、PML、Stage ladder |
| 15. 求解器 | ordinary direct |
| 16. RTA 恒等式 | 无损对 Fresnel/R+T；复材料增加 A_volume |
| 17. 输出 | numerical/reference E/H/R/T/A differences |
| 18. Gates | Fresnel unit、field error、energy、PML sensitivity |
| 19. Canonical 结果 | 尚无冻结 record |
| 20. Records | 无 |
| 21. Artifact 规则 | `benchmarks/artifacts/013/` ignored |
| 22. 限制 | experimental；历史 p2 路线只作 diagnostic |

## 物理问题

air/substrate 平界面加入材料跳变和 Fresnel analytic background，再用 incident-scattered/correction 路径求解。它把 Stage2A Floquet、Stage2B PML 与材料 interface 组合起来。

## 参数说明

`config.json` 冻结轻量无损 smoke；代码可接受 complex substrate 和 oblique s/p，但这些偏离没有本 case 的 canonical 资格。`expected.json` 要求明确保留 experimental 身份。

## PyCharm

使用 [`input/smoke/3d_stage2c_fresnel_smoke.dat`](../../../input/smoke/3d_stage2c_fresnel_smoke.dat)。自定义 complex index 时先核对 `exp(-i omega t)` 与 `Im(epsilon)>0`，并确保 interface z 恰落在网格面。

## CLI 或测试

```text
sh benchmarks/cases/013_3d_stage2c_fresnel/run.sh
python scripts/run_case.py input/smoke/3d_stage2c_fresnel_smoke.dat
python -m unittest src.test.test_09_fresnel_pml src.test.test_10_stage2_combined
```

## 代码路径与理论

`run_stage2c_fresnel_interface_3d_case -> analytic_fields_3d -> common_3d_forms -> run_prepared_3d_case_flow -> run_fresnel_analytic_postprocess_sanity`。理论入口是 [`../../../notes/theory/3d_stages_and_validation_ladder.md`](../../../notes/theory/3d_stages_and_validation_ladder.md)。

## 当前证据

Fresnel helper、组合 weak form 和 PML 有 focused tests；没有冻结 p2 网格收敛或 complex absorption physical record。当前目录因此只提供 config/expected/run contract。

## 结果解释

无损时比较 E/H、Fresnel R/T 和 `R+T`；有损时还需 volume A 与端口余额。先验证材料 tag volume、interface alignment 和背景源区域，避免用能量闭合掩盖错误的几何标记。

## 限制

该路径不是 Stage4 multi-order DtN 的替代品。历史 diagnostic 数值不能自动升级为 canonical；需要干净环境、轻量 record 和 checker Gate。
