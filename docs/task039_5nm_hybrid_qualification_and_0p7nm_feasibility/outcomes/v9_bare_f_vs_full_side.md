# V9-1：bare-F 与完整 side residual 诊断

## 结论先行

本轮只重新评估 bottom 侧的 `J1` 和 `F1`。`r_F` 是把候选近似逆作用于 bare `F` 后的真实残差，`r_A`
是把同一候选作用于完整 `A_side` 后的真实残差；二者都由真实 PETSc action 计算，不是 reference-solution
误差。`physical_side_rhs` 为零，只记录为 degenerate，不进入 mandatory Gate。

| 结果 | 实测/裁决 |
|---|---|
| 正式分类 | `CONTROLLED_NUMERICAL_NEGATIVE` |
| 直接原因 | single-layer sweep 对 bare `F` 已严重失效；J1 优于 F1，但两者仍未达到 residual Gate |
| J1 mandatory `r_F` | `24.9344011544 / 30.6816397942 / 50.7689715097 / 48.9025618833 / 50.6201709297` |
| J1 mandatory `r_A` | `24.5336746747 / 29.9755365263 / 50.2410648372 / 47.4220201894 / 49.1083939012` |
| J1 `r_A/r_F` | `0.970–0.990`；完整 side 没有放大 J1 的 bare-F 误差 |
| F1 mandatory `r_F` | `202.5760502350 / 304.9206423328 / 328.3617777975 / 351.6456668970 / 367.2128685567` |
| F1 mandatory `r_A` | `81.3295078519 / 119.1767628382 / 141.0763808200 / 127.1634413153 / 129.8984826821` |
| F1 `r_A/r_F` | `0.354–0.430`；DtN/Woodbury 缓和了 bare-F 残差，但仍远超 Gate |
| finite / repeat / linearity | J1 全部通过；F1 repeat/linearity 最大 `3.6229046068e-11`，均 `<=1e-10` |
| K | rank `296`，condition `63.9432505898`，两方法相同 factor set |
| construction | `23.8684272766 GiB <=45 GiB`，swap `0` |
| retained | `not_run`；数值失败后没有 preferred candidate |

因此根因是 single-layer sweep 对 bare `F` 本身不够准确，不是 DtN/Woodbury 单独放大了 J1。J1 明显优于
F1，但这只是一项诊断结论，不能把任一方法提升为 V9-3 inner solver。

## 五个 frozen probe

阈值为 mandatory true residual `<=1e-2`，preferred modal/external `<=1e-3`，repeat/linearity `<=1e-10`。
数值顺序为 positive modal、negative modal、external、random773、random779。

| method | probe | `r_F` | `r_A` | `r_A/r_F` | repeat | linearity |
|---|---|---:|---:|---:|---:|---:|
| J1 | positive | 24.9344011544 | 24.5336746747 | 0.983929 | 2.23e-13 | 2.15e-13 |
| J1 | negative | 30.6816397942 | 29.9755365263 | 0.976986 | 4.39e-13 | 1.91e-13 |
| J1 | external | 50.7689715097 | 50.2410648372 | 0.989602 | 3.69e-13 | 6.30e-13 |
| J1 | random773 | 48.9025618833 | 47.4220201894 | 0.969725 | 2.88e-13 | 4.19e-13 |
| J1 | random779 | 50.6201709297 | 49.1083939012 | 0.970135 | 2.30e-13 | 3.19e-13 |
| F1 | positive | 202.5760502350 | 81.3295078519 | 0.401476 | 3.08e-11 | 2.67e-11 |
| F1 | negative | 304.9206423328 | 119.1767628382 | 0.390845 | 1.33e-11 | 1.61e-11 |
| F1 | external | 328.3617777975 | 141.0763808200 | 0.429637 | 1.16e-11 | 2.28e-11 |
| F1 | random773 | 351.6456668970 | 127.1634413153 | 0.361624 | 2.62e-11 | 3.62e-11 |
| F1 | random779 | 367.2128685567 | 129.8984826821 | 0.353742 | 1.95e-11 | 2.58e-11 |

`physical_side_rhs` 的 `r_F=r_A=0`，但 source norm 为零，因此 `degenerate=true`、`mandatory=false`，不参与上述
最坏值或 pass 判定。

## 计数、耗时与对象边界

| method | setup s | holdout s | correction apply s | bare-F/A true matvec | side-inverse apply | layer solves |
|---|---:|---:|---:|---:|---:|---:|
| J1 | 78.705259702 | 7.447137749 | 4.981149436 | 6 / 6 | 18 | 1920 (`320` each layer) |
| F1 | 86.680200840 | 7.970189338 | 5.368767116 | 6 / 6 | 18 | 1920 (`320` each layer) |

两方法复用同一组六层 factor；每个方法的 Woodbury 在下一个方法前销毁并 collective cleanup。最终 layer factor
为 `6→0`，full-side/global direct factor `0/0`，nested KSP `0`。`FB1/FB2/FB4` 没有执行，不能从旧 V8
记录复制为本轮诊断结果。

## 资源、身份和证据

父 watchdog 的完整 process-tree 历史峰值为 `25,628,528,640 B = 23.8684272766 GiB`，低于本 route
`48,318,382,080 B = 45 GiB` hard stop，swap 为 `0`。construction resource pass；因为 numerical Gate
失败，没有 preferred retained candidate，overall retained 是 `not_run`，不是失败值也不是 `30 GiB` pass。

本次 route identity 是 schema/profile/method/source SHA：

```text
schema  = task039.v9.h4.bare_f_full_side.diagnostic.v1
profile = task039.v9.h4.bare_f_full_side.diagnostic.v1
method  = task039_v9_h4_bare_f_full_side_diagnostic
source  = 2faf2a1a89a065e2985e46e462c6b7396f72b051
```

复用的 frozen exact-bottom holdout 绑定 producer source `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f`、catalog
SHA256 `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384`、8 个 producer ranks、6 个 labels
和 96 个 response artifacts。selected-mode packet 未打开；exact spool 只在 setup 后加载用于 holdout，随后释放。

raw 为 ignored local evidence，不提交大型文件：

```text
results/task039_v9_h4_bare_f_full_side_diagnostic_mpi8_2faf2a1a/
```

compact record：[task039_v9_bare_f_full_side_diagnostic_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_bare_f_full_side_diagnostic_v1.json)。

V9-2 尚未开始；本轮没有重跑、没有进入 FB、outer、recovery 或 physics。

## 通俗解释

可以把 bare `F` 看成只描述有限元局部耦合的原始系统，把 `A_side` 看成再加上 DtN/Woodbury 端口影响后的完整
side operator。J1 直接按层解局部块，F1 再加入一次前向层间传递。实测表明 J1 对原始 `F` 已产生约几十倍残差，
所以问题首先在单层 sweep 近似本身；加入完整端口作用并没有把 J1 进一步放大，F1 甚至降低了相对残差，但离
`1e-2` 数值要求仍差很多。低内存和 finite/repeat/linearity 通过不能替代真实 residual 通过。
