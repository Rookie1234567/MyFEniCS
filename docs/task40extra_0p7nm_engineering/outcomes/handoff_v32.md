# V32 终态交接（2026-10-15，新加坡）


当前 run 为 20261014T121113.504617Z，service 为 myfenics-case-task40-v32-all-q-reference-9ba8f0aa2750.service，source 为 9ba8f0aa2750d020533321860d653dbbc44b885f，window SHA-256 为 ec92e117479ef7e41854a4dab647c8c1bc963ef2705fb6ec390926f252294bf6。数值截止 2026-10-15T01:48:33.255938807Z 已触发 PERFORMANCE_CONTROLLED_STOP；TERM 后 30 秒 KILL，worker exit -9，后代清场完成。该状态来自固定时间门，不是数值或内存失败；窗口不延长，本轮不重启。

q4 既有 COMPLETE/native PASS 收据保留：777424×777424、581086528 结构槽、四个完整 CSR action 通过，最大相对误差 2.6835748652861403e-14（限值 1e-11）。这不是当前 run 的全局参考或目标场 pass。global_reference_builder 未完成；没有其他 q 新 COMPLETE/native、完整 reference、原尺寸 FE 场或 official R/T/A。自动受监督 checker 的真实结果为 NO_PARTIAL_FOOTER，checker_passed/full_pass/official_result 均 false；不合成 worker footer。

时间与资源口径：run_case 父段 49072.819633 s，required checker 父段 2.896090 s，加上入口/activation/ABI等后的全部不重叠父段合计 49077.043640 s；watchdog 49072.059610 s 是嵌套子段。进程树 simultaneous RSS 峰 50996031488 B，专用 job cgroup 峰 33537933312 B，task swap 峰 0 B。宿主 global swapin 增量 82 页、swapout 0 页，只是宿主诊断，不能归到任务。campaign accounting 在 2026-10-15T01:58:26Z 的快照显示最后已落账 85235.547721 s、只读投影累计 85793.12263780605 s，剩余 closeout 606.877362 s；以 campaign state 的 current projected 字段为权威，不刷新 T0。

下一断点是 src/solvers/task40_v10_p6_yorbit.py::build_task40_v10_p6_reference_inverse。若获下一轮授权，应只在 _build_same_mesh_levels、build_same_mesh_physical_action(..., verify_dtn_quadrature=True)、q provider/sector builder 这些真实调用边界补阶段证据。现有日志仅能确认 global_reference_builder 外层未结束，不能识别具体热点。

原始证据和 hashes 见 benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation/terminal_9ba8f0aa/；文件集合和结果边界见 docs/task40extra_0p7nm_engineering/response_v32.md 与 outcomes/records/review_v32_terminal_closeout.json。所有旧 attempt、费用、UNKNOWN 和受控停止记录均保留。执行者未改数值源码、未启动运行、未 commit/push；由主控审核并集中发布。


> 以下是已结束的P0/批准前历史命令与边界，不能直接重启已截止窗口；当前状态以上文为准。

# V32 P0 交接：新运行窗尚未批准

实现源码：`a4f7d53af234dbd156388a4be133a0d5aeee1c16`。完整结果HEAD以主控最后推送/回读为准。当前只有本机P0实现和小fixture，没有新重型attempt、T0或deadline。

## 数据与下一科学断点

只读导入根：

```text
/home/fenics/Projects/laptop_share/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_54cf6d367b07355c0ab08c8c10655ecac73cfc6a/factor_bank/selected_q/q4_twist0
```

pending：`task40_v30_q4_twist0_numeric_pending.json`，SHA256 `1938828321a57ee6eaaea0def485f73daddbd13432cc6ef8823d19bcc44640ad`。三数组分别保留：

| 数组 | SHA256 |
|---|---|
| data | e0e209b7804956a8c998eac05422f6f6ff255ed857182e066eedfd509b005ad2 |
| indices | 3af86cbe15de1615304659e112deccb0d00c86c7cfe5d588cde846d84c3a7c97 |
| indptr | 0049c1ab9662e30b7cfe460f622557571172f8b5196174e64d4b4529ba2f334b |

新consumer/native/COMPLETE只写新source根。旧contribution、V31 numeric、V32 native与本次live factor四层来源分开。require-existing缺项拒绝，不重建routes/pattern/fill。q4仍缺独立native；原q0只消费已资格数据，旧因子不再live。

## 实际入口

主控已在本机资格化环境实际执行下列CLI，成功生成PENDING草稿（非批准包，不产生T0或大数组扫描）：

```bash
python scripts/task40_v20_service_workflow.py prepare-v32-p0   --execution-root /home/fenics/Projects/laptop_share   --output-dir benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation/controller_draft_package_1
```

草稿原文：`benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation/controller_draft_package_1.stdout.json`。它生成时源码尚未冻结，仅保留入口事实；不得拿这个旧草稿启动。主控在最终clean HEAD重新生成pending包，记录其原文及hash。

以下为**批准新窗口之后**的既有目标环境入口，主控先部署同分支clean源码并记录真实批准，再运行。批准receipt必须来自本次人类许可，不能用历史V30/V31批准代替：

```bash
cd /home/fenics/Projects/laptop_share
source scripts/task40_fresh_c1/activate_native_complex.sh   benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix   benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json   benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache native_linux
v32_source_sha="$(git rev-parse HEAD)"
v32_pending="benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation/v32_pending_package/source_${v32_source_sha}"
python scripts/task40_v20_service_workflow.py prepare-v32-p0   --output-dir "$v32_pending" --execution-root /home/fenics/Projects/laptop_share
# 主控依据真实批准提供 user_approval_v32.receipt.json；不得自行伪造。
python scripts/task40_v20_service_workflow.py prepare-v32-approved   --pending-dir "$v32_pending"   --approval-receipt "$v32_pending/user_approval_v32.receipt.json"
v32_root="benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_${v32_source_sha}"
bash scripts/run_case_in_user_service.sh   --service-unit "myfenics-case-task40-v32-all-q-reference-${v32_source_sha:0:12}"   "$v32_root/stage_inputs/full/target_original_ny8_resource_pilot_v20.dat"   --task40-v32-execution-contract "$v32_root/execution_contract_v32.approved.json"
```

窗口内修复源码后，使用生成包中的 `prepare_same_window_after_source_fix` 命令和原approved contract；不得再创建T0。实际源码修复后必须冻结clean来源，运行中不热改。

required checker由上述service创建真实supervision request并自动调用 `supervise-required-checker`、独立watchdog和 `check-partial`，实际路径、命令、结果、释放落盘；不把另一次裸check-partial命令冒充监督完成。P0已验证合法partial与缺footer实际子进程路径，数值cutoff后仍在同窗closeout记账；真实工作站运行仍须保存自己的监督证据。

## 批准后的固定边界

总86400 s / numeric85200 s / closeout1200 s；cap1649267441664 B / reserve68719476736 B / task swap0。原ABI、MPI1、数学线程1、MUMPS和全部残差门不变。阶段合格且资源/时间允许时连续推进P1–P7，不逐q停审；真实失败保留并只停止依赖路径。当前不得宣称完整冷流程、全八q或原尺寸精度已经通过。
