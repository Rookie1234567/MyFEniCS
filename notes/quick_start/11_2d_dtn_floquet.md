# 2D TM Fourier-DtN + Floquet

## 两个入口

```bash
python src/main.py --preset 2d_tm_dtn_auxiliary_smoke
python src/main.py --preset 2d_tm_dtn_explicit_smoke
```

`auxiliary` 是正式稀疏装配：每个端口模态引入少量幅值未知量。`explicit` 直接形成稠密低秩边界更新 `Q^H Y Q`，只用于小问题交叉核验。两者描述同一截断算子，不能因矩阵布局不同就赋予不同物理意义。

## 运行前确认

| 项 | 要求 |
|---|---|
| backend | 当前 2D DtN 必须 `manual` 且串行 |
| `port_use_pml` | 必须 false；端口与未耦合 PML 不能混搭 |
| 衍射级 | `port_use_diffraction_orders=True` 自动纳入明确传播级 |
| Rayleigh 点 | 接近截止时需记录容差并做敏感性检查 |

## 判定

对零对比介质，辅助与 trace/explicit 的 R、T 应相符且 `R+T≈1`。对复材料，比较 `1-R-T` 与 `A_volume`。不能只读 probe 方法后宣称端口守恒。

理论见 [`../theory/dtn_modal_ports_and_condensation.md`](../theory/dtn_modal_ports_and_condensation.md)，实现见 [`../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md`](../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md)，基准见 [`../../benchmarks/cases/002_2d_tm_dtn_equivalence/README.md`](../../benchmarks/cases/002_2d_tm_dtn_equivalence/README.md)。
