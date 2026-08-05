# Task006 M3R forward robustness closeout

## 结论

Case143 的无 FEM 预检查通过后，严格按冻结身份完成了唯一允许的四个
fresh-process 重试：`117.5,17.25/A07` 和 `A09` 各两次。四次都完成了
Full3D 求解，但每次都只因原封不动的 `true_residual_le_1e-9` Gate 失败；其余
前向、能量、固定 order、topology、n≠0 leakage 和 ledger Gate 均通过。

两次重复的 residual 和 observable vector 分别完全一致（固定 order 的复振幅、
功率和 mask 使用 `1e-10` 绝对比较），因此这是可重复的 forward numerical
robustness 缺口，不是代理预测误差。四个 FEM 已耗尽本轮授权预算，状态冻结为：

```text
status = controlled_stop_blind_forward_incomplete
qualification_status = blind_forward_route_not_reproducibly_qualified
training qualification = passed and locked
full 12/12 blind qualification = not run
```

### 实际重试结果

| tuple | repeats | relative residual | failed Gate | 其他 Gate | repeat response |
|---|---:|---:|---|---|---|
| `117.5,17.25/A07` | 2/2 | `1.5050283166105661e-09` | `true_residual_le_1e-9` | 全部通过 | 一致 |
| `117.5,17.25/A09` | 2/2 | `1.4079544140587495e-09` | `true_residual_le_1e-9` | 全部通过 | 一致 |

A07 的绝对残差范数/RHS 分母为
`3.2603068026197944e-09 / 2.16627605383681`，A09 为
`6.739545376931229e-09 / 4.786763910560821`。两者都保留了原始
`CONVERGED_ITS`、MUMPS 和资源证据；没有提高容差、改变 mesh/p/MPI/thread、
MUMPS/PETSc 选项或切换模型。

## 证据边界

- [Case143 record](../../../benchmarks/cases/143_task006_blind_retry_preflight/records/case143_check.json) 在重试前通过，原 Case141 campaign、failure report、lock 和失败目录的 hash 保持不变。
- [retry manifest](../../../benchmarks/artifacts/cases/144_task006_blind_retry_requalification/BLIND_RETRY_CAMPAIGN.json) 只含四个授权 attempt；[Case144 checker](../../../benchmarks/cases/144_task006_blind_retry_requalification/records/case144_check.json) 独立确认四个 formal record 的身份、hash、唯一失败 Gate 和重复响应一致性。
- 第一次错误激活造成的 ABI preflight 中止记录在 `BLIND_RETRY_PREFLIGHT_ABORT.json`，其 FEM count 为 0，不计入四个 solver retry，也没有写入原目录。
- 由于两个 tuple 均未达到 2/2 `measured_pass`，没有生成 canonical retry sample、没有把 34 条原成功记录与 retry 混合、没有执行唯一的 12/12 blind qualification，也没有运行模型训练、主动加点或反演。

模型选择并列只作为历史语义保留在 `MODEL_SELECTION_TIE_AUDIT.*`；模型锁
`TASK006_MODEL_SELECTION_LOCK.json` 未被修改。后续若研究新的 solver profile，
必须作为新的 numerical identity 重新资格化，不能把本次失败重试混入当前
train37/blind package。
