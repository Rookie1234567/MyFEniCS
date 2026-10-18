# D13 Y2 上 R13→R14 模态扩展结果

日期：2026-10-18

## 范围与身份

这是两个已自然完成的 p6 凝聚直接法结果之间的离线比较，不启动 FE、因子、VTU 读取或资源流扫描。两场使用同一 Y2 网格 `[6,24,14]`（2016 个六面体）、相同 physical SHA `ac65772c3fda31f22599824023f43e05e62b8292de31652dff226909fc83fa7b`、surface quadrature q28、volume q15/default 与 `scale_homogeneous_relative_only_v1` cutoff（`1e-13`）。

| 场 | run | source | input | 模式 |
|---|---|---|---|---:|
| R13 | `20261016T190312.893443Z` | `73e2fd2c4a36c9698298235148c59aa1551d74d6` | `7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994` | 612，SHA `1987a2b3…7e522e` |
| R14 | `20261018T071859.358847Z` | `0d42d9fd999f5df7df22709723fd91ad2c5d70b1` | `cf9bc38fe33be5f658fb58d45e40242e70f6e1ef41b95c76a61102dfdf007cb5` | 836，SHA `deefaa83…b1a860e` |

两场 source SHA 不同，不能称 source-identical。矩形从 `m=-4…4,n=-8…8` 扩为 `m=-5…5,n=-9…9`；R13 的 612 个键全部包含于 R14，另增 224 个键。共同键的 medium/direction/polarization、beta、boundary phase、传播/携功标记逐项一致，未拟合整体相位。

## 求解、能量与资源

R14 自然完成，exit 0、`worker_exit0`、后代清空。凝聚相对残差 `5.009036507395619e-12 ≤ 1e-9`；同一因子完成 1 次 numeric、2 次 solve（其中 1 次校正）；独立 `A6_D13_Y2_R14_active_rectangle` 相对残差 `3.0723166436241147e-10 ≤ 1e-6`。总能量闭合 `2.9922064825882444e-11 ≤ 1e-5`。R14 单场为 `TASK40_PHI90_D13_Y2_P6_DIRECT_R14_COMPLETED_AUTHORITY_LIMITED`。

| 量 | R13 | R14 | R14−R13 |
|---|---:|---:|---:|
| `R_total` | 0.2513556633066366 | 0.2513556633074687 | `+8.3211e-13` |
| `T_total` | 0.05712882413359571 | 0.057128824133641655 | `+4.5942e-14` |
| `A_balance` | 0.6915155125597676 | 0.6915155125588897 | `−8.7796e-13` |
| `A_volume` | 0.69151551258949 | 0.6915155125888116 | `−6.7835e-13` |
| `R00,s` | 0.2513229707636959 | 0.25132297076453325 | `+8.3733e-13` |
| `|1−R−T−A_volume|` | `2.9722e-11` | `2.9922e-11` | `+1.9962e-13` |

R14 增广矩阵为 `410372×410372`，`nz_used=370,867,392`、`nz_allocated=400,488,976`。MUMPS 为 1 symbolic、1 numeric、2 solves；因子和矩阵在完整 p6 恢复及独立 A6 后、场后处理前按生命周期合同释放。workflow `7102.771 s`，峰值整树 RSS `103,634,391,040 B`，task swap 峰值 0，PSS 关闭；WSL 全局 swap-in 增量 28 页、swap-out 0，仅为全机 observe-only 记录，不能归因到此任务。13.5 nm 本 profile 使用 64 GiB host-available floor，没有固定 RSS cap。

## 模态与场比较

共同 612 模式的边界 outgoing 复振幅相对 L2 差 `4.9658e-12`，最大绝对差 `8.8808e-13`，键为 top `(0,0,s)`；incident projection 逐项相同。共同模式中，最大逐模 `|ΔR|=8.3733e-13`（top `(0,0,s)`），最大 `|ΔT|=4.7309e-14`（bottom `(0,0,s)`）；all-common、propagating 与 power-carrying 子集均远低于 `1e-6` 诊断阈值。

R14 新增 224 个模式没有 R13 解作为逐模差值基准。它们在 R14 中均非 propagating，但 112 个标记为 power-carrying（有损底部介质）；这 224 个模式的 R 贡献合计 0，T 贡献合计 `2.0206e-15`。此尾部功率是 R14 结果的新增通道贡献，不是“相对 R13 的零值误差”。

共同模式的未缩放 outgoing 系数与 auxiliary projection 相对 L2 差均为 `2.5505e-7`，最大原始系数绝对差 `3.4460e68` 出现在 top `(4,8,p)`。这些倏逝系数受指数尺度影响；物理边界相位缩放后的复振幅差如上，不能用 raw 系数绝对差替代边界量。

同一保存坐标上的有限复场样本未做相位拟合：

| 样本 | 相对 L2 差 | 最大绝对差 | `1e-4` 样本诊断 |
|---|---:|---:|---|
| `E` | `5.4810e-11` | `1.1243e-10 V/m` | PASS |
| `H` | `3.9528e-11` | `2.8209e-13 A/m` | PASS |
| 水平面 `E_t` | `4.8037e-11` | `9.8349e-11 V/m` | PASS |
| 水平面 `H_t` | `2.0882e-9` | `2.8209e-13 A/m` | PASS |

样本仅为有限共同点，不是全域范数。这里的 `H_t` 是水平 z-plane 样本，不是柱侧壁 canonical H(curl) trace；侧壁仍 `NOT_MEASURED`。两个结果均为有限模式算子，`FULL_DTN_NOT_VERIFIED` 与 `AUTHORITY_LIMITED` 保持。六键 pre-release full-primal witness 是 `OBSERVED_NOT_QUALIFICATION`，没有作为额外求解门或完整 DtN 资格。

## 可复现文件

- [分析脚本](analysis/compare_d13_y2_r13_r14.py)
- [836 模式逐行 CSV](records/d13_y2_r13_r14_all_836_modes_v1.csv)
- [机器可读比较记录](records/d13_y2_r13_r14_same_mesh_mode_expansion_v1.json)
