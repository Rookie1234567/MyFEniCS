# REVIEW REPORT V1：Task032 Hybrid FEM–Modal 直接法及 0.7 nm 可扩展性审查

## 0. 审查身份与最终判断

```text
review = Task032 review_report_v1
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
base = Task031 merged master dae03170b0cdd87f2d72769aea7ce04e32acce2b
review_status = changes_required_before_selective_merge

Task032_13p5nm_h5_h3_numerics = PASS
Task032_hybrid_physical_equivalence = PASS_WITH_SCOPE_QUALIFICATION
Task032_modal_truncation = PASS_FOR_CURRENT_SINGLE_POINT
Task032_direct_memory = ENGINEERING_POSITIVE_BUT_H2_NOT_UNLOCKED
Task032_parameter_smoke = INTERFACE/API_PASS_ONLY
Task032_current_code_for_0p7nm = NOT_RESOURCE_FEASIBLE
Task032_architecture_for_0p7nm = PROMISING_AND_WORTH_CONTINUING
ordinary_default_changed = false
h2_run = correctly_not_run_by_gate
formal_heavy_rerun_required = no
master_merge = blocked_by_documentation_scalability_and_selective_merge_closeout
```

审查结论必须分成两层理解：

1. **Task032 已经证明 Hybrid FEM–Modal 域分解在当前 13.5 nm、规则结构、h5/h3 离散上是正确的。** 中间 100 nm 三维体网格可以由截面模式替代，Hybrid 与同网格 full-3D 的 R/T/A、界面场、选定平面场、体吸收和能量闭合均通过任务 Gate。
2. **Task032 当前代码并不能直接扩展到 0.7 nm。** 当前实现仍依赖局部三维 MUMPS 直接因子、显式保存大量左右模态、复制的稠密 `M x M`/`2M x 2M` 模态块，以及 `N_local x (2M+1)` 的全量 dense multi-RHS。它们在 0.7 nm 的模式数和局部网格数下会重新产生 TB 乃至多 TB 级存储。

因此最准确的最终身份是：

```text
Task032 = hybrid_direct_engineering_success_at_13p5nm
0.7 nm verdict = architecture promising, current implementation not scalable enough
```

本轮不要求冒险运行 h2，也不要求在 Task032 内启动 0.7 nm 求解。合并前要求 Codex 完成表格化 summary、0.7 nm 可扩展性报告、工作规则同步和选择性合并清单。

---

# 1. 审查范围

本轮审查覆盖：

```text
- Task032 task.md、理论笔记、response_v1、全部 outcomes；
- Case080 config、expected gates、正式 h5/h3/M120/M160 records；
- 六条独立 direct lifecycle 内存记录和 h2 预测；
- QEP、Floquet reduction、左右模、分类、tracking；
- stable two-port propagation；
- matched trace projection 和接口符号；
- bottom/top local FEM + external Fourier-DtN；
- augmented direct；
- fast / memory-minimal Modal-Schur direct；
- E/H、吸收和中间截面重构；
- 角度/S-P smoke；
- serial/MPI2/MPI4 tests 和 302/302 checker；
- 当前实现从 13.5 nm 向 0.7 nm 扩展时的内存和算法复杂度。
```

并结合项目长期目标审查：

```text
最终用途 = 掠入射光栅结构参数反演
目标波长 = 0.7 nm
预计服务器内存 = 1–2 TB
当前阶段 = 13.5 nm 固定 Si、规则结构、1–10°、S/P
```

---

# 2. Task032 已经真正证明了什么

## 2.1 分阶段成果表

| 阶段 | 实现内容 | 主要证据 | 审查结论 |
|---|---|---|---|
| Phase 0 | 新目录、Git、环境、旧功能 smoke | 新目录和 remote 记录；旧目录只读 | 通过 |
| Phase 1 | h5/h3 full-3D reference 和 E/H 选面 | clean h5/h3 direct records | 通过 |
| Phase 2 | 分布式 mixed H(curl)/H1 二次 beta 本征问题 | SLEPc PEP/TOAR；解析 beta 对照 | 通过，仍需物理离散收敛限定 |
| Phase 3 | Poynting 分类、显式 adjoint QEP、双正交、tracking | clean modes record | 通过 |
| Phase 4 | 无 growing inverse 的双向 two-port 传播 | composition/passivity/reciprocity | 通过 |
| Phase 5 | 匹配 Nédélec 接口迹、左右模投影和法向约定 | clean trace record | 通过 |
| Phase 6 | bottom/top local FEM + real QEP + augmented direct | residual/interface traction | 通过 |
| Phase 7 | physical E/H、吸收和选面重构 | h5/h3 M160 field evidence | 通过 |
| Phase 8 | fast 与 memory-minimal Modal-Schur | augmented/Schur 等价 | 通过 |
| Phase 9 | M20–M160 漏斗、角度/S-P smoke | M120→160 strong；30/30 smoke | 单点截断通过；参数仅 smoke |
| Phase 10 | 六路径 simultaneous RSS 和 h2 Gate | h3 3.224 GiB；h2 not-run | 决策通过 |

## 2.2 主数值结果

| 指标 | h5 / M160 | h3 / M160 | Gate / 解释 |
|---|---:|---:|---|
| Hybrid true residual | `2.5455e-12` | `2.6036e-12` | 通过 |
| R | `0.0890210691064` | `0.0046128199040` | official |
| T | `0.4425867427429` | `0.5836509402052` | official |
| A | `0.4683921881508` | `0.4117362398908` | volume/balance 闭合 |
| Hybrid–full3D max `|ΔR/T/A|` | 约 `2.07e-6` | `2.63e-6` | `<1e-5`，通过 |
| sampled interface `E_t` error | `2.46e-7` | `2.50e-8` | 通过 |
| sampled interface `H_t` error | `7.42e-3` | `4.82e-4` | 通过；不是机器精度 |
| selected-plane max E error | `3.20e-4` | `9.96e-5` | 通过 |
| selected-plane max H error | `9.61e-4` | `7.80e-4` | 通过 |
| volume closure | `1.73e-11` | `3.27e-12` | 通过 |

这组结果足以支持：

> 在相同 x/y/z 离散和相同物理定义下，当前中间 z 不变区可以用截面模式替代，而不会破坏主要物理输出。

## 2.3 模态截断

| 比较 | h5 | h3 | 结论 |
|---|---:|---:|---|
| M20→M40 max total delta | `2.25e-5` | 未作为正式终点 | 早期 M6/M20 平台不可信 |
| M120→M160 max `|ΔR/T/A|` | `6.24e-14` | `1.22e-14` | strong pass |
| M120→M160 significant complex amplitude relative delta | `1.48e-10` | `1.33e-10` | strong pass |
| 正式模式数 | 160 / direction | 160 / direction | 只资格化当前主点 |

Codex 正确保留了 M20→M40 的负证据，没有用 M6 的表面稳定代替宽漏斗。

## 2.4 Modal-Schur 正确性

Task032 形成：

$$
S_m
=
H_m
-
D_bA_b^{-1}C_b
-
D_tA_t^{-1}C_t.
$$

h5/h3 M160 中：

```text
augmented direct
vs
Modal-Schur direct
```

在 modal coefficients、bottom/top local fields、interface projection、R/T/A 和 full residual 上均低于 `1e-9` 差异，并且只形成 `320 x 320` modal Schur，没有形成 `N_interface x N_interface` 稠密矩阵。该代数实现可以接受。

---

# 3. 不能由 Task032 推出的结论

## 3.1 尚未证明连续物理网格收敛

full-3D h5 与 h3 的 R/T/A 差异很大。Task032 当前证明的是：

```text
Hybrid(h5) ≈ full3D(h5)
Hybrid(h3) ≈ full3D(h3)
```

不是：

```text
h5 ≈ h3 ≈ continuum solution
```

Phase 2 homogeneous-air beta 误差为：

| 网格 | beta 相对解析误差 |
|---|---:|
| h5 | 29.53% |
| h3 | 5.59% |
| h2 | 1.13% |
| h1.5 | 0.455% |

因此 Task032 的同网格一致性非常重要，但它不能替代后续 h/p 离散收敛。0.7 nm 路线必须同时控制：

```text
local 3D FEM discretization error
+ cross-section eigenmode discretization error
+ modal truncation error
```

## 3.2 1–10° 与 S/P 尚未物理资格化

30/30 参数 smoke 使用 M=4，证明：

```text
参数能进入代码
QEP 会重算
方向分类可运行
Hybrid algebra 可求解
R/T/A 输出有限
```

它不证明：

```text
所有角度的 M 截断收敛
所有角度与 full-3D 一致
P 偏振在 h3/h2 上 production-qualified
cutoff/临界角附近鲁棒
```

项目文档必须继续将其标成 `parameter_interface_smoke`，不能写成 `1–10° solver qualification`。

## 3.3 h2 没有实测

h2 预测：

| 预测方法 | 中心值 | 保守上界 | Task Gate |
|---|---:|---:|---|
| h5/h3 网格尺度 power law | 5.365 GiB | 6.170 GiB | fail |
| MUMPS factor payload | 11.647 GiB | 13.394 GiB | fail |

任务要求中心 `<=4 GiB`、上界 `<=5 GiB`。因此 h2 被锁定是正确的 fail-closed 工程决策。

不得写：

```text
Task032 h2 direct requires approximately 3 GiB
```

只能写：

```text
Task032 h2 was not run; two estimates disagree materially and both fail the launch Gate.
```

---

# 4. 内存结果审查

## 4.1 实测结果

| mesh / path | simultaneous worker RSS | cgroup current | total time | 结论 |
|---|---:|---:|---:|---|
| h5 augmented | 1.865 GiB | 1.584 GiB | 70.72 s | reference |
| h5 Schur fast | 1.755 GiB | 1.160 GiB | 63.01 s | positive |
| h5 Schur minimal | 1.698 GiB | 1.061 GiB | 60.91 s | positive |
| h3 augmented | 3.853 GiB | 3.215 GiB | 102.58 s | reference |
| h3 Schur fast | 3.998 GiB | 3.362 GiB | 111.97 s | negative |
| h3 Schur minimal | 3.224 GiB | 2.586 GiB | 99.69 s | best measured |

准确结论是：

> Modal-Schur 本身不保证省内存；只有顺序建立、使用并释放 bottom/top factor 的 memory-minimal 生命周期，在 h3 上取得 16.31% 的结构性下降。

## 4.2 峰值主因

h3 memory-minimal 的峰值发生在：

```text
bottom_schur_contribution / top_schur_contribution
```

而不是小型 modal Schur solve。当前 h3 每个 local system 约 34,238 rows，MUMPS factor 约 30M nnz、估算约 0.69–0.70 GiB；`[f,C]`/solution dense multi-RHS 也在 factor contribution 阶段占用显著存储。

因此当前主要瓶颈是：

```text
local sparse direct factor
+ all-mode dense multi-RHS
```

不是 `320 x 320` modal Schur 本身。

---

# 5. 0.7 nm 可行性：架构正确，但当前实现不可直接扩展

## 5.1 Hybrid 域分解能解决什么

当前完整域高度为 140 nm；Task032 local FEM 实际覆盖：

```text
bottom: -10 to 10 nm = 20 nm
top: 110 to 130 nm = 20 nm
total local 3D height = 40 nm
```

因此当前 Hybrid 将三维体积大约减少：

$$
\frac{140}{40}=3.5.
$$

若未来真正复杂区域只有 `0–10 nm` 和 `110–120 nm`，且外部均匀区域直接用端口模式截断，则 local 3D 总厚度可以降至 20 nm，对 140 nm 全域约为 7 倍体积降维。

这是很有价值的降维，但不能单独解决几十亿 DoF：均匀 `0.1 nm` 网格下，即使只保留 20–40 nm local 3D 区域，仍可能有数千万体单元和十亿级 p2 H(curl) DoF。

## 5.2 泛化二维周期截面的传播模数量

对真正二维周期中间截面，一个粗略的传播 reciprocal-order 数量级为：

$$
N_{\mathrm{order}}
\approx
\frac{\pi L_xL_y}{\lambda^2}.
$$

考虑两个极化，每个传播方向的模态下界数量级为：

$$
M_{\mathrm{prop}}
\approx
2\pi\frac{L_xL_y}{\lambda^2}.
$$

对 `Lx=50 nm, Ly=25 nm`：

| wavelength | generic 2D propagating orders（估算） | two-pol modes / direction（估算下界） |
|---:|---:|---:|
| 13.5 nm | 21.5 | 43 |
| 5 nm | 157 | 314 |
| 2 nm | 982 | 1,963 |
| 1 nm | 3,927 | 7,854 |
| 0.7 nm | 8,014 | 16,029 |

这些数字是几何/波数计数估算，不是 Task032 实测模式数；它们还没有包含为了界面近场所需的衰减模缓冲。

当前 13.5 nm 主点使用 `M=160`，约为传播下界的 3.7 倍。若机械保持该比例，0.7 nm 可能需要约 5.9 万个模式/方向。不能把这个比例视为预测，但它说明当前显式全模态实现面临的数量级风险。

## 5.3 当前代码中的显式模态存储壁垒

当前实现具有以下复杂度：

| 对象 | 当前复杂度 | h3 / M160 | 0.7 nm 风险 |
|---|---|---:|---|
| right/left reduced/full eigenvectors | `O(N_xy M)` | 40.9 MB | 可能达到 TB 级 |
| biorthogonality matrix | `O(M²)`，且逐元素 MatMult | 160² | 不可扩展到万级 M |
| trace Gram / negative map | replicated `O(M²)` | 160² | 单 rank 内存/计算瓶颈 |
| modal constraint / Schur | replicated dense `(2M)²` | 320² | 万级 M 时几十至数百 GiB/矩阵 |
| bottom/top contribution | dense `2M x (2M+1)` | 小 | 与 Schur 同阶 |
| local multi-RHS | `O(N_local M)` | 321 RHS | 0.7 nm 时不可形成全量 dense RHS |
| modal owner | 全部 modal rows 在最后一个 rank | M=160 可接受 | 万级 M 严重负载/内存集中 |
| QEP | shift-invert + MUMPS，要求约 `2M` candidates | 320 candidates | 万级 eigenpairs 不可按当前方式直接求 |

以 `M=16,000` 的传播模下界举例：

| 对象 | 单份 complex128 存储估算 |
|---|---:|
| 一个 `(2M)x(2M)` dense matrix | 约 15.3 GiB |
| 当前四个同阶 dense arrays / rank | 约 61 GiB/rank |
| 若 MPI4 每 rank 复制 | 约 244 GiB 总量 |

若按当前 `M=160` 相对传播模的倍率外推至约 `M=59,500`，一个 `(2M)^2` dense matrix 已约 211 GiB，当前多份复制会超过 1–3 TiB。更严重的是 full eigenvector 和 `N_local x (2M+1)` multi-RHS，它们会先于小型 modal Schur 失控。

## 5.4 cross-section 和 local 3D 网格壁垒

h3 QEP full shape 约 2,053。若二维均匀网格从 3 nm 缩到 0.1 nm，面积型 DoF 粗略增长：

$$
\left(\frac{3}{0.1}\right)^2=900.
$$

对应 cross-section unknown 数可到约 185 万。当前 h3/M160 retained left/right reduced/full vectors 为 40.9 MB；按 DoF 和模式数同时机械缩放：

| 0.7 nm 假设 | 粗略 eigenvector payload |
|---|---:|
| M=16k | 约 3.35 TiB |
| M≈59.5k | 约 12.5 TiB |

这只是用当前对象布局做的工程外推，并非统计预测；它明确说明 current layout 不能用于 0.7 nm。

h3 每个 local block 约 34,238 unknowns。均匀缩到 0.1 nm，三维体积型 DoF 粗略乘以：

$$
\left(\frac{3}{0.1}\right)^3=27,000,
$$

即每个当前 20 nm local block 可能接近 9 亿未知量。直接 LU 明显不再是目标服务器上的合理主线。

## 5.5 最终可行性判定

| 问题 | 判定 |
|---|---|
| 中间 z 不变区用模态替代 3D 体网格是否正确？ | **是，Task032 h3 已证明** |
| 该思想是否值得作为 0.7 nm 主架构？ | **是，是必要降维之一** |
| 当前 augmented / dense Modal-Schur direct 能否直接扩到 0.7 nm？ | **不能** |
| 仅做 Task033 h/p 自适应是否足够？ | **不够，还需重构 modal core 和 local solver** |
| Task032 是否应因 h2 未运行而判失败？ | **否，工程成功但未达 strong-memory** |
| 是否可以现在直接开始 0.7 nm full run？ | **不可以** |

---

# 6. 当前规则结构隐藏的最大正机会：y 不变性

Case080 冻结几何：

```text
period_y = 25 nm
grating_width_y = 25 nm
phi = 0° primary point
```

因此当前规则结构的材料在 y 方向实际上不变。由此可以推断：

```text
当前 generic 2D x/y cross-section QEP
并不是该规则 benchmark 的最小数学表示。
```

若中间区域和接口几何均 y 不变，则不同 y Fourier harmonic sector 不耦合。对于主点，只有入射所在 sector 需要参与；横截面 eigenproblem 可以退化为 x 方向的一维全矢量/TE-TM block 问题，或按 y harmonic 分块独立求解。

一维周期 x 方向的传播 order 数量级约为：

$$
N_x\approx\frac{2L_x}{\lambda}.
$$

| wavelength | x harmonic count（估算） | two-pol count（估算） |
|---:|---:|---:|
| 13.5 nm | 7.4 | 15 |
| 5 nm | 20 | 40 |
| 2 nm | 50 | 100 |
| 1 nm | 100 | 200 |
| 0.7 nm | 143 | 286 |

即使增加衰减模缓冲，也更可能落在数百到低千级，而不是一万到六万级。

这是 Task032 后最应优先验证的方向。它不是为了修改当前通过结果，而是决定未来 0.7 nm 是否有真正可执行路线。

需要注意：

- 若未来中间区域真正为 `epsilon(x,y)`，则必须保留 generic 2D 模态路线；
- 若仅上下局部复杂区随 y 变化，它们会在接口上激发多个 y harmonic，但中间 operator 仍可按 harmonic sector 分块；
- 不能在未做接口系数能量审计前假设只有 n=0；必须从 modal coefficients 和 interface projection 中验证 active sectors。

---

# 7. 对当前规则结构，更彻底的降维路径

当前规则 benchmark 在 z 上本身也是分段不变：

```text
substrate
+ 0–120 nm patterned cross-section
+ air
```

因此对**当前规则结构**，理论上可以完全取消 bottom/top local 3D volume，改为：

```text
substrate Fourier modes
↔ patterned-layer eigenmodes
↔ air Fourier modes
```

在 z=0 和 z=120 直接做 E/H 模态匹配，并通过稳定 scattering matrix 传播。这是 pure modal / eigenmode expansion / Fourier-modal 路线。

它应成为下一阶段的重要对照：

| 路线 | 适用结构 | local 3D volume |
|---|---|---:|
| Task032 Hybrid | 允许上下复杂三维区 | 有 |
| Pure modal layered | 当前完全规则、分段 z 不变 | 0 |
| Future Hybrid | 仅 0–10 和 110–120 复杂 | 只保留真正复杂区 |

这条 pure-modal 路线不仅可显著减少内存，还能作为未来 Hybrid 接口和模态截断的独立 reference。

---

# 8. P0：重新整理 `outcomes/summary.md`

当前 summary 的技术内容丰富，但大量关键数字埋在长段落中，不利于用户数月后回顾，也不利于独立审查。

Codex 必须重写：

```text
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
```

不能只在末尾追加一张表。应改成“表格为主、解释为辅”的结构，至少包含下列独立表格：

| 必需表格 | 最低内容 |
|---|---|
| 最终状态与范围 | classification、review、h2、ordinary default、已验证参数 |
| Phase 0–10 实施矩阵 | planned / run / pass / fail / superseded / not_run |
| QEP 和 mode validation | beta error、residual、biorthogonality、tracking |
| Hybrid/full3D 结果 | h5/h3 R/T/A、field、absorption、residual |
| modal truncation | M20/40/80/120/160 与终止 Gate |
| direct path memory/time | augmented / fast / minimal，baseline、降幅、单位 |
| h2 decision | 两种预测、Gate、not_run |
| 参数 smoke | 角度、偏振、M、证明/不证明 |
| negative results | 根因、修复/停止、是否保留代码 |
| 0.7 nm 可扩展性 | measured / analytical estimate / unresolved |
| merge decision | merge / experimental / research_only / do_not_promote |
| 下一步 | 动机、Gate、停止条件 |

所有表格必须：

```text
- 标出单位；
- 标出 baseline 和分母；
- 区分 measured / derived / predicted / not_run；
- 给出证据文件或 record；
- 未运行项明确写 not_run；
- 不混用 historical peak 和 simultaneous RSS。
```

长叙述只用于解释根因和边界，不得替代结果表。

---

# 9. P0：将“表格优先 summary”写入长期工作规则

用户已明确要求以后每个 Task 采用同样的可回顾格式。Codex 在 `response_v1.md` 中必须同步更新：

```text
docs/repository_work_principles.md
README.md 的保护区
docs/README.md 的保护区
docs/task_retrospective_standard.md
src/test/test_24_repository_work_principles.py
src/test/test_26_documentation_contract.py 或新的通用 summary contract
```

建议加入的强制条款：

> 从 Task032 起，中型和大型算法、物理或性能任务的 `outcomes/summary.md` 必须以表格作为主要信息载体，至少包含最终状态/范围、实施或实验矩阵、关键数值结果、资源或性能结果、失败与未运行项、合并和下一步决策表。每张表必须标明单位、baseline、数据身份（measured/derived/predicted/not_run）和证据入口；叙述文字用于解释表格，不得替代表格。

测试不得只检查字符串存在。至少应验证 Task032 summary：

```text
- 存在不少于 8 张 Markdown 表；
- 存在状态、实施矩阵、数值、内存、h2、负结果、合并、下一步等表格；
- 同时出现 measured / predicted / not_run 口径；
- 关键 h3 3.224 GiB、h2 not_run、M160、302/302 可在对应章节定位；
- 规则在三个 protected files 中同步。
```

本规则从 Task032 起强制，不要求本轮重写 Task000–Task031 的全部历史 summary。

---

# 10. P0：新增 0.7 nm 可扩展性专门报告

Codex 必须新增：

```text
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/
    task032_0p7nm_scalability_assessment.md
```

至少包含以下表格：

1. 当前 13.5 nm 实测事实；
2. 0.7 nm 解析估算及假设；
3. generic `epsilon(x,y)` 与 y-invariant `epsilon(x)` 两种模式数情景；
4. 当前各对象的 `O(...)` 存储和计算复杂度；
5. local 3D volume / DoF 预算；
6. 1 TB 与 2 TB 可行性预算；
7. current code 中必须重构的模块；
8. pure-modal、Hybrid 和 fallback 路线比较；
9. 进入波长缩短前的硬 Gate。

建议增加一个不执行 PDE 的确定性脚本：

```text
benchmarks/run_task032_scalability_projection.py
```

输入：

```text
lambda
period_x / period_y
local thickness
mesh target
mode safety factor
MPI size
```

输出 JSON 只允许标记为：

```text
analytical_resource_projection
```

不得进入“数值 solver pass”统计。

---

# 11. P0：选择性合并清单

Task032 是大型 research branch。依据仓库原则，不能只写“整个分支 merge”。Codex 必须新增：

```text
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/
    selective_merge_manifest.csv
```

建议分类如下。

## 11.1 建议合并的验证基础设施

| 模块 | 决定 | 身份 |
|---|---|---|
| cross-section mixed spaces / QEP | merge | experimental validated infrastructure |
| cross-section Floquet reduction | merge | validated infrastructure |
| mode classification / adjoint QEP / tracking | merge | experimental infrastructure |
| stable two-sided propagation | merge | validated infrastructure |
| matched modal trace projection | merge | validated matched-interface infrastructure |
| hybrid local mesh / local DtN | merge | experimental hybrid infrastructure |
| augmented direct | merge as reference | not production 0.7 solver |
| Modal-Schur direct | merge as reference | current-scale experimental |
| field reconstruction / absorption | merge | validation infrastructure |
| Case080 / tests / theory / walkthrough | merge | evidence and documentation |

## 11.2 可保留但必须明确非 scalable production API

| 对象 | 状态 |
|---|---|
| last-rank modal ownership | current-scale reference only |
| replicated dense modal arrays | current-scale reference only |
| all-mode dense multi-RHS | current-scale direct reference only |
| MUMPS shift-invert PEP for all requested modes | current-scale only |
| direct local LU | Task032 reference, not 0.7 production |

它们可以为复现 Task032 留在代码库，但必须在 capability matrix、docstring 和使用文档中标为：

```text
experimental / not scalable to target wavelength without redesign
```

不得从 ordinary default 或未来 service API 自动选用。

## 11.3 不进入 Git/master 的内容

```text
- heavy fields / meshes / full eigenvectors；
- raw memory timelines；
- full matrices / factors；
- temporary PEP caches；
- Windows/Docker 临时日志；
- 未通过的 dirty records。
```

同时检查正式 JSON 大小。逐模态完整数组若使 lightweight record 失去“轻量”属性，应保留摘要、Gate、hash 和 artifact 指针，把详细 arrays 移入 ignored artifacts。

---

# 12. 下一步建议：调整原 Task033–Task035 顺序

原路线是：

```text
Task033 h/p adaptivity
→ Task034 iterative
→ Task035 wavelength continuation
```

根据 Task032 的新证据，建议先插入一个强制的 modal-scalability 阶段。否则即使 local 3D DoF 因 h/p 降低，显式模式和 dense Schur 仍会在 0.7 nm 爆炸。

## 推荐 Task033

```text
Task033：0.7 nm scalability gate, symmetry-aware modal reduction,
and pure-modal reference
```

### Lane A：当前规则结构的 pure-modal solver

实现：

```text
substrate Fourier modes
↔ patterned-layer eigenmodes
↔ air Fourier modes
```

不保留 local 3D volume；与 Task032 Hybrid/full3D 在 13.5 nm 对照。

### Lane B：y-invariant / harmonic-sector fast path

由于当前 `grating_width_y = period_y`：

```text
- 证明材料 y 不变；
- 将 generic 2D QEP 分解为 y harmonic sectors；
- 对主点验证 active sector；
- 比较 1D/sector solver 与 generic 2D QEP 的 beta、R/T/A 和场；
- 统计 mode-count 和内存下降。
```

### Lane C：modal activity audit

对 M160 记录新增：

```text
- modal coefficient energy/rank；
- y harmonic identity；
- propagation attenuation；
- interface coupling norm；
- dropped-mode a posteriori residual。
```

不得仅按 beta 距 target 选择所有 modes。

### Lane D：重构 scalable modal core

至少完成设计和 h5 原型：

```text
- modal rows distributed across ranks；
- dense M² arrays 不在各 rank 复制；
- block/streamed RHS，而不是一次 N_local x (2M+1)；
- matrix-free or distributed modal Schur apply；
- paired forward/backward basis，使 negative mapping 尽量为 permutation/block diagonal；
- mode vectors streamed/compressed，不同时保留 right/left full/reduced 四份；
- QEP spectrum slicing / block solve / continuation，而不是单 target 获取数万 eigenpairs。
```

### Lane E：波长资源投影

仅做经过验证的资源模型：

```text
13.5 → 5 → 2 → 1 → 0.7 nm
```

不要求立即求解 0.7 nm，但要明确：

```text
mode count
cross-section DoF
local 3D DoF
eigenvector bytes
projection bytes
modal core bytes
Krylov/vector bytes
1 TB / 2 TB margin
```

## Task034

在 Task033 明确 modal core 可扩展后，再做：

```text
local 3D robust h/p adaptivity
+ interface placement optimization
+ fixed matched trace or controlled mortar
```

特别应比较接口位置：

```text
current 10/110 nm
vs
closer to truly irregular zones
```

因为 0.7 nm 下保留 10 nm 规则缓冲相当于十多个波长，可能浪费大量 local 3D cells。接口向复杂区靠近会增加衰减模需求，因此需要“local volume vs modal count”的联合优化。

## Task035

针对最终 adaptive local blocks 构造：

```text
matrix-free local FEM
+ distributed modal core
+ interface Schur
+ outer flexible Krylov
```

local LU 只用于小 reference 或 coarse solve，不作为 0.7 nm 主线。

## Task036

最后才执行正式波长 continuation：

```text
13.5 → 5 → 2 → 1 → 0.7 nm
```

每一步更新材料色散、模式范围、网格和 solver profile，并在资源 Gate 失败时停止。

---

# 13. 若 generic Hybrid 路线最终不可行，可采用的替代或多保真方法

| 方向 | 适用场景 | 优点 | 风险/边界 |
|---|---|---|---|
| pure modal / EME | 分段 z 不变规则结构 | 无 3D volume，最省资源 | 模式数和接口矩阵仍需 scalable 实现 |
| RCWA / Fourier modal middle | 规则或分层横截面 | FFT/sector 结构强 | 高对比/曲面需收敛控制 |
| FEM ends + RCWA/EME middle | 局部复杂、长规则中段 | 与真实需求匹配 | 接口和模式截断需验证 |
| matrix-function / rational-Krylov propagation | 显式全 eigenbasis 太大 | 可避免存储全部 modes | 实现和误差估计较难 |
| envelope/phase-extracted high-order FEM | 高频但主传播方向明确 | 减少每波长网格数 | 多衍射级和反射下需严谨验证 |
| HDG/static condensation + matrix-free p-multigrid | local 3D 大规模 block | 降低 trace/volume存储 | 新离散和 PC 工作量较大 |
| DWBA / multislice | 弱散射、反演大量调用 | 极快，可作低保真模型 | 不能替代严格 Maxwell reference |
| multi-fidelity inversion | 大量参数反演 | 低保真筛选+Hybrid校正 | 需要模型误差和校准 |

若 Task033 证明 current regular geometry 的 y-sector / pure-modal fast path成立，应优先继续该路线，而不是直接转向近似模型。

---

# 14. Codex Response V1 要求

Codex 应在同一分支提交：

```text
docs/task032_hybrid_fem_modal_direct_baseline/response_v1.md
```

当前已有一个执行总结文件也叫 `response_v1.md`。为保持审查闭环，Codex 不得覆盖原文件；应将当前执行总结重命名或保留为：

```text
execution_response_v0.md
```

然后新增真正回应本 review 的：

```text
response_v1.md
```

如果不希望重命名历史文件，则新增：

```text
response_v1_review_followup.md
```

并在 Task README 和 docs/README 中明确两者身份。不能静默覆盖已有内容。

回应必须逐项关闭：

```text
P0-A summary table-first rewrite
P0-B repository-wide table-summary rule and tests
P0-C task032_0p7nm_scalability_assessment.md
P0-D deterministic scalability projection script/report
P0-E selective_merge_manifest.csv
P0-F compact-record size inventory
P0-G roadmap/development_progress/capability_matrix wording sync
```

## 14.1 文档必须统一的最终措辞

```text
Task032 at 13.5 nm = hybrid_direct_engineering_success
h2 = not_run_by_gate
current direct implementation at 0.7 nm = not resource feasible
Hybrid architecture = promising / retained
parameter 1–10° S/P = smoke only
ordinary default = unchanged
```

## 14.2 不要求的工作

```text
- 不重跑 h5/h3 formal physics；
- 不运行 h2；
- 不运行 0.7 nm；
- 不在本分支实现完整 Task033；
- 不改材料和物理模型；
- 不用放宽 Gate 制造通过。
```

## 14.3 最低验证

```text
Ruff / compileall
Task32 focused serial tests
MPI2/MPI4 selected tests
repository principles tests
documentation contracts
Case080 checker --no-write
JSON/CSV/Markdown table contract
git diff --check
tracked tree clean
```

---

# 15. 当前合并决定

```text
Task032 physical/numerical implementation = ACCEPTED
Task032 13.5 nm engineering classification = ACCEPTED
Task032 current 0.7 nm scalability claim = REJECTED
Task032 h2 not-run decision = ACCEPTED
selective merge = PROVISIONALLY RECOMMENDED AFTER RESPONSE V1
ordinary default = UNCHANGED
Task033 start = WAIT FOR REVIEW RESPONSE AND SELECTIVE MERGE
```

Task032 不是失败。它完成了非常关键的科学验证：把长 z 不变区从三维体离散中移除是正确的。它同样暴露了下一层真正问题：

```text
local 3D direct LU
+ explicit full modal basis
+ replicated dense modal core
```

仍不能支撑 0.7 nm。

下一步不应回到全域 3D FEM，也不应立即冒险缩波长；应先利用当前规则结构的 y 不变性和分层 z 不变性，把 pure-modal / sector-decomposed 路线和 scalable modal core 做出来，再进入 local h/p 与 hybrid iterative。
