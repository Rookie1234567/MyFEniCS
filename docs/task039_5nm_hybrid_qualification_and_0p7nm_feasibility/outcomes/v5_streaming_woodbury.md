# V5-5：streaming-W component evidence

本阶段回答一个很窄的问题：在已经有 exact-side factor 的前提下，是否可以不长期保存完整
`W = F^{-1}C`，仍然得到同一个 Woodbury action。它是 MPI1、64 行、32 个小模态和 4 个
固定 RHS 的 component，不是 h4/MPI8 正式求解，也不是 process-tree 内存 Gate。

## 1. 数学与实现边界

`F` 是 side 矩阵，`C/D` 是 side 与模态空间之间的耦合，`H` 是模态块。两种存储都使用同一个
Schur 补：

```math
K = H - D F^{-1} C.
```

retained-W 路径在 setup 时保存所有列 `W = F^{-1}C`。一次 apply 先计算
`z = F^{-1}r`，再用 `q = K^{-1}Dz`，最后完成 `y = z + Wq`。

streaming-W 路径仍然构造同一个 `K`，但按固定 batch（8、16 或 32 列）暂存
`F^{-1}C` 响应，把对应列累积进 `D F^{-1}C` 后立即释放 batch；它不保存完整 `W`。
apply 保留 `C` action，因此执行两次 side solve：

```math
z = F^{-1}r,\qquad q = K^{-1}Dz,\qquad y = z + F^{-1}(Cq).
```

所以 batch 只改变 setup 的瞬时 response buffer，不改变 32 次 setup factor solve 或 32 次
`D` apply；它把 apply 的 side solve 从 1 次变为 2 次。没有使用 normal equations。

## 2. 四个 fresh-process component 结果

| storage | max error vs NumPy | max error vs retained | W / batch bytes | setup factor/D | apply factor/D/C | internal wall (s) | ru_maxrss / current RSS (MiB) | swap / cleanup |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| retained | `4.8713e-16` | `0` | `32768 / 0` | `32 / 32` | `4 / 4 / 0` | `0.01537` | `954.20 / 120.77` | `0 / factor=0, all released` |
| batch8 | `4.8713e-16` | `1.1145e-20` | `0 / 8192` | `32 / 32` | `8 / 4 / 4` | `0.01672` | `634.39 / 120.84` | `0 / factor=0, all released` |
| batch16 | `4.8713e-16` | `1.1145e-20` | `0 / 16384` | `32 / 32` | `8 / 4 / 4` | `0.01835` | `701.42 / 121.00` | `0 / factor=0, all released` |
| batch32 | `4.8713e-16` | `1.1145e-20` | `0 / 32768` | `32 / 32` | `8 / 4 / 4` | `0.01622` | `823.27 / 120.73` | `0 / factor=0, all released` |

四个过程使用相同 fixture hashes、`K_rank=32`、condition=`1.206598`、`K=16384 B` 和
`LU=16512 B`。四个 raw 及 SHA 见 [component record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_streaming_woodbury_component_v1.json)。

`ru_maxrss` 是单个 fresh MPI1 Python 进程从启动到退出的 Linux lifetime high-water mark；
它包含 Python/PETSc/MUMPS 初始化和 allocator 行为。它不是 h4 process-tree peak，不能用
retained 与 batch8 之间约 320 MiB 的差异外推正式内存收益。current RSS 只是结束前的资源
采样，swap 四例均为 0。

## 3. 选择 batch8

本 component 选择 batch8，不是因为 RSS 噪声，而是因为它有最小且确定的 response buffer，
同时四个 RHS 的输出与 retained-W 的最大相对误差只有 `1.1145e-20`。这是 synthetic
component 选择，不是 h4/MPI8 正式参数批准。

## 4. 对 h4 对象容量的派生影响

V5-2 h4 setup raw 中，bottom/top 的 retained `W` 分别为 `74,961,408 B` 和
`83,261,952 B`，合计：

```math
W_{\mathrm{h4}} = 74{,}961{,}408 + 83{,}261{,}952
                 = 158{,}223{,}360\ \mathrm{B}
                 = 150.8935546875\ \mathrm{MiB}.
```

streaming 仍需常驻由 action owned 的 `C` action。使用同一 V5-2 NNZ 与当前 CSR estimate
公式，bottom/top `C` 约为 `47,985,008 B` / `49,522,304 B`，合计 `97,507,312 B`。
因此仅从 retained object capacity 派生：

```math
\Delta_{\mathrm{object}} = 158{,}223{,}360 - 97{,}507{,}312
                           = 60{,}716{,}048\ \mathrm{B}
                           = 57.90333557128906\ \mathrm{MiB}
                           = 0.056546226143836975\ \mathrm{GiB}.
```

这不是 process-tree RSS 节省，也没有把 transient response buffer、factor、K/LU、coupling
或 allocator 开销加进来；不能声称解决约 `10.96 GiB` 的 h4 回归。按 batch8 的同一
owner-row 估算，bottom/top 单侧 max-rank response buffer 分别约为 `2,025,984 B` 和
`2,191,104 B`，construction 顺序仍是 bottom side 后 top side。

## 5. 结论边界

- component numerical equivalence、finite output、factor destroy、C ownership/release 和
  zero swap：`measured`。
- h4 retained-W 到 streaming-W 的对象容量变化：`derived`，不是 RSS。
- h4/MPI8 process-tree reduction、正式 solve/recovery/physics Gate：`not_established`。
- ordinary default 与正式 runner 未接入本 component，保持不变。

证据：[四份 raw](../../../results/task039_v5_streaming_woodbury_component_76d374f/retained.json)、
[runner](../../../benchmarks/task039_v5_streaming_woodbury_component.py)。

