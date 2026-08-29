# C0 同网格 H(curl) canonical source 资格证据

## 结论

V13 C0 在同一份新源码 4dc9b55cd3519a03b23c9d27779c0379cef84f66 下，以 p3/p1 同网格、h=50、MPI1 与 MPI2 各运行一次，独立 checker 均通过。因此本证据的分类是 C0_CANONICAL_SOURCE_PASS_MPI1_MPI2。它只证明物理 canonical source、owner packet 传递和约束闭合；没有运行 C1 solver、p6、PDE 或 official physics。

V12 的旧 C1 identity negative 仍原样保留：same_mesh_hcurl_pmg_c1_mpi_identity_v1.json 的 primal relative=0.10049859821442367、dual relative=0.004662851981572301，分类仍为 CLOSED_BY_MPI_CANONICAL_IDENTITY_GATE。C0 v4 是新 schema、新 artifact root 下的独立证据，不重分类这项历史结果。

## 固定身份与 Gate

| 项目 | 实测/固定事实 |
|---|---|
| 源码 / 分支 | 4dc9b55cd3519a03b23c9d27779c0379cef84f66 / codex/20260820-task38-extra-full3d-iterative-0p7nm |
| 网格与层 | p3/h50；fine/coarse=(3,1)；MPI1、MPI2 |
| Basix variant | fine/coarse 均 legendre |
| schema | record v3 / marker v3 / checker v4；canonical-source hash v1 |
| source Gate | key set exact；primal/dual source finite、nonzero；coefficient relative ≤1e-13、max abs ≤1e-12 |
| transfer Gate | owner primal/adjoint、linearity、repeat、finite、input unchanged、phase-once、local/global adjoint 均通过 |
| architecture | no global high-order AIJ、no global transfer matrix、no numeric allgather、no p1 factor/KSP/smoother、no physical/recovery |

## 两次运行

| 指标 | MPI1 | MPI2 |
|---|---:|---:|
| watchdog peak process-tree RSS | 141,524,992 B | 262,807,552 B |
| swap / return / lifecycle | 0 B / 0 / natural, no orphan | 0 B / 0 / natural, no orphan |
| source primal packets | 162（102 independent + 60 dependent） | 162（102 + 60） |
| source dual packets | 2,538 independent | 2,538 independent |
| source primal relative | 0 | 0 |
| source dual relative / max abs | 1.3112141111956135e-17 / 2.2887833992611187e-16 | 2.012501428728352e-17 / 2.2887833992611187e-16 |
| global adjoint work relative | 1.6024250121032939e-15 | 5.8266238536862765e-16 |
| implemented vs explicit vector relative | 1.732205676136131e-17 | 1.2248543800056866e-17 |
| linearity / repeat | 1.377237509255599e-16 / 0 | 1.4396768382121543e-16 / 0 |

## Cross-MPI canonical identity

两个 rank-shard 合并后按 physical key 比较，未使用 PETSc global row、rank、local row、ownership 或 Python hash。两种 MPI 数的 source key set 均完整，missing/extra/duplicate 都是 0。

| 比较对象 | relative | max absolute |
|---|---:|---:|
| source primal | 0 | 0 |
| source dual | 1.950065385229289e-17 | 2.2887833992611187e-16 |
| projected primal | 7.098786108663455e-16 | 2.3738609781529628e-15 |
| adjoint dual | 4.1067748418222563e-16 | 9.103828801926284e-15 |

primal dependent values 不是独立 hash source，而是由 master 与 Floquet/MPC 关系生成；实测 relation relative=1.9801606126261387e-16、max abs=2.237726045655905e-16。dual 使用 slave-zero storage，未重复施加 phase。

## 证据入口

完整紧凑记录见 records/same_mesh_hcurl_pmg_c0_v4.json。原始 ignored artifact root 为：

benchmarks/artifacts/task038_extra_full3d_c0_canonical_source_v4/4dc9b55cd3519a03b23c9d27779c0379cef84f66/

| MPI | worker record SHA256 | checker SHA256 | watchdog compact SHA256 |
|---|---|---|---|
| 1 | cb9f3550a78536a25542002edf242f1f57a338b308ae656e702801b7936d1ce6 | fd045daba810c2aa4f0f6cab833aa6f319574ed2912e888933b79de9df389a89 | 943ee72c22719aadf6ddc040b734737f67bcb5391cc7fbe3fe571bd835f921ca |
| 2 | a68037b088f91a7546e824af981f0b2fb91a158036f9b8b5adb9e33aa4a138af | 3d8d523f8ac7215ef93d25415469a0e5472f9fbb9e5c6c77c62ebb96419de5ef | ece8662f106790ad90e89e3a296ae161496e7a389e292f80d25cd02d024a6cd4 |

## V13 更新：C0 之后的 C1 exact-input 资格

C0 的结论和证据入口保持不变；C0 是由 A0 fail 后按固定分支进入的。V13 在同一 exact input 身份下继续完成了 p6/h10、13.5 nm、same-mesh H(curl) 的四个 positive source；这四次运行验证的是正定辅助算子上的固定 p6→p3→p1 预条件器，不能替代真实含波动和 streaming Fourier-DtN 的 physical Maxwell workflow。

| source | formal source SHA | iterations / final explicit true residual | process-tree peak / retained peak | C1 结论 |
|---|---|---:|---:|---|
| random | 0da00e98c0423ade6cea38cabc3c8415ea32510e | 200 / 5.550975220267439e-9 | 1,517,903,872 B / 772,497,408 B | C1_P6_POSITIVE_PASS_MPI1 |
| gradient | 82c56d92ac80ddf84071a6e1eff6d28e3513af7e | 220 / 2.7889793119815017e-9 | 1,516,544,000 B / 770,650,112 B | C1_P6_POSITIVE_PASS_MPI1 |
| curl | 48866f2990a12113a28e556e6956104625b3da34 | 180 / 5.6105046279899595e-9 | 1,536,192,512 B / 790,028,288 B | C1_P6_POSITIVE_PASS_MPI1 |
| checkerboard | 80b0d8d36364007f4dda941d7770a307eee15dd4 | 200 / 7.760965317017376e-9 | 1,533,190,144 B / 786,751,488 B | C1_P6_POSITIVE_PASS_MPI1 |

四案均为新 source SHA、新 ignored artifact root、独立 worker/checker、swap=0、natural exit、no orphan 和全量 watchdog readability 通过。记录的固定输入为 input SHA 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41、physical model SHA 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f、grazing=1°、theta=89°、phi=0°、p6/h10、13.5 nm。正定辅助 lane 的 architecture 仍明确禁止 p6 global AIJ、global dense transfer、numeric allgather、p6 factor、physical solve 和 recovery。

四源通过后，V13 的 selected_hierarchy 为 same_mesh_hcurl_pmg_v1_requalified。四源 compact 入口分别为：

- records/same_mesh_hcurl_pmg_p6_positive_exact1_random_v4.json、其 _watchdog.json 和 _checker.json；
- records/same_mesh_hcurl_pmg_p6_positive_exact1_gradient_v4.json、其 _watchdog.json 和 _checker.json；
- records/same_mesh_hcurl_pmg_p6_positive_exact1_curl_v4.json、其 _watchdog.json 和 _checker.json；
- records/same_mesh_hcurl_pmg_p6_positive_exact1_checkerboard_v4.json、其 _watchdog.json 和 _checker.json。

V12 的 C1 identity negative 仍是历史结论，primal relative=0.10049859821442367、dual relative=0.004662851981572301，分类仍为 CLOSED_BY_MPI_CANONICAL_IDENTITY_GATE；它没有被 C1 V13 结果覆盖或重分类。V12 的 selected_hierarchy=NONE 也作为旧版本结论永久保留。V13 的 P0 physical 结果见 p6_physical_v13.md：cold setup 触发严格 process-tree RSS hard stop，因此不能把 selected positive hierarchy 写成 physical qualification。
