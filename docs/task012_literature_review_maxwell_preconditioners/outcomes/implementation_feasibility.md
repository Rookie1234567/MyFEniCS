# 实现可行性

## 本项目已有基础设施

| 基础设施 | 状态 | 对 task013 的价值 |
|---|---|---|
| Stage 4 direct/BLR official R/T/A | 已有 | 用作 correctness reference |
| iterative profile 框架 | 已有 | 可记录 KSP/PC/true residual/memory |
| A/P 双矩阵路径 | task010 已打通 | 可构造 physics P，而不改原 A |
| FE/aux block 识别 | 已有雏形 | 可做 DtN-aware block PC |
| real FE-only AMS smoke | task011 已通过 | 可复用 `discrete_gradient(Q,V)` 和 AMS setup |
| matrix-free FE action smoke | task011 已通过 | 后续内存优化层 |

## Task013 最小实现范围

推荐只做以下内容：

```text
1. 新增 real-split FE-only 或 reduced Stage 4 smoke runner；
2. 不跑 p=2 h=2/h=1.5 大算例；
3. 不输出 official R/T/A，除非 KSP 真正收敛；
4. 优先验证 true residual 曲线和 PC apply 稳定性；
5. 保留 BLR/direct reference，不替换 official 主线。
```

## 可行实现路径

### 路径 A：显式 real block matrix

| 项目 | 判断 |
|---|---|
| 做法 | 从 complex matrix `A` 提取 `Ar/Ai`，组装 real AIJ block `[[Ar,-Ai],[Ai,Ar]]` |
| 优点 | 数学清楚；可直接用 real PETSc/hypre AMS |
| 缺点 | 需要 real-mode 或额外矩阵转换；内存会翻倍；petsc4py 里 complex-to-real sparse extraction 需小心 |
| 适合 | 最小 smoke、debug、验证收敛 |

### 路径 B：Python PC apply 分离 real/imag

| 项目 | 判断 |
|---|---|
| 做法 | complex KSP 保持原 A；PC apply 中把 complex vector 拆成 real/imag，调用两个 real AMS KSP |
| 优点 | 不必显式构造 2x2 real A；外部仍是 complex Stage 4 |
| 缺点 | hypre AMS 的 real matrix 必须另行构造；交叉项处理更近似；Python PC 性能风险 |
| 适合 | 验证 blockdiag PC 概念 |

### 路径 C：先只做 FE-only real split

| 项目 | 判断 |
|---|---|
| 做法 | 用 task011 FE-only Maxwell form 构造 complex/real split smoke，不含 DtN/MPC |
| 优点 | 最安全，最容易定位 AMS 与 real block 问题 |
| 缺点 | 与完整 Stage 4 仍有距离 |
| 适合 | Task013 第一阶段 |

建议 Task013 采用 `Path C -> Path A/B` 的顺序。

## 内存风险审计清单

| 项目 | 为什么重要 | 记录字段 |
|---|---|---|
| `A` rows/nnz/AIJ GB | real block 会放大系统规模 | rows, nnz, estimated_gb |
| `G` rows/nnz | AMS 必需 | G_shape, G_nnz |
| high-order `Pi` 是否构造 | p=2 高阶 AMS 的主要风险 | Pi_shape, Pi_nnz |
| Aalpha/Abeta 是否传入 | hypre 文档指出可影响额外矩阵构造 | alpha_beta_mode |
| AMS setup RSS | task011 p=2 h=4 的瓶颈可能在 hierarchy | rss_before_setup, rss_after_setup |
| true residual | KSP residual 可能误导 | true_relative_residual_norm |

## 成功标准

Task013 不应以“能跑完”作为成功，至少需要满足：

```text
1. 不触发 complex hypre AMS crash；
2. true residual 比 Jacobi-Krylov 明显改善；
3. p=1 h=5 或 p=2 h=5 至少一个 case 达到 <= 1e-6；
4. 未收敛时不输出 official R/T/A；
5. 记录内存瓶颈来自 A、G/Pi、AMS hierarchy 还是 Python PC。
```

## 停止标准

出现以下情况应停止并回到设计层：

| 停止条件 | 解释 |
|---|---|
| real AMS 在 FE-only real split 上也不收敛 | 说明 task011 smoke 与 real split 构造不一致，需要定位 |
| p=1 h=5 即内存不可接受 | 路线工程不可行，需要先做 p-coarsened/low-order |
| PC apply 后 true residual 反而系统性恶化 | 交叉项/符号/real block 构造可能错误 |
| coarse/modal deflation matrix 病态且无正则化方案 | 先缩小 coarse space 到 propagating orders |

## 不建议立刻做的事

- 不直接跑 full `p=2 h=2` Stage 4 real-split AMS。
- 不继续测试更多 Jacobi restart 或 BiCGStab/TFQMR 变体。
- 不把 BLR 当成“迭代求解器已解决”的证据。
- 不把 RCWA-like approximate inverse 直接做到完整 3D grating；先做 flat/layered background smoke。
