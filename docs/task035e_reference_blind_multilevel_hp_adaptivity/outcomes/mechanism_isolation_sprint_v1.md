# Task035e h/p mechanism-isolation sprint 结果

## 1. 结论

本轮停止沿 H3 继续迭代，并保留 C2、P3、H2、H3 的全部历史负结果。
开始时的 development Pareto incumbent 恢复为 C1；随后在同一
`160-leaf` 网格上完成两个 MPI8 判别点：

| ID | 空间 | E2 / Einf | 通过 tolerance | rows / matrix NNZ / factor NNZ | simultaneous RSS peak | 结论 |
|---|---|---:|---:|---:|---:|---|
| C1 | 15/138/7 个 p4/p5/p6 cell | 860,562.378 / 5,764,876.171 | 1/59 | 20,564 / 11,084,868 / 43,034,248 | 8,345.027 MiB | 本轮起点 |
| A | global p6 saturation | 1,498.841 / 10,158.841 | 4/59 | 31,760 / 26,088,224 / 101,581,976 | 12,335.223 MiB | 精度强正信号；11 GiB Gate 失败 |
| C | fixed p5 trace + p6 interior | 5,627.897 / 41,001.145 | 0/59 | 21,680 / 12,503,824 / 48,120,600 | 8,998.922 MiB | **接受为新的 development Pareto incumbent** |

C 相对 C1：

- E2 改善 `99.346021%`，Einf 改善 `99.288777%`；
- power、amplitude、totals、fields E2 分别改善
  `99.350519%`、`93.691964%`、`95.163287%`、`76.689073%`；
- rows、matrix NNZ、factor NNZ 分别增加
  `5.426960%`、`12.800838%`、`11.819312%`；
- factor 属于 `10%–25%` 成本档，而 E2 改善远高于要求的 `2%`；
- residual、energy、Floquet、hanging、MPI8、11 GiB 和 zero-swap
  Gate 全部通过。

因此 C 按本轮规则接受。它的 actual conforming active FE DoF 为
`97,775`，高于 `90,000` advisory target，但凝聚后仅 `21,680` rows；
这项 advisory miss 原样保留，不改写为 hard-Gate pass。

C 仍不是最终解：`0/59` 目标进入固定 tolerance。结果分类保持
`REFERENCE_VISIBLE_DEVELOPMENT_SPRINT`，不获得 reference-blind 或 hidden
audit credit。

## 2. 身份和执行边界

- 分支：
  `codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity`
- 本轮开始 HEAD：
  `a343dd4d049a57485cbbed34b79421fe625c1050`
- 两条新 PDE 的 numerical source：
  `f1ba5627f163da54fa383b43be58fd38c0da7bc9`
- ABI：MPI8、PETSc `complex128` / `int32`
- 两条 PDE 严格串行运行；C 在 A 完整结束并评价后才启动
- 复用既有 worker；没有新增或修改 numerical source
- ordinary default 未修改
- 没有启动相同 broad-p、isotropic full-h、Path B、Hybrid、p7、
  level-3、迭代法、reference 重算或 exact selected-action Schur

## 3. 既有 V2 endpoint 的严格 E2² 前十贡献

下面的百分比是该 candidate 全部 59 项
`sum(((J-Jref)/tau)^2)` 中的严格贡献比例。固定 reference 和 tolerance
均未修改。

### C1

|#|goal|reference|candidate|tau|normalized error|E2² contribution|
|-:|---|---:|---:|---:|---:|---:|
|1|`top:m-7:n0:power`|6.26510524e-07|0.00576550268|1e-09|5764876.17|76.061212%|
|2|`bottom:m-7:n0:power`|2.36110528e-06|0.00551499629|1.8140519e-09|3038851.97|21.135006%|
|3|`bottom:m-6:n0:power`|8.34318008e-09|0.00109821014|1e-09|1098201.8|2.760245%|
|4|`top:m-1:n0:power`|6.66799489e-06|0.00031841558|3.33399744e-09|93505.6461|0.020011%|
|5|`top:m-7:n0:co_amp_real`|-0.000505265017|-0.0482121916|1e-06|-47706.9266|0.005209%|
|6|`scalar/R_total`|0.000762007531|0.0685259183|1.73268867e-06|39109.1094|0.003501%|
|7|`bottom:m-7:n0:co_amp_imag`|-8.73666504e-05|0.0384478249|1e-06|38535.1916|0.003399%|
|8|`top:m0:n0:power`|0.000752888385|0.0623430295|1.73049441e-06|35591.0661|0.002899%|
|9|`scalar/R00_total`|0.000752888385|0.0623430295|1.73049441e-06|35591.0661|0.002899%|
|10|`bottom:m-1:n0:power`|2.17848209e-05|0.00032578625|1.08924105e-08|27909.4723|0.001783%|

### C2

|#|goal|reference|candidate|tau|normalized error|E2² contribution|
|-:|---|---:|---:|---:|---:|---:|
|1|`top:m-7:n0:power`|6.26510524e-07|0.00669273499|1e-09|6692108.48|85.922867%|
|2|`bottom:m-7:n0:power`|2.36110528e-06|0.0045505721|1.8140519e-09|2507211.07|12.060480%|
|3|`bottom:m-6:n0:power`|8.34318008e-09|0.0010183181|1e-09|1018309.75|1.989494%|
|4|`top:m-1:n0:power`|6.66799489e-06|0.000280395257|3.33399744e-09|82101.8211|0.012933%|
|5|`top:m-7:n0:co_amp_real`|-0.000505265017|-0.0510139078|1e-06|-50508.6428|0.004895%|
|6|`bottom:m-7:n0:co_amp_real`|0.000981020042|0.0409554963|1e-06|39974.4762|0.003066%|
|7|`bottom:m-1:n0:power`|2.17848209e-05|0.000327177421|1.08924105e-08|28037.1916|0.001508%|
|8|`scalar/R_total`|0.000762007531|0.0477177264|1.73268867e-06|27099.9169|0.001409%|
|9|`top:m0:n0:power`|0.000752888385|0.0406551362|1.73049441e-06|23058.2933|0.001020%|
|10|`scalar/R00_total`|0.000752888385|0.0406551362|1.73049441e-06|23058.2933|0.001020%|

### H2

|#|goal|reference|candidate|tau|normalized error|E2² contribution|
|-:|---|---:|---:|---:|---:|---:|
|1|`top:m-7:n0:power`|6.26510524e-07|0.00576449158|1e-09|5763865.07|76.067174%|
|2|`bottom:m-7:n0:power`|2.36110528e-06|0.00551287748|1.8140519e-09|3037683.97|21.127828%|
|3|`bottom:m-6:n0:power`|8.34318008e-09|0.00109821193|1e-09|1098203.59|2.761439%|
|4|`top:m-1:n0:power`|6.66799489e-06|0.000318454187|3.33399744e-09|93517.2259|0.020024%|
|5|`top:m-7:n0:co_amp_real`|-0.000505265017|-0.0482076192|1e-06|-47702.3542|0.005210%|
|6|`scalar/R_total`|0.000762007531|0.0685212017|1.73268867e-06|39106.3873|0.003502%|
|7|`bottom:m-7:n0:co_amp_imag`|-8.73666504e-05|0.0384369069|1e-06|38524.2735|0.003398%|
|8|`top:m0:n0:power`|0.000752888385|0.062339235|1.73049441e-06|35588.8734|0.002900%|
|9|`scalar/R00_total`|0.000752888385|0.062339235|1.73049441e-06|35588.8734|0.002900%|
|10|`bottom:m-1:n0:power`|2.17848209e-05|0.000325911214|1.08924105e-08|27920.9449|0.001785%|

### P3

|#|goal|reference|candidate|tau|normalized error|E2² contribution|
|-:|---|---:|---:|---:|---:|---:|
|1|`top:m-7:n0:power`|6.26510524e-07|0.00668710964|1e-09|6686483.13|85.803111%|
|2|`bottom:m-7:n0:power`|2.36110528e-06|0.00457251872|1.8140519e-09|2519309.19|12.180650%|
|3|`bottom:m-6:n0:power`|8.34318008e-09|0.00101801679|1e-09|1018008.45|1.988888%|
|4|`top:m-1:n0:power`|6.66799489e-06|0.000282058868|3.33399744e-09|82600.8053|0.013094%|
|5|`top:m-7:n0:co_amp_real`|-0.000505265017|-0.0509745453|1e-06|-50469.2803|0.004888%|
|6|`bottom:m-7:n0:co_amp_real`|0.000981020042|0.0410754384|1e-06|40094.4184|0.003085%|
|7|`bottom:m-1:n0:power`|2.17848209e-05|0.000327615969|1.08924105e-08|28077.4534|0.001513%|
|8|`scalar/R_total`|0.000762007531|0.0477778515|1.73268867e-06|27134.6173|0.001413%|
|9|`top:m0:n0:power`|0.000752888385|0.0407183543|1.73049441e-06|23094.8251|0.001024%|
|10|`scalar/R00_total`|0.000752888385|0.0407183543|1.73049441e-06|23094.8251|0.001024%|

### H3

|#|goal|reference|candidate|tau|normalized error|E2² contribution|
|-:|---|---:|---:|---:|---:|---:|
|1|`top:m-7:n0:power`|6.26510524e-07|0.00576302136|1e-09|5762394.85|76.062107%|
|2|`bottom:m-7:n0:power`|2.36110528e-06|0.00551231971|1.8140519e-09|3037376.5|21.132923%|
|3|`bottom:m-6:n0:power`|8.34318008e-09|0.00109795545|1e-09|1097947.11|2.761374%|
|4|`top:m-1:n0:power`|6.66799489e-06|0.000318665352|3.33399744e-09|93580.5628|0.020060%|
|5|`top:m-7:n0:co_amp_real`|-0.000505265017|-0.0482033969|1e-06|-47698.1319|0.005212%|
|6|`scalar/R_total`|0.000762007531|0.0684984718|1.73268867e-06|39093.269|0.003501%|
|7|`bottom:m-7:n0:co_amp_imag`|-8.73666504e-05|0.0384170344|1e-06|38504.401|0.003396%|
|8|`top:m0:n0:power`|0.000752888385|0.0623177103|1.73049441e-06|35576.4349|0.002899%|
|9|`scalar/R00_total`|0.000752888385|0.0623177103|1.73049441e-06|35576.4349|0.002899%|
|10|`bottom:m-1:n0:power`|2.17848209e-05|0.000326095196|1.08924105e-08|27937.8358|0.001788%|

前三个 power goals 对 C1/H2/H3 合计贡献约 `99.956%`，对 C2/P3
也超过 `99.97%`。这说明 H2/H3 的微小总 E2 改善并未改变主误差机制，
而 broad-p 进一步放大了 `top:m-7:n0:power`。

## 4. 四类 category E2

| ID | aggregate E2 | Einf | power E2 | amplitude E2 | totals E2 | fields E2 |
|---|---:|---:|---:|---:|---:|---:|
| C1 | 860,562.378 | 5,764,876.171 | 1,652,381.126 | 12,337.220 | 23,681.047 | 83.1866 |
| C2 | 939,902.026 | 6,692,108.476 | 1,804,776.220 | 12,225.951 | 15,968.011 | 83.1317 |
| H2 | 860,377.728 | 5,763,865.068 | 1,652,026.544 | 12,335.616 | 23,679.494 | 83.1863 |
| P3 | 939,767.088 | 6,686,483.133 | 1,804,516.906 | 12,234.586 | 15,990.328 | 83.1507 |
| H3 | 860,186.917 | 5,762,394.854 | 1,651,660.154 | 12,334.490 | 23,671.429 | 83.1956 |
| A | 1,498.841 | 10,158.841 | 2,777.615 | 468.028 | 646.907 | 10.0087 |
| C | 5,627.897 | 41,001.145 | 10,731.896 | 778.236 | 1,145.384 | 19.3916 |

这项分解避免了 totals 的局部改善掩盖 power 恶化，也证明 A、C 的四类
目标均不是以牺牲另一类为代价获得总体改善。

## 5. Task35b h13/h14/h15 离线评价

| existing artifact | status | evaluated | partial E2 | power | amplitude | totals | fields |
|---|---|---:|---:|---:|---:|---:|---|
| h13 directional-z | partial | 53/59 | 1.524805 | 1.544134 | 1.560303 | 1.197631 | missing |
| h14 directional-z | partial | 53/59 | 2.403424 | 2.316124 | 2.583708 | 1.157865 | missing |
| h15 | partial | 53/59 | 6.611045 | 7.274470 | 6.762803 | 1.112701 | missing |

三条旧 artifact 缺少：

```text
scalar/interface_probe_l2
scalar/volume_probe_l2
complex/interface_probe_complex/real
complex/interface_probe_complex/imag
complex/volume_probe_complex/real
complex/volume_probe_complex/imag
```

因此不能写成 59-goal pass。h13/h14 对 power、amplitude 和 totals
给出明显的 directional-z 正信号，但它们使用不同 structured mesh；
本轮没有重跑或补造旧 PDE。

## 6. C2 的 24 个 p-up target

C2 实际 solver plan 是 C0→C1 与 C1→C2 action 的 union；本节分类的是
执行过的 C0→C2 共 24 个 target，不把它误写成仅 C1→C2：

| transition / mechanism | count |
|---|---:|
| p4→p5；edge/face trace-affecting | 10 |
| p5→p6；edge/face trace-affecting | 10 |
| p5→p6；cell-interior-only | 4 |

它们共同改变 `15` 个 physical edges 和 `33` 个 physical faces。

| material / z-band nm | trace-affecting | interior-only |
|---|---:|---:|
| substrate / -10..-5 | 4 | 0 |
| substrate / -5..0 | 1 | 2 |
| air / 10..20 | 4 | 0 |
| air / 20..40 | 0 | 1 |
| air / 40..60 | 0 | 1 |
| air / 60..80 | 2 | 0 |
| air / 120..125 | 7 | 0 |
| air / 120..130 | 1 | 0 |
| air / 125..130 | 1 | 0 |

全部 24 个 canonical target、degree 和分类位于 compact；结果说明 C2
并不是一个纯 interior 或纯 trace 实验，不能用其负结果直接关闭任一机制。

## 7. A/C 机制分离和资源判定

A 与 C 具有完全相同的 `160-leaf` forest，且 160 个 cell interior
全部为 p6。两者的差别是：

- A：global p6 trace；
- C：global p5 trace。

因此 A−C 是本轮唯一严格的 global p6 trace 增量对照：

| C→A | change / improvement |
|---|---:|
| E2 improvement | 73.367649% |
| Einf improvement | 75.223032% |
| power / amplitude / totals / fields E2 improvement | 74.118134% / 39.860389% / 43.520510% / 48.386592% |
| rows | +46.494465% |
| matrix NNZ | +108.641964% |
| factor NNZ | +111.098731% |
| simultaneous RSS | +37.074450% |

结论不是“trace 无效”，而是 **完整 global p6 trace 精度价值很高，但资源
成本过高**。A 的 simultaneous RSS `12,335.223 MiB`，且 rank-history
upper bound `12,300.105 MiB`，均稳定超过 11 GiB；它按 Gate 保存为
controlled resource negative，仅可作为 cycle-local fine solution。

C 的 simultaneous RSS `8,998.922 MiB`，rank-history upper bound
`8,963.277 MiB`，swap 为 0。它的 true residual 为
`2.082322e-12`，energy closure 为 `7.862599e-13`，所有 Floquet mismatch
为 0。

C 是现有工具可直接运行的最接近 interior mechanism 的候选，但不是严格的
“C1 interior-only”：它把 C1 的 p4 trace entities 提升到 p5，同时把
C1 的 4 个 p6 faces 降到 p5。该边界在 compact 中显式记录，没有把 proxy
冒充 exact mechanism。

## 8. 为什么在这里停止

- **精确 B（C1 trace-only）不可直接表达**：C1 使用 cell-driven variable
  trace；现有 selective-p6-face 路径要求 pure p5 trace base，源码明确规定
  两者互斥。
- **精确 C（C1 interior-only）不可直接表达**：当前 variable-p plan
  同时决定 cell interior 和 incident trace；C proxy 完成后 160 个
  interior 已全部 p6，而 p7 被本轮禁止。
- **D（C1 directional-z）不可直接表达**：当前 balanced-dyadic forest
  只有 isotropic split；Task35b structured-z 是不同 mesh identity。

继续任一项都需要新增独立 trace/interior map 或 anisotropic child
topology，已超出“优先零代码、不得大型框架”的约束。随机挑 selected faces
或再次使用已否定生成器的信息价值更低，因此没有为了填满时间盒而扫描。

## 9. Evidence

- compact authority：
  `benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/mechanism_isolation_sprint_v1.json`
- actual plans：
  `benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/mechanism_isolation_sprint_v1_plans/`
- ignored raw root：
  `benchmarks/artifacts/task035e/mechanism_isolation_sprint_f1ba5627/`

Compact 保存完整 59-goal A/C 行、旧 endpoint 的 top-10、Task35b partial
评价、C2 的 24-target 分类、全部 Gate、raw path 和 SHA-256。
