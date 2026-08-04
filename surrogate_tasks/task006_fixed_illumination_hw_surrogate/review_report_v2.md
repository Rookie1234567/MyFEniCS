# Task006 Review Report V2：M2R 验收、blind 前向残差受控停止与两点重资格化

## 1. 审阅结论

本轮正式批准并保留：

```text
Task006 M2R S0/S1 authority correction                 = approved
S0 predicted R/T as the sole S1 side-total authority   = approved
actual selected/other/ledger OOF evidence              = approved
frozen geometry-grouped folds                          = approved
Case139 deterministic replay                           = pass
pre-blind TASK006_MODEL_SELECTION_LOCK                 = valid and immutable
blind campaign design / 36 point identities            = approved
34 blind measured-pass records                         = approved and retain
original 2 failed records                              = preserve unchanged
no post-blind model tuning                             = approved
```

本轮**不接受**把当前结果解释成：

```text
Task006 surrogate failed blind validation
```

也不接受把它作为最终 `controlled_negative` 关闭。准确状态应为：

```text
training qualification          = passed and locked
blind forward campaign          = incomplete
blind records expected          = 36
blind records measured_pass     = 34
blind records failed gate       = 2
complete blind geometries       = 11 / 12
full blind qualification        = not run
surrogate blind pass/fail       = not yet determined
review classification           = controlled_stop_blind_forward_incomplete
```

历史文件 `TASK006_BLIND_FAILURE_REPORT.json` 不得删除或改写；其中的
`controlled_negative` 保留为当轮执行状态。但在科学审阅层面，停止原因是同一
blind geometry 的两条 Full3D 前向记录未通过严格 residual Gate，而不是代理预测
误差超标。

本报告授权一个严格受限的 M3R：先完成无 FEM 的失败遥测与重试合同冻结，然后
最多重算这两个失败 tuple，各进行两次 fresh-process 重复。不得重算其余 34 条
blind 记录，不得改变模型锁、训练数据、候选模型、阈值、噪声合同或反演程序。

---

## 2. M2R 可以正式验收

Review V1 要求 S1 不得独立预测另一套 side total。最新 M2R 已改为：

\[
P_{\mathrm{selected}}^R=\widehat R_{S0} f_R,
\qquad
P_{\mathrm{other}}^R=\widehat R_{S0}(1-f_R),
\]

\[
P_{\mathrm{selected}}^T=\widehat T_{S0} f_T,
\qquad
P_{\mathrm{other}}^T=\widehat T_{S0}(1-f_T).
\]

因此公开预测只有一套 R/T authority，并且逐条保存：

```text
S0 side total
selected power
other power
selected + other
ledger residual
selected / other nonnegative flags
selected <= side-total flag
```

Case139 已在不可变 train37 上重建 folds、transform、OOF prediction hash、
composition、ledger、metrics 和 synthetic recovery。M2R 不需要返工，也不需要
重跑 79 个 training FEM。

---

## 3. 当前 blind 停止的准确原因

36 条 blind forward 均已按锁定顺序启动一次。结果：

```text
attempted        = 36 / 36
measured_pass    = 34
failed_gate      = 2
```

两个失败记录均来自：

```text
geometry = (h,w) = (117.5 nm, 17.25 nm)
```

分别为：

| key | illumination | 唯一失败 Gate |
|---|---|---|
| `117.5,17.25/A07` | grazing 2 deg, azimuth 90 deg | `true_residual_le_1e-9=false` |
| `117.5,17.25/A09` | grazing 4 deg, azimuth 60 deg | `true_residual_le_1e-9=false` |

两条记录都已经：

```text
completed direct solve                  = true
energy closure <= 1e-7                 = true
fixed order schema                     = true
runtime topology                       = true
n != 0 leakage                         = true
raw reflection / transmission ledger   = true
compact output identity                = true
```

因此目前没有证据表明：

```text
材料、网格或几何无解
传播 topology 错误
能量不守恒
order 后处理错误
MUMPS 工作区不足
代理模型预测失败
```

真正需要回答的是：这两个 true residual 是略微超过 `1e-9` 的可重复数值边界问题，
还是该 frozen forward identity 在此几何的稳定性缺口。

当前 tracked 报告只保存了布尔 Gate 和 formal hashes，没有保存可供远程审阅的实际
true-residual 数值、分子/分母、RHS norm、KSP reason 与 MUMPS 细项。不得猜测它们
距离 `1e-9` 有多远；M3R 必须先补齐这项遥测。

---

## 4. 部分 blind 结果只能作为积极的 advisory evidence

需要更正“正式盲评分根本没有开始”这一过强表述。Case141 在模型锁不变的条件下，
已经读取 34 条成功响应，并对 successful rows 与 11 个三照明完整几何计算了部分
诊断；只是没有执行 36/36、12/12 的最终 qualification。

现有部分证据非常积极：

```text
successful-row minimum 95% coverage   = 1.0
p95 interval half-width / N1 sigma    = 0.40786
composition max residual              = 1.11e-16
predicted selected/other nonnegative  = true
selected <= S0 side total             = true
predicted ledger max residual         = 0
```

11 个完整 blind geometries 的 synthetic recovery 为：

```text
p95 |height error| = 0.0009265 nm
p95 |width error|  = 0.0001696 nm
max |height error| = 0.0009881 nm
max |width error|  = 0.0001713 nm
rejected           = 0
```

这些数值远低于冻结恢复 Gate，但只能标记为：

```text
partial_advisory_evidence
```

因为 `(117.5,17.25)` 缺少 A07/A09，完整 blind geometry count 仍是 11/12。
不能用 11/12 代替 12/12，也不能据此提前发布代理资格。

---

## 5. 模型锁现在必须永久保持不变

M2R 的 candidate scores 中存在精确并列：

```text
legendre_3                           = 1.0
matern52_ard_exact_gp                = 1.0
degree2_trend_plus_matern52_residual = 1.0
```

当前代码在固定 candidate 顺序中使用 `min(..., key=selection_score)`，所以并列时
确定性地选择最先出现的 `legendre_3`。该 tie-break 在 blind 前完成，因而不是
blind leakage；但它没有被科学合同显式说明。

由于 34 条 blind response 已被读取并形成部分诊断，现在绝对禁止：

```text
换成 GP 或 trend+GP
重新定义 selection score
增加 tie-break 指标
改变不确定度校准
改变 S0/S1 target
改变恢复权重或优化器合同
```

M3R 只需新增：

```text
MODEL_SELECTION_TIE_AUDIT.json
MODEL_SELECTION_TIE_AUDIT.md
```

记录并列、candidate 固定顺序和历史选择语义；不得改写
`TASK006_MODEL_SELECTION_LOCK.json`。

---

## 6. Required M3R0：无 FEM 的失败遥测和重试计划

在运行任何重试前，必须建立：

```text
outcomes/BLIND_FORWARD_FAILURE_TELEMETRY.json
outcomes/BLIND_FORWARD_FAILURE_TELEMETRY.md
outcomes/BLIND_RETRY_PLAN.json
outcomes/MODEL_SELECTION_TIE_AUDIT.json
outcomes/MODEL_SELECTION_TIE_AUDIT.md
benchmarks/cases/143_task006_blind_retry_preflight/
```

### 6.1 失败遥测

从原始失败目录只读提取并 hash-bound：

```text
actual true residual
residual numerator and denominator, if available
absolute residual and normalized residual semantics
RHS / solution norms used by the check
KSP converged reason and iteration count
factor solver identity
MUMPS INFO / INFOG / RINFOG fields available in execution evidence
matrix rows / nnz
ordering / pivot / refinement settings
requested and actual ICNTL values
peak RSS / PSS / USS / swap
PETSC_OPTIONS and thread environment
formal / execution hashes
```

若原始文件没有某项，应明确写 `not_recorded`，不得制造数值。

### 6.2 原失败证据不可覆盖

原 Case141 campaign、failure report、formal records 和 run directories 必须保持
原 hash。重试必须进入新的 attempt-specific 目录，例如：

```text
.../blind_retry/117.5_17.25/A07/attempt_2/
.../blind_retry/117.5_17.25/A07/attempt_3/
.../blind_retry/117.5_17.25/A09/attempt_2/
.../blind_retry/117.5_17.25/A09/attempt_3/
```

不得在原失败目录上原地覆盖。

### 6.3 冻结唯一允许的 tuple

`BLIND_RETRY_PLAN.json` 必须只包含：

```text
117.5,17.25/A07
117.5,17.25/A09
```

并绑定：

```text
unchanged TASK006_MODEL_SELECTION_LOCK hash
unchanged blind design hash
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
Full3D p5/h10/Ny4
mesh = (6,4,14)
MUMPS ICNTL(14)=40
MPI2 / thread1
same observable/config/tolerance
true residual Gate = 1e-9, unchanged
```

Case143 checker 通过前不得运行重试。

---

## 7. Conditional M3R1：最多四个相同身份重试 FEM

Case143 通过后，批准：

```text
2 failed tuples x 2 independent fresh-process repeats = at most 4 FEM
```

每个 tuple 的两个 fresh repeats 必须都：

```text
status = measured_pass
true residual <= 1e-9
all original Task006 numerical/resource Gates pass
zero unexplained swap
cleanup complete
source/config/observable identity exact
```

不允许：

```text
放宽 residual Gate
改变 MUMPS / PETSc 参数
启用新的 iterative refinement
更换 ordering、pivot 或 OOC/BLR
改变 mesh / p / MPI / thread
只保留成功重试并删除失败重试
```

### 7.1 重复一致性

对于同一 tuple 的两个通过 repeats，至少比较：

```text
R/T/A
fixed order powers
fixed order complex amplitudes
power-carrying mask
```

它们必须在预先冻结的直接求解重复容差内一致。建议沿用 Task004/005 anchor 的
`1e-10` 级绝对比较；如现有正式 anchor 合同规定更严格值，以既有值为准。

两个 repeats 都通过后，按照预先冻结规则选择第一个通过的 repeat 作为 canonical
blind record；第二个只作为 reproducibility evidence。

若任一 tuple 无法 2/2 重复通过，则停止：

```text
status = blind_forward_route_not_reproducibly_qualified
```

不得运行完整 blind score，也不得将 34 条成功记录与新的 solver profile 混合。

---

## 8. Conditional M3R2：组装 36 条并进行唯一一次完整资格评分

只有两个 tuple 都完成 2/2 通过后，建立一个新的派生 blind package：

```text
34 original measured-pass records
+ 2 canonical retry records
= 36 complete records
```

不得修改原 `BLIND12_CAMPAIGN.json`；应新增：

```text
TASK006_BLIND12_COMPLETED_PACKAGE.json
TASK006_BLIND12_COMPLETED_PACKAGE_HASHES.json
benchmarks/cases/144_task006_blind_retry_requalification/
benchmarks/cases/145_task006_blind_full_qualification/
```

Case144 独立检查原 34 条 hash、两个 canonical retry、四个 retry attempt、lock 和
全部执行身份。通过后，Case145 才能在**原模型锁**下进行 12/12 完整评分。

最终分支：

### 8.1 完整 blind 通过

创建：

```text
TASK006_FORWARD_SURROGATE_QUALIFICATION.json
TASK006_FORWARD_SURROGATE_QUALIFICATION.md
```

然后停止等待下一任务审阅。此时才允许声称：

> 固定 A05/A07/A09、13.5 nm、S 入射及 frozen p5/Ny4 forward identity 下，二维
> h/w 代理通过独立 12-geometry blind qualification。

### 8.2 完整 blind 模型指标失败

保存不可变：

```text
TASK006_BLIND_MODEL_FAILURE.json
```

不得使用 blind12 调模型、改 tie-break 或重新声称 blind validation。

### 8.3 两点仍无法重复通过

保存不可变 forward robustness closeout。后续若研究新的 solver profile，必须作为
新的 numerical identity 重新资格化，不得静默混入当前 train37/blind 包。

---

## 9. 本轮明确禁止

```text
重跑79个training FEM
重跑34个成功blind records
增加training geometry或主动学习
更换legendre_3
修改模型锁
读取Task003 frozen validation
运行Task004 blind24
放宽1e-9 residual Gate
将部分blind结果称为正式资格通过
开始Bayesian inversion或实验拟合
扩展P偏振、波长或更多结构参数
```

---

## 10. 给 Codex 的执行指令

```text
请执行 git pull --ff-only，并完整阅读：

surrogate_tasks/task006_fixed_illumination_hw_surrogate/review_report_v2.md

先执行M3R0，不得立即重跑FEM：
- 保留Case141和原失败目录/hash；
- 提取两条失败记录的实际residual/KSP/MUMPS/resource遥测；
- 记录legendre_3与GP/trend-GP的training score并列，但不得改模型锁；
- 冻结仅包含117.5,17.25/A07和A09的BLIND_RETRY_PLAN；
- 建立Case143独立checker。

Case143通过后，才允许每个失败tuple运行两次完全相同身份的fresh-process重试，
最多4个FEM。不得放宽residual Gate或改变任何solver/model/config参数。

只有两个tuple均2/2 measured_pass且重复响应一致，才组装34个原成功记录加2个
canonical retry记录，并在原模型锁下执行唯一一次12/12完整blind qualification。

无论重试或最终评分通过/失败，均提交证据并停止等待下一轮审阅。
不得重训、主动加点、换模型或开始正式反演。
```
