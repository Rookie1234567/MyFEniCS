# Task038-extra Review Report V15：checkpoint 驱动的 bounded Floquet 波模残差诊断

## 0. 审阅身份与决定

```text
review                                  = Task038-extra Review Report V15
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 36bae0daf1e7dabbc4a113c7ca6dcff58b428f14
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v14.md
selected_hierarchy                      = same_mesh_hcurl_pmg_v1_requalified
V14_J5_status                           = CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED
V14_J6_status                           = not_run_by_J5_eligibility
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
ordinary_default_change                 = forbidden
full_0p7nm_PDE                          = forbidden
production_correction_in_this_round     = forbidden
new_long_Krylov_in_this_round           = forbidden
continuous_authorized_batch             = F0 through F4 below, subject to hard Gates
response_required                       = response_v15.md
```

V14 已证明真实 p6/h10 Maxwell 的冷启动和至少到 checkpoint-1000 的运行在停止前保持低于 2 GB；但 500 到 1000 步的显式真残差只从 `0.48387099430079733` 降到 `0.4837947981092168`。继续用同一预条件器累加数千或数万步没有工程价值。

本轮只回答一个更便宜、可证伪的问题：停滞残差是否主要由少量、事先由物理定义的 Floquet 全局波模造成。通俗地说，我们不再让求解器盲目迭代，而是先检查“卡住的误差”是否大部分落在 32 个明确的出射/掠传播方向中。若答案是否定的，立即关闭 bounded Floquet correction；若答案是肯定的，也只获得进入下一轮短 screen 的资格，不把诊断写成求解通过。

---

## 1. 必须永久保留的历史边界

| 对象 | 冻结状态 | V15 边界 |
|---|---|---|
| V13 C1 四类 positive | `PASS` | 只证明正定辅助问题，不是 physical Maxwell PASS |
| V13 P0 | `FAILED_RESOURCE_HARD_STOP` at `2,024,108,032 B` | 不覆盖、不重分类 |
| V14 J5 v3 | `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED` | checkpoint-500/1000 与全部 raw evidence 原样保留 |
| V14 J6 | `not_run_by_J5_eligibility` | V15 是新诊断，不是补写 J6 PASS |
| J7/J8/official physics | `not_run` | 本轮仍锁定 |
| V11/V12 及更早 negative | frozen | 不重开 Route A/B/C、HX、普通 GenEO/BDDC 或旧 spectral family |

任何新 PASS 必须属于新 source SHA、新 schema 和新 artifact root。不得覆盖旧 checkpoint、raw timeline、marker、compact 或 response。

---

## 2. 固定物理模式选择，不允许看残差后挑方向

### 2.1 当前 authority

当前 ordered mode manifest 固定为：

```text
mode count                 = 80
propagating                = 78
near-cutoff                = 0
evanescent                 = 2
mode manifest SHA256       = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
rayleigh tolerance         = 1e-6
```

模式身份、顺序、极化、归一化和分类继续由 `src/solvers/fullspace_dtn_action.py` 与当前 physical config 产生。不得修改 `diffraction_rayleigh_tol`，也不得增加新的 near-cutoff window。

### 2.2 唯一 selector

先过滤 `classification in {near-cutoff, propagating}`，再按下式从小到大排序：

```math
\eta_i = \frac{|\beta_i|}{|n_i|k_0}.
```

这里的 `n_i` 明确指该物理 mode 在 ordered manifest 中的复数
`refractive_index`，不是整数衍射级字段 `n`；`k_0=2\pi/13.5\ \mathrm{nm}`。

完全相同的 `eta` 只按原 ordered manifest 的 `mode_index` 破同值。固定选择前 32 个；不得扫描 rank、window、side、polarization、weight 或 source。

该规则在当前 authority 上必须得到：

```text
selected rank              = 32
selected classification    = 32 propagating / 0 near-cutoff
selected side              = 16 top / 16 bottom
selected polarization      = 16 s / 16 p
selected mode indices      =
  38,39,72,73,76,77,32,33,36,37,40,41,0,1,42,43,
  46,47,2,3,6,7,74,75,34,35,66,67,70,71,26,27
```

selector identity 使用 canonical JSON schema `task038.v15.floquet-selection.v1`；固定 payload SHA256 为：

```text
7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3
```

上述 SHA 对应的唯一 payload 为：

```json
{"eligible_classifications":["near-cutoff","propagating"],"policy":"eligible_class_filter__normalized_abs_beta_ascending__mode_index_tiebreak","rank":32,"schema":"task038.v15.floquet-selection.v1","selected_mode_indices":[38,39,72,73,76,77,32,33,36,37,40,41,0,1,42,43,46,47,2,3,6,7,74,75,34,35,66,67,70,71,26,27],"source_mode_manifest_sha256":"dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"}
```

序列化规则固定为 `sort_keys=True`、`separators=(",", ":")`、
`ensure_ascii=True`，随后以 ASCII bytes 计算 SHA256。

若当前 manifest 不能精确产生上述结果，F0 失败并停止。不得用 hard-coded mode rows 绕过动态 inventory；测试和 checker 可以把上述值作为 formal authority。

---

## 3. 固定诊断子空间

对每个被选模式 `i`：

1. 用现有 owner-local DtN carrier 的 `apply_modal_rhs(e_i)` 构造物理 modal dual `f_i`；
2. 只作确定性单位二范数归一化；这不改变 span，也不是可调 mode weighting；
3. 用现有、完全冻结的 `same_mesh_hcurl_pmg_v1_requalified` 单次 apply 得到高空间 primal `z_i=M_B^{-1}f_i`；
4. 用当前 exact split-volume 加 streaming DtN 的 matrix-free action 得到 `y_i=A z_i`；
5. 对 `y_i` 按固定顺序执行两遍 modified Gram-Schmidt，形成 `Q` 和小型上三角 `R`。

本轮 basis 不允许：

```text
从 checkpoint residual 拟合或排序
使用 Krylov/Ritz/harmonic Ritz 向量
增加 PC apply 次数来改善单列
替换、平滑或丢弃失败列后补其他模式
形成 high-order global AIJ、global dense transfer 或 FE-sized numeric allgather
保存每个模式的 factor 或局部 Krylov history
```

F3 formal 中只保留 `Q`；每列的 `f_i/z_i/y_i` 在完成正交化后销毁。诊断不保留 `Z/AZ` 双包，也不接入 production PC。

---

## 4. checkpoint-1000 的精确重建合同

唯一输入是 V14 J5 v3：

```text
checkpoint manifest SHA256 = 7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139
solution shard SHA256       = 00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b
iteration                   = 1000
stored true residual        = 0.4837947981092168
rows                        = 173802
MPI                         = 1
dtype                       = complex128
```

新 worker 必须在新 source SHA 下重新建立同一 exact bundle 和 RHS，然后使用现有 fail-closed checkpoint reader 恢复 solution。必须同时精确闭合：

```text
input identity SHA256       = 754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f
operator identity SHA256    = bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3
physical model SHA256       = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
mode manifest SHA256        = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
checkpoint source SHA       = ee5920b9fa977a39fea7bc09cfbe155303acdb2d
```

重新计算：

```math
r = b-Ax_{1000}.
```

要求重新计算的 `norm(r)/norm(b)` 与 `0.4837947981092168` 的 relative difference `<=1e-11`，且 `A` apply 前后 `x` unchanged、`b` unchanged、所有数组 finite、owned slave condition通过。任何一项失败均为 identity/algebra hard stop，不得进入模式投影。

---

## 5. 执行顺序 F0→F4

### F0：docs/read-only preflight

必须确认：

```text
branch/HEAD/upstream exact and clean
V14 old root/checkpoint readable and hashes exact
80-mode authority and 32-mode selector exact
exact action/PC implementation path未被本轮诊断代码改写
central live-set prediction < 1.8 GB
hard upper prediction < 1.95 GB
没有 major unknown
```

F0 只允许读取和计算 compact metadata。若容量或身份不能闭合，不写 solver。

### F1：最小实现与 focused oracle

允许的最小文件范围：

```text
one generic research helper in src/solvers for selector + fixed QR/projection
one thin Task038 diagnostic worker/runner
one read-only independent checker
focused tests, starting at the next unused test number
minimal extension of the existing cold-staged parent only if needed to launch this worker
```

不得扩展 existing physical worker 为第二套 solver framework，不得建立 registry/dataclass hierarchy/fallback tree。checker不得导入 runner、solver、PETSc、MPI 或 DOLFINx。

F1 先在 small fixture 上验证：

| oracle | Gate |
|---|---:|
| selector identity | exact 32 indices and selector SHA |
| modal dual canonical identity MPI1/MPI2 | relative `<=1e-12` |
| PC-output canonical identity MPI1/MPI2 | relative `<=1e-10` |
| transfer `P/P^H` adjoint work | relative `<=1e-11` |
| linearity / repeat / input unchanged | relative `<=1e-12` |
| finite / high-space primal / owned slaves | pass |
| QR orthogonality and reconstruction on synthetic oracle | `<=1e-12` |

只运行 small oracle；不得加载 p6 checkpoint 或启动长 Krylov。明确、唯一的代码 bug 可窄修并重跑 focused tests；禁止参数扫描。

### F2：fresh cold-staged p6 checkpoint residual

F1 全部通过后，在新 source SHA 和全新空 artifact root 中启动一次 MPI1 formal parent：

```text
same seven sequential precompile groups as V14
all compiler descendants gone before solver child
solver cache hashes unchanged
build exact p6/h10 physical bundle and RHS
restore checkpoint-1000
one exact action for r=b-Ax
no KSP and no recovery
```

只有 §4 全部身份和残差 Gate 通过，才在同一个 live bundle 中继续 F3；避免为了诊断重复一次昂贵 setup。

### F3：唯一 rank-32 span diagnostic

F2 通过后在同一 formal parent 内完成 32 列构造和投影。除 residual 重建的一次 action 外，basis 阶段应恰好执行 32 次现有 PC apply 与 32 次 exact action；不得启动 KSP。

计算：

```math
c = Q^H r,
\qquad
r_\perp = r-Qc,
\qquad
\rho_{\mathrm{wave}} = \frac{\lVert r_\perp\rVert_2}{\lVert r\rVert_2},
\qquad
E_{\mathrm{captured}} = 1-\rho_{\mathrm{wave}}^2.
```

正式 Gate：

| Gate | 要求 |
|---|---:|
| accepted numerical rank | exactly `32` |
| `sigma_min(R)/sigma_max(R)` | `>=1e-10` |
| `norm(Q^H Q-I)_2` | `<=1e-10` |
| QR reconstruction relative | `<=1e-10` |
| projection repeat difference | `<=1e-12` |
| captured residual energy | `>=0.90` |
| equivalent `rho_wave` | `<=sqrt(0.10)=0.31622776601683794` |
| ideal projected true residual relative to `b` | `<=0.153` |
| finite/input unchanged/high-space primal/slaves | pass |
| complete process-tree peak | `<2,000,000,000 B` |
| process-tree/rank swap | `0 B` |

`captured residual energy >=0.90` 的含义是：固定 32 维波模 span 至少解释停滞误差二范数能量的 90%。这是进入下一轮短 corrected screen 的最低依据；本轮不据此运行 correction。

若 `rho_wave` 超线、rank/conditioning失败或 ideal projected residual高于 Gate，分类为 `FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE`，不得更换 32 个模式、扩大 rank 或再跑长求解。

### F4：独立 checker、文档、提交与停止

checker 必须从 raw facts 重算 selector、checkpoint identity、residual reproduction、QR/span Gate、计数和资源结论。完成后更新：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/floquet_wave_residual_diagnostic_v15.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/floquet_wave_small_oracle_v15.json
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/floquet_wave_checkpoint1000_v15.json
docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/development_progress.md
docs/task038_extra_full3d_iterative_0p7nm/response_v15.md
```

提交并只推送当前 extra 分支，然后停止等待审阅。

---

## 6. 资源预审与 formal watchdog

p6 owned vector payload 为：

```text
173802 rows * 16 B = 2,780,832 B
Q32 payload        = 88,986,624 B
```

F3 不保留 `Z/AZ` 双包。`Q32` 加六个同时工作向量的纯数值增量为：

```text
88,986,624 + 6 * 2,780,832 = 105,671,616 B
```

以上一轮停止前完整 staged peak `1,450,262,528 B` 作保守基线，当前 preflight 冻结为：

| 口径 | 预测 |
|---|---:|
| central complete live set | `<=1,650,000,000 B` |
| hard upper before formal | `<1,800,000,000 B` |
| runtime warning | `1,800,000,000 B` |
| watchdog controlled stop | `1,950,000,000 B` |
| formal success hard Gate | `<2,000,000,000 B` and swap `0 B` |

预测不是 measured PASS。formal 必须由统一 parent watchdog 覆盖 cold precompile、solver setup、checkpoint restore、32 列和 teardown。达到 `1,950,000,000 B` 时受控终止并保存 evidence，不允许等到 OOM。

---

## 7. formal 次数与 bug 修复边界

1. F1 focused tests 可以针对明确代码 bug 窄修；不得改变 selector、rank、Gate、PC 或物理。
2. F2/F3 只允许一次正式数值 attempt。
3. 若首次 formal 在读取 checkpoint 之前因唯一可定位的 path/marker/cache/provenance bug失败，可修复后做一次 execution retry；旧失败必须完整保留。
4. identity、rank、conditioning、span、2 GB、swap 或 nonfinite 失败是真实 Gate，不允许重跑改变分类。
5. weekly quota 为 0 时立即暂停，不使用点数。

---

## 8. 本轮禁止项

```text
继续或重启 V14 J5
任何 20/100/200/20000 步 corrected screen
把 ideal least-squares residual称为实际 solver residual
把 diagnostic PASS称为 physical PDE PASS
production deflation/correction
official E/H、R/T/A、A_volume、12+12 channels
physical MPI2、p6/h5 或完整0.7 nm PDE
新 smoother、coarse space、GenEO、BDDC/FETI-DP、HX 或 transmission family
restart/omega/shift/GAMG/Chebyshev/mode/rank/window扫描
global high-order AIJ、global Schur、global direct factor、numeric allgather
ordinary default或master修改
```

---

## 9. F3 后的唯一决策

| F3 结果 | 决策 |
|---|---|
| 全部 identity/resource/algebra Gate通过且 captured energy `>=0.90` | 只获得下一 Review 中一次 fixed rank-32 correction 的 20/100/200-step short screen资格；不得直接长跑 |
| span Gate失败 | 正式关闭 bounded Floquet correction；不扩大 rank或换 selector |
| algebra/identity失败 | 只在可证明是唯一代码 bug时按 §7 处理，否则关闭该实现路径 |
| resource失败 | 关闭显式 Q32 retained 设计；不得提高2 GB线 |

若 span Gate失败，F4 额外创建 `outcomes/next_wave_aware_dd_after_v15.md`，只比较真正独立的 wave-aware domain-decomposition 路线：局部 matrix-free Maxwell 子域逆、物理传播粗空间和固定内存 coarse distribution。不得在本轮自动实现，也不得把普通正定 GenEO/BDDC/HX 重新命名后重开。
