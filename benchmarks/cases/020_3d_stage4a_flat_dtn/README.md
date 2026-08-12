# 020：3D Stage 4A 平层 DtN

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `020_3d_stage4a_flat_dtn` |
| 2. 证明 | 3D total-field auxiliary DtN、复基座、RTA 对 Fresnel 平层闭合 |
| 3. 不证明 | 光栅几何散射或 h=2 target 迭代鲁棒性 |
| 4. 物理问题 | air/吸收 substrate 平层 |
| 5. 几何 | 10x10 nm 周期，air/substrate 各 5 nm |
| 6. 材料 | air 1，Si complex substrate |
| 7. 波长/角度/偏振 | 13.5 nm、normal、默认 polarization |
| 8. 边界 | x/y Floquet，top/bottom zero-order auxiliary DtN |
| 9. FE/网格 | N1curl p1，h2 nm preset |
| 10. Task38 input | [`input/smoke/3d_stage4a_flat_layer_direct.dat`](../../../input/smoke/3d_stage4a_flat_layer_direct.dat) |
| 11. 参数表 | quick start 30 |
| 12. 精确命令 | `python scripts/run_case.py input/smoke/3d_stage4a_flat_layer_direct.dat` |
| 13. 调用链 | Stage4A -> dtn_port_3d -> flat reference/rta_3d |
| 14. 理论 | DtN、RTA、Stage ladder |
| 15. 求解器 | ordinary direct |
| 16. RTA 恒等式 | DtN R/T 对 Fresnel；`A_balance≈A_volume` |
| 17. 输出 | auxiliary/trace、flat reference、volume absorption |
| 18. Gates | residual、Fresnel differences、energy closure、mesh variation |
| 19. Canonical 结果 | 本轮不重跑；由现有 tests/历史 outcomes 支持 |
| 20. Records | 尚无独立 canonical record |
| 21. Artifact 规则 | `benchmarks/artifacts/020/` ignored |
| 22. 限制 | test-backed；晋级需把小域平层结果冻结为轻量 record |

## 物理问题

10 x 10 nm 周期平层，空气和复折射率基座各厚 5 nm。无光栅几何，因此横向尺寸不改变解析 Fresnel 比例；小域用于低成本验证 3D total-field、zero-order auxiliary DtN、法向和体吸收。

## 参数说明

`config.json` 冻结 p1/h2、13.5 nm 和 normal incidence。网格 h 可按 `lambda0/N` 选取并四舍五入为工程值，但每次变化都应保存 resolved axes/DoF。`expected.json` 声明 residual、Fresnel delta、closure 和 `A_balance-A_volume` 的目标。

## PyCharm

使用 [`input/smoke/3d_stage4a_flat_layer_direct.dat`](../../../input/smoke/3d_stage4a_flat_layer_direct.dat)。这是轻量 direct sanity；若解释器不是 complex PETSc，程序会在建网格前失败。不要依赖 `src/main.py` 的隐式 preset。

## CLI 或测试

```text
sh benchmarks/cases/020_3d_stage4a_flat_dtn/run.sh
python scripts/run_case.py input/smoke/3d_stage4a_flat_layer_direct.dat
```

## 代码路径与理论

`Stage4A wrapper -> common_3d_forms -> dtn_port_3d::solve_stage4_dtn_port_total_field -> flat_layer_reference_3d -> rta_3d::compute_volume_absorption_3d`。完整模式/功率路径见 [`../../../notes/reference/code_walkthrough/22_3d_dtn_augmented_system.md`](../../../notes/reference/code_walkthrough/22_3d_dtn_augmented_system.md)。

## 当前证据

当前状态为 test-backed，已有历史 mesh variation 和 Fresnel/energy sanity，但本 Task28 未重跑并冻结独立 record。目录 contract 不把历史结果伪装成 clean canonical rerun。

## 结果解释

依次检查 full residual、top R、bottom T、基座 A_volume、`A_balance-A_volume` 和 analytic Fresnel/finite-layer reference。若端口法向写反，常见表现是 T 负值或假全反射；若把 amplitude 搬回界面算功率，会重复消除基座吸收。

## 限制

平层闭合不能证明 grating mode coupling。晋级需要在本目录新增轻量 record，并至少保留 h2/h1.9 一组网格变化；重型 VTU 仍只放 ignored artifact。
