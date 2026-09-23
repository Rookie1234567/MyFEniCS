# Selective merge manifest V26

本 manifest 只登记当前 V26 收口涉及的最小依赖组。没有 master merge approval；V26 不改变 ordinary default。

| 依赖组 | 文件/证据 | 数值行为与边界 | 测试/正式证据 | 建议 |
|---|---|---|---|---|
| production numerical/core | `src/runners/task038_launcher.py` 的 V26 observe-only policy helper | 只修正 V26 Q4 的 watchdog swap-policy 接线；不改变 p6/p4 数值算子；旧 formal raw wrapper mismatch 保留 | `test_task39extra_v25_parameterization.py` targeted mock；旧 V26 formal run为 `c27c07e...` | review 后再考虑合入；不改默认 profile |
| reusable runner/watchdog | 同上及相关 policy dispatch | 让 worker summary 的 observe-only 语义进入 watchdog kwargs；没有新 PDE qualification | 23项 focused tests；compileall | 可审阅，不能把旧运行写成修复后重跑 |
| checker/benchmark | `benchmarks/postprocess_laptop_speed_v24_fe_metrics.py` fallback；离线 regression records | 只支持读取已有 summary 中缺少 semantic geometry identity 的旧记录；不创建 solver、不改变数值 | FE field、saved-output/channel/power checker 均离线通过 | 可合入为兼容性/证据工具 |
| compact evidence/docs | `response_v27.md`、`outcomes/setup_efficiency_v26.md`、V26 records、`summary.md`、`test_summary.md`、`run_index.json` | 记录 measured/derived/not_run/deferred；保留 64.917 s 首次 bug、001753 正式结果和 gate rejection | JSON parse、diff check、targeted tests | 优先合入证据文档 |
| research-only | V26 setup profile、component timing、T5 cache-deferred record | V26 相对 r2 慢，不能升级为加速或默认优化；无 matched component attribution | existing V26 formal + offline regression | 仅保留研究证据 |
| do-not-merge/default promotion | local numeric cache loader、V26 default promotion、任何新 PDE replay | T5 没有 qualified packet/loader；replay ledger exhausted；不得伪造第二场结果 | no new PDE by design | 不合入、不启动 |

## 身份与证据边界

- V26 old formal source: `c27c07e305739b2dcf02c18dde44a0bc8bc70642`。
- 当前 policy-fix source: `32bf03e0ab50ea67487ecb1ca06f5da468800482`。
- r2 speed baseline source: `4bf2bba56cc2e568d56ff3096aeb4a108744f28d`。
- V26 formal workflow 用时 `3595.9571450339936 s`，r2 为 `3114.283619607013 s`；V26 不作速度提升。
- 新 service `myfenics-case-20260923T014131-156906.service` 在 worker 前拒绝；其 log 和账本 hash 记录在 `setup_efficiency_v26_relaunch_gate_rejection_20260923T014131.json`。
- 本 manifest 不授权 master merge；最终合并必须等待主控明确批准。
