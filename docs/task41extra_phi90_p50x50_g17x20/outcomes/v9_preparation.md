# V9 准备阶段：同一局部 LU 的 RHS 缩减与保存数据判别

本文件只记录 Review V9 的准备里程碑，不是 `response_v9`，也不是新的执行授权。执行依据仍为 `review_report_v9.md`（`b24b6ce6577225af7fb03e4a62bef80126efc9b8`）。结果基线为 `a63e51f39ee7ed35b03d521cb42fa3fe6c9f834f`。

## 当前状态与边界

| 项目 | 当前事实 |
|---|---|
| 科学候选 | `same_lu_rhs_solve`：每个非零内部 RHS 用原 LU 解一次 `Kz=b_i`，再计算 `-Jz`，避免先固化 T 后乘 RHS；不改 S、R、积分、native 或物理输入 |
| 实现 | 默认仍为 `stored_T`；实际同张量 J 按键只读保留并借用，Di 修正复用 z；新增计数、成本及释放检查 |
| 首个可执行阶段 | 现有 service/watchdog 中的 saved-star screen，只读 V8 两个 incident cells、四组已存 LU 及八个已存 z；不重新 factor 或积分 |
| 正式数值状态 | **NOT_RUN**：尚无 V9 局部 d 改善实测，更没有新全域 action/recovery PASS |
| 新窗口 | **PENDING_USER_APPROVAL**；86400/85200/1200 s，未生成真实授权收据、T0 或新窗口；原 V6 窗口已结束，旧账不改写 |
| 后续真实链路 | Task41 全域 volume-only owner 的新策略接入、紧凑 action/recovery 输出、独立终态 checker 和 qualified-owner 同进程交接仍需在昂贵重建前闭合；通用 adapter 的参数传递不能代替这部分资格 |
| 历史数值 | V6 两列完整 action 的冻结尺度误差 `1.7183209126709868e-10` / `3.6180522433957604e-10` 仍超过 `1e-11`；候选初次恢复也仍 FAIL。V8 局部反事实不能转授全域 PASS |
| 完整缓存 | 旧进程已退出；保存的小块不是 28,000-key 完整可恢复 owner。不声称旧 LU/J 仍 live |
| 资源 | J 的 `87,091,200,000 B` 以及旧 numeric 加 J 的 `435,653,172,000 B` 是派生载荷，不是 RSS 或准入结论；原 cap/reserve/swap/证据门均未改变 |

准备工作发生于新正式数值窗口之前，不能隐藏为零费用。现有执行对话本轮实现开始时间为 `2026-10-21T13:19:04Z`；主控更早只读核验、审查、等待及分项开发成本未完整记录，记 **UNKNOWN/NOT_RECORDED**。本文件没有以开发耗时冒充 FE、GETRS 或正式 service 实测。

## 只读输入绑定

两个报告保留原路径、字节、source 和窗口，consumer 单独绑定新合同与冻结源码：

| 输入 | SHA-256 |
|---|---|
| `results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_selected_star_35fd1bbf_20261021T072801Z_attempt1/task41_p0_v8_selected_trace_star_audit.json` | `1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f` |
| `results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_saved_checker_3ce1a158_20261021T092516Z_attempt4/task41_p0_b0_saved_evidence_audit.json` | `b12af06f818dd4a93443498371aa653216b1646207418f8eaac265e09ddf78c6` |

真实根为 `/home/fenics/Projects/laptop_share`。原报告绑定的数组逐文件核验，不能只相信这里两项哈希，也不改写旧报告。当前 service fixture 验证真实 selector→helper→watchdog 授权接线，但资源、activation 和子进程使用测试替身，不能写成工作站服务运行通过。

## 已实现的实际命令形状（尚未执行）

以下命令需先取得新窗口批准、记录正式准备 T0、冻结 clean source 并按现有授权格式保存真实授权收据。它们不会替用户批准，也不能用于复活旧窗口。

```bash
cd /home/fenics/Projects/laptop_share
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache native_linux
python -m src.runners.task41_p0_contract --prepare --case B0 --b0-v9-continuation \
  --runtime-prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  --abi-receipt benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  --jit-cache benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache
```

使用 prepare 返回的真实合同路径替换 `<frozen-v9-contract>`；选择未使用的 attempt，不覆盖旧输出：

```bash
bash scripts/run_case_in_user_service.sh \
  --service-unit task41-b0-v9-saved-star-screen-<attempt> \
  --task41-p0-execution-contract <frozen-v9-contract> \
  --task41-p0-saved-b0-v9-star-screen \
  --v8-report /home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_selected_star_35fd1bbf_20261021T072801Z_attempt1/task41_p0_v8_selected_trace_star_audit.json \
  --v8-report-sha256 1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f \
  --v8-checker-result /home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_saved_checker_3ce1a158_20261021T092516Z_attempt4/task41_p0_b0_saved_evidence_audit.json \
  --v8-checker-result-sha256 b12af06f818dd4a93443498371aa653216b1646207418f8eaac265e09ddf78c6 \
  --output results/task41extra_phi90_p50x50_g17x20/<attempt>/task41_p0_b0_v9_saved_star_screen.json
```

这里只是精确已有参数的待执行命令模板；真实合同/attempt 不存在时不能复制裸跑。服务限定只读保存包，不调用 FE worker。局部否决应保存 `LOCAL_CANDIDATE_REJECTED`，不自动启动全域；局部就绪也仅解除第一个依赖，后续仍须完整生产接线、资源、时间与原数值门。

## 测试与已发现的工程问题

第一次最终定向组合为 **26 passed in 1.04 s**；本地合格 activation 的 fixture，不是 FE 结果。随后主控发现旧 V8 helper 不必改变、有符号恒等式诊断遗漏、旧 B0 authority/v1 新字段兼容问题，要求窄修后再跑受影响节点；该最终增量结果以冻结时的 test summary 为准。

保留工程负记录：早期 fixture 缺 pytest 导入、临时合同路径/source 变量及 service 参数 guard/JSON reader 问题已定向修复；另一次扩到旧合同文件的运行有 3 项因历史 fixed window 过期失败，未通过改生产时间门或重跑 PDE 消除。Ruff 在现有环境不可用（NOT_RUN），未安装新环境或依赖。`bash -n`、相关 compileall 与 `git diff --check` 通过。没有全仓 pytest 或 CI PASS 声明。


冻结前修正已完成：旧 V8 helper 精确恢复；旧 stored_T cache identity v1 保留；旧 B0 authority/v1 不强迫新增字段，V9/v2 缺字段仍拒绝。有符号诊断真实计算选中行 `(J+TK)z` 并另列重组余差；candidate gate 仍由原完整 `T@bi`、`S@t`、`-(J@z)` 生成，诊断不能改变判门。最终执行者受影响节点 **10 passed in 0.54 s**；主控同工作树复验 **10 passed in 0.51 s**。其中故意污染诊断投影的 fixture 要求原 d 逐浮点列表不变。新增 fixture 首次预期遗漏诊断偏置，9 passed/1 failed，修正测试预期后通过，未放宽生产门。

完整节点命令、测试日志和冻结前源码内容 hash 见 [准备回执](v9_preparation.json)。日志 SHA-256：`3489eb2434195e306846bfcca847a76580c07ad48fe60931d3b8ca824d487e2e`；本机 ABI 日志 SHA-256：`9c5f454497bb6e17f1cdf5017c8234052fe1c9f4f57293f6eb10b3bcf4716cd1`。这些日志留 ignored artifacts，没有复制旧科学数组。
