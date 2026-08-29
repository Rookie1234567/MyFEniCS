# V7 后续路线更正

下文的 V6-2 identity negative 原始表与结论保持不变。其后的 V7 scale-normalized identity
已完成 candidate raw/checker，随后 full-spectrum 与 moving-PML 路线确实被尝试；因此下文若
仍写“所有后续路线未运行”，应以本轮 [V8 response](../response_v8.md)、[V7 scale outcome](v7_scale_normalized_identity.md)、[full-spectrum outcome](full_spectrum_floquet_sweep.md) 和 [moving-PML outcome](moving_pml_sweep.md) 的更晚记录为准。full-spectrum 没有形成 numerical no-signal，moving-PML 的 corrected run 是真实 wall/resource Gate。

# V6-2 完整接口 Schur identity 结果

## 结论

V6-2 在 source SHA `82bd11099a843dc960629970b9074fb241fba0f4` 上执行一次 MPI8 formal，随后
执行一次独立 checker。结果为：

```text
status        = completed_v6_2_identity_gate_negative
classification= V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL
checker_pass  = true
evidence_valid= true
gate_pass     = false
executed_exact= false
```

这是有效的 identity negative：raw evidence、rank 一致性和 checker 独立审计有效，但完整
接口 Schur action identity 未建立，故在 exact qualification 和 PDE 前停止。它不是 exact
numerical negative，也没有产生五源 exact residual 或 packet 结果。

## 入口与证据

| 项目 | 值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| formal source / checker source | `82bd11099a843dc960629970b9074fb241fba0f4` |
| formal run root | `results/task040_v6_2_full_interface_schur_mpi8_82bd1109_native` |
| checker formal root / worker root | `results/task040_v6_2_full_interface_schur_mpi8_82bd1109_native/worker` |
| checker output | `results/task040_v6_2_full_interface_schur_mpi8_82bd1109_native/v6_2_checker_82bd1109.json`（worker 外） |
| manifest / run-summary SHA | `71963c98b543ae9b6de05dbce249f3b72931b202ecffc542aedb08f0eeaaa4fa` |
| checker artifact SHA | `9da96cc142e4a1e590d8f790398c98352466849a08f0bde5a55ff691b6b0c9c3` |
| watchdog SHA | `d34adcea148891ca33e0badc1af5b9dbf1a9c82a788fbf52559ea6c643847788` |
| operator audit SHA | `bd3a5fa88bceb45f35bf202cb1fa7b64a6736c4a77158b4faa50041baee8ca2c` |
| checker read NPY | `false` |

## Identity thresholds与观测

| Gate | 固定阈值 | 观测值 |
|---|---:|---:|
| Gamma action | `<= 1e-10` | max `3.783538480529195e-10`，fail |
| full-interior residual | `<= 1e-10` | max `1.2298155651030158e-9`，fail |
| linearity | `<= 1e-11` | `6.766170711131541e-9`，fail |
| repeat | `<= 1e-11` | max `1.4161645932820494e-9`，fail |
| zero map | `<= 1e-13` | `0`，pass |
| roundtrip | `<= 1e-11` | `0`，pass |

Gamma `L/U/joint = 7560/7560/15120`。三个 deterministic vectors 的 solve count 均为 `3`；
canonical layout、owner-distributed mapping、coverage、no full-interface replica、rank
consensus 和 rank artifact integrity 均通过。矩阵 `C/D/H=0`，没有 QEP、PDE 或 exact
qualification 执行。

allgather 口径必须分开记录：top-level `numeric_allgather=false`、`fe_numeric_allgather=false`、
`full_interface_numeric_replica=false`；`identity_gate.numeric_allgather=true` 是该检查通过，
不是失败。

## 生命周期、资源与 bridge

factor lifecycle 为每 rank `3 -> 0`，construction/destruction 为 `3/3`，最大同时因子数为
`3`，没有 full/global factor。watchdog 为 `natural_exit`、worker `rc=0`，完整调用耗时
`339.7141449260016 s`，峰值 process-tree RSS 为 `27,801,870,336 B`（约 `25.89 GiB`），
swap 为 `0`，authoritative samples 为 `616`，hard stop 为 `45 GiB`、timeout 为 `21600 s`。

`run_summary.json` 与 checker 输出均未发出 `operator_identity_bridge` 字段（`has=false`）。
这是因为 identity stop 发生在 exact runner 之前，`exact_output_vectors_loaded=0`；bridge
未执行、未判定，不能写成显式 null、pass 或 fail。冻结 RHS 没有被加载到该 exact 阶段，也没有
被修改；不得从历史 raw-byte hash 推断数值变化。当前 live bare-F hash 记录为
`c7a5551232f23f835ee0c21ea74b337f779addaef2d76464370000fb53c49ee4`。

## 后续边界

V6-0 已记录 `FORENSIC_TRUE_FACTOR_STALL`，V6-1 factor-only rescue 禁止重试；V6-2 identity
stop 后，full-spectrum、moving-PML、adaptive Schwarz、factor-free local service、bottom/top/
both/full Hybrid、h3、0.7 nm 和 Full3D 均为 `not_run_by_v6_2_identity_gate`。本结果不构成
production side inverse、0.7 nm 或 arbitrary Full3D 资格；等待 ChatGPT 与用户审核。
