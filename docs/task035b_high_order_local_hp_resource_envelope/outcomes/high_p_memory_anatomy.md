# Task035b 高阶 p6 内存构成与 exact static condensation

| 项目 | global p6 full | exact p6 condensed | 结论 |
|---|---:|---:|---|
| source SHA | `c1040a0197d3e113576c9dc1e8d3ae13a5fa66b2` | `0f4b786d618c37e1c572a4f596a9235e53d73161` | 两者均为 clean committed SHA |
| mesh | h10 hexa `(6,3,14)`, 252 cells | 相同 | mesh/cell-tag/facet-tag hashes 相同 |
| MPI | 8 | 8 | formal resource identity 相同 |
| FE / augmented rows | 173,802 / 173,882 | 173,802 / 60,482 active | 113,400 cell-interior rows 被物理消去 |
| matrix NNZ | 210,353,120 | 52,058,162 | -75.25% |
| factor NNZ | 386,625,292 | 243,270,308 | -37.08% |
| fill | 1.838 | 4.673 | Schur 更稠密 |
| formal memory authority | 35.024 GiB | 29.212 GiB | -16.59% |
| full explicit residual | `2.018e-11` | `1.959e-11` | 均通过 `1e-9` Gate |
| p6 elapsed | 2,526.7 s | 2,495.3 s | 无可信 wall-time 加速 |

这是两个 clean SHA 上的单次 MPI8 实测对照。ordinary full-system path 在新
SHA 上默认关闭 condensation，矩阵 rows/NNZ 和 official observables 均保持
一致；但 MUMPS ordering/factor inventory 存在 run-to-run 波动，例如两次
p5 control 的 factor NNZ 相差约 5.8%。因此 factor NNZ 和 peak-memory
降幅是当前实测工程信号，不应写成统计置信区间或逐位确定量。

## 身份与实现边界

本结果只研究 Task034 fixed rectangular block grating，不含任何不规则几何。
condensed solve 在同一实际 mesh instance 上执行，并保持：

- mesh SHA-256
  `f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857`；
- cell-tag SHA-256
  `42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131`；
- facet-tag SHA-256
  `0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd`；
- exact Basix periodic orientation/mapping、80 个 DtN auxiliary unknowns；
- ordinary `stage4_cell_static_condensation=False` default 不变。

实现逐 cell 形成

```text
S = A_tt - sum_K A_ti(K) A_ii(K)^-1 A_it(K)
g = b_t  - sum_K A_ti(K) A_ii(K)^-1 b_i(K)
```

求解 60,482-row trace system 后重新逐 cell 恢复 113,400 个 interior
unknowns，再用原完整 173,882-row operator 显式重算 residual。没有
max-p zero masking，也没有保留 all-cell dense factor cache。

## 为什么 DoF 大降但 MUMPS 内存没有同比下降

实测给出四个互补原因：

1. 当前 prototype 从已经装配的完整 p6 sparse matrix 开始，未消除
   2,195.58 s full base assembly 及其生命周期峰值。
2. trace Schur 的 average row width 为 860.7；虽然低于 full p6 的
   1,209.7，但相对 60,482 rows 已显著稠密。
3. factor fill 从 1.838 增到 4.673，所以 rows -65.22% 只换来
   factor NNZ -37.08%。
4. Schur build 期间 full matrix、transpose copy 和 condensed matrix
   存在生命周期重叠；正式 memory authority 因而只从 35.024 GiB 降到
   29.212 GiB。

Schur build 共 84.69 s：

| 子阶段 | MPI8 max time |
|---|---:|
| transpose | 1.69 s |
| local dense solves | 15.22 s |
| Schur insertion | 26.14 s |
| final parallel assembly | 57.99 s |
| full recovery | 7.75 s |

子阶段存在重叠，不能把这些 max-time 数简单相加解释为总 wall time。

## 物理等价 Gate

| observable | global p6 full | exact p6 condensed | absolute delta |
|---|---:|---:|---:|
| R_total | 0.000762881475130 | 0.000762881475131 | `9.41e-16` |
| T_total | 0.602701633983078 | 0.602701633983515 | `4.38e-13` |
| A_volume | 0.396535484541640 | 0.396535484541834 | `1.94e-13` |

该 lane 是明确正信号：物理等价、full residual、rows、NNZ、factor NNZ 和
memory 均通过。但它尚未达到“完整 p6 assembly 不存在”的最终工程目标，
也不构成 local-p/regionwise-p 完成证明。

## Evidence

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_p6_condensed_mpi8.json`
- raw ignored evidence:
  `benchmarks/artifacts/task035/actual_global_r5/hexahedron_p5_p6_h10_pols_mpi8_20260723T143152Z_single_mesh_pair_condense_p6/`
