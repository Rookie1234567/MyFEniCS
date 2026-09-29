# 本轮实际测试、失败与文档检查

| 检查 | 真实结果及范围 | 证据 |
|---|---|---|
| strict协议/PC/表示 | 33原协议测试、局部block容量/complex/input、streamed POD对精确SVD/native Gram/固定线性PC | 前期40/41项bounded array检查；最终focused数量与source见[final](records/final_checks_v2.json) |
| 真实FE配对 | F1 A4=PH A6P、primal/dual、p4 assembled与独立cell作用、非零内部/port制造解 | [F1](records/f1_real_components_v2.json)是物理组件资格；不同于toy或正式p6场资格 |
| borrowed p4/default | caller-owned p4材料化witness与默认拒绝/无所有权转移；真实80mode complex序列化保持相位 | paired tests与实际F1通过；最终同focused FE checks |
| resource enforcement | setsid grandchild触测试128MiB门仍被清场，独立sibling未被信号 | [bounded前期](records/shared_preimplementation_checks_v2.json)与最终focused watchdog验证；未控制邻任务 |
| teacher/表示/模型 | 384对原native/port/internal/恒等式<=1e-10；native像核验；CPU float64 intra/inter1 Loader0；Torch/NumPy probe | [teacher](records/teacher_complete_v2.json)、[oracle](records/oracle_complete_v2.json)、[训练](records/training_complete_v2.json) |
| strict F4 | 同16 heldout ×3候选；所有非零256步后未达到1e-10，zero自身精确0 | 独立raw Gate重算，[48项CSV](records/strict_rhs_metrics_v2.csv)；失败完整state/历史本地保留 |
| 本轮最终测试/静态 | targeted source regressions、Ruff、compile、bash、diff，Markdown表格/围栏/链接/JSON/CSV/原历史合同 | [final checks](records/final_checks_v2.json)、[独立静态](records/static_checks_v2.json)；dirty文档检查不冒充clean数值source |
| GitHub发布渲染 | push后检查真实exactHEAD的summary/架构/response_v2/两总账richText表格/标题/公式renderer | [publication](records/publication_checks_v2.json)；没有浏览器像素截图资格 |

此前接口错误与修复按原attempt保留：缺pyvista→独立固定依赖；CFFI缺setuptools→NN-Lab setuptools及complex CFFI probe；材料化p4被旧默认拒绝→显式borrowed witness/paired tests；mode包含complex且one-element数组需保留形状→定向metadata修复。没有改变p/h/通道/残差/FGMRES budget。F4-B0手写schema enum遗漏在正式数值前被静态parse拦截，一次局部修复/all-phase input test后运行，旧28a8 source没有formal负载。原失败resource与blob/hash记录均保留。

F4 zero路径会直接返回精确零、不调用backend；原报告字段沿用前次`audit.last`，数值zero检查正确但该附带native_audit不是本次。交付前仅修正记录条件，旧raw不改、v2置null并明确说明；算法、误差门和已运行source不变，不因报告修复再作正式数值重放。

首次广一点的affected input-schema检查为57pass/2fail；两个fail在精确起点a76e0435a40139dd6d2a31f0726fb229c7adaff8旧input_schema与README上复现：字段97预期/110实际，README行102实际/115预期。这是继承schema2文档枚举不一致，未增公共字段，不修改无关旧合同来制造全绿。受影响targeted regression56通过及最小input tests通过，见[前期检查](records/shared_preimplementation_checks_v2.json)。全仓pytest、MPI2/4、本任务GPU和F5物理验算not_run；用户仅授权共享受控阶段，任务仍禁止邻heavy下full pytest。没有CI声明。

各安装/probe/数组/serial FE接口/静态采样完整wall/RSS/swap、source和worker hash见[auxiliary账](records/auxiliary_costs_v2.json)；数值组件单列[run index](records/run_index_v2.json)，不重复相加同阶段RSS，不以pytest内计时替代监督wall。原F0记录在[历史bounded runs](records/bounded_f0_runs.json)、[原static](records/static_checks.json)、[原publication](records/publication_checks.json)完整保留。

所有测试和后处理Math threads1、仅自身nice/idle I/O、fresh现场选核及bounded监督。最终Markdown本地实际生成HTML并核对表格/标题/链接；local markdown-it的math按code展示，推送后用GitHub真实math-renderer核对，不能只凭本地预览宣称公式显示资格。

最终协议/表示/监督器44 passed（11 deselected），小型FE/80mode/默认与noncommuting/BAL_H18 passed（1 deselected），治理/文档27 passed。额外旧总账checker为1 failed：其40节固定序列和旧Task038缺失evidence在精确a76已存在；Task042表头缺失已在V2局部补成统一格式，基线对比当前无新增错误。[完整基线proof](records/registry_contract_baseline_v2.json)保留原失败及修复后剩余两项错误，不删历史章节、不改测试期待，也不称全仓全绿。Ruff0.16.6对20个新源/协议/测试文件通过，41个相关Python定向compile、bash与diff通过；没有重新运行昂贵F1–F4。


## V3 最新有限诊断的实际检查（V2历史完整保留）

| 检查 | 实际结果 / 范围 | 证据 |
|---|---|---|
| 前期pure/准入 | 48纯数组/协议/表示/几何、4准入与自有监督；首次lint阻断未执行tests/FE，全部尝试保留 | [辅助成本](records/auxiliary_costs_v3.json) |
| FE小接口 | ABI/complex128/int64、几何MPC主从支撑、原borrowed witness/80mode/default，4 passed；未重跑teacher/F1正式算例 | 本地tmp/task042/v3/overlap-fe-support-tests、[环境](environment_and_isolation.md) |
| 最终pure/source | 49 passed；11个相关Python定向compile，10文件Ruff无问题，input_schema仅对经proof的ISC004/RUF022作本次限定；bash/diff通过 | tmp/task042/v3/final-array-checks-complete；[继承schema lint proof](records/schema_lint_baseline_v3.json) |
| 资源测试真实失败 | 首次汇总observed_child_pids只记1，但原RSS样本含2后代及setsid孙进程，触128MiB测试门并整树清场、sibling仍活；另一次修复后lint未使用变量失败保留 | [原始样本与修复](records/watchdog_test_evidence_v3.json)、辅助账 |
| 资源测试最小修复 | 只把测试断言改为原始整树samples的后代/setsid证据，监督器与数值实现不变；49项重跑通过，不重跑任何数值 | src/test/test_task042_shared_watchdog.py；[冻结源码 proof](records/static_checks_v3.json) |
| 新正式残差 | 3项各0..256每步，reported/显式/独立native/port/internal与恢复，原字段重算5条件全部<=1e-10才passed，三项failed | [Gate](records/gate_decisions_v3.json)、[完整CSV](records/full_residual_history_v3.csv) |
| 文档/治理/原历史 | 定向治理/表格测试与V3独立表格/链接/围栏/Gate/hash/source/旧正文保护；结果见static，不冒充全仓CI | [独立static](records/static_checks_v3.json)、[继承registry proof](records/registry_contract_baseline_v3.json) |
| GitHub发布 | 首次push后实际exactHEAD richText表格与math-renderer，最终文档bytes保持一致；见实际检查，不称像素截图 | [publication](records/publication_checks_v3.json) |

扩大Ruff范围时input_schema原有12条诊断（11 ISC004、1 RUF022）与本轮起点d42逐项源码片段一致，未改旧schema错误。原schema字段/README枚举及总账40节/Task038历史问题不因V3改为green；registry检查当前与起点的错误相同。raw失败尝试完整保留，未放宽数值Gate或迭代预算来重跑。

全部检查单核math1、nice10/idle I/O、fresh现场核与自身2GiB整树监督；辅助wall/RSS/swap/source/命令/失败均在新v3账，V2记录逐字保护。新数值仅两个分进程阶段，CPU12 reuse、CPU0 structure，真实clean source各自绑定。旧16heldout消费边界、fresh未运行、teacher/训练/误差空间/F5/正式物理/GPU/短波not_run。未运行full pytest、MPI2/4，也没有CI声明。辅助峰为顺序树峰的最大，不是会话总峰；编辑/Git/审阅未持续采样。

V3治理/文档表格定向测试28 passed；registry当前继承两项错误与d42完全一致。首次独立static因其结果文件尚未生成而报告三处自身链接缺失，真实FAIL副本和辅助尝试保留；生成结果文件后仅重查静态链接/Gate，不重跑数值。

## V4 最终有界检查（V1–V3正文逐字保留）

| 检查 / 身份 | 实际结果 | 证据与范围 |
|---|---|---|
| 执行前相关协议/局部PC/准入/监督 | 57 passed；affected algebra/Gate 9 passed；FE monitor/ownership/full80/default 6 passed | [pre-run记录](records/pre_run_checks_v4.json)，均有界单核，未重复F0环境安装或旧384 teacher |
| P4隐私局部修复 | 6 passed、1 deselected；source core blob未改、未生成fresh数组 | [修复记录](records/p4_privacy_repair_v4.json)；不重放P0/P1 |
| 最终affected + Markdown | 17 passed in 1.04s | `tmp/task042/v4/final_focused/worker.log`；两层5、独立Gate5、monitor2、Markdown5，真实PETSc小fixture无FE JIT |
| 最终ABI | complex128/int64、MPI1、PETSc3.19.6；资格化activation/独立src与缓存 | `tmp/task042/v4/final_environment_fe.json`；preflight在pytest前，原生prefix仅只读 |
| 真实P0/P2算法资格 | rank4及双rank128、真实原S/native配对、四恒等式通过 | [空间/真实代数](records/coarse_space_algebra_v4.json)；不是收敛资格 |
| 真实P1/P3独立checker | 16train/128误差的teacher与S-error关系合格；两路线strict0/3，P4未解锁 | [快照](records/training_snapshot_manifest_v4.json)、[独立范数Gate](records/gate_decisions_v4.json)；六次负结果不改为成功 |
| 静态检查 / 历史保护 | 新10文件Ruff/format-check、11文件compileall、diff，101旧文件byte-exact；summary旧suffix、test_summary/项目总账旧prefix | [final static](records/static_checks_v4.json)；仅检查V4局部链接/表格，不做全仓清理 |
| 继承总账checker | Review333f与当前错误、实际41节数一致，BASELINE_IDENTICAL_NOT_GREEN | [基线proof](records/registry_contract_baseline_v4.json)；40节固定序列与旧Task038缺失路径仍继承，不改期待或伪称通过 |
| GitHub实际表格/公式 | Review333f的7表/5math-renderer检查已通过；V4发布后按实际提交检查 | [Review render](records/review_render_check_v4.json)；publication记录与原源码/Markdown哈希绑定 |

所有测试/聚合/后处理顺序在Task042 own lock、现场单核/math1、2GiB有界辅助监督中执行，own swap0；费用与原失败尝试见[本批辅助账](records/post_checks_v4.json)，不叠加嵌套timer。静态helper首次因相对Path不符合checker接口失败，保留1.98289s/38633472B/清场证据；只修正绝对路径并重查静态，没有数值重放。正式六阶段整树wall1534.00828393s、最大同时RSS1128828928B；共享工作站成本，不宣称CI、全仓pytest或无争用加速。正常数值停滞没有当bug，未重试、未扩参数或重跑旧昂贵Gate。full repository pytest/MPI2/MPI4/新teacher/训练/P4/F5均not_run，本批数值入口仅MPI1。


## V5 固定对象诊断检查（历史正文逐字保留）

| 检查 | 真实结果 / 限制 | evidence |
|---|---|---|
| 执行前相关pure/core/适配/协议 | 55 passed in1.50s；另9 adapter/准入/monitor/orphan监督通过，原default/full80/source不改 | [前检](records/pre_run_checks_v5.json) |
| 反例与正常例 | 旧四恒等式不保证补空间；复杂相位/尺度/零/不可变/精确小LS验证 | 新test_task042_fixed_localization.py；不把toy当FE结论 |
| 真实D0/D1 | 12可用，9历史native exact；3旧参考原A4/port/恢复<=1e-10 | [状态](records/common_state_manifest_v5.json)、[teacher](records/teacher_exception_v5.json) |
| 原同向量独立审核 | 24作用/192原方程审核/2补空间full-image重算合格，solver strict0/192 | [独立Gate](records/independent_checks_v5.json) |
| 最终文档/静态 | Markdown5；新8文件Ruff与5新文件format、9compileall、diff；继承schema及registry错误同Review91 | [static](records/static_checks_v5.json)、[baseline](records/registry_contract_baseline_v5.json) |
| 历史/隐私保护 | 原task/review/response/records逐字；summary旧suffix、test/总账旧prefix；基与冻结核hash不变、seed420620未消费 | static与原unconsumed plan；无全仓cleanup |
| 真实GitHub表格/公式 | Review91的5表/7math-renderer通过；新文档发布后实际HTML绑定推送HEAD | [review](records/review_render_check_v5.json)、[publication](records/publication_checks_v5.json) |

早期FE .venv无ruff模块，子命令真实失败；改用已有只读ruff0.16.6后修复一处新RUF005风格，未安装/重放数值。失败尝试全部保留[辅助成本](records/post_checks_v5.json)。四新FE阶段wall1144.401529s、最大同时树RSS1135407104B/own swap0，源`5d82651af0f723c73487783deb43969f05d46ed3`；所有成本shared-workstation，嵌套计时不相加，总会话编辑/Git/RSS未持续采样。full pytest/CI/MPI2/MPI4、旧teacher384、训练/新KSP/fresh/F5均not_run。


## V6：材料独立的神经FE接口检查

最终23相关pytest通过（几何／未知材料／input opt-in／复数梯度／Basix完整矩／原shared组件与orphan监督）；两项CPU-only ML无fixture断言通过，实际OpenBLAS和Torch intra/inter-op1。新增代码Ruff/format、compileall及两dat校验通过。初次预检查2项配置字段失败、2项complex空气波数失败、ML缺pytest均保留；标准库执行相同两断言，未安装环境。正式FE第一次因原[0,L]载体与新居中范围不符失败，唯一research坐标修复后FE／ML各一次成功，不扩大数值预算。

实际FE矩／MPC配对约1.8e-15，非平凡orientation96 cell／5类；NN q15/30差1.1695e-15，非零合成非Hermitian192trace＋3port的三实方向FD最大9.7612e-9，chunk／一体梯度差6.8049e-16。真实0.7nm S/Sᴴ、native/port/恢复、NEURAL/FREE/LSQR／参考／场／功率not_run：材料缺失；不称完整N1或物理解通过。独立聚合只重算已存FD字段、canonical tags和hash，不重放FE或网络。

[pre-run](records/pre_run_checks_v6.json)、[C1静态](records/precommit_static_v6.json)、[唯一正式修复](records/centered_geometry_fix_v6.json)、[C2静态](records/centered_fix_static_v6.json)、[接口](records/adjoint_gradient_checks_v6.json)、[源／资源](records/run_index_v6.json)、[精简checker](records/independent_evidence_checks_v6.json)。Review V3实际GitHub4表／4math渲染通过。最终文档／原权威保护／继承registry baseline及发布检查另列；不执行full pytest、MPI2/4或旧campaign，不声明CI。


## V7：真实材料、真实N1、三路线及盲验证

| 检查／实际范围 | 真实结果／边界 | evidence |
|---|---|---|
| 四波长材料回归 | 7通过；原decimal/复平方/正吸收符号/历史一致/单alias/未知拒绝/离线；无四波长PDE | input/materials/si_optical_constants_v1.json、test_optical_material_table.py |
| 真实N1 | 原S/SH/native/nonzero内部+port/恢复配对<=8.491e-15；三方向9FD最大1.8213e-9、chunk0 | [real检查](records/adjoint_gradient_checks_v7.json) |
| 固定预算／ML回归 | CPU-only FP64完整2000closure/Adam500断言，small gradient不作pass；既有ML无pytest用标准库执行原断言，不安装 | tmp/task042/v7/optimizer_final_regression/worker.log |
| p3参考接线与最小修复 | 首次29相关pytest；UFL Form除法后4个targeted通过，恢复后仅FE/EH/功率25.633s，无新LU/solve；14.456s失败保留 | [原参考／重放](records/independent_blind_validation_v7.json) |
| 最终相关pytest | 32 passed in1.85s；真实材料/complex action/LSQR/CSR/有效UFL forms/独立Gate反例/trace/basix | tmp/task042/v7/final_focused_tests/worker.log |
| 独立数值checker | 忽略saved status，从原审核字段/复E/H/全port重算；0/3方程/场/功率通过，参考准确；未重复FE | benchmarks/neural_fe_gate_check.py、[独立决策](records/neural_fe_gate_decisions_v7.json) |
| 静态／历史／文档 | 新增相关Ruff/format/compileall、局部表格/链接/公式及原authority/records byte保护，最终记录另列 | records/static_checks_v7.json；无全仓清理/昂贵回放 |
| Review V4实际GitHub显示 | 4表/1math-renderer、列一致，review未修改；新文档发布绑定实际commit和Markdown hash另列 | [review](records/review_render_check_v7.json) |

测试命令一次不存在文件名no tests ran/2.281s，随后更正真实路径并通过，费用保留；一个纯metadata查询把epsilon属性误称epsilon_r已更正，loader/材料/FE未变化。所有正式source/失败/修复/训练预算及辅助成本见[run index](records/run_index_v7.json)、[费用](records/resource_costs_v7.json)。32测试不代表三路线收敛或CI；本批MPI1 only，无full repository pytest/MPI2/4、环境安装、旧campaign或继承checker全仓清理。旧封存seed420620未生成/读取/消费。
