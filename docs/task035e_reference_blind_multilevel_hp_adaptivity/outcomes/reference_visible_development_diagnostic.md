# Task035e reference-visible development diagnostic

## 结论

本批次只打开既有 sealed reference package，离线比较 Path A cycle 0 的
`current`、完整 `p-shadow`、完整 `h-shadow`、single-cell candidate 和
four-cell candidate。分类严格为：

```text
REFERENCE_VISIBLE_DEVELOPMENT_DIAGNOSTIC
```

它不获得 reference-blind credit、formal candidate credit 或 final hidden-audit
credit，也没有修改 blind controller、controller input、cycle state、ordinary
default 或历史 controlled negative。

按固定 reference tolerance 归一化后，既有 full p-shadow 相对 cycle 0 current
的 59-goal L2 true error 降低 `27.120392%`。四个正式分类均未出现本文所定义的
系统性恶化：

- 16 个 N=8 power：L2 降低 `27.121411%`，`10` improved / `6` worsened；
- 16 个 grouped complex amplitudes：L2 降低 `14.927729%`，
  `8` improved / `8` worsened；
- 5 个 totals：L2 降低 `28.077422%`，`5` improved / `0` worsened；
- 6 个 field goals：L2 降低 `3.372554%`，`5` improved / `1` worsened。

因此本批次只提出：

```text
propose existing full p-shadow as development cycle 1 current
reuse existing artifact; do not solve again
proposal only; controller state unchanged
```

这不是收敛声明。full p-shadow 仍只有 `1/59` 位于 reference tolerance 内，
`0/59` 位于 reference uncertainty 内；现有 cycle 0 current 继续保持正式状态，
直到后续审阅明确授权 development-only promotion。

## 身份与边界

| 项目 | 值 |
|---|---|
| adaptive numerical source | `f1ba5627f163da54fa383b43be58fd38c0da7bc9` |
| reference certification source | `03ddc8319fa9ee9da6a9ee948b539a067e9c3dd0` |
| sealed package SHA-256 | `69b620849c89a984d5c2e940695b19eea751374708fe540d704f43b1311672d7` |
| compact payload SHA-256 | `3501b68220962cf8e0f1f30da3e86da96fbb08454a0aeb867e33a9e5142a368d` |
| compact file SHA-256 | `e4cb1a249cc456104512a327aceb35918e25ebfe1a2c6db9fe7dca97c7a4cc40` |
| fixed inventory | 59 goals = 16 power + 32 amplitude components + 5 totals + 6 fields |
| fixed order set | top/bottom，`m=0,-1,...,-7`，`n=0` |
| new PDE / primal / adjoint | `not_run` |
| cycle promotion | `not_performed` |

本次没有运行新 current、p-shadow、h-shadow、其他 selected cell、selected-h、
Path B、exact selected-action Schur、p7/level-3 或 Hybrid。sealed package
由独立 development evaluator 打开，blind controller 未导入它，也未收到任何
reference path、hash、数值或派生标签。

## 输入绑定

| 输入 | bytes | SHA-256 |
|---|---:|---|
| `records/task035e_sealed_reference_manifest_v1.json` | 7,186 | `54f5191ec689dba3b5afe28cf4497661dce607462de12d79abbfad838984ec37` |
| ignored sealed reference package | 47,421,013 | `69b620849c89a984d5c2e940695b19eea751374708fe540d704f43b1311672d7` |
| `records/path_a_cycle0_v28_59goal_dwr_compact_v1.json` | 65,317 | `56336031990e9c30aed3fb0a8107db8ffd9aaf9e32b88c6ccdb144fb349442b9` |
| `records/path_a_cycle0_single_cell_p_actual_checkpoint_v1.json` | 46,312 | `3276c9a4804030017da8e638f203292ea47d2a884a35b54cd264043c87986d50` |
| `records/path_a_cycle0_selected_p_actual_checkpoint_v1.json` | 53,588 | `5b04b200eec7b9d02ceb92f8626c8cbb651eb79b8b571675037da324324c5643` |

evaluator 在使用任何数值前重算了上述文件 SHA、四个 compact 的 canonical
payload SHA、sealed package size/SHA、`qualified` 状态、N=8 inventory、
三层 h inventory 和五组 59-goal identity。

## Reference center、uncertainty 与归一化

16 个 power、16 个 complex amplitude 和 5 个 totals 的 center/uncertainty
直接来自 qualified convergence rows。每个 complex amplitude 在 compact 中
拆成 real/imag 两个正式目标，但二者共享 parent complex magnitude 定义的
tolerance。

六个 aggregate field goals 不把 h5 endpoint 冒充 reference center：

- interface/volume L2 center 由 3,200/7,200 个 qualified E-field sample
  convergence centers 取 Euclidean norm；
- complex mean center 由同一批 qualified centers 取算术均值；
- L2 uncertainty 使用
  `sqrt(sum(per-sample uncertainty^2))` 的 Euclidean-norm Lipschitz 上界；
- complex mean uncertainty 使用
  `sum(per-sample uncertainty)/N` 的 triangle-inequality 上界。

field component 的归一化只属于本 development diagnostic，不能替代最终
hidden auditor 的完整 interface/volume field-vector relative-L2 Gate。

每个目标的 reference center、reference uncertainty、candidate value、
signed/absolute/normalized error、within-uncertainty 和 within-tolerance
均保存在
[59-goal compact](reference_visible_development_diagnostic_v1.json)。

## 五组结果

`I/W/U` 表示相对 current 的 improved / worsened / unchanged 数；current
自身以 baseline 计数。`within u` 与 `within tol` 分别表示落入 reference
uncertainty 和 reference tolerance 的目标数。

| candidate | absolute L2 | normalized L2 | normalized Linf | I/W/U | within u | within tol | normalized L2 reduction vs current |
|---|---:|---:|---:|---:|---:|---:|---:|
| cycle0 current | 13.4185108 | 9,069,896.59 | 7,935,707.32 | baseline | 0 | 0 | baseline |
| full p-shadow | 12.8843498 | 6,610,105.05 | 5,764,876.17 | 38/21/0 | 0 | 1 | **27.120392%** |
| full h-shadow | 13.4185734 | 9,069,620.30 | 7,935,566.36 | 23/36/0 | 0 | 0 | 0.003046% |
| single-cell candidate | 13.4219890 | 9,114,335.27 | 7,982,589.57 | 25/34/0 | 0 | 0 | -0.489958% |
| four-cell candidate | 13.7171963 | 11,521,664.81 | 11,109,191.00 | 32/27/0 | 0 | 0 | -27.031931% |

未加权 absolute L2 仅作为补充诊断，因为严格弱通道会被它掩盖；full p-shadow
的未加权 absolute L2 降低 `3.980777%`，而正式 per-goal tolerance
归一化 L2 降低 `27.120392%`。后者用于本文的 development decision。

## 分类统计

下面的 amplitude 行是 59-goal inventory 中的 32 个 real/imag components。
物理上 grouped 的 16 个 complex amplitudes 另列在下一节。

| candidate | category (count) | absolute L2 | normalized L2 | normalized Linf | I/W/U | within u / tol | reduction vs current |
|---|---|---:|---:|---:|---:|---:|---:|
| current | power (16) | 0.249984550 | 9,069,226.74 | 7,935,707.32 | baseline | 0/0 | baseline |
| current | amplitude components (32) | 1.37576800 | 82,035.9634 | 53,351.5677 | baseline | 0/0 | baseline |
| current | totals (5) | 0.318371454 | 73,624.2107 | 54,373.0017 | baseline | 0/0 | baseline |
| current | fields (6) | 13.3416581 | 210.876709 | 172.602252 | baseline | 0/0 | baseline |
| full p-shadow | power (16) | 0.210931969 | 6,609,524.50 | 5,764,876.17 | 10/6/0 | 0/1 | **27.121411%** |
| full p-shadow | amplitude components (32) | 1.42078342 | 69,789.8568 | 47,706.9266 | 18/14/0 | 0/0 | **14.927729%** |
| full p-shadow | totals (5) | 0.279925944 | 52,952.4301 | 39,109.1094 | 5/0/0 | 0/0 | **28.077422%** |
| full p-shadow | fields (6) | 12.8009763 | 203.764779 | 171.717269 | 5/1/0 | 0/0 | **3.372554%** |
| full h-shadow | power (16) | 0.249985203 | 9,068,950.44 | 7,935,566.36 | 4/12/0 | 0/0 | 0.003046% |
| full h-shadow | amplitude components (32) | 1.37577565 | 82,034.1435 | 53,348.2639 | 16/16/0 | 0/0 | 0.002218% |
| full h-shadow | totals (5) | 0.318372822 | 73,624.7685 | 54,373.3715 | 0/5/0 | 0/0 | -0.000758% |
| full h-shadow | fields (6) | 13.3417203 | 210.874231 | 172.601681 | 3/3/0 | 0/0 | 0.001175% |
| single-cell | power (16) | 0.249904523 | 9,113,668.18 | 7,982,589.57 | 8/8/0 | 0/0 | -0.490025% |
| single-cell | amplitude components (32) | 1.37587152 | 82,182.1020 | 53,412.9203 | 13/19/0 | 0/0 | -0.178140% |
| single-cell | totals (5) | 0.318310358 | 73,524.8130 | 54,314.7640 | 3/2/0 | 0/0 | 0.135007% |
| single-cell | fields (6) | 13.3451487 | 210.853696 | 172.619388 | 1/5/0 | 0/0 | 0.010913% |
| four-cell | power (16) | 0.178290657 | 11,521,347.75 | 11,109,191.00 | 10/6/0 | 0/0 | -27.037818% |
| four-cell | amplitude components (32) | 1.44319349 | 83,536.1680 | 59,810.1609 | 15/17/0 | 0/0 | -1.828716% |
| four-cell | totals (5) | 0.266841101 | 18,102.7283 | 15,512.0149 | 3/2/0 | 0/0 | 75.411990% |
| four-cell | fields (6) | 13.6372899 | 190.522371 | 164.290268 | 4/2/0 | 0/0 | 9.652246% |

four-cell 的未加权 power L2 虽降低，但正式 normalized power L2 恶化
`27.037818%`。原因是它改善部分大功率级的同时显著恶化了具有严格绝对
tolerance 的弱级次；这正说明不能用总功率或未加权范数替代固定 N=8 Gate。

## Grouped complex-amplitude 统计

| candidate | complex channels | absolute L2 | normalized L2 | normalized Linf | I/W/U | within u / tol | reduction vs current |
|---|---:|---:|---:|---:|---:|---:|---:|
| current | 16 | 1.37576800 | 82,035.9634 | 56,504.8979 | baseline | 0/0 | baseline |
| full p-shadow | 16 | 1.42078342 | 69,789.8568 | 48,036.5305 | 8/8/0 | 0/0 | **14.927729%** |
| full h-shadow | 16 | 1.37577565 | 82,034.1435 | 56,504.3639 | 5/11/0 | 0/0 | 0.002218% |
| single-cell | 16 | 1.37587152 | 82,182.1020 | 56,672.5563 | 5/11/0 | 0/0 | -0.178140% |
| four-cell | 16 | 1.44319349 | 83,536.1680 | 66,933.9105 | 8/8/0 | 0/0 | -1.828716% |

full p-shadow 的 grouped amplitude absolute L2 增加，但正式
per-channel normalized L2 降低，且 improved/worsened 为 `8/8`。本文把
“无系统性恶化”严格定义为：power、grouped complex amplitude、totals 和
fields 各自的 normalized L2 均不增加，且每组 worsened 数不超过 improved
数；它不等于“每一个目标都改善”。

## 冻结状态与下一步

```text
cycle0_current_retained = true
candidate_promoted = false
cycle_advanced = false
single_cell_controlled_negative_retained = true
four_cell_controlled_negative_retained = true
exact_selected_action_repair_deferred = true
```

本结果支持审阅者下一轮考虑把**已有** full p-shadow 作为
development cycle 1 current，且无需重新求解；但本提交没有实施该状态转换，
也不得把 reference-visible 选择反向写入 blind controller 或追认为
reference-blind adaptive success。
