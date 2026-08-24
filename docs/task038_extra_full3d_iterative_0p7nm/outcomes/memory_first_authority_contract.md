# Memory-first P0 authority contract

## 这一步在验证什么

这里的“memory-first”（先控制内存生命周期）是指：求解器每完成固定的 20 步，就销毁这一轮的 Krylov 基和 KSP，只保留一个解向量快照，再从快照继续。这样可以避免把很长的 Krylov 历史留在内存中。

“checkpoint”是第 20 步的解快照；它只保存每个 rank 自己拥有的 solution shard，不保存 basis、action 或 residual 向量。“explicit true residual”是用精确的矩阵自由算子重新计算的 `b-Ax`，不是 PETSc 报告的近似残差，因此是本轮正确性依据。

## P0 范围与结论

| 项目 | 结论 |
|---|---|
| 固定算子 | production multiplicative-v1 HX；未启用 additive-v2 |
| formal case | p2 / h50 / random / MPI1 |
| P0 结论 | **PASS（以 ba901631 fresh v2 为 authority）** |
| 后续资格 | 允许进入 P1 评审/实现 |
| P0 closeout 当时未做 | P1、p6、PDE、完整 0.7nm workflow 均未运行；P1 后续状态见本文末尾 |

## 两次 formal attempt

第一次 attempt 必须保留，因为它暴露了证据层问题；它不是数值算法失败，也不能重分类为 PASS。

| attempt | worker/checker | 结果边界 | 证据摘要 |
|---|---:|---|---|
| `cc0f322` | rc `0` / `1` | `CONTROLLED_STOP_EVIDENCE_LAYER_FAILURE` | 10 个 artifact logical name/role contract errors；4 个 shared-cgroup swap 误判；process-tree swap=`0 B`，不是数值失败 |
| `ba901631` | rc `0` / `0` | **PASS** | artifact 命名闭合；shared `/init.scope` 不再被当作 dedicated；所有 P0 checker contract/Gate 通过 |

第一次 attempt 中记录的 `/init.scope` 原始 `13,799,424 B` 只属于共享 cgroup diagnostic。它不能作为 dedicated job swap：正式 process-tree/rank swap=`0 B`，`dedicated=false`，`job_no_swap=true`。

## ba901631 fresh v2 结果

### provenance 与环境

| 字段 | 实测值 |
|---|---|
| source SHA start/end | `ba9016310d09c388a953fce93d9e71761343311f` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| clean start/end | `true / true` |
| activation / MPI / threads | qualified=1 / MPI1 / MKL=1, OMP=1, OPENBLAS=1 |
| PETSc ABI | complex128 / int32；PETSc 3.19.6；DOLFINx 0.10.0.post2 |

### P0 Gate

| 指标 | 实测 | 限值 | 结果 |
|---|---:|---:|---|
| checkpoint solution roundtrip | `0.0` | `1e-13` | PASS |
| restart-boundary true residual relative | `0.0` | `1e-12` | PASS |
| next-cycle first residual relative | `0.0` | `1e-11` | PASS |
| PC linearity | `4.345224260821012e-16` | `1e-12` | PASS |
| PC repeat | `0.0` | `1e-13` | PASS |
| PC input unchanged | `0.0` | `0` | PASS |
| finite / primal slave constraint | `true / 0.0` | finite / `1e-12` | PASS |

### 四个 cycle boundary

`reason=-3` 表示正常的 restart-20 周期结束；不是异常 breakdown。

| 路径 | 区间 | explicit true residual | matvec / PC | process-tree RSS | process-tree swap |
|---|---:|---:|---:|---:|---:|
| production | 0→20 | `2.885866622208196e-4` | `20 / 21` | `139026432 B` | `0 B` |
| restored restart | 20→40 | `1.688759138396504e-6` | `21 / 21` | `141615104 B` | `0 B` |
| continuous reference | 0→20 | `2.885866622208196e-4` | `20 / 21` | `143278080 B` | `0 B` |
| continuous reference | 20→40 | `1.688759138396504e-6` | `21 / 21` | `143278080 B` | `0 B` |

GNU `/usr/bin/time -v` 的单进程观察为 wall=`7.66 s`、max RSS=`125104 kB`、Swaps=`0`。本次 shared `/init.scope` 的 dedicated 字段为 `dedicated=false`、swap=`null`；不能把单进程 GNU time RSS 当作 process-tree 峰值 authority。

## 证据索引

轻量 compact 位于：

- `outcomes/records/memory_first_authority_v1.json`
- `outcomes/records/memory_first_authority_checker_v1.json`

两次 raw attempt、record、check 和 manifest 的路径与 SHA256 均在 compact 中逐项绑定；compact 不复制 raw 数值向量。旧 `cc0f322` evidence 原样保留，P0 PASS 只归属于 `ba901631` fresh v2。

## 边界

P0 PASS 表明固定 p2/h50/MPI1 的内存生命周期、checkpoint/restart、residual authority、PC legality 和 provenance 合同闭合。它不表示 P1、p6、MPI2、PDE 或完整 0.7nm 计算已经通过；这些项目仍等待后续 Review 授权与独立 Gate。

## V9 P1 后续状态

V9 在保持上述 P0 PASS 和旧负证据不变的前提下，实际运行了 P1 v2 的 9/16 个 small cases：8 个 p2 案通过，p3/h50 MPI1/random 在固定 2000 步后未达到最终真残差限值。该案的独立 `check_v2` 只有数值 Gate 失败，最终显式真残差为 `0.01027838962263555 > 1e-8`，因此当前 memory-first multiplicative-v1 family 按 V9 关闭；剩余 7 案及 P2–P7 均为 `not_run_by_gate`。详细事实见 `outcomes/memory_first_small_v2.md`、`outcomes/records/memory_first_small_v2.json` 和 `outcomes/records/memory_first_small_v2_checker.json`。

这不是内存或 swap 失败：已运行案的 process-tree/rank swap 与 GNU time `Swaps` 均为 0；共享 `/init.scope` 的 `13,799,424 B` 只作 non-dedicated diagnostic，不能当作资源 Gate。失败含义是固定内存、固定 `restart=20` 和 `max_it=2000` 下，p3 random 的残差仍不够小，不能从下降趋势外推 p-robust 收敛或 p6/h10 物理可行性。
