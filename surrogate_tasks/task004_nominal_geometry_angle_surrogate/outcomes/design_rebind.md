# 冻结设计的 source-metadata rebind

Case123 的四组角度 tuples 没有改变，只把 source metadata 从历史失败身份
重新绑定到 clean implementation SHA `fdf961545f217d620e22800f2704ae9913a6d270`。
每个设计仍固定 `h=120 nm, w=17 nm, wavelength=13.5 nm, S`，角度域仍是
`grazing=0.5–10°`、`azimuth=0–90°`。

| design | count | point tuple SHA256 | source dirty |
|---|---:|---|---|
| training | 96 | `bfd68a374e5510284a972c640c6332d818917052ae30bd77c10af5240f0500ef` | false |
| frozen validation | 24 | `af6cc7c87236aa2e1050b40f1cca1282932e071b22b3b767057b94bc8c11af57` | false |
| candidate pool | 4096 | `db2a6155274614b5129846ace0a277fe69161f2e5120966d7968d6b210d981fa` | false |
| anchors | 5 | `63decea83a844d49a9e6a49e0ca01dddf548b8e2e592eea1b3bfadfaf8ec63f5` | false |

独立 checker 重新计算了四个 hash，确认 training/validation 无 tuple 交集，
并保留了显式 anchor overlap 记录（anchor indices 0–3 与 training 重合，
这是资格化 anchor 允许的重叠，不是 validation 泄漏）。

生产 identity 冻结为 `S_PROD_FULL3D_STATIC_P5_H10_NY4` /
`full3d_static_uniform_n1curl_p5_h10_ny4`，parameter schema 为
`task002.s-p5-ny4-production-parameters.v3`，observable schema 为
`task002.fixed-n0-orders.v3`。
