# V17 Oracle A：exact p3 coarse span

## 结论

这是一次已完成、证据有效的窄诊断。它问的是：把 p6/h10 checkpoint 的残差投影到 p3，是否能由一个与现有 matrix-free physical operator 同源的 p3 assembled diagnostic operator 修正回来。它不是 full PDE，也不是生产 preconditioner。

`checker.json` 的 `status=PASS`、`evidence_valid=true` 表示 raw 证据完整且独立重算通过；机制结果是 `EXACT_P3_COARSE_SPAN_FAIL`，唯一 Gate failure 是 `rho_ref`。因此这是有效的数值负结果，不是基础设施失败。

| 项目 | 实测/派生结果 | 判定 |
|---|---:|---|
| A1 checkpoint reproduction | stored `0.4837947981092168`；重算 `0.48379479479924`；absolute `3.309976792653657e-9`；relative `6.8416957056789795e-9` | PASS，limit `1e-8` |
| A1 residual norms | `||r6||=0.6412077991519657`；`||r3||=0.39933395062332444` | finite |
| A2 p3 direct residual | `3.5516052364193747e-12` | PASS，limit `1e-10` |
| A3 coarse residual | `rho3=4.298361509181443e-12` | PASS，limit `1e-6` |
| A3 fine residual | `rho_ref=20.97573925716883` | FAIL，limit `0.70` |

`rho_ref` 的计算是 `||r6_new||/||r6||`；raw 中 `||r6_new||=13.449807604674712`，而 `||r6||=0.6412077991519661`。这说明 p3 correction 在 coarse projected space 内几乎消除了 p3 残差，却把 fine physical residual 放大了约 21 倍。A1、A2 和 A3 的 canonical dual/primal packet、MPC facts、input hashes、finite facts 和 operation counts 均闭合，故不能把该结果归咎于缺失数据。

## 冻结的数学路径与生命周期

1. A1 用同一 physical p6 action 重建 `r6=b6-A6*x1000`，再用 owner-distributed `P63^H` 得到 `r3`。
2. A2 只构造 p3 diagnostic operator，求 `A3 e3=r3`；矩阵是 diagnostic-only global AIJ，`production_global_aij=false`，没有把它提升为生产 PC。
3. A3 形成 `e6_full=P63 e3`，验证它是满足 Floquet/MPC 约束的 full physical primal；随后按已资格化路径 homogenize 成 slave-zero `e6_algebraic`，且 A6 只作用于这个 algebraic 输入：`r6_new=r6-A6 e6_algebraic`，再算 `r3_new=P63^H r6_new`。
4. A1→A2→A3 是同一 parent 内的顺序 heavy child；每个 stage 自然退出并释放对象后才进入下一 stage。parent process-tree peak 为各阶段的最大实测值，不是对象体积求和。

| stage | rows/NNZ 或资源事实 | 结果 |
|---|---|---|
| A1 | p6 residual reconstruction；peak RSS `1,487,446,016 B` | return `0` |
| A2 | degree 3，rows `23,073`，global NNZ `5,907,213`；static condensation `false`；diagnostic global AIJ `true` | return `0` |
| A2 MUMPS | preferred ordering `external`；MUMPS internal auto `ICNTL(7)`；symbolic/numeric/solve `1/1/1`；INFOG16 `424` | predicted peak `977,725,952 B < 12,000,000,000 B` |
| A3 | p3 residual and both rho values measured from raw vectors | return `0` |

A2 的预测公式是 `post-analysis process-tree RSS + max(INFOG16,0)*1,000,000`，即 `553,725,952 + 424,000,000 = 977,725,952 B`；它不是 `Mat.getInfo()["memory"]` 的替代猜测。该 run 未触发 12 GB resource block。

## 物理字段与 canonical authority

`e6_full` 是恢复后的 full physical primal，owned slave 非零并不代表错误：owned slave count `9210`、max `1.4400418062523395`，fine MPC constraint residual `0`，transfer shared-row defect `1.807312143953211e-15`。A6 的实际输入是另一个 raw descriptor `e6_algebraic`，其 owned slave count/max 为 `0/0`。A3 action、`r6_new`、`r3_new` 也均为 slave-zero dual；action input SHA 与 `e6_algebraic` SHA 均为 `f83a1f24a5ece98ec5b9f618f22a007515f8c00321801c806ffd0fe5d26d93b6`。

| role | kind | key-inventory SHA | manifest SHA |
|---|---|---|---|
| A1 `r6` | p6 dual | `c0daa91cb698aa96eb6397988a84b49212777afb7f8ac478f3beddc816a1f66a` | `08b89de5aba5d6bf28815e093957520a45ec13373dcaaa4c8c105961f9013bf0` |
| A1 `r3` | p3 dual | `e066581db97e33212bf8696de2c6f9ad4b6a1795915bd49efbe7835ca8f7f2e9` | `cf243ee3d03ae34e2b80bf8f60baadfac4ad64d6f742da509681c6300fa9e750` |
| A2 `e3` | p3 primal | `8985ac2ce1774a0a3463ba25fd8a8f8dde06e5d15b7ca0f25055e9592dd1cd02` | `b2a8896ab22bfb07c6f445fffe4ae51099d6e312468b4ed526c432e496ac8669` |
| A3 `e3_loaded` | p3 primal | same as A2 | `95ea85de322cc491a94ec49f79ac8e24332cee799428c0a20abe548be31b5bea` |
| A3 `e6_full` | p6 primal | `32118b7bf66ad8e8a52dbc16c1cf2e72e61602b862a00cd105ab277365036c28` | `3a9fc6402d3579de514457c82c47c47ab598588f612e679d414ac35384cc3cc1` |
| A3 `action` | p6 dual | same as A1 `r6` | `4a8aeaa345186a83fdf9961abc258d4966049357c0bbe2b9f770aab4c369791e` |
| A3 `r6_new` | p6 dual | same as A1 `r6` | `20d8e92327e67dddfb59efc7091b470f354bafd2def3ba069cbb7e4a0efbcdc9` |
| A3 `r3_new` | p3 dual | same as A1 `r3` | `68ea105e88a645177dc1fc86cc6eec5efce4321bee7175074053319a359600cc` |

The A3 raw records independently bind `e3_loaded` to the A2 descriptor; source and loaded array SHA are both `7a4fd736741118cdd1bbdfac148cfda1f5f9303d7a87a8b5e6ed4db5deea7b2b`. The canonical packet writer uses rank shards and metadata only; it does not perform numeric allgather.

## Evidence index and boundary

Artifact root: [`v17 Oracle A v3`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v17_oracle_a_v3/d521d85ed63535a2c9bb03e44fe9f7a5e8d394e7/mpi1)

| file | SHA256 |
|---|---|
| `parent_record.json` | `cf5b2c08ec2bbfc68d938edf5a28062c566e95fe5b266538fe7c93114df52b56` |
| `raw/A1_record.json` | `8777c2e0bc69cb4f8e2f02ce918f6ab528875c00c2937ba80fb7045f28f50f90` |
| `raw/A2_record.json` | `4169ee36e10a74d59c07f16fa3205b3e6dd587a2300365151a81543c54984ea9` |
| `raw/A3_record.json` | `5628bfff1b7e509556c9bac6647d7dcfd36e553f795f43d020a3a5469257a3ea` |
| `checker.json` | `49b62a9a3f04269785fcc5066c7a7aa71c761f398ae513a73d64d742bebfddc3` |
| `marker_manifest.json` | `4c01645ac9e9ce8f65ca6fc0929b3c27bd047107579a956dd375785bc6efaf82` |

The A3 result closes this exact-span experiment only. It does not authorize A/B recovery, a 20,000-step PDE, a production physical coarse PC, Oracle B, or any later PC family.
