# Task40extra Response V21：端口库存与 E2 只读复核完成，原尺寸完整求解仍未资格化

本轮在 `task40extra_0p7nm_engineering` 分支、HEAD `75273597809d2876f091a222b678f3af6756725c` 上继续 Review V21。工作树仍有未提交改动；未 commit、未 push，也未启动 E2、原尺寸 PDE 或其他 heavy worker。

| 分项 | 本轮结论 | 证据边界 |
|---|---|---|
| `TARGET_PORT_INVENTORY` | 真实 z 端口面每侧 2,176；mode manifest 共 32,060 个有序 key | 全边界每个 cell 关联多少模式、`Σm_c` 和 `Σm_c²` 仍 `UNKNOWN`；没有建 global carrier/MPC |
| `ZERO_BLOCK_STORAGE` | `None` 不再物化为稠密零块；两侧局部 action/RHS/recovery/B/D 与显式零表示逐项相同 | 两侧移除的逻辑 payload 共 27,680 B；没有可归因的 RSS/cgroup 节省证据 |
| `BOUNDED_PORT_ACTION` | `P6CellCondensedAction` 的生成式 B/D 回调与单面局部见证通过 | fullspace carrier builder 和 Task40 worker 仍未接入该回调；不能称完整生产路径已 bounded |
| E2 | 新的 raw-event 只读重算通过；仍是首个 q0 symbolic admission 前的资源受控停止 | 历史 `NO_PARTIAL_FOOTER` 和外层 `WORKER_FAILED` 保留；不补写旧 run 的 footer |
| full target / 2 TB / 48 h | `NOT_QUALIFIED` | 本轮没有全局目标映射、全场、官方 R/T/A 或精度资格 |

## 目标端口库存与单面见证

几何回执来自原尺寸 Ny=8 目标网格：30,464 cells，axes 为 `272×8×14`；目标和 filled-reference 各有 60 个 cell class，60 个 class ID 共同出现。z 端口 tag 15/16 的实际面数分别为 2,176，坐标配对通过。几何回执中 `global_C_D_created`、`global_mpc_created`、`global_p6_space_created`、`q_csr_created` 和 `factor_created` 均为 false。原几何 JSON SHA-256 为 `491dac32b7e3ba927ce44444f834ff1e27406c3dfe95a9438fac8cae45adce34`；对应 mesh HDF5 为 2,839,728 bytes，SHA-256 `0bcc83dea1fb912a88612732f088467b7cb2fd2e152e19370d98342709be1dba`。本轮只记录 HDF5 文件身份，没有读取其中的 cell/facet membership 数据。

mode manifest SHA-256 为 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`：bottom/top 各 16,030 个 mode，p/s 各 16,030 个。它证明了有序模式表和侧别数量，不证明每个 mode 在每个边界 cell 上都非零。现有 carrier builder 按精确非零的 `Bi/Di` interior support 关联模式，不用浮点阈值；但本轮没有建立目标全局 carrier，也没有把每个真实 port facet 与 cell class 对齐。因此实际 support 直方图、全局 `Σm_c`、`Σm_c²` 及独立 backing/alias 总量全部保持 `UNKNOWN`。

新生成动作回执每侧只执行一个已保存的实际 mode：top `['top', -142, -5, 's']`，index 0；bottom `['bottom', -142, -5, 's']`，index 16,030。每个局部 witness 有 882 行（450 interior、432 trace），只使用 identity local mapping；没有完整 side scan 或 global target MPC。两侧合计是 2/32,060 个 full-order mode witness，不能折算为 60 类覆盖。本轮 witness 未绑定目标 cell/facet/class ID，因此 V20 的 17/60 仍是唯一合格方向类别覆盖；其余 43 类仍未资格化。生成式 B/D 与回执中的 native-mode 向量差异在 roundoff 量级；与 saved V20 candidate B/D 的对照是同一保存 witness 的身份比较。当前回执**没有**把新生成 B/D 直接与独立 q30 full-row B/D checker 对照；这项仍未完成。保存的 geometry examples 给出 bottom `(cell 0, facet 0)` 和 top `(cell 503, facet 2344)`，但未证明它们就是新 generated witness 所用的实例；该 witness 的 cell ID、facet ID 和 class ID 均记 `UNKNOWN`。

独立 dense local Schur oracle 的 reduced action、RHS 和 recovery 对照分别保留在 inventory record。known-state forward 门限为 `1e-11`：bottom `9.173378724262687e-12` 通过；top `1.488391772882517e-11` 超限，状态 `CONTROLLED_NEGATIVE_ABOVE_LIMIT`。该 top 负结果保留，不调整阈值，也不据此声称全局 solver 失败或通过。

完整计数、原始输入身份、分类边界和逐类数量见 [target port inventory V21](outcomes/records/target_port_inventory_v21.json)。条件情景假定每个端口邻接 cell 都关联本侧全部 16,030 个 modes：`Σm_c=69,762,560`、`Σm_c²=1,118,293,836,800`。按 complex128 推导，`Bi+Di` 为 1,004,580,864,000 B，缺省零 `Bt+Dt` 为 964,397,629,440 B，`XiB+Bhat+Dhat` 为 1,466,688,061,440 B，缺省 `Hlocal` 为 17,892,701,388,800 B，合计 21,328,367,943,680 B。它是明确的条件库存情景，**不是实测 allocation、实际 support 或峰值内存**。

## None 零块与内存测量

目标 top/bottom 单模式局部数据上，cached 显式零和 absent `None` 表示的 action、RHS、recovery、full B、full D 数值差均为零；与 dense local Schur 对照的结果另行记录。每侧旧 raw port payload 28,240 B，新表示 14,400 B，省去的逻辑零块 13,840 B；两侧合计 27,680 B。该节省只表示数组逻辑 payload。

零块对照在同一进程中顺序进行，VmHWM 包含此前运行时和分配的累计历史：bottom 对照前 192,585,728 B，过程最高 193,347,584 B；top 对照前 196,640,768 B，过程最高 196,661,248 B。共享 cgroup 历史峰值 14,030,671,872 B、swap current 145,637,376 B，均不能归因给本任务。另一份两侧 generated witness 的进程级 VmHWM 从 351,195,136 B 到 500,154,368 B，也覆盖两次顺序 probe 与此前 runtime allocation。结论是 `NO_DETECTABLE_NOT_ATTRIBUTABLE`，没有 RSS savings claim。

## E2 只读重算与阶段回执

新记录从保存的 97,311 条事件、candidate summary 和 run manifest 重算四个 q CSR 的计数及 symbolic admission 算术。事件日志 SHA-256 为 `a286afa3344ea6473ef5a71837e5562e97527d95b143f3ea69452cf16f2bf0ef`。四个 q CSR 均已创建：总计 98,440,612 stored slots、98,334,635 numeric nonzeros、105,977 retained exact-zero slots、1,969,523,536 B unique backing；事件记录没有每个 CSR 内容 hash，因此 per-q CSR content hashes 为 `UNKNOWN`。

| q0 symbolic admission 输入 | 字节数 |
|---|---:|
| 当时 process-tree RSS `R_live` | 10,079,617,024 |
| 请求 payload `Δ` | 486,803,844 |
| 同时请求 workspace `W` | 486,803,844 |
| future co-resident reserve | 2,481,665,040 |
| 固定 headroom | 134,217,728 |
| 重算投影 `R_live + Δ + W + reserve + headroom` | 13,669,107,480 |
| dynamic launch cap | 13,519,601,664 |
| 超额 | 149,505,816 |

两项 486,803,844 B 是独立同时存活的 payload 与 conversion workspace，不能合并或抵扣。两个 admission inequality 均未通过；停止时 q0 symbolic 尚未覆盖，numeric factor、KSP、field 和 official R/T/A 都 `NOT_RUN`。候选 worker 保留 `CONTROLLED_STOP / RESOURCE_CONTROLLED_STOP`；外层 manifest/summary 仍为 exit 4、`WORKER_FAILED`。旧 checker 的 `NO_PARTIAL_FOOTER` 保留为 checker failure；新 [E2 partial recheck V21](outcomes/records/e2_partial_recheck_v21.json) 是分离的解释性回执，未改写历史 run。E2 的 native owner/descendant cleanup 没有可核验 footer，明确为 `UNKNOWN`。

阶段 runner 现在在 build/symbolic 与 one-q numeric worker 的 success、resource stop、exception 路径都写 V2 partial receipt；heavy 授权拒绝仍只记实际安全前缀。checker 重算 authorization、requested/attempted/completed 顺序、worker outcome、q coverage 与 candidate artifact hash。heavy stage 的 `STAGE_COMPLETED` 或 `RESOURCE_CONTROLLED_STOP` 只有在 native owner、process descendants 和临时对象释放均有证据时才可通过 checker；缺字段是 `UNKNOWN`，不能填成 PASS。四种状态的 fixtures 和 E2 算术测试见 [targeted test receipt](outcomes/records/targeted_tests_v21.json)。

## 实现范围与测试

`P6CellCondensedAction` 保留缺省零块为 `None`，并为本地操作提供生成式 B/D 回调；one-mode side witness 验证了实际 saved target local data。生产 `build_p6_cell_condensed_action_from_carrier` 仍未接受 `generated_port_actions`，Task40 worker 仍经 fullspace carrier 和 cached builder，因此本轮只能报 `PARTIAL_BOUNDED_LOCAL_ACTION`，不能称端到端 production adapter 已接好。global target operator、q coverage、native class coverage 和 final solver qualifications 继续不变。

V21 receipt/checker 的较早 combined focused suite 为 **15 passed in 0.16 s**；文档与索引收口后，三组最终定向复测分别为 V21 recheck **12 passed in 0.12 s**、heavy-authorization route **3 passed in 0.12 s**、p6 cell-action 回归 **23 passed in 0.76 s**。主控随后在相同最终 solver source 上联合复跑 p6 action 与 streamed-port 两个测试文件，**28 passed in 129.61 s**。相关 documentation-contract suite 为 **29 passed、134 subtests passed in 0.23 s**。此前局部 p6/streamed regression 28 passed in 119.45 s、兼容性项 3 passed/2 deselected in 0.26 s 的独立收据仍保留。`git diff --check` 通过。没有运行 full repository pytest、MPI4、Ruff、CI 或新 PDE；不声称这些项目通过。完整测试边界见 [test summary](outcomes/test_summary.md)。

## 固定窗口、只读投影与进程状态

本轮沿用同一个 V19 固定窗口，没有刷新 T0/deadline。主控使用同一 qualified runtime 和既有 read_campaign_state 接口做了只读采样；没有追加 CampaignAccount 行，也没有改窗口或账本。

| 读数 | 值与来源 |
|---|---|
| 固定窗口 | benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json；SHA-256 b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0 |
| T0 / deadline | 2026-10-09T01:45:00.727771902Z / 2026-10-10T01:45:00.727771902Z；总预算 86,400 s，数值 cutoff 85,800 s，保留收口 600 s |
| 持久账本尾记录 | campaign_accounting_v10.jsonl，83,032 行，seq 83031，SHA-256 7ea9e880520accf2fd87d8ee63b894c7e3e1ec366308dd0c8bb4492abd705a11；最后已写 cumulative charge 为 66,919.72841801553 s |
| 主控只读 sample | 2026-10-10T00:38:20.741056830Z；API 的 conservative-realtime interval 为 15,480.292692466 s，UTC-minus-monotonic discrepancy 为 1,546.894188271197 s |
| sample 投影 | cumulative 82,400.02111048152 s；扣除收口预留后的 numerical remaining 为 3,399.9788895184756 s；距离 deadline 的 wall time 约 3,999.986715072 s |

V20 snapshot 0dcd4752f762ac66516b954e64914fc09816a3a9ed92f37a2099507268c79de4 是更早的 as-of 读数：sample 为 2026-10-09T21:10:21.576890277Z，投影 cumulative 69,920.85694392852 s。它不是 V21 当前余额。V21 数值仅是主控 API 在给定 sample 的只读投影；账本当前最后实际写入值仍是 seq 83031 的 66,919.72841801553 s。投影没有成为新扣账，尚未结算区间及旧 unknown 不改写为零。

qualified shell 的进程名扫描没有发现 Python、pytest、DOLFINx 或 MPI worker；这是进程名过滤结果，不构成对任意 detached descendant 的完整清场证明。历史 E2 的 owner/descendant cleanup 仍为 UNKNOWN。本轮没有启动 E2、PDE 或其他 heavy worker。

执行者未提交/推送，也未合并 master；由主控完成本轮集中提交与推送，最终 SHA 在主控回执中报告。
