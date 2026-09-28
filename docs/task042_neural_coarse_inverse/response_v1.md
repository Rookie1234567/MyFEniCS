# Task042 Response V1：F0 完成，资源等待

| 身份 | 实际值 |
|---|---|
| branch / upstream | `task42_neural_coarse_inverse` / `origin/task42_neural_coarse_inverse` |
| 工作树 / common Git | `/home/fenics/Projects/NN-Lab` / `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` |
| base | `ccd357885f7f9be84efe3be07868cc94f13d93fc`，已验证祖先 |
| 初始task锚点 | `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`，已验证祖先；没有为匹配旧SHA回退 |
| HEAD / source（最终clean F0运行时） | **9934c2e08d017124ba70bdc86ec0c22f39ca792f** |
| 交付文档HEAD | 后续C5提交；精确最终HEAD/clean/ahead-behind由推送后Git回报给出，不替代上述运行source |
| 最终阶段 / 分类 | F0完成；`WAITING_FOR_SHARED_WORKSTATION`；F1–F5 not_run |
| review / merge | 待ChatGPT review，未合并master或其他分支 |

canonical与origin/worktree现场核验后，NN-Lab本身登记为linked worktree。远端开始时实读f8c51c8；仅取任务对象/ref并禁用维护。原fetch只映射Task39，使标准upstream失败；收到用户明确“允许仅追加Task042 refspec并设置upstream”后仅追加该映射、保留原URL和refspec，再建立正确upstream。没有独立clone、force/reset/stash/clean，旧计算/文档工作树HEAD保留。完整准备过程与真实失败见[outcomes/environment_and_isolation.md](outcomes/environment_and_isolation.md)和[Git record](outcomes/records/git_preparation.json)。

本轮停止由资源决定：2026-09-28T08:57:36.348903Z，原2nm PID341839/start_ticks17197130仍运行，CPU24、RSS1,149,927,038,976B；原监督CPU9/10；另一任务两GPU100%、CPU25–32。[现场记录](outcomes/records/shared_workstation_snapshot.json)来自只读status/stat/affinity与短GPU查询，无邻任务smaps/numa_maps/大日志扫描或控制动作。Task042固定CPU14、数学线程1、整树2GiB上限，仅做F0；没有后台等空闲启动器。

FE与ML分环境/分进程：新`.venv`只读使用合格complex128/int64 FE prefix、MPI1，独立`.venv-ml`为Torch2.7.1+cpu。`src`全部从NN-Lab导入，results/artifacts/TMP/XDG/JIT/bytecode/Torch/HF/model/pip等可写位置全部隔离。[最终环境records](outcomes/environment_and_isolation.md)绑定clean源码9934c2e；FE只导入，没有构造mesh/form/JIT/factor。FE初检误用cache API失败，保存原失败并一次最小修复后重检通过，不是数值停滞或参数调优。

新协议要求原A4、累计port closure和内部恢复三个独立数值witness，complex128/finite/尺寸/逐位slave-zero及零RHS；固定RIGHT FGMRES32/max256/zero start和构建容量声明。它只是严格返回验证接口，实际FGMRES/B0/FE adapter尚未实现，旧LU ledger及MatSolve计数未改。**F0没有构建global p4 LU，但真实candidate部署的无因子Gate未运行**；不能把声明或toy检查当实际因子消除资格。[架构与oracle审计](outcomes/architecture_and_oracle.md)明确旧factory先建global factor的禁区，以及非零port实际RHS需补绑定。

clean源码上的33纯数组测试通过（pytest0.19s）；11解析toy返回中native witness最大1.2757622972373108e-16，port/recovery最大0。[这些数值](outcomes/records/pure_component_audit.json)不是Maxwell原A4/A6残差。初期安装、开发测试、保留的失败导入与最终导入/测试9个受监督顺序工作流合计72.22524276096374s，RSS采样峰236,548,096B、各树swap0、后代清场；toy证据提取另1.7514610590296797s/RSS65,552,384B。[完整成本与范围](outcomes/accuracy_performance_memory.md)、[测试](outcomes/test_summary.md)、[运行索引](outcomes/records/run_index.json)保留逐项精确值与raw hash。GPU训练/推理未启动，Task042 VRAM峰not_run；未持续监督Git/编辑/审阅/venv创建，不伪造整段会话资源总账。

R-LU/R-B0/R-LIN/R-NN本轮全部not_run；teacher、dataset、split、basis、线性map、模型、checkpoint均未创建，[provenance](outcomes/dataset_and_model_provenance.md)写明null与具体原因。故原A4/A6、R/T/A/A_volume、全部通道、场/scaled-curl/E/H、内存/时间改善、NN是否超过线性和N=1/10/100摊销都没有本轮数值结论。没有以历史结果补分母或把去因子/传统/降维收益归给NN。

已只读审计冻结神经SHA下Task001/004/005全部11份实际合同/最新review/response/summary及5个模型/capture/teacher接口；Task001实际没有response，已列缺失。[审计索引](outcomes/records/neural_reference_audit.json)保存blob和依赖。001整体更慢、004全16 exact two-step仅是局部逆改善信号、005完整模型+basis+private CSR超预算且非线性无明显线性优势，均保留其限定；本轮没有整体迁移、旧CSR副本或LU fallback。

交付包含任务书要求的summary、隔离/架构/provenance/准确性与资源/测试/changed_files、run index、Gate、component/full p6 CSV，并同步本分支development progress和模型总账独立小节。详见[统一summary](outcomes/summary.md)。只推送 `HEAD:refs/heads/task42_neural_coarse_inverse`；完成文档渲染与最终Git核验后停止，等待ChatGPT review。继续研究需重新确认heavy清场/同机lock，依序完成F1真实模型和无因子factory、F2oracle、F3同预算线性/NN、F4严格返回，最后才允许F5；本轮不自动续跑。
