# Task036 Response V4

## 结论先行

```text
Phase A exact one-cell audit = completed_fail_closed
axial cross-mode mixing = not_proven
projected/block propagation = not_authorized_not_implemented
production candidate = none
Hybrid production qualification = stopped
iterative implementation = not_started
ordinary default = unchanged
master = untouched_not_merged
```

这轮没有继续“试一个新传播矩阵看看”。先把 A004-S 中间规则区域的一个真实 10 nm
三维 Nédélec 单元拆出来，消去单元内部未知量，再用 Full3D 的原始有限元 trace 检查
现有 scalar-CG 逐模态传播。

结果表明：对实际场中重要的模式，现有 scalar-CG 传播通过；没有证据证明当前误差由
M120 空间内部的 cross-mode mixing 引起。失败的是 M120 trace basis 对 Full3D 端点场的
完整表示能力。由于一个 `120 x 120` 传播矩阵只能重排当前空间内的分量，不能生成空间
外缺失的分量，所以 Review V4 的 Phase B 条件不成立。

## 1. 本轮做了什么

1. 新增真实 p5 `(6,4,1)` one-cell assembly-time static condensation 审计；
2. 建立 left/right 端口行、两端口 Schur 块和 Petrov 投影；
3. 用 raw production Floquet constraint rows 审计高阶 orientation；
4. 验证正确/错误 outward-normal 符号；
5. 用 scalar-CG 和 continuous-beta 分别计算 per-mode、group 和 projected
   off-diagonal residual；
6. 运行唯一允许的 A004-S p5/h10 MPI8 Full3D exact-trace oracle，保存 11 个结构化
   z 平面的原始 FE trace；
7. 比较 sampled 与 exact coefficient oracle；
8. 按 A/B/C/D 规则 fail closed，未实现 projected/block propagation。

详细数值表见：

[one_cell_discrete_bloch_audit.md](outcomes/one_cell_discrete_bloch_audit.md)

## 2. strong trace 为什么没有修复衍射通道

Review V3 已证明 strong trace 的代数和资源实现正确：它消除了接口上没有被模态系数
控制的自由补空间，接口跳跃降到机器精度，但 A004-S 的 19 个失败通道和约
`1.53e-5` energy 平台几乎不变。

本轮进一步说明原因不应被写成“现有 M120 模式之间需要一个传播混合矩阵”：

- significant-mode scalar-CG `rho` 为 `6.40e-11 / 6.51e-11`，通过 `1e-10`；
- global projected off-diagonal ratio 为 `3.36e-12 / 3.30e-12`；
- exact Full3D 跨单元 forward/backward mismatch 为 `2.00e-7 / 9.21e-9`；
- 唯一 connected block 只含非显著尾部模式，没有相同 exact physical group 支持。

更直接的信号是 Full3D 端点 trace 投影进 M120 空间仍有
`3.51e-6 / 5.22e-6` 残差。strong trace 强制接口场属于 M120 空间时，也会强制丢掉这
部分空间外内容；把同一空间内部的传播从 diagonal 改成 matrix 并不能补回它。

## 3. exact one-cell 审计是否证明 cross-mode mixing

**没有。**

| 判据 | 结果 | Gate | 状态 |
|---|---:|---:|---|
| forward significant `rho` | `6.39675e-11` | `1e-10` | pass |
| backward significant `rho` | `6.50899e-11` | `1e-10` | pass |
| forward projected offdiag | `3.35919e-12` | `1e-8` | pass |
| backward projected offdiag | `3.30137e-12` | `1e-8` | pass |
| exact forward trace-metric mismatch | `2.00386e-7` | mixing支持需 `>4e-4` 且对齐 | 不支持 |
| exact backward trace-metric mismatch | `9.21383e-9` | 同上 | 不支持 |
| exact M120 trace projection | `5.22493e-6` | `1e-8` | **fail** |

因此 artifact 给出的正式分类为
`D_OR_PHASE_A_INDETERMINATE`：trace-space foundation 未闭合，Phase B 禁止。

旧 sampled oracle 的 forward mismatch 约 `3.9956e-3`；本轮 sampled 与 exact
endpoint coefficients 自身就相差 `7.99e-6 / 1.19e-5`，而 exact 多平面传播 mismatch
降到 `2.00e-7`。旧采样诊断不再作为 matrix mixing authority。

## 4. 是否实现 projected discrete Bloch propagation

没有实现，也没有修改 production Hybrid propagation core。

Review V4 只允许在 Phase A 明确证明 B 或 C 时进入 Phase B。本轮既没有认证的局部
block mixing，也没有广泛 off-diagonal mixing；同时 exact trace projection foundation
失败。继续实现只能是没有证据支撑的尝试，并且不能达到用户要求的 production level。

## 5. PDE 与 fixture 运行表

| 项目 | 运行状态 | 结果 |
|---|---|---|
| analytic sign fixture | pass | polynomial `2.01e-16`；wrong sign `1.381` |
| p1–p5 matched-trace fixture | pass | targeted tests |
| MPI2 M4 one-cell fixture | pass | Floquet约 `8.4e-16`，scalar offdiag约 `2.7e-13` |
| MPI1 standard/static matrix | pass，复用 | Frobenius `4.327e-15` |
| MPI8 M120 one-cell + exact Full3D | pass as audit | Full3D residual `8.317e-11`，energy `-1.612e-12` |
| Task035c high-grazing S control | not_run | Phase B未授权 |
| A004-S new Hybrid | not_run | 没有 new propagation |
| A049-P | not_run | A004-S 前置条件未满足 |
| A001-P | not_run | A004-S 前置条件未满足 |

唯一 Full3D oracle 的实际网格为 `(6,4,14)`，134,320 FE DoF；condensed+DtN 矩阵
46,656 rows、26,952,096 NNZ，factor 164,378,718 NNZ，总求解时间 132.598 s。
它只用于 exact trace，不是恢复参数扫描。

## 6. 本轮真正修复了什么

### 6.1 修复

- one-cell audit 的 PETSc 子矩阵构造改为合法的稀疏插入路径；
- 分布式端点 lift 改用 raw Floquet slave/master/coefficient/offset rows 检查，避免把
  ordinary interpolated vector 错当作可直接 `backsubstitution` 的解；
- exact Full3D observer 在诊断前保存原始 FE trace 和 Petrov coefficients；
- root-only artifact 写入传播异常，避免 MPI rank 等待；
- 复用 MPI1 standard/static authority 时增加冻结 SHA-256、ABI、case、row/NNZ、
  Git ancestry 和 matrix-kernel identity 校验；
- p1–p5 matched-trace 覆盖补齐。

这些是审计和证据路径修复，不是生产 Hybrid 数值修复。

### 6.2 被否定的假设

- “自由 trace complement 是主因”：Review V3 actual anchor 已否定；
- “M120 内部的 scalar-CG 模式互混是主因”：本轮 exact one-cell 审计不支持；
- “旧 sampled coefficient mismatch 足以启动 matrix propagation”：本轮 exact FE
  oracle 否定。

### 6.3 deferred

当前 physical QEP M120 trace space 对端点 exact Full3D 场的严格表示不够。修复它需要
新的 port-basis 架构，而不是 Task036 内的局部 bug port；因此分类为
`DEFERRED_ARCHITECTURE_REQUIRED`。

## 7. 代码、提交与测试

### 7.1 Git 身份

| 项目 | SHA |
|---|---|
| 起始 Task036 HEAD | `ec8d49f65d7094899ffdb3edb1f50ca2ce5c4005` |
| 起始/当前 master authority | `007298261681014efbe6508ac91c6c3ae9a6a44a` |
| 正式数值 SHA | `c70ad32e3cb741f382e2cc901e056ae1ea0ba284` |
| 文档前审计 hardening SHA | `7bccfeb` |
| 最终 Task036 HEAD | 见本轮最终提交及聊天报告 |

关键提交：

```text
5cdcd748a986995f78faf93c9c914134cf60a2c3  add exact one-cell Bloch audit
7445298a0a174b524f83f625304fffb77ef81171  audit Floquet lifts from raw rows
c70ad32e3cb741f382e2cc901e056ae1ea0ba284  reuse serial matrix authority
7bccfeb                                      harden reused authority Gate
```

### 7.2 修改文件

```text
src/solvers/one_cell_discrete_bloch.py
benchmarks/run_task036_one_cell_discrete_bloch.py
src/test/test_214_task036_one_cell_discrete_bloch.py
src/test/test_52_task033_high_order_matched_trace.py
docs/task036_forward_solver_bugfix_hardening/
  outcomes/one_cell_discrete_bloch_audit.md
  response_v4.md
```

### 7.3 测试

在 qualified WSL 环境已经完成：

```text
targeted one-cell + matched-trace tests = 4 passed
broader focused strong-trace set       = 10 passed
local Markdown link contract           = 1 passed
Ruff                                   = pass
compile/py_compile                     = pass
git diff --check                       = pass
MPI2 M4 fixture                        = pass
MPI8 M120 exact oracle                 = completed
```

本轮出现明确的 Phase A negative 后，按用户指令没有运行 full-repository pytest。没有
把“未运行”写成通过。曾尝试包含全局 case registry 的文档合同组合，结果为
`17 passed, 1 failed`；唯一失败是既存 `test_26` 尚未登记历史 Case098/099，与本轮文件
和链接无关，因此没有越界修改旧 registry。随后精确的本地 Markdown 链接测试通过。

## 8. production disposition

```text
strong trace = research algebra/resource pass, physical qualification fail
projected Bloch = not implemented
Hybrid = not production-qualified
Task036 = stop after Phase A
Full3D iterative = not started in this task
master = not modified, not merged
```

## 9. 唯一下一建议

Task036 现在停止并等待审阅；在用户再次授权前不进入迭代法。后续唯一 production
建议是另立任务执行
**Full3D assembly-time static condensation + FGMRES +
H(curl)/trace-aware preconditioner**。本轮没有实现或运行它。

`full-interface discrete Bloch trace modes` 仅作为延期研究方向，不是本轮自动后续。
