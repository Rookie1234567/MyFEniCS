# Review V32 P0 回应：旧 q4 严格接续与监督链已接通，运行窗待批准

本轮尚未新增 q4 native、因子、完整参考或原尺寸场的科学资格。已完成运行前 P0：明确指定旧矩阵的原路径与 hash，禁止找不到文件时悄悄重建；用已资格原始 B/D/H 端口数据配合必要的新 FE/体积/内部恢复对象，接入独立原生验证；修复实际受监督 checker 的跨窗口输入和收口记账。正式 24 小时窗口仍待用户批准，T0/deadline 未建立。

| 项目 | 本轮可核验结果 | 限制 |
|---|---|---|
| 源码冻结 | `a4f7d53af234dbd156388a4be133a0d5aeee1c16` | 基于 Review `e2737b4049045a1824f5a1c49bb7bfac85e6e929`；未合并 master |
| q4 正式导入 | package、DAT、worker、loader、finalizer/provider 与 checker 贯通固定旧路径/hash；新输出与旧只读根分离 | require-existing；缺失、内容或身份不符即拒绝，不 fallback routes/pattern/fill |
| 原生恢复对象 | 保存原始 B/D/H 与 fresh volume/recovery 组合；复用同一 q map 与 owner；真实调用内记录阶段 | 小型复数作用/RHS/恢复/销毁验证通过；未在工作站建立新正式 owner，不声称实际提速 |
| 监督链 | 真实小子进程经过 service 授权、supervisor、watchdog、实际 check-partial 和清场 | 合法 partial 为 PARTIAL_RECEIPT_CHECKED；缺 footer 仍为 NO_PARTIAL_FOOTER；两者均非 official 科学结果 |
| closeout 修复 | watchdog_end 显式记录实际 phase；V32 checker 对照固定 q4 模板、批准合同与 staged DAT | 不删 source/hash/资源/截止门；V31 原退出及缺 footer 负结果不追认通过 |
| 命令 | 已实际运行本机 prepare-v32-p0 CLI，生成 PENDING 草稿；window_created=false、未扫描大数组 | 正式 clean HEAD 包由主控冻结文档后生成；获批后才部署和起算 |
| 回归 | 50 个不同小型测试全部通过；执行者 6.24 s、主控审查 6.22 s | 同一集合重复两次，保留两次费用，不算100个测试；不是 PDE、全仓或 CI PASS |

## 原成果及历史问题

旧 q4 保持 `NUMERIC_COMPLETE_NATIVE_PENDING`：777424×777424、581086528 个结构位置、纯 CSR 11624840260 B。pending SHA256 为 `1938828321a57ee6eaaea0def485f73daddbd13432cc6ef8823d19bcc44640ad`。P0 没有再次扫描这三份大数组，也没有修改旧 pending 或把旧数据重署为新 source。实际运行时仍须受监督地执行完整内容、结构、有限性及身份核验，费用进入新获准窗口。

只读旧日志审计覆盖104216条资源样本，其中51485条落在未完成 owner wrapper 及清场区间。历史没有内部 FE、JIT、端口或凝聚的完整阶段边界，因此热点仍为 UNKNOWN。没有采样到 compiler 不能证明未发生编译，更不能把约4.57小时未完成 wrapper 全算成 JIT。此次只读提取耗时17.769863148918375 s；P0全部准备/实现父钟未完整记录，保留UNKNOWN，不拿测试时间代替总成本。

V31 原 q4 保存父段17281.822695894 s、watchdog父段33786.45508461888 s、tree RSS峰值16563810304 B、cgroup峰值24329441280 B及任务swap0属于历史同场证据，不是新 owner 或新因子的实测。本轮未建立新科学资源峰值。旧 q0资格保留，V29因子已销毁；八 q、完整参考与目标场仍未完成。

## 下一步与批准边界

请一次批准 Review V32 的新固定窗口：总86400 s，数值85200 s，最后1200 s收口。沿用 `fenics-ws:/home/fenics/Projects/laptop_share`，task cap 1649267441664 B、host reserve 68719476736 B、task swap0、原 ABI/MUMPS、MPI1/数学线程1及数学门不变。收到批准后，在第一项必要运行准备前锚定唯一T0；旧V31窗口与全部费用保留。

获准后直接按旧q4导入→独立native→三个真实sector→八q驻留准确因子→完整参考→条件原尺寸pilot连续推进。q4不重做pattern/fill；checker/输出错误优先复用合格保存数据。新科学门仍须实际通过，不把P0测试或文件hash当作数值资格。最终冷流程、原尺寸精度与十进制2TB/48h目标仍未闭合。

## 证据入口

- [主控P0审查与测试](outcomes/records/review_v32_controller_p0_audit.json)
- [P0 compact](outcomes/records/review_v32_p0_compact.json)、[时间资源分账](outcomes/records/time_resource_accounting_v32.json)
- [历史owner只读审计](outcomes/records/review_v32_historical_owner_audit.json)
- [实际命令与断点交接](outcomes/handoff_v32.md)、[测试摘要](outcomes/test_summary.md)、[运行索引](outcomes/records/run_index.json)

受监督小fixture使用临时身份与测试资源提供者，不是工作站真实运行的批准或资源收据。`ruff`在资格化环境中不可用，未安装另一套环境；bash语法与git diff检查通过。失败日志、旧NO_PARTIAL_FOOTER及未记录字段均保留。
