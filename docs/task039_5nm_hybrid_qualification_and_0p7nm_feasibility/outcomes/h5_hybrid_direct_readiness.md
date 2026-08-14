# Review V2-4：h5 Hybrid direct readiness

本文件只记录 V2-4 的启动前资格审计，不是 h5 Hybrid 正式运行结果。正式 V2-5
尚未启动；没有 QEP 特征值计算、local FE/DtN 组装、augmented 组装、MUMPS factor
或 PDE。机器可读证据为
[V2-4 readiness record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_direct_readiness_v1.json)。

## 身份与输入

| 项目 | 结果 |
| --- | --- |
| source | `d4ea422cbd48de9b5ad6c2e59615e748f2babbac`，branch clean，0/0 |
| input | `5nm_p6h5_hybrid_direct_m480_mpi8.dat`，SHA256 `576e2631615330565e28eef6637264e4fdd539a558157405f252ae230f084fa4` |
| resolved identity | `c367a4ee9f8a459dce64ba1dd38235e1cd6e4d65893031e884777cbddbe11a60`，来自 `load_and_resolve` dry-run；尚无正式 run 文件 |
| physical identity | `e35907c72ab97069d9ab66958fd00787f98dea08dce1aa6f64c053b7bda46cdb` |
| method / mesh / modes | `hybrid_direct` / h=`5 nm` / M=`480` per direction / MPI8 |
| fixed physics | 5 nm wavelength、p6、S、10°、interfaces 10/110 nm、full3d_uniform_cg、exact one-cell traction |
| external inventory | 604 exact unique；bottom/top=`300/304`；spatial surface orders=`302` |
| validate / dry-run | pass / pass；dry-run 111815 bytes，未启动 worker |

## ABI、整数与资源

qualified activation 使用仓库 `.venv`、PETSc complex128/int32、PETSc 3.19.6；petsc4py、
slepc4py、dolfinx 和 mpi4py 均来自同一 Linux WSL2 ABI 栈。MUMPS 头文件为 5.6.2：
`MUMPS_INTSIZE32`、`MUMPS_INT=int32`，而 `MUMPS_INT8=int64`，`nnz`/`nnz_loc` 使用
`MUMPS_INT8`。因此当前已知的 row/order 与 NNZ counter ABI 没有阻断项；运行时 factor
内部路径仍是 conditional/not_established，不能写成已证明安全。

| 启动前 measured 项 | 值 | Gate |
| --- | ---: | --- |
| MemTotal | `228.0657501220703 GiB` | selected finite limit |
| MemAvailable | `225.03710174560547 GiB` | `>=200 GiB`，pass |
| swap | total `32 GiB`，used `0` | immediate stop on any use |
| disk free | `808005708 KiB` | `>=20 GiB`，pass |
| concurrent heavy job | none observed | pass |
| cgroup memory/swap limit | not_available in current scope | not a measured blocker |

用户覆盖的运行策略仍是：warning=`170 GiB`；critical=`195 GiB` 只记录 crossing；
绝对终止=`224000000000 bytes`（`208.6162567138672 GiB`）；poll 全程 `<=0.25 s`；
任意 swap 立即终止。预测超过 195 GiB 只记录风险，不单凭预测阻止启动。

## Derived capacity prediction

中心值使用相邻实测网格比：

```math
r_{\mathrm{mesh}}=\frac{1127502\ {\rm h5\ Full3D\ DoF}}{173802\ {\rm h10\ Full3D\ DoF}}=6.4872786274.
```

将 h10 Hybrid M480 的 local/augmented 记录乘以该比值；结构和 resident-resource
区间再使用 `0.8–1.25`，表达 local-vs-global mesh scaling、fill-in 和生命周期的
不确定性。以下全部是 `derived/predicted`，不是 h5 Hybrid measured：

| 对象 | 中心值 | 保守区间/口径 |
| --- | ---: | --- |
| cross-section QEP full/reduced | `2053² / 1944²` | derived from h10 Hybrid same p6 cross-section |
| candidate / retained | `960 / 480` per direction | input contract |
| bottom/top local full FE rows | `168578 / 168578` | each `134863–210723` |
| active trace rows | `54649` each | `43719–68311`；auxiliary `300/304` exact |
| P/T shape | bottom `[480,54949]`; top `[480,54953]` | derived active trace + exact auxiliary rows |
| P/T NNZ | `4035606` each | `3228485–5044508` each |
| augmented rows | `110862` | `89002–138186` |
| augmented assembled NNZ | `118466258` | `94773006–148082822` |
| factor NNZ | `723592076` | `578873661–904490095` |
| factor bytes estimate | `17367972385 bytes` | `13894377908–21709965481 bytes` |
| process-tree RSS/PSS/USS | `132002/121822/120197 MiB` | RSS `105602–165003`; PSS `97457–152277`; USS `96158–150246` |

factor 中心值使用 `60473536 × (2597000000/217041864)`；RSS/PSS/USS 使用 h10 Hybrid
measured peak 乘以 h5/h10 Full3D measured RSS ratio。锚点分别为 h10 Hybrid M480、
h10 Full3D T3 和 h5 Full3D V2-2；其路径和 SHA 在 JSON 中绑定。对象容量不能相加
冒充 simultaneous process-tree RSS，正式 stage-aligned telemetry 只能由 V2-5 实测。

## 决定与边界

| Gate | 状态 |
| --- | --- |
| readiness / launch eligibility | `true`，conditional：资源、ABI、输入和 604 inventory 通过 |
| V2-5 formal h5 Hybrid direct | `not_run` |
| h5 Hybrid own numerical authority | `not_established` |
| h6↔h5 convergence | 保持 V2-3 negative；不在本阶段重判 |

因此本记录只说明可以等待单独授权后尝试 V2-5；它不预言正式 factor 成功，也不
改变普通 defaults、已有 h10 historical boundary 或 0.7 nm 结论。
