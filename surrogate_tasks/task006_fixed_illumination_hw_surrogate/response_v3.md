# Task006 Response V3：M3R0 遥测、固定身份重试与受控停止

## 执行边界

本轮先执行 `git pull --ff-only`，确认分支已是远端最新；随后完整读取
`review_report_v2.md`。Task006 的 train37、原 Case141 blind 记录和
`TASK006_MODEL_SELECTION_LOCK.json` 均保持不可变。没有重训、主动加点、换模型、
访问 Task003 frozen validation 或开始正式反演。

## M3R0：无 FEM 预检查

从原 Case141 的两个失败目录只读提取了 residual、KSP、MUMPS、矩阵和资源遥测，
并保存为 `BLIND_FORWARD_FAILURE_TELEMETRY.json/.md`。Case143 checker 在任何
重试前通过：

```text
case143 status                 = pass
retry_authorized              = true
generated_without_fem         = true
failed tuple set              = exactly A07 and A09
original campaign/lock hashes = unchanged
```

training-only score 并列也只被记录，没有修改模型锁：
`legendre_3 = 1.0`、`matern52_ard_exact_gp = 1.0`、
`degree2_trend_plus_matern52_residual = 1.0`。固定候选顺序的历史 tie-break
仍选择 `legendre_3`。

原失败遥测的关键值为：

| tuple | relative residual | absolute residual / RHS | KSP | swap |
|---|---:|---:|---|---:|
| `117.5,17.25/A07` | `1.5050283166105661e-09` | `3.2603068026197944e-09 / 2.16627605383681` | `CONVERGED_ITS`, 1, preonly+MUMPS | 0 B |
| `117.5,17.25/A09` | `1.4079544140587495e-09` | `6.739545376931229e-09 / 4.786763910560821` | `CONVERGED_ITS`, 1, preonly+MUMPS | 0 B |

未记录的环境字段明确标为 `not_recorded`，没有从缺失字段推断数值。原
Case141 campaign、failure report、formal record、execution 和失败目录 hash
都在 plan/checker 中绑定。

## M3R1：四个且仅四个授权重试

Case143 通过后，使用完全相同的 forward/config identity：

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
model/route        = S_PROD_FULL3D_STATIC_P5_H10_NY4 /
                     full3d_static_uniform_n1curl_p5_h10_ny4
mesh               = (6,4,14), degree 5, h=10 nm
observable         = task002.fixed-n0-orders.v3
MUMPS              = ICNTL(14)=40, ICNTL(22)=0
MPI / threads      = 2 / 1
residual Gate      = true_residual <= 1e-9
```

A07 和 A09 各运行 attempt 2、3 两个独立 fresh process，共四个 FEM。第一次
错误 orchestration shell 在 ABI preflight 阶段发现 `/mnt` PATH 污染并在 FEM
前中止；该事实单独记录在 `BLIND_RETRY_PREFLIGHT_ABORT.json`，FEM count 为 0，
不占用四个授权 solver attempts。修正为仓库资格化 `.venv` activation 后，四个
solver attempts 均完整结束：

| tuple | attempts | measured pass | relative residual | 失败 Gate | 复响应 |
|---|---:|---:|---:|---|---|
| `117.5,17.25/A07` | 2 | 0/2 | `1.5050283166105661e-09` | `true_residual_le_1e-9` | 一致 |
| `117.5,17.25/A09` | 2 | 0/2 | `1.4079544140587495e-09` | `true_residual_le_1e-9` | 一致 |

两次重复的 absolute residual、RHS、reduced trace residual、fixed-order 功率、
复振幅和 power-carrying mask 一致到 Case144 规定的 `1e-10` 绝对容差；其余
original numerical/resource Gate 均为 true。四个 formal record 的 source SHA、
model/route、observable、MPI/thread、execution hash 均通过 Case144 独立检查，
且四个 attempt 都没有生成 production sample。

Case144 的结果为：

```text
checker status                         = pass
qualification_status                  = blind_forward_route_not_reproducibly_qualified
retry_reproducibly_qualified          = false
model_lock_modified                   = false
original_case141_modified             = false
```

这里的 checker `pass` 只表示负结果证据和重复一致性合同通过，不表示 forward
route 或代理资格通过。

## M3R2 未执行

因为两个 tuple 均未达到 `2/2 measured_pass`，按 review 的 controlled-stop 规则：

- 没有选择 canonical retry；
- 没有建立 `34 original + 2 canonical` package；
- 没有重用 34 条成功记录做新的 12/12 scoring；
- 没有运行 Case145 或任何新的 blind qualification；
- 没有改写 model lock、训练数据、阈值或模型候选。

最终状态写入：
`outcomes/TASK006_BLIND_FORWARD_RETRY_CLOSEOUT.json/.md`，并同步更新
`outcomes/summary.md` 与本任务 README。后续若要研究另一种 solver profile，必须
作为新的 numerical identity 重新资格化，不能把本轮四个失败重试混入当前
train37/blind package。
