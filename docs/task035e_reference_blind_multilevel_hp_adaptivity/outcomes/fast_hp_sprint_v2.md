# Task035e Fast h/p Sprint V2 结果

## 1. 结论

本轮按 V2 执行，V1 与 V2 冲突处以 V2 为准。既有 full
`p-shadow` 被复用为 development current `C1`，没有重新求解；随后一次只运行
一个 MPI8 PDE，共完成四个新 candidate：

```text
C1 full-p (existing)
├── C2 broad-p = rejected
└── H2 h-check = accepted, but h-stagnation
    ├── P3 broad-p = rejected
    └── H3 h-check = accepted, but h-stagnation
```

`H3` 是本轮最佳 development current，直接复用其已求解结果，不再重跑。
它相对 cycle-0 current 的 59-goal normalized RMS true error 下降
`27.152189%`，因此分类为 `PARTIAL_PROGRESS`，但不是最终解：

- `0/59` 目标进入 reference tolerance；
- `D2=198.779433`、`Dinf=1470.213566`，远未达到
  `D2<=0.5`、`Dinf<=1.0` 的 response-stable Gate；
- actual conforming active FE DoF 为 `105,857`，高于既有
  `90,000` 目标；
- H3 只获得 cgroup 强制的 simultaneous `<=11 GiB` 上界，未获得精确
  PSS/USS 峰值。

两条 broad-p candidate 均使 E2 恶化约 `9.22%`；两条 h candidate
虽按 V2 Gate 被接受，但各自只改善约 `0.02%`。因此触发 V2 第 7 节停止条件
6：p 与 h 两条 lane 均连续停滞。停止原因不是 PDE 数量上限或时间盒耗尽。

本结果分类固定为：

```text
REFERENCE_VISIBLE_DEVELOPMENT_SPRINT
reference_blind_credit = false
formal_hidden_audit_credit = false
```

## 2. 身份与执行边界

- 执行分支：
  `codex/20260728-task35e-reference-blind-multilevel-hp-adaptivity`
- 本轮开始时 documentation HEAD：
  `7f325e6071d60c543e2516b94d16ea098ec38913`
- 所有新 PDE 的 numerical source：
  `f1ba5627f163da54fa383b43be58fd38c0da7bc9`
- ABI：MPI8、PETSc `complex128` / `int32`
- ordinary default 未修改，数值 kernel 未修改
- Path B、p7、level-3、hidden audit、Hybrid、迭代法和 matrix-free 均未运行
- 未新增 package、campaign、schema、receipt 或 watchdog

V2 覆盖 V1 的 heavy-PDE 数量上限、固定 P2/P3/Hcheck/combined 顺序、
按 PDE 数量停止规则和 blocker 时间；V1 的 59-goal、reference-visible
分类、数值 Gate、资源口径和禁止大型框架等规则继续有效。

`C1` 的 FE coefficient snapshot 没有被既有实现持久化。为避免重算 C1：

- C2 的实际 solver plan 由 C0 plan 加 C0→C1 与 C1→C2 的 action union
  生成；其 numerical solver content 与顺序生成的 C1→C2 plan 完全相同；
- H2、P3 和 H3 使用同一 numerical source 上的薄 task-local worker，
  直接求解各自 immutable plan；
- worker 只做 clean-source、MPI/ABI、plan hash 和 immutable output
  preflight，然后调用已有 production solver；它不实现新的数值 kernel。

## 3. 59-goal 与结构结果

表中的 rows 包含 80 个 DtN auxiliary rows；active DoF 是 actual conforming
active FE DoF，不是 raw broken DoF 或完整 p6 container DoF。

| ID | parent | lane / decision | leaves；p4/p5/p6 | active / raw DoF | rows / matrix NNZ / factor NNZ | E2 / Einf | D2 / Dinf | 相对 parent E2 | wall s |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| C1 | C0 | p；复用既有结果并 development-only 接受 | 160；15/138/7 | 62,284 / 64,180 | 20,564 / 11,084,868 / 43,034,248 | 860,562.378 / 5,764,876.171 | 322,847.128 / 2,170,831.145 | +27.120392% | 228.683 |
| C2 | C1 | broad-p；拒绝 | 160；14/132/14 | 64,115 / 66,011 | 20,756 / 11,267,444 / 43,591,790 | 939,902.026 / 6,692,108.476 | 139,647.333 / 927,232.305 | -9.219512% | 211.954 |
| H2 | C1 | h；接受，h-stagnation | 216；15/180/21 | 85,605 / 93,221 | 26,910 / 15,439,810 / 56,149,846 | 860,377.728 / 5,763,865.068 | 201.149 / 1,168.002 | +0.021457% | 426.486 |
| P3 | H2 | broad-p；拒绝 | 216；15/172/29 | 87,385 / 95,001 | 26,990 / 15,506,754 / 55,087,818 | 939,767.088 / 6,686,483.133 | 138,279.733 / 922,618.065 | -9.227268% | 363.131 |
| H3 | H2 | h；接受，h-stagnation | 272；15/236/21 | 105,857 / 113,529 | 32,544 / 17,928,674 / 64,509,638 | 860,186.917 / 5,762,394.854 | 198.779 / 1,470.214 | +0.022178% | 441.610 |

四条新 PDE 的 solver wall 合计 `1443.180788 s`，约 `24.05 min`。
所有四条均满足：

- full explicit true residual `<=1e-9`；
- energy、Floquet、hanging、MPI8 Gate；
- MUMPS direct solve 成功；
- zero swap；
- exact-sequence inactive-row-free variable-p / local-h 路径；
- ordinary default unchanged。

H3 的 parent 仍是 H2；P3 已被拒绝，没有成为 H3 的离散起点。

## 4. 分类误差

| ID | power E2 | amplitude E2 | totals E2 | fields E2 |
|---|---:|---:|---:|---:|
| C0 | 2,267,306.684 | 14,502.047 | 32,925.748 | 86.0901 |
| C1 | 1,652,381.126 | 12,337.220 | 23,681.047 | 83.1866 |
| C2 | 1,804,776.220 | 12,225.951 | 15,968.011 | 83.1317 |
| H2 | 1,652,026.544 | 12,335.616 | 23,679.494 | 83.1863 |
| P3 | 1,804,516.906 | 12,234.586 | 15,990.328 | 83.1507 |
| H3 | 1,651,660.154 | 12,334.490 | 23,671.429 | 83.1956 |

两次 broad-p 都改善了 totals，且 amplitude 略有混合信号，但 power
误差的恶化主导了 59-goal aggregate E2 和 Einf，因此不得只根据 totals
将它们提升为 current。两次 h-check 对 power/totals 的改善极小，fields
在 H3 中反而轻微恶化；h lane 没有形成可用收敛斜率。

## 5. 内存口径

| ID | simultaneous RSS MiB | PSS / USS MiB | 非同时 rank 历史峰值和 MiB | swap | authority |
|---|---:|---:|---:|---:|---|
| C1 | 8,345.027 | 6,955.710 / 6,847.707 | 7,975.352 | 0 | v28 formal watchdog timeline |
| C2 | 9,122.090 | 7,539.798 / 7,324.938 | 8,769.879 | 0 | formal watchdog |
| H2 | `<=11,264` bound | not measured | 10,466.348 | 0 | successful systemd cgroup, `MemoryMax=11 GiB` |
| P3 | `<=11,264` bound | not measured | 10,483.523 | 0 | successful systemd cgroup, `MemoryMax=11 GiB` |
| H3 | `<=11,264` bound | not measured | 12,087.977 | 0 | successful systemd cgroup, `MemoryMax=11 GiB` |

H3 的 `12,087.977 MiB` 是各 rank 在不同时间的历史峰值之和，不是
simultaneous whole-job peak，不能与 11 GiB cgroup 上限直接比较。
H3 在 `MemoryMax=11 GiB`、`MemorySwapMax=0`、`OOMPolicy=stop` 下成功退出，
因此只证明 simultaneous peak 有 `<=11 GiB` 的强制上界。由于 transient
cgroup 退出前没有采样 `memory.peak`，不得把 `11 GiB` 写成实测峰值，也不得
补造 PSS/USS。

## 6. V2 问题的回答

1. 既有 full p-shadow 可以作为 development C1，且无需重算；但它不获得
   blind credit。
2. 第二层和 H2 后的 broad-p 均没有继续降低 59-goal true error，反而分别
   恶化 `9.219512%` 和 `9.227268%`。
3. h-refinement 只产生 `0.021457%` 与 `0.022178%` 的微弱改善，属于连续
   h-stagnation，不是明显收益。
4. accepted h steps 的 `D2/Dinf` 约为 `200/10^3`，没有接近
   `0.5/1.0`，因此没有 response stability。
5. H3 在 11 GiB hard cap 下完成，但其精确 whole-job peak 和 PSS/USS
   未测；同时 active DoF 已达 `105,857`，不能称为 resource-efficient。
6. 本轮得到了一条可复核的实际 h/p 序列，但没有得到 59/59 收敛解。

因为已经命中正式 lane-stagnation 停止条件，即使实际 wall time未达到 6
小时，也没有继续无目的扫描。额外工作只限于离线校正结构口径、绑定 raw
hash、保存实际 plan 和归档已使用的薄 worker；没有借机扩建框架。

## 7. Evidence

- Compact authority：
  `benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/fast_hp_sprint_v2_compact_v1.json`
- 实际 plan/action：
  `benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/fast_hp_sprint_v2_plans/`
- 已使用的薄 worker：
  `benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/fast_hp_sprint_v2_candidate_worker.py`
- ignored raw root：
  `benchmarks/artifacts/task035e/fast_hp_sprint_v2_f1ba5627/`

Compact authority 绑定每个 run summary、candidate output、evaluation、
watchdog/cgroup authority、selection、plan/action 和本报告输入 authority 的
SHA-256。所有 controlled negatives 原样保留。
