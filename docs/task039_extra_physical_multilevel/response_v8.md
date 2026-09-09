# Response V8：V6/V7 收口与两条 bounded 候选的边界

## 最终结论

Task39extra 本轮收口为：V5 保留两个完整 BAL_H 成功模型；V6 递归粗逆及其真实误差诊断保留为未资格化负结果；V7 的 entity16 与 projected seq2 两条冻结 bounded 候选均在约 5400 秒中点未达 residual Gate。V7 没有新的官方场或物理结果，也没有 notch 资格。

| 范围 | 结论 |
|---|---|
| V5 | 原始模型 564 步、notch 576 步均通过完整真残差和物理 Gate；仍是唯一双模型 complete success baseline；R/T/A=`0.365625791/0.0129906323/0.621383577`、`0.337120585/0.0162886742/0.646590741`；whole `6997.531 s` / `7058.7424 s`，RSS `3466235904 B` / `3600924672 B` |
| V6 | G1/G2 与递归/互补诊断负结果不改写；粗近似未成为 production default |
| V7 A | 121 步，explicit true residual `0.04256451212826674`，RSS `1449623552 B`，midpoint fail |
| V7 B | 88 步，explicit true residual `0.06385558342151046`，RSS `1517813760 B`，midpoint fail |
| official outputs | A/B 的 fields、R/T/A、`A_volume`、near-field、衍射级均 `not_run` |

详细的逐 8 步曲线、真实调用成本、有限控制和 raw hash 索引集中在 [V7 中心结果页](outcomes/bounded_inexact_outer_v7.md)；hash-bound 机器记录为 [A compact](outcomes/records/bounded_inexact_outer_a_original_v7.json)、[B finite compact](outcomes/records/bounded_inexact_outer_b_controls_v7.json) 和 [B original compact](outcomes/records/bounded_inexact_outer_b_original_v7.json)。A compact 保持不变。

## V6 早期诊断背景与收口

V6 的早期诊断背景（不是 V7 新结果）包括：旧 H4/p2 outer 在 13 步时 `rho≈0.667843`、约 `1800.799 s`；owner 改善路线到 60 步约 `rho≈0.0080024`；完整 252 内部路线在 64 步约 `rho=0.03132214952676454`，该数只属于内部诊断，延长到 256 步约 `0.00037381775` 仍未达到 `1e-4`，并留下超时负证据。具体数字和分类以 [V6 中心报告](outcomes/coarse_inverse_replacement_v6.md)、[V6 compact](outcomes/records/coarse_inverse_replacement_v6.json) 及 [V6 recursive diagnostic compact](outcomes/records/recursive_p4_complement_diagnostic_v6.json) 为准；本轮没有重查或重跑这些记录。

此前真实难误差定位（`response_v6` 历史补充授权，而非本轮 Review V6 新结果）显示：匹配 fine reference 下三类场的相对误差约为 `22.46%/24.92%/31.34%`，但 phase-invariant M0 correlation 高于 `0.9975`；p4 表示缺失约 `0.83%/0.84%/0.82%` 范数，native A4 RHS 与 range identity 通过。难点来自小的 p6 互补场在物理算子下产生近等大反向 coarse RHS，导致粗修正与细层场误差不平衡；单位 coarse correction 甚至使 fine residual 增大，MR 小步长又几乎不改变场。该因果说明支持“当前粗细耦合不匹配”，不支持色散定理、整体近共振或连续真解等更强结论。

V6 G1/G2 固定输入和正式 I4 没有达到 LO target，V6 递归路线因此关闭为 `COARSE_APPROXIMATION_UNQUALIFIED`。fine reference 的约 7.23 GB 峰值和诊断的约 3.88 GB 峰值分别属于不同工作流，不能拼成 2 GB 资格；旧的 negative、resource caveat 和 `response_v6.md` 均保留。

## V7 方法与结果

V7 用受内存约束的局部修正为 p6 外层 FGMRES 提供近似预条件。A 使用高阶边/面实体局部修正，共 1566 个实体小因子（792 edge、774 face）；`16` 指 I4 的最多内层步数。B 使用两个各 126 个因子的 parity group，按顺序作用并在两组之间施加一次完整 `T`。B 不是 global p4 matrix/factor，而是用 252 个 144 维局部因子近似处理局部 block coupling。

`1e-4` 是 I4 inner early-stop target，不是 hard Gate。B 的 176 次 I4 都是合法 approximate return，最多 16 步且观测耗时低于 30 秒；外层成功仍必须由 full explicit true residual 和物理 Gate 判定。A/B 的 native A4、旧 S bridge、输入不变性和 slave constraint closure 通过，但这没有消除 outer longtail。B 额外的 complete T 与 patch work 在实际成本下没有优于 A。

两条冻结路线的中点结果都高于 `1e-3` 进度线，因而 classified 为 `PROGRESS_INSUFFICIENT_AT_MID_BUDGET`。这表示它们在本轮预算中有可观测的 residual reduction，但不具备完整求解资格；`WORKER_FAILED` 是 wrapper/worker 退出分类，不能被解释成 engineering crash 或 physics mismatch。

## V5 完整基线、V7 总时间和扩展债务

V5 original 的 solve/whole 时间为 `6102.6143 s/6997.531 s`、RSS peak `3466235904 B`；V5 notch 的 whole 时间为 `7058.7424 s`、RSS peak `3600924672 B`。按统一 parent/whole conservative 口径，V7 A 为 `5637.122687149011 s`、RSS `1449623552 B`，V7 B 为 `5622.279368720655 s`、RSS `1517813760 B`；A 的 workflow monotonic `5167.972956766025 s` 另列，不与 B 的 whole conservative 混比。A/B 虽然失败得早且 RSS 较低，却没有完整 residual、fields 或物理输出，不能与 V5 成功 baseline 做“更快/更省”的等价比较。

当前 B 仍依赖全局 S/p2 factor（`7326 rows`）。252 patch 的历史构造约为 `1603.835 s` 和 `36288` 个 S columns；本次 `restored_factors=252` 是复用已保存结构，不表示 fresh 构造成本被消除。该构造与复用债务、以及 0.7 nm 的规模扩展债务仍未解除。

## 对本轮六个审阅问题的直接回答

1. **finite seq2 是否真实且合法？** 是。finite witness 的输入、slave constraints 和 seq2 explicit relative 均通过；它证明有限比较的代数/约束闭合，不证明 complete outer convergence。
2. **`1e-4` 是否必须由每次 I4 达到？** 不是 hard Gate，而是 inner early-stop target。176 次 B I4 的 approximate return、16-step 上限和小于 30 秒 hard-time observation 均符合冻结 bounded contract。
3. **B 是否解决了 A 的长尾？** 没有。B 在 88 步 residual `0.06385558342151046` 停止，A 在 121 步 residual `0.04256451212826674` 停止；两条曲线都没有接近正式 `1e-6`。
4. **B 的额外结构是否值得成本？** 本轮实测不值得。B 使用 252 个局部因子、2812 个 complete T、708624 个 patch backsolve 和 8436 个 S/bottom solve；实际中点 outer charge 与 A 同为约 5.6 ks，且 B residual 更高。更完整的 V5/V7 时间和 RSS 对照见上一节，失败 workflow 不能冒充成功 solver 的节省。
5. **RSS 低于 2 GB 是否构成成功 PDE？** 不构成。RSS 是受控未完成进程树的资源观测；A/B 没有 official fields 或 R/T/A，p2 policy budget 也不是 allocator/RSS 上界。即使失败 workflow 的 RSS 小于 V5 成功 baseline，也不等价于节省了完成同一任务的总成本。
6. **本轮能否推出所有无 global p4 LU 路线都不可能？** 不能。证据只关闭 entity16 与 projected seq2 两条冻结 bounded candidates；其他算法、机器或实现的可行性没有被本轮证明。

## 资源、预算与工作站边界

A/B process-tree swap peak 和 global swap delta 都为零，但低于 2 GB 的峰值不能改写为完整 PDE 成功。共享 ledger 在 finite preparation、controls 和两次外层尝试后为 `12327.598368146999 s` charged、`30872.401631853 s` remaining，其中 B 账内已包含 `132.113 s` preparation charge；具体模型级费用和双时钟口径见中心结果页及 B compact，模型等待时间不重复计入。

本轮不启动新的 workstation heavy case。V5 baseline 可以作为复现参考；V6/V7 不提供 0.7 nm 或 2 GB production capability。未来若重新授权，必须先重新冻结 source/input/environment、资源口径和独立 physical output Gate，不能从本轮两条 negative 外推普遍不可能性。

## selective merge 建议

| 依赖组 | 本轮结论、依赖和顺序 |
|---|---|
| production numerical/core | 不因 V7 负结果改变现有 production 数值核心或 ordinary default；V7 profiles 仍需独立批准，先审既有 source/test commit |
| reusable runner/watchdog | 可审阅现有 bounded route、单 KSP、midpoint stop 和 descendant cleanup；J5 本轮不修改 runner，V7 route 本身已在 source `355322e8…` 中实现，依赖其 targeted tests 和 fresh raw evidence |
| checker/benchmark | finite `checker_recheck.json` 是独立 audit 入口；保留正式 outer checker 原规则，不把 2-vs-4 audit mismatch 写入 production fix |
| compact evidence/docs | 合入本轮新增 B finite/B original compact、V7 center、response V8、summary/index/handoff；保留 A/V5/V6 raw identity，作为最后文档组审阅 |
| research-only | entity16、projected seq2、252 patch construction 和 V6 recursive/C paths；均有局部或完整负结果，不升为 ordinary default |
| do-not-merge | raw results、fields、matrix/factor、cache、timeline、checkpoint 大文件和 ignored audit scratch；只以 hash-bound compact 定位 |

本表是依赖分组建议，不是 merge approval。最终合并仍需明确批准并由 Codex 执行；本轮没有合并到 `master`。

## 测试与身份

本轮只做 J5 文档/compact 合同检查和 diff 检查，不重跑 PDE、MPI、factor、正式 checker 或 full pytest。此前 source change 的最小相关测试在 source `355322e8be0716cdc3dd70df2665b8c74ff76583` 上为 `8 passed in 0.22 s`；它与本轮文档修改分开记录，不能冒称 full repository 或 CI 通过。

执行分支为 `task39extra`，source HEAD 与 `origin/task39extra` 均为 `355322e8be0716cdc3dd70df2665b8c74ff76583`，ahead/behind 为 `0/0`。本轮文档的最终提交与推送状态以随后 Git 回执为准；没有修改 task、review、生产 source/test 或 A compact。
