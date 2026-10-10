# W0.7 bounded modal policy：V12 准备进度

## 结论

本阶段完成了 V12 有界模态策略的 11 路径代码提交、分批 serial/MPI2 合同验证、service resolve 与 public CLI `--validate-only`，并生成了纠正 method 冲突的独立 warm 包。**没有发出 dispatch，也没有运行新的 QEP 或 FE。** 修正包不继承父包 2026-10-10 08:24 UTC 的 host admission；它自己的 fresh 双样本门尚未运行。

直观地说，模态内层是外层求解器使用的“近似帮手”：它即使没有达到内部 `1e-3` 目标，只有在正常结束、向量可信且独立残差有限并满足 `eta<=0.1` 时才允许作为预条件器返回。策略先用 fixed-H6；符合明确触发条件后，最多切到一次借用现存侧区因子的 fixed physical BAL_H。任何异常、非有限值、布局/身份错误仍拒绝，不用备用动作遮盖。原方程、outer 与最终五项真残差/物理门不变。

## 提交与测试账目

| 项目 | 状态 | 证据 |
|---|---|---|
| 提交 | `eca72c8b12e2b979f919cb5b69578ad99111fef0`，parent `8af296d9cbe41e7132e9e623574d9b9a5fb5fdda`，原分支 upstream 0/0 | 精确 11 个获审源码/测试路径；stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976` 保留 |
| source binding | 34 runtime + 5 test = 39 条；SHA `ecfbf7c4650fa47951b8a5a727717b1edb68d428d75146dedc56bfbf1e8294bb` | 每条 Git HEAD blob OID/hash 与工作树逐项匹配 |
| pytest attempts | 15 个唯一父 attempt，累计 `184.67645929614082 s` | V5 218→233 项；只计一次每个 attempt；ABI/preflight不计 |
| ledger | SHA `18bca854947d3dbfecc2081153469e70d5b395dd70e507bd0a1c3ac9400378f1` | 当前 233 条 |
| attempt compact | [compact JSON](../../../results/task041_v12_a2_setup_public_bridge_scope_fix_fixturefix16_20261010T0814Z/v12_a2_test_attempts_compact.json)，SHA `6b7338fb08996301c37d2c637ab7637d0a729c8c3de44e777cfcd7663dd63406` | 含逐 attempt source SHA、stdout/attempt SHA、pass/fail/skip、wall 和清理结果 |

证据是分批的：restart64/backup 小测试在不同 serial 和 MPI2 attempts 通过；一个 MPI2 attempt 因 non-owner rank 的测试断言先失败而等待 collective，父 wall `133.939134262 s`，已保留并清场；另有 staged bridge scope 与 default trial-state 接线失败记录，随后修正并以受影响的 public/setup 节点通过。最终 fixturefix16 两个 setup/public 入口通过，父 wall `5.392439984 s`。测试 SHA 按 attempt 变化，**不能说最终 commit SHA 在单次完整组运行中通过**。测试不包含真实 W0.7 FE，也不验证真实模态收敛或全物理结果。

## Warm 包身份与固定合同

| 内容 | 封存身份/约束 |
|---|---|
| 准备包 | `results/task041_v12_w0p7_bounded_modal_backup_policy_only_preparation_20261010T085320Z/`；manifest 17 项 payload；SHA256SUMS 全通过 |
| config | SHA `d9dcbb98be62870d1db14e9da1a206d9c00b80a7534e81d6c85be71646bae460` |
| systemd argv JSON | SHA `849ee146a1a2548a5ef51e428d721470f79b7e3a6319e4f261364661edb91674`；真实执行字段是 JSON argv 数组，包内 `dispatch_authorized_by_package=false` |
| unit / runroot | `task041-v12-w0p7-bounded-modal-backup-policy-only-cpu10-11-14-15-16-17-18-19-20261010T085320Z.service` / `results/task041_v12_w0p7_bounded_modal_backup_policy_only_run_20261010T085320Z/` |
| policy/method | 独立 `modal_feedback_method=null`，唯一请求为 `task041_v12_bounded_inexact_modal_once_backup`；初始 actual fixed-H6；条件备选标签 `fixed_physical_balh_once_modal_gmres_research`，当前皆未运行 |
| numerical model | W0.7 reduced，10×5 nm、p6/h0.70、M400/MPI8、interfaces 2/22、matched L20/N29/h20/29；producer复用，QEP=0 |
| original gates | PORD/同因子延迟 numeric；P4 target `5e-13`/最多2次；fixed-Q原残差门、8项 SH setup、modal solver/total S budget 34/35、outer原五项 residual 与恢复/物理门不改 |
| resources | hard `85,899,345,920 B`，warning `77,309,411,328 B`，W `8,589,934,592 B`，node0 floor `412,316,860,416 B`；无 elapsed stop，swap按现有 V8 绑定仅观察 |
| producer / bridge | producer source `2708214386d38bd69f73e6b196c8ed843bb53d81`，manifest `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`，identity `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`；bridge SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b`；QEP不重算，准备阶段不读全 shards、不重复跑validator，consumer正式路径仍执行原封套/lifecycle验证与 hydration |

config、public command、systemd argv、service parent/ExecStopPost 的路径一致；public argv 不含 standalone feedback-method flag，仅带 fixed-H6 与 V12 solver-policy。39 条源绑定在当前 HEAD `eca72c8b12e2b979f919cb5b69578ad99111fef0`。CPU tuple 为 `[10,11,14,15,16,17,18,19]`。复用既有 ABI 记录的 rank map、native complex128/Int32、membind0、六线程环境和精确桥；该 MPI8 ABI 记录的测量源码 HEAD 为 `f4718519d8a244eae9ea87148422ade14771e534`，不是当前 Python 代码的数值测试。

包内 service `_service_contract` 将请求解析为 pure fixed-H6 primary + V12 once-backup policy；同一 public command 追加 `--validate-only` 后返回 `valid`，stdout / stderr 与 receipt hash 见 Response V14 和包内 `public_validate_only_receipt.json`（SHA `9ba7bfc5699588d64a9a5d8210580cd6262ee881b88cee4d572c35985b27f720`）。该入口在 launcher 前结束；仅读五个小 producer envelope，不读 shards、不运行完整 packet validator、QEP 或 FE。

修正包 manifest 中沿用的 host raw/assessment SHA `9afef4e5aac0bdff309040984653965c9e680730f3ab43e9bb037e6884ea1a0a` / `ae4fc65137778eab4841529c14158175d324c978f01e6fab5f117a1b3bffba82` 属于父包 08:24 UTC 样本，只是历史来源记录，不是修正包的 fresh 准入。修正包启动前仍须重新检查 CPU、邻任务、manager/unit/root、host/node0/cgroup/disk；不得把父包样本说成当前通过。

## 未运行与下一步

| 项目 | 状态 |
|---|---|
| dispatch / service Invocation | `not_run` |
| 本包新 QEP、packet shards 预读、完整 validator | `not_run`；consumer 正常路径负责既有检查与 hydration |
| 真实 two-side numeric、modal backup、outer、五项 true residual、恢复、E/H/RTA/A_volume/衍射 | `not_run` |
| 数值资格 | 未建立；本准备不能称 FE PASS 或 W0.7 完成 |

下一步是主控审阅此包及之后需要的 fresh 启动门。本阶段不 dispatch。W5问题按用户决定延期处理，W2不延误W0.7主线；50×25 nm、2 TB与48 h目标仍在本记录之外，未完成。
