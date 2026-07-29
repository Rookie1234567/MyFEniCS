# Task035e cellwise-p estimator repair 设计

## 1. 已证实的问题边界

当前 global 59-goal p-shadow DWR 仍然有效；失效的是把该 global enriched
problem 的 cellwise residual-adjoint attribution 直接解释成某个实际
selected p-action 的 endpoint delta。

现有两个 actual controlled negatives 给出了互补证据：

1. four-cell grouped action：`19/59` factor-two，`25/59` opposite-sign；
2. single-cell `r42...k0` action：`0/59` factor-two，`30/59`
   opposite-sign。

第二条消除了“只是四个 cell 相加产生交互误差”的解释。当前 cellwise row
包含 full p-shadow 上的全局 adjoint/residual attribution，但实际 action 只激活
132 个 cell-interior modes 和一个 16-mode face orbit。两者的 trial space、
trace closure、Schur coupling 和目标线性化都不同，所以 cellwise row 不能作为
该 action 的定量 Fréchet prediction。

该结论只关闭 `cellwise-p quantitative predictor`。cellwise partition 仍可作为
无 accuracy credit 的排序信号；global p-shadow 的 59-goal DWR authority 不受
影响。

## 2. Repair A：entity/mode-orbit DWR

目标是把一个 p-up action 定义为实际新增的 exact-sequence mode 集合，而不是
一个几何 cell 标签。

对每个候选 action 必须先生成以下 immutable inventory：

- 新增 cell-interior modes；
- 新增 edge orbit 与 face orbit；
- periodic、hanging、material 与 incident-cell minimum closure；
- 从 active variable-p rows 到 p6 local tensor container 的 expansion；
- static-condensation 后的 complement Schur block；
- action 与当前 active trace、DtN auxiliary rows 的 coupling。

令当前系统为 `A00 x0 = b0`，action 新增 mode-orbit 为 `q`。在同一
exact-sequence basis 下形成：

```text
[ A00  A0q ] [dx] = [r0]
[ Aq0  Aqq ] [dq]   [rq]
```

不装配完整 candidate matrix，只形成 action-local `Aqq`、`Aq0` 与必要的
current-factor solves。对每个正式目标使用相同 orbit 上的 adjoint complement，
计算带符号的 mode-orbit contribution。cell-interior modes 必须在局部 Schur 中
消元；face/edge modes 必须按完整 periodic/hanging orbit 作为一个不可拆 action。

这个 estimator 的必要审计字段为：

- action basis SHA 与 transition plan SHA；
- active/complement mode IDs 与 entity-orbit SHA；
- exact-sequence/Piola/orientation/Floquet identity；
- complement residual、adjoint residual和Schur solve residual；
- 59-goal signed prediction；
- predicted rows、matrix NNZ、factor proxy 与 memory proxy；
- inactive modes 未进入全局矩阵的证明。

## 3. Repair B：exact selected-action DWR

如果 mode-orbit 一阶近似仍不足，则直接针对已经冻结的 transition 构造 exact
selected-action enriched operator：

1. 从 current plan 与 transition action 生成 `A1` 的真实 active basis；
2. 把 current primal/adjoint 无损嵌入 `A1`；
3. 在 `A1` 上重算 enriched residual，而不是复用 full p-shadow cell row；
4. 对 59 个目标使用 multi-RHS adjoint，目标导数在 current 与 predicted
   endpoint 上保持一致；
5. 通过 complement Schur / low-rank update 求 action correction，不运行新的
   full PDE；
6. 输出 `predicted J(x1)-J(x0)`，并把 global endpoint closure 与 modewise
   attribution分开。

Maxwell operator 是线性的，但 power、L2 norm 与复振幅分量的目标映射并不都
是线性标量。exact selected-action DWR 必须显式包含这些目标的 action-consistent
线性化或二次余项，不能只用场方程线性这一事实忽略 goal remainder。

## 4. 离线资格化顺序

不得通过新的 PDE 调试 estimator。先使用已经存在的两条 raw actual candidate：

1. replay single-cell action；
2. replay four-cell grouped action；
3. 对每条 action 分别要求至少 `54/59` factor-two-or-neutral；
4. 正式逐衍射级与总量不得出现系统性 opposite-sign；
5. prediction 必须只读取 current、transition、current factor/tensor cache 与
   blind DWR inputs，不得读取 hidden reference；
6. actual candidate 只在最终 checker 中作为 qualification label，不得反向进入
   predictor。

只有两条历史 action 都通过，才能重新开放一个新的 selected-p actual
diagnostic。若 Repair A 失败，转 Repair B；不得通过扫描其他 cell 调参。

## 5. 当前不实施的内容

本轮只冻结设计，不修改数值源码，也不新增 schema、receipt、watchdog 或
checker。以下全部保持 `not_run`：

- 其他 selected-p cell；
- selected-h；
- cycle 1；
- Path B；
- p7/level-3 saturation；
- hidden audit；
- Hybrid。
