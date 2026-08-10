# Task37c R0：继承的 Task37b master 审计

本文件是 Task37c 第一阶段的只读继承审计。它记录已经发布到 master 的 Task37b 选择性内容、
最终 M10 anchor 证据和本任务的明确边界；本阶段没有修改 solver、runner、watchdog、checker、
测试或配置，也没有运行 PDE。

## 1. 分支与来源身份

| 项目 | 值 | 证据语义 |
|---|---|---|
| 创建时 master | `ee779be42004d555f9aba21bf54f8ca8d3287ff4` | Task37b 发布后的 master 起点 |
| 当前分支 | `codex/20260810-task37c-hybrid-iterative-robustness` | Task37c 唯一执行分支 |
| upstream | `origin/codex/20260810-task37c-hybrid-iterative-robustness` | 非强制 push 后精确跟踪 |
| 创建时 local/remote | `ee779be42004d555f9aba21bf54f8ca8d3287ff4` | `0/0`，clean |
| Task37b reviewed source ref | `origin/codex/20260807-task37b-hybrid-iterative-development` | `00293d95419f0435407c04bc5312ed1e61e20415` |
| Task37b M10 implementation provenance | `b291f3dfdf5f0064ff243038f6809172f811d7aa` | M10 生命周期优化的历史 source |
| 当前 R0 结论 | `docs-only` | 不继承 Task37b 未合入的研究分支代码 |

本审计读取了 [Task37c task](../task.md)、Task37b 的 task/review/response/outcomes、
仓库治理与 Markdown 合同，以及 master 中实际存在的最终 runner/core/test 文件。Task37b
的完整全仓 authority 是其代码/config parent `f99d6cd7d76f4e369d13b88166b788e80802dfd0`：
`899 passed, 48 skipped`，`1370.06 s`；其日志在 `/tmp/task037b_v7_full_pytest_f99d6cd.log`。
`ee779be` 只增加 Task37c handoff 的两份 Markdown，因此 R0 不重复运行该全仓 Gate。

## 2. Task37b 的 17 个选择性 master commit

下表是 `454df04358bd4e1670ec14c5b0276b430249cd37..ee779be...` 的完整顺序。职责是对
已审阅提交的实际内容作摘要，不把历史研究分支重新带入 Task37c。

| 顺序 | 完整 SHA | 职责 |
|---:|---|---|
| 1 | `80a3bd834d0916d73b02cf89e0ede56dc8955e23` | fenced math、仓库 README 与文档合同 |
| 2 | `4a2d9184b7286329dfe515484c106c6eb8fa4df6` | 导入 V7 reviewed qualification docs/outcomes |
| 3 | `452e6c612ae66c3f9844c8de35b59d7773791f06` | near-degenerate grouping 与 static recovery contract |
| 4 | `582774c1c072eb904fbd2a8686a5780e80cf1a9c` | 触碰 recovery 模块的机械格式 Gate |
| 5 | `f985f78af4fbf093f82c02ba0ba0d68e6ec01323` | exact matrix-free Hybrid action |
| 6 | `5924e326e7b13d560b3d2e15f01f75514861bd76` | fixed whole-endcap ILU(0) 与 40-mode DtN Woodbury |
| 7 | `03459ea014715de5cf089c11c2ff7b6b033d2b91` | action-consistent modal Schur 与 block-LDU iterative core |
| 8 | `80281f2c454b348cdc357bc801fbe911c8579515` | bounded canonical vector streaming |
| 9 | `1552798b60afe4ae4eaf52b55883459dfd77c454` | Floquet phase assertion 的 partition-safe 测试修正 |
| 10 | `98e54ba0ba250754603e9569f9c5197218e92b54` | pinned Full3D authority binding |
| 11 | `8c7fff2fb911bb6b7b96fa829807a8c6e33bf063` | explicit-opt-in frozen M10 runner |
| 12 | `7a49b4c030a8afd6d49541fd182cf445d54cf778` | frozen M10 process-tree watchdog |
| 13 | `9c8158ea0b5a730b83044fe0b79714c32d6de65d` | 独立 frozen M10 offline checker |
| 14 | `c360dd77efe2f939d648e86a4aa9e6eee743f9b5` | frozen qualification、compact 与 handoff 文档 |
| 15 | `4b6f361ca02c1088924f8179a6645df2bf1dd259` | M10 physics 后处理使用 recovered physical fields |
| 16 | `f99d6cd7d76f4e369d13b88166b788e80802dfd0` | checker 绑定 reviewed H1/Full3D/significant authorities |
| 17 | `ee779be42004d555f9aba21bf54f8ca8d3287ff4` | Task37c continuous-execution handoff 两份文档 |

## 3. 已进入 master 的 runner/core 与 ordinary boundary

实际存在的专用入口和组件为：

| 层次 | 路径 | R0 审计结论 |
|---|---|---|
| runner | `benchmarks/run_task037b_hybrid_iterative.py` | 只接受显式 `--frozen-m10`，无 flag fail closed |
| watchdog | `benchmarks/run_task037b_hybrid_iterative_watchdog.py` | 只观测 frozen M10 进程树，固定 MPI8/资源口径 |
| checker | `benchmarks/task037b_hybrid_iterative_checker.py` | 只读重算 online、payload、canonical 与 authority |
| action/core | `src/solvers/hybrid_fem_modal_iterative.py`、`hybrid_fem_modal_block_ldu.py` | exact operator、action Schur、right FGMRES、五残差 Gate |
| endcap/core | `hybrid_local_dtn_action.py`、`hybrid_local_dtn_woodbury.py`、`hybrid_whole_endcap_fixed_smoother.py` | 两侧 fixed whole-endcap ILU(0)+DtN Woodbury |
| canonical | `src/solvers/hcurl_canonical_vector_dolfinx.py`、`benchmarks/canonical_vector_artifacts.py` | active/full bounded streaming |

runner 的 ordinary direct Hybrid 入口没有被 frozen flag 改写；`ordinary_default_changed=false`。
M10 是 research-only、explicit opt-in 能力，不是 production default，也不是新的物理方程。

## 4. M10 final anchor 证据

最终 `ee779be` clean source 的唯一 online raw 目录、watchdog 和 checker 均在 Git-ignored
`benchmarks/artifacts/task037b/v7_1_integrated_m10_ee779be_mpi8_final*`。两份摘要的 hash
分别为：watchdog `8075b978b6d08472fa9009e1ba9cc282e25f9e88d1e88117818ecd0b80dce6c9`，
checker `50065d1702a8e4aaaf26e9a7b7f297a5da9bd044544cbcfd4e96200ddac8e334`。

| Gate/指标 | final measured value | 结论 |
|---|---:|---|
| KSP reason / iterations | `2 / 792` | numerical pass |
| reported/global/bottom/top/modal | `3.5780619125563715e-9 / 3.5780616039507176e-9 / 4.92185571070692e-9 / 2.6635961838749455e-9 / 1.0981513620080873e-15` | 五项均 `<=5e-9` |
| exact traction bottom/top | `4.820140963800131e-9 / 2.6635961838749455e-9` | 均 `<=1e-8` |
| R/T/A/A_volume/closure | `0.0007628816277262339 / 0.6027016338728411 / 0.39653548449943266 / 0.39653548508185416 / 5.824214444061226e-10` | finite，energy pass |
| external orders | `80/80`，unique/finite/identity valid | pass |
| recovery and q | 两侧 40 mode，q residual `0.0 / 0.0` | pass |
| canonical | bottom/top active-trace/full-FE 四 role | pass |
| selected fields | own-grid 与 H/E payload 对齐 | pass |
| significant authority | iterative/direct Hybrid power/amplitude `12/12 + 12/12` | pass |
| process-tree RSS | `6036.2265625 MiB`，峰值阶段 `own_physics_grid` | `<6144 MiB`，resource pass |
| swap | `0 MiB` | pass |
| total lifecycle | `461.623009 s`；linear `175.0794349249918 s`；physics `17.129798026988283 s` | measured |

watchdog 是 `watchdog_pass_awaiting_offline_checker`，checker 完成后为 `pass=true`、
`failures=[]`、evidence integrity/authority bindings true；checker 自身资源不计入 online
RSS。raw modal coefficient 保持 independent-QEP gauge diagnostic，资格权威是 modal magnitude、
物理 E/H、orders 与 energy，而不是逐项 raw coefficient 相等。

## 5. 排除项、正式运行边界与动态 mode 审计

本次选择性合入没有带入 H5/V1/V2/V3 负结果的可执行 machinery、standalone local inverse、
nested local FGMRES、M1–M9 profile runner 或其 raw artifacts。它们的历史结论只在 V7 文档中
作为审计证据保留；大场、matrix、factor、timeline 和 stdout 均不进 Git。

Task37b 的 formal PDE policy 是 MPI8 anchor 与 MPI1 诊断；MPI2/MPI4 只用于轻量 action/
lifecycle tests，不把它们写成 formal PDE qualification。

当前 master 的 M10 profile 明确固定 `dtN_modes_per_endcap=40`、`candidate_modes=240`，
并在 runner/checker/test247 中有 40-mode shape、identity 和 Woodbury rank 合同。因此它不是
Task37c 所要求的真正动态 external-mode 支持。R0 只记录这个缺口；R1 才可做一个窄的动态
dimension 修复和 focused test，不能在本文件中提前修改或重跑。

本 R0 审计结论是：Task37b 的 frozen M10 research capability 已由 master 继承，ordinary
direct/default 未变；Task37c 的 1° S 偏振、方位角鲁棒性、dynamic mode 和 MPI1 正式工作尚未开始。
