# Targeted tests 与文档复核

本页保留首次失败与修复后结果。完整suite与CI没有运行；检查限定于新增full-FE数学/事务/Riesz及本任务文档，不重跑旧heavy。

| 检查/尝试 | 监督状态/exit | wall / s | 同时树RSS / MiB | own swap / B | 子树清场 |
| --- | --- | --- | --- | --- | --- |
| algebra_and_lint_20260929T104946920206Z | WORKER_FAILED/1 | 1.998625 | 59.152 | 0 | True |
| c3_reference_static_20260929T180338558573Z | COMPLETED/0 | 1.519846 | 38.395 | 0 | True |
| cholmod_dependency_20260929T102823494524Z | WORKER_FAILED/1 | 7.300278 | 146.961 | 0 | True |
| e5_analytic_target_capacity_20260929T182053680758Z | COMPLETED/0 | 1.515314 | 41.074 | 0 | True |
| e5_compact_evidence_20260929T182110831272Z | COMPLETED/0 | 1.519980 | 40.312 | 0 | True |
| e5_independent_raw_check_20260929T182126238712Z | COMPLETED/0 | 2.024982 | 60.969 | 0 | True |
| fe_abi_20260929T102600471321Z | COMPLETED/0 | 3.311251 | 175.434 | 0 | True |
| implementation_checks_20260929T105219053119Z | COMPLETED/0 | 1.974255 | 59.156 | 0 | True |
| ml_abi_20260929T102713264800Z | COMPLETED/0 | 6.851944 | 265.969 | 0 | True |
| optimizer_transaction_20260929T111245150321Z | COMPLETED/0 | 5.494056 | 269.293 | 0 | True |
| pure_algebra_20260929T104743142102Z | WORKER_FAILED/1 | 2.664926 | 83.258 | 0 | True |
| sparse_gram_binding_20260929T104918118890Z | COMPLETED/0 | 2.657193 | 93.379 | 0 | True |
| task_local_ruff_20260929T105023806802Z | COMPLETED/0 | 9.171619 | 114.961 | 0 | True |

相关测试文件为 `src/test/test_feinn_full_algebra.py`（4项）、`test_feinn_riesz_ml.py`（2项）、`test_feinn_transaction_ml.py`（2项）和 `test_optical_material_table.py`（7项）。分别覆盖完整保留内部量的A/Aᴴ/原增广关系、复SPD解及symbolic拒绝numeric、优化外层异常恢复与accepted状态、材料离线hash/插值/边界；不会把纯测试称为物理5nm通过。

首次纯代数检查的fixture键名 `dofs` 与实现 `cell_dofs` 不一致，在C1提交前最小修复，原失败日志保留。scikit-sparse打包缺少Cython，改用系统已有CHOLMOD薄C ABI；没有在旧环境安装。后续source、Ruff/compile、输入解析和相关pytest以实际light记录为准，费用全部计入[研究成本](records/resource_costs_v1.json)。

E1真实制造解/384cell完整矩/原action/Gram、3方向FD与batch1/8、q15/30属于正式one-run接口资格，另见[interface](records/interface_gates_v1.json)。它们不是本页纯测试的替代，也不是候选原方程/场/功率通过。

独立stdlib checker从compact原数值重算方程、字段/复杂幅值、功率、能量和资源；大artifact hashes可在本机加 `--verify-raw`：

```bash
python benchmarks/check_feinn_pilot.py --evidence docs/task042extra_feinn_5nm/outcomes/records --output /tmp/task42extra_gate_recheck.json --verify-raw
```

结果见[Gate](records/gate_decisions_v1.json)，而非仅复述status字符串。FE体积分差由原独立积分保留absolute/denominator；complex E/H与ordered通道从compact复值重新算范数；功率差与闭合由原R/T/A_volume重新计算。

本任务Markdown逐页检查closed fences、math fence、表格列数、UTF-8 replacement及本地相对链接；summary按回顾标准16节且至少8张表。总账只运行相关3项Markdown检查，不宣称历史模型/COMSOL数值重验。解析、实际GitHub rendered view、raw blob一致性、浏览器DOM/截图和明确blocked原因分别见[render记录](records/render_check_v1.json)，本地解析不替代浏览器视图。

实际 GitHub Firefox 首轮检查 11 页（任务书、8页本任务文档、两份总账新节），每张表的浏览器 DOM 列数一致。它发现发布任务书 §5.4 的 `\operatorname{Re}` 和本任务方法映射原式的 `\operatorname{solve}` 均被 GitHub 数学渲染器拒绝。任务书由发布方维护，记录为 `RENDERED_VIEW_FAIL_TASK_MATH`；方法映射已改成 `\mathrm{solve}`，其复核随最终 render 记录提交。截图和完整 DOM 留在本任务 ignored 目录，compact 文件保留 hash，不称该失败检查为通过。

实际数值source是E1 C1、E2 C2及E3/E4各run index；之后证据提交HEAD不会冒充运行源码。运行中的HEAD未移动，提交前与推送后clean核验。

## Review V1 后续 V2 定向测试和保留失败

V2 复用原生FE/ML资格环境及V1 native/Gram/历史/checkpoint，不重新安装或重跑旧E0/E1与full pytest。先运行 `src/test/test_feinn_scaling_ml.py` 的9项定向测试、Ruff/编译/FE环境缩放导入检查，再通过正式one-run的D1资格：合成复数非Hermitian A/Hermitian正定G，固定M5上3个非零复向量、3个非零实参数方向，h=1e-4/1e-5/1e-6中心差分，AD共轭转置、`c=Dy`往返、真实Gsolve、预算/线搜索事务及冻结checkpoint一致性。D1全部通过；原始误差与费用见[scaling checks](records/scaling_checks_v2.json)。D0仅评价4个实存状态，未造Adam500中间状态。

首次compare-only因FE进程顶层导入Torch失败于物理前；最小延迟导入修复提交后，默认沙箱在MPI_Init本地socket处失败；在任务自身监督下完成第三次compare-only。两次失败均保留于[run index](records/run_index_v2.json)与[资源账](records/resource_costs_v2.json)，不是数值失败或参考重算。第三次compare-only复用V1准确同p3参考，MUMPS symbolic/numeric/solve=0。独立checker逐字段复算原40级复通道、参考分母、功率、energy、原方程及`D`来源、冻结物理`c`，结果[严格/研究 Gate](records/gate_decisions_v2.json)均未通过。这是固定优化设置的真实负结果，不能被9项接口测试的通过覆盖。

Markdown局部检查范围扩展到新review、获授权修正的task、Response V2、V2诊断、summary和两份总账新增节；检查fence、表格列数、相对链接、UTF-8及解析结果。GitHub渲染只复查review与修正task，浏览器DOM/截图与失败原因见[render记录](records/render_check_v2.json)。本地解析不等于浏览器PASS，也不宣称CI或全仓测试。

实际GitHub预览在首轮Firefox完整页面加载策略下导航60秒超时，无DOM可判；改用 `pageLoadStrategy=eager` 后只对同两页复核成功。Review V1 的6表/3公式和修正task的6表/7公式均无列错或数学报错，全部24张截图hash一致，抽看review首页/公式和task修正公式/表格。[render记录](records/render_check_v2.json)区分失败与成功两次监督，不能用首次失败代替最终结果，也不声称逐张截图人工精读。

## Review V2 后续 V3 定向资格与保留失败

本批没有重装 FE/ML ABI、BLAS/CUDA，也不重跑整套 E0/E1 或 full pytest。实现源 `d9e5a7d00a1cac82390b058384e0cd9193b472d4` 的轻量 `src/test/test_feinn_reference_fit_ml.py`、事务和完整非 Hermitian 代数共 8 项通过；Ruff、compileall及Git diff空白检查通过。首次 `ruff` 在ML环境因可执行文件不在该环境而于启动前失败，改用原资格化FE环境的Ruff检查通过，没有安装或修改环境。FE import/ABI预检在默认执行沙箱被 MPI 本机 socket 拒绝；依既有最小执行权限重试后，PETSc complex128/int64、FE进程未导入Torch及本任务单核/树RSS/zero swap通过。两次费用保留在[V3资源账](records/resource_costs_v3.json)，不把默认沙箱拒绝记为 ABI 或物理失败。

正式 one-run `v3_fit_checks` 实测合成复数目标相对差`3.01e-11`，真实固定 M5 的 batch1/8 c/loss/梯度差`4.22e-16/0/7.96e-16`；三非零实方向、h=`1e-4/1e-5/1e-6`的全部误差均≤`1e-5`，异常事务参数逐位恢复，训练标签hash与master/背景/port身份锁定。P0 `A(c-c_ref)=r-r_ref` 四态差≤`3.45e-13`、真实Gsolve最大相对`2.15e-13`，不重放未保存的旧状态。[资格原始记录](records/reference_fit_checks_v3.json)、[P0记录](records/error_residual_geometry_v3.json)。

P1 唯一训练被执行会话意外中断；最后完整观察825 closure，第817次已提交参数审核只有指标没有checkpoint，最后保留参数为Adam500。原运行没有`run_summary`/final/last_trial，按[中断记录](records/fit_interruption_v3.json)保守计费，不伪造正常停止。恢复接线的轻量8项pytest、Ruff、compileall及新one-run输入解析通过；P2留存态q30与独立FE审核完成，`q30/q15=2.85841e-12`，MUMPS0、整树峰647409664B/own swap0。独立checker从保存参数/完整c、原Gram、原复E/H样本、40级复通道及独立R/T/A_volume重算，所得场/方程/功率检查均false，并断言监督路线的`pde_only_solver_qualified=false`与`official_candidate_results=false`。[V3 Gate](records/gate_decisions_v3.json)、[资源账](records/resource_costs_v3.json)。首次局部Markdown检查因渲染记录链接尚未落盘而失败；创建明确待发布记录后，Review V2与本轮7页新增/修改文档共8页、38张表的链接/围栏/数学/表列检查通过。精确已发布commit的GitHub实际浏览器渲染8页、11表、7公式，26截图hash一致，抽看Review公式、诊断公式与summary结果表；浏览器树峰2042216448B、own swap0，低于2GiB轻预算。[实际渲染记录](records/render_check_v3.json)保存发布blob与URL，旧task/V1不重复全套检查。没有CI或全仓测试通过的声明。

## Review V3 后续 V4 定向资格

| 检查 / 本地实测 | 结果 | 范围 |
| --- | --- | --- |
| C1 optimizer checkpoint＋fit目标/政策 | 9 passed | 小复数loss、完整state加载等价、Adam→fresh L-BFGS、原子写入中断、真实非零strong-Wolfe异常及接受更新量 |
| 自身进程故障 | 4类通过 | 明确停止、监督报告失效、监督SIGKILL清场、启动端退出/关闭输出管道；未测平台回收路径不声称通过 |
| M5阶段边界资格 | 2次完整loss/gradient，配对差0 | E_G0.20082113406866917、native14.263463207213235；不重跑原Adam500/P0/旧FE Gate |
| C2计时修正与fit政策 | 11 passed、0失败/错误/skip | 包含9项复测及2项launch时钟测试；不是20个独立新测试 |
| FE preflight | complex128/int64、MPI1、Torch未导入 | 复用资格化ABI、task-local activation，无安装 |
| final q15/q30独立重建 | 参数→c=0；q30/q15=8.5141e-13 | 完整边/面/内部矩；固定网络buffers与8966参数匹配 |
| independent FE compare-only | 审核完成；严格方程/场/功率失败 | 负结果如实保留，参考复用，新MUMPS0；不把审核完成称solver PASS |
| compact checker | 冻结state/hash/optimizer与原始复场/功率重算通过 | G matvec仅证据验算，无训练、Gsolve或新因子 |
| Ruff / compile / Markdown / GitHub | 按本轮实际记录收口 | 本地与远端渲染分列，不推断CI |

初始小测试快照见[durability checks](records/durability_checks_v4.json)，后续边界与11项复测见[post-fit checks](records/post_fit_checks_v4.json)，完整检查点见[checkpoint index](records/checkpoint_index_v4.json)。R0小问题同时树≤2GiB、自身swap0；数值阶段逐个监督并清场。原始Ruff/compile/测试/浏览器尝试及所有失败费用在[资源账](records/resource_costs_v4.json)，不full pytest、不重验整套E0/E1，不宣称GitHub Actions通过。

C1正式段的保存留白有计时偏差，作为规则未满足记录；C2已用launcher时钟和150s cutoff修正，并有定向测试，未再次正式执行。旧V3后段状态未恢复，失联原因仍unknown。[新review及V4页渲染记录](records/render_check_v4.json)分别绑定真实GitHub DOM、published blob和截图，不能用本地Markdown代替。
