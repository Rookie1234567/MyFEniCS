# D13 同策略 Y2/Y3 收口

Y3 已在前一执行阶段完成；本文的比较阶段只使用已经结束的 Y2/Y3 有限 R13 直接解，分析把 y 网格从 24 层加密到 48 层后端口振幅、逐级功率和复电磁场的变化。相同策略指两场均用 `scale_homogeneous_relative_only_v1`（稀疏端口项按相对最大值筛选，不带固定绝对下限），相同 612 模态、q28 表面积分与 q15/default 体积分；比较阶段没有再运行 FE、分解、读取 VTU 或重扫资源流。

## 两场身份与单场检查

| 场 | y 网格 / cells | source / input | physical / resolved SHA | R / R00,s / T | A balance / A volume | 能量闭合绝对差 | 凝聚 / A6 残差 | elapsed / 峰值整树 RSS |
|---|---|---|---|---|---|---:|---|---|
| Y2 relative-only | 24 / 2016 | `73e2fd2c4a36c9698298235148c59aa1551d74d6` / `7908141fe455ee73a1c8f213970a5c5655095a31f6afd10ce18904367b63a994` | `ac65772c3fda31f22599824023f43e05e62b8292de31652dff226909fc83fa7b` / `69d1e4fc40ca9e726ec0b7163217d72fc22b61022ee1a6c92235d05aa0982246` | 0.251355663307 / 0.251322970764 / 0.057128824134 | 0.691515512560 / 0.691515512589 | 2.9722e-11 | 3.0670e-12 / 3.0742e-10 | 3610.504 s / 85,740,769,280 B |
| Y3 relative-only | 48 / 4032 | `8faf8094e5309e7e7c0f0a094276cbacb31c1a00` / `0bcf87e01f6e17cc89808e0296cc24aafe8df3deb4f7265fe4c60b93e4ac6e22` | `96894bba4dcf50858ccc83b35ef227ef5b6facd363b0b0505bcc9a140ad3fee1` / `9bcdc23e93b6901b4147e2bf235c8b6c986d00c7a069a43c2ae7d834d1903224` | 0.251355662436 / 0.251322969893 / 0.057128824230 | 0.691515513334 / 0.691515513276 | 5.7914e-11 | 1.0770e-11 / 1.2994e-9 | 7391.328 s / 179,617,648,640 B |

两场 612 模态有序身份 SHA 都是 `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e`，稀疏策略身份 SHA 是 `bd35b7553d1e0397425f933ddb59522b8a11239a827404496fb5e77a4e5d57ba`，表面 q=28，体积分记录相同且为 q15/default。x、z 轴 SHA 完全相同，只有 y 轴变化。两个 `physical_model_sha256` 不同，因为 resolved identity 把 y 离散和 Y2/Y3 profile/run provenance 纳入哈希；逐字段比较中其余差异仅为 y 轴、网格计划、预期单元/材料标签计数及相应 profile/provenance 身份。几何、材料、入射、边界参数没有随本次 y 加密改变。

Y3 自然 exit 0、后代清空；凝聚残差 `1.0770119658e-11 < 1e-9`，恢复场 active-rectangle A6 `1.2993912130e-9 < 1e-6`，同一因子校正 1 次（上限 2）。`R+T+A_volume` 闭合绝对差 `5.7914e-11`，小于该场 `1e-5` 能量门。终态直接结果为 `AUTHORITY_LIMITED`，不是完整 DtN 或连续解资格。

## Y2 到 Y3 的差异

| 可观测量 | Y2→Y3 差异 | 口径 |
|---|---:|---|
| 总反射 R | `−8.7031087892e-10` | 所有活动端口功率汇总 |
| 零级反射 R00,s | `−8.7024465412e-10` | s 偏振零级；p 分量另行保留 |
| 总透射 T | `+9.6121055559e-11` | 所有活动端口功率汇总 |
| A balance | `+7.7418982336e-10` | `1−R−T` |
| A volume | `+6.8655392482e-10` | 材料体积分吸收；Grating `+6.2456928518e-10`，substrate `+6.1984639643e-11` |
| 612 模 boundary outgoing 复振幅 | 相对 L2 `1.84826914e-9`；最大绝对差 `9.29326612e-10`，top `(0,0,s)` | 对每个模式直接比较保存的边界平面复振幅，不作相位拟合 |
| 612 模逐级反射 R | 最大绝对差 `8.70244654e-10`，top `(0,0,s)` | 未删倏逝或零功率记录 |
| 612 模逐级透射 T | 最大绝对差 `9.60953817e-11`，bottom `(0,0,s)` | 未删倏逝或零功率记录 |
| 复 E 样本 | 相对 L2 `2.83648098e-7` | 12,800 个共同采样点 |
| 复 H 样本 | 相对 L2 `5.85241044e-7` | 与 E 同坐标 |
| 水平采样面的切向 Ht | 相对 L2 `1.28546577e-7` | z=10/110 nm 水平面，不是方柱侧壁 |

模式数分类为全部 612、propagating 166、power-carrying 390、evanescent/nonpropagating 446；分类可重叠。所有 612 行的复振幅、单模功率和差值见 CSV。未经 boundary phase 缩放的倏逝模 raw 系数差相对 L2 为 `3.1363e-5`，数值受指数尺度影响；同一模式乘保存的 boundary phase 后，物理端口面复振幅差是上表中的 `1.8483e-9`。两种口径均保留，raw 差不当作边界面误差。

样本坐标逐位相同，E/H 直接作复数差，没有整体相位拟合或空间插值。保存的 `H_t_interface` 位于水平 z 平面，不能替代 canonical pillar-sidewall H(curl) trace。`FULL_DTN_NOT_VERIFIED` 与 `AUTHORITY_LIMITED` 保持；原 V4/V5 saved-field max-facet `FAIL/OPEN` 历史不改写。此比较支持在当前有限 R13 和相同 relative-only cutoff 下，Y2 与 Y3 的结果很接近，但不能证明省略 DtN 尾部或连续网格收敛。

## 资源与证据

Y3 workflow 为 `7391.328 s`，同时采样整树 RSS 峰值 `179,617,648,640 B`（约 167.282 GiB），任务进程树 swap 峰值 `0 B`，PSS 按 profile 禁用，后代已清空。宿主全局观察到 `pswpin +3 pages`、`pswpout +0`；这是 WSL 全局计数，未归因到本任务。无固定 RSS cap，本场使用 host-available-floor 监督。

比较脚本两次在读取小 NPZ 后因摘要键校验退出，第三次已生成 CSV 但在 JSON 序列化 NumPy 标量处退出，第四次成功写出最终 JSON；因此两个约 1.3 MiB 的 sample NPZ 各读取 4 次。没有读取 VTU，也没有重扫 `resources.jsonl`。本记录明确保留该读取次数。

- [可复现比较脚本](analysis/compare_d13_same_policy_y2_y3.py)，SHA256 `e9bf78b4b2c4b3ae2caa83dd68c26c6694f75623aa4d806f94a9d828368d1b44`。
- [同策略比较 JSON](records/d13_y2_y3_same_relative_only_comparison_v1.json)，SHA256 `a701e86e557e19e19d52ea7753f95e90467fdf1bdf6b8c4f5866f3f44ae9329`。
- [全部 612 模态 CSV](records/d13_y2_y3_same_relative_only_all_612_modes_v1.csv)，SHA256 `be2b34407c6c4b98de1c65bf7b276676154a92ef9e4363b52147d5b33bd894bb`。
- 本场原始 run 目录位于 ignored `results/`；tracked JSON 保存 source/input/physical/resolved、run summary/manifest、终态、模式、积分、资源与输出 artifact hash。ignored 主机回执只在运行工作站可访问，不作为远端 Git 文件。
