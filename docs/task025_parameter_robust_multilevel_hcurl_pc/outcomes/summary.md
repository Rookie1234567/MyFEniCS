# 结果总结

## 任务

Task025：为目标 Stage4 p=2 Maxwell + double Floquet + 80 个 DtN auxiliary unknown 构造低内存、参数鲁棒的多层 H(curl) 预条件器，并重点突破 h=2。

## 分支

`codex/20260710-task25-parameter-robust-hcurl-pc`

## 最终答案

本轮找到了一条明显优于 plain ASM/ILU 和嵌套 FieldSplit 的工程研究路线：

```text
FGMRES
+ A_FE - i beta |diag(A_FE)| 吸收移位
+ distributed ASM/ILU1 FE inner solve
+ 缓存全部 80 列 Q_j ~= A_FE^-1 C_j
+ 显式 80 x 80 Schur S ~= A_aux - D Q
+ Schur LU
```

h=5 达到完整 80-aux 真残差 `5.338896e-6`，完成 official R/T/A；h=2 在 14 GB 配额内完成同一结构，100 步真残差 `0.1184751`，峰值 RSS `13.006 GB`。因此 h=2 的内存和 full-aux 工程闭环通过，但 strong / production gate 仍未通过，不能输出 h=2 official R/T/A，也不能声称已经解决 production h=2。

## 核心结果

| case | 方法 | 完整真残差 | RSS 峰值 | gate |
|---|---|---:|---:|---|
| h=5 | cached 80-response shifted Schur，200 外步 | `5.338896e-6` | `1.894 GB` | strong，接近 production |
| h=2 | cached 80-response shifted Schur，100 外步 | `1.184751e-1` | `13.006 GB` | minimum |
| h=2 | shifted FieldSplit，20 外步，FE5/aux10 | `2.423611e-1` | `11.274 GB` | minimum，成本受控 preflight |
| h=2 | shifted ASM/ILU1 FE response，50 步 | `2.407585e-1` | `8.656 GB` | FE-only 指标 |
| h=2 | Task24 m=1，100+100 步 | `1.585917e-1` | `4.469 GB` | 既有对照 |
| h=2 | Task23 plain FieldSplit ASM/ILU，40 步 | `9.895611e-1` | `8.948 GB` | fail |

Task025 cached-Schur 相对 Task24 最好完整残差改善约 `1.34x`，相对 Task23 plain FieldSplit 改善约 `8.35x`；但没有达到任务要求的 h=2 `<=1e-6`。

## 吸收移位与局部平滑

| h | 局部 PC | beta | 50 步 FE residual | RSS |
|---:|---|---:|---:|---:|
| 5 | ASM/ILU2 | 0.3 | `0.34145` | `~2.1 GB` |
| 2 | ASM/ILU0 | 1.0 | `0.26411` | `7.03 GB` |
| 2 | ASM/ILU1 | 1.0 | `0.24076` | `8.56 GB` |
| 2 | ASM/ILU2 | 0.5 | `0.23094` | `12.57 GB` |

ILU2 只有约 4% 相对收益，却几乎耗尽内存，不能再叠加 49,208,640 nnz 的 Q cache。最终选择 ILU1。

## 多层与粗空间诊断

| 粗空间 | 结果 | 判断 |
|---|---:|---|
| gradient/H1 hybrid，h=5 | 20 步最好约 `0.414` | 只改善随机向量，不捕获真实端口 RHS |
| p2->p1 重离散，h=5 | 50 步 `0.3530` | 弱于 fine-only |
| p2->p1 Galerkin，h=5 | 50 步 `0.3731` | 随机向量强，真实 RHS 弱 |
| p2->p1 重离散，h=2 | 50 步 `0.6740` | fail |
| y 不变 2D Q1，5 nm | 一次校正约 `1.01x` | 太粗 |
| y 不变 2D Q1，2.5 nm | 一次校正约 `1.98x`，10 外步 `0.8345` | 有覆盖率但不是 solver |
| ordinary BDDC，h=5 | 50 步 `0.3549` | 无优于 ASM 的收益 |
| adaptive deluxe BDDC，h=5 | setup 10 分钟未完成，`12.78 GB` | h=2 资源不可扩展 |

结论：本轮实现了 p-transfer、Galerkin/重离散对照和定制 2D coarse，但没有完成通用 nonmatching 3D H(curl) h-transfer；不能把这些原型称为 COMSOL 式 h-GMG。

## Cached Schur 为什么更好

嵌套 FieldSplit 在 h=5 用 FE30/aux80、100 外步得到 `1.3225e-4`，但求解耗时 `732 s`。cached-Schur 把 80 次 FE response 移到可复用 setup，并将小 Schur 显式因子化：

| case | assembly | Q setup | S factor | outer solve | total peak RSS |
|---|---:|---:|---:|---:|---:|
| h=5 | `16.4 s` | `62.0 s` | `0.02 s` | `78.0 s` | `1.894 GB` |
| h=2 | `114.8 s` | `393.7 s` | `0.10 s` | `503.2 s` | `13.006 GB` |

h=2 的 Q 列 residual 为 `0.286–0.541`，这是最终 `0.118` 平台的主要来源。Schur 本身只有 80 x 80，因子成本可以忽略。

## h=5 Official R/T/A

| residual | R | T | A_volume | R+T+A_volume | closure error |
|---:|---:|---:|---:|---:|---:|
| `5.338896e-6` | `0.0890283523` | `0.4425611881` | `0.4683744816` | `0.9999640219` | `-3.5978e-5` |

direct reference 为 `R=0.089021602936`、`T=0.442588278657`、`A_volume=0.468390118406`。当前差异符合 residual 尚高于 `1e-6` 的事实，因此只标为 strong diagnostic，不标为最终 production reference。

## Krylov Recycling

原生 PETSc build 没有 `gcrodr` 和 `hpddm` 注册。LGMRES 在 h=5 200 步仅把 residual 从 `0.33036` 改为 `0.320998`，h=2 full m=1 也没有收益。当前最有效的复用对象不是 Krylov 向量，而是 80 列 response cache 和 80 x 80 Schur。

## Gate 决策

| gate | 状态 | 原因 |
|---|---|---|
| h=5 full augmented strong | pass | `5.34e-6`，official R/T/A 完成 |
| h=2 内存 | pass | `13.006 GB < 14 GB` |
| h=2 minimum | pass | `0.1185 < 0.5` |
| h=2 strong | fail | `0.1185 > 1e-2` |
| h=2 production | fail | `0.1185 > 1e-6` |
| h=2 official R/T/A | blocked | 线性 residual gate 未通过 |
| 角度/波长鲁棒性矩阵 | blocked | reference h=2 gate 未通过 |
| h=1.5 | blocked | h=2 未通过且内存余量不足 |

## 已知问题

1. cached Q 当前只在进程内复用，尚未实现跨波长/角度的磁盘缓存与低秩更新。
2. Q 使用显式 AIJ 存储；h=2 有 49,208,640 nnz，是峰值 RSS 接近 14 GB 的主要新增项。
3. 通用 3D h-GMG 未完成；DOLFINx 当前路径缺少可直接用于 nonmatching Nedelec 空间的稀疏插值矩阵构造。
4. adaptive BDDC 在 h=5 已达到资源边界，不应上 h=2。
5. 未收敛 h=2 配置禁止输出 official R/T/A。

## 下一步

下一轮不应继续扩大 ILU fill、p1 粗层或 BDDC。最有价值的工程方向是：

1. 将 cached Q 从显式 80 列改为低秩压缩或按传播/近截止模态筛选，释放 1–2 GB 给更强 FE inner PC。
2. 在同一装配进程中实现 response recycling：新波长/角度先用旧 Q 作初值，只更新 residual 最大的列。
3. 为 h=2 FE block 实现真正的 low-order-refined / h-coarsened H(curl) hierarchy，目标把 Q 列最大 residual 从 `0.54` 降到 `<0.1`。
4. 只有 h=2 full residual 达到 `<=1e-6` 后才开启角度、波长和 h=1.5。
