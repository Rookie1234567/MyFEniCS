# Task037 Candidate F 补充执行说明：p6 → p4 → p2 局部 p-multigrid

## 1. 执行顺序

先完成并按既有 Gate 收口当前正在运行的部分凝聚实验；不得中断、改阈值或为 Candidate F 重调部分凝聚配置。

部分凝聚收口后，执行本文件定义的唯一 Candidate F。它用于回答：Candidate D 失败是否主要因为 `p6 → p2` 跨度过大，而不是 auxiliary-space 思路本身无效。

## 2. 冻结空间

六面体第一类 Nédélec 局部空间：

| degree | local DoFs | trace DoFs | interior DoFs |
|---:|---:|---:|---:|
| p2 | 54 | 48 | 6 |
| p4 | 300 | 192 | 108 |
| p6 | 882 | 432 | 450 |

构造 exact-sequence、orientation/Floquet 一致的局部 transfer：

```math
P_{46,j}=R_{6,j}P_{4\to6}R_{4,j}^{T},
\qquad
P_{24,j}=R_{4,j}P_{2\to4}R_{2,j}^{T}.
```

禁止连续 row slice、最近坐标、手工 index 对应或训练解投影。

## 3. F0：局部 p4 空间容量 oracle

在 tiny/medium local fixture 上构造：

```math
A_{4,j}=P_{46,j}^{H}A_{6,j}P_{46,j},
\qquad
A_{2,j}=P_{24,j}^{H}A_{4,j}P_{24,j}.
```

所有 shift、人工接口项必须先在高阶算子定义，再通过同一 transfer 投影。

F0 允许临时使用 complex128 的 p4 direct/ILU，只作为空间容量 oracle，不进入正式 PDE solver。计算：

```math
z_j=P_{46,j}A_{4,j}^{-1}P_{46,j}^{H}r_j+D_{6,j}^{-1}r_j,
```

```math
\rho_j=\frac{\|r_j-A_{6,j}z_j\|}{\|r_j\|}.
```

对与 Candidate D 相同的 low/high/mixed sources 报告结果，并与 B4、D0 比较。

F0 Gate：

- transfer 与 projected-action relative error `<=1e-11`；
- high、mixed source 相对 B4 的 contraction improvement 均 `>=1.5`；
- 完整报告 p4 rows、matrix NNZ、factor NNZ 与 payload；
- p6 retained matrix/factor/NNZ 始终为 `0/0/0`。

任一 high/mixed Gate 失败，记录：

```text
P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE
```

并停止 Candidate F，不开发三层 PDE profile。

## 4. F1：唯一允许的三层 factor-free p-V-cycle

只有 F0 通过才实现。正式 F1 不允许长期保留 p4 factor；只允许保留小型 p2 local factors。

局部 p6 inverse 固定为四步 FGMRES，其 inner PC 为一个固定 p4→p2 V-cycle：

```text
p6 cheap shifted-diagonal / low-degree polynomial pre-smooth
→ restrict p6 to p4
→ p4 factor-free pre-smooth
→ restrict p4 to p2
→ local p2 ILU(0) or small direct solve
→ prolongate p2 to p4
→ p4 factor-free post-smooth
→ prolongate p4 to p6
→ p6 cheap post-smooth
```

冻结条件：

```text
slabs                    = 16
overlap                  = 0.125
outer                    = right FGMRES restart 90
local p6 steps           = 4
p6 retained factor NNZ   = 0
p4 retained factor NNZ   = 0
only retained factors    = local p2 factors
global A / F             = false / false
fine operator/residual   = complex128
Matrix-free DtN          = enabled and qualified
wave coarse              = existing 75D basis
```

不得同时扫描 p4 smoother、local steps、shift、slab 数、overlap、p3 或 p5。

## 5. fine-system 选择

当前部分凝聚实验完成后冻结：

- 若部分凝聚通过其既有数值和资源 Gate，Candidate F 使用该部分凝聚 fine operator；
- 若部分凝聚失败，Candidate F 使用当前 fully-condensed factor-free fine operator；
- 禁止为 Candidate F 同时运行两套 heavy fine systems。

## 6. MPI8 受控漏斗

只运行一个冻结 Candidate F。

### Screen-20

```text
finite / no NaN
true residual < 0.35
strictly better than B4@20 = 0.4261192527
MPI8 peak <= 7.0 GiB
```

### Screen-100

```text
true residual <= 0.12
last 40 iterations net decrease
strictly better than B4@100 = 0.1708326448
```

### Screen-200

```text
true residual <= 0.05
predicted iterations <= 3000
predicted wall <= 7200 s
strictly better than B4@200 = 0.1405734648
```

任一 Gate 失败立即停止，不得调参后自动重跑。

只有 Screen-200 全部通过，才允许：

1. 一次 MPI8 full solve；
2. 数值、canonical field、12+12 channels 与 R/T/A 全部通过后，测试 restart `90 → 60 → 40 → 30 → 20`；
3. 最优配置运行一次 MPI1 full，检查 whole-job peak `<=2.0 GiB`，优选 `<=1.5 GiB`。

## 7. 停止边界

Candidate F 完成后写 compact evidence 和 response 补充并停止。不得自动进入 modal coarse、Hybrid、0.7 nm PDE、p3/p5、多参数扫描或新的预条件器家族。
