# Candidate D 局部 p2 预条件器：D0 受控负结果

## 身份与范围

| 项目 | 值 |
|---|---|
| 结论 | `D0 FAIL / controlled_negative_numerical` |
| source SHA | `6f152a6e50f8e8fc475fc6b3e2bc39aca1bdf1d2` |
| 分支 | `codex/20260803-task37-matrix-free-iterative-development` |
| 运行类型 | serial algebra-only；非 PDE、非 full solve |
| activation | qualified `scripts/activate_myfenics_wsl.sh`，项目 `.venv` |
| ABI | PETSc `complex128/int32`；Python/MPI/PETSc/DOLFINx 同一 Linux ABI |
| 命令 | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q -s src/test/test_241_task037_candidate_d_local_p2.py` |
| 测试结果 | `1 xfailed`，4.00 s；完整诊断已打印 |

Candidate D 的局部预条件器使用真实 transfer `P_j`，先构造同一局部算子
`A6_j = R6_j (A6 + S6) R6_j^T`，再使用
`P_j A2,j^-1 P_j^H v + v/(diag(A6_j))`。这里的 p2 矩阵只保留
ILU factor；p6 slab matrix 和 p6 factor 均不保留。

## 代数与库存 Gate

| 指标 | measured 值 | Gate |
|---|---:|---|
| same-shift projected action relative error | `3.447354284340337e-16` | `<=1e-11`，通过 |
| omitted-shift controlled negative error | `0.09547160292763984` | 显著非零，负对照通过 |
| factor-only solve repeat error | `0.0` | `<=1e-12`，通过 |
| p2 slab factor count | `2` | 正常 |
| p2 slab factor NNZ | `4608` | 正常 |
| p6 slab matrix count | `0` | 必须为 0，通过 |
| p6 factor count / NNZ | `0 / 0` | 必须为 0，通过 |

`same_shift_error` 验证了 shift 通过同一个 `P_j` 投影；`no_shift_error`
是受控负对照，证明测试没有只把实现和自己比较。

## D0 source 结果

`rho` 是四步局部校正后 `||r-Az||/||r||`。`improvement` 定义为
`rho_B4/rho_D`，D0 要求 high 和 mixed 都至少为 `1.5`。

| source | rho_B4 | rho_D | improvement | Gate |
|---|---:|---:|---:|---|
| low | 0.24599945418880295 | 0.2540230551088513 | 0.9684138870126958 | 描述性 |
| high | 0.24651896436171644 | 0.26531876351572775 | 0.929142594723057 | FAIL |
| mixed | 0.24612971921817314 | 0.2715867504171219 | 0.9062655628087525 | FAIL |

因此 D0 的高频与混合 source 均未达到改善阈值；这是真实数值负结果，
不是 fixture 或资源失败。Candidate D 不具备继续进入重型漏斗的资格。

## xfail 语义与停止边界

test241 在完成所有 earlier algebra、same-shift、finite、factor-only
repeat、inventory 和三类 source 诊断并打印完整 metrics 后，才对
`high` 或 `mixed` improvement 小于 `1.5` 调用条件性
`pytest.xfail`。这不是放宽 D0 阈值，也不掩盖任何更早的普通失败；若未来
两项都达到阈值，测试将不调用 xfail 并自然通过，需重新审阅资格。

本轮未运行并按 V3 停止规则保持 `not_run`：

| 项目 | 状态 | 原因 |
|---|---|---|
| MPI2 / MPI4 D0 | `not_run` | serial D0 numerical Gate 已失败 |
| D1 screen20/100/200 | `not_run` | D0 负结果，V3 禁止进入下一阶段 |
| Candidate D full | `not_run` | 未取得 D0 资格 |
| PDE、full repository pytest | `not_run` | 本阶段范围禁止 |

普通 B4/default 路径未改变；Candidate D 仍是 research-only，不能称为
production-qualified，也不能替代 direct solver。后续只允许由 V3 R7 新审查
明确授权；不得在本轮重开 D 调参、shift/steps 扫描或其他 Schwarz 变体。
