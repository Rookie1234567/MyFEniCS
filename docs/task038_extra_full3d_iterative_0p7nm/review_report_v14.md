# Task038-extra Review Report V14：cold JIT staging 与真实 Maxwell 全流程内存闭合

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V14
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = d9ced796e61cbcc0585e0ced511cde3bb652da7a
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 215 / behind 0
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v13.md
reviewed_summary                        = docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
reviewed_positive_outcome               = docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6_positive_v13.md
reviewed_physical_outcome               = docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6_physical_v13.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
ordinary_default_change                 = forbidden
selected_hierarchy                      = same_mesh_hcurl_pmg_v1_requalified
C1_positive_status                      = PASS at p6/h10 MPI1 for four sources
V13_P0_status                           = FAILED_RESOURCE_HARD_STOP before bundle_built
primary_blocker                         = cold physical JIT/setup overlap, not yet a Maxwell numerical failure
primary_objective                       = final correctness under bounded memory
iteration_count_and_wall_time           = secondary
production_Krylov                       = right-preconditioned GMRES
production_restart                      = 20, fixed
physical_Maxwell_max_it                 = 20000, fixed
process_tree_hard_limit                 = 2000000000 B
process_tree_warning                    = 1800000000 B
swap_gate                               = 0 B
full_0p7nm_PDE                          = forbidden
response_required                       = response_v14.md
continuous_authorized_batch             = J0 through J9 below, subject to fixed Gates
mandatory_stop                          = after J9 or any earlier terminal hard stop
```

本 Review 只围绕长期主线继续推进：

> 在单节点约 2 TiB 物理内存内，以自主 FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解 0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

V14 的直接目标不是再寻找新的 PC，而是让已经获得强正信号的 same-mesh `H(curl)` p-multigrid 首次进入真实 Maxwell Krylov，并在严格的 p6/h10 `<2,000,000,000 B` 战略锚点下完成残差和 official physics 闭环。

---

# 1. 对 V13 结果的审阅

## 1.1 必须永久保留的事实

| 对象 | V13 权威状态 | V14 解释边界 |
|---|---|---|
| Route A `6→3→1` | `CLOSED_BY_VECTOR_OR_STABLE_ADJOINT_GATE` | gradient pairwise-vs-compensated `2.7478465599487806e-12 > 1e-13`；不得重开 |
| C0 canonical source | `C0_CANONICAL_SOURCE_PASS_MPI1_MPI2` | 证明旧 C1 MPI mismatch 主要来自测试源身份，不覆盖旧 negative |
| C1 same-mesh p-MG | `C1_P6_POSITIVE_PASS_MPI1` | p6/h10 四类正定辅助问题通过；不等于 physical Maxwell 已通过 |
| V13 P0 physical | `FAILED_RESOURCE_HARD_STOP` | cold setup 只到 `paths_ready`；没有 residual 或 physics，不能分类为数值失败 |
| P1/P2 | `not_run_by_resource_gate` | 尚无 physical residual，不能提前增加 deflation 或运行 MPI2 |
| GenEO / BDDC | `not_run_by_selected_C1` | 不是失败；但当前没有理由切换到它们 |
| complete 0.7 nm PDE | `not_run` | 本 Review 仍禁止 |

所有旧 negative、controlled stop、source SHA、watchdog 和 artifact 均保持不可变。新的运行必须使用新 source SHA、新 schema 或明确版本号以及全新 artifact root。

## 1.2 C1 是当前应继续保留的唯一 selected hierarchy

V13 exact-input p6/h10 MPI1 positive 结果为：

| source | iterations | final explicit true residual | process-tree peak | retained peak | swap |
|---|---:|---:|---:|---:|---:|
| random | 200 | `5.550975220267439e-9` | `1,517,903,872 B` | `772,497,408 B` | `0 B` |
| gradient | 220 | `2.7889793119815017e-9` | `1,516,544,000 B` | `770,650,112 B` | `0 B` |
| curl | 180 | `5.6105046279899595e-9` | `1,536,192,512 B` | `790,028,288 B` | `0 B` |
| checkerboard | 200 | `7.760965317017376e-9` | `1,533,190,144 B` | `786,751,488 B` | `0 B` |

这四项同时证明：

```text
p6 matrix-free positive action                  = usable
same physical mesh p6→p3→p1 transfer            = usable
p3/p1 sparse positive hierarchy                 = usable
restart20 memory-first Krylov                    = usable
p6/h10 complete positive workflow below 2 GB    = measured PASS
```

因此 V14 禁止因为 P0 cold setup 超线而切换到 GenEO、BDDC/FETI-DP、新 coarse space、新 smoother 或新 hierarchy。

## 1.3 P0 的准确失败性质

V13 P0 的实测事实为：

| 项目 | 实测值 |
|---|---:|
| reached marker | `paths_ready` only |
| elapsed at final sample | `5167.201565908967 s` |
| process-tree peak | `2,024,108,032 B` |
| hard line | `2,000,000,000 B` |
| strict overage | `24,108,032 B`，约 `1.2054%` |
| first warning | `1,813,069,824 B` at `5165.438371994998 s` |
| process-tree swap | `0 B` |
| worker record / residual / checkpoint | `not_created` |
| recovery / official physics | `not_run` |

该结果严格是资源失败，不能舍入为 PASS。与此同时，watchdog 在约 1.76 秒内观察到至少约 211 MB 的突然增长，现场留下约 108.7 MB 的未完成 FFCx C source 和两个额外 child PID。现有证据支持“form compiler transient 与完整 hierarchy 同时驻留”的高可信工作假设，但缺少 child cmdline 和阶段 marker，尚不能写成唯一已证实根因。

## 1.4 为什么下一步是生命周期修复，而不是重新研究 PC

当前 `build_p6_same_mesh_physical_bundle` 的顺序是：

```text
先建立完整 p6→p3→p1 positive hierarchy
→ 再建立 mode inventory / surface assemblers / DtN
→ 再 JIT physical p6 volume form
→ 再建立 physical matrix-free action
```

这使完整 hierarchy、p1 factor、p3 matrix、smoother/work vectors 与 physical compiler subprocess 可能重叠。V14 要把这些阶段串行化，使正式全流程峰值接近“各阶段峰值的最大值”，而不是阶段 live set 的叠加。

---

# 2. V14 的 formal cold-workflow 定义

## 2.1 cold-staged 不等于 warm-cache 绕过

V14 允许的唯一正式形式是：

```text
一个外部 parent watchdog 覆盖完整运行
→ 在 parent 内创建全新、空的 JIT cache
→ 一个或多个最小 precompile child 顺序编译全部必需 forms
→ 每个 child 和其 compiler descendants 完整退出
→ 同一 parent 内启动 solver child
→ solver child 只从本次新 cache 加载 kernel
→ setup / source / Krylov / release / recovery 全部完成
```

整个 parent process tree 从空 cache 到 official outputs 的最高 RSS 才是 formal memory authority。

禁止：

```text
在 formal parent 启动前预热 cache
复用旧 case 或旧 source SHA 的 cache
只报告 solver child 而排除 precompile child
把各阶段累计 bytes 当 simultaneous RSS
因 staged cache hit 而把全流程称作 ordinary warm run
```

正式状态名称固定为：

```text
COLD_STAGED_END_TO_END
```

## 2.2 资源 Gate

| Gate | 数值 | 作用 |
|---|---:|---|
| complete parent process-tree hard peak | `< 2,000,000,000 B` | 绝对成功线 |
| warning | `1,800,000,000 B` | 预警，不等于失败 |
| solve-ready retained preferred target | `<= 1,600,000,000 B` | 保留充足运行余量 |
| solve-ready retained hard start Gate | `<= 1,700,000,000 B` | 超过则不得启动 20,000 步 full solve |
| process-tree/rank swap | `0 B` | 硬 Gate |
| residual RSS growth across restart cycles | no monotone growth | 固定内存合同 |

`solve-ready retained` 指 compiler children 已退出、cache 已冻结、完整 physical bundle、RHS、PC 和 restart20 所需常驻对象就绪后的同时 RSS。

---

# 3. 总执行顺序

Codex 可按以下固定顺序连续执行，不需要在每个子阶段等待审阅：

```text
J0  冻结证据、选择性复用审计和 direct authority packet 审计
J1  physical setup 阶段化 instrumentation 与 form inventory
J2  cold-staged JIT parent/child workflow
J3  条件 two-action physical volume split
J4  fresh P0R setup + one-action + one-PC + one restart20 cycle
J5  条件 full P0 physical Maxwell MPI1
J6  条件唯一 bounded Floquet/near-cutoff deflation
J7  release-before-recovery、official physics 和 direct authority comparison
J8  条件 MPI2、h5 setup-only 和 0.7 nm / 2 TiB capacity update
J9  outcomes、development progress、response_v14.md、commit/push 后停止
```

固定分支规则：

1. J2 通过则直接进入 J4；J3 只有 J2 的单个 minimal physical-volume compile 仍越过 2 GB或 solver phase仍触发同一 kernel 编译时才允许。
2. J4 通过后才进入 J5。
3. J5 达到 `1e-6` 后直接进入 J7；只有满足 J6 的 long-tail 条件才运行一次 J6。
4. J7 通过后才进入 J8。
5. 任一 terminal hard stop 均保存证据并进入 J9，不得自动切换到新 PC family。

---

# 4. J0：证据冻结、复用边界与 direct authority 审计

## 4.1 历史证据冻结

必须首先确认：

```text
branch / HEAD / upstream / clean worktree
V13 C1 four-source records and checkers
V13 P0 ignored root and tracked watchdog/paths copies
input SHA / physical SHA / mode manifest SHA
ordinary default unchanged
```

不得删除旧 failed attempts、startup/provenance stops 或重复资格记录。

## 4.2 Task37-extra JIT pattern 只作选择性复用

只读审计 Task37-extra 中可复用的：

```text
fresh-cache staging
process-tree watchdog
compiler-child teardown
cache identity
object lifetime / malloc trim
```

迁移时只取通用模式和必要 helper，不得整体 cherry-pick Task37-extra runner、PC 或旧 task orchestration。

## 4.3 direct authority packet 审计

在不启动新 PDE 的前提下，检查本机已有 Task037c、Task039 和 direct p6/h10 ignored artifacts，寻找与当前 exact input/profile 完全一致的：

```text
selected complex E/H samples or minimal near-field packet
R / T / A / A_volume
same 12 significant diffraction identities
12 power values
12 complex boundary amplitudes
input / physical / source / artifact hashes
```

必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/direct_authority_packet_audit_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/direct_authority_packet_audit_v1.json
```

若现有 artifact 足够，提取最小 hash-bound authority packet；若不存在，记录 `AUTHORITY_ARRAYS_MISSING`，但在 J5 数值通过前不得重跑 direct。

---

# 5. J1：阶段化 instrumentation 与 form inventory

## 5.1 必须增加的阶段 marker

至少记录：

```text
parent_started
fresh_cache_created
precompile_positive_p6_started / complete
precompile_positive_p3_started / complete
precompile_positive_p1_started / complete
precompile_dtn_surface_started / complete
precompile_incident_rhs_started / complete
precompile_physical_volume_started / complete
all_precompile_children_gone
solver_child_started
positive_setup_started / complete
mode_inventory_started / complete
surface_assemblers_started / complete
dtn_carrier_started / complete
dtn_action_complete
physical_volume_action_started / complete
bundle_built
source_built
one_action_complete
one_pc_complete
solve_started / complete
solver_stack_release_started / complete
recovery_started / complete
parent_complete
```

## 5.2 每个阶段必须保存的进程事实

```text
PID / PPID
cmdline
stage tag
RSS
PSS when readable
swap
start/end timestamp
exit code
compiler child count
```

如果 `/proc` 的短暂退出导致一次读取 race，可按已资格化 watchdog 规则重试；不能静默丢弃不可读样本。

## 5.3 form inventory

必须列出本次 exact profile 所需的全部 distinct JIT objects：

```text
UFL/form role
polynomial degree
quadrature degree
coefficient identity
cache key or generated module identity
expected .c/.o/.so artifacts
which runtime component consumes it
```

J1 只增加 instrumentation 和 inventory，不改变弱形式、材料、DtN、PC、smoother、restart 或 recovery。

---

# 6. J2：cold-staged JIT parent/child workflow

## 6.1 precompile child 的最小对象原则

每个 precompile child 只建立编译对应 form 所需的最小：

```text
mesh
目标 degree 的 function space
必要 Floquet/MPC metadata
UFL form 与明确 JIT options
```

禁止在 precompile child 中建立：

```text
p3/p1 assembled matrices
p1 factor
multigrid V-cycle
restart20 basis reserve
physical RHS
recovery fields
full DtN retained carrier beyond form compilation needs
```

## 6.2 顺序编译

至少按下列组顺序执行，允许一个组内继续按 component 顺序拆成多个短 child，但不得并发：

```text
1. p6 positive action form
2. p3 positive matrix form
3. p1 positive matrix form
4. top/bottom × tangential component surface forms
5. incident traction RHS form
6. p6 physical volume form
```

每个 child 完成后必须：

```text
wait child
wait compiler descendants
record exit and peak
gc / PETSc cleanup where applicable
confirm no descendant remains
freeze cache artifact hashes
```

## 6.3 solver phase 的 cache-hit Gate

solver child 使用同一 formal cache，并必须证明：

```text
compiler child count during solver phase = 0
cache artifact hashes unchanged
no new large .c/.o/.so appears
all expected modules imported from this formal cache
```

若 solver phase仍触发编译，分类为 `JIT_STAGING_IDENTITY_FAIL`，只允许修复缺失的 inventory/cache key；不得通过复用外部旧 cache 绕过。

## 6.4 J2 Gate

```text
all precompile groups natural exit
all per-child process-tree peaks < 2,000,000,000 B
parent process-tree peak < 2,000,000,000 B
swap = 0
all compiler children gone before solver child
cache identity and source/input/physical identities closed
```

J2 只需把 solver child推进到 bundle build 前的 cache-hit证明；不运行长 Krylov。

---

# 7. J3：条件 two-action physical volume split

J3 只在以下任一情况触发：

```text
minimal p6 physical-volume precompile child alone reaches 2 GB hard line
或
solver child在已完整 inventory的cache上仍重新编译同一 monolithic volume form
```

唯一允许的新数值实现是把原 physical volume action 分成：

```text
curl-curl action
+
complex material mass action
```

最终 physical operator仍为：

```text
split volume sum + unchanged streaming Fourier-DtN
```

禁止：

```text
改变弱形式符号
改变材料或损耗
改变 quadrature
按结果继续拆成更多 material-specific variants
引入 assembled p6 AIJ
修改 PC hierarchy
```

必须先验证：

| oracle | Gate |
|---|---:|
| p2/p3 split-sum vs original assembled/action identity | `<= 1e-12` |
| p6 fixed random/gradient/curl/checkerboard split-sum vs original matrix-free action | `<= 1e-12` |
| source identity | exact |
| Floquet/MPC phase | exactly once |
| finite / linear / repeat / input unchanged | pass |

若 two-action split 的任一 minimal compile child仍超过2 GB，或 action identity失败，则 P0 physical memory architecture在 V14 关闭；不得继续三拆、四拆或改变 compiler optimization。

---

# 8. J4：P0R setup 与一个 restart20 cycle 的正式资源资格

J4 必须从：

```text
new clean source SHA
new empty formal cache
new artifact root
zero initial guess
```

开始，并在一个 parent watchdog 内完成：

```text
cold staged precompile
→ solver child cache-hit
→ full same-mesh positive hierarchy
→ dynamic mode inventory
→ streaming DtN
→ exact physical volume action
→ physical RHS
→ one physical action
→ one PC apply
→ one 20-step GMRES cycle
→ explicit true residual replacement
→ retained observation
→ orderly destruction
```

## 8.1 J4 hard Gates

```text
complete parent process-tree peak < 2,000,000,000 B
solve-ready retained <= 1,700,000,000 B
process-tree/rank swap = 0 B
compiler children absent during solver phase
bundle_built / source_built / one_action / one_pc / solve markers complete
physical action and PC output finite
source/input unchanged
owned slave condition pass
20-step explicit true residual finite and not greater than initial residual beyond 1e-12 roundoff
no monotone RSS growth across setup/apply/cycle teardown
```

`solve-ready retained <=1.6 GB` 是 preferred target；`1.6–1.7 GB` 可继续但必须记录 warning；超过 `1.7 GB` 不得启动 J5。

## 8.2 允许的执行修复次数

若第一次 J4 在 bundle/source/solve 前因唯一可定位的路径、marker、cache-key或provenance bug失败，允许一次 execution-fix retry；旧失败必须完整保留。数值、内存或 action identity失败不允许通过第二次重跑改变结论。

---

# 9. J5：完整 p6/h10 physical Maxwell MPI1

只有 J4 全部通过才运行。

固定：

```text
wavelength = 13.5 nm
p6/h10
MPI1
exact input and physical identity
selected_hierarchy = same_mesh_hcurl_pmg_v1_requalified
exact matrix-free Maxwell volume
streaming Fourier-DtN
right-preconditioned GMRES
restart = 20
cycle_max_it = 20
max_it = 20000
residual replacement every 20
solution-only checkpoint every 500
zero initial guess
```

禁止修改：

```text
p6→p3→p1 hierarchy
p3/p1 operators
smoother degree/count
p1 development oracle
restart
physical coefficients
DtN inventory
```

## 9.1 J5 success Gates

```text
final explicit true residual <= 1e-6
complete cold-staged end-to-end process-tree peak < 2,000,000,000 B
process-tree/rank swap = 0 B
finite / checkpoint / provenance = pass
no restart-cycle RSS accumulation
```

必须记录：

```text
iterations 20 / 100 / 200 / 500 / 1000 / 2000 / 5000 / 10000 / 15000 / 20000
explicit true residual at every restart boundary
matvec / PC apply / KSP-destroy counts
per-stage wall time and memory peak
```

若达到 20000 步仍未通过且不满足 J6 条件，则分类为 `PHYSICAL_NUMERICAL_FAIL_AT_FIXED_CAP`；不得继续提高 max_it 或 restart。

---

# 10. J6：唯一一次 bounded Floquet / near-cutoff deflation

只有 J5 同时满足以下条件才进入：

```text
positive hierarchy已通过
physical solve确实运行到20000步
finite且无RSS增长
last 5000 steps降低至少1个十进制数量级
资源失败不是停止原因
```

固定 correction：

```text
propagating + near-cutoff Floquet directions only
no residual-derived vectors
rank hard cap = 32
one construction
one formal rerun
```

运行前必须闭合：

```text
predicted added retained <= 180,000,000 B
measured headroom to 2 GB >= 250,000,000 B
coarse/operator payload distributed or bounded
```

不满足内存前置条件则 J6 `not_run_by_headroom_gate`。不得扫描 rank、near-cutoff window、mode weighting 或追加第二批方向。

J6 的 full solve仍使用 `restart=20`、`max_it=20000` 和相同最终 residual/资源 Gate。

---

# 11. J7：release-before-recovery 与 official authority

## 11.1 生命周期顺序

数值通过后必须严格执行：

```text
save minimum recovery packet
→ destroy outer KSP and restart basis
→ destroy p1 development direct factor
→ destroy p3/p1 matrices, transfers, smoothers and work vectors
→ preserve only mesh/space/Floquet, physical/DtN action and recovery solution
→ gc + PETSc garbage cleanup + heap trim
→ observe process-tree RSS release
→ recover total E/H and DtN auxiliary
→ official postprocess
```

必须保存 release 前后同时 RSS、释放对象清单和观测窗口。

## 11.2 official outputs

只有 final explicit true residual `<=1e-6` 的场才可生成：

```text
complex E and H
R / T / A
A_volume
energy closure
near-field export
all diffraction orders
same 12 significant identities
12 power values
12 complex boundary amplitudes
```

完整 recovery 后 process-tree peak仍必须 `<2,000,000,000 B`。若 solve通过但 recovery超线，分类为：

```text
NUMERICAL_PASS_RESOURCE_FAIL_DURING_RECOVERY
```

不得把它写成 complete workflow PASS。

## 11.3 direct authority

优先使用 J0 找到并绑定的现有 matching authority packet。

若 J0 确认数组缺失，且 J5/J6 数值已经通过，才允许额外运行一次同一 p6/h10 物理身份的 direct authority generation：

```text
one heavy job at a time
swap = 0
warning = 10 GB
controlled hard stop = 12 GB
release-before-recovery
output only the minimum authority packet and hashes
```

该 direct authority 的资源不冒充 iterative `<2 GB` workflow；它只用于正确性验证。比较 Gate必须在运行前复用现有项目 checker/authority语义，不得看结果后新设 tolerance。

---

# 12. J8：条件 MPI2、h5 和 0.7 nm / 2 TiB 更新

仅在 MPI1 complete workflow 和 direct-authority comparison通过后执行。

## 12.1 MPI2

使用相同 cold-staged parent workflow：

```text
MPI2
same input/physical/mode identity
same hierarchy rule
same restart20
max_it <= 20000
```

Gate：

```text
final explicit true residual <=1e-6
complete process-tree peak <2GB
swap=0
final physical observable vector与MPI1一致
```

PC内部中间向量不要求逐位相同，但 exact A/b identity、最终 residual 和 official observables必须通过。

## 12.2 p6/h5 setup-only scaling

只有基于 h10 measured components 的 preflight预测低于开发机 `12 GB` controlled-stop线时才运行：

```text
cold-staged precompile
full setup
one action
one PC apply
one restart20 cycle
no long physical solve
```

记录 rows、NNZ、transfer、DtN、JIT、retained和完整process-tree scaling。

## 12.3 0.7 nm / 2 TiB capacity audit

创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/feasibility_0p7nm_2tib_v5.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/feasibility_0p7nm_2tib_v5.json
```

必须使用：

```text
measured h10 complete physical workflow
conditional measured h5 setup scaling
formal 0.7 nm material and channel inventory
FE / transfer / sparse levels / DtN / Krylov / checkpoint / recovery / MPI duplication
optimistic / central / conservative scenarios
system reserve and zero-swap policy
```

不得运行完整 0.7 nm PDE，也不得把 p6/h10 `<2GB` 自动外推为 2 TiB production PASS。

---

# 13. terminal decision tree

| 结果 | 决策 |
|---|---|
| staged workflow通过且 J5/J6 residual、physics、resource全部通过 | 保留 same-mesh p-MG 为 Full3D iterative production candidate；进入 MPI2/h5/2TiB审计 |
| minimal monolithic compile超线，但 two-action split通过 | 使用 split physical action继续；原 monolithic P0 negative保留 |
| two-action split仍有单 child超2GB | 关闭当前 FFCx physical-kernel memory architecture，不关闭 selected PC |
| solve-ready retained超过1.7GB | 关闭当前 complete physical live-set；不得用提高hard line绕过 |
| physical residual在固定cap失败且不满足唯一deflation条件 | 关闭该PC对当前真实 Maxwell 的数值资格，不转写为positive问题失败 |
| solve通过但recovery超2GB | 数值通过、完整workflow资源失败；下一任务必须专门重构streaming recovery |
| MPI1 complete workflow通过 | 才可执行MPI2、h5和2TiB更新 |

如果 J2/J3 均无法使 cold physical compilation低于2GB，J9 必须额外创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/next_physical_kernel_architecture_after_v14.md
```

只比较下一步，不自动实现：

```text
build-time/AOT hash-bound form kernels
sum-factorized/tensor-product p6 H(curl) action
custom low-memory generated kernel pipeline
streamed recovery/postprocess architecture
```

不得因此自动开始新 PC family。

---

# 14. 测试、证据和文档要求

## 14.1 focused tests

至少覆盖：

```text
fresh cache must be empty
precompile children are sequential
compiler descendants are gone before solver phase
cache artifacts unchanged during solver phase
staged kernel action identity
conditional split-action identity
parent watchdog includes every child
same root cannot be reused
marker order and fail-closed behavior
release order and recovery packet minimum set
```

## 14.2 regression

必须重跑与以下模块直接相关的现有 focused tests：

```text
matrix-free MPC form action
streaming full-space DtN
same-mesh p-MG setup/positive
memory-first restart20/checkpoint
watchdog/process-tree readability
physical RHS and recovery helpers
markdown/repository contracts
```

记录真实本地测试；没有 GitHub Actions 不得声称 CI PASS。

## 14.3 evidence

每个 formal run必须绑定：

```text
source SHA
input SHA
physical-model SHA
mode-manifest SHA
command and environment ABI
fresh-cache identity and artifact hashes
stage markers
raw and compact watchdog hashes
true residual history
resource scope
checkpoint hashes
official artifact hashes
```

checker必须从原始字段独立重算，不得只信 record 中的 `status`。

---

# 15. J9 交付与停止点

最终至少更新或创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/jit_staging_physical_memory_v14.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/direct_authority_packet_audit_v1.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/p6_physical_v14.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/development_progress.md
docs/task038_extra_full3d_iterative_0p7nm/response_v14.md
```

未触达阶段不得创建伪 PASS outcome；可以创建明确写有 `not_run_by_gate` 的预置记录，但不得填入推测数值。

完成后：

```text
run final focused tests
check GitHub Markdown rendered view
commit in logical units
push same branch
report exact HEAD / base / ahead-behind / worktree / tests / evidence
stop for review
```

禁止 merge/rebase master、改变 ordinary default 或运行完整 0.7 nm PDE。

---

# 16. V14 最终审阅结论

V13 已经找到当前 Full3D iterative 主线最强的正定辅助预条件器证据：same-mesh `p6→p3→p1` 在 p6/h10 四类 source 上以 180–220 步达到约 `1e-9`，峰值约 1.52–1.54 GB、swap为零。真实 Maxwell 尚未产生一条 residual；唯一新失败发生在 cold setup 的 compiler/physical-form阶段。

因此下一最小可审计步骤不是更换 PC，而是：

```text
完整阶段归因
→ formal cold JIT staging
→ 必要时唯一的curl/mass two-action split
→ setup + one restart20 resource qualification
→ 原selected hierarchy的真实Maxwell求解
→ release-before-recovery和official physics
```

只要该流程保持完整 parent process tree `<2,000,000,000 B`，它就直接消除“已有强 positive PC 不能进入真实物理方程”的当前 blocker，并为后续 h-scaling 与 0.7 nm / 2 TiB 容量模型提供第一条完整 Full3D iterative 实测锚点。