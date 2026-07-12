# 3D Stage 2C Fresnel 界面

```bash
python src/main.py --preset 3d_stage2c_fresnel_smoke
```

Stage 2C 增加空气/基座平界面和解析 Fresnel 参考场，用来隔离材料标签、背景场、界面连续性、PML 与功率方向错误。默认基座可为复折射率。

必须比较：数值/解析 Fresnel 振幅，界面两侧 E/H，R/T，损耗介质中的衰减，以及体吸收。无损界面检查 `R+T≈1`；有损有限基座检查 `R+T+A_volume≈1` 时还要明确底端口所在位置。

Stage 2C 不含光栅，也不证明 Stage 4 多衍射级 DtN。详见 [`../theory/3d_stages_and_validation_ladder.md`](../theory/3d_stages_and_validation_ladder.md) 和旧理论长文 [`../theory/stage2_3d_floquet_pml_fresnel.md`](../theory/stage2_3d_floquet_pml_fresnel.md)。
