# V13 变化与selective merge依赖边界

| 分组 | 本批变化／数值行为 | 依赖、测试及fresh证据 | 建议合入顺序／边界 |
|---|---|---|---|
| production numerical/core | 无生产方程／默认改变，原材料、Maxwell、MPC、DtN及恢复不改 | 所有新入口显式V13 opt-in | 不提升失败研究为production |
| research-only numerical | `src/solvers/neural_trace_tangent.py`、`tangent_head_model.py`、`tangent_head_study.py`：手推JVP、实小LS、补偿／实际试探、有限记录恢复 | 原batch8/action/Hhat/stable_head；小型复数与真实A/B/C/D资格 | 核心→局部模型→study；极小J下降，非精确VarPro或solver资格 |
| reusable runner/watchdog | `tangent_head_window.py`不可刷新deadline／journal，复用既有tree/subreaper，无永久后台等待器 | 超时、setsid清场、sibling保护；六run清场 | 先审窗口／ownership；无cgroup连续限额声明 |
| research入口／接线 | `src/io/tangent_head_compensation.py`、薄runner及run_case/profile/shared的最小显式分支，六独立dat | identity／预算／参考屏障；四基础validate及有限复核／恢复 | 核心之后；普通default不变，不复制每方向脚本 |
| checker／benchmark／tests | `src/io/tangent_head_evidence_check.py`、`benchmarks/check_task042_v13.py`、三组V13测试 | raw与NPZ状态hash重算，反例、25pytest＋4ML小断言 | 证据一致性可单独审阅；不等于solver PASS |
| compact evidence/docs | Response V13／outcome／JSON/CSV/journal、README导航及summary/test_summary、Task042两总账追加 | 初始／失败／接受／恢复／审核source与measured/derived/unknown分开 | 可保留负证据，master merge未批准 |
| do-not-merge | results/artifacts、P/Z/R/A、参数／moment/action/REF7、venv与JIT/TMP/cache | ignored只在NN-Lab；Git只有轻量指标／hash | 不提交大数组或环境，历史失败不删除 |

实际接受source `33f7d613b1341fa585f0324ead6039bf28211fff`；writer最小修复及记录恢复／D source `7615baae2f0d75fbc47c05be392b35ef2878c431`，没有重新优化。[Run index](records/run_index_v13.json)、[完整研究](tangent_scale_head_compensation_v13.md)。以下旧分组与失败历史正文保留。

# Task042 实际变化与依赖分组

| Selective merge组 | 变化与数值行为 | 依赖/验证/fresh证据 | 建议顺序和边界 |
|---|---|---|---|
| production numerical/core | 没有把研究逆提升生产默认；旧p6 action/runtime仅显式`borrowed_p4_witness`/`retain_coarse_schur` opt-in | paired默认拒绝/ownership测试、noncommuting原p4测试、真实F1 A4/A6/恢复 | 先审查opt-in与所有权；本轮无合格F5，不能宣布production逆替换 |
| research-only numerical | `coarse_inverse_protocol.py`、`learned_coarse_inverse.py`、`learned_coarse_runtime.py`、`learned_coarse_data.py`、`learned_coarse_packets.py`、`learned_reduced_correction.py`、`learned_training.py` | 原方程/有界局部PC/strict return→p4同身份→teacher packet/POD→线性/NN；pure tests与F1/F2/F3/F4实际记录 | 协议→原p4 witness/容量→离线数据/表示→候选；严格逆失败，维持research opt-in |
| reusable runner/watchdog | `benchmarks/subreaper_watchdog.py`新增可选memory_envelope/health/include_pss；原默认不变 | 既有subreaper语义，资源触线orphan/setsid清理且sibling不受信号；可读健康资源检查 | 先验证own descendants范围和cgroup权限声明；不合并其他任务共享规则 |
| research orchestration | `src/runners/task042_shared.py`、`task042_experiment.py`、`task042_coarse_stages.py`、`task042_training.py`及`src/io/task042_profile.py` | 自有flock、clean source、隔离ABI、逐阶段退出；src承载算法，runner仅装配/记录 | 所有numerical/data模块之后；普通runner新增显式dispatcher，不复制每case solver |
| checker/benchmark/tests | `src/test/test_task042_*`、解析研究profile枚举和input validation opt-in | tiny complex arrays/真实80mode元数据/borrowed witness/资源监督；同组16 RHS及独立raw Gate重算 | 核心接口/枚举变化的focused验证，不运行邻heavy下full pytest或MPI2/4 |
| local activation/config | `scripts/activate_task042.sh`、`task042_preflight.py`、`task042_bounded_check.py`、Task042 dat/profile/依赖lock/尺度模型 | 单核/线程/缓存realpath、FE/ML分环境、CPU-only FP64、每dat一次明确阶段 | 配置→ABI/probe→数值；不得把本机readonly prefix路径当普遍部署配置 |
| compact evidence/docs | 本outcomes/v2 JSON/CSV、`response_v2.md`、本分支progress/registry Task042段 | 所有实际source/input/dataset/model hash、误差与failed/not_run、过程时间/RSS | 可独立审阅负结果；原task/review/response_v1/F0数值records保留 |
| do-not-merge | `.venv/.venv-ml`、results/artifacts、raw logs/time lines、JIT/bytecode/cache、Q/模型/checkpoint/teacher包 | ignored仅NN-Lab；不包含旧大结果/factor，也不向Git提交大矩阵/权重 | 本地复現artifact，Git只提交必要轻量hash记录 |

所有代码路径与data provenance见[架构](architecture_and_oracle.md)、[数据模型](dataset_and_model_provenance.md)。研究模块名字带Task042的部分承担固定范围入口/记录，不把新的p4数学只实现于benchmark脚本；通用core函数参数化。已有A4/A6物理、传递、DtN库存、材料/几何、BAL_H方程和最终门限保留；既有task/review及其他任务源码、环境、watchdog、锁未修改。仅两个原solver/runtime opt-in点与明确research dispatcher/schema分支改变现有文件。

## 真实实现提交及失败修复

| 完整SHA | 阶段/实际作用 |
|---|---|
| `ae5b7d2b79dec38056e4a8b9bd986429989455dd` | 共享CPU profile、F1原方程与有界PC；首次缺pyvista导入失败，无JIT |
| `23cb4710e3ed2c8f7c51fd2b3f4e4dd952bea716` | NN-Lab graphics依赖固定后一次重试；CFFI缺setuptools，保留失败 |
| `f194e455cf904d255fbb30151f21d12be19bc56b` | 独立setuptools与complex CFFI资格；真实p6/p4构建后默认action拒绝材料化p4，非数值失败 |
| `7188564f1a284049ddac3eb32a77ccbda84c5c6b` | 明确借用p4 witness接口，paired旧行为测试；实际mode complex JSON serialization失败 |
| `cca180f875bd22146f2d30fa4d004e372135dfbb` | complex元数据和数组形状最小修复；F1接口实际通过、B0非零失败保存 |
| `b72448bb2117a0221f041f1b47ac41049750a3c7` | 真实teacher、batch packet/native检查；384对实际生成 |
| `d9de8ad69bfeeac4860e5187e1738c902a3d808e` | teacher资格绑定、表示容量、F1失败state完整audit；oracle实际四rank |
| `28a814d1c740c5c23916fe8053c0de7435608a80` | FP64 CPU MLP/冻结推理与F4候选；静态发现F4-B0手写schema enum漏登记，此source无正式数值负载 |
| `a221d881bae9405c98e351df2b0b9533582e6d50` | enum最小修复/all-phase input test；CPU实际训练300epoch |
| `7216efa605bae155ee383fd716c0fae422448b52` | model/dataset/basis资格绑定、真实训练摘要；三条F4均在此同一clean源码运行 |

这是局部实现/元数据修复顺序，原失败资源与错误保留，未以参数扫描反复求数值成功。最终交付另修正零RHS报告不携带前一个native audit缓存；返回/迭代算法及冻结F4结果不变、不重放、不冒充新文档source。最终测试、静态检查和后续文档HEAD另记录。[run index](records/run_index_v2.json)是每次实际clean运行的身份权威，非最新HEAD回填。


## V3 最新有限诊断（原V2正文保留）

V3新增research-only `learned_geometry_overlap.py`、几何/预算/phase测试和`task042_diagnostics.py`；旧backend只可选observer，默认不变。两独立dat/diagnostic_v3.json显式opt-in、V3活动样本准入、CPU纠正和compact CSV/JSON/response/两总账新增段。numeric SHA与文件hash见[运行账](records/run_index_v3.json)。原task/review/response_v1/v2、原v2JSON/CSV和raw保护，未修改邻任务或共享配置；未获production/merge资格。

最终仅修正Task042 watchdog测试从原始整树样本断言后代；未改变监督器/数值源码，原失败记录保留。冻结numeric source仍7fc3f1434cf4f38f43e5244ebfed3a19d0780a26。


## V6：关闭旧路线，材料独立神经trace接口

| 依赖组 | Task042实际变化／数值行为 | 测试与边界 |
|---|---|---|
| research-only geometry/core | 新`neural_micro_pilot.py`参数化box/notch标签＋居中坐标载体；`neural_trace*.py`完整moment/Piola/orientation packet、复数loss/VJP、固定FP64 MLP／局部checker | 23相关pytest、两ML断言、真实FE／ML接口；无目标S、物理恢复或solver资格 |
| reusable runner/watchdog | 新薄`neural_fe_interface.py`接线，原run_case／profile／shared仅两个显式material-blocked入口、实时V6准入；原subreaper复用 | 普通PDE仍要求材料，默认不变；source clean／一dat一stage／独立artifact，唯一坐标修复保留失败 |
| compact evidence/docs | 新V6 design／2dat、material blocker、原字段聚合／source与资源／response和两总账新增段 | 原task/review/response/records保护，旧augmentation不实施，seed420620不消费 |
| production numerical/core | 无新增资格化路径；原A4/A6/S/Floquet与默认不改 | 不提升新表示为production |
| do-not-merge | FE packets／零初始与非零接口witness checkpoint、mesh／日志／缓存／临时helper | ignored只在NN-Lab，无旧大型结果复制 |

C1 `64c128c3541887e22788343692cc4f7832a45696`；唯一正式坐标修复／成功接口C2 `2a2cb4af78ba869a26a1254b4b4b76c9ac158366`。模型11696参数并非合格解，未建真实S/Sᴴ／物理port／内部恢复，三求解路线尚未运行。新材料独立loader是必要显式研究例外，普通schema的Si材料要求保留。所有权威／历史及原结果不改，不merge。


## V7：四波长材料与真实单次FE求解对照

| Selective merge依赖组 | 必要Task042改动／数值行为 | 对应测试／边界／顺序 |
|---|---|---|
| material/core独立组 | input/materials/si_optical_constants_v1.json、optical_material_table.py及离线回归；唯一来源/精确alias/complex square | 7材料回归，先审材料/loader；不自动改变普通case输入 |
| research numerical/core | hcurl_assembly_time_condensation仅可选保留原局部张量审计；neural_fe_action_packet/pilot/gradient_check/optimization/bounded_complex_lsqr | 默认False不改旧求解；真实N1/三路线源绑定，未资格化research-only，不能默认部署 |
| reference-only组 | neural_fe_blind_reference.py，单次p3 symbolicGate/LU，原FE/EH/power；一个范数Form修复后只验证重放 | complex CSR/valid UFL 4 targeted、实际参考；依赖三状态先冻结，不进入候选/loss，不回旧p4 |
| runner/watchdog组 | 原run_case/profile/shared与薄neural_fe_continuation opt-in、独立one-run dat、cumulative V6+V7预算 | 复用原监督器/own lock，MPI1、整树16/12GiB/swap0；无复制watchdog、无ABI/邻任务修改 |
| checker/benchmark组 | neural_fe_gate_check.py与两个反例；复E/H和完整40channel重算、不相信status | 最终32相关pytest，checker无solver/FE重放 |
| compact evidence/docs组 | material/geometry/gradient/三路线/全channels/226audit/source/model/budget/response_v7及summary/两个项目总账新增 | 先数值依赖再轻证据；历史byte/prefix/suffix保护，Review V4不改 |
| do-not-merge | 209MB packet、model/checkpoints、accurate reference、global p3 reference临时CSR/LU、JIT/cache/大日志与临时helper | ignored NN-Lab，不把global参考逆放候选、不上传大型数组 |

正式source完整表在[response_v7](../response_v7.md)／[run index](records/run_index_v7.json)：N1 70f5f543…、三路线7c4037a2…、参考19adac7e…、后处理1ff6f8ba…。后续compact checker/docs HEAD不替代这些source；普通default/原方程/MPC/材料旧输入/旧80通道模型/Task与Review及V1–V6负结果保持。不amend/强推/merge，只原执行分支待review。


## V8：有界尺度与等价计算校准

| 依赖组 | 必要Task042变化／行为 | 验证／边界 |
|---|---|---|
| research numerical/core | optimizer_step_transaction、neural_fe_column_scaling及原optimization显式包装 | 事务/稳定列范数/非Hermitian adjoint/原LSQR递推；严格负结果，非production默认 |
| research neural execution | neural_trace_batched、neural_fe_batch_calibration | 原3×64/8载波/FP64/完整矩，batch8＋固定缓存；真实等价与三对micro，无训练 |
| runner/profile/input | calibration_v8 plan＋独立dat、neural_fe_calibration IO/薄stage、原run_case/shared dispatcher | clean source/自有锁/原watchdog/预算；C2未用moment读入最小修复后边界回归，原运行保留 |
| checker/tests | neural_fe_calibration_gate_check复用原物理checker，新增raw损坏反例、C1/C2/C3/输入边界tests | 不含FE求解；从raw标量/复observable重算，不信PASS标签 |
| compact docs/records | response_v8、scaling_and_execution_v8、所需CSV/JSON、summary及两总账新段 | source/hash/真实负结果/全过程费用及not_run；旧历史逐字保护 |
| do-not-merge | D/state/packet/网络参数、raw日志/监控/缓存/环境和临时helper | ignored NN-Lab；无global p4部署，setup小CSR释放，参考只验证 |

建议合入顺序：事务→列尺度/包装→batch数学核→研究profile/runner→checker/compact证据，全部依赖组待review，不提升默认、不merge。原action、LSQR递推、原FE／A4/A6/MPC、material和旧task/review/response/records不改。正式source仅1a2984a44ca48573bbe18ffe8a7f8c5d6bdacc05和52d47d35656c5a763bed07e07f827fb6fb285bb7，后续所有权及checker/docs source另列。


## V9：只读固定误差定位的依赖组

| Selective merge组 | 必要变化／数值行为 | 测试／边界 |
|---|---|---|
| research numerical/core | 新frozen_fe_error和frozen_fe_field_localization；齐次误差helper、缓存原作用、一次FE积分；原生产S/F/MPC不改 | 复数非零特解/port、原方程身份和实际区域积分；不生成新解 |
| research runner/profile/input | 新frozen_fe_diagnostic IO/薄stage、固定六状态plan和one-run dat；run_case/profile/continuation/shared仅显式V9 dispatch | clean source、原自有lock/watchdog、128调用/3600及累计预算；ordinary default不改 |
| checker/tests | 新frozen_fe_error_check与两个focused test；单次修复交叉平方身份运算尺度 | 23相关最终pytest、真实raw checker，不求解、不信status |
| compact evidence/docs | response_v9、frozen_error_localization_v9、九必需records及显示/静态/环境；summary新前缀，两总账及测试/变化追加 | 历史按字节保护，首次失败和负结果不改写，完整source/hash/成本 |
| production numerical/core | 无新资格路径，V8事务和batch8实现保留 | 不改loss/network/PC、不重开p4、不提升默认 |
| do-not-merge | raw_fixed_error_vectors、原状态/packet、FE积分JIT、日志、环境、tmp helper | ignored NN-Lab；Git只有小CSV/JSON/文档 |

建议依赖顺序为helper→FE积分→研究IO/stage→显式dispatch→checker/tests→compact证据，均待review，不merge。正式FE source a1dc3466294c30b6de292468d6dd1aa9b685b193；最小checker修复source e21af767d3522af531ad83c45eacc1df252566c9，不替代运行source。原task/review/response、旧records和所有负结果保留，不修改邻任务。


## V10：自主输出头／端口研究依赖组

| Selective merge组 | 必要文件／行为与依赖 | 测试、fresh证据及建议顺序 |
|---|---|---|
| production numerical/core | 无新增合格production路线；原S/A4/A6/MPC/材料/trace矩/恢复/优化事务/batch8按字节不改 | 四候选负结果，不提升默认，不merge |
| reusable runner/watchdog | autonomous_batch_window、自有journal/父监督保护；task042_shared最小deadline/dispatch，沿原subreaper | 原start不重置、超时及整树触线/独立兄弟存活测试；先于研究stage接入 |
| research-only numerical/core | neural_linear_head、neural_linear_head_torch、neural_port_closed_head、neural_volume_balance | 复代数/薄容量/原矩与真实回写/Hhat真梯度/保存分项；原action依赖，有限pilot实测，不生产部署 |
| research runner/profile/input | autonomous_neural_head IO及统一参数化stage、run_case/profile最小显式V10入口；冻结plan与one-run dat | clean实际source/hash/自有锁；E/P入口预登记但不准入、不启动，普通default不改 |
| checker/benchmark/tests | neural_head_gate_check、薄LS/矩/窗口/Hhat/元数据及watchdog tests | 25最终pytest、ML三见证、真实pilot补核与原raw false-PASS反例；数值核后接入 |
| compact evidence/docs | response_v10、autonomous_neural_head_v10及必需11compact记录、通道/身份/静态/发布；summary新前缀及两总账/README/tests/changed追加 | 旧历史逐字保护，D2失败与Gate时序偏差披露，费用source完整；依赖最后归档 |
| do-not-merge | P/W/参数/field/action/raw分项、环境/JIT/监控/tmp helper及大日志 | ignored NN-Lab，保留hash-bound数据，不入Git；无global p4部署/hidden fallback |

建议审阅依赖顺序：窗口/监督→薄LS→原矩输出映射→Hhat精确端口与原V诊断→研究IO/stage/显式dispatch→checker/tests→compact证据。全部待review，不merge；E/P/最大模型未运行，不提升普通默认。最初B一见证、三个见证后补，原时序偏差及首次D2失败保留；后续文档source不冒充正式1fb8/6e56/6cba运行source。


## V11：稳定头与变量投影研究依赖组

| Selective merge组 | 本批必要文件、行为与依赖 | 验证／边界／建议顺序 |
|---|---|---|
| production numerical/core | 无新增合格production路径；原A4/A6、S、MPC、材料、40端口、普通默认与旧p4负结果不改 | M2内部门限与原物理场失败，禁止提升默认或合并master |
| research numerical/core | `src/solvers/stable_head_varpro.py`、`stable_head_varpro_torch.py`、`stable_head_window.py`：P=ZR、原S对Z重算A、Hhat40闭合、原方程loss及有界变量投影导数／接受状态 | 依赖原action/q15/batch8/port helpers；合成复数梯度与事务测试通过，但真实FD因S1/S2失败未运行；仅research-only |
| reusable runner/watchdog | `src/runners/task042_shared.py` 的V11窗口/整树监督沿用与最小字段；`src/runners/stable_head_varpro.py` 薄阶段编排（仍较长，后续审查应关注） | 单独one-run MAIN/REPLAY/VERIFY、own lock/CPU0/MPI1/math1/16GiB树监督，真实后代清场；不改邻任务 |
| research input/dispatch | `input/task042_neural_coarse_inverse/stable_head_varpro_v11.json`及三个`v11_*.dat`；`src/io/stable_head_varpro.py`、`task042_profile.py`、`scripts/run_case.py`仅显式V11入口 | 预登记seed/预算/物理hash/参考屏障；干净实际source a2cba715…、036e36ec…；旧默认不受影响 |
| checker/tests | `src/io/stable_head_varpro_check.py`、`src/test/test_task042_v11_checker.py`、`test_task042_v11_stable_varpro.py`；从raw重算S1/S2/场门限，拒绝坏saved status | 最终12 pure pytest＋3 ML小断言、compileall、真实S1/S2/FE；checker源码c6c650ad…是后置审计，不冒充正式计算源码 |
| compact evidence/docs | `response_v11.md`、`outcomes/stable_head_varpro_v11.md`、Review要求的9项compact记录，另加40复通道CSV及Review／静态／发布显示；README最新导航、summary新前缀、tests/changed及两项目总账 | 保留历史原字节与失败源／MAIN序列化缺陷，文档只说明真实结果；最后归档审阅 |
| do-not-merge | ignored P/Z/R/A、trial/workspace、参数/场/action packet、FE JIT/cache、原raw stage和tmp collect helper | 只在NN-Lab ignored目录，hash绑定不入Git；无在线global p4 factor、完整S/CSR、ILU/Riesz、正规方程或隐藏fallback |

建议审阅依赖次序：已有action／q15／Hhat→研究solver→窗口／stage／显式输入→独立checker/tests→compact负结果。真实 S3 FD、S4 hidden update、p4 enrichment 与目标大模型未运行，不能把已写的研究代码视为经过这些阶段的数值资格。原 task/review/response 及 V1–V10 raw 保留；无master合并授权。

## V12：固定头真实损失研究路径的依赖与合入边界

| Selective merge组 | Task042 本批变化／实际行为 | 验证、依赖及审阅建议 |
|---|---|---|
| production numerical/core | 无新增合格路径；原A4/A6、S、MPC、Si表、q15、40端口和普通默认未修改 | 原Schur0.7977/native0.3094、散射误差0.734均失败，不提升默认、不合并master |
| research-only numerical/core | 新 `src/solvers/actual_loss_block_descent.py`：固定γ真实原loss、40维Hhat闭合、共轭转置VJP、分辨率和Armijo规则；`actual_loss_window.py`不刷新四小时钟 | 依赖原action、batch8原矩、V11端口；真实 FD 未资格化，T3代码尚无真实接受更新证据，需保持research-only |
| runner/watchdog | 新 `src/runners/actual_loss_block_descent.py` 三stage编排，`task042_shared.py`只增加显式V12分流、own supervisor和原16/12GiB采样门 | T1最小两次接线修复及失败记录均保留；第二次后源码`d9df7068…`三正式stage成功；不改变邻任务或共享父cgroup |
| input/dispatcher | `src/io/actual_loss_block_descent.py`、`task042_profile.py`、`scripts/run_case.py`和三个独立`v12_*.dat` | 同物理hash、材料、输入及one-run身份；旧V1–V11输入／入口不变 |
| checker/tests | 新`src/io/actual_loss_block_descent_check.py`及两份V12 focused tests，从raw重算T1、FD、state、场及通道，5类坏证据反例 | checker在正式数值后提交`559846ee…`，不冒充run source；ML环境无pytest，纯环境最终26项通过／1排除，ML直接断言通过 |
| compact evidence/docs | `response_v12.md`、`actual_loss_block_descent_v12.md`、9项规定compact记录、README最新导航、summary/test/changed及两个项目总账 | 旧task/review/response/raw字节保留；所有负结果、未运行项、历史有载下界与source分开记 |
| do-not-merge | ignored V11/V12 P/Z/R/A、参数NPZ、原packet/REF7、FE JIT/cache、supervision/完整日志 | 只在NN-Lab，hash绑定不入Git；无global p4 LU、global S/CSR、ILU/Riesz或隐藏fallback |

建议审阅顺序：冻结原action和V11状态→研究数学核→自有窗口／one-run分流→独立checker／损坏证据测试→紧凑负结果。T3有界隐藏优化和块末头提议虽已实现，但本批由真实T2门限阻止，不能据未运行代码授予数值资格。若下一轮需要改变该Gate，应另行正式授权；本轮不做变相阈值放宽。
