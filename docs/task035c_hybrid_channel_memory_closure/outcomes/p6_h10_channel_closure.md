# Task035c p6/h10 高阶逐通道闭合

## 1. Authority 身份

| 字段 | 值 |
|---|---|
| numerical source | `244b62e1fb4f299a468363cf90a2dd548dc34ff6` |
| branch | `codex/20260726-task35c-hybrid-channel-memory-closure` |
| geometry | Task034 fixed rectangular block grating |
| mesh | structured hexa `(6,3,14)`，252 cells，`h10` |
| field space | first-family Nédélec `p6` |
| wavelength / incidence | 13.5 nm；10° grazing；S |
| formal MPI | 8 |
| PETSc | `complex128` / `int32` |
| significant reference | Case095 `significant_channel_reference_v1.json` |
| amplitude convention | physical boundary plane `outgoing_amplitude_at_boundary` |
| ordinary default | `standard_full`，unchanged |

`p6/h10` 是当前 best available global-p discrete reference。它与 COMSOL
高阶趋势接近，但没有独立证明 continuum convergence。

## 2. 为什么必须同时跑六条路径

六条路径分别回答三个不同问题：

1. Full3D standard/static 检查静态凝聚是否保持完整三维离散；
2. Hybrid standard/static 检查把同样的消元放入上下 local FEM 后是否仍等价；
3. Full3D/Hybrid 与 M120/M160 检查离散传播相位、traction、模态截断和
   physical reference plane 是否真正闭合。

任何一类单独通过都不能替代另两类。

## 3. 六条 MPI8 正式结果

| path | rows | matrix NNZ | factor NNZ | true residual | Rtotal | Ttotal | Aclosure | Avolume | peak GiB | total s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full3D standard | 173,882 | 210,353,168 | 438,050,956 | `1.708691e-11` | `0.000762881475133097` | `0.602701633983338` | `0.396535484541529` | `0.396535484541761` | 34.041210 | 2581.549788 |
| Full3D static | 51,272 | 41,989,040 | 212,343,992 | `3.092135e-11` | `0.000762881475125861` | `0.602701633985538` | `0.396535484539337` | `0.396535484542807` | 14.721756 | 260.736180 |
| Hybrid standard M120 | 52,292 | 60,434,236 | 141,010,528 | `4.858359e-12` | `0.000762881475146551` | `0.602701633983422` | `0.396535484541431` | `0.396535484696121` | 11.076893 | 942.026047 |
| Hybrid static M120 | 17,168 | 12,313,232 | 45,293,792 | `2.078714e-12` | `0.000762881475141562` | `0.602701633984217` | `0.396535484540641` | `0.396535484696529` | 7.544262 | 322.781788 |
| Hybrid standard M160 | 52,372 | 60,434,236 | 141,010,528 | `7.877882e-12` | `0.000762881475143137` | `0.602701633983403` | `0.396535484541454` | `0.396535484687084` | 11.247025 | 1014.706182 |
| Hybrid static M160 | 17,248 | 12,313,232 | 45,293,792 | `2.368230e-12` | `0.000762881475138196` | `0.602701633984275` | `0.396535484540587` | `0.396535484687489` | 7.929413 | 393.840814 |

所有路径均：

- `full explicit true residual <= 1e-9`；
- 无 swap；
- geometry/material/Floquet/DtN/reference-plane identity 通过；
- R/T/Aclosure/Avolume 与 energy closure 通过；
- interface E/H 和 selected middle-plane E/H 通过；
- 12/12 significant powers + 12/12 boundary-plane complex amplitudes 通过。

Hybrid M120 的上下 interface relative L2 为：

| field | bottom | top | Gate |
|---|---:|---:|---:|
| tangential E | `1.509542e-7` | `1.639492e-7` | `<=5e-3` |
| tangential H | `3.895753e-5` | `3.341563e-5` | `<=1e-2` |
| middle-plane E max | `1.302750e-11` | n/a | `<=5e-3` |
| middle-plane H max | `4.173301e-6` | n/a | `<=5e-3` |

M160 对应数值不劣于相同 Gate，且没有显示需要 M240 的物理信号。

## 4. 逐通道结论

独立 checker 从原始 80 个 DtN orders 读取功率和
`outgoing_amplitude_at_boundary`，而不是相信 record 中预填的状态。12个通道为：

```text
R/T (m,n) = (0,0), (-1,0), (-2,0), (-4,0), (-5,0), (-7,0)
```

| comparison | powers | amplitudes | max relative power / amplitude |
|---|---:|---:|---:|
| Full3D standard/static | 12/12 | 12/12 | `3.403216e-10 / 4.157596e-10` |
| Full3D/Hybrid standard M120 | 12/12 | 12/12 | `9.808479e-10 / 5.219422e-10` |
| Full3D/Hybrid static M120 | 12/12 | 12/12 | `7.973629e-10 / 6.631737e-10` |
| Hybrid standard/static M120 | 12/12 | 12/12 | `2.538984e-10 / 3.631079e-10` |
| Full3D/Hybrid standard M160 | 12/12 | 12/12 | `8.606937e-10 / 4.445835e-10` |
| Full3D/Hybrid static M160 | 12/12 | 12/12 | `8.414276e-10 / 6.428430e-10` |
| Hybrid standard/static M160 | 12/12 | 12/12 | `5.076477e-10 / 3.826741e-10` |
| static M120/M160 | 12/12 | 12/12 | `1.865505e-10 / 1.610320e-10` |

这些相对差都比冻结 `1e-3` tolerance 小六个数量级以上。旧 checker 曾错误
比较未平移的 `outgoing_amplitude`；本轮只修正字段与 reference hash 的嵌套读取，
没有修改 significance floor、通道集合或 tolerance。

## 5. 资源比较

### Full3D

| metric | standard | static | reduction |
|---|---:|---:|---:|
| rows | 173,882 | 51,272 | 70.5133% |
| matrix NNZ | 210,353,168 | 41,989,040 | 80.0388% |
| factor NNZ | 438,050,956 | 212,343,992 | 51.5253% |
| peak | 34.041210 GiB | 14.721756 GiB | 56.7531% |
| base build | 2246.006652 s | 92.631094 s | 95.8755% |
| direct linear solve | 301.039365 s | 143.372679 s | 52.3738% |
| total | 2581.549788 s | 260.736180 s | 89.9000% |

standard Full3D 的主要成本是 2246 s 高阶完整矩阵装配，而不是 301 s MUMPS。
static path 直接构造 trace Schur，没有先组装173,882行完整p6矩阵。

### Hybrid

| M | standard/static peak | peak reduction | standard/static modal | modal ratio | standard/static total | total ratio |
|---:|---:|---:|---:|---:|---:|---:|
| 120 | 11.076893 / 7.544262 GiB | 31.8919% | 34.714218 / 37.340495 s | 1.075654× | 942.026047 / 322.781788 s | 0.342646× |
| 160 | 11.247025 / 7.929413 GiB | 29.4977% | 48.192441 / 51.869917 s | 1.076308× | 1014.706182 / 393.840814 s | 0.388133× |

M120 是当前推荐点。它通过所有物理 Gate，且比 M160 少5.1%峰值、少38.9%
coupling时间、少22.0%总时间。

## 6. Raw artifact hash

| authority | SHA-256 |
|---|---|
| `p6_h10_full_standard_mpi8_244b62e.json` | `0a0846cd5e7bdef1532fda0ee2540fe2af00f54a8e1cc7c963f53dbf019df246` |
| `p6_h10_full_static_mpi8_244b62e.json` | `b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3` |
| `p6_h10_hybrid_standard_m120_mpi8_244b62e.json` | `563e4158955f251e067be6d40bb3ca0e34e1032c2b1ad1e265a3751d3889979b` |
| `p6_h10_hybrid_static_m120_mpi8_244b62e_retry1.json` | `194a22ee2528a2536f794c0a0a8871671cb023a2f8dc029b31fae456694d5532` |
| `p6_h10_hybrid_standard_m160_mpi8_244b62e.json` | `724923b23976000d44640177d50fc4882628c957fdffaf4800aa28f4e22734b5` |
| `p6_h10_hybrid_static_m160_mpi8_244b62e.json` | `58281f5f0be5c9d30b441d9b573018070502734043a81cb8cd10ddd068f5c137` |

Tracked compact authority：

- `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json`
- `benchmarks/cases/096_hybrid_channel_memory_closure/records/compact_authority_v1.json`

重型原始文件保持 ignored，由生成器在存在本地 artifact 时逐 hash 复算。
