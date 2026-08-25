# Task040 Review Report V5：fresh bare-`F` authority、加速路线漏斗与 0.7 nm 导向的 side inverse

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V5
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = 3c591d5f8fb2ee74e69663f371ca77db3a145e58
reviewed_response                           = response_v5.md
reviewed_compact_record                     = task040_v4_1_exact_authority_compatibility_v1.json
reviewed_compact_sha256                     = 5ededd4bb9acfb9e4e3a403a410cecb37fb1490e7bf6056ca4644c7bfda7c36a
reviewed_formal_source_sha                  = 9f3d6e39cb607125a773b35d9a2a9f7459c7f2dc
reviewed_checker_source_sha                 = 4b70adfb6707464aaed4309ece5bca179dd60b57
review_status                               = PASS_WITH_CONTROLLED_IDENTITY_NEGATIVE_AND_CONTINUATION
V4_1_evidence                               = ACCEPTED
V4_1_gate                                   = FAIL_IDENTITY_AS_DESIGNED
V4_1_classification                         = EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F
V4_1_unique_failure                         = canonical_source_binding
bare_F_numerical_compatibility              = NOT_EVALUATED
trace_dual_projection_lift                  = NOT_RUN_BY_GATE
current_primary_blocker                     = VALID_CURRENT_BARE_F_EXACT_AUTHORITY_UNAVAILABLE
next_primary_action                         = FRESH_CURRENT_LAYOUT_BOTTOM_BARE_F_AUTHORITY
execution_mode                              = ACCELERATED_MULTI_ROUTE_FUNNEL
small_test_policy                           = MINIMAL_FOCUSED_RISK_BASED
one_diagnostic_heavy_authority_run          = AUTHORIZED
conditional_one_full_hybrid_run             = AUTHORIZED_AFTER_SIDE_GATES
same_branch_continuation                    = required
new_execution_branch                        = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
merge_approval                              = NO
physical_case                               = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
QEP_M_physical_DtN_global_Hybrid_change     = forbidden
full_0p7nm_PDE                              = forbidden
response_required                           = response_v6.md
```

提交 `e13456d2a2835490ec954dddc8bacc0f173bbbc9` 曾加入一份不符合角色分工的
`review_report_v5.md`，随后已经由当前 HEAD `3c591d5f8fb2ee74e69663f371ca77db3a145e58`
完整撤销。该被撤销文件不具有审阅权威。本文件是当前唯一有效的 Task040 Review V5。

本轮继续服务 Task040 唯一主线：

> 用稳定、低内存、可扩展的 iterative side inverse 替代 bottom/top 两个完整 exact MUMPS
> side factors，并使最终架构在 0.7 nm 更密网格下仍具有 bounded local factors、bounded
> global information、分布式数据和接近线性的 resident memory。

正式裁决如下：

1. 接受 V4-1 的 `controlled_identity_negative`。它证明旧 spool 缺少合格的 canonical
   source-row binding；它没有证明 exact vector 数值错误，也没有评价 span、dual、lift 或
   preconditioner；
2. 不再把“修补旧 raw-row remap”作为 Task040 的主要执行路线。旧 PETSc global row
   继续禁止跨布局直接搬运；
3. 旧 frozen output 由 `ResearchExactSideLuAction`/Woodbury 路径产生，其 operator 语义
   不能未经独立核验就视为 bare `F_b` authority。canonical bridge 即使建立，也不能代替
   bare-`F` operator identity Gate；
4. 本 Review 授权一次 bottom-only、current-layout、fresh bare-`F` exact authority producer。
   它可以临时建立一个完整 bare-`F` MUMPS factor，但只属于离线诊断 authority，不属于
   Task040 formal candidate，也不得进入 production side inverse；
5. authority 建立后，Codex 按本 Review 的 Route A/B/C 漏斗连续推进。某条路线达到明确
   no-signal Gate 后立即停止该路线并切换，不再反复扫描小参数；一旦出现跨 training/holdout
   的正信号，就沿该路线继续做到 bounded online reconstruction、Level B、bottom/top 和条件
   full Hybrid，不在普通小阶段停下来等待审阅；
6. 测试采用最小、风险驱动原则。不得让重复的 serial/MPI2/MPI4、全仓 pytest 或大规模
   schema 测试阻塞数值研究；但 ownership、orientation、Floquet、factor lifecycle 和独立
   true residual 等关键风险仍必须有直接测试；
7. 任何 h4 正信号都必须同时记录其 0.7 nm 延伸边界。若一个方法依赖随横截面或全局 DoF
   增长的 factor、rank、replicated basis 或 FE-sized allgather，即使 5 nm 有改善，也不得
   称为面向 0.7 nm 的候选。

---

## 1. V4-1 证据裁决与当前边界

### 1.1 已接受的身份负结论

V4-1 已独立验证：

```text
input / physical / selected / resolved identity       = pass
spool catalog / producer / exact-output metadata      = pass
canonical source-row binding                          = fail
checker                                                = 37/37 checks true
formal numerical vectors                              = not constructed
bare-F residual                                       = not run
A_side explanatory residual                           = not run
trace / projection / lift / FGMRES                    = not run
```

因此当前首要 blocker 不是“776 span 已被完整 exact 解证明不足”，而是：

```text
VALID_CURRENT_BARE_F_EXACT_AUTHORITY_UNAVAILABLE
```

### 1.2 旧 spool 的 operator-semantics 风险

旧 exact spool 的 producer 使用 exact bare-`F` factor 加 Woodbury 外部耦合来施加
`ResearchExactSideLuAction`。在没有独立 action/residual 证据前，不得将旧 output 简化解释为：

```text
F_b x* = b
```

它至少与完整 side action 的历史语义有关：

```text
A_side = F - C H^{-1} D
```

本 Review 不预判旧向量最终对哪个 operator 成立，只规定：

```text
old spool metadata = retained historical authority
old raw values      = not a current bare-F numerical authority
old raw-row remap   = forbidden
```

不得通过只增加一个 descriptor 或把 `bridge_qualified` 改成 `true` 绕过该 Gate。

### 1.3 未改变的正式基线

| 路线 | 范围 | process-tree RSS peak | 数值状态 | 当前用途 |
|---|---|---:|---|---|
| Hybrid direct h4 | full workflow | `93.377006531 GiB` | pass | matched authority |
| exact-side Hybrid iterative h4 | full workflow | `80.025856018 GiB` | pass | 当前最佳完整 iterative authority |
| V3-2 full776 | bottom bare-`F` component | `26.118938446 GiB` | numerical negative | mechanism baseline |
| V4-1 metadata preflight | identity only | `1.643180847 GiB` | controlled identity stop | 不属于 solver Pareto 点 |

V3-2 五源 `r16` 仍为 `0.9706859881–0.9832307912`。没有新的 bottom、top、both-side、full
Hybrid、h3 或 0.7 nm 数值结果。

---

## 2. 冻结物理、离散与禁止项

整个新 campaign 继续冻结：

```text
wavelength                         = 5.0 nm
grazing angle                      = 1 deg
azimuth                            = 0 deg
polarization                       = S
finite element                     = p6 Nedelec H(curl)
mesh                               = h4 formal mesh identity
scalar                             = complex128
Floquet x/y                        = unchanged
Hybrid internal modes              = M480 positive + M480 negative
selected-mode packet               = inherited hash-bound packet
static condensation                = unchanged
physical external DtN              = unchanged
modal traction/projection/Schur    = unchanged
global Hybrid MatPython action     = unchanged
recovery/physics/checker            = unchanged
formal MPI / threads               = 8 / 1
```

继续禁止：

```text
修改物理、材料、几何、p/h、M、external keys或normalization
重跑或改变QEP
扫描ordinary ILU/BLR/drop tolerance/restart/Robin参数
修改physical DtN或global Hybrid operator
重跑Hybrid direct authority
使用旧raw global row跨布局重建向量
把任何exact packet作为production runtime dependency
运行完整0.7 nm PDE
修改ordinary defaults
写入或合并master、Task039或其他分支
```

本 Review 对旧禁止项作一个狭窄覆盖：

```text
允许一次 current-layout bottom bare-F exact factor
用途 = fresh diagnostic authority producer only
formal scalable candidate factor count = 0 remains mandatory
```

---

## 3. 加速执行与最小测试政策

### 3.1 总原则

测试只覆盖本轮实际新增风险，不为每个 JSON 字段、marker 或文档句子单独增加测试。正常阶段
通过后直接继续；不得因“还没跑全仓 pytest”停止等待审阅。

### 3.2 测试分级

| 变更类型 | 最小要求 | 默认不要求 |
|---|---|---|
| docs/JSON-only | JSON parse、相对链接、Markdown table/math、`git diff --check` | Ruff、compileall、MPI、full pytest |
| pure packet/math helper | 直接相关 serial focused tests | MPI2/MPI4、全仓测试 |
| owner/scatter/collective | serial + MPI2 focused test | 每次同时跑 MPI4 |
| orientation/Floquet/partition identity | serial + MPI2；在 formal 前或关键实现完成时一次 MPI4 | 每个 commit 重复 MPI2/MPI4 |
| PETSc factor/action lifecycle | 一个直接 component/tiny test + cleanup inventory | 全套历史 Task039/040 tests |
| formal numerical run前 | touched tests、Ruff touched files、compileall touched modules、clean SHA | full repository pytest |
| response_v6 closeout | 一次 consolidated focused suite、documentation contract、repository principles、benchmark no-write | 无关旧 heavy tests |

`MPI4` 只在以下情况运行：

```text
partition invariance本身被修改
MPI2不能覆盖owner split
或进入正式MPI8前需要一次最终分区检查
```

如果一个实现 bug 已由一个 focused regression 精确复现并修复，不得再用大量旁系测试阻塞同一
阶段。保留失败 root、加一条直接回归、重跑同阶段后继续。

### 3.3 Case104 合同缺口

在新的 formal heavy run 前，最小关闭现有 Case104 numbered-case registration gap。只需建立
case-contained research contract并使：

```text
test_26_documentation_contract.py
test_24_repository_work_principles.py
```

一次通过。通过后，除非这些合同文件再次修改，不要求在每个数值阶段重复运行。

### 3.4 重型运行纪律

```text
一次只运行一个heavy process tree
formal前 MemAvailable / swap / disk / source SHA / clean worktree全部通过
达到hard stop终止完整进程组
失败root与原始telemetry保留
数值negative不因重跑或改阈值而消失
```

本 Review 最多预授权：

```text
1 次 fresh bare-F authority producer
每条算法路线最多 1 个正式component screen序列
最终selected candidate最多 1 次 full Hybrid formal
通过后最多 1 次 h3 scaling probe
```

implementation failure 的同阶段最小修复重跑不计作新算法路线，但必须有明确复现和新 SHA。

---

# 4. 连续执行总路线

```text
V5-0  Case104 contract closure + inherited audit
V5-1  authority operator-semantics audit and fresh-run preflight
V5-2  one fresh current-layout bottom bare-F exact authority producer
V5-3  fresh no-full-factor reconstruction + exact trace/lift decomposition

classification:
    dual/composition issue       -> Route A
    span/coarse-content issue    -> Route B
    exact authority unavailable  -> Route C

positive route:
    bounded total-rank coarse
    -> packet-independent online rebuild
    -> bounded local patch Level B
    -> bottom bare F
    -> bottom full A_side
    -> same-config top
    -> both-side setup
    -> one full Hybrid formal
    -> conditional h3 scaling
    -> 0.7 nm capacity implications

V5-final  compact evidence + outcomes + response_v6.md
```

Codex 不需要在 V5-0、V5-1、普通 focused test、R1/R2/R3 或 rank筛选之间等待审阅。只在本
Review 的 stop Gate、完整成功或全部路线无信号后停止。

---

## 5. V5-0：Case104 与继承审计

### 5.1 必须完成

最小补齐：

```text
benchmarks/cases/104_5nm_hybrid_side_factor_pc/README.md
benchmarks/cases/104_5nm_hybrid_side_factor_pc/config.json
benchmarks/cases/104_5nm_hybrid_side_factor_pc/schema.json
benchmarks/cases/104_5nm_hybrid_side_factor_pc/expected.json
benchmarks/cases/104_5nm_hybrid_side_factor_pc/test_command.txt
```

允许对 `src/test/test_26_documentation_contract.py` 做最小、通用的 active-research contract
支持，不得弱化其他 case。

### 5.2 状态合同

至少绑定：

```text
status                    = active_research_controlled_identity_negative
canonical                 = false
production_qualified      = false
ordinary_default_changed  = false
pde_run_in_v4             = false
V4-2 through V4-10        = not_run_by_v4_1_identity_gate
```

完成后自动继续 V5-1，不等待 review。

---

## 6. V5-1：authority semantics 与 fresh producer preflight

### 6.1 先做轻量 source audit

明确记录：

```text
old exact spool producer action
old output operator semantic
old RHS source definitions
current bare-F builder/action/hash route
current canonical active trace extraction/reconstruction route
```

结论必须区分：

```text
old A_side or Woodbury-associated authority
current bare-F authority
```

不得把二者混写。

### 6.2 fresh RHS 规则

五个 RHS 必须在 current source/current layout 中按冻结 source definition重新生成，而不是加载旧
row数组：

```text
modal_traction_positive
modal_traction_negative
external_dtn_coupling
fixed_random_repeat_0
fixed_random_repeat_1
```

每个 RHS 绑定：

```text
source definition/hash
current ownership ranges
canonical key-set hash
norm/finite/repeat
input/physical/selected/resolved/source SHA
```

随机源必须由 canonical physical identity 或明确的当前 active-row stable formula生成；不得把
旧 PETSc global row 当作物理 identity。

### 6.3 preflight Gate

```text
branch/upstream/worktree clean
PETSc complex128 / MPI8 / threads1
input/physical/selected hashes exact
qep_calls = 0
swap = 0
MemAvailable >= 90 GiB
process-tree watchdog active
output disk >= 20 GiB
only bottom bare-F route enabled
```

若环境不满足，记录 `not_run_by_resource_preflight`，切换 Route C 的低内存在线方向采样；不得
通过降低系统安全余量强行启动。

---

## 7. V5-2：一次 fresh current-layout bare-`F` exact authority producer

### 7.1 它解决什么问题

这一步用当前布局临时建立一次 exact bare-`F` factor，直接回答“正确的 current bare-`F` 解
是什么”。它改变的是诊断 authority 的生成方式，不改变 Task040 candidate，也不改变物理方程。

### 7.2 固定范围

```text
side                              = bottom only
operator                          = explicit current bare F_b
factor                            = one MUMPS exact factor
RHS                               = frozen five
physical DtN / C-D-H-W-K          = not constructed for solve
QEP                               = 0
selected-mode packet              = reuse only where source construction requires
three-group factors               = 0
full Hybrid                       = not run
recovery/physics                  = not run
ordinary default                  = unchanged
```

producer 对每个 RHS 解：

```text
F_b x_j* = b_j
```

并用完整显式 action检查：

```text
relative true residual <= 1e-9
repeat <= 1e-12
all finite = true
```

### 7.3 authority packet

producer 必须写出 owner-sharded、hash-bound 的 current canonical packet：

```text
five RHS canonical packets
five exact-output canonical packets
current owner-row shards for same-layout direct audit
Gamma_L exact trace packets
Gamma_U exact trace packets
source/operator/key-set/value/shard/manifest hashes
current bare-F hash and ownership ranges
```

大数组保存在 ignored results；Git只提交 compact manifest/record。

### 7.4 生命周期与资源

```text
full-side exact factor count      = 1 -> 0
factor retained in consumer       = false
producer exits before consumer    = true
swap                              = 0
preferred peak                    <= 55 GiB
warning                           = 58 GiB
absolute hard stop                = 64 GiB
```

该峰值只属于 `DIAGNOSTIC_BARE_F_AUTHORITY_ORACLE`，不得加入 scalable candidate Pareto，也
不得称为新的 Hybrid workflow。

### 7.5 producer 决策

```text
FRESH_BARE_F_AUTHORITY_PASS
    five residual <=1e-9，packet identity/round-trip/lifecycle/resource通过

FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED
    identity/preflight正确，但达到hard stop或环境不足；转Route C

FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL
    source/operator/canonical key无法一致重建；只允许一次最小identity修复

FRESH_BARE_F_AUTHORITY_NUMERICAL_FAIL
    exact solve本身未达到bare-F residual；停止并报告operator/RHS/factor证据
```

除 implementation failure 外，不得为 producer 扫描 MUMPS 参数或重复 heavy run。

---

## 8. V5-3：fresh no-full-factor trace/lift consumer

consumer 在 fresh MPI8 进程中：

```text
重新装配相同 bare F_b
读取canonical authority packet
重构current owner layout的RHS和exact output
full-side exact factor = 0
验证five F_b x* - b residual <=1e-9
```

随后使用同一 lower/upper ordering 比较：

```text
exact trace t*
current Petrov trace tP
interface-mass metric-best trace tB
```

metric-best 必须用 stable complex QR/SVD，不得形成 normal equations。

三种 trace 使用同一个 particular solve和同一个 group back-substitution，得到：

```text
x_lift_exact
x_lift_petrov
x_lift_best
```

报告五源：

```text
lower/upper/joint trace representation error
full solution relative error
full bare-F true residual
Petrov-vs-best coefficient/trace difference
factor lifecycle
process-tree RSS / swap / wall
```

exact-trace lift identity Gate：

```text
five solution relative error <=1e-8
five bare-F true residual    <=1e-9
group factors                = 3 -> 0
full-side exact factor       = 0
peak                         <45 GiB
swap                         =0
```

若 exact-trace lift identity 失败，先按 implementation/algebra identity处理；只允许围绕
restriction、sign、orientation、row ordering和back-substitution做最小修复。若一个明确修复后
仍无法建立 identity，分类：

```text
GROUP_LIFT_IDENTITY_NOT_ESTABLISHED
```

并停止，不得用 response enrichment掩盖错误的 lift。

---

# 9. Route A：dual / lift / two-level composition 窄修正

Route A 只在 fresh exact decomposition 表明当前 span 足以表示主要 trace 时使用。

## 9.1 A1 mass-dual

触发条件：

```text
best-trace lift有效
Petrov-trace lift明显更差
```

只允许同一 `Z` 的固定 interface-mass dual；不得换 basis family、增加 rank或扫描 regularization。
运行：

```text
one-apply
continuous FGMRES 4/8/16/conditional32
five frozen RHS
```

## 9.2 A2 one-post composition

触发条件：

```text
best与Petrov lift均有效
但V3-2完整preconditioner仍弱
```

只允许：

```text
local pre
-> true residual
-> coupled interface correction
-> true residual
-> one local post
```

不增加 sweep、overlap、damping或新参数。

## 9.3 Route A 信号与退出

```text
ROUTE_A_STRONG_SIGNAL
    five r16相对V3-2至少改善5倍，且modal+/modal-/external <=0.1

ROUTE_A_WEAK_POSITIVE_SIGNAL
    five源均改善，worst r16至少改善2倍，holdout无明显退化

ROUTE_A_NO_SIGNAL
    固定A1/A2后worst改善不足2倍，或任一holdout恶化超过20%
```

`STRONG` 或 `WEAK_POSITIVE` 后不再停下审阅，直接进入 bounded-rank/online reconstruction；
`NO_SIGNAL` 立即结束 Route A，转 Route B，不扫描更多 dual/post/sweep 菜单。

最终 side numerical Gate仍保持：

```text
all mandatory <=1e-2
modal+/modal-/external <=1e-3
preferred <=64 iterations
research <=256 iterations
```

---

# 10. Route B：response-enriched coupled coarse

Route B 是 fresh exact decomposition 证明 span/coarse content不足时的主路线。

## 10.1 B1 R1/R2/R3 mechanism pilot

冻结：

```text
training = modal_traction_positive, external_dtn_coupling, fixed_random_repeat_0
holdout  = modal_traction_negative, fixed_random_repeat_1
```

对 training 构造：

```text
missing trace = exact trace - metric-best current-span trace
```

用 interface mass metric去除已有span后，通过complex RRQR/SVD形成最多三个嵌套方向：

```text
R1 / R2 / R3
```

不得增加 R4+，不得更换 train/holdout。

## 10.2 B1 信号 Gate

```text
ROUTE_B_STRONG_SIGNAL
    all training r16 <=0.1
    two holdout r16各自至少改善2倍

ROUTE_B_WEAK_POSITIVE_SIGNAL
    training median r16改善>=30%
    两个holdout均改善>=20%
    无source出现明显不稳定或非有限

ROUTE_B_OVERFIT
    training改善，但任一holdout无改善或恶化

ROUTE_B_NO_SIGNAL
    R3后training worst仍>0.7，或training/holdout均无一致改善
```

`STRONG` 或 `WEAK_POSITIVE`：沿 Route B 一直推进到 online/Level B；
`OVERFIT`：保留 exact direction仅作oracle标签，转 Route C 的online directions；
`NO_SIGNAL`：停止当前 exact-trace enrichment family，转 Route C。

## 10.3 B2 bounded total-rank audit

最终 coarse 是总rank，而不是在776上无限叠加：

```text
64 / 128 / 256 / 512
```

先离线计算 representation/lift/train/holdout proxy。只有最小满足 proxy 的 rank及下一较大rank
进入 component FGMRES；heavy rank screen最多两个，不运行四个rank菜单。

离线 stop Gate：

```text
rank512 modal+/modal-/external lifted residual >0.1
或 five-source worst lifted residual >0.25
```

分类：

```text
BOUNDED_RESPONSE_COARSE_NOT_ESTABLISHED_BY_RANK512
```

并停止 Route B。

## 10.4 B3 online reconstruction

oracle rank通过后，fresh进程必须只使用：

```text
bare-F action
bounded current local/group PC
frozen deterministic training RHS
online residual / harmonic Ritz extraction
fixed selection rule
```

重新生成同一总rank coarse。construction中：

```text
exact outputs loaded = 0
exact packet required = false
full-side exact factor = 0
FE-sized allgather = false
full basis replication = false
```

oracle-vs-online principal-angle sine目标 `<=1e-6`；若无法移除exact依赖，分类：

```text
EXACT_ORACLE_DEPENDENCE_NOT_REMOVED
```

并停止，不得进入Level B。

---

# 11. Route C：online long-Krylov / harmonic-Ritz fallback

Route C 在以下任一情况启动：

```text
fresh authority被resource preflight或64 GiB hard stop阻止
Route B出现overfit或no-signal
exact packet可用但不适合成为运行时coarse来源
```

它不需要 exact output 参与basis构造。

## 11.1 固定采样

只运行：

```text
external_dtn_coupling
fixed_random_repeat_0
```

每个 RHS 一个连续 right-FGMRES：

```text
restart = 32
checkpoints = 16 / 32 / 64 / 128
conditional = 256
```

不允许512、1000或五源全部长跑。

保存：

```text
true residual history
lower/upper interface residual traces
每restart最多8个harmonic Ritz directions
跨RHS shared-subspace diagnostics
owner-row distributed basis
```

## 11.2 Route C 信号与退出

```text
ROUTE_C_STRONG_SIGNAL
    r128 <=0.5
    或64->128下降>=0.25 decade

ROUTE_C_WEAK_POSITIVE_SIGNAL
    r128 <=0.8
    或64->128下降>=0.10 decade
    或两个RHS存在稳定共享慢方向

ROUTE_C_NO_SIGNAL
    r128 >0.9
    且64->128下降<0.05 decade
    且无稳定共享慢方向
```

`STRONG` 或 `WEAK_POSITIVE`：使用 online directions 构造总rank `64/128/256/512`，沿用 Route B
的最多两个rank screen和fresh reconstruction Gate；
`NO_SIGNAL`：停止当前 coupled-response coarse family。此时不得继续靠更多RHS、更长迭代或
更多rank追逐结果，应在 `response_v6.md` 中将 Task040 当前 side-interface family分类为无正
信号并等待新算法 review。

256只在下列条件同时满足时运行：

```text
finite
peak <45 GiB
swap=0
r128 <=0.8 或64->128下降>=0.05 decade
总wall可控
```

---

# 12. Route D：有正信号后的 productionization 与完整工作流

Route D 不是独立救援路线。只有 Route A/B/C 中至少一条建立 bounded、online、holdout有效的
coarse 后才进入。

## 12.1 删除横截面 group factors

把当前三个 cross-section exact group factors替换为：

```text
local FGMRES
+ bounded overlapping patch PC
+ selected bounded coupled coarse
```

硬合同：

```text
full-side exact factor          = 0
full-cross-section factor       = 0
global direct factor            = 0
max_local_rows                  <=1024
coarse total rank               <=512
factor class count              = bounded and reported
one deterministic owner/class   = true
FE-sized numeric allgather      = false
full basis per-rank replica     = false
```

bottom bare-`F` Gate：

```text
all mandatory <=1e-2
modal+/modal-/external <=1e-3
preferred <=64 iterations
research <=256 iterations
construction peak <=35 GiB
strong target <=30 GiB
post-setup retained <=30 GiB
swap=0
```

若 `max_local_rows>1024`、rank必须超过512、内存超过35 GiB或256步仍无Gate，Route D停止；
不得扩大上限掩盖0.7 nm不可扩展性。

## 12.2 一直推进到完整 Hybrid

bottom bare-`F`通过后，Codex无需中途review，按完全相同参数连续执行：

```text
bottom full A_side with physical DtN unchanged
same-config top bare F and A_side
both-side setup-only
one full Hybrid formal
```

不得为top单独调rank、patch、restart、budget或training source。

full Hybrid沿用 Task039 authority Gate：

```text
reported/global/bottom/top/modal true residual <=5e-9
recovery pass
R/T/A/A_volume matched
selected E/H matched
canonical/normal flux/channels matched
external keys/order exact
bottom/top full-side exact factor = 0/0
global direct factor = 0
swap = 0
```

完整峰值必须与：

```text
93.377006531 GiB direct
80.025856018 GiB exact-side iterative
```

比较，并报告真实 memory-residual-time Pareto。只要 `<80.025856018 GiB` 即为新完整低点；
`<=65.363904572 GiB` 为至少30% direct节省的强目标，但不是唯一成功条件。

---

## 13. 0.7 nm 延伸合同

每个候选和每条失败路线都必须回答：

> 它消除了“2 TB 内存内求解 0.7 nm 三维 Maxwell”的哪个 blocker？它是否引入了另一个随
> 网格增长的 blocker？

### 13.1 必须报告的内存组成

```text
side active rows N
explicit bare-F bytes
PC retained bytes
local factor bytes
coarse basis/operator bytes
Krylov bytes
construction transient
process-tree RSS peak
MPI replication/allgather inventory
```

### 13.2 0.7 nm-oriented hard requirements

```text
full/global exact factor        = 0
full-cross-section factor       = 0
max_local_rows                  <=1024 and independent of N
coarse total rank               <=512
coarse rank selection           = physics/response bounded, not proportional to N
full basis replication          = false
FE-sized numeric allgather      = false
swap                            = 0
```

显式 bare `F` 仍由 Task040 允许，用作operator carrier与true-residual authority；但最终
0.7 nm production路线仍需要后续 cell-wise/matrix-free action。Task040 不得把“显式 `F` 尚可
存在”误写成0.7 nm最终架构已经完成。

### 13.3 条件 h3 probe

只有完整 h4 side candidate通过后，允许一次 `p6/h3` bottom setup/apply和有限checkpoint：

```text
same PC parameters
same coarse rank
same max_local_rows
no top
no full Hybrid
no QEP
```

目标：

```text
PC retained memory exponent p_mem <=1.30
max_local_rows unchanged
coarse rank unchanged
no new replication/allgather
```

### 13.4 2 TB capacity implications

`response_v6.md` 必须将结果区分为：

```text
measured  = h4/h3实际RSS、bytes、iterations、wall
derived   = 由实测component ledger计算的占比或指数
predicted = 0.7 nm在2 TB物理内存下的容量区间
not_run   = 未运行的0.7 nm PDE或full-scale geometry
```

2 TB是整机物理内存，不是单进程可占满的RSS。预测必须保留系统余量、zero swap、一次一个heavy
case和process-tree watchdog，不得因内存总量增加就宣称当前架构自动可行。

---

## 14. Stop Gate 与自主继续权限

### 14.1 Codex必须停止的情况

```text
fresh bare-F exact residual无法达到1e-9
fresh authority达到64 GiB hard stop且Route C也无正信号
exact-trace lift identity在一次明确最小修复后仍失败
Route A固定对照无2倍改善
Route B R3无training/holdout一致信号
rank512仍无法满足bounded proxy
Route C满足NO_SIGNAL
online reconstruction无法移除exact dependence
Level B违反rows/rank/memory/iteration scalability Gate
same-config top出现不可解释数值失败
full Hybrid residual/physics/resource Gate失败
所有A/B/C路线均已分类为no-signal/blocked
```

### 14.2 不需要停止的情况

```text
docs/JSON合同修复
path/schema/hash/marker错误
PETSc owner/scatter/workspace错误
orientation/Floquet phase-once且tiny oracle明确的错误
checker/watchdog/telemetry wiring错误
单个focused test回归修复
Route内出现已定义的正信号
```

这些情况保留失败现场、最小修复、一个直接回归后自动继续。

### 14.3 有正信号就做到底

若 Route A/B/C 任一条达到 `STRONG_SIGNAL` 或 `WEAK_POSITIVE_SIGNAL`，Codex自动沿该路线完成：

```text
bounded rank
online rebuild
Level B
bottom full side
top
both-side
full Hybrid
conditional h3
0.7 nm capacity implications
```

除真正Gate外，不得在“完成一个小实验”“写完一个outcome”或“还没跑全仓测试”时停止等待审阅。

---

## 15. Evidence、outcomes 与 response_v6

至少新增或更新：

```text
outcomes/authority_operator_semantics.md
outcomes/fresh_bare_f_authority.md
outcomes/exact_trace_representability.md
outcomes/group_lift_identity.md
outcomes/route_signal_ledger.md
outcomes/long_krylov_direction_sampling.md
outcomes/response_enriched_coarse.md
outcomes/bounded_patch_pc.md
outcomes/production_side_inverse.md
outcomes/bottom_full_side.md
outcomes/top_full_side.md
outcomes/both_side_setup.md
outcomes/full_hybrid_result.md
outcomes/h_refinement_scaling.md
outcomes/0p7nm_side_pc_capacity.md
outcomes/memory_residual_time_pareto.md
outcomes/test_summary.md
outcomes/summary.md
response_v6.md
```

`route_signal_ledger.md` 必须对 A/B/C 每条路线记录：

```text
entry condition
exact configuration
actual residual checkpoints
training/holdout behavior
memory/wall
positive/no-signal classification
继续或切换原因
0.7 nm scaling implication
```

compact records必须从raw fields重算，不相信预填status；大packet和完整日志保留在ignored
`results/`。

`response_v6.md` 至少包含：

```text
branch / exact HEAD / upstream / worktree
all commits after this Review
focused test matrix and deliberately not-run tests
fresh authority result and factor lifecycle
A/B/C route ledger
selected route or all-routes-negative conclusion
bottom/top/full Hybrid results if reached
h3 result if reached
0.7 nm and 2 TB implications
selective merge dependency groups
remaining blockers
```

---

## 16. 提交与审阅节奏

建议提交按真正阶段组织，而不是每个小修复都拆成独立停顿：

```text
fix(task040): register Case104 active research contract
feat(task040): add fresh bare-F authority and canonical packet path
bench(task040): qualify fresh bare-F authority and trace lift
feat(task040): pursue selected coupled coarse route
feat(task040): replace group factors with bounded local patches
bench(task040): qualify factor-free side and full Hybrid
 docs(task040): close accelerated route funnel and response v6
```

可以根据实际路线省略未发生的提交，但不得把数值核心、heavy evidence和最终文档全部混成一个
不可审阅巨型提交。提交并推送后正常继续，不要求每次等待ChatGPT。

---

## 17. Merge 与生产边界

```text
merge approval = NO
```

本 Review 只授权在当前 Task040 分支继续研究。即使 fresh authority、某条route或full Hybrid
通过，也必须由下一轮 ChatGPT review决定 selective merge。旧 spool bridge、exact authority
producer、cross-section oracle、失败route和大packet默认属于 research-only；不得提升为ordinary
production default。

最终判断：

```text
V4-1 evidence accepted                         = yes
current numerical side-PC pass                 = no
fresh current bare-F authority                 = authorized
minimal focused testing                        = required
blind parameter/test menu                      = forbidden
multiple route funnel                          = authorized
no-signal early route switch                   = required
positive-signal end-to-end continuation        = required
one conditional full Hybrid formal             = authorized
direct 0.7 nm PDE                              = not authorized
0.7 nm-oriented scalability accounting         = mandatory
master merge                                   = not approved
```
