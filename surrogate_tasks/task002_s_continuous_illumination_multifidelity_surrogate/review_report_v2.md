# Task002 Review Report V2

## 1. 审阅结论

```text
review_status = solver_domain_qualification_required
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M2A_evidence = approved_and_retain
old_near_cutoff_explanation = rejected
LF4_uniform_full_angle_fidelity = rejected
p4_M_truncation_as_root_cause = rejected
true_p_converged_reference_branch = not_established
general_conical_Hybrid_robustness = not_established
bulk_generation = not_authorized
surrogate_training = not_authorized
angle_DOE = not_authorized
production_inversion = not_authorized
required_next_action = M2B_solver_domain_robustness_qualification
```

M2A 已按 Review V1 完成，结果有价值且应保留。当前问题已经不是单个 `0.5°/15°/S` 样本偶然越过能量 Gate，而是连续角域扩展暴露了三个不同层次的问题：

1. `Hybrid p4/h10/M120` 在低掠射一般方位角下存在随方位角系统变化的能量闭合缺陷；
2. p4 与 p5/p6 给出两条明显不同的响应分支，但目前只有 Full3D p4 reference，尚不能判断哪条才是 p 收敛方向；
3. p6 在 `0.5°/45°/S` 出现独立的 biorthogonality Gate failure，说明一般锥形入射下模态配对/归一化的鲁棒性仍未建立。

因此，不应继续“出现一个失败点就修一个点”，也不应直接开始 4D 训练数据生成。下一阶段应先完成一次**求解器域资格化（solver-domain qualification）**：在中心几何上系统扫描角域，并以同阶 Full3D、跨阶 Full3D、Hybrid A/B 路径和模态连续性证据建立明确的有效域或显式 solver routing map。

---

## 2. 已确认并接受的 M2A 结论

### 2.1 Rayleigh/cutoff 不是当前失败根因

升级后的 cutoff v2 已区分：

```text
incident/specular m=0 grazing metric
nearest non-incident diffraction-order metric
local Rayleigh opening/closing event
```

在 `0.5°/15°/S`：

```text
incident m=0 |beta|/k0 = 0.0087265
nearest non-incident order = bottom m=-7
nearest non-incident |beta|/k0 = 0.2777146
local nonzero-order Rayleigh crossing = false
```

所以旧 `near_cutoff=true` 只是入射零级法向波数很小，不能解释中间方位角失败。不得继续把该问题称为 Rayleigh anomaly。

### 2.2 p4 的失败不是 M120 截断不足

同一点的 p4 结果：

| M | R | energy closure | assembled E |
|---:|---:|---:|---:|
| 80 | 0.818563073 | `-2.620e-5` | `1.242e-3` |
| 120 | 0.818563132 | `-2.606e-5` | `1.240e-3` |
| 160 | 0.818563134 | `-2.607e-5` | `1.240e-3` |
| 240 | 0.818562935 | `-2.666e-5` | `1.240e-3` |

M80--M240 已稳定在同一结果，因此继续增加 p4 模态数不能解决当前闭合缺陷。M 截断不是 p4 失败的主要根因。

### 2.3 p4 Hybrid 的外部响应接近同阶 Full3D

独立 Full3D static-condensed p4/h10 在 `0.5°/15°/S`：

```text
R = 0.8186083122
T = 0.0014147086
A = 0.1799769792
energy closure = 4.92e-13
```

Hybrid p4/M120：

```text
R = 0.8185631316
T = 0.0014147769
A_balance = 0.1800220914
A_volume  = 0.1799960301
```

其中 `delta R=-4.52e-5`。这说明 p4 Hybrid 的外端口解并非完全错误；它主要存在一个小但系统性的 Hybrid 能量闭合缺陷。不能把这个结果描述成“线性方程没解对”或“p4 场完全错误”。

### 2.4 吸收体积分本身不是主因

p4 中间模态区域的 volume loss 与两接口 Poynting loss 只差约 `2.18e-6` code units；p5/p6 更接近。Full3D p4 的体积吸收与 port balance 闭合到 `4.92e-13`。因此：

- 不是普通 z 积分阶次不足；
- 不是简单增加 M 可以修复；
- 仍需进一步检查上下 local FEM 子域各自的离散 Poynting identity、接口功率配对和 external auxiliary port coupling。

### 2.5 LF4 的失败形成一般锥形方位角带

在 `grazing=0.5°` 时，LF4 energy closure：

```text
azimuth 0°  :  3.45e-7
azimuth 5°  : -1.57e-6
azimuth 10° : -7.73e-6
azimuth 15° : -2.61e-5
azimuth 20° : -5.85e-5
azimuth 30° : -1.83e-4
azimuth 45° : -3.30e-4
azimuth 60° : -1.76e-4
azimuth 75° : -2.41e-5
azimuth 90° : -6.88e-9
```

误差在 `phi=0°/90°` 两个特殊端点消失，在一般 `kx!=0, ky!=0` 的中间方位角增强，并近似围绕 45°形成带状分布。这是一个**系统性角度依赖模式**，不是随机浮点误差。

---

## 3. 当前最重要的未决问题

### R1：尚无独立 high-order reference，不能判定 p6 是 HF truth

在 `0.5°/15°/S`：

```text
p4 Hybrid / Full3D p4: R ≈ 0.8186
p5 Hybrid:             R = 0.6317
p6 Hybrid:             R = 0.6215
```

p5 与 p6 彼此更接近，可能表示 p4 严重欠分辨，也可能表示 p5/p6 Hybrid 进入了错误的模态/传播分支。当前只有 Full3D p4 reference，不能从现有证据决定哪一种解释正确。

因此以下说法都尚未获证：

```text
p4 是可信 LF、p6 是可信 HF
p5/p6 的跳变一定是代码 bug
p4 与 Full3D p4 一致就代表 p4 接近连续真解
```

在建立 Full3D p5 或其他独立高阶 reference 前，Task002 的 LF/HF 层级不成立。

### R2：p-dependent axial propagation/traction 映射是高优先级嫌疑

当前 Hybrid 使用：

```text
transverse mode source = 2D mixed Maxwell QEP
axial propagation       = full3d_uniform_cg
interface traction      = scalar_cg_discrete_derivative
```

即先求连续横截面 QEP 的 beta，再通过独立的 scalar CG(p) 周期链将 beta 映射为 p-dependent propagation beta，并用另一 endpoint-derivative symbol 形成 traction beta。这套方法会随 p 改变传播和 traction，但没有从同一个完整三维离散 Maxwell pencil 同时导出 `E/H/propagation/traction`。

p4→p5/p6 的巨大分支跳变与这一 p-dependent 映射高度相关，但目前尚无 A/B 证据。必须直接比较：

```text
continuous_beta + continuous_qep_beta
vs
full3d_uniform_cg + scalar_cg_discrete_derivative
```

而不是继续假定后者在整个角域内天然正确。

### R3：p6 biorthogonality 在 45°失败

`0.5°/45°/S` 的 p6 解在 residual、energy 和 interface 指标上接近通过，却独立触发：

```text
biorthogonality_identity_error_le_1e-6 = false
```

这说明当前模式选择、reciprocal pairing、near-degenerate block rotation 或 left/right normalization 在一般锥形角度下不稳定。即使 R/T/A 看似平滑，也不能忽略该失败，因为代理训练会把角度间的 mode swap 或 basis discontinuity 当成物理响应。

### R4：双 Floquet 约束缺少真实解析 probe authority

Cross-section Floquet 实现会记录 `max_probe_residual`，但当前返回值为固定 `0.0`，并非真正用解析 quasi-periodic field 或随机自由向量验证 `u=Cq` 后的 x/y/corner 相位与高阶方向变换。

一般方位角同时具有非平凡 `phase_x` 和 `phase_y`；0°/90°端点不能覆盖双相位 corner、两轴 orientation 与 mixed transverse/longitudinal coupling 的全部风险。因此必须增加真实 probe，而不能把“约束成功构建”当成“约束在任意 kx/ky 下已物理验证”。

### R5：当前工程流程是点资格化，不是域资格化

Task001 主要在少数端点和名义角度上资格化。Task002 将目标扩展为连续四维域后，之前的单点回归测试只能保证旧点不退化，不能证明整个角域稳定。

“总是不停出现问题”的根本流程原因是：

```text
先扩大参数域
-> 在第一个新点发现新失败
-> 定向修复
-> 再遇到下一个未覆盖机制
```

应改为：

```text
先做求解器域扫描和交叉 reference
-> 冻结有效域/solver routing
-> 再生成 surrogate dataset
```

---

## 4. Required M2B：求解器域鲁棒性资格化

下一轮仍属于 Task002 M2，不开始 M3--M10。

建议建立：

```text
benchmarks/cases/114_task002_solver_domain_robustness/
```

以及：

```text
surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m2_solver_domain_qualification.md
  outcomes/solver_routing_map.md
  response_v3.md
```

### M2B-0：保留证据与 source 纪律

1. Case112/113 的 raw、compact records 和 hashes 原样保留；
2. instrumentation-only 修改可使用新的 diagnostic SHA；
3. 修改矩阵、QEP、Floquet、mode selection、propagation、traction、postprocessing 或 Gate 后，建立新的 formal source SHA；
4. 一次一个 FEM，MPI2、每 rank 一线程、zero swap、watchdog；
5. 不 merge/rebase master，不开始 bulk/surrogate。

### M2B-1：先建立真正的 p-reference

在中心几何至少对以下点建立 independent Full3D static-condensed reference：

```text
A = 0.5° / 15° / S
B = 0.5° / 45° / S
C = 2.0° / 15° / S
D = 10°  / 45° / S
```

每点优先运行：

```text
Full3D p3/h10
Full3D p4/h10
Full3D p5/h10
```

p5 启动前做 RSS/factor projection；若安全则运行。p6 Full3D 在 16 GB 本机不是强制项，不能用 swap/OOC 强行完成。若 p5 仍不足，允许增加一个资源安全的 h-refinement（如 Full3D p4/h7.5）或在工作站另行运行独立 reference。

必须比较：

- R/T/A 与每个 fixed order complex amplitude/power；
- volume absorption；
- residual；
- p/h 差值；
- 是否向 p5/p6 Hybrid 分支收敛。

判定：

```text
Full3D p5 -> Hybrid p5/p6 branch
    => p4 在低掠射区欠分辨；LF4 不可用

Full3D p5 -> Full3D/Hybrid p4 branch
    => p5/p6 Hybrid 数值路径有错误

Full3D p3/p4/p5 不稳定
    => 需要 h/p reference 或独立 2.5D EUV solver，不能冻结 HF
```

### M2B-2：对 axial model 做 A/B，而不是猜测

在 `0.5°/15°` 与 `0.5°/45°`，对 p4、p5、p6（资源允许范围）比较：

```text
Route A:
  propagation = continuous_beta
  traction    = continuous_qep_beta

Route B:
  propagation = full3d_uniform_cg
  traction    = scalar_cg_discrete_derivative
```

其余 QEP、mode set、M、接口、网格保持相同。记录：

- mode beta 与 effective beta；
- propagation factor correction；
- traction beta correction；
- R/T/A/orders；
- exact E/traction residual；
- energy closure；
- 对同阶 Full3D reference 的误差。

若分支跳变随 Route B 出现，根因定位到离散 axial mapping；若两条 route 都跳变，应转向 QEP/Floquet/mode basis。

### M2B-3：真实双 Floquet probe

新增不依赖最终 PDE 的解析/代数测试：

1. 对 p=1..6、MPI1/2、代表性 `(grazing,phi)`：
   ```text
   (0.5,15), (0.5,45), (2,30), (10,45)
   ```
   构造解析 quasi-periodic vector/scalar field；
2. 检查 x、y、corner 的 phase、edge orientation、longitudinal corner phase；
3. 检查 `u=Cq` 后每一个 slave row 的真实 residual；
4. 对随机 free vector 检查 C 的 deterministic MPI identity；
5. 小网格比较 `C^H A C` 与独立显式消元 action；
6. `max_probe_residual` 必须来自实际计算，不能继续固定为 0。

### M2B-4：模态连续性与 biorthogonality 扫描

固定中心几何和 grazing=0.5°，按：

```text
phi = 0,5,10,15,20,30,45,60,75,90°
```

对 p4/p5/p6 记录完整 mode identity：

- beta；
- polynomial residual；
- left/right overlap；
- biorthogonality matrix error；
- near-degenerate groups 与 condition；
- selected candidate indices；
- 与前一 phi 的 overlap matching、permutation 和 subspace angle。

模式必须通过 overlap/continuation 跟踪，不得只在每个角度独立按 target magnitude 排序后假设“第 j 个模式”具有相同物理身份。

45°的失败必须定位到具体 mode/block：

```text
isolated mode normalization
near-degenerate block rotation
reciprocal pairing
candidate pool遗漏
或条件数本身不可接受
```

### M2B-5：完整子域能量 identity

现有 middle volume/Poynting ledger 不足。对代表点增加：

```text
bottom local FEM:
  external flux
  interface flux
  volume absorption
  discrete balance residual

top local FEM:
  interface flux
  external flux
  volume absorption
  discrete balance residual

middle modal:
  bottom/top interface flux
  volume absorption
  balance residual

external DtN:
  raw modal power sum
  auxiliary unknown work/power identity
```

这样才能判断 azimuth-dependent closure 缺陷属于：

- local FEM/interface load；
- middle modal propagation；
- external DtN auxiliary coupling；
- 或只属于 volume postprocessing。

### M2B-6：中心几何角域鲁棒性扫描

有必要扫描，但不是直接扫描完整 `(h,w,grazing,phi)` 四维数据域。先固定：

```text
h=120 nm, w=17 nm, S, lambda=13.5 nm
```

冻结角度矩阵：

```text
grazing = [0.5, 0.75, 1, 2, 4, 6, 8, 10]°
azimuth = [0, 5, 10, 15, 20, 30, 45, 60, 75, 90]°
```

共 80 个角度。建议：

1. 每个角度运行 Hybrid p4/M120；
2. 每个角度运行 independent Full3D p4 static（已有证据表明成本可承受）；
3. 计算同阶 Hybrid-vs-Full3D 的 R/T/A/order error map；
4. 在误差峰值、角域边界和分支变化处选择 12--20 个点运行 Full3D p5 与 Hybrid p5/p6；
5. 生成：
   - formal Gate pass/fail map；
   - same-p Hybrid error map；
   - p-reference map；
   - biorthogonality map；
   - solver route map。

这个扫描是求解器资格化证据，不是 surrogate training dataset。失败点应继续记录，不在首个失败时终止整个诊断矩阵。

只有中心几何角域完成 disposition 后，才在几何四角/轴向点做少量确认；不要现在直接扩大到完整 4D。

### M2B-7：冻结 solver routing decision

最终必须选择并明确记录一种方案：

#### Route 1：统一 Hybrid 多保真

只有 p-reference、biorthogonality、energy 和 same-p Full3D 对照均通过时，才能继续使用统一 Hybrid LF/HF。

#### Route 2：升级统一 LF

若 p4 欠分辨而 p5 合格且经济：

```text
LF = qualified p5 route
HF = qualified p6 route or independent higher reference
```

旧 LF4 不得混入同一 fidelity layer。

#### Route 3：显式角域分区

例如：

```text
ordinary-angle region -> Hybrid route
low-grazing general-conical region -> Full3D static route
```

允许分区，但每个样本必须保存 route id，不能把不同 solver 静默拼成同一个 LF。代理也必须获得 regime/route-aware uncertainty，并在边界加密验证。

#### Route 4：Hybrid 暂缓，统一使用 Full3D static

若 Hybrid 在一般方位角无法建立稳定域，而 Full3D p4/p5 成本仍可接受，则正式数据生成先使用资格化的 Full3D static fidelity hierarchy。这比用不稳定的 Hybrid 生成大量廉价但错误的数据更合理。

---

## 5. M2B 通过条件

只有以下事项全部完成，才允许恢复 Task002 M3：

1. 独立 p-reference 确定可信响应分支；
2. p4/p5/p6 的角色重新冻结，不再仅凭名义角度假定 LF/HF；
3. 一般 `kx!=0,ky!=0` 的 Floquet probe 通过 p1--p6、MPI1/2；
4. 45° biorthogonality failure 有根因和修复，或该 route/region被明确排除；
5. 中心几何 80-angle robustness map 完成；
6. formal failures 有明确修复或显式 solver routing disposition；
7. 不放宽既有 Gate 来掩盖失败；
8. 新 formal solver/source、dataset schema 和 route identity 已冻结；
9. Case112/113 历史负证据保留；
10. 尚未开始四维 bulk、surrogate fit、angle DOE 或 inversion。

---

## 6. 需要交付的报告

至少生成：

```text
benchmarks/cases/114_task002_solver_domain_robustness/
  config.json
  expected.json
  records/full3d_p_reference.json
  records/axial_model_ab.json
  records/floquet_probe.json
  records/mode_continuation.json
  records/energy_identity.json
  records/angle_robustness_map.json
  records/solver_routing_map.json

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m2_solver_domain_qualification.md
  outcomes/solver_routing_map.md
  response_v3.md
```

完成后提交并只推送当前代理分支，停止等待 ChatGPT Review V3。不得自行恢复正式 49 点 campaign 或开始 M3--M10。
