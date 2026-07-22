# Task035：H(curl) 场/目标量驱动自适应与 hp 策略

## 当前身份

```text
status = phase_b_gate_pass_phase_c_unlocked
execution_lock_released_by_Task034_final_selective_merge = true
execution_branch_created_by_codex = true
base_sha = 5002636852ffb67b4711443da70eb536c303e34e
task035_pde_started = false
heavy_p4_started = false
```

Task035 专门处理 Task034 尚未解决的核心问题：

```text
如何为双周期、复材料、高阶 Nédélec、DtN/Hybrid Maxwell 问题
建立真正由场误差或目标量误差驱动的 h/p/hp 自适应，
而不是手工几何 graded mesh。
```

执行权威：

- [`task.md`](task.md)：正式任务书；
- [`../../notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md`](../../notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md)：文献、候选 estimator、mesh backend 与 hp 策略；
- Task034 最终 `outcomes/summary.md`、Case093 和最终 review：13.5 nm 固定结构基线与能力边界；
- [`../repository_work_principles.md`](../repository_work_principles.md) 和根 `AGENTS.md`：分支、审查、证据与合并规则。

## 执行前置条件

Task035 不得在 Task034 尚未完成最终 selective merge 时启动实现或重型 PDE。

Task034 最终合并后，由 Codex 从最新 clean `origin/master` 创建：

```text
codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

ChatGPT 与 Codex 的 Task035 任务材料、review、代码、outcomes 和 response 全部保存在该执行分支；最终审阅和用户授权前不得合并 `master`。

## 主范围

```text
13.5 nm
fixed physical geometry
S polarization mainline
10° grazing first
p2/p3/p4 Nédélec
Full3D + Hybrid
field-driven h-adaptivity
residual / recovery / equilibrated / two-level / DWR estimator bake-off
DtN and internal-mode truncation error separation
anisotropic conforming mesh regeneration
conditional hp capability audit
```

## 非目标

```text
0.7 nm production PDE
完整 P 入射矩阵
直接进入 arbitrary cellwise variable-p production
在 estimator 未资格化前运行大规模 p4 campaign
在 Task035 中同时重写 scalable modal core 或最终 iterative solve
```

Task035 的成功不要求所有候选方法都成功；要求每条方法都有可审计的 fixture、筛选、正/负决定，并至少判断是否存在一个可信的 field-driven adaptive 主线。

## Phase A 状态

Task035 执行分支已从 clean `master` 创建并推送。WSL、source、ABI、MPI1/2/4/8、
MUMPS/PEP microfixture、Task034 compact baseline 与六份必需 ignored artifact 的哈希
资格化子 Gate 均通过；首次 Case094 文档合同失败已按 Review V1 修复，最终 full pytest 通过，
Phase B 已解锁。仍未启动真实 Task035 PDE 或重型 p4。详见
[`outcomes/environment_and_base.md`](outcomes/environment_and_base.md) 和
[`base_manifest.json`](../../benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json)。

## Phase B 状态

R1、R2、R3、R5、G1、G2、B1、M1 的 analytic/manufactured fixture decision 已通过；
R4 仅完成公式与局部 SPD precursor，保持 `formula_defined`。serial/MPI2/MPI4 component
identity、Task035 focused suite 和正确 complex activation 下的 full pytest 均通过，
Phase C 已解锁。没有启动真实 PDE 或 adaptive mesh。详见
[`outcomes/estimator_definitions.md`](outcomes/estimator_definitions.md) 和
[`response_v2.md`](response_v2.md)。
