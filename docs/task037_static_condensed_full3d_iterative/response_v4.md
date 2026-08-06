# Task037 Response V4：Candidate F F0 修复后科学负结果

## 1. 结论与边界

本轮数值证据只验证 Candidate F 的 F0；随后按用户显式追加指令完成 V4-6 docs-only closeout。前一轮的 PETSc 索引类型错误已通过最小修复消除，测试能够进入完整的 p4 capacity oracle 计算；但 F0 的科学 Gate 失败，因此 Candidate F 仍是受控科学负结果，不是实现失败，也不是生产求解器资格。

这里的“残差”可以直观理解为误差剩余量；“improvement”定义为 B4 残差除以 Candidate F 残差，只有大于 1 才表示残差下降。本次三个 source 的 `rho_F` 都大于 1，说明 p4 correction 实际放大了残差。

| 项目 | 结果 |
|---|---|
| 审查边界 | Review V4；用户要求按 V4-1→V4-6 顺序执行，任一 Gate 失败立即停止 |
| Candidate F F0 | `P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE` |
| `ordinary_defaults_changed` | `false` |
| `production_qualified` | `false` |
| 生产代码/默认参数 | 未修改 |
| 测试重跑 | 只运行一次；失败后未重跑 |

静态凝聚是先把每个单元内部的未知量消掉，只保留接口上的未知量。Candidate F 的 F0 是容量和作用测试，用来判断 p4 中间空间能否帮助 p6 的局部修正；它不是正式 PDE 求解。

用户级 stop 规则覆盖 Review V4 中 V4-2/V4-3 的独立必做安排，也覆盖 F0 失败后启动 V4-5 的一般安排。因此 F0 失败后 V4-2、V4-3、V4-4、V4-5 均未运行；本次用户显式追加的 V4-6 docs-only closeout、compact evidence 和本 response 已完成。

## 2. 提交链与静态 Gate

| 提交 | 内容 | 验证 |
|---|---|---|
| `fbb99bf90b2beee2d0d614815314d3502408af00` | Markdown 公式清理，3 个 Markdown，`153+/153-` | 修复脚本 exit 0；`--check` exit 0；`git diff --check` exit 0 |
| `1e641c5c23f3d87c8d72b5ad622921681fe556a8` | 仅 `test_246` 新增 `from petsc4py import PETSc`，并将 `p6_rows` dtype 改为 `PETSc.IntType` | Ruff check、Ruff format check、compileall、`git diff --check` 全部通过 |

本轮测试使用 qualified activation：`/home/Projects/MyFEniCS/.venv/bin/python`，`PETSc.ScalarType=complex128`，`PETSc.IntType=int32`，MPI size 为 1，工作树在运行时 clean。

## 3. 唯一 F0 命令与资源记录

核心命令只执行一次：

```bash
python -m pytest -q -s -x \
  src/test/test_246_task037_p4_capacity_oracle.py::test_f0_degree_pairs_preserve_floquet_orientation_identity \
  src/test/test_246_task037_p4_capacity_oracle.py::test_f0_p4_capacity_oracle_and_d0_comparison
```

| 指标 | 实测值 |
|---|---:|
| pytest 结果 | `1 passed, 1 failed` |
| exit code | `1` |
| pytest 报告耗时 | `20.84 s` |
| `/usr/bin/time -v` wall | `21.22 s` |
| MaxRSS | `287300 kB` |
| swap | `0` |
| serial / MPI size | `true / 1` |
| 重跑次数 | `0` |

上述内存是 serial tiny F0 进程的记录，不是正式 solver peak，也不是正式 PDE 内存结论。

## 4. Transfer identity 审计

以下数值均来自本次 clean SHA 的 stdout 原始审计：

| 指标 | 实测值 |
|---|---:|
| composition error | `3.512063090206927e-15` |
| P24 interpolation error | `8.326653945790752e-16` |
| P46 interpolation error | `6.595217588690049e-15` |
| P24 adjoint error | `1.1106734086056049e-15` |
| P46 adjoint error | `2.6080775955612308e-15` |
| orientation nonzero count | P24=`21`，P46=`21` |
| active rows | P24=`2712`，P46=`6372` |
| Floquet phase x | `(0.8541859931542107-0.5199675846619236j)` |
| Floquet phase y | `(0.818001826003227+0.5752156227497531j)` |

Transfer identity Gate 通过。

## 5. Capacity action 审计

| 指标 | 实测值 |
|---|---:|
| transfer46 adjoint error | `3.441690023284426e-16` |
| transfer24 adjoint error | `4.945975109804328e-16` |
| projected4 error | `7.327741312843947e-16` |
| projected2 error | `3.3442374965785637e-16` |
| high complement absolute | `9.203541846744294e-17` |
| p4 repeat error | `0.0` |

这些 action、投影和重复性检查均通过 `<=1e-11` Gate。

## 6. low/high/mixed 完整 residual 审计

`rho_B4` 是 B4 基线残差，`rho_F` 是 Candidate F p4 correction 后残差，`rho_D0_frozen` 是冻结的 D0 对照；`improvement = rho_B4 / rho_F`。

| source | `rho_B4` | `rho_F` | `rho_D0_frozen` | improvement |
|---|---:|---:|---:|---:|
| low | `0.24599945418880292` | `1.7392087353510792` | `0.2540230551088513` | `0.14144331798054424` |
| high | `0.2465189643617165` | `1.3350076891675904` | `0.26531876351572775` | `0.1846573367045002` |
| mixed | `0.2461297192181731` | `1.517457339175566` | `0.2715867504171219` | `0.1621987734771478` |

三类 source 的 `rho_F` 均大于 1，故 p4 correction 放大残差。科学 Gate 要求 high 和 mixed improvement 均 `>=1.5`；实测分别为 `0.1846573367045002` 和 `0.1621987734771478`，因此分类必须为：

```text
P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE
```

该失败是科学方法 Gate 负结果，不是实现失败；PETSc dtype 修复已使 F0 完整执行。

## 7. capacity inventory

| 项目 | 实测值 |
|---|---:|
| p6 slab rows | `432` |
| p4 trace/factor rows | `192` |
| p2 trace/factor rows | `48` |
| p4 matrix shape | `192 x 192` |
| p4 matrix NNZ | `36864` |
| p4 factor NNZ | `36864` |
| p4 LU payload | `590592 bytes` |
| p4 matrix payload | `589824 bytes` |
| P46 transfer NNZ | `291` |
| P24 transfer NNZ | `96` |
| transfer payload | `1474560 bytes` |
| retained oracle payload | `2698752 bytes` |
| construction workspace lower bound | `147456 bytes` |
| p6 slab matrix/factor/NNZ | `0/0/0` |
| global p6 matrix/factor materialized | `false/false` |
| frozen D0 factor count/NNZ | `2/4608` |

因此本次 oracle 的 p4 matrix/factor 是实际构造的容量对象；p6 slab matrix 和 factor 均未物化，NNZ 为 `0/0/0`。完整 operator identity 为 `P46H_restricted_p6_action_P46`，correction identity 为 `P46_A4_inverse_P46H_plus_D6_inverse`。

## 8. raw artifact 与 compact record

raw 日志没有复制进 Git，只以绝对路径、SHA256 和字节数绑定：

| 文件 | 绝对路径 | SHA256 | size |
|---|---|---|---:|
| stdout | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037/v4_candidate_f_f0_1e641c5c/stdout.log` | `b9dfcafcced810876b273bd89738e1e37551d53ee64806ca74448ed3e3b3eced` | `10530` |
| stderr | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037/v4_candidate_f_f0_1e641c5c/stderr.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `0` |
| time | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037/v4_candidate_f_f0_1e641c5c/time_v.txt` | `930b92e780b4f079c540dc83ec25e88e0ec29b7b4c2f6ec7c568f1dcfe27006b` | `998` |
| exit | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037/v4_candidate_f_f0_1e641c5c/exit_code.txt` | `4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865` | `2` |

机器可读 compact record：[`task37_candidate_f_f0_postfix_scientific_negative_v1.json`](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_candidate_f_f0_postfix_scientific_negative_v1.json)。该 record 将原始审计标为 `measured`，Gate 判定和 improvement 比值标为 `derived`，未执行阶段标为 `not_run`。

## 9. V4 hard-stop 与后续决策

| 阶段/路线 | 状态 | 原因 |
|---|---|---|
| V4-1 | `completed_with_scientific_negative` | F0 完成，但 P4 intermediate space Gate 失败 |
| V4-2 | `not_run_after_f0_failure` | 用户级“任一 Gate 失败立即停止”覆盖 Review V4 独立必做安排 |
| V4-3 | `not_run_after_f0_failure` | 用户级“任一 Gate 失败立即停止”覆盖 Review V4 独立必做安排 |
| V4-4 | `not_run_after_f0_failure`; `not_authorized_by_F0_failure` | F0 科学 Gate 失败 |
| V4-5 | `not_run_after_f0_failure` | 用户级 stop 规则阻止启动后续数值路线 |
| V4-6 | `completed_docs_only_closeout` | 用户显式追加 docs-only closeout、compact evidence 和 response |
| Candidate F F1 | `not_run_by_f0_failure` | 不开发 F1 |
| Candidate F p3/p5 scan | `not_run_by_f0_failure` | 不扫 p3/p5 |
| Candidate F parameter tuning | `not_run_by_user_stop_rule` | 不调参 |
| Candidate E | `not_run_after_f0_failure` | Review V4 触发条件已满足，但更高优先级的“任一 Gate 失败立即停止”规则阻止执行 |
| full pytest | `not_run` | 本轮未授权 |

按 Review V4 关闭 Candidate F family 的后续开发，不开发 F1、不扫描 p3/p5、不调参；ordinary defaults 保持不变，`production_qualified=false`。

## 10. 数值证据身份与发布边界

| 字段 | 值 |
|---|---|
| branch | `codex/20260803-task37-matrix-free-iterative-development` |
| source SHA | `1e641c5c23f3d87c8d72b5ad622921681fe556a8` |
| 数值证据身份/报告父提交 | `1e641c5c23f3d87c8d72b5ad622921681fe556a8` |
| tested HEAD | `1e641c5c23f3d87c8d72b5ad622921681fe556a8` |
| tested upstream | `1e641c5c23f3d87c8d72b5ad622921681fe556a8` |
| ahead/behind | `0/0` |
| worktree_at_test | clean |
| full repository pytest | not run |

报告自身的发布 SHA 由后续 commit/push 外部回执提供；本 response 不在自身内容中写入该 SHA，以避免自引用。
