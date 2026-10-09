# Response V13：Review V11 的 P0/P1 进行中进度

本文件回应 Task041 Review V11 的当前执行批次。任务目录未提供单独 `README.md`；本轮依照仓库规则读取 `task.md`、Review V11、此前 Response V12、outcomes、仓库文档规则及开发总账。W5 的弱显著衍射通道按用户决定延期处理；保留其原失败与比较工件，不写成通过，也不作为本轮 W0.7 的前置。W2 本批未推进，避免延误 W0.7 主线。

## P0：独立 W0.7 资源合同

P0 给注册的缩减 W0.7 case 独立配置 80 GiB 上限，避免为了 pilot 放宽共享常量而影响 W5、13.5 nm 或 W2。384 GiB node0 floor 仍独立生效；case cap 是运行限制，不是峰值预测。运行前只有当 host/node0、cgroup 与 case 限制均满足时才允许继续。

| 项目 | 结果与边界 |
|---|---|
| 变更 | 只修改 pilot DAT、`src/io/input_validation.py`、`benchmarks/task041_exact_side_workflow.py`、`src/test/test_351_task041_balh_public_workflow.py`；新增 pilot 独立资源合同，未改变共享 W5/13.5/W2 常量、未加 CLI 或 runner 框架 |
| 资源合同 | hard cap `85,899,345,920 B`；warning `77,309,411,328 B`；政策余量 W `8,589,934,592 B`；node0 floor `412,316,860,416 B`。swap 按 V8 仅观察；不设 elapsed 强停 |
| 提交 | `a3332dc12de1ddfec824a8b64ab5dcc23f68261b`，parent `cd43819dc91112b8ca49d1dd2c2066d0074eda44`，原分支已同步 upstream；protected stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976` 未动 |
| P0 测试范围 | 7 个批准 selector 的参数化合同共 12 个唯一 case，分三个 pytest attempt 完成；这些是注册/路由/预算/兼容性合同，不运行 QEP、FE 或 consumer numerical solve |

| pytest attempt | 源码边界、结果、唯一父 wall | 原始证据 |
|---|---|---|
| `task041_v11_p0_resource_contract_serial_20261009T072725Z` | 初始 test351 SHA `ef84f11829906c9e5dd73de70cb9a5f8dcdac7ad22a8702174301ab07cf2c6e8`；实际执行 2 项，1 passed、1 fixture assertion failed；parent wall `4.291536791017279 s`。失败为预算 fixture 读取不存在的 `cap_headroom_bytes` 键；保留原失败 | `results/task041_v11_p0_resource_contract_serial_20261009T072725Z/serial/pytest.stdout.log`，SHA `e7857bb4712a8acc1c7d11697a548320b628fa93e48ffd08b799eab50c47e83c` |
| `task041_v11_p0_stage_budget_retry_20261009T073055Z` | 修正后 test351 SHA `dbd840cc89427483dacca71412d1d80a63b81d2a02ab5204171bbcee9770e116`；受影响预算节点 1 passed；parent wall `3.2227331469766796 s` | `results/task041_v11_p0_stage_budget_retry_20261009T073055Z/serial/pytest.stdout.log`，SHA `cf686c05bfe0139c25a206ee55ec21e7cde334ccb5bbab67376ece2414185475` |
| `task041_v11_p0_serial_remaining_20261009T073150Z` | 同一 test351 SHA；余下 selector 参数化后 10 passed；parent wall `8.533090129029006 s` | `results/task041_v11_p0_serial_remaining_20261009T073150Z/serial/pytest.stdout.log`，SHA `c30d645302cb5ef96b0e8966a6f2c0f00258fdb8da6ff6f17443d22016133651` |

三个父 wall 合计 `16.047360067022964 s`，逐 attempt 唯一计入 V5，不重复计算失败后重试；ledger 为 192 项，SHA `710b71f59d0109ace55963b2ac909eca5e4fccdcb8ef237259f9abff679ef774`。12 个唯一参数 case 跨三次 attempt 通过；不能表述成最终 test351 SHA 在一次完整组运行中通过。延迟 `complete_numeric` 异常的 failure-classification 传播仍为 `not_covered`，本轮没有扩展分类框架。

## P1：W0.7 PORD warm 包已准备，等待唯一启动裁定

当前目标仍是已注册的缩减 W0.7 pilot：W 材料，10×5 nm，p6/h0.70、M400、MPI8，Hybrid 接口 2/22 nm，matched 全长 L20/N29/h20/29，fixed-H6。P4 target 为 `5e-13`，每个同因子最多两次修正；原方程、八次 fixed-H6 setup 作用、GMRES 9+1、五项真实残差和物理门均保留。route-plan、leading-PH 与其他研究诊断关闭。

| 包/身份 | 已核事实 |
|---|---|
| 当前源码 | HEAD `a3332dc12de1ddfec824a8b64ab5dcc23f68261b`；source binding 含 34 runtime + 5 test 共 39 条，已逐条比对 HEAD blob OID、Git blob bytes 与工作树 SHA |
| 准备包 | `results/task041_v11_w0p7_pilot80gib_pord_warm_preparation_20261009T074322Z/`；runroot `results/task041_v11_w0p7_pilot80gib_pord_warm_run_20261009T074322Z/`；unit `task041-v11-w0p7-pilot80gib-pord-warm-cpu10-11-14-15-16-17-18-19-20261009T074322Z.service` |
| sealed config/argv | config SHA `b4bf3edc0c7acfca3aa7b1d00c6b2f8a69c19f2caa220e44c05460ef83c22385`；systemd argv SHA `363dbb74f6e23f46665c900dd0e31b4d4fcab48048fe764e5e28b47e30f42236`；post-ABI admission receipt SHA `76be97971219ab03155fe63deb0ba14fe918c55f66c7c8fd42bc3108fbd2bdc9`；包 manifest 有 26 个内容文件，逐项 checksum 通过 |
| rank map / ABI | 排序 map `[10,11,14,15,16,17,18,19]`。fresh MPI8 ABI rc0，parent wall `1.8218492951709777 s`；8 ranks 精确按此 map、node0 membind、complex128、Int32、六线程变量全为1，并从指定路径加载 SHA `7c0e7458e928de1c66fe66622b19afa200f4fdb2f83cadf368cda3ffd675ef9b` 的原生桥 |
| producer | 复用 source `2708214386d38bd69f73e6b196c8ed843bb53d81` 的 validated producer-root；manifest SHA `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2`，packet identity SHA `73111acd2d48344e4ef36a0d838371f8ccc0efcddc1b7d9d3a46173f4ad2fbc6`。11 个小封套文件哈希/字节数匹配；没有重求 QEP、预读 shards 或在准备阶段运行完整 validator。实际 public consumer 仍按原链执行封套验证及 packet reader/hydration |
| 当前 run 状态 | dispatch 尚未发生；unit 未加载，runroot/service logs/dispatch marker 均不存在。准备包与当前宿主及 ABI 收据已提交主控审阅 |

post-ABI 两点真实 host 样本为 `2026-10-09T07:54:18.523917Z` 和 `07:54:23.603283Z`。同 user-manager 查询显示目标 unit 未加载、active Task041 units 为空。宿主进程视图看到了其他任务：Task039 在 CPU24，Task042 在 CPU26 及 CPU6；它们没有固定绑定到候选 map，本轮未干预。Task042 有宽 affinity，故仍保留 `performance_not_isolated=true`，不宣称核完全隔离。node0 MemFree `719,097,163,776 B`，扣 floor 后 `306,780,303,360 B`，再扣 80 GiB case cap 后余 `220,880,957,440 B`；node0 gate 通过。host MemAvailable `2,009,497,427,968 B`；user.slice 与 user-1000.slice 的 memory.max/high 均为 `max`；磁盘可用 `3,148,500,914,176 B`。swap 仅记录观察，没有把它作为硬门。

PORD source-counted Δ（bottom `3,962,155,812 B`、top `5,500,664,516 B`）仅供 symbolic 筛查，须与对应阶段 fresh B 和 W 一起判定，不能解释为 RSS 上界。numeric 门使用当场 fresh B + 单份当前 INFOG(17)×1,000,000 + W。bottom 因子在 top 取样时仍计入 fresh B，不重复相加；两侧预算尚未在真实矩阵上评估。

在主控对包审核并另行裁定前，不启动 dispatch。此阶段没有 QEP、packet shards、factorization、FE、R/T/A、fixed-H6 feedback 或 outer 结果，不能称 pilot 通过、W0.7 数值资格或完整目标通过。50×25 nm、2 TB 和 48 h 目标仍未资格化；W5 弱显著衍射通道按用户决定延期处理，保留原失败工件。
