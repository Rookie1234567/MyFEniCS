# 2D TM Fourier-DtN + Floquet 教程

## 1. 功能与物理图景

DtN 端口把上下均匀半空间中的每个 Floquet 阶映射为边界 traction，从而在有限区域内表示开放边界。本项目保留 explicit `Q^H Y Q` 参考实现和 auxiliary 模态未知量实现。

## 2. 当前能力状态

| 路径 | 身份 |
|---|---|
| `port_dtn_assembly="auxiliary"` | 推荐主路径，modal amplitude official |
| `port_dtn_assembly="explicit"` | 参考/cross-check |
| MPI | 当前 2D Fourier DtN manual backend 为 serial |
| Case002 | 两次完整 solve 的 canonical 等价性证据 |

## 3. 运行前提

必须使用 `constraint_backend="manual"`、`port_boundary_model="dtn"`、`use_pml=False`。上下 port plane 应位于均匀材料层内。

## 4. PyCharm presets

```python
ACTIVE_PYCHARM_PRESET = "2d_tm_dtn_auxiliary_smoke"
# 或
ACTIVE_PYCHARM_PRESET = "2d_tm_dtn_explicit_smoke"
```

## 5. `main.py` 修改位置

两个 preset 都由 `_TM_DTN_AUX_2D` 派生，只有 `port_dtn_assembly` 不同。这样可保证比较时几何、材料、网格和入射完全相同。

## 6. 完整参数示例

```python
replace(
    EUV_GRATING_2D,
    calculation_method="port",
    constraint_backend="manual",
    port_boundary_model="dtn",
    port_dtn_assembly="auxiliary",
    port_use_diffraction_orders=True,
    nedelec_degree=2,
    mesh_target_size=3.0,
)
```

## 7. 关键参数

| 参数 | 含义 | 合法值/影响 |
|---|---|---|
| `port_dtn_assembly` | 边界算子实现 | `explicit`/`auxiliary` |
| `port_use_diffraction_orders` | 自动保留传播阶 | `True` 推荐一般周期问题 |
| `port_dtn_order_count` | 手动 `-N...N` | 自动关闭时生效 |
| `port_rayleigh_tolerance` | Rayleigh 邻域排除 | 不应随意缩到机器零 |
| `period_x`、`lambda0`、angle | 决定 `alpha_m/beta_m` | 改后需重建阶次 |

## 8. Qualification 边界

Case002 是小型无损等价性案例，不证明复杂 grating 的网格精度。Case003 另外验证有损传播阶；near-Rayleigh 条件仍未系统资格化。

## 9. CLI 与 Case002

普通入口：

```text
python src/main.py --preset 2d_tm_dtn_auxiliary_smoke
python src/main.py --preset 2d_tm_dtn_explicit_smoke
```

冻结双求解：

```text
SOURCE_COMMIT=<sha> sh benchmarks/cases/002_2d_tm_dtn_equivalence/run.sh
```

## 10. 真实调用链

```text
run_cases::main
-> solve_port_maxwell::run_port_case
-> _add_fourier_port_operators_explicit
   或 _add_fourier_port_operators_auxiliary
-> solve_with_constraints_with_stats
-> compute_dtn_port_power_metrics
-> compute_dtn_auxiliary_power_metrics
```

## 11. 输出目录树

```text
explicit/
├── run_summary.json
└── dtn_port_power_metrics.json
auxiliary/
├── run_summary.json
├── dtn_auxiliary_amplitudes.json
└── dtn_auxiliary_power_metrics.json
records/
├── explicit.json
├── auxiliary.json
└── comparison.json
```

## 12. 当前 canonical 数值

| 量 | explicit | auxiliary | 差 |
|---|---:|---:|---:|
| FE DoF | 139 | 139 | 0 |
| auxiliary DoF | 0 | 2 | 2 |
| matrix rows | 139 | 141 | 2 |
| residual | 2.17e-15 | 1.87e-15 | - |
| field relative difference | - | - | 2.77e-15 |
| max R/T/A difference | - | - | 1.22e-15 |

## 13. 成功 Gate

```text
两次 residual <= 1e-10
field relative difference <= 1e-8
R/T/A absolute difference <= 1e-8
lossless energy closure <= 1e-8
auxiliary system rows > explicit rows
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| DtN + official MPC 被拒绝 | 当前非局部端口只支持 manual backend |
| auxiliary 与 explicit 几何不同 | 比较脚本/配置没有共享同一 contract |
| 没有 aux amplitude 文件 | 实际运行了 explicit |
| 把 probe 当 official | 数据源身份混淆 |

## 15. 改成自己的 case

复制 Case002 的 `config.json` 到新 case，保持 explicit/auxiliary 共用同一块 physical/numerical 配置。先通过场差和功率差，再增加衍射阶、复材料或更高 p。

## 16. 链接

- DtN 理论：[`../theory/dtn_modal_ports_and_condensation.md`](../theory/dtn_modal_ports_and_condensation.md)
- 代码导读：[`../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md`](../reference/code_walkthrough/12_2d_dtn_and_rta_postprocess.md)
- Case002：[`../../benchmarks/cases/002_2d_tm_dtn_equivalence/README.md`](../../benchmarks/cases/002_2d_tm_dtn_equivalence/README.md)
