# Task004 Response V4：Required M4E controlled stop

## 1. 执行边界

本轮从 Review V3 的 Required M4E 开始，先执行 `git pull --ff-only`，
并以 `6ea590d7c44b1737dba90842b6fb02eb43d9b324` 为同步后的起点。所有
模型比较只读取不可变的 Case125 `train96` package：

```text
dataset_id          = task004_angle_nominal_p5_ny4_train96_v2
training rows       = 96
forward_solver_sha  = fdf961545f217d620e22800f2704ae9913a6d270
geometry            = h=120 nm, w=17 nm
angle domain        = grazing 0.5–10°, azimuth 0–90°
```

没有运行新 FEM，没有运行 24 个 blind-validation 点，没有打开 Task003
frozen validation，没有创建模型锁，也没有执行第二轮主动学习、Fisher、
geometry sensitivity 或 inversion。Case125 原始记录和其旧 holdout 文件
未被改写。

## 2. 实现与数据合同

新增 `src/surrogate/angle/m4e.py`，实现有限且可重建的四类候选：

1. local RBF + nested/cross-conformal uncertainty（邻居 24/32/48）；
2. local Matérn-5/2 ARD exact GP（邻居 24/32/48，确定性 8-start）；
3. topology-aware local expert；
4. 可选 Chebyshev degree-2 global trend + local residual。

所有候选使用同一组五折、同一 `zR/zT` composition latent 和同一 Gate。局部
Matérn 的每个 query 保存邻域、最近距离、fitted kernel、LML、选中的初值和
ConvergenceWarning 计数；警告没有被静默丢弃。局部 RBF 没有假造原生 GP
方差，而是用内层残差半径和外层 cross-fitted 校准产生训练经验不确定度。

在任何拟合前冻结了 `SUPPORTED_INTERPOLATION_WINDOWS_V2.json`。四个有限
局部窗口分别是 low-grazing、high-azimuth、cutoff-near 和
ordinary-interior；每个 held-out 点有六个不相交的 support rows。Case125
的 `SPATIAL_HOLDOUT_WINDOWS.json` 保留原内容和哈希，仅作为整区外推压力
测试的 advisory authority。

## 3. 分层资格结果

### Level A：aggregate R/T/A

CV 选择 `L1_local_rbf_k24_s1e-08`，其结果为：

| target | NRMSE | p95 abs | max abs |
|---|---:|---:|---:|
| `R_total` | 0.01877 | 0.02379 | 0.06020 |
| `T_total` | 0.02995 | 0.01521 | 0.11859 |
| `A_balance` | 0.04219 | 0.03665 | 0.13350 |

`R+T+A=1` 精确成立，selected candidate 的 cross-fitted coverage 为
`R=0.96875`、`T=0.95833`、`A=0.94792`。但是 accuracy Gate
（NRMSE≤0.01、p95≤0.01、max≤0.03）未通过，因此：

```text
aggregate = not_qualified_but_viable
```

这不是对前向有限元或二维响应本身的否定，而是当前局部模型仍不能在
冻结的完整 OOF 合同下达到筛选精度。

### Level B：order-resolved power

order 结果单独生成，不借用 Level A 的总布尔值。mask agreement 为 100%，
sidewise power ledger 最大误差为 `2.220446049250313e-16`，但 primary
channel Gate 未通过。例如 reflection `m=0,S` 的 p95/max 为
`0.0230207/0.10852`，transmission `m=0,S` 的 p95/max 为
`0.0196077/0.34159`，超过 `p95≤0.01` 或 `max≤` 规定值。因此：

```text
order_resolved = not_qualified
```

未激活的通道继续保留 false mask/null power；candidate pool 的 7 个 rare
unseen mask signatures 继续 fail closed，不能因 aggregate 有定义而被宣称
order-qualified。

## 4. 主动学习资格（仅生成，不执行）

local-RBF selected score `4.4499` 优于 Case125 global reference `4.9507`，
并且有 cross-fitted uncertainty 和可定位的高误差区域；因此生成了条件式
资格记录：

```text
eligible_for_one_round_16_fem = true
budget                       = 16
fem_started                  = false
validation_target_accessed   = false
plan_status                  = eligibility_only_no_fem
```

这里的 `true` 只是满足 Review V3 的 eligibility 记录条件，不是执行授权。
本轮没有生成或运行 16 个 FEM 点，没有改变 train96，也没有触碰 blind
validation。

## 5. 独立检查与证据

Case126 独立 checker 直接重算 train96 文件哈希、数组形状/dtype、角度/几何
身份、窗口支撑、旧 stress authority 哈希以及 aggregate/order/active-learning
合同，结果为 `pass`：

`benchmarks/cases/126_task004_local_topology_angle_surrogate/records/case126_check.json`

主要证据：

- `outcomes/ANGLE_AGGREGATE_QUALIFICATION_CONTRACT.json`
- `outcomes/ANGLE_ORDER_QUALIFICATION_CONTRACT.json`
- `outcomes/SUPPORTED_INTERPOLATION_WINDOWS_V2.json`
- `outcomes/ACTIVE_LEARNING_ELIGIBILITY.json`
- `outcomes/model_structure_comparison.md`
- `outcomes/aggregate_qualification.md`
- `outcomes/order_qualification.md`
- `outcomes/uncertainty_qualification.md`
- `outcomes/topology_support.md`
- `outcomes/test_summary_v4.md`

当前状态是受控停止，等待 ChatGPT Review V4。下一阶段如未获明确授权，
不得运行新 FEM、blind validation、Task003 Round3、第二轮主动学习、Fisher、
geometry sensitivity 或 inversion。
