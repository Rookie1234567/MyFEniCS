# dot 云端并行研究：首批结果

## 面向 0.7 nm / 2 TB 的结论

局部矩阵生成有正信号，但它只解决装配的一部分工作。完整求解仍受全域 p4 因子、每步纠错成本和实际端口/工作向量库存影响；本批没有目标模型解，也没有 2 TB 或 48 小时达标证明。结构化几何的精确共享比逐单元最坏情形有利，不能把 15–17 TB 假设写成不可避免。

| 实验/分析 | 实际结果 | 数据身份、单位与范围 | 证据 |
|---|---|---|---|
| p6 六参考积分复用 | 14 组矩阵最大相对差 3.5810e-16；作用 4.3008e-16；5 组 Schur 最大差 5.6901e-15；补充 G1 恢复残差 1.4651e-11 | measured；无量纲；局部 882/450/432 维，非完整 PDE | [tensor findings](../../../benchmarks/cases/task40extra_dot_parallel_cloud/tensor_reuse/findings_zh.md) |
| 同批局部生成成本 | 含共享构造器及模板准备后候选 1.4009 s / 原核 5.1446 s，约 3.67 倍；六实模板 35.61 MiB | measured；6 次配对、云端调度噪声；不是完整求解提速 | 同上 results.json 与 provenance.json |
| DtN 模式 | 母体 M0/M1/M2/M3 = 80/180/340/532；增长 M2 母体 q1.25/q1.5 = 588/700 | measured generator；通道数；按键是子序列，非前缀 | [DtN findings](../../../benchmarks/cases/task40extra_dot_parallel_cloud/dtn_modes/findings_zh.md) |
| 实际生产端口默认规则 | M3 degree27 对应 14×14；局部投影对 48×48 相对差最大 2.252e-10 | measured component；未查全局装配/运行时 override；无需据此盲改默认 | 同上 production_port_rule.json、trace_quadrature.json |
| 原 G1 时间分账 | KSP 占 76.523%；即删除全部 setup，其他不变也最多 1.28464 倍 | derived from parent measured；不是新云端 PDE | [容量与优先级](capacity_assessment_zh.md) |
| 精确几何计数 | G0/G1/E1/E2 原始材料+metric 类型 33/30/156/156；假设恢复带缺口尺寸有 1,369,452 cells、211 原始类型 | derived metadata；orientation/factor 实际类型 unknown | [compact inventory](records/exact_metric_inventory_compact.json) |

## 含义与保留边界

参考积分复用是把单元基函数积分预先做成六张表，随后用每个单元真实几何组合矩阵，避免重复积分；它不合并近似几何、不共享不同局部 LU，也不减少全域 p4 因子。当前比较共享 Basix 基础，缺独立编译 FFCx oracle、真实方向/Floquet/MPC、非零端口 RHS 和完整原 A6 资格。

DtN 实验检查开放边界通道的编号、物理方向和局部投影积分。它没有测量增加通道后的全局场/功率变化，因此不能授予截断资格。8×8 的 1.942% 误差仅是人为低阶负对照，生产已采用更高且自适应的规则。

| 负结果/未执行项 | 实际状态与原因 | 下一步 |
|---|---|---|
| 原构造器在新 UFL 测试 | cellname 方法/属性 API 不兼容，原测试真实失败；实验副本一行适配后通过 | 保留错误日志，不改父源码或声称原 ABI 通过 |
| 完整 PDE、official R/T/A、截断/连续精度 | not_run；本支线是组件诊断 | 正式任务需原环境完整验证 |
| 目标 2 TB / 48 h | unknown；实际目标几何和全面库存尚不足 | 优先弄清全域 p4 与每步纠错成本，不再只优化装配 |
| CI / 全库 pytest / MPI | not_run | 只陈述本批实际检查 |
| GitHub 视觉渲染 | 未验证；源码表格/链接结构检查完成 | 不把提交成功等同渲染 Gate 通过 |

## 身份、检查与合并边界

基线 c786e87d03976a52f57d1e7f69a3c63f992afe90；云端下载 20 文件各多一个末尾 LF，去掉恰好该 LF 后 blob 匹配，实际字节 SHA256 均保留。新 research 核心位于 src，未接入生产。portable 脚本仅改源/输出路径，保留实际计时版本；发布前在独立云端布局复跑六个 portable 脚本均 exit 0，数值检查通过，未用复跑挑性能样本。详见 [复现入口](../../../benchmarks/cases/task40extra_dot_parallel_cloud/README.md)。

| 依赖组 | 本批变化 | 建议 |
|---|---|---|
| production numerical/core | 无生产接线、无默认变化 | 不授予生产资格 |
| research-only | src/solvers/task40extra_reference_metric_component.py | 保持 opt-in；下一步独立 oracle/方向检查 |
| checker/benchmark | 两类组件 runner、计数脚本与 compact records | 仅其明示范围 |
| compact evidence/docs | 本目录、benchmark findings、项目回顾 | 可独立审阅 |
| do-not-merge | 整体研究分支、raw/模板/cache | 未开 PR、未 merge；仅更新 dot 独占分支 |

## V2：真实三维G0 p4算子数据

| 范围 | 实际状态与数据 | 证据 |
|---|---|---|
| 小型真实三维p4装配/导出 | measured；336 cells，29,072 rows、10,912,592 NNZ、80端口；complex128/int32 CSR 218,368,132 B | [V2详细结果](real_p4_probe_preparation_v2.md) |
| 独立内容/资源核验 | 全1,486 arrays核验；同时树RSS峰1,199,104,000 B，136.742秒，swap0；无global factor/solve | [compact记录](records/real_p4_probe_preparation_v2.json) |
| 失败/ABI边界 | 两次collection失败、一次mode-hash失败保留；危险历史private-FFI未运行；新环境小型资格单独记录 | 同上 |
| 最终目标 | 完整三维原尺寸50×25×140 nm、无缺口规则基线、0.7 nm、约2 TB/≤48小时；未来三维缺口能力保留；截至2026-10-04 10:07:14 UTC的72小时研究窗口 | 当前目标能力unknown；不以二维/2.5D替代 |
| 下一步 | 准备公共backend128reference+完整原A4 residual screen；尚未运行；64在其通过后再决定 | [Response V2](../response_v2.md) |

## V3：完整三维 y-orbit 参考逆架构

| 对象/数据身份 | 实际结果 | 资格边界与证据 |
|---|---|---|
| scaled p2 full3D规则A0，全部2048独立DoF/4块/532 aliases | 原残差3.4914e-14（generic all-q）、8.2937e-15（incident）；完整direct场差≤1.4738e-13 | measured；[详细结果](y_orbit_full3d_pilot_v1.md) |
| 同mesh真实nonseparable notch | generic/incident FGMRES4/3步，原A残差5.2744e-15/5.8469e-13；真实incident非零q比例1.4217e-5 | measured；所有y内部通道和端口保留，无n0投影 |
| 资源/失败 | attempt2 tree RSS638,885,888B、8.839s、swap0；warm JIT；attempt1 readonly Vec API失败保留 | [compact及失败hash](records/y_orbit_full3d_pilot_v1.json) |
| 独立核验 | 12矩阵/direct残差重算及all-q/aliases/nonzero-q通过；focused3 passed | 未做full pytest/MPI2+/Ruff/CI/rendered view |
| 后续/目标 | 非零y ky、真实p4/p6、直接单cellblock生成、原尺寸2TB/48h均未资格 | 小p2架构正结果，生产和目标能力unknown；[Response V3](../response_v3.md) |

## 原始端口 H：独立组件资格

端口 H 是每个出射模式的独立归一化。用对角向量代替稠密方阵，可以保持全部三维 DOF/全部模式，仅减少无必要存储和通用求解。production 暂未接线，也不是二维等效。

| 项目 | 结果 | 身份与边界 |
|---|---|---|
| 全尺寸真实生成器 | 50×25nm、0.7nm、1°掠入射/Si：32,060模式，31,488个n≠0；包络142/35 | measured inventory；截断未资格，非目标PDE |
| 实际G0 p4 port | B/D各42,624项、1,536唯一行；无Bi/Di/XiB，carrier1,704,960B | measured saved export scan；不是当前主要内存瓶颈 |
| 实际80mode原H组件 | 任意complex1285RHS/单列/零向量，solve/action差0；20 targeted tests pass | measured standalone component；production与原A资格未完成 |
| 资源 | corrected watchdog2.0147s、同时树RSS196,882,432B、swap0；H数组1,280B | measured；独立树RSS与named payload不相加 |
| Hhat | synthetic factored action差9.1427e-17，无新增LU/方阵 | algebraic supplement；actualp6完整作用/性能未运行 |

详见[组件结果与接线清单](original_port_blocks_component_v1.md)、[原始记录](records/original_port_blocks_component_v1.json)、[全尺寸库存](records/full_size_port_inventory_v1.json)。0.7nm完整目标、全域p4因子、截断/连续精度、2TB/48h仍未解决。

## V3后续：真实非零y Bloch phi5

| 数据身份/范围 | 实际结果 | 证据/限定 |
|---|---|---|
| measured；同80cell/p2 scaled full3D，phi5，532 ports/4 blocks/480 interiors | phase_y0.5285127306+0.8489253758i；native covariance3.1047e-16；全部aliases保留 | [phi5详细](y_orbit_phi5_pilot_v1.md) |
| measured；同2-cell三维notch、原A FGMRES | generic/incident4/3步；原残差1.2852e-13/7.1414e-12；direct差5.4957e-13/5.5650e-11；incident非零q5.5252e-5 | 原门未放宽；独立checker通过 |
| measured；whole-tree watchdog | 701,861,888B、10.107636026s、swap0，清场；warm JIT；4 focused tests | [compact/hash](records/y_orbit_phi5_pilot_v1.json) |
| 下一步 | 暂停新实现/数值计算；先远程code/docs/history审计；72小时workstation-ready大型验证方案 | 原尺寸精度/2TB/48h/收敛仍unknown；工作站由用户执行 |

## V4：全分支复用审计（无新数值运行）

| 身份/范围 | 审计结论 | 决策/边界 |
|---|---|---|
| indexed；35当前HEAD、8713去重blob | 全树无截断；4773代码/正文blob共104291461B核验并自动检索，缺失0 | 搜索不等于全文精读；SHA/path/范围见[覆盖](records/repository_audit_coverage_v1.json) |
| historical measured；Task040 S2d | exact背景逆tiny残差serial/MPI2约1.60e-14/2.14e-14已存在 | y-only异质x-z/full-RHS/all-alias/sparse是扩展，不是首次提出 |
| derived；p4/port/neural复用与负结果 | 复用准确凝聚/恢复、已有gauge和fullspace对角H；避免同对象BLR/神经/streaming重试 | 不改变历史资格；[综合审计](repository_reuse_audit_v1.md) |
| not_run；新高阶/工作站资格 | 当前p2 phi5已过；p4/p6、跨ABI、目标资源/物理与中断恢复仍缺 | 与本机同一大验证；自主读main新push；用户执行工作站大运行 |

[Response V4](../response_v4.md)。本轮仅compact docs/evidence，无新PDE或生产接线；完整语料不入Git。

## V5：sparse-p2 q0因子失败检查点

| 身份/对象 | 实际结果 | 资格边界 |
|---|---|---|
| measured；source f2bd95ba、80cell/p2/phi5/manual532 | 原A0全部2048列差0；凝聚covariance9.953e-17、off-block4.116e-16 | 原已截断离散operator与对称性通过 |
| failed；q0 468行/26264NNZ | 混合FE/aux单位量级cos/sin载荷残差1.434203246972e12；重复0；linearity NaN | 未保存解向量，不能据NaN范数判条目非有限；完整inverse/p4未运行 |
| measured；watchdog | 7.320493135s；同时树RSS433651712B；swap0；exit2；后代清场 | 非资源Gate停止 |
| derived；保存场见证 | 凝聚FE6.233e-14、q0FE4.023e-14；内部RHS范数2.678e-15 | 支持近零内部载荷符号/映射，不是任意RHS逆通过 |
| diagnostic；端口 | H最小1.072e-194；172零C列/174零D行；q0共同零16项 | 532身份保留不证明未裁剪泛函完整；同离散缩放不能恢复上游裁剪 |

[Response V5](../response_v5.md)、[hash-bound失败检查点](records/sparse_p2_failure_checkpoint_v1.json)。旧phi5原A/direct/Bloch数值保留并限于已生成operator；不外推本机未发布结果。新p4和gauge资格未运行。

## V6：同一已裁剪离散算子的positive-H求逆坐标诊断通过

端口幅度换成均衡单位再恢复原单位，精确保留原S0/原FE operator；没有恢复上游被裁掉的functionals。

| 身份/对象 | 实际结果 | 资格边界 |
|---|---|---|
| measured；worker1c83fae、同80cell/p2/phi5 | 原S0 bytehash与raw失败相同；原A0全部2048列差0；原S制造载荷残差≤1.1554e−13 | 全4q、480interiors、532identities；172零C/174零D仍在 |
| measured；完整原FE reference inverse | generic/physical原残差9.9685e−13/7.9961e−14；保存direct差≤9.4279e−13 | 固定原FE RHS与完整内部恢复，不删y通道 |
| measured；full3D notch | generic/physical/notch-supported4/3/4步，原残差≤7.1415e−12；physical非零q5.5252e−5 | sampled PC defects仅3.32e−5..9.08e−4，弱扰动，不能外推大型收敛 |
| measured；资源/独立checker | worker11.1352s/RSS437866496B；checker2.8673s/RSS253747200B，分别swap0/清场；88/88及全局门通过 | warm cache；1.5GiB/600s；512MiB声明余量不是fill保证 |
| failed；旧raw factor与checker1 | raw单位辅助载荷1.4342e12/NaN仍失败；checker1 NumPy-bool JSON失败保留 | worker1c与checker d095分开，1234依赖hash/ABI不变，无PDE重跑 |
| not_run | 预sparsification boundary-plane修正、p4、原尺寸accuracy/2TB/48h | p4held；新边界representation须独立p2权威，不把身份数当未裁剪物理贡献 |

[Response V6](../response_v6.md)、[compact及失败/worker-checker身份](records/positive_H_same_discrete_p2_v1.json)。本批补足main Task40extra，ordinary defaults不变。

## V7：boundary-plane完整532模式组件资格

| 身份/范围 | measured/verified结果 | 限定 |
|---|---|---|
| a054626组件；80cell/p2/phi5/manual532/fullMPC/sameGauss | 8项小测试＋真实532模式测试通过；恢复空C172/空D174，新空均0 | PASS_COMPONENT_ONLY；无centered PDE/official RTA |
| 未截断坐标等价 | C/D约4.13e-14；每模式stored损失界最大1.368e-13 | 逐模式组件门，不是累计相对operator norm证书 |
| 五状态旧stored→new stored | 0.03082258966421717 | 新存储算子改变，V6只保留旧clipped authority |
| 资源/失败 | actual532树RSS327430144B、10.3655s、swap0；attempt1–3失败保留 | warm/sampled；不推断目标RAM/时间 |
| 同快照候选2839e7 | 54定点pass/1真实PDE skipped；新centered p2仍NOT_RUN_PDE_CANDIDATE | 不继承组件资格；p4/p6/原尺寸2TB/48h未资格 |

[Response V7](../response_v7.md)、[完整532 ledger](records/boundary_component_v7/all532_compact_ledger.json)。本轮只文档归档，不改变数值源码。

## V8：新centered原算子的完整p2 dense→sparse资格

先将端口相位参考点移到实际边界，使衰减模式的微小指数系数不再被装配的绝对截断消去；再直接求解完整原有限元系统建立对照。候选把单元内部未知量精确消去、按y单元平移分成四块求逆，最后恢复每个原始三维未知量。全部y通道和532模式仍在，减少的是因子规模；高阶和目标尺寸的实际收益尚未测量。

| 身份/范围 | measured/verified结果 | 限定 |
|---|---|---|
| source7c4410；同80cell/p2/phi5/532非空ports | dense129/129、sparse164/164项checker；全部2048原FE列差0 | 新centered authority；完整480interiors与四类载荷 |
| regular原FE恢复 | 四载荷最大原残差3.1766e−13；q因子残差最大6.2886e−14 | generic/interior_only/physical/notch_supported；全部4q |
| 真实两cell三维缺口 | 4/4/3/4步；原残差最大7.4874051e−12；相对新direct差最大5.8732785e−11 | physical非零q比例6.2100442e−5；弱扰动，不外推大型收敛 |
| 逐模式输出 | 每个checker40组×532模式均通过；最差局部运算误差1.5851e−12 | 原场/辅助量/完整MPC绑定；官方R/T/A未资格 |
| worker资源 | dense633204736B/19.1875s；sparse464019456B/15.1345s | 同时采样树RSS；分别swap0/清场；warm cache |
| 独立checker资源 | dense460742656B/3.5745s；sparse327389184B/3.2861s | 独立监督；分别swap0/清场；不与worker相加 |
| 失败/身份 | dense attempt1/2严格raw-C/context停止保留；每次实际live carrier均独立资格 | 创建顺序只是原因候选；不假设未来JIT上下文相同 |
| not_run | p4/p6、强对比、目标精度/截断、跨ABI/MPI/重启、原尺寸2TB/48h | p4仅计划；尚不能启动目标大运行 |

旧clipped到centered全部原FE矩阵相对Frobenius变化0.0061060864，是算子改变诊断；不同于V7五状态action变化0.0308226，也不是坐标等价误差。详见[Response V8](../response_v8.md)、[compact](records/centered_p2_v8/centered_p2_v8_compact.json)与[独立复核事后记录](records/centered_p2_v8/independent_verification.json)；1247源码文件、712产物hash条目，不称712数组。本次仅归档已完成计算，不重跑PDE。

## V9：同80-cell centered p4与显式跨HEAD p2桥接

升阶把每个单元的基函数从p2增至p4，用同一个三维小网格检验更多内部未知量能否完整消去、恢复，并验证全部y块求逆。它检查实现随阶数增长后的可信度；原尺寸、强扰动与目标误差还需要独立资格。

| 身份/范围 | measured/verified结果 | 限定 |
|---|---|---|
| sourcead356715；新p2 sparse桥接 | 旧7c4410d dense全部2048原列差0；checker164/164 | old/new源hash与自身live carrier分别绑定；无dense重跑 |
| 同80-cell p4；15872独立/8640内部/7232trace | checker148/148；basis300、Gauss23/144点自身live532资格 | 4q块1884/1960/1960/1960；全部532实际端口非空 |
| p4原方程与真实三维缺口 | regular最大4.2235259e−12；notch4/4/3/4步、最大7.9668824e−12 | physical非零q比例3.0887006e−5；无full p4 direct |
| p4逐模式输出/因子 | 40组×532模式通过；块原残差最大5.0543e−13 | 原C/D digest、入射及局部尺度独立重算；official R/T/A未资格 |
| p4 worker/checker资源 | 117.4464s/913350656B；4.7910s/524525568B；分别swap0/清场 | sampled同时树RSS；不同run不相加；无phase硬峰归因 |
| 实际setup成本 | condensation24.9723s（kernel23.7653s）；reference setup7.7761s | 后者含审计/因子/诊断；没有纯factor或PC apply计时 |
| named payload/支持 | condensed CSR62914140B；局部保留24760944B；8cells非零Bi/Di | 不是RSS；不假定内端口支持为零；fill/workspace未知 |
| not_run | p6、强对比、原尺寸精度/截断、跨ABI/MPI/restart、2TB/48h | 下一阶段仅两单元参考quotient计划；不将数值块当物理降维 |

缺口的四个采样PC缺陷仅1.8697e−4至2.0507e−3，不是算子范数界或大型收敛证明。原volume authority为保存live FFCx作用，p4未做全局direct对照。详见[Response V9](../response_v9.md)、[compact](records/centered_p4_v9/centered_p4_v9_compact.json)、[独立核验](records/centered_p4_v9/independent_verification.json)：1251源文件、591产物hash条目及48 raw-factor hash。本轮归档不重跑数值，全部历史失败与源身份保留。

### V10 两胞元full3D p4 Q0–Q2审计

两个真实三维40-cell空间按y平移相位覆盖原80-cell/p4的四个q分支；边、面、胞元内部、MPC及532原alias全部保留。这里只验证同一原方程的表示、作用及manufactured恢复，不是物理解或quotient inverse。

|项|实测/边界|
|---|---|
|source/tree|35dd9e5c39939d14bbded98f288007aff4a08368 /38fde56b7e8988194699a8943145d7b087f22318，clean|
|资格|Q0–Q2；独立checker4842/4842；evidence_valid=true|
|覆盖|两sector228/304 modes；全部四q；每q3968 FE列；每侧4320内部RHS全非零|
|最大运算差|CSR norm7.623844459299511e−16；entry1.2633342716896627e−15；map1.112995121386375e−15；original action9.123615983914468e−16；complete recovery2.0082399999380633e−13|
|cross控制来源|4 fresh local同twist；8 immutable旧S/maps跨twist，complete map桥接和2 fresh原作用witness支持|
|资源|worker334.13608062599815s /741564416B；checker10.395193903998006s /312737792B；采样整树RSS、swap0、后代清场|
|因子|global/q0；继承108×108 cell内部LU，20 shared buffers/sector|
|未资格|Q3–Q5 inverse/forcing/outer/notch/full outputs；目标尺寸/精度/2TB/48h；官方R/T/A、MPI/restart|

[Response V10](../response_v10.md)、[compact](records/two_cell_p4_v10/two_cell_p4_v10_compact.json)、[独立复核](records/two_cell_p4_v10/independent_verification.json)记录1267源文件、2222 artifact hash entries和1064 raw packet JSON描述符；不重跑数值，不重命名旧ad356715权威，不改历史失败。


## V11 两胞元full3D p4完整恢复逆通过

数值worker `5e0364cd` 与saved-only checker `029a0cd8` 独立绑定；仅checker和新增测试有差异，数值/配置/ABI依赖不变。prefactor19/19及完整inverse checker312/312、evidence_valid=true。两个40-cell三维空间覆盖原80-cell、15872独立FE/8640内部、四q/532 aliases；四fresh q CSR差0后才分解，四因子全部保留。

regular四载荷最大原残差 `5.26717490249291e-12`；真实两cell三维notch的generic/interior/physical/support迭代4/4/3/4、最大原残差 `7.966735639625955e-12`，对不可变V9 full-period保存场差最大 `2.609464583066699e-14`。8 packets各532模式通过独立原系数与V9输出门，仍非official R/T/A或目标截断资格。

worker145.83506661900174s/RSS788480000B，saved-only checker7.072437755996361s/RSS300224512B，分别swap0/清场、同1.5GiB/600s。首个checker因历史old full_Q行未排序失败，原失败保留；新checker只做被hash钉住的private row-sort copy及exact permutation/action等价门，无候选CSR放宽、算子改变或PDE重跑。只授予有界scaled full3D架构资格；本两cell路线p6、强对比、目标精度/32060模式收敛、跨ABI/MPI/restart、原尺寸λ0.7nm及2TB/48h仍未资格。

[Response V11](../response_v11.md)、[compact](records/quotient_inverse_v11/quotient_inverse_v11_compact.json)、[配对归档核验](records/quotient_inverse_v11/independent_verification.json)。历史V9/V10范围及全部失败保持原身份。


## V12 共享完整实体变换资格通过

同80-cell共享变换在source `3570347c`通过资格：原312项数值门与新38,881项状态/存储/生命周期门全部通过，四q、8640内部及532端口保留。完整outer+local记录矩阵/inverse逻辑体积69,435,392B由4个矩阵内容模板与4个lazy inverse复用，实际8个template owners为410,624B；全部named owners另为46,234,084B，不能混称RSS。

原regular/notch最大true residual为5.2675719230699435e-12/7.96690203269436e-12，notch generic/interior/physical/support为4/4/3/4步。worker170.035s/RSS1,065,373,696B，checker43.125s/RSS952,623,104B，分别swap0/清场、同1.5GiB/600s。因独立legacy/evidence重叠，整树峰高于V11，本轮不授予RSS或加速收益。p6、原尺寸准确网格/端口收敛/2TB/48h仍未资格；X direct profile正在实施且尚未运行。

[Response V12](../response_v12.md)、[compact](records/shared_transform_v12/shared_transform_v12_compact.json)、[独立归档](records/shared_transform_v12/independent_verification.json)。历史V11与所有失败范围保留。


## V13：X网格加密点完整保存证据资格

X在同光学尺寸、manual532下将网格加密至p4/6×4×5=120 cells；两local twist各60 cells，精确消去再恢复全部12960内部未知量，四q因子同时保留。其意义是检查完整三维恢复路线随离散密度增长的行为。

| 项目 | measured结果与范围 |
|---|---|
| 完整独立核验 | 358 direct＋33519 raw＋37 operator＋41217 shared＝75131条通过；shared控制名称允许合法重复 |
| 原三维残差 | notch最大4.710949682298374e-12；regular physical native保存7.57682638912512e-11、独立最大7.546733167266532e-11，gate为1e-10 |
| notch与输出 | generic/interior/support/physical为4/4/5/4步；8组各532完整有限且可表示模式输出 |
| worker / checker | 1535.1467s / 590.1043s；整树RSS峰1422172160B / 1567666176B；swap0、清场 |
| 明确限制 | X-only 2GiB/1800s；非普通1.5GiB/600s；目标尺寸/AUTO32060/2TB48h、official RTA未资格 |

worker816b7247与checker2a07d23分别绑定。原startup/resource/source-role/residual定义失败、成功后launcher KeyError及首supplemental唯一label断言失败均保留；当前checker只消费保存证据，factor calls0。CSR54078536B不是factor fill/RSS；sampled PC defect0.013423不是算子范数。详见[Response V13](../response_v13.md)、[compact及失败索引](records/direct_X_v13/compact_record.json)、[最终独立核验](records/direct_X_v13/independent_final_X_evidence_linkage_review_v1.json)。下一步须审查后再准入XZ/Ny扩展，尚不推出目标可行性。
