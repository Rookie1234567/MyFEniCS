# Task41 P0 Review V2 执行响应

**结论：Review V2 已执行到正式 P0 RHS recovery 门；该数值门失败，根因仍未闭合。** V2 修复了分域资源判断、严格接入既有 carrier 并复用现有 P6/native 路径；随后三个冻结 source 经过三次正式 consumer 尝试。前两次分别暴露 MPC row 分类和 B witness 检查问题，第三次在已知输入 recovery 上以 2.0454083899234283e-11 超过 1e-11 门限而失败。原始第三次 run receipt 保留 WORKER_FAILED/exit 4，V2 总结状态为 NUMERICAL_GATE_FAILED_ROOT_CAUSE_UNRESOLVED。

Review V2 正式运行 source 按次序为 ab9e14dd00b2f1a94acd7ced5949e940caa724e6、6c31c5be468ebe6b50102a9beaaa701f48107b4d、53243cd6766b564fed17668753e9fdbb7cab1129。第三次正式运行 source 与当时执行分支 HEAD 均为 53243cd6766b564fed17668753e9fdbb7cab1129。另有一份本机相关测试记录绑定 source-tree HEAD 5e82225427d91d2ec4650169e558b6da29e75a8e 和 tracked-diff SHA 9c8707fc9541087d1d7523edfa1eb10f18842845ed8b4ead70a97369561b98e7；这组测试身份与第三次工作站 service source 分开记录。第三次正式运行时分支 HEAD 与科学 source 同为 53243cd6766b564fed17668753e9fdbb7cab1129；本机最终测试记录另绑定 HEAD 5e82225427d91d2ec4650169e558b6da29e75a8e 与 tracked-diff SHA。文档结果 HEAD 由主控在统一分支收口时单独记录。

## 实现、checkpoint 与 action 路径

watchdog 现在按资源所属域检查 reserve：host available 对 host reserve，task/ancestor cgroup remaining 对各自 reserve。修复保留原 1.5 TiB task cap、64 GiB host reserve、task reserve 0、time cutoff、swap 和采样门。原错误样本中 host available 854,915,547,136 B、host reserve 68,719,476,736 B；task cgroup available 68,698,267,648 B、其 reserve 为 0 B。旧 cross-domain 比较多算出 21,209,088 B 短缺，按分域谓词不应触发停止。

consumer 严格使用 require-existing donor，缺失或身份不匹配时失败关闭。对旧 producer source c52d0d3c0ec6b46c52c3bcf464ee53164308f1c5 的完整 carrier 核验得到 64,120 modes、363,791,051,840 B；committed-prefix SHA-256 为 2595b9518e2422bfadbc2f1a6640e619d60501525b07bda48a068a8ec478a10e。offset index 为 64,121 项、512,968 B，SHA-256 为 2a59fd6a2504ac0b0b8c675325dcaf517ec7bc5dc87b8cb496b96b413b592453。新生成模式数为 0。fresh Task41 B0 support certificate 为 boundary B/D 各 9,094,725,000 rows、cell-interior nonzero values 0；它没有借用 Task40 内部零证据。

计算继续走共享 P6/native 接口：volume_action.apply 形成并复制 native RHS，action.reduce_rhs 执行约束映射，action.recover_storage 对已知输入做恢复检查。第三次运行在真实候选路径上到达 recovery，但首列失败，故不能称完整 target action 已闭合或通过。PSS、每个数组及其 backing 的峰值驻留量，以及 full RHS action/recovery 独立子阶段时长，都没有记录，保持 UNKNOWN。

## 三次正式尝试

| attempt / frozen source | workflow 父时间与结果 | 已定位的问题或后续边界 | 资源读数 |
|---|---|---|---|
| 20261018T090832.301793Z / ab9e14dd00b2f1a94acd7ced5949e940caa724e6 | 4,266.0541681298055 s；WORKER_FAILED：original trace row is not an independent active row | donor validation PASS 后，row map 把非独立 active trace row 交给 mapper。后续修复区分 cell-interior、active-original、slave rows：只映射 active rows，保留 interior 值，不二次 pullback slave。 | process-tree RSS 9,186,394,112 B；job cgroup peak 79,297,404,928 B；task swap 0 B；time gate passed，失败时 fixed-window balance 68,645.48685476984 s。RSS/cgroup 分列。 |
| 20261018T104243.408669Z / 6c31c5be468ebe6b50102a9beaaa701f48107b4d | 4,223.6894003856 s；WORKER_FAILED：mode 16030 saved nonzero P6 B/D action gate failed | 离线 raw 诊断发现 B gate 误把近零 mode wave number 当成 B witness alpha。修复改用实际 witness [0.7, -0.4]；对应 raw B relative error 3.7430835942673515e-14。raw D 对照为 5.316414382339111e-14 / 1.594284501170206e-14；失败 attempt 未保存实际 P6 D 值，离线 raw 结果不构成 fresh P6 资格。 | process-tree RSS 9,185,849,344 B；job cgroup peak 9,326,239,744 B；task swap 0。systemd exit 后另有不同读数，差异 UNKNOWN，不相减。 |
| 20261018T121210.548690Z / 53243cd6766b564fed17668753e9fdbb7cab1129 | 9,364.070864045061 s；原始 WORKER_FAILED/exit 4；V2 NUMERICAL_GATE_FAILED | 64,120/64,120 saved-surface applications 完成；首个 full RHS recovery probe mode 16030 相对误差 2.0454083899234283e-11 > 1e-11。第二列 mode 48090 与 condensed RHS 比较未到达。输入、native RHS、recovered 向量没落盘，绝对误差和根因 UNKNOWN。 | process-tree RSS 11,411,648,512 B；task cgroup peak 11,872,563,200 B；task swap 0；后代已清场；资源/时间门未触发。最后固定窗口样本约余 52,529 s。 |

第三次 parent workflow 的 9,364.070864 s 包含 saved-surface apply 子阶段 4,257.863888 s；校验后读入 363,795,691,904 B，frame-parse 子计时 93.118294 s 也属于该阶段，不另行相加。最后样本还记录宿主全局 swapin/out 为 13/0 页，但该计数不能归因到 task（归因 UNKNOWN）。此前 carrier-build resource stop 的 task-cgroup peak 1,580,571,795,456 B 与第三次 consumer/recovery 的 11,872,563,200 B 属于不同 phase 和工作量；不把它们当成同口径的内存收益。

两个已选模式的 saved B/D consumer receipts 均 PASS，只证明这些 consumer checks。q CSR/factor、KSP/FGMRES、完整场、独立 A6、official R/T/A 和 A_volume 均 NOT_RUN，official_result=false。13.5 nm A1/A2 的既有结果保持有效。

## 验证记录与下一步

Review V2 阶段实际有针对性测试：以 ab9e 为基线、随后提交为 6c31 的 row-map/recovery 修复 fixtures 为 2 passed in 0.55 s；以 6c31 为基线、随后提交为 53243 的 alpha/action 修复 fixtures 为 2 passed, 13 deselected in 0.34 s，另一次 whole-file 批次为 12 passed、3 failed（未改动的 regular-inverse fixtures，未重跑 baseline）。本机最终相关套件记录为 16 passed in 0.88 s，另有 py_compile 和 git diff --check 通过；其 source-tree HEAD 为 5e82225427d91d2ec4650169e558b6da29e75a8e，tracked-diff SHA 为 9c8707fc9541087d1d7523edfa1eb10f18842845ed8b4ead70a97369561b98e7，与第三次正式 service source 53243cd6766b564fed17668753e9fdbb7cab1129 分列，不跨 source 重署名。1 项 B0 service-contract fixture 因 ABI receipt 与 runtime profile/host/boot 不匹配，在 imports/preflight/pytest 前阻塞，不计为通过。Ruff 不可用；未运行全仓测试。

下一步由 ChatGPT 基于数值门失败与关键向量缺失审阅后续处理，重点是在任何续作前保存首个失败列的 known input、native RHS、recovered 向量、mapping identity 与 local residual，以区分 native/local 与 LU 相关误差来源。本次真实数值门失败后没有自动重复 heavy，也没有调宽门限。证据与完整三次 attempt 索引见 [adoption/action/performance compact](outcomes/p0_v2_adoption_action_performance_20261018.json)、[failure compact](outcomes/b0_full_rhs_recovery_gate_failure_20261018.json)、[run index](outcomes/run_index.json)、[summary](outcomes/summary.md) 和 [test summary](outcomes/test_summary.md)。

Review V2 的三次 source/attempt 和本机测试树身份均按原证据分列；文档结果 HEAD 由主控在分支统一收口时记录。

主控补充：在最终冻结源码 `53243cd6766b564fed17668753e9fdbb7cab1129` 部署后，使用工作站既有 native complex activation 执行新 B-action 振幅 fixture 与 two-input borrowed-buffer fixture，结果 `2 passed, 13 deselected in 0.56s`，随后才启动 `121210` 正式 attempt。该记录来自主控部署命令回执，不能抹去此前本机旧 ABI receipt 的阻塞记录。科学 source 与本次文档结果 HEAD 分开；最终结果 HEAD 由集中推送后回读提供。
