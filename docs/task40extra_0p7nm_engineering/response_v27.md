# Task40extra Review V27 执行回应：q0 pattern 完整持久化，数值 CSR 在固定截止时受控停止

**结论：q0 的结构位置与列索引已完整保存；数值 data 未完成，当前状态为 CSR_PENDING。** V27 使用保存贡献的 q0-only 路径，没有重新创建有限元网格、MPC 或 native action。watchdog 到达固定 campaign 数值 cutoff 后受控清理。现有 routes、row witness、indptr 和 indices 可恢复；data 没有可靠 contribution cursor，无法报告填值比例、numeric nonzero、exact-zero 计数或完整 data hash。

## 身份、对象和状态

| 项目 | 本轮事实 |
|---|---|
| 分支 / accepted baseline / formal source | task40extra_0p7nm_engineering；V26 accepted science source f9093c87f81d52b75fbc156e562b3745df45ccf4、结果 base 399787abc991e0e30975bc694bd18a9a30c5470e；V27 正式运行冻结 source 61530133bd02b18052e3ba64a5f78b87424c57f6 |
| campaign | window SHA e806c514c8208ae7a887bdb6ddaaec25936c9204a3ccc34a4fb870ad0bb0010d；T0 2026-10-11T13:37:38Z；数值 cutoff 19:17:38Z；总 deadline 2026-10-11T19:37:38Z；不刷新 |
| attempt / service | attempt 20261011T153931.649307Z；myfenics-case-20261011T153916-2321795.service |
| 进程身份 | 数学 worker PID 2321856/start_ticks 127336767；watchdog root 2321839；service parent 2321801。数学 worker 已退出 |
| 实际模型 | 原尺寸 parent target 对应 regular reference，去掉 notch/void；272×2×14=7,616 cells；不是带缺口的完整 Ny=8 target |
| 数值状态 | manifest NUMERIC_FILL_INCOMPLETE；777,644×777,644；完整 pattern 有 577,061,168 slots；numeric nonzero/exact-zero UNKNOWN |

### 源码与输入身份

这些 SHA 指向不同阶段，不能互相替代：V25 donor payload 的 producer source 是 `9d0f4dbfc730dd620b709d048e33e9da6c77520c`；V26 已接受的科学 source 是 `f9093c87f81d52b75fbc156e562b3745df45ccf4`，对应结果 base 为 `399787abc991e0e30975bc694bd18a9a30c5470e`。V27 依次冻结 `c1307939a028bdce491ef242ab1c13d70c05cc37`、`99429d69e29d2180892814d370a41dae2dc31c03`、`66d49273737ae1f8362e06e255f3b76565173cea` 和 `61530133bd02b18052e3ba64a5f78b87424c57f6`；本次正式运行使用最后一个冻结 source。当前输入 SHA 为 `134ea5f08d5d5dbc366870f451ba0de0df5893c5cd73d227dac77f8a11aa2c0b`，当前 window SHA 为 `e806c514c8208ae7a887bdb6ddaaec25936c9204a3ccc34a4fb870ad0bb0010d`，旧 window 未刷新。完整 donor 身份包括六个 producer payload、三个 V26 native NPZ、saved replay、恢复 manifest/checker 和结构见证的路径与哈希，见 [operator compact](outcomes/records/target_operator_probe_v27.json)；其中 V26 native recovery 是 donor 证据，不是 V27 新计算。

saved-only route 已把有限元/native rebuild 次数降为 0。支撑路由计数 3,428,612；pattern 生成耗时 2,106.867 s。全部 777,644 行都由行计数见证覆盖。pattern 的这些事实描述矩阵系数应写入的位置，不代表复数值已全部算出。

| 持久成果 | 文件大小 | 内容身份 |
|---|---:|---|
| row structure witness | 2,121,772 B | SHA-256 56d344256ff60e73ec36ecd58d1aade6e6d7dac5164741de60f0631dc0407bda |
| support routes SQLite | 1,328,558,080 B | SHA-256 a27d291a1bc41751b7a70f15bfef6cf1d1fc85aeb9ce4c01fd7f5153143186f1 |
| indices | 2,308,244,800 B | SHA-256 9279c5dbfb8921c61dc229ea6a99d30bb76f8b31d005076796d4504a1e7d0d6e |
| indptr | 3,110,708 B | SHA-256 6d24828a2cd820601fedf92c5b6575fc2dd95a905c2533677f3a3367648a7819 |
| data | 9,232,978,816 B | full-size NPY preallocation including header; values incomplete; hash absent |

data 文件的长度反映完整 shape 的预分配，不表示相同字节数的数值贡献已经写入，也不能作为完成比例。manifest 的 contribution_cursor 为 null；后续必须使用既有 from-clear API 清零后重填。当前数值 CSR 尚未完成，因此没有 native readback。

## 截止、资源和未完成项

watchdog 将本轮归类为 PERFORMANCE_CONTROLLED_STOP，leader exit 15；systemd wrapper 最终 ExecMainStatus=3。descendants_cleared=true、remaining child list 为空。process-tree RSS peak 为 12,962,181,120 B，dedicated cgroup memory peak 为 13,374,246,912 B；task-local swap peak 为 0 B。WSL global pswpin 增加239页、pswpout增加6,345页，无法归因，不能声称宿主全局 swap 为零。campaign API 在数值 cutoff 的只读投影累计 20,405.100316 s，numerical remaining=0；1,200 s closeout reserve 在 cutoff 后。

q0 纯 CSR payload 11,544,333,940 B 是 derived 数组容量。factor 的显式 source CSR+转换副本下界 23,088,667,880 B，现行保守准入 envelope 80,884,991,404 B，均非 MUMPS factor 实测。factor 因 CSR_PENDING 未尝试；80.885 GB 是保守预测，不是本轮实测 factor 资源停止。数值 matrix-native readback、factor/KSP、target field/PDE、official R/T/A、全 q 和 2 TB/48 h 均未运行/未资格化。outer required checker 的 returncode 与 pass 均为 null，保持原样。

## 可恢复入口

下一次先获得新执行窗口授权，并按 Task40 环境运行 ABI、动态 host/tree/cgroup/disk 与 task-swap 预检。使用完整 pattern 与原 donor arrays 构造 saved q0 adapter 后调用现有 **fill_saved_q0_csr_values**。函数只接受仍可恢复的结构状态，并在每次数值 pass 前清零 data，所以无需猜测 cursor。该入口尚无 standalone command wrapper。

独立 factor continuation CLI/wrapper **未实现**。现有安全 API 组合是先调用 **open_saved_q0_csr_from_manifest**（只接受 COMPLETE_CSR 并核验数组 hash），再调用既有 **run_task40_v26_selected_q0_factor_lifecycle**。已对实际 pending manifest 执行只读 opener 检查，确认它按预期拒绝；本轮没有因子尝试。更完整的调用说明和 artifact path 见 [V27 handoff](outcomes/target_stage_handoff_v27.md)。

## 验证与提交边界

qualified ABI preflight 通过：当前仓库 .venv、PETSc complex128/int32、MPI1。各阶段冻结源码的定向测试结果见 [test summary](outcomes/test_summary.md)；本次 closeout 的 clear-all continuation fixture 为1 passed in 0.39 s，真实 pending manifest opener 只读拒绝也通过。最终冻结 source 的完整测试套件、full repository pytest、MPI2/4、Ruff 和 CI 未运行。V27 的冻结源码链包含上述数值源码改动；本次 terminal closeout 只改文档与证据，没有再改数值源码，也没有改变 ordinary solver default。执行者没有提交或推送；由主控发布该分支。没有合并 master。详细证据见 [summary](outcomes/summary.md)、[operator compact](outcomes/records/target_operator_probe_v27.json)、[time/resource ledger](outcomes/records/time_resource_accounting_v27.json)、[workflow ledger](outcomes/records/review_v27_incremental_workflow_ledger.json) 与 [test summary](outcomes/test_summary.md)。

旧 donor 与当前执行身份分列在 operator compact：producer source 9d0f4dbfc730dd620b709d048e33e9da6c77520c，V26科学源码 f9093c87f81d52b75fbc156e562b3745df45ccf4、结果base 399787abc991e0e30975bc694bd18a9a30c5470e；原六文件、三组native、recovery/checker路径与hash原样保留，本轮source/window不重新署名旧成果。前序bootstrap/端口维度/私有NumPy接口失败及原source见workflow ledger；费用统一累计，分项unknown不捏造。

行政收口负记录：数值cutoff被严格执行；文档审稿与推送超过总deadline。实际超时和累计费用见 [主控审计回执](outcomes/records/main_closeout_audit_v27.json)，没有恢复数值工作或刷新窗口。
