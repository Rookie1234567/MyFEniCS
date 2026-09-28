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
