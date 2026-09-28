# Task042 首轮交付：F0 完成，等待共享工作站

| 项目 | 实际状态 / 数据身份 | 证据 |
|---|---|---|
| 最终分类 | `WAITING_FOR_SHARED_WORKSTATION`；F0 接口与隔离通过，F1–F5 `not_run` | [Gate](records/gate_decisions.json) |
| 分支 / 工作树 | `task42_neural_coarse_inverse`；`/home/fenics/Projects/NN-Lab` linked worktree | [Git 准备](records/git_preparation.json) |
| base / 初始任务锚点 | `ccd357885f7f9be84efe3be07868cc94f13d93fc` / `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`；均为祖先 | 同上 |
| clean 运行源码 | `9934c2e08d017124ba70bdc86ec0c22f39ca792f`；此后提交为交付文档，不替代运行源码 | [运行账](records/bounded_f0_runs.json) |
| 邻 heavy | 2026-09-28 08:57:36 UTC，原 2 nm worker 仍运行；另两 GPU 各100% | [现场快照](records/shared_workstation_snapshot.json) |
| 环境 | FE complex128/int64、MPI1；独立 Torch `2.7.1+cpu`；项目导入、可写缓存均在 NN-Lab | [环境与隔离](environment_and_isolation.md) |
| 无全局 p4 因子 | F0 新模块只有返回验证和声明检查；没有构建 FE/candidate/factor。实际部署 Gate 为 `not_run` | [架构](architecture_and_oracle.md) |
| review / merge | 待 ChatGPT review；未批准 master merge；普通默认未改变 | [response](../response_v1.md) |

目标是在保留原电磁方程和最终验算的前提下，减少粗层直接分解的内存。粗层直接分解相当于提前存储一套快速求解辅助表；迭代粗逆则逐步纠正误差，节省存储但可能增加作用次数。本轮先做好独立环境和严格返回检查，避免把不合格近似解送入原平衡预条件器。工作站仍忙，因此没有执行数值研究，不能判断低内存、线性降维或神经网络的实际收益。

## 实施矩阵

| 阶段 | 实施内容 | 状态 | 具体原因 / 范围 |
|---|---|---|---|
| F0 Git | 核验 canonical、仅 fetch 本分支、登记 NN-Lab、设置 upstream | measured pass | 原 Task39 refspec 保留；用户另授权仅追加 Task042 refspec |
| F0 环境 | 新 activation、两独立 venv、导入路径/实际动态库/缓存核验 | measured pass | FE 仅导入，不创建 mesh/form/JIT；ML 仅 CPU 导入 |
| F0 接口 | 原方程、累计端口、内部恢复、slave-zero、固定内层设置、因子容量声明 | 33 pure-array tests pass | 使用解析 toy 的受控 backend；不是 FGMRES 或 Maxwell 资格 |
| F0 历史 | 冻结神经 SHA 下001/004/005的11份实际文档及5个接口审计 | read-only complete | Task001 无 response 文件；无 merge/cherry-pick/代码迁移 |
| F1 | 真实小 FE、A6/A4/传递、固定 B0、离线 LU 参考 | not_run | heavy 资源 Gate 阻止；adapter/profile 尚未实现 |
| F2 | teacher、分段数据、POD / 可表达性 oracle | not_run | 没有真实算子或数据，不做 synthetic 训练替代 |
| F3 | 同预算 R-LIN 与一个 R-NN | not_run | 数据/表示 Gate 未通过；模型未创建 |
| F4 | 至少16未见 RHS、严格 p4 返回、三独立进程计时 | not_run | 没有合格实际 candidate |
| F5 | 条件 p6 外层和完整输出比较 | not_run | F4 未解锁 |

冻结输入见 [静态清单](../../../input/task042_neural_coarse_inverse/frozen_model.json)：13.5 nm、1°、s、original Si block、Full3D p6/h10，同网格 p4、双 Floquet 和完整 auto Fourier-DtN。252 cells、173802/53084 FE storage、80通道是历史锚点；当前 mesh/mode/physical SHA 均未构建，未强填历史数量。

## 统一数值与资源结果

| 路线 | 比较目的 | 原 A4 / A6 真残差 | R/T/A/A_volume、场、E/H、全部通道 | 端到端时间 / RSS / VRAM | 数据身份 |
|---|---|---|---|---|---|
| R-LU | 本轮准确粗逆参考，计入分解和验算 | not_run | not_run | not_run | 没有本轮实测 baseline |
| R-B0 | 去全局因子后的固定传统低内存 PC | not_run | not_run | not_run | 无 candidate 构造 |
| R-LIN | 在 B0 上增加线性低维修正 | not_run | not_run | not_run | 无数据、basis、线性 map |
| R-NN | 在相同表示上检验神经增量 | not_run | not_run | not_run | 无训练/checkpoint/推理 |

详见 [full p6 CSV](records/full_p6_comparison.csv) 和 [准确性、性能、内存](accuracy_performance_memory.md)。旧任务成功解仍是历史证据，不作为本轮速度分母。去因子、B0、线性降维、NN增量四项收益全部未测；G-memory/G-time/G-neural 和 N=1/10/100 摊销均 `not_run`。

| F0 实测口径 | 数值 / 单位 | 含义 / 证据 |
|---|---|---|
| clean 最终纯数组测试 | 33 passed，pytest 0.19 s； enclosing workflow 1.659649 s；RSS 67,231,744 B | [运行账](records/bounded_f0_runs.json) |
| 11个解析 toy 返回 | native witness 最大 `1.2757622972373108e-16`；port/recovery最大0 | [数组记录](records/pure_component_audit.json)；不是物理 A4 残差 |
| 初期安装/测试、失败导入和最终导入/测试 | 9个顺序监督工作流共72.225243 s；采样同时整树 RSS 最大236,548,096 B；各树 swap0 | 同上；峰值取最大，不相加 |
| 数组证据提取 | 1.751461 s；RSS 65,552,384 B；swap0 | [运行索引](records/run_index.json) |
| GPU | 不启动 GPU；Task042 VRAM 峰 `not_run` | CPU-only Torch；不能把邻 GPU 使用量记为本任务 |
| 覆盖限制 | 未持续监督编辑器、Git、只读审阅、venv 创建与等待 | 不虚构整段会话峰值/总耗时；最终静态检查另列 [测试摘要](test_summary.md) |

## 失败、决策与下一步

| 项目 | 事实 | 决策 |
|---|---|---|
| FE 初次预检 | C1 上错误 API `jit.get_parameters()` 抛 AttributeError；3.719178 s、179,027,968 B、swap0、后代清场 | 保留失败；最小修复为0.10实际 `get_options()`，补隔离 XDG_CONFIG_HOME；一次针对性重检通过 |
| 共享资源 | 原 worker PID341839/start_ticks17197130、CPU24，RSS快照1,149,927,038,976 B；监督器CPU9/10，另 ML CPU25–32 | Task042 CPU14仅轻测试；没有控制邻任务；交付后等待 review |
| 数值研究 | 未启动；不存在数值停滞、表示失败或NN负结果 | 不作算法结论、不进行参数扫描或自动等空闲启动 |
| 后续 | 同机重新核验 heavy 清场与 lock，完成 F1 opt-in adapter、真实身份和容量检查 | 再按原 F1→F5 Gate 顺序；首轮不跨到5/2/0.7 nm |

## Selective merge 边界

| 依赖组 | 本轮内容 | 建议 / fresh PDE evidence |
|---|---|---|
| production numerical/core | 无 production 变更 | 不提升新协议为生产粗逆；没有 fresh PDE |
| reusable runner/watchdog | 复用既有 subreaper；新脚本只是 F0 2 GiB 参数封装 | research tool；依赖既有监督器；仅自身后代可被停止 |
| checker/benchmark | 独立返回检查、33纯数组测试、import/path核验 | 可审阅基础接口；真实 FE witness、构造记账仍待资格化 |
| compact evidence/docs | 本 outcomes、response、progress、registry | 正负与未运行证据可独立审阅 |
| research-only | activation、独立依赖清单、静态模型冻结、新协议 | 全部保留本执行分支，等待 review |
| do-not-merge | venv、下载/bytecode/JIT缓存、raw日志/时间线 | ignored；不提交大数据、factor、模型或旧结果 |

实际变化和依赖见 [changed_files](changed_files.md)。本轮只推送执行分支，之后停止等待 ChatGPT review。
