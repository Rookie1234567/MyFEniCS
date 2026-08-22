# V7 L0：native-complex LOR-HX 容量预检

## 结论先行

这一步只回答“新路线在完整 p6/h10 live set 的字节账本中是否有可信窗口”，没有运行
LOR solver、PDE、physical contraction 或正式 p6 worker。LOR（低阶 refined mesh）把
高阶 H(curl) 空间换成 p-refined 网格上的最低阶边元；HX-style（辅助空间）用边
Jacobi、一个标量 nodal hierarchy、梯度和三个顺序的向量-nodal correction 共同近似
边空间逆。这样做的收益是避免高阶 global AIJ、real-split 复制和直接粗网格因子；代价
是要额外保存一个低阶边矩阵、nodal hierarchy、transfer/map 和 Krylov 工作区。

| V7 L0 Gate | 实值 | 判定/口径 |
|---|---:|---|
| central complete setup+online+restart-20 budget | `1,600,288,800 B` | `< 1,700,000,000 B`；derived exact arithmetic + explicit budget |
| hard-upper complete workflow budget | `1,831,288,800 B` | `< 1,900,000,000 B`；不是 process-tree 实测 |
| major unknown live-set component | `0` | 每个 V7 §7.5 项目都有 measured/exact/derived/budget provenance；预算阶段仍须 L3 watchdog 验证 |
| LOR topology / maps | `59,755` vertices, `173,802` edges, `170,076` faces, `54,432` cells | exact structured-grid arithmetic |
| scalar hierarchy | native complex PETSc `PCGAMG`, `agg`, explicit Jacobi coarse | tiny capability smoke passed; no LU/direct coarse in qualified tree |
| prohibited global/materialized path | all `false` in the frozen design | no high-order global AIJ, real/imag split, global direct coarse, FE numeric allgather |
| classification | `LOR_NATIVE_COMPLEX_HX_L0_CAPACITY_PASS_CONDITIONAL` | 只授权继续做 L1 oracle；不是数值或资源 formal PASS |

旧 FC3 local-spectral family 保持关闭。它的 process-tree hard stop 为
`2,228,187,136 B >= 2,000,000,000 B`；本 L0 不重跑 FC3，也没有把 FC3 的
regional/top spectral objects 带入新账本。

## 1. 身份、ABI 与轻量资源预检

| 字段 | 实值 |
|---|---|
| canonical worktree | `/home/shenjh/Projects/MyFEniCSx_task37_extra`，`.git-codex`，`canonical=true` |
| branch / HEAD | `codex/20260820-task38-extra-full3d-iterative-0p7nm` / `6006034e19c0dcf32a874bf9f074db8d85b868cb` |
| upstream / ahead-behind | `origin/codex/20260820-task38-extra-full3d-iterative-0p7nm` / `0/0` |
| merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| executable | `/home/shenjh/MyFEniCS-Surrogate/.venv/bin/python`；Linux qualified stack |
| MPI / PETSc | Open MPI `4.1.6`；PETSc `3.19.6` |
| petsc4py / slepc4py / dolfinx / basix / scipy | `/usr/lib/petscdir/petsc3.19/...-complex` Linux ABI；DOLFINx `0.10.0.post2`；Basix `0.10.0`；SciPy `/usr/lib/python3/dist-packages/scipy` |
| scalar / index | `numpy.complex128` / `numpy.int32` |
| threads | `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1` |
| MemAvailable | `13,163,592 kB` |
| system swap | total `41,943,040 kB`，free `41,926,804 kB`，used `16,236 kB`；本表不是 worker swap Gate |
| process-tree/cgroup swap | no worker was launched in L0；`not_measured`，不冒充 formal `swap=0` |
| disk free | `941,945,712,640 B` |
| concurrent heavy jobs | none observed |
| sandbox note | sandbox singleton PMIx listener probe失败；同一 qualified activation 的受控 non-sandbox ABI/smoke通过；这不是数值结果或源码失败 |

## 2. 历史差异与证据边界

| 来源 | 只读身份与事实 | 新路线如何不同 |
|---|---|---|
| Task011 | `docs/task011_low_memory_ams_hx_iterative_solver/outcomes/summary.md`，SHA-256 `75d258cbb5efdf4b6dcb1b86d4b4640c08302cdb0f81edb7d3e56231c65af3e9`；complex hypre AMS minimal path 出现 malloc invalid size / signal 11 | 不使用 hypre/AMS；使用当前 PETSc complex ABI 的 native scalar PCGAMG |
| Task013 | `docs/task013_real_split_ams_hx_qualification/outcomes/summary.md`，SHA-256 `0772fa715062fa952ad5ed1ce5a927fe4d3c28c081aac7560045fe521d0ce8d7`；real-split FE-only p2/h5 best residual `9.964e-7`、RSS `1.323 GB` | 不做 2N real split；LOR matrices 在 complex PETSc ABI 中保存正系数，不复制 real/imag hierarchy |
| Task014a | `docs/task014a_real_split_stage4_reduced_block_pc/outcomes/solver_profile_ranking.md`，SHA-256 `c6ae17fcc591c195f2f4acb789180d112b3c2c236b7d90b8e89462a5bf40e5d8`；reduced Stage4 未形成可用收敛 | 不复用旧 Stage4 auxiliary/DtN block；只在 positive volume auxiliary 上做 LOR-HX |
| Task023 | `docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md`，SHA-256 `942a45a64b2b0a62f51e7f4e64c2ed1bb5c230a6016a5c7b635f196b11c4b479`；h2 assembly `7.37 GB`，ASM/ILU `8.95 GB` | 不组高阶 global AIJ、Schur 或 local LU；先闭合低阶结构预算 |
| Task024 | `docs/task024_engineering_iterative_solver_fast_track/outcomes/summary.md`，SHA-256 `851e1fd4d86989747a4a571363a8a61760ff6f00799be2c6d1f1c7c2550a62eb`；m=1 full residual 约 `0.15–0.18` | 只把历史资源/收敛边界当负证据，不把旧 same-H1 hierarchy 迁入 |
| Task037 M3a | 只读 remote branch `origin/codex/20260806-task37-iterative-extra-development`，tip `b8785c53ce12986aa5a63300038c80c7d0ad1798`；`task37_m3a_mpi_scaling_v1.json` SHA-256 `12826f33487e85bf26b81fe6a5f6072989fb318f7ac80055bd520724a45b4400`；MPI1/2/4/8 authority `4.600/5.683/8.266/12.593 GiB`，global static-factor CSR estimate `1,828,829,728 B` | 只证明旧 global/slab factor 路径不可迁移；新路径无 global factor/direct coarse |
| Task037 h2a | remote `benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache.json`，SHA-256 `2af81d454b89d63e1a5d03916286b527112dd76da34259712e73557918516c9c`；24 classes/16 unique，retained `201,933,812 B`，peak `717,139,968 B`，solve residual `4.8619e-11` | 只作 bounded owner-local class 参考；不是新路线代码或 Gate |
| Task037 h2b | remote `.../h2b_row_complete_patch_exactclass_v4.json`，SHA-256 `2f1862043f9e75002f53230eee86f8c6ee68ac389b319397bd71b3bdd93fc75b`；882 rows，dense `12,446,784 B`，factor `12,450,312 B`，peak `767,352,832 B` | 不迁移 dense factor；LOR capacity 只使用 structured sparse pattern |
| Task037 M3Y | remote `.../m3y_full_packed_patch_store.json`，SHA-256 `f40d6e27c628b946f9ff735027e966cd192748322aa29f752f27ebc4daeab979`；packed store `523,357,632 B`，isolated stage `1,280,749,568 B`，builder `1,068,343,296 B` | 只作为 cold/JIT 历史校准；不把旧 stage peak 与新 online live set 相加 |
| T2 exact action | `outcomes/matrix_free_action.md`，SHA-256 `b49a0d94f2a3af0a253fbd689c6d8c8773ae058d1a707854b49fe23ba2295de55`；p6/h10 MPI1 action identity `7.263059324300498e-17`、rows `173802`、T2 setup self RSS `951,054,336 B` | 作为当前 high-order matrix-free baseline；T2 retained 不重复加到 baseline |
| T3 exact DtN | `outcomes/dynamic_dtn.md`，SHA-256 `035ec128f70768a9ffa1258d3fac9495eda1c13905e71ae396b41a7543ffb957`；retained `2,875,480 B` + batch work `256 B`，action identity `1.5267729283364925e-16` | 只以 `2,875,736 B` 增量计入；DtN 仍只属于 exact physical A，不进入 positive auxiliary |
| FC3 closed family | `outcomes/records/n2_local_spectral_setup_mpi1_v3.json`，SHA-256 `5ca647ad42e304a9fc9733bc5271ffa4269bbddf1150ff5211f13a6fea0b00f0`；peak `2,228,187,136 B`，hard stop；后续 family 已关闭 | 不恢复 trace-harmonic/regional/top spectral coarse；不携带 FC3 objects、参数或 code |

L0 的新实现迁移数为 `0`：没有从 Task011–024 或 FC3 整体迁移代码、factor、hierarchy
或 record schema。允许复用的只是当前分支已资格化的 T2/T3 exact action、T4
MPC/Floquet topology、canonical packet 和 watchdog/provenance 约定。L0 未修改
`src/`，因此新 production implementation surface 仍为 `0`；L1 若获授权，才会
在新的、与旧 spectral family 分离的 `src/solvers/` 模块中开始。

## 3. PCGAMG complex capability smoke

L0 做了两个 4×4 scalar SPD PETSc 小烟测。第一次默认 PCGAMG 只作为诊断，实际树的
coarse branch 为 `bjacobi`/`lu`，因此没有拿默认值当资格结论。随后用唯一冻结的
无直粗网格配置重做一次：

```text
pc_type=gamg
pc_gamg_type=agg
mg_coarse_pc_type=jacobi
mg_coarse_ksp_type=preonly
```

该 qualified smoke 的 `setup/apply` 成功，输出 finite，repeat relative 为 `0.0`；
实际 PC view 为 `PCGAMG`, `levels=2`, coarse PC=`jacobi`，没有 LU、Cholesky、
PCLU、PCREDUNDANT 或 rank-0 direct factor。它验证的是 PETSc 3.19 complex ABI 的
能力和“禁用 direct coarse”的可配置性，不是 p2/p6 PDE 或 HX convergence。

本次 qualified non-sandbox smoke 的实际入口是下面的同一 shell 命令；inline probe
只创建 4×4 scalar SPD PETSc matrix、执行两次 PC apply、打印 PC tree，然后销毁
所有对象：

```bash
source scripts/activate_myfenics_wsl.sh
python - <<'PY' > /tmp/task038_v7_pcgamg_smoke.stdout 2>&1
# 4x4 SPD Mat、pc_type=gamg、pc_gamg_type=agg、
# mg_coarse_pc_type=jacobi、mg_coarse_ksp_type=preonly；
# apply twice, print FACTS and pc.view(), destroy.
PY
```

stdout raw 的 bytes=`2,568`，SHA-256=
`0b22b3adf2bc1b47e1d415dadcfe2efdb6f65bd95b1fd4cf1c7469436a2fccc7`。
这是 tiny capability raw 的 hash-bound 事实，不是 p6 resource sample。沙箱中的同一
入口先触发已知 PMIx listener failure；上述 hash 对应唯一一次受控 non-sandbox
qualified retry，未启动 worker/PDE。

## 4. 冻结的 LOR/HX 设计边界

positive auxiliary 只使用当前配置中的正体积分系数：

```math
B_L(u,v)=∫ |mu_r^{-1}| curl(u)·conj(curl(v)) dx
       + k0^2 ∫ |epsilon_r| u·conj(v) dx.
```

高阶 p=6 空间通过真实 p-refined lowest-order H(curl) edge mesh连接；LOR 的 H1
nodal space只用于 scalar corrections。HX inverse 冻结为：

```math
M_L^{-1}=S_e + G_L K_0^{-1}G_L^H
              + Σ_{q=x,y,z} Π_q K_1^{-1}Π_q^H,
```

其中 `S_e` 是一次 fixed edge Jacobi pre/post action，`omega=2/3`；`K_0/K_1`
使用同一份 native-complex scalar `PCGAMG(agg)` hierarchy，x/y/z correction sequential
复用，不保存三份 hierarchy。只允许一个 V-cycle；不引入 hypre/AMS、real split、
global direct coarse、global high-order AIJ、Schur 或 FE-sized numeric allgather。

## 5. p6/h10 LOR topology 的精确算术

现有 p6/h10 authority 给出 coarse structured cells `6×3×14=252`，每条轴做 6 倍
LOR refinement。以下 counts 是从规则网格连接公式直接得到的 exact arithmetic，尚未
声称实际 PETSc allocation measurement：

| 对象 | 公式 | exact count |
|---|---|---:|
| coarse cells | `6×3×14` | `252` |
| LOR vertices | `(36+1)(18+1)(84+1)` | `59,755` |
| LOR edges | `36×19×85 + 37×18×85 + 37×19×84` | `173,802` |
| LOR faces | `36×18×85 + 37×18×84 + 37×19×84` | `170,076` |
| LOR cells | `36×18×84` | `54,432` |
| edge AIJ local tensor pattern | `54,432×12×12` 去重 | `5,461,482` |
| scalar nodal AIJ local tensor pattern | `54,432×8×8` 去重 | `1,516,735` |
| discrete gradient incidence | `2×173,802` entries | `347,604` |

edge AIJ 的 exact complex128 value bytes 为 `5,461,482×16=87,383,712 B`，int32
column bytes `21,845,928 B`，row pointer `695,212 B`，合计 raw CSR-equivalent
`109,924,852 B`。scalar nodal AIJ 的对应 raw bytes 为 `30,573,724 B`。`G_L`
的 raw complex/int32/row-pointer envelope 为 `7,647,292 B`。三份 `Pi_q` map 以
每条 edge 的 int32 target、complex128 coefficient和 row-pointer 存储，精确数组尺寸
为 `3×(173,802×20+173,803×4)=12,513,756 B`。这些不是完整 PETSc RSS；额外
allocator/object overhead 在下一节单独预算。

## 6. 完整 live-set 容量账本（十进制 B）

`central` 是正常实现的预算口径，`hard_upper` 是同一固定布局的保守预算上界。预算
不是测量；历史 measured 只作为基线或校准，不与别的历史峰值相加。

| live component | central | hard upper | provenance | 说明 |
|---|---:|---:|---|---|
| T2 current-self runtime baseline | 951,054,336 | 951,054,336 | measured lower-bound/calibration | 已包含 mesh/space/MPC/Python/DOLFINx 和 T2 retained `6,151,104 B` |
| T3 retained+batch increment | 2,875,736 | 2,875,736 | derived | `2,875,480+256`；T2 retained 不重复 |
| runtime/process-tree baseline uncertainty reserve | 32,000,000 | 64,000,000 | budget | current-self 不是 process-tree 上界；不与 JIT/allocator 混称 |
| LOR edge AIJ raw storage | 109,924,852 | 109,924,852 | exact arithmetic | values/indices/rowptr；complex ABI 不把值减半 |
| LOR edge AIJ PETSc overhead | 20,000,000 | 35,000,000 | budget | allocator、row map、AIJ object，不代替 raw bytes |
| scalar nodal AIJ raw storage | 30,573,724 | 30,573,724 | exact arithmetic | local 8-node tensor pattern |
| scalar nodal AIJ overhead | 8,000,000 | 15,000,000 | budget | allocator/AIJ metadata |
| `G_L` raw incidence | 7,647,292 | 7,647,292 | exact arithmetic | complex PETSc-compatible sparse representation |
| `G_L` overhead | 4,000,000 | 8,000,000 | budget | row/owner metadata |
| `Pi_x,Pi_y,Pi_z` raw maps | 12,513,756 | 12,513,756 | exact arithmetic | three maps；不保存三份 scalar hierarchy |
| `Pi` metadata/allocator | 5,000,000 | 10,000,000 | budget | bounded owner/ghost descriptors |
| local tensor transfer factors | 8,000,000 | 16,000,000 | budget | fixed p=6→LOR tensor factors；无 global transfer matrix |
| owner/ghost/MPC canonical maps | 16,000,000 | 28,000,000 | budget | 包含 orientation/Floquet key maps；不含 FE numeric allgather |
| PCGAMG hierarchy matrices | 52,000,000 | 84,000,000 | budget | scalar hierarchy增量，不把初始 nodal AIJ重复计算 |
| PCGAMG interpolation/transfer | 28,000,000 | 48,000,000 | budget | fixed maximum-level envelope |
| PCGAMG work vectors/level work | 20,000,000 | 28,000,000 | budget | one shared hierarchy，one V-cycle |
| FGMRES restart-20 basis | 114,014,112 | 114,014,112 | exact arithmetic | `(m+1)+m=41` full vectors，`41×173802×16` |
| source/residual/solution/3 work | 16,684,992 | 16,684,992 | exact arithmetic | `6×173802×16` |
| HX action transient work | 18,000,000 | 30,000,000 | budget | sequential corrections；不持有额外 hierarchy |
| JIT/allocator reserve | 120,000,000 | 180,000,000 | budget | cold staging envelope；不是 warm peak |
| watchdog/telemetry/recovery reserve | 24,000,000 | 40,000,000 | budget | marker、process samples、small recovery metadata |
| **complete total** | **1,600,288,800** | **1,831,288,800** | `sum` | 各组件同时存活的保守 envelope |

阶段最大值按生命周期而不是历史峰值求和：

| 阶段 | central | hard upper | 口径 |
|---|---:|---:|---|
| mesh/space/MPC + cold JIT/LOR structure | `1,327,589,696` | `1,470,589,696` | baseline、T3、LOR sparse/map payload、JIT reserve、baseline reserve |
| hierarchy build | `1,427,589,696` | `1,630,589,696` | 上一阶段加 hierarchy matrix/interpolation/work |
| online + FGMRES restart20 | `1,600,288,800` | `1,831,288,800` | complete retained/work/telemetry live set |
| complete workflow max | **`1,600,288,800`** | **`1,831,288,800`** | `max(stage)`，不是阶段相加 |

M3Y 的 `1,280,749,568 B` 是不同 local-factor 路线的 isolated JIT stage measurement，
不能替代本路线 cold watchdog，也不能与上表 online total 相加。上表对本路线的
JIT/allocator 已有明确 `120/180 MB` reserve；若实现无法在该固定 envelope 内闭合，
那是后续 L3 的真实 hard stop，而不是通过改口径解决。因而本 L0 的 `major unknown`
为 0 的含义是“无未计入类别”，不是“所有预算项目都已测量”。

## 7. 生命周期、禁止项与后续 Gate

固定顺序是：qualified preflight → mesh/space/MPC/Floquet 与 cold JIT → LOR topology
和 sparse positive matrices → transfer/maps → 一个 scalar PCGAMG hierarchy → HX
one-cycle apply → outer FGMRES screen。高阶 T2/T3 exact action 只在 fine operator
保留；positive `B_L` 不包含 dynamic DtN，也不把 physical source/residual 用于
构造 hierarchy。

L0 已闭合且明确为 false 的项：

```text
high_order_global_aij = false
real_imag_hierarchy_duplication = false
global_direct_coarse_factor = false
global_schur = false
fe_sized_numeric_allgather = false
per_rank_full_basis_replication = false
hypre_ams = false
candidate_a_b_c = false
fc3_reopened = false
```

L1 只允许验证 high-order↔LOR 的 local tensor action、de Rham commuting、orientation/
Floquet/MPC phase-once、MPI1/MPI2 canonical identity 与 spectral equivalence。L0 不
宣称这些 algebra Gate 已通过，也不宣称 `<2 GB` 已实测。任何 L1/L2 identity、ABI、
swap、forbidden materialization 或后续资源 Gate 失败，都必须保留 raw/compact 并
停止，不得扫描 transfer、PCGAMG 或 mode 参数。
