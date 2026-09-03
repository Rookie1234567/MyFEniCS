# Task038-extra Review V16 response：最终 authority

## 当前 authority 总览

| 阶段 | 当前结论 | 证据边界 |
|---|---|---|
| Q0 | PASS | physical p-coarse preflight；不是 official physics |
| Q1.1 | PASS | 同一 h50 mesh 的 p6/p3 physical action identity；MPI1、MPI2、pair |
| Q1.2 | PASS | p3/h50 physical inner；MPI1、MPI2、pair |
| Q2 | `Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL` | p6/h10 checkpoint correction 的真实数值 Gate 失败 |
| W0 | `W0_INTERFACE_RANK_CAPACITY_FAIL` | interface rank/byte authority 与容量 major unknown |
| Q3–Q6 | locked/not_run | Q2 失败后未进入 |
| W1–W4 | locked/not_run | W0 FAIL 后未进入 |
| official physics | not_run | 未形成 official E/H、near-field、R/T/A 或 recovery 结果 |

总体分类为 `V16_Q_AND_W_CLOSED_BY_REAL_GATES / NOT_QUALIFIED`。下方保留首次
Q1 source-authority controlled-stop 的完整历史；后续 Q1.1/Q1.2 PASS、Q2 数值
失败和 W0 关闭均按实际 raw/checker 追加，未覆盖或重分类旧 negative。

---

## 历史首次受控停止（永久保留）

| 阶段 | 结果 |
|---|---|
| Q0 | PASS；reference commit 12252290c3d9ec51713094f08c335f24ce172a5b |
| Q1 | CONTROLLED_STOP_PREMEASUREMENT_PROVENANCE / NOT_QUALIFIED |
| Q2–Q6 | not_run |
| W0–W4 | not_run_by_trigger_not_met |

Q1 core 已在 clean core commit 6edf5f5c1255185052a2a5d5fb8dd422f3238f04 实现，但没有启动 formal。V16 固定的
r3_long_tail_derived 需要 p6/h50 source，而唯一旧 R3 authority 是 p6/h10。
当前 F1 p3/h50 只有 mesh=[4,4,3]、rows=4641、active dual packets=4176、
slaves=465；旧 T2 p3/h50 为另一几何、rows=3018；p6/h50 canonical inventory
不存在。

旧 R3 compact SHA 为 4c3f9f23f22bc9e20cef8992d99db86f8eda159951b78b016685214bbc274b68，
source SHA 为 2c8fca90c7300b85b30021081868b699c0b306d2，MPI1 residual manifest SHA
为 62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce；它是
p6/h10、degree6、rows=173802、active dual packets=164592、excluded slaves=9210。

当前源码的 canonical dual reconstruction 对 wrong role、duplicate、missing 和
MPI1 extra key fail closed，但没有跨 mesh 映射。same-mesh P63/P63^H、LOR transfer、
PETSc row 重排或重新 hash source 都不构成 h10→h50 authority。

## Review V16 §19 逐项回答

| # | 问题 | 当前状态 |
|---:|---|---|
| 1 | A3 identity | not_run |
| 2 | small inner solve | not_run |
| 3 | Q2 rho_ref/rho3 | not_run |
| 4 | I20/I100 | not_selected / not_run |
| 5 | short screen | not_run |
| 6 | fresh physical residual/RSS/swap | not_run |
| 7 | release-before-recovery + RSS下降 + official来源 | not_run |
| 8 | direct authority arrays | not_reached / not_run |
| 9 | W与旧路线差异 | not_run_by_trigger_not_met |
| 10 | W local-only/two-level contraction | not_run_by_trigger_not_met |
| 11 | measured/derived/predicted/failed/controlled_stop/not_run 分类 | 见下方证据口径表 |
| 12 | 已消除与仍存 blocker | Q0/核心缺口已消除；p6/h50 R3 authority仍阻塞 |

| 证据口径 | 本轮事实 |
|---|---|
| measured | 没有 Q1 数值或资源测量 |
| derived/read-only | 旧 R3 与当前 F1 identity facts |
| predicted | Q0 central=1714887192 B；hard=1889004056 B；major_unknown=[] |
| failed | 无真实数值或资源 Gate |
| controlled_stop | source-authority mismatch |

既有 [Q0 preflight](outcomes/physical_pcoarse_preflight_v16.md)、
[Q1 oracle](outcomes/physical_pcoarse_oracle_v16.md) 和
[Q1 compact](outcomes/records/physical_pcoarse_q1_authority_v16.json) 已给出证据入口。
第 12 项结论是：Q0 公式/容量预审和 Q1 核心实现缺口已消除，但合法 p6/h50
R3 source 定义/映射仍阻塞，因此 A3 identity 及后续均未资格化。

## 用户明确的次数边界

用户明确允许真实 checkpoint/数值测量之前唯一定位的 path/cache/marker/import/
provenance bug，在保留旧证据、窄修、focused test、review、commit 后用新 SHA/root
唯一重试；这类修复不计正式数值次数。真实 identity、numerical、span、2 GB、
swap、nonfinite Gate 不得重跑。本次是缺少 h50 source 定义的数学合同问题，不是
局部代码 bug，故不能套用 execution-fix retry。V13 positive、V14 J5、V15 F1/F2/F3
和全部历史 negative 原样保留。

## 决定与下一步

固定六 probe formal 不可合法启动；Q2–Q6、W0–W4、official physics 均未运行。
按 V16 文字，W0 只在 Q 被真实数学、数值或资源 Gate 关闭后触发，本次未发生
这类 Gate，因此 W0 未触发。

下一步需主线程明确二选一：提供绑定 p6/h50 mesh、mode、source identity 的合法
R3 source 定义/映射后继续 Q1；或明确授权将 source-authority blocker 视为 Q 关闭
并进入 W0。本 response 不替 Review 做选择。

## 用户最新明确的 MPI 资源口径覆盖

| 项目 | 冻结口径 |
|---|---|
| MPI1 | 完整 process-tree RSS `< 2,000,000,000 B` 是严格硬资源 Gate。 |
| MPI2 | 即使 RSS 超过 2 GB，也只记录精确峰值；不得仅因 RSS 关闭 Q 或判定资源 Gate 失败。 |
| MPI2 其他条件 | 数值、finite、linear/repeatable、input unchanged、合法 high-space primal、provenance、swap=0 与对象生命周期仍必须通过。 |
| 工程 bug | path/cache/import/runner/JIT/provenance 等非真实数值或资源 Gate 问题，保留旧证据后唯一归因、窄修并重试；不得借此放宽数值阈值、修改物理或扫描参数。 |

Q1.1 v2 的既有 negative artifact 仍永久保留、不覆盖、不重分类；本口径覆盖只适用于后续 MPI2 资源判定。

## 后续正式 authority（按时间顺序）

### Q1.1：同一 h50 mesh 的 p6/p3 physical action identity

六个 probe 为 `random`、`gradient`、`curl`、`checkerboard`、
`physical_component_derived`、`r3_long_tail_derived`。每个 probe 独立比较

```text
A3 v  与  P63^H A6 P63 v
```

并核对 P/P^H work identity、linearity、repeat、input unchanged、finite、
owned-slave zero 和 canonical key。MPI1/MPI2 的 physical Galerkin worst，以及
pair checker 的 direct/composed MPI worst 均来自 raw/pair checker：

| 事实 | 数值 | probe | Gate |
|---|---:|---|---:|
| MPI1 worst `physical_galerkin_relative` | `4.3068152418800024e-14` | `curl` | `<=1e-9` |
| MPI2 worst `physical_galerkin_relative` | `3.631160363261226e-13` | `curl` | `<=1e-9` |
| pair worst direct MPI relative | `1.3304006108072395e-14` | `physical_component_derived` | `<=1e-10` |
| pair worst composed MPI relative | `3.620657472911387e-13` | `curl` | `<=1e-10` |
| MPI1 worst work identity / linearity | `7.688109888104707e-15` / `1.9692433825989632e-15` | `random` / `curl` | passed |
| MPI2 worst work identity / linearity | `1.5952093930127624e-15` / `2.3753469222061536e-15` | `checkerboard` / `curl` | passed |

对应的 Q1.1 MPI1/MPI2/pair raw/checker 路径和 SHA 见
[`physical_pcoarse_q1_qualification_v16.json`](outcomes/records/physical_pcoarse_q1_qualification_v16.json)。
Q1.1 的 MPI1/MPI2 process-tree peak 为 `1,558,728,704 B` /
`1,451,368,448 B`，swap 均为 0。

### Q1.2：p3/h50 physical inner

Q1.2 只在 p3/h50 运行 physical RHS 与 random 的 p3 inner；它不是 p6/h10
inner，也不是完整 official solve。MPI1 单侧 checker 与独立 pair checker（读取
MPI1/MPI2 raw）均通过，MPI1/MPI2 两侧数值均为 PASS：

| MPI | source | final explicit true residual | iterations | parent / worker peak |
|---|---|---:|---:|---:|
| 1 | `physical_rhs` | `8.492309832071864e-7` | 880 | `1,558,450,176` / `284,377,088 B` |
| 1 | `random` | `9.452221758437722e-7` | 2280 | `1,558,450,176` / `284,377,088 B` |
| 2 | `physical_rhs` | `8.456504897210137e-7` | 880 | `1,558,446,080` / `504,700,928 B` |
| 2 | `random` | `9.46295350977649e-7` | 2280 | `1,558,446,080` / `504,700,928 B` |

四项 solver residual 都低于 `1e-6`，swap=0；MPI pair canonical relative 为
`2.8791244124846644e-16`（physical_rhs）和
`2.7874227585299645e-15`（random）。Q1.2 的 parent、worker、timeline、marker
和 pair checker 的逐文件 SHA 见上述 qualification compact；MPI2 RSS 按用户
明确覆盖只记录，不因超过 Q1 small worker 线单独关闭路线。

### Q2：p6/h10 checkpoint correction

Q2 使用旧 checkpoint 恢复 p6/h10 状态，按

```text
r6 = b6 - A6*x1000
r3 = P63^H*r6
A3*e3 = r3
e6 = P63*e3
r6_new = r6 - A6*e6
r3_new = P63^H*r6_new
```

得到：

| 事实 | 数值 | Gate |
|---|---:|---:|
| checkpoint stored / recomputed residual | `0.4837947981092168` / `0.48379479479924` | reproduction relative `6.8416957056789795e-9 > 1e-11` |
| inner final true residual | `0.7749555148382701` at 10000 | `>1e-6` |
| `rho_ref` | `2.7001483995603124` | `>0.70` |
| `rho3` | `0.774955514838267` | `>0.10` |
| `r6` → `r6_new` norm | `0.6412077991519661` → `1.7313562126657716` | correction worsened p6 residual |
| `r3` → `r3_new` norm | `0.39933395062332383` → `0.309466047297697` | p3 reduction insufficient |

inner true-residual history 为：

| iteration | 0 | 20 | 1000 | 2000 | 4000 | 6000 | 8000 | 10000 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| true residual | 1.0 | `0.8309410237461273` | `0.7830431676258411` | `0.78048347154443` | `0.7781984682037493` | `0.7766983492676462` | `0.7756091855405819` | `0.7749555148382701` |

设置是 zero-start、right FGMRES、restart=20、每 20 步显式 true residual、
`max_it=10000`。matvec/PC/explicit action/KSP destroy 为
`10999/10000/501/500`；upper p6 smoother apply delta=`0`，合法 lower
p3→p1 cycle delta=`10000`。parent peak `1,560,625,152 B`、worker peak
`873,783,296 B`、swap=0；这些是窄 checkpoint correction 的实测过程树事实，
不能冒充 full physical PDE 的正确解或 official physics。精确 raw/checker
证据见 [`physical_pcoarse_checkpoint_v16.md`](outcomes/physical_pcoarse_checkpoint_v16.md)
和 [`physical_pcoarse_checkpoint_v16.json`](outcomes/records/physical_pcoarse_checkpoint_v16.json)。

## Review V16 十二项最终回答

| # | 问题 | 最终回答 |
|---:|---|---|
| 1 | Q1.1 A3 identity | 同一 h50 mesh 的 p6/p3 action identity 已 PASS；worst MPI1/MPI2 physical Galerkin 为 `4.3068152418800024e-14` / `3.631160363261226e-13`，均为 `curl`；pair direct/composed worst 为 `1.3304006108072395e-14`（`physical_component_derived`）/ `3.620657472911387e-13`（`curl`）。 |
| 2 | Q1.2 small inner | p3/h50 physical inner 的 MPI1、MPI2、pair 均 PASS；精确 residual、iterations 和资源见 Q1.2 表。 |
| 3 | Q2 `rho_ref` / `rho3` | 已实际运行并失败：`2.7001483995603124` / `0.774955514838267`，分别超过 `0.70` / `0.10`；不是扫描失败。 |
| 4 | I20/I100 与 Q3 | I20/I100 均未选择、未运行；Q3 locked/not_run，不把它写成扫描失败。 |
| 5 | Q4 short screen | `not_run`。 |
| 6 | Q5 fresh physical residual/RSS/swap | `not_run`；Q2 的 `1,560,625,152 B` 是 checkpoint correction parent peak，不是 full PDE。 |
| 7 | release/recovery/official | Q5 release-before-recovery、RSS下降和 official recovery 均 `not_run`；Q2 的 `release_complete` marker 只证明该窄 runner 的对象生命周期，不证明 official recovery。 |
| 8 | direct authority arrays | `direct_authority_packet_audit_v1` 仍为 `AUTHORITY_ARRAYS_MISSING`：已有 scalar `R/T/A/A_volume`，但没有同一 12+12 的 complex E/H、near-field 和 boundary-amplitude arrays，不能替代 official physics authority。 |
| 9 | W 与旧路线差异 | W0 候选是四个 geometry-only z quartile 子域、三界面、one-cell overlap、T4 impedance closure、physical local Maxwell operator、exact gradient/tangential trace、two-sided harmonic extension 和 owner-distributed interface Schur；它不是 two-slab Robin、V15 rank32 global projection、普通 GenEO/BDDC/HX 或旧 trace-harmonic/local-spectral 的换名。 |
| 10 | W local-only/two-level contraction | `locked/not_run_by_W0_gate`；W0 的 local inverse 只能是 fallback same-mesh positive pMG，local inner restart/max_it=20/100 fixed，不恢复 physical p-coarse；没有 contraction measurement。 |
| 11 | evidence 分类 | measured：Q1.1/Q1.2 数值、Q2 residual/history/RSS/swap；derived：checker 重算的 relative、canonical/cache/provenance/hash；predicted：Q0/W0 capacity arithmetic；failed：Q2 numerical Gate、W0 rank/byte capacity closure；controlled_stop：首次 Q1 source-authority mismatch；not_run：Q4/Q5/Q3–Q6/W1–W4/official。 |
| 12 | 已消除与仍存 blocker | 已消除 Q0 公式/容量预审、Q1 core、source bridge、quadrature/JIT/cache/lifecycle 等工程缺口；仍存 Q2 numerical failure、W0 interface rank/bytes major unknown、official E/H/recovery 缺失和 0.7nm/2TiB scalability 未证。 |

## W0 与最终边界

W0 候选的定义、phase-disjoint 容量账本和 unknown 已记录在
[`wave_aware_dd_preflight_v16.md`](outcomes/wave_aware_dd_preflight_v16.md)；其
真实分类为 `W0_INTERFACE_RANK_CAPACITY_FAIL`，因此 W1–W4 全部锁定。W0 失败
不是第五个 PC 的实现结果，也不允许把 future direction 写成已通过。

`2,000,000,000 B` 是 MPI1 的严格 process-tree RSS 硬线；用户明确 MPI2 即使
超过该线也只记录，但仍须通过 numerical、finite、repeat、input、provenance、
swap 和 lifecycle。当前没有一个通过 official physics 的 p6/h10 full solve：
Q2 的 p6/h10 correction 数值 Gate 已失败。0.7nm/2TiB scalable solve 同样
未证明。Z0 仅完成文档架构收口，未实现 W1–W4 或新的 solver。
