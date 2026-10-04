# Response V24：W0 已完成真实组件、独立检查与保存读回

用户在 Review V23 收口后要求在现有工作树继续 W0，再推进原尺寸完整端口。本次实际完成了 W0 的 worker → 原科学数组 → 未改数学的独立 checker → 本机持久读回。**数值组件 PASS，接收批次 PASS_WITH_QUALIFICATIONS**；初始 nice/IO/终端绑定缺口保留。不是再次确认收信或只做测试。W1 尚未启动：本机缺少已冻结 32060-key manifest 正文；已请求原件的可读位置，不要求用户手工 clone、接线或运行。

W0 检查的是：在每个单元内准确消去内部未知量，再恢复全部内部值，这两条计算路径是否等价于原三维方程。它使用非零内部及端口载荷、真实方向和周期约束，保留全部 52992 独立复 FE 系数、36000 内部量及 532 端口。固定资格模型是 80 hex/p6、λ0.7、φ5°、7/135 缩比的规则组件；不是原尺寸三维散射前向解。

## 1. 实际结果与原门

误差列沿用原 checker 的运算标度 `operation_scale`，分子/分母及所有 955 项见 [CSV](outcomes/records/w0_metrics_v24.csv)。制造态是预先给定全场并由原方程生成载荷的验算，不能当作未知入射问题已经求解。

| measured / derived，W0 固定同离散组件 | 实际值 | 原限值 / 判定 |
| --- | ---: | --- |
| 独立原 native 制造态相对残差 | 1.00024728294e-15 | ≤1e-10 / PASS |
| 增广 FE / port 制造态相对残差 | 5.00107631184e-16 / 1.11980109081e-16 | 各≤1e-10 / PASS |
| 制造态约化残差 | 1.55415099136e-14 | ≤1e-11 / PASS |
| 全部作用/恢复项的最坏相对差 | 1.50062605406e-12 | ≤1e-11 / PASS；完整原场恢复 |
| 纯代数项最坏相对差 | 2.50758590994e-14 | ≤1e-12 / PASS |
| 独立原门 / 故意错误负控 | 955 / 4 项通过 | 漏修正、错误共轭、错误符号、以 Hhat 替原 H 均被检出 |
| 本机完整数组读回 | 1619 原件 / 3287 逻辑角色；625253744 B 文件 | 全数值/file hash、形状、dtype、字节、清单配对通过 |
| 原尺寸 E/H/curl、复通道、R/T/A/A_volume | NOT_RUN | 无散射解、无 official 物理结果，不授目标解或 NN 增益 |

原 worker 21 个控制项通过后，独立 checker 重建原局部基、方向/MPC、完整载荷与恢复，没有只相信 worker 的 PASS。532 模式 same-live 资格及原 H 身份复核通过；没有用 Hhat 替换原 H。原科学文件和失败目录均不改。

## 2. Source、有限排障与成本

数值源码原样消费主线冻结 Git objects；只读 cache 没有 `.git`，不是新 clone 或第二个维护的求解器，也未修改主线工作树。

| 身份 | 完整 SHA / 绑定 |
| --- | --- |
| 输入审阅 seal / base | `43304469ca307b10dbccaccdf9c1229ca17ef3e3` / `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff` |
| worker 与独立数学 checker 依赖 | `d4b6ed6b6cb2a0431cb75bba9d8fc74dc9d9e382`；133 文件 / 3361424 B，运行前后 hash 相同 |
| 真正 worker 的接收源码 | `1527e11582dde9038a35f3b819f47caf080ce9b3` |
| 最终保存 checker / 读回源码 | `6eb24884c4443021150ce3d55fbf91a7395e21ee`；后续文档 HEAD 不替代它 |
| worker report SHA256 | `324d59624b8cb7837d7dc0251e60cc060b292dccea05002d07710d6c205318bf` |
| 原数学 checker 文件 SHA256 | `59766663b1e9e66f8cb0ce64407772ad952468693ad9ca42aef95dc0bfababfe` |
| 1619 原件读回清单 SHA256 | `3e9862fda086962986a3c1795b65f293937448ac93fd66d25d67b83ddf0e7e6c` |

完整 FE worker **只启动一次**。首次 checker 的 EMFILE、启动前观察器拒绝、第二次 EMFILE 全部保留；修复只调整自己的文件额度，并使逻辑别名复用同一只读映射。最终 3385 次读取请求仅映射 1619 原件，实际 1636 个 FD，soft4096/hard1048576，硬上限及系统配置未改。公共输入首行、测试断言作用域及 Ruff 小错均在本批定位修复。详见 [修复链](outcomes/records/repair_log_v24.json)。

| measured，阶段 / 同时树采样口径 | wall / s | RSS 峰 / B | swap / B |
| --- | ---: | ---: | ---: |
| 原完整 worker（嵌套阶段） | 3363.41865728 | 2338578432 | 0 |
| 首次原 checker（失败保留） | 47.877514524 | 405151744 | 0 |
| 第二次 checker 树（失败，含导入） | 71.808672812 | 328142848 | 0 |
| 最终独立 checker 树（含导入） | 142.490834824 | 972025856 | 0 |
| 完整纯数组读回 | 6.971519277 | 105771008 | 0 |
| 整个原 W0 父生命周期（包含 worker 与首次失败，勿重复加和） | 3478.276792353 | 2383208448 | 0 |
| 最终修复父生命周期（含60s稳定窗口，勿与 checker 相加） | 203.854294045 | 972025856 | 0 |

固定新接收窗口 14400s，T0=`2026-10-04T14:46:52Z`，截止 `18:46:52Z`；单调时钟包含600s早期未测准备 allowance，不重置原主线已过期窗口。资源账快照 7105.710350s 包含准备、等待、失败、代码和正式运行；后续汇总/文档/呈现/发布尾段另补记，全部仍受同一截止约束。旧3284s失联和所有旧费用保留，精确项目累计 UNKNOWN，父子墙钟不重复求和。

初始接收器漏掉 nice10/idle IO 和 tmux 管理核绑定，已于运行中只针对自己 identity-bound 四进程纠正，未重启 worker；这段缺口不能追认全流程资源 PASS。数学/数组证据成立，流程限定如实保留。永久修复后的独立 checker 全链单核、nice10/idle IO；原始 CPU 忙率与观察器自身开销补偿分别保留，邻任务窄亲和性及忙 SMT 排除不变。3GiB W0 / 2GiB轻树、MPI1、数学线程1、自身swap/OOC0、系统余量和384GiB邻增长门不放宽；MPI后台线程并不冒称一个OS线程。

## 3. 下一实际卡点与完整目标

| 接续项 | 当前证据与执行边界 |
| --- | --- |
| W0 | 实际数值/读回闭环完成，流程附限定，待审阅；原址 raw、科学报告、资源与 source 冻结 |
| W1 原尺寸全端口 | 三个声明原路径和固定 Git tree 均无 manifest 正文。需要已保存 36,244,923 B 原件，SHA256 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`；不能用30250B库存摘要或重新生成 AUTO 替代 |
| W1 真正接入后的门 | 复用已有可靠q60及方向边界，只核实际32060全key、真实材料/RHS、原H、MPC与内部恢复；本轮未冒称已通过这些门 |
| W2 | dot C1c/后端及W1前置尚未闭合；未复制dot存储、传统PC或全局求解器 |
| FEINN与生产 | FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED；D0成本否决、D1未运行；无NN训练或初始化收益 |
| 原终点 | 原50×25×140nm、Si17/120nm、λ0.7完整3D FE，decimal2e12B整机、swap/OOC0、172800s完整流程及原精度门仍未达成 |

工作树本身已经承载并完成了真实 W0。尚不能启动原尺寸端口的具体原因是冻结输入缺失，而不是目录名称。没有扫描权重、扩大模型、重建AUTO或重复主线Gx784参考。M3600较好时刻、最终退化、旧端口/场失败、UNKNOWN及全部费用均保留。

## 4. 交付与检查入口

[专题](outcomes/w0_receiver_v24.md)、[运行/全部hash](outcomes/records/run_index_v24.json)、[独立数学原量](outcomes/records/independent_checker_v24.json)、[955行CSV](outcomes/records/w0_metrics_v24.csv)、[本机读回](outcomes/records/durable_readback_v24.json)、[资源账](outcomes/records/resource_costs_v24.json)、[Gate](outcomes/records/gate_decisions_v24.json)、[测试](outcomes/records/targeted_tests_v24.json)、[输入及接入包](outcomes/records/next_input_and_handoff_v24.json)。最终28项pure targeted fixtures、Ruff和compile通过；不声称full pytest或CI。大数组/原始科学报告/日志/cache留ignored。

实际GitHub呈现单列 [呈现记录](outcomes/records/render_check_v24.json)，不拿本地parser或旧Review V23的视觉收据充当新页视觉通过。完成本批只推精确FEINN分支；准确发布HEAD、tracking、工作树和自身清场见最终交付收据及最终回复，不合并master，不修改其他工作树。整批一次正式通知审阅线程后停止。
