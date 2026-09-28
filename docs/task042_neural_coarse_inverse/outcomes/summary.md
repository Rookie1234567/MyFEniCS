# Task042 第二轮：真实首轮试验，严格粗逆未合格

| 项目 | 实际结果 / 单位与身份 | 证据 |
|---|---|---|
| 终态 | `COARSE_INVERSE_NOT_QUALIFIED`；F1、teacher、oracle、CPU训练和三条F4路线已运行；F5 `not_run` | [独立重算Gate](records/gate_decisions_v2.json) |
| 授权 | 用户允许Task042受控共享运行，覆盖本任务§2.3 heavy禁令和全机独占锁；原task/review保留；不代表F0正式review通过 | [授权原文与适用边界](shared_authorization_v2.md) |
| 工作树 / 分支 | `/home/fenics/Projects/NN-Lab` canonical linked worktree；`task42_neural_coarse_inverse` | [隔离](environment_and_isolation.md) |
| 冻结模型 | original Si矩形块13.5nm、1°/phi0/s、p6/h10、同网格p4、完整80个DtN通道；252cells | [真实F1](records/f1_real_components_v2.json) |
| 真实运行源码 | F1 `cca180f875bd22146f2d30fa4d004e372135dfbb`；teacher `b72448bb2117a0221f041f1b47ac41049750a3c7`；oracle `d9de8ad69bfeeac4860e5187e1738c902a3d808e`；训练 `a221d881bae9405c98e351df2b0b9533582e6d50`；F4 `7216efa605bae155ee383fd716c0fae422448b52` | [逐run索引](records/run_index_v2.json)；后续文档HEAD不替代source |
| 候选无全局p4 LU | B0及线性/NN构建全过程没有global p4 factor；只有有界cell/port、43个<=512行patch和128行bottom | [构造与全部F4](records/run_index_v2.json)、[架构](architecture_and_oracle.md) |
| 资源 | MPI1、现场选核CPU0（48独立物理核，无SMT）；数学/编译/训练线程1；nice10/idle I/O；整树RSS hard16GiB/warning12GiB、own swap0 | [资源与影响](environment_and_isolation.md) |
| GPU / 性能 | 两卡持续邻训练，CPU-only；所有成本标 `shared-workstation`，性能结论 `inconclusive` | [时间与内存](accuracy_performance_memory.md) |

粗层直接分解提前存储一套精确求解辅助表，迭代粗逆则反复纠正误差，节省因子存储但可能难以收敛。本轮用固定传统块方法B0处理全部未知量，再分别增加线性低维修正与小型神经修正，检验它们能否把原方程的误差降到严格门限。真正的p4返回需原A4、端口和恢复全部通过`1e-10`；局部误差或训练loss变小不等于返回合格。

## 完成的数值阶段

| 阶段 | 实际结果 | Gate与限制 |
|---|---|---|
| F0历史 | 独立Git/FE/ML/缓存和33解析协议测试；先前因heavy等待 | [response_v1](../response_v1.md)及无后缀records是保留历史；不再把等待状态当本轮终态 |
| F1真实接口 | 原A4=PH A6P相对差`3.366065072840215e-15`；独立p4 Schur作用差`2.3566154699905024e-16`；非零内部/80端口制造解p4/p6原残差`1.2255722548154e-14 / 2.0935547822786585e-14` | 接口通过；F1 B0七个非零载荷在256步失败，全部保留 |
| F2 teacher | 256train/64validation/64heldout，每batch<=32；384对原方程/端口/内部/恒等式均<=1e-10；最坏native`3.959901353972973e-12` | global LU仅离线teacher；destroy且退出后才运行下一阶段 |
| F2可表达性oracle | ranks16/32/64/128全部通过预登记的诊断标准；rank128 validation误差比`.5138245737888352`、最佳native残差比`.3338841772011458` | 仅表示正信号，非严格逆资格；固定rank128继续，未扫描扩大 |
| F3 R-LIN / R-NN | 同basis/FP64/归一化/B0；NN两hidden64、103040参数、300epochs，validation选51；有载训练19.036s | 独立CPU-only Torch进程；heldout不参与训练或选型 |
| F4严格返回 | 三路线各同16 heldout；每路线只有精确零通过，其余15个均256步后未达1e-10 | 无fallback、无数值调参重跑；端口失败独立记录，内部恢复小不改变判定 |
| F5 / 三次合格计时 | `not_run` | 无F4合格路线，不能嵌入p6；不产生official R/T/A、场或通道数据 |

## 同组严格粗返回结果

| 路线/作用 | 严格通过 | 实际 PH b6 原A4残差 | 同 RHS port closure | 非零 RHS 内部恢复最大 | 整树 wall s | 整树 RSS 峰 |
|---|---|---|---|---|---|---|
| R-B0 | 1/16，仅零 RHS | 0.998655 | 0.465472 | 4.70942e-16 | 486.668 | 0.793 GiB |
| R-LIN | 1/16，仅零 RHS | 0.998262 | 0.239496 | 2.11953e-16 | 1239.273 | 0.962 GiB |
| R-NN | 1/16，仅零 RHS | 0.998456 | 0.179987 | 2.20347e-16 | 1238.082 | 0.937 GiB |

原A4残差是完整原方程的相对不平衡量，port closure是端口方程的独立相对不平衡量；门限均`1e-10`。内部恢复达到很小误差，只证明局部消元有效，全局及端口错误仍接近原载荷量级。全部16项与实值见[逐RHS CSV](records/strict_rhs_metrics_v2.csv)和[准确性分析](accuracy_performance_memory.md)。

去全局因子已由构造及容量记录证明；B0、线性降维和NN均未提供合格粗返回。oracle显示线性子空间能表示部分训练/验证误差，但未使严格迭代成功。神经额外贡献没有正信号，不能把表示改善或去因子的效果算给NN。共享负载、缓存及生命周期不同，不能据此宣布正式20%内存/时间改善或10%神经加速；N=1/10/100合格求解摊销与break-even未定义。

## 全过程数值成本及未运行项

全部正式组件尝试（包含4次实现/环境失败）监督wall合计`8250.064 s`；阶段同时整树RSS最大`2.198 GiB`（取最大，不相加），各树swap0。teacher、oracle、训练和各路线分别计费；安装/测试/预检另列，编辑器/Git/只读审阅的总会话内存与耗时未持续采样。所有数值成本均shared-workstation，未启动Task042 GPU，无本任务VRAM分配，PSS及cgroup峰未采样。

原p6物理载荷求解与全部R/T/A/A_volume、R00_s/p/total、复E/H、场/scaled-curl、80通道复振幅/功率均`not_run`，见[统一p6 CSV](records/full_p6_comparison_v2.csv)。p6仅F1矩阵作用/制造解接口验证，不冒充最终物理解。5/2/0.7nm、h/p/角度/几何泛化、GPU训练和无界参数扫描均未运行。

运行中未观测到触线的持续内存压力或Task042 swap，邻worker/监督器身份保留并有CPU时间推进；已有可读阶段记录缺少可比实时耗时，不能证明绝对零干扰，也不能判断邻任务自然阶段变化是否受影响。详见[环境与影响证据](environment_and_isolation.md)。

## 审阅与合入边界

研究接口、参数化监督器、严格checker、有限数值证据和模型总账可审阅；本轮研究粗逆未合格，不作为production默认。[实际变化与依赖分组](changed_files.md)、[测试](test_summary.md)、[数据与模型身份](dataset_and_model_provenance.md)、[response_v2](../response_v2.md)给出完整入口。保留所有失败与F0记录；只推送本执行分支，之后停止等待ChatGPT review，不合并master。
