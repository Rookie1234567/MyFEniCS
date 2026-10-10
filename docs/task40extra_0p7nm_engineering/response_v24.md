# Task40extra Response V24：q0 端口小块、复用盘点与真实内部边轨道面板

V24 的冻结源码最终为 **809d6a151eed7b4d0eca0430fee2782285e786e7**。本阶段先后提交六次源码变更，完成了 B 的单个 q0 端口 tile、C 的 32 模态复用与全网格几何类别盘点、D 的真实内部 y 边轨道体积行面板。三者是不同源码身份下的分阶段证据，不能把 C/D 的来源改写为 B 的来源。它们都只证明有限接口或局部对象，完整 q 矩阵为 0/8，完整体积作用、全局 reference inverse、PDE 和官方 R/T/A 均未完成。

q 表示 y 周期相位扇区；trace 是单元边、面上的自由度，内部自由度则位于单元内部。D 对内部自由度作局部消元后检验一个有限边轨道的方程行块。读者可据此理解它为何能验证有限局部计算，却还不能代表整台器件的体积算子。

## 冻结身份、窗口和环境

| 身份 | 值 |
|---|---|
| 科学基线（V24 开始时的 HEAD） | **84dce5a39eb34a259166f34e063312a2cd86ef0c** |
| 注册的 Review | **92a59c167b53f828cc0408eca664d0eebc878428** |
| 固定执行源码终点 | **809d6a151eed7b4d0eca0430fee2782285e786e7** |
| 原始 input SHA-256 | **33cb569eb900f60100569a6659138589a9d26784a22e05d50c7fe63190bac4ff** |
| physical model SHA-256 | **ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241** |
| mode manifest SHA-256 | **52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d** |
| 固定 V24 window SHA-256 | **b6a3063404fdbfd88c1099f381c9fe64c09f9bf04e7e7a3871e5454dfa728358** |
| window | T0 2026-10-10 16:33:11Z；数值截止 22:13:11Z；deadline 22:33:11Z；未刷新 |
| ABI | 资格化 WSL runtime；PETSc complex128、int32、MPI1；preflight returncode 0 |
| ABI 证据 | receipt SHA-256 **ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426**；Python/runtime 位于 local_w0_wsl/runtime_prefix |

B 的 tile 同时绑定旧扫描 artifact window **e77793e53542c6094da819456457910893b33c9be5ca3b548482be6bfc3dbdfb** 和新执行 window **b6a306…**；两者用途不同。B 的 run manifest 与 outer record、C/D 的 outer workflow records 都确认 V24 execution window、相同 input/model 和 qualified ABI。原始 D panel JSON 没有顶层 window 字段；该字段从 D 的 outer workflow record 读取，不把缺失的顶层字段误写成 UNKNOWN。五份 compact 的身份对象和 outer-record hashes 见 [operator](outcomes/records/target_operator_probe_v24.json)、[support](outcomes/records/production_support_v24.json)、[performance](outcomes/records/performance_v24.json)、[q0 tile](outcomes/records/q_tile_v24.json) 和 [workflow ledger](outcomes/records/review_v24_incremental_workflow_ledger.json)。

## 六个已冻结源码提交与改动范围

V24 不是一个“源码未改动”的阶段。按科学基线 84dce5a… 至冻结源码 809d6a1…，共有六个 V24 源码提交：

| 提交 | 作用 |
|---|---|
| a516bbe532525e024df1cc3fde00c14efbd930e1 | 让新执行 window 绑定不可变的 V23 扫描证据 |
| eca24be972a0eca1480b6f1f2fb9d745fb823718 | 读取 V23 checkpoint 时保留原生 row dtype |
| 4d4942fb69c6bac4342f1f024d2d9b08e52803f1 | 检查 typed q payload 与独立投影回读 |
| 99e2322bbe60ea916ba3954feca0fd1a431cd3b7 | 选择有界端口模式并批量映射 active rows |
| a233ac49f84269265ddc684d31cb9b790864b018 | 实测有界生产端口复用并独立回读 |
| 809d6a151eed7b4d0eca0430fee2782285e786e7 | 资格化有界真实内部边体积行与 V17 q 行 tile |

累计变更文件如下：

- scripts/task40_v20_service_workflow.py
- scripts/task40_v21_readonly_recheck.py
- src/runners/task40_v10_campaign.py
- src/runners/task40_v20_stage_runner.py
- src/solvers/fullspace_dtn_action.py
- src/solvers/hcurl_assembly_time_condensation.py
- src/solvers/p6_cell_condensed_action.py
- src/solvers/task40_v22_operator_probe.py
- src/solvers/task40_v24_real_edge_panel.py
- src/test/test_task39extra_v19_p6_cell_condensed_action.py
- src/test/test_task40_v10_campaign.py
- src/test/test_task40_v20_routes.py
- src/test/test_task40_v21_readonly_recheck.py
- src/test/test_task40_v22_operator_probe.py
- src/test/test_task40_v24_real_edge_panel.py

普通默认 worker 没有因此接通完整 target action；本次文档 closeout 本身未改数值源码。

## 实际接线范围：哪些阶段跑过，哪些仍未接入

| 计算环节 | V24 实际验证 | 尚未验证或未接入 |
|---|---|---|
| caller / stage selector | Task40 显式 opt-in 的 B/C/D scope、固定 input、window 与源码身份绑定 | 普通 default worker 没有自动进入这条完整实验路径 |
| 端口 provider | B 对 q0 一个实际模式生成 C、−D、H；C 对 32 个 side×q×偏振模式测量冷生成、复用和再生成 | C 的缓存没有接入完整生产 worker 的长寿命 global carrier/action owner |
| 端口消费者 | B 建立有限 trace map 并独立回读 C、−D、H；C 做有限模式 provider replay | 未建立任何完整 q 矩阵，也没有完整 selected-q consumer |
| 体积消费者 | D 对 8 个真实内部 y-edge 轨道的 incident cells 聚合局部 FE 项，做局部消元及 V17 q row tile | 不是 exterior DtN port/boundary-facet panel；不是完整 global volume action |
| RHS / 恢复 | D 对该有限 panel 使用局部非零 RHS、native LU 和局部恢复 witness | 没有 global RHS、全局场恢复或 full explicit residual |
| residual | B/C 投影误差、D 局部方程/trace residual | 没有完整 global equation residual，故不能称 PDE solve pass |
| ordinary production integration | 无 | ordinary fullspace worker/reference consumer 尚未形成 full production path |

## B：q0 单真实端口模式的有限端口 tile

B 使用源码 **eca24be972a0eca1480b6f1f2fb9d745fb823718**，不是最终 C 或 D 的源码身份。它从原始 Ny=8 模式表选取 q0，并配对 q4；实际模式 key 为 [10, "top", -142, 0, "s"]。q0 端口库存有 4,076 个 alias；本次只选择 alias column 0，对应 original mode 10、local mode 2，原 H_p 在该模式上的数值为 1250.0（模式索引仍为 10）。数值检查只覆盖这一列的 C、对应一行 −D 和 H；几何上覆盖 top 侧全部 2,176 个端口 facets，不代表对 4,076 个 alias 都做了数值投影。

| B 指标 | 实测 |
|---|---:|
| real trace map | shape 50,048×773,568，222,946 nnz |
| map SHA-256 | 34b0ccad4b756bef2c63c015de339a2106e5f03677b5ee9589483f730d04d7e1 |
| C 投影相对误差 | 4.8436017086968805e-17 |
| −D 投影相对误差 | 4.690516209749925e-17 |
| H 投影相对误差 | 0 |
| 各项限值 | 1e-11 |

原始 required checker 确有两项失败（退出码 2）：q_only_raw_C_minus_D_H_payload_recomputed 与 q_only_projection_npz_readback_recomputed。保留该失败后，4d4942f 源码上的离线 postfix checker 对已保存数据执行 22 项重算，结果为 PARTIAL_RECEIPT_CHECKED；它没有重跑 B，且 full_pass=false、official_result=false。因此可接受的是有限 tile 的端口投影数值结果，不是整项 checker 的 full pass。输入、模式、原始数组、checker 和哈希在 [q_tile_v24.json](outcomes/records/q_tile_v24.json) 中分开绑定。

B 运行树 RSS 峰值为 2,939,039,744 B，专用 cgroup 峰值为 3,120,656,384 B / 16 GiB，task swap 为 0；PSS 未启用，native owner cleanup 为 UNKNOWN。B 的旧 artifact window 与新 execution window 都保留在 compact 中。

## C：32 模态端口复用与全网格类别盘点

C 使用源码 **a233ac49f84269265ddc684d31cb9b790864b018**。它覆盖 32 个 side×q×s/polarization 模式组，提供冷生成、两次 warm provider apply 和释放后再生成对照。冷生成用时 6.768845421960577 s，warm apply 分别为 0.4829748719930649 s 和 0.48880144278518856 s，释放后再生成用时 6.561613416997716 s、再生后的 apply 为 0.468681805068627 s。逻辑缓存 payload 为 180,373,760 B。128/128 个数组 backing 在再生成前和结束后均释放；这是对象生命周期证据，不是同等 RSS 降幅。

C 的独立 checker 22 项通过。全网格 census 统计 30,464 个单元、29 个原始几何类别和 60 个有方向类别。类别数值缓存加单元元数据的估算上界为 2,199,609,160 B，但不包括全局 trace constraint maps、expansion、lookup table、action owner closure 和 full-q setup。C 没有重跑 B 的 q0 anchor，没有完整体积作用，也没有生成全局 q 矩阵。C 自身是有界复用与类别证据，不证明全生产 worker 的缓存 owner 生命周期。

## D：真实内部 y-edge 轨道体积行面板

D 使用最终源码 **809d6a151eed7b4d0eca0430fee2782285e786e7**。这里的 edge 是器件内部的 y 方向单元轨道；它不是外部 DtN 端口或边界 facet。每个单元的“trace rows”是局部单元接口自由度。D 取 8 个轨道、每轨道 4 个 incident cells，共 32 个单元；每单元有 450 个内部行和 432 个 trace 行。应用 finalized MPC 后触及 312 个 slave rows 和 8,688 个 active trace columns，覆盖 6 个有方向类别。

| D 面板量 | 实测结果 | 说明 |
|---|---:|---|
| V17 q row block | 48×8,688，417,024 nnz，误差 0 | 是有限 48 行对全部触及 active trace 列的行块 |
| 选定 edge 的 q×r 子块 | 48×48，2,304 nnz，误差 1.3236785363666466e-16，限值 1e-11 | 仅此 edge self 子块完成 q 列投影 |
| off-diagonal q 作用 | 最大块范数 7.651965843602257e-14；最大 diagonal 范数 109.95379046015648 | 交叉项被实际评估，没有预设为零 |
| 局部消元 | 6 次新 LU，每类最多 1 次；同 LU 修正次数 0 | 只覆盖这 6 个局部类别，不外推全局因子 |
| 非 edge-self q 列 | 未投影 | 不能从一个 q×r 子块推出完整 q 算子 |
| 完整 q / PDE | 0/8；未运行 | full volume action、PDE、official R/T/A 均未完成 |

D independent checker 的 34 项检查均为真，但 checker 状态是 PARTIAL_RECEIPT_CHECKED，full_pass=false、official_result=false。主控 D audit 只重算原始 NPZ 文件 SHA，并读取、调和这 34 个 checker 结果及序列化的 residual/timing/resource/cleanup 字段；**主控没有对 6 个类别重新独立运行整套数值运算**。audit 中记录的局部最大值是 full-equation residual 1.1482096831726816e-15、恢复前向误差 6.3309899286681456e-12、凝聚 trace residual 4.8468962492704906e-14，分别是 checker/audit 记录的局部见证值，不是全局 PDE residual。D 也是 S-only panel，没有重新计算完整 C−D+H 组合；C 的回执由 hash 绑定。

## B、C、D 计时和资源口径

| 运行 | tile / sample wall 与 CPU | workflow / watchdog / parent | 进程树 RSS；专用 cgroup 峰值/上限 | swap / 生命周期 |
|---|---|---|---|---|
| B q0 | tile 23.758030/25.875420 s | workflow 56.047974 s；watchdog 56.006413 s 嵌套；parent 60.399410/66.230654 s monotonic/conservative | 2,939,039,744 B；3,120,656,384 / 17,179,869,184 B | task swap 0；后代清除；PSS null；native owner cleanup UNKNOWN |
| C reuse/census | sample 19.169655/20.602398 s | workflow 52.632271 s；watchdog 52.537910 s 嵌套；parent 57.149449/63.003227 s | 3,170,832,384 B；3,470,761,984 / 17,179,869,184 B | task swap 0；后代清除；PSS null；128 backing 数组生命周期通过 |
| D internal-edge panel | panel 42.859896/46.734382 s | workflow 83.052900 s；watchdog 79.830053 s 嵌套；parent 89.760632/98.590943 s | 2,950,139,904 B；3,557,376,000 / 17,179,869,184 B | task swap 0；后代清除；PSS null；未发生 OOM/resource gate stop |

每行 watchdog 都嵌在 workflow/parent 范围中，不得再与 parent 相加。RSS 是同时进程树采样峰，cgroup 是专用任务组峰值；两者口径不同。C 的约 2.20 GB 类别缓存估算不是 full-stage cap。

可选完整单 q 收口保持 NOT_ADMITTED，因为 full volume action 尚未运行、complete selected-q streaming reference entry 尚未资格化、full-stage 共驻容量仍 UNKNOWN。资源 Gate 没有触发，因此这不是“测得资源不足”。要恢复数值工作，需要新的 review/window 和重新冻结的 source；接下来应先把 complete selected-q streaming reference entry 与 full-volume action 接好，再验证 global RHS、内部场恢复、full explicit true residual 和共驻容量，之后才能决定是否进入 PDE。

## 证据历史、测试与选择性合入边界

q0 的表示 cast mismatch、B 的 required checker 两项 raw readback 失败和 22 项离线 postfix 收据均保留。另有一次 source 为 a516bbe532525e024df1cc3fde00c14efbd930e1 的早期 V24 service attempt 以 exit 3 结束，按其自身 source/outer record 保留，不归类为 C 失败；C 的正式运行和独立 checker 22 项通过。D checker 输出也保留。V24 fixed window 未刷新，append-only accounting 仍为收费权威；单项行政耗时 UNKNOWN，不从累计差值反推。本次文档 closeout 还发生过一次未加载 qualified activation 的命令失败；它没有启动 pytest 或 PDE，之后的文档检查在正确 activation 下完成。

| 依赖组 | 主要文件 | 行为与资格证据 | 建议合入边界 |
|---|---|---|---|
| 可复用数值核心 helpers | fullspace_dtn_action.py、hcurl_assembly_time_condensation.py、p6_cell_condensed_action.py | V24 改了生产 helper 接口/局部 action seam；B/C/D 是有界证据，没有 full target PDE | 先由 review 分拆并审查调用契约；不得据此改普通默认 |
| Task40 opt-in orchestration | Task40 service workflow、read-only recheck、campaign/stage runner、V22 operator probe | 依赖显式 Task40 stage selector/window/input；不自动进入 ordinary worker | 保持显式 opt-in，连同对应 tests/checker 选择性审查 |
| 紧凑证据与文档 | V24 response、README、summary、四份 compact、run index、development ledgers | 绑定 B/C/D 不同 source/run、ABI、window、raw hashes；无 fresh PDE | 完成 review 后可按证据依赖组选择性合入 |
| 研究用内部 edge panel | 新 task40_v24_real_edge_panel.py 与对应测试 | D 只资格化有限内部 y-edge row panel，不是端口面板或完整体积算子 | research-only；不提升为 production default |
| 不合入 ordinary default 的范围 | 完整 q/reference、global factor/KSP、full target worker path | q 完整矩阵 0/8，full volume action、PDE、official R/T/A 未运行 | 保持 do-not-merge / not-qualified，直到新 review 给出完整证据 |

本次 closeout 只改文档与 compact；六个 V24 源码提交已存在于 frozen HEAD。本 closeout 未新增数值源码修改、commit 或 push；没有合并 master，ordinary numerical default 未改变。
