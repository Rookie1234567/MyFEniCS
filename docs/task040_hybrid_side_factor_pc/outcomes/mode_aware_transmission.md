# V1-3/V1-4 mode-aware transmission

状态：V1-3 `setup_started_but_not_ready / not_qualified_due_resource_stop`，V1-4
`not_run_by_gate`。本页只记录未完成的 setup，不把计划写成数值结果。

## V1-3 projected-exact route

只有 V1-2 sampled Schur/Steklov oracle 完成并通过 identity/finite/resource Gate 后，才可构造

```math
\widehat S = Y^H S_\Gamma Z,
```

其中 `Y` 必须是正确的非 Hermitian/QEP left dual，不能用 `Y=Z` 代替。selected mode span 外继续使用已经冻结的 scalar base；selected span correction 只能以 action/Woodbury 形式存在，不生成 FE-sized dense interface matrix、不复制全量 mode basis、不改变 external DtN。

V1-3 复用同一五个非零 source、physical zero、三组 exact factors、`[0,1,2,2,1,0]` sweep 和 right-FGMRES `0/4/8/16/(32)` checkpoints。Gate 与 V1-1 相同：mandatory true residual `<=1e-2`，modal+/modal−/external `<=1e-3`，并满足 finite、identity、RSS `<45 GiB`、swap `0`、cleanup。32 步失败时分类为 `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`，停止 analytic/bounded/top/full 路线。

## V1-4 analytic mode-aware route

只有 V1-3 通过后才可进入 V1-4。lower uniform interface 使用实际 transverse Floquet `kx/ky`，并按 outgoing branch 计算

```math
\beta_{mn}=\sqrt{(k_0 n_{substrate})^2-k_x^2-k_y^2}
```

同时保留 S/P admittance，并对 near-cutoff case 做独立 oracle 验证。upper route 复用冻结 M480 right/left modes、beta branches、orientation 和 normalization；不得重跑 QEP、改变 M、重归一化或用 raw coefficient 替代 canonical mode identity。

所有实现必须 owner-row/batched/action-only，scalar complement 保留，external DtN 不变，并先与 V1-2 oracle 对比，再执行同一 Krylov Gate。32 步失败分类为 `ANALYTIC_MODE_AWARE_TRANSMISSION_FAIL`，不扫描 mode count、beta shift、rational order 或 damping；通过后才允许 V1-5 bounded patch。

## 当前结论边界

V1-3 只完成了未就绪的 setup，因此 mode span coverage、projected exact error、near-cutoff behavior 和对 0.7 nm 的资格均为 `not_available`；V1-4 的 analytic error 为 `not_run`。T40-3 只裁决固定 normal-incidence scalar candidate；不能据此声称 mode-aware transmission、bounded patch、coarse information 或完整 Hybrid 不可行。

两阶段都继续绑定 inherited audit 中的 branch/HEAD、input/physical/selected/external-key hash、bare-F、resource authority 和禁止项；任何 missing left/right/traction identity、ABI/resource/nonfinite 或真实 Gate 失败都保留 raw 并停止，不翻符号、不调参、不重跑 producer。

## V1-8 状态

V1-2 到达 exact-oracle ready/release，随后 V1-3 projected transmission setup 开始；MPI8
进程组在 `projected_ready`、one-apply 或 FGMRES checkpoint 前被 45 GiB watchdog 停止。
因此 V1-3 为 `setup_started_but_not_ready / not_qualified_due_resource_stop`，numerical
capacity 为 `NOT_EVALUATED`；V1-4 仍为 `not_run_by_gate`。不能将此次停止分类为
`THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`。
