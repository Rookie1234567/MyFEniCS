# Task038-extra T4 sweep/oracle evidence

## 1. 作用与边界

T4 验证的是两层三维子域之间的传输边界动作：给定一个有限元场，candidate A 在真实 interior facets 上施加切向一阶 Robin/impedance 弱式，并把结果传回 owner-local trace。它验证数据限制/延拓、Floquet 约束和传输动作是否一致；它不是 Maxwell PDE 求解，也没有 KSP、全局界面矩阵、dense Schur 或 slab factor。

每个 case 使用同一非平凡斜入射方向（theta=21.131°, phi=33.690°）的固定 s/p 两个解析源，测试场是固定的 `0.6+0.1i` s 与 `0.35-0.2i` p 线性组合。独立 oracle 用 fresh scalar facet quadrature pairing 检查 candidate output；checker 只读取 record/raw manifest，不导入或执行 runner、solver、PETSc、MPI。

## 2. Provenance 与正式 case

| item | value |
|---|---|
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| upstream | `80c3fa29d54813d0344a93ffa7768108ff15fa76` |
| T4 implementation SHA | `8560488d9bafbd608f9dc7c419815f9a632d46af` |
| T4 evidence-fix SHA used for formal v2 | `88e5cef8a007445270721b9076b0c33453f743f3` |
| branch relation at v2 formal | ahead 11 / behind 0 |
| expected/start/end SHA in every v2 record | `88e5cef8a007445270721b9076b0c33453f743f3` |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| profile | `full3d_scalable_v1` |
| slab count | 2 |
| transmission | `first_order_impedance_robin_v1` |
| official physics | not run |

正式输入是四个冻结组合：p2/MPI1、p2/MPI2、p3/MPI1、p3/MPI2，mesh target 为 50 nm。四次 runner 均使用新的 ignored 根目录 `benchmarks/artifacts/task038_extra_full3d_iterative_t4_formal_v2/`；tracked evidence 只在四次 runner、checker 和 aggregate 全部通过后生成。

## 3. Formal 数值与资源结果

| case | runner wall | global/local facets | owned trace rows | max oracle relative error | R/P adjoint | reconstruction max | warm RSS span | swap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| p2 MPI1 | 1.64 s | 6 / 6 | 48 | `8.6902e-16` | 0 | 0 | 1,409,024 B | 0 B |
| p2 MPI2 | 9.00 s | 6 / 6 | 48 | `5.1927e-16` | 0 | 0 | 1,363,968 B | 0 B |
| p3 MPI1 | 2.13 s | 6 / 6 | 108 | `9.6792e-16` | 0 | 0 | 1,683,456 B | 0 B |
| p3 MPI2 | 9.17 s | 6 / 6 | 108 | `1.1347e-15` | 0 | 0 | 1,667,072 B | 0 B |

每个 case 有两个 source、两个方向、两个 repeat，共 8 次真实 apply；每次 apply 后记录 elapsed、rank-max current self RSS 和当前进程 `VmSwap`。所有 repeat relative differences 为 0。四个独立 checker 均为 `T4_PASS`，aggregate 为 `T4_AGGREGATE_PASS`，精确包含四个 case。

两种 degree 的 topology canonical digest 分别为：p2 `8a325f1de93fbe250235b4a89280007f6bb51a51d9deda80f0698344633f9afa`，p3 `1c60a381f4b5e807328bc5f7c82622f4bff535a1bc260ba0d8fed3046bf97512`。MPI1/MPI2 的 source 和四组 action physical packet key identity 均相同；aggregate 的最大 cross-MPI relative L2 为 `7.1149e-15`，限值 `1e-12`。四组均报告 homogeneous 与 nonhomogeneous interface classes、nontrivial Floquet phases、`finalized_floquet_mpc_once`、slave-row exclusion 和 owner closure。

## 4. Retained payload 与 bounded work

| degree / MPI | retained numeric bytes (local / global-max) | bounded temporary work per apply |
|---|---:|---:|
| p2 / 1 | 45,696 / 45,696 B | 10,368 B |
| p2 / 2 | 30,192 / 30,624 B | 10,368 B |
| p3 / 1 | 127,296 / 127,296 B | 27,648 B |
| p3 / 2 | 84,936 / 85,968 B | 27,648 B |

forward/backward 的数值 payload 与 work 均分别记录在 compact record 中。所有 forbidden materialization audit 均为 false：numeric allgather、global AIJ、dense interface mass/Schur、slab factor 均未发生。process-tree peak 明确为 `not_measured_t4`，不能从这些 rank-local RSS samples 推导 process-tree 峰值。

## 5. v1 负证据与 v2 修复

v1 使用 implementation SHA `8560488d9bafbd608f9dc7c419815f9a632d46af` 的 p2/MPI1 record 首次 checker 失败。真实 pairing 已通过（最大 `8.6902e-16`），但 runner 没有把首个 action output manifest 登记到 `artifacts[source_direction]`，checker 因此拒绝 evidence registry closure。该负结果没有被覆盖或删除：

- [`t4_p2_h50_mpi1_v1_evidence_defect_record.json`](records/t4_p2_h50_mpi1_v1_evidence_defect_record.json)，SHA `b562a70f225d849243a7d82b02d237484518632ed1891eb5efc5beb7d4e71682`
- [`t4_p2_h50_mpi1_v1_evidence_defect_check.json`](records/t4_p2_h50_mpi1_v1_evidence_defect_check.json)，SHA `0195869f2f787ee72949e6ef013114ecc3e8fc2db351c1336743c768e917e308`

Review V1 允许的唯一窄修只增加了该 registry assignment 和对应 contract；没有改变 action、oracle、source、mesh、MPC、apply、packing 或数值路径。v2 以新 SHA 重新完成全部四 case 后才取得资格结果。

## 6. Tracked evidence index

- [`t4_p2_h50_mpi1_v2.json`](records/t4_p2_h50_mpi1_v2.json)
- [`t4_p2_h50_mpi2_v2.json`](records/t4_p2_h50_mpi2_v2.json)
- [`t4_p3_h50_mpi1_v2.json`](records/t4_p3_h50_mpi1_v2.json)
- [`t4_p3_h50_mpi2_v2.json`](records/t4_p3_h50_mpi2_v2.json)
- [`t4_aggregate_check_v2.json`](records/t4_aggregate_check_v2.json)，SHA `c6f160facd0d843078788fd65c655aba3517d4f70017e3c003d58d8525ce5eb7`

所有 raw vectors、canonical shards、mesh/JIT files 与 console logs 仍留在 ignored artifact 根目录；没有运行 T5、T6、KSP、PDE 或 push。
