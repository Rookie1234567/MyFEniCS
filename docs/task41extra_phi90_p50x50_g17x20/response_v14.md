# Task41 Review V14 response：有界同 LU 残差校正的保存包结果

## 结论

V14 在既有保存数据上验证了两组局部候选：原 trace 关联 cells 360/446，以及已保存 star cells 23352/23493。初始 wide-arithmetic independent checker 对两组都返回 `INCONCLUSIVE`；对保存残差的 Decimal 补充复核分别返回 `LOCAL_CANDIDATE_PASS`。这说明八个局部 RHS 的残差下降经较宽算术复核仍成立，**不等于完整算子、候选恢复、科学资格或 official result 通过**。

V9 的全域 full-action 门保持原失败：两列相对差分别为 `2.674977063720297e-10`、`5.613598120037966e-10`，限值 `1e-11`；最大差行均为 87567。V14 没有重算或改写这个门。V14 全部服务回执均为 `official_result=false`、`scientific_qualified=false`、`full_owner_unlocked=false`；未运行全域 owner/action/recovery，也未生成 official R/T/A。

本候选在原 LU 初解后，用实际 K 计算 RHS 残差，并以 `math.fsum` 分别补偿累加实、虚分量；残差校正最多两步，共用原 LU，不另做分解。这样能减少局部求和误差，但仍受浮点乘积误差和局部覆盖范围限制。每个 RHS 做两次残差计算，两次合计实测 `0.117–0.183 s/RHS`；8 个 RHS 共 16 次计算。四个候选单元覆盖两个 tag 和两个方向，不新增积分来扩充覆盖。

## 身份与窗口

| 项目 | 已核记录 |
|---|---|
| Review V14 / 结果 base | `5707187055d79083879b69f41fc2c9c084f70ff0` / `e9cbfb0ed3d26257d6c70c7de8ce7b3e21fe88c2` |
| 执行分支 / 最终源码冻结 | `task41extra_phi90_p50x50_g17x20` / `eb57f88f26fb3cbbe0d7c34ebb725f9a6b310fe1` |
| 最终源补丁 SHA-256 | `e64a266cec40bc054652623bb1bf320e2b312c3ba5eca288c614598c63ab2af2` |
| V14 固定窗口 SHA-256 | `4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c` |
| Window T0 / 截止 | `2026-10-25T08:47:53Z` / `2026-10-25T14:47:53Z` |
| 预算 | 总 21,600 s；数值截止 20,400 s；保留收口 1,200 s |
| 最终定向测试 | 7 passed in 9.15 s；日志 SHA-256 `54397e91fa48c6889c4b2b969c5d91d14258c864cc9464b12e4c40f32006ebb3` |

最终测试由原资格化工作站环境执行；本地没有再次运行 pytest。16 passed / 10.27 s 是早一版源码快照的结果，日志 SHA-256 `fb1385482a4bcad7311a35ff19625734f1139a5f913eda3a83e9aabefbbc7d31`，不替代最终 7 项复核。没有运行全仓 pytest、Ruff 或正式 FE/PDE。

## 保存候选与复核结果

| Attempts | 保存范围 / 证据 | 初始独立复核 | Decimal 补充复核 | 资格边界 |
|---|---|---|---|---|
| 01 → 03 | cells 360/446、columns 0/1；4 个 RHS，3 次 GETRS/RHS，共 12 次 | attempt01 `INCONCLUSIVE`：四个变化量均落在 wide-resolution 判定区间 | attempt03 `LOCAL_CANDIDATE_PASS`，4/4 residual checks 为 `credible_improvement`；新增 GETRS 0 | 仅对原两 cell 的保存残差成立；checker 将受限的 star 扩展作为下一步开放，不是 full owner pass |
| 04 → 05 → 06 | 已保存 star cells 23352/23493、columns 0/1；4 个 RHS，共 12 次 GETRS | attempt04 `INCONCLUSIVE`，四个变化量在 wide-resolution 判定区间 | attempt05 因 checker 错误要求其 source 必须不同于 candidate source 而失败；attempt06 用移除该不等式后的 d311 source 对保存数据复核，`LOCAL_CANDIDATE_PASS`、`saved_coverage_ready=true`，新增 GETRS 0 | saved coverage 准备状态通过；`conditional_star_coverage_unlocked=false`、`full_owner_unlocked=false` 仍保持，不能转授全域资格 |

两组共有 4 cells × 2 columns = 8 个唯一 RHS；候选阶段各 3 次 GETRS，总计 24 次。两次 Decimal 补充只复核已保存残差，没有再次求解。

V14 盘点的 8 个代表键及 tag/perm 为：`26762 (1/0)`、`26897 (1/0)`、`0 (2/0)`、`1 (2/36873)`、`2 (2/576)`、`5 (2/4680)`、`6 (1/32769)`、`7505 (3/0)`。既有 V6 index 对这些键登记了 candidate/reference 的 raw 与 oriented 量、R/T/S、坐标及局部作用；完整保存 candidate LU/pivots 与原始 `b_i` 映射缺失，因此不能把这些键转成资格，也不新增积分来补覆盖。

候选自身报告的 `|d|` 基线与校正后值如下；这些是局部候选指标，不是全域 action 差：

| Cell | Column | 基线 `|d|` | 候选 `|d|` |
|---:|---:|---:|---:|
| cells 360/446 | 0 | 4.714842990596683e-9 | 2.038566996070134e-10 |
| cells 360/446 | 1 | 1.018211453698345e-8 | 4.684649807421053e-10 |
| cells 23352/23493 | 0 | 8.305744689149506e-10 | 8.745466676409231e-11 |
| cells 23352/23493 | 1 | 1.7692662680591898e-9 | 2.8094269677463915e-10 |

每个 star 的 j0/j3 状态标签共用同一 RHS；表列的是该 star 的完整目标行 d，不是每个 cell 各自重复一份的 d。

Decimal 复核的初始 / 最终残差 L2（每行一条实际数值，单位为局部复数向量的 L2）：

| Cell | Column | 初始 | 校正后 |
|---:|---:|---:|---:|
| 360 | 0 | 3.2682919007946529e-9 | 2.2156026632222233e-10 |
| 360 | 1 | 8.2799428365422260e-9 | 4.3566889308483421e-10 |
| 446 | 0 | 4.9375681203954801e-9 | 2.7095813783673753e-10 |
| 446 | 1 | 8.6564331531147785e-9 | 5.4635179748946118e-10 |
| 23352 | 0 | 3.3705075293146419e-9 | 2.3980888202517792e-10 |
| 23352 | 1 | 8.0148067936670855e-9 | 4.4983281860466364e-10 |
| 23493 | 0 | 3.7228375436506450e-9 | 2.3253723785338470e-10 |
| 23493 | 1 | 8.0100941742135384e-9 | 4.9724482179844918e-10 |

attempt05 的精确 worker 错误为 `ValueError: V14 Decimal review contract is not a new-source binding to the same fixed window`。checker 错误地要求 checker source 必须不同于 candidate source；这条不等式并非必要身份门。attempt06 的 consumer source `d311d20cf9d9ea1bafe3aefe9d6446d2570335a8` 移除该不等式，同时保留相同固定 window 和全部身份核验，之后完成 saved-only 复核。attempt05 是接线错误，不是残差或物理验收失败；失败 receipt 与 worker log 保留。

## 时间与资源口径

五个有完整 service parent receipt 的 attempt（01、03、04、05、06）父段累计 **221.4241482896236 s**。attempt02 的 systemd unit `myfenics-case-task41-p0-v14-decimal-recheck-attempt02-20261025T0938Z.service`（invocation `057461078d6f46778ef1d35363f8ea68`）在 scientific worker 前以 exit 1 被拒绝，0 GETRS；没有完整 service receipt，墙钟成本 `UNKNOWN_NOT_MEASURED`，不能把 journal 时间差当作实测父段。watchdog 是父服务段内的子阶段，不再相加。五个有回执 attempt 的观察中，最大 process-tree RSS 为 667,795,456 B，最大 task cgroup memory peak 为 497,860,608 B，task swap peak 为 0 B，均记录 descendants cleared。每个服务沿用独立 task cgroup、1.5 TiB task memory cap、64 GiB host reserve 与 task swap 0；这些小型 saved-only service 数值不能代表全域工作集峰值。

窗口 ledger sequence 139 的历史样本时间为 `2026-10-25T11:33:32Z`，当时累计扣账 `9939.785210496382 s`，数值阶段余额 `10460.214789503618 s`。提交前较新的 closeout 样本为 `2026-10-25T11:47:24.817406945Z`、phase=`closeout`、累计 `10771.817644471404 s`；该 observation SHA-256 为 `485c5bc31fa4e47962cc78f69b2fd3f5911acb18229016c4470efa896e2f27e0`，当时 campaign ledger SHA-256 为 `dc1c219027709540c71986d1c4e1fc862cdc70a2cd60204662d8db8054f3c0b1`。这仍是文档发布前快照，不是最终窗口总耗时；发布后费用 `UNKNOWN_NOT_MEASURED`。不得将 V14 数值服务父段总和当作整个窗口费用。

## 冻结后的代码验证与未完成项

工作站对最终冻结源码对应的相同文件快照执行了 7 项定向测试，覆盖：prebuilt owner 的 live strategy / actual K / LU identity 绑定，P6 最终 z、Di 与 recovery 接线，borrower 清理，以及 saved-candidate 和 star-extension 测试。此验证是接口与回归测试，不是数值候选的新一轮运行；测试日志路径和回执见 [V14 evidence index](outcomes/v14_closeout/evidence_index.json)。

最终冻结代码已经实现并通过定向测试的窄接线包括 owner/target/reference/recovery 身份绑定及最终 z、Di、recovery 路径。仍未完成的是这套接线在全域运行合同中的执行、官方终态 checker 与独立全域验收。另有 8 个代表键缺完整 candidate LU 与原始 RHS 映射；完整场、200q/factor、KSP/FGMRES、A6 与 R/T/A均未运行。V14 局部结果和接线测试不自动授权或满足这些范围。

按保存核心的测量，若对全域都保留 K，载荷估算为旧载荷 `435.653172 GB`（435,653,172,000 B）加新增 K `90.72 GB`（90,720,000,000 B），共 `526.373172 GB`（526,373,172,000 B）。这是派生载荷估算，不是 RSS/cgroup 实测值，也不是运行准入证明。后续若申请全域范围，必须单独评审该内存账和完整全域门。

紧凑时间/资源与 RHS 账见 [V14 closeout ledger](outcomes/v14_closeout/timing_and_adjoint_ledgers.json)；hash-bound 原始证据入口见 [V14 evidence index](outcomes/v14_closeout/evidence_index.json)。
