# H15-YZ480 第14场与已有网格对照

## 执行身份

- 场：`task40_phi90_13p5_H15_YZ480_p6_direct_v1`，2026-10-17，run `20261017T095134.921987Z`。
- 源码：`60be8967be874d471313608f4bd649b690eb3637`；input `1c6e25c48e8f86e722ee4992f6df42ee4723b97624d59937c42e2ef03291c75c`；physical `8b3d63f735e0fa5346ca6a03a54265a766065d4d9abdafdf884f75bb7df500a3`；resolved `66258ee70b58b0e1073307a58f8c7c7e084cece11e0229d7e256d82c27099b25`。
- 实际网格 QA：`[6,10,8]`、480 cells、材料标签 `air/substrate/grating=348/60/72`。相对 H15-Y 的 x 轴 SHA 不变；y/z 均变化。
- 四场均为 612 模式 SHA `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e`、surface q28、volume q15/default、`scale_homogeneous_relative_only_v1` cutoff (`1e-13`)。本场与 H15-Y 比较改变 y 和 z；与 D13-Y2/Y3 的网格也不同，不能将跨场差异单独归因到某一轴。

## 本场数值与资源结果

run 自然结束 `worker_exit0`，direct summary `passed=true`。凝聚残差初值 `2.10293e-9`，一次同矩阵、同因子校正后为 `3.52566e-12`（上限两次）；独立原 p6 A6 active-R13 相对残差 `9.09323e-11`（门 `1e-6`）；R/T 与体吸收闭合 `9.64118e-13`（门 `1e-5`）。

| 量 | H15-YZ480 |
|---|---:|
| `R_total` | 0.25154225679008296 |
| `R00_s` | 0.25150958360466596 |
| `T_total` | 0.05710258476441602 |
| `A_balance` | 0.6913551584455011 |
| `A_volume_total` | 0.6913551584464651 |

MUMPS 使用同一 `[S_V,Bhat;-Dhat,Hhat]` 矩阵完成一个 symbolic、一个 numeric 和两次 solve（含一次校正）。增广矩阵为 `99972×99972`，`nz_used=88,369,672`、`nz_allocated=100,093,104`；组装耗时 `1833.91 s`。整场 elapsed `2246.612 s`，一次终态资源审计峰值 tree RSS `19,708,227,584 B`、tree swap 峰值 `0 B`、PSS disabled。run summary 中的 launch `MemAvailable=2,125,532,762,112 B` 是启动采样；运行期最低可用内存未持久化，记为 `UNKNOWN`。host-floor 为64 GiB，无固定 RSS cap；global swap delta 为0仅是整机诊断，未作任务归因。

本场为 `AUTHORITY_LIMITED`，`FULL_DTN_NOT_VERIFIED`；单场 solver 门通过不等于完整 DtN 资格。

## 已保存输出对照

比较直接读取四场的612模态 JSON、各自小型 full3d sample NPZ（每份约1.3 MB）及 run summary/evidence。未读 VTU 或 resources 流；复数振幅按完全相同的有序 signed mode key 比较，场只在坐标数组逐位相同处比较，不插值、不拟合整体相位。逐模 R/T CSV 保留所有612项及 classification。

| 对照参考 | `ΔR_total` | `ΔR00_s` | `ΔT_total` | `ΔA_balance` | `ΔA_volume` | 全612 boundary outgoing 振幅相对 L2 | E / H 相对 L2 | 水平面 Et / Ht 相对 L2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| H15-Y `[6,8,10]` | `−1.13232e-6` PASS | `−1.11273e-6` **FAIL** | `+1.48594e-7` PASS | `+9.83724e-7` PASS | `+9.83727e-7` PASS | `1.30858e-4` **FAIL** | `7.47527e-5` / `8.72565e-5` PASS | `6.90424e-5` PASS / `2.77924e-3` **FAIL** |
| D13-Y2 `[6,24,14]` | `+1.86593e-4` **FAIL** | `+1.86613e-4` **FAIL** | `−2.62394e-5` **FAIL** | `−1.60354e-4` **FAIL** | `−1.60354e-4` **FAIL** | `4.34082e-4` **FAIL** | `2.85990e-4` / `6.07301e-4` **FAIL** | `2.62664e-4` / `2.67644e-3` **FAIL** |
| D13-Y3 `[6,48,14]` | `+1.86594e-4` **FAIL** | `+1.86614e-4` **FAIL** | `−2.62395e-5` **FAIL** | `−1.60355e-4` **FAIL** | `−1.60355e-4` **FAIL** | `4.34084e-4` **FAIL** | `2.85992e-4` / `6.07301e-4` **FAIL** | `2.62665e-4` / `2.67644e-3` **FAIL** |

逐模功率门 `|ΔR|, |ΔT| <= 1e-6` 现按同一规则分别统计全部612模式、`power_carrying` 390模式和 `propagating` 166模式。下表给出每组最大绝对差、signed key、带符号差及判定；signed key 写作 `(side,m,n,pol)`。数值从已有612行CSV按其分类字段离线汇总，没有读取VTU/resources或重跑FE。

| 对照参考 | 模式组 | 数量 | 最大 `|ΔR|`；signed key；`ΔR`；判定 | 最大 `|ΔT|`；signed key；`ΔT`；判定 |
|---|---|---:|---|---|
| H15-Y | 全612 | 612 | `1.11273135e-6`；`(top,0,0,s)`；`−1.11273135e-6`；**FAIL** | `1.48981821e-7`；`(bottom,0,0,s)`；`+1.48981821e-7`；PASS |
| H15-Y | power-carrying | 390 | `1.11273135e-6`；`(top,0,0,s)`；`−1.11273135e-6`；**FAIL** | `1.48981821e-7`；`(bottom,0,0,s)`；`+1.48981821e-7`；PASS |
| H15-Y | propagating | 166 | `1.11273135e-6`；`(top,0,0,s)`；`−1.11273135e-6`；**FAIL** | `4.69292761e-8`；`(bottom,0,−2,s)`；`+4.69292761e-8`；PASS |
| D13-Y2 relative-only | 全612 | 612 | `1.86612841e-4`；`(top,0,0,s)`；`+1.86612841e-4`；**FAIL** | `2.62362701e-5`；`(bottom,0,0,s)`；`−2.62362701e-5`；**FAIL** |
| D13-Y2 relative-only | power-carrying | 390 | `1.86612841e-4`；`(top,0,0,s)`；`+1.86612841e-4`；**FAIL** | `2.62362701e-5`；`(bottom,0,0,s)`；`−2.62362701e-5`；**FAIL** |
| D13-Y2 relative-only | propagating | 166 | `1.86612841e-4`；`(top,0,0,s)`；`+1.86612841e-4`；**FAIL** | `4.72901807e-8`；`(bottom,0,−2,s)`；`+4.72901807e-8`；PASS |
| D13-Y3 relative-only | 全612 | 612 | `1.86613711e-4`；`(top,0,0,s)`；`+1.86613711e-4`；**FAIL** | `2.62363662e-5`；`(bottom,0,0,s)`；`−2.62363662e-5`；**FAIL** |
| D13-Y3 relative-only | power-carrying | 390 | `1.86613711e-4`；`(top,0,0,s)`；`+1.86613711e-4`；**FAIL** | `2.62363662e-5`；`(bottom,0,0,s)`；`−2.62363662e-5`；**FAIL** |
| D13-Y3 relative-only | propagating | 166 | `1.86613711e-4`；`(top,0,0,s)`；`+1.86613711e-4`；**FAIL** | `4.72901786e-8`；`(bottom,0,−2,s)`；`+4.72901786e-8`；PASS |

三个对照中，`(bottom,0,0,s)` 均为 `propagating=false, power_carrying=true`。因此 D13-Y2/Y3 的 propagating 子集 `ΔT` 通过，不能推出全612或全部带功率模式的 `ΔT` 通过；两组都由该底部 lossy 模式超出 `1e-6`。H15-Y 的全612与 power-carrying `ΔT` 通过，但 `ΔR` 仍失败。总体结论仍是本场单次 solver/能量检查通过、网格比较未过；有限R13比较不构成完整DtN或canonical sidewall资格。

H15-Y 对照的总 R/T/A_volume 接近，但 `R00_s`、全模式 boundary 幅值及水平 Ht 仍有门失败；不能据总反射率差很小称全部输出通过。对 D13-Y2/Y3 的差异更大。D13-Y2 与 D13-Y3 是此前同策略网格，当前 H15-YZ480 同它们的比较同时跨越 y/z 网格；不作单轴收敛结论。sample 中的 `Et/Ht` 是水平 z=10/110 nm 截面，不是方柱 canonical 侧壁 trace；canonical sidewall 仍为 `NOT_MEASURED`。raw reference-plane 倏逝模振幅受指数边界相位尺度影响，保留在逐模 CSV 作诊断；跨网格的主振幅指标采用边界面 `P` 乘后的复振幅。

## 可复核文件

- [逐模/场比较分析脚本](analysis/compare_h15_yz480_to_h15_y_d13_y2_y3.py)，SHA256 `1a383ec0922637d58429efa762587dadfd9a4c01d18e5a831a8e3a6ef7b0cab7`。
- [比较 JSON](records/h15_yz480_vs_h15_y_d13_y2_y3_same_relative_only_v1.json)，SHA256 `2563d4c52b1e94f398693b5aca8d9df0df4fb9733f90a879f8bbcdb071294538`。
- [全部612模态 CSV](records/h15_yz480_vs_h15_y_d13_y2_y3_all_612_modes_v1.csv)，SHA256 `29d99c55cb3c676e874823627eeefe1a7f9c604982862c0eab37c099a09ee127`。
- [终态身份、数值和资源收据](records/h15_yz480_field14_terminal_v1.json)，SHA256 `5742b4ffbff76545b7fbdaad00f09b5f4ed2aa998eaaf622785f0f3a47acde05`。

本场是用户明确批准的第14场；不据此自动启动第15场，也不把有限 R13 结果提升为 full-DtN 或 canonical sidewall 资格。
