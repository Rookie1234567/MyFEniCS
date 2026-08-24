# Task038-extra Review V9 P8 closeout

## 结论先行

本轮把“memory-first”用于小规模正定辅助问题：求解器每 20 步释放旧 GMRES 基，只保留当前解，再用精确算子重算 `b-Ax`。它解决的是长 Krylov 历史可能持续占内存的问题，代价是固定总迭代上限内可能仍然收敛不够快。

P1 v2 实际完成 9/16 案：8 个 p2 案通过，p3/h50 MPI1/random 在固定 2000 步后显式真残差为 `0.01027838962263555`，超过 `1e-8`。因此按 V9 hard stop 分类为 `FAILED_AT_FIXED_MEMORY_ITERATION_CAP`，停止剩余 P1，并将 P2–P7 全部标为 `not_run_by_gate`。

这不是内存 Gate、swap Gate、ABI、JIT、生命周期或当前 checker 的失败：p3 的 PC legality、finite、input unchanged、primal constraint、process-tree/rank swap 均闭合；新 `check_v2` 的 `contract_errors=[]`，唯一 gate failure 是 final residual。下降趋势不能外推为 p-robust convergence，更不能外推 p6/h10 或物理问题。

## Review V9 §16 逐项回答

### 1. branch、HEAD、base、upstream、ahead/behind、worktree、ABI、threads 与资源身份

| 字段 | P8 草稿时事实 |
|---|---|
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| formal worker source | `891ef7fba8cb7d154ad9cac61d67652f02063fbb` |
| current pre-closeout HEAD | `24c0aa332d956313b1b484c81a91cfdcd5b5f07a` |
| current parent | `891ef7fba8cb7d154ad9cac61d67652f02063fbb` |
| base / origin-master merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| upstream | `origin/codex/20260820-task38-extra-full3d-iterative-0p7nm` at `599fba5a06a76b21db72d3c8d4e5908a753f0aed` |
| ahead/behind | `6/0` |
| worktree | pre-commit dirty only because this P8 draft新增/更新 docs/JSON；未改 Python，最终提交后的 HEAD 不能在本文自引用 |
| activation/ABI | qualified marker=1；Python 3.12.3；PETSc 3.19.6；DOLFINx 0.10.0.post2；Basix 0.10.0；SLEPc 3.19.2；complex128/int32 |
| threads | `MKL_NUM_THREADS=1`、`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1` |
| qualified Python | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |

P1 MPI1 直接使用 qualified Python，MPI2 使用同一 activation 的 `mpiexec -n 2`。P1 的 cycle RSS 是 rank-root process-tree ledger；MPI2 不包括 launcher。GNU `/usr/bin/time -v` 是单 worker 或 launcher 观察，不能冒充完整 process-tree/cgroup peak。共享 `/init.scope` 的 `13,799,424 B` 只作 non-dedicated diagnostic。

### 2. V8 M0 negative、orientation fix 和 scalar owner debt

V8 M0 attempt1/attempt2、9f orientation placement fix、scalar MPC/remote owner debt 均原样保留。9f fix 已由 focused/edge oracle 验证，但 M0 全体未闭合，仍是 research-only/pending follow-up，不提升 ordinary default。没有删除、覆盖或重分类旧 negative。

### 3. P0 checkpoint 与 pair-bound contract

P0 只归属于 `ba9016310d09c388a953fce93d9e71761343311f` fresh v2，结论为 PASS：checkpoint solution roundtrip、restart-boundary residual、next-cycle residual、PC linearity/repeat/input/primal 和 provenance 均通过。P0 compact 入口是：

`outcomes/memory_first_authority_contract.md`、`outcomes/records/memory_first_authority_v1.json`、`outcomes/records/memory_first_authority_checker_v1.json`。

P1 沿用 residual-based pair bound，但因 p3 hard stop 没有生成 16 案 aggregate。p2 已完成的四个 source 可以从 raw canonical shard 派生 pair 诊断，详见第 5 项；它不是 aggregate PASS。

### 4. P1 p2/p3 16 案的 final true residual、iterations、cycles、matvec/PC

| case/source | final explicit true residual | iterations | cycles | matvec / PC | checker |
|---|---:|---:|---:|---:|---|
| p2-mpi1/random | `1.1143047039371322e-10` | 80 | 4 | 83 / 84 | PASS |
| p2-mpi1/gradient | `2.400032697598806e-9` | 60 | 3 | 62 / 63 | PASS |
| p2-mpi1/curl | `8.598540668057664e-11` | 80 | 4 | 83 / 84 | PASS |
| p2-mpi1/checkerboard | `7.629665027029832e-9` | 60 | 3 | 62 / 63 | PASS |
| p2-mpi2/random | `1.0757562911789184e-10` | 80 | 4 | 83 / 84 | PASS |
| p2-mpi2/gradient | `4.070514353398614e-9` | 60 | 3 | 62 / 63 | PASS |
| p2-mpi2/curl | `9.798780243058586e-11` | 80 | 4 | 83 / 84 | PASS |
| p2-mpi2/checkerboard | `7.648588208477553e-9` | 60 | 3 | 62 / 63 | PASS |
| p3-mpi1/random | `0.010278389622635529` | 2000 | 100 | 2099 / 2100 | **FAIL fixed cap** |

剩余 7 个 frozen cases 均为 `not_run_by_gate`：

| case/source | status |
|---|---|
| p3-mpi1/gradient | `not_run_by_gate` |
| p3-mpi1/curl | `not_run_by_gate` |
| p3-mpi1/checkerboard | `not_run_by_gate` |
| p3-mpi2/random | `not_run_by_gate` |
| p3-mpi2/gradient | `not_run_by_gate` |
| p3-mpi2/curl | `not_run_by_gate` |
| p3-mpi2/checkerboard | `not_run_by_gate` |

P3 failure案的 `check_v2` 为 `8702c22a1965a9d776dc10b3bc6135930f8e8cf46c907d1df825ade63753ec5a`，record 为 `bb3017db9234c464e55dc6827d0c50d55441c77bb4471cd24a041b1af2f53e4c`。worker rc=0，checker rc=1；没有 execution/contract failure。完整每 200 步 residual history 保留在 ignored raw/record，未复制大数组到 Git。

### 5. 已完成 p2 MPI pair 的 exact source/action identity 与 residual-based bound

由于 P1 在 p3 failure 后按规则停止，完整 aggregate checker 没有运行。下表是从 p2 MPI1/MPI2 的 raw canonical shards 按 key 重新对齐得到的 `derived_not_aggregate` 事实；它说明已完成的 p2 pair 可计算的边界，但不把未完成 campaign 变成 16-case aggregate。

| source | source identity | RHS identity | `||A x1-A x2||/||b||` | dynamic bound | raw-derived result |
|---|---:|---:|---:|---:|---|
| random | `1.417734557397384e-15` | `1.6029978812022376e-15` | `5.0327071033835924e-11` | `2.2900770250948626e-10` | within bound |
| gradient | `1.6222171816489272e-15` | `9.78406907963663e-16` | `3.0847953901989848e-9` | `6.480548029404328e-9` | within bound |
| curl | `2.042338716606187e-15` | `1.4429255308456253e-15` | `5.928495332369234e-11` | `1.9397465203669334e-10` | within bound |
| checkerboard | `7.0527624724249594e-15` | `2.6435190265449354e-15` | `3.5263665345542788e-9` | `1.528825587902641e-8` | within bound |

这里的 RHS identity 是当前 positive `B_h` action/RHS identity：也就是同一 exact positive operator 对同一 source 得到的 dual RHS，在 MPI1/MPI2 canonical key 对齐后的相对差；它正是 V9 pair Gate 使用的量。双方 p2 final residual 都低于 `1e-8`。solution-vector 与 residual-vector 的相互 relative 只作诊断，未被用来否定这些 raw-derived action bounds。

### 6. p6/h10 完整 LOR/GAMG inventory、cold peak、retained 和 swap

未运行，状态为 `not_run_by_gate`。没有 p6/h10 LOR rows/NNZ、G/Pi/map bytes、PCGAMG retained hierarchy、cold setup peak 或 repeated-apply resource facts。p2 的约 123–155 MB 观察不是 p6/h10，也不是 `<2,000,000,000 B` 完整 workflow authority。

### 7. p6/h10 positive longrun 的完整 cycle-boundary residual history

未运行，状态为 `not_run_by_gate`。没有 p6/h10 random/gradient 的 5000 步、restart20 或 checkpoint history。

### 8. p6/h10 physical MPI1 最终 residual、全过程 peak、release/recovery 与 official physics

未运行，状态为 `not_run_by_gate`。V9 的 physical workflow/official recovery 是条件授权，但未满足 P1 前置 Gate；没有 exact volume+streaming DtN solve、`<=1e-6` residual、release-before-recovery、E/H、R/T/A、`A_volume`、channels 或 energy closure。

### 9. p6/h10 physical MPI2 最终 residual、全过程 peak、action bound 与 physics comparator

未运行，状态为 `not_run_by_gate`。没有 MPI2 physical RHS/A identity、15,000 步 solve、`rho_1+rho_2+...+1e-9` bound 或 physics comparator。

### 10. checkpoint/resume 与 segmented resource evidence

P0 使用过一次 20→40 checkpoint/restart，并通过 P0 roundtrip/residual/provenance Gate。P1 p2 案在 60/80 步前通过，因此 checkpoint count=0；p3 案使用 200 到 2000 的 10 个 solution-only checkpoint，但没有从 checkpoint 恢复后继续求解。所有 P1 worker 是单次连续运行；没有用分段 worker 隐藏 RSS 增长，也没有把分段结果写成完整 workflow resource PASS。

### 11. h5 是否运行与停止原因

未运行，状态为 `not_run_by_gate`。P6 的 p6/h5 预测/试跑必须以已资格化 p6/h10 measured inventory 和 P4/P5 前置结果为输入；P1 hard stop 使这些输入不存在，不能凭 p2 RSS 线性外推。

### 12. 更新后的 0.7 nm / 2 TiB optimistic/central/conservative 审计

未运行，状态为 `not_run_by_gate`。没有新的 p6/h10、p6/h5、external-channel、MPI duplication、hierarchy/recovery 或 postprocess measurements，因此没有新的 optimistic/central/conservative 数字。不能使用“p2/h50 观察 × 缩放”宣称 2 TiB 可行；完整 0.7 nm PDE 也未运行。

### 13. failed / not_run / controlled_stop 分类

| 分类 | 本轮事实 |
|---|---|
| `PASS` | P0 ba901631；P1 已完成的 8 个 p2 individual checker |
| `FAILED_AT_FIXED_MEMORY_ITERATION_CAP` | P1 p3-mpi1/random：2000 步、residual `0.01027838962263555 > 1e-8` |
| `not_run_by_gate` | P1 剩余 7 案、P2、P3、P4、P5、P6、P7 |
| `controlled_stop` | P1 在真实 numerical hard Gate 后停止后续，不是把未运行项写成失败或通过 |
| `evidence-layer history` | p3 旧 `check.json` 的非固定 checkpoint-status 误报；`check_v2` 已纠正，旧文件不覆盖 |

### 14. tests、commands、records、raw hashes 与 provenance

P1 worker 统一由 qualified activation 调用 `benchmarks.run_task038_full3d_lor_hx_memory_first --stage p1 --case ... --source ...`；MPI1 直接 Python，MPI2 `mpiexec -n 2`，每案有 `/usr/bin/time -v`、stdout/stderr、rank marker 和 raw shards。formal source、record、checker、raw root 都绑定 `891ef7f...`；P3 old/new checker SHA 如上。

本 P8 文档草稿引用的轻量 compact 是：

- `outcomes/records/memory_first_small_v2.json`
- `outcomes/records/memory_first_small_v2_checker.json`
- `outcomes/memory_first_small_v2.md`

P1 的 8 个 p2 record/check SHA、p3 record/check_v2/old-check SHA、raw path、rank marker SHA 和每案资源都在 compact 中逐项列出。旧 wrong-root/partial P1 attempt 与 V8/P0 raw 继续保留，但不混入当前 v2 campaign compact。旧 L2 record SHA 为 `0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3`，旧 one-apply `1.7348663090876784 > 0.45` 永久不重分类。

P8 轻量验证实际结果为：首次 sandbox PMIx singleton 在 collection 前环境启动失败（不是 test failure）；同一 qualified 命令在允许 socket 的执行环境得到 `41 passed, 1 skipped in 2.63s`。JSON strict parse（`allow_nan=false`）、逐项 raw record/check/marker SHA 与 path、自洽检查、相关 compileall 和 `git diff --check` 全部 PASS。不声称 CI 或 full pytest；不运行 worker、PDE 或新的 MPI campaign。

### 15. 下一步：关闭当前 family，等待新 review

当前 `multiplicative-v1 memory-first` family 因 p3 固定 cap 下没有 p-robust convergence 而正式关闭。它不是内存失败，也不是“把参数调大”就能自动通过的结果。不得自动增加 restart、调 omega/shift/GAMG、扫描 Krylov 或恢复 additive-v2；若要继续，必须由新 review 明确新的研究边界、输入和 Gate。当前 selective merge 只允许审阅 compact/docs 与既有 research evidence；不得把未资格化 family 合入 ordinary default。

## 旧结论永久保留

旧 L2 one-apply FAIL、旧 80-step performance FAIL、additive-v2 CLOSED、V8 M0 negative/orientation/scalar-owner debt，以及 P0 PASS 均未被本响应重分类。P1 的 8 个 p2 PASS 不能抵消 p3 failure，也不能替代 p6/h10、physical physics 或 2 GB workflow 证据。
