# Task038-extra Review Report V18：V18 restart64 审阅与真实 physical 最终正确性资格

## 0. 审阅身份与总裁决

```text
review                                  = Task038-extra Review Report V18
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = eda919ab09897793bcb8792dc65ca8f30b5d6e23
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
ordinary_default_change                 = forbidden
V18_historical_classification           = V18_RESTART64_NUMERICAL_GATE_FAIL; frozen
new_execution_lane                      = restart64_physical_eventual_v1
positive_hierarchy_role                 = auxiliary_preconditioner_only
physical_operator                       = exact split matrix-free Maxwell + streaming Fourier-DtN
primary_objective                       = final physical correctness under bounded memory
iteration_count_and_wall_time           = secondary
full_0p7nm_PDE                          = forbidden
response_required                       = response_v18.md
continuous_authorized_batch             = E0 through E5
mandatory_stop                          = after E5 or any earlier terminal hard stop
```

本 Review 继续服从项目最终目标：在单节点约 2 TiB 物理内存内，以自主
FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解
0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

本轮不再把正定辅助问题的通过当作最终目标。已资格化的
`same_mesh_hcurl_pmg_v1_requalified` 只保留为真实 Maxwell 外层求解器中的辅助近似逆；
所有继续或成功判断都必须由真实 physical operator 的 full explicit true residual 决定。

---

## 1. 对 V18 结果的正式审阅

### 1.1 必须永久保留的历史分类

V18 对同一个 p6/h10、MPI1、13.5 nm physical checkpoint-1000，固定使用：

```text
exact split matrix-free physical Maxwell A6
streaming Fourier-DtN
same physical RHS
same complex lossy material
same dual Floquet/MPC
same positive p6→p3→p1 auxiliary PC
right FGMRES
restart = 64
```

独立 checker 已确认 raw evidence 有效。V18 旧性能 Gate 的结论必须永久保留：

| 项目 | measured | 冻结 Gate | 历史结论 |
|---|---:|---:|---|
| initial physical true residual | `0.48379479479924` | diagnostic | measured |
| additional step 512 | `0.35604872662297266` | `<=0.25` | FAIL |
| additional step 1024 | `0.27299642739429014` | `<=0.10` | FAIL |
| `r1024/r768` | `0.8588033360973709` | `<=0.85` | FAIL |
| parent process-tree peak | `1,583,013,888 B` | `<2,000,000,000 B` | PASS |
| process-tree swap | `0 B` | `=0 B` | PASS |

因此下列分类不得覆盖、删除或改写：

```text
V18_RESTART64_NUMERICAL_GATE_FAIL
```

完整历史证据见：

- [V18 restart64 outcome](outcomes/restart64_physical_checkpoint_v18.md)
- [V18 compact record](outcomes/records/restart64_physical_checkpoint_v18.json)

### 1.2 V18 已经是真实 physical 结果

V18 的外层 residual 是：

```text
||b_physical - A_physical x|| / ||b_physical||
```

其中 `A_physical` 包含真实 curl-curl、负的复材料质量项和 streaming Fourier-DtN。
正定 p-multigrid 只作为右预条件器被调用。因此 `0.27299642739429014` 不是 positive
auxiliary residual，也不能被 positive 四源结果替代。

### 1.3 为什么仍授权新的 eventual-correctness lane

V18 失败的是预先冻结的短程性能 Gate，不是资源、finite、provenance 或 physical
operator Gate。16 个 restart-64 周期的 physical true residual 连续下降：

```text
additional 64    = 0.38962773965567615
additional 512   = 0.35604872662297266
additional 768   = 0.31788002668324270
additional 1024  = 0.27299642739429014
```

最近 512 步的 measured ratio 为：

```text
0.27299642739429014 / 0.35604872662297266
= 0.7667389516698698
```

若这一平均对数斜率保持，从当前 residual 到 `1e-6` 还约需 `2.4e4` 步。该数值只是
由当前曲线得到的 derived estimate，不是收敛保证，也不是新的 Gate。

用户已明确当前优先级是：先证明固定内存内最终正确求解，迭代次数和耗时暂居第二。
因此本 Review 以前瞻方式建立新的 eventual-correctness 合同；它不追溯改变 V18 的旧
performance FAIL。

---

## 2. 本轮允许和禁止的改变

### 2.1 冻结不变

```text
wavelength / geometry / material / incidence
p6/h10 fine discretization
complex128
physical RHS
matrix-free split physical A6
streaming Fourier-DtN
Floquet/MPC identity
same_mesh_hcurl_pmg_v1_requalified auxiliary PC
right FGMRES
restart = 64
exact true-residual replacement every 64 steps
MPI = 1
threads = 1
```

### 2.2 明确禁止

本轮不得：

```text
运行新的 positive-only random/gradient/curl/checkerboard campaign
改变或扫描 restart=20/32/48/80/96/128
恢复 p3 physical coarse、p3 LU、p2/p4 coarse 或 Petrov coarse
实现 Krylov rank compression、GMRES-DR、GCRO-DR 或 residual-derived basis
切换 FBCGS、BCGSL、TFQMR、IDR 或其他 Krylov family
恢复 Robin、PML、Schwarz、sweep、interface Schur、GenEO、BDDC 或 HX 变体
改变 DtN mode inventory、quadrature、材料、mesh 或物理边界
提高 2,000,000,000 B 的 MPI1 process-tree hard line
```

本轮只允许把已有 fixed-restart infrastructure 扩展为：

```text
V18 checkpoint-2024 continuation
以及条件 fresh zero-start formal
```

不得新建重复数值核心。优先参数化现有 runner/checker；若确需新增薄 orchestration，必须
复用 `src/solvers/fullspace_memory_first_krylov.py` 和现有 physical bundle，不得复制
operator、PC 或 checkpoint 数值实现。

---

## 3. E0：历史证据冻结、checkpoint 与实现预审

### 3.1 冻结 authority

E0 必须记录并验证：

```text
V18 formal source SHA                 = a20008734c8bf0df03890bf35576c697eb0967f0
V18 closeout HEAD                     = eda919ab09897793bcb8792dc65ca8f30b5d6e23
checkpoint original origin            = absolute iteration 1000
latest V18 solution-only checkpoint   = absolute iteration 2024
latest checkpoint physical residual   = 0.27299642739429014
input SHA256                           = 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41
physical model SHA256                  = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
mode manifest SHA256                   = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
```

必须从 V18 raw manifest 读取并记录 checkpoint-2024 的实际 manifest SHA、solution shard
SHA、ownership、source SHA 和 artifact path；不得根据文件名猜测。

若 checkpoint-2024 缺失、hash 不闭合、ownership 不匹配或不是 solution-only，分类为：

```text
E0_BLOCKED_BY_CHECKPOINT_AUTHORITY
```

并停止。不得通过重跑 V18 前 1024 步静默重造该 checkpoint。

### 3.2 允许的实现修正

E0/E1 之前可运行 focused tests、compile 和 Ruff。若出现发生在任何 physical 数值测量前、
且可以唯一定位的 import/path/cache/offset/checker/provenance bug，允许窄修一次：

```text
保留旧失败 evidence
新 source SHA
新 fresh artifact root
不改变任何物理、数值参数或 Gate
```

数值 Gate、资源 Gate、nonfinite 或真实 stagnation 不能用“实现修复”名义重跑规避。

---

## 4. E1：checkpoint-2024 真实 physical 长 continuation

### 4.1 起点和总迭代账本

E1 从 V18 absolute iteration `2024` 的 solution-only checkpoint恢复。迭代账本同时保留：

```text
original checkpoint origin additional iteration = 0 at absolute 1000
V18 completed additional iterations              = 1024
E1 start absolute iteration                       = 2024
E1 total-additional hard cap                      = 32768 from absolute 1000
E1 remaining maximum                              = 31744 steps
```

`31744` 是 `64` 的整数倍。不得把新的 child-local counter冒充原始 absolute/additional
iteration。

### 4.2 恢复 Gate

进入长运行前必须：

1. 用相同 exact physical `A6` 和 RHS 重算 checkpoint-2024 true residual；
2. 重算值与 `0.27299642739429014` 的 relative difference 不高于 `1e-11`；
3. 验证 RHS、初值、action input 和 PC input finite、unchanged、slave-zero；
4. action 和 PC repeat relative 不高于 `1e-12`；
5. 确认 compiler children 已退出，solver child 不改变 parent-owned cold JIT cache。

任何一项失败即停止，不进入长运行。

### 4.3 求解合同

```text
KSP                         = right FGMRES
restart / cycle max-it      = 64 / 64
physical residual authority = full explicit true residual
residual replacement        = every 64 iterations
solution-only checkpoint    = every 1024 total-additional iterations
success                     = explicit true residual <=1e-6
hard cap                    = total-additional 32768
```

不得再设置 `4096`、`8192` 或其他中间 residual 必须达到某个绝对值的性能 Gate。

### 4.4 唯一允许的提前 stagnation stop

慢下降本身不是停止理由。只有完成至少两个完整的 4096-step block 后，才允许评价平台。
对每个 4096-step block定义：

```text
q_block = residual_at_block_end / residual_at_block_start
```

若连续两个完整 block 均满足：

```text
q_block >= 0.95
```

即连续两个 4096-step 区间各自都没有取得至少 5% 的净下降，则分类为：

```text
E1_PHYSICAL_STAGNATION
```

并停止。一个 block 未达该条件、局部非单调或仍有超过 5% 的净下降时，不得提前停止。

### 4.5 资源与生命周期 Gate

完整 parent watchdog 必须覆盖：

```text
fresh cold precompile children
solver setup
checkpoint restore
全部 continuation cycles
checkpoint writes
record/checker
release
```

硬要求：

```text
process-tree RSS < 2,000,000,000 B
process-tree swap = 0 B
all required /proc status readable
no orphan / no compiler descendant during solve
KSP and restart basis destroyed after every 64-step cycle
no RSS growth proportional to total iteration count
```

若达到 `1e-6`，分类为：

```text
E1_CHECKPOINT_CONTINUATION_PHYSICAL_NUMERICAL_PASS
```

这只证明同一 physical equation 从历史 checkpoint可以在固定内存下最终收敛，不得冒充
fresh zero-start official solve。

---

## 5. E2：条件 fresh zero-start physical formal

只有 E1 达到 `1e-6` 才允许 E2。E1 因 cap、stagnation、resource、swap、nonfinite、
breakdown 或 provenance失败时，E2锁定为 `not_run_by_E1_gate`。

### 5.1 固定配置

E2 必须从全新空 JIT cache 和零初值开始，使用与 E1完全相同的：

```text
p6/h10 physical model
exact matrix-free A6
streaming Fourier-DtN
same positive auxiliary PC
right FGMRES
restart = 64
residual replacement every 64
```

fresh run 的固定 hard cap为：

```text
max_it = 32768
```

每 `1024` 步保存 solution-only checkpoint。成功 Gate为：

```text
final full explicit physical true residual <=1e-6
complete process-tree RSS <2,000,000,000 B
swap=0
```

E1 的同一双 4096-step stagnation条件适用于 E2；不得因前几个周期比 E1慢而提前停止。

### 5.2 Fresh 结果分类

| 结果 | 分类 |
|---|---|
| `<=1e-6`、RSS/swap/provenance通过 | `E2_FRESH_PHYSICAL_NUMERICAL_PASS` |
| 到32768仍未达到且未触发其他停止 | `E2_FRESH_PHYSICAL_MAXIT_FAIL` |
| 连续两个4096-step block均 `q>=0.95` | `E2_FRESH_PHYSICAL_STAGNATION` |
| RSS/swap/nonfinite/breakdown/provenance失败 | 按真实 Gate 分类 |

不得把 E1 checkpoint PASS替代 E2 fresh结果。

---

## 6. E3：条件 release-before-recovery 与 official physical 输出

只有 E2 fresh numerical PASS 才允许 E3。

### 6.1 生命周期

求解完成后严格执行：

```text
保存最小 recovery packet和solution hash
→ 销毁 outer KSP / Krylov basis
→ 销毁 p1 development direct factor
→ 销毁 p3/p1 auxiliary matrices、solver stack和不再需要的DtN work
→ gc / PETSc cleanup / malloc_trim（若现有资格路径支持）
→ 记录RSS下降
→ recovery / postprocess
```

完整 solve + release + recovery 的同一 parent process-tree峰值仍须 `<2,000,000,000 B`，
swap仍须为零。

### 6.2 必须输出

```text
complex E
complex H
selected near-field samples
R / T / A
A_volume
energy closure
同一12个significant diffraction identities的power
同一12个identities的complex boundary amplitudes
完整input/resolved config/run manifest/source/physical/artifact hashes
```

先与已有 direct scalar authority 比较 `R/T/A/A_volume`。现有 direct authority若仍缺
complex E/H、near-field和同一12+12数组，必须明确标记：

```text
DIRECT_AUTHORITY_ARRAYS_MISSING
```

本轮不因该缺口自动重跑大型 direct authority。不得把缺少对照数组写成 iterative physics
错误，也不得把未完成的完整 observable comparison写成已通过。

---

## 7. E4：本轮最终决策

| E1 checkpoint continuation | E2 fresh | E3 recovery/physics | 本轮决策 |
|---|---|---|---|
| FAIL / blocked | not run | not run | 关闭 `positive pMG + fixed restart64 FGMRES` standalone physical lane |
| PASS | FAIL / blocked | not run | 证明 checkpoint eventual机制，但 fresh production未资格化 |
| PASS | PASS | resource或recovery FAIL | numerical PASS；完整workflow FAIL |
| PASS | PASS | outputs完成但direct arrays缺失 | discrete physical PASS with authority qualification |
| PASS | PASS | 全部数值、资源、物理和authority comparison通过 | p6/h10 MPI1 discrete Full3D physical PASS |

即使最后一行通过，也只能证明当前13.5 nm、p6/h10离散锚点；不得宣称 continuum
convergence、p6/h5通过、0.7 nm通过或2 TiB最终可行。

若 E1/E2失败，本轮不得自动切换到 FBCGS、TFQMR、低秩回收、PML或Schwarz。应在
`response_v18.md` 中基于真实 physical曲线、资源和失败位置，给出下一架构对比，等待新
review后再实现。

---

## 8. E5：证据、文档和停止要求

必须创建或更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/restart64_physical_eventual_v18.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/restart64_physical_eventual_v18.json
```

若 E2运行，还必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/restart64_physical_fresh_v18.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/restart64_physical_fresh_v18.json
```

若 E3运行，还必须创建最小 official output/authority manifest，不提交大型场数组，只提交
hash-bound compact evidence和artifact路径。

同时更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/development_progress.md
docs/task038_extra_full3d_iterative_0p7nm/response_v18.md
```

`response_v18.md` 必须逐项回答：

1. checkpoint-2024是否通过hash、ownership和residual reproduction；
2. E1实际执行步数、最终physical true residual和完整曲线；
3. 是否触发双4096-step stagnation、max-it或其他停止；
4. process-tree peak、swap、每周期KSP销毁和RSS随总迭代的趋势；
5. E2是否运行，fresh zero-start最终结果；
6. E3 release前后RSS、official E/H、R/T/A、A_volume和12+12状态；
7. direct authority arrays是否仍缺失；
8. 所有未运行项、失败项和证据路径；
9. selective merge建议；
10. 下一步是否需要新的physical PC架构。

完成后提交并推送同一分支，报告精确 HEAD、测试、工作树和artifact索引，然后停止等待审阅。

---

## 9. 最终审阅意见

V18 的短程 performance Gate 已真实失败，但它证明了三点：

```text
真实physical residual能够持续下降
restart64完整live set低于2GB
总迭代增加不会让固定restart basis无限增长
```

因此当前最小、最直接、且不偏离最终目标的下一步，不是继续做 positive surrogate，也不是
立即创建新 PC，而是把同一真实 physical equation运行到明确的最终正确性、长期平台或有限
hard cap。只有这一 physical eventual lane被真实结果关闭后，才有充分依据投入新的
wave-aware physical preconditioner架构。
