# Task004 Response V7：Required M4H 训练内选择性代理闭合

## 1. 执行边界与不可变身份

本轮先完成 `git pull --ff-only`，并以 Review V6 为唯一审阅依据。只使用
不可变的 train112 package、冻结五折、已有 M4G OOF 和 response-blind 的
4096 candidate / 24 blind angle designs。没有运行任何新 training FEM、第二轮
主动学习或 blind FEM，没有打开 Task003 frozen validation，也没有执行 Fisher、
geometry sensitivity 或 inversion。

| identity | value |
|---|---|
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| training rows | 112 |
| tuple hash | `00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68` |
| M4H clean implementation SHA | `9325d90479a7d0c9448ca302ee4b438632950d2d` |
| validation response accessed | `false` |
| new FEM / blind FEM | `0 / 0` |

## 2. 选择器合同

点预测器严格限制为：

```text
P1 = local RBF k24
P2 = local Matérn k24
P3 = existing E1 latent median
```

风险规则严格限制为：

```text
S1 = 0.35*Matérn std
   + 0.25*Matérn(k24,k32) disagreement
   + 0.20*RBF/Matérn disagreement
   + 0.10*nearest-training distance
   + 0.10*cutoff/topology risk

S2 = max(max-target Matérn std,
         max-target(RBF/Matérn disagreement, Matérn(k24,k32) disagreement))
```

S1 权重、允许的输入信号、q05/q95 归一化和 response-blind screening 规则见
`SELECTIVE_RISK_SIGNAL_CONTRACT.json`。每个 outer-test fold 的归一化和阈值
只由另外四个 outer folds 的 OOF risk/error 拟合；held-out row 的 truth 不
参与本行接受/拒绝。`SELECTIVE_OOF.json` 保存 672 条 predictor/rule/row
记录、source-fold hash、threshold、risk components、accepted/rejected 和
原因。没有训练黑箱 error classifier。

## 3. 训练内 Gate

| pair | accepted OOF | pool accepted | blind-design accepted | Gate 结果 |
|---|---:|---:|---:|---|
| P1 / S1 | 81/112 (0.7232) | 3937/4096 | 22/24 | fail：accepted accuracy、coverage |
| P2 / S1 | 81/112 (0.7232) | 3937/4096 | 22/24 | fail：coverage |
| P3 / S1 | 81/112 (0.7232) | 3937/4096 | 22/24 | fail：coverage |
| P1 / S2 | 112/112 | 4096/4096 | 24/24 | fail：accuracy、supported-window |
| P2 / S2 | 112/112 | 4096/4096 | 24/24 | fail：accuracy、supported-window、coverage |
| P3 / S2 | 112/112 | 4096/4096 | 24/24 | fail：accuracy、supported-window、coverage |

S1 的 P2/P3 accepted-set R/T/A 精度分别通过，但三者 cross-fitted 95%
coverage 都是 `1.0`，超过冻结上限 `0.99`；不能通过放宽区间把过度保守的
区间包装成通过。P1/S1 的 `A_balance` NRMSE=`0.01481109`、p95=`0.01395993`
也超过 Gate。S2 接受全部 OOF 点，保留了完整域的高方位角/cutoff 尾部误差，
因此不构成 selective surrogate。

## 4. 两个独立 domain

`ANGLE_AGGREGATE_STRUCTURAL_SUPPORT_DOMAIN.json` 只使用 response-blind 的
实际训练角度支撑、解析 mask topology 和 train112 leave-one-out 距离阈值：
candidate pool 为 `4074/4096`，blind design 为 `24/24`。这是结构支撑事实，
不是预测安全域。

`ANGLE_AGGREGATE_SELECTIVE_ACCEPTANCE_DOMAIN.json` 单独保存六个风险接受集、
rejected 集以及 index/angle tuple hashes；它不把 structural support 布尔值
冒充预测资格，也没有读取 blind response。高方位角、低掠射、cutoff、边界、
old96/new16 均在 `selective_region_report.md` 中分别报告。

## 5. 独立复核与停止

Case129 checker 不导入 M4H fitter，而是独立重算 train112 文件 hash、五折
覆盖、source-fold 排除、S1/S2 risk arithmetic、accepted-set metrics、
composition、candidate/blind acceptance hashes、结构域分离以及 no-lock/no-blind
约束，结果为 `status=pass`。该 checker pass 表示证据合同完整，不代表模型
资格通过；qualification status 明确为 `controlled_negative`。

没有任何 predictor/rule pair 同时通过 accepted accuracy、最低接受率、
supported-window 和 coverage Gates。因此：

```text
ANGLE_AGGREGATE_SELECTIVE_QUALIFICATION = controlled_negative
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK = not created
blind-validation FEM = not run
Order Level B = not qualified
```

被拒绝角度必须返回 `requires_fem`，不得静默输出未经资格化的代理值。本轮
到此停止，等待 ChatGPT Review V7；不调整阈值、不恢复 FEM campaign、不进入
Task003 或反演路线。

