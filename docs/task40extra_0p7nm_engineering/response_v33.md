# V33 已授权延时续作：源码冻结前记录

用户已明确“继续 V33 延时续作；忽略旧 V32 选项回执”。本次增加 86400 s，保留原 T0 `2026-10-15T04:25:22.963327363Z`；延时数值截止为 `2026-10-17T04:05:22.963327363Z`，总截止 `2026-10-17T04:25:22.963327363Z`。原窗口与旧账本不改写，新账本承接原末尾累计 `85235.4722084753 s`，停机、修复和等待继续计费。cap、64 GiB 系统余量、任务零 swap、ABI、线程和数学门不变。此处记录授权与实现，尚不表示新服务已启动。

新增保存流将每个模式的 B/D/H 原样写入并持久提交，使同一源码、输入、窗口和 owner 身份下的已完成前缀可重开。旧运行的 7680/8036 没有保存数组，仍不可恢复；新实现不能追认旧进度。既有 q0/q4 资格继续导入，不重跑旧矩阵或 native。服务、launcher、watchdog 与 checker 改为读取同一延时合同与账本，原尺寸官方 checker 使用 profile 冻结模式数。

本次最终定向回归为 **9 passed, 50 deselected（1.48 s）**，覆盖保存流完整复数读回/续写/损坏拒绝、实际 owner 传递、原/延时窗口、账本继承、CLI 与 service/checker 路由。指定 Task40 runtime 的 complex128/int32 ABI preflight、改动 Python 的 compileall 和 `git diff --check` 通过。主控另做空 B/空 D 保存流精确回读；均为工程资格，不是新 q 数值资格。

下文保留原窗口的真实终态与历史 P0；正式接续的 source、合同、window、service/run_id 和结果在实际发生后追加。

# Review V33 运行终态：固定时间门受控停止

本次 V33 正式 worker 使用冻结源码 `86574e478148db8a1dd39909ccc6455fc2ea2646` 和原窗口 SHA-256 `65276658776a76c0616fd3e6f1b16d7f8fd763410f35e934d22794daa3c7dedf`。这是一个 0.7 nm、Ny=8 原尺寸参考流程尝试；它没有产出新的 q 资格、完整参考逆、FE 场、完整残差或 official R/T/A。

| 项目 | 实测与状态 | 解释 |
|---|---|---|
| 运行分类 | `PERFORMANCE_CONTROLLED_STOP`；worker exit `-9` | 原数值截止触发 watchdog：04:05:23.241 UTC 对整个子进程树发送 SIGTERM，30 秒宽限后于 04:05:53.282 UTC 发送 SIGKILL；后代已清空。此为固定时间门停止，不代表数值方法失败或超内存。 |
| 流程时间 | `full_workflow_monotonic_seconds=84418.945441`；watchdog `elapsed_seconds=84418.655942` | 两者是不同测量范围，不相加。campaign 账本在 watchdog 开始时已累计 813.619551 s；watchdog 结束累计 85232.387040 s，略过 85200 s 数值截止；launcher 随后记录 85232.388583 s。 |
| 窗口 | T0 `2026-10-15T04:25:22.963327363Z`；数值截止 `2026-10-16T04:05:22.963327363Z`；deadline `2026-10-16T04:25:22.963327363Z` | 原窗口 86400 s，其中 85200 s 数值期、1200 s 收口期；本次没有改写原窗口身份。 |
| 最后进度 | `dtn_carrier_mode`，7680/8036 | 这是 relay 的进度下界，不是已保存 checkpoint；不能从该计数续算。q4 为已有资格导入；没有新的 q 结果持久化。 |
| 资源 | 进程树同时 RSS 峰 `26848030720 B`；专用 job cgroup 峰 `28745129984 B`（上限 `1649267441664 B`）；任务 swap 峰 `0 B` | PSS 未采样。fenics-ws 原生 Linux 宿主 swapin/swapout 分别增加 49/72 页；旧 raw 的 `wsl_global_*` 是历史字段名，属于宿主全局诊断，不能归到此任务。 |
| Required checker | `NO_PARTIAL_FOOTER`；`checker_passed=false`、`full_pass=false`、`official_result=false` | 原始输出无 official packet 或 V20 partial footer；保留真实失败状态，不合成结果。 |

运行原始摘要、watchdog、checker 和最后 relay 的逐文件哈希见 [V33 terminal closeout record](outcomes/records/v33_terminal_closeout.json)。本轮没有 FE/RTA 结果。窗口延期授权没有作用于已经结束的进程；任何后续续作都必须使用独立、可审查的保存数据和新合同，不能把旧的 7680/8036 进度当作可恢复结果。后续方向按主控与用户最新确认执行。

---

## Review V33 P0 快照：执行链已准备（运行前历史）

> 历史快照：以下内容记录在本次 V33 窗口创建前；其中“V33 尚未获批、未创建 T0”只描述当时状态，实际运行终态见本文件上方。

本文件只记录本轮 P0 接线，不是数值阶段收口。既有 q0/q4 完整 CSR/native 为 2/8；本次未新增 q 矩阵、native qualification 或 factor。V32 窗口已结束；V33 尚未获批，未创建 T0。

V33 P0 现在可显式读取本机固定目录 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation/q4_complete_767323bb` 中两份 q4 JSON 元数据，并核对原有 SHA-256。该路径只供 pending P0 使用；模板登记的 manifest、native 和 CSR artifact 路径仍指向 `/home/fenics/Projects/laptop_share`。P0 不扫描历史大数组；获批后的 native 准备和 service 继续由原目标路径及严格导入流程处理。

使用 qualified local WSL activation 的 P0 命令为：

```bash
cd /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering &&
source scripts/task40_fresh_c1/activate_local_wsl_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit &&
python scripts/task40_v20_service_workflow.py prepare-v33-p0 \
  --execution-root /home/fenics/Projects/laptop_share \
  --q4-complete-metadata-directory /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation/q4_complete_767323bb
```

本轮实际 CLI 烟测使用临时输出目录，返回 `PENDING_SOURCE_FREEZE_AND_USER_APPROVAL_NO_WINDOW_CREATED`，`window_created=false` 且 T0/window path 均为空；临时包已清理。本机 pending 文件属于本机准备目录，不能直接当作工作站 package。获准、主控冻结并部署同一 source 后，应在工作站用原 native activation、不传本机 metadata 覆盖，重新登记 target package：

```bash
cd /home/fenics/Projects/laptop_share &&
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache native_linux &&
python scripts/task40_v20_service_workflow.py prepare-v33-p0 \
  --execution-root /home/fenics/Projects/laptop_share
```

之后只使用这个 target package 生成的 `prepare_approved_package_after_explicit_user_approval` 和 `single_supervised_service_after_approved_package` 命令：前者仍使用目标机 `activate_native_complex.sh`，后者走 `scripts/run_case_in_user_service.sh --task40-v33-execution-contract`。主控冻结后再生成带最终 source SHA 的 target package 与命令；本机 package 不作为其输入。

最后一项定向回归 `test_v33_p0_reads_fixed_q4_metadata_copy_without_changing_target_paths`：1 passed；同时完成三份改动 Python 文件的 `compileall`、qualified ABI preflight 和 `git diff --check`。Ruff 未安装，未运行。没有启动 service、FE、factor 或 PDE；执行者未 commit/push，源码由主控审核冻结。

## 本轮完整 P0 修改与验证范围

原流程先准备全局参考算子，其他六份矩阵要等这一步结束才能开始。本次改为先用各自真实 sector 数据生成并保存 `(q1,q5) → (q2,q6) → (q3,q7)`，再按需建立 twist0 恢复 owner 和全局算子；这改变等待顺序，不减少必须完成的全局数值检查。q0/q4 仍严格读取已有资格，不重新生产或验证旧 native。

- 冻结模式和 H 的轻量描述供局部构建使用；全局 carrier 实际建立后再核对其模式/H 身份。各 sector 共用同一 transform bank，不跨 twist 复用不同物理矩阵。
- 后续实现补入的 carrier checkpoint 按 global 与 twist 0–3 分开存放，并把源码、科学输入、staged input、campaign window、execution contract 和作用域写入身份。只有身份完全相同的重启可恢复已提交前缀；旧 worker 的 `7680/8036` relay 没有对应的 durable checkpoint，本改动不会追认或恢复它。更换源码、window、contract 或 owner 都会拒绝复用；数据和 manifest 保留，跨身份接续需另行审查的显式 donor 流程。
- carrier 进度现在区分已生成与已持久提交；每个进度事件只在 frame 写入、`fsync` 且提交清单原子更新后报告，计数以 durable prefix 为准。此接线尚未用于 FE/factor/PDE 正式运行。
- 修复循环中 `trace`、真实库存与已移出作用域的 `compiled`；合并新 q 的 selector/qualification 收据，矩阵资格及时持久保存。全局对象在创建后立即登记拥有者，异常清理仍有效。
- 在真实局部/全局构建、端口生成、pattern、fill、native 和保存处增加阶段事件；端口进度按每 64 个模式节流，不改变积分、筛选、PC 或数值门。
- 沿现有合同/service 显式登记 V33；旧 V32 审批不能创建 V33 T0。worker、campaign loader、required checker 识别同一 review/window，旧默认合同保留。

相关最小验证分三组：合同/入口/真实 sector 调用链 9 passed；实际 worker prefix 两分支 2 passed；最后本机凭据/CLI 接线 1 passed，共 12 个相关测试，不把重复复验累计为更多测试。昂贵 FE/factor 在调用链 fixture 中替身化，因此这些结果仅证明 P0 接线，不是新 q 数值资格。13 个已改 Python 文件完成语法编译；最后窄修的三个文件另做编译。未运行全仓测试或新 PDE。

权威 review 为 `68cadd5731f4fb55bd661d3841754eb0ff79865a`，报告 SHA-256 `34bb6cf9fde457cf554f255c199c627de6a72183a165f917b49af0e4758aac48`；旧结果 base 为 `a8fe7b597333619c19ad3ae301c9bf96d0c381e8`。冻结后本机命令输出的 registration/contract/command 文件保存精确 source SHA 与各文件 hash。

按 Review V33 第 5 节，申请一次新窗口：总 86400 s，数值 85200 s，收口 1200 s；批准后在第一项必要部署/激活/ABI/读取前冻结 T0。继续原 `fenics-ws:/home/fenics/Projects/laptop_share`，cap 1649267441664 B、host reserve 68719476736 B、任务零 swap、原 complex128/int32/MUMPS、MPI1/数学线程1。旧 T0/费用不变；本次准备不表示已取得新窗口许可。
