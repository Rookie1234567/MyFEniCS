# Task43 执行进展

| 范围 | 当前实测状态 | 证据 |
|---|---|---|
| 工作区与分支 | 复用 NN-Lab-V2 注册 worktree；跟踪既有 `origin/task43_hp_adaptivity`；初始 HEAD `0a625d770e1d3638bf53016a72facecfc8c81407`，基线祖先核验通过 | [工作区与环境](records/workspace_environment_v1.json) |
| 运行环境 | 复用 Task40 pord64 activation，complex128/int64；原通用 activation 缺失 MPC，未用其启动正式 PDE | 同上 |
| 旧成果 | 旧分支保留；按用户后续授权删除旧 Task42extra 大型 artifacts/results，保留删除前路径与体积；这些大文件本地已不可回放 | [清理记录](records/old_artifact_cleanup.txt) |
| p3/p4 局部核心 | 参考空间、实际实体阶次映射、周期约束、复数装配及内部场恢复定向测试通过 | [G1 组件记录](records/g1_components_v1.json) |
| p4–6 兼容 | 参考空间模块 9 项通过，既有阶次计划及 local-h 内部阶次回归通过 | 同上 |
| 悬挂约束 | 17 项通过，1 项旧 p4 字节哈希失败；初始源码与修改后矩阵在当前 ABI 下逐项相同 | 同上；失败不改为通过 |
| one-level 联合 h/p 组件 | p3/p4、p4/p5 的 9↔12 单元独立已知场检查通过；真实 36 单元空 h active-p3 的独立残差、同阶完整场/612 模态对照和 MPI1/2 对照均通过 | [mixed-p 组件](records/mixed_hp_9_to_12_component_v1.json)；[三锚点记录](records/h100_anchor_triplet_v1.json) |
| 完整场比较与首轮选择 | 冻结180单元active-p3 current及Y6_1/Y6_2共同q8/q10积分选出46个单元；首轮p-up按冻结规则接受为transition 1，accepted updates=1；首轮h受控停止，资格状态unknown | [transition 1记录](records/round1_selection_transition1_v1.json)；Y5_1及最终6×10×6 p6对照未读 |
| Round-2 p-up 与残差修正 | 首次求解在内部场恢复后因 full-active residual `9.1353e−8 > 1e−9` preflight 失败，未写完整场checkpoint或运行独立A6；随后同一计划以显式 same-LU 校正完成求解，并按冻结 G/J/noise 与实际 DoF 规则接受为transition 2（accepted updates=2）。Round-2 h 计划审计为 579 叶、ΔFE=60,349；其含噪得分上界低于p-up保守下界，故 not_run/unknown，不是数值资格通过 | [transition 2选择与失败成本记录](records/round2_selection_transition2_v1.json)；[持久化独立复算](records/round2_independent_audit_v1.json)；[修正组件记录](records/same_lu_residual_correction_component_v1.json) |
| p6 carrier 张量组件 | Task43 实际完整 curl+mass/q15/default grating 单元的 FFCx 与 BlockedGram 矩阵相对差 1.7235×10⁻¹⁵（门槛 1e−10）；p6 carrier 上 active p3 builder 定向重试 4 项通过 | [张量组件记录](records/p6_tensor_component_v1.json)；首轮接口失败日志保留 |
| 36 单元小模型与独立 A6 | attempt1 **数值门失败**：active 预检查残差 1.6445×10⁶⁴，A6 未调用；attempt2 使用已授权的边界幅值缩放后，solver、完整独立 active action 和两级残差门均通过。A6 relative residual 为 8.7763×10⁻¹³（task gate 1e−6、小模型门 1e−8）；独立行数为 trace 1782 + cell interior 1296 + modal lower 612 | [attempt1 负结果](records/a6_component_attempt1_v1.json)；[attempt2 组件记录](records/a6_component_attempt2_v1.json)；全量逐模态数据留在 ignored artifact |
| 真实场接线级锚点 | 三个 36 单元 h100 算例均通过同阶、完整场/端口和 MPI 等价 Gate | 属于 `numerical_sanity_only`，不能代替空间精度证明 |
| 正式 180 单元起点 | 3×10×6、active p3；独立 A6=2.3848e−10，condensed residual=6.3065e−11，能量闭合差3.2516e−13；15,120独立 FE DoF | [正式起点与参考恢复](records/initial_current_and_reference_restore_v1.json)；只通过离散求解门，空间精度待比较 |
| 丰富参考的原场恢复 | Y6_1/Y6_2 的576单元p6系数、网格/周期约束与历史612模态身份吻合；12,800点E差0，H相对差约8.7e−16 | 同上；只取得恢复身份，不等于完整参考精度、q/R14或侧壁资格 |
| 自适应闭环与成本 | 七个p-up候选已按冻结规则接受，accepted updates=7；Round-7 η_G=0.000194591143、J∞=54.874993，仍未达到最终精度；h1受控停止/unknown，h2–h7均未完整求解 | [transition7](records/round7_selection_transition7_v1.json)、[Round-7独立审计](records/round7_independent_audit_v1.json)；真实h、独立精度及同精度成本优势仍缺 |
| Round-6 真实父场计划 | accepted5重新标记48格，无p6饱和；p/h正式空间审计及p同网格转移完成；p候选后续以固定MUMPS完成并接受transition6；h仅计划审计后按界剪枝 | [Round-6计划与成本](records/round6_plan_transfer_audit_v1.json) |
| 固定直接因子后端组件 | 真实36格mixed p4/p5、完整612模态的PETSc LU/MUMPS原数组等价检查通过；末尾JSON标量失败保留，比较从原数组单独恢复；默认后端不变 | [后端组件、失败与恢复](records/direct_factor_backend_component_v1.json)；不是正式候选精度或全流程加速证明 |
| Round-7 准备与空间审计 | accepted6真实场重新标记54格，52可升、2已p6；显式跳过未使用的p转移，真实p/h authority均完成；p候选后续已解并接受transition7，h按界剪枝未解 | [计划、两项小修、测试与负证据](records/round7_plan_preparation_audit_v1.json) |
| Round-8 真实父场计划 | accepted7重新标记31格，均p5可升；p/h实际空间authority完成，尚未运行第8轮PDE或接受transition8 | [第8轮准备compact](records/round8_plan_preparation_audit_v1.json)；无需源码/cache改动，转移显式not_run |
| 迭代与 0.7 nm | `not_run`，等待前置 Gate | 不启动额外 campaign |

局部 p 自适应通过增加选定单元及共享边、面的多项式阶次来提高表达能力；局部 h 自适应把选定单元分成八个更小单元。二者均需额外约束，保证相邻单元和周期边界上的场能够正确连接。当前组件验证只说明这些空间与装配操作局部一致，还不能证明真实散射解更准确。

场比较需要在同一物理位置评价不同网格的解。当前组件把每个单元的原始高阶电场及旋度复制到能完整容纳这些多项式的独立单元表示（DGQ6），再用共同积分点计算差异，避免低阶可视化输出丢失细节；代价是额外临时场存储和采样时间。残差则衡量把解代回离散方程后还剩多少不平衡，残差不过关时不能用输出功率证明物理解正确。

新增 p3 测试曾暴露一处梯度秩误判：旧判据使用 QR 分解对角元估计独立方向数，把应为零的常数梯度误算为额外方向。现改为奇异值分解的标准浮点秩判据，并以常数核、curl-grad、方向变换及局部凝聚恢复交叉验证。阈值尺度随判据改变，不能表述为“阈值数值不变”。旧 p4 哈希失败另属起始源码在当前环境下已存在的身份差异；未修改旧 golden。

用户指定最终对照为 50×50×140 nm、6×10×6、uniform p6。该信息只用于选型完成后的独立精度及自由度比较，不进入标记与候选排序；不宣称整个研究从未知道对照。独立有限元自由度的公式估计为 237600，仍须用实际约束审计核对，不能与凝聚后的矩阵行数混称。参见[对照合同](records/final_control_contract_v1.json)与[推导计数](records/uniform_dof_estimates_v1.json)。

attempt1 与 attempt2 是两个独立结果，均保留。attempt1 使用未缩放衰减模态并在进入 observer 前因 active residual 超门而失败；attempt2 启用 `boundary_magnitude_scaled_r5_v1` 后，36 单元、uniform p3-on-p6 的同类组件算例完成。attempt2 的 condensed true relative residual 为 3.0631×10⁻¹³；独立重组的 FE trace、cell interior 和原始 modal lower 行残差范数分别为 4.2934×10⁻¹³、5.5804×10⁻¹³ 和 1.1028×10⁻¹³。primary modal R/T 为 0.9999860056 / 1.15824×10⁻⁵，`A_volume_total` 为 2.4120155×10⁻⁶，`R+T+A_volume` 与 1 的差约 1.83×10⁻¹³。这些量来自 `numerical_sanity_only` 组件；runner 内部 `official_result=true` 不代表 Task43 正式模型或精度结论。attempt2 runner 总时长约 541 秒，完整 pytest 595 秒；A6 observer 在报告中只记录合并区间，编译与后续 action 未分别计时。单 rank 历史 RSS 峰约 1072 MiB，不是编译子进程计入的进程树峰值，也不是资源 Gate。

这三个 36 单元 fixture 都不是冻结的 3×10×6 起点。它们已验证同一几何上，原生 p3 有限元空间与 p6 载体上的空细化 active-p3 空间给出一致的全域场和 612 个端口模态；同一个 active-p3 算例在 MPI1/MPI2 下也一致。它们仍不能证明更细网格上的精度、自适应收益或完整任务完成。后续显式 Task43 profile 已将 variable-p 体张量的几何/缓存身份切换为 `raw_unrounded`；local-h forest及拓扑box key仍保留12位舍入，不能宣称整条链都不舍入。本次冻结轴及单层二分坐标可精确表示；历史三等分参考采用其原始 Task40 网格恢复协议。

## 正式起点与丰富参考恢复（G2准备）

正式起点用较少的多项式未知量先求一个场，再将它与更丰富的已存场比较，寻找需要提高表达能力的单元。本次求解采用直接消元，保存了完整恢复系数、实际网格和自由度顺序，使后续可以在新公共积分点重采样。这样避免因缺少场数据而重复求解，代价是额外存储和后处理时间。

| 模型与目的 | R / T / A_volume | 自由度与方程 | 实测成本及结论 |
|---|---|---|---|
| phi90、13.5 nm、3×10×6、全体active p3；正式current | 0.807473677583 / 0.005279003523 / 0.187247318894 | 独立FE=8640 trace+6480 interior=15120；612端口；凝聚系统9252行、2,420,652 used NNZ；p6存储124530 | watchdog395.323s；同时进程树RSS峰1,270,714,368B（1.18345GiB），task VmSwap峰0；完整A6及物理闭合通过，尚未通过空间精度门 |
| Y6_1 selection参考恢复；6×16×6、p6 | 历史功率只随原始身份保留 | 389832个complex128存储系数；历史unscaled模态转换到boundary规范后比较 | 恢复及核对21.776s；E历史样本差0、H相对差8.7304e−16；公共q8/q10比较完成，仍非精度/连续参考资格 |
| Y6_2 calibration参考恢复；不同y分段的6×16×6、p6 | 用于测量参考之间的差异 | 389832个complex128存储系数；同612模态 | 恢复及核对21.254s；E差0、H相对差8.6978e−16；公共q8/q10比较完成，不替代最终holdout |
| Round-1 p-up：46个标记根单元由p3升至p4，180个叶单元 | 0.619051847080 / 0.012126176567 / 0.368821976411；能量闭合差5.7802e−11 | 独立FE=9,887迹+9,792内部=19,679（较current +4,559）；612端口；矩阵10,499行、3,049,725 NNZ | watchdog总时长1,694.686s，进程树RSS峰1,438,400,512B，task VmSwap峰0；独立A6=1.1636e−9、凝聚残差=7.3970e−10；η_G=0.4280717→0.2927588，J∞=556,138.09→367,685.66，按冻结规则接受为transition 1（accepted updates=1），但最终精度未通过 |
| Round-1 h：46个标记根单元请求细化，闭包实际形成600个p3叶单元 | legacy求解器报告R/T=0.552257539825/0.015288131019；`A_volume_total=null`，不是Task43 gated物理结果 | 计划审计FE DoF=25,635迹+21,600内部=47,235（较parent +32,115）；增广矩阵26,247行、6,695,999 used NNZ | watchdog记录`USER_CONTROLLED_STOP`，2,430.829s，进程树RSS峰2,904,961,024B、task VmSwap峰0；solver residual=7.4766e−10。未保存Task43独立A6、完整field/storage或候选record，故h数值资格unknown |
| Round-2 p-up：180叶；51个请求升阶、41个邻接闭包强制升阶，p3/p4/p5=81/60/39 | R/T/A_volume=0.385363241190/0.023644896449/0.590991862361；η_G=0.292758831001→0.124586848900；J∞=367685.6637→134007.8296，witness为R00_s | 独立FE=13,602迹+18,756内部=32,358（较parent +12,679）；612通道 | watchdog2,252.183s、进程树RSS峰2,165,133,312B、task VmSwap峰0；A6=2.7081e−9、凝聚残差=3.1939e−13、闭合差=2.7267e−13。top_p固定尺度误差2.32894e−4→2.59190e−4略恶化，bottom_p 4.00439e−4→2.88524e−4改善；依冻结单位DoF分数接受为transition 2，最终1e−4精度门未通过 |
| Round-2 h：51个标记根请求细化、6个材料闭包强制细化，审计形成579叶、p3/p4=246/333 | 不运行PDE；按当前parent `η_G≥0`，新增独立FE DoF=60,349 | 独立FE=35,208迹+44,820内部=80,028；跨网格转移仍not_run | h实体审计嵌套耗时461.392s；包含p/h计划和p同网格转移的runner内部耗时767.096s（以外层shell时间推得的wrapper为774.183s，二者嵌套不相加）。含噪score上界4.85125e−6，低于实测p-up保守下界1.32631e−5，按预冻结规则剪枝本候选；该剪枝不构成h Gate通过，后续真实h资格仍未关闭 |
| Round-3 p-up：60个请求升阶、9个邻接闭包强制升阶，180叶，p3/p4/p5/p6=51/60/60/9 | R/T/A_volume=0.293641473138/0.037723817989/0.668634708875；η_G=0.124586848900→0.048336049703；J∞=134007.8296→42271.5272，witness为R00_s | 独立FE=16,442迹+26,766内部=43,208（较parent +10,850）；增广矩阵17,054行、7,862,404 used NNZ；612通道 | watchdog 2,448.934s、进程树RSS峰2,783,928,320B、task VmSwap峰0；A6=4.4025e−9、凝聚残差=4.5730e−13、能量闭合差=1.5381e−12。按冻结规则接受为transition 3（accepted updates=3），但η_G/J∞仍远高于最终精度限值 |
| Round-3 h：60个标记根请求细化，审计形成600叶、p3/p4/p5=228/270/102 | 不运行PDE；新增独立FE DoF=71,294，含噪score上界1.74764e−6；p-up保守下界7.02689e−6 | p/h两候选计划及p转移合计watchdog 918.234s（h实体审计约599.030s为其子阶段）；本轮h跨网格转移和求解均not_run | 按冻结分数界严格剪枝本h候选，不是h Gate通过；至少一次完整真实h资格仍未完成 |
| Round-4 p-up：57个请求升阶、9个闭包强制升阶，180叶，p3/p4/p5/p6=21/61/82/16 | R/T/A_volume=0.258839644327/0.052155779229/0.689004576445；η_G=0.048336049703→0.009542819712；J∞=42271.5272→7475.0800，最大项为R00_s | 独立FE=19,435迹+34,224内部=53,659（较parent +10,451）；增广矩阵20,047行，operator NNZ used/allocated=10,274,139/12,846,443；factor NNZ=54,095,179，factor对象估算1,298,444,680 B；612通道 | 求解watchdog 3,704.762s、进程树RSS峰3,752,202,240B、task VmSwap峰0；A6=4.9789e−9、凝聚残差=5.1880e−13、能量闭合差=8.3844e−13。p得分下界3.71105e−6严格高于h4含噪上界5.74245e−7，故接受transition 4；最终精度仍未通过 |
| Round-4 h：57个标记根请求细化，31个材料闭包强制细化，审计形成796叶、p3/p4/p5/p6=408/270/109/9 | 不运行PDE；独立FE=53,339迹+74,058内部=127,397，较parent增加84,189；h得分上界5.74245e−7 | p/h计划watchdog 1,992.979s、进程树RSS峰2,258,251,776B、task VmSwap峰0；h跨网格转移和求解均not_run | h计划经实体闭包和资源审计，但按预冻结排名界被p4严格支配；不构成真实h Gate通过 |
| Round-5 p-up attempt1：transition4后的混合p5候选计算 | 在端口行准备到150/612模态时受控停止；没有完整候选场或结果记录 | 主控发起的性能停止，原因是严格零载荷单元仍做稠密投影；非数值失败 | 2,230.240s、进程树峰2,911,133,696B、task VmSwap峰0、后代清理；[停止与修复证据](records/sparse_zero_skip_component_v1.json) |
| Round-5 p-up attempt2：从transition4重新标记60格，53格可升、7格已p6；30格邻接闭包强制升阶；180叶，p4/p5/p6=51/82/47 | R/T/A_volume=0.254762604502/0.056767101216/0.688470294283；η_G=0.009542819712→0.003411538344；J∞=7475.0800→3407.0428，最大项仍为R00_s | 独立FE=23,874迹+46,338内部=70,212，较父增加16,553；612端口，凝聚矩阵24,486行；operator NNZ used/allocated=14,583,076/17,936,292，factor NNZ=72,608,080；factor对象估算1,742,789,816B不是进程树RSS | 求解watchdog 3150.040s、进程树RSS峰4,975,054,848B、task VmSwap峰0；A6=5.82775e−9、凝聚残差=5.40094e−13、闭合差=1.20648e−12；主控原始数组复算后接受transition5，最终精度未通过 |
| Round-5 h：60格请求细化、30格材料闭包强制细化，90根分裂形成810叶、30悬挂patch；p3/p4/p5/p6=168/278/299/65 | 仅计划/实体审计；FE=78,010迹+137,082内部=215,092，较父增加161,433；h含噪得分上界5.91695e−8，低于p实测保守下界3.69854e−7 | p/h计划及p转移watchdog合计3669.122s；p authority396.139s、转移236.344s，h authority3014.454s均为其嵌套阶段；h工作集67项超cache64 | 本h按冻结排名界剪枝，跨网格转移和PDE均not_run，不构成h资格通过；只有该路径确需执行才修容量；[计划、选择和成本证据](records/round5_independent_audit_v1.json) |
| Round-6 p-up：从transition5重新标记48格、12格闭包，无p6饱和；180叶，p4/p5/p6=21/82/77 | R/T/A_volume=0.251540795421/0.057013313685/0.691445890896；η_G=0.003411538344→0.000409698662；J∞=3407.04275→182.905872，witness R00_s | FE=27,361迹+56,598内部=83,959，Δ13,747；612端口，矩阵27,973行；NNZ used/allocated=18,441,921/22,760,057；MUMPS factor NNZ92,517,035、因子对象估算2,220,632,632B非树RSS | PDE watchdog2918.359s、树RSS峰5,598,105,600B、task swap0；A6=7.66816e−9、cond=5.56287e−13、closure=2.59526e−12；主控独立复算后接受transition6，最终精度仍未过 |
| Round-7 p-up：54标记中52实升、2已p6，无额外p闭包；180叶，p5/p6=72/108 | R/T/A_volume=.251411251282/.057119092082/.691469656635；η_G=.000409698662→.000194591143；J∞=182.905872→54.874993，witness R00_s | FE=31,677迹+65,880内部=97,557，Δ13,598；612端口/实际32,289行；NNZ used/allocated=23,873,213/28,987,493；MUMPS factor120,398,039项/对象估算2,889,811,256B非RSS | PDE2740.413s/树RSS峰6,623,186,944B/taskVmSwap0；A6=8.43966e−9、cond5.46995e−13、closure5.59885e−13；主控原数组审核后接受transition7，最终精度仍未过 |
| Round-7 h计划：54请求+25材料闭包，79根分裂、733叶、107悬挂patch；p4/p5/p6=168/418/147 | h跨网格转移与PDE均not_run，不能称真实h资格通过 | qualified flattened authority FE=89,114迹+184,614内部=273,728，Δ189,769；broken301,502不是独立FE | authority5380.287s；新增84miss，p/h联合总110miss/110键、cache128；含噪score上界2.206824196e−9低于p实测保守下界1.515071040e−8，按冻结界剪枝not_run，不授予真实h资格 |
| Round-8 p计划：31格p5→p6，无饱和或强制p闭包；180叶p5/p6=41/139 | PDE/功率/η/J尚未运行，不能填为通过 | 实际FE=34,335迹+72,390内部=106,725，Δ9,168；预期full612时增广34,947行 | authority835.046s，cache19miss/161hit；direct不使用转移初值，显式skip/pass null/wall null |
| Round-8 h计划：31请求+17材料闭包，48根八分，516叶/56悬挂patch；p5/p6=289/227 | 跨网格转移/PDE均not_run，尚不能剪枝或接受 | qualified flattened authority FE=80,222迹+171,510内部=251,732，Δ154,175；broken271,166非独立FE | authority2675.266s，新增39miss；p/h总58miss=58keys，含噪score上界1.321091630e−9；不据此授予h资格 |

Round-5延续相同Y6_1选择参考及同一q8公共积分，共589,824点，域体积350,000 nm³。J∞表示把每个输出误差除以各自允许值后取最大值，只有J∞≤1才表示全部输出达标；本轮3407.04仍远高于1。候选的体吸收绝对误差由0.002512950337增至0.003047232499，虽然电磁场差与最大输出误差下降，也不能称所有物理量单调改善。按事前冻结的G下降、最大J不恶化以及实际新增FE得分规则，主控在独立重算完整数组/612通道后接受transition5。详细各分量见[transition5](records/round5_selection_transition5_v1.json)。

同一LU残差校正只复用原矩阵与因子做一次回代，不改变离散模型。其绝对残差范数为2.8561565780531e−9→4.639877230557785e−13；除同一RHS范数后，相对残差为3.3672340071620075e−9→5.470131616677909e−13。恢复后的凝聚相对残差5.400944605698828e−13另列，最终还要通过独立完整active方程A6=5.82775188872619e−9。上述三种口径不能混称。预验证checkpoint与最终storage的11个共享数组逐位相同；原始JSON/NPZ及资源样本由[Round-5独立审计](records/round5_independent_audit_v1.json)绑定hash，属于本地非CI复算。

截至transition5已有7条完整模型网格/p-map lineage、10次实际full-scale solver attempts（包含同计划失败/受控停止/重试），不等于10个成功模型。累计26条终态watchdog的wall小计为29,736.18805150129s；Round-5计划、attempt1性能停止、attempt2成功求解、q8比较分别为3669.122262/2230.240470/3150.039591/276.609321s。这不是完整campaign成本，未覆盖未监控tests/工作及导入参考生成，组件优化的各次测试费用继续单列于[原组件记录](records/sparse_zero_skip_component_v1.json)。所有计算复用了既有JIT缓存，不称为隔离冷启动收益；70,212与对照推导237,600的差只说明候选规模，不能证明等精度资源优势。

Round-5求解和比较的源码HEAD均为 `366591b226ee69172fa7704224a66b814888070e`。不可变的pre-run archive只列40个依赖，漏列必需的 `src/adaptivity/variable_p_transfer.py`；未将该archive改写为完整。该文件在原PDE仍运行时于2026-10-23T06:32:38.630739327Z真实补充采集，与clean HEAD逐字节一致，明确不是pre-run采集。补充manifest、源文件hash及19输入/40已列源码的posthash复核均见[审计记录](records/round5_independent_audit_v1.json)。运行期间只交接执行者，未重启计算；watchdog原有“WSL-global”文本保留，实际全机swap增量是native Linux host诊断，不能替代任务进程树swap口径。


Round-6从transition5的实际场重新分配计算量，θ=.5的最小标记为48格：贡献最大的前47格只捕获0.499772833，48格捕获0.508143347；其中p4为18格、p5为30格，无p6饱和。误差较大的区域已移到z=90–130 nm，不能沿用上一轮的固定标记。轻量预览使用实际degree/entity map计工作集，没有构造数值参考空间；其cache前后均为0miss/0hit/0size。两次仅脚本准备失败及第三次成功的watchdog成本8.592/10.759/16.852s均保留，合计36.203s。

| Round-6计划期候选（p后续已求解，h未求解） | 实际空间与约束 | 实测阶段成本及边界 |
|---|---|---|
| p-up：48格升阶、12格闭包升阶 | 180叶，p4/p5/p6=21/82/77；FE=27,361迹+56,598内部=83,959，Δ13,747；后续实际含612端口的凝聚系统为27,973行 | authority1839.210s、父场转移1401.189s；p6相对恢复差3.24430e−14、约束差2.75028e−15；cache authority35miss、转移1miss；转移已发生但不是direct warm start，不重复计入未来PDE成本 |
| h-refine：48请求+1周期闭包根分裂 | 523叶、55悬挂patch，p4/p5/p6=184/292/47；flattened FE=60,020迹+111,102内部=171,122，Δ100,910；迹数来自既有合格authority，主控另核对叶/阶继承及内部公式 | authority1280.128s、6新miss；h跨网格转移与PDE均not_run，不能称真实h Gate通过 |

正式两plan与预览字节完全一致，source冻结为a0fdfef53ffea06cb68816dcf65e5afe8a6dd0b4；16输入及47个已列源码的pre/post hash一致，明确包含variable_p_transfer，仍只声明listed scope。正式plan watchdog4536.816s、同时进程树RSS峰3,002,015,744B、任务VmSwap峰0，exit0/后代清理；原20–40min预测被实测超出。native host全机pswpin增加33页、pswpout为0，job归因UNRESOLVED，不能把任务VmSwap0写成全机swap无活动。p工作集36、h32及父/候选联合42键均可容纳于64，但容量合适不保证构造快。R5 h的67>64只证明容量风险；63miss及主机竞争不能单独证明cache颠簸或解释全部3014s。第6轮h候选的含噪分数上界约3.38977950934508e−8；p实测η=0.000409698662低于条件界0.0029364571961372436且其余冻结门通过，保守得分下界2.17702154890150e−7严格更高。主控据此接受transition6，并剪枝该h候选；不授予h数值资格。

直接因子后端指把同一个稀疏方程直接消元的具体实现。现有入口可显式选择常规MUMPS in-core，目的是评估未来更大矩阵的分解成本；默认配置保持不变。它只可能改善分解，不会消除已测1839s空间构造或1401s转移。新增组件在同一36格真实mixed p4/p5空间上固定比较PETSc LU与MUMPS，两个后端均自然启用同一same-LU校正，没有人工扰动，也不做BLR/OOC或预条件器扫描。

| 36格组件后端 | R / T / A_volume（离散组件结果） | 独立残差与恢复残差 | 成本与范围 |
|---|---|---|---|
| PETSc LU；live/summary均petsc | 0.999316430849 / 0.000193185495 / 0.000490383656 | A6=1.7145329208483104e−11；cond=1.2375293051405681e−14；重算1−R−T−Av=1.8030021919912542e−13 | 本侧572.636s，先运行；不是正式Task43精度结果 |
| MUMPS；live/summary均mumps | 0.999316430849 / 0.000193185495 / 0.000490383656 | A6=1.7146857037646924e−11；cond=1.1680467391717958e−14；闭合差1.8041124150158794e−13 | 本侧478.365s，后运行；共享mesh/JIT，不能取两侧生命周期比声称全流程加速 |

两侧11项mesh/DoF/CSR矩阵/RHS数组逐位相同，实际FE=4,230迹+6,264内部=10,494，612端口；凝聚矩阵4,842行、2,348,388 used NNZ。完整612功率最大绝对差1.14925e−17，R总差1.11022e−16、Av差1.73472e−18；四组复边界幅值固定尺度差均≤3.14519e−16，完整系数差范数2.54771e−13、相对差4.20350e−15。q8/q10由实际网格积分得到V约350000 nm³；E、curl/k0、物理H和G的固定入射尺度差均约2.1e−16，全部低于冻结1e−8门。弱模态使用max(参考组范数,1单位入射模态)作分母；物理场使用实际积分V建立共同入射尺度，原始相对差也保留。系数的1 coefficient-unit仅为相同代码基底的代数地板，不代表物理场尺度。逐通道、逐系数、全体采样和原始范数保留在ignored数组，不只报告最大值。

原pair的PDE与raw输出完成后，末尾JSON因numpy.bool_序列化失败：pytest1 failed/2 deselected，watchdog仍为WORKER_FAILED，1064.968s、同时树RSS峰1,731,317,760B、task swap0/global增量0、后代清理。修改前49个listed source posthash全部一致；唯一后续修复为floor_active的bool(...)包装，数值段未变。未补写原比较JSON、未覆盖原失败，也未重跑PDE；从保存数组重放同一fixture的比较语句，独立输出目录通过44门，恢复watchdog9.856s、RSS425,197,568B。主控用独立NumPy/stdlib从完整raw重算矩阵/场/模态、A6及闭合通过。本次最终本地非重型Task43 suite为25 passed/3个显式opt-in物理fixture skipped（4.80s），CLI映射、Ruff及compileall通过，不称CI或原pytest通过。原6–15min组件估计也被1064.968s实测超出。

截至后端组件资格化、正式PDE尚未启动的历史检查点，accepted updates为5，完整模型lineage仍为7、full-scale solver attempts仍为10；新增两plan不占完整模型数，36格配对是另记的组件。累计32条终态watchdog wall小计35,384.03147977451s，包含全部三次预览、正式plan、原pair失败和JSON恢复；不是全campaign成本，未纳入watchdog的tests/工作及导入参考生成仍另外保留。Y6_1历史MUMPS生命周期551.736s不能与R5的PETSc LU setup1000s当成同问题加速比；后续PDE预测当时纳入plan authority1839s作为校准；实际PDE独立authority没有另行拆计，不能把该校准冒充本次实测。


截至第6轮的历史检查点，主控独立复算原始A6/cond/closure、全部612模态、589824点原数组及J见证、11个checkpoint共享数组和资源样本后接受第6次更新。该历史轮通过中间接受规则，当时最终误差如下（均对固定Y6_1离散参考，并非连续真误差）：

| 第6轮历史量及含义 | 实测差异 | 冻结最终限值 | 状态 |
|---|---:|---:|---|
| 总反射R绝对差 | 1.863292399e−4 | 1e−5 | 未达，约18.63倍 |
| 总透射T绝对差 | 1.146933874e−4 | 1e−5 | 未达，约11.47倍 |
| 体吸收A_volume绝对差 | 7.163588595e−5 | 1e−5 | 未达，约7.16倍 |
| 零级s反射R00_s绝对差 | 1.829058719e−4 | 1e−6 | 未达，当前最大归一项182.91 |
| 完整电场与旋度G的固定入射尺度差η_G | 4.096986620e−4 | 1e−4 | 未达，约4.10倍 |

本轮固定MUMPS in-core，requested、live KSP和summary三处一致。自然same-LU校正的绝对残差2.8100337858552366e−10→5.438276283968267e−13，除RHS后相对2.9131601627943403e−10→5.637857418110685e−13；恢复后凝聚相对残差5.562866590119647e−13另列，独立A6为7.396707891886114e−9/0.9645998259017158=7.668162167634242e−9。这些口径不能混称。actualFE83,959及完整612均由原字段复核；checkpoint与storage的11个共享数组逐位一致。

PDE source为clean b5fd4c821eac858c60f266926eccd14850d4f34c，49个pre-run已列源码（包含variable_p_transfer及比较器）与26个输入posthash全匹配，仍只声明listed scope；比较另有42个输入posthash通过。PDE/比较watchdog分别2918.359404/216.733807s，树RSS峰分别5,598,105,600/1,139,601,408B，均task VmSwap0、native host全机增量0、exit0/后代清理；旧WSL-global文本原样保存并注明native范围。原60–100min PDE预测比本次实测偏高，原4–7min比较预测下界也略偏高，均不回写成正确预测。

本次base_matrix_assembly1588.027638s包含空间/约束准备；嵌套total_build67.299108s、preallocation1.060468s和raw metadata0.027836s不能相加作独立成本。端口向量417.420670s、factor setup70.234884s、恢复20.617704s、field capture17.314257s、独立A6727.930542s均保留原计时。PDE没有单独计纯authority时间，plan的1839.210s仅是先前预测校准。已发生的p-transfer1401.189s完整保留，但直接解未使用它作初值，不能重复加入PDE。R5与R6的p-map、矩阵规模及费用构成均不同，不从setup或总时长差推出同问题后端加速。

截至第6轮求解及比较的历史检查点，accepted updates=6，8条完整模型lineage/11次full-scale solver attempts（不是11个成功模型）；34条终态watchdog wall小计38,519.124690737575s。该小计包括被监控的组件、失败和恢复，不覆盖未监控测试/工作及导入参考生成。R5性能停止、零载荷修复、原40文件snapshot缺口和真实运行中补充、未知sender的旧h停止、两次预览失败及backend JSON失败均保留。83,959与uniform-p6推导237,600的规模差仍不能证明等精度资源优势。详见[transition6](records/round6_selection_transition6_v1.json)与[独立审计](records/round6_independent_audit_v1.json)。后续已完成以下第7轮准备；真实h、最终holdout/control、q/R14、侧壁、终点加严和同精度成本仍未关闭。

## 第7轮：保留真实空间审计，跳过直接解未使用的转移

父场转移把已有有限元解改写到新候选空间中，先前用于核对升阶时的场恢复，但直接消元求解器并未把该场用作初值。因此现有plan runner新增显式 `--skip-parent-transfer`，默认仍保留旧行为；本轮仅跳过这项重复资格工作。父storage hash、真实marking、闭包、空间约束和独立FE计数仍必须通过，未运行的转移记为 `not_run_direct_solve_does_not_use_initial_guess`、pass null、wall null、cost not_incurred，不是PASS或实测零秒。历史R2/R6转移资格与R6已付1401.189s成本保留，h跨网格转移仍未资格化。

| 第7轮准备项 | 实测／派生结果 | 范围与限制 |
|---|---|---|
| 真实标记 | θ=.5最少54格捕获G²的0.502880556，前53格0.495718189；父p4/p5/p6=21/31/2，分布z−10..0、0..30、60..90为21/12/21 | 主控从原589824点另算一致；52格升阶、2格饱和，无伪升阶或额外p闭包 |
| 参考空间缓存 | p/h含uniform-p6工作集26/88，交集4、联合110；原64容量不足，唯一共享容量常量扩为128，其他helper32不变 | 缓存复用同一种局部多项式基及映射，减少被逐出后重复构造的风险；保留更多内存，不改变方程/离散。三矩阵854,068,544B仅对象体积部分账，非RSS上界 |
| 最小检查 | transfer策略最终serial2pass（9.83s）；MPI2每rank2skip（2.32s）；原四项转移测试4pass（108.90s）；ABI、compileall、Ruff错误级通过 | 新CLI测试的MPI1 guard经review补入单独提交；缓存模块完整Ruff与基线同3项旧发现。无额外PDE anchor、不称CI |
| 正式plan资源 | watchdog6625.771690s=110.43min，5408原采样复算；同时树RSS峰5,936,697,344B=5.53GiB，task VmSwap0、exit0/后代清理 | native host全机swapin+10页/out0，归因UNRESOLVED；保留原WSL-global标签并说明native诊断口径 |
| 预测偏差 | p authority1223.016s在20–40min内；h5380.287s=89.67min超过25–75min；总110.43min在45–115min内 | 7200s门未延长，约5979s已报剩余时间与资源；110次miss恰等于110联合键，不据耗时宣称cache颠簸或诊断未知内部子阶段 |
| 失败与全部成本 | 临时preview父selection文件名错误保留WORKER_FAILED8.618s；修正attempt2为21.775s，key补测13.324s。首次策略Ruff局部失败及启动身份helper误匹配原JSON均保留 | 累计38条终态watchdog小计45,188.612906735856s，仅已列监控成本；未监控tests/工作和导入参考生成不在此小计，不能当全campaign费用 |

正式plan source为clean `b06e834e4de7ce8a0c65dd3017efd02da3cc4cb0`，50个pre-run已列源码（含variable_p_transfer）及64输入posthash全匹配，仍只声明listed scope；p/h计划与轻量预览字节相同。主控独立核对几何、阶次继承、内部计数和资源；h迹89,114采用合格flattened authority记录，不宣称另一套迹实现。原始审计、数组身份、两项小修提交及测试日志统一绑定在[第7轮准备compact](records/round7_plan_preparation_audit_v1.json)。

第7轮p实测η=.000194591143低于事前条件界.000370602108，全部冻结残差/G噪声/J门通过；保守得分下界1.51507103982934e−8严格大于h含噪上界2.20682419577817e−9。主控从完整q8总场E/curl/G、612模态和11checkpoint数组独立复核，并用总场误差及共同入射地板给scattered分量建立低于R00_s见证的上界，据此确认完整J最大值，正式接受transition7；未宣称另重算全部scattered分项精确范数。h仅按界剪枝，仍没有跨网格转移或PDE资格。R7准备compact保持当时PDE尚未运行的历史状态，当前选择与独立审计另见下文。


第7轮求解与冻结比较已经完成；选择参考仍为Y6_1，未读取holdout/control场用于本轮标记或排序，历史metadata已审阅，不作全局盲法。当前最终精度的具体缺口是：

| 第7轮量及含义 | 实测差异 | 最终限值 | 状态 |
|---|---:|---:|---|
| 总反射R绝对差 | 5.678510090e−5 | 1e−5 | 未达，约5.68倍 |
| 总透射T绝对差 | 8.914990378e−6 | 1e−5 | 本项已过，不能替代全部验收 |
| 体吸收A_volume绝对差 | 4.787014710e−5 | 1e−5 | 未达，约4.79倍 |
| 零级s反射R00_s绝对差 | 5.487499313e−5 | 1e−6 | 未达，当前J∞见证54.875 |
| G固定入射尺度差 | 1.945911432e−4 | 1e−4 | 未达，约1.95倍；部分E/H和同偏振复幅也未达 |

本轮requested/live/summary均为MUMPS。自然same-LU绝对残差9.213054112855192e−11→5.374871264352757e−13，相对RHS为9.551167090708054e−11→5.572125476311671e−13；恢复后cond=5.469946697245848e−13另计。独立A6原范数8.140894831109839e−9/RHS.9645998259017159=8.439660274144942e−9，通过task1e−6与诊断1e−8；能量闭合差5.598854713184664e−13。record、完整612和checkpoint/final storage的11个共享数组由主控另算通过，checkpoint与storage完整文件SHA也一致。

PDE/比较watchdog为2740.412610/239.528684s，2206/193条原采样、同时树RSS峰6,623,186,944/1,139,380,224B，均taskVmSwap0、exit0/后代清理。PDE native全机swapin+3页/out0仍归因UNRESOLVED；比较全机增量0；原WSL-global文本保留并注明native诊断。50个pre-run已列源码及30个PDE输入、49个比较输入posthash匹配，source clean e53220aae5dff0af1996735254513c161eaa32f1，只声明listed scope。

base assembly1205.705467s包括新进程空间/约束准备；plan1223.015709s仅校准，不额外叠加。嵌套total_build70.975482/preallocation1.165401/raw metadata.024957s不相加；port vector657.165467s、factor setup62.240171s、内部恢复18.305517s、field capture13.814926s、独立A6692.990341s另记。总45.67min在45–85min预测内，setup与A6低于各自阶段预测下界，原预测保留；R6/R7的p-map/矩阵不同，不作同问题后端加速比。p转移仍not_run/pass null，旧1401.189s成本保留。

当前accepted updates=7，9条完整模型lineage/12次full-scale attempts，16份正式p/h计划另记；第8轮仅完成空间审计。42条终态watchdog wall小计51,709.340370008256s，仅已列监控成本，包含受监控组件/失败/恢复，未覆盖未监控tests/工作和导入参考生成；全部历史负项保留。候选106,725与uniform-p6推导237,600的规模差不构成等精度收益。已接受场及hash见[transition7](records/round7_selection_transition7_v1.json)和[独立审计](records/round7_independent_audit_v1.json)，下一判断见[第8轮准备compact](records/round8_plan_preparation_audit_v1.json)。真实h、最终holdout/control、q/R14、侧壁、终点加严、迭代与同精度成本仍未关闭。

第8轮用accepted7真实场重新标记31格（z120–130有30格，z30–60有1格），捕获G²的.504682243901，前30格仅.489098353029；不是复用上轮标记。metadata预览15.284s，reference cache前后0miss/0size；实际degree-map工作集p19/h54、交15/并58，含uniform p6，现容量128足够，无源码修改。三矩阵shape部分体积522,009,312B不是RSS或内存上界。

第8轮正式plan source clean `ca437b83b3e9a5a13fd257da403ddcd312ca202b`，50个listed源码/35输入posthash通过，p/h计划与preview字节相同。全队列3525.502383s/2842采样，同时树RSS峰4,409,544,704B、taskVmSwap0、exit0清理；native全机swapin+10页/out0归因UNRESOLVED，旧WSL-global标签保留。主控另审几何/阶次继承/内部计数及资源，h迹80,222采用合格flattened authority，未称第二套独立实现。p13.917min低于15–35min预测下沿，h44.588min/全58.758min在30–90/45–125min内；58miss只确认实际键计数，不证明缓存加速。原7200s草稿未启动、原样保留；主控按预测125min+10min余量，在此次启动前登记8100s门，全程未延长，也未放宽数值门。

若第8轮p候选实测η严格低于.0001733912163613156且其余全部冻结残差/正ΔFE/G噪声/J门通过，才可严格支配第8轮h含噪上界；当前未有p结果。主控已审唯一p-up的固定MUMPS/自然same-LU/full612/q15q28草稿，预计40–85min/树RSS6–14GiB只是规划，PDE门为7200s/192GiB（不同于本轮plan的事前8100s）。提交准备证据后须新host/ABI/源码和输入快照；硬门通过可接既有parent7/Y6_1冻结q8比较，再交主控原数组审核，不自动接受transition8，不启动h/下一轮或读取holdout/control。

current的R00_s=0.807460398697、R00_p=1.23971e−26，R00_total为两者之和。比较器在所有三张实际网格断点并集上用张量 Gauss 规则重新采样原始高阶电场和旋度；q8 有589,824点，q10 有1,152,000点，两者积分体积均为350,000 nm³。q8/q10 的每单元 G² 贡献最大绝对差为1.64e−11，46个标记完全相同，表明这次标记对积分阶数稳定。此处的 G 衡量电场及其旋度差异，用固定入射场范数处理近零分母；它用于分配下一轮计算，不表示已知连续真误差。

| 比较对象（均以当前场/selection Y6_1 为主） | G 差范数 / 固定入射尺度相对差 | 电场总场 / 磁场 / 旋度相对差（固定尺度） | 612 通道及标记结果 |
|---|---:|---:|---|
| current 对 Y6_1，q8 与 q10 | 358.1505046 / 0.42807173；q8/q10差约3.2e−16 | E=0.42795664；H=0.42818679；curl(E)/k0=0.42818679 | 最大单通道功率差0.5561381（top,0,0,s）；46/180格捕获G²的0.5011251 |
| 校准 Y6_2 对 Y6_1，q8 与 q10 | 0.0038018494 / 4.54408e−6 | E=9.33331e−7；H=6.35816e−6；curl(E)/k0=6.35816e−6 | 最大逐通道功率差4.17448e−8（top,0,0,s） |

两参考的全域 G 差远小于当前相对 selection 参考的场差，因此可用于首轮选择；该参考差只是一次校准观测，不是完整的不确定度模型。逐通道功率使用完整612个有序模态，未拟合全局相位。原始场数组和逐单元贡献的hash、标记 IDs与全量字段见[公共比较记录](records/reference_comparison_v1.json)。Y5_1未读取，最终6×10×6 p6对照不参与标记。四侧壁单侧迹、独立重算参考完整残差及最终精度验收仍未完成。

p-up 将有限参考差降低，但相对场及边界量仍远高于最终 `1e−4` 精度限值。交叉极化幅值略有恶化：`top_p` 固定尺度相对误差从1.9256e−4升至2.3289e−4，`bottom_p` 从3.2090e−4升至4.0044e−4；不应说全部观测都改善。完整612通道、真实独立DoF和方程硬门由比较器从原始字段重算通过。冻结分数下界为2.9678396669976532e−5。h计划与求解路径的实际新增独立FE DoF为32,115，即使假设其 `eta_G=0`，加入同一G噪声后得分上界也仅1.3329622224401209e−5；因此p-up在冻结的单位DoF排名上严格胜出，已接受为transition 1，accepted updates=1。该选择只表示第一轮中间更新，不是最终精度或成本优势。精简判定及证据哈希见[transition 1记录](records/round1_selection_transition1_v1.json)。

h算例完成矩阵分解、回代、旧求解器显式残差及其R/T输出后，watchdog记录受控停止并清理全部子进程。其progress记录分解setup 764.040s、solve 0.665s和旧残差7.4766e−10；这些不能替代Task43独立A6。当前目录没有 `candidate_recovered_solution_storage.npz` 或 `task43_round1_candidate_record.json`，端口记录的 `A_volume_total` 为空，因此无法从R/T或模态数据恢复完整场或计算 `eta_G`、`J_infinity`。h资格状态为unknown/controlled_stop，不能称h Gate通过或数值失败。watchdog只记录收到SIGTERM的时间和整树范围，不存发送者身份；没有证据能把停止归因于用户或工具会话清理。其原始hash索引与资源/失败成本列在上述compact记录中。

主控还从保存的 q8/q10 原始场数组独立重算 G 差及标记；数值与该记录一致。这是审阅侧复算，不是 CI 测试。

Round-2 p-up 首次求解完成内部有限元场恢复后，在进入 live observer 时因原 full-active residual 未过 1e−9 preflight 而失败；Task43 完整场 checkpoint/采样未写出，独立 A6 未运行。保留该失败和资源记录。之后同一计划显式启用 same-LU 回代：只复用原矩阵、右端和 LU 因子，true residual 有限且严格下降后才更新原解向量；重试完成完整 field capture、独立 A6 和冻结比较，并已接受为 transition 2。首轮 h 的 watchdog 原始分类仍为 `USER_CONTROLLED_STOP`；用户明确表示没有手动停止，停止发送方仍未知，不把记录归因于用户。失败、修正、比较和成本证据见[组件记录](records/same_lu_residual_correction_component_v1.json)与[transition 2记录](records/round2_selection_transition2_v1.json)。

本次current基于 `8fe6793e0a5e0689a5435ddf209d095b75b3bd0f` 加已归档dirty源码；完整35文件快照、命令/环境、分阶段时间及原始artifact哈希见[轻量记录](records/initial_current_and_reference_restore_v1.json)。使用既有JIT缓存，395.323s不是隔离冷缓存成本。当前已有七次p-up中间接受（accepted updates=7），η_G降至0.000194591143、J∞降至54.874993，最终精度仍未通过。h1保持unknown/controlled_stop，用户未发停止、sender未知；h2–h7均未完整求解，按排名界剪枝不构成h数值资格。Y5_1与最终6×10×6 uniform-p6对照未进入选择。第7轮p已通过固定MUMPS求解及冻结比较并由主控接受；后续仅授权第8轮轻量预览，PDE待具体放行。

Round-4候选的原始记录、计划/转移审计、全部612通道和比较数组的主控独立复算见[transition 4选择记录](records/round4_selection_transition4_v1.json)及[Round-4合并审计](records/round4_independent_audit_v1.json)。固定参考为Y6_1、校准为Y6_2；Y5_1 holdout和6×10×6 p6对照场未被读取用于该轮选择；历史上部分参考metadata已经审阅，不作全局盲法声明。round4 p候选的G误差下降超过预冻结噪声，完整J∞没有恶化；它的保守单位FE得分下界3.71105e−6高于h计划上界5.74245e−7，因此接受为transition 4。h4形成796叶、127,397独立FE DoF，但此次没有求解或跨网格转移，不能称真实h Gate通过。

Round-4 还验证了有限缓存容量修复：旧32项上限无法容纳34种单元阶次映射及uniform-p6映射；本地缓存上限改为64后，35项的p工作集与56项的h工作集均可容纳。重复同一p计划时，父场转移的缓存miss从28降到1，转移时间从1,171.160s降到255.146s；计划构造本身在两次实测间更慢，不能据此声称整体求解或整个campaign加速。缓存修复前的Round-4 plan尝试因实测重复构造受控停止，第二次仅因外层shell缺少 `python` 命令而未启动worker；两种失败均保留。缓存修复的4项定向测试用时51.13s，详细成本与哈希绑定在上面的审计记录中。

Round-5 p-up attempt1在准备端口行期间由主控受控停止：耗时2,230.240s、进程树RSS峰2,911,133,696 B、任务进程swap峰0、全部后代清理；只准备到150/612模态，没有候选场/official记录。原因是旧端口投影还对严格零载荷单元执行稠密局部变换。当前修复只在一个单元全部882个复数载荷都恰为零时跳过该次变换；任何非零载荷（包括1e−100缩放）仍完整投影，不使用截断阈值。真实顶/底端口载荷串行、MPI2均与测试保留的逐单元全投影结果逐元素一致；36单元真实 A6 组件与历史attempt2的独立动作、模态幅值和体吸收身份通过主控逐项复核。串行/MPI测试、历史失败和warm诊断成本均列在[稀疏零投影组件记录](records/sparse_zero_skip_component_v1.json)。这种小fixture的warm耗时只作局部性能诊断，不外推整场求解加速；A6组件也不是正式起点/精度结果。

截至transition 4，已有6条完整模型网格/p-map case lineage：current、Round-1 p/h、Round-2 p、Round-3 p、Round-4 p；共8次实际 full-scale solver attempts，含current另一次same-LU加严以及Round-2同计划残差失败/修正重试。这些attempt不是8个成功official结果。task.md §9的8–12是目标、16是完整PDE模型case规划预算；若规划超过16，先说明新增判断所需的最少case，不把16当无条件硬停。四轮审计的8个不同p/h候选计划是plan-only，不占该预算。另有3个36单元组件锚点、组件测试与Y6_1/Y6_2既有场恢复，均单独记账，不算完整模型case。按未改写的冻结watchdog inventory v1加上Round-4四条终态watchdog，累计22条watchdog wall小计为20,410.176s；该值不含未监控的参考恢复、一般组件工作及其它规划/后处理，不是campaign全部成本。Round-4计划、求解及比较watchdog合计5,913.217s；受控停止1,712.273s另列，第二次无worker包装器失败2.7s与缓存定向测试51.13s也另列。Round-5 attempt1的2,230.240s为后续性能受控停止，单独记账、不改写冻结inventory v1小计。累计口径与所有例外见[Round-4合并审计](records/round4_independent_audit_v1.json)和[稀疏零投影组件记录](records/sparse_zero_skip_component_v1.json)。

启动包装器曾因可选版本字段及在watchdog父进程提前初始化MPI而退出，均发生在PDE worker启动前；失败日志保留。Y6_1首次恢复误用了Task43简化模态序列化，历史SHA检查失败；改用历史原函数后exact hash通过，未改预期值或覆盖首试证据。后续审核另发现MPI采样的非root提前返回、未参与最后错误广播；已局部修复并通过MPI2成功及域外点集体失败测试。本次current为MPI1，原数据不受该分布式控制流修正影响。

新增的独立小组件把两个相邻单元中的一侧分成八块，得到 9 个叶单元；另行建立把接口切分贯穿到另一侧的 12 单元网格。两者的离散空间与自由度不同，检查采用双方均能表示的已知复数多项式场，右端由原始形式独立积分得到，再比较各自恢复场与已知场，不能解释为任意散射解在两网格上都严格相等。

| mixed p 组件 | 9 叶单元独立 FE DoF | 12 单元独立 FE DoF | 两网格电场相对 L2 差 | 两网格旋度相对 L2 差 | 判定 |
|---|---:|---:|---:|---:|---|
| p3/p4 | 1082 | 1782 | 1.3775×10⁻¹¹ | 9.7871×10⁻¹³ | 小于 1e−8 组件门槛 |
| p4/p5 | 2320 | 3649 | 3.3996×10⁻¹¹ | 9.5386×10⁻¹³ | 小于 1e−8 组件门槛 |

两组原始单元作用的一致性指标均约 1e−14，但其分母是未装配的逐单元作用及右端范数，因此只作为组件一致性指标，不与正式模型独立组装右端归一化的 A6 混称。逐网格对已知场的误差、原始残差范数、日志及源码身份见[9↔12 组件证据](records/mixed_hp_9_to_12_component_v1.json)。

后续选择采用的 G 范数同时衡量电场大小和空间旋转变化，让局部较快变化也能进入网格标记；旋度项先除以波数，以免直接相加不同量纲。它是两个离散场之间的距离，不是已知的连续真误差。为避免弱散射场造成无意义的巨大相对差，归一化还保留固定入射场尺度：本域体积为 350000 nm³，单位入射平面波的电场 L2 范数平方为 350000，G 范数平方为 700000。散射场从总场减去同一解析平面空气/基底背景；共同积分取所有比较网格的断点并集，先用每方向 8 点 Gauss，再以 10 点检查积分扰动，代价是额外采样和积分工作。指标、容差、完整模态分组与四侧壁双侧位置均已写入[比较合同](records/comparison_contract_v1.json)，未运行项仍未获资格。

## 36 单元空细化同阶与 MPI 锚点（G1）

三个算例使用相同的 phi90、13.5 nm 模型和边界拟合网格。它们只相差有限元实现或 MPI 进程数：原生 p3/`standard_full` 给出基准；空 h 代表“保持原网格、不分小单元”，在 p6 载体上求解 active p3；最后把同一 active-p3 算例改为 MPI2。这样可检查新 active 空间是否复现原生 p3，并检查分布式划分是否改变结果。完整比较在共同的 q8/q10 积分点上核对电场、旋度、电场推得的磁场，并逐项检查 612 个有序复模态和功率。

| 算例 | 实际空间和求解方式 | DoF/矩阵口径 | 残差与耗时 |
|---|---|---|---|
| 原生 p3 / MPI1 | 真正 p3 N1curl、`standard_full`，CPU1 | 3540 个有限元存储行含 462 个周期从属行；独立 FE 为 3078；含 612 模态的增广矩阵 4152 行、1,048,424 NNZ | 显式完整 `Ax−b` 相对残差 7.5466×10⁻¹³；runner wall 115.70 s |
| 空 h active-p3 / MPI1 | p6 载体，36 个叶单元全部 active p3，无 h 标记、无悬挂面 | 独立 active FE 为 trace 1782 + cell interior 1296 = 3078；加端口为 3690 行；消去 cell interiors 后矩阵 2394 行、547,386 NNZ | 凝聚 trace 相对残差和旧 full-active 变换残差均 1.2281×10⁻¹²；独立原方程 A6/RHS 2.1429×10⁻¹²；runner wall 280.43 s |
| 空 h active-p3 / MPI2 | 与上一行相同的网格和 active 空间；rank affinity 为 Linux CPU1/29 | 独立 FE 与增广/凝聚行数同上一行；两 rank 历史 RSS 峰值合计上界 1170.0 MiB（不是进程树峰值） | 凝聚 trace 相对残差和旧 full-active 变换残差均 1.3528×10⁻¹⁴；独立原方程 A6/RHS 1.7762×10⁻¹²；runner wall 173.97 s |

两种 p3 空间在相同 36 单元网格上的 q10 电场与磁场相对差分别为 7.7927×10⁻¹³ 和 8.4190×10⁻¹³；固定单位入射尺度下的 G 差为 3.5442×10⁻¹⁵。MPI2 对 MPI1 的 q10 电场/磁场相对差为 6.3581×10⁻¹³ / 4.6890×10⁻¹³。两组比较均核对全部 612 通道并通过 1e−8 Gate。近零 p 偏振通道须同时报告两种尺度：active MPI1 对 native 的 top-p 原始相对幅值差为 1.0730×10⁻⁹，使用固定单位模态尺度后为 4.2345×10⁻¹⁵；本记录保留二者，不能只挑较小者。R00_s、R00_p、R00_total、总 R/T 和 A_volume 均在合同容差内；最大单通道功率差对 serial/native 为 4.4539×10⁻¹⁶，对 MPI2/MPI1 为 3.3307×10⁻¹⁶。独立复核者还从原始 q8/q10 NPZ 与 612 通道 JSON 重算，结果通过；该手工复核不是 CI。

DoF 数必须区分“存储行”“独立有限元自由度”和“凝聚后矩阵行”。原生 p3 的 3540 存储行中 462 行由周期条件关联，所以独立 FE 为 3078。active p3 用 1782 个独立迹自由度和 1296 个单元内部自由度构成同一个 3078 维 FE 空间；另有 612 个端口未知量。凝聚只把内部未知量从全局矩阵中消去，求解后仍会恢复，所以 2394 个矩阵行不表示 active FE 只有 2394 个自由度。三个结果均标记为 `numerical_sanity_only`；runner 的 `official_result=true` 只表示本算例自身数值 Gate 通过，不表示 Task43 精度或自适应目标通过。

复现和逐字段证据见[三锚点 compact record](records/h100_anchor_triplet_v1.json)，原始 solver records、q8/q10 场、模态 JSON、日志和源码快照按其中路径及 SHA256 绑定；全部大文件保留在 ignored `benchmarks/artifacts/task43/h100_anchor/`。正式180单元起点、参考恢复和公共全域场比较已在前文登记；下一步先测更紧求解对场差与标记的影响，再进入真实候选闭环。本三锚点不提供候选排序依据，也没有运行最终p6对照。
