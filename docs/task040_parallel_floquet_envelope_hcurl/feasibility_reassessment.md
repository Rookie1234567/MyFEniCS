# Floquet-envelope H(curl) 可行性再评估：高风险、小投入、严格止损

## 0. 结论

```text
method_family_exists                         = yes
project_specific_feasibility                 = not established
recommended_role                             = high-risk parallel feasibility probe
recommended_role_as_main_0p7nm_route         = no
heavy_run_before_tiny_gates                  = forbidden
local-carrier production development_now     = forbidden
merge_approval                               = no
```

本分支不能被解释为“已经找到 0.7 nm 的解决方案”。准确定位是：

> plane-wave / Trefftz / partition-of-unity enrichment 在波动问题和部分 Maxwell edge-element
> 研究中有先例，但尚无仓库内证据证明它能在本项目的三维、complex-lossy、双 Floquet、
> Fourier-DtN、高阶 Nedelec 和任意非可分材料条件下，同时保持精度、条件数、总自由度和
> 内存优势。

因此本路线只允许通过三个很小的判别实验决定是否继续，不与 Task040 Review V6 的
full-interface / moving-PML / adaptive Schwarz 主线竞争资源。

---

## 1. 已知文献能够证明什么

已知方法族包括：

```text
partition-of-unity finite elements with plane-wave enrichment
plane-wave edge elements for Maxwell
Trefftz discontinuous Galerkin for time-harmonic Maxwell
Nedelec FE in complex region coupled to plane waves in homogeneous exterior
```

这些工作证明“把波动相位写入近似空间”不是凭空构造，也说明在合适问题中，一个单元可以跨越
多个波长。

但现有证据常有下列边界：

```text
2D or simplified geometry
homogeneous or piecewise-homogeneous coefficients
DG rather than conforming high-order Nedelec
integration-method study rather than a complete scattering solve
plane waves used only in homogeneous exterior, not arbitrary 3D volume
small carrier sets and limited conditioning studies
```

因此文献先例只能支持 tiny implementation probe，不能支持 5 nm 或 0.7 nm heavy campaign。

---

## 2. 与 Task035e h/p 自适应的关系

用户对 h/p 自适应的判断成立。Task035e 已证明：

```text
true local-h / local-p capability                  = pass
reference certification                            = pass
automatic reference-blind 59-goal hp cycle         = incomplete
accepted adaptive candidate                        = none
cellwise quantitative predictor                    = controlled negative
direct selective-trace lane                        = closed controlled negative
```

关键数值包括：

```text
four-cell selected-p actual:
    19/59 factor-two-or-neutral
    25/59 opposite sign

single-cell p4->p5 actual:
    0/59 factor-two-or-neutral
    30/59 opposite sign
```

这说明对于当前规则周期结构和多目标输出，局部 h/p 可以改变解、也可以节省局部未知量，但
自动选择“哪里升 p、哪里细化 h”没有形成可靠、reference-blind、全目标一致的生产策略。

Floquet-envelope 与 h/p 自适应不是同一件事：

```text
h/p adaptivity:
    仍用 polynomial Nedelec space
    通过改变 h 和 p 解析快速波相位

carrier enrichment:
    改变 trial space
    把一部分已知快速相位写入 basis
```

但二者共享同一个风险：如果 enriched direction / carrier 选择不可靠，未知量和条件数会增加，
而完整物理输出不一定改善。因此本分支禁止一开始实现复杂的 carrier adaptivity controller。

---

## 3. 对本项目的主要失败风险

### 3.1 carrier 数量膨胀

任意三维材料可把一个入射方向耦合到很多传播和 evanescent 方向。若必须为大量方向复制完整
三维 envelope space，则：

```math
N_total approximately N_carrier * N_envelope
```

可能比普通 FEM 更大。

### 3.2 envelope 未必缓变

几何边缘、薄层、材料突变、近截止场和强 evanescent 场仍可能在 envelope 中产生短尺度。
若 matched-accuracy envelope mesh 只能比普通网格粗很少，carrier 乘数会抵消全部收益。

### 3.3 高振荡积分

跨 carrier block 包含：

```math
exp(i*(kappa_p-conj(kappa_q))*x)
```

粗网格并不自动意味着低装配成本；可能需要 phase-aware quadrature 或半解析 moments。

### 3.4 条件数和近线性相关

方向接近的 carriers 会产生近相关 basis。增加 carrier 数可能降低近似误差，却快速恶化矩阵
条件数和 Krylov 收敛。

### 3.5 H(curl) conformity

全局 carrier 乘以一个完整 Nedelec space容易保持 conformity；局部 carrier active set则必须
在共享 tangential DoF 的全局 support 上一致定义。element-by-element独立选 carrier 会破坏
切向连续性。

### 3.6 DtN 与后处理闭环

即使 volume representation成立，仍要证明：

```text
physical DtN action exact
all diffraction orders recoverable
E/H reconstruction exact
R/T/A and complex channel amplitudes match authority
```

carrier coefficient本身不能直接当作 diffraction amplitude。

---

## 4. 三个严格 go/no-go 实验

## E1：单 carrier manufactured identity

用途只验证公式和实现，不评价规模收益。

```text
homogeneous periodic box
one analytic plane wave
one carrier exactly equal to wavevector
coarse Nedelec envelope
```

Gate：

```text
matrix action relative error <=1e-10
solution relative error      <=1e-9
true residual                <=1e-9
Floquet phase applied once   = pass
```

E1失败即停止本分支。

## E2：三个已知衍射方向的小周期结构

比较：

```text
ordinary Nedelec FEM
one-carrier envelope
3/5/8-carrier envelope
```

必须使用完整重构场比较：

```text
complex E/H samples
all propagating diffraction amplitudes
R/T/A/A_volume
true residual
```

minimum signal：

```text
all authority observables pass
and total active unknowns <= ordinary matched-accuracy unknowns / 2
and process memory <= ordinary matched-accuracy memory
and carrier Gram condition <=1e10
```

strong signal：

```text
total active unknowns <= ordinary matched-accuracy unknowns / 4
and wall time or peak memory improves >=2x
```

E2达不到 minimum signal即停止；不得进入 C2-16/C2-32 或 local carriers。

## E3：固定规则三维 grating

只有 E2 strong signal才运行。使用规则但真正三维、不可用单一前后向波表示的结构。

只允许：

```text
C0
C1
C2-16
conditional C2-32
```

E3 minimum signal：

```text
matched diffraction/channel/field tolerances pass
unknown reduction >=4x
no dense all-carrier block materialization
condition <=1e10 or robust iterative evidence
```

若 C2-16无信号，禁止 C2-32；若 C2-32仍无 >=4x reduction，global carrier route关闭。

---

## 5. 暂不实施的内容

在 E1/E2/E3 通过之前，禁止：

```text
0.7 nm PDE
5 nm p6/h4 formal
local adaptive carrier controller
all external channels as volume carriers
carrier x full-volume MatNest at large scale
new hp/carrier DWR campaign
large MPI or memory study
ordinary solver integration
```

当前已提交的 `floquet_envelope_hcurl.py` 只保留为参考代数和 UFL helper，不代表 production
architecture。

---

## 6. 与主线的资源优先级

优先级明确为：

```text
Priority 1:
    Task040 Review V6 full-interface / moving-PML / adaptive Schwarz

Priority 2:
    matrix-free H(curl) and streaming DtN infrastructure

Priority 3:
    本分支 E1/E2 tiny feasibility

Priority 4:
    E3 and local carriers, only after strong signal
```

原因是主线不改变离散物理，风险较低；carrier enrichment同时改变 trial space、assembly、solver
和后处理，验证成本高得多。

---

## 7. 当前正式状态

```text
classification = KNOWN_METHOD_FAMILY_BUT_PROJECT_FEASIBILITY_UNPROVEN
confidence      = low_to_moderate_for_tiny_regular_cases
confidence      = low_for_full_3d_lossy_floquet_dtn
confidence      = very_low_for_arbitrary_3d_0p7nm_without_E2_E3
next_action     = E1 then E2 only
```
