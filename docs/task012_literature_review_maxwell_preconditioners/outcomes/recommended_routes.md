# 推荐路线

## 总体判断

本项目不缺 Krylov 外迭代，缺的是能处理以下结构的预条件器：

```text
complex indefinite H(curl) Maxwell
Nedelec FE 主块
Floquet x/y 周期约束
z 方向 Fourier-DtN auxiliary modal port
有损材料和体吸收
official R/T/A 对 residual 和 port modal amplitudes 敏感
```

下一步应把“Maxwell H(curl) 结构”和“周期光栅 Rayleigh/DtN 模态结构”叠加起来，而不是继续尝试普通 PETSc 预条件器。

## 路线 1：real-split AMS/HX block preconditioner

| 项目 | 内容 |
|---|---|
| 优先级 | 1 |
| 目标 | 绕开 complex hypre AMS 崩溃，用 real-valued AMS/HX 预条件 real block system |
| 外迭代 | FGMRES 或 GMRES，优先 FGMRES |
| 预条件器 | `blockdiag(B_AMS, B_AMS)` 起步，之后加入交叉项近似 |
| 本项目证据 | task011 real FE-only p=2 h=5，7 次迭代 true residual `4.024e-7` |
| 文献证据 | HX/AMS 是 H(curl) auxiliary-space 正统路线；time-harmonic Maxwell 文献存在 real/imag block form |
| 主要风险 | p=2 内存、MPC/DtN auxiliary 接入、high-order Pi/G 构造 |

建议矩阵形式：

```text
A = Ar + i Ai

real system:
    [ Ar  -Ai ] [xr] = [br]
    [ Ai   Ar ] [xi]   [bi]

minimal PC:
    P0^-1 = blockdiag(B^-1, B^-1)
    B ≈ curl-curl + tau mass 的 positive/shifted H(curl) AMS inverse
```

第一阶段不要试图一次处理全部 Stage 4。先证明 `P0` 能在小问题上明显降低 true residual，再讨论 DtN auxiliary block。

## 路线 2：Rayleigh/Floquet modal deflation

| 项目 | 内容 |
|---|---|
| 优先级 | 2 |
| 目标 | 用已有 DtN port modal basis 构造低维粗空间，消除全局传播慢模态 |
| 外迭代 | FGMRES/GMRES with deflation 或 coarse correction |
| 预条件器 | 可与 Route 1 叠加，也可先接 Jacobi 做 residual 曲线对比 |
| 本项目证据 | Stage 4 已有 top/bottom Rayleigh orders、official power 来自 modal amplitudes |
| 文献证据 | biperiodic Maxwell DtN 与 RCWA 都说明 Fourier/Rayleigh modes 是周期散射自然变量 |
| 主要风险 | 粗向量如何 lift 到 FE 空间；近截止 evanescent modes 是否纳入；coarse solve 稳定性 |

建议 coarse correction：

```text
Z = [lifted Rayleigh/Floquet modal fields]
E = Z^* A Z
M_defl(r) = Z E^-1 Z^* r
```

最小验证可以只取 propagating orders，甚至先只取 incident/reflected/transmitted 零阶模式，比较 residual 曲线。

## 路线 3：DtN-aware FE/aux block preconditioner

| 项目 | 内容 |
|---|---|
| 优先级 | 3 |
| 目标 | 利用 Stage 4 增广矩阵天然 block 结构，而不是普通 FieldSplit |
| 外迭代 | FGMRES |
| 预条件器 | FE block 用 AMS/HX；auxiliary modal block 用 exact small dense/diagonal DtN approximation |
| 本项目证据 | task010 已打通 A/P 双矩阵与 FE/aux block 识别，但 generic fieldsplit 不行 |
| 文献证据 | DtN/Fourier modal 边界在周期 Maxwell 中是自然截断；block preconditioner 文献支持 real/imag block |
| 主要风险 | Schur complement 近似设计不当会退化为 identity auxiliary block |

建议形式：

```text
[ A_FE   C ]
[ D    A_aux ]

P^-1 ≈ [ B_FE^-1        0       ]
       [ -S_aux^-1 D B  S_aux^-1 ]

S_aux ≈ A_aux - D B_FE^-1 C
```

最小版可先用 `S_aux ≈ A_aux`，因为 auxiliary 维数小，后续再加入低秩 Schur 修正。

## 路线 4：layered-background / RCWA-like approximate inverse

| 项目 | 内容 |
|---|---|
| 优先级 | 4 |
| 目标 | 用周期层状背景的 Fourier/modal 解作为近似逆或 coarse correction |
| 外迭代 | FGMRES right preconditioning |
| 预条件器 | FFT/Fourier harmonic in x/y + 1D transfer/scattering in z |
| 本项目证据 | 几何是周期光栅；已有 layered background notes 与 DtN modal machinery |
| 文献证据 | RCWA/Fourier modal 是周期层状 Maxwell 的经典高效方法 |
| 主要风险 | 高对比/有损材料/矩形 ridge 的 Fourier Gibbs 与 Li factorization；实现复杂 |

这条路线最有“科学发现”潜力，因为它不是把通用 PC 硬套到光栅，而是用光栅自己的半解析结构作为预条件器。但它不应先于 Route 1/2。

## 路线 5：matrix-free operator + physics PC

| 项目 | 内容 |
|---|---|
| 优先级 | 5 |
| 目标 | 在 PC 已有收敛信号后，降低 assembled A 的存储压力 |
| 外迭代 | FGMRES with MatShell / matrix-free action |
| 预条件器 | Route 1/2/3 的低阶或 modal PC |
| 本项目证据 | task011 FE-only action 与 assembled matvec 相对误差 `7.56e-16` |
| 主要风险 | MPC、DtN auxiliary 和 matrix-free MatShell 集成复杂 |

matrix-free 不单独作为求解路线，只作为内存优化层。

## 路线 6：BLR/H-matrix fallback

| 项目 | 内容 |
|---|---|
| 优先级 | fallback |
| 目标 | 在没有低内存 iterative candidate 前，保留可信 R/T/A 参考 |
| 本项目证据 | task010 BLR eps=1e-5 在 p=2 h=2 复现 direct R/T/A |
| 风险 | 仍是压缩因子化，内存下降有限，h=1.5 未解决 |

BLR 应作为“可出结果的应急路线”，不作为科研主线。

## 明确停止的路线

| 路线 | 停止原因 |
|---|---|
| Jacobi-Krylov 加迭代数 | true residual 仍在 `1e-1` 级别 |
| ASM/ILU/local LU 微调 | 本项目和文献都显示 high-frequency Maxwell 下无全局 coarse/physics 结构会停滞 |
| complex hypre AMS 直接上 Stage 4 | 最小 complex smoke 已崩溃 |
| generic BoomerAMG/GAMG | 不尊重 H(curl) de Rham 结构 |

## 推荐组合

| 阶段 | 组合 | 成功信号 |
|---|---|---|
| Task013 | FE-only/reduced Stage 4 real-split + real AMS/HX | true residual 明显优于 Jacobi，最好达到 `1e-6` |
| Task014 | Rayleigh/Floquet modal deflation + Task013 PC | 迭代数下降，R/T/A 与 direct/BLR 在 coarse case 一致 |
| Task015 | layered-background/RCWA-like inverse | 对 layered/flat/background case 几步收敛，并能改善 block grating residual |
