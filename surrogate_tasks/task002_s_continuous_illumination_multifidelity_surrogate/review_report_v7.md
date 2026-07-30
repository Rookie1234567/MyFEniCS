# Task002 Review Report V7

## 1. 审阅结论

```text
review_status = route_A_Ny4_approved_after_tangential_projection_correction
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M4D_Case118_evidence = approved_and_retain
Ny3_root_cause = confirmed_discrete_Bragg_trace_alias
Ny3_production_route = rejected_and_hard_quarantined
Ny4_production_candidate = approved
reported_outgoing_P_discrepancy = diagnostic_projection_contract_error
production_auxiliary_modal_amplitudes = not_invalidated_by_Case118
Case117_Ny3_campaign = closed_controlled_stop_do_not_resume
new_Ny4_campaign = conditionally_authorized_after_M4E_preflight
M4_bulk = conditionally_authorized_after_enhanced_canary
M5_dataset_transfer = not_authorized_until_Ny4_dataset_complete
M6_surrogate_training = not_authorized
angle_DOE = not_authorized
production_inversion = not_authorized
required_next_action = M4E_Ny4_production_rebaseline_and_full_data_generation
```

Case118 已充分完成 Review V6 的核心诊断目标：`Ny=3` 时，实际有限元端口 trace space 中 `n=0` 与 `n=-3` 出现显著非正交；在 `2ky≈3Gy` 的窄角度区间，该非正交被放大为可见的非物理 y-harmonic 泄漏。将 y 向单元数从 3 增加到 4 后，泄漏、trace overlap 和 demodulated-field `n=-3` Fourier fraction 均降到舍入误差，且 n=0 的 R/T/A 沿 Ny=4/5/6 稳定收敛。

因此批准 Route A：

```text
Full3D static uniform N1curl p5/h10
Nx = 6
Ny = 4
Nz = 14
MPI2 / thread1
assembly-time static condensation
S incident, wavelength 13.5 nm
```

但不得恢复原 Case117。Case117 是 `Ny=3` 的不可变 controlled-stop evidence；新的正式数据必须使用新的 model/route/schema identity、clean implementation SHA 和独立 campaign（建议 Case119）。Ny=3 已通过的 56 个样本只能保留为诊断数据，不能与 Ny=4 数据混合。

Case118 报告中的 outgoing-P auxiliary/direct discrepancy 不构成阻塞 Ny=4 物理解的证据。静态代码审阅确认，当前独立诊断函数 `_mode_projection_from_solution(...)` 将完整三分量 `E_total` 与完整 P 模式向量做内积，却使用仅由切向分量定义的 denominator。DtN 边界 trace、辅助方程和 denominator 的合同均是切向电场合同。S 模式的 `e_z=0`，因此错误被掩盖；P 模式的 `e_z≠0`，于是错误地把法向场加入分子并产生 `O(10^-3)` 差异。该诊断公式必须改为纯切向投影并重新验证，不能据此否定官方 auxiliary amplitudes。

完成第 6 节的 M4E 实现和 enhanced canary 后，若全部 Gate 通过，Codex 可以在同一轮任务中从头完成 Ny=4 的 96 个 training 和 16 个 frozen-validation 求解，无需在 canary 后再次等待 Review。

---

## 2. 已接受的 Case118 证据

### 2.1 窄角度峰与几何独立性

失败几何与中心几何的 50--58° 扫描给出了几乎相同的峰位和峰高：

```text
azimuth 54.25°:
    n!=0 power ≈ 1.10e-6
    max amplitude ≈ 1.24e-3

azimuth 54.50°:
    n!=0 power ≈ 8.9e-7
    max amplitude ≈ 8.27e-4
```

原 Case117 精确失败角 `54.420819°` 位于该窄峰中。该结果证明问题主要由角度与离散 trace 结构决定，而不是某个特殊 h/w 几何导致。

### 2.2 Ny 收敛

接受以下结果：

| Ny | n!=0 total power | max amp | R | T | A | bottom-S n0/n-3 overlap | Gram cond |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1.2312e-6 | 1.0147e-3 | 0.00650900 | 0.29609606 | 0.69739494 | 3.6302e-1 | 2.1398 |
| 4 | 3.2783e-25 | 2.3532e-13 | 0.00644595 | 0.29623235 | 0.69732170 | 2.6829e-16 | 1.0000 |
| 5 | 1.1317e-24 | 1.6618e-13 | 0.00644227 | 0.29624034 | 0.69731739 | 1.4648e-16 | 1.0000 |
| 6 | 5.8333e-25 | 1.8991e-13 | 0.00644188 | 0.29624118 | 0.69731693 | 1.1292e-16 | 1.0000 |

Ny=4 相对 Ny=6：

```text
|ΔR| = 4.07e-6
|ΔT| = 8.83e-6
```

Ny=5 相对 Ny=6 进一步收敛。Ny=4 的误差远小于 Task002 以后针对 R/T 和主要衍射通道的代理验证尺度，同时资源显著低于 Ny=5/6，因此 Ny=4 是合理生产候选。

Ny=4 实测 PSS 约 5.82 GB、zero swap；Ny=5/6 也能运行，但不应为了已经达到的 y-invariance 再增加生产成本。

### 2.3 Demodulated field

接受：

```text
bottom-port n=-3 Fourier energy fraction
Ny=3: 3.10e-6
Ny=4: 4.88e-26
```

这证明泄漏不仅存在于 auxiliary JSON 后处理，而存在于 Ny=3 的离散 FE/port trace 解；Ny=4 后物理解恢复到单一 y Bloch harmonic。

### 2.4 Surface quadrature

接受 q=21/31/39/47 完全相同的泄漏：

```text
1.2312320314e-6
```

因此排除 surface Fourier quadrature 欠积分为首要根因。正式 Ny=4 可以继续沿用现有 deterministic q policy，但必须保留 q identity。

### 2.5 Trace Gram

接受 actual trace-space 的直接证据：

```text
Ny=3 bottom-S normalized overlap = 0.3630216842
Ny=4 bottom-S normalized overlap = 2.6828958e-16
```

这比只比较最终 R/T/A 更直接，足以将根因定为 Ny=3 的端口 trace alias，而不是随机求解波动。

### 2.6 执行和测试

接受：

```text
35/35 new PDE completed
all zero swap
all cleanup complete
Case118 independent checker = 13/13 pass
Task000/001/002 + repository regression = 81 passed
M4D + Task002 focused tests = 41 passed
Case117 stopped-state checker = 8/8 pass
compileall = pass
git diff --check = pass
```

---

## 3. 根因定案

生产域满足：

```text
period_y = 25 nm
grating_width_y = period_y
material and geometry invariant in y
```

连续问题中，已知 Bloch `ky` 后，周期 envelope 应保持 `n=0`；没有真实 y-periodic contrast 可以把能量耦合到 `n=-3`。

Ny=3 时：

```text
2*ky ≈ 3*Gy
```

并且 `gamma(n=0)≈-gamma(n=-3)`。有限元 trace 仅有 3 个 y 单元，其离散 reciprocal frequency 正好为 `3*Gy`，使两个不同连续 Fourier order 在离散 trace space 中形成近 alias pair。实际 surface vectors 的 overlap 为 O(1)，确认这不是纯解析猜测。

Ny=4 后：

- 原 `n=0/n=-3` vectors 恢复正交；
- `n=-3` 辅助振幅、功率和 field Fourier fraction 降至舍入误差；
- R/T/A 向 Ny=5/6 收敛；
- 原 leakage Gate 无需改变。

因此：

```text
root cause = Ny3 mesh-induced discrete Bragg / trace alias
fix = Ny4 production trace resolution
threshold relaxation = forbidden and unnecessary
```

---

## 4. outgoing-P discrepancy 的正确 disposition

### 4.1 为什么当前 P comparison 不成立

当前 `_mode_projection_from_solution(...)` 构造：

```text
reference = full 3-component mode.e_vector * phase
numerator = integral E_total · conjugate(reference)
denominator = area * electric_tangential_norm_sq * |phase|^2
```

但 augmented DtN auxiliary row 是通过 x/y surface component vectors 构造的，只作用于 H(curl) 的切向 trace：

```text
E_t = (E_x, E_y)
e_t = (e_x, e_y)
```

所以正确的独立检查必须是：

\[
a_m =
\frac{\int_\Gamma \mathbf E_t\cdot\overline{\mathbf e_{t,m}e^{i\mathbf k_t\cdot\mathbf x}}\,d\Gamma}
     {\int_\Gamma |\mathbf e_{t,m}e^{i\mathbf k_t\cdot\mathbf x}|^2\,d\Gamma}.
\]

不能在分子中加入 `E_z * conj(e_z)`，再除以切向 denominator。

S 模式满足 `e_z=0`，错误诊断恰好与 auxiliary 一致；P 模式通常具有较大的 `e_z`，特别是掠射入射，因此错误诊断出现放大的差异。这也解释了：

```text
S discrepancy <= 7.7e-14
P discrepancy = O(1e-3)
```

该模式与代码公式完全一致。

### 4.2 必须修正

在恢复生产前：

1. 将 `_mode_projection_from_solution(...)` 改为明确的 tangential projection，或新增不易误用的：
   ```text
   _tangential_mode_projection_from_solution(...)
   ```
2. numerator 中显式使用：
   ```text
   E_t = (E_total[0], E_total[1], 0)
   reference_t = (e_x, e_y, 0) * phase
   ```
3. denominator 继续使用 `electric_tangential_norm_sq`；
4. 更新 docstring，明确该函数检查的是 port tangential trace coefficient；
5. 增加解析 plane-wave / synthetic trace tests，覆盖：
   - oblique S；
   - oblique P with nonzero e_z；
   - top incident subtraction；
   - lossy-bottom P；
6. 在 Case118 Ny=3 和 Ny=4 原点上重新生成 auxiliary-vs-direct comparison；
7. 要求所有被检查的 S/P、top/bottom、n=0/n=-3：
   ```text
   absolute amplitude difference <= 1e-10
   ```
   对近零通道同时报告 absolute scale，不使用不稳定的相对误差。

若修正后的纯切向投影仍与 auxiliary 不一致，则 controlled stop，继续审查 auxiliary row/denominator/static-condensation Schur。按当前代码和数值比例判断，预期该 Gate 会通过。

### 4.3 对历史/生产数据的影响

- Case118 的 S-alias 根因结论不受影响；S direct comparison 本来已通过。
- 官方 R/T/order power 来源是 augmented auxiliary modal amplitudes，不是错误的 full-vector diagnostic projection。
- 当前没有证据表明 production auxiliary P coefficients 错误。
- 但在 tangential direct Gate 通过前，不得开始新的 Ny=4 bulk。

---

## 5. Production identity 必须升级

不得仅把内部常数 `(6,3,14)` 改成 `(6,4,14)`，却继续使用旧 identity。

建议冻结：

```text
model_id = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route_id = full3d_static_uniform_n1curl_p5_h10_ny4
axis_cell_counts = (6,4,14)
element = uniform N1curl p5
backend = assembly-time static condensation
observable_schema = task002.fixed-n0-orders.v3
output_profile = compact_surrogate_record
```

并版本化：

```text
parameter schema -> v3 or later
dataset schema   -> v3 or later
campaign schema  -> v4 or later
full3d record     -> new version if topology identity semantics change
```

硬要求：

1. production registry 不再允许 Ny=3 identity；
2. actual runtime topology 必须报告 `(6,4,14)`；
3. planned/actual geometry、tags、Floquet blocks、element、DoF count 全部匹配；
4. 新 model/route ID 必须进入每个 record、manifest 和 dataset manifest；
5. Case117 Ny=3 manifest 和 raw evidence不可重写；
6. 原 56 个 Ny=3 measured-pass 不能进入 Ny=4 production dataset；
7. 建议新建 Case119，避免将两个离散模型混入 Case117。

---

## 6. Required M4E：Ny4 production rebaseline

### M4E-1 修正 P tangential projection

完成第 4 节的代码、测试和两点 PDE/observer 回归。不得通过忽略 outgoing P 字段来绕过；observable v3 继续保存 outgoing S/P。

### M4E-2 建立 Ny4 production route

更新 production config、registry、runtime topology、campaign、adapter 和 checker。Ny4 必须成为代码层面唯一允许的 Task002 production mesh。

### M4E-3 新 clean baseline 与设计 rebind

完成实现和 targeted tests 后提交新的 clean implementation SHA。使用 Case116 完全相同的冻结四元组重新生成 metadata，并断言：

```text
training tuple hash unchanged
validation tuple hash unchanged
candidate tuple hash unchanged
audit tuple hash unchanged
```

只允许 source/model/route/topology/schema/combined identity 更新。

### M4E-4 enhanced canary

新 SHA 下，先执行：

#### A. 16 个四维 domain corners

保持原 canary。

#### B. 原失败 training index 40

必须通过原 leakage Gate：

```text
n!=0 total power <= 1e-7
n!=0 max amplitude <= 1e-4
```

预期应降至舍入量级。

#### C. 三个 alias-neighborhood diagnostic points

在 center geometry、原 grazing 下：

```text
azimuth = 54.25°, 54.50°, 54.75°
```

这些是 diagnostic canary，不加入 training/validation。要求 Ny4 的 n!=0 泄漏均通过原 Gate。

#### D. tangential auxiliary/direct Gate

至少在：

```text
original failed point
center geometry at 54.50°
one high-grazing conical point
```

对 v3 中所有实际 power-carrying S/P modes做 auxiliary-vs-direct tangential comparison；最大 absolute difference `<=1e-10`。

#### E. 其余数值 Gate

每点要求：

```text
direct solve completed
true residual <= 1e-9
|R+T+A_volume-1| <= 1e-7
observable v3 complete
fixed/raw ledger pass
actual runtime topology matches Ny4 plan
uniform N1curl p5
zero swap
cleanup complete
compact output identity pass
```

若 enhanced canary 全部通过，Codex 无需再次等待 Review，可以继续 M4E-5。

### M4E-5 从头生成 Ny4 production data

新 campaign 中：

```text
training = 96 Ny4 p5 samples
frozen validation = 16 Ny4 p5 samples
total = 112
```

要求：

- 不复用 Ny3 的 56 个结果；
- 每 16 点 checkpoint；
- first unexplained failure stop 保持；
- frozen validation 只运行和封存，不读取其响应做模型选择；
- 所有样本一个 clean SHA、一个 Ny4 model/route、一个 observable v3；
- 8 个 discretization-audit points 独立存放，不进入 production dataset。

### M4E-6 compact dataset

完成后生成 p5/Ny4-only compact dataset，并由独立 checker 验证：

```text
96 train exactly once
16 frozen validation exactly once
no extra points
no overlap
one clean SHA
Ny4 route only
observable v3 only
all runtime topology/leakage/ledger/resource Gates pass
file hashes and array identities pass
```

M4E 完成后停止等待 Review V8。不得自行开始 PCE、GP、frozen-validation scoring、active learning、angle DOE 或 inversion。

---

## 7. Discretization uncertainty and audit

Ny4 已解决 y-alias，但 p5/h10 仍是 best-available operational high fidelity，不是 continuum truth。

后续 discretization audit 应更新为与 production y-grid 相容的路线。若运行 p4/h7.5 或其他比较模型，其 y 向网格也不得重新引入 Ny=3 alias。建议至少使用 Ny=4，并记录独立 model identity。

Case118 给出的 Ny4--Ny6 局部差异可作为 y-discretization evidence：

```text
|ΔR| ≈ 4.1e-6
|ΔT| ≈ 8.8e-6
```

但不能把单点差异直接当作整个四维域的统一误差上界。后续 8 个 discretization-audit 点应继续用于估计 `Sigma_discretization`。

---

## 8. 禁止事项

本轮禁止：

- 恢复或修改 Case117 Ny3 campaign；
- 将 Ny3 56 个 pass 混入 Ny4 dataset；
- 放宽 leakage Gate；
- 删除 outgoing P 以规避诊断；
- 修改冻结四元组点表；
- 在 enhanced canary 失败后跳过点继续 bulk；
- 在 Ny4 dataset 完成前训练 PCE/GP；
- 读取 frozen-validation 响应做 feature/kernel/model选择；
- 开始 angle DOE 或正式反演。

---

## 9. 交付要求

建议新增：

```text
benchmarks/cases/119_task002_p5_ny4_bulk_campaign/
    README.md
    config.json
    expected.json
    checker
    records/

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
    outcomes/m4e_ny4_production.md
    outcomes/m4e_dataset_report.md
    response_v8.md
```

至少保存：

- tangential P-projection correction report；
- old/new design tuple hash audit；
- new Ny4 implementation SHA；
- enhanced canary report；
- training/validation inventories；
- first-failure/negative inventory；
- resource summary；
- compact dataset verification；
- focused/full regression summary；
- branch/upstream/clean status。

---

## 10. Review V8 通过条件

1. P direct diagnostic 已改为纯切向投影，S/P auxiliary comparison 通过；
2. production identity 明确为 Ny4，并硬拒绝 Ny3；
3. frozen point tuple hashes 完全不变；
4. enhanced canary 全部通过；
5. 96 training + 16 validation 全部为 Ny4 measured-pass；
6. 无 skipped failure、无 swap、cleanup complete；
7. compact dataset 独立 checker 通过；
8. frozen validation 未用于模型选择；
9. 未提前开始 surrogate training、angle DOE 或 inversion。
