# Review V32 回应：q4 native 通过，固定窗口受控停止

## 当前终态（2026-10-15，新加坡；原始时间戳保留 UTC）

本轮沿 V32 已冻结源码继续执行，source 为 9ba8f0aa2750d020533321860d653dbbc44b885f。固定窗口已在数值截止处受控停止。本轮 source 767323bbee161a6163fec01d27c96723f52b5f97 已新增完成 q4 独立 native；本次续跑复用其通过收据；本次没有完成完整参考逆、其他 q 的全组因子或原尺寸目标场。

| 阶段/对象 | 实际结果 | 解释与边界 |
|---|---|---|
| q4 CSR/native | COMPLETE；四项 CSR 作用均通过，最大相对误差 2.6835748652861403e-14，限值 1e-11 | 777424×777424、581086528 个结构槽。复用既有 q4 独立 native 收据；未声称本次重新构建或生成当前 live factor |
| global_reference_builder | STARTED，数值截止前未记 COMPLETE | 外层阶段跨度约 46863.032 s；内部事件没有把时间拆到某个具体函数，热点仍 UNKNOWN |
| 其他 q 与因子库 | 未取得新的 COMPLETE/native；当前 factor bank 没有新增 q CSR 或因子 | 不补造缺失事件，也不把 UNKNOWN 写成 0 |
| 完整 reference / target FE | 未完成 / NOT_RUN | 没有原尺寸场、完整 true residual 或 official R/T/A |
| required checker | NO_PARTIAL_FOOTER | 无 worker footer；checker_passed、full_pass、official_result 均 false。未合成 footer，也不抹去独立 q4 结果 |
| 停止与清场 | PERFORMANCE_CONTROLLED_STOP；SIGTERM 后 30 s SIGKILL；worker exit -9；后代已清场 | 固定时间门触发，不是数值失败或内存失败 |

| 时间/资源量 | 记录值 | 口径 |
|---|---:|---|
| run_case 父段 | 49072.819633 s | 运行外层父钟 |
| required checker 父段 | 2.896090 s | 完整外层父段合计 49077.043640 s，另含入口核验、activation、ABI 等；父子不重复相加 |
| watchdog 父段 | 49072.059610 s | 嵌套于运行区间，不重复相加 |
| simultaneous process-tree RSS 峰 | 50996031488 B | 进程树同时采样峰 |
| 专用 job cgroup memory 峰 | 33537933312 B | 与 RSS 分开报告 |
| task swap 峰 | 0 B | 任务级零 swap 门通过 |
| 宿主 swapin/out 增量 | +82 / 0 页 | 全局诊断值，不能归因给本任务 |
| campaign 累计扣款 | 85235.547721 s | 最后已落账值，非此时投影累计；01:58:26Z 投影累计 85793.12263780605 s；不刷新窗口 |

窗口 T0 为 2026-10-14T02:08:33.255938807Z，数值截止为 2026-10-15T01:48:33.255938807Z，总 deadline 为 2026-10-15T02:08:33.255938807Z；window SHA-256 为 ec92e117479ef7e41854a4dab647c8c1bc963ef2705fb6ec390926f252294bf6。窗口未延长，未再次启动数值计算。

下一轮应在 src/solvers/task40_v10_p6_yorbit.py 的 build_task40_v10_p6_reference_inverse 中，分别记录 _build_same_mesh_levels、build_same_mesh_physical_action(..., verify_dtn_quadrature=True) 以及 q provider/sector builder 的真实调用边界。本次只证明外层 global_reference_builder 长时间未完成，不能断言其中哪一项是热点；该建议不授权新运行。

完整轻量索引见 [V32 terminal closeout](outcomes/records/review_v32_terminal_closeout.json)。主控保存的终态原始文件位于 benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation/terminal_9ba8f0aa/；包含 controller_terminal_readback、run summary、events、watchdog、受监督 checker request/response 和原始输出，并有逐文件 SHA-256 索引。P0 定向回归的 50 个不同测试通过；执行者与主控重复运行的是同一集合，不按 100 项累计。q4 selector 修复另有 1 项定向测试通过。收口期间未重跑 PDE、全仓测试、Ruff 或 CI；GitHub 页面渲染未核验。

> 以下保留的是运行窗批准前的 P0 快照。其“窗口待批准”和“q4 native pending”只描述当时状态；本页开头的终态记录覆盖其后的实际运行结果。

# Review V32 P0 运行前历史记录

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

## P0 运行前批准边界（历史快照）

请一次批准 Review V32 的新固定窗口：总86400 s，数值85200 s，最后1200 s收口。沿用 `fenics-ws:/home/fenics/Projects/laptop_share`，task cap 1649267441664 B、host reserve 68719476736 B、task swap0、原 ABI/MUMPS、MPI1/数学线程1及数学门不变。收到批准后，在第一项必要运行准备前锚定唯一T0；旧V31窗口与全部费用保留。

获准后直接按旧q4导入→独立native→三个真实sector→八q驻留准确因子→完整参考→条件原尺寸pilot连续推进。q4不重做pattern/fill；checker/输出错误优先复用合格保存数据。新科学门仍须实际通过，不把P0测试或文件hash当作数值资格。最终冷流程、原尺寸精度与十进制2TB/48h目标仍未闭合。

## 证据入口

- [主控P0审查与测试](outcomes/records/review_v32_controller_p0_audit.json)
- [P0 compact](outcomes/records/review_v32_p0_compact.json)、[时间资源分账](outcomes/records/time_resource_accounting_v32.json)
- [历史owner只读审计](outcomes/records/review_v32_historical_owner_audit.json)
- [实际命令与断点交接](outcomes/handoff_v32.md)、[测试摘要](outcomes/test_summary.md)、[运行索引](outcomes/records/run_index.json)

受监督小fixture使用临时身份与测试资源提供者，不是工作站真实运行的批准或资源收据。`ruff`在资格化环境中不可用，未安装另一套环境；bash语法与git diff检查通过。失败日志、旧NO_PARTIAL_FOOTER及未记录字段均保留。
