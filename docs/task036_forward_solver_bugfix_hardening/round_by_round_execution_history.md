# Task001 至 Task002 按轮次执行历史

> 本文按实际开发与审阅轮次整理：每轮先列出运行过的模型与主要结果，再说明发现的问题、采用的诊断/修正方法，以及为什么进入下一轮。
>
> 需要特别区分两类结论：
>
> 1. **阶段性结论**：在当时有限角度、有限几何和有限模型下成立；
> 2. **当前结论**：经过后续连续角域、p/h 收敛、实际网格和批量运行检验后仍然成立。
>
> 因此，本文不会把早期已经被后续证据推翻的判断继续写成最终生产结论。

---

## 0. 当前状态总览

截至 Review V7，正式项目状态为：

```text
wavelength = 13.5 nm
incident polarization = S only
forward inputs = (height, width, grazing angle, azimuth angle)
unknowns for future inversion = (height, width)

current approved production candidate:
    Full3D static
    uniform N1curl p5
    assembly-time static condensation
    Nx = 6, Ny = 4, Nz = 14
    MPI2, one thread per rank

formal surrogate dataset:
    not yet completed
surrogate training:
    not started
angle Fisher scan:
    not started
formal inversion:
    not started
```

早期 Hybrid、p4 和 Ny=3 数据均保留为研究与诊断证据，但不再进入最终生产训练集。

---

# 第一轮：Task001 前向封装与保真度资格化

## 本轮目标

1. 将原固定前向程序封装为可输入高度、宽度、角度和偏振的运行入口；
2. 在本地 16 GB 机器上选择高保真和低保真候选；
3. 建立 clean-SHA、watchdog、zero-swap、失败状态与 compact evidence 合同。

## 本轮运行模型与结果

| 模型 | 数值身份 | 是否真正运行 | 主要结果 | 当时决策 |
|---|---|---:|---|---|
| HF10 | Hybrid，uniform N1curl p6，h10，M120/方向，MPI2 | 是 | nominal peak RSS `3.288 GB`；wall `253.97 s`；true residual `2.48e-12` | 初选 high fidelity |
| HF7P5 | Hybrid，p6，h7.5，M120，MPI2 | 否，资源预估停止 | central memory projection `11.59 GB`；conservative `15.88 GB` | 本地不启动，`controlled_stop_resource_projection` |
| LF4 | Hybrid，uniform N1curl p4，h10，M120，MPI2 | 是 | 五点平均 wall/HF `0.19155`；RSS/HF `0.31765` | 初选 low fidelity |
| LF5 | Hybrid p5/h10/M120 | 否 | LF4 在当时局部 Gate 已通过 | 不运行 |
| M160 | Hybrid p6/h10/M160 | 否 | 正式身份冻结 M120，缺少必要性 | 不运行 |

HF10 名义点与 Case095/096 的 12 个冻结显著通道比较：

```text
maximum absolute power difference    = 2.052e-12
maximum complex amplitude difference = 2.183e-12
```

说明当时的 Hybrid p6/h10/M120 能复现已有 best-available 离散参考；该参考不是 continuum truth。

LF4 与 HF10 五点灵敏度方向：

```text
cosine(dy/dh) = 0.999689
cosine(dy/dw) = 0.999998
```

## 本轮发现的问题

1. 早期文档把 HF 写为 `p5 trace / p6 interior`，但实际代码只设置了 `nedelec_degree=6`；历史 HF 实际是 **uniform N1curl p6**。
2. HF7P5 在 16 GB 本地机器上资源风险过高，不能靠实际 OOM 来验证。
3. LF4/HF10 的一致性只在少量几何点和少量照明条件下验证，尚不能推广到连续角域。

## 采用的解决方法

- 建立参数化 forward wrapper；
- 绑定 numerical source SHA；
- 每次只运行一个 PDE；
- MPI2、每 rank 1 thread；
- watchdog、zero swap、资源 preflight；
- 将 `measured_pass`、`physical failure`、`trace-map failure`、`resource stop` 分开记录；
- 不启动 HF7P5，保留资源投影证据。

## 进入下一轮的理由

保真度候选初步建立，但还不知道哪些角度和偏振真正有助于区分高度与宽度，因此进入 Task001 照明筛选与可辨识性分析。

## 主要证据

- `surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/outcomes/summary.md`
- `benchmarks/cases/110_surrogate_two_parameter_pilot/records/`

---

# 第二轮：Task001 照明筛选与局部可辨识性

## 本轮目标

1. 对代表性掠射角、方位角和 S/P 偏振进行 pilot；
2. 选择最少的照明组合；
3. 用 Jacobian/Fisher 判断高度、宽度是否局部可分。

## 本轮运行配置与结果

| grazing / azimuth / polarization | 模型与几何点 | 结果 | 结论 |
|---|---|---|---|
| 10° / 0° / S | LF4，9 个 geometry | 全部通过 | 选为 planar 配置 |
| 10° / 90° / S | LF4，9 个 geometry | 全部通过 | 选为 conical 配置 |
| 0.5° / 90° / S | LF4，9 个 geometry | 全部通过，但单独 R+T `rho=-0.9839` | 高度/宽度强耦合，不选 |
| 0.5° / 0° / S | LF4 nominal | trace-map failure，约 `6.99e-8 / 6.31e-8` | fail closed |
| 0.5° / 0° / P | LF4 nominal | trace-map failure，约 `1.38e-7` | fail closed |
| 0.5° / 90° / P | LF4 nominal | interface E `0.8993`；energy `8.729e-4` | physical Gate failure |
| 10° / 0° / P | LF4 nominal | interface E `0.6008`；energy `2.203e-5` | physical Gate failure |
| 10° / 90° / P | LF4 nominal | interface E `0.6005`；energy `2.566e-5` | physical Gate failure |

HF10 对最终两个 S 配置分别运行五点中心差分：

```text
G00 = (120, 17)
Gh- = (117.5, 17)
Gh+ = (122.5, 17)
Gw- = (120, 16.5)
Gw+ = (120, 17.5)
```

最终选定照明 bundle：

```text
C1 = 10° grazing / 0° azimuth / S
C2 = 10° grazing / 90° azimuth / S
```

## 可辨识性结果

| 数据 | rank | cond(Jw) | rho(h,w) | 1% provisional sigma h/w |
|---|---:|---:|---:|---:|
| LF reflection-only | 2 | 1.3250 | `-5.79e-5` | 0.03536 / 0.04685 nm |
| LF reflection + transmission | 2 | 1.8386 | -0.2659 | 0.02844 / 0.01660 nm |
| HF reflection-only | 2 | 1.3217 | `1.82e-4` | 0.03150 / 0.04164 nm |
| HF reflection + transmission | 2 | 1.2208 | -0.1479 | 0.02648 / 0.02320 nm |

Synthetic local recovery：

```text
zero perturbation        -> exactly recovered
(+0.5,+0.1) nm           -> noiseless exact recovery
(-0.5,-0.1) nm           -> noiseless exact recovery
2000 draws with 1% noise -> std(h) ≈ 0.0264–0.0267 nm
                            std(w) ≈ 0.0236–0.0237 nm
```

这些只是局部线性和假设噪声下的 DOE sanity，不是正式实验精度。

## 本轮发现的问题

1. 五个照明配置没有通过原 Gate；
2. P 偏振失败不清楚是物理不可解、Hybrid 模态不足，还是诊断错误；
3. 10°/90°/S 角点相对局部线性误差达到约 `0.1617`，说明整个几何域并不适合简单线性或高阶全局多项式；
4. 仅凭少量离散角度不能回答“0.5–10°、0–90°内哪些角度最好”。

## 采用的解决方法

- 不放宽失败 Gate；
- 将五个失败点转入独立 M9 根因诊断；
- 将每个衍射级保存为固定物理 identity；
- 建立 Fisher 与 synthetic recovery，但明确其局部性质；
- 决定未来 Task002 要把角度也作为连续前向输入。

## 进入下一轮的理由

必须先判断五个失败是否属于代码鲁棒性问题，尤其要确认 P 偏振是否物理上可计算。

---

# 第三轮：Task001 M9 五配置失败诊断

## 本轮运行模型与结果

### F1：0.5° / 0° / S trace-map

| 检查 | 原值 | 修正后 |
|---|---:|---:|
| maximum interior trace residual | `O(1e-8)` | `2.78e-13 – 2.91e-13` |
| slave residual | failed | 0 |
| reciprocal consistency | 未闭合 | `<=3.4e-16` |

### F2：0.5° / 0° / P 模态数扫描

| M | interface E error |
|---:|---:|
| 40 | 约 0.893 |
| 80 | 约 0.893 |
| 120 | 约 0.893 |
| 160 | 约 0.893 |
| 240 | 开始下降 |
| 320 | 继续下降 |
| 480 | 约 0.604 |
| 576 | `1.38e-8` |

M576、middle length 2 nm：

```text
interface E = 2.447e-8
energy closure = 1.5491e-4  -> still failed
```

middle loss 独立核对：

```text
volume loss   = 0.0042349041179860734
Poynting loss = 0.004234904117986632
absolute diff = 5.59e-16
```

说明 absorption 后处理不是根因。

### F2–F5 独立 Full3D p4/h10 reference

| ID | configuration | R | T | A | energy error |
|---|---|---:|---:|---:|---:|
| F2 | 0.5° / 0° / P | 0.85842948 | 0.00083315 | 0.14073737 | `6.46e-13` |
| F3 | 0.5° / 90° / P | 0.86093862 | 0.00082812 | 0.13823326 | `1.29e-12` |
| F4 | 10° / 0° / P | 0.00183930 | 0.59665798 | 0.40150272 | `1.06e-12` |
| F5 | 10° / 90° / P | 0.00181296 | 0.60301099 | 0.39517605 | `1.06e-12` |

## 本轮发现的问题

1. F1 是高阶 trace 坐标/degree/quadrature 路径不一致；
2. P 偏振物理解存在，但 Hybrid M120 严重缺少 P trace rank；
3. 即使 M 接近完整 rank，Hybrid propagation/traction/energy closure 仍不闭合；
4. 若 P 需要 M≈576，Hybrid 的降维优势几乎消失。

## 采用的解决方法

### F1 修正

- lifted modal coefficient 使用真实 polynomial degree；
- 显式 surface quadrature；
- reciprocal negative trace 共用 canonical coordinate identity；
- 将 strong traction density proxy 与真正 variational conormal dual 分离。

### P 路线决策

- 不再声称 P 物理失败；
- P 需要时采用已验证的 Full3D static-condensed direct route；
- Hybrid-P 改造延期为独立数值研究；
- 第一版代理和反演只使用 S incident。

## 本轮最终决策

```text
Task001 S scope = closed
Task001 P-Hybrid scope = deferred
Task002 S continuous-angle scope = authorized
```

## 主要证据

- `surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/outcomes/five_configuration_failure_correction.md`
- `benchmarks/cases/111_task001_illumination_robustness/`

---

# 第四轮：Task002 M0–M2 连续角度框架与第一次 pilot

## 本轮目标

将前向映射从：

```text
(h, w) -> response at two fixed angles
```

升级为：

```text
(h, w, grazing, azimuth) -> diffraction mother response
```

固定：

```text
wavelength = 13.5 nm
incident polarization = S
```

## 本轮运行模型与结果

### 四个 S anchor

```text
0.5°/0°/S
0.5°/90°/S
10°/0°/S
10°/90°/S
```

LF/HF anchor 共 8 个均通过原数值 Gate。

### LF angle pilot

原计划中心几何 49 点：

```text
grazing = 0.5, 1, 2, 4, 6, 8, 10°
azimuth = 0, 15, 30, 45, 60, 75, 90°
```

实际在第一个新增内部角度：

```text
h=120, w=17, grazing=0.5°, azimuth=15°, S
```

出现受控停止：

```text
R = 0.8185631316
T = 0.0014147769
A_balance = 0.1800220914
A_volume  = 0.1799960301
A_volume - A_balance = -2.6061e-5
true residual = 2.07e-11
```

## 本轮发现的问题

1. 线性系统求解正确，但 LF Hybrid 未通过冻结能量 Gate；
2. 最初把问题称为 near-cutoff，但 0.5° 所有方位角都具有相同 incident m0 小 beta，而端点却能通过；
3. 低掠射下 LF 与 HF 的 R/A 差达到约 0.23，远超 10° 条件；
4. 当前不能继续假定 p4 Hybrid 是整个连续角域的统一 low fidelity。

## 采用的解决方法

- 停止 49 点 pilot；
- 拒绝“near-cutoff 已解释失败”的表述；
- 建立 M2A：same-point p/M、Full3D reference、energy ledger 和低掠射角度 stencil。

---

# 第五轮：Task002 M2A 低掠射中间方位角定向诊断

## 本轮运行模型与结果

### 0.5° / 15° / S 的 p/M 矩阵

| 模型 | R | energy closure | interface E |
|---|---:|---:|---:|
| Hybrid p4/M80 | 约 0.818563 | `-2.62e-5` | `1.242e-3` |
| Hybrid p4/M120 | 0.818563 | `-2.61e-5` | `1.240e-3` |
| Hybrid p4/M160 | 约 0.818563 | `-2.61e-5` | `1.240e-3` |
| Hybrid p4/M240 | 约 0.818563 | `-2.67e-5` | `1.240e-3` |
| Hybrid p5/M120 | 约 0.631653 | 高阶分支 | — |
| Hybrid p6/M120 | 约 0.621509 | 高阶分支 | — |
| Full3D static p4/h10 | 0.818608 | `4.92e-13` | — |

### 低掠射诊断 stencil

```text
LF diagnostic points = 13
formal pass = 4
formal fail = 9
```

## 本轮发现的问题

1. p4 的结果对 M80–M240 几乎不变，说明不是模态数不足；
2. Full3D p4 与 Hybrid p4 很接近，说明 Hybrid 能复现同阶 p4 离散；
3. p5/p6 却跳到完全不同的响应分支；
4. 仍无法判断是 p4 欠分辨，还是高阶 Hybrid 路线错误。

## 采用的解决方法

进入系统性的 M2B：

- 独立 Full3D p3/p4/p5；
- Full3D p4/h7.5 h-refinement；
- Hybrid p4/p5/p6；
- axial Route A/B；
- 双 Floquet 实际 probe；
- mode continuity / biorthogonality；
- 80-angle robustness map。

---

# 第六轮：Task002 M2B 求解器域鲁棒性资格化

## 本轮运行模型总表

| 诊断 | 运行量 | 主要用途 |
|---|---:|---|
| Full3D p3/h10 | 4 个强制点 | 低阶响应分支 |
| Full3D p4/h10 | 80 个角度 | same-p 独立角域 reference |
| Full3D p5/h10 | 21 个代表点 | 高阶响应分支 |
| Full3D p4/h7.5 | 4 个强制点 | 判断 p4/h10 是否欠分辨 |
| Hybrid p4 | 80 个角度 | 全角域 formal map |
| Hybrid p5 | 12 个点 | same-p 高阶一致性 |
| Hybrid p6 | 12 个点 | 高阶 HF 与模态鲁棒性 |
| axial Route A/B | p4/p5/p6 × 15°/45° | 连续 beta vs scalar-CG beta |
| double Floquet probe | p1–p6 × 4 角度 × MPI1/2 = 48 | x/y/corner、orientation、C^HAC |

## 独立 p/h reference

| point | p3/h10 R/T/A | p4/h10 R/T/A | p5/h10 R/T/A | p4/h7.5 R/T/A |
|---|---|---|---|---|
| 0.5°/15° | 0.996916 / 0.000015 / 0.003068 | 0.818608 / 0.001415 / 0.179977 | 0.631656 / 0.005904 / 0.362441 | 0.634389 / 0.005815 / 0.359796 |
| 0.5°/45° | 0.949061 / 0.000087 / 0.050851 | 0.649408 / 0.005348 / 0.345245 | 0.621729 / 0.006239 / 0.372032 | 0.623374 / 0.006184 / 0.370443 |
| 2°/15° | 0.986648 / 0.000062 / 0.013290 | 0.325438 / 0.015546 / 0.659015 | 0.081682 / 0.042411 / 0.875907 | 0.083440 / 0.042032 / 0.874527 |
| 10°/45° | 0.003837 / 0.586317 / 0.409846 | 0.000828 / 0.602164 / 0.397008 | 0.000769 / 0.602592 / 0.396638 | 0.000773 / 0.602567 / 0.396660 |

关键判断：

```text
p4/h7.5 与 p5/h10 处于同一响应分支
=> 粗 p4/h10 在低掠射区欠分辨
```

## 其他关键结果

### Hybrid same-p

```text
Hybrid p5 vs Full3D p5, 12 selected points:
maximum R/T/A difference = 1.853e-5
```

说明 p4→p5 的大跳变不是 Hybrid p5 coupling 人为制造。

### Axial Route A/B

```text
maximum observable difference = 3.30e-7
```

远小于 p4→p5 的 O(1e-1) 跳变，排除 axial mapping 为主要根因。

### Double Floquet probes

```text
48/48 pass
maximum quasiperiodic residual = 1.898e-15
maximum slave-row residual     = 0
maximum C^H A C action error   = 1.517e-16
```

基础 x/y/corner Floquet 相位与高阶 orientation 不是大分支问题的原因。

### Hybrid formal map

```text
Hybrid p4: 39 pass / 41 fail
Hybrid p5: 10 pass / 2 fail among 12
Hybrid p6: 9 pass / 3 fail among 12
```

### p6 near-degenerate block failure

```text
blocks [114,115] and [116,117]
near-coincident beta
cross-block biorthogonality row sum = 1.7766e-6 > 1e-6 Gate
```

## 本轮发现的问题

1. Task001 选定的 p4 LF 在全角域欠分辨，不能继续作为统一 LF；
2. Hybrid p4 全角域 formal pass 率过低；
3. Hybrid p6 在 45° 发生 near-degenerate block split；
4. Hybrid mode-set 随方位强交换，不能把每个独立排序后的 mode index 当成连续物理身份；
5. 当前尺度下 Hybrid p4 并没有稳定速度优势。

## 采用的解决方法

选择 Route 4：

```text
暂停 Hybrid production
转向 Full3D static fidelity hierarchy
```

Hybrid 保留为研究代码和 same-p 诊断，不进入正式 Task002 数据生产。

## 主要证据

- `surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/outcomes/m2_solver_domain_qualification.md`
- `benchmarks/cases/114_task002_solver_domain_robustness/records/`

---

# 第七轮：Task002 M2C Full3D 层级资格化与单保真决策

## 本轮运行模型与结果

### Full3D p5 中心几何 80-angle map

```text
8 grazing × 10 azimuth = 80 points
80/80 completed
80/80 numerical Gates pass
new-point wall = 61.55–85.27 s
maximum RSS ≈ 4.42 GB
zero swap
```

### p4→p5 相关性

| aggregate | Spearman correlation |
|---|---:|
| R_total | 0.98174 |
| T_total | 0.98167 |
| A_balance | 0.74587 |
| A_volume | 0.74587 |

### 几何灵敏度一致性代表点

```text
0.5°/0°   LF/HF sensitivity cosine = 0.68425
2°/15°    LF/HF sensitivity cosine = 0.82875
```

### p4/h7.5 资源对比

```text
Full3D p4/h7.5 wall_max > Full3D p5/h10 wall_max
Full3D p4/h7.5 RSS_max  > Full3D p5/h10 RSS_max
```

## 本轮发现的问题

1. p4 的 R/T 排序相关性虽高，但吸收和 h/w 灵敏度关系不够稳定；
2. p4/h7.5 既不是便宜 LF，也不是最终 truth；
3. 强行做 p4→p5 多保真，可能不如直接训练 p5 单保真；
4. p5/h10 仍不是 continuum truth，只是当前可承受的 best-available operational HF。

## 采用的解决方法

正式拒绝 p4→p5 多保真生产路线，冻结为：

```text
production = Full3D static uniform N1curl p5/h10 single fidelity
p4/h10     = diagnostic only
p4/h7.5    = discretization audit only
Hybrid     = hard quarantined from production
```

并要求未来反演协方差中保留 discretization/model-discrepancy 项。

---

# 第八轮：Task002 M3R 生产合同、数据结构与采样设计冻结

## 本轮实现与 smoke 结果

| 项目 | 结果 |
|---|---|
| production model | Full3D static uniform N1curl p5/h10 |
| runtime topology smoke | 5/5 pass |
| actual global DoFs | 101,815（Ny=3 旧身份） |
| actual element | Basix N1E hexahedron degree 5 |
| planned-vs-actual mesh/tags/Floquet/DoF | pass |
| observable re-extraction | 206 existing raw artifacts pass |

## Observable v3

```text
n = 0
m = -7,-6,-5,-4,-3,-2,-1,0,+1,+2,+3
ports = reflection / transmission
components = outgoing S / outgoing P
```

在当前 order sign convention 下，已观测的传播 union 为 `m=-7..0`；`+1..+3` 保留为稳定 structural-null axes，而不是宣称它们已被证明传播。

## 冻结采样设计

| split | point count | seed |
|---|---:|---:|
| training | 96 | 20260729 |
| frozen validation | 16 | 20260730 |
| candidate pool | 4096 | 20260731 |
| discretization audit | 8 | deterministic |

训练、验证、候选和 audit 的 exact tuple intersection 均为空。

## 本轮发现的问题

1. 旧 campaign 不是完全 resume-safe；
2. production run 尚未强制绑定冻结设计；
3. 每个样本会写完整 VTU/PVD，112 点 campaign 的磁盘与 I/O 风险很高；
4. `n!=0` 泄漏只记录但未进入正式 Gate；
5. 正式数据集适配器和 exact-design checker 还未完成。

## 采用的解决方法

进入 M4P：

- design-bound campaign；
- 原子 manifest；
- attempt history；
- stale running/reserved 恢复；
- first-failure stop；
- compact surrogate output；
- `n!=0` leakage Gate；
- formal-record → production-sample adapter；
- exact-design dataset checker。

---

# 第九轮：Task002 M4P 与 Case117 第一次正式批量数据生成

## M4P 工程结果

| 工程项目 | 结果 |
|---|---|
| campaign v3 | design-bound、atomic、resume-safe |
| first-failure stop | 已实现 |
| ordinary vs compact A/B | 2/2 pass |
| aggregate differences | 最多约 `1.07e-12` |
| mother-response numeric difference | 最多约 `4.99e-13` |
| ordinary payload | 约 14.4 MB/sample |
| compact payload | 约 0.62–0.66 MB/sample |
| field VTU/PVD/BP in compact | 不写 |

## 第一次正式 campaign 结果

```text
16-point domain-corner canary = 16/16 pass
training measured_pass        = 56
training failed               = 1
training not_run              = 39
frozen validation             = 0
```

57 次 PDE：

```text
all direct solve completed
all zero swap
all cleanup complete
wall = 58.51–80.82 s
peak RSS = 4.19–4.33 GB
```

## 第一个失败点

```text
training design index = 40
h = 116.446369998157 nm
w = 17.513626368716 nm
grazing = 4.538499870338°
azimuth = 54.420819282532°
```

通过项：

```text
true residual         = 2.0915e-11
energy closure        = -1.3267e-12
runtime topology      = pass
fixed/raw ledger      = pass
compact identity      = pass
zero swap / cleanup   = pass
```

失败项：

```text
n!=0 reflection power   = 1.2728e-7
n!=0 transmission power = 1.1040e-6
n!=0 total power        = 1.2312e-6
n!=0 max amplitude      = 1.0147e-3
```

主导通道：

```text
bottom (m=0, n=-3, outgoing S)
power = 1.1036e-6
```

## 本轮发现的问题

几何和材料沿 y 完全均匀，连续解应保持单一 Bloch harmonic；出现明显 `n=-3` 能量说明 Ny=3 离散模型尚未资格化。

## 采用的解决方法

- 按合同立即停止，未跳过 index 40；
- 原 56 个 pass 保留但不急于组成 dataset；
- 建立 Case118 M4D：角度峰值、Ny convergence、surface quadrature、auxiliary/direct projection 和 trace Gram。

---

# 第十轮：Task002 M4D / Case118 y 向离散 alias 根因诊断

## 本轮运行矩阵

| 诊断 | 运行量 |
|---|---:|
| failed geometry azimuth 50–58° stencil | 14 点 |
| center geometry same azimuth stencil | 14 点 |
| Ny convergence | Ny=3/4/5/6 |
| surface quadrature | q=auto(21)/31/39/47 |
| independent boundary projection | q=63 |
| total new PDE | 35 |

所有 35 个 PDE 均：

```text
direct solve complete
zero swap
cleanup complete
```

## 角度窄峰

| geometry | azimuth | `2ky-3Gy` | n!=0 power | max amp |
|---|---:|---:|---:|---:|
| failed | 54.25° | `-9.04e-4` | `1.108e-6` | `1.242e-3` |
| failed | 54.50° | `1.45e-3` | `8.907e-7` | `8.271e-4` |
| center | 54.25° | `-9.04e-4` | `1.104e-6` | `1.244e-3` |
| center | 54.50° | `1.45e-3` | `8.887e-7` | `8.271e-4` |

峰位和峰高几乎与 h/w 无关，说明是角度与离散 trace 结构主导。

## Ny 收敛

| Ny | n!=0 power | max amp | R | T | A | bottom-S n0/n-3 overlap | Gram cond | PSS |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | `1.2312e-6` | `1.0147e-3` | 0.00650900 | 0.29609606 | 0.69739494 | 0.3630 | 2.1398 | 4.16 GB |
| 4 | `3.2783e-25` | `2.3532e-13` | 0.00644595 | 0.29623235 | 0.69732170 | `2.68e-16` | 1.0000 | 5.82 GB |
| 5 | `1.1317e-24` | `1.6618e-13` | 0.00644227 | 0.29624034 | 0.69731739 | `1.46e-16` | 1.0000 | 7.87 GB |
| 6 | `5.8333e-25` | `1.8991e-13` | 0.00644188 | 0.29624118 | 0.69731693 | `1.13e-16` | 1.0000 | 10.60 GB |

Ny=4 相对 Ny=6：

```text
|ΔR| = 4.07e-6
|ΔT| = 8.83e-6
```

Demodulated bottom-port `n=-3` Fourier energy fraction：

```text
Ny=3: 3.10e-6
Ny=4: 4.88e-26
```

## Surface quadrature

```text
q=21,31,39,47
n!=0 power in all four runs = 1.2312320314e-6
```

结果完全不变，排除 surface quadrature 不足。

## 本轮根因定案

正式模型有：

```text
period_y = 25 nm
Ny = 3
```

失败角附近满足：

```text
2*ky ≈ 3*Gy
```

于是连续理论上不同的 `n=0` 和 `n=-3` 在 Ny=3 trace space 中形成近 alias pair。实际 trace overlap O(1) 直接确认该机制。

```text
root cause = Ny3 mesh-induced discrete Bragg / trace alias
fix        = Ny4 production trace resolution
relax Gate = forbidden and unnecessary
```

## 本轮又发现的第二个问题

独立 q63 projection：

```text
outgoing S auxiliary/direct difference <= 7.7e-14
outgoing P auxiliary/direct difference = O(1e-3)
```

代码审阅发现该 independent diagnostic：

- 分子使用完整 `E_x,E_y,E_z` 与完整 P mode；
- 分母却使用 `electric_tangential_norm_sq`。

DtN port 的正确合同是切向 trace：

```text
E_t = (E_x,E_y)
e_t = (e_x,e_y)
```

S 模式 `e_z=0`，错误被掩盖；P 模式 `e_z!=0`，于是产生假 discrepancy。

## 采用的解决方法

Review V7 批准：

1. 将独立 mode projection 改为纯切向投影；
2. 在 Ny3/Ny4 上重新验证 outgoing S/P；
3. 正式生产网格改为 `(Nx,Ny,Nz)=(6,4,14)`；
4. 建立新的 model/route/schema/clean SHA；
5. Case117 Ny3 永久作为 controlled-stop evidence；
6. Ny3 的 56 个 pass 不得混入 Ny4 数据集。

## 主要证据

- `surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/outcomes/m4_y_alias_diagnosis.md`
- `benchmarks/cases/118_task002_y_alias_qualification/records/`

---

# 第十一轮：Review V7 已批准、尚未执行的 M4E

本轮尚未运行正式生产模型，以下是已批准的执行顺序。

## 待建立的新生产身份

```text
model_id       = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route   = full3d_static_uniform_n1curl_p5_h10_ny4
axis counts    = (6,4,14)
element        = uniform N1curl p5
backend        = assembly-time static condensation
observable     = task002.fixed-n0-orders.v3
output profile = compact_surrogate_record
```

## M4E preflight

### A. 修正切向投影

要求所有被检查的：

```text
top / bottom
S / P
n=0 / n=-3
```

满足：

```text
|a_auxiliary - a_direct_tangential| <= 1e-10
```

### B. 新 Ny4 clean SHA 与 design rebind

原四元组点表保持不变：

```text
training = 96
validation = 16
candidate = 4096
audit = 8
```

只更新 source/model/route/topology/schema identity。

### C. Enhanced canary

```text
16 domain corners
+ original failed index 40
+ center geometry at 54.25°, 54.50°, 54.75°
```

### D. Canary 通过后

从头生成：

```text
96 Ny4 training
16 Ny4 frozen validation
Ny4-only compact dataset
independent exact-design checker
```

遇到第一个未解释 failure 仍然必须停止。

---

# 累计结论：哪些早期判断被保留，哪些被推翻

## 仍然成立的结论

1. 高度与宽度在合适的 S 照明组合下局部可辨识；
2. P 照明物理上可解，Full3D direct 路线有效；
3. F1 reciprocal trace 坐标/degree/quadrature 问题已经修正；
4. 双 Floquet 基本 x/y/corner 约束实现通过高阶实际 probe；
5. Full3D p5/h10 是当前本地资源下可用的 best-available operational HF；
6. production campaign、compact output、runtime topology 和 exact-design checker 已基本建立；
7. Ny=3 的 `n=-3` 泄漏是离散 Bragg/trace alias；Ny=4 可消除。

## 被后续证据推翻或降级的结论

| 早期判断 | 当前修正后的结论 |
|---|---|
| Hybrid p4 可作为全角域 LF | 只在 Task001 局部条件下有效；全角域欠分辨且 formal pass 率低 |
| Hybrid p6 是可靠统一 HF | same-p 局部可用，但存在 near-degenerate block 与连续 mode identity 问题；不用于 production |
| p5-trace/p6-interior | 历史模型实际是 uniform N1curl p6 |
| p4→p5 多保真值得做 | 吸收和 h/w 灵敏度不够一致；改为 p5 单保真 |
| Ny=3 足够，因为几何沿 y 均匀 | 错误；Ny=3 在 `2ky≈3Gy` 出现离散 alias，正式改 Ny=4 |
| outgoing-P auxiliary/direct discrepancy 表示 auxiliary 错 | 当前证据显示是 independent full-vector projection 与 tangential denominator 合同不一致 |
| 56 个 Ny3 pass 可继续用于训练 | 不可；Ny3 与 Ny4 是不同离散模型，Ny3 只保留为诊断证据 |

---

# 当前真正完成到哪里

```text
Task001:
    S-polarized scope closed
    local identifiability established
    P-Hybrid deferred

Task002 solver qualification:
    completed through Case118

Task002 production data:
    Ny3 campaign controlled-stopped
    Ny4 production data not yet generated

surrogate model:
    not trained

angle optimization:
    not run

formal inversion:
    not started
```

下一真正里程碑是：

> 在新的 Ny4 production identity 下完成 96 个 training 和 16 个 frozen-validation Full3D p5 样本，并形成可由独立 checker 完整重建的 compact dataset。

完成该里程碑后，项目才正式从“前向求解器与数据生产资格化”转入“代理模型构建”。
