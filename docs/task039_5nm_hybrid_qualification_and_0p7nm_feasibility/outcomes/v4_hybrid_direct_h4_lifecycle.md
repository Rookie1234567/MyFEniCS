# V4-5 Hybrid direct h4/M480 packet consumer

## 结论

本次是固定 5 nm、1° grazing、phi=0、S、p6/h4、M480、MPI8 的 Hybrid-direct
own-Gate 运行。Hybrid direct 把两个端口的内部传播模态通过共享 packet 读入，再组装
一个全局增广矩阵并用 MUMPS 直接求解；它不是 Full3D direct，也没有重新运行 QEP。
求解后按已批准的顺序释放 MUMPS factor 和 global system，再从同一 packet 重新 hydrate
恢复所需模态并完成 field/canonical 后处理。

| 项目 | 实测值 | 判定 |
| --- | ---: | --- |
| consumer source SHA | `1515f09575a94484116938d3749f151841e3cdb8` | clean、hash-bound |
| packet producer SHA / manifest | `eaad0f942f014b65474ac57e3d5e561316489f20` / `2dddaf7a...` | 同一 packet |
| direct solve | reason `4`；true residual `3.7053063181108737e-10` | pass |
| interface projection bottom/top/combined | `3.4769692899430483e-12 / 8.252657999159727e-11 / 8.229846170461895e-11` | pass |
| exact variational traction bottom/top | `8.660439882115594e-11 / 3.434237062556144e-10` | pass |
| R / T / A_balance / A_volume | `0.7331842736908196 / 0.0002200986949369512 / 0.26659562761424344 / 0.26659627261424806` | finite |
| energy closure | `6.450000047397708e-7` | pass (`<=1e-5`) |
| external keys | `600/600` unique；bottom/top `296/304`；SHA256 `ba431e...` | exact |
| process-tree peak | `100262797312 B = 95618.0546875 MiB = 93.37700653076172 GiB` | below `224000000000 B` |
| swap / warning / critical | `0 / false / false` | pass |

因此本次直接法 own Gate 通过，分类为
`TASK039_V4_HYBRID_DIRECT_OWN_GATE_PASS_INTEGRATED_COMPARISON_NOT_AVAILABLE`。
这不是同网格三方法完整资格：此前 Full3D h4 在 MUMPS factor setup 阶段 timeout，故
Full3D integrated comparison、same-grid RTA/field delta 和相对节省均为
`not_available`/`not_run`，不能用旧 h5 或 partial h4 代替。

## 共享 packet 与生命周期

packet 的 manifest、identity 和 consumer SHA 均被实际读取并核对：

- manifest：`results/task039_v4_h4_m480_shared_packet_eaad0f94/manifest.json`，SHA256
  `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067`；identity SHA256
  `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9`；
- `consumer_qep_required=false`、`qep_calls=0`；第一次和 factor-release 后的 manifest/
  identity 完全相同；两次 mmap/packet 引用均已释放；
- selected packet 的 direct E/H 数组为 finite complex128，形状 `[5,20,40,3]`，payload
  SHA256 为 `2cee09c0bd8f1d0b53fa1b6dbff1c6b1a23bcd3f752a4cc72cbf15fbdaf4c376`；
- bottom/top active canonical packet 各 `141972` 条，full-FE packet 各 `425472` 条，四个
  manifest 均 `pass=true`、无重复且 finite；canonical manifest SHA 见 compact record；
- 独立的 `12+12` power/complex-amplitude checker count 没有在本次 worker record 中单独
  持久化。raw 只保存完整 600 条 dynamic orders/amplitudes，因此这里不把它补写成
  `12/12` 通过。

factor-ready marker 位于 MUMPS factor 持有期间；随后记录了
`direct_factor_released_before_postprocess`。因子释放前后生命周期证据为：

| 生命周期边界 | 证据 |
| --- | --- |
| MUMPS | ICNTL(14) requested/observed/verified = `100/100/true`；INFOG(1)=`0` |
| release | `factor_destroyed_before_postprocess=true`、`system_destroyed_before_postprocess=true` |
| cleanup | collective PETSc cleanup 完成；最大 rank RSS `16535.79296875 -> 2577.9765625 MiB` |
| modes | factor 创建前已 detach/destroy，`factor_modes_overlap=false`；cleanup 后 vector count `0` |
| recovery | second packet hydrate 后 `recovery_after_factor_system_release=true` |

全过程峰值出现在 factor/solution 仍保留的 MUMPS 阶段：UTC
`2026-08-17T22:30:19.815000+00:00`，worker elapsed `7023.345766295039 s`。worker
阶段计时为 packet read `0.8070760400150903 s`、首次 hydrate `0.07595701399259269 s`、
local FEM-DtN `387.86823651200393 s`、internal coupling `3194.1688997440506 s`、
augmented setup `3394.103840555006 s`、solve `1.9525350429466926 s`、field
reconstruction `83.35377941501793 s`、worker total `7131.113596254028 s`。这些是
不同 clock/origin 的 authority 字段，不能与 parent wall elapsed 混算；compact record
同时保留 parent run manifest 的 `6771.478625 s`。

18-stage taxonomy 中，本 direct packet consumer 实际发出并对齐 12 个 marker，覆盖
stage `0` 及 `7–17`；stage `1–6` 属于本 consumer 没有执行的 mesh/QEP/packet-prep
边界，不是缺失样本。12 个 raw marker 均对齐到 process-tree sample；MUMPS analysis
的独立快照仍为 `not_available`，没有为凑齐 taxonomy 伪造 marker。

## Gate 边界与下一阶段

所有 V4 direct own numerical/physics/lifecycle/resource Gate 均通过；raw 通用 Task33
字段仍显示 `physical_integration_pass_mode_convergence_pending`、`mode_count_converged=false`
和 `official_record=false`，这是旧 M-funnel 的 generic status，不是本次固定 M480 own
Gate 的失败，也不能通过它宣称通用 M-convergence 已完成。sampled traction density
proxy 的 Gate 为 false，但它在 raw 中明确是 diagnostic-only；正式 traction authority
是上表的 exact variational dual residual，已通过。

Full3D h4 timeout 仍是本阶段的 integrated-comparison blocker，但不阻断 direct own Gate。
下一步 exact-side Hybrid iterative 已由主审按 Review V4 放行，必须继续使用同一 h4/M480 packet、同一 physical
identity，global direct factor 保持 0；不得回到 ordinary ILU0、重新 QEP 或更换参数。

完整小型证据见
[`task039_v4_h4_hybrid_direct_packet_consumer_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_h4_hybrid_direct_packet_consumer_v1.json)，
raw results 保持在 ignored run root。
