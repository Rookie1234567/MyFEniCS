# Task001 M9：五个失败照明配置的根因分析与鲁棒性修正

## 状态

```text
status = ready_for_codex_execution
parent_review = review_report_v2.md
Task002 = blocked
bulk_generation = forbidden
surrogate_training = forbidden
inversion = forbidden
```

本任务只解决 Task001 中五个失败照明配置的代码鲁棒性问题。不得重新定义用户参数域，不得删除 P 偏振，不得提高掠射角下限，不得通过放宽 Gate 获得成功。

## 五个目标配置

```text
F1 = grazing 0.5°, azimuth 0°,  S
F2 = grazing 0.5°, azimuth 0°,  P
F3 = grazing 0.5°, azimuth 90°, P
F4 = grazing 10°,  azimuth 0°,  P
F5 = grazing 10°,  azimuth 90°, P
```

## 执行顺序

### 1. 接收与复现

- 完整读取 `review_report_v2.md`；
- 确认唯一 branch/upstream、clean status 和最新 HEAD；
- 复用已有失败 raw artifacts 和 hashes；
- 在新 clean implementation baseline 上仅重跑 LF4/G00 必要诊断；
- 每次一个 forward job、MPI2、threads=1、zero swap、watchdog。

### 2. F1/F2 trace reduction

必须记录每个 interface mode：

```text
side / role / mode index / kind / beta
mode normalization and trace norm
quadrature degree and coefficient degree
max active / slave / cell-interior entry
absolute and relative cutoff
roundoff units
first offending dof/entity
```

依次验证：

1. lifted DG coefficient 的真实 polynomial degree；
2. interface quadrature convergence；
3. equivalent modal rescaling invariance；
4. standard Hybrid 与 static-condensed Hybrid；
5. full-space surface vector与trace/entity-supported assembly；
6. near-Rayleigh beta conditioning。

禁止将 `1e-7` 通过提高 eliminated tolerance 掩盖。

### 3. F3--F5 P 偏振

依次验证：

1. algebraic interface projection和traction residual；
2. assembled H(curl) trace mass/Riesz E residual；
3. assembled traction/H dual residual；
4. sampled interface diagnostic的分子、分母、绝对误差和one-sided cell identity；
5. reconstruction使用的 propagation beta；
6. reconstruction使用的 traction beta；
7. continuous QEP beta与discrete scalar-CG beta混用；
8. M=40/80/120/160 收敛；
9. standard/static observable equivalence；
10. phi=0 与2D TE/TM或direct 3D low-order reference；
11. phi=90 与direct Full3D low-order reference；
12. S/P共偏振、交叉偏振和功率归一化。

### 4. 修复原则

允许的修复包括：

- 正确的高阶 surface quadrature；
- trace/entity-aware surface assembly；
- 稳定的 near-Rayleigh mode normalization；
- propagation/traction/reconstruction beta 统一；
- exact assembled interface diagnostic；
- 经过收敛证明的 modal count 更新；
- 明确的 Rayleigh limiting formulation。

禁止：

- 只提高容差；
- 只关闭 physical Gate；
- 只删除失败配置；
- 把 P 结果改成 S；
- 修改原始失败证据；
- 将不同 M、不同 source 或不同 schema 静默混合。

### 5. 正式验收

F1--F5 每个 G00 必须满足：

```text
complete solver record
true relative residual <= 1e-9
interface projection residual <= 1e-8
traction equilibrium residual <= 1e-8
assembled physical interface E/H Gate pass
sampled and assembled diagnostic conclusions agree
abs(R + T + A_volume - 1) <= 1e-5
raw diffraction sum matches R/T
fixed-order mother response valid
zero process swap
watchdog cleanup complete
```

若某点被判定为精确 Rayleigh 数学奇点，必须由解析 beta 判据识别，并提供两侧角度极限与收敛证据；普通求解异常不能重命名为奇点。

### 6. 回归

修复后至少运行：

- 原通过的 `10°/0°/S`；
- 原通过的 `10°/90°/S`；
- 原通过的 `0.5°/90°/S`；
- F1--F5；
- Case095/096 targeted contracts；
- static-condensation tests；
- observable schema v2 checker；
- compileall 和 `git diff --check`。

只有最终 DOE 需要的新配置才扩展到 9 个 geometry points；不得在定位阶段运行完整 campaign。

## 必须交付

```text
benchmarks/cases/111_task001_illumination_robustness/
  README.md
  config.json
  expected.json
  test_command.txt
  records/

surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/outcomes/
  five_configuration_failure_correction.md
  test_summary.md
  illumination_identifiability.md
  task002_dataset_plan.md

surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/
  response_v3.md
```

`five_configuration_failure_correction.md` 必须逐项给出 F1--F5 的：

- 原始失败值；
- diagnostic matrix；
- 排除的假设；
- 最终根因；
- 数学和代码修复；
- before/after 指标；
- independent reference；
- M/quadrature/normalization 收敛；
- 新测试；
- 剩余边界。

完成提交、推送后停止，等待 ChatGPT Review V3。不得开始 Task002。
