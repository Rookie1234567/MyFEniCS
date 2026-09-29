# Review V4：冻结四个波长的 Si 材料，解除阻塞并续跑神经有限元试验

## 0. 决定、身份与本批要消除的 blocker

**接受 V6 为材料独立接口的部分实现记录，不授予真实 Maxwell 求解资格。用户本轮直接提供的 0.7 nm／2 nm 数据，加上已核对的 5 nm／13.5 nm 旧输入，构成下表的正式任务材料依据。解除“缺少已授权的 Si 0.7 nm 材料数值及来源”这一输入阻塞；不再要求找回旧数据库文件或另行联网核准后才能运行。**

解除的是材料定义缺失，不是跳过读取、符号、原方程或资源检查。Codex 将表格固化为可复用机器记录、核对实际加载值后，直接完成真实算子接口和已经授权的三路线试验；不只再交付一份材料审计然后等待确认。

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task42_neural_coarse_inverse
worktree                    = /home/fenics/Projects/NN-Lab
review_date                 = 2026-09-29
reviewed_HEAD               = 255ca88e6f4aa2c15252a512d1d499f34c95f042
original_base_SHA           = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review             = review_report_v3.md @ d5f45787168123a1680523ccf8e73c33de7c7a34
latest_response_reviewed    = response_v6.md
V6_successful_interface_src = 2a2cb4af78ba869a26a1254b4b4b76c9ac158366
material_table_id           = SI_OPTICAL_CONSTANTS_USER_20260929_V1
material_definition_gate    = RESOLVED_BY_USER_INPUT_AND_REPOSITORY_RECORDS
material_runtime_gate       = NOT_YET_RUN
next_batch                  = V7_MATERIAL_FIXED_NEURAL_FE_CONTINUATION
response_required           = response_v7.md
old_p4_inverse_route        = CLOSED_RESEARCH_NEGATIVE
final_0p7nm_48h_gate         = NOT_QUALIFIED
master_merge                = NOT_APPROVED
```

最终目标仍为：现有约 2 TB 工作站资源内、端到端不超过 48 小时，得到一个新的、0.7 nm、真正非可分三维周期单胞的合格有限元解。本批沿用 [Review V3](review_report_v3.md) 的微型模型与新计算链，不把微型模型冒充目标规模，不转向扫参／反演代理，也不重开旧 p4 强近似逆路线。

本 review 的新工作属于**物理输入固化＋既定求解试验续跑**。ChatGPT 核对了远程合同、V6 response/summary 和下面列出的历史材料输入，并以十进制高精度算术复算转换值；没有在工作站运行新 PDE、训练或性能试验。

## 1. V6 的审阅边界

依据：[Response V6](response_v6.md)、[V6 结果](outcomes/neural_fe_single_solve_v6.md)、[summary](outcomes/summary.md)、[材料审计](outcomes/records/material_source_audit_v6.json)、[独立 Gate](outcomes/records/neural_fe_gate_decisions_v6.json)。

| 项目／数据身份 | 已取得证据 | 本次判断 |
|---|---|---|
| 实际几何 measured | 384 hexa、p3、FE 34050、独立 trace 18144、slave 2082、notch 8 cells；材料标签具有 y/z 变化 | 可以复用已绑定身份的几何／映射，不重新进行整套 F0 |
| 表示与导数 measured | FE 矩配对约 1.8e-15；合成非 Hermitian 梯度检查最大约 9.76e-9 | 只证明所测插值、MPC 和合成导数；不等于真实 S/Sᴴ 通过 |
| 真实计算 not_run | S/Sᴴ、完整端口、内部恢复、NEURAL-TRACE／FREE-FE-OPT／FE-LSQR、准确参考均未完成 | 没有新神经求解成功或失败结论 |
| V6 资源 measured | 三次正式接口启动合计 26.136697164 s，采样整树峰 314408960 B，自身 swap 0 | 只是接口成本，不是目标求解成本；保留失败与辅助费用 |
| 材料历史 blocked | 当时没有可核准的 Si 0.7 nm 数值，按 Review V3 停止 | 当时的记录正确；本轮收到新输入后解除，不能追溯改写为当时已具备 |

## 2. 冻结的 Si 光学常数：以后直接引用本表

### 2.1 用户本轮原始输入，逐字保留数值

```text
Wavelength (nm), Delta, Beta
 0.699999988  0.000114859526  4.32477054E-06
 2   0.00119851693  0.000213688647
```

这两行的 provenance 是 **user_supplied / user_authorized，2026-09-29，本次材料补充指令**。本 review 及其 Git commit/blob 是可保存、可追溯的来源载体。用户没有在本轮给出原数据库文件名、版本、密度或测量不确定度；这些外部元数据可标 `not_provided`，不得编造为某个 CXRO/Henke 版本，也**不得继续把这些缺项当作本任务使用已授权数值的阻塞**。

不再用 ChatGPT 前一轮基于外部表和密度假设得到的近似数值替换本次用户值；不二次乘密度、不重算原子散射因子。这里使用的是已经给定的材料光学常数，不是待换算的原子数据。

### 2.2 四个波长的主表

Delta、Beta 和折射率均无量纲，波长为真空波长 nm。表中小数按来源的十进制文本保留；13.5／5 nm 的 Delta 由原输入 n_real 精确作 1−n_real 得到，不是新插值或重新拟合。

| nominal wavelength / nm | source wavelength / nm | Delta | Beta | provenance |
|---:|---:|---:|---:|---|
| 0.7 | 0.699999988 | 0.000114859526 | 4.32477054E-06 | 用户本轮直接提供；按 §2.4 显式映射到 nominal 0.7 |
| 2 | 2 | 0.00119851693 | 0.000213688647 | 用户本轮直接提供，且与旧输入 S2 一致 |
| 5 | 5 | 0.00603145547 | 0.00435380777 | 旧输入 S5：Delta 由 n_real 推导，Beta 为 n_imag |
| 13.5 | 13.5 | 0.000997695141 | 0.00182649365 | 旧输入 S13：Delta 由 n_real 推导，Beta 为 n_imag |

**适用对象：本任务定义的 Si substrate 和 Si grating 使用同一个所选波长条目；air 保持 n=1+0i、epsilon_r=1+0i，mu_r=1+0i。** 未来明确指定不同材料或不同 Si 数据版本时，应新建版本，不能静默覆盖本表。本次登记四行不是授权同时运行四个波长的 PDE。

### 2.3 已实际核对的旧记录

以下三份文件均在审阅 SHA `255ca88e6f4aa2c15252a512d1d499f34c95f042` 读取，其 `[materials]` 的 substrate／grating 数值相同。

| ID | 文件／原输入身份 | n_real | n_imag |
|---|---|---:|---:|
| S2 | [original_2nm_si_p6h1p5_native.dat](../../input/task39extra_para_workstation_capacity/original_2nm_si_p6h1p5_native.dat)，blob `0861dc4f55be67463561012c6b8a5c7556f08df9` | 0.99880148307 | 0.000213688647 |
| S5 | [original_5nm_si_p6h4_native.dat](../../input/task39extra_para_workstation_capacity/original_5nm_si_p6h4_native.dat)，blob `a17c4aadf07272d882773b24fa961fd2f349dabe` | 0.99396854453 | 0.00435380777 |
| S13 | [original_13p5nm_p6h10_balanced_h6_p4_v5.dat](../../input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat)，blob `0c5211a0e99b4f1b74ad5e4223b5d91066b57816` | 0.999002304859 | 0.00182649365 |

这些是本项目已使用的输入记录，不冒称本次已独立测量材料，也不补造其最初外部数据库 provenance。两行新用户数据与两行旧输入分别标识来源，不能合并标成“全部来自用户本轮原表”。不得为补材料重新启动旧 workload 或修改其他任务工作树。

### 2.4 0.699999988 nm 与 0.7 nm 的显式别名规则

用户在当前 0.7 nm 任务中提供 `0.699999988` 一行，本 review 将它**明确接纳为本任务 nominal 0.7 nm 的材料条目**。两标签差为 1.2e-8 nm，相对 nominal 值为约 1.7142857e-8；这是十进制算术差，不是对数据误差的物理估计。

计算仍采用冻结的 `wavelength_nm=0.7`，几何、k0、入射相位和所有通道计算均以该 nominal 波长为准；材料 Delta/Beta 原样取用户行，不做插值。原始标签 `source_wavelength_nm="0.699999988"` 必须保留，记录 `nominal_wavelength_nm="0.7"` 及明确的 alias reason，不反过来把求解波长偷偷改成原标签。

只登记这两个标签之间的显式对应；禁止使用宽泛 `isclose`／nearest-neighbor 将其他波长混配到本行。其余 2／5／13.5 nm 按各自条目匹配。未登记的波长不自动沿用、插值或外推，需要单独的数值与来源授权；不影响已登记四行的可用性。

## 3. 转换为复折射率和介电常数

沿用仓库时间约定 exp(−iωt)。本任务按以下关系写入复数材料，Beta 为正时虚部为正。

```math
n=(1-\delta)+i\beta,\qquad
\epsilon_r=n^2=\bigl((1-\delta)^2-\beta^2\bigr)+i\,2(1-\delta)\beta,\qquad
\mu_r=1.
```

必须是复数平方 n*n，不是 abs(n)**2，不是 n 本身，也不使用 epsilon≈1−2Delta+i2Beta 的近似来替换完整公式。Delta 不是介电常数，Beta 不是介电常数虚部。以下值是**依据主表推导的转换检查值**，额外小数位只用于检查实现，不表示材料有相同位数的实验精度。

| nominal nm | n_real | n_imag | epsilon_r real / derived | epsilon_r imag / derived |
|---:|---:|---:|---:|---:|
| 0.7 | 0.999885140474 | 0.00000432477054 | 0.9997702941220070727210241084 | 0.00000864854759781143367192 |
| 2 | 0.99880148307 | 0.000213688647 | 0.997604356919993639934291 | 0.00042686507507764341258 |
| 5 | 0.99396854453 | 0.00435380777 | 0.9879545118729884805480 | 0.0086550959446206099962 |
| 13.5 | 0.999002304859 | 0.00182649365 | 0.998002269034540884687381 | 0.00364934273232065529070 |

0.7 nm 新正式输入的显式值应为以下片段。它只是材料片段，不是完整 one-run dat，不包含任何旧求解器／无时间限制 profile 授权。

```toml
[materials]
n_air = [1.0, 0.0]
mu_r = [1.0, 0.0]
substrate_name = "Si / silicon"
n_substrate = [0.999885140474, 0.00000432477054]
grating_name = "Si / silicon"
n_grating = [0.999885140474, 0.00000432477054]
```

运行时用 complex128。读入原字符串后可用 Decimal 复算主表与转换表，再与运行时 float64/complex128 做舍入一致性测试；例如绝对差不超过 16 个 float64 machine-epsilon 乘 max(1,目标绝对值)。该阈值仅为算术实现检查，不是物性不确定度或 Maxwell 残差门限。无需因材料未附 photon energy 而阻塞：原模型由真空波长驱动；若需要能量，单独由 SI 常量计算并标 derived，不冒充用户提供。

## 4. 永久固化与防止再次因同一材料缺失停机

本轮由 Codex 新建或在已有合适 registry 机制上登记 `input/materials/si_optical_constants_v1.json`，ID 固定为 `SI_OPTICAL_CONSTANTS_USER_20260929_V1`；若复用既有等价目录，应在输入 README 明确唯一 canonical path，不能产生两个可相互漂移的来源。

机器记录保存十进制字符串和表版本，至少包含：nominal/source 波长、Delta/Beta、n/epsilon 检查值、time convention、用户原始两行、source_kind、原始来源日期、本 review 路径和实际 Git commit/blob，以及 S2/S5/S13 的冻结 path/commit/blob。保留 `external_dataset_version=not_provided` 等真实边界；不为通过 schema 伪造 URL、密度或测量证书。登记文件本身计算内容 hash，不把自身 hash 写入自身而形成循环。

以后任务读取本表或由它显式展开 n 至 `.dat`；现有输入 schema 无材料引用能力时，允许新 Task042 opt-in reader／sidecar 保存材料 ID 与 hash，并把解析后的 n 写入 resolved_config/manifest，不必为了一个表重写普通输入 schema。原始 dat、有效 n/epsilon、材料 hash、mesh/完整通道身份和源码 SHA 都随 run 保存。背景基底材料、下端口材料和体材料必须取同一个已选条目，避免不同路径各用旧默认。

必要回归应一次覆盖：四行转换、0.7 显式 alias、2／5／13.5 与旧输入一致、未知波长拒绝、正吸收符号、air／mu、完整精度保存，以及离线读取无需网络。材料正确载入后新状态应为 `MATERIAL_READY_USER_SUPPLIED`；若是 loader/schema/path 错误，标 `MATERIAL_WIRING_ERROR` 并最小修复，不再回报“旧 Task039 没有材料”或要求用户重复提供同一表。

**本表已经满足本批材料数值与来源授权。原数据库、密度和网页查询不可用不是再次触发 `MATERIAL_0P7NM_BLOCKED` 的理由。** 若实际文件损坏、数值与本表冲突或今后出现用户明确覆盖，则保留针对性 integrity/conflict Gate，不能为了“永不阻塞”悄悄用错误数值。

更新本分支 input/README、Task042 README/summary 和项目总账的当前入口，指向材料 ID 与本 review。V6 及更早的 blocked 记录逐字保留，在新段落说明本轮解除，不改写过去的 physical hash。其他分支／运行不会被此文件自动改变；未来采用本表须在各自输入和 run provenance 中明确绑定。

## 5. 已授权的继续执行顺序

本 review 接续 Review V3 的 N0–N4，**仅替换其 §5“必须从旧库取得材料，否则停止”的前提，并明确 V6 后可继续执行**。以下步骤完成前置 Gate 后可连续推进，无需逐小步再次请求确认。旧 p4 路线保持关闭，不执行 V5 augmentation，不增加其他波长 campaign。

**M0：固化并加载材料。** 建立机器记录与 targeted tests，保持原 384-cell/p3 缺口几何、grazing1度、phi0、s 和完整双 Floquet/DtN。绑定 nominal 0.7 和所选 Si 数据，重新计算完整上下端口 inventory，包括 key、极化、归一化与材料来源；不能把 V6 空气侧20通道当总量，不能硬套旧80通道。完成本次物理 hash 和完整容量估算；旧 unresolved design hash 不冒充新 physical operator hash。

**M1：补完真实算子与导数。** 复用已资格化的矩映射、MPC、网格和分块 VJP，不因文档 SHA 变化重复安装／完整 F0。实现本目标的单层凝聚 S 和 Sᴴ、非零端口、内部恢复及独立 native 验算。材料改变会影响真实方程，因此相关物理 Gate 必须实测。Sᴴ 是共轭转置乘法，不是另做伴随方程求逆；候选不建 global p4 层、不保留见证 CSR或全局因子。按 Review V3 的非零实参数方向差分、dot test 和 chunk 配对完成真实 N1，合成195维自检不替代它。

**M2：顺序完成 NEURAL-TRACE／FREE-FE-OPT／FE-LSQR。** 同一原 S/Sᴴ、RHS、约束与材料，同样零散射初值，互不 warm start，不读取目标准确解。保持既定3×64、8载波、seed420906、FP64网络，以及原未加权完整Schur平方残差；不扩大结构、扫loss权重或引入隐藏强逆。端口未知量完整参与，所有元素贡献先正确组装再取全残差范数，不以采样loss或单元平方和替代。

**M3：冻结结果后独立验证。** 三条路线结束并冻结 checkpoint/hash 后，按原预算执行独立同mesh/p3准确参考，不把参考结果用于回训或初始化。仅在同离散资格通过且预算足够时，做原合同允许的一次p4 enrichment作为离散误差对照；这是新目标的参考，不是恢复旧p4预条件路线。未通过原残差的场不输出official结果。

**M4：收口。** 将材料与物理输入、新求解结果、负结果、资源和48小时未知项分开报告。目标级几何／资源配额尚未冻结时继续标未知，但不能以此阻止已经批准的micro-pilot。有限试验结束后等待review，不自动放大或启动完整48小时目标运行。

## 6. 精度、资源与停止条件不放宽

数值与物理 Gate 全部沿用 Review V3 §6–8：真实算子／约束／恢复配对1e-10；梯度差分稳定区1e-5；完整原Schur及未凝聚增广相对残差1e-6；端口同时检查绝对／固定RHS尺度／operation-relative；同离散E/H、scaled-curl和完整复通道1e-4；R/T/A/A_volume差1e-5、每通道功率1e-6、能量闭合1e-5；条件p-enrichment差目标1e-3。完整散射场／相对背景变化也要检查，不能靠弱材料对比和零散射混过Gate。详细近零规则不被本摘要覆盖。

保留500次Adam、lr1e-3，然后history20／strong-Wolfe L-BFGS；每条优化路线总完整closure最多2000且wall最多2小时。LSQR最多2000次S/Sᴴ配对作用且2小时。V6至本次续跑的新数值有载总wall仍累计不超过10小时，包含已发生的26.136697164秒接口启动和其余按原口径应计费用；不因版本升级重置预算。首次使用的三条路线之前均未启动，其路线计数从0开始。所有线搜索closure与S/Sᴴ次数计入，不按optimizer外层更新掩盖成本。

受控共享CPU授权继续：其他heavy存在不是自动阻塞，不争用GPU；MPI1、数学／Torch线程1、DataLoader0、现场选空闲物理核和避开忙碌SMT同胞。Task042自有nonblocking锁、内部顺序运行、独立FE/ML环境与缓存；nice10／idle I/O只作用自身。整树RSS hard16GiB／warn12GiB、own swap0、无OOC、磁盘至少50GiB、artifacts上限20GiB；系统reserve=max(128GiB,effective_total的10%)、邻增长128GiB及本任务预算均保留。只有采样watchdog时如实报告0.5s采样，不冒称cgroup连续限额。

只监督／停止本任务后代，不修改邻任务、共享锁、环境、HEAD、亲和性、优先级或watchdog，不升级ABI/CUDA/BLAS。资源／算子／数值真实失败仍要保存并停止受影响阶段；不回到旧p4 PC、不扩大范围扫描。共享计时标shared-workstation，不能承诺零邻影响或无争用加速。48小时是最终目标的端到端预算，不是本review已经证明的能力，也不是当前开发的时间承诺。

## 7. 提交、证据与 Response V7

所有正式FE阶段仍通过 `python scripts/run_case.py input/task042_neural_coarse_inverse/<one-run>.dat`。新输入独立命名，不覆写 V6 unresolved dat/records。每次运行前提交clean实现、核实branch/upstream及资源并记录真实source；文档HEAD不冒充运行源码。数值核进入合适src模块，runner只补必要opt-in参数；不为四个材料条目复制四套脚本，不整体merge其他分支，不全仓清理或无故full pytest。

建议提交：C1四波长材料记录、解析与回归和入口；C2真实S/Sᴴ／恢复／梯度；C3三路线与条件验证；C4 compact结果和response。本次ChatGPT只新增本review，机器记录、代码和运行由Codex实现，不声称已部署材料loader。

最少新增交付为机器材料记录、`response_v7.md`、`outcomes/neural_fe_single_solve_v7.md`，以及 compact 的材料载入与来源、完整通道库存、真实梯度检查、三路线比较、独立Gate、run index与48小时预算记录。同步本分支Task042的summary/test_summary/changed_files、development_progress和development_model_registry。新记录链接旧证据，避免复制巨大嵌套JSON；场、模型checkpoint和数组留在ignored目录。

Response V7首先报告实际完整HEAD与source，四个材料条目是否已可离线读取，0.7实际采用的n/epsilon、alias与hash，完整端口数和真实物理身份；随后说明真实N1和三路线各做到哪一步、残差/物理/离散/资源/神经增量分别如何。材料已存在而后续数值失败时必须报具体数值失败，不再以旧材料来源不足笼统收口。未运行项明确原因。

仅推送 `git push origin HEAD:refs/heads/task42_neural_coarse_inverse`；不amend/强推、不改旧task/review/response/负结果，不操作master或其他工作树。推送后停止等待ChatGPT review。**本次材料解除不构成merge approval、完整N1通过、神经解通过或最终0.7nm／48小时通过。**
