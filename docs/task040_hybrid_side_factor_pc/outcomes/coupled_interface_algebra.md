# V3-1 联合接口代数审计

## 状态

`pending_conditional_not_run`。本页冻结 V3-1 的输入、公式和 Gate；尚未读取 packet 数值矩阵、尚未组装
PDE 或 PETSc/MUMPS factor，也未运行 QEP/heavy。V3-1 结果必须在代码与 focused tests 完成后
补写，不能把计划字段当成 measured evidence。

## 固定 ordering 与输入

仅使用已完成 V2-A1 packet 中的三个 group small matrices：

| group | interface span | ordering |
|---|---:|---|
| group0 | 296 | lower |
| group1 | 776 | lower 296 后 upper 480 |
| group2 | 480 | upper |

每组保留 `G=Y^H Z`、`projected_scalar=Y^H S_scalar Z` 和
`projected_exact=Y^H S_exact Z` 的 shape、rank、singular values、condition 与 SHA256。
所有矩阵必须为 finite complex128；不能从 worker status 推断 Gate。

## 联合矩阵

三组矩阵按相同的 left/right dual 和 coefficient convention 组合：

```math
E_{joint}=E_1+\operatorname{blockdiag}(E_0,E_2).
```

从 group1 的 lower-then-upper 矩阵切出四个明确 block：

```math
E_{joint}=\begin{bmatrix}
E_{LL} & E_{LU}\\
E_{UL} & E_{UU}
\end{bmatrix}.
```

`E_LU` 与 `E_UL` 不得默认置零。V3-1 必须同时报告四个 block 的 Frobenius norm、相对
norm、rank 和 hash，并保留 incoming/block-diagonal map 与 middle cross-interface response
的语义区别。

求解允许使用 complex SVD、rank-revealing QR 或直接 Petrov solve；禁止 normal equations。
不得创建 FE-sized dense interface matrix，也不得 allgather FE numeric 或复制完整 basis。

## 独立 tiny oracle 与 failure decomposition

focused fixture 必须是 complex、non-Hermitian、三分区 block-tridiagonal 系统，独立比较：

- 直接消去 interior 得到的 full interface Schur；
- `E_1 + blockdiag(E_0,E_2)` 的联合组装；
- 联合 reduced solve 后的 full residual；
- 省略 `LU/UL` cross block 的明确 negative control。

matrix/action relative error 与 full residual 目标均为 `<=1e-12`。另按 physical、modal、
complement、middle lower-to-upper、middle upper-to-lower 分组汇总 scalar-exact、
projected-exact、in-span、complement orthogonality 和 cross-interface energy ratio。

## V3-1 Gate 与停止条件

通过需要：packet identity/hash exact、joint finite、full expected rank 或明确的数值 rank、
condition `<=1e12`、cross-block ordering identity、tiny oracle 全部通过，并证明现有 packet
足够构造 joint operator。若缺少只能从同一 producer 已有内存结果序列化的一个 small matrix，
才允许一次最小 schema enhancement；若必须重新求解物理问题，分类：

```text
COUPLED_PACKET_INFORMATION_INCOMPLETE
```

V3-1 不授权 V3-2 formal；当前尚无 measured rank、condition、block norm 或 failure metrics。
