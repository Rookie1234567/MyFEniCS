# V3-2 联合接口机制 consumer

## 状态

`completed_numerical_negative`：`COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL`。
独立 checker 判定 `evidence_valid=true`；identity、packet、joint、lifecycle、one-apply、
telemetry 和资源均通过，失败只发生在完整 bare-F 的 true residual / FGMRES 数值 Gate。

本阶段回答的是一个受限的机制问题：把 V2 的三个独立 projected inverse 加 sweep，改为
lower/upper 两个人工截面的 776 维联合接口 correction，能否让冻结的 bare-F side equation
进入规定的 Krylov 收敛范围。它不是 production side inverse，也不是完整 Hybrid formal。

## 身份与运行

| 项目 | 实测值 |
|---|---|
| formal source / checker source | `c11aea058d01e86052d5490a71575a375e3fe207` / `0fbc33d07d27f8e4b2bce9c2bae2704ea9372c7b` |
| formal root | `results/task040_v3_2_full_span_mpi8_c11aea05` |
| packet producer source | `fa1720d8f137de81023cd45d6a43262d386e6521` |
| packet manifest / true joint content | `f480189663ef293ec4f809818e322186d75a205f725a3aa35dc12c2d24aad209` / `ed7c973c92ff4704a687c9d61032930bb458076e552892c988990cf893e6e035` |
| input / physical | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` / `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected / probe / spool | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` / `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` / `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| MPI / threads / QEP / PDE | `8 / 1 / 0 / not_run` |
| exit / process-sample wall | `natural_exit, rc=0` / `892.680907273083 s` |

## 776 维 joint 与身份 Gate

| 项目 | 实测值 |
|---|---|
| joint shape / rank / condition | `776×776` / `776` / `72530856.63880321` |
| Gamma global rows | `7560 / 15120 / 7560`（lower / middle / upper） |
| spans | `296 / 776 / 480` |
| group1 owner remap | source local `1902` → target local `1884`；sent/received `1902/1884`；bijection true |
| roundtrip / numeric allgather / global basis replica | `0` / `false` / `false` |

四个 block 都由独立 checker 核对 shape、rank、norm 和 hash：

| block | shape | norm | rank | SHA256 |
|---|---:|---:|---:|---|
| LL | `296×296` | `1052857.3530587784` | `296` | `4be30638ca6ca7e6d6980ef45fa53250755d76961b336b60360f4b06a187dbe0` |
| LU | `296×480` | `36531.317719106126` | `296` | `1033fcc0d2d5ff2b0a3a018870f839b6e131d39a01de4d205fd3d496fc97db9e` |
| UL | `480×296` | `9728.7850526928` | `296` | `969e15b2d61f185bb276bab40904235343f118ef0a4d1aef2a6b05c61c048972` |
| UU | `480×480` | `6371.749206867203` | `480` | `3935fc7fbd064d333dfdc53fb738076a0273b9c2529274d648e11777369c6d09` |

```math
E_\Gamma =
\begin{bmatrix}E_{LL} & E_{LU}\\ E_{UL} & E_{UU}\end{bmatrix},
\qquad E_\Gamma c = Y_\Gamma^H g_\Gamma,
\qquad \lambda_\Gamma = Z_\Gamma c.
```

正式 carrier 实际保留 LL/LU/UL/UU，并通过同一 joint solve 做 harmonic back-substitution；
它不是把三个旧 groupwise inverse 重新命名为 coupled action。

## one-apply、生命周期与资源

| Gate | 实测值 |
|---|---|
| zero-map、five-source finite、repeat、linearity、factor inventory、coarse finite | 全部 `true` |
| action apply count | `15` |
| linearity relative | `1.5604941032988232e-12` |
| factor ready | 3 个 cross-section group factor + 1 个 reduced dense factor |
| exact-interface / full-side / global / nested | `0 / 0 / 0 / 0` |
| cleanup | group `3→0`；reduced `1→0`；action/factor destroyed `true/true` |
| bare-F hash before / after | 相同：`e532b69e2cacc5205454ba42a563b537ccfaf7f9ca67b64be0ea4cfebca9d5b9` |
| peak RSS / swap | `28,044,996,608 B = 26.118938446045 GiB` / `0 B` |

`factor_count_ready=3` 与 `projected_inverse_factor_count=3` 是同一组三个 group factor 的
两种 inventory 视图，不是 3+3 个同时驻留 factor。PSS/USS 未记录，不能从 RSS 推算。

## FGMRES 数值 Gate

| source | r4 | r8 | r16 |
|---|---:|---:|---:|
| modal traction positive | `0.9931120049077101` | `0.9908281636708466` | `0.9753543932125024` |
| modal traction negative | `0.9947389065952192` | `0.9916159544066352` | `0.9753434891844831` |
| external DtN coupling | `0.9873782795035724` | `0.9829723343875048` | `0.9706859881449064` |
| fixed random repeat 0 | `0.9910369479287503` | `0.988904915975861` | `0.9829154077946104` |
| fixed random repeat 1 | `0.9920231223407014` | `0.9893566601030788` | `0.9832307911898668` |

所有 phase1 checkpoint finite，但 r16 仍约 `0.9707–0.9832`；conditional32、conditional64
均为 `false`，first preferred checkpoint 为 `null`。失败的是完整 bare-F correction 的有效性，
不是 identity、资源或生命周期失败。

## 机制目标

当前 V2 失败的是三个独立 projected inverse 再做 sweep。V3-2 只测试一个问题：在相同三分区、
相同 lower 296/upper 480 span 和相同 local exact group solve 下，一次求解两个接口的 776 维
耦合系统，是否能使 bare-F side equation进入可用 FGMRES 范围。

一次 action 必须包含：local/group pre-correction、形成 lower/upper interface residual、
`Y_Gamma^H` 投影、联合 reduced solve、`Z_Gamma` 合成和三个 group 的一致 back-substitution。
它不得退化成已有三个 local inverse 加 sweep。

## 运行与 Gate

允许作为 mechanism oracle 的资源边界：

| 项目 | 合同 |
|---|---|
| interface reduced solve | full rank 776，complex128，SVD/QR/dense LU均可 |
| group factors | 最多三个，simultaneous max=3 |
| exact-interface oracle | `0` |
| full-side/global factor | `0/0` |
| QEP / PDE | `0 / not_run` |
| RSS / swap | `<45 GiB` / `0` |
| cleanup | group factors `3 -> 0` |

固定 source 为五个非零 source 加 physical zero-map。checkpoint 为 `0/4/8/16`，仅在 16
步全部 finite 且最近 8 步下降至少 `0.25 decade` 时授权 32；只有 32 步最坏 residual
`<=0.1` 且最近 16 步继续单调下降时才授权 64。首个同时满足 mandatory `<=1e-2`、
modal+/modal-/external `<=1e-3` 的 checkpoint 才能分类：

```text
COUPLED_INTERFACE_FULL_SPAN_PASS
```

若 tiny/packet identity 通过但最终 64 仍未通过，必须分类：

```text
COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL
```

不得继续同 span analytic、bounded patch 或增加 Krylov budget。

## checker 现场与后续边界

首次 checker artifact 保留为 `results/task040_v3_2_full_span_mpi8_c11aea05/checker_recomputed.json`
（SHA256 `70ef07f4fc8942cac0e20a25e5039cb806198713f80a75d438e59cc118b303b7`）。它的 rc2
是 checker 接线问题：复用 augmented packet audit 时未绑定 producer watchdog，错误地产生
`COUPLED_PACKET_INFORMATION_INCOMPLETE`；没有改动 raw packet 或 formal 数值。修复后的
`checker_recomputed_after_0fbc33d0.json`（SHA256
`e4d127090e83580ada4070a5ca558c2a75c045c003d2d61dfbd282df99050750`）独立重算后仍 rc2，
但分类改为本页的数值负结果，`evidence_valid=true` 且全部身份/资源/实现 checks 为真。

这个结果说明：V3-2 的 full776 联合机制和 formal 证据链成立，但当前 296/480 span 与
harmonic lift 对完整 bare-F 的残差改善不足。它排除了“只是旧 groupwise sweep 接线错误”
这一单一解释；同时不能推出所有 296/480 trace 数学都无用，也不能把该组件提升为
production side inverse、完整 Hybrid 或 0.7 nm 资格。

V3-3 bounded rank、V3-4 packet-independent production、V3-5 bounded local patch、V3-6
bottom/top/both/full、V3-7 h3/0.7 nm 均为 `not_run_by_v3_2_numerical_gate`。V1/V2 历史
结论和三个旧 implementation-failure root 未被覆盖。

完整 compact record：[task040_v3_2_full_span_consumer_v1.json](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v3_2_full_span_consumer_v1.json)。
