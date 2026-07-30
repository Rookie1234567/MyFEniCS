# Task002 Review Report V6

## 1. 审阅结论

```text
review_status = controlled_stop_approved_targeted_y_alias_diagnosis_required
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M4P_engineering = approved_and_retain
16_point_canary = approved_16_of_16
training_progress = retain_56_pass_1_failed_39_not_run
first_failure_stop = procedurally_correct
current_p5_Ny3_production_domain = not_qualified
M4_resume = not_authorized
M5_dataset_transfer = not_authorized
M6_surrogate_training = not_authorized
angle_DOE = not_authorized
production_inversion = not_authorized
required_next_action = M4D_y_direction_discrete_Bragg_alias_diagnosis
```

Case117 没有因 campaign、资源或线性求解失败而“卡死”。它按照 Review V5 的 first-unexplained-failure 合同，在 training design index 40 主动停止。M4P 的 resume-safe campaign、design binding、compact output、formal-record adapter、功率账本和 checker 均应保留。

但当前不能简单放宽 `n!=0` Gate 并继续。新的数值证据高度指向：**y 向仅 3 个单元时，在特定方位角附近发生网格诱导的离散 Bragg/傅里叶混叠，导致物理上应解耦的 `n=0` 与 `n=-3` 通道发生数值耦合。** 该假设必须通过定向 A/B 试验确认。

---

## 2. 已接受的 Case117 结果

### 2.1 M4P 工程实现

接受：

- campaign v3 绑定冻结 design，采用原子 manifest、attempt history、stale artifact recovery 和 first-failure stop；
- `compact_surrogate_record` 与 ordinary output 的两点 A/B 一致；
- compact payload 约 0.62--0.66 MB，而 ordinary payload 约 14.4 MB；
- p5-only leakage Gate、fixed/raw power ledger 和 exact-design dataset adapter 已实现；
- M4 clean implementation SHA 为：
  ```text
  ba50cd36b081637ed5ea97c2dc8e4827d992b940
  ```
- Case116 冻结四元组没有改变，只重新绑定 source metadata。

### 2.2 Campaign 进度

接受并保留：

```text
canary                 = 16 / 16 pass
training measured_pass = 56
training failed        = 1
training not_run       = 39
frozen validation      = 0 run
dataset                = not built
```

57 次 PDE attempt 均完成 direct solve、zero swap 和 cleanup。

### 2.3 第一个失败点

```text
training design index = 40
height_nm  = 116.446369998157
width_x_nm = 17.513626368716
grazing_deg = 4.538499870338
azimuth_deg = 54.420819282532
polarization = S
```

通过项：

```text
true residual         = 2.0915e-11
energy closure        = -1.3267e-12
runtime topology      = pass
fixed/raw power ledger = pass
compact identity      = pass
zero swap / cleanup   = pass
```

失败项：

```text
n!=0 reflection power = 1.2727992374e-7
n!=0 transmission power = 1.1039521077e-6
n!=0 total power      = 1.2312320314e-6
n!=0 max amplitude    = 1.0146566168e-3
```

主导通道：

```text
bottom (m=0, n=-3, outgoing S)
power = 1.1036365120e-6
```

因此当前问题不是总能量错误，而是能量在离散 port orders 之间出现了不应有的 y-harmonic 分配。

---

## 3. 首要根因假设：Ny=3 网格诱导的 n=0 ↔ n=-3 离散 Bragg 混叠

正式模型满足：

```text
period_y = 25 nm
grating_width_y = period_y
y-axis cell count Ny = 3
```

所以几何、材料和连续 Maxwell 算子沿 y 不变，物理解应保持单一 Bloch harmonic；`n!=0` 不应成为真实结构响应。

定义：

```text
k0 = 2*pi/13.5 = 0.4654211339 1/nm
Gy = 2*pi/25   = 0.2513274123 1/nm
```

在失败角度：

```text
ky = k0*cos(grazing)*sin(azimuth)
   = 0.3773457689 1/nm

3*Gy/2 = 0.3769911184 1/nm
ky - 3*Gy/2 = 3.5465e-4 1/nm
```

即：

```text
2*ky ≈ 3*Gy
```

同时：

```text
gamma(n=0)  = +0.3773457689
gamma(n=-3) = ky - 3*Gy = -0.3766364680
```

两者几乎互为相反数，因此具有近似相同的横向波数平方和传播常数。

另一方面，Ny=3 意味着 y 单元宽度为 `period_y/3`，其离散网格 reciprocal frequency 恰好为 `3*Gy`。因此 `n=0` 与 `n=-3` 正好构成该网格的近退化 Bragg/alias pair。有限元对 Bloch 相位的分段多项式表示、surface trace projection 或离散 DtN 耦合中的极小非正交误差，会在这个近退化点被显著放大。

这也解释了：

1. 泄漏身份恰好是 `n=-3`，与 Ny=3 对应；
2. 之前 80-angle authority 的 azimuth 网格包含 45° 和 60°，但没有覆盖约 54° 的窄峰；
3. authority 最大总泄漏仅 `4.94e-9`，而 Sobol 点在 54.42° 达到 `1.23e-6`；
4. 16 个 domain-corner canary 全部通过，但 interior Sobol point 失败。

这是目前最强的根因推断，但仍需 M4D 的收敛与算子证据才能正式定案。

---

## 4. Required M4D：定向诊断，不恢复 bulk

本轮不得重试 index 40 来“碰运气”，不得修改 frozen point tables，不得继续 index 41--95，也不得读取 frozen validation。

### M4D-1：失败邻域的 azimuth 峰值图

固定失败几何和 grazing：

```text
h = 116.446369998157 nm
w = 17.513626368716 nm
grazing = 4.538499870338°
```

运行 p5/h10/Ny=3：

```text
azimuth = 50, 51, 52, 53, 53.5, 54, 54.25, 54.5,
          54.75, 55, 55.5, 56, 57, 58°
```

另以中心几何 `(120,17)` 运行相同的小型 stencil，区分角度主导与几何放大。

必须报告每点：

- `ky`, `2*ky-3*Gy`；
- n=0 与 n=-3 的 alpha/gamma/beta；
- auxiliary amplitude 和 power；
- n!=0 total power/amplitude；
- R/T/A、residual、ledger；
- DtN surface quadrature degree。

### M4D-2：y-cell-count convergence / alias-shift test

在失败点执行：

```text
Ny = 3, 4, 5, 6
Nx = 6, Nz = 14, p = 5 保持不变
```

至少 Ny=3 与 Ny=4 必须完成。资源预估显示 Ny=4 约为现有规模的 4/3，原则上仍在 16 GB 本机可承受范围；仍需 watchdog 和 zero-swap。

关键判据：

- 若 Ny=4 后 `n=-3` 泄漏显著下降，且 n=0 aggregates 稳定，则支持 mesh-alias 根因；
- 若主泄漏随 Ny 改变而转移至 `n=-Ny` 或对应网格 reciprocal pair，则几乎可确认离散 Bragg alias；
- 若泄漏不随 Ny 收敛，则继续检查 DtN coupling/Floquet/材料身份。

### M4D-3：surface quadrature convergence

当前 p5/auto-order 的 surface quadrature 通常约为 q=23。固定 Ny=3 失败点，运行：

```text
q = current, 31, 39, 47
```

若 n=-3 amplitude 随 q 明显变化，则根因位于 Fourier surface assembly/projection；若稳定，则排除积分阶次不足。

不得以单次提高 q 后“刚好低于 Gate”作为完成标准，必须给出收敛趋势。

### M4D-4：auxiliary amplitude 与独立场投影对照

对失败点从重构的 `E_total` 独立计算：

```text
n=0 / n=-3
reflection / transmission
S / P
```

使用独立高阶 quadrature，比较：

```text
amplitude_from_augmented_auxiliary_unknown
amplitude_from_direct_boundary_projection(E_total)
```

判定：

- 二者一致：离散 FE/DtN 解本身含 alias harmonic；
- 二者不一致：auxiliary equation、projection denominator 或 coupling assembly 有 bug。

同时计算 demodulated field：

```text
E_tilde(x,y,z) = E(x,y,z) * exp(-i*ky*y)
```

在 top/bottom port 与若干 volume slice 上测量 y-variation 和 Fourier energy fraction。

### M4D-5：离散 port-vector Gram / condition audit

在相同实际 trace space中构造 n=0 与 n=-3 的 surface vectors，计算归一化 overlap、Gram singular values 和 condition number：

```text
Ny=3 vs Ny=4
current q vs high q
```

连续理论上不同 Fourier orders 正交。若 projected trace vectors 在 Ny=3 近相关而 Ny=4 改善，即直接确认端口离散 alias。

### M4D-6：static condensation 排除试验

若资源允许，对失败点做一次：

```text
assembly-time static-condensed p5/Ny3
vs
standard-full or independently equivalent p5/Ny3
```

比较 R/T/A 和 n=-3 amplitude。若 standard full 不可承受，允许在可控降阶/缩小 benchmark 上验证同一 alias mechanism。不得把 static condensation 预设为根因；现有 residual/ledger 证据更支持 port/trace alias。

---

## 5. 修复路线判定

### Route A：Ny=4 消除 alias（当前首选）

若 Ny=4 满足：

```text
n!=0 total power <= 1e-7
n!=0 max amplitude <= 1e-4
R/T/A 与 Ny-refinement 趋势稳定
all original numerical Gates pass
```

则正式 production mesh identity 改为：

```text
AXIS_CELL_COUNTS = (6,4,14)
```

随后：

1. 建立新 clean solver SHA、parameter/config/topology identity；
2. 保持 96/16/4096/8 的冻结四元组完全不变，只 rebind metadata；
3. 重新运行：
   - failure-neighborhood stencil；
   - 16 domain-corner canary；
   - 至少 8 个 general interior canary，必须包含原 index 40；
4. 全部通过后，从零重新生成 96 training + 16 validation。

现有 Ny=3 的 56 pass 不得与 Ny=4 dataset 混用；保留为 immutable negative/diagnostic evidence。

### Route B：quadrature/projection bug

若 q 或 independent projection 对照暴露错误：

1. 修复 surface assembly/projection；
2. 新 clean SHA；
3. 保持点表不变；
4. 重新运行最小 authority、16 corner canary、原 index 40 和邻域；
5. 通过后重启完整 M4。

### Route C：auxiliary DtN 近退化 mode basis 问题

若 surface-vector Gram 在 n=0/n=-3 近奇异，但 y-refinement不足以解决，应考虑：

- 对 projected port basis 做 block orthogonalization/biorthogonalization；
- 对近退化 Fourier pair构造完整 Gram coupling，而非只使用单模 denominator；
- 加入 condition-number Gate；
- 重新验证 DtN power/reciprocity。

不得通过从 auto DtN 中静默删除 n=-3 来掩盖问题。

### Route D：工程性放宽 leakage Gate

只有在以下条件全部成立时才可讨论：

- Ny/q/投影收敛已经证明该泄漏是有界离散误差而非 bug；
- n=0 observables 与更细参考闭合；
- leakage 对所有生产目标远低于 measurement、surrogate 和 discretization error budgets；
- 新阈值在恢复 campaign 前预冻结。

当前证据不足，禁止直接将 `1e-7` 改成 `1e-6` 或 `1e-5`。

---

## 6. 方法上的长期说明

由于材料和几何沿 y 完全不变，最干净的方法是因子化：

```text
E(x,y,z) = E_tilde(x,z) * exp(i*ky*y)
```

即 2.5D Maxwell 或等价的 Bloch-envelope 子空间。这会从根本上消除非物理 n!=0 mixing，也比三维 y 网格更高效。

但 Task002 当前不要求立即重写 2.5D。优先完成 Ny=4 与 port-projection 定向诊断；若 Ny-refinement 仍不能提供全角域稳定性，再把 2.5D 作为正式替代路线评估。

---

## 7. 交付合同

新增 Case118 或等价隔离 case，至少生成：

```text
benchmarks/cases/118_task002_y_alias_qualification/
  README.md
  config.json
  expected.json
  records/
    failed_point_reproduction.json
    azimuth_resonance_map.json
    y_cell_convergence.json
    surface_quadrature_convergence.json
    auxiliary_vs_direct_projection.json
    port_vector_gram_condition.json
    solver_route_decision.json
  test_command.txt

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m4_y_alias_diagnosis.md
  response_v7.md
```

要求：

- 不修改 Case117 raw evidence；
- 不修改 frozen point tuples；
- 不读取 frozen validation；
- 不继续 M4 bulk；
- 不训练 surrogate；
- 所有诊断绑定 clean SHA、zero swap、artifact hashes；
- targeted tests、compileall、`git diff --check`；
- 提交后停止等待 Review V7。

---

## 8. Review V7 放行条件

只有满足以下条件之一，才恢复 M4：

1. Ny=4 或其他明确的新 production discretization 在原失败点、邻域、corner/interior canary 中全部通过，并建立新 dataset identity；或
2. 明确的 DtN quadrature/projection/coupling bug 已修复并经相同矩阵验证；或
3. 经过收敛证据支持的新 leakage acceptance contract 已预冻结。

在此之前：

```text
56 Ny3 pass = retain diagnostic only
index40 failure = retain negative authority
M4 resume = forbidden
M5/M6/DOE/inversion = forbidden
```
