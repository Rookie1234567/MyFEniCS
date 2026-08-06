# Task037 Response V5：Candidate F F0b 理想容量裁决

## 1. 执行边界与结论

本轮只执行了一次 serial F0b 测试。它使用冻结的 p6/h10 局部 slab、exact-sequence 的 p6 → p4 → p2 层级，以及 B4 四步 local family。结论只适用于这组冻结问题与这条 candidate family，不泛化为所有 p-multigrid 方法。

“残差”是把候选修正代回离散方程后剩下的误差；这里统一使用相对二范数 $\rho=\lVert r-Az\rVert_2/\lVert r\rVert_2$。`I` 是改善倍数，由 B4 残差除以相应修正后的残差得到。

| 项目 | 结果 |
|---|---|
| Task / candidate | Task037 / Candidate F |
| 阶段 | V5-3/V5-4 |
| implementation Gate | PASS |
| science capacity Gate | controlled scientific negative |
| 精确分类 | `P6_P4_P2_FAMILY_CLOSED_ON_FROZEN_CAPACITY_ORACLE` |
| ordinary defaults | unchanged |
| production qualification | false；研究性证据，不是 production solver 资格 |
| 适用范围 | 冻结 p6/h10 局部 slab、exact-sequence p4/p2 hierarchy、B4 四步 local family |

唯一命令是 `python -m pytest -q -s -x src/test/test_248_task037_candidate_f_f0b_capacity.py::test_f0b_decisive_capacity_oracle`，实际只启动 1 个 serial pytest 进程。`pytest` 的 1 failed 是测试内预设的科学关闭哨兵，不是 implementation failure，也不能写成测试通过。

## 2. 五类 correction 与理想容量含义

“minimum-residual”指在给定搜索空间里直接寻找使残差二范数最小的系数；它是该空间能提供的理想容量上界，不是生产求解器。所有最小残差问题都用 `scipy.linalg.lstsq(..., lapack_driver="gelsd")`，即秩揭示的 SVD 路径；没有使用 normal equations。

| correction | 做法 | 本轮用途 |
|---|---|---|
| diagonal-only | $z_D=D_6^{-1}r$ | 单独观察 p6 对角修正 |
| p4 Galerkin-only | $z_G=P_{46}A_4^{-1}P_{46}^Hr$ | 观察当前 p4 Galerkin correction |
| multiplicative D → G | 先算 $z_D$，再对 $r-A_6z_D$ 做 p4 Galerkin correction | 区分 additive 与顺序作用 |
| p4-MR | 在完整 `range(P46)` 中最小化残差 | 给 p4 trial space 的理想容量上界 |
| B4 + p4 augmented-MR | 在实际四步 Arnoldi basis 与 `P46` 的联合空间中最小化残差 | 给当前 B4+p4 组合的理想容量上界 |

B4 basis 与 `FactorFreeLocalSlabKrylovPc._fixed_step_gmres` 同序构造，并与实际 B4 residual 对齐到 $10^{-12}$ 以内。此次 p4-MR 和 augmented-MR 只用于裁决容量，不能被解释为已经实现或资格化的生产 preconditioner。

## 3. 三类 source 的主结果

下表的所有 `rho` 是 measured；`I4` 与 `Iaug` 是由 measured residual 计算的 derived quantity。`D0 frozen` 是 Candidate D0 的冻结对照，不是本轮 diagonal-only 的结果。

| source | $\rho_{B4}$ | $\rho_D$ | $\rho_G$ | $\rho_{DG}$ | $\rho_{p4MR}$ | $\rho_{aug}$ | $I_4$ | $I_{aug}$ | $\rho_{D0\ frozen}$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| low | 0.24599945418880292 | 0.8659810034369345 | 0.7064196292266616 | 0.7046020895141476 | 0.5123881456570735 | 0.19288646052129424 | 0.4801037187801047 | 1.2753588485369356 | 0.2540230551088513 |
| high | 0.2465189643617165 | 0.8828368769585927 | 0.8927483160663825 | 0.6544183945365035 | 0.7468190953365038 | 0.18295415440920001 | 0.3300919404727316 | 1.3474357286817646 | 0.26531876351572775 |
| mixed | 0.2461297192181731 | 0.8577324302601345 | 0.7992926346930095 | 0.6549793370724306 | 0.6421941395092988 | 0.18991184302694836 | 0.38326372676997805 | 1.2960209078864422 | 0.2715867504171219 |

本表不列旧 additive F0；旧 F0 是对同一原 residual 直接相加 p4 Galerkin 与 diagonal 的前轮对象。本轮分别给出 diagonal-only、p4 Galerkin-only、multiplicative D → G、p4-MR 和 augmented-MR。`rho_D0_frozen` 只是冻结的 Candidate D0 对照，不能改称 diagonal-only。

## 4. QR/SVD 与实际 B4 搜索空间审计

每行的 `raw LS` 是最小二乘残差的未归一化二范数；`normalized LS` 是除以 source 范数后的值。`raw orth` 是 $\lVert Y^H\,residual\rVert$，`normalized orth` 是按矩阵与 residual 范数归一化后的审计量。`repeat rank/error` 是同一 `gelsd` 求解重复执行的稳定性审计。

### 4.1 B4 四步 Arnoldi basis

| source | rank / repeat rank | condition | singular count / max / min retained | raw LS | normalized LS | raw orth | normalized orth | repeat error | rho basis / actual |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| low | 4 / 4 | 10.893310885537534 | 4 / 7.397928053004939 / 0.679125761739415 | 0.24599945418880273 | 0.24599945418880267 | 1.3927942683499392e-14 | 6.070342204640527e-15 | 0.0 | 0.2459994541888029 / 0.24599945418880292 |
| high | 4 / 4 | 11.287274614379351 | 4 / 7.307981364125713 / 0.647453137608237 | 0.24651896436171583 | 0.24651896436171578 | 1.6725082228576203e-14 | 7.332483550849472e-15 | 0.0 | 0.2465189643617165 / 0.2465189643617165 |
| mixed | 4 / 4 | 11.046963515720538 | 4 / 7.340782572876754 / 0.6645068178626958 | 0.2461297192181738 | 0.2461297192181738 | 1.718532553291746e-14 | 7.538788936888509e-15 | 0.0 | 0.24612971921817303 / 0.2461297192181731 |

### 4.2 p4-MR 空间

| source | rank / repeat rank | condition | singular count / max / min retained | raw LS | normalized LS | raw orth | normalized orth | repeat error |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| low | 192 / 192 | 11.868427740843005 | 192 / 8.423805704445492 / 0.7097659343247731 | 0.5123881456570736 | 0.5123881456570735 | 1.675186561951292e-14 | 6.389146178583111e-16 | 0.0 |
| high | 192 / 192 | 11.868427740843005 | 192 / 8.423805704445492 / 0.7097659343247731 | 0.7468190953365039 | 0.7468190953365038 | 1.3150179966543857e-14 | 3.441081828164496e-16 | 0.0 |
| mixed | 192 / 192 | 11.868427740843005 | 192 / 8.423805704445492 / 0.7097659343247731 | 0.6421941395092988 | 0.6421941395092988 | 1.4828941848038596e-14 | 4.512555348052858e-16 | 0.0 |

### 4.3 B4 + p4 augmented-MR 空间

| source | rank / repeat rank | condition | singular count / max / min retained | raw LS | normalized LS | raw orth | normalized orth | repeat error |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| low | 195 / 195 | 17.7082965505731 | 196 / 10.287111905389262 / 0.5809204671951542 | 0.19288646052129427 | 0.1928864605212942 | 6.359420298421868e-14 | 6.338660679418012e-15 | 0.0 |
| high | 196 / 196 | 20.114548875872902 | 196 / 10.197602474050766 / 0.506976444611325 | 0.18295415440920013 | 0.1829541544092001 | 6.516327906159103e-14 | 6.849410270473222e-15 | 0.0 |
| mixed | 196 / 196 | 20.42927580105611 | 196 / 9.984037252691087 / 0.48871224559878684 | 0.1899118430269483 | 0.1899118430269483 | 4.794546511880221e-14 | 4.854835689263319e-15 | 0.0 |

三类 source 的 p4 Galerkin repeated solve error 都是 `0.0`；所有 solution、singular value、residual 和审计标量均 finite。

## 5. Implementation Gate

| Gate | 阈值 | 实测 | 判定 |
|---|---:|---:|---|
| P26 与 P46@P24 nested relative error | ≤ $10^{-11}$ | 5.557279606005943e-16 | PASS |
| P24 adjoint identity | ≤ $10^{-11}$ | 4.945975109804328e-16 | PASS |
| P46 adjoint identity | ≤ $10^{-11}$ | 3.441690023284426e-16 | PASS |
| $Y_4=A_6P_{46}$ action identity | ≤ $10^{-11}$ | 5.767608963170237e-16 | PASS |
| all LS solutions / metrics finite | true | true | PASS |
| repeated LS error | ≤ $10^{-12}$ | 0.0 | PASS |
| p6 matrix / factor / NNZ | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| ordinary defaults | unchanged | unchanged | PASS |

## 6. Transfer、factor inventory 与资源

| 项目 | 实测值 |
|---|---:|
| P24 coarse/fine degree | 2 / 4 |
| P24 NNZ | 96 |
| P24 trace interior dependency max | 5.8889452311529e-16 |
| P46 coarse/fine degree | 4 / 6 |
| P46 NNZ | 291 |
| P46 trace interior dependency max | 1.725758366989246e-14 |
| p6 / p4 / p2 rows | 432 / 192 / 48 |
| p4 matrix shape | 192 × 192 |
| p4 matrix / factor NNZ | 36864 / 36864 |
| p4 matrix payload | 589824 bytes |
| p4 LU payload | 590592 bytes |
| transfer payload | 1474560 bytes |
| retained oracle payload | 2698752 bytes |
| construction workspace lower bound | 147456 bytes |
| p6 matrix/factor materialized | false / false |

本次资源数字来自一个 serial tiny F0b local oracle 进程：wall `4.92s`，user `3.97s`，system `0.32s`，MaxRSS `217804 kB`，swap `0`。它不是正式 PDE solver peak，也不能外推为 Full3D 求解内存。

## 7. Science capacity Gate

V5 的容量通过条件要求 high 与 mixed 均同时满足 $I_{aug}\ge1.5$ 且 $\rho_{aug}<0.15$；正式关闭条件是 high/mixed 同时落入任一失败侧（$I_{aug}<1.5$ 或 $\rho_{aug}\ge0.15$）。实际结果如下。

| source | $I_{aug}$ | $I_{aug}\ge1.5$ | $\rho_{aug}$ | $\rho_{aug}<0.15$ | 结论 |
|---|---:|---|---:|---|---|
| high | 1.3474357286817646 | false | 0.18295415440920001 | false | family closed |
| mixed | 1.2960209078864422 | false | 0.18991184302694836 | false | family closed |

high 与 mixed 各自都同时满足相反的关闭证据：$I_{aug}<1.5$ 且 $\rho_{aug}\ge0.15$。因此正式分类是 `P6_P4_P2_FAMILY_CLOSED_ON_FROZEN_CAPACITY_ORACLE`。

由于 p2 trial space 嵌套在完整 p4 trial space 中，连完整 p4 空间与 B4 联合空间的理想最小残差容量都没有达到 Gate，冻结问题下仅使用其子空间 p2 不会超过这个理想界。这是本轮的科学含义；它不是对所有 p-multigrid、其他离散、其他 source 或生产 solver 的普遍断言。

## 8. Provenance 与 artifact

测试源 SHA、HEAD 和 upstream 都是 `6e7b0103e9192bbf9fed5113838572fbb842c2ab`；branch 是 `codex/20260803-task37-matrix-free-iterative-development`，测试时工作树 clean，ahead/behind 为 `0/0`。qualified ABI 为 PETSc complex128/int32，MPI size 为 1。

底层 pytest command 是 `python -m pytest -q -s -x src/test/test_248_task037_candidate_f_f0b_capacity.py::test_f0b_decisive_capacity_oracle`。实际测量使用的 timed wrapper 是 `/usr/bin/time -v -o benchmarks/artifacts/task037/v5_f0b_6e7b0103/time_v.txt python -m pytest -q -s -x src/test/test_248_task037_candidate_f_f0b_capacity.py::test_f0b_decisive_capacity_oracle > benchmarks/artifacts/task037/v5_f0b_6e7b0103/stdout.log 2> benchmarks/artifacts/task037/v5_f0b_6e7b0103/stderr.log`；两者均保留在 provenance 中。

唯一 artifact 根目录是 `/home/Projects/MyFEniCS/benchmarks/artifacts/task037/v5_f0b_6e7b0103/`。

| 相对路径 | bytes | SHA256 | data class |
|---|---:|---|---|
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/stdout.log` | 19814 | `7aaf7296a9b30c358830539631e2e0aaaa79326d5e34064a1a6bd7662956e892` | measured raw |
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | measured raw |
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/time_v.txt` | 881 | `cee1629b0da62ade0124116bc554d4979eed533111f8644c20445acc58dd286c` | measured raw |
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/exit_code.txt` | 2 | `4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865` | derived_post_run_metadata |
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/exact_command.txt` | 308 | `c78396d20570aec8f34ce6a3796b0d1e593c50a5c85cbadd2c884f3fc120022a` | provenance |
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/preflight.stdout.log` | 588 | `b93c7a6497c8a1a9c6dc79bd5ee2f9bf8be28e90400515c1a09a3f19964a5448` | measured raw |
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/preflight.stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | measured raw |
| `benchmarks/artifacts/task037/v5_f0b_6e7b0103/preflight_exit_code.txt` | 2 | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` | measured raw |

`exit_code.txt` 的 wrapper 未能自动落盘，是因为 `set -e` 在 pytest 返回 1 后提前结束；没有第二次运行。该文件仅依据 pytest summary 与 `time_v.txt` 的 Exit status=1 补写，不能冒充原始测量。

## 9. 阶段状态与停止边界

| 阶段/候选 | 状态 | data class |
|---|---|---|
| V5-1 实现与静态 Gate | completed | measured |
| V5-2 唯一 serial F0b | completed | measured |
| V5-3 scientific classification | completed | derived |
| V5-4 compact record / response 草稿 | completed docs-only | derived |
| Candidate E | not_run | not_run |
| heavy PDE | not_run | not_run |
| MPI > 1 | not_run | not_run |
| Hybrid | not_run | not_run |
| 0.7nm | not_run | not_run |

本轮不启动 Candidate E，不开展 Hybrid、0.7nm、重型 PDE、MPI 扩展、调参或任何重跑。生成这两份文档后即停止，等待主审审查。
