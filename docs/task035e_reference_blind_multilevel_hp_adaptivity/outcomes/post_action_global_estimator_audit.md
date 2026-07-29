# Task035e post-action global-estimator 离线审计

## 1. 范围、authority 与结论

本轮严格固定 numerical source：

```text
f1ba5627f163da54fa383b43be58fd38c0da7bc9
```

只读取既有 Path A cycle 0 current、full p-shadow、four-cell actual
candidate、single-cell actual candidate、full p-shadow primal/adjoint 与 raw
tensor/plan。没有运行新 PDE，没有执行 primal `KSPSolve`，没有读取 sealed
或 hidden reference，也没有启动 selected-h、Path B、cycle 1、saturation
或 Hybrid。

离线审计在 MPI8 下由既有 raw tensor cache 重装 full p-shadow operator，
只执行 MUMPS factor setup 和 59 个既有目标的 adjoint backsolve。该操作用于
计算 post-action residual-adjoint estimator，不产生新的 primal solution。

结论是 **没有候选显著降低 global remaining estimator**：

| 项目 | fixed-blind-tolerance aggregate norm | 相对 current | 判定 |
|---|---:|---:|---|
| cycle 0 current remaining DWR | 3,421.5539650198 | 1.000000 | baseline |
| cycle 0 current actual-to-full-shadow | 3,421.5539650008 | 1.000000 | endpoint closure |
| single-cell corrected remaining DWR | 3,426.4883968936 | 1.001442 | worsened |
| single-cell actual-to-full-shadow | 3,426.4883968919 | 1.001442 | endpoint closure |
| four-cell corrected remaining DWR | `not_evaluable` | `not_evaluable` | strict embedding failed |
| four-cell actual-to-full-shadow | 5,056.9308419007 | 1.477963 | endpoint distance only |

因此不能采用正信号分支所提议的
`cellwise = ranking only; post-action global estimator = accept/reject`
作为已经资格化的标准合同，也不得追认任何现有 candidate 成功。cycle 0
current 保留，下一研究方向进入 exact selected-action complement
Schur/low-rank repair。

## 2. Hash-bound 输入与 replay 资格

完整 39 项输入文件 catalog 的 SHA-256 为：

```text
b02c3062896c05cba554e0c71ce39b7d77b8970ba06ed0dc802f90614aabc9c7
```

离线 raw audit SHA-256 为：

```text
1754c8b6ce50723691d49b9ab41da236c2c7bd954226dae8f80baf55f5b744c4
```

提交的 compact payload SHA-256 为：

```text
a351113f49da48a4941d4894fe72511dcdd6184acbd10e952c2a92061f6ac94c
```

existing full p-shadow VTU 先重建到 DG-p6 carrier，再投回其真实 active
variable-p exact-sequence space。重建和 operator replay 的关键检查为：

| 检查 | 结果 |
|---|---:|
| DG-p6 roundtrip 最大绝对误差 | `1.182242e-13` |
| DG-p6 roundtrip 最大相对误差 | `7.367346e-14` |
| full-shadow active projection 相对误差 | `2.105280e-14` |
| full-shadow reduced-operator relative residual | `1.796961e-11` |
| replay 最大 adjoint true relative residual | `1.408845e-11` |
| replay current DWR 与原始 current DWR 最大绝对差 | `1.709743e-14` |
| replay current DWR 与 endpoint delta 最大绝对差 | `2.728706e-12` |
| operator rows / matrix NNZ / replay factor NNZ | `20,564 / 11,084,868 / 41,929,778` |
| primal backsolve | `not_run`（`0.0 s`） |

该 replay 不是 byte-identical reproduction：stored/replayed report SHA 不同，
`operator_identity_exact_match=false`，59 个 gradient partition 中 54 个
byte hash 相同，59 个 adjoint partition byte hash 均不同。现有 raw 不能证明
这些 byte 差异的唯一根因，因此本报告不把它改写为 exact hash pass。
与此同时，逐目标 signed DWR 数值在 `1.71e-14` 内重现，且本轮结论是保守的
negative，不依赖把 byte identity 冒充通过。未来 repair 的正式资格化仍须把
operator、gradient 与 adjoint identity 分层记录，不能只用数值接近代替身份
Gate。

## 3. Single-cell post-action audit

动作仍严格是：

```text
cell:r42:l1:i1:j0:k0 : p4 -> p5
```

该 candidate 与 full p-shadow 使用同一个 160-leaf forest，且每个 cell 的
candidate degree 都不高于 full p-shadow degree，所以存在严格 nested
embedding。candidate 的 DG-p6 roundtrip 最大相对误差为
`7.449072e-14`，active-space roundtrip 相对误差为 `2.098434e-14`，
independent-trace roundtrip 相对误差为 `2.788550e-14`。

把 candidate 严格嵌入 full p-shadow active space 后，
`||A_shadow x_candidate-b_shadow||/||b_shadow|| =
0.3448853171`。这是 candidate 相对 enriched operator 的预期非零 residual，
不是 candidate 自己的 solver residual Gate。

59 个既有 full p-shadow adjoint 给出的结果为：

- corrected remaining aggregate：`3426.4883968936`；
- linear-only aggregate：`3429.0659945292`；
- actual candidate-to-full-shadow aggregate：`3426.4883968919`；
- 相对 current remaining aggregate：`1.0014421611`，即恶化
  `0.144216%`；
- `24/59` 目标改善，`35/59` 目标恶化；
- 23 个 power/L2 quadratic 目标均加入 action-consistent secant/quadratic
  remainder；
- 最大绝对 nonlinear remainder 为 `1.720603e-03`；
- corrected estimate 与 actual endpoint distance 的逐目标最大绝对差为
  `4.835021e-14`。

因此 single-cell candidate 明确没有达到“aggregate 至少下降 10%”的
significant-reduction 条件，且不得被追认为 formal pass。

## 4. Four-cell structural controlled stop

four-cell candidate 与 full p-shadow 虽然共享同一个 160-leaf forest，但有
两个 cell 在 candidate 中为 p6、在 full p-shadow 中仅为 p5：

```text
[16.5, 0.0, 20.0, 33.5, 12.5, 40.0]
[16.5, 0.0, 100.0, 33.5, 12.5, 120.0]
```

因此该 candidate **不是**现有 full p-shadow active space 的子空间，无法满足
“严格嵌入后在 full p-shadow operator 上取 residual”的前提。诊断性的
coefficient-L2 nonmatching projection 得到：

- p6 roundtrip relative error：`6.332561e-03`；
- shared-active prediction maximum relative error：`3.757479e-02`。

该 nonmatching projection 没有获得 exact-transfer credit，也没有被代替成
formal residual。four-cell 的 full-shadow residual、59-goal remaining DWR
和 reduction ratio 均保持 `not_evaluable_strict_embedding_failed`。

既有 endpoint values 可以独立给出
`actual candidate-to-full-shadow aggregate = 5056.9308419007`，比 current
endpoint distance 大 `47.7963%`；它只是一项 endpoint distance，不得写成
post-action DWR estimator。

## 5. Exact selected-action repair

负结果触发的是 action-consistent algebra repair，而不是继续扫描其他 cell。
repair 必须建立能同时容纳 full p-shadow 与 selected action 的最小 union
space，并保留 current space 的 exact-sequence identity。

### 5.1 新 interior modes 对旧 trace 块的更新

设旧 trace 为 `t`、旧 cell interior 为 `i`、action 新增 interior 为 `q`。
不能只追加 `Aqq/Aqt/Atq` 而假设旧 condensed trace block `A00` 不变。应形成：

```text
        [ Att  Ati  Atq ]
Aact = [ Ait  Aii  Aiq ]
        [ Aqt  Aqi  Aqq ]
```

并计算：

```text
Sact = Att
       - [Ati Atq] [ Aii Aiq ]^-1 [Ait]
                   [ Aqi Aqq ]    [Aqt]

Delta A00 = Sact - (Att - Ati Aii^-1 Ait)
```

`Delta A00` 必须显式进入 old-trace block。只有在审计证明交叉块严格为零时，
才允许退化为更简单的 low-rank update。

### 5.2 完整 entity/mode orbit 与 closure

action complement 不能只含 cell-interior modes。所有新增 edge/face mode
必须按完整 physical entity orbit 加入，并在建立 Schur block前完成：

- edge/face orientation 与 covariant Piola；
- periodic/Floquet orbit；
- hanging-trace 与 2:1 closure；
- material-interface incident-cell minimum degree；
- MPI owner/ghost 唯一性。

inactive mode 不得进入矩阵，partial face/edge orbit 不得获得数值 credit。

### 5.3 Union-space residual、adjoint与目标余项

对 single-cell 可在现有 full p-shadow space 中复用 factor；对 four-cell
必须形成：

```text
V_union = V_full-p-shadow + V_selected-action-only
```

然后把 current、candidate 与 full p-shadow 都无损嵌入 `V_union`。在同一个
union operator 上计算 candidate residual、59 个 adjoint及 remaining signed
DWR。power 和 L2 目标必须使用 candidate-to-shadow action-consistent secant
或 exact quadratic remainder；复振幅线性目标仍须保持同一 phase、port 与
orbit identity。

repair 的离线 qualification 继续使用既有 single/four-cell raw actual
candidate，只在最终 checker 中比较 actual endpoint，不允许 actual
candidate 反向进入 predictor。两条历史 action 都通过前，不重新开放其他
selected-p 或 selected-h。

## 6. 冻结状态

```text
Path A cycle 0 current = retained
single-cell formal candidate = rejected
four-cell formal candidate = rejected
cellwise-p attribution = ranking only
post-action global estimator standard contract = not_qualified
next lane = exact selected-action complement Schur/low-rank repair
selected-h = not_run
Path B new run = not_run
cycle 1 = not_run
p7 / level-3 saturation = not_run
hidden audit = not_run
Hybrid = not_run
```

完整 59-goal current/candidate remaining estimate、actual distance、fixed blind
tolerance、reduction ratio、improved/worsened 分类、nonlinear remainder、
input file path/size/SHA 和 decision 位于
[`path_a_cycle0_post_action_global_estimator_audit_v1.json`](../../../benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_post_action_global_estimator_audit_v1.json)。
