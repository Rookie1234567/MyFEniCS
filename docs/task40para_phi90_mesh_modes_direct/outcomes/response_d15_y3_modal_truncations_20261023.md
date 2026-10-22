# D15-Y3 模态截断 K1–K4 离线比较（2026-10-23）

## 范围与身份

用户授权在原始 D15-Y3 网格上依次完成四个 p6 凝聚直接场，截断矩形为 `m,n ∈ [-K,K]`、`K=1,2,3,4`。四场均已自然结束、清场，单场 direct/A6/能量门通过；没有重跑基准，也没有启动其他 FE。

参照是 D15-Y3 `20261021T081011.745578Z` 的**有限 R13、612 模态**场，不是无限 DtN 参照。参照 source/input/physical/resolved SHA256 分别为 `ba26075e2a871db10a81efbceeb32b51d95ea96b`、`bf27bd09cb2b01509b13d2da414919db8b14fd49842e632cfa932fb00baa5943`、`ce77eb0b9e32affdcd51da2159e5d05caf28807a32def69618546350b1bfe861`、`05b05b5518fd889fab9788e3a740f92f01b9fab0a7ae132172c620d8ea8079e4`；R13 mode SHA `1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e`。

所有 K 场保持同一物理 SHA、Y3 `[6,10,6]`/360-cell 网格和三轴 SHA、surface q28、volume q15/default，以及 `scale_homogeneous_relative_only_v1` 稀疏 cutoff/`1e-13`。active modes 分别为 36/100/196/324；各自实际 mode SHA 与选择哈希写在机器记录。逐键核对表明每个候选键都是 R13 的精确子集，所有共同 signed key 的介质、beta、boundary phase、传播/功率分类和极化等身份字段完全相同。被省略的父键在比较中以零延拓。

Y3 与 K 场 source SHA 不同，因为增加了截断配置路由；比较器核实的 p6 direct solver、cell action、fullspace DtN action、`dtn_port_3d` 与物理 runner 文件在两个 source 间没有变化。比较读取每场小型 modal JSON 和约 1.3 MB 的同坐标 sample NPZ；没有读取 VTU/resource stream、插值或拟合整体相位。

## 单场检查

| 场 | modes | condensed residual | 独立 A6 residual | 能量闭合绝对值 | 同因子校正 | workflow / 峰值树 RSS |
|---|---:|---:|---:|---:|---:|---:|
| K1 | 36 | `1.9034e-10` | `2.4115e-10` | `4.5000e-12` | 0 | 2219.82 s / 12.50 GB |
| K2 | 100 | `7.2933e-10` | `2.7796e-10` | `1.6230e-11` | 0 | 1696.21 s / 13.02 GB |
| K3 | 196 | `3.7161e-10` | `3.2626e-10` | `3.5142e-11` | 0 | 1470.81 s / 15.60 GB |
| K4 | 324 | `3.0414e-10` | `1.6110e-10` | `9.6461e-12` | 0 | 1604.98 s / 16.78 GB |

四场均分别满足 condensed `1e-9`、active-rectangle A6 `1e-6`、能量 `1e-5` 的单场门；任务树 swap peak 均为 0。它们各自求解通过不代表截断与 612-mode 参照相符。

## 三组比较门

门槛保持：全局 `R/T/A_balance/A_volume` 绝对差 `≤1e-5`；所有 612 个父 signed channel（包括 power-carrying、即便非 propagating）逐通道 `R/T` 绝对差 `≤1e-6`；边界复振幅及相同坐标复 E/H 相对 L2 差 `≤1e-4`，不作相位拟合。

| 场 | `|ΔR_total|` | `|ΔT_total|` | `|ΔA_balance|` | `|ΔA_volume|` | 全 612 最大 `|ΔR|`（key） | 全 612 最大 `|ΔT|`（key） | boundary rel. | E rel. | H rel. | 三组全过 |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|---|
| K1 | `3.32284e-6` | `1.37613e-5` **FAIL** | `1.70841e-5` **FAIL** | `1.70841e-5` **FAIL** | `6.89410e-6` top/up `(0,0,s)` **FAIL** | `5.29791e-6` bottom/down `(2,-1,s)` **FAIL** | `1.80193e-3` **FAIL** | `1.85014e-3` **FAIL** | `2.15369e-3` **FAIL** | **FAIL** |
| K2 | `2.55822e-6` | `8.74885e-7` | `3.43310e-6` | `3.43310e-6` | `5.30261e-7` top/up `(0,-4,s)` | `2.67015e-7` bottom/down `(0,0,s)` | `6.41996e-4` **FAIL** | `1.46071e-3` **FAIL** | `1.83395e-3` **FAIL** | **FAIL** |
| K3 | `2.34100e-6` | `8.63999e-7` | `3.20500e-6` | `3.20502e-6` | `5.30261e-7` top/up `(0,-4,s)` | `2.36897e-7` bottom/down `(0,0,s)` | `6.12322e-4` **FAIL** | `1.46017e-3` **FAIL** | `1.83195e-3` **FAIL** | **FAIL** |
| K4 | `2.86046e-6` | `9.91844e-7` | `3.85231e-6` | `3.85230e-6` | `1.54502e-6` top/up `(0,0,s)` **FAIL** | `1.79913e-7` bottom/down `(-1,-7,s)` | `5.54723e-4` **FAIL** | `1.21453e-3` **FAIL** | `1.54949e-3` **FAIL** | **FAIL** |

逐通道最大值在 power-carrying 集中相同；K1 有 3 个 R 和 2 个 T 父键超 `1e-6`，K2/K3 没有父键超限，K4 有 1 个 R 父键超限。K2/K3 虽然总量和所有通道 R/T 都过门，边界复幅与样本 E/H 仍超过门槛，因此不能判截断可接受。K4 的 R00,s 差就是最大 R 差 `1.54502e-6`，略超逐通道门。

## 被截掉的 R13 尾部

| 候选 | 删除父键数 | 删除的 power-carrying 键 | 其中 propagating 键 | 父尾部 `ΣR` | 父尾部 `ΣT` | 尾部 boundary 幅值相对父全量 L2 |
|---|---:|---:|---:|---:|---:|---:|
| K1 | 576 | 364 | 152 | `1.01704e-5` | `1.37310e-5` | `1.80175e-3` |
| K2 | 512 | 318 | 124 | `2.79622e-6` | `1.13621e-6` | `6.41971e-4` |
| K3 | 416 | 252 | 88 | `2.28924e-6` | `1.08222e-6` | `6.12183e-4` |
| K4 | 288 | 174 | 60 | `1.30720e-6` | `1.02794e-6` | `5.54685e-4` |

这些是参照解中被候选删除的通道贡献，不能当作完整省略耦合误差界。比较 CSV 对每个候选都保留全部 612 个 signed parent key、propagating 与 power-carrying 标签、reference/candidate R/T 和 boundary 复幅。

同坐标 E/H 样本数组为 `[5,64,40,3]`，坐标逐位相等；`E_t_interface`/`H_t_interface` 仍只是水平界面采样。canonical 方柱侧壁 trace 继续 `NOT_MEASURED`，端口继续 `FULL_DTN_NOT_VERIFIED`。本轮结论仅为：四个已算矩形截断都未同时满足原三组比较门；不能从 K2/K3 的总量/逐模通过外推边界场通过，也不能从 finite R13 推断无限 DtN。

## 可复现文件

- [分析脚本](analysis/compare_d15_y3_modal_truncations_20261022.py)，SHA256 `e1477c40202a140b1357d856d8e0f218a060ab7d5e8496d1d8944f824a53f1d6`
- [比较 JSON](records/d15_y3_modal_truncation_comparison_20261022_v1.json)，SHA256 `57769afe29d5b3497c9c6e3f23ebd5026d4fac5247a419536c4c3cadb07cbd0c`
- [612 × 4 signed-key CSV](records/d15_y3_modal_truncation_all_612_20261022_v1.csv)，SHA256 `1f80bfe6461fcefc4a7ad27476b2b2729c7dfe5e612385b2b0680d34931bfb74`
- 运行环境：`source scripts/activate_task40_phi90_pord64.sh` 后执行分析脚本。仅离线读取，不启动 FE/factor。
