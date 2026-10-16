# D13 Y/Y2/Y3 离线比较

本记录汇总已结束的 Y、Y2、Y3 三个 p6 凝聚直接法场。只读取各场的小型 summary / diffraction-mode JSON / volume-absorption JSON 和保存的 field-sample NPZ；没有新 FE、factor、资源流扫描、相位拟合或空间插值。原 Y/Y2 记录保留；本文件增加 Y3 及两组新差分。

## 身份与终态

| 场 | 网格 / cells | source SHA | input SHA | surface q / volume q | active modes | 终态 |
|---|---:|---|---|---|---:|---|
| Y | [6, 12, 14] / 1008 | `9c0fe6a30554aab33a04ff0245b19c03e4f01f28` | `78b595e4b514e4471184f281e2aa3072dd321206acfee5295b0c0151a7f74f10` | 28 / 15 default | 612 | TASK40_PHI90_D13_Y_P6_DIRECT_R13_COMPLETED_AUTHORITY_LIMITED |
| Y2 | [6, 24, 14] / 2016 | `74d5aae3dea064e128e53a253fc5aac0f2b1f146` | `7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994` | 28 / 15 default | 612 | TASK40_PHI90_D13_Y2_P6_DIRECT_R13_COMPLETED_AUTHORITY_LIMITED |
| Y3 | [6, 48, 14] / 4032 | `d742562e706b896cdb78da7fe8ba9c3dfd83f4b0` | `0bcf87e01f6e17cc89808e0296cc24aafe8df3deb4f7265fe4c60b93e4ac6e22` | 28 / 15 default | 612 | TASK40_PHI90_D13_Y3_P6_DIRECT_R13_COMPLETED_AUTHORITY_LIMITED |

三场 x/z 轴 SHA 完全相同，y 轴 SHA 依次改变；mode SHA 均为 `1987a2b3…7e522e`，612 个 FE 端口模式顺序/支路/材料及 boundary phase 对齐。Y→Y2、Y2→Y3 的源码 SHA 不同，但只改了 Task40 轴计划/profile 身份与测试，没有改 direct solver 核心文件；各场仍保留独立 source/input identity。面向模式比较的相同体积分规则为 q15/default、表面规则 q28。

## 总量与直接求解检查

| 场 | R total | R00,s | T total | A balance | A volume | grating / substrate Avol | energy closure | condensed residual | independent active-A6 residual | elapsed | peak tree RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Y | 0.251356807082 | 0.251324114555 | 0.0571286654497 | 0.691514527468 | 0.691514527469 | 0.654700218 / 0.0368143095 | 8.82e-13 | 2.6e-12 | 8.64e-11 | 1102.5s | 34.82 GB |
| Y2 | 0.251355715251 | 0.251322877436 | 0.0571288273931 | 0.691515457356 | 0.691515682641 | 0.654701282 / 0.0368144002 | 2.25e-07 | 9.52e-12 | 3.07e-10 | 2451.7s | 81.63 GB |
| Y3 | 0.251355662447 | 0.251322969903 | 0.0571288242309 | 0.691515513322 | 0.691515513275 | 0.654701102 / 0.0368144114 | 4.71e-11 | 1.21e-11 | 1.3e-09 | 4922.4s | 166.46 GB |

表中“independent active-A6 residual”指 `native_residual = native_effective_rhs - A6_physical(field)`；本 runner 的 `A6_physical` 明确包含体积作用与 DtN，**不是**单独的 augmented FE-block residual。残差 evaluator 另行计算 `augmented_fe_residual` 与 `augmented_port_residual`，但 runner 未将这两组分块残差、`port_residual_relative` 或 MUMPS 保留的 `alpha` 写入终态文件；`condensed_direct_relative` 是约化 trace+port 系统的整体残差。输出 auxiliary 则从恢复后的 storage 重新计算 `H_p^{-1}D_pu`。因此现有终态不能单独证明 port block 的残差。

Y3 自然 exit 0，direct summary `passed=true`，active-rectangle A6 为 `1.2986205283e-9`（该场本地门 `1e-6`），凝聚残差 `1.2086510683e-11`（门 `1e-9`），一次同因子修正；R/T 与体吸收能量闭合 `4.7085447e-11`（门 `1e-5`）。这些只说明有限 R13 矩形 direct solve 和本场门通过。三场均为 `AUTHORITY_LIMITED`，`FULL_DTN_NOT_VERIFIED`。

## 邻级差分：所有 612 个端口与场采样

| 对比 | ΔR00,s | 全模式最大 ΔR (key) | 全模式最大 ΔT (key) | E 采样相对 L2 | H 采样相对 L2 | 水平面 Ht 相对 L2 | 边界 outgoing 幅值相对 L2 |
|---|---:|---|---|---:|---:|---:|---:|
| Y→Y2 | 1.24e-06 | 1.24e-06 (top,m=0,n=0,s) | 1.4e-07 (bottom,m=0,n=0,s) | 1.16e-05 | 3.96e-05 | 0.000184 | 0.00397 |
| Y2→Y3 | 9.25e-08 | 9.25e-08 (top,m=0,n=0,s) | 1.89e-08 (bottom,m=0,n=0,s) | 9.89e-06 | 9.89e-06 | 0.000184 | 0.00397 |
| Y→Y3 | 1.14e-06 | 1.14e-06 (top,m=0,n=0,s) | 1.59e-07 (bottom,m=0,n=0,s) | 5.98e-06 | 3.84e-05 | 6.21e-06 | 2.57e-06 |

All per-order R/T differences were computed over all 612 records, with propagating and power-carrying subsets separately retained in JSON. Counts are 612 total, 166 propagating, 390 power-carrying. Y2→Y3 gives `ΔR00,s=9.2467e-8`; Y→Y2 was `1.2371e-6`, while Y→Y3 remains `1.1447e-6`. Thus the adjacent R00 trend improves at Y3, but the coarser-to-finest span is still above `1e-6`. The saved `H_t_interface_A_per_m` values are on horizontal z=10/110 nm planes; Y2→Y3 remains `1.8411e-4`, above the earlier `1e-4` diagnostic threshold. These are not pillar sidewalls or the canonical H(curl) sidewall trace gate.

## Top (m=±4,n=0,p) boundary amplitudes

| m | Y 复 boundary amplitude | Y2 复 boundary amplitude | Y3 复 boundary amplitude | beta (nm⁻¹) | phase magnitude | propagating / power-carrying | modal R/T |
|---:|---|---|---|---|---:|---|---|
| -4 | -2.306629267e-07+3.608258091e-07i | +1.485361929e-03+6.305133255e-05i | -2.507826894e-07+3.595125781e-07i | +0+0.502589190i | 4.213834205e-29 | false / false | R=0, T=0 |
| +4 | +2.306629284e-07-3.608257970e-07i | -1.485361929e-03-6.305133249e-05i | +2.507826860e-07-3.595123898e-07i | +0+0.502589190i | 4.213834205e-29 | false / false | R=0, T=0 |

Y2 的两个边界幅值各约 `1.4867e-3`，Y 约 `4.2825e-7`，Y3 约 `4.3834e-7`。Y↔Y2 与 Y2↔Y3 的这对 mode 分别占所有 612 模 boundary-amplitude 差平方约 `99.9918%`；Y↔Y3 仅约 `0.0437%`。它们的 `β=+0.5025891902i nm⁻¹`，顶部参考面 `z=130 nm`，相同保存 `|boundary_phase|=4.2138342045e-29`；逐模复核 `raw_outgoing × boundary_phase == outgoing_at_boundary`（JSON 中误差 0）。所以巨大的 raw 系数来自倏逝模态的参考面指数尺度，但同一个 phase 不能消掉 Y2 的边界面异常。此对 mode 被标为非传播、非 power-carrying，三场每模 R/T 为零；边界幅值对网格仍高度敏感，原因未定。

## 可用证据与限制

Y3 生产 RHS/MPC witness 实际使用 612 modes、q28、finalized Floquet MPC，报告 54,840 个约束及配对/相位误差为 0；它验证的是 RHS/MPC 构造路径，不是独立重算的 port equation/projection residual。没有再做 factor/action 诊断，该独立残差为 `NOT_RUN`。

保存的 field-sample NPZ 坐标在三场之间逐位一致；比较是复数 E/H 直接差、没有整体相位拟合或插值，形状为 5×64×40×3。水平 Et/Ht sample 只作诊断，不替代 canonical sidewall trace。canonical pillar sidewall trace gate 仍 `NOT_MEASURED_AS_CANONICAL_HCURL_TRACE_GATE`；full DtN 仍 `FULL_DTN_NOT_VERIFIED`。本次 Y3 是 y 方向最后一级；结果支持“Y2 有异常、Y3 回到接近 Y 的边界幅值水平”这一有限观察，不证明误差根因，也不支持 Y4。

Y3 资源终态：elapsed 4922.42 s、tree RSS peak 166,464,983,040 B、task VmSwap peak 0、PSS disabled、descendants cleared。全局 WSL swap delta 为 +2 pages（仅主机观察，未归因任务）。

## 记录与来源

- JSON：`docs/task40para_phi90_mesh_modes_direct/outcomes/records/d13_y_y2_y3_comparison_v1.json`，SHA256 `86cc5cc70eb90d9bbbd23a1c97145df4d5983170d25a230c30bfbadcdfac1727`。
- 既有 Y/Y2 比较：`d13_y_y2_comparison.json`，既有幅值诊断：`d13_y_y2_modal_amplitude_diagnostic.json`。
- 三场原始 run 目录和 JSON/NPZ artifact SHA 均记录在新 JSON；没有覆盖/改写任何原始 run 输出或既有比较记录。
