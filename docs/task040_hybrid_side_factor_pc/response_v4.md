# Task040 Review V3 Response V4：V3-2 full-span 收口

## 结论先行

V3-2 在冻结的 `5 nm / 1° / phi=0 / S / p6h4 / M480 / MPI8` 身份下完成了一次唯一
formal。full776 联合接口 action 的 packet identity、owner remap、生命周期和资源证据均
成立，但它没有把完整 bare-F 的五个冻结 source 残差降到 Review 要求的范围。独立 checker
因此给出：

```text
COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL
```

这是数值负结果，不是 resource、identity、telemetry、checker 或 implementation failure。
它说明当前的 `296 + 480` interface span 与 harmonic lift 组合还不足以成为有效 side inverse；
同时不能推出所有 296/480 trace 数学对其他问题都无用，也不能宣称 production、完整 Hybrid
或 0.7 nm 可用。

## 身份、正式运行与证据

| 项目 | 值 |
|---|---|
| formal source | `c11aea058d01e86052d5490a71575a375e3fe207` |
| independent checker source | `0fbc33d07d27f8e4b2bce9c2bae2704ea9372c7b` |
| formal root | `results/task040_v3_2_full_span_mpi8_c11aea05` |
| packet producer source | `fa1720d8f137de81023cd45d6a43262d386e6521` |
| packet manifest | `f480189663ef293ec4f809818e322186d75a205f725a3aa35dc12c2d24aad209` |
| true joint content | `ed7c973c92ff4704a687c9d61032930bb458076e552892c988990cf893e6e035` |
| input / physical | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` / `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected / probe / spool | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` / `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` / `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| exit / wall | natural exit, `rc=0` / `892.680907273083 s` process-sample wall |
| peak / swap | `28,044,996,608 B = 26.118938446045 GiB` / `0 B` |
| samples | `1770/1770` authoritative and readable；terminal exclusion `0` |

raw/checker 绑定如下：

| artifact | SHA256 |
|---|---|
| run summary | `125e04c30aee500bddb7115a1d1a9ef0cbe84309e53af998d589d59a06b674ae` |
| watchdog summary | `aa4a0b2c959a01c66929f37686e922bb03c59f4cc724b5d5813a287c5e26d5fe` |
| process timeline | `e2809753f2a5fb5ae4ff54cea57b67acc5bd8a5cfbf78d2c51ea2536d672f63e` |
| raw memory markers | `733dc5fc9b6097d7915451a3b479ef7815dc32047f9398a027a961020e29c9bc` |
| memory stages | `6b443bd13c51395dad1eb8e5d387f4161ecef022c3923da7eebd283eb50595eb` |
| worker stdout | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| first checker artifact | `70ef07f4fc8942cac0e20a25e5039cb806198713f80a75d438e59cc118b303b7` |
| fixed checker artifact | `e4d127090e83580ada4070a5ca558c2a75c045c003d2d61dfbd282df99050750` |

首次 checker rc2 是 checker 接线 bug：复用 augmented packet audit 时没有绑定 producer
watchdog，导致错误的 `COUPLED_PACKET_INFORMATION_INCOMPLETE`。首次 artifact 和 raw 均
保留；修复后的独立 checker 仍为 rc2，但分类为本次真实数值负结果，`evidence_valid=true`。
该修复没有改变 raw、packet 或数值字段。

## 1. V2 失败来自 groupwise sweep，还是 296/480 span 不足？

两者不能再被拆成“只有旧 sweep 接线错误”。V2 的三个独立 projected inverse 加 sweep 的
负结果促成了 V3-2；V3-2 已换成真正的 lower/upper 联合接口 solve，显式保留跨块 LL/LU/UL/UU，
但五源完整 bare-F residual 仍接近 1。因此本次证据排除了“只要把旧 sweep 改正确就会通过”
这一单一解释。

更准确的结论是：当前冻结的 `296/480` span 与当前 harmonic lift/back-substitution 共同形成
的 side correction 不足以成为有效 side inverse。formal 没有改变 mode count、beta、sign、QEP、
physical DtN、bare-F 或 Hybrid 方程，所以不能进一步判断是 span 需要扩展、lift 需要改变，还是
还缺少三分区之外的 long-range/nonlocal representation。那需要新的、明确授权的机制研究。

## 2. `E_joint` 的 LL/LU/UL/UU norm、rank、condition

联合矩阵 shape 为 `776×776`，rank=`776`，condition=`72530856.63880321`。四块为：

| block | shape | Frobenius norm | rank | content hash |
|---|---:|---:|---:|---|
| LL | `296×296` | `1052857.3530587784` | `296` | `4be30638ca6ca7e6d6980ef45fa53250755d76961b336b60360f4b06a187dbe0` |
| LU | `296×480` | `36531.317719106126` | `296` | `1033fcc0d2d5ff2b0a3a018870f839b6e131d39a01de4d205fd3d496fc97db9e` |
| UL | `480×296` | `9728.7850526928` | `296` | `969e15b2d61f185bb276bab40904235343f118ef0a4d1aef2a6b05c61c048972` |
| UU | `480×480` | `6371.749206867203` | `480` | `3935fc7fbd064d333dfdc53fb738076a0273b9c2529274d648e11777369c6d09` |

使用的 reduced action 关系是：

```math
E_\Gamma c = Y_\Gamma^H g_\Gamma,
\qquad \lambda_\Gamma = Z_\Gamma c,
\qquad
E_\Gamma = \begin{bmatrix}E_{LL}&E_{LU}\\E_{UL}&E_{UU}\end{bmatrix}.
```

## 3. full776 coupled-interface oracle 是否通过？首次通过 checkpoint 是什么？

它通过了机制的结构性、身份、资源和生命周期检查，但没有通过 full bare-F numerical
qualification，因此不能写成 `COUPLED_INTERFACE_FULL_SPAN_PASS`。one-apply implementation
subset 全真，action apply count=`15`，三个 group factor 与一个 reduced factor 的 inventory
为 `3+1`，cleanup 后为 `0+0`；exact-interface/full/global/nested 均为 `0`。

FGMRES phase1 的所有 r4/r8/r16 都 finite，但：

| source | r4 | r8 | r16 |
|---|---:|---:|---:|
| modal traction positive | `0.9931120049077101` | `0.9908281636708466` | `0.9753543932125024` |
| modal traction negative | `0.9947389065952192` | `0.9916159544066352` | `0.9753434891844831` |
| external DtN coupling | `0.9873782795035724` | `0.9829723343875048` | `0.9706859881449064` |
| fixed random repeat 0 | `0.9910369479287503` | `0.988904915975861` | `0.9829154077946104` |
| fixed random repeat 1 | `0.9920231223407014` | `0.9893566601030788` | `0.9832307911898668` |

没有 source 达到规定的 preferred Gate；conditional32 和 conditional64 都未授权，first
preferred checkpoint=`null`。所以 full-span mechanism 是一个有完整证据的 numerical negative，
不是通过。

## 4. 最小通过 coarse rank 是多少？

没有测得。V3-3 的 `64/128/256/512` rank screen 在 V3-2 数值 Gate 后按决策树停止，因而
不存在可以诚实报告的“最小 rank”或实际极限。不能把 full776 的失败外推为四个 bounded rank
都失败，也不能把未运行写成 rank Gate 失败。

## 5. 正式 candidate 是否完全不依赖 exact-interface packet producer？

不是。V3-2 明确是 packet-dependent full776 mechanism consumer；它绑定 augmented producer
source `fa1720d8...`、manifest `f480...` 和 true joint hash `ed7c...`。consumer 没有构造
`PetscInterfaceSchurOracle`、没有加载 exact-output vectors，但依赖 producer packet 的 joint
small matrices、owner-row data 和 provenance。因此它不能被称为 packet-independent production
candidate；V3-4 才定义 packet-independent 重建，而 V3-4 本轮未运行。

## 6. bounded local patch 的 max rows、factor、RSS、residual

没有数据。bounded local patch 属于后续 V3-5/V3-6 路线，状态为
`not_run_by_v3_2_numerical_gate`。本次 V3-2 只证明当前 component carrier 的 inventory：
三个 cross-section group factor、一个 reduced dense factor，cleanup 后 `0/0`；不能把这
个 inventory、`26.118938446045 GiB` 或五源 residual 当作 bounded local patch 的结果。

## 7. bottom/top/full side 是否在 full-side factor=0 下通过？

没有运行，不能回答为通过或失败。V3-2 自身记录 full-side exact factor=`0`，但这是该
component route 的 inventory，不是 bottom/top/full workflow 的资格结果。bottom、top、both
和 full Hybrid 均为 `not_run_by_v3_2_numerical_gate`，没有对应 residual、physics、factor
或资源数据。

## 8. 完整 Hybrid 的峰值、时间、五项 residual 和 physics 结果

没有本轮完整 Hybrid 数据。`93.377006531 GiB` direct full workflow 和
`80.025856018 GiB` exact-side iterative full workflow 是继承的 baseline/reference，不是
V3-2 candidate 结果；不能把 `26.118938446045 GiB` 的 component RSS 当作 full workflow saving。
本轮没有 QEP、global Hybrid action、recovery、R/T/A、E/H、canonical、channel 或完整五项
physics 输出，因此不做 full Hybrid 数值或内存宣称。

## 9. h3 scaling 是否支持 0.7 nm 近线性 PC 内存？

没有。V3-7 h3/0.7 nm probe 未运行，既没有 DoF/row scaling，也没有 retained-byte exponent、
RSS 或 wall 观测。V3-2 的 776 维 fixed-case joint solve 只能证明这一机制在当前 5 nm component
上可被取证，不能证明 mode count、owner rows 或 coarse rank 在更密网格下保持有界，更不能
证明近线性 PC resident memory。

## 10. 哪些可复用，哪些只能保留为 research-only 负结果？

| 类别 | 内容 | 边界 |
|---|---|---|
| 可审阅/可复用工具 | canonical owner-row packet/remap、joint small-matrix assembly、独立 checker、watchdog/lifecycle evidence | 仍需后续 bounded-rank 与 packet-independent Gate；不改变 ordinary defaults |
| research-only mechanism | V3-2 packet-dependent full776 coupled action、三个 group factor + 一个 reduced factor | 当前 numerical negative；不能提升为 production side inverse |
| research-only negative evidence | V2 scalar/projected/groupwise routes、V3-2 五源 FGMRES negative | 绑定冻结 5 nm case；不外推为所有 trace/coarse 方法无效 |
| 尚未资格化 | bounded rank、packet-independent production、bounded local patch、bottom/top/full、h3/0.7 nm | 全部 `not_run_by_v3_2_numerical_gate` |

## 资源、生命周期和数值边界的通俗解释

V3-2 的资源通过表示这一次 component process 在 45 GiB hard line 以下完成，并且 swap 为零；
它不表示完整 workflow 只需 26 GiB。三个 group factor 在构造期间为 3，reduced dense factor
为 1，退出前都释放为 0；这说明生命周期合同成立，但不改变 action 对 bare-F residual 的
效果。

数值 Gate 关注的是“把 correction 作用到完整 bare-F 方程后，真实 residual 是否下降”。本次
五个 r16 仍在 `0.9707–0.9832`，所以联合接口虽然按结构求解了 776 维系统，却没有提供
足够有效的 side correction。不能因为矩阵 full rank 或资源较低，就把它写成 mechanism pass。

V3-3 以后没有继续运行，是因为 Review 要求在这个真实 numerical Gate 失败后停止扩展；不是
因为环境、内存或 checker 让路线被动中断。V1/V2 的历史 root、V3-2 raw 和两份 checker
artifact 均保留，负结果没有覆盖旧 evidence。

## 验证结果

| 检查 | 最终实跑结果 |
|---|---|
| `src/test/test_311_task040_v3_2_runner.py` + `src/test/test_312_task040_v3_2_checker.py` | `36 passed` |
| `src/test/test_183_development_model_registry_markdown.py` | `5 passed` |
| `python -m benchmarks.check_benchmarks --no-write` | `302/302 passed` |
| immutable V3-2 checker | `rc=2`；分类为预期 `COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL`，不是 implementation/resource failure |
| `src/test/test_26_documentation_contract.py` | `13 passed, 1 failed`；唯一失败是既有 Case104 numbered-case registration gap |
| Ruff check / Ruff format / compileall | 相关 checker 文件全部通过 |
| JSON parse / Markdown links+math / `git diff --check` | 全部通过 |
| full repository pytest / additional PDE or additional MPI heavy during closeout | `not_run`；上文 V3-2 MPI8 component formal 已运行 |

## 当前阶段与提交边界

| 阶段 | 状态 |
|---|---|
| V3-0 | docs audit completed |
| V3-1 | augmented packet algebra completed；legacy packet negative 保留 |
| V3-2 | completed numerical negative |
| V3-3–V3-7 | `not_run_by_v3_2_numerical_gate` |
| V3-8 | evidence/docs closeout completed |

本轮文件只包含 compact evidence 与文档更新，没有修改 raw/results、solver、runner 或测试
架构。当前 documentation parent / numerical source / checker source 分别由 Git history、
上表和 compact record 绑定；本次 closeout commit 的完整 SHA 由最终 handoff 报告给出，文件
不自引用未来 SHA。

compact record：[task040_v3_2_full_span_consumer_v1.json](../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v3_2_full_span_consumer_v1.json)。
