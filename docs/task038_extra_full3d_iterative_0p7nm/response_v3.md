# Task038-extra Review V3 response

## 结论先行

Review V3 的 D0、D1 已完成；D2 只完成了一次 MPI1 formal attempt，并在 rank-64
trace-harmonic construction 阶段受固定迭代 Gate 停止。D2 没有得到合法的 `Z`、
`AZ` 或 `E`，所以 D3/D4、T6-S 和所有后续 PDE 均未运行。这个结果是受控的
`controlled_negative`，不是资源硬停，也不是对 Full3D iterative 的永久数学否定。

本文中：`action` 指 exact full-space 算子对一个向量的作用；`Z/AZ` 是 coarse
校正方向及其 exact action；`E=Z^H A Z` 是最多 64×64 的小型 coarse operator；
`controlled stop/negative` 表示按预先写死的 Gate 停止并保留真实现场。它们都不能
被未运行的 rho 或内存数字替代。

## 1. 身份、分支和 worktree

| 项目 | 实际值 |
|---|---|
| repository | `Rookie1234567/MyFEniCS` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| base / merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| Review V3 reviewed/start HEAD | `9705e6e84a4b491a7d9fc87b20e12f1938232b07` |
| D2 formal/pre-evidence source HEAD | `cc8de60cc3e21b647aafb29ac9c10b46919823e7` |
| upstream at formal close | `9705e6e84a4b491a7d9fc87b20e12f1938232b07` |
| ahead / behind | `9 / 0` |
| current worktree | formal start clean；docs closure前当前5项：2个 tracked 修改（本文件外的两个 outcomes 文档）+ 3个 untracked（两份新文档与 D2 worker record） |
| docs final commit | 文档不能自引用未来 commit；本回合未 commit/push，最终 handoff SHA须由交付报告给出 |

ABI preflight 通过：`_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`，Python 3.12.3，
qualified `.venv` resolved bin 为 `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin`，
Open MPI 4.1.6，PETSc scalar `complex128`，PETSc int `int32`，petsc4py、slepc4py、
dolfinx、Basix 和 mpi4py 均来自 Linux ABI 栈，`OMP/OPENBLAS/MKL=1`。preflight 时
`MemAvailable=13,174,740 kB`，`SwapTotal=41,943,040 kB`，`SwapFree=41,925,780 kB`，
磁盘可用约 879 GB。

## 2. Candidate C 与 standalone transmission lane

Candidate C 的 fixed second-order local impedance 源码和既有负证据保留，但分类为
`DO_NOT_RERUN / DO_NOT_OPTIMIZE / DO_NOT_MERGE` research archive。它不是数学上
永远无效；Review V3 只是在当前 arbitrary-3D、p6、内存和开发预算约束下关闭这条
研究线。没有修改 Candidate C，不做 JIT 预热、系数扫描、更多阶数或更高硬上限。

Candidate B 对当前 mixed Si–Si / Si–air interior interface 仍是
`NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED`：T3 资格化的
是 exterior top/bottom dynamic DtN，不是 mixed interior modal transmission。

Candidate A 不再作为 standalone production preconditioner；若未来被授权，只能保持
完整冻结的 one forward+backward smoother oracle：two slabs、transmission、local
GMRES restart/max-it=8/8 和所有参数不变。A 的历史结果仍为 physical RHS
`rho=0.8145890334049838 > 0.60`、gradient `rho=0.8889127715646881 <= 0.90`，
不是本次 D2 结果。

## 3. D0–D4 状态矩阵

| stage | planned | actual | classification |
|---|---|---|---|
| D0 | 关闭旧 transmission family，建立粗空间字节预算 | 完成；A/B/C 分类和 rank ladder 记录齐全 | `PASS / derived preflight` |
| D1 | p2/p3 trace-harmonic small oracle | p2/p3 MPI1/MPI2 四 case individual 与 aggregate PASS | `PASS / frozen oracle` |
| D2 | p6/h10 rank16/32/48/64 owner-local Z/AZ/E | MPI1 只到 slab0 interior CG；未得到 Z/AZ/E | `CONTROLLED_NEGATIVE` |
| D2 MPI2 | cross-MPI packet identity | 未运行 | `not_run_by_D2_rank64_hard_stop` |
| D3 | coarse-only 与 two-level contraction | 五类 source 均未运行 | `not_run_by_D2_rank64_hard_stop` |
| D4 | 条件 T6-S screen | 20/100/150/200 均未运行 | `not_run_by_D2_rank64_hard_stop` |

## 4. D0 内存算术与 rank ladder

`N=173802`，一个 complex128 full-space vector 的精确大小为：

```text
173802 × 16 B = 2,780,832 B
```

固定 rank ladder 只允许 `16/32/48/64`：

| rank r | Z+AZ exact bytes | MiB（1024²） |
|---:|---:|---:|
| 16 | 88,986,624 | 84.864 |
| 32 | 177,973,248 | 169.729 |
| 48 | 266,959,872 | 254.593 |
| 64 | 355,946,496 | 339.457 |

coarse metadata/work budget 为 `<=64,000,000 B`，所以 D0 的 rank64 derived total
为 `355,946,496 + 64,000,000 = 419,946,496 B`。这是 exact arithmetic 加 budget
上界，分类为 `derived/budget`，不是 D2 measured retained pass。owner-local sharding
只让每个 rank 保存自己的 Z/AZ 行；禁止每 rank 复制完整 basis、FE-sized numeric
allgather、global AIJ/Schur 和 growing sparse factor。

## 5. D1 local eigenproblem 与 algebra authority

每个 slab 独立使用固定辅助能量：


\[
B_i(u,v)=\int_{\Omega_i}\mu_r^{-1}\,\operatorname{curl}u\cdot
\overline{\operatorname{curl}v}\,dx
+k_0^2\int_{\Omega_i}|\epsilon_r(x)|u\cdot\overline v\,dx .
\]

真实 broken tangential facet mass 是 `M_{Gamma,i}`。固定 trace 后，harmonic
extension 只解 slab interior block 的 B_i 最小能量延拓，outer shell rows 不被
伪装成 interior unknown。由 extension `H_i` 形成：

```text
K_i = H_i^H B_i H_i
K_i q = lambda M_Gamma,i q
```

D1 取每侧最小特征值，按确定性顺序和相位保存最多 16 个；Hermitian defect、
eigen residual、mass normalization、repeat 和 R/P adjoint 都通过规定阈值。D1
允许 p2/p3 的小型 assembled oracle，但它不是 p6 production path；MPI2 的正式
边界是 distributed B/M action identity，不能把 serial dense algebra 搬到 p6。

## 6. Harmonic extension、orientation、phase 和 MPI identity

restriction/prolongation 复用已资格化的 owner-active-row Euclidean adjoint：
`<R x,y> = <x,P y>`。shared trace 在 PoU 中固定 0.5，非重叠 slab interior 为 1；
这只是 coarse vector 嵌入的搬运/合并规则，不是新物理权重。

所有 source 和 action 都沿 finalized MPC 的 full-space contract 走：primal source
使用 `full_fe` canonical role，B/M action 使用 `full_fe_dual` role；slave rows 不
作为独立 trace carrier，Floquet phase 只由 finalized MPC 施加一次。canonical key
来自物理实体/坐标和已资格化 extractor，而不是 local row、rank 或 MPI size，因此
MPI1/MPI2 可以按 key 对齐而不 numeric allgather。

D1 四 case 的 source/B/M cross-MPI relative L2 均 `<=1e-12`，missing/extra/duplicate
均为 0；process-tree peak 没有测量，不能扩展为资源资格。

## 7. D2 的 Z/AZ/E 与 coarse solve 身份

D2 本应只构造一次 rank64 owner-local `Z`，逐列用 exact physical action 得到 `AZ`，
再用小型 `E=Z^H A Z`。`Z` 不从 physical RHS、R3 residual 或 checkpoint 拟合；
coarse solve 若进入后续只允许最多 64×64 的小型 oracle，不代表 0.7 nm production
global coarse solver。

本次 formal 在 `trace_basis_build` 中固定的 interior CG 未收敛：

| item | actual |
|---|---|
| attempt | p6/h10 MPI1，唯一一次 |
| wall / monotonic | `557.385958733 s` / `510.287976466 s` |
| failure | slab0 interior CG `-3` = PETSc `KSP_DIVERGED_ITS` |
| fixed iteration | `max_it=500` 已用尽；不增加 steps |
| marker sequence | `preflight → mesh_mpc_topology → trace_basis_build → failure` |
| Z/AZ/E | 均未得到，online action/canonical evidence 未运行 |

因此没有 D2 algebra、condition、rank prefix、canonical MPI identity 或 retained-byte
Gate 可以报告。D2 worker/checker/runner 因 rank64 未资格化归类
`research-only / do-not-merge`，D1 小 fixture oracle 不受影响。

## 8. D3 五类 source 的 coarse-only/two-level rho

D3 原计划先看 coarse-only 是否相对 identity 有至少 20% 的明确改善，再组合冻结的
Candidate A。由于 D2 未得到 Z/AZ，所有数值项均未运行：

| source | coarse-only rho | Candidate A + coarse rho | required Gate |
|---|---:|---:|---:|
| physical RHS | not run | not run | `<=0.60` |
| gradient-dominated | not run | not run | `<=0.90` |
| curl-dominated | not run | not run | `<=0.90` |
| checkerboard/high-frequency | not run | not run | `<=0.75` |
| R3 qualified long-tail residual | not run | not run | `<=0.70` |

`online <2 GB` 也没有测量；不能把 D0 算术或 D2 construction peak 当作 online Gate。

## 9. Candidate A 的限定身份

Candidate A 只能是完全冻结的 one forward+backward local smoother oracle。它不能改
slab 数、transmission 符号、GMRES 8/8、restart、overlap 或 inner steps；不能以
gradient 的历史 PASS 推导 physical/long-tail PASS。D3 若未来重新授权，必须把 A
作为固定局部步骤，单独测 coarse-only 和组合后的真实 residual，不能称 T4 的一个
boundary apply 就是完整 outgoing data。

## 10. build/JIT 与 online process-tree 资源

D2 watchdog 保存 513 个 samples，process-tree peak 为 `3,013,468,160 B`，峰值
阶段是 `trace_basis_build`；process-tree swap 为 `0 B`，worker natural exit，rc=1。
这是 construction/JIT 阶段的 measured resource fact，未进入 online AZ/E。

因此没有 online process-tree peak，也没有完整 workflow peak。D0 的
`419,946,496 B` 是 derived/budget；D2 的 3.013 GB 不能被称为 D3 online，也不能
被称为完整 PDE 峰值。

## 11. 是否真正低于 2 GB

没有。当前批次没有取得 complete-workflow `<2,000,000,000 B` 资格，也没有取得
online `<2 GB` 测量。不能用既往 Candidate A 的 cold/warm-like 数字或 D0 的字节
算术代替本次 D2/D3 evidence。未来若重新授权，必须分别测 construction/JIT 与
online correction，并以两者最大值判断 complete workflow；不得隐藏 cold build。

## 12. T6-S checkpoints

D4/T6-S 未启动，因此没有 20、100、150、200 的 true residual、wall、RSS 或 swap。
这些全部为 `not_run_by_D2_rank64_hard_stop`，不能写成 0、通过或失败。T6-S 原定
要求 20/100/200 residual Gate 与 150→200 至少 20% improvement，但本轮没有
coarse basis 和 source action 可供执行。

## 13. T6-F、official observables 和 0.7 nm 边界

T6-F、official E/H、R/T/A、`A_volume`、EH/RTA、T7 h-scaling、T8 0.7 nm capacity
audit、T9 closeout 和 full 0.7 nm PDE 均未运行。未运行项保持
`not_run_by_D2_rank64_hard_stop` 或 `not_run_by_R4/D2_gate`，不因本轮有负结果而
伪造物理失败。

## 14. measured / derived / failed / controlled / not_run 分类

| 类别 | 本轮事实 |
|---|---|
| measured | ABI preflight；D2 marker/wall/monotonic elapsed；watchdog 513 samples；process-tree peak `3,013,468,160 B`；process-tree swap `0 B`；natural exit rc=1 |
| derived | full vector `2,780,832 B`；rank ladder Z+AZ bytes；D0 rank64 total `419,946,496 B` |
| budget | coarse metadata/work `<=64,000,000 B`；retained `<=424,000,000 B` |
| failed | slab0 fixed interior CG convergence；error `KSP_DIVERGED_ITS (-3)` after 500 steps |
| controlled_negative | D2 MPI1 worker record `classification=controlled_negative` |
| controlled_stop | 未发生 12 GiB/swap/watchdog termination；本次是 natural exit |
| not_run | D2 MPI2、Z/AZ/E、D3 五 source rho、online `<2 GB`、D4/T6-S、T6-F/EH/RTA/T7–T9/full 0.7 nm |

独立 checker 对 negative backfill 返回 `passed=false`，错误是
`record schema or stage is invalid`。这是 fail-closed，不是 checker 通过；缺失成功
字段不能变成 PASS。

## 15. 下一轮授权建议

本轮不建议授权 T6-F，也不建议把 D2 rank64 当作已通过后继续 D3。首先需要新的
review 明确是否值得重新研究 slab0 interior CG 的 contract；若要继续，必须在新
clean source、明确的一次窄 implementation defect 边界下重新审查，不能直接增加
inner steps、改变 solver 参数或原样重跑。若 rank64 仍不能闭合固定 algebra/memory
Gate，则关闭当前 adaptive coarse family；Candidate C 仍保持 do-not-merge。

## 16. selective merge、文件与证据索引

### selective merge 分类

| group | 内容 | 当前建议 |
|---|---|---|
| production numerical/core | 已冻结并通过的 T1–T4 exact action、dynamic DtN、interface topology | 保留既有已审查范围；不因 D2 negative 改 ordinary default |
| reusable oracle | D1 p2/p3 trace-harmonic small-fixture oracle | 可保留为 oracle evidence，不等同 p6 production coarse |
| D2 numerical/runner/checker | `fullspace_trace_harmonic_distributed.py`、`fullspace_adaptive_coarse.py`及 D2 runner/checker | `research-only / do-not-merge`，rank64 未资格化 |
| research archive | Candidate C second-order impedance、旧 standalone sweep负证据 | `DO_NOT_RERUN / DO_NOT_OPTIMIZE / DO_NOT_MERGE` |
| compact evidence/docs | 本 response、D2 negative record、outcomes 文档和 hash-bound watchdog descriptors | 作为审阅证据保留；raw 大文件继续 ignored |
| forbidden | T6-F、T7–T9、full 0.7 nm、master integration、Candidate C rerun | 不执行 |

### 本回合实际文件

只编辑/新增以下文档，未改 Python、未改 solver、未改 Candidate C：

- 更新 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/adaptive_coarse_oracle.md`；
- 更新 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md`；
- 新建 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/two_level_contraction.md`；
- 新建 `docs/task038_extra_full3d_iterative_0p7nm/response_v3.md`；
- 保留 D2 worker record，不覆盖 raw/compact/log。

### Evidence paths and hashes

| artifact | path | SHA-256 |
|---|---|---|
| worker record | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/d2_worker_p6_h10_mpi1_v1.json` | `ef98ba1e7c478b6c6a8297baf599aa34c1849188f3b1668f0cdaf63e4e95635d` |
| watchdog raw | `benchmarks/artifacts/task038_extra_full3d_iterative_d2/cc8de60/p6_h10_mpi1_v1/watchdog.raw.json` | `4313d5a3112db849a1b80c2ea2adae6fbe3c30f47da554c48ff9771a7c620a10` |
| watchdog compact | `benchmarks/artifacts/task038_extra_full3d_iterative_d2/cc8de60/p6_h10_mpi1_v1/watchdog.compact.json` | `53d6b314af83fafc8a0d13f14542229072869139914e031573574a262c877d7d` |
| worker log | `benchmarks/artifacts/task038_extra_full3d_iterative_d2/cc8de60/p6_h10_mpi1_v1/worker.log` | `c5dd34f422162cd4a5dc84a3e01052e71427292d905f5e95f20d2e5b9e9f133b` |

raw 文件均为 ignored artifact；compact worker record 在 outcomes 的预定 tracked
路径中，但当前文档 closure 未提交，故 `git status` 暂显示为 untracked。没有把
大 raw、mesh、JIT 或 watchdog samples 加入 Git。

### Tests and validation

源码收口验证为 `test284/285/286=25 passed`，并通过 compileall 与 `git diff --check`；
docs closure 验证为 `test_26=14 passed`、JSON parse、Markdown fence/table/link 和
`git diff --check` pass。以上均为本地检查，不声称 CI；本回合未重跑数值/PDE，
仅运行了 doc contract pytest。
