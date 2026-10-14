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
