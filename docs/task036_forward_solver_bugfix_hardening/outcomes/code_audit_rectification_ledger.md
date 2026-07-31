# Task036 code audit rectification ledger

## 1. 权威与边界

本台账逐项回应
[`code_audit_and_0p7nm_roadmap_report.md`](../code_audit_and_0p7nm_roadmap_report.md)，
输入报告的审计结论保持不变，仅按要求清理 Markdown 空白。整改实现与阶段性测试以
`1f4e48a...` 为历史基线；当前 pre-checkpoint HEAD/upstream 已因 review-only fast-forward
更新为 `3375e417...`。不把 checkpoint 前的 worktree 实现误写成已进入当前 HEAD，也不因
旧快照结论而强行修改代码。

| 项目 | 值 |
|---|---|
| 原审计报告快照 | `6efcafff318dce684ad35648e4568baebe8f5d20` |
| 整改实现 / 阶段性测试历史基线 | `1f4e48a9683b9167bedb28aaf4ee44931078b40b` |
| 当前 pre-checkpoint HEAD / upstream | `3375e417dd2cca2c56479ef0c58039b79c3019c8` / `3375e417dd2cca2c56479ef0c58039b79c3019c8` |
| Review-only fast-forward | `1f4e48a...` 至 `3375e417...` 仅更新 `review_report_v5.md`，未改变 Python 内容 |
| Checkpoint 前实现身份 | 73-entry 未提交工作树；未 commit、未 push；提交后本行仅作为历史验证状态 |
| 最终证据绑定 | checkpoint 前 worktree diff + 历史基线 HEAD + pre-checkpoint HEAD + 资格化环境 |
| 工作分支 | `codex/20260730-task36-forward-solver-bugfix-hardening` |
| 执行环境 | WSL Ubuntu；仓库资格化 activation |
| PETSc scalar / integer | `complex128` / `int32` |
| 重型 PDE / MUMPS | 本轮不运行 |
| 普通数值 solver/backend default | 不修改 |
| checker CLI default | S09 已改为默认只读；仅显式 `--write` 写 tracked 汇总 |
| master | 不修改、不合并 |

每个已审计条目只保留一个既有正式 enum，并映射为三类审阅语义：`FIXED` 表示“已整改”；
`ALREADY_FIXED` 与 `NOT_A_BUG/NO_CHANGE` 表示“无需改”；`DEFERRED/ROADMAP` 表示
“后续路线”。“无需改”同时覆盖“报告归属不成立”和“整改基线已具备等价实现”两类情况，
但每项都必须给出具体理由和证据。下方实现身份记录的是 checkpoint 前未提交工作树；提交
后不得再把该历史状态解释为当前工作树状态。45 项统计包含 F/D/N/S/A 全部编号，D01 与
N01 均计入。

## 2. 工作队列

| 顺序 | ID | 报告条目 | 最终工作树结论 |
|---:|---|---|---|
| 1 | F01a | 5.1 完整进程组终止 | `FIXED` |
| 2 | F01b | 5.1 `/init.scope` 不得作为单 job authority | `FIXED` |
| 3 | F02a | 5.2 workstation false-pass / exit code | `FIXED` |
| 4 | F02b | 5.2 Task031 screen-only 语义 | `FIXED` |
| 5 | F03 | 5.3 `A_volume` 缺失与 partial sum | `FIXED` |
| 6 | F04 | 5.4 QEP requested/actual provenance | `FIXED` |
| 7 | F05a | 5.5 无可验证身份的 existing artifact 安全拒绝 | `FIXED` |
| 8 | F05b | 5.5 原子输出目录 | `FIXED` |
| 9 | F05c | 5.5 source attestation | `FIXED` |
| 10 | F06 | 5.6 interpolation callback 内 collective | `FIXED` |
| 11 | F07a | 5.7 QEP/Hybrid 异常清理 | `FIXED` |
| 12 | F07b | 5.7 遗留 full-size PETSc Vec | `FIXED` |
| 13 | F08a | 5.8 generic Floquet capability gate（不承载物理指纹） | `NOT_A_BUG/NO_CHANGE` |
| 14 | F08b | 5.8 material-wavelength consistency | `FIXED` |
| 15 | F09 | 5.9 无 coordinator 时的 heavy serial-only guard | `FIXED` |
| 16 | F10 | 5.10 local condensation fail-closed | `FIXED` |
| 17 | D01 | 2.3 Case098/099 documentation contract | `FIXED` |
| 18 | N01 | 2.4 PETSc complex `Vec.dot` 共轭语义 | `NOT_A_BUG/NO_CHANGE` |
| 19 | S01 | 9.1 modal Schur residual 的 `modal_rhs` | `FIXED` |
| 20 | S02 | 9.1 2D power metrics communicator | `FIXED` |
| 21 | S03 | 9.1 analytic reference identity | `FIXED` |
| 22 | S04 | 9.1 diffraction probe partition dependence | `FIXED` |
| 23 | S05 | 9.2 Full3D reference guard allocation order | `FIXED` |
| 24 | S06 | 9.2 boundary locator tolerance | `NOT_A_BUG/NO_CHANGE` |
| 25 | S07 | 9.2 historical/simultaneous memory labels | `ALREADY_FIXED` |
| 26 | S08 | 9.2 mode/power clipping and floors | `DEFERRED/ROADMAP` |
| 27 | S09 | 9.3 `check_benchmarks.py` 默认写入 | `FIXED` |
| 28 | S10 | 9.3 根目录 `run_demo*.sh` | `FIXED` |
| 29 | S11 | 9.3 runner 删除 caller output | `FIXED` |
| 30 | S12 | 9.3 benchmark runner 内数值核心 | `DEFERRED/ROADMAP` |
| 31 | S13 | 9.3 skip/source-text tests | `DEFERRED/ROADMAP` |
| 32 | A01 | 6.1 whole-domain direct Full3D | `DEFERRED/ROADMAP` |
| 33 | A02 | 6.2 direct Hybrid 数据布局 | `DEFERRED/ROADMAP` |
| 34 | A03 | 6.3 modal core 稠密/集中所有权 | `DEFERRED/ROADMAP` |
| 35 | A04 | 6.4 mesh/postprocess 复制与峰值 | `DEFERRED/ROADMAP` |
| 36 | A05 | 6.5 0.7 nm DtN order | `DEFERRED/ROADMAP` |
| 37 | A06 | M0 剩余项：并发 aggregate-memory coordinator | `DEFERRED/ROADMAP` |
| 38 | A07 | M1 冻结 0.7 nm 物理/材料合同 | `DEFERRED/ROADMAP` |
| 39 | A08 | M2 可选 2D/2.5D 诊断（不在 production 主链） | `DEFERRED/ROADMAP` |
| 40 | A09 | M3 缺失接口空间 | `DEFERRED/ROADMAP` |
| 41 | A10 | M4/P3 distributed streamed modal/QEP core | `DEFERRED/ROADMAP` |
| 42 | A11 | M5/P4 matrix-free strong-trace Hybrid iterative | `DEFERRED/ROADMAP` |
| 43 | A12 | M6/P5 scalable local h/p | `DEFERRED/ROADMAP` |
| 44 | A13 | M7/P6 wavelength continuation | `DEFERRED/ROADMAP` |
| 45 | A14 | 第 8 节 exact-byte resource authority（横向 Gate，非 M8） | `DEFERRED/ROADMAP` |

## 3. 逐项结论

本节按工作队列顺序记录。每项按适用性提供：最小 worktree diff 与 targeted behavior
test、无需改的源码/行为理由，或后续路线的触发条件与验证 Gate；`NO_CHANGE` 和
`ROADMAP` 不伪造实现 diff。

下文所有 `python -m pytest`、`mpiexec ... python -m pytest`、Ruff 和 compileall 命令均以
`source scripts/activate_myfenics_wsl.sh` 为前置，并使用已核验的 complex128/int32 ABI。
各处 pass/skip 数量是对应整改阶段的 targeted evidence，不是最终文档编辑后的 full
repository 回归；最终 Python worktree 的 consolidated post-edit regression 见本文末尾。

### F01a — 完整进程组终止

**结论：`FIXED`（POSIX/WSL scope）。** 先前结论只证明显式 memory/timeout stop 会终止
独立 process group，属于 premature `FIXED`：Task031、Task032、Task033 Full3D、Task033
memory 的 sampler loop 在普通异常或中断时仍可直接离开；Case090 只覆盖了
`KeyboardInterrupt`，普通异常仍会遗留 worker。共享 helper 的 process-group existence probe
与 `SIGTERM`/`SIGKILL` delivery 之间还存在自然退出竞态。

最小修改：

- 五个 launcher 各自在现有 `Popen`/sampling lifecycle 周围增加一个局部异常边界；worker
  仍存活时调用现有
  [`watchdog_process_control.py`](../../../benchmarks/watchdog_process_control.py) 清理，随后
  原异常原样抛出；cleanup 自身失败只附加到原异常，不能变成 solver pass；
- Case090 保留既有 `KeyboardInterrupt -> external_interrupt` 记录语义，并为普通异常补同一
  局部清理；没有增加 lifecycle framework、context manager 或状态机；
- helper 只在 `SIGTERM` 和 `SIGKILL` 两个 delivery 点窄捕获 `ProcessLookupError`，按进程组
  已自然消失继续 wait/final verification；其他 `OSError` 不被吞掉；
- 若 SIGKILL 后 worker 或进程组仍存在，helper 抛出错误，因而不能把不完整清理写成
  `controlled_stop`。

Targeted evidence：

```text
focused behavior = 5 passed in 1.53 s
  parent-alive + TERM-ignoring descendant -> TERM, grace, KILL, group gone
  leader-exited + TERM-ignoring descendant -> saved PGID cleanup, group gone
  SIGTERM delivery ProcessLookupError race -> final verification passes
  SIGKILL delivery ProcessLookupError race -> final verification passes
  Task031 actual worker-group fixture -> sampler RuntimeError and KeyboardInterrupt
    both remove leader + descendant and preserve the injected exception type
domain regression (test_30 + test_57 + test_59 + test_68) = 70 passed, 1 skipped
scoped Ruff = pass
scoped compileall = pass
git diff --check = pass
MPI/PDE = not_run (no collective or numerical operator changed)
```

完整进程组保证明确限定为 POSIX/WSL：`start_new_session=True` 使 leader PID 成为稳定 PGID，
因此即使 leader 先退出仍可验证 descendants。非 POSIX 分支仍是 psutil best effort；leader
退出后无法证明 descendants 已全部发现，未被提升为正式完整进程组保证。本轮不扩写 Windows
process supervisor。改动没有触及正常退出、memory threshold、timeout、return code、数值
solver、PDE 参数或普通数值 solver/backend default，也没有新增源码字符串测试。

### F01b — `/init.scope` 不得作为单 job authority

**结论：`FIXED`。** `_sample()` 已经记录 `mpi_process_tree_rss_mb`、cgroup path 和
`job_cgroup_dedicated`，但 Task031/032 的终止分支仍只读取
`container_cgroup_current_mb`。在 WSL `/init.scope` 下，该值包含同一发行版中的其他
作业，能导致当前 job 被误停。

最小修改是在 Task031 增加一个由 Task031/032 共用的判定函数：formal memory 为
`max(process-tree RSS, dedicated cgroup memory.current)`；非 dedicated 的
`/init.scope` 数值继续写入 timeline/summary，但只作诊断。没有改变 warning/terminate
阈值，也没有改动公共 WSL resource sampler。

Targeted evidence：

```text
before:
  test_f01b_global_init_scope_is_diagnostic_only = failed (helper absent;
  both launchers directly used global cgroup current)
after:
  test_30 Task031 contract = 15 passed (including F01b/F02 wrapper cases)
  Ruff (four touched Python files) = pass
  git diff --check = pass
```

测试同时证明：48 GiB 的 non-dedicated `/init.scope` 不覆盖 1 GiB process-tree
authority；相同数值若来自 dedicated job cgroup，则仍正确参与终止判断。

### F02a — workstation false-pass / exit code

**结论：`FIXED`。** 整改基线 `1f4e48a...` 中的 `qualified_profile` 只表示命令参数与历史 profile
一致，却直接决定 `status="pass"`；`main()` 又丢弃 `run()` 结果并无条件返回 0。
因此负 KSP reason、超限 explicit residual 或缺失 official RTA 都可能 false-pass。

最小修改：

- 增加纯函数 `_workstation_formal_qualification()`，只读取 runner 已经计算的
  `ksp_reason`、condensed/full explicit residual、R/T/A、能量闭合和 source-clean
  字段；
- 状态明确区分 `experimental_unqualified`、`source_identity_not_pass`、
  `numeric_not_pass`、`physics_not_pass` 和 `formal_pass`；
- 只有 `formal_pass` 才写 `official_rta`。其余已计算的量放在
  `diagnostic_rta`，并显式标记 `formal_gate=false`；
- `main()` 只在 `formal_pass` 时返回 0，其他状态返回 2。
- condensed/full true residual 与 energy closure 分别使用独立冻结的
  `1.0e-6`，不再跟随可配置的 `rta_threshold=1.1e-6`；后者只控制是否计算
  diagnostic RTA。删除没有冻结合同依据的额外
  `passive_power_nonnegative` 判据。

Targeted evidence：

```text
before:
  test_f02a_workstation_false_pass_is_rejected = failed (qualification/exit helper absent)
  code path: qualified profile alone wrote pass; main returned 0 unconditionally
after:
  test_29 WorkstationFormalQualification = 2 passed
  includes KSP failure, condensed/full residual failure, missing RTA,
  1.05e-6 true-residual failures, 1.05e-6 closure failure, and positive control
  Ruff = pass
  git diff --check = pass
```

测试中的负例具有 qualified 参数、低 residual 和完整 RTA，但 `ksp_reason=-3`；现在
确定得到 `numeric_not_pass` 和 exit 2。正 control 得到 `formal_pass` 和 exit 0。没有
改变 KSP、预条件器、容差或数值算子。

### F02b — Task031 screen-only 语义

**结论：`FIXED`。** 旧 wrapper 把 history 末端 residual 小于起点称为
`screen_pass`，再通过逻辑 OR 升级为 `numeric_pass`。这只证明迭代趋势变好，不能
证明 KSP 收敛、explicit residual 达标或 official RTA 存在。

最小修改是在原 wrapper 内集中现有字段的 disposition：

- screen-only 只可得到 `screen_trend_positive` 或 `screen_no_positive_trend`；即使
  worker 因非正式 screen 语义返回 rc=2，residual 改善趋势仍被保存；
- full run 不再建立第二套数值状态机，只转发 worker 的唯一 formal qualification；
- resource termination 单独为 `resource_controlled_stop`；
- worker rc 非零为 transport failure；`numeric_pass/formal_pass` 只在未被
  screen/resource disposition 覆盖且 worker 正式通过时为真。
- worker 已写出的 `numeric_not_pass`、`physics_not_pass` 或
  `source_identity_not_pass` 即使正常以 rc=2 退出也原样转发；只有 record
  缺失/不可识别的非零 rc 才归为 transport failure。

Targeted evidence：

```text
before:
  residual history 1.0 -> 0.9 and worker rc=0 was promoted to numeric_pass
  test_f02b_screen_trend_never_becomes_numeric_pass = failed (helper absent)
after:
  test_30 Task031 contract = 16 passed
  includes screen rc2 trend, resource stop overriding a stale worker pass,
  contradictory status/formal boolean fail-closed, and positive formal forwarding
  Ruff = pass
  git diff --check = pass
```

没有修改既有历史记录，也没有把 screen-only 结果删除；它仍作为趋势 evidence 保留，
但不再拥有数值通过或 exit-0 权限。

### F03 — `A_volume` 缺失与 partial sum

**结论：`FIXED`。** 原实现先把缺失 region 的 `A_volume=None` 过滤，再对剩余值求和，
所以两侧都缺失会得到 `status=ok, A_volume_total=0.0`，一侧缺失则把 partial sum
冒充 total。incident power 和 NaN/Inf 也没有形成 top-level failure。

最小修改：

- 在 `rta_3d.py` 增加纯 aggregation contract，不改变任何 UFL 积分公式；
- required region 由实际几何决定：block grating 要求实际存在的 grating，物理界面
  下存在 substrate 时要求 substrate；flat layer 不把预期不存在的 grating 误判为错；
- required region 缺失、任一 present absorption 缺失/非有限，或 incident power
  非有限/非正时，写 `status=invalid`、`official_result=false`、
  `A_volume_total=null` 和具体 failures；可观测 partial 只放在明确命名的
  `A_volume_partial_sum`，不进入 closure；
- DtN merge 仅接受 `status=ok`、`official_result=true` 且 R/T/A 全有限的 volume；
- public `compute_volume_absorption_3d()` 即使 `incident_power=None` 也生成非 ok
  payload，而不是在 `float(None)` 或区域归一化处崩溃；failure reason 去重，不把
  无效 incident power 的派生 `A_volume=None` 重复记成区域故障；
- Stage-4 summary 对缺失或 invalid volume 降级为
  `failed_volume_absorption_contract`；workstation RTA 同样不再对 `None` 做零填充。

Targeted evidence：

```text
before:
  test_f03_volume_absorption_rejects_missing_and_partial_regions = failed
  both missing -> ok/0.0; one missing -> partial total
after:
  test_11_stage4_diffraction_modes = 18 passed
  Ruff = pass
  git diff --check = pass
```

测试通过 public API 覆盖 `incident_power=None/NaN/0/negative`、block/flat
required-region mapping、both-regions-missing、NaN absorption、required missing 的
单一 failure reason 以及 summary official-result 降级。没有新增
负吸收政策。该补丁只收紧 evidence/official-result 合同，
不改变已具备完整材料 tag 的历史数值路径。

### F04 — QEP requested/actual provenance

**结论：`FIXED`。** 原 QEP 先请求 TOAR/SINVERT/PREONLY/LU/MUMPS，随后调用
`setFromOptions()`；全局 options 可覆盖请求值，但 report 仍硬编码原请求，产生错误
provenance。

最小修改：

- 将当前冻结的 QEP profile 写成一份常量，仅用于 requested/actual 比较；
- `setFromOptions()` 后通过 SLEPc/PETSc getter 读取实际 PEP problem/type、ST、KSP、
  PC 和 factor solver；非 factor PC 不调用 factor getter；
- 通用 QEP core 默认保留 override 并记录每个 mismatch，不再无条件拒绝合法的
  PETSc/SLEPc options；冻结的 formal/clean evidence caller 才在 `pep.solve()` 前
  fail closed；
- `QuadraticBetaSolveReport.profile_provenance()` 固定输出 `requested`、`actual`、
  `profile_match`、`mismatches` 四个字段。Phase2/3/5/6、Task033 与 Task036 runner
  直接复用这一小方法，不再各自手写 serializer；旧
  `solver/problem_type/spectral_transform` 字段由 actual profile 派生；
- formal-callsite 全仓核验结果：Phase2 right-only；Phase3 material positive/negative
  与 angle tracking；Phase5 stage4/near-degenerate；Phase6 positive/negative；Task033
  matched trace/QEP matrix；Task036 one-cell 的 right QEP 均显式
  `strict_profile=True`，所有实际构造的 adjoint basis 均显式
  `strict_qep_profile=True`。Phase3 angle tracking 不再丢弃 right report；各原有 record
  均保存 right/adjoint profile；
- Phase6 finite-capacity 早停只保存停止前实际完成的 report：positive 早停只有
  positive-right；negative 早停另有已完成的 positive right/adjoint 与 negative-right。
  这避免把未运行的 adjoint 写成证据。

Targeted evidence：

```text
before:
  test_f04_qep_requested_and_actual_profiles_are_distinct = failed
  report fields were hard-coded after setFromOptions
after:
  real COMM_SELF PETSc options override drives setFromOptions = pass
  pre-solve non-strict capture records linear/shift/gmres/jacobi actual profile = pass
  strict formal path rejects the same actual override before solve = pass
  complete non-strict qarnoldi solve converges and QuadraticBetaSolveReport
    derives legacy solver identity from actual profile = pass
  test_32 + test_33 = 30 passed
  Task033/Task036 related suites = 40 passed
  Phase6 light targeted regression = 4 passed
  Ruff / compileall / git diff --check = pass
```

测试不再以手造 dict 代替 `setFromOptions()` 行为；其中 qarnoldi 用例执行完整
`solve_quadratic_beta_modes()` 并检查实际 `QuadraticBetaSolveReport`。此项只校验和记录 solver 身份，
不改变 QEP operators、target、tolerance、mode ordering 或 normalization；实际
QEP/PDE 不因 provenance 修复重跑。

### F05a — 无可验证身份的 existing artifact 安全拒绝

**结论：`FIXED`（安全拒绝，而非实现通用复用器）。** 原 dispatcher 只要发现
`run_dir` 已存在就返回 `existing_artifact_not_rerun`；上层仅把字面 `failed` 当失败，
因此空目录、残缺目录或旧源码结果都能绕过实际命令。

本轮没有依据建立新的 artifact schema/receipt/hash 框架。最小补丁把任何 existing
run directory 统一返回：

```text
status = failed
failure_kind = existing_artifact_requires_validation
```

因此 batch 会立即 fail closed。用户可以保留旧 artifact，但必须选择新的输出目录；
未来若授权复用，需由独立 validator 同时检查 schema、source、input、command、正式
status 和 raw hashes。

Targeted evidence：

```text
before:
  empty existing directory -> existing_artifact_not_rerun (not treated as failure)
  test_task036_existing_artifact_fails_closed = failed
after:
  Task036 existing-artifact targeted test = 1 passed
  Ruff / git diff --check = pass
```

改动只有原 existing-directory 返回分支，没有触碰 command、PDE、扫描点或历史目录。

### F05b — 原子输出目录

**结论：`FIXED`。** 原子成功路径保持不变：`unique_run_dir()` 用
`mkdir(exist_ok=False)` 将选名与认领合并，只有 `FileExistsError` 才递增原有编号重试；
`enabled=False` 仍直接返回显式共享目录且不创建它。

先前结论属于 premature `FIXED`，但六个入口的历史形态分为两类：

- `run_3d_cases`、`run_cases`、`run_3d_airbox_old` 和 `stage4_2p5d_compare` 原本就是
  rank 0 调 `unique_run_dir()` 后广播；原子 mkdir 若因 permission、read-only filesystem
  或其他可恢复 I/O error 抛出，非 root 会永久等待；
- `run_grating_manual` 和 `run_grating_mpc_official` 原本由所有 rank 各自调用
  `unique_run_dir()`；先前原子认领修复会让不同 rank 分流到不同新目录，因此中间整改先将
  它们改为 rank0+bcast，而该中间形态同样存在 rank0 mkdir 在广播前抛出的缺口。

本轮 shared helper 同时收口这两类入口。

最小补丁在 `output_paths.py` 增加一个小型 `shared_unique_run_dir()`：

- rank 0 仍调用原 `unique_run_dir()`，不回退原子认领；
- 只在该 rank-0 目录选择调用周围捕获 `Exception`，把成功 path 或原异常 type/message
  组成的小 payload 广播；
- 所有 rank 在广播后对失败共同抛出文本完全相同的 `RuntimeError`，失败不被吞掉或改写为
  成功；
- `run_3d_cases`、`run_cases`、`run_3d_airbox_old`、`run_grating_manual`、
  `run_grating_mpc_official` 和诊断入口 `stage4_2p5d_compare` 复用该 helper。

没有新增 lock service、retry framework、exception registry、MPI abort、barrier、fallback、
目录事务状态机或 `/tmp` 自动切换；普通单进程调用仍直接使用 `unique_run_dir()`。

Targeted evidence：

```text
before:
  four existing rank0+bcast entries: rank0 mkdir OSError -> non-root blocked
  two all-rank grating entries: atomic claims split ranks across different directories;
    intermediate rank0+bcast fix retained the same pre-broadcast OSError gap
after:
  两次调用分别原子占用 case_... 与 case_..._02
  serial atomic-claim regression = 1 passed in 0.50 s
  MPI2 root-OSError + success + enabled=False behavior = 1 passed per rank
    rank0 injected OSError -> both ranks receive identical RuntimeError text
    success -> both ranks receive the same path and observe the claimed directory
    enabled=False -> both ranks receive the explicit path and no directory is created
  scoped Ruff = pass
  scoped compileall = pass
  git diff --check = pass
  solver/PDE = not_run
```

边界保持窄：测试注入可恢复的 rank0 `OSError`，未模拟 rank0 被强杀、MPI communicator/bcast
自身失败或非共享文件系统；这些情形无法由同一次健康广播协议解决，且本轮未授权 MPI abort
或容错运行时。改动未改变 solver、输入参数、结果内容或任何既有 artifact。

### F05c — source attestation

**结论：`FIXED`。** 先前的 `FIXED` 判定对 workstation runner 自身输出造成的
source-attestation 污染收口过早；本轮仅补齐这一窄缺口。两条旧路径都存在“外部声明
覆盖本地事实”的同一缺陷，但补丁分别留在原入口内，没有新增通用 provenance 框架：

- Task031 恢复并保留重型 PDE 前的严格 preflight：Git capture 失败、verified SHA
  格式错误或与 mounted HEAD 不符立即停止；dirty 只有显式
  `--allow-dirty-research` 才能运行，且永不 formal；
- workstation worker 仅 rank 0 抓 Git snapshot，再 broadcast 给所有 rank。
  `BENCHMARK_COMMIT_SHA` 与 `BENCHMARK_VERIFIED_CLEAN_SHA` 都只是待核对的
  attestation；broadcast 后所有 rank 在 PDE assembly 前一致检查 capture、SHA 格式和
  mounted HEAD match，不设置 branch-name Gate。dirty 仍可作为 diagnostic 运行，但
  不能取得 formal 身份。原有 `git_dirty`、
  `tracked_source_dirty`、`tracked_source_verification` 以及 top-level
  container/image/host/kernel/Python/NumPy 字段键保持兼容；既有本地枚举的错误值按下文
  纠正，其余变化只增量添加新字段；
- Task031 watchdog 与 workstation worker 都在数值 solve/RTA 完成后、最终 record 写入前
  保存 end snapshot。只有 HEAD 保持相同、capture 可读、start 完整工作树 clean 且 end
  在下述 exact owned-output 排除范围外 clean 时，`source_identity_stable=true`；漂移分类为
  `controlled_negative_source_identity`；
- workstation 的 start snapshot 始终检查完整工作树且排除清单为空；end snapshot 才用
  Git `top+literal+exclude` pathspec 精确排除本次 runner 明确拥有的四个 sibling 文件：
  final record、`_parameters.json`、`_progress.json` 和 `_memory_stages.jsonl`。只有位于
  repository root 内的 exact path 才进入排除，仓库外输出不会生成 pathspec；不排除父目录、
  glob、其他 untracked 文件或无关源码。若 owned 文件在 start 已经 dirty，完整 start
  snapshot 仍使最终 identity fail closed；若 end 另有无关 tracked/untracked 变化也仍失败；
- metadata 显式保存 `git_status_scope` 与
  `git_status_excluded_runner_owned_paths`：start 为 `full_repository` 和 `[]`，end 为
  `repository_except_exact_runner_outputs` 和四个仓库相对 exact paths。因此 end 的
  `git_dirty=false` 可审计地表示 scoped clean，不能被误读为未排除任何路径的完整工作树
  clean。若 rank 0 解析 owned path 时遇到 `OSError`/`RuntimeError`，该路径不进入排除、
  不使用 fallback，并以 `runner_owned_path_capture_ok=false`、
  `source_capture_ok=false` 和 unqualified provenance 返回可广播 metadata，避免非 root
  留在 broadcast；仓外路径的 `ValueError` 仍表示 Git status 本来不可见而正常跳过；
- 未使用 host attestation 时，兼容字段 `tracked_source_verification` 记录仓库已有枚举
  `local_git_status`；此前的 `git_status_untracked_files_no` 与实际
  `--untracked-files=all` 命令矛盾，现已纠正。精确 status scope 与 exclusions 仍由上述
  新字段独立表达；
- source failure 只取消 formal/official 权限；Task031 从真实 worker record 转发
  `numeric_solver_pass` 与 `physics_pass`，保留 residual 和 diagnostic RTA；
- worker 保存 canonical `input_config_sha256` 以及 host/container/kernel/Python/NumPy/
  PETSc scalar/int 组成的 environment identity；start/end environment identity 参与稳定性
  Gate。同一份已解析 resolved config 在开始与结束各重算一次 canonical hash，并比较
  `input_config_stable`；这只是运行输入绑定，不 reload 配置文件，也不新增 schema/receipt；
- provenance 只在 measured clean 且 attestation 相符时写 `clean_rerun`，否则写
  `runtime_git_capture_unqualified`。
- Task036 当前正式 watchdog 已具有 start/end HEAD、tracked dirty 和输入 identity
  检查；F05a 已同时关闭未验证 existing artifact 绕过，因此没有重复修改该路径。

Targeted evidence：

```text
before:
  verified SHA could mask real dirty status
  worker lacked end snapshot and input/environment binding
  source identity stability helper absent
after:
  Task031 invalid/mismatched/dirty-default preflight stops before heavy PDE
  workstation snapshot diagnoses SHA mismatch and preflight stops before PDE assembly
  workstation start attestation mismatch stops before PDE assembly
  HEAD/dirty change makes source_identity_stable=false
  environment identity change makes source_identity_stable=false
  dirty end snapshot rewrites top-level provenance to runtime_git_capture_unqualified
  resolved-input hash drift makes input_config_stable=false and blocks formal status
  non-root rank receives broadcast without querying Git
  real controlled-negative worker record keeps numeric/physics pass but blocks formal
  canonical input hash is order-independent and input-sensitive
  start metadata records an empty exclusion list and uses unscoped status
  end metadata records exactly four literal runner-owned relative paths
  tracked/untracked owned outputs alone remain source_identity_stable=true
  dirty owned output at start or unrelated src/other.py at end remains unstable
  spaces and Git-special characters in owned filenames are matched literally
  owned-path resolution OSError returns broadcastable fail-closed metadata
  start metadata labels the measured status as local_git_status
  F05c self-output targeted = 3 passed; source-metadata class = 10 passed
  test_29 targeted = 10 passed; test_30 = 20 passed
  Ruff / compileall / git diff --check = pass
```

本项只改变正式资格判定与 provenance 字段；线性算子、迭代算法、PDE 参数和历史
artifact 均未改变，因此没有运行重型 PDE。

### F06 — interpolation callback 内 collective

**结论：`FIXED`。** 先前的 `FIXED` 只资格化了 zero-local-cell 成功路径，未覆盖 rank-local
异常发生在相邻 MPI collective 之间的分叉风险，因而判定过早。旧
`extract_tangential_trace()` 把
`_DistributedTangentialEvaluator` 直接交给 DOLFINx `interpolate()`；该 callback 内的
point ownership 和 `alltoall` 要求所有 rank 同时进入，但 DOLFINx 可以在零 local
trace-cell 的 rank 上跳过 callback。

最小补丁照仓库现有 `_ReusableInterfaceLifter` 的已验证模式迁移，没有抽象出新框架：

1. 每个 rank 先从同一 trace space/cell 集合显式取得 interpolation coordinates；
2. 所有 rank 显式调用 `evaluate_points()`，在 callback 外完成 distributed ownership
   与 `alltoall`；空点集合也参与；
3. `trace.interpolate()` 只调用 local `cached_values()`，其中没有 MPI collective；
4. 保留坐标一致性检查，避免 DOLFINx 在两步之间静默改变点顺序。

本轮在同一模块内增加一个窄 private helper：各 rank 对普通 local `Exception` 编码
type/message，使用实际 `source_mesh.comm` 做一次 `allgather`，按最低失败 rank 选择并让
所有 rank 抛出文本完全相同的 `RuntimeError`。它只用于四个明确边界：

1. coordinate normalization/validation 完成后、进入
   `determine_point_ownership()` 前；
2. ownership 后的 conversion、unresolved、source evaluation 与 send preparation
   完成后、进入 `alltoall()` 前；
3. `alltoall()` 后的 bytes accounting、owner-index/count/order reconstruction 完成后、
   `evaluate_points()` 返回前；
4. local `trace.interpolate(cached_values, trace_cells)` 完成后、
   `scatter_forward()` 前，原有 cached-coordinate correctness check 保留在此边界内。

本补丁不捕获 `BaseException`，也不承诺从 rank hard-kill、communicator failure 或
DOLFINx/PETSc/MPI collective 内部异常恢复；这些情形无法靠下一次 `allgather` 协调，需要
外层 watchdog/process-group authority。没有增加 barrier、MPI abort、timeout、retry、
fallback 或通用 MPI 状态机。

Targeted evidence：

```text
before:
  existing MPI4 fixture distributed trace cells as [4,5,4,5]
  so it did not exercise the zero-local-cell collective hazard
  trace.interpolate(evaluator, trace_cells) remained active
after:
  source-string/inspect test removed
  real 1x1 quad p1 fixture has MPI2 local cells [0,1]
  real 1x1 quad p1 fixture has MPI4 local cells [0,0,1,0]
  bottom and top extraction both complete on MPI2 and MPI4
  zero-cell ranks issue zero queries; global queries equal evaluations
  unresolved points = 0; distributed affine error <= 1e-11
  MPI2 unresolved + local-interpolate failure paths = 2 passed per rank
  both MPI2 ranks receive the same RuntimeError type/full message and exit normally
  MPI2 zero-local success regression = 1 passed per rank
  MPI4 zero-local success regression = 1 passed per rank
  serial orientation + affine trace regression = 2 passed
  Ruff / compileall / git diff --check = pass
```

该函数仍只被旧 Task032/033/036 research runners 调用；新版 Hybrid lifter 原本已采用
安全模式。本项没有改变 trace 空间、Piola 映射、Floquet orientation 或投影公式。

### F07a — QEP/Hybrid 异常清理

**结论：`FIXED`。** 本项没有加入 rollback manager、对象 registry 或通用状态机；
每个 solver 只在实际拥有 PETSc/SLEPc 对象的函数内建立局部所有权边界。创建后的对象
先由局部变量拥有，返回 dataclass 构造完成后才转移；异常时只清理已经成功创建的对象，
并重新抛出原异常。

覆盖的真实路径如下：

- QEP：partial full/reduced operator assembly 形成单一事务边界；polynomial residual 的
  第二个 Vec 创建失败时释放第一个；第二个 mode expansion 失败时同时释放当前 partial
  mode 和先前完整 mode。若 `pep.solve()` 的主 PETSc Error 91 后 `pep.destroy()` 又报
  Error 58，主异常和 traceback 保持不变，cleanup error 只通过 exception note 附加；
  成功路径若单独 cleanup 失败仍照常抛出。
- augmented direct：KSP setup、linear solve、explicit residual、layout split 和 bottom/
  top static recovery 失败时释放已创建的 KSP、monolithic Vec 与 local Vec；成功
  solution 销毁时清空 recovered owner 引用，但不直接销毁
  `Function.x.petsc_vec`。
- modal Schur：MUMPS/KSP setup 失败释放 KSP；modal action、local recovery 和 residual
  的 partial Vec 由一个 solve ownership envelope 反序释放；top recovery、residual 或
  static top recovery 失败时清理 bottom/top Vec，并清空已经构造的 recovered owner；
  `_local_schur_response()` 的 dense multi-RHS `matSolve` 也位于同一个局部 ownership
  边界内，失败时恰好释放 RHS 与 solved Mat。
- strong trace：只修报告证据对应的三个 helper 边界：modal Vec 成功而 trace Vec 创建
  失败、modal `Mat.mult` 失败、strong residual 分批创建 partial Vec/Mat 失败；static top
  recovery 同样清空 bottom recovered owner，successful solution destroy 清空两侧 owner。
- 共用 static recovery：第二个 modal/reduction Vec 创建失败时释放第一个；full/reduced
  RHS 与 internal action 在返回前保持局部 ownership；surface component 的第二个 full
  Vec 构造失败时释放第一个。

Targeted evidence：

```text
before:
  real small QEP: pep.solve PETSc Error 91 was replaced by pep.destroy Error 58
  Schur MUMPS/KSP setup failure: KSP destroy count = 0
  Schur multi-RHS matSolve failure: RHS Mat destroy = 0; solved Mat destroy = 0
  strong modal Mat.mult failure: result Vec destroy count = 0
  bottom static recovery success + top failure retained the bottom owner in traceback
after:
  QEP representative ownership tests = 4 passed
    partial full/reduced assembly; second residual Vec; solve+cleanup dual error;
    second-mode expansion rollback
  augmented/Schur/static/strong ownership tests = 10 passed
    setup/solve; top/residual; static top; partial reduction; three strong helpers;
    successful solution owner release; multi-RHS matSolve rollback
  combined representative F07 ownership node set = 14 passed
  related light domain suites (test32/test196/test28/test14) = 58 passed
  test215 contains no F07/F07b test; tests live in their domain files
  Ruff / compileall / git diff --check = pass
```

成功路径仍返回原 dataclass 和原 physical fields；本项没有改变矩阵、求解配置、残差
公式或结果 Gate，也没有运行正式 PDE。测试只覆盖报告点名的典型 ownership 边界，
没有枚举每个 PETSc setter，也没有扩建“任意 API 调用都强异常安全”的框架。

### F07b — 遗留 full-size PETSc Vec

**结论：`FIXED`。** 报告点名的两个位置实际对应三个只用于诊断的临时量：

- `common_3d_solve._assembled_rhs_norm()` 的 unconstrained RHS Vec；
- `common_3d_solve._linear_system_diagnostics()` 的 full residual Vec；
- `dtn_port_3d._linear_residual()` 的 augmented residual Vec。

它们都只在函数内部读取 norm，不属于返回结果。最小补丁为各函数增加局部
`finally`，无论 norm/matvec 成功或抛出异常都立即销毁；没有改变返回字段或异常时原有
`None` 语义。

Targeted evidence：

```text
before:
  successful diagnostic path returned without Vec.destroy()
  test_f07b_full_size_diagnostic_vectors_are_destroyed = failed
after:
  all three temporary Vec objects are destroyed exactly once
  common diagnostic Mat.mult exception also destroys its residual exactly once
  tests migrated to test28 and test14; test215 contains no F07b test
  related light domain suites (test32/test196/test28/test14) = 58 passed
  Ruff / compileall / git diff --check = pass
```

这只缩短诊断临时量生命周期，不改变 Full3D/DtN 矩阵、solution Vec 或 observable。

### F08a — fixed-target fingerprint

**结论：`NOT_A_BUG/NO_CHANGE`。** 报告指出“完整物理身份不能只由
`stage_case + geometry_kind` 资格化”是正确的，但把完整物理 fingerprint 放入 generic
Floquet constraint dispatcher 属于 wrong ownership。该 dispatcher 只判断某个
degree/topology/geometry 是否有可用的 periodic constraint builder；它不宣称材料、波长、
网格轴、配置或正式 run 已通过物理资格。

因此撤销未完成审阅时加入的 Task036 rectangular-family 连续范围白名单：删除材料常量
imports 和 `_is_qualified_task036_rectangular_target()`，恢复原 generic
topology/geometry capability dispatch。源码只增加一条注释，明确 capability gate 不等于
physical-target qualification。没有把相同白名单复制到 builder，也没有保留 lookalike
source-shape 测试。

Targeted evidence：

```text
  existing test46 remains the authority for generic/high-order Floquet topology
  test27 + test46 + test197 = 32 passed, 0 skipped
  Ruff / compileall / git diff --check = pass
```

完整 canonical target identity 不是在此处“无需解决”；它转入 A07/M1，保持 fail-closed
延期，不能由 generic Floquet capability 自动获得正式资格。

### F08b — known-13.5 material/wavelength guard

**结论：`FIXED`（仅限 active-region known-13.5 mismatch guard）。** 当前仓库只有一组
命名的 13.5 nm Si label/index 常量。最小 guard 只防止这组已知身份被拆开或换波长误用：

- substrate 仅在 substrate 几何实际存在时检查；grating 仅在
  `has_grating_block` 时检查；纯 airbox 返回 `not_applicable`，不检查 `n_air`；
- 已知 label 与已知 complex index 必须双向成对，任一方单独出现都失败；
- 活动区域中任一已知 label/index 出现在非 13.5 nm 时失败；
- 全部活动区域均为完整已知 pair 时返回 `known_material_consistent`；其他合法 custom
  数据只在 `validation_role=numerical_sanity_only` 时返回
  `custom_material_unverified`；若活动 custom 区域请求 physical/formal role，则在 PDE
  前 fail closed；`not_applicable` 不受此限制。

`SimulationConfig3D.as_jsonable()` 不再调用 validator，也不增加 material-consistency
字段，因此 diagnostic config 仍可序列化，既有 normalized config hash 不因本轮 guard
改变。统一 solver 入口只在 mesh/PDE 前调用 validator 一次并记录状态；没有新增 material
registry、schema、状态机或空 provenance 字段。

Targeted evidence：

```text
  canonical 13.5 target = known_material_consistent
  known 13.5 identity at 0.7 nm = rejected before PDE
  known label + wrong index = rejected
  known index + wrong label = rejected
  inactive grating mismatch = ignored
  custom 0.7 config = JSON serializable + custom_material_unverified
  active custom 0.7 + physical benchmark role = rejected before PDE
  airbox with no active Si region = not_applicable
  test27 + test46 + test197 = 32 passed, 0 skipped
  Ruff / compileall / git diff --check = pass
```

### F09 — heavy dispatcher safe guard

**结论：`FIXED`（当前 heavy dispatcher guard）。** Task036 dispatcher 只有 per-job
CPU lease 和 per-job watchdog，没有共享 cgroup/job-group memory authority。只限制每个
worker 的资源不能阻止多个 worker 的同时峰值超过整机预算，因此在 aggregate coordinator
完成前，真实 heavy dispatch 必须串行。

最小修改为一个纯 policy helper，合并原有 `max_parallel in [1,5]` 检查与运行模式约束：

- 非 dry-run 只允许 `max_parallel=1`；
- dry-run 仍允许 1--5，用于冻结和检查计划，但不启动 job；
- `main()` 在参数解析后立即调用该 helper，位于任何 `_git()`、points/artifact 读取、
  CPU lease 或 job 启动之前，非法真实并行因而 fail closed。

没有修改 `_run_batch()`、CPU affinity lease、watchdog 或 worker 命令；没有新增 aggregate
memory 参数、预测、host RSS polling、队列或调度器。

Targeted evidence：

```text
  non-dry max_parallel=2 = rejected
  non-dry max_parallel=1 = allowed
  dry-run max_parallel=5 = allowed
  test197 = 12 passed
  scoped Ruff / compileall / git diff --check = pass
```

### F10 — local static condensation fail-closed

**结论：`FIXED`（只限 assembly-time fixed-p 与 variable-p 两条 production 构建
路径）。** 两条路径原先都直接调用 `lu_factor/lu_solve`。某一 rank 的局部 LU 失败时，
fixed-p 的其他 rank 会进入下一次 `Barrier`，variable-p 的其他 rank 会进入
`Mat.assemble()`；失败 rank 也不会释放已经创建的 PETSc matrix。variable-p 原有的
primal/adjoint residual Gate 又位于 matrix assembly 之后，无法在构建期阻断坏局部
recovery map。

最小修改：

- 在 `hcurl_assembly_time_condensation.py` 增加唯一共享私有 helper
  `_checked_local_static_condensation()`，由 variable-p 直接复用；
- helper 只检查四个输入、LU、primal/adjoint recovery map、trace map 与 Schur 的
  finite 状态；将 SciPy `LinAlgWarning` 提升为异常；
- primal `X=-Aii^-1 Ait` 和 adjoint `Aii^H Y=Ati^H` 使用同一个冻结的
  `5.0e-11` normwise backward-residual Gate；Schur 公式仍为
  `A_tt + A_ti @ X`；
- `pivot_ratio=min(abs(diag(U)))/max(abs(diag(U)))` 只写入趋势 telemetry，不设
  threshold，不计算 condition number、SVD、determinant 或 inverse norm，也没有
  fallback、pinv 或 regularization；
- 两个 cell loop 都只捕获 helper 调用本身的异常，并在下一 collective 之前
  `allgather`。任一 rank 失败时，所有 rank 释放当前 PETSc matrix，再按 rank 顺序抛出
  完全相同的错误；projection、orientation、`setValues` 等 API 没有增加包装层；
- fixed-p build audit 新增 primal/adjoint residual max 与 pivot-ratio min；variable-p
  复用原有两个 residual 字段并新增 pivot-ratio min。

Targeted evidence：

```text
pure synthetic helper:
  command: python -m pytest -q \
    src/test/test_115_task035b_assembly_time_condensation.py::TestTask035bAssemblyTimeCondensation::test_checked_local_condensation_matches_direct_complex_schur \
    src/test/test_115_task035b_assembly_time_condensation.py::TestTask035bAssemblyTimeCondensation::test_checked_local_condensation_rejects_singular_and_nonfinite \
    src/test/test_115_task035b_assembly_time_condensation.py::TestTask035bAssemblyTimeCondensation::test_checked_local_condensation_uses_one_gate_for_both_maps
  result: 3 passed, 0 skipped in 2.35s; no warning
  coverage: non-Hermitian complex direct Schur/maps; exact singular;
    non-finite input/solve output; same 5e-11 primal/adjoint Gate;
    worsening pivot ratio remains diagnostic and does not reject the solve

existing success fixtures:
  command: python -m pytest -q \
    src/test/test_115_task035b_assembly_time_condensation.py::TestTask035bAssemblyTimeCondensation::test_fixed_p5_trace_p6_interior_kernel_condenses_exactly \
    src/test/test_185_task035d_variable_p_petsc_assembly.py::Task035dVariablePPETScAssemblyTests::test_single_cell_uniform_p6_degenerates_to_direct_schur
  result: 2 passed, 0 skipped in 107.34s
  coverage: fixed p5-trace/p6-interior and variable-p direct Schur identity;
    all three new/existing audit fields finite and residuals <=5e-11

MPI2 collective failure fixtures:
  command: mpiexec -n 2 python -m pytest -q \
    src/test/test_115_task035b_assembly_time_condensation.py::TestTask035bAssemblyTimeCondensation::test_mpi2_local_condensation_failure_releases_matrix \
    src/test/test_185_task035d_variable_p_petsc_assembly.py::Task035dVariablePPETScAssemblyTests::test_mpi2_local_condensation_failure_releases_matrix
  result: 2 passed, 0 skipped per rank in 19.26s max
  coverage: rank 0 helper failure; identical exception on both ranks;
    no Barrier/Mat.assemble hang; both ranks observe destroyed matrix handle=0

scoped Ruff / compileall / git diff --check: pass
heavy PDE / MUMPS: not run
```

没有修改 legacy `hcurl_cell_static_condensation.py`、fixture-only
`hcurl_variable_p_local.py`、后续 field recovery、Schur bilinear API、
`_iteratively_refined_lu_solve`、solver tolerance 或 ordinary backend。

#### Calibrated 0.7 nm condition cutoff

**后续路线/尚未校准项。** 当前没有 0.7 nm 材料 authority、正式样本分布或可据以
校准 local-block condition cutoff 的证据。`pivot_ratio` 因此严格保持 diagnostic-only；
本轮没有臆造硬 floor。未来只有在冻结 0.7 nm 物理合同并取得代表性 local-block
统计后，才能在独立任务中决定是否需要 condition Gate。

### D01 — Case098/099 documentation contract

**结论：`FIXED`。** 本轮整改前的 test26 把 `benchmarks/cases/` 下所有目录都当作
已登记 case，因此本地被忽略的 Case098 `__pycache__` 残留也进入 `observed`；与此同时，
tracked Case099 没有适合其 evidence-only 身份的分类。补丁前现有节点真实失败并同时报告：

```text
Items in the first set but not the second:
  098_reference_blind_multilevel_hp_adaptivity
  099_strong_trace_hybrid_fixture
```

事实核验：`git ls-files benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity`
为空，目录中只有两个 ignored `__pycache__/*.pyc`；Case099 则 tracked 一个 README 和
三个 records，且 README 明确声明“不是 production benchmark”。

最小修改：

- test26 把含任意非 `__pycache__` 条目的编号目录纳入 `observed`：当前仅含缓存的
  Case098 被忽略，但未来有真实内容却缺 README 的 case 仍会使合同失败；不需要解析
  `.gitignore`、调用 Git subprocess 或删除本地缓存；
- 增加窄集合
  `EVIDENCE_ONLY_FIXTURE_CASES={"099_strong_trace_hybrid_fixture"}`；Case099 只检查
  README 文件和 records 目录存在，不要求或伪造 config、expected、runner；
- `benchmarks/cases/README.md` 仅补 Case097 与 Case099 两行，分别标为
  `research partial with controlled negatives` 和
  `evidence-only fixture; not production benchmark`；表后 22 项合同明确只适用于
  qualified、recorded 和 active-research cases，evidence-only fixture 使用窄证据合同；
  没有登记 Case098。

Targeted evidence：

```text
before:
  python -m pytest -q \
    src/test/test_26_documentation_contract.py::DocumentationContractTests::test_numbered_benchmark_cases_use_case_contained_contracts
  result: 1 failed; observed-only Case098 and Case099

after targeted:
  same command
  result: 1 passed, 0 skipped in 0.03s

after whole domain file:
  python -m pytest -q src/test/test_26_documentation_contract.py
  result: 14 passed, 0 skipped in 0.07s

scoped Ruff / compileall / git diff --check: pass
```

没有恢复 Case098、创建占位文件、删除 ignored 缓存、把 Case099 提升为 active/qualified，
也没有引入目录治理框架。

### N01 — PETSc complex `Vec.dot` conjugation

**结论：`NOT_A_BUG/NO_CHANGE`。** `run_workstation_iterative.py` 的 fixed Floquet
coarse-basis Gram--Schmidt 当前使用：

```python
vector.axpy(-np.conjugate(accepted.dot(vector)), accepted)
```

在本仓库资格化的 complex128 petsc4py ABI 中，方法调用
`accepted.dot(vector)` 返回 `vector^H accepted`；外层 `conjugate` 后才得到投影需要的
`accepted^H vector`。因此当前 AXPY 从 `vector` 中减去正确的复投影。删除这层共轭会在
一般复相位下使用错误系数。

一次性轻量复现（未创建持久测试）使用已归一化的两元素复向量，结果为：

```text
PETSc.ScalarType=complex128
accepted.dot(vector)=(-1.7881186820378094+3.973597071195132j)
vector^H accepted=(-1.7881186820378094+3.973597071195132j)
accepted^H vector=(-1.7881186820378094-3.973597071195132j)
conjugate(dot)=(-1.7881186820378094-3.973597071195132j)
matches_vector_H_accepted=True
conjugate_matches_accepted_H_vector=True
post_axpy_accepted_H_trial=(5.134781488891349e-16+5.551115123125783e-16j)
post_axpy_orthogonal=True
```

所以本项没有修改 `run_workstation_iterative.py`，也没有增加 PETSc 版本分支、runtime
探测、fallback、二次正交化或新的容差/相位框架。D01/N01 scoped Ruff、compileall 和
`git diff --check` 均通过。

### S01 — modal Schur residual RHS correction

**结论：`FIXED`。** `_modal_residual()` 原来只计算 bottom/top FE projection 加
`modal_constraint @ modal`，没有减去构建 modal 方程时存在的原始 cell-interior
elimination RHS correction。因此非零 correction 即使被左端精确平衡，也会报告非零
modal residual。F07 只修复该函数及其调用路径的 PETSc ownership/lifecycle，没有覆盖
本项代数公式。

最小修改严格局限于 `_modal_residual()`：

- 保留 bottom/top projection、`try/finally` 和 Vec 销毁顺序不变；
- 明确计算 `modal_constraint_action` 和
  `left_hand_side = projected_bottom/top + modal_constraint_action`；
- 使用 `rhs_correction = internal_modal_rhs_correction(coupling)`，再计算
  `residual = left_hand_side - rhs_correction`；
- 绝对残差为 `norm(residual)`；相对尺度为 left-hand side、原始 RHS correction、
  modal constraint action 三者 norm 的最大值及 `1e-30`；
- 没有使用 `system.modal_rhs`。后者是包含 `-D A^-1 b` 的消元后 Schur RHS，在这里减去
  会重复计算。

补丁前新增行为节点真实失败：非零 correction 精确平衡案例应为零，旧公式却返回
`absolute=1.292749008895385`。补丁后同一节点的三个 subTest 全部通过：

```text
python -m pytest -q \
  src/test/test_39_task032_hybrid_augmented_direct.py::Task032HybridDirectOwnershipTests::test_modal_residual_includes_original_rhs_correction
result: 1 passed, 0 skipped in 1.79s

coverage:
  nonzero correction exact balance -> absolute/relative = 0
  nonzero correction small perturbation -> scaled nonzero relative, not 1
  zero correction -> unchanged legacy formula

python -m pytest -q \
  src/test/test_39_task032_hybrid_augmented_direct.py::Task032HybridAugmentedDirectTests::test_modal_schur_multi_rhs_matches_augmented_solution
result: 1 passed, 0 skipped in 5.10s
```

没有修改 Schur 构造、`system.modal_rhs`、solve/factor、Gate 阈值、普通 zero-correction
路径或 ordinary backend，也没有新增 residual framework、dataclass 或 helper。Scoped
Ruff、compileall 和 `git diff --check` 均通过；未运行正式 PDE。

### S02 — 2D power-metrics communicator authority

**结论：`FIXED`。** `src/postprocessing/power_metrics.py` 的计算和 field sampling 已从
`mesh_data.mesh.comm` 取得实际 mesh communicator，但文件仍有 7 个控制点读取
`MPI.COMM_WORLD`：4 个写文件 rank Gate 和 3 个 serial capability size Gate。当 mesh
位于 WORLD 的子 communicator 时，这会错误决定是否支持计算以及哪个 rank 写 evidence。
F05b 修的是 atomic output directory，F06 修的是 interpolation callback 内 collective；
两者都没有覆盖本项 communicator authority。

最小修改仅将这 7 个引用分别替换为 `mesh_data.mesh.comm.rank/size`。文件其他位置仍用
`MPI.SUM` 做 mesh-local scalar reduction，所以保留 `from mpi4py import MPI`。没有增加
communicator 参数/helper、writer abstraction、barrier、lock、广播或状态机，也没有修改
功率公式、文件名、skip reason、采样、R/T/A 或 ordinary behavior。

新增一个 serial pure/mock 节点，以当前测试进程 WORLD size=1、fake mesh comm size=2
和不可访问 field sentinel 调用三个入口。补丁前第一个 subTest 越过错误的 WORLD Gate，
访问 `E_total.x` 并以 `AttributeError` 失败；补丁后三个入口均在 field access 前返回各自
既有 `skipped` payload：

```text
python -m pytest -q \
  src/test/test_20_2d_lossy_port_modes.py::LossyPortModeTests::test_serial_power_capability_uses_mesh_communicator
result: 1 passed, 0 skipped in 1.50s

python -m pytest -q src/test/test_20_2d_lossy_port_modes.py
result: 5 passed, 0 skipped in 1.52s
```

仓库中只有 test20 直接 import `src.postprocessing.power_metrics`；其余 4 个既有节点已在
上述整文件运行中覆盖 lossy/evanescent order、modal power 和实际 port-plane 系数。
`rg` 确认该生产文件不再含 `MPI.COMM_WORLD`；scoped Ruff、compileall 和
`git diff --check` 均通过。未运行 PDE。

### S03 — analytic exact-reference geometry identity

**结论：`FIXED`。** `save_airbox_3d_fields()` 原来用
`not cfg.stage_case.startswith("stage4_")` 决定是否分配并输出 analytic exact field。
`stage_case` 只是调用/记录名称，不是物理几何身份：它会让 stage4 命名的实际 flat layer
丢失 reference，也会让 custom/non-stage4 命名的真实 grating block 错误获得 reference。
F08a 只厘清 generic Floquet capability gate 不应承担完整 physical fingerprint；没有覆盖
这里的 postprocessing analytic-reference identity。

最小修改是在同文件增加一个私有纯函数，只按实际几何判断：

- `airbox` 与 `fresnel_interface`：有 analytic reference；
- `rectangular_block_grating` 且 `has_grating_block=False`：实际是 flat layered
  reference，因此有 analytic reference；
- actual grating block 或 unknown geometry：无 analytic reference。

`save_airbox_3d_fields()` 只调用该函数，不再读取 `stage_case`。false payload 的 note 改为
“当前实际几何没有 analytic exact field，因而不写 exact-field arrays/errors”的通用说明，
不再把所有 false 情况称为 Stage4 grating。没有以
`uses_layered_fresnel_background` 单独放行，也没有比较材料近似值或引入 fingerprint、
material registry。

纯配置测试先以原字符串策略运行：`stage4_flat_layer_sanity` 的 zero-block 反例实际失败，
返回 `False` 而预期 `True`；同一旧表达式对 `custom_block_case` actual block 会返回
`True` 而预期 `False`。最终几何函数的五个 subTest 全部通过：

```text
python -m pytest -q \
  src/test/test_11_stage4_diffraction_modes.py::Stage4DiffractionModeTests::test_analytic_reference_identity_uses_actual_geometry
result: 1 passed, 0 skipped in 1.69s

python -m pytest -q \
  src/test/test_11_stage4_diffraction_modes.py::Stage4DiffractionModeTests::test_analytic_eh_probe_and_net_flux_match_lossy_flat_reference
result: 1 passed, 0 skipped in 1.67s
```

没有调用 field save、mesh 或 PDE，也没有修改 analytic E/H 公式、field allocation/output
流程或 ordinary solver。Scoped Ruff、compileall 和 `git diff --check` 均通过。

### S04 — deterministic internal-facet diffraction trace

**结论：`FIXED`。** `src/postprocessing/diffraction_3d.py` 的 diagnostic diffraction
sampler 原来在一个 probe 恰落内部水平 facet 时取本 rank 的 `links[0]`，随后跨 rank 汇总
又接受第一个命中值。对于由 curl 插值得到的 DG H，这会让所取 trace 依赖局部 cell 顺序和
MPI 分区。该路径虽不生成 official DtN R/T，diagnostic probe 仍必须确定性并遵守同一物理
取迹约定：top probe 从两 probe 平面围成区域一侧的 `-z` cell 取值，bottom probe 从
`+z` cell 取值。

最小修改使 `_sample_field_at_points()` 强制要求无默认值的 keyword-only `z_side`，且只
接受 `-1/+1`。函数一次性计算本 rank 的 owned+ghost cell midpoints；每个碰撞 cell 用
`z_side * (midpoint_z - point_z)` 评分，本 rank及 `allgather` 后均只接受最高分值。不再按
`links` 或 rank 的先后顺序选择；任一点在所有 rank 都无人命中时仍按原合同 fail closed。
全部现有调用点显式传侧：top E/H 为 `-1`，bottom E/H 为 `+1`；calibration mode E/H
直接由既有 `side=top/bottom` 映射，没有新增第二套 side authority。没有修改
diffraction/Fourier/modal fit/power 公式、official DtN R/T、probe z 位置或其他 sampler。

真实 `1 x 1 x 2` hexa mesh 上构造 DG0 vector field，使 `z=0.5` 共享面上下 cell 具有
不同复向量值。补丁前测试因 sampler 没有 `z_side` 合同而以 `TypeError` 失败；补丁后
serial 与 MPI2 都分别确定性取得指定侧，并对非法 side fail closed：

```text
python -m pytest -q \
  src/test/test_11_stage4_diffraction_modes.py::Stage4DiffractionModeTests::test_internal_facet_sampling_selects_requested_z_side
result: 1 passed, 0 skipped in 1.70s

mpiexec -n 2 python -m pytest -q \
  src/test/test_11_stage4_diffraction_modes.py::Stage4DiffractionModeTests::test_internal_facet_sampling_selects_requested_z_side
result: each rank 1 passed, 0 skipped in 4.36s

python -m pytest -q src/test/test_11_stage4_diffraction_modes.py
result: 20 passed, 0 skipped in 2.84s
```

这是 mesh/function sampling 回归，不是 PDE；scoped Ruff、compileall 和
`git diff --check` 均通过，未运行正式 PDE。

### S05 — Full3D reference allocation guard ordering

**结论：`FIXED`。** `periodic_plane_sample_grid()` 原来先为 x/y 坐标建立
`np.arange`、`meshgrid` 和完整 point array，随后 `export_full3d_reference_samples()` 才
执行既有 64 MiB replicated-data Gate。极大但语法合法的 sample count 因而可能在 Gate
之前分配巨型坐标数组。

最小修改在网格函数完成既有 nx/ny、plane 非空/唯一/递增/物理范围验证后，以 Python
整数计算同一 E+H payload：
`plane_count * ny * nx * 3 * complex128.itemsize * 2`。超过既有
`MAX_REPLICATED_SAMPLE_BYTES` 时沿用原 ValueError 语义，并同时报告 64 MiB 与 requested
bytes；该检查现在位于任何 `np.arange`、`meshgrid` 或 `column_stack` 之前。exporter 仅
删除重复的 policy Gate，仍正常构造 shape 并计算相同字节数用于 reshape 和 metadata。
没有新增配置、动态阈值、chunking、streaming、内存探测或通用 allocation guard，也没有
修改坐标、半格偏移、point ordering、side selector、archive/schema、写入或 field sampling。

新增纯配置测试使用两个合法 plane 和 `100000 x 100000` sample counts，同时把本模块
`np.arange`/`meshgrid` mock 成“一旦调用即失败”。补丁前以
`AssertionError: coordinate allocation attempted` 安全失败；补丁后先得到包含 requested
bytes 的 64 MiB ValueError，且两个分配函数均未调用：

```text
python -m pytest -q \
  src/test/test_31_full3d_reference_export.py::Full3dReferenceExportTests::test_replicated_payload_guard_precedes_coordinate_allocation
result: 1 passed, 0 skipped in 0.92s

python -m pytest -q src/test/test_31_full3d_reference_export.py
result: 6 passed, 0 skipped in 0.96s
```

上述均为轻量配置/网格合同测试；scoped Ruff、compileall 和 `git diff --check` 均通过，
未运行 PDE。

### S06 — boundary locator tolerance

**结论：`NOT_A_BUG/NO_CHANGE`。** 审计报告担心
`src/geometry/mesh_builder_3d.py::_mark_boundary_facets()` 中默认 `np.isclose` 会在极细
网格上把邻近内部 facet 标成外边界。该 failure mechanism 与当前调用链不符：代码把每个
坐标 marker 传给 `dolfinx.mesh.locate_entities_boundary(msh, fdim, marker)`。DOLFINx 先按
mesh topology 将候选限制为连接 exterior boundary facets 的实体，marker 随后只判断这些
候选外边界实体的坐标属于 box 的哪一面。`np.isclose` 即使也会接受某个邻近坐标，也不能
把根本没有进入 exterior-topology 候选集的内部 facet 变成 exterior facet。

当前矩形 box 的六面 tag identity 已由
`src/test/test_15_stage4_hexa_mesh_spacing.py` 中真实 DOLFINx hexa mesh 构建、
`facet_tag_sha256` 和 partition-independent mesh identity 覆盖。当前工作树在该未修改模块
没有复现内部 facet 混入，也没有行为证据支持改变现有 tolerance，因此不新增 tolerance helper、配置
字段、显式 `rtol/atol`、额外 mesh traversal 或 source-text test，生产代码和测试均不改。

本结论不表示默认 `np.isclose` 对所有未来几何尺度都永远最佳。若以后出现极小物理域，或
两个不同 exterior boundaries 的坐标在默认 tolerance 下发生混淆，应先保存真实反例并
定义几何尺度/tolerance 合同，再建立独立修复任务；不能从当前未成立的内部-facet 假设
预先扩展代码。本项只更新台账，未运行 PDE。

### S07 — simultaneous and historical memory semantics

**结论：`ALREADY_FIXED`。** 审计报告担心各 MPI rank 的历史 high-water mark 之和被
混称为 simultaneous peak。整改基线 `1f4e48a...` 已明确分离三个不可互换的口径：

- `sum_current_rss_all_ranks_mb` 是同一 progress 采样时刻各 rank current RSS 的和；
- `sum_rank_historical_peaks_mb_upper_bound` 是各 rank 可能发生在不同时刻的历史峰值之
  和，只能作为 upper bound，不能解释为同一时刻的作业峰值；
- external watchdog/forensics 的 process-tree 或 dedicated-cgroup peak 是对完整作业进程
  集合的同步采样 authority，只有这种有权的 simultaneous job/process-tree peak 才能用于
  正式 exact-byte resource Gate；TB/TiB 与 cgroup authority 须先由 A14 冻结。

`src/solvers/common_3d_utils.py` 的 progress telemetry 同时提供前两种显式字段；旧
`total_peak_rss_mb/gb` 仅作为历史 schema/records 的兼容 alias 保留，并由
`total_peak_rss_semantics=sum_rank_historical_peaks_upper_bound` 明确限定语义。
`src/solvers/common_3d_case_flow.py` 的各 summary 路径进一步标注
`sum_rank_historical_peaks_upper_bound_not_simultaneous`。因此不能用该 alias 或 historical
upper bound 代替 process-tree/cgroup simultaneous authority。

watchdog/forensics 已使用 `max_simultaneous_*`、process-tree 与 dedicated-cgroup authority；
F01b 又禁止把无权的 `/init.scope` 当作单作业 cgroup，F09 则在缺少 aggregate coordinator
时禁止真实 heavy 并发。`src/test/test_196_task036_forward_solver_hardening.py` 还锁定日志
不得输出含糊的 `total peak RSS` 文案。现有实现和测试已经覆盖报告关注点，本轮不改名或
删除兼容 alias，不新增 telemetry class、schema version、migration 或 validator，也不修改
历史 records、不运行 PDE；只更新本台账。

### S08 — mode and power floors/clipping

**结论：`DEFERRED/ROADMAP`。** 审计报告把多类 `max(..., 0)` 与 `1e-30`
写法合并成一个问题，但当前实现中的代表性用法至少有三种不同语义，不能用一次全仓替换
安全解决：

- QEP、线性求解与投影 residual 中的 `1e-30` 多为无量纲相对量的零分母保护；
- 传播级判定以及 `max(Re(beta), 0)` 表示 evanescent/lossy mode 的零实功率语义；
- 吸收功率的非负裁剪涉及被动材料的符号约定、数值舍入容差，以及未来是否允许
  active/gain media。

在 canonical 0.7 nm material provenance、passivity/active-material policy、signed-power
定义和允许的负吸收 tolerance 尚未冻结前，统一删除 floor/clip 会把数值保护、模态物理和
材料物理混为一谈；新增一个 generic power validator 或任意 magic tolerance 也没有权威
依据。未来应先完成材料/被动性/active 合同，再逐条路径分别定义 signed-power 与 tolerance
Gate，并为每条被修改路径建立具体物理反例和回归。

本轮已经能明确收紧的窄缺口由 F03 完成：3D volume absorption 对 missing/nonfinite/
nonpositive incident power fail closed，并降级 official summary；2D TE/TM power 路径也已
拒绝 nonpositive incident power。当前没有第二个同时具备失败证据和冻结阈值的窄修复，
因此不重复增加防御代码。

该延期不表示所有现有 clipping 都被永久认可为物理正确，只表示当前缺少统一改写所必需的
物理 authority。本项不全仓扫改 `max(..., 0)`/`1e-30`，不新增 validator、config 字段、
测试矩阵或未经校准的 tolerance，不改生产代码或测试，也不运行 PDE；只更新台账。

### S09 — benchmark checker explicit write opt-in

**结论：`FIXED`。** `benchmarks/check_benchmarks.py` 原来的默认 CLI 会在完成
`evaluate()` 后调用 `_write_outputs()`，因而一次普通验收就会刷新 tracked
`benchmark_summary.csv` 和 `benchmark_gate_report.json`。checker 的默认验收行为现改为
只读：argparse 的 mutually-exclusive group 提供显式 `--write` 和兼容的 `--no-write`，
二者共用 `dest="write"`，默认值冻结为 `False`；只有 `args.write=True` 才调用原 writer。

没有修改 `evaluate()`、任何 Gate、打印内容或退出码，也没有拆分这个大文件，未新增
dry-run class、writer abstraction、备份/锁/atomic framework、schema version 或输出路径。
`--no-write` 继续可用且与无 flag 的默认命令同为只读；只有 `--write` 刷新原来的两份
tracked 文件。`docs/quick_start.md` 和 `docs/result_schema.md` 已同步说明该合同，没有批量
修改 benchmark 报告或 level scripts。

一个 mock 行为节点以同一份 `gates/summaries` 覆盖三个 subTest。补丁前 default subTest
观察到 writer 被调用并失败；补丁后 default 与 `--no-write` 均为零写，`--write` 恰好调用
一次并收到 `evaluate()` 返回的原对象：

```text
python -m pytest -q \
  src/test/test_25_benchmark_contract.py::BenchmarkContractTests::test_checker_writes_only_with_explicit_opt_in
result: 1 passed, 0 skipped in 0.06s

python -m pytest -q src/test/test_25_benchmark_contract.py
result: 6 passed, 0 skipped in 0.24s
```

测试全程 mock writer，没有修改 tracked benchmark 输出；scoped Ruff、compileall 和
`git diff --check` 均通过，未运行 PDE。

### S10 — obsolete root demo scripts

**结论：`FIXED`（deletion only）。** 删除三个已 tracked、已失效的仓库根入口：

- `run_demo.sh`；
- `run_demo_mpc.sh`；
- `run_demo_mpi.sh`。

三者都把位于仓库根的 `SCRIPT_DIR` 再向上一级解析为 `PROJECT_DIR`，随后继续引用已不存在
的 `fenics_vector_maxwell_floquet_demo_v2_parallel/Dockerfile.mpc`、旧嵌套 package 和旧
Docker build context；当前 `Dockerfile.mpc` 等入口已经位于现仓库结构中。因此这些脚本
不可执行且会误导用户，不应保留为 active entrypoint。

本项没有创建 replacement wrapper、deprecation shim、转发脚本或新 CLI。删除后
`rg --files -g 'run_demo*.sh'` 无结果；排除 Task036 审计/台账自身后，唯一剩余文字命中是
`notes/parallel/parallel_v2_guide.md` 中两处带旧嵌套目录前缀的历史记录，不是当前根脚本
调用，按任务边界不修改。仓库没有其他 active 引用。这三个 tracked 文件仍可从 Git 历史
恢复；本轮未新增测试，未运行 shellcheck、容器或 PDE。

### S11 — cooperative memory-stage claim

**结论：`FIXED`（narrow cooperative claim）。** Phase6 与 workstation runner 原来都在
启动时由 rank0 对 memory-stage JSONL 执行 `unlink(missing_ok=True)`，然后 barrier。这会
无条件删除既有证据，也允许两个并发启动互相覆盖。两条路径现在各自拥有一个很小、同语义
的私有 `_claim_memory_stage_file()`，没有抽取共享框架：

- 所有 rank 都调用；rank0 捕获路径校验、建目录和创建文件中的全部 `Exception`，转换为
  `TypeName: message`，随后通过一次 `comm.bcast` 发送；有错误时所有 rank 抛出相同
  `RuntimeError`，rank0 不会在 collective 前单独漏出异常；
- stage 为 `None` 时也广播一次无错误 payload 后返回，保持 collective 序列；
- stage 与 owner 用 `Path.resolve(strict=False)` 比较，只拒绝解析到同一个文件；stage 保持
  caller 指定的位置，可与 owner 位于不同目录，实际 mkdir/open 使用原 stage 路径；
- rank0 用 `stage.open("x", encoding="utf-8")` 创建空的一次性 claim；已存在时拒绝并保留
  原字节；旧 unlink 和紧随其后的 barrier 已删除；
- Phase6 以 `args.output` 为 owner，workstation 以 `record_path` 为 owner；后续既有
  `open("a")` / `_append_jsonl()` 追加路径与数值流程不变。

真实临时文件 serial 测试分别覆盖首次创建（含不存在 parent 的 mkdir）、append sentinel、
二次 claim 拒绝且原字节不变、same-path 拒绝、cross-parent caller path 成功创建空文件和
`None`。唯一 MPI2 纯文件节点由 rank0 预置 sentinel，证明两个 rank 收到相同
`FileExistsError`-bound RuntimeError、文件内容不变且进程正常退出：

```text
python -m pytest -q \
  src/test/test_181_task035c_p6_h10_runner_gates.py::Task035cP6H10RunnerGateTests::test_phase6_memory_stage_claim_is_exclusive_and_preserves_existing \
  src/test/test_29_hcurl_multilevel.py::TestWorkstationMemoryStageClaim::test_claim_is_exclusive_and_preserves_existing
result: 2 passed, 0 skipped in 2.90s

mpiexec -n 2 python -m pytest -q \
  src/test/test_181_task035c_p6_h10_runner_gates.py::Task035cP6H10RunnerGateTests::test_phase6_memory_stage_existing_claim_is_collective_mpi2
result: each rank 1 passed, 0 skipped in 1.84--1.88s
```

这是同一个 stage-file 的 cooperative claim，不是 output owner lock 或完整并发锁。Phase6
若对同一 output 配置不同 stage，仍可能竞争 output；固定 workstation record 二次运行会因
派生 stage 已存在而安全拒绝，必须改用新 record 路径或由用户人工处置旧证据。claim 不防
恶意 unlink 或 TOCTOU，也不提供 stale 检测、自动清理、rollback、重试、随机改名、fsync
或 owner 独占。本轮没有修改 solver、数值流程、watchdog wrapper 或正式 output writer，
也没有运行 PDE 或 full suite。
Scoped Ruff、compileall 和 `git diff --check` 均通过。

### S12 — numerical core accumulated in benchmark runners

**结论：`DEFERRED/ROADMAP`。** 当前若干大型 benchmark runner 仍把数值计算、运行编排、
状态分类、资源生命周期和 provenance/正式记录生成混在同一文件及较长入口中。这是实际
架构债，但不表示所有 runner 都具有同等问题，也不应把函数行数本身当作正确性 Gate。
F01 只统一了 watchdog 的窄进程组终止语义及其 authority 边界，不能据此宣称 runner 的
整体职责混杂已经解决。

本轮不做机械式“大函数拆分”。没有先冻结合同就移动或重排代码，无法证明数值等价，并
可能改变 MPI collective 顺序、PETSc 对象创建/销毁生命周期、正式状态与 provenance、
失败 evidence 的落盘时机。后续必须建立独立架构任务，先冻结每个目标 runner 的输入、
输出、状态转换、collective 顺序、资源 ownership/lifecycle 和 evidence 合同；再把经过识别
且可复用的数值核心逐阶段迁入 `src/`，让 runner 只保留薄编排层，并以行为测试和确有必要
的 PDE anchors 分阶段重新资格化。

延期不代表允许继续向大 runner 堆入数值核心；仓库 `AGENTS.md` 对新数值算法进入 `src/`、
benchmark runner 保持参数化薄入口的规则继续有效。本项也不预建 generic pipeline、
state-machine framework、base Runner、plugin/registry、dependency injection、统一 exception
hierarchy 或通用 provenance service，不借机批量重排/重命名或抽取 solver，不新增
source-text/AST length tests。当前只记录路线与前置合同，没有修改生产代码、测试或其他
文档，没有运行 pytest 或 PDE；仅执行 `git diff --check`。

### S13 — skip and source-shape test debt

**结论：`DEFERRED/ROADMAP`。** 审计 9.3 估计测试中存在约 60 处 skip 门控、约 200 处
源码文本或 `inspect.getsource()` 断言。这反映真实测试债，但这些只是当前快照的约数，
不能写成稳定精确计数、覆盖率目标或验收阈值，也不能 blanket 判定每一项都是 bug。

合理 skip 可能由 MPI size、缺少 optional dependency、平台能力、重型资源限制或明确的
integration profile 决定。source/command-shape 合同有时也有独立价值，例如锁定入口、
禁用路径、精确 worker command 或文档政策；但它们只能约束代码/命令形状，不能证明 MPI
collective、真实文件副作用、数值残差或物理量正确。

本轮已在适合的具体缺陷上优先使用真实行为证据，而不是再写泛化的“测试测试的测试”：

- F01 使用真实父子进程树与 TERM-to-KILL 行为；
- S04 使用真实 DG0 内部共享 facet，并分别资格化 serial/MPI2 取迹；
- S05 mock 实际 allocation 入口，证明 64 MiB Gate 在坐标分配前触发；
- S09 直接执行 CLI main，并 mock writer 验证默认/显式写入行为；
- S11 使用真实临时文件及 serial/MPI2 collective claim，验证错误一致性和证据保留。

后续应建立独立测试债任务，先按理由清点为 `legitimate environment skip`、`stale skip`、
`behavior missing`、`source-shape-only`、`duplicated/obsolete`。优先对 solver、MPI、文件
副作用和正式 Gate 相关的 source-only 断言补充或替换为行为测试，同时保留确有必要的
source/command contract；每次只随对应模块改动做 targeted replacement，只有行为风险确实
需要时才运行 PDE anchor。

延期不表示永久认可所有 skip/source-text 断言。本项也不批量删除或强制 unskip，不创建
pytest plugin、skip registry、AST linter、source-test ban、coverage quota 或自动
monkeypatch framework，不为追求零 skip 安装重型依赖或启动 PDE。当前只更新台账，没有
修改生产代码、测试或其他文档，没有运行 pytest/PDE；仅执行 `git diff --check`。

### A01 — whole-domain direct Full3D scaling boundary

**结论：`DEFERRED/ROADMAP`。** 当前 whole-domain direct Full3D 仍可作为小尺度
physics/numerical anchor，用于交叉验证离散、边界条件和完整 observables；但不能把
13.5 nm 路线机械均匀细化后当作 0.7 nm、最多 2 TB 约束下的 production 路线。延期既不
表示认可 current direct 路线具有所需可扩展性，也不删除它在小模型上的验证价值。

审计中的约 1.75 亿 cells、数十亿 DoF，以及数 TiB 到数十 TiB 内存来自机械均匀细化和
既定数据布局模型的 `derived/predicted` 投影。它们不是实际 0.7 nm run 测得的
simultaneous RSS，也不能证明所有可能的 Full3D 离散在数学上都不可行；只能证明当前
uniform whole-domain direct/layout 路线按这些假设外推时不具备 production 资源可行性。

本轮不通过调整 current direct 参数或增加另一个内存 guard 来冒充数量级问题已解决。
production 路线的前置依赖包括：A07 冻结材料与物理合同；A09--A12 建立合格的接口空间、
分布式/matrix-free 与 local h-p 架构；A13 定义 wavelength continuation；A14 冻结 TB/TiB、
exact-byte 与 cgroup authority。缺少这些前置时，单独“修” direct solver 不足以形成
0.7 nm production 能力。

后续任何 Full3D anchor 仍必须绑定 full explicit true residual、完整 observable vector、
source/artifact identity 和有权的 simultaneous memory measurement。未实际运行的模型必须
保持 `not_run`，预测不得写成 solver pass、resource feasible 或实测结果。

本项不新增 second Full3D runner、mesh estimator framework、自动降阶/路线切换逻辑、
magic wavelength/DoF threshold，也不启动“验证一下”的 0.7 nm PDE。当前只更新路线台账，
不修改生产代码、测试或其他文档，不运行 pytest/PDE；仅执行 `git diff --check`。

### A02 — direct Hybrid data-layout scaling boundary

**结论：`DEFERRED/ROADMAP`。** 当前 direct Hybrid 路线继续作为 13.5 nm 的
reference/anchor，但不是 0.7 nm production solver。现有显式布局仍包含 last-rank modal
ownership、local MUMPS LU 和 all-mode dense RHS 等主导对象；仅增加 MPI ranks 或启用
MUMPS OOC 不能消除这些对象的代数规模与所有权瓶颈。

审计中的约 16,029 modes/direction 是特定 planning 假设下的估算量级，59,306 是 stress
illustration；约 1,595.6 TiB 的 all-mode dense RHS 和 1,611.3 TiB 累计对象体积属于
`derived/predicted layout pressure`。这些不是实际 0.7 nm run 的 simultaneous process-tree
RSS，也不是任意几何、任意接口空间或所有 Hybrid 离散的普适内存下界。

当前 evidence 足以否决“保持此显式 direct 数据布局，只增加机器或微调 MUMPS/MPI/OOC
参数即可压入最多 2 TB”的 production 路线；但不能据此宣称 Hybrid 方法本身在数学上
不可行。本轮也不以 direct MUMPS 参数、rank 数、OOC 或临时分块 RHS 微调冒充数量级问题
已经解决。

future replacement 依赖 A09 冻结合格接口空间、A10 建立分布式/streaming modal core、
A11 建立 matrix-free iterative Hybrid、A12 引入 local h/p，再由 A13 continuation 和 A14
exact-byte resource authority 验证。当前 direct Hybrid anchor 仍予保留；以后每个 anchor
必须报告实际对象生命周期、有权的 simultaneous peak、full explicit residual 和完整
observable vector，所有预测保持 `derived/predicted`，不得冒充 solver/resource pass。

本项不新增 adaptive chunker、OOC policy engine、auto rank tuner、第二套 direct backend
或 magic M cap，也不运行 0.7 nm PDE。当前只更新路线台账，不修改生产代码、测试或其他
文档，不运行 pytest/PDE；仅执行 `git diff --check`。

### A03 — dense modal core and concentrated ownership

**结论：`DEFERRED/ROADMAP`。** 当前实际瓶颈包括 dense `M^2` overlap/Gram/
near-degenerate matching、dense Hungarian assignment、last-rank modal row ownership、
strong-trace `NΓ x M` operators，以及 all-mode `Nlocal x M` RHS。它们随 mode count 和
interface trace size 扩展，不能通过重新命名字段或增加资源 guard 修复。延期不表示认可
这些 dense/last-rank 路线具有 production 可扩展性，也不否认它们在当前小尺度 anchor 中的
验证价值。

同时必须纠正审计原文的过度概括：不能写成“所有 global row/entity maps 都在每个 rank
复制”。当前 cross-section Floquet matching、constraint transform，以及 PETSc
eigenvector/Vec 等已经存在分布式路径。问题集中在若干特定 modal、variable-p/assembly
metadata 和 dense operators，而不是全仓所有对象或每一条通信路径。

A03 不独立实施。必须先由 A09 冻结物理上真正需要的接口空间、传播通道和 completeness
合同，再由 A10 重新设计 distributed ownership、streaming，并去除不必要的 replicated
`M^2` operators 与 all-mode RHS；否则提前优化错误 basis 只会把错误接口架构进一步固化。

future Gate 必须同时证明：完整传播空间没有丢失，transfer-tail/modal completeness 合格，
MPI ownership 与 collective 顺序正确，内存采用有权的 simultaneous measurement，且完整
observables 与 full explicit residual 相对 anchor 等价。仅减少 replicated bytes 或降低 M
不能独立构成成功。

本项不新增 generic distributed-map framework、全局 cache/registry、自动 sparsifier、
magic overlap threshold，不任意删除 modes，也不把全部对象先 allgather 后宣称为
distributed。当前只更新路线台账，不修改生产代码、测试或其他文档，不运行 pytest/PDE；
仅执行 `git diff --check`。

### A04 — mesh construction and postprocess materialization peaks

**结论：`DEFERRED/ROADMAP`。** 当前部分 structured hex/tetra mesh 路径仍可能在每个
rank 构造完整 global vertex-coordinate array，而只对 cells 做分片。后处理阶段还可能同时
materialize 多个 DG functions、NumPy arrays 和 PyVista rank-local copies，并保留
`grid.copy()`；这些对象的生命周期可能与 direct factor、KSP 或 field recovery 重叠，形成
实际峰值压力。延期不表示认可这些复制在 production 尺度上可扩展。

必须纠正审计中的过度概括：DOLFINx solution/field 本身是按 MPI 分布式的，不能写成
“每个 rank 都持有完整全局场”。当前问题是部分 mesh builder 的全局坐标构造，以及每个
rank 内部同时存在的 materialized DG/NumPy/PyVista 副本，不是 distributed solution vector
整体在每个 rank 复制。

提前释放 direct factor/KSP 已有 opt-in 路径，但普通数值 solver/backend default 尚未完成对应数值、输出
和资源资格化。本轮不能把“已有 opt-in”写成整体问题已解决，也不能直接翻转 ordinary
default。

future work 必须先冻结必须保留的 official observables 与 artifact contract，再分阶段实施：

- distributed mesh construction，避免每 rank 无条件构造全局坐标；
- selective/streamed port、material 和 slice outputs；
- 避免无条件全域 DG/PyVista materialization 与 `grid.copy()`；
- 在最后消费者完成后阶段性释放 factor/KSP/field 和大型临时对象；
- 将 postprocess 纳入独立、有权的 simultaneous process-tree/dedicated-cgroup memory Gate。

任何生命周期或输出路径改变，都必须用 anchor 证明 full explicit residual 与完整 official
observables 等价，并核对 artifact identity/完整性。本项不建立 generic memory manager、
object registry、自动 gc/finalizer、全局 copy-on-write wrapper，不任意删除 official
outputs、不默认禁用所有 field output，也不加入 magic size threshold 或运行 0.7 nm PDE。

累计对象估算和各 rank historical peak sum 继续只能作为 inventory/upper bound，不得冒充
同一时刻的作业峰值。当前只更新路线台账，不修改生产代码、测试或其他文档，不运行
pytest/PDE；仅执行 `git diff --check`。

### A05 — 0.7 nm DtN order qualification

**结论：`DEFERRED/ROADMAP`。** 必须先纠正 current-state 描述：generic
`SimulationConfig3D` 与 canonical target 已使用 `auto_propagating`；`src/main.py` 中的
`zero_order` 是明确命名的 demo façade/default，不等于 production target 的默认策略。
因此不能照抄“整个仓库在 0.7 nm 仍默认 zero-order”，也不能据此把 demo 本身判成 bug。

但 `auto_propagating` 只描述 order-selection policy，不代表 0.7 nm 已完成 formal
qualification。真正缺少的 production evidence 包括：

- canonical 0.7 nm config/material identity，并与 period 和 incidence 严格绑定；
- 全部物理传播级的枚举与 Rayleigh 临界级处置；
- 有界、经收敛验证的 evanescent buffer；
- modal power completeness、M/order convergence；
- 覆盖完整显著衍射级的 power/complex-amplitude observable vector。

未来任何 mode 保留、筛选或压缩策略都必须证明物理必需的完整传播空间没有丢失。只比较
R00 或代数 residual，均不足以资格化开放边界和 DtN order policy。

A05 依赖 A07 冻结 0.7 nm config/material identity，并须与 A09 的接口空间、A10 的
distributed modal core 协同，再由 A13 wavelength continuation 形成分阶段证据。当前
`auto_propagating` 只能视为实现状态，不能写成 0.7 nm formal pass。

本项不修改 demo default，不增加 `lambda <= ...` 魔法分支、固定 mode count、自动 buffer
猜测器或第二套 DtN policy registry，不任意删除 evanescent/propagating modes，也不运行
0.7 nm PDE。延期不表示认可 zero-order 可用于 0.7 nm production；它表示 production
物理合同与资格证据尚未具备。当前只更新路线台账，不修改生产代码、测试或其他文档，不
运行 pytest/PDE；仅执行 `git diff --check`。

### A06 — M0 剩余项：并发 aggregate-memory coordinator

**结论：`DEFERRED/ROADMAP`。** 不能把整个 M0 写成未完成。F01--F10 已分别关闭大部分
基础设施硬化问题，各自保持其 `FIXED`、`NOT_A_BUG/NO_CHANGE`、`ALREADY_FIXED`、窄
guard 或延期结论。尤其 F01 已闭合进程组终止与 cgroup authority 的窄合同，F09 已把当前
真实 heavy dispatcher 强制为 serial-only；仓库内该 dispatcher 现在不会同时启动多个真实
heavy cases。

A06 的剩余缺口只在未来若要恢复 concurrent heavy dispatch 时成立：需要一个具有单一 job
ownership 的 aggregate coordinator。它必须在每个同一采样时刻读取并求和各 worker 的
current process-tree RSS/bytes，形成 aggregate time series 后再取该序列最大值；或者使用
一个包住全部 worker 进程树的单一 dedicated-cgroup peak。严禁相加各 worker 发生在不同时刻
的 historical peaks。MUMPS OOC、JIT/cache、scratch/temp 还须以各自正确口径进入预算，
不能混入 RSS。exact-byte 上限、TB/TiB 定义与 reserve 必须先由 A14 冻结。

A06 只阻止尚无 coordinator 的未来并发 heavy，不禁止当前 serial guarded heavy/PDE 按其
任务合同运行。dry-run 的并发计划只表示调度形状，不构成真实资源资格。未来 Gate 还必须
定义 dedicated job-group authority、超限前的受控停止和完整进程组清理、record ownership
以及 fail-closed 状态；F01 的终止能力和 F09 的串行化均不等同 coordinator 已完成。

当前没有用户/调度器/cgroup authority，不能以 per-job limit、CPU lease、各 rank 历史峰值
相加或一个 `2 TB` 字符串伪造 aggregate coordinator。本项不新增 daemon、lock service、
scheduler abstraction、global resource registry、background monitor framework、自动 OOC
allocator 或并发重试，不恢复 heavy concurrency，也不运行 PDE。当前只原位校正台账，
不修改生产代码、测试或其他文档，不运行 pytest；仅执行 `git diff --check`。

### A07 — M1 冻结 0.7 nm 物理与材料合同

**结论：`DEFERRED/ROADMAP`。** F08b 的窄 guard 只防止把仓库内明确命名的 13.5 nm
Si material pair 用于不匹配波长。它不能证明任意 custom 0.7 nm 材料可信，也不构成完整
canonical 0.7 nm fingerprint。

A07 真正缺少的是可审查的 0.7 nm authority，至少包括：

- geometry、period、incidence、polarization、boundary、mesh-axis、element-degree 和
  完整 config identity；
- 材料数据来源、版本/hash、适用波长、密度/组成/温度；
- 插值与吸收边处理规则，以及 `n + ik` 或散射数据到复介电常数的 exact conversion；
- 时间因子、虚部符号、passivity/active-material policy；
- roughness、oxide 和 interface diffusion 的允许范围及不确定度。

这些合同可以分阶段冻结，但任何尚未冻结的字段必须显式标记 `unavailable/not_qualified`，
不得用默认值或 custom label 填补。A07 冻结的是“每一级运行使用什么物理与材料身份”；
`13.5 -> 5 -> 2 -> 1 -> 0.7 nm` 的逐波长运行和证据属于 A13 continuation，不再作为 A07
的完成条件。

A07 是任何正式短波长、尤其 0.7 nm run 的前置条件，但不阻止先在已经冻结的 13.5 nm
authority 下开展 A09 接口空间研究。延期不表示所需材料一定不可获得；它表示用户尚未
提供并冻结权威来源和 exact conversion contract，Codex 不得自行猜测。

本项不创建假 material registry/cache、占位 0.7 nm 常数、自动网页抓取/插值器、波长
fallback 或 magic passivity tolerance，不把 `custom_material_unverified` 提升为
formal/physical pass，也不运行 PDE。当前只原位校正台账，不修改生产代码、测试或其他
文档，不运行 pytest；仅执行 `git diff --check`。

### A08 — optional 2D/2.5D diagnostic, outside production chain

**结论：`DEFERRED/ROADMAP`。** 审计报告曾根据 `grating_width_y == period_y` 的潜在
y-invariance，建议优先验证 2D/2.5D 降维。最新任务 authority 已明确
`2.5D production assumption = forbidden`；当前 0.7 nm 目标统一按真正 3D 问题规划。

因此 A08 不能作为 production solver，不能成为 A09/A10 的前置条件，也不能用作最多
2 TB 可行性依据、资源预算 baseline，或证明约 286 modes 等缩减估算成立。几何外观上的
y 不变性并不自动证明材料、入射、polarization、boundary conditions 和全部物理通道都
满足降维假设。

若未来获得独立授权，2D/2.5D 只可作为诊断或交叉核验，并必须与小型 3D anchor 比较：
trace identity、S/P coupling、`R00_s`/`R00_p`/`R00_total`、全部显著衍射级、T/A/
`A_volume` 和 full explicit residual。即使这些观测在特定点一致，也不能自动把降维模型
提升为 production 3D 的替代品。

A08 不在 production dependency chain，不阻塞 A09 在已冻结 13.5 nm authority 下开展
接口空间工作。延期不表示降维永远没有科研价值；它只表示当前禁止将其作为生产假设或
2 TB 解决方案。

本项不新增 2D/2.5D solver façade、auto symmetry detector、
`width_y == period_y` 自动切换、Fourier-separated backend、mode-count shortcut 或
fallback policy，也不运行降维或 3D PDE。当前只更新路线台账，不修改生产代码、测试或
其他文档，不运行 pytest；仅执行 `git diff --check`。

### A09 — transfer-optimal-port interface space

**结论：`DEFERRED/ROADMAP`。** 当前 13.5 nm evidence 中，30/90 nm 与 40/80 nm
接口点都只有 79/96 个冻结通道通过；继续移动接口或盲目增加 global M 均不是已经证实的
路线。后续 exact joint-Cauchy audit 已经完成，但它只提供 basis-family 选择证据；actual
enrichment candidate 仍是 `not_run`：尚未实现、尚未运行，也没有通过证据。

旧审计报告曾并列 full-interface discrete Bloch、thin-buffer transfer eigenmodes/
optimal-port 等多个候选。最新 authority 已冻结唯一 family 为
`transfer_optimal_port_modes`，后续不再做多 family shotgun comparison。明确禁止回退到：

- 继续扫描接口位置；
- ordinary E-only buffer 或 full-interface corrector；
- 为每个失败通道分别加入 adjoint mode；
- 依靠无限增加 global M。

A09 的资格化顺序固定为：

1. **P0 — synthetic/fixture：**冻结 exact joint Cauchy pairing、normalization、
   near-degenerate block、transfer singular-value tail 和 deterministic identity；
2. **P1 — one actual anchor：**只运行一个 A004-S 13.5 nm actual case，复用已有 Full3D
   exact traces 验证 actual enrichment；
3. **P2 — frozen parameter anchors：**只在预先冻结的 parameter anchors 上验证，不得
   根据结果事后挑点。

只有 P0、P1、P2 依次通过后才允许进入 A10。成功不能只依据某个 R/T；必须同时通过
full explicit residual、96/96 frozen channel vector（或后续 authority 冻结的等价完整
向量）、R/T/A/`A_volume`、interface trace/Cauchy error、transfer-tail、source/artifact
identity 和 simultaneous resource authority。任何未运行阶段都保持 `not_run`，不得写成
pass。

A07 不阻止 A09 先在已冻结的 13.5 nm authority 下工作；任何 0.7 nm actual run 仍必须
先满足 A07。当前本项不建立 basis registry/plugin、automatic enrichment controller、
failing-channel mode factory、generic SVD cache 或 interface scanner，不修改 solver，也不
运行 pytest/PDE。这里只更新路线台账并执行 `git diff --check`。

### A10 — P3 distributed streamed modal/QEP core

**结论：`DEFERRED/ROADMAP`，当前为 `not_run`。** A10 严格等待 A09 P2 通过；在
`transfer_optimal_port_modes` 尚未证明 actual physics closure 前，不得先为可能错误的
接口空间优化分布式数据布局。只有 A09 P0、P1、P2 顺序 Gate 全部通过，A10 才可开始。

当前代码已有 PETSc/SLEPc `Vec`/`Mat` 和部分 Floquet/constraint 分布式路径，但这不等于
scalable modal core 已经实现。last-rank modal ownership、replicated/dense M² operations、
all-mode Nlocal×M RHS 和 dense matching 等瓶颈仍然存在。

P3 的 future target 是：

- distributed mode/trace ownership；
- 按 block/stream 生成、投影并消费 modes，避免长期 materialize 全量 RHS 与 replicated
  M² operators；
- 对 near-degenerate blocks 保持整体一致性和 deterministic identity，不随意拆块；
- 明确通信、对象生命周期和 simultaneous memory 记录。

这里的 “observable-related modes/streaming” 绝不能解释为只保留当前看起来影响某个
R/T 的 modes。实现必须保留全部物理传播空间；evanescent/enrichment 的任何截断都必须由
A09 transfer-tail/modal-completeness evidence 证明，Rayleigh 和 near-degenerate blocks
不得任意拆分。

P3 的资格 Gate 必须证明：与 A09 P2 direct anchor 的 full explicit residual、完整通道及
complex amplitudes、R/T/A/`A_volume`、trace/Cauchy error、ordering/degenerate identity
等价；MPI2/MPI4 ownership 与 collective behavior 正确；并有 simultaneous memory 随
ranks 和 M 扩展的证据。仅降低内存却丢失通道不构成 pass。A10 通过后才允许进入 A11；
在实现和验证前持续标记 `not_run`。

本项不建立 generic distributed tensor framework、mode service/cache、automatic chunk
tuner、magic M cap、full allgather fallback、silent serial fallback 或 arbitrary
sparsification，不修改 QEP/solver，也不运行 pytest/PDE。这里只更新路线台账并执行
`git diff --check`。

### A11 — P4 matrix-free strong-trace Hybrid iterative

**结论：`DEFERRED/ROADMAP`，当前为 `not_run`。** A11 严格等待 A10/P3 通过；否则
matrix-free 层仍会消费未资格化或不可扩展的 modal core。只有 A10/P3 的 physics、MPI
ownership 和 resource Gates 全部通过，A11 才可开始。

仓库已有部分 Full3D/condensed `MatPython`、FGMRES 和 preconditioning components，但它们
不等于 matrix-free strong-trace Hybrid。当前 strong-trace 路线仍会组装完整方阵并执行
direct solve；存在 shell/action 类不能作为本项已完成的证据。

P4 必须实质避免 materialize global strong-trace/augmented operator 及其 direct factor，
并提供可审查的：

- volume、trace 和 modal block actions；
- transpose/adjoint action（当所选算法需要时）和 full residual action；
- block-triangular/approximate-Schur 与 local H(curl) scalable preconditioning；
- 每个大对象、通信步骤和生命周期的明确 ownership。

禁止伪完成：只把现有 assembled matrix 包入 `MatShell`/`MatPython`，或在 shell 内仍组装、
保存同一 global matrix 与 factor，都不构成 matrix-free。

P4 的资格 Gate 必须相对 A10/P3 及其 direct anchors 证明 full explicit true residual、完整
observables/complex amplitudes、R/T/A/`A_volume` 和 trace/constraint 等价；KSP
convergence reason、iterations、orthogonalization 与 preconditioner behavior 可解释；
MPI2/MPI4 collective 和 ownership 正确；simultaneous memory evidence 证明峰值不再由
global factor/assembled operator 主导。单次收敛或较低 RSS 但物理 Gate 失败不算 pass。

本项不新增 empty-shell `MatShell`、generic operator DAG、preconditioner registry/factory、
automatic KSP fallback/retry、parameter searcher 或 silent direct fallback，不修改 solver，
也不运行 pytest/PDE。A11 未实现前保持 `not_run`；只有 A11 通过后才允许进入 A12。当前
只更新路线台账并执行 `git diff --check`。

### A12 — P5 scalable local h/p

**结论：`DEFERRED/ROADMAP`，当前为 `not_run`。** A12 严格等待 A11/P4 通过。仓库已有
exact-sequence、variable-p/local-h 和 static-condensation 等可复用组件，但 Task035e 没有
production candidate；blind adaptive controller 已产生负结果，Hybrid/iterative 也尚未
资格化。组件存在不能作为 scalable local h/p 已完成的证据。

P5 的 future target 包括：

- owner-routed distributed numbering，以 ghost/neighbor exchange 替代全量 entity/row
  allgather；
- 保持 H(curl) conformity、Floquet/periodic constraints 和 near-interface directional h/p；
- 复用 F10 已覆盖的两条 production 构建路径：singular/nonfinite、`LinAlgWarning` 和
  primal/adjoint backward-residual 超限会 fail closed；`pivot_ratio` 仍仅为趋势 telemetry，
  经代表性 0.7 nm local-block 数据校准的 condition-number cutoff 继续属于后续路线。

误差驱动必须覆盖完整目标，包括 `A_volume_total`、主要衍射通道和完整 observable vector
对应的 adjoint、goal derivative 与 DWR；不得只追踪单个 R，也不得只用 DoF 下降作为优化
目标。structured/uniform high-order 必须保留为 control。历史 adaptive p6 结果不能证明
自动节省 50% DoF，任何预测节省都不得写成 measured fact。

P5 必须先通过 accuracy/physics Gate：full explicit residual、完整 observables、
R/T/A/`A_volume`、trace/constraint、h/p transfer/condensation consistency，以及 MPI
ownership/collective behavior；通过后才能评价 simultaneous memory。迭代内存比较只能在
adaptive/Hybrid candidate 先通过 accuracy Gate 后开始，不能以较低内存掩盖物理失败。

本项不恢复 blind controller，不新建 generic adaptivity framework/controller DSL、
automatic threshold tuning、global allgather fallback、silent uniform fallback 或 magic 50%
target，也不运行 pytest/PDE。A12/P5 未实现前保持 `not_run`；只有 A12/P5 通过后才允许
进入 A13。当前只更新路线台账并执行 `git diff --check`。

### A13 — P6 wavelength continuation

**结论：`DEFERRED/ROADMAP`，当前为 `not_run`。** A13 必须同时等待 A07 为每一级冻结
physics/material authority，并等待 A09 P0→P2、A10/P3、A11/P4、A12/P5 全链通过。
continuation 尚未运行，当前不得写成 feasible 或 pass。

continuation authority 归 A13，固定为 `13.5 → 5 → 2 → 1 → 0.7 nm`。每一级都是新的
qualification point，必须重新绑定：

- material identity/conversion；
- propagating orders、Rayleigh handling、M、transfer-tail 和 evanescent buffer；
- mesh/local h/p 与 solver/preconditioner；
- 完整 channel observables 和 resource prediction。

不能只修改 wavelength，也不能沿用上一波长点的 pass。每一级先运行低成本解析/结构性
anchors，包括适用的 homogeneous、zero-contrast、Fresnel/manufactured 以及
operator/action/constraint tests；然后才运行小型 3D Full3D/Hybrid anchors。需要独立软件
比较时必须使用同一 physics、units 和 observable identity；没有取得证据就标记
`unavailable`。

每一级必须通过 full explicit true residual、official-result identity、完整
propagating/modal completeness、完整 complex channel vector、R/T/A/`A_volume` closure、
适用的 passivity/reciprocity、interface trace/Cauchy、source/config/material/artifact hashes
以及 A14 simultaneous resource Gate。任一 Gate 失败即停在该级，不得继续缩短波长。

只有预测峰值显著低于 A14 冻结的 exact-byte budget，才可授权下一次 heavy case；预测只
决定是否启动，不能冒充 measured peak 或 solver pass。本轮不运行 PDE，因为 P0–P5、
0.7 nm material authority 和 exact-byte authority 尚未满足。路线台账可以静态核对，但未来
数值可行性必须由实际 PDE anchors 验证。

本项不建立 automatic continuation/resume framework、parameter scheduler、automatic
material interpolation/fallback，不在失败后放宽 Gate，不跨波长复用 stale artifacts，也不
启动任何波长 PDE。当前只更新路线台账并执行 `git diff --check`。

### A14 — exact-byte resource authority (horizontal Gate, not M8)

**结论：`DEFERRED/ROADMAP`，当前为 `not_run/unresolved authority`。** A14 是横向约束
A09–A13 每个 actual stage 的资源 Gate，不是 M8。用户原始表述是“最多 2 TB”，不得静默
解释为 2 TiB。当前单位算术为：

- `2 TiB = 2048 GiB`；相对 1530 GiB design allocation 余 518 GiB，约 25.3%；
- decimal `2 TB = 2,000,000,000,000 bytes = 1862.65 GiB`；相对 1530 GiB 只余约
  332.65 GiB，约 17.9%；
- `1.5 TiB = 1536 GiB`，不等于 1530 GiB。

因此“2 TB”标题与按 2 TiB 计算约 25% 余量不能同时成立。1530 GiB 目前只是未校准的
design allocation，不是 measured peak、scheduler limit 或已执行 Gate，也不构成可运行
承诺。

正式合同至少必须冻结 exact bytes 和以下四个 authority 字段：

- `physical_or_scheduler_limit_bytes`；
- `host_os_reserve_bytes`；
- `job_cgroup_limit_bytes`；
- `simultaneous_process_tree_peak_bytes`。

swap/pagefile、MUMPS OOC scratch、persistent artifact storage 与 temporary storage 必须分开
记录，不能混入 RSS。在用户和部署环境确认前不编码任何阈值；如果只能按用户字面做保守
planning，上限不得超过 decimal `2,000,000,000,000 bytes`，但 formal Gate 仍须绑定实际
physical/scheduler/cgroup authority。

A09–A13 每个 actual stage 的 prediction 必须给出 calibration points 和 uncertainty，只用于
决定是否授权启动。运行时以 dedicated-cgroup 或完整 process tree 的同一时刻峰值判定；
超限必须触发 F01 的受控进程组清理并 fail closed。预测、历史 rank 峰值之和或累计对象体积
均不能冒充 simultaneous measured peak。

下一步需要用户或部署环境明确：“2 TB”究竟是 physical-machine limit、scheduler
allocation 还是 job-cgroup limit，并提供 exact bytes 与 host OS reserve。在这些 authority
冻结前，A14 保持 `not_run/unresolved authority`。

本项不加入 hard-coded 1530/2048 GiB constants、generic budget manager、automatic reserve
guessing、unit-conversion service、swap/OOC automatic quota 或 fake cgroup，也不运行内存
压力测试、pytest 或 PDE。当前只更新路线台账并执行 `git diff --check`。

## 4. 最终逐项自检

本台账共有 45 个唯一编号，包含全部 F/D/N/S/A 项；D01 与 N01 均计入。逐项段落与正式
`结论` 均为 45 个，每项恰好一个，没有未分类项；F10 的 0.7 nm condition cutoff 仅作为
同一条目下的“后续路线/尚未校准项”，不构成第二个正式结论。

| 审阅语义 | 保留的正式 enum | 数量 | 条目 |
|---|---|---:|---|
| 已整改 | `FIXED` | 24 | F01a、F01b、F02a、F02b、F03、F04、F05a、F05b、F05c、F06、F07a、F07b、F08b、F09、F10、D01、S01、S02、S03、S04、S05、S09、S10、S11 |
| 无需改 | `NOT_A_BUG/NO_CHANGE`、`ALREADY_FIXED` | 4 | F08a、N01、S06、S07 |
| 后续路线 | `DEFERRED/ROADMAP` | 17 | S08、S12、S13、A01--A14 |

仍未闭合的是上述 17 个 `DEFERRED/ROADMAP` 路线项；它们没有被写成当前实现或通过结果。
其中 A06 只在未来恢复 concurrent heavy dispatch 时触发，A07/A09--A13 是 production
研究依赖，A14 仍缺用户/部署环境的 exact-byte authority；S08、S12、S13 分别等待物理
合同、runner 架构合同和测试债独立任务。其余 28 项均已有“已整改”或“无需改”的逐项
证据与残余边界，没有额外未分类 blocker。

所有代码与测试结果属于以
`1f4e48a9683b9167bedb28aaf4ee44931078b40b` 为历史基线、叠加在 pre-checkpoint HEAD
`3375e417dd2cca2c56479ef0c58039b79c3019c8` 之上的 73-entry 未提交 worktree；这是
checkpoint 前的历史验证状态，提交后不再描述当前工作树。上文测试计数是各整改阶段在
资格化 activation 下取得的 targeted evidence，不是本次纯 Markdown 身份更正后的 full
post-edit regression。

## 5. 最终工作树验证

| 项目 | 最终监督证据 |
|---|---|
| Git identity | 整改实现/阶段性测试历史基线 `1f4e48a9683b9167bedb28aaf4ee44931078b40b`；pre-checkpoint HEAD/upstream `3375e417dd2cca2c56479ef0c58039b79c3019c8`；branch `codex/20260730-task36-forward-solver-bugfix-hardening` |
| Review-only fast-forward | `1f4e48a...` 至 `3375e417...` 仅更新 `review_report_v5.md`，Python 内容未改变 |
| Worktree | checkpoint 前历史验证状态：未提交 dirty worktree；`git status --short --untracked-files=all` 为 73 entries；未 commit/push；提交后不得称为当前状态 |
| Qualified ABI | activation `1`；Python `/home/Projects/MyFEniCS/.venv/bin/python`；PETSc `complex128/int32`；DOLFINx、petsc4py、slepc4py、mpi4py 均来自 Linux ABI stack |
| Python inventory | checkpoint 前 65 个 changed+untracked Python，按 path sort 后逐文件 SHA-256 再汇总；review-only fast-forward 与本次 Markdown 身份更正均未改变其内容；digest `5cb5c91beb45a5a61b7066fbeab827a029b14e03bd4fd416e524f56a389fa9d0` |
| Consolidated serial | 22 个 changed `test_*.py`；298 collected；286 passed、12 skipped，195.48 s |
| MPI2 key set | F05b、S04、S11、F10 两实现、F06 两负一路正；每 rank 8 passed，5.44/5.47 s |
| MPI4 key set | F06 zero-local；每 rank 1 passed，2.84--2.85 s |
| Static checks | 65 个 Python 的 Ruff pass、compileall pass；tracked `git diff --check` pass |
| Untracked whitespace | 三个 untracked 文件逐个 `git diff --no-index --check`：均 rc=1、output 0 bytes；rc=1 只因与 `/dev/null` 内容不同，不是 whitespace failure |
| Ledger structure | 45 unique sections、45 formal conclusions、无 duplicate ID；`FIXED=24`、`NO_CHANGE/ALREADY_FIXED=4`、`ROADMAP=17` |

未运行 formal benchmark PDE 或 0.7 nm solve。serial suite 的 12 个 skip 包含 MPI/Docker
Gate；关键新增 MPI 路径已按上表单独覆盖，但这些证据不能宣称完整 MPI matrix 或 full
repository suite。此末尾纯 Markdown 同步不改变上述 Python inventory digest，因此无需
重跑数值测试。
