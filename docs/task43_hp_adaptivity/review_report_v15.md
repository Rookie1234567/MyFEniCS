# Task43 正式审阅 V15：接受固定 seed8 诊断，授权同位置 p 加密配对实验

## 1. 固定身份与总裁决

审阅日期：2026-10-27。审阅和提交只作用于 `task43_hp_adaptivity`。

| 项目 | 固定身份 |
|---|---|
| 仓库／唯一执行分支 | `Rookie1234567/MyFEniCS`／`task43_hp_adaptivity` |
| 本轮被审提交 | `1290b4f283c01d81f23ba9e1a187458d24bde2af` |
| 本轮变更基点 | `12c7d4b2d35d033defead807e3e4c5d3407dc85f` |
| P5 实际运行 HEAD | `e1ca85df5e181daec7f0e4715e6d43038a1683a2` |
| 上一份已提交正式执行 review | `37f3376be410657fbaec86b0412086745419c506`，`review_report_v12.md` |
| 科学补充任务书 | `supplement_v11_scientific_restart.md`，原提交 `70e2cfdcc3e5a7c3be5e8b714076420e3eac1129` |
| 长期数值基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |

审阅开始时，远端分支正好位于被审提交。base→HEAD 为线性新增 11 个提交、126 个变更文件；P5 运行 HEAD→交付 HEAD 只有一次文档／证据提交，研究源码及测试未变。未将交付提交追认为旧运行 HEAD。工作站 clean、upstream、ahead/behind 的陈述与远端相容，但本审阅没有访问 canonical worktree，不能独立认证其本地工作树。

**总裁决：接受本轮已完成的有限工程修复、固定 primary 恢复及 seed8 小 h 科学诊断；原两次正式 FAILED 保留。当前证据不足以接受新自适应状态或整体精度。明确批准第9节的下一项科学任务：从同一 R9 父状态，仅将同一 global cell 8 的 p5 提升到 p6，完成与既有 H8 的配对比较。新增一个专用正式槽及最多五个支持槽，主控逐门核实后连续执行，不为成功阶段另等 review。**

“配对比较”是固定同一个位置，分别观察切小单元的 h 动作和提高多项式阶次的 p 动作，测量输出改善与增加的独立未知量。它回答动作选择问题，不保证这个位置足以解决全部误差，也不授权继续换位置试算。

| 裁决维度 | 结论 |
|---|---|
| 工程修复／保存场恢复 | **有限接受**；未发现恢复重新求解、追加 correction 或放松 raw 数值门。新 fresh phase 的 writer 收口必须按第9节先验证 |
| 固定 seed8 科学诊断 | **接受其受控负结论**：两阶均无超过冻结尺度的明确输出收益；不是所有 h/p 无效 |
| 资源与费用 | Git 可见实值内有限接受；失败全计费。完整工作站资源流、trace、NPZ 未亲验 |
| 下一步运行 | **明确批准 R9_P8 一解及其限定支持链**；其余模型、扫描、旧槽复活均不批准 |
| 科学资格 | 空间／选择 PARTIAL；精度 NOT_PASSED；同精度全过程成本 NOT_ESTABLISHED；迭代 NOT_RUN / NOT_QUALIFIED |
| 实际合并许可 | **没有 merge approval**；本报告不执行合并，也不授权任何依赖组实际合入 master |

第9节是下一轮唯一执行授权。它前瞻新增一个有限实验，保留旧任务书、合同、失败、review、accepted9/R9、R10 拒绝和所有历史运行身份。

## 2. 实际审阅工作与证据可见性

已阅读三层 AGENTS、仓库工作原则、Task43 任务书、V11 科学补充任务书、V11/V12 正式 review、V13/V14 相关回应、V15 回应、授权与恢复绑定、机器结果、当前导航／summary／manifest／模型总账／进展；检查本轮全部提交差异，逐函数追踪三个研究入口及测试，并沿引用检查共享恢复、残差、writer、场和模态比较实现。固定提交中没有 `review_report_v13.md` 或 `review_report_v14.md`，没有凭回应假定存在新的正式 review。

本次下载全部 126 个变更文件，另读必要权威文件和依赖；初次下载集合为 140 个 HEAD 文件及四个 base 源文件，144 份均按 Git blob 算法与固定提交返回身份核对一致。另按固定 SHA 读取相关共享代码与旧 R9/R10 记录。核对四个改动 Python 的最终 SHA256、五份原 JUnit XML、launch／终态／退出文件、轻量 trace 原行和资源摘录，未把 PASS 标签当作验证。

本审阅用标准库对 Git 比较 JSON 重新枚举完整 R13 键集合，核各通道功率差、四组复幅差范数、场范数归一关系、J 的全部分量、最大值、两阶分类和新增 FE 收益。P5 作了 5,068 次标量相容性比较，A1 作了 620 次；包括跨 q 的重复模态，**不是独立观测数量、pytest 节点或 NPZ 原数组复算数量**。审阅脚本首次错误地要求两个并列最大 J 分量具有唯一字典顺序，修正为“所报 witness 的数值等于真实最大值”后复核；这是审阅脚本的局部错误，不是仓库失败。

| 证据层级 | 本审阅实际范围 |
|---|---|
| 亲读的 Git 文件 | 固定代码／diff、JSON、XML、shell、主控算术和终态审计脚本文本、完整已提交的比较实值 |
| 亲读的 Git 运行摘录 | P5 全部 62 个 affinity syscall 原行、三个 setter 栈、七个退出尾段；提交的首／峰／尾资源行与 Z 态异常摘录；其余阶段的相应轻量终态 |
| 历史复用 | R9/R10、旧 A2、早期能力限制及未受改动影响的具体测试节点；不等于最终整文件重跑 |
| **未亲验的工作站原件** | 全部 primary/checkpoint/field NPZ、现场 source/input 快照原文件、十次完整 stdout/stderr、P5 七份完整 trace 共1,506行、完整1,741条 resources 流及其他完整运行流 |
| 本次没有执行 | 项目导入、pytest、collect-only、ABI探针、归档脚本、构网、旧场采样／积分、独立 A6 算子作用或 PDE |

工作站待追溯原件具体位于 `benchmarks/artifacts/task43/v11_science/` 下的 `formal/A1_q_attempt3/`、`formal/R9_H8_attempt1/`、`support/union_comparison_attempt1/` 及 `recovery_v15/`。逐项路径／hash 见 [V15证据导航](outcomes/records/v15_bugfix_sources/README.md)、[P5联合终态](outcomes/records/v15_bugfix_sources/P5/P5_joined_root_closeout.json)、[P5资源/trace摘录](outcomes/records/v15_bugfix_sources/P5/trace_resource_excerpt.json)和各 launch manifest。哈希是身份绑定，不是本审阅已访问原件的证明。无需为外审可见性重跑旧 PDE；下一运行前只核实际消费的原件。

## 3. 按严重性排列的问题、影响与验收

### V15-01｜高，科学目标未达：两条功率通道仍超限，H8 无明确收益

**位置：** [P5比较记录](outcomes/records/v15_bugfix_sources/P5/v11_r9_h8_union_comparison.json) 第1行 JSON `results.q8/q10.*`、`q10_primary_classification`；[比较代码][compare-score] `1614–1648`、[分类与方向][compare-classify] `2114–2142,2571–2622`。

J 是“每项误差除以各自容差，再取最大值”，所以 J>1 表示至少一项超限，不能由整体功率守恒替代。H8 的 J 从4.0650619452降至3.9745473240，改善0.0905146212，小于冻结 εJ=0.1271641623；G 绝对增量5.51673849e−6，小于 εG=9.08815880e−6。两阶分类都正确为 `NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE`。

除最大项 top(0,0,s) 外，**bottom(0,0,s) 也超1e−6**，详见第5节。不能把“比237600 FE少50.867%”解释为相同精度，也不能将原方程残差合格当作空间精度合格。

**裁决／最小行动：** 这是方法诊断负结果，不是应当降低容差的实现 bug。接受原负结论，不重解 H8、不写 transition10。第9节只补同位置 p 动作，取得此前欠缺的 h/p 实际收益配对；正、负或不明确响应均可构成该实验的完整交付。最终独立精度仍需另行核验，不能用本次固定 Y6_1 自证。

### V15-02｜中，下一 fresh phase 前必须关闭：NPZ summary 包装只覆盖 R9_H8

**位置：** [h100_anchor.py][writer] `825–933`，特别 `881–883`；同文件 `7468–7470`；固定共享源码 [dtn残差产生][dtn-raw] `8560–8566`、[残差进入summary][dtn-summary] `8787–8788`、[最终writer调用][flow-writer] `2718`；测试 `5012–5087`。

包装明确只在 `primary_phase == "R9_H8"` 生效。A1 同样启用 raw-vector capture；tuple/list 修复和后处理成功，不证明新的完整 fresh A1 会通过最终 summary 写出。拟新增 P8 也不会自动落入这个 guard。修复后的 H8 writer 只有小数组 fixture 证据，P5 恢复不执行 fresh writer，不能替它补现场资格。

**影响：** 不否决已有保存场比较；不要求重跑 A1/H8。但如果仅新增 phase 名称、沿用 mesh 前 sentinel，就可能再次在昂贵求解完成后遇到 ndarray 写出错误。

**最小整改／验收：** 在现有研究入口以显式 V16 phase 策略复用同一 NPZ 引用 writer，不修改共享默认 writer。新增小数组集成必须穿过真实 main／observer、实际共享 JSON writer 和 terminal 收口，验证原数组不变、primary 文件及逐数组身份、normal1/extra0、错误包拒绝和异常后恢复 writer。昂贵 mesh/solve 边界可替身，不能把受验 writer／terminal 本身 mock 成通过。第9节给出唯一允许的新 phase，不普遍放开任意失败端点。

### V15-03｜中，已局部修复：快照集合不对称及主控审查时序遗漏

**位置：** [compare_round1_candidate.py][compare-binding] `343–350`；[失败主控记录](outcomes/records/v15_bugfix_sources/h_validation_failed/root_closeout.json) `104–419`；[恢复验证](outcomes/records/v15_bugfix_sources/h_validation_recovered/h_saved_primary_validation_root_gate.json)；修复提交 `d48ee3c389b42387dcff522cba059c0ddb5beffc`。

首次前置漏 binding 自身、后置包含，完整结果无法通过不变性检查。主控预审没有发现这项确定性集合差异。随后 worker 已退出、root 读取器未完成时 compare 被修；失败轮原 snapshot 未改，但当时 current compare 已不同，不能笼统称“失败轮全部当前源码未变”，也不能据此反推运行期间发生输入漂移。

独立差异核对表明修复是4删4增，把 binding hash 移入前后共用 builder，测试字节未变。四个受影响节点新通过，另九个节点按不受该 opt-in 变动影响的范围复用，处理成立。

**验收／最小行动：** 本缺陷有限关闭，不要求全套补跑。下一轮沿用同一构造器形成前后输入集合；已失败 worker 的终态审计先固定其不可变快照，若在审计结束前编辑 current 文件，必须分别报告 snapshot identity 与 current identity。新比较 fixture 覆盖 binding 自身、源／输入漂移和已保存 q8 不丢失。不得修改本轮失败记录。

### V15-04｜低，当前文档需收敛，不能成为又一轮纯归档任务

**位置：** [Task43 README](README.md) `23–27` 仍称“最新交付 V14／P2后置字段门失败”，与文首 V15 完成段冲突；[manifest](outcomes/selective_merge_manifest.md) `9,13` 同时把 FAILED closeout 放在可保留证据与 do-not-merge；[round1源码][round-binding] `2035–2042` 及 base 同文件 `1136–1138`。

此外，正确的 `hanging_or_floquet_slave_rows_globally_numbered` 键读取在 base 已存在；本轮 round1 实际只新增八行恢复来源绑定。应表述为“P2_BUGFIX 来源绑定及实际运行验证了此前字段修复”，不把那个键的编辑归到这八行。

**验收：** 在下一轮当前导航同步最新执行权威，旧 V14 段明确历史；manifest 区分“轻量失败档案可保留”“禁止覆写或升级 FAILED”“ignored 大原件不进 Git”。同时在当前科学表列两条超限通道。只作轻量文案更正，不改旧 review／合同／失败，不消耗新 driver，也不阻塞已经满足数值前门的下一阶段。

## 4. 工程路径、恢复边界与测试验收

### 4.1 P2、A1、H8/P5 分别接受到什么程度

| 路径 | 直接代码／证据检查 | 裁决 |
|---|---|---|
| P2_BUGFIX | 固定用户授权、原 P2R 失败 closeout、新 plan/audit/joined 显式绑定；不扫描目录挑成功项；真实空间 audit 已返回 | 接受具体空间结果；旧 P2R FAILED、合同和费用保留 |
| A1 scope 修复 | `h100_anchor.py:4033–4040` 只接受 list/tuple、恰好两个 Python int、完整 `(0,reduced_rows)` 范围，保留 MPI1/shape 及 raw 门 | 正确的表示兼容修复，不是放松容差 |
| A1 saved-primary | `h100_anchor.py:2794–3307` 固定原 FAILED、packet/checkpoint、计划与模态；先 raw gate，再逐数组绑定恢复 coefficients 和 mesh/DOF 索引，之后 q8/q10、Av | 接受同一旧场的非 PDE 后处理；没有新 solve/correction；原正式失败不升级 |
| H8 summary 修复 | `h100_anchor.py:825–933` 把已保存 raw vectors 替换为 NPZ key/dtype/shape/hash 引用；原对象不变，finally 恢复共享 writer | 接受有限 fixture；没有 fresh H8 重跑，不称通用 writer 资格 |
| P5 FAILED-primary adapter | `compare_round1_candidate.py:210–683,2183–2282` 专用 opt-in 核 packet/checkpoint/plan/terminal、同状态数组及实际恢复布局，raw 门后才比较 | 接受研究恢复；普通 pending reader 未普遍放开；`official_result=false`、`passed=false`、无 continuation/transition |

用户“普通 bug 修复后继续，数值 Gate 未过再停”的实际指令，在 [恢复授权记录](outcomes/records/v15_user_bugfix_recovery_authorization.json) 中有明确范围，与本轮用户陈述一致。不能机械套用已被该指令前瞻覆盖的旧支持禁重试规则，把八次支持全判越权。该指令也不允许把数值失败包装成 bug、再解 A2 或改变模型／容差；本轮未见这种扩张。

恢复原向量检查仍只是保存数据的范数／同状态关系复核。A6 原独立算子作用在正式 worker 中产生；本次恢复和本审阅都未再施加算子。必须继续区分原凝聚系统残差、full-active Gram residual、独立 A6、载体非活动行缺陷。

### 4.2 测试证据不能累计成一次最终全绿

| 批次 | 原 JUnit／终态实测 | 合理复用范围 |
|---|---|---|
| P2 focused | 10 passed；whole29.4738281304s | 对应当时绑定／reader字节 |
| A1 首次 | 2 passed、1 failed、12 NOT_RUN；whole17.6573073789s | 失败是 fixture 再要求已创建 phase 不存在 |
| A1 窄恢复 | 14 passed；whole22.3142602020s | 仅 fixture phase 复用处理变化；raw 节点和 h100 未改，另一个 raw 历史通过可复用 |
| h/P5 首次 | 10 passed、1 failed、2 NOT_RUN；whole22.5334596308s | snapshot 集合不对称真实失败保留 |
| h/P5 窄恢复 | 4 passed；whole9.2257785001s | main、opt-in成功、opt-in q10故障、joined拒绝；其余9个未变节点复用，共13 unique |

五份 XML、测试文件 SHA 和修复提交差异相容。最终测试文件 SHA256 为 `336d88e3005525780e83fe5ea940f4c5ecf1f6572cf281f55fa156d1a04ddf4c`。A1 恢复只改变 test-local phase 处理，严格产品默认未放开；h 恢复则是产品 snapshot 集合的小修复，不能只称 fixture 问题。

没有一次最终整文件或全仓完整重跑；没有全仓 CI 或生产 ABI 通过。旧全仓收集／ABI及共享 overlay 资格限制保留。未受行为影响的节点可以按源码、测试函数、依赖、输入和断言范围复用；不因无关文档变化重复旧20项或完整 p6 witness。

## 5. 科学结果的独立读审

### 5.1 实际空间与自由度

[P2实际audit](outcomes/records/v15_bugfix_sources/P2/v11_r9_h8.audit.json) `40–62,161–191,2010–2042` 支持以下具体空间；计数算术可从 Git 实值核算：

| 量 | 实值／独立核算 | 口径 |
|---|---:|---|
| 根／叶 | 180→194，`180+2×7` | 两个根一分八；不是全局层切分 |
| 用户 seed | global cell8＝forest root4，box `[16.5,5,-10]→[33.5,10,0]`，父p5 | global ID 与 root index 不能混用 |
| 必需闭包 | root34，box `[16.5,5,0]→[33.5,10,30]`，父p6 | 材料闭包；没有擅自删掉 |
| 叶阶次 | p5=35、p6=159 | 叶继承各自父p |
| 独立 FE | `116740=36790+79950` | independent trace＋interior |
| 约束计数核对 | `124012−1820−5452=116740` | raw active FE减hanging/Floquet从属；不是p6 carrier存储 |
| interior核对 | `35×240+159×450=79950` | 与实际阶次直方图相容 |
| ΔFE／低于控制 | `116740−110472=6268`；比237600少50.867003367% | 只成立自由度比较，不成立同精度比较 |
| P4实际矩阵 | rows37402＝36790＋612；NNZ used30072292、allocated36616200 | 装配实测；P2中的rows只是预测，不能混用 |

Y6_1 是576格、380160 FE 的固定离散参考；237600 FE 对照是另一模型，只用于评价门槛。二者在计划、比较器和报告中没有混为同一对象。此次证据支持这个一层 mixed-p/local-h 实例，不自动支持一般多层 h、p3、多MPI、跨h初猜转移或迭代。

### 5.2 残差与 q 响应

| 保存的 h primary 量 | 实值 | 冻结门 |
|---|---:|---:|
| 独立 A6 相对残差 | 7.77267194814766e−9 | ≤1e−8 |
| full-active Gram residual | 5.203523992032973e−13 | ≤1e−8 |
| returned condensed residual | 5.323075566556481e−13 | ≤1e−9 |
| normal前→后 | 7.133919099294296e−11→5.323075566556481e−13 | 同RHS、严格下降一次 |
| normal／extra次数 | 1／0 | extra未请求，不写旧extra门通过 |
| R／T／Av | 0.2513585633216903／0.057125759200644305／0.691515677476035 | Av由实际体积分，未用1−R−T回填 |
| R+T+Av−1 | −1.6303625116620424e−12 | 绝对值≤1e−5 |

依据：[P4原量复核](outcomes/records/v15_bugfix_sources/P4_failed/P4_raw_stdlib_recheck.json)、[失败closeout](outcomes/records/v15_bugfix_sources/P4_failed/P4_failed_root_closeout.json)、[Av实值](outcomes/records/v15_bugfix_sources/P4_failed/volume_absorption.json)。原数组未亲验；不能把记录复核等同重新装算子。

A1 恢复后的612通道最大功率变化8.184619648687885e−12，q8/q10最大场分量归一差约6.92e−12，Av=0.6915150591709378，能量闭合约4.10e−12，符合冻结 q 响应门。旧 A2 只复算原保存数组，最大功率变化约4.51e−11、q差约6.04e−11；旧端点、automatic Av规则、extra严格下降失败和 LIMITED 清理仍原样保留。

这支持“R10和Y6两个被测空间，对一次指定 q15/q28→q19/q32 加严的响应很小”。它不能分别归因体积分和端口积分，不能给积分绝对误差上界，也不能排除 R9 mixed-p、H8、未来P8的积分误差。没有新增 R13→R14、native/variable-p完整等价或独立 holdout 资格。

### 5.3 J/G、612通道、总／散射场和共同积分

比较方向始终 `Y6_1(reference)→R9/H8(candidate)`。R13精确包含上下端口、m=−4…4、n=−8…8及s/p，共612键；四复幅组各153项，未只选强通道。J 的功率、逐通道、复幅、E/H/G分别使用原单位／容差。比较代码采用同解析背景形成总／散射场，无相位拟合；近零项使用冻结参考／入射尺度地板，未用相对弱量爆炸或总入射场掩盖作为放宽理由。[J实现][compare-score]及`compare_initial_to_references.py:347–405,607–673`与原任务定义相容。

共同分区为1104盒、350000nm³；q8为565248点，q10为1104000点，分别等于盒数乘每盒8³、10³。P5保存每阶实际点／权／三场／owner数据。q10主结果如下；q8同样判无明确收益：

| 指标 | R9 | H8 | 意义 |
|---|---:|---:|---|
| J | 4.065061945224269 | 3.9745473239816143 | 均>1，输出精度未过 |
| top(0,0,s)候选减Y6 | +4.065061945224269e−6 | +3.974547323981614e−6 | 两者均超1e−6 |
| bottom(0,0,s)候选减Y6 | −2.1482450713386503e−6 | −2.1129819847975906e−6 | 两者均超1e−6；其余610功率通道在门内 |
| G的固定地板归一差 | 3.9956834234581814e−5 | 4.5473572724057846e−5 | h略增，绝对增量低于εG |
| E总／散射固定地板归一差 | 1.46916982589543e−5 | 2.59070128660590e−5 | 共享背景相消，差相同，参考norm仍分别保存 |
| H总／散射固定地板归一差 | 5.45641934455879e−5 | 5.88601589951830e−5 | 均在原1e−4尺度内 |
| ΔJ／ΔG | — | 0.09051462124265441／−5.516738489476032e−6 | 定义均为R9减H8 |
| 每新增FE的ΔJ／ΔG | — | 1.4440750038713213e−5／−8.801433454811793e−10 | 分母是实测6268，不能替换为rows或carrier |

上表中的跨列量仅在H8列列示，R9列不参与该项。H8的T00_s略改善，但T_total带符号差由−2.1481161652722736e−6变成−2.247871772678711e−6，仍低于aggregate1e−5门。不能只报最有利分量。G相对R9增加约13.81%，但冻结εG本来就约为R9 G的22.74%；本轮不能后验改成更小尺度宣布显著恶化或据此断言空间实现错误。

原全p6 R10对Y6_1的J约2.837172688、较R9下降约1.227889257，提供p方向的历史信号；其G改善8.4129e−6仍未超过旧εG，拒绝有效。[R10拒绝记录](outcomes/records/round10_rejected_candidate_v1.json)没有被当前结果回写。单P8不能按28个p5单元平均分摊该收益来预测；仍需要一次真实求解。

**当前主要瓶颈是：在预算内的局部动作尚未产生超过冻结尺度的关键输出改善，现有以G贡献定位的标记还没有证明能预测这些输出的收益。** 积分加严在两个已测空间的响应很小、保存原方程残差合格，使“那些被测 q 响应或明显代数失败解释全部误差”缺少支持；但“参考误差、R截断、路线差异、局部p不足或标记目标不匹配”仍未被逐一排除。不能断言其中某一项已是唯一根因。

## 6. 主控复核、资源、身份与费用

### 6.1 已有主控复核的接受边界

主控的2,654项标准库检查对应 [原件读取脚本](outcomes/records/v15_bugfix_sources/P5/task43_v15_recheck_p5_data.py) `16–23,47–89` 和 [结果](outcomes/records/v15_bugfix_sources/P5/P5_data_stdlib_recheck.json)：它从保存NPZ核E/curl及由其得到的H/G和收益；owner只核slot/global-ID内部一致性，未重做几何搜索；散射参考和modal参考norm仍用worker标量；没有新背景sampler或A6作用。这些限制已披露，接受其有限工作内容，**不把2,654称为本审阅重新访问原NPZ所做的检查**。

P5 Git JSON是紧凑归档，SHA256为`5ca43116e023b6cb49281021b09da6bb8f1b54f856780f1ba8c9746b97615fe9`。按`indent=2, sort_keys=True, ensure_ascii=False`加末尾换行恢复原格式后，精确得到原件引用SHA`26c836ba9abab4ec2636c7c3467381a25b087e7b9c6e85cd655508589abe8097`；归档脚本也明确压缩。该差异可定位为序列化格式，不是比较内容漂移，不需补运行。

P5恢复case中实际direct-backend字段为null，并说明失败端点未记录；不据这个null补造MUMPS现场证明。实际配置／可用性和原P4求解路线从其launch、runtime及原阶段记录分别解释，不能把“可用”混成P5重新求解实测。下一次新正式端点必须明确保存实际使用backend。

### 6.2 P5资源与终态

[trace/resource摘录](outcomes/records/v15_bugfix_sources/P5/trace_resource_excerpt.json) `53–537` 的59个getter、三个成功setter均为CPU1；setter有SCOTCH帧，不能要求“零setter”才通过。七份退出尾段为0、所列行数合计1506，signals为空。已提交资源首／峰／尾七行及三条Z态观察与summary相容；Z态cmdline空、RSS/swap0，不等于活进程CPU缺测。

whole1134.8697960400023秒，采样同时树RSS峰1621196800B，task swap0，全局换入／换出增量0/0，worker/watchdog/launcher=0/0/0，相关后代清除。51项source与76项input的记录首尾一致；worker内部source清单50项，外层另含恢复manifest，数量不同不构成遗漏。

完整1741条资源流及完整trace未亲读，不能把摘录核验升级为全流审计。trace始于taskset后、TID无独立start_ticks、RSS/VmSwap为采样、PSS禁用、无cache-path；空cache SHA不证明实际JIT/global cache稳定。

### 6.3 失败与全过程费用分账

| 互斥工作流 | whole-watchdog秒 | 状态／计数 |
|---|---:|---|
| P2 focused | 29.47382813040167 | 支持1，成功 |
| P2_BUGFIX实际空间＋旧数组 | 959.6084092017263 | 支持1，成功 |
| A1验证失败／恢复 | 17.657307378947735／22.31426020199433 | 支持2，失败不退款 |
| A1 saved-primary恢复 | 44.807101065758616 | 支持1，非新PDE |
| h验证失败／恢复 | 22.533459630794823／9.225778500083834 | 支持2，失败不退款 |
| P5共同点比较 | 1134.8697960400023 | 支持1 |
| **V15支持合计** | **2240.4899401497096** | **8次** |
| A1_q3正式 | 3036.0769646498375 | 正式1，FAILED |
| R9_H8正式 | 2174.3347835741006 | 正式1，FAILED |
| **V15正式合计** | **5210.411748223938** | **2次；累计7/8** |
| 历史V12–V14 recovery | 2215.2188096446916 | 单列历史，不重复并入V15 |
| 更早V11 support | 853.8004706790671 | 单列历史 |

十份summary均未显示task swap、资源硬超限或未清后代。正式工作／whole门为6900／7200秒、32GiB；测试270／300秒、8GiB；P5及A1恢复1740／1800秒、8GiB。P2沿用扩展名义5400／5580秒，实际959.608秒低于旧1740／1800秒，不把名义上限变化写成已经延长计算。

P5标准库原件读取49.98319954331964秒另列。静态编辑、Git、人工读审等not_measured，不补造整轮wall；原读取错误、fixture失败和正式失败见 [机械问题记录](outcomes/records/v15_bugfix_sources/local_mechanical_notes_final.json)。不能叠加已含在whole内的A6、恢复或比较阶段时间，不能将不同源码／缓存／生命周期的耗时直接做同精度加速比。

## 7. 五项能力与本轮验收结论

| 能力 | 裁决 | 本轮增加的具体证据／仍缺什么 |
|---|---|---|
| 空间 | PARTIAL | seed8及必需材料闭包的194叶mixed-p空间、FE/约束/恢复与保存解成立；一般多层、p3联合能力不据此升级 |
| 选择 | PARTIAL | 有一个真实小h动作的成本和输出响应；无清晰收益，没有新增接受态，也没有完整同标记h/p配对 |
| 精度 | NOT_PASSED | top/bottom零级s两功率通道超限；固定参考诊断和q响应不替代独立核验 |
| 同精度全过程成本 | NOT_ESTABLISHED | 费用记账更完整，但不存在已合格同精度端点及完整生命周期对照 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 未接线／验证，继续锁定 |

有限工程修复及恢复方法接受；fresh writer覆盖不足是下一新phase的具体前门，不是旧诊断作废。V15科学负结果接受；无需为取得“成功终态外观”重解A1或H8。当前文档需作V15-04小修，但不再安排一轮单纯归档。

## 8. 依赖组与合并资格

| 组 | 文件／依赖和证据 | 本次资格与阻塞 |
|---|---|---|
| compact evidence/docs | V15 response、机器结果、sources轻量原值、当前summary/导航/总账及本review | 可保留、可进入选择性审阅；先澄清V15-04；**没有实际merge approval** |
| test-only | `src/test/test_task43_v11_scientific_restart.py`，依赖三个研究入口、checkpoint/恢复及native环境 | 指定节点有限有效，历史复用边界成立；不等于独立生产测试包或整套最终绿 |
| research-only入口 | `round1_candidates.py`、`h100_anchor.py`、`compare_round1_candidate.py`及现有`candidate_checkpoints/reference_restore`调用依赖 | 新增约1700行恢复/绑定逻辑仍是研究入口；只允许显式用途，不提升默认，不复制新controller |
| checker/benchmark | raw保存数组checker、物理比较、root算术脚本 | 可审阅复算设计；工作站原件可见性及完整生产闭包未补齐，不独立授生产资格 |
| reusable runner/watchdog | 本轮未改共享watchdog/activation/ABI | 指定shell实测不等于共享启动全面资格；本组无V15生产变更批准 |
| production numerical/core | 本轮无`src/adaptivity`或`src/solvers`数学变更；旧manifest核心依赖组及shared overlay缺口仍在 | 无新的生产资格；不由研究fixture/保存场诊断替代共享核验 |
| 整分支／do-not-merge | 未资格化研究路径、历史FAILED和大ignored数据 | 不整体合并；大原件留ignored，轻量失败档案保留但不升级；不得改master |

未来任何实际合并仍需明确的逐依赖组 merge approval、用户授权和 Codex 执行。本报告只提交审阅文件。

## 9. 下一轮唯一执行授权：R9_P8 与既有 H8 的固定配对实验

### 9.1 明确批准的科学问题、模型与动作

**批准立即进行本节最小实现、支持验证、一次正式 P8 求解和共同点比较。主控核门后在同一授权内顺序继续，不为阶段成功另等review。**

唯一问题：**同一 G 标记位置在原 R9 状态下，p5→p6 是否比已做的 h1 产生更清楚的输出改善、以及每新增 FE 是否更有效？** H8已实际求解但无明确输出收益，P8缺失；补这一对照比换seed或扩大patch更能辨别动作类型，且复用现有p-up实现与三个旧场。单位置可能仍低于冻结分辨尺度，这是允许的有效负结果，不承诺整体精度。

| 项目 | 本次唯一允许值 |
|---|---|
| 父状态 | 原 accepted9/R9，180根／180叶，28个p5、152个p6，110472 FE；冻结R9计划、storage、selection身份沿V11/P5来源 |
| 唯一请求 | global cell8／forest root4，box `[16.5,5,-10]→[33.5,10,0]`nm，p5→p6 |
| h变化 | **无h分裂**，forest仍180叶；不改seed、无p7、无p-down、无level2 |
| 闭包 | 复用既有p/entity/Floquet合法闭包，记录requested与forced实际变化；不人为要求forced为空。H8的材料root34不是P8用户请求，不硬塞进p动作 |
| 物理／q／R | 新phi90、50×50×140nm、13.5nm，材料/Floquet/入射/端口同R9；operator q15、incident/port q28、R13完整612、原cutoff；Av实际规则单列，不静默改q19 |
| 求解 | MPI1、complex128/int64、MUMPS direct，normal correction一次、extra零，primary-only；不跨h转移，不新解reference |
| 固定参考 | 原Y6_1离散目标，576格／380160 FE；禁止换参考或用Y5／两份6×10×6控制选动作 |
| 目标FE | 实际 `110472 < FE_P8 < 237600`；独立trace/interior、约束、carrier、rows分别记账 |
| 用途 | 固定动作响应研究；不写transition10、不改accepted9或旧R10/H8结论 |

若仅这个cell改变cell-p，interior预期增加210；这是执行前交叉检查，不是总FE实测。实际p闭包与总FE必须由现有authority返回，不能按均摊或预测填写通过。

### 9.2 允许修改的文件与先行只读工作

只允许最小改动：

- `benchmarks/task43_hp_adaptivity/round1_candidates.py`：复用`_build_next_round_plan`的`p_up`和`raise_cell_degrees_for_p_up`，显式固定P8请求及真实审计；不增加p算法。
- `h100_anchor.py`：新增明确`R9_P8`用途，复用既有primary-only、原向量门、ledger、失败保护和受限NPZ summary writer；必要时提取小型显式phase策略，不能复制第三套运行框架。
- `compare_round1_candidate.py`：在同一比较器内增加“读取固定P5三场样本，只采P8”的显式模式；沿用现有物理metrics/J，不另写数值比较算法。
- `src/test/test_task43_v11_scientific_restart.py`：本节定向风险测试；新`outcomes/records/v16_r9_p8_contract.json`；新回应／结果、当前导航／summary／manifest／模型总账／进展，以及下述ignored薄launch与快照。

`candidate_checkpoints.py`、`reference_restore.py`和共享数学模块优先不改；现有能力不能满足上述范围时，报告确切缺口，不修改共享方程、约束、缓存算法、writer默认、activation/ABI或环境。不得把新phase冒名为A1_q3/R9_H8，不改旧合同内容或伪称旧合同包含新动作。

先只读核R9/Y6/H8所需输入、P5两NPZ及原正式primary/失败身份，核V15源码到新字节的数值意义。核现有实际canonical、空新root和邻近占用；不重复V6–V10 ELF/归档全审、不跑独立导入probe。新合同逐项映射本节，包含动作、比较规则、root、预算、测试selectors及允许文件；只作绑定，不具备自行扩大权限的权威。

实现、测试、合同先静态审查并提交，再冻结实际源码/测试/命令和输入；每次launch记录实际HEAD与字节。新产物的hash在生产后单独绑定，不回写合同形成自引用。普通后续小修复用新提交和新launch快照，旧快照不改。

### 9.3 T：一次主验证，必要时一次局部恢复

最多两个支持driver，每次270秒工作／300秒whole、8GiB，第二次只补受影响节点。首次一个受监控pytest worker，启动前登记精确展开节点，**最多20个节点**，不collect-only，不选整个文件。使用现有`python -u -m pytest -q -s --tb=short --maxfail=1`，结果与basetemp落本次root。

必须覆盖以下实际风险；允许在同一参数化节点内检查多个相关拒绝，不能以无关hash失败替代目标断言：

1. 真实p计划builder和实际后置门：正例固定global8/box/p，forest180无h；错误seed/box/p、额外h及FE非正增量／达到237600拒绝。保留必要实体闭包，检查所有实际改变。T调用真实计划builder／closure和后置判定，昂贵authority的数量可以由明确实值的小fixture提供，不能把判定函数替换为PASS；完整180格mesh/space authority只在S执行，不在270秒测试内重复。
2. 真实main的父链／ledger／ABI门；再以小数组mesh/solver边界替身穿过实际observer、共享JSON writer和terminal。正常一次、extra调用即失败；新phase的原向量与NPZ引用一致，原raw容器不改，写出前已保存primary。
3. 错packet/数组、非零或未知终态、缺失/错配source/contract/plan以及重新绑定外层hash的混包拒绝；writer异常保留原primary和原异常，finally恢复共享writer。不得把新模式泛化为任意FAILED可读。
4. 新四场比较真实主路径：P5三场sample被调用即fixture失败，新P8每阶只采一次；点/权/owner/reference/binding错配拒绝，前后集合包括binding自身；q10故障保留q8，输入漂移或joined失败不得授完整诊断。

真实worker环境／父链／ABI门先于所有上述测试执行，失败即结束该driver。昂贵边界可用小fixture，环境/身份函数必须实际执行，保存结果；首次真实main只到mesh sentinel的旧测试不能替代本次writer收口测试。T预算内另用一个小fixture覆盖9.8的同worker测试后续接及phase隔离，仍在20节点上限内。历史未变节点、V15恢复结果可按真实依赖范围复用，不要求旧20项、全仓pytest或p6 witness重跑。

T主验证通过即跳过T恢复；它不是“最终全绿清洗”槽。局部bug可静态修复、冻结、按本节第二槽验证后继续；两槽耗尽仍未满足前门则不启动S/F/C，也不挪用它们重跑测试。

### 9.4 S：实际P8空间与旧P5输入资格，一次支持

先核现存旧输入，再构真实P8 mesh/space authority，**不装PDE矩阵、不factor、不solve，不复算旧A2**。保存完整请求／闭包／cell和entity-p、独立FE/trace/interior、Floquet从属与carrier；预测rows单列。核forest180、几何/材料/周期不变，FE严格在本节区间，source/input/资源/清理完整。产物在新root逐阶段及时保存。

同时核即将复用的两份P5 NPZ：

- q8 SHA256 `7286c09d6b3f3bb3a7ece1cd46284a9a5faafd6ebbcb213e2568b6a32ed1119e`；
- q10 SHA256 `82d7bc676e23bea0794caf5e16b3d6c28ee02cb18c57cb59e4bfc08a55759f99`。

它们必须绑定原comparison、原P4 FAILED/primary、三场系数与空间、rule/点/权/owner及同物理背景。核565248/1104000点、正权和350000nm³、1104盒包含P8全部轴断点，原owner与各自索引/几何支持一致；保存校验范围，不把内部slot核对称为新几何搜索。缺原件、hash/布局/参考冲突时停止，**不能重新采三个旧场“修补”为相近数组**。

这个前门是新实验实际消费输入的有限核验，不重做历史全部归档。主控从实际产品核S通过后，直接进入F。

### 9.5 F：R9_P8 attempt1，唯一正式求解

只允许下表正式root的一次调用。装配前核实际空间与S plan/audit逐项一致；保存实际rows、NNZ、backend、normal前后原向量、全active/A6、coefficients/恢复布局、612模态和Av。原子保存primary应早于后续高风险输出/采样；体q8/q10留给C。

必须同时满足：

- 独立完整active A6≤1e−8，full-active显式/Gram门≤1e−8，condensed≤1e−9；更严格原实现门保持。
- normal恰1、同RHS、正收敛原因且原残差严格下降；extra=0。
- 能量闭合绝对值≤1e−5，Av真实体积分；612及所有必要实值有限、身份完整。
- FE与S一致且满足预算；无source/input漂移，CPU/资源/父链/trace/写入/清理合格。

正常成功终态可以为明确的“求解完成、等待本次比较”，不能先写整体科学PASS。若普通后处理/summary bug发生在完整合格primary保存后，可按9.8显式恢复；原formal FAILED不改。不允许因为新phase写出错误再解一遍。

### 9.6 C：同点四场比较，旧三场不重采样

P8几何不变，因此旧P5共同分区仍是其合法细分。**明确允许复用同字节P5的R9/H8/Y6场数组、点和权，每阶只恢复并采样新P8一次。** 不重跑旧三个sampler、不新增reference、不改原NPZ。P8真实owner须由其恢复场生成并检查；不能因为几何相同便无条件套用旧local slot。

沿用同解析背景和单位，形成R9、H8、P8、Y6四场的同点报告；Y6固定为reference。输出全部612带符号功率差、四复幅组、R/T/Av、两零级s、总／散射E/H/G、J、实际ΔFE及两种收益/FE。旧三场从保存数组重新形成同一比较口径，必要的背景解析后处理允许，但无旧场重新采样/积分求解；明确区分保存数组求和与新native场评估。

q10主、q8稳健；**冻结εJ=0.12716416232413652、εG=9.088158796603444e−6不变**：

| P8完整结果条件 | 科学结论 |
|---|---|
| ΔJ_P8>εJ，且G_P8≤G_R9+εG；两阶分类一致 | `POSITIVE_FIXED_REFERENCE_OUTPUT_RESPONSE`，只支持该动作的固定参考输出响应 |
| J_P8>J_R9+εJ 或 G_P8>G_R9+εG | `NEGATIVE_OR_TRADEOFF_RESPONSE`，保留所有分量 |
| 其余完整结果 | `NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE` |
| 两阶分类不同 | `SAMPLING_SENSITIVITY_UNRESOLVED`，不追加第三阶或重采样 |
| 硬门／身份／资源／持久化／清理未过 | `ACTION_ENDPOINT_NOT_QUALIFIED`，不得充当p方法负结果 |

Δ定义始终R9减动作场。并列给旧双门ΔG>εG、J不显著恶化是否满足，但不写transition。先判断改善是否超过尺度，再解释收益/FE；不能将未分辨的微小正数除以很小ΔFE就宣布选择器成功。对a=P8、H8，同时列点估计`s_a=ΔJ_a/ΔFE_a`与`I_a=[(ΔJ_a−εJ)/ΔFE_a,(ΔJ_a+εJ)/ΔFE_a]`；这是冻结敏感度尺度区间，不是统计置信区间。只有P8自身正响应及G门成立，且两阶都满足I_P8下端>I_H8上端，才称“在这两个固定动作中，P8的输出收益/FE已辨优”；否则排序记未分辨，点估计照报。即使J_P8≤1，也只表示固定离散参考下本轮指标门通过，独立精度总状态不自动升级。

**J>1、ΔJ未过或最终负响应不是提前砍掉预定q8/q10证据的理由。** 在硬数值/资源门已过的前提下完成两阶比较，然后结束这一实验；不追加seed、扩大patch或开启第二p候选。

### 9.7 唯一路径、命令、次数及累计预算

canonical固定为 `/home/fenics/Projects/NN-Lab-V2`。新artifact唯一前缀：

`/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v16_p8/`。

表中root和launch均相对此前缀。**唯一外层命令形状为 `bash <上述绝对前缀>/launch/<表中脚本>`。** 不把它解释为已有脚本已经存在；先按9.2实现、冻结并存同字节launch。每次root排他创建、非空拒绝，失败不删除、不换名抵扣。

| 槽位 | 唯一root | launch文件 | 最多调用 | 工作／whole含清理，秒 | RSS |
|---|---|---|---:|---:|---|
| T主验证 | `support/focused_attempt1/` | `focused_attempt1.sh` | 1 | 270／300 | 8GiB |
| T局部恢复 | `support/focused_recovery1/` | `focused_recovery1.sh` | 1，条件使用 | 270／300 | 8GiB |
| S空间及输入 | `support/space_attempt1/` | `space_attempt1.sh` | 1 | 1740／1800 | 8GiB |
| F正式P8 | `formal/R9_P8_attempt1/` | `R9_P8_attempt1.sh` | **1正式** | 6900／7200 | 32GiB |
| C同点比较 | `support/paired_comparison_attempt1/` | `paired_comparison_attempt1.sh` | 1 | 1740／1800 | 8GiB |
| E普通bug非PDE恢复 | `support/engineering_recovery_attempt1/` | `engineering_recovery_attempt1.sh` | 1，条件使用 | 1740／1800 | 8GiB |

支持最多5次、whole总上限 **6000秒**；正式最多1次、whole **7200秒**；本轮新预算最多 **13200秒（3小时40分）**。这是监控运行总上限，不含not_measured编辑/人工wall。预算依据是V15空间959.6秒、比较1134.9秒、正式2174–3036秒，沿用已有上限，不未经证据扩大计算时间。

正式包络从 **7/8前瞻增加专用P8槽为7/9**，调用后最多8/9；A1仍累计3、A2仍3、H8仍1、P8最多1。**原历史最后一槽继续封存**，不是使用7/8的余额。旧sanity、D3、S1及所有失败槽不恢复。调用唯一shell即计数，包括preflight、watchdog前失败；剩余时间不换次数。没有watchdog计时就记未取得，不补0秒。

worker命令范围只使用现有三个模块和一个新增显式参数 `--paired-p8-contract <canonical>/docs/task43_hp_adaptivity/outcomes/records/v16_r9_p8_contract.json`。该参数是本节授权实现的接口，不是假称当前已可运行：

- S：`python -u -m benchmarks.task43_hp_adaptivity.round1_candidates --paired-p8-contract <固定合同>`，唯一产物 `support/space_attempt1/plan_output/plans/v16_r9_p8.json` 及同名audit/joined。
- F：同一 `h100_anchor`，`--case round1_candidate_mpi1`，`--candidate-id v16_r9_p8`，`--candidate-plan <S唯一产物>`，`--run-root <F唯一root>/run`，原 `round1_acceptance_contract_v1.json` 和 `round9_selection_transition9_v1.json` 路径不变，`--same-lu-solve-residual-correction --direct-factor-backend mumps --paired-p8-contract <固定合同> --primary-diagnostic-phase R9_P8`；不用旧V11合同伪装新phase。
- C：同一 `compare_round1_candidate`，`--candidate-run-root <F唯一root>/run`，原R9 `--accepted-parent-selection-record`，`--attempt-id v16_r9_p8_paired_attempt1 --paired-p8-contract <固定合同>`；输出固定 `<C唯一root>/comparison/`。旧P5样本来源由合同固定，不接受任意reference覆盖。
- E：仅上述S/C或F保存场后处理的同一受影响入口，加显式 `--resume-paired-p8-stage S|F_POSTPROCESS|C`；三选一，首次调用前冻结选择与原失败/primary绑定，输出只到E根。不得提供F_SOLVE选项，不得装PDE矩阵、factor、solve或新增correction。

S恢复来源仅允许两个枚举：`S_MAIN`为S表列plan/audit/joined；`E_S`为`support/engineering_recovery_attempt1/space/plan_output/plans/v16_r9_p8.json`及同名audit、该`space/`下joined。若S因普通bug必须由E收口，F/C显式绑定E_S及原S失败，F的candidate-plan改为这个唯一已声明路径；不得扫描目录取latest。S已完整保存的正确plan/authority可按原hash复用，不为换目录重构或覆写原件。E用于F_POSTPROCESS时派生产物只到`E/postprocess/`，用于C时只到`E/comparison/`，原F/C失败及已完成q8保持原路径/字节。新合同先声明这三个互斥恢复用途，launch再冻结实际采用项。

完整实际argv/env在相应launch前冻结。复用原环境：`scripts/activate_task40_phi90_pord64.sh`，worker内`HWLOC_COMPONENTS=-x86`、`OMPI_MCA_pml=ob1`；CPU1、MPI1、OMP/OpenBLAS/MKL/BLIS/NumExpr/VECLIB六线程变量1。真实worker核complex128/int64及MUMPS，绑定watchdog直接父PID/start_ticks和tracer。继续已验证的`taskset -c 1 strace -D -ff -ttt -k -e trace=sched_setaffinity,sched_getaffinity`组织，0.25秒名义采样，task swap必须0，全局swap另报。

`PHYSICAL_NATIVE_CAPACITY=task43_hp_adaptivity_resource_v1`，support node cap8589934592B、formal34359738368B；与原动态available/reserve取更严者，保留`max(64GiB,15%有效总内存)` reserve。一次一个Task43 workflow，不干扰邻近任务、不改共享activation/ABI、不清缓存/预热。

### 9.8 普通bug可继续的条件与必须停止的条件

**普通静态路径、容器、fixture、JSON/绑定接线问题：允许立即定位、最小修复、提交冻结、验证受影响节点并在本节额度内继续，不为修好一个bug另等review。** T第二槽专用于T问题；T通过以后，E保留给最多一次S/F后处理/C的普通实现恢复，E内先跑明确受影响的最小节点（最多6个，最多270秒工作，计入E总限额），通过后才恢复选定阶段。若无此问题，不调用E。

E由同一个watchdog直接子worker先运行`pytest.main`或等价进程内最小验证，再调用既有受影响入口；不得以subprocess另起pytest／恢复worker，不产生未计数driver。测试产物和模拟terminal仅写`E/fixtures/`隔离目录，不污染实际resume输出。开始前检查恢复所用phase状态；若phase已经由同一worker建立，只允许在PID/start_ticks/绝对phase路径完整绑定后显式allow-existing继续，不能删除phase伪装首次启动或放宽其他入口默认。该顺序须在T小fixture与launch静态预审中确认。

可恢复必须同时有原失败及原异常、稳定source/input快照、完整资源/清理和明确局部原因。F若已保存同状态合格primary，C或E可显式读取该失败端点完成后处理，保持原FAILED；F_POSTPROCESS不得重解或追加correction。C若只缺后续部分，只复用已持久化且身份正确的q8，未完成q10在E最多一次；已完成采样不为择结果重做。S的已完成合格产物优先只读续接，不借E变更动作。

**以下立即停止受影响动态链，E不能覆盖：** A6/full-active/condensed、normal计数/严格下降、能量或有限性硬门失败；实际FE/几何不符；非CPU1成功setter、活worker非CPU1或未解释setter；源码/输入漂移、父链/tracer异常；RSS/swap/时间门；必需primary/证据持久化失败或哈希不可信；未知退出、相关后代未清。只能保留原件、静态定位并交付具体剩余工作，不换容差、不延时、不换参考、不重解。

普通summary序列化失败只有在**primary与必要原件已经完整、可读、hash固定，原异常及终态可靠保存**时才属上面的后处理恢复；存储故障或原件缺失不享受此例外。F在合格primary产生前失败时正式槽已耗尽，没有第二次求解权；静态修复可以交付，但不能把“bug修复继续”解释为隐性正式重试。E失败或额度耗尽不再新建目录补跑。

到工作阈值仅允许TERM/KILL/reap和保存已得终态，whole余量不用于继续计算。只处理已核本任务PID；unknown exit、whole超限或残留后代均不得通过。所有失败、重做、支持和恢复费用保留，嵌套时间不重复相加。

### 9.9 主控复核、交付与明确禁止项

主控在T→S→F→C每个放行点亲读新原件/实值：核实际闭包/FE、primary原向量同状态、全部模态、数值门、源码/输入首尾、资源trace/退出及清理，不能只接代理PASS。已有V15原件核验按实际消费范围复用，新的worker环境/父链/资源必须现场核。读失败快照与current源码的区别按V15-03处理。

每阶新样本完成即保存；输出包含P8源/计划/primary和旧三场身份、q8/q10点权及owner、完整J分量和612、ΔJ/ΔG/ΔFE与收益、两阶标签、每次成本/失败。交付 `response_v16.md`、`outcomes/records/v16_r9_p8_results_v1.json` 和必要轻量证据，更新当前导航／summary／manifest／模型总账／进展；保留旧合同、review、FAILED和负结果。

本实验完整正/负/不明确响应，或明确硬停止及最小剩余任务，才是本轮收口；不以“又整理了一轮hash”代替科学交付。**开始动作是9.2的最小P8实现和9.3的定向验证，不是等待新的任务授权。**

除本节外，A1/A2 q重试、A1_R、A2_R、一般B/C、第二seed／全p6／p7／h+p组合、fresh baseline、端口或q扫描、成本campaign、迭代、0.7nm、NN/FTT、共享activation/ABI修改和任何合并继续禁止。即使P8表现积极，也不自动升级独立精度、accepted链或生产资格。

## 10. 提交声明

本次只新增本报告，没有运行项目或修改科学实现、历史合同与失败记录，没有提交master或执行合并。review完整提交SHA由提交产生后在交付消息提供，文件不制造包含自身SHA的循环身份。

[writer]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/benchmarks/task43_hp_adaptivity/h100_anchor.py#L825-L933
[dtn-raw]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/src/solvers/dtn_port_3d.py#L8560-L8566
[dtn-summary]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/src/solvers/dtn_port_3d.py#L8787-L8788
[flow-writer]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/src/solvers/common_3d_case_flow.py#L2718
[compare-score]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/benchmarks/task43_hp_adaptivity/compare_round1_candidate.py#L1614-L1648
[compare-classify]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/benchmarks/task43_hp_adaptivity/compare_round1_candidate.py#L2114-L2142
[compare-binding]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/benchmarks/task43_hp_adaptivity/compare_round1_candidate.py#L343-L350
[round-binding]: https://github.com/Rookie1234567/MyFEniCS/blob/1290b4f283c01d81f23ba9e1a187458d24bde2af/benchmarks/task43_hp_adaptivity/round1_candidates.py#L2035-L2042
