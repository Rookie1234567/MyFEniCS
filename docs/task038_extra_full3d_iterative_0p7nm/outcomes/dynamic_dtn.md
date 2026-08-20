# Task038-extra T3 动态流式 Full3D DtN formal evidence

## 1. 结论与作用

T3 formal aggregate 为 `T3_PASS`。该组件把边界上的场先投影到每个 Fourier 模式，再按固定大小的 mode batch 累加返回边界作用；它解决的是“不为全部模式建立一个 FE-sized 的显式边界矩阵”这一内存问题。它只验证 action、恢复的模式系数和证据合同，没有创建 KSP，也没有运行 PDE。

本轮最终正式证据只使用同一 clean source SHA `691ac261fd62258d356183cb3c0383307605b15e` 下的 v2 MPI1/MPI2 两条记录。旧 SHA `b9ec1375d6e0727059b4f3c043561aa00bcf3ffc` 的 MPI1 PASS 和 MPI2 attempt1 现场没有混入 aggregate。

## 2. 冻结 benchmark identity

| 字段 | 实测/绑定值 |
|---|---|
| source SHA（start/end） | `691ac261fd62258d356183cb3c0383307605b15e` |
| authority input | `input/templates/full3d_iterative_example.dat` |
| input bytes / SHA-256 | `2119` / `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| resolved-config bytes / SHA-256 | `4076` / `78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad` |
| physical-model SHA-256 | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| case / wavelength / degree / mesh target | `p6-h10` / `13.5 nm` / `6` / `10 nm` |
| method / profile | `full3d_iterative` / `full3d_scalable_v1` |
| boundary / mode policy / assembly | `dtn_port` / `auto_propagating` / `auxiliary` |
| input adapter / encoder | `src.io.load_and_resolve` / `src.io.resolved_config.resolved_config_bytes` |

resolved JSON 位于 ignored raw artifact 的 `benchmark_input/resolved_config.json`；它由上述 `.dat` 通过 T1 adapter 生成，不能用手写配置替代。

动态发现得到 80 个模式，并以完整 ordered manifest 绑定：`propagating=78`、`near-cutoff=0`、`evanescent=2`，manifest bytes `86377`，SHA-256 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。80 只在这个冻结 benchmark identity 中作为 authority count；production builder 仍从当前配置动态发现。

## 3. Formal commands and scope

两次 runner 都在 qualified activation 下、逐次执行，使用同一 resolved JSON 和 source SHA：

```bash
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task038_full3d_t3 --resolved-config benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/benchmark_input/resolved_config.json --raw-dir benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/p6-h10-mpi1/raw --record benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/p6-h10-mpi1/record.json --case p6-h10 --expected-source-sha 691ac261fd62258d356183cb3c0383307605b15e
mpiexec -n 2 python -m benchmarks.run_task038_full3d_t3 --resolved-config benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/benchmark_input/resolved_config.json --raw-dir benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/p6-h10-mpi2/raw --record benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/p6-h10-mpi2/record.json --case p6-h10 --expected-source-sha 691ac261fd62258d356183cb3c0383307605b15e
```

runner wall time：MPI1 `23.52 s`，MPI2 `12.12 s`。每次 apply 后都记录 elapsed、rank-max current self RSS 和 swap；每条记录 `apply_count=12`。正式运行没有 KSP、PDE、process-tree peak claim；process-tree 明确为 `not_measured_t3`。

## 4. 数值与资源事实

| MPI | action vs independent modal sum | recovery | 最大 repeat 差异 | apply elapsed 范围 | RSS warm span | swap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | `1.5267729283364925e-16` | `8.148489733468128e-17` | `0.0` | `0.000971896–0.001616392 s` | `61440 B` (`0.05859375 MiB`) | `0 B` |
| 2 | `1.5267729283364925e-16` | `8.148489733468128e-17` | `0.0` | `0.000971896–0.001245411 s` | `45056 B` (`0.04296875 MiB`) | `0 B` |

两条记录均为 12 次确定性 apply，故实际 apply telemetry 与 repeat 数量闭合。RSS span 均远小于 `64 MiB` 限值。

| 项目 | MPI1 | MPI2 |
|---|---:|---:|
| retained numeric bytes（local / rank-max / global-sum） | `2875480 / 2875480 / 2875480` | `1428808 / 1447312 / 2876120` |
| bounded batch work bytes（local / rank-max） | `256 / 256` | `256 / 256` |
| batch size / batch count | `8 / 10` | `8 / 10` |
| recovery output | `1280 B` / `80` complex128 | `1280 B` / `80` complex128 |
| H denominator min / max | `0.3807331130650235 / 1250.0000000000002` | 同左 |

归一化使用显式 per-mode `H` 投影分母，且 `normalization_nonidentity=true`；没有把 H 假装成 identity。carrier 保留的数值数据与固定 batch 的工作区分别报告，工作区审计为 `fixed_modal_batch_size`。

## 5. 独立 checker 与 MPI physical identity

MPI1、MPI2 独立 checker 均为 `T3_PASS`。aggregate 的六项检查全部通过：两条记录 pass、MPI1/MPI2 配对、同一 physical identity、ordered mode manifest identity、source/action/reference canonical physical L2、mode-ordered recovery L2。

canonical source、candidate action 和 independent reference action 的 MPI1/MPI2 比较均为 relative L2 `0.0`，每项 canonical packet count `173802`；recovery cross-MPI relative L2 也是 `0.0`。因此比较的是物理 canonical packet，而不是 partition-dependent PETSc global row bytes。

carrier audit 同时确认：无 numeric allgather、无 slave functional rows、无 global AIJ/Schur/trace matrix、无显式 C/D、`ksp_created=false`、`pde_solved=false`。独立 reference 重新建立 surface assemblers 并逐模式组装 modal sum，没有读取 candidate carrier entries，也没有调用 candidate apply。

## 6. 证据索引与失败现场

| artifact | tracked compact SHA-256 |
|---|---|
| [`t3_p6_h10_mpi1_v2.json`](records/t3_p6_h10_mpi1_v2.json) | `63f9d46d35564acfe5494482d6ef4c8a84ca9840a79594e4f8a5013976c75f6c` |
| [`t3_p6_h10_mpi2_v2.json`](records/t3_p6_h10_mpi2_v2.json) | `e8dec640c09d7e06bb5b14ead4f6adf2b26722884c6350c36b6f21c1972ffca4` |
| [`t3_aggregate_check_v2.json`](records/t3_aggregate_check_v2.json) | `f8fc4947c18d96120057dfefe5a286dc330ce0d3a30d3ff6f74b5d5e33aa6131` |

ignored raw roots：

```text
benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/p6-h10-mpi1/raw
benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v2/p6-h10-mpi2/raw
```

v2 checker JSON 的 SHA-256 分别为 MPI1 `197459bcf278e2fbc5f0f560af925f6185d4ec601c3aa9a675156e09f4aa7ce0`、MPI2 `7b12ea14592f704513f45952bf980e1e5cc003d6a63180813de2f4619cc62084`；raw records 中保留 source/action/reference、canonical manifest、mode manifest、resolved-config 和 recovery 的各自 bytes/SHA descriptor。

MPI2 attempt1 的真实 preflight 失败没有覆盖：

```text
benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v1/p6-h10-mpi2/attempt1_failure.log
benchmarks/artifacts/task038_extra_full3d_iterative_t3_formal_v1/p6-h10-mpi2/raw
```

它只触发了所有 ranks 共享目录初始化的 TOCTOU（rank0 创建后较慢 rank 误见 existing path），没有进入 mesh/JIT/action；窄修复和 MPI2 focused regression 已证明 rank0-only initialization 与 existing-path fail-closed。

## 7. 未运行项

T3 本轮不运行 KSP、Maxwell PDE、DtN 之外的求解阶段、T4 或任何 0.7 nm full PDE。T7/T8/T9 仍未授权。
