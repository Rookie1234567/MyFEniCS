# Task034 资源模型 v2.1

## 结论与数据身份

本模型是基于既有 13.5 nm Hybrid M160 证据的离线 engineering stress test；它不是 PDE run、
不是 solver pass，也不授权重型计算。Review V2 将原先含混的 `predicted_total_gib` 拆分为：

- `largest_component_gib`：单一组件下界；
- `local_component_subtotal_gib`：local assembly/factor/recovery 的累计子项；
- `modal_and_runtime_component_subtotal_gib`：QEP、mode、projection、Schur 与 runtime 的累计子项；
- `cumulative_component_envelope_gib`：所有组件逐项相加的保守 envelope，不是同时峰值；
- `measured_simultaneous_peak_gib`：仅 13.5 nm 基准运行的实测 worker RSS 峰值；
- `predicted_simultaneous_peak_gib`：外推波长全部为 `null`，因为没有生命周期 overlap 模型。

因此 envelope/budget 只能写成保守预算距离，不能冒充 peak/budget 或实测压缩需求。

## 三个 current-layout 场景

| 场景 | 角色 | 13.5 nm 实测 simultaneous peak GiB | 13.5 nm envelope GiB |
|---|---|---:|---:|
| p2/h3 | Task033 equal-accuracy threshold baseline | 4.695 | 4.695 |
| p3/h3 | Task034 finer discrete reference | 14.272 | 14.272 |
| p4/h5 | Case093 best available discrete reference | 9.206 | 9.206 |

三个场景用于覆盖 p2/p3/p4 的机械缩放敏感性。它们的 `h`、离散误差与 DoF 不相同，
所以不是共同 target accuracy 的 p-refinement 比较；不能据此断言生产精度下哪一个 `p` 最省资源。

## 0.7 nm stress-test envelope

| 场景 | 最大单组件 GiB | local 子项 GiB | modal/runtime 子项 GiB | 累计 envelope GiB | 外推 simultaneous peak |
|---|---:|---:|---:|---:|---|
| p2/h3 | 1,747,721 | 199,869 | 1,815,106 | 2,014,975 | unknown |
| p3/h3 | 5,713,351 | 1,015,284 | 5,789,387 | 6,804,671 | unknown |
| p4/h5 | 2,567,626 | 370,459 | 2,638,305 | 3,008,763 | unknown |

三个场景的最大单组件都已经超过 2 TiB，因此可保守断言：在这些 current-layout stress-test
场景中，0.7 nm 对 256 GiB、1 TiB 和 2 TiB 均存在单组件瓶颈。不能进一步断言未来 production
target accuracy 的 DoF、M 或 simultaneous peak；这些量仍为 `unknown`。

单个 complex `(2M)^2` 对象在 `M=59,511` 时约 211.093 GiB。模型按当前 48-rank replicated
layout 计入六个此类对象，并分别保留 dense multi-RHS、local direct factor、mode vectors、
projection 等组件；这些组件并非假设同时达到峰值。

## 缩放假设

令 `s = 13.5 / wavelength_nm`。三个场景分别从自己的 13.5 nm 组件库存机械外推：

| 组件 | 缩放 | 身份 |
|---|---:|---|
| local 3D FE assembly | `s^3` | measured-calibrated / predicted |
| local 3D direct factor | `s^4` | engineering sparse-fill proxy |
| QEP coefficient matrices | `s^2` | engineering sparse proxy |
| QEP shift-invert factor | `s^3` | engineering 2D factor proxy |
| right/left mode vectors | `s^4` | QEP DoF `s^2` × M `s^2` |
| interface projection `N_interface M` | `s^4` | trace × modes |
| replicated dense modal arrays | `s^4` | six complex `(2M)^2` × 48 ranks |
| Hybrid dense multi-RHS | `s^5` | local rows `s^3` × modal RHS `s^2` |
| field reconstruction | `s^3` | local vectors |
| MPI/process overhead | `s^0` | 13.5 nm calibration residual proxy |

M 使用 `160 s^2` 的 reciprocal-order area 机械外推。material dispersion、cutoff、角度、
evanescent buffer 与未来 S/P 生产要求会改变 M，必须在较长波长逐级重新做 M funnel。

## Adaptive 与重构边界

三档 graded-h 候选均未通过固定 Full3D 同误差 Gate，所以允许抵扣的 accuracy-preserving
adaptive compression factor 仍为 `1.0`。raw DoF reduction 不得用于降低上述 envelope。

进入生产可行性复核前至少需要：

1. 通过 common-mesh 与角度验证的 field-driven h-adaptivity；
2. 有 true residual 和 official R/T/A 证据的 matrix-free/iterative local solver；
3. distributed/streamed mode vectors，消除 replicated dense `M^2` inventory；
4. blocked/streamed multi-RHS Schur 与 field recovery；
5. 明确组件生命周期 overlap，并测量 simultaneous peak。

完整机器可读结果见 `resource_model_v2.json` 和 `resource_model_v2.csv`；每行均带 scenario、
预算分类、largest-component lower-bound ratio、cumulative-envelope ratio 与 peak identity。
