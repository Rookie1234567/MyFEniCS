# Review v1 回应：R6 集中收口

| 身份 | 完整值 |
|---|---|
| 分支 | `task39extra` |
| Task base | `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` |
| R0 / R1 source | `1e10d80cdb446e23001d01d3886e20bc9a33a263` / `116df6e759fef2876da39ef89f8e4db4edb33771` |
| 唯一R3 source | `cbf56e87e515ab0c3fc5756cb6cf52feb047f610` |
| 当前代码HEAD | `597546311feea60d61acb2a9999b706dd895dcf0`；R3之后停止路由修复，主任务已推送；R6文档留未提交diff审阅 |
| R3 audit SHA256 | `a88a998e541bef7de69ff601dec7fe6b9736328837223a4a6b90c91107ee2cc5` |

## 本轮执行结果

| review阶段 | 执行与判定 |
|---|---|
| R0 | 完成同机profile；原22秒口径为非warm六次完整PC中位22.021386729524238 s，冷setup单列 |
| R1 | 等价原型7/7完成；same-input最大误差1.4723857041130954e-14，PC误差7.557862568198792e-13；中位74.87089344408014 s、ratio3.3999172878472805>0.75，`EQUIVALENT_SPEEDUP_INSUFFICIENT` |
| R2 | 速度Gate未过，按条件跳过；未再次调整R1 |
| R3 | 自动进入唯一LIGHT候选；用户授权原始13.5nm p6/h10 MPI1零初值；solve7200.255611149943 s触发停止，workflow7966.278611822054 s<10800 s |
| R4 / R5 | 原始残差/输出Gate未过，非可分与独立direct/h5 heavy未运行；不放宽问题 |
| R6 | 整理成本、贡献、资源、退出与局限；保留全部历史负结果和response_v1，不启动第三PC |

PC是帮助外层降低方程误差的一次辅助修正。R1保持S6路线的数学作用，只改变局部计算实现；R3改用H6–p4–H6，H6在p6上平滑局部误差，省去S6的p3/p1步骤，p4仍依赖一次全局分解。B6是H6使用的辅助算子，不是完整PC的逆。两条分支按本轮合同结束，但两种算法没有被彻底研究完或否定：R1只证明被测等价原型更慢，后续H6使用的contiguous packing未用于完整S6路线重新资格化，明确为not_run。

R0非warm成本中B6 assemble占62.847%、PC内原A6 volume占19.131%；R1对应累计341.0612200219184/83.96741845988436 s，比旧82.86955374584068/25.226458011951763 s更慢。嵌套父子范围不可重复相加，完整exclusive/inclusive口径、同机A/B和冷setup见 [成本与贡献](outcomes/cost_and_contribution_v1.md)。后续packing仅局部8单元诊断通过，不把组件提速当完整S6资格。

## R3最终可用证据

| 量 | 实际数值及限制 |
|---|---|
| last_safe | iteration576，原A6显式真残差0.0791360407785889，要求≤1e-6，失败 |
| reported末项 | iteration582，0.07877047901292458；不替代终止时真残差 |
| p4原残差 | 583次最大7.058163970105702e-11≤1e-10；准确中间逆不保证外层资格 |
| 完整PC | 582次，中位10.293892393587157 s；18完整32步周期+6次；第583个post只记录开始，未完成成本未知 |
| 计数 | H6=1164、B6=2328、原A6 MR=1746；S6/p3/p1=0；72安全monitor+初始，共73快照 |
| time-to-residual | 共同32步记录、约0.1826残差附近累计周期wall由3528.55降至2861.69 s，约19%；不插值、不外推1e-6 |
| 资源 | parent+完整后代同期RSS峰值3352014848 B；cap8588566528 B，至少4294967296 B余量；30230样本RSS可读，cap/余量违规0，进程树swap0，全局换页增量0 |
| PSS限制 | 1个尾样本不可读；该时RSS36118528 B低于可读PSS峰值3317585920 B，缺样不会提高采样峰值 |
| normal/partial退出 | parent为PERFORMANCE_CONTROLLED_STOP；SIGTERM后MPI leader exit1并清场；没有新safe快照或worker terminal summary，应用合作退出未证明 |
| checker / 输出 | 无final_residual_arrays.npz和checker.json，normal checker not_run；无official R/T/A、A_volume、R00_s/p/total、衍射级、复E/H、近场与参考平面 |

MR用原方程计算每段方向的缩放系数alpha，以避免误差被放大。对physical_middle，rho中位0.9818892519247393，abs(alpha)中位0.05529829316771673；仅此段在Galerkin关系下可用abs(1-alpha)解释剩余粗空间残差比例，其中位0.9499915645616905。563/582未缩放方向会增大残差，不能直接建议alpha=1。H6 pre/post不使用上述粗空间解释；不同Arnoldi输入的统计不是因果证明。

## 事后修复、测试与边界

R3尾段没有worker摘要。真实MPI1小fixture重现旧watchdog向整树（含mpiexec）发SIGTERM会抢先结束应用，支持修复退出流程。当前代码仅对未来LIGHT opt-in登记worker PID/start-ticks并核验活身份，只请求一次应用SIGTERM；最多60秒安全点宽限，资源/监控失败或宽限到期整树硬停。真实fixture验证合作、不合作、资源硬停、陈旧身份及旧路径复现；原R3空worker日志不足以独立断言精确死因。没有重跑R3，缺失结果不补造。

已有R3实现检查104 passed/1 skipped；停止修复23 passed，compileall/diff通过。失败的混合MPI测试批次与修复依据保留；环境显式传递仅用于测试隔离，生产不清洗环境。最终R6 task-focused回归及文档检查见 [测试摘要](outcomes/test_summary.md)。不运行full repository或新heavy；Ruff不可用，无CI通过声明。

最终R6回归为153 passed、1 skipped（MPI2专用），代码绑定当前HEAD；pytest原始120.69 s与外层monotonic107.97184431797359 s分别保留，compileall通过。JSON/链接/hash/计数与文档diff检查通过。批次账本截至该回归累计扣账11689.293882762804 s，上限36000 s，余24310.706117237198 s；包括早期60/5 s登记和所有失败尝试，不把账本总额称纯solve实测。剩余预算不授权继续formal。

账本共42项attempt，SHA256为`e9bfe4cb0042242ded42032d1e7e468676ffa4d8c5b57e83c4134ef35da732d3`，路径`benchmarks/artifacts/task39extra/review_v1_batch_budget.json`；按候选Gate收口，并非预算耗尽。紧凑JSON保留每项分类和扣账值，不新增预算工具。

独立同离散全场authority、非可分、h5以及0.7nm均未资格化。主要研究blocker是准确p4诊断逆辅助下外层真残差仍未在预算内达标；global p4 factor仍限制扩展，不能宣称production、2TB容量或0.7nm物理收敛成功。下一步集中review，不自动开展S6重开、第三PC或新formal。

证据入口：[汇总](outcomes/summary.md)、[成本/曲线小JSON](outcomes/records/cost_and_contribution_v1.json)、[运行索引](outcomes/records/run_index.json)、[测试摘要](outcomes/test_summary.md)、[移交/依赖组](outcomes/workstation_handoff.md)。原始矩阵、向量、cache和完整audit保持ignored，R6仅提交紧凑可核验材料。本文记录当前代码身份，待review后的文档提交SHA由最终交付另报，不伪造未发生提交。
