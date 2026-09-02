# Task040 Review Report V10：停止 standalone LOR，验证 physical p-coarse 后转 wave-aware DD

## 0. 审阅身份与总裁决

```text
review                                  = Task040 Review Report V10
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260822-task40-hybrid-side-factor-pc
reviewed_HEAD                           = 1e48d6935bc842f646e9dec07c8bf7ca8d82f622
reviewed_review                         = docs/task040_hybrid_side_factor_pc/review_report_v9.md
reviewed_response                       = docs/task040_hybrid_side_factor_pc/response_v10.md
reviewed_task038_reference              = docs/task040_hybrid_side_factor_pc/outcomes/task038_extra_reference_boundary.md
task038_reference_branch                = codex/20260820-task38-extra-full3d-iterative-0p7nm
task038_reference_HEAD                  = 40dc1faeebfaa48c66b6e50c9406f148c4b720e1
working_branch_continues                = yes
master_write_or_merge                   = forbidden
Task038-extra_write_or_merge            = forbidden
ordinary_default_change                 = forbidden
standalone_LOR_status                   = CLOSED_NO_FURTHER_PARAMETER_WORK
positive_operator_requalification       = forbidden
next_physical_candidate                 = same_mesh_physical_pcoarse_for_condensed_side
fallback_after_span_fail                = wave_aware_physical_domain_decomposition
full_0p7nm_PDE                          = forbidden
response_required                       = response_v11.md
Task041_heavy_campaign_priority          = higher than Task040 heavy execution
concurrent_heavy_runs                   = forbidden
```

本 Review 的核心裁决是：

> Task040 不再试图把 positive/LOR hierarchy 调成完整 physical Maxwell inverse。已有证据已经充分证明其对 positive operator 有效、对真实 physical Maxwell 形成平台。下一步只允许把它作为 local/pre-post smoother，验证一个包含真实负质量、复材料及物理边界作用的 same-mesh physical p-coarse；若准确 physical p-coarse 本身没有 span signal，立即切换 wave-aware physical DD，不再优化 LOR。

Task041 的 MPI1 短波长容量 campaign 由用户本轮单独授权，优先占用工作站 heavy-run 时间。Task040 可先完成轻量实现、tiny identity 和输入准备，但不得与 Task041 同时运行 heavy PDE、QEP 或 factorization。

---

## 1. 继承事实与不得重跑的工作

### 1.1 Positive hierarchy 已被充分证明

Task038-extra V13 在 p6/h10、13.5 nm、MPI1 的 positive operator 上，random、gradient、curl、checkerboard 四源均在约 180–220 步达到约 `1e-8` 或更小 true residual。Task040 自己的 fixed-LOR h10 component screen 也取得 positive action pass。

这些结果已经足以支持以下工程判断：

```text
same-mesh p-transfer                         = usable component
positive p-MG / LOR local hierarchy          = usable component
bounded positive local inverse               = usable component
fixed-restart lifecycle                      = usable component
```

因此禁止再次运行：

```text
positive random / gradient / curl / checkerboard qualification
h10 positive replay
更多 positive-only mesh points
普通 shift / smoother / Chebyshev-degree scan
仅为得到更小 positive residual 的长 Krylov
```

### 1.2 Standalone physical LOR 已无继续信号

必须同时保留：

```text
Task038-extra physical Maxwell:
    checkpoint-500  = 0.48387099430079733
    checkpoint-1000 = 0.4837947981092168

Task040 physical bare-F external fixed-LOR:
    iteration-256 = 0.7349227023138162
```

两者物理与离散不同，不能直接比较绝对数值；但它们一致证明 positive/LOR inverse 能消除部分局部误差，却无法单独处理完整 physical Maxwell 的全局传播、负质量、复杂材料相位和近共振误差。

正式关闭：

```text
standalone_fixed_LOR_side_inverse
LOR_iteration_escalation
LOR_shift_scan
LOR_smoother_scan
```

保留但降级为组件：

```text
LOR / positive p-MG as local smoother
LOR / positive p-MG as inner PC for a physical coarse equation
```

### 1.3 小型预选 wave space 也不能冒充 physical coarse

必须保留以下负结果：

```text
Task038-extra rank32 Floquet captured energy = 0.002179823642496248
Task038-extra rank32 post-projection rho      = 0.9989094935766222
Task040 current two-plane full-spectrum       = numerical no-signal
Task040 630×160 unselected coarse             = rho 6.778773552009804
```

这些结果关闭的是固定小型预选外部波空间和未选择的大型候选集合，不是所有 physical multilevel 或 wave-aware DD。

---

## 2. 第一项必要修复：surface quadrature 语义

Task038-extra 最新修复将 surface quadrature degree 绑定到每个 UFL integral metadata，而不是依赖全局 `form_compiler_options`。Task040 当前 `dtn_port_3d.py` 的 surface source、reusable surface component、mode projection 和 surface scalar 路径仍需选择性同步该通用修复。

### 2.1 允许修改

只允许在通用 surface-form helper 中重写：

```text
quadrature_degree
→ integral.metadata()["quadrature_degree"]
```

必须保留原 integral 的其他 metadata，不改变 integrand、facet tag、材料、phase、sign 或 mode identity。

### 2.2 Source-only 对照

在任何新的 Task040 physical external run 前，必须比较修复前后同一 `external_dtn_coupling` 的：

```text
canonical physical key set
canonical value digest
source norm
relative vector difference
orientation/sign
Floquet phase exactly once
surface quadrature degree
```

决策：

```text
relative source difference <= 1e-12
    -> 旧 external numerical evidence继续有效，不重跑旧 LOR campaign

relative source difference > 1e-12
    -> 只允许重跑一次受影响的同一 physical external screen
    -> 不重跑 positive probes，不扫描 LOR 参数
```

---

## 3. 新主候选：condensed same-mesh physical p-coarse

### 3.1 它解决什么问题

当前 positive fine-level local action概念上类似：

```math
B_6 = K_{\mathrm{curl},6} + k_0^2 M_{|\epsilon|,6}.
```

真实 side bare operator为：

```math
F_6 = K_{\mathrm{curl},6} - k_0^2 M_{\epsilon,6}.
```

完整 physical side阶段再加入不改变的 external DtN/Woodbury action。

新候选不再要求 `B_6^{-1}` 近似整个 `F_6^{-1}`，而是在 same mesh p3 空间建立真实 coarse operator：

```math
F_3 = K_{\mathrm{curl},3} - k_0^2 M_{\epsilon,3}.
```

对完整 side阶段，相应 coarse action必须包含与 fine side同一物理定义的 DtN coupling，不能用 positive mass替代。

### 3.2 固定组合

设 condensed active-trace spaces为 `V_6^Γ` 与 `V_3^Γ`，建立：

```math
P_{63}^{\Gamma}:V_3^\Gamma\rightarrow V_6^\Gamma,
\qquad
R_{63}^{\Gamma}=(P_{63}^{\Gamma})^H.
```

一次候选 PC apply固定为：

```math
z_0 = S_6 r,
```

```math
r_1 = r - F_6 z_0,
```

```math
r_3 = (P_{63}^{\Gamma})^H r_1,
```

```math
F_3 e_3 \approx r_3,
```

```math
z_1 = z_0 + P_{63}^{\Gamma} e_3,
```

```math
M_{\mathrm{phys-p}}^{-1}r
=
z_1 + S_6(r-F_6z_1).
```

其中 `S_6` 只使用已资格化的 positive/LOR local smoother；outer 必须使用 right FGMRES。

---

## 4. 执行漏斗

### P0：轻量继承审计

必须绑定：

```text
Task040 input/physical/source SHA
Task038-extra V13–V16 read-only reference SHA
surface quadrature helper semantics
Task040 static-condensed p6 active layout
candidate p3 space definition
```

不得导入 Task038-extra benchmark runner、raw result或 checkpoint。

### P1：p6/p3 condensed transfer identity

先在 tiny/reduced case验证：

```text
canonical entity identity
orientation consistency
Floquet phase exactly once
slave-zero
P/P^H adjoint work
linearity and repeat
MPI1/MPI2 owner consistency
```

禁止 global dense transfer和 FE-sized numeric allgather。

### P2：physical p3 action identity

必须验证：

```math
F_3 v \approx (P_{63}^{\Gamma})^H F_6 P_{63}^{\Gamma}v.
```

记录 absolute 与 relative error、source/output norm和 owner-local work。若 rediscretized `F_3` 与 Galerkin action在固定 Gate下不一致，不得静默替换定义；必须分别标记并选择数学上闭合的一种。

### P3：accurate physical p3 coarse-span oracle

固定代表源：

```text
external_dtn_coupling
fixed_random_repeat_0
```

先在最小合法 physical case使用足够准确的 p3 solve，只比较：

```text
zero correction
positive/LOR local-only
accurate physical-p3 coarse correction
local-pre -> physical-p3 -> local-post
```

development oracle可以暂时使用小型 p3 exact factor或高精度 p3 iterative solve，但必须：

```text
oracle-only
factor destroyed after use
not production
not 0.7 nm scalable claim
```

建议继续条件为两源同时满足至少一项：

```text
composite one-cycle true residual <= 0.5

or

relative to local-only residual, improvement >= 4x
```

若任一代表源无 signal，分类：

```text
PHYSICAL_PCOARSE_SPAN_NO_SIGNAL
```

立即关闭 physical p-coarse，不得通过增加 inner iterations、继续调 LOR 或改变 source 来挽救。

### P4：bounded physical p3 inner solve

只有 P3有信号才实现：

```text
p3 physical FGMRES
+
existing positive p3->p1 hierarchy as inner PC
```

固定小 restart；先测 external/random0 的 one-apply 与 8/16/32/64 checkpoints。有一致 positive后才扩展到五源和 h5/h4。

---

## 5. Physical p-coarse失败后的唯一新 PC

若 P3 span失败，下一候选为：

```text
wave-aware physical domain decomposition
```

其最低结构要求：

```text
bounded 3D physical Maxwell subdomains
local complex Maxwell action
optimized impedance or local-PML transmission
physical canonical interface variables
distributed matrix-free interface/coarse action
no full-side factor
no full-cross-section factor
no fixed global rank assumption
bounded local rows
```

LOR仍可作为 subdomain inner smoother，但不得成为全局 inverse。该路线必须先做 local/interface identity与 one-cycle signal，不直接启动大型 h4 formal。

---

## 6. 与 Task041 的资源调度

Task041 将运行 MPI1 exact-side Hybrid 5/3/2 nm容量 campaign。为避免 2 TiB 工作站上的资源与证据污染：

```text
Task041 heavy run active
    -> Task040只允许docs、source-only、tiny serial/MPI2工作

Task041 heavy run complete or controlled stop
    -> Task040才可进入P3及之后的physical heavy run
```

禁止两个 branch 同时运行 QEP、MUMPS factor、large FGMRES或 recovery。

---

## 7. 测试政策

只运行直接风险测试：

```text
surface metadata helper
surface source before/after canonical comparison
p6/p3 canonical transfer serial + MPI2
P/P^H work
physical p3 action identity
factor lifecycle if oracle used
touched Ruff/compileall
```

禁止：

```text
重复positive campaign
full repository pytest during research loop
无关MPI4
Task038-extra heavy replay
旧full-spectrum/LOR campaign replay
```

---

## 8. 停止与继续边界

```text
surface source unchanged
    -> 不重跑旧external LOR

surface source changed
    -> 唯一一次受影响external requalification

physical p3 accurate span positive
    -> bounded p3 inner -> two source -> five source -> h5/h4

physical p3 accurate span no-signal
    -> wave-aware physical DD

Task041 heavy active
    -> Task040 heavy paused
```

只有 physical p-coarse或wave-aware DD形成五源、factor-free positive后，才允许进入 bottom full side、top、both-side、full Hybrid、h3和0.7 nm容量判断。

---

## 9. Response 要求

Codex 完成授权阶段后提交：

```text
docs/task040_hybrid_side_factor_pc/response_v11.md
docs/task040_hybrid_side_factor_pc/outcomes/surface_quadrature_source_audit.md
docs/task040_hybrid_side_factor_pc/outcomes/physical_pcoarse_identity.md
docs/task040_hybrid_side_factor_pc/outcomes/physical_pcoarse_span_oracle.md
docs/task040_hybrid_side_factor_pc/outcomes/route_signal_ledger.md
docs/task040_hybrid_side_factor_pc/outcomes/summary.md
```

必须区分 `measured`、`derived`、`predicted`、`not_run`、`failed` 和 `controlled_stop`。本 Review 不批准 merge。
