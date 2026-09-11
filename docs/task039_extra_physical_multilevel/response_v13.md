# Task39extra Review V12 response：O0–O4 真实物理验证收口

## 结论

本轮已经在 review base `96e5d5fcfc3e801ef33d4a2d241ea7571937f734` 之后的 source `e8c3c82bab2687a811a11f0798a2879c725532b5` 上完成 V12 O0 预检、42 个真实物理宏块的 O1 构建/库存审计、4 组有限 p4 控制、O4 finalize 和最终轻量回归。O1 的 4 组 p4 控制均只执行了合同允许的 4 次 I4 `B4` 作用，均以 `INNER_APPROXIMATE_RETURN` 返回，未达到内部 `1e-4` 目标；共享 O0/O1 保守账本随后受控停止。

准确状态是：

`PARTIAL_PHYSICAL_CONTROLS_WITH_PERFORMANCE_CONTROLLED_STOP`

不是 OOM、MUMPS numeric failure 或 Maxwell convergence failure，也不是完整物理 solver pass。O2 restart、O3 original/notch 和全部新的 official R/T/A 等字段均 `not_run`。普通默认保持不变，`master merge` 未获批准。

完整中心结果见 [physical macro V12](outcomes/physical_macro_v12.md)；机器记录见 [compact](outcomes/records/physical_macro_v12_compact.json) 和 [lossless raw JSON evidence](outcomes/records/v12_raw_json_evidence.json)。原始 raw evidence SHA256 为 `0ff0246b6c1212b5d1c2706cd1954884626b828192697d1a7d0c9e99d06e6710`，tracked normalized copy SHA256 为 `329ed513c351896c3db09ea5899389a060b71ff36805daf456132e304fdd1580`。

## 阶段结果

| 阶段 | 结果 | 关键边界 |
|---|---|---|
| O0 | `O0_PRECHECK_COMPLETED` | 2.0600177589932294 s；RSS peak 147095552 B；swap 0；清场完成 |
| O1 | `PERFORMANCE_CONTROLLED_STOP` | 42/42 numeric inventory、84 witnesses recounted；资源审计无 cap violation、swap 0；p4 records 只记已持久化下界 |
| O2 | `not_run` | O1 未完成，未形成 ONE/BAL framework selection |
| O3 | `not_run` | O2 未运行；没有 original 或条件 notch |
| O4 | `O4_FINALIZED` | 2.0538921670007735 s；未新建 reference factor/solve；清场完成 |

O1 的终止是 shared O0/O1 budget exhaustion：`7201.319691806935 s` 对 `7200 s`，保守账面超出 `1.319691806935 s`。这个差异保留在 ledger 中；实现活动、阶段费用、未单独计时的间隔和 O4 费用没有混称为一个 gapless CPU 时间。

## 真实宏块和 p4 结果

42 个物理 block records 覆盖 p4 全部 `48960` 个独立行；42 个宏块各有独立 numeric factor record。另有 18 个 C_U 元素内部响应的 `local_classes/local_factors`，它们是不同层的类因子，不能替代 42 块物理构建。最大局部回代相对残差 `2.1772149386553977e-15`，6 个 native witness 最大 `8.243915633632588e-16`，cached/native relative bridge `2.787784119354311e-15 < 1e-11`。C_U 已构建并通过 inventory 记录，但 closure scalar 没有持久化，故不写 closure PASS。

S/p2 同时存在但与 local inventory 分开计账：rows=`7326`、NNZ=`818100`、allocated/used padded=`270000000/65000000 B`、derived matrix+reported-factor=`341069688 B < 536870912 B`，symbolic/numeric=`0.025815314998908434/0.371230351000122 s`。这是 derived policy budget，不是 RSS；原始 `stages.jsonl:247` SHA256 为 `4b1fd995693c14177c028304916b964a21cde7a23f833fd24d7b98ac9ac0ca40`，并已绑定到 compact/inventory audit。build/JIT/其他检查没有独立终态时钟，记为 `unknown/included`，不能从 O1 阶段费用中扣除 p4 小计后冒充 build 实测。

四条 p4 记录如下：

| record | bare field L2 / scaled curl | I4 true residual | I4 field L2 / scaled curl | I4 seconds | 真实不足 |
|---|---:|---:|---:|---:|---|
| `A2R160_BAL_H_p4_01` | `0.8489923330716638 / 0.8488357966287257` | `0.9502310252350668` | `0.9647147926182198 / 0.964639027200986` | `6.0514075710001105` | residual改善但场误差变差，且仍远高于 `1e-4` |
| `A2R160_BAL_H_p4_02` | `0.9146177153493735 / 0.9142807117909154` | `0.1012649488434464` | `0.8777570760481551 / 0.8773717677729929` | `5.5842256810014685` | residual和场误差均改善，但仍约 `10^3` 倍高于目标 |
| `LIGHT448_BAL_H_p4_09` | `0.8581820338128715 / 0.8581222874792352` | `0.9778952412775763` | `0.9928176043406823 / 0.9928022756707928` | `5.449962579003718` | residual改善但场误差变差，4 步内部纠错不足 |
| `LIGHT448_BAL_H_p4_10` | `0.9154309172609856 / 0.9151104456074007` | `0.10194959659698315` | `0.8775511199054001 / 0.8771869820432219` | `5.575606445003716` | residual和场误差均改善，但仍未达 `1e-4` |

四条 record 名称中的 BAL_H 是历史 g/reference packet 标签；本轮只做 bare B4/I4 内部检查，没有执行完整 BAL_H 或 ONE_C 外层 PC，因此不能推出框架优劣。reference residual 约 `1e-11` 和 A4 identity 约 `1e-13` 是评价/身份字段，不是 I4 收敛证据。已完成工作量的保守下界为 4 I4、至少 20 B4、至少 840 次局部 `M_D` solve；停止时的 in-flight work 未计入。

## 资源与 official 边界

新 profile 的局部库存 cap 为 `2684354560 B`，旧 V10/V11 cap 仍为 `2147483648 B`。O1 retained lifecycle 的最大记录值为 `2180383916 B`（C_U 后），W transfer 后为 `2180380092 B`，均低于新 cap；tree RSS/PSS 峰为 `2574671872/2539922432 B`，样本无 cap violation、swap 为零。这些字段分别代表 derived inventory 和 measured process-tree memory，不相互替代。

未运行项包括 restart32/64、p6 full residual、original/notch、E/H、near-field、R/T/A、`A_volume`、modal amplitudes、衍射级、守恒和 official result；p6 原方程 `1e-6` 门槛没有检验。V5 原始/notch 成功 baseline 仍保留，但其条件参考 workflow 的 448 页 global `pswpout` 归因仍为 `UNRESOLVED`。不得从局部残差、p4 reference residual 或低 swap 推导 official physics pass。

## 测试和交付

最终 changed-source focused regression 为 `27 passed in 0.72 s`；停止安全性 smoke 为 3 个 `PASS`，包括 monitor-at-10 保留安全解、external-at-50 保留 iteration48、真实 `FloatingPointError` 原样传播。9 个 V12 dat 的 public `--dry-run` 均 exit 0 且 PDE 未启动；qualified activation 下 `complex128/int32` ABI、`compileall` 和 `git diff --check` 也通过。Ruff 只做 parent 保存的 changed-file F821/F822/F823 检查通过，不作 full-repository Ruff 或 CI 通过声明。

raw stdout/stderr 已保存在 [focused stdout](outcomes/records/v12_final_root_focused.stdout.log)、[focused stderr](outcomes/records/v12_final_root_focused.stderr.log)、[stop smoke stdout](outcomes/records/v12_stop_smoke.stdout.log)、[stop smoke stderr](outcomes/records/v12_stop_smoke.stderr.log)，哈希和完整测试边界见 [test summary](outcomes/test_summary.md)。

## 分支状态与后续

本轮正式运行的 source SHA 为 `e8c3c82bab2687a811a11f0798a2879c725532b5`，review base SHA 为 `96e5d5fcfc3e801ef33d4a2d241ea7571937f734`；代码提交已推送至 `origin/task39extra`。本次 docs/evidence closeout 仍只提交到 `task39extra`，不得合并 `master`。审阅入口为 [V12 selective merge boundary](outcomes/selective_merge_manifest_v11.md) 的最新 V12 节、[workstation handoff](outcomes/workstation_handoff.md)、[development progress](../development_progress.md) 和 [model registry](../development_model_registry.md)。

若要继续 O1/O2/O3，必须先有新的 review、独立预算，并重新绑定新的 source/input/artifact identity；本轮不自动升 cap、延长 I4、扩 MPI、启动 5 nm/0.7 nm 或 workstation heavy case。
