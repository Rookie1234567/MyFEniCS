# Task040 Review Report V4：exact 解可表示性、三维 lift 定位与 response-enriched coarse

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V4
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head_before_review          = 589e982c9074b6231ba17adb344ccfb9ceeebecc
reviewed_response                           = response_v4.md
reviewed_compact_record                     = task040_v3_2_full_span_consumer_v1.json
reviewed_numerical_source_sha               = c11aea058d01e86052d5490a71575a375e3fe207
reviewed_checker_source_sha                 = 0fbc33d07d27f8e4b2bce9c2bae2704ea9372c7b
review_status                               = PASS_WITH_QUALIFICATIONS
V3_2_full776                                = CONTROLLED_NUMERICAL_NEGATIVE
V3_2_identity_resource_lifecycle            = PASS_COMPONENT
current_776_small_system_solve              = NUMERICALLY_ACCURATE_INSIDE_SELECTED_SPAN
full_bare_F_side_inverse                    = NOT_QUALIFIED
primary_unresolved_question                 = SPAN_VS_DUAL_VS_LIFT_COMPOSITION
next_primary_action                         = EXACT_AUTHORITY_REPRESENTABILITY_AND_LIFT_DECOMPOSITION
long_FGMRES_role                            = DIAGNOSTIC_DIRECTION_DISCOVERY_ONLY
response_enriched_coarse                    = AUTHORIZED_CONDITIONALLY
same_branch_continuation                    = required
new_branch                                  = forbidden
master_or_Task039_write                     = forbidden
ordinary_default_change                     = forbidden
merge_approval                              = NO
physical_case                               = 5 nm / 1 deg grazing / phi=0 / S / p6h4 / M480 / MPI8
QEP_M_physical_DtN_global_Hybrid_change     = forbidden
full_0p7nm_PDE                              = forbidden
response_required                           = response_v5.md
```

本轮审阅始终服务于 Task040 的唯一主线：

> 用稳定、低内存、可扩展的 iterative side inverse 替代 bottom/top 两个完整 exact MUMPS
> side factors；最终候选必须在 0.7 nm 更密网格下仍保持 bounded local factors、bounded
> coarse information 和近线性 resident memory，而不能把完整 side factor换成另一种增长型大
> factor。

正式裁决：

1. V3-2 已经证明 lower/upper 联合 `776 x 776` 接口系统可以正确组装、求解和释放，三个
   group factor与一个 reduced factor的资源峰值为 `26.118938446 GiB`，swap为零；
2. V3-2 同时证明，当前 `296 + 480` span 与当前 harmonic lift/back-substitution组合，不能
   在16步内形成有效 bare-`F` side inverse；五个 true residual仍为 `0.97069–0.98323`；
3. 当前 reduced solve内部 residual约为 `1e-14`，所以不能继续把问题归因于`776 x 776`
   线性系统没解准；
4. 下一步必须先把失败拆成三个可能来源：
   `current span不能表示正确接口场`、`left/right dual投影不合适`、`接口场向三维group内部的
   lift或pre/coarse组合不正确`；
5. 本轮允许使用已有、hash-bound的 exact-side frozen outputs作为**诊断 authority**，但禁止
   为此重新建立一个 full-side exact factor；
6. 几百次三维Maxwell迭代在独立单次求解中并不反常，但 side inverse会被 bottom/top、modal
   Schur和outer Hybrid反复调用。因此长FGMRES只用于采集慢残差、harmonic Ritz和接口困难
   方向，不得被包装成0.7 nm生产方案；
7. 只有证据确认 coarse内容不足后，才构造 response-enriched coarse；只有该coarse可由
   `bare F action + bounded local PC + frozen training RHS`在fresh进程中重建，才有资格继续
   bounded patch Level B。

---

## 1. 已审阅事实与边界

### 1.1 完整 workflow 基线

| 路线 | 范围 | process-tree RSS peak | 数值/物理状态 | 当前用途 |
|---|---|---:|---|---|
| Hybrid direct h4 | full workflow | `93.377006531 GiB` | matched authority pass | direct reference |
| exact-side Hybrid iterative h4 | full workflow | `80.025856018 GiB` | residual、recovery、R/T/A、E/H、canonical、channels pass | 当前最好完整 iterative authority |
| V3-2 full776 | bottom bare-F component | `26.118938446 GiB` | identity/resource pass，numerical fail | mechanism diagnostic |

V3-2 的 `26.119 GiB` 是 bottom component，不得称为完整 Hybrid saving tier。当前完整
workflow 最好结果仍为 `80.025856018 GiB`，相对 direct节省 `14.298%`。

### 1.2 V3-2 联合接口与 FGMRES

```text
joint shape       = 776 x 776
joint rank        = 776
joint condition   = 7.253085663880321e7
lower span        = 296
upper span        = 480
lower+upper rows  = 15120
```

| source | r4 | r8 | r16 |
|---|---:|---:|---:|
| modal traction positive | `0.9931120049` | `0.9908281637` | `0.9753543932` |
| modal traction negative | `0.9947389066` | `0.9916159544` | `0.9753434892` |
| external DtN coupling | `0.9873782795` | `0.9829723344` | `0.9706859881` |
| fixed random repeat 0 | `0.9910369479` | `0.9889049160` | `0.9829154078` |
| fixed random repeat 1 | `0.9920231223` | `0.9893566601` | `0.9832307912` |

这些数据说明 full776 比 V2 groupwise sweep略有改善，但仍远离：

```text
all mandatory true residual <= 1e-2
modal+ / modal- / external  <= 1e-3
```

### 1.3 已有 failure decomposition

V3-1 已记录：

| probe family | projected-exact error |
|---|---:|
| current span内 modal combination | `2.4890293803e-8` |
| physical trace | 约 `1.02035` |
| current span正交补 | 约 `1.02819` |

因此当前 strongest hypothesis是：

> 当前方法对它已经认识的接口模态方向处理准确，但真实 side error还包含大量不在这些方向中的
> physical/complement response。

该结论仍是 probe级证据；本Review首先要求用完整 exact-side solution直接验证。

---

## 2. 为什么不能只继续增加迭代次数

当前研究的是：

```math
F_b x=b,
```

其中 `F_b` 是 bottom三维 static-condensed Nédélec bare operator。FGMRES每一步调用：

```text
三个group局部solve
-> lower/upper接口residual
-> reduced coarse solve
-> interface synthesis
-> 三个group back-substitution
```

三维、complex、non-Hermitian、indefinite Maxwell问题需要几百次迭代并不罕见；Task037和
Task037b的13.5 nm正结果分别需要约 `341–365` 和 `792` 次迭代。因此16步不能证明数学上永不
收敛。

但 side inverse不是一次独立PDE solve。它未来会用于：

```text
bottom多个RHS
top多个RHS
modal Schur构造
outer Hybrid FGMRES反复apply
```

若每个side RHS需要数千步，完整Hybrid时间将不可接受，0.7 nm时也不会自然改善。因此：

```text
long FGMRES = 诊断和困难方向采样
long FGMRES != production pass
```

本Review不授权五个RHS全部盲目运行到1000步，也不允许通过增加max_it把弱PC包装成成功。

---

## 3. 冻结项与允许修改

继续冻结：

```text
5 nm / 1 deg grazing / phi=0 / S
p6/h4 / M480 / MPI8 / threads1
material / geometry / Floquet
selected-mode packet、mode keys、beta branches和normalization
static condensation和explicit bare F
physical external DtN / C-D-H-W-K
modal traction / projection / modal Schur
global Hybrid MatPython action
recovery / R-T-A / E-H / canonical / channel checker
```

禁止：

```text
重跑或改变QEP
改变M480或扫描mode count
调scalar beta、sign、damping或sweep count
普通ILU/BLR参数菜单
修改physical DtN或dynamic DtN redesign
修改global Hybrid operator
重跑Hybrid direct authority
重新建立full-side exact factor
完整0.7 nm PDE
```

允许：

```text
读取已有hash-bound exact-side frozen outputs用于诊断
exact trace representability与group lift审计
一个固定的local-pre/coarse/local-post组合对照
两个代表RHS的bounded continuous FGMRES采样
response/harmonic-Ritz enriched coarse
通过后的bounded local patch Level B
```

---

## 4. Implementation bug 自主修复权限

Codex可自行最小修复并继续：

```text
syntax/import/type/path/package invocation
exact spool字段、SHA、canonical key和owner remap接线
PETSc Vec/Mat ownership、scatter、workspace alias
lower/upper row ordering与trace extraction
block sign、restriction、prolongation和back-substitution接线
对象destroy顺序和明确内存泄漏
checker、watchdog、telemetry和artifact registry
由tiny/exact algebra证明的transpose、conjugation、orientation或phase-once bug
```

要求：保留失败root，分类为`implementation_failure`；先用unit/tiny/MPI测试复现；做最小
修复；新增回归测试；绑定新source SHA后重跑同一阶段。

下列变化不是bug fix，必须按Gate执行：

```text
更换basis family或training source
增加未授权rank/iteration菜单
改变分区或增加overlap
加入新coarse family
放宽residual、memory、rank或local-row上限
```

---

# 5. 连续执行顺序

```text
V4-0  inherited audit
V4-1  exact authority compatibility与trace/lift decomposition
V4-2  条件dual或two-level composition狭窄修正
V4-3  exact-response enrichment train/holdout pilot
V4-4  bounded continuous FGMRES direction sampler
V4-5  response-enriched bounded coarse audit
V4-6  packet-independent/online production reconstruction
V4-7  bounded local patch Level B
V4-8  bottom full side / top / both / full Hybrid
V4-9  conditional h3 scalability probe
V4-10 evidence、Pareto、response_v5.md
```

正常通过或可修复implementation bug后自动继续；只有本Review定义的真实identity、数值、
资源、泛化、packet-independent或扩展性Gate才停止等待审阅。

---

## 6. V4-0：继承审计

第一提交：

```text
docs(task040): audit review v4 trace response campaign
```

创建或更新：

```text
outcomes/review_v4_inherited_audit.md
outcomes/exact_trace_representability.md
outcomes/group_lift_identity.md
outcomes/long_krylov_direction_sampling.md
outcomes/response_enriched_coarse.md
outcomes/production_side_inverse.md
```

至少绑定：

```text
branch / HEAD / upstream / worktree
review_report_v4 identity
response_v4与V3-2 compact hash
exact-spool catalog与五个exact-output identity
input / physical / selected / probe hashes
bare-F hash
93.377 / 80.026 / 26.119 GiB baselines
V3-2 r4/r8/r16表
所有冻结项和禁止项
```

V4-0只允许docs，不运行heavy。

---

## 7. V4-1：exact authority compatibility与trace/lift decomposition

### 7.1 目的

只回答三个问题：

```text
A. 当前776 span能否表示正确side解的lower/upper接口trace？
B. 当前left/right dual是否把可表示的trace投影错了？
C. 给定正确接口trace后，当前group harmonic lift/back-substitution能否恢复正确三维side解？
```

### 7.2 authority来源

只允许读取已有 exact-spool 中五个冻结RHS及其 exact outputs：

```text
modal_traction_positive
modal_traction_negative
external_dtn_coupling
fixed_random_repeat_0
fixed_random_repeat_1
```

不得重新建立full-side exact factor。必须先在fresh MPI8进程中验证：

```math
\frac{\lVert F_b x_j^\star-b_j\rVert_2}{\lVert b_j\rVert_2}
\le 10^{-9}.
```

同时绑定 exact-output identity、canonical active-row keys、bare-F hash与source SHA。任何一项
不兼容，停止为：

```text
EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F
```

不得静默重算exact factor。

### 7.3 提取真实接口trace

对每个 `x_j^star` 提取：

```text
lower Gamma trace：7560 rows
upper Gamma trace：7560 rows
joint trace：15120 rows
```

使用canonical keys而不是假设PETSc global row稳定。

### 7.4 两种投影必须同时计算

#### 当前Petrov投影

```math
c_P=G^{-1}Y^Ht^\star,
\qquad
t_P=Zc_P.
```

#### 与dual无关的metric-best投影

使用冻结interface mass metric，通过complex QR/SVD求：

```math
c_B=\arg\min_c\lVert t^\star-Zc\rVert_{M_\Gamma},
\qquad
t_B=Zc_B.
```

禁止使用normal equations。必须分别报告 lower、upper、joint 的：

```text
Euclidean relative error
interface-mass relative error
Petrov-vs-best coefficient difference
Petrov-vs-best trace difference
```

### 7.5 exact-trace与projected-trace三维lift

构造相同local particular solve，并分别使用：

```text
真实trace t*
当前Petrov trace tP
metric-best trace tB
```

做三个group内部回代，得到：

```text
x_lift_exact
x_lift_petrov
x_lift_best
```

必须报告：

```math
\frac{\lVert x_{lift}-x^\star\rVert_2}{\lVert x^\star\rVert_2},
```

以及：

```math
\frac{\lVert b-F_bx_{lift}\rVert_2}{\lVert b\rVert_2}.
```

### 7.6 identity Gate

真实trace lift必须满足：

```text
all five solution relative error <=1e-8
all five full bare-F residual      <=1e-9
finite / repeat / linearity        =pass
group factor lifecycle             =3 -> 0
full-side exact factor             =0
swap                               =0
peak                               <45 GiB
```

若失败且tiny/exact algebra证明为implementation bug，Codex可最小修复并重跑。否则停止：

```text
EXACT_TRACE_LIFT_IDENTITY_NOT_ESTABLISHED
```

### 7.7 诊断分类

identity通过后，按以下规则分类；允许多标签并存：

```text
CURRENT_SPAN_INSUFFICIENT
    任一modal+/modal-/external的best-trace lift full residual >0.1
    或五源worst best-trace lift residual >0.25

DUAL_PROJECTION_INSUFFICIENT
    best-trace lift residual <=0.1，
    但Petrov-trace lift residual > max(0.5, 5*best residual)

TWO_LEVEL_COMPOSITION_INSUFFICIENT
    best与Petrov lift均能给出<=0.1，
    但当前V3-2 preconditioner仍在16步后>0.9
```

这些是机制定位标签，不是完整solver pass。

---

## 8. V4-2：条件dual或two-level composition狭窄修正

### 8.1 dual分支

只有 `DUAL_PROJECTION_INSUFFICIENT` 成立时，允许使用同一 `Z` 构造冻结的mass-dual：

```math
Y_{new}=M_\Gamma Z\left(Z^HM_\Gamma Z\right)^{-H}.
```

不得更换span或加入新方向。重新执行：

```text
trace projection
one-apply
FGMRES 4/8/16/条件32
```

### 8.2 composition分支

只有 `TWO_LEVEL_COMPOSITION_INSUFFICIENT` 成立时，允许一个固定对照：

```text
local pre-solve
-> recompute true residual
-> coupled interface correction
-> recompute true residual
-> one local post-solve
```

不增加overlap、不改变group factor、不增加sweep count。重新执行同一五源screen。

### 8.3 Gate

若dual或composition对照使五源首个checkpoint满足：

```text
all mandatory <=1e-2
modal+/modal-/external <=1e-3
```

则进入V4-5进行bounded-rank审计。

若仍不通过，继续V4-3；不得扫描更多dual、post-smooth或damping菜单。

---

## 9. V4-3：exact-response enrichment train/holdout pilot

### 9.1 目的

只回答：

> 当前span外的真实response方向加入后，是否能显著改善未参与训练的source？

这一步仍是oracle，不是production candidate。

### 9.2 冻结train/holdout

```text
training:
    modal_traction_positive
    external_dtn_coupling
    fixed_random_repeat_0

holdout:
    modal_traction_negative
    fixed_random_repeat_1
```

不得更换划分追逐结果。

### 9.3 enrichment方向

对training source构造：

```text
exact trace t*
current best-in-span trace tB
missing trace d = t* - tB
```

使用interface mass metric去除当前span、归一化，并用complex SVD/RRQR形成最多三个嵌套
response directions。禁止直接使用raw RHS/load vectors。

pilot候选固定为：

```text
R1
R2
R3
```

其中 `Rk = current776 + first k response directions`。该总rank超过512时仍只属于
mechanism oracle，不能称为0.7 nm scalable。

### 9.4 pilot Gate

每个候选运行：

```text
exact-trace representability
one-apply
FGMRES 4/8/16/条件32
```

定义：

```text
RESPONSE_ENRICHMENT_SIGNAL_PASS
    所有training r16 <=0.1
    且两个holdout r16均 <= 0.5 * 对应V3-2 r16

SOURCE_SPECIFIC_RESPONSE_OVERFIT
    training通过但任一holdout未达到二倍改善

RESPONSE_TRACE_ENRICHMENT_NO_SIGNAL
    training本身也没有显著改善
```

`RESPONSE_TRACE_ENRICHMENT_NO_SIGNAL`触发时停止；不得继续靠更多exact training columns扩大
固定案例oracle。

`PASS`或`OVERFIT`均允许进入V4-4，以在线Krylov数据构造可重建的广义response方向。

---

## 10. V4-4：bounded continuous FGMRES direction sampler

### 10.1 定位

本阶段不是solver qualification，而是：

```text
观察restart后的长期收敛行为
采集current PC最难消除的interface error directions
生成不依赖exact factor的online response data
```

### 10.2 冻结训练RHS

只运行：

```text
external_dtn_coupling
fixed_random_repeat_0
```

其他三个source只作后续holdout，不运行长迭代。

### 10.3 连续solve合同

每个RHS只启动一个连续FGMRES：

```text
right FGMRES
restart = 32
zero initial guess
checkpoints = 16 / 32 / 64 / 128
conditional checkpoint = 256
```

不得像旧phase一样每个checkpoint从零重启。

128步固定运行；256仅在同时满足下列条件时授权：

```text
all quantities finite
peak <45 GiB
swap=0
wall仍可保持总计<=6 h
r128 <=0.8
或64->128下降至少0.05 decade
```

本Review不授权512或1000步。

### 10.4 保存的数据

每个restart周期最多保存：

```text
true residual history
lower/upper interface residual trace
若exact authority兼容：exact error interface trace，仅作标签
最多8个slow/harmonic Ritz interface directions
Ritz value与residual estimate
```

所有大向量必须owner-row分布；不得保存每个rank完整basis，不得FE-sized numeric allgather。

总在线response方向硬上限：

```text
128-step stage <=256 directions
conditional256 stage <=512 directions
```

### 10.5 capacity分类

```text
LATE_KRYLOV_ACCELERATION_OBSERVED
    r128 <=0.5，或64->128下降>=0.25 decade

SLOW_BUT_INFORMATIVE
    r128 >0.5，但Ritz/trace方向稳定、重复source间存在共享子空间

PURE_STAGNATION
    r128 >0.8，64->128下降<0.05 decade，且没有稳定共享慢方向
```

`PURE_STAGNATION`并不否定response enrichment；若V4-3已有signal，可继续使用exact+early
Krylov方向。若V4-3也无signal，则停止当前coarse family。

---

## 11. V4-5：response-enriched bounded coarse audit

### 11.1 数据来源

候选可使用：

```text
现有lower Fourier/Floquet与upper QEP mode metadata
V4-4 online residual/harmonic Ritz interface directions
V4-3 exact directions仅作oracle排序与holdout验证
```

正式候选basis不得把exact output values作为运行时输入。

### 11.2 bounded rank

使用mass-weighted complex SVD、RRQR或等价稳定方法，形成**总rank**：

```text
64
128
256
512
```

不得解释为“在776上再加512”；rank是最终coarse总维数。不得按列号截断。

### 11.3 先做离线authority筛选

对四个rank先利用已有exact outputs计算：

```text
best trace representation error
Petrov trace error
lifted full bare-F residual
train/holdout误差
basis/subspace hash
```

只有满足下列条件的最小rank及其下一较大rank进入heavy FGMRES：

```text
modal+/modal-/external lifted residual <=0.1
five-source worst lifted residual       <=0.25
holdout finite                          =true
```

若rank512仍不满足，停止：

```text
BOUNDED_RESPONSE_COARSE_NOT_ESTABLISHED_BY_RANK512
```

### 11.4 heavy FGMRES资格

最多两个rank运行五源连续FGMRES：

```text
16 / 32 / 64 / 128
conditional 256
```

允许定义两个时间等级：

```text
preferred side capacity = 首次<=64步通过
research side capacity  = 首次<=256步通过
```

最终数值Gate仍为：

```text
all mandatory true residual <=1e-2
modal+/modal-/external       <=1e-3
```

若最小通过rank `<=512` 且迭代 `<=256`，分类：

```text
BOUNDED_RESPONSE_COARSE_ORACLE_PASS
```

这仍不等于production pass，因为当前还保留cross-section group factors。

---

## 12. V4-6：packet-independent / online production reconstruction

正式side-PC不得依赖exact-output spool或exact-interface packet作为运行时输入。

使用冻结：

```text
bare-F action
current lower/upper physical mode metadata
bounded local/group PC
V4-4 deterministic training RHS
在线FGMRES/Ritz提取算法
V4-5 selected rank与selection rule
```

在fresh进程中重新生成同一bounded coarse。exact authority只用于事后比较，不参与basis构造。

必须证明：

```text
selection rule identity/hash一致
oracle-vs-online subspace principal-angle sine max <=1e-6
coarse action relative error <=1e-6
五源FGMRES达到V4-5同一Gate
exact outputs loaded during construction =0
exact-interface packet required =false
full-side exact factor=0
```

若失败：

```text
EXACT_ORACLE_DEPENDENCE_NOT_REMOVED
```

停止，不进入Level B。

---

## 13. V4-7：bounded local patch Level B

只有V4-6通过后，才删除三个横跨完整x/y截面的group factors，改为：

```text
local FGMRES
+ bounded overlapping patch PC
+ V4-6 bounded response-enriched coarse
```

可扩展性硬合同：

```text
full-cross-section exact factor =0
full-side exact factor          =0
max_local_rows                  <=1024
factor class count              =bounded and reported
one factor owner                =deterministic
full basis per-rank replica     =false
FE-sized numeric allgather      =false
```

bottom bare-F Gate：

```text
all mandatory <=1e-2
modal+/modal-/external <=1e-3
construction peak <=35 GiB
strong target <=30 GiB
post-setup retained <=30 GiB
swap=0
```

允许的inner iteration容量仍为：

```text
preferred <=64
research <=256
```

超过256步不得称为production-capable side inverse。

---

## 14. V4-8：bottom full side、top、both与完整Hybrid

bottom bare-F通过后，按完全相同的算法参数执行：

```text
bottom full A_side，physical DtN保持不变
same-config top
both-side setup-only
唯一一次full Hybrid formal
```

不得对top单独调rank、restart、patch或iteration budget。

完整Hybrid继续要求：

```text
five explicit true residual <=5e-9
recovery pass
R/T/A/A_volume matched
selected E/H matched
canonical/normal flux/channels matched
bottom/top full-side exact factor =0/0
global direct factor=0
swap=0
```

完整峰值分级：

| 分类 | full workflow peak |
|---|---:|
| 未刷新当前 iterative | `>=80.025856018 GiB` |
| 新最低点 | `<80.025856018 GiB` |
| 至少节省20% vs direct | `<=74.701605225 GiB` |
| 至少节省30% vs direct | `<=65.363904572 GiB` |
| 至少节省40% vs direct | `<=56.026203919 GiB` |
| 至少节省50% vs direct | `<=46.688503266 GiB` |

---

## 15. V4-9：条件h3扩展性probe

只有完整h4 side candidate通过后才允许。保持所有PC参数和rank不变，仅运行5 nm p6/h3
bottom setup/apply与有限checkpoint，不运行top或完整Hybrid。

报告：

```text
side active rows
PC retained bytes
local factor bytes
coarse bytes
Krylov bytes
construction peak
max_local_rows
factor class count
```

目标：

```math
p_{mem}
=
\frac{\log(B_{PC,h3}/B_{PC,h4})}
     {\log(N_{h3}/N_{h4})}
\le1.30.
```

同时：

```text
max_local_rows unchanged
coarse rank unchanged <=512
full-cross-section/full-side factor =0/0
swap=0
```

这是0.7 nm-oriented扩展性证据，不是0.7 nm PDE资格。

---

## 16. 资源、时间与停止条件

### 16.1 通用资源线

```text
one heavy process at a time
swap =0
component hard line <45 GiB
formal default time gate =6 h
```

只有已经进入授权的连续FGMRES、residual持续下降、RSS低于45 GiB且无swap时，才允许一次
延长到总计8小时；不得因停滞而延长。

### 16.2 真正停止Gate

以下情况停止等待审阅：

```text
exact authority与current bare F不兼容
exact-trace lift identity无法建立
V4-3 response enrichment无training signal
V4-4与V4-3均显示pure stagnation/no shared response subspace
rank512仍无法建立bounded response coarse
online reconstruction不能移除exact authority依赖
bounded patch违反max_local_rows或资源合同
bottom通过后，同配置top真实数值失败
完整Hybrid residual/physics/resource失败
h3增长指数或固定rank合同失败
```

Implementation bug按第4节自行修复后继续。

---

## 17. 证据与交付要求

至少创建或更新：

```text
outcomes/exact_trace_representability.md
outcomes/group_lift_identity.md
outcomes/long_krylov_direction_sampling.md
outcomes/response_enriched_coarse.md
outcomes/production_side_inverse.md
outcomes/bounded_patch_pc.md
outcomes/bottom_bare_f_pc.md
outcomes/bottom_full_side.md
outcomes/top_full_side.md
outcomes/both_side_setup.md
outcomes/full_hybrid_result.md
outcomes/h_refinement_scaling.md
outcomes/memory_residual_time_pareto.md
outcomes/0p7nm_side_pc_capacity.md
outcomes/test_summary.md
outcomes/summary.md
response_v5.md
```

每个formal/controlled-negative必须提交独立compact record，绑定：

```text
source SHA
input/physical/selected/probe/spool hashes
exact-output identities when used
basis/rank/selection hashes
true residual checkpoints
resource timeline/hash
factor lifecycle
train/holdout身份
not_run_by_gate列表
```

完整raw继续保留在ignored `results/`，不得提交大型向量、矩阵、factor或field。

---

## 18. 本轮最终判断

```text
V3-2 evidence                         = PASS_WITH_NUMERICAL_NEGATIVE
current full776 reduced algebra       = PASS_COMPONENT
current full776 side inverse          = FAIL
hundreds_of_iterations_possible       = true in principle
hundreds_of_iterations_as_production  = not acceptable without strong multi-RHS strategy
current primary diagnostic            = exact trace representability and lift identity
next coarse family                    = response/harmonic-Ritz enriched, bounded rank
final local solver target             = bounded patch + local iterative solve
0.7 nm-oriented contract              = unchanged
merge approval                        = NO
```

核心判断：

> 下一步不是继续证明`776 x 776`小系统能否解准，也不是把现有弱PC直接跑到数千步；而是用
> exact-side authority把“接口basis不足、dual不足、三维lift不足”彻底分开。若缺的是basis，
> 就用在线慢残差和harmonic Ritz构造可在fresh进程中重建的response-enriched bounded coarse；
> 该全局困难方向修正通过后，才把三个局部大factor换成真正可扩展的bounded local solver。
