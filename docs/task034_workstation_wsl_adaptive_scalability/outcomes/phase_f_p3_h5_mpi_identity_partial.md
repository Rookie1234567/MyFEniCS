# Task034 阶段成果：p3/h5 S 偏振 MPI 数值一致性闭合

## 1. 状态与范围

本文记录 Task034 第二组重型计算及其 post-merge hardening。状态为 `PARTIAL_RESULT_COMPLETE`，不表示 Task034 全部完成。

代表案例固定为：

- `degree = 3`
- `h = 5.0 nm`
- `polarization_kind = s`
- `MPI = 1/8/16/32`
- `wavelength = 13.5 nm`
- bottom/top interface = `10/110 nm`
- incident grazing angle = `10 deg`
- Hybrid selected mode count = `M160/direction`
- 本机 physical core count = `48`，MPI32 为 user-requested exploratory row，未 oversubscribe
- 所有重型作业遵守 one-heavy-case-at-a-time、零 job swap 和外部 watchdog

full3D 四行在 clean source `2e944c957b95d95139490ce8c2d151089467e7bb` 上完成。随后仅修复离线 MPI identity 对 native full3D `beta` schema 的兼容，以及 Hybrid interface active-column 诊断对 PETSc explicit-zero 的错误计数；Hybrid 最终四行在 clean source `4f1cec96890af6a91770281d800e968b5740ac9a` 上完成。每种方法内部的 MPI1/8/16/32 均为同一 clean SHA、同一 case/config/structure，两个修复均不改变 Maxwell/Floquet/QEP 数值算法。

## 2. full3D 分级 Gate 与 MPI identity

每个 MPI size 均按 assembly-only、factorization-only、full-solve 顺序通过 Gate，未跳级启动 full solve。

| MPI | assembly (s/GiB) | factorization (s/GiB) | full solve (s/GiB) | true residual | R_total | T_total | A_balance |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `633.99 / 4.510` | `1035.12 / 6.329` | `1055.60 / 6.340` | `1.265045e-10` | `0.001090107012040803` | `0.6006224782943147` | `0.3982874146936445` |
| 8 | `90.59 / 5.947` | `148.78 / 8.899` | `154.77 / 9.014` | `8.304969e-12` | `0.0010901070120382089` | `0.6006224782934397` | `0.3982874146945221` |
| 16 | `53.55 / 7.658` | `82.84 / 10.784` | `84.22 / 11.359` | `1.142801e-11` | `0.0010901070120389802` | `0.6006224782934460` | `0.3982874146945151` |
| 32 | `51.10 / 10.975` | `70.24 / 15.619` | `72.62 / 15.773` | `6.911947e-12` | `0.0010901070120352314` | `0.6006224782934385` | `0.3982874146945262` |

以 MPI1 为 baseline，MPI8/16/32 的最大观测漂移为：

- R/T/A/A_volume absolute drift：`8.8174e-13`
- field/interface relative-L2 drift：`3.2561e-11`
- significant order power absolute drift：`8.7741e-13`
- complex amplitude relative drift：`6.6071e-10`
- complex amplitude phase drift：`4.3648e-10 rad`
- QEP beta relative drift：`0`

上述数值分别低于官方 Gate `1e-8`、`1e-6`、`1e-8`、`1e-7`、`1e-7 rad` 和 `1e-7`。aggregate 状态为 `qualified`，failures 为空。

full3D 证据：

| record | SHA256 |
|---|---|
| `p3_h5_full_mpi1_2e944c9_s.json` | `e6362c52d75f89eb0b0701fdcc65c836592e457c84d5699274520ecfd6681ad7` |
| `p3_h5_full_mpi8_2e944c9_s.json` | `86339abffead7dc6929e8c3f1395b9d799d15421081e46f6de6d806e98cb606a` |
| `p3_h5_full_mpi16_2e944c9_s.json` | `d2ff1b2a82d135f826cfe0742d251007f5108a866519e605cd7f5edbc9976f7a` |
| `p3_h5_full_mpi32_2e944c9_s.json` | `ad00206c05aecf46fbe161e885670fff8d5be6672b865501f9edc155d8296bde` |
| `p3_h5_full3d_mpi_identity_1_8_16_32_2e944c9_beta_schema_fix_candidate.json` | `47a7daf8ff787f423c6931c71da500bee3d5939e463c44fed33cdbe01cfa3da8` |

以上文件均位于 `benchmarks/artifacts/task034/phase_f/records/`；runtime artifacts 保持 gitignored，由路径与 SHA256 定位。

## 3. Hybrid MPI identity

| MPI | status | elapsed (s) | peak memory (GiB) | true residual | max R/T/A/Avol drift vs MPI1 | max field relative-L2 drift | swap |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `measured_shard_pass` | `431.07` | `1.245` | `6.418010e-12` | `0` | `0` | 0 |
| 8 | `measured_shard_pass` | `144.69` | `4.900` | `1.163511e-11` | `3.8525e-13` | `1.5654e-13` | 0 |
| 16 | `measured_shard_pass` | `134.13` | `7.150` | `3.396705e-12` | `1.9185e-13` | `1.0114e-13` | 0 |
| 32 | `measured_shard_pass` | `201.10` | `12.088` | `3.787907e-12` | `1.4877e-13` | `9.9312e-14` | 0 |

四行的结构诊断一致：bottom/top local FE DOFs 均为 `21807/21807`，bottom/top interface active DOFs 均为 `1080/1080`，requested modes 为 `160`。以 MPI1 为 baseline，最大 significant-order power absolute drift 为 `3.8103e-13`，最大 complex-amplitude relative drift 为 `1.0258e-9`，最大 phase drift 为 `9.9044e-10 rad`，QEP beta relative drift 为 `0`。所有 identity Gate 均通过。

Hybrid aggregate：

- status：`qualified`
- failures：空
- required/observed MPI sizes：`1/8/16/32`
- qualified selected-mode funnel：true
- same case/source/config/structure：true
- no oversubscription：true
- all no swap：true

Hybrid 证据：

| record | SHA256 |
|---|---|
| `p3_h5_hybrid_m160_mpi1_4f1cec9_identity_closure.json` | `e73fc76ab98b6a8bf41d1c6b04787f14566af045e0c7596fa2c420a4ba05ce54` |
| `p3_h5_hybrid_m160_mpi8_4f1cec9_identity_closure.json` | `5438aeaf4bc884674557943096a157b5378ba2479011e619a16601787bc28b8f` |
| `p3_h5_hybrid_m160_mpi16_4f1cec9_repeat.json` | `7477dadd914cb3b20ee3f67009c54c4928ef478c1ef479de66416cacc4092365` |
| `p3_h5_hybrid_m160_mpi32_4f1cec9_active_column_hardening.json` | `9b03d07e2be3ee149c794b24bb21a16ae854f21bef0fd1d91e0f48a89db916b2` |
| `p3_h5_hybrid_mpi_identity_1_8_16_32_4f1cec9_qualified.json` | `a4e5664a7d2eed9eedb72929cda57ce3ad4e3cf150ffdb660af3c3b212046214` |

## 4. 保留的负结果与 post-merge hardening

### 4.1 native full3D `beta` schema

第一次 full3D aggregate 误报 order identity failure。原因是 native full3D order JSON 使用 `beta`，离线聚合器只读取 `beta_per_nm`。原失败 aggregate `p3_h5_full3d_mpi_identity_1_8_16_32_2e944c9_s.json` 已保留，SHA256 为 `d532e0f368f3226461356b6b407a5324e35b4949a7a4bb16c7bcf4693fb4280f`。修复仅增加 native `beta` fallback 与回归测试；修复后同一原始 PDE 记录 aggregate 为 `qualified`。

### 4.2 Hybrid explicit-zero active-column 诊断

第一次 MPI32 Hybrid 行把 PETSc 矩阵中显式存储但值为零的列计入 active columns，导致 top/bottom `1090/1080` 的 partition-dependent 假差。修复后诊断只统计 `value != 0` 的结构贡献，MPI4/MPI8 fixture 通过，真实 MPI32 重跑得到 `1080/1080`。该改动只影响诊断，不改变矩阵、R/T/A 或 field 数值。

### 4.3 MPI16 biorthogonality 单次负结果

原 MPI16 Hybrid 行的 negative-basis max biorthogonality row sum 为 `1.1100153524288491e-6`，略高于 `1e-6` Gate；失败未删除、未放宽阈值，原 aggregate `p3_h5_hybrid_mpi_identity_1_8_16_32_2e944c9_with_mpi16_negative.json` 已保留，SHA256 为 `1889342dc39b4511538fa9b04ee6af7454bdd662768439575b936869b0bd9160`。同 SHA hardening 后的 MPI16 独立重跑分别得到 positive/negative `3.6929e-7 / 2.5986e-7` 并通过，物理量仍与 MPI1 一致。因此分类为 eigensolver 单次数值波动，而不是物理结果随 MPI size 改变；没有修改 biorthogonal 算法或阈值。

## 5. 测试与结论

- MPI identity native-`beta` 修复后完整测试：`459 passed, 18 skipped`
- explicit-zero active-column hardening 定向测试：`43 passed`
- hardening 后完整测试：`460 passed, 18 skipped`
- Hybrid MPI32/16/1/8 真实 PDE closure 均通过 formal/numeric measurement Gate
- full3D 与 Hybrid 各自的 MPI1/8/16/32 aggregate 均为 `qualified`

结论：在 p3/h5 S 偏振代表案例上，MPI 数量从 1、8、16 到 exploratory 32 不影响官方物理结果；观测差异远小于 Task034 Gate。按用户批准的 reduced scope，MPI 数量扩展项在此关闭，不再对每个 p/h/S/P 案例重复 MPI 矩阵。

下一阶段按既定顺序执行：P 偏振 p2/h5 MPI8 的 full3D + Hybrid M160 可计算性示例；随后 S 偏振 p2/h1、p3/h2、p4/h3 的 full3D 分级 Gate 与 Hybrid。Case093、adaptive compression、resource model v2、0.7 nm assessment 和最终交付保持不变。

本文不作 Task034 最终 PASS 声明。
