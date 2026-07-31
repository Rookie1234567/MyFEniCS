# Task002 M4E：Ny4-only compact dataset 报告

## 1. Dataset 身份

| 项目 | 值 |
|---|---|
| dataset_id | `task002_m4e_p5_ny4_112_v3` |
| source SHA | `10e3356ba8364286a452077f71d7e3b92ea24cd5` |
| schema | `task002.s-p5-ny4-single-fidelity-dataset.v3` |
| model | `S_PROD_FULL3D_STATIC_P5_H10_NY4` |
| route | `full3d_static_uniform_n1curl_p5_h10_ny4` |
| topology | `(6,4,14)` |
| observable | `task002.fixed-n0-orders.v3` |
| samples | 112（96 train + 16 frozen validation） |

dataset 位于 `benchmarks/artifacts/cases/119/m4e/compact_dataset/`；tracked Case119
records 保存其文件 hashes、array identity、精确设计覆盖与 checker 结论。

## 2. Array 布局

| 文件 | shape | dtype |
|---|---:|---|
| `inputs.npy` | `(112,4)` | float64 |
| `aggregates.npy` | `(112,4)` | float64 |
| `order_amplitudes.npy` | `(112,22,2,2)` | float64 |
| `order_powers.npy` | `(112,22,2)` | float64 |
| `power_carrying_mask.npy` | `(112,22,2)` | bool |
| `train_indices.npy` | `(96,)` | int64 |
| `frozen_validation_indices.npy` | `(16,)` | int64 |

输入轴为 height、width、grazing、azimuth。22 个 order 由 reflection/transmission
两侧的固定 `m=-7..+3,n=0` 构成；component 轴为 S/P，complex 轴为 real/imag。
非功率携带分量使用 NaN 加 false mask 表达 structural null，没有伪造零功率。

## 3. 独立 exact-design checker

checker 结论：

- training 96 点恰好出现一次；
- frozen validation 16 点恰好出现一次；
- missing=0、extra=0；
- source SHA、Ny4 model/route、observable v3 和 runtime topology 唯一；
- 每条 formal leakage、ledger、residual、energy、resource Gate 通过；
- sample record、arrays、split 与 order identity hashes 通过；
- Case117/Ny3 结果没有被复用；
- 8 个 discretization-audit points 不在 dataset 中。

dataset `sample_ids_hash` 为
`e511a075ab2614e9c8d18436815c5a9843bfb559e01d4b772de16ef7ad38c36b`，
split hash 为
`376a4b052a50dec54b8a8a4b6817e04e9758ab28435350461e37bd6d7f8f220f`。
独立 checker 与 Case119 checker 均为 pass。

## 4. 使用边界

该数据是 p5/Ny4 single-fidelity best-available operational HF，不是 continuum truth。
frozen-validation 响应尚未评分或读取用于模型选择。M5/PCE/GP、active learning、
angle DOE 和 inversion 均未开始，等待 Review V8。
