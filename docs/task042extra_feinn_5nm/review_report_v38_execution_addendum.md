# Review V38 执行补充：远端尚无新数值提交，完成唯一 V39 工作包

## 0. 裁决与身份

**本次回读远端时，HEAD 仍是 Review V38 的发布提交；没有新的已推送数值结果可供授予资格或否决新实现。继续执行 Review V38 已批准的 V39_STRUCTURE_AWARE_FTT_COMPLETION，不新开 V40，不更换神经方案，不重新获得一份12小时预算。本文件是执行补充，不是假称完成了对 Response V39 的审阅。**

```text
repository                  = Rookie1234567/MyFEniCS
branch                      = task42extra_feinn_5nm
canonical_worktree          = /home/fenics/Projects/NN-Lab-V2
review_date                 = 2026-10-10 Asia/Singapore
observed_remote_HEAD        = 15d20ed4f109fef52376a13e58c1204bce89d588
remote_latest_commit_time   = 2026-10-10T04:05:41Z / 2026-10-10 12:05:41 +08:00
latest_numerical_result_HEAD = 8136afcd8a5229974556038428b28833eafb9c91
latest_available_response   = response_v38.md
controlling_review          = review_report_v38.md
campaign                    = V39_STRUCTURE_AWARE_FTT_COMPLETION
required_response           = response_v39.md
new_campaign_or_budget      = NONE
production_or_merge_master  = NOT_APPROVED
```

原目标为0.7nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet、Fourier-DtN、完整E/H/衍射/体吸收；十进制2e12B是整机内存，保留系统余量、自身swap/OOC为0，单场必要准备至完整检查不超过172800s。**当前目标尚未通过；本支只做神经研究，不承接传统Full3D辅助工程。** 本轮问题属于神经求解成本、数值资格和执行证据闭环。

本补充不改变原物理、算法、精度、候选容量、阶段预算及安全门。仅明确现场状态分流、同一任务继续执行和不重置预算；不因新增一份文档使已经运行的合格source、检查点或数值证据失效。

## 1. 这次实际查到了什么

已实际读取分支HEAD/提交时间、任务目录、根AGENTS、仓库原则、任务目录AGENTS、原task身份、最新summary和训练费用记录，并回读Review V38的blob身份。原Review V38全文由本会话挂载原件读取并核对Git blob；原任务及其他未变规则沿此前原文衔接。本次没有新代码差异可审，不重复声称发现了新的实现问题。

在上述固定HEAD查询 `docs/task042extra_feinn_5nm/response_v39.md` 返回404；summary当前入口仍为V38。与上次已发布的Review V38相比，已推送的新提交为0。这里说的是**远端记录未更新**，不是工作站没有执行。审阅端未连接工作站，未查看本地PID、锁、未提交代码、未推送commit或ignored结果，现场状态为UNKNOWN；不得凭远端静止断言Codex空闲、故障、已经超时或已结束。

依据：[Review V38](review_report_v38.md)、[Response V38](response_v38.md)、[summary](outcomes/summary.md)、[原训练与费用](outcomes/records/training_and_fit_v38.json)、[原物理Gate](outcomes/records/full_numerical_gates_v38.json)。所有数字是此前执行端measured，本轮只读复核，不是新测量。

| 同M5/5nm/384hex/p3/N31968/40端口 | FTTNN | Cheb-TT控制 | 判断 |
|---|---:|---:|---|
| 完整梯度调用 / Adam更新 | 46 / 46 | 68 / 68 | 未到原Adam500边界 |
| L-BFGS外层步 | 0 | 0 | 主要后段尚未执行 |
| native/augmented相对残差 | 0.998818668222 | 3.39713275365 | 原门1e-6，均FAIL |
| 散射E相对误差 | 0.999950913962 | 0.999993299439 | 原门1e-4，均FAIL |
| 独立能量闭合误差 | 0.414094976032 | 0.414078472276 | 原门1e-5，均FAIL |
| 新结构映射的正式结果 | 远端无新增证据 | 远端无新增证据 | 不判作PASS，也不判作新失败 |

原FTTNN worker的核评价、连乘、点包装/AD分别约1099.845/495.139/1659.498s，合计约94.7%；A/A*合计约8.831s。该数据继续支持先降低神经映射重复工作的方案；不支持跳去开发新的Maxwell预条件器。没有新证据，不再推荐另一个rank、loss或网络变体。

## 2. 先确定现场处于哪一步，不把状态检查做成新项目

Codex先利用已有锁、run index、PID/start_ticks、checkpoint与Git状态作一次有限只读检查，简要告知当前状态，然后继续。不得全盘扫描、重复全仓hash或编写新监控平台。

| 现场事实 | 本轮直接动作 |
|---|---|
| V39尚未启动，没有合法活跃作业 | 安全同步后立即实施Review V38的A，资格和性能过门后同批执行B及条件C/D与终验；不再写一轮准入提案 |
| V39已经合法运行 | 不改运行工作树HEAD、代码、环境或CPU配置，不kill、不启动第二份；保持同一监督链。此纯文档补充不要求重启 |
| 已有部分完成阶段，当前没有活跃数值作业 | 核对source/输入/模型/数组hash，复用健康阶段，从下一依赖阶段或匹配的完整检查点继续；继承已耗时间与调用 |
| V39已完成但尚未推送 | 优先核对完整原始Gate及交付，发布实际 `response_v39.md`、compact记录和源码提交；不为本次审阅重复跑整包 |
| 发生普通可修复工程故障 | 最小修复、受影响定向测试、绑定新source，复用未受影响数据后继续；不以目录、writer或页面错误结束整批 |
| 真实安全/权限/ABI/不可恢复输入问题，或原总预算已经耗尽 | 保护自身子树，保存准确证据和未运行项，完成可做的轻交付；不改门、不清零预算，也不冒称数值通过 |

**本次用户重复要求审阅，不构成重新启动或重置V39的授权。** 若V39尚未首次启动，按原合同建立其唯一窗口；已经启动就沿原起点、截止及账本执行。超过截止后不能把本补充当新12小时窗口。远端提交时间不是工作站campaign起点，必须读原账本。

## 3. 最近应取得的实质结果：先测整步成本，再完成原优化量

保留Review V38第3节的两级实现：各轴严格相同节点核值复用及余切scatter-add；可证明张量积结构的完整矩作一维有限和重排。原材料、A/f和DtN不低秩近似，不减q，不裁小非零，不形成大Jacobian或全局波库。不能张量化的行用已授权准确后备；不因一行不支持就放弃整个映射。

原逐点实现保留作独立对照。正确性、参数更新和缓存失效检查通过后，计时必须包含setup、完整loss/gradient、更新后c/r及保存，不只报告热前向。按原式判断两小时能否承受剩余优化量：

```math
T_{\mathrm{setup}}+1.5(1000-n_{\mathrm{inherited}})t_{\mathrm{full}}^{\max}+600\le7200.
```

沿原记录，FTT/Cheb名义剩余954/932调用。仅将setup取0作**最乐观必要条件的推导**，完整工作最大实测时间应分别不超过约4.61/4.72s；实际有setup时更严格。这不是本轮实测，不是承诺加速倍数，也不是额外修改原性能门。若实现仅略快、仍需几十秒，就应继续修复已经授权的结构计算，而不是马上消费新两小时长训。

资格与性能都过门后，继续原无标签FTT/Cheb完整状态，累计Adam500后fresh原L-BFGS，原总调用1000和每条新增7200s不变。已有V39更新优先续用，不退回V38重算；从V38起步时分别使用原Adam46/68完整状态与匹配动量/RNG。参考拟合始终隔离，不能成为主训练初值或误差修正来源。

无需在“内核写好”“tests通过”“实现已commit”处分段等待review。允许的继续执行范围已在Review V38给出。另一方面，若完成原预算后仍不合格，不能用另一个未授权优化器或传统完成器制造成功。

## 4. 何时才算推进了最终目标

一次交付必须分开回答以下三层问题，而不是只给一个PASS。

| 层次 | 本包必须给出的证据 |
|---|---|
| 计算机制 | 等价映射是否完成；完整一步成本与峰值；原预算是否足以执行原优化量 |
| 神经数值 | 实际累计Adam/L-BFGS和调用；native/增广/独立total残差；实际模型完整E/H/curl、复通道、功率和体吸收 |
| 目标与成本 | 同离散精度是否通过；同精度资源收益是否成立；冷N=1缺项与2TB/48h仍未验证项 |

正式门全部沿原合同：三原残差各1e-6；total/scattered E/H/curl、六点复场和四类完整通道向量各1e-4；功率/体吸收/独立能量1e-5；逐级功率1e-6；实际模型/MPC/端口恢复1e-10；独立求积1e-8。保留分子/分母，不能用背景主导的total掩盖散射误差。

只有无标签FTT的M5联合PASS、安全且原窗口余时符合Review V38，才有条件运行原授权0.7nm缩小非可分三维pilot；未过不预注册空输入。长度×0.14保持近似几何/波长比，并不解决原尺寸电尺寸增长；通过也只是晋级证据，不是原尺寸0.7nm完成。p3同离散通过不代表p/h或端口收敛。

神经核提速不等于传统FE被超越，更不等于整个流程已可在2TB内48小时结束。核心判断仍是：更大内存不能补救尚未求准的原方程。本支不向Task42、主线或dot派活，不以Full3D组件进展替代神经数值结果。

## 5. 安全、Git与不重复执行

原V39总窗43200s、候选及条件阶段上限、最后1800s预留、数据/环境/资源provenance不变。CPU-only/MPI1/math/Torch1、数值warn12/hard16GiB、规划12GiB、新cache/AD1GiB、轻2GiB、自身swap/OOC0、原PSI和系统/384GiB邻增长保护不放宽。普通bug无次数交棒卡，但修复、失败和等待全计入原窗。

合法活跃计算期间不为拉取本补充改变HEAD。无活跃作业且工作树可安全更新后，使用原精确refspec同步。若本地已有未推送V39提交，不得reset或rebase/amend丢弃实现。**仅当工作树clean、无活跃run、确认远端分歧部分只有本执行补充等本任务审阅文档、且不存在数值文件冲突时，允许同一执行分支的一次普通merge保留双方历史；不得merge master或其他任务分支。** 出现冲突先保留两侧文件并报告具体路径，不强行覆盖。纯审阅文档合并不要求重跑hash绑定的旧健康数值。

本补充不增加stage、不增加参考求解、不增加训练预算、不要求新建状态服务。继续使用既有V39输入和 `scripts/launch_task42extra_durable.py` 包装，其内部通过 `scripts/run_case.py` 执行one-run dat。执行顺序、checkpoint hash和详细数学以原Review V38为准。

## 6. 一次交付，结束审阅—改名—重新启动的循环

唯一数值回执仍为 `response_v39.md`，专题仍为 `outcomes/ftt_structure_aware_v39.md`。现场状态、复用/恢复、修复账与是否实际进入L-BFGS直接并入已有V39记录，不再专门创建另一个空结果版本。当前远端没有Response V39，不得在交付中说本补充已审阅了它。

若完整结果已在工作站，优先发布该结果。否则完成原已授权包，再提交实现/测试、真实Gate、互斥费用和资源、source/input/artifact绑定以及本分支summary/总账。大数组留ignored，健康数据不因文档/封存错误重算。发布只限本分支，不强推、不amend、不merge master。

本文档的结构和远端blob一致性可由发布端核对；GitHub完整浏览器视觉未验证，不追认视觉PASS，亦不令网页故障阻断数值。没有新的数值算法，本次不声称执行了新的FE/训练或M5回归。

**最终要求：下一份交付提供真实的映射性能、优化执行量和联合物理Gate，或者准确的已触发硬出口；不能用重复审阅、重复准入说明或未推送的状态替代结果。**
