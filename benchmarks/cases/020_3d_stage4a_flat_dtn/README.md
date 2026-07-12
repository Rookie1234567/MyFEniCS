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
| 10. PyCharm preset | `3d_stage4a_flat_layer_direct` |
| 11. 参数表 | quick start 30 |
| 12. 精确命令 | `python src/main.py --preset 3d_stage4a_flat_layer_direct` |
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
