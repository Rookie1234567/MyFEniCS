# Task40para outcomes summary — D13 relative-only Y2 follow-up

本阶段使用已保存的 D13 场，检查 Y2 的 relative-only DtN 稀疏提取结果，并与旧 Y2、Y、Y3 对比。**没有新 FE、factor、VTU 读取或资源流扫描。** `FULL_DTN_NOT_VERIFIED`、canonical 方柱侧壁切向检查 `NOT_MEASURED` 及旧 V4/V5 保存场失败记录继续保持。

## 当前范围与状态

| 项目 | 结果 | 状态与证据 |
|---|---|---|
| 新计算 | Y2 网格 `[6,24,14]`、2016 cells、p6 condensed direct、612 R13 模态、surface q28 / volume q15 | 已自然 exit 0；run `20261016T190312.893443Z`；source `73e2fd2c4a36c9698298235148c59aa1551d74d6`；[终态回执](../../../tmp/task40_d13_y2_scale_homogeneous_launch_v1/terminal_receipt_20261017.json) |
| 稀疏 cutoff | 新场 `scale_homogeneous_relative_only_v1`, relative tolerance `1e-13`；旧 Y/Y2/Y3 源使用 `max(1e-30, 1e-13 × global_max)` | 旧 policy 由各旧 run source 的 `dtn_port_3d.py` 实际代码核定；旧 manifest 未单独写 policy。不同策略结果必须标为混合比较 |
| 单场数值门 | 凝聚残差 `3.0670e-12 < 1e-9`；恢复场 active-rectangle A6 `3.0742e-10 < 1e-6`；同因子校正 `1` 次 | 本场直接求解检查通过；不等于全 DtN 或连续解资格 |
| 全任务状态 | D13 y 网格证据仍有 cutoff-policy 混合；full DtN、canonical sidewall trace 均未验证 | `AUTHORITY_LIMITED`；D5/M5 与后续波长阶段尚未因本记录自动启动 |

## 四场身份与总量

| 场 | y cells / total cells | cutoff policy | R total | R00,s | T total | A balance / A volume | 能量闭合差 | elapsed / peak tree RSS |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Y | 12 / 1008 | legacy absolute floor | 0.251356807082 | 0.251324114555 | 0.057128665450 | 0.691514527468 / 0.691514527469 | `8.83e-13` | 1102.52 s / 34.816 GB |
| Y2 legacy | 24 / 2016 | legacy absolute floor | 0.251355715251 | 0.251322877436 | 0.057128827393 | 0.691515457356 / 0.691515682641 | `2.25e-7` | 2451.68 s / 81.628 GB |
| Y2 relative-only | 24 / 2016 | relative-only | 0.251355663307 | 0.251322970764 | 0.057128824134 | 0.691515512560 / 0.691515512589 | `2.97e-11` | 3610.50 s / 85.741 GB |
| Y3 | 48 / 4032 | legacy absolute floor | 0.251355662447 | 0.251322969903 | 0.057128824231 | 0.691515513322 / 0.691515513275 | `4.71e-11` | 4922.42 s / 166.465 GB |

四个 run、source、input、resolved、physical、mesh、mode、sample 与 modal artifact 的完整 hash 在比较 JSON 中逐场绑定。run ID/source 简表：Y `20261016T102453.831934Z` / `9c0fe6a3…`；旧 Y2 `20261016T112452.011352Z` / `74d5aae3…`；Y3 `20261016T122621.622353Z` / `d742562e…`；relative-only Y2 `20261016T190312.893443Z` / `73e2fd2c…`。所有场的有序 612 mode key、beta、boundary phase、q28 surface 与 q15/default volume rule 一致。这里的 `A_volume` 来自材料体积分吸收记录；R/T 来自各场保存的端口 modal power。端口范围有限，仍为 `FULL_DTN_NOT_VERIFIED`。

## 旧新 Y2 与 Y/Y3 对照

| 对比 | 变化类别 | 全 612 模式 boundary outgoing 幅值相对 L2 | 最大逐模 R / T 绝对差 | E / H / 水平面 Ht 相对 L2 |
|---|---|---:|---|---|
| Y2 legacy → Y2 relative-only | 同网格、稀疏 cutoff 策略和 source 身份不同 | `3.9705e-3`；最大差 `1.48696e-3`，top `(m=+4,n=0,p)` | `9.33e-8` at top `(0,0,s)` / `1.88e-8` at bottom `(0,0,s)`；无单模差超过 `1e-6` | `9.89e-6 / 9.87e-6 / 1.8411e-4` |
| Y legacy → Y2 legacy | 只细化 y；相同 legacy cutoff | `3.9704e-3`；最大差 `1.48691e-3`，top `(m=-4,n=0,p)` | `1.2371e-6` at top `(0,0,s)` / `1.3986e-7` at bottom `(0,0,s)` | `1.1561e-5 / 3.9563e-5 / 1.8423e-4` |
| Y2 legacy → Y3 legacy | 只细化 y；相同 legacy cutoff | `3.9705e-3`；最大差 `1.48693e-3`，top `(m=-4,n=0,p)` | `9.2467e-8` at top `(0,0,s)` / `1.8888e-8` at bottom `(0,0,s)` | `9.8907e-6 / 9.8892e-6 / 1.8411e-4` |
| Y legacy → Y3 legacy | 只细化 y；相同 legacy cutoff | `2.5747e-6`；最大差 `1.27924e-6`，top `(0,0,s)` | `1.1447e-6` at top `(0,0,s)` / `1.5875e-7` at bottom `(0,0,s)` | `5.9757e-6 / 3.8353e-5 / 6.2069e-6` |
| Y legacy → Y2 relative-only | 网格与 cutoff/source 都变，混合对照 | `2.6009e-6`；最大差 `1.27832e-6`，top `(0,0,s)` | `1.1438e-6` at top `(0,0,s)` / `1.5865e-7` at bottom `(0,0,s)` | `5.9855e-6 / 3.8308e-5 / 6.2518e-6` |
| Y3 legacy → Y2 relative-only | y 网格与 cutoff/source 都不同，混合对照 | `9.2916e-7` | `8.6082e-10` at top `(0,0,s)` / `9.6151e-11` at bottom `(0,0,s)` | `2.8364e-7 / 5.8524e-7 / 1.2858e-7` |

复场差直接使用相同坐标上的已保存 complex E/H，未拟合整体相位，也未插值。样本为 12,800 点、数组 `[5,64,40,3]`，四场的坐标逐位相同。`H_t_interface` 是水平 z=10/110 nm 采样面（plane index 0/4），不是方柱侧壁的 canonical H(curl) trace；侧壁门仍 `NOT_MEASURED`。全部逐模复幅值与 R/T 在[612-mode CSV](records/d13_y_y2_y3_relative_cutoff_all_612_modes_v1.csv)。其中保存 all 612、propagating 与 power-carrying 分类；这些集合不互斥，尤其有损介质中的倏逝级可携带功率。

## retained alpha 与恢复场 auxiliary

新 Y2 的 `retained_modal_alpha.npy` 是增广解末尾 612 个 modal unknown；`recover_aux` 是 P6 完整场恢复后重新计算的 total projection。按 `auxiliary_index` 将两者逐模对齐，并对两向量逐模乘同一保存的 boundary phase `P`。结果为：

| 口径 | `||alpha||₂` | `||recover_aux||₂` | 差的 `||·||₂` | 相对差（以 alpha 为分母） |
|---|---:|---:|---:|---:|
| raw modal coefficient | `2.3608772383e75` | `2.3608772628e75` | `7.3326494226e67` | `3.1059e-8` |
| boundary `P × coefficient` | `1.1119343467` | `1.1119343467` | `1.9337e-15` | `1.7390e-15` |

612 个 `|P|` 从 `1.9057e-84` 到 `1.0`。所以 raw 系数不能跨倏逝模态直接解释物理边界误差；逐模 P 缩放后的结果与保存 outgoing boundary amplitude 自洽。对 top `m=±4,n=0,p`，`H=1.5535e-54`、`P=4.2138342e-29`；新 retained 与恢复值 raw 仍约 `1e22`，但 boundary 差分别约 `1.03e-16` 和 `5.07e-17`。新输出边界幅值模长约 `4.9117637e-7 / 4.9117632e-7`，与旧 Y2 的约 `1.4867e-3` 不同。

本场原有 legacy raw six-key projection audit 仍为 `false`（容差 `1e-10`，最大 raw outgoing 差 `1.4856556e13`），且明确 `used_as_solver_gate=false`；这里的 P-scaled alpha/recovery 相符不回写该 legacy 布尔值，也不将其改判 PASS。native port residual observation 为 `5.2117e-16`、operation scale `5533.8778`，亦非新增门。完整逐模 raw、P、P-scaled alpha/recovery 与差均在 CSV 和[JSON 记录](records/d13_y_y2_y3_relative_cutoff_comparison_v1.json)。

主控对终态保存证据另行复核了 top `m=−4/+4,n=0,p`：相应 boundary 幅值为 `4.911763694969092e-7 / 4.911763247569474e-7`，与独立 full-primal 同单位量的差为 `5.122126747848201e-16 / 6.260306451231583e-16`；六个取证 key 的最大同单位差 `6.256774122628426e-15`。这是六 key 的局部交叉核验，不等于所有 612 模态的完整 DtN 资格。

## 耗时与资源总账

截至本记录，七个成功 D13 完整 direct 场的 workflow 墙钟累计 `15,852.48 s`（`4.4035 h`）；这是墙钟时间相加，不是 CPU 时间。七场各自 peak RSS 不相加，最高单场为 Y3 的 `166,464,983,040 B`。本轮 Y2 relative-only 增加 `3,610.504 s` workflow 与 `85,740,769,280 B` tree RSS peak；单场 task swap peak `0`、PSS disabled、host-floor observe-only。此账不包含之前 setup 入口失败、saved-field diagnostics 或离线后处理用时。

| 场 | workflow seconds | peak tree RSS bytes | task swap peak bytes |
|---|---:|---:|---:|
| B | 825.435 | 15,786,909,696 | 0 |
| X | 1958.120 | 49,416,364,032 | 0 |
| Y | 1102.521 | 34,816,004,096 | 0 |
| Z | 981.796 | 30,786,502,656 | 0 |
| Y2 legacy | 2451.684 | 81,628,168,192 | 0 |
| Y3 | 4922.421 | 166,464,983,040 | 0 |
| Y2 relative-only | 3610.504 | 85,740,769,280 | 0 |

新 Y2 的有限 R13 端口—体吸收闭合 `2.9722e-11`，但 official scope 是 finite rectangle；不能从小残差、closed energy 或 612 个输出外推省略 DtN 的完整作用。没有重读旧资源流、VTU 或 larger recovered-storage coefficients；本轮 terminal resource audit 早先已对新 Y2 `resources.jsonl` 单遍完成，回执见[terminal receipt](../../../tmp/task40_d13_y2_scale_homogeneous_launch_v1/terminal_receipt_20261017.json)。

## 保留的失败、未运行与下一步

| 项目 | 状态 |
|---|---|
| 新 Y2 单场 direct/A6/能量检查 | `COMPLETED_AUTHORITY_LIMITED`；本场门通过 |
| 新旧 Y2 保存场 cutoff 对照 | 已完成；解释旧 Y2 evanescent boundary outlier 的强证据，但不是完整求解器/全 DtN 资格 |
| 旧 V4/V5 保存场 Gate | 原 `FAIL/OPEN` 历史保留；未重读或改写 |
| canonical 方柱侧壁切向 trace | `NOT_MEASURED` |
| full parent DtN 与 reference-tail 扩展 | `FULL_DTN_NOT_VERIFIED` / `NOT_RUN` |
| Y4、D5、额外 FE/factor | `NOT_RUN` |

唯一建议的下一项 same-policy 方向验证是：在已有 Y3 网格 `[6,48,14]`、R13、q28 surface/q15 volume 上以 relative-only 同一 cutoff 重新求解一次，再与本次 Y2 relative-only 作 y 单变量比较。它只回答最后两级 y 方向在同一提取策略下是否一致；不启动 Y4，不自动扩模式，不代表全 DtN 尾部通过。该项未在本次执行。

## 可复现证据

- [分析脚本](analysis/compare_d13_relative_cutoff_runs.py)，SHA256 `dc1d60e3be5a7181390f2878f657f74bd41e6d8d1f47227273ccf22fa08fa53c`
- [比较 JSON](records/d13_y_y2_y3_relative_cutoff_comparison_v1.json)，SHA256 `36ae9ae1d3dedf31243d1fc74bdae994baf4849532cc5bb1deaf6d0ceae0fafc`
- [全部 612 mode CSV](records/d13_y_y2_y3_relative_cutoff_all_612_modes_v1.csv)，SHA256 `02cbe9e448a6bb3bc3238c4e51e9344d1e620cb10d5b24c2d9f1e76963ccb7eb`
- [保留的旧 Y/Y2/Y3 比较](response_d13_y_y2_y3_comparison.md)：没有覆盖历史报告；本文件补充 relative-only Y2。
