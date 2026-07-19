# Task034 阶段成果：p2/h5 P 偏振可计算性示例

## 1. 状态与边界

本文记录用户批准的唯一 P 偏振重型示例。状态为 `CAPABILITY_EXECUTED_WITH_CONTROLLED_PHYSICAL_FIELD_NEGATIVE`，不表示 Hybrid P 结果通过完整物理资格化，也不表示 Task034 全部完成。

固定参数：

- `degree = 2`
- `h = 5.0 nm`
- `polarization_kind = p`
- `MPI = 8`
- `wavelength = 13.5 nm`
- bottom/top interface = `10/110 nm`
- incident grazing angle = `10 deg`
- Hybrid requested/candidate modes = `160/320 per direction`
- solver path = `modal-schur-memory-minimal`

按用户 reduced-scope 指示，本例只用于证明 P 路径可完成 full3D 和 Hybrid 计算；不运行 P 偏振矩阵，不运行 M80/M120/M240，也不放宽任何 Gate。

## 2. full3D 分级 Gate

full3D 在 clean source `31110efb16fa58d2631b23d6d9635c8354e7e99e` 上严格按 assembly-only、factorization-only、full-solve 顺序执行。

| Gate | status | elapsed (s) | peak memory (GiB) | rows | assembled NNZ | factor NNZ | swap |
|---|---|---:|---:|---:|---:|---:|---:|
| assembly-only | `assembly_calibration_pass` | `10.872` | `2.155` | `44778` | `4896156` | N/A | 0 |
| factorization-only | `factorization_calibration_pass` | `15.787` | `2.877` | `44778` | `4896156` | `31504676` | 0 |
| full-solve | `full3d_reference_pass` | `16.454` | `2.972` | `44778` | `4896156` | `31460044` | 0 |

full-solve 官方物理量：

| observable | value |
|---|---:|
| true relative residual | `1.0194577337195329e-12` |
| R_total | `0.09585457599329973` |
| T_total | `0.4382691568246436` |
| A_balance | `0.46587626718205666` |
| A_volume_total | `0.4658762671820833` |
| port-volume closure error | `2.6645352591003757e-14` |

证据：

| record | SHA256 |
|---|---|
| `p2_h5_assembly_mpi8_31110ef_p.json` | `c1bcccea4c5d6ff9ed636cef76aba01d156435803628794971cd5188921378bc` |
| `p2_h5_factorization_mpi8_31110ef_p.json` | `966bb4e9ccac2c95397bcc48239463f0822d342ef2e000692aa24fe3b41b8573` |
| `p2_h5_full_mpi8_31110ef_p.json` | `48e5bb1d58b98aca716906a63f428cf46a3fec366a5ee6221891c96de00c691d` |

## 3. P 专属 Hybrid launch hardening

原 Task034 workstation Gate 只允许 S，并且 authority 仅按 `(p,h)` 匹配。为避免 P 错误复用 S 资源锚，提交 `c626ffa59ef0f949f8074c0f0fd19d4c173ebf61` 做了以下 fail-closed hardening：

1. authority 匹配身份扩展为 `(degree, h_nm, polarization_kind)`；
2. 只有 `p2/h5 + P + MPI8 + M160` 通过用户批准的 P scope check；
3. native full3D reference normalization 保留并验证 `s/p` 身份；
4. M80、M120、M240、MPI16 和其他 p/h 的 P 组合保持未授权；
5. 新增 P authority 使用本次 P full3D 三阶段实测资源锚，保守上界为 `4.4577484130859375 GiB`；
6. authority SHA256 为 `1a047717a0497e52f6788efff4293a5d63f6d24f04b71b2956ead0086bcb2e80`。

测试：

- P 相关解析场/Fresnel/PDE fixture/CLI/watchdog：`37 passed, 5 skipped`
- P authority/reference/watchdog 定向回归：`42 passed`
- hardening 后完整测试：`462 passed, 18 skipped`
- 完整测试日志：`benchmarks/artifacts/task034/tests/p2_h5_p_hardening_full_suite_31110ef.log`
- 日志 SHA256：`b37bfd60f2c104fc77575cd243bdc947dadc98a859946ff8cff479a278e8c39b`

## 4. Hybrid M160 结果与受控负结论

Hybrid 在 clean source `c626ffa59ef0f949f8074c0f0fd19d4c173ebf61` 上执行。launch Gate、authority hash、source compatibility、memory authority、no-swap、true residual、algebraic chain、interface continuity、volume energy closure 均通过；运行没有被内存或 timeout 终止。

| observable | Hybrid | Hybrid - full3D |
|---|---:|---:|
| true relative residual | `6.513185913815536e-13` | N/A |
| R_total | `0.09585591857617719` | `1.3425828774560333e-06` |
| T_total | `0.4382654960004637` | `-3.6608241799074293e-06` |
| A_balance | `0.46587858542335914` | `2.3182413024791515e-06` |
| A_volume_total | `0.46587858960773776` | `2.3224256544551736e-06` |
| energy closure error | `4.1843786213746625e-09` | N/A |

资源：

- elapsed：`91.140 s`
- peak simultaneous worker RSS：`3.283 GiB`
- swap：`0`
- watchdog memory Gate：pass
- launch/source Gate：pass，failures 为空

固定物理 Gate 的受控失败：

| Gate | measured | threshold | result |
|---|---:|---:|---|
| middle-plane electric relative-L2 | `0.006610997220361647` | `0.005` | fail |
| middle-plane magnetic relative-L2 | `0.006664748791407013` | `0.005` | fail |

因此 watchdog 顶层状态为 `formal_not_pass`、`physical_integration_failed`。该记录未删除，阈值未放宽，也未改写为通过。证据为 `benchmarks/artifacts/task034/phase_f/records/p2_h5_p_hybrid_m160_mpi8_c626ffa.json`，SHA256 `b983ea34ebf5f5e96590b4a859e258bd463cc601db9a85bf96ef388227cea44f`。

## 5. 范围结论与下一步

本例确认 P 偏振从 full3D 到 Hybrid 的 CLI、QEP、biorthogonal basis、local FEM-DtN、modal coupling、direct solve、true residual、R/T/A、volume absorption 和 selected-plane reconstruction 均可实际执行并生成有限结果；但 M160 的 selected-plane 精度未达到正式 `5e-3` Gate，所以只可声明“可计算路径已执行”，不可声明“Hybrid P 物理资格化通过”。

按照用户明确的 reduced scope，本阶段在此停止 P 扩展，不增加 P mode funnel、不重复 P 案例。后续恢复 S 偏振主线，依次处理 p2/h1、p3/h2、p4/h3 的 full3D 分级 Gate 与 Hybrid；失败继续保存为受控负结果。

本文不作 Task034 最终 PASS 声明。
