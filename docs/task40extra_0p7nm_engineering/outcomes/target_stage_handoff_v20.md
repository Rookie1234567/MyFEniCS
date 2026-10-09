# Task40extra 原尺寸阶段交接 V20

## 当前冻结身份

| 项目 | 身份 / 状态 |
|---|---|
| canonical worktree / branch | `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering` / `task40extra_0p7nm_engineering` |
| 当前源码冻结 | `c319719433e99fe652754f2844c5d79669b111cb`；父源码 `4b004d09b17d07a1f19f4c9d8443e76153e69a4b` |
| 固定 campaign window | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json`；SHA-256 `b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0`；不可刷新 |
| source freeze receipt | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/controller_v20_target_runtime_source_freeze.json`；SHA-256 `df5ba8626186bb2ee6ba68ded57b59a8e84d73232e04067bcb3d875102fb2cff` |
| 实际 pre-mesh receipt | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/controller_target_actual_pre_mesh_chain.json`；SHA-256 `8ed9ce90941e697bf773a5cf71c1fee05db0594b67481898e4eb1132f82feebd`；FE/qCSR/factor 均为 0 |
| stage input 清单 | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs/stage_input_manifest.json`；SHA-256 `0b57a37331f356d90cec15c6535faf6fbdf5efe80d9ffc77162c8dacbf3820ac` |
| 可复制命令清单 | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs/stage_commands.md`；SHA-256 `f9d06f0ee71ab3fb7151b118267497468aa2ca0d2fa54ccaaddbf676c2dfbd9b` |
| 模式 manifest | `benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json`；SHA-256 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`；32,060 ordered keys，key SHA-256 `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec` |
| 目标输入 | `input/task40extra_0p7nm_engineering/target_original_ny8_resource_pilot_v20.dat`；SHA-256 `f6726d005713b586f1bccfbf6904dd64f3f1f31dd3b069607b55e9b430d294c7` |
| 资格化 ABI | Task40 `local_w0_wsl` WSL2 runtime；PETSc complex128/int32、MPI1、线程数 1；ABI receipt SHA-256 `ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426` |

运行前应重新核对上述 source/input/window 哈希与 ABI 身份。manifest 中传播模式数量不是倏逝模式截断收敛证明；不可删除 mode 以满足 32,060 计数。

## Stage 输入生成、固定窗口与准入边界

stage `.dat` 位于 Git ignored artifact 目录。现有 stage 包的生成入口是已资格化 Task40 activation shell 中的 `python scripts/task40_v20_service_workflow.py prepare-inputs`；它从 canonical preflight 输入派生 stop-stage 变体，并拒绝覆盖字节不同的已有文件或清单。已使用的 component-resume 输入生成 CLI 为 `python scripts/task40_v20_service_workflow.py prepare-component-resume-input --manifest benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/component_resume/target_original_ny8_from_completed_prefix_manifest_v3.json --sha256 c0a22a6aaefd4062b2d4d3c3553dcfa8029845840f32eb1c1bc76a83836c9255`。以上命令仅说明现有生产入口；本次收口没有执行它们，也没有重建 stage 包。

模式 manifest、固定 window 与 ABI receipt 是独立 authority inputs。缺失或哈希不符时应 fail closed；禁止自动重新生成 AUTO mode manifest、刷新 campaign window，或用其他文件替代 ABI 原始回执。当前 mode manifest SHA-256 为 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`，固定 window SHA-256 为 `b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0`，qualified ABI receipt SHA-256 为 `ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426`。

固定 campaign 的 T0 是 `2026-10-09T01:45:00.727771902Z`，deadline 是 `2026-10-10T01:45:00.727771902Z`，closeout reserve `600 s`；不刷新窗口。既有单任务进程树静态 cap 为 `16 GiB`（`17,179,869,184 B`），实际 launch admission 按 `min(dynamic_memory_envelope, explicit_tree_cap)` 取较小值，并保留 system/evidence reserve；不提高 cap。任务进程树和专用 cgroup swap 必须为零，独立 watchdog 监测进程树 RSS 并在退出/停止后清除全部后代。PSS 若 profile 禁用，记作 null 并单列 `DISABLED_BY_PROFILE`，不能写成零。`task40_target_heavy_authorized=false` 且 `full_target_release_allowed=false` 仍有效，build/symbolic、numeric 与 full target 继续关闭。


## 阶段状态与命令

所有命令来自已保存的 `stage_commands.md`。命令模板只是路由记录，不构成新的 heavy 运行授权。执行任何阶段前，先核验固定 window、source、输入、ABI、实际资源和该阶段预算；当前 `task40_target_heavy_authorized=false`。

| 阶段 | 输入与 SHA-256 | 当前证据 / 放行状态 | 原始命令模板 |
|---|---|---|---|
| `preflight` | canonical target dat；`f6726d…d294c7` | route/identity 可执行；本轮 route 验证不创建 FE | `bash scripts/run_case_in_user_service.sh input/task40extra_0p7nm_engineering/target_original_ny8_resource_pilot_v20.dat --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json` |
| `geometry_inventory` | stage dat SHA-256 `c012a19be60f73f2394df1a9d5bfd233b4efa48e7272064f7c05ff09ef86c940` | **PASS**：30,464 cells，60 类，周期配对通过；无全局 FE/MPC | `bash scripts/run_case_in_user_service.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs/geometry_inventory/target_original_ny8_resource_pilot_v20.dat --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json` |
| `local_port_components` | stage dat SHA-256 `e5e0986920a71d8e9d5224c6c7be8e9060ba5791391db2037a9128741061bf38` | **PARTIAL**：本地/端口数值过各自门限；17/60 个方向匹配，43 个未资格化 | `bash scripts/run_case_in_user_service.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs/local_port_components/target_original_ny8_resource_pilot_v20.dat --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json` |
| `build_and_symbolic` | stage dat SHA-256 `8df83f6d6f1302242b09068ea066cae071f493d23d05c5765a28786332b24f45` | 已注册但当前授权关闭；若调用只应在 preflight 后 fail closed；本轮未执行目标 heavy | `bash scripts/run_case_in_user_service.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs/build_and_symbolic/target_original_ny8_resource_pilot_v20.dat --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json` |
| `one_q_numeric` | stage dat SHA-256 `da8c8c19ba59c2d10ae664fb28148538a1386eab6c07e30b2b6920636b3d186b` | 已注册但当前授权关闭；本轮未运行目标 numeric factor/RHS | `bash scripts/run_case_in_user_service.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/stage_inputs/one_q_numeric/target_original_ny8_resource_pilot_v20.dat --task40-v10-campaign-window benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json` |
| `full` | 无可放行的原尺寸 full-field 输入 | **NO-GO**：`full_target_release_allowed=false`；不能把 E2 full 输入冒充原尺寸命令 | 不提供 full 命令；需先补齐 target operator、资源和精度资格及明确授权 |

runner 要求 all-q symbolic 在任何 numeric factor 前完成。即使未来允许 q0 numeric pilot，也只能报告 q0 本身，不能宣称所有 q 的 fill/内存均已通过。正常 partial footer 必须列明完成阶段、`official_result=false`、未运行项和预算消耗。

主控只读 campaign snapshot `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/controller_closeout_campaign_snapshot.json` 的 SHA-256 为 `0dcd4752f762ac66516b954e64914fc09816a3a9ed92f37a2099507268c79de4`：tail sequence `83031`，tail cumulative `66,919.728418 s`，只读投影 `69,920.856944 s`，扣除 600 s closeout reserve 后暂余 `15,879.143056 s`。该快照未改 window 或 ledger，是 as-of 投影而非最终冻结余额；后续提交与等待仍占用固定窗口，需由主控最终结算。

## 已完成的数值及资源证据

- E2 p6 880-cell 案例已建四个 canonical q CSR 与变换表，在 `one_q_symbolic_admission_v19` 因总投影 13,669,107,480 B 超出动态 cap 13,519,601,664 B（149,505,816 B）而受控停止。没有 numeric factor、KSP、field 或官方 R/T/A。
- 原尺寸几何实测 `272×8×14=30,464` cells。几何库存/读回计时为 `0.48784481384791434 s`，不代表完整 mesh 构建耗时。局部/端口记录 60 类，底/顶侧各分解一次；底部和顶部已知解前向误差分别 `4.38956601568474e-14`、`4.456757248975752e-14`，限值 `1e-11`；原局部方程残差分别 `6.369701138645506e-16`、`5.735468421207556e-16`，限值 `1e-10`。
- 两侧 boundary receipt 各记录 32,060 full-ordered mode rows、2,004 batches、432 trace rows；manifest 则将 32,060 个 key 均分成 bottom/top 各 16,030。这里保留原回执计数，不能把两种语义改写成同一计数。
- 合并的原尺寸 local/port run 的进程树 RSS 峰值为 `665,841,664 B`，专用 cgroup memory peak 为 `700,948,480 B`；进程树/cgroup swap peak 均为 `0 B`，watchdog 清场后无残余后代。PSS=null，状态 `DISABLED_BY_PROFILE`。这是整个 run 的共享峰值，未分别采集 bottom/top 峰值。单个局部类别的最大 unique backing 合计 `34,260,316 B`；独立的最大 owner 标量未汇总，记为 unknown。
- final target FE/MPC/qCSR/factor/KSP/field 均未资格化。2 TB、48 h 和最终 h/p/模式截断精度仍 `NOT_QUALIFIED`。ordinary solver default 未改变。

完整原始身份、分类和轻量证据 hash 见 [V20 run index](records/run_index.json) 和 [V20 response](../response_v20.md)。前次失败与中断 fixture、旧费用和 unknown 均保留；固定 window 不刷新。最终结算与后续阶段决定由主控处理，执行者不提交或推送。

## 跨阶段恢复与成本口径

上表各 stage dat 是可复制的停止点模板，不是要求把每个命令依次独立运行。分开重新启动会再次执行命令所包含的前置几何/组件阶段，重建时间与资源必须计入该次 outer workflow；不能把这些重复构建隐藏在合计中。优先在一条获准的运行内走到批准的 stop stage，或仅恢复带有匹配 source、输入、ABI、manifest 与 owner 关系的已保存数据。`target_resume_readback_v1.json` 只验证其明确列出的 60 类/输入/manifest 关系，不构成 q CSR 或 numeric factor 的恢复凭证。

没有可验证持久化凭证的 q CSR、symbolic/numeric factor、workspace 与 mode/operator 对象，均视为未保存；后续阶段必须按真实流程重建并计费。V20 中断 fixture 的原 stop receipt 虽有 `campaign_window_charged=false`，但固定 campaign window 实际包含该段；精确独立耗时与费用未知，保留原总账且不重复叠加一个估算值。
