# V7 BAL_H 平衡约束失败：有界诊断提案

**状态：`IMPLEMENTED_PENDING_MAIN_REVIEW; ONE_SAME_TARGET_INSTRUMENTED_REPLAY_AUTHORIZED`。** 用户已明确授权一次同目标取证重放：沿用 V7 数值基线与所有原门限，在第一次 BAL_H 初始 balance rejection 时保存失败输入和分解后按原异常终止；若该门通过，则继续完整 V7 solve。该授权不代表已证明或修复数值缺陷，也不授权第二次重放。失败 run 的数值基线 source 为 `00789bd1ae41fc7bddbe47d049624eb520de888b`；新诊断实现必须绑定新的 clean source SHA，并显式引用该旧 SHA 为数值基线。

## 已有证据与缺口

Run `20261012T110145.583366Z` 以 `WORKER_FAILED` / exit 4 结束，完整 workflow 为 16,533.2349 s。失败发生在第 2 个已完成的 outer FGMRES iteration 之后、outer PC apply 3 的 BAL_H 初始平衡检查：该调用计数为 `C=1, A_structure=1, PH_audit=2, smoother=0`，因此失败在 smoother 和第二次 C 反馈之前。拒绝值为 `||PH(residual)||=9.608395623437402e-10`、操作尺度 `0.08885057559044918`、相对值 `1.0814106222256414e-8`，限值 `1e-8`。这是超限的真实数值失败，不是资源停止。

可用记录只有标量日志：p4 logical correction #7 在同一因子一次 refinement 后通过 `A4_n0` 相对残差门，`1.5437358100e-7 → 3.2266594819e-11`，RHS norm `0.04442528784`，端口闭合相对量 `5.95276e-11`；该逻辑修正累计到 14 次 solve、1 次 symbolic、1 次 numeric。日志保留的 coarse timing 是最近两个 logical correction 的滚动窗口，不能据此推断失败 PC 又执行了 C2。

`retained_native_aq_projection_check` 对单个确定性探针通过：p4/p6 行数为 9,757,120/32,061,312，native volume、DtN、total 投影相对差分别为 `7.8538300944e-15`、`1.6346078987e-14`、`7.8538262063e-15`。该探针不是失败输入；实际 BAL_H 路径使用 p4 `fast_a4` 与 p6 `pc_physical` packed action，故 native probe 不能证明失败向量上的 fast/native 一致性。

**失败输入没有落盘。** `retained_vectors/iteration_000000.npy`（148,502,080 B）是 solve 前初始向量，不是失败 coarse/primal 向量。现有 `pc_applies.jsonl`、`p4_decisions.jsonl` 只有标量、计数、时间及矩阵/端口身份；没有失败时的 `g`、`c`、`Pc`、`PH(g)` 或 action 差分。没有读取 NPZ，也没有用初始向量冒充失败向量。因此目前没有被证据证明的 root-cause-specific fix。

## 当前最小实现边界

- **同一 V7 数值基线、输入、活动模式、数学与阈值。** 数值基线 source 为 `00789bd1ae41fc7bddbe47d049624eb520de888b`；诊断 hook 会形成新的 source SHA，必须在运行身份中分别记录，不能声称与旧 SHA 相同。保持 p6/p4、N0 572 模式、q160、BAL_H `1e-8`、A4 refinement 与残差门；不改 PC、不改容差、不扩成 solver qualification。诊断由 V7 专用环境变量和 run manifest 双向绑定，在标准 worker 预 FE gate 与 retained workflow 入口各验证一次；未显式启用时保持关闭。observer 不增加 outer-PC 调用上限，也不改变 fullsolve 的调用上限。
- **只在第一次 `BalancedConstraintRejected` 抛出前、工作向量仍有效且清理尚未发生时记录。** V7 callback 当前会在返回前销毁 `c`；最小 instrumentation hook 必须把这个失败调用的 p4-owned `c` 暂存到有界诊断 holder，保持其 MPC/DOF 身份，并保证异常、正常返回和其他清理路径都释放 holder。保存 `c` 与 source `g`，连同 shape/dtype、owned-row/DOF 与 MPC 身份、模式/网格/source/input/resolved SHA、各 action backend 身份和迭代/PC 调用序号。不要保存逐步全场、因子、NPZ 或重复场副本；`Pc` 由失败时 live `c` 及原 prolongation 形成，不另解方程。
- **记录一个 scalar/vector-norm decomposition，分开 volume 与 DtN。** `c` 是 full p4 向量（9,757,120 rows），`g` 是 source full p6 向量（32,061,312 rows）。对同一 `c,g,Pc` 记录实际顺序的 `PH(g − A6_fast Pc)`，并将它与以下和式核对：`r4 + (A4_fast − A4_native)c + (A4_native c − PH(A6_native Pc)) + PH(A6_native Pc − A6_fast Pc)`，其中 `r4 = PHg − A4_fast c`。分别记录 A4/A6 volume 与 DtN 子项，并比较实际求值顺序和上述分组求和的差范数，以区分算子差异和浮点相减/归约顺序。全长临时 action 顺序计算、不落盘，只记录有限性、范数及对象身份。不得调用额外 `MatSolve`、MUMPS numeric factorization 或新 PC；诊断所需的既有矩阵自由 action 应限于上述一次失败输入。
- **捕获空间与体积上限先核实。** 实际 complex128 p4 `c` 是 156,113,920 B；p6 source `g` 是 512,980,992 B；两数组 raw 合计 `669,094,912 B`，另计小型 manifest。仅保存这两数组并绑定 hash；不得把动作中间量或 `Pc` 另存成全场快照。
- **严格区分观察与执行策略。** Observer 在 setup QA 完成、outer FGMRES 开始前激活。首次 BAL_H balance 拒绝时捕获输入与诊断并保留原拒绝异常；若 balance 通过，observer 继续保持被动，完整 V7 solve 照常运行。它不发停止信号、不截断 outer solve、不添加 3-PC stop，也不改变 fullsolve 上限。当前授权仅覆盖一次该同目标重放，且仍须主审冻结 source/启动合同并完成 fresh admission 后执行。

现有已结束 run 的因子没有持久化，执行一次同目标取证重放需重新完成 full setup 与 factor。旧 workflow 实测 16,533.2349 s（约 4.59 h）仅是该次运行成本，不是下一次运行的时长保证。现有记录没有失败时的 `c/g/Pc`，也没有其上的 fast/native 动作结果；因此没有现成数据可以证明源码缺陷或支持有针对性的数值修复。上面的 hook 只补齐这项证据缺口，**不构成修复**。一次取证重放已获用户授权，但尚待主审确认实现和启动合同；该次若没有复现拒绝但完整 solve 通过，也只说明本次未复现，不能替代后续数值资格判定。

## 来源

- Run summary SHA256 `b90be14f2aea9e284021faf46a7e7821c8274da7a6f4f021d5e0816191300d2a`；worker log SHA256 `71c0a24b23bdd5d552fbc1bdc711719ab7455ca7a987e63c1d8462774e1b8900`。
- 已有 compact：`tmp/p3_main_review/v7_main_terminal_compact_20261012_v1.json`，SHA256 `96d726c281cc3f014ace2cb373df00df38a4808460ea4b823ac817b8bd5bdb94`。其唯一资源审计已完成；本提案未重读 resources 流或 NPZ。
