# Task034 阶段成果：p3/h3 current-source S 偏振闭合

## 1. 状态与范围

本文记录 Task034 第一组重型计算的阶段结果。状态为 `PARTIAL_RESULT_COMPLETE`，不表示 Task034 全部完成。

本组固定参数：

- `degree = 3`
- `h = 3.0 nm`
- `polarization_kind = s`
- `MPI = 8`
- `wavelength = 13.5 nm`
- bottom/top interface = `10/110 nm`
- incident grazing angle = `10 deg`
- full3D 与 Hybrid 均使用 WSL2 Ubuntu 24.04 原生环境
- 所有重型作业遵守 one-heavy-case-at-a-time、零 job swap 和外部 watchdog

full3D 在 clean source `3a1bc99c469b5ac053ddaf53c68ebba63ace9632` 上完成。更新 measured launch authority 后，Hybrid funnel 在 clean source `8438cca405d0fdea70c77fe556bde274552f4dad` 上完成。两者之间仅有 authority、测试和 Case090-disjoint 证据分类变更；Hybrid launch Gate 对 full3D reference source compatibility 的审计通过。

## 2. full3D 分级 Gate

| Gate | status | elapsed (s) | peak memory (GiB) | rows | assembled NNZ | factor NNZ | swap |
|---|---:|---:|---:|---:|---:|---:|---:|
| assembly-only | `assembly_calibration_pass` | 410.986 | 19.749 | 656405 | 157785425 | N/A | 0 |
| factorization-only | `factorization_calibration_pass` | 1722.240 | 43.766 | 656405 | 157785425 | 1290761069 | 0 |
| full-solve | `full3d_reference_pass` | 1726.362 | 44.069 | 656405 | 157785425 | 1307605045 | 0 |

full-solve 官方物理量：

| observable | value |
|---|---:|
| true relative residual | `8.489277332587551e-11` |
| R_total | `0.0007894679573742296` |
| T_total | `0.6025149841382069` |
| A_balance | `0.39669554790441885` |
| A_volume_total | `0.39669554790437317` |
| port-volume closure error | `-4.574118861455645e-14` |

full3D 证据：

| record | SHA256 |
|---|---|
| `benchmarks/artifacts/task034/phase_f/records/p3_h3_assembly_mpi8_3a1bc99_s.json` | `80d397e8f1878315b00858f3368e400cdd30bffa34200613bf1ed9f22fad41cb` |
| `benchmarks/artifacts/task034/phase_f/records/p3_h3_factorization_mpi8_3a1bc99_s.json` | `1cc4e443ab3be4392e85f2bff5864a4d870521fe7fbda3e99434763e3256d3f1` |
| `benchmarks/artifacts/task034/phase_f/records/p3_h3_full_mpi8_3a1bc99_s.json` | `2c1ec18a3877a4452f7ac52cd411df0a4785204b811dc52e466e1f7c91ea393a` |

## 3. Hybrid M funnel

| M/direction | status | true residual | peak memory (GiB) | elapsed (s) | max abs full3D delta | swap |
|---:|---|---:|---:|---:|---:|---:|
| 80 | `measured_shard_pass` | `2.075863265594657e-11` | 12.737 | 529.556 | `7.177991201423595e-09` | 0 |
| 120 | `measured_shard_pass` | `6.972466530490021e-12` | 13.709 | 567.573 | `6.074567404645848e-09` | 0 |
| 160 | `measured_shard_pass` | `6.718449402239955e-12` | 14.272 | 661.410 | `6.065997648629917e-09` | 0 |

M160 官方物理量：

| observable | value | Hybrid - full3D |
|---|---:|---:|
| R_total | `0.0007894673342924205` | `-6.230818090213058e-10` |
| T_total | `0.6025149786987333` | `-5.439473649282434e-09` |
| A_balance | `0.3966955539669743` | `6.062555457653218e-09` |
| A_volume_total | `0.3966955539703708` | `6.065997648629917e-09` |

M160 最大 selected-plane relative-L2：

- electric: `1.0594283355819105e-06`
- magnetic: `2.3620846868492505e-05`

各 shard 的 algebraic、physical-field、pointwise-H-jump、volume-absorption 和 selected-plane measurement Gate 均通过。

funnel 比较：

| pair | max total delta | max significant power relative delta | max significant amplitude relative delta | mandatory | strong |
|---|---:|---:|---:|---:|---:|
| M80 -> M120 | `1.3916867658281262e-11` | `6.500297927901679e-09` | `5.1192867448174775e-09` | pass | pass |
| M120 -> M160 | `2.83550960489265e-13` | `1.390984220149714e-09` | `7.966131932857785e-10` | pass | pass |

funnel 结论：

- status: `qualified`
- all sources same clean SHA: true
- mode-count converged: true
- selected mode count per direction: `160`
- selected pair strong: true
- evidence: `benchmarks/artifacts/task034/phase_f/records/p3_h3_hybrid_funnel_mpi8_8438cca_s.json`
- evidence SHA256: `615ff2e9e3541f4a45583608aa712462cbf0f896d9f63939d694327847c7cd08`

Hybrid shard SHA256：

| M | SHA256 |
|---:|---|
| 80 | `739bb15bc8cba08c2d62ea20c986b45c8a8dcb0c698e723917e10b7d50640605` |
| 120 | `17a0449003ea5a80bee21d71154b0b43cea5dbb4c1bd4ccec1c76000d32201a5` |
| 160 | `10d179b586ec4fb863b20e0e878d5919975652097cb8005f2ed0bf37ab96fae9` |

## 4. 保留的失败与修复

首次 current-authority M160 launch 在 PDE worker 启动前 fail-fast，状态为 `formal_not_pass/not_run_preflight_failed`。原因是新离线聚合器 `benchmarks/task034_mpi_identity.py` 尚未被 Case090 source audit 分类为 pure-3D Floquet core 的 component-disjoint 文件。

该失败未删除、未改写为通过。修复仅把离线聚合器加入 Case090 compatible 与 component-disjoint 显式集合，并增加测试证明核心 QEP/Floquet 数值文件仍 fail-closed。相关测试 `30 passed`，修复提交为 `8438cca`。随后 M80/M120/M160 均通过 preflight 和正式 watchdog。

## 5. 测试状态

- authority/native-reference 定向测试：`28 passed`
- Case090/source-authority 定向测试：`30 passed`
- MPI identity 聚合器测试：`3 passed`
- 最近一次完整测试套件：`458 passed, 18 skipped`
- 在下一次源码冻结前将重新执行完整测试套件

## 6. 用户批准的范围更新与下一步

本报告之后的执行范围按用户最新指示：

1. 代表性 MPI PDE identity 只选 p3/h5、S 偏振，在同一 clean SHA 下运行 full3D 与 Hybrid 的 MPI1/MPI8/MPI16，并保留 MPI32 exploratory；误差通过后关闭 MPI 扩展。
2. P 偏振只选 p2/h5、MPI8，运行 full3D 与 Hybrid M160，证明 P 路径可计算，不扩展完整 P 矩阵。
3. 不运行 p1。
4. 新增 S 偏振 p2/h1、p3/h2、p4/h3 的 full3D 与 Hybrid；full3D 仍严格执行 assembly/factorization/full-solve 分级 Gate，资源失败保存为受控负结果。
5. 后续 Case093、adaptive compression、resource model v2、0.7 nm assessment 和最终交付保持不变。

本文不作 Task034 最终 PASS 声明。
