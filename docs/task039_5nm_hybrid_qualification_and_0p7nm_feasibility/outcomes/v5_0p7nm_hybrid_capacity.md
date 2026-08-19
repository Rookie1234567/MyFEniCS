# V5 0.7 nm / 2 TB Hybrid capacity envelope

本页不是 0.7 nm 正式算例。它把现有 h4/h5 measured evidence 与旧的 0.7 nm derived estimate 放在同一张表中，说明哪些只是容量信封，哪些还缺少真实矩阵、factor 和 recovery 数据。

## 物理内存线

下表按 `2 TiB = 2048 GiB` 作为规划基点；这不是对机器厂商十进制 TB 标称的替换。70/80/90% 只是容量风险线，不是 solver Gate。

| 线 | 规划值 |
| --- | ---: |
| 70% | `1433.6 GiB` |
| 80% | `1638.4 GiB` |
| 90% | `1843.2 GiB` |

## 可追溯对象容量

```math
K = H - D F^{-1} C,
\qquad
y = F^{-1}r + F^{-1}C K^{-1}D F^{-1}r.
```

这里的 `F` 是侧向显式系统，`K` 是 Woodbury 修正矩阵；表中 bytes 是数组或 CSR payload 的对象容量，不能加总成 process-tree RSS。

| 对象/阶段 | 当前 evidence | 口径 | 0.7 nm 结论 |
| --- | --- | --- | --- |
| h4 exact-side setup peak | `85.376991272 GiB` | measured process-tree peak，setup-only | 当前 h4 baseline；不含完整 solve |
| h4 matched direct | `93.377006531 GiB` | measured process-tree peak | reference，不是 0.7 nm 预测 |
| h4 V4 iterative | `104.334560394 GiB` | measured full-run process-tree peak | numerical/physics pass，资源 regression |
| h4 W bottom/top | `74961408 + 83261952 B = 158223360 B` | measured/recorded object bytes | 不是 RSS，也不是 0.7 nm scale law |
| h4 streaming C action | `97507312 B` | derived CSR estimate | 对象容量变化约 `60716048 B`，不等于 RSS saving |
| h4 exact factor bottom/top | `25719433640 / 25695030824 B` | derived CSR/factor estimate from V5-2 telemetry | factor-ready object 很大；未给出 0.7 nm factor authority |
| h4 P/T coupling | projection `87095048 B`，每侧 positive/negative traction `88149608 B` | derived PETSc CSR estimates | 不能代替 0.7 nm reconstruction |
| h4 modal Schur | `960 x 960` complex128，约 `14745600 B` per matrix/LU | measured/derived component evidence | 与 full factor/RHS 不同量级 |
| h4 fixed-budget | setup `21.677326202393 GiB` | measured local/coarse setup interval；无 numerical upper bound | numerical Gate failed，不能作为可行候选 |
| h5 sidecar | consumer `50.3562393188 GiB` | measured current h5 sidecar | 不与 h4 网格收敛或 0.7 nm 等同 |
| h4/h5 current direct RSS ratio | `93.37700653076172 / 50.356239318847656 = 1.854328436631525` | derived engineering capacity ratio | h5 own Gate borderline；不是 continuum fit |

## 0.7 nm envelope 与缺口

| 项目 | 现有估计/基点 | 状态与不确定性 |
| --- | --- | --- |
| Full3D FE rows/NNZ | 旧 p6/h1 estimate `173802000` DoF、`51192000` active trace、`43283050000` NNZ | `derived`，不是 0.7 nm formal artifact |
| Full3D factor values-only | `3234.18–32341.76 GiB` | `predicted/conditional`；缺真实 ordering、fill、pivot、OOC、recovery |
| 单 air-side Hybrid W | `201.22 GiB` | `derived` from earlier scaling；substrate/two-side coupling unresolved |
| 单 air-side W + K/LU | `205.049–208.878 GiB` | `derived/predicted/conditional`；约为 2 TiB 的 `10.0–10.2%`，低于 70% line；相对旧 `256 GiB` hard-stop 才是高占用；完整 two-side 总峰值仍 unresolved |
| hypothetical global W | `12228.01 GiB` | `not_authoritative`，不用于 Hybrid conclusion |
| P/T、modal Schur、Krylov/recovery | 没有 0.7 nm reduced operator/RHS/field mapping | `unresolved`；不能从 h4 bytes 线性推断 |

```math
B_{\mathrm{payload}}(M) = B_{\mathrm{header}} + M\,B_{\mathrm{item}},
\qquad
\mathrm{RSS}_{\mathrm{peak}} \ne \sum B_{\mathrm{payload}}.
```

因此当前只能给 conditional envelope：已知的 air-side component 自身低于 2 TiB 的 70% line，但没有 two-side、side factor、P/T、modal、recovery 和 allocator 的总峰值上界，不能裁决完整 Hybrid 是否低于 `70%/80%/90%` 任一条线。Full3D factor values-only 的 `3234.18–32341.76 GiB` 下界则已超过 2 TiB 的 90% line；这仍是 predicted/conditional，不是 0.7 nm formal result。本轮不做新的 PDE、QEP 或参数扫描。
