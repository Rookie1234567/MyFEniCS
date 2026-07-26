# Task035c p2/h5 逐通道根因闭环

## 结论

`p2/h5` 的原始 Full3D–Hybrid 弱通道误差不是 modal cross-section
子空间不完备，也不是 `M120/M160` 截断不足。根因是 Hybrid 中间均匀层使用
连续 QEP 的 `exp(i beta L)` 和连续端点牵引，而 Full3D 在 z 方向实际使用
scalar CG(p) 有限元链的离散传播相位和离散端点导数符号。

Task035c 新增的两个 opt-in 诊断模型为：

```text
internal_propagation_model = full3d_uniform_cg
internal_traction_model = scalar_cg_discrete_derivative
```

两者联合使用后，static Hybrid M120 和 M160 对同一 final-source Full3D
锚点都达到：

```text
12/12 significant powers
12/12 significant complex amplitudes
```

最大相对误差不但低于任务要求的 `1e-3`，也低于 `1e-6`。因此
Task035c 的 `p2/h5` 诊断 Gate 已闭合。

这两个模型仍是显式 opt-in；ordinary Hybrid 默认继续使用
`continuous_beta` 与 `continuous_qep_beta`。

## 隔离证据

### 1. modal trace 子空间完整

Full3D interface trace 到 modal basis 的 rank 为 `320/320`。投影重构误差约为：

| 量 | relative L2 |
|---|---:|
| electric trace | `1e-7` |
| magnetic trace | `1e-6` |

因此继续提高 M 不能解释原来的弱通道误差。

### 2. 连续传播存在离散相位偏差

Full3D trace oracle 对连续 QEP 传播的 coefficient relative L2 为：

| 方向 | relative L2 |
|---|---:|
| forward | `3.395e-2` |
| backward | `1.724e-3` |

只替换 scalar CG 离散传播相位后，M160 从原来的 `3/12 power +
2/12 amplitude` 改善到 `4/12 + 4/12`，但仍未闭合。该结果作为
controlled-negative evidence 保留，证明传播相位是必要条件，但不是充分条件。

### 3. 离散端点牵引是剩余缺项

对单元动态刚度

```text
D(q) = K - q^2 M,  q = beta h
```

凝聚 interior scalar CG DoF 后，端点 Schur 符号同时决定：

- Bloch 传播乘子；
- 左、右端点的离散 outward derivative/traction。

Full3D 使用这两个离散符号；旧 Hybrid 只使用连续 `beta`。同时替换传播和
traction 后，R/T/A 与全部显著通道在舍入及 QEP 截断误差范围内闭合。

## final-source p2/h5 结果

共同源码：

```text
8a1e40c420e36407cd827e1fd7e8f11401a0d39b
```

Full3D static MPI8 锚点：

```text
benchmarks/artifacts/task035c_hybrid_channel_memory/
p2_h5_full_static_mpi8_8a1e40c.json
sha256 = 228517adc2829ea5f026ce571f22041b872e504906699eb661abab13db56a2a2
```

Hybrid 原始 watchdog 记录：

```text
M120:
benchmarks/artifacts/task035c_hybrid_channel_memory/
p2_h5_static_m120_scalar_cg_phase_traction_watchdog.json
sha256 = 13632704da826c100e5d252cda50a33b8f9bb86ab38f9109f2f3ae69e798b2d5

M160:
benchmarks/artifacts/task035c_hybrid_channel_memory/
p2_h5_static_m160_scalar_cg_phase_traction_watchdog.json
sha256 = 03afd5a2547c934cf51df273c5057275b98f5e0776a9ffb7588907140b362ce6
```

| 对照 | power pass @ `1e-3` | amplitude pass @ `1e-3` | max power rel. | max amplitude rel. |
|---|---:|---:|---:|---:|
| Full3D vs Hybrid M120 | 12/12 | 12/12 | `2.4125e-7` | `1.2196e-7` |
| Full3D vs Hybrid M160 | 12/12 | 12/12 | `8.2794e-7` | `4.5273e-7` |
| Hybrid M120 vs M160 | 12/12 | 12/12 | `6.7107e-7` | `3.7037e-7` |

| 量 | Full3D static | Hybrid static M120 | Hybrid static M160 |
|---|---:|---:|---:|
| peak memory / GiB | `2.7747` | `2.6793` | `3.3243` |
| true residual | `1.05e-11` | `2.78e-12` | `2.91e-12` |
| total time / s | `9.66` | `67.95` | `98.22` |
| internal modal coupling / s | n/a | `8.22` | `12.81` |

M120/M160 对 Full3D 的 `R_total`、`T_total` 和 `A_closure` 绝对差都不超过
`1.5e-12`。

## 权威边界

- `p2/h5` 只用于低成本根因诊断，不是高阶物理 authority。
- scalar CG 映射与 fixed rectangular、均匀 z 网格绑定；非整数层数、
  非均匀 z 网格或非资格化 degree 必须 fail closed。
- electric field reconstruction 使用离散传播相位后，middle-plane relative
  L2 降至 `2.6e-10` 以下。
- magnetic reconstruction 仍以原始 QEP mode shape/curl 作为场定义；
  middle-plane relative L2 约 `8.8e-4`。这不影响已由统一 Rayleigh
  后处理重算的 12 通道结论，但必须在 `p6/h10` 的 interface/field Gate
  中单独报告，不能把通道闭合替代场闭合。
- p6/h10 的正式结论必须来自 final-source、hash-bound 的六条 MPI8
  正式路径；本文件不预判 p6 资源成功。
