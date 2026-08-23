# Review V8 closeout response

## 1. 执行边界与最终裁定

用户明确授权针对 code bug 做分析和窄修，但没有授权放宽数值、identity、内存或 swap Gate。按 V8 §12，最终确认存在无法由单一修复关闭的 transfer/MPC/owner algebra mismatch，因此本轮停止。V8 §12 是 hard-stop authority，M1–M7 全部为 NOT_RUN_BY_M0_HARD_STOP。

最终 closeout 阶段没有修改 Python，没有重跑 formal，没有进入 M1，也没有提交或 push。旧 L2 one-apply FAIL、旧 v1 80-step FAIL、additive-v2 formally closed 以及两次 M0 negative 均不重分类。

| 本轮代码提交 | 内容与边界 |
|---|---|
| f76a30e843dcc1e3e25aee6a73df6aca12222f10 | M0 oracle、runner、checker 和 focused test implementation |
| 9f44464eda27590492dcfe0432129a126625b5cc | verified orientation placement + lattice evidence fix；不提升 ordinary default |

## 2. 身份、分支和环境

| 字段 | 值 |
|---|---|
| formal attempt2 source / pre-closeout HEAD | 9f44464eda27590492dcfe0432129a126625b5cc |
| parent | f76a30e843dcc1e3e25aee6a73df6aca12222f10 |
| branch | codex/20260820-task38-extra-full3d-iterative-0p7nm |
| frozen base / merge-base | 438caf150439343ee7c4c58ad7e02a3da812a23c |
| upstream | origin/codex/20260820-task38-extra-full3d-iterative-0p7nm |
| upstream SHA at closeout | 10e94c48e94c2cbff98422cd33d59fd6552f3028 |
| source ahead/behind | 2/0 |
| activation | tracked scripts/activate_myfenics_wsl.sh，qualified marker=1 |
| ABI | complex128、int32、Python 3.12.3、PETSc 3.19.6、DOLFINx 0.10.0.post2、Basix 0.10.0 |
| threads | OMP/MKL/OPENBLAS=1 |

.venv 的资格路径按仓库约定解析到 /home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin。正式 worker 的 MPI1 直接用 qualified Python，MPI2 用同一 activation 的 mpiexec -n 2。

## 3. Formal 命令与结果

两次 attempt 都使用同一类 M0 diagnostic worker：

    source scripts/activate_myfenics_wsl.sh
    /usr/bin/time -v python -m benchmarks.run_task038_full3d_lor_hx_root_cause --mode diagnostic --case p2-mpi1 --raw-dir <attempt-sha>/p2-mpi1/raw --record <attempt-sha>/p2-mpi1/record.json --expected-source-sha <attempt-sha> --expected-mpi-size 1
    /usr/bin/time -v mpiexec -n 2 python -m benchmarks.run_task038_full3d_lor_hx_root_cause --mode diagnostic --case p2-mpi2 --raw-dir <attempt-sha>/p2-mpi2/raw --record <attempt-sha>/p2-mpi2/record.json --expected-source-sha <attempt-sha> --expected-mpi-size 2
    python -m benchmarks.task038_full3d_lor_hx_root_cause_checker --record <attempt-sha>/p2-mpi1/record.json --output <attempt-sha>/p2-mpi1/check.json
    python -m benchmarks.task038_full3d_lor_hx_root_cause_checker --record <attempt-sha>/p2-mpi2/record.json --output <attempt-sha>/p2-mpi2/check.json
    python -m benchmarks.task038_full3d_lor_hx_root_cause_checker --record <attempt-sha>/p2-mpi1/record.json --record <attempt-sha>/p2-mpi2/record.json --output <attempt-sha>/pair_check.json

正式源路径分别是 benchmarks/artifacts/task038_extra_full3d_lor_hx_m0_v1/f76a30... 和 9f44464...；目录 fresh、worker 独占创建，旧 raw 未覆盖。两案 worker rc=0，individual checks 完成；pair check 的 9f attempt contract_errors=[] 但 gate_failures=32、passed=false。故它是数学/代数负裁决，不是启动、JIT、JSON closeout 或 orphan 失败。

9f44464 attempt2 的实际 worker 前缀为：

    /usr/bin/time -v python -m benchmarks.run_task038_full3d_lor_hx_root_cause --mode diagnostic --case p2-mpi1 --raw-dir benchmarks/artifacts/task038_extra_full3d_lor_hx_m0_v1/9f44464eda27590492dcfe0432129a126625b5cc/p2-mpi1/raw --record benchmarks/artifacts/task038_extra_full3d_lor_hx_m0_v1/9f44464eda27590492dcfe0432129a126625b5cc/p2-mpi1/record.json --expected-source-sha 9f44464eda27590492dcfe0432129a126625b5cc --expected-mpi-size 1
    /usr/bin/time -v mpiexec -n 2 python -m benchmarks.run_task038_full3d_lor_hx_root_cause --mode diagnostic --case p2-mpi2 --raw-dir benchmarks/artifacts/task038_extra_full3d_lor_hx_m0_v1/9f44464eda27590492dcfe0432129a126625b5cc/p2-mpi2/raw --record benchmarks/artifacts/task038_extra_full3d_lor_hx_m0_v1/9f44464eda27590492dcfe0432129a126625b5cc/p2-mpi2/record.json --expected-source-sha 9f44464eda27590492dcfe0432129a126625b5cc --expected-mpi-size 2

两案的 checker 只把上述 record 换成对应的 check.json；pair checker 同时传入两个 record。f76a30 attempt1 使用完全相同的 argv、顺序和直接 MPI1/MPI2 方式，仅将 source SHA 与 attempt root 替换为 f76a30e843dcc1e3e25aee6a73df6aca12222f10。

## 4. 两次 attempt 的精确事实

| attempt | record/check/pair 状态 | 关键边界 |
|---|---|---|
| f76a30 | worker rc=0；pair rc=1；pair contract_errors 含 8 个 node key-set mismatch，30 个 exact gate failures | edge orientation placement 未修 |
| 9f44464 | worker rc=0；两 individual contract_errors=[]；pair rc=1，contract_errors=[]，32 个 gate failures | edge placement 已修，但 exact nodal pair 未闭合 |

9f attempt 的 canonical 输入/edge facts 是：high source before 1.417734557397384e-15，high residual 1.6029978812022376e-15，low input 1.6864438658655413e-15，exact edge correction 1.5658061021293675e-15，exact edge action 1.7783413648977776e-15。exact nodal output relative 为 0.03757191918203578，远大于 exact component limit 1e-10。

最早 exact-nodal 分歧在 gradient：rhs 0.36157950436833775、nodal delta 0.2949106829240065、edge delta 0.1894457691797068、result 0.020169732344255478。Pi_x/Pi_y/Pi_z 的 result 分别为 0.0638917565026212、0.07786760176186892、0.05576217631355618；post result 为 0.03356471572091377。完整 component arrays 不在 Git，保留于 ignored raw。

## 5. 外层诊断 history

这是 M0 的对照诊断，不是 V8 后续 qualification。它比较 production multiplicative-v1 与 exact nodal direct replay，均为 right GMRES、restart=20、每 20 步 residual replacement、zero initial guess；完整 0/1/2/5/10/20 及边界 scalar history 在 worker record。

| path | cycles / iterations | first explicit true pass | final explicit true residual | reason | matvec / solver PC / monitor reconstruction PC / total PC |
|---|---:|---:|---:|---:|---:|
| production MPI1 | 4 / 62 | 62 | 9.276247638965869e-09 | 2 | 65 / 66 / 4 / 70 |
| exact nodal MPI1 | 5 / 82 | 82 | 9.510953881688309e-09 | 2 | 86 / 87 / 4 / 91 |
| production MPI2 | 4 / 62 | 62 | 9.431179719931108e-09 | 2 | 65 / 66 / 4 / 70 |
| exact nodal MPI2 | 5 / 84 | 84 | 9.713792528761725e-09 | 2 | 88 / 89 / 4 / 93 |

pair checker 的 exact outer final action/solution/explicit true-residual 三个 canonical vector 的 MPI1↔MPI2 relative 分别为 9.283829676136373e-09、1.142232152655208e-07、0.9557368639478777。这三个数不是任一 case 的 final residual norm；两边各自的 final true residual norm 约为 1e-8，但残差/解向量仍不是同一个 canonical 结果，因此 exact nodal route 没有闭合，不能写成 pass。

## 6. 根因边界

实际 cell permutation 诊断得到 MPI2 92 个负向 cell-edge reference、4 张 map 合计 208 个 minus factors，raw row mismatch=0。当前 placement 的 MPI2 owner roundtrip 为 0.5849607443002511；orientation-aware oracle 为 2.060948712431624e-17；first edge-pre relative 为 0.2898861945930992，修后 edge/pre 约 1e-15。这验证了 9f 的 edge orientation placement 窄修。

但 sign-only map 修复后的 gradient.rhs 仍为 0.20630212828353248。临时 owner-consistent ghost relation 将 gradient.rhs 降至 2.396070826157907e-15，同时仍得到 nodal_delta=0.11660480519091415；固定 lattice node_matrix action=0.08847380943557186。remote relation inconsistency 为 37，phase rows=220、actual slave rows=220、mismatch=0，direct nodal residual 约 MPI1 5.310854724390275e-16、MPI2 4.602617923986701e-16。

因此不能把问题描述成“只漏了一个 sign”，也不能把 37 条 owner relation 或 node matrix 结论中的任一项写成已完成 production 修复。剩余边界是 constrained rectangular maps、remote MPC relation、node-matrix representation 与 owner-additive routing 的联合代数一致性。

## 7. 资源、生命周期和证据

| case | wall | GNU time max RSS | GNU time Swaps | 口径 |
|---|---:|---:|---:|---|
| 9f MPI1 | 12.88 s | 194732 KiB = 199405568 B | 0 | 单 qualified Python 进程 |
| 9f MPI2 | 7.42 s | 192496 KiB = 197115904 B | 0 | mpiexec launcher 观察 |

这不是 process-tree/cgroup peak，也不是 p6/h10 2GB Gate。系统 swap baseline 约 16625664 B，不能与 worker Swaps=0 混称。markers 到 cleanup_end 完整，natural exit 后 no orphan。

旧 L2 record SHA 为 0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3，旧 one-apply rho=1.7348663090876784、limit=0.45，保持永久 FAIL。两次 M0 的 10 份 tracked compact 副本逐字节绑定 ignored 源，文件名以 m0_attempt1_f76_* 与 m0_attempt2_9f_* 区分；9f raw manifest SHA 为 MPI1 a3f60e350573c612492d75cf322b7434718c7cd1743a40a9da2da6c8bfde2d34、MPI2 329b58469117099cdfe2941bdde5ac18b018990a3e21ce598de0c1b2dd7e23b9。

| tracked evidence | SHA256 |
|---|---|
| m0_attempt1_f76_p2_mpi1_record / check | 47b5eb320bcfd5723c443bc803d0dcbcca2b8ce794a25fe7ee36fab2132d1876 / 7924db27543e6d8d65a97de463a8761c1dade70b853b7f0677d5c310bde37064 |
| m0_attempt1_f76_p2_mpi2_record / check | 47c8f9d5f5594cca3b00111cf8efb0824a0c47f4d408c6496ea4d4358cc0ff84 / 110695004b7bdb5889a1812c935ce2f822dd6a01f97d59e433ce7bece72d0043 |
| m0_attempt1_f76_pair_check | 94c54ac2d6c77b33c5c1dbbe6b0e6da739b585ab9a3f7fccf94e00d46fa1bf52 |
| m0_attempt2_9f_p2_mpi1_record / check | 5c038d233afefb45020f33ad2feb5b16b673a47541fcbc0e57f017522975daf5 / 50807c4916867b15051fdec6eba695f9e1123415b7542a236c6e577d1dec4841 |
| m0_attempt2_9f_p2_mpi2_record / check | 1b2545ccc3a042e201b09f3f55f4290035abd6bcd5cdc213d5490ad677fa5f6d / f26e43134610cb55eb528eab2b035f08e00c7318d6e602759ff01409eb9935e1 |
| m0_attempt2_9f_pair_check | bc5e52ca753ebfb04ee17f0196c41b4f4c3df5739549de918dd5b43732e93098 |
| m0_postfailure_diagnostic_v1 | f39d3d3eb328acfc4452ee540d21f9f5124b022c7c1263a3cdbd2923b137f22d |

## 8. 测试范围

本轮 closeout 不运行测试、不运行 formal。已实际完成且绑定 9f 代码窄修链最终状态的 focused 结果为：serial test_296 + test_300 共 12 passed、1 skipped；MPI2 test_296 每 rank 1 passed、2 skipped；compileall/diff-check 通过。这里不把它们扩写成 full pytest 或 CI，也不因本轮文档修订声称重新运行。临时诊断脚本和 NPZ 只由 m0_postfailure_diagnostic_v1.json 的 hash 绑定，不是 tracked formal pass。

## 9. 未运行与 selective merge

M1 memory-first small、M2 p6/h10 setup、M3 positive longrun、M4 physical longrun、M5 p6 MPI2、M6 h5 scaling、M7 0.7nm/2TiB feasibility 全部 NOT_RUN_BY_M0_HARD_STOP；2GB 目标、p6 setup、PDE、official physics 均未验证。

9f 的 edge orientation fix 已被 focused test 与 edge oracle 验证，但因为整个 M0 未闭合，不提升为 ordinary production default；暂列 research-only / pending follow-up review。M0 runner、checker 和 evidence 可单独审阅。旧 negative evidence do-not-delete。本分支没有 merge approval。
