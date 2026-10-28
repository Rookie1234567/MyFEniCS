# Task43 正式审阅 V18：接受固定 h/p 配对负结果，转入保存场响应分解

## 1. 固定身份、授权来源与总裁决

审阅日期：2026-10-28（Asia/Singapore）。唯一执行分支：`task43_hp_adaptivity`。

| 身份 | 完整值 |
|---|---|
| 仓库 | `Rookie1234567/MyFEniCS` |
| 固定被审交付 | `5ceb617ee85058bc29da7ff126a9d594779dc34b` |
| 上一正式V16 review／差异基点 | `ddbe92264d17f1111dcb551431b3b96d26b0d167` |
| V17失败交付 | `297b9ec78351b1ddc38e56fe4923d7a74696dcca` |
| T3／S／F实际运行HEAD | `196571795199dc0f48fd8ad3daaac258ab3390cb` |
| C_RECOVERY2实际HEAD | `84ae81d34cb03448b468f429b8d1bb3707f4d01a` |
| 最终C实际运行HEAD | `75e1e05c8223bd15237162fc869b51637cdfe710` |
| 长期数值基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |

审阅开始时远端正好位于固定被审交付，无后续提交。V16 review至交付为10个线性提交、56个变更文件；实际F至最终C为4个提交；最终C至交付只有2个文档／证据提交，研究源码及测试没有再变。远端身份相符不等于本审阅访问过canonical worktree或独立认证其clean/upstream状态。

**总裁决：接受本轮固定P8研究链的有限工程恢复，接受“同一位置h/p配对实验完成，但两种动作都没有超过冻结尺度的明确输出收益”这一科学结论。没有发现需要重解P8才能解除的确定性实现错误。整体精度仍未通过，不能接受transition10、p优于h或同精度成本优势。**

**明确批准下一任务：第9节的“已保存四场局部误差—动作响应分解”。新增最多4次有条件支持调用、累计whole上限3000秒，新增正式PDE为0；正常T通过后直接D，普通局部工程错误可在专用恢复槽内修复续接，不逐阶段等待review。** 本任务要利用已有R9/H8/P8/Y6_1数组解释小收益的结构，产出180单元分解和完整612通道表；不是再整理一轮hash，也不换seed盲试。

| 裁决维度 | 本次结论 |
|---|---|
| 工程接受 | `PASS_WITH_QUALIFICATIONS_FIXED_P8`，限定实际身份与用途 |
| 科学结果接受 | `COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE`；两阶无明确收益，负结论有效 |
| 资源资格 | Git实值范围内有限接受；退出竞态解释相容，完整原流未亲验 |
| 下一步 | 批准保存数组的有界科学后处理；不批准任何新PDE或新采样 |
| 正式账 | 9/10保持；历史最后槽封存，不恢复失败或旧额度 |
| 合并资格 | 无具体依赖组或整分支的merge approval，不执行合并 |

用户在V17监控父链失败后明确要求“没有到数值gate不允许停止”，本轮用户再次确认其同一P8工程恢复授权。[执行恢复绑定](outcomes/records/v18_p8_execution_recovery_v3.json)第6–20行、[C恢复绑定](outcomes/records/v18_p8_comparison_recovery_v3.json)第8–30行保留这一来源。它覆盖本轮普通工程修复后的继续，不追认为V16原本允许重试，也不授权其他模型、放宽硬门、无限计算或未来自动运行。旧V17的watchdog消失、外层143与launcher文件0矛盾及具体信号来源仍为UNKNOWN。

## 2. 实际审阅范围及证据可见性

已读三层AGENTS、仓库工作原则、Task43任务书、V11科学补充任务书、V15/V16 review、相关V17/V18回应、全部本轮差异、六份恢复绑定、结果及sources轻量文件、当前README／summary／manifest／模型总账／进展；追踪三个研究入口、新launch和定向测试，检查共享比较与watchdog相关源码。三个子审阅分别检查工程、科学、证据，主审再次核关键调用和实值并作最终裁决。

取得70份固定HEAD文件并逐份按Git blob算法核对；另取4份实际F源码和2份历史测试用于字节／AST差异。下载过程中只纠正本地传输为五份无末尾换行XML多加的换行，使副本回到Git原字节；没有修剪其原有行尾空白。审阅执行的是标准库文本、JSON/XML、hash、AST和标量算术，没有执行项目导入、pytest、collect-only、ABI探针、归档脚本、场恢复、采样、积分或PDE。

| 层级 | 本审阅亲自核对 | 不可扩写为 |
|---|---|---|
| 固定Git源码／差异 | 三个研究入口、583行launch、测试、合同和新旧身份链 | 通用运行器或生产数值核心已资格化 |
| 测试原文 | 5份JUnit XML及其节点、历史测试字节、实际reader调用 | 一次最终5项／全文件／全仓或CI通过 |
| 科学轻量实值 | FE算术、残差数值与门限、J分量最大值、两阶Δ及收益区间 | 亲读primary 42数组或重新施加独立A6 |
| C终态原行 | 4条SIGCHLD原行、10个exit0尾行、PID/start_ticks关联 | 亲读全部838行trace、678行资源或全部29个getter |
| F终态 | joined、source_index中的具体数值、时间及原件引用 | 亲读完整1767行trace、5581行资源或全部setter栈 |
| 主控复算 | 读取其脚本文本和已提交的比较算术结果 | 本审阅访问了工作站NPZ或独立重建全部模态物理量 |

**未亲验的工作站原件**包括：F完整primary／prevalidation NPZ、42数组复核JSON、原612模态JSON及Av文件；四份q8/q10旧／新场NPZ；完整comparison JSON；所有完整资源、trace、host observation及source/input快照。具体路径见[sources索引](outcomes/records/v18_r9_p8_sources/source_index.json)、[F joined](outcomes/records/v18_r9_p8_sources/F_endpoint_joined_terminal.json)及[C closeout](outcomes/records/v18_r9_p8_sources/C_root_comparison_closeout.json)。索引明确是导航／转录，不是独立gate。hash说明引用哪个原件，不证明外审已经读过原件。

## 3. 按严重性排列的问题、影响与最小验收

### V18-01｜高，科学目标未达：精度和可辨识收益都未通过

**位置：** [结果](outcomes/records/v18_r9_p8_scientific_results_v1.json) `comparison.accuracy_failure/orders`；[保存数组复算](outcomes/records/v18_r9_p8_sources/C_saved_array_recomputation.json) `orders.q8/q10.results`；[比较器][compare]第1617–1651、4494–4592行。

P8的J为4.020864574738603，最差已列项R00_s绝对差4.020864574738603e−6，高于1e−6。ΔJ=0.04419737048566574只有εJ的34.756%；q10 ΔG=2.768523717739272e−7只有εG的3.046%。不能以FE仅增250或点估计收益/FE较高替代冻结判定。

**性质：** 有效的固定动作负结果，不是应该修容差的bug，也不否定所有h/p方案。接受原分类，不回写accepted9/R9、R10或H8。下一步按第9节解释实际动作响应，不追加seed／p阶／PDE。

**验收：** 保留两个阶次、全部J/G分量及完整通道；科学诊断成功不要求正收益。不得把采样q8/q10极接近用来后验缩小原ε。

### V18-02｜中：关键原件在Git中的覆盖不足，接受须有明确范围

**位置：** [source_index](outcomes/records/v18_r9_p8_sources/source_index.json)第602–673行；[F joined](outcomes/records/v18_r9_p8_sources/F_endpoint_joined_terminal.json)第18–25、45–94行；[C closeout](outcomes/records/v18_r9_p8_sources/C_root_comparison_closeout.json)第75–234行；[read_primary](outcomes/records/v18_r9_p8_sources/read_primary.py.txt)第14–67行。

F的退出竞态和42数组复算主要以实值转录及hash呈现；C提供较强的退出原行，但资源vanished窗口仍是摘要。Git没有P8完整612逐条功率／复幅表，只有最差值和J分量。因此不能声称本审阅独立枚举了全部超限通道，更不能断言“只有R00_s超限”。

**裁决：** 没有发现原件冲突或数值造假，有限研究接受成立；完整外部资源／原向量资格不据此宣告通过。

**最小整改／验收：** 随下一任务静态准备，从原绑定文件提取F/C退出连续小窗口、实际身份、setter/退出原行和42数组复算JSON；第9节科学产物输出完整612带符号表。原文件hash和原行号同时保留，不补造缺失原件，不重跑PDE、采样或旧测试。若消费原件不可读或不匹配，停止该诊断并报告确切缺项；不把补证另立成一轮主任务。

### V18-03｜中，生产合并阻塞：恢复接线规模大，单份terminal不能充当通用资格

**位置：** [round1][round]第947–1586行；[h100][h100]第4067–4453行；[compare][compare]第3161–3835行；[launch][launch]第69–124、317–428、527–583行。

V16→V18三个入口合计新增1642行、删除91行，另有583行含大量inline Python的shell和681行测试。多个reader重复核固定attempt、历史源码、路径及错误形态；这是具体研究恢复，不是已经可迁移的通用“薄启动器”。

launch第79–85行读取资源JSON时跳过坏行；其COMPLETED主要结合退出、watchdog summary和whole，不能独立证明逐行资源、CPU、输入和科学门合格。当前链另有主控完整读取和joined门，尚未发现这个边界实际掩盖本轮异常。

**最小处置：** 冻结这条已完成研究恢复路径；下一任务不再往三个reader或583行launch叠新controller。继续要求资源解析错误否决，不能只凭COMPLETED自动消费。无需为架构整洁先重构／重解P8；未来生产迁移须另做最小职责抽取和依赖验证。本次不给这些文件生产或合并资格。

### V18-04｜中，已修复但责任保留：前置检查漏掉确定性fixture和严格集合错误

**位置：** 五份[测试原文目录](outcomes/records/v18_r9_p8_sources/README.md)；[测试][tests]第42–261、274–681行；[source_index](outcomes/records/v18_r9_p8_sources/source_index.json)第822–831行。

T1未定义RECOVERY_PATH，T2读取错误终态字段，C_RECOVERY1漏targeted_fixture，C_RECOVERY2只核common refs的路径/hash而漏完整键集合13对16。代理误核summary与实际manifest的区别、主控放行遗漏和T2误读RSS warning阈值均应保留。

真实reader在严格集合不相等时拒绝是正确行为；后续修复没有把集合门改成“公共子集即可”。C_RECOVERY3的三个实际节点通过后在同worker完成比较，修复有现场证据。

**验收：** 该组有限关闭，不重跑原11项或5项。下一任务第一次动态运行前同时核完整键集合、路径、hash及实际展开selector；不能再以一个数量或PASS标签代替内容检查。

## 4. 工程恢复、运行身份与测试接受

### 4.1 恢复没有改变被冻结的科学问题

[round1][round]第2051–2230行仍调用真实p-up builder，仅请求global8/root4的p5→p6；原R9的180叶、28p5/152p6、box和FE110472均检查，实际变阶与必要闭包逐项对应，无h。实际authority由S取得，F装配前再核其一致性。

实际F至C的四份源码diff表明：

- h100只增加历史S/F上下文与归档launch/source map读取；不把最终C源码写成F运行源码。
- compare增加唯一历史H8标签兼容及固定q8保存包读取。旧`v11_r9_h8`只在内存副本中规范为`R9_H8`，其余数值及键集合仍严格核对，旧P5文件不改。
- round1增加C-only绑定，严格16项refs一致；不得用于T/S/F或新模型。
- launch新增C_RECOVERY的同worker测试→main路径；原生命周期函数和worker包装字节保持。

没有修改共享数值核心、activation、ABI、watchdog默认或原J/G、raw残差与分类公式。新路径是显式研究用途，不能因它处在既有文件中就称为小型生产补丁。

### 4.2 父链与保存端点

[launch][launch]第37–207、272–318、430–524、554–583行使用分离会话supervisor、watchdog和`exec taskset/strace -D` worker；保存PID/start_ticks、信号、wait结果及原件引用。原runtime检查继续核watchdog直接父、TracerPid、CPU1和实际环境，关键数值阶段仍复核身份。新组织的成功不证明旧V17的信号来源已查明。

[compare][compare]第3161–3835行要求成功F terminal、endpoint、primary/raw、原计划与source代际，核612 inventory、MUMPS、q/R、FE及能量；从primary重新调用原向量门，不仅读取PASS。旧FAILED F没有被伪装成成功端点。

第3901–4002、4366–4458行的q8恢复核F terminal/primary、P5包及点权、mesh、五数组目录、dtype/shape/hash和owner；返回原包路径，不复制或重采。q10才调用sampler一次。旧R9/H8/Y6_1三场仍只读原P5数组。

### 4.3 分批测试及具体覆盖

| 批次 | 原XML实测 | NOT_RUN | 可接受范围 |
|---|---:|---:|---|
| T1 | 2 passed、1 failed | 8 | 失败为fixture NameError，原失败保留 |
| T2 | 9 passed、1 failed | 1 | 生命周期分支已运行；终态字段fixture失败保留 |
| T3 | 11 passed | 0 | 对应196571…的11个定向节点 |
| C_RECOVERY2 | 2 passed、1 failed | 2 | q8/q10 alias通过；实际reader严格refs拒绝 |
| C_RECOVERY3 | 3 passed | 0 | 实际F reader、未许可源码漂移拒绝、原q8复用；随后同worker比较 |

T3测试SHA256为`46168e480ce22939806bc0a00ee0cc10cc692187f659e13522e2f593b3955414`；最终为`a2347a91910322444f479373ea2631d01ade43be6fc46449cd63e657430f7de6`。T3原10个顶级定义在最终文件AST未变，最终新增5个定义；这只支持相关历史范围，不意味着后来新增部分已在T3运行。C_RECOVERY2测试文件与最终交付逐字节相同，因此两个alias节点可以历史复用；**2+3不是一次最终5项通过**。

T3的S/F handoff使用合成包，mock了恢复manifest loader；真实reader正向只到缺完整F处拒绝，不能称全链成功集成。最终测试第157–176行实际读取现场F primary/checkpoint，第179–202行真实reader拒绝未许可watchdog源码漂移，第205–261行读取原q8并验证错误外部terminal绑定拒绝；配合实际C主流程，支持本次使用范围。无全仓pytest、CI或生产ABI资格。

13份Git compact副本的bytes/SHA与来源索引相符，包括五份XML和三份审计脚本文本。失败XML的原尾空白保持正确，不要求修剪。已说明最初未暂存检查不涵盖untracked证据，暂存后完整diff-check有原字节例外；排除固定原件后的文本格式通过，不写成无例外全绿。

## 5. 科学结果及其含义

### 5.1 空间、原方程与吸收

FE指施加约束后独立有限元未知量；端口辅助行、载体存储和求解矩阵行是不同口径。以下由Git实值作算术交叉核对，实际原件仍按第2节限定。

| 量 | 实值／关系 | 身份与意义 |
|---|---|---|
| 空间 | 180叶，27p5/153p6；h分裂0 | measured，固定cell8/root4 |
| 独立FE | 35392 trace＋75330 interior＝110722 | measured；interior也等于27×240＋153×450 |
| 约束核对 | 116174 raw active−5452 periodic slave＝110722 | 不能把raw或p6 carrier当独立FE |
| 实际增量 | 110722−110472＝250 | derived；interior增210，其余独立trace增40 |
| 返回矩阵 | 35392＋612＝36004行 | F实测；S的同值是预测 |
| stored NNZ | used29053038，allocated35416466 | F实测，不用allocated冒充used |
| 相对237600控制 | FE少53.39983165% | 仅规模比较；不是同精度压缩 |
| 独立A6 | 8.154258542762765e−9≤1e−8 | 为门限81.5426%；通过不表示裕量巨大 |
| full-active／condensed | 5.261452776589861e−13／5.36565601165842e−13 | 分别对1e−8／1e−9门 |
| normal | 7.36358356126758e−11→5.36565601165842e−13 | 一次、同RHS、严格下降；extra零 |
| R／T／Av | .2513584864859189／.05712592329889687／.6915155902132417 | 保存的诊断场结果，非accepted output |
| R＋T＋Av−1 | −1.942446203884174e−12 | abs≤1e−5；Av不是1−R−T回填 |

[h100][h100]第4989–5280行以保存的独立A6 trace/interior/modal残差及RHS重算范数；full-active使用匹配的Gram作用，不能用raw trace欧氏范数替代；normal前后同RHS、returned primary和正收敛原因也核对。实际C再次调用这些门，保留primary/prevalidation数组逐项绑定。

[Av观察器][h100]第1196–1255行记录实际fem.form元数据：两个材料吸收form为q15/default，两个区域体积核验form为空metadata，即automatic。两者用途和次数清楚，不把材料吸收写成automatic，也不把体积form写成q15。

### 5.2 两阶比较及单位FE收益

J把各输出差除以各自容差再取最大值，J>1表示至少一项超限。G是同一固定离散参考下的场差范数，包含电场与旋度；它不是已证明的连续真误差上界。比较方向始终Y6_1为reference，Δ为R9减动作场。q10主、q8稳健；原两份6×10×6控制及holdout没有用于本轮动作或参考挑选。

| q10量 | R9父场 | H8历史保存场 | P8本轮场 |
|---|---:|---:|---:|
| 独立FE | 110472 | 116740 | 110722 |
| 新增FE | — | 6268 | 250 |
| J | 4.065061945224269 | 3.9745473239816143 | 4.020864574738603 |
| G | 3.9956834234581814e−5 | 4.5473572724057846e−5 | 3.9679981862807887e−5 |
| ΔJ | — | .09051462124265441 | .04419737048566574 |
| ΔG | — | −5.516738489476032e−6 | 2.768523717739272e−7 |
| ΔJ／新增FE | — | 1.4440750038713213e−5 | 1.7678948194266297e−4 |
| ΔG／新增FE | — | −8.801433454811793e−10 | 1.1074094870957087e−9 |
| 冻结尺度区间下端 | — | −5.847086962584893e−6 | −3.318671673538831e−4 |
| 区间上端 | — | 3.472858704001132e−5 | 6.854461312392091e−4 |

这些是已提交轻量实值及本审阅重新算术所得，不是本审阅重算NPZ。P8单位FE的点估计约为H8的12.2424倍，**但两区间都跨零，P8下端没有超过H8上端**；点估计不能变成p辨优结论。

q8的P8 G为3.967998186281264e−5，与q10相差约4.75e−18；J相同。两阶均为`NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE`，分类正确。这个一致性只说明该保存离散场的两套共同采样结果稳定，不排除算子q、R截断、参考离散误差或native/variable-p路线差异，也不能据此重估更小ε。

代码严格核R13上下端口、m=−4…4、n=−8…8、s/p共612键及四组153复幅，无相位拟合。总／散射场使用同一背景，差中背景相消，但参考norm仍按各自地板保留。Git当前不足以独立枚举P8全部612数值；下一任务须列R00_s、T00_s及**所有**超限通道，不能只列最大项或把其余610/611条推定通过。

### 5.3 主控复算做到了什么

[read_primary](outcomes/records/v18_r9_p8_sources/read_primary.py.txt)核42数组目录、dtype/shape/hash、finite、prevalidation同状态，并算A6/full-active/condensed与normal；没有重新施加A6算子。其完整输出在ignored原件，不能把脚本存在等同本审阅已经读取数组。

[read_comparison](outcomes/records/v18_r9_p8_sources/read_comparison.py.txt)第23–49行从保存NPZ重算E/curl/H-total/G及散射E差范数；J的模态分量和部分散射归一量仍取worker保存metrics，未新生成背景或独立重建模态物理。已提交结果明确这一边界。主审另从Git数值核J最大值、Δ、区间、FE和费用，未将这些标量核算称为原数组物理复算。

## 6. 资源、退出竞态及全部费用

### 6.1 退出竞态的裁决

F两个vanished观察为elapsed3658.686311531812、3659.181689874269秒，worker PID3551561；索引记录其trace以0退出，之后四个采样exit0且无后代，host最终身份消失。C第673行记录worker3574825 vanished、elapsed460.24501897301525，随后674–677行exit0/空后代。C的worker/watchdog/tracer PID与start_ticks、直接父链，以及4条正常status0 SIGCHLD和10个exit0尾行相互一致。

**判断：** 这些时间顺序支持进程退出和采样读取之间的竞态，没有显示本轮再次发生V17式活worker脱离监控后继续运行。vanished本身既不是资源异常的自动证明，也不是可一概忽略的字段。F原资源窗口/trace原行未提交，C原资源窗口也未提交，故接受为有具体实值支持的有限解释，不能写成外审完整资源流无条件PASS。按第9.2节补取原连续窗口；不为一个退出采样竞争重算PDE。

F采样同时树RSS峰6338056192B、C峰1639280640B，低于32/8GiB上限；记录task swap0、CPU1、MPI1、六线程1。F三次成功setter均为CPU1的陈述需与原行一并保留；正常SCOTCH setter或SIGCHLD不构成失败，不能要求所有PDE零setter／零signal。

采样峰不是连续高水位；trace在taskset之后开始，TID没有独立start_ticks，PSS未启用。无cache-path不能证明实际JIT/global cache稳定。这些限制不由一次成功运行消失。

### 6.2 九次调用全部计费

| 调用 | 类型 | workflow whole秒 | 树RSS采样峰B | 终态与计数 |
|---|---|---:|---:|---|
| T1 | 支持 | 24.753636937 | 269787136 | fixture失败，计1次 |
| T2 | 支持 | 95.981342056 | 332460032 | fixture失败，计1次 |
| T3 | 支持 | 101.654528933 | 331329536 | 11节点通过，计1次 |
| S | 支持 | 355.112776690 | 1366196224 | 空间完成，计1次 |
| F | 正式 | 3663.379578318 | 6338056192 | 数值端点完成，计1次 |
| C0 | 支持 | 243.148277828 | 1005113344 | H8标签失败，q8保留，计1次 |
| C_RECOVERY1 | 支持 | 3.589317171 | NOT_MEASURED | watchdog前漏字段，计1次 |
| C_RECOVERY2 | 支持 | 31.377051030 | 272154624 | 严格集合失败，计1次 |
| C_RECOVERY3 | 支持 | 465.385582418 | 1639280640 | 3节点后比较完成，计1次 |
| **支持合计** | **8次** | **1321.002513063** | 不相加峰值 | 失败不退款 |
| **正式合计** | **1次** | **3663.379578318** | — | 正式账9/10 |
| **V18已测whole总计** | **9次** | **4984.382091381** | — | 不是任务全历史或整轮人工wall |

本审阅用Decimal逐项精确相加，与结果一致。C_RECOVERY1只有launcher退出1，watchdog/runtime/pytest均未启动；3.589317171秒是入口生命周期，**不能称九次都是whole-watchdog**。T及C内层pytest时间不再相加。

三项只读复核40.116043168120086、0.5373938349075615、3.96355346404016秒，另合44.6169904670678075秒；手工静态费用NOT_MEASURED。旧V17 F whole仍NOT_MEASURED，末资源756.7104571810924秒仅为下界，不补0，不与launcher时间戳区间相加。

原恢复序列上限11700秒、三次C恢复另5400秒，总上限17100秒，是本次用户同任务工程恢复下的限定分配；不推导未来还可用其剩余秒数。未见删除失败、改名退款或扩成新科学模型。已用sanity/D3/支持和旧正式槽均不恢复。

## 7. 当前瓶颈与五项能力

现在已取得同位置h/p两种实际响应。P8用更少新增FE，G点值略改善；H8的J点值稍好、G点值反而增大。两者都没有达到冻结可辨识收益。**当前瓶颈是：按全域G场差贡献定位的局部动作，尚未证明能带来主导相干输出的可辨识改善。** “相干输出”指复场的相位和幅度共同决定反射，场差较小或局部变好不保证某个反射通道同步改善。

不能据此确定唯一根因为参考不准、R截断、局部p不足或标记错误；也不能由较小残差推导输出精度界。下一步应先利用已经保存的响应，测量哪里改善、哪里恶化、修正方向是否对准原差异。

这一区分也符合目标量误差研究的方法边界：Ingelström的[Chalmers作者学位论文记录](https://research.chalmers.se/en/publication/1747)明确用对偶问题构造散射参数误差估计；Demkowicz的[Maxwell hp方法](https://doi.org/10.1016/j.cma.2004.05.023)以参考解投影误差下降／新增DoF指导候选。这里只借其区分“场范数”和“目标量”的思路，不声称本仓库具有这些方法的可靠性保证。第9节不解对偶问题，不把普通G分解冒充DWR。前者作者机构摘要已直接查阅；后者核对出版方摘要，未声称读到付费全文。

| 能力 | 状态 | 新增证据／仍缺什么 |
|---|---|---|
| 空间 | PARTIAL | 固定P8真实180叶、FE和端点成立；不外推多层、p3或多MPI |
| 选择 | PARTIAL | 同位置h/p诊断完整，收益未分辨；没有新接受态 |
| 精度 | NOT_PASSED | 已知R00_s超限，独立核验及其他既有资格缺口仍在 |
| 同精度全过程成本 | NOT_ESTABLISHED | 两动作都未达同精度目标，研究生命周期不可直接作加速比 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 未接线、未验证 |

## 8. 依赖组及实际合并资格

| 组 | 本轮文件／依赖与证据 | 裁决及阻塞 |
|---|---|---|
| compact evidence/docs | V18回应、六份恢复绑定、结果、sources、当前导航／总账及本review | 研究档案接受；V18-02小原件摘录待补；无实际merge approval |
| test-only | `src/test/test_task43_p8_execution_recovery.py`，依赖研究reader、现场资产及native环境 | 指定版本/节点有效；不是独立可迁移生产测试包 |
| checker/benchmark | 三个reader、q8复用及保存数据复核 | 固定研究用途接受；完整原件可见性与通用输入策略有限 |
| research-only | `round1_candidates.py`、`h100_anchor.py`、`compare_round1_candidate.py`、六份绑定 | 不再扩建恢复框架；迁移前需最小依赖抽取和对应验真 |
| reusable runner/watchdog | `v18_p8_stage_launch.sh`；共享watchdog未改 | 具体生命周期和此次实跑有效，非共享生产资格；terminal单独不足 |
| production numerical/core | 本轮无共享数学核心／activation／ABI变更 | 不凭本次P8补发历史全部核心及overlay资格 |
| 整分支／do-not-merge | 整体研究历史、未经批准路径、大ignored原件 | 不整体合并，不把大原件提交Git，不提升accepted或official |

**本次没有授予任何具体依赖组的merge approval。** “研究档案可保留／进入选择性审阅”不等于合并许可。实际合并仍需明确逐组批准、用户授权及Codex执行；本次不合并。

## 9. 下一轮唯一执行授权：已有四场的局部误差—动作响应诊断

### 9.1 批准决定、科学问题与禁止的替代动作

**批准立即实施并完成本节；新增正式PDE、场恢复/新采样、矩阵装配/算子作用、对偶求解均为0。** 新增支持最多T1/T2/D1/D2四次，whole累计最多3000秒。T通过直接D；必要的普通局部工程恢复按9.8使用专用槽，不为阶段成功另等review。

唯一问题：**seed8的h/p动作为什么只给出小的全局收益？已有保存场能否区分局部响应弱、局部改善被域外恶化抵消、动作增量与原误差方向不一致，以及G与R00/T00输出响应不同步？**

模型、父状态和参考完全不变：新phi90、50×50×140nm、13.5nm，R9父场、已有H8/P8、固定Y6_1，原q15/q28/R13、normal1/extra0，既有q8/q10共同点权。只分析global8/root4以及H8必需闭包root34和其余域；**不生成新seed、p/h候选、transition10或自动选择器**。Y5/holdout/两控制不用于本诊断排序或替换参考。

### 9.2 静态准备：消费原件与小型补证同时完成

canonical仍为`/home/fenics/Projects/NN-Lab-V2`。安全fetch/fast-forward本review，核后续差异和已有工作，不覆盖其他修改。唯一新artifact前缀：

`/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v19_saved_hp_response/`。

先读原合同角色和source_index，绑定四个现存场包，原路径不变：

| 场包 | SHA256 |
|---|---|
| 旧P5 q8，三场＋共同点权 | `7286c09d6b3f3bb3a7ece1cd46284a9a5faafd6ebbcb213e2568b6a32ed1119e` |
| 旧P5 q10 | `82d7bc676e23bea0794caf5e16b3d6c28ee02cb18c57cb59e4bfc08a55759f99` |
| P8 q8，原C0保存包 | `5475cffe826f45217cebd8df35239f4ba8a4a5813657cf2ca7696ce871af792f` |
| P8 q10，最终C包 | `a3f3edca3f1f07fca79c37c1823b1616d6c330c36122ebc405d47ef2f8c20a85` |

旧两包路径与[原合同](outcomes/records/v16_r9_p8_contract.json)的`V15_P5_q8/q10_union_npz`一致。P8 q8为`v16_p8/support/v18_paired_comparison_attempt1/comparison/v16_r9_p8_q8_samples.npz`；P8 q10为`v16_p8/support/v18_paired_comparison_recovery_attempt3/comparison/v16_r9_p8_q10_samples.npz`，均相对`benchmarks/artifacts/task43/`。

同时绑定：原P5 comparison；最终C comparison SHA `1fca6095529c01685717f3db97b8d00302bb90fc1dfb2df9042cff58e9e137af`；R9 plan/owner映射、H8 plan及root34闭包；四场已有modal orders与Av。R9/H8/Y6来源沿原合同角色；P8 modal orders SHA `c7b1ff6033f0a901a6e42f827bd26a9f3e7ab1b046dcf57cd7656548d2e446c8`，Av SHA `f718627465f72c0783f02f60c73256232d73de00ca34128e237fc3be7459d080`。不扫描目录挑替代文件，不从最终文档反推旧运行HEAD。

在同一准备中完成V18-02最小补证：从已绑定原文件提取F两条vanished之前、期间、之后直至四个清空样本的连续原行；C原第672–677行，注明原索引从0还是1开始；对应F/C退出、F三条成功setter及栈、runtime PID/PPID/start_ticks/TracerPid、watchdog/launcher终态和host最终不存在实值。保留原hash、原行号、原字节及clock类型，不直接比较未校准的monotonic与epoch。复制原42数组复核JSON为轻量证据即可，不重施加A6或重新运行旧审计器。

这些只读文字/JSON核对不另设动态槽，不补跑旧测试或全流审计。缺原件、hash冲突或仍不能区分活进程失联与退出竞态时，停止消费受影响端点，明确缺什么；不以新PDE替代缺失证据。可读完整输入满足后进入实现/定向验证，不为补证本身再等待审阅。

### 9.3 最小代码范围与单一绑定

允许新增：

- `benchmarks/task43_hp_adaptivity/analyze_saved_hp_response.py`：只读标准库／NumPy checker，读取已有数据并计算本节恒等式；不导入FEniCS、PETSc、SLEPc或三个研究求解入口，不恢复FE场。
- `src/test/test_task43_saved_hp_response.py`：小合成数组与真实文件拒绝测试。
- `docs/task43_hp_adaptivity/outcomes/records/v19_saved_hp_response_contract.json`：本review的单一输入/规则/目录/预算绑定，无自主扩权逻辑；新回应、结果和当前文档。
- 新前缀下短launch、快照、原件摘录和产物。复用现有watchdog与已验证父链组织，**不修改共享watchdog、activation/ABI、旧三个runner、V18 launch或旧合同**。

checker的工作入口固定为：

`python -u -m benchmarks.task43_hp_adaptivity.analyze_saved_hp_response --manifest <新合同绝对路径> --output-root <D1或D2的唯一data目录>`。

D2可加`--resume-from <D1/data>`，只读取并显式绑定D1已经完整保存的阶次，不改D1。这个接口是本次授权实现项，不假称现在已存在。不得加PDE、sampler、choose-next或任意模型选项。使用分块求和、每次只展开一个q包组，减少无谓大数组复制。

新合同先逐项映射本节，包含旧输入hash、单位、reference方向、完整612键、owner来源、测试selectors、算术容差和四个唯一槽。源码/测试/launch完成后提交冻结；提交后的每次run-manifest在唯一ignored运行槽内记录实际HEAD、文件字节和NumPy版本。tracked规则合同不要求自包含自身commit SHA，run-manifest也不把自身hash加入自身refs，避免循环绑定。无关文档不追认为运行HEAD。不要把旧51源清单换成新计算身份；本纯数据checker记录其实际最小依赖，旧F/C的51源身份继续作为历史来源。

### 9.4 必须交付的局部分解

从保存的R9 `point_cell_global_ids`将共同点分到原180个单元，核`cell_global_ids[local_slots]`相等、全覆盖且每点只归属一次。global ID与forest root必须沿原R9映射，不将global8误作root8。允许对已存点和已存box作确定性归属核对，不重新调用native几何搜索。

令e为Y6_1减R9，d为动作场减R9。以原G内积、相同正权和k0=2π/13.5计算每单元K：

```math
B_K=\langle e,e\rangle_{G,K},\quad
D_{a,K}=\langle d_a,d_a\rangle_{G,K},\quad
X_{a,K}=2\Re\langle e,d_a\rangle_{G,K}.
```

```math
I_{a,K}=X_{a,K}-D_{a,K}
=\langle e,e\rangle_{G,K}-\langle e-d_a,e-d_a\rangle_{G,K},
\qquad a\in\{H8,P8\}.
```

通俗地说：B是原来与参考的差异，D是这次动作实际改变了多少场，X看改变方向是否对准原差异，I才是该块误差平方的净减少。每项同时拆E与curl/k0，保留原量和同一个全域参考分母归一量；**不能把每单元开方后的量相加冒充全域G**。

两阶各交180行表及三块汇总：请求root4／global8；H8必需闭包root34（box `[16.5,5,0]→[33.5,10,30]`nm）；其余域。P8没有请求root34，但仍用同一空间分块便于配对。给B占比、D分布、正I之和、负I之和、净I及抵消；B或D为0时相关系数记N/A，不除零。若报告方向相关度，固定为Re内积除两个范数，不做相位拟合或最优缩放。

全域和须复现既有G平方差和原G；两种恒等式逐单元独立计算，不能把一边定义为另一边后再断言相等。点权单位nm/nm³和curl单位沿原包，不混入m尺度。

共享背景在差中相消，因此该分解不需要新背景。不得凭这一事实新造散射参考norm。**G平方可加，J的最大值和R00相干输出不能按这些单元贡献直接相加。** 本任务不产生“某单元的R00误差”、DWR或目标导向选择器资格。

### 9.5 完整612通道与全局输出响应

读取四场原modal JSON，按相同端口/m/n/s-p键对齐，要求精确612键、唯一且finite，四复幅组各153项；不只读最差项。交付每个通道的四场复幅与保存功率、候选减Y6及动作减R9的带符号差、绝对差和原门限，列出所有功率超1e−6的通道，重点解释R00_s与T00_s；aggregate R/T/Av及R00total继续使用原各自门限。

复幅可用同一归一化下的代数恒等式拆分动作响应：

```math
|a_R+\delta a|^2-|a_R|^2
=2\Re(\overline{a_R}\,\delta a)+|\delta a|^2.
```

这个式子本身是幅值平方，不自动等于物理功率。功率列优先直接读取原保存的物理量；只有原件完整保存对应物理归一因子时才额外核功率重算，不能从零/极小幅值反除权重。无因子不阻塞本任务的模态带符号诊断，但必须标`independent_modal_power_reassembly=NOT_PERFORMED`。保留evanescent复幅，不能因其功率为零便认为没有响应。

重现原完整J分量和最大witness；散射E/H的J分量以共同差分范数结合原hash-bound comparison保存的各自reference norm/floor复现，明确标为分母历史复用，不为此新生成背景或重建散射reference。并列P8/H8的J/G点响应与原冻结ε、收益区间，不重估ε，不把新局部分解用于回写旧accepted结果。q8/q10分别完成，若局部图解释不同就报告采样敏感性或混合原因，不加q12或第三次采样。

### 9.6 验证节点、原始产物与通过标准

只为新checker运行小数组定向测试，首次最多12个展开节点，selector完整清单在T1前冻结；不collect-only，不重复旧11/5/18/20项或全仓pytest。至少覆盖：

1. 非均匀正权、多单元及重排后的覆盖/加和；
2. 零增量、复数同向／反向／正交响应、域内外正负抵消和两种独立恒等式；
3. reference反向、错误owner、缺/重复612键、混包重新绑定外层hash仍被拒绝；
4. 物理功率与复幅平方分开、零幅/evanescent不反除；
5. 输入只读、q8已完成而q10序列化失败时保留原q8，恢复不覆写或静默复制旧输入。

通过标准前瞻固定：

- 原文件前后hash不变，NPZ内嵌目录与每数组dtype/shape/hash/finite一致；q8/q10点数565248/1104000，权正、体积350000nm³；完整180 owner及612 inventory。
- 既有E/curl/H-total/G/J标量复现采用现有保存数据复核尺度：relative≤3e−11、absolute≤1e−15；体积沿旧350000核验尺度，不更改历史结果。
- 对每单元和全域的G平方恒等式，误差≤1e−10乘以`max(B, after_error_squared, abs(X), D, 1e-30)`；分块/分项求和以同样正量尺度核。这里是新算术自洽门，不是放宽旧科学ε或精度门。
- 每阶完成即原子保存compact JSON/CSV；原数组不写入Git。保存完整180表、612表、全域复现、全部超限项及明确科学解释，不能只输出PASS。
- 全部资源/身份/退出/清理合格后，主控亲读数值与原件作最终判断。正、负、抵消、混合或未能辨别原因都可为完整诊断；是否有利不是工程通过条件。

若重现差异只是已确定的索引/共轭/序列化实现错误，按9.8的专用恢复修复；若原件或数学身份仍不相容，不以“应该是bug”自动归因并放行。

### 9.7 唯一launch/root及预算

表中路径相对第9.2节唯一新前缀。外层唯一命令形状为`bash <绝对前缀>/launch/<脚本>`；脚本先实施、审查、冻结，不假称已存在。每个root排他创建、非空拒绝，不删除失败或改名续跑。

| 槽 | 唯一launch | 唯一root | 次数／条件 | 工作／whole秒 | RSS |
|---|---|---|---|---:|---:|
| T1 | `targeted_attempt1.sh` | `support/targeted_attempt1/` | 1，首次新checker验证 | 270／300 | 8GiB |
| T2 | `targeted_recovery1.sh` | `support/targeted_recovery1/` | 至多1，仅T1已定位普通bug受影响节点 | 270／300 | 8GiB |
| D1 | `decomposition_attempt1.sh` | `support/decomposition_attempt1/` | 1，两阶保存数组科学诊断 | 1140／1200 | 8GiB |
| D2 | `decomposition_recovery1.sh` | `support/decomposition_recovery1/` | 至多1，仅D1普通工程失败恢复 | 1140／1200 | 8GiB |

**新增支持最多4次、whole累计3000秒（50分钟）；新增正式0次。** 原正式9/10、封存末槽、旧sanity/D3/T/S/F/C均不恢复。T2和D2不能互换或因不用而变成新科学动作；调用shell即计数，包括watchdog前失败。无watchdog计时记录实际入口whole或NOT_MEASURED，不填0；内层测试/读取时间不重复相加。

预算依据是本轮保存数组独立复核约40.116秒，包含native恢复/新q10采样的最终C为465.386秒；本任务只读已有数组，1200秒whole有余量，不意味着必须用满。静态文本/原件hash准备与人工时间另列，不冒充整轮wall。

CPU1、单worker、无mpiexec、六线程变量1、task VmSwap=0；无MPI并行，不启动MPI/PETSc/SLEPc完整ABI探针。若记录MPI字段，注明未使用MPI／非ABI资格，不能以环境变量假称本次MPI实测。使用原资格化activation供解释器和NumPy，worker局部环境保留既有设置；新测试worker局部设置`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`并记录，避免外部插件引入native导入，不改共享配置。RSS取8GiB及现有动态available/reserve更严者，保留64GiB/15%系统余量规则。

复用既有watchdog、CPU绑定与strace-D直接父链组织。新纯数组worker用标准库核实际PID/PPID/start_ticks、TracerPid、affinity和线程环境，保存开始/结束实值；不为了读取旧场而导入h100的native依赖。逐行资源解析失败否决；真实setter/信号逐项分类；非CPU1成功setter、活worker偏离、swap、未知退出或残留后代均否决。whole清理余量只用于TERM/KILL/reap和保存终态，不延长计算。

### 9.8 普通bug修复、连续执行与硬停止

**T通过后主控核实即可直接D1，成功完成两阶即收口，不等中间review。** 静态准备中的路径/字段/文档错误可以立即修正并继续，保留原失败；不另外计动态槽。

T1失败若确定是新checker/fixture普通实现bug，可局部修复、提交冻结、T2只跑受影响节点；历史未变节点按实际字节/依赖复用，不能拼成最终全套批次。T2仍不通过则停止动态阶段，提交确切缺陷和最小节点，不启动D1凑次数。

D1发生确定的路径、字段、索引、容器或序列化bug，且输入/资源/清理完整、已得产物可信时，允许D2。D2同一受监控Python worker先以`pytest.main`跑最多6个受影响小节点，测试耗时包含在D2预算内，然后调用同一checker恢复；不另起未计数验证driver。fixtures与data隔离，已完成q包只读复用并显式引用；D1不改，D2写自己的data。受影响算法变化使旧派生值失效时，可从同一原数组重算受影响派生值，明确新字节，不能称旧派生结果自动通过。原场不重采样。

以下没有自动恢复权：原件缺失/身份漂移、reference或owner物理不相容、未解释的算术闭合/原指标复现失败、非有限原数据、资源/时间/CPU/swap、父链/tracer异常、必需证据持久化不可信或清理失败。先停止动态消费，保留全部原件和精确缺口并静态定位；只有能明确限定为本checker普通实现错误且其余硬门完整，才可使用尚未消耗的对应恢复槽。在该恢复槽内先运行独立小fixture确证，未通过不得续接checker，不得另起未计数验证driver；不能降低容差、换输入或重解来“修好”。

**科学上无明确响应、域外抵消、p/h未辨优都不是bug，不得据此使用D2。** q8/q10解释不一致也只报告未决，不追加阶次或PDE。槽或累计预算耗尽即结束，剩余秒数不换次数；失败不退款。

### 9.9 下一交付与仍锁定的工作

交付`response_v19.md`、`outcomes/records/v19_saved_hp_response_results_v1.json`、两阶180单元表和完整612通道表、最小原件摘录及实际测试/源/命令/资源/费用索引；更新当前summary、manifest、模型总账和进展，旧review／合同／失败／运行身份全部保留。科学解释至少回答哪些区域的原差异大、动作改了哪里、是否发生抵消，以及这些场差结论与R00/T00全局响应是否一致；不能把局部G直接当目标敏感度。

本轮不得启动新的P8/H8/R9/A1/A2求解、fresh baseline、参考/控制或holdout重算、q/R扫描、对偶PDE、其他seed、p7、h+p、E、成本campaign、迭代、0.7nm、NN/FTT、共享环境重建或任何合并。后处理结果可支持下一次有理由的科学决策，**不自动解锁下一PDE**；本次已经给出可执行诊断及预算，不以再写一份归档回应代替实施。

## 10. 提交声明

本次只新增本报告，不修改master，不执行合并，不修改旧review、冻结合同、失败或运行身份；未运行项目测试或科学计算。review完整提交SHA在提交产生后由交付消息提供，不制造文件自包含自身SHA。

[round]: https://github.com/Rookie1234567/MyFEniCS/blob/5ceb617ee85058bc29da7ff126a9d594779dc34b/benchmarks/task43_hp_adaptivity/round1_candidates.py
[h100]: https://github.com/Rookie1234567/MyFEniCS/blob/5ceb617ee85058bc29da7ff126a9d594779dc34b/benchmarks/task43_hp_adaptivity/h100_anchor.py
[compare]: https://github.com/Rookie1234567/MyFEniCS/blob/5ceb617ee85058bc29da7ff126a9d594779dc34b/benchmarks/task43_hp_adaptivity/compare_round1_candidate.py
[launch]: https://github.com/Rookie1234567/MyFEniCS/blob/5ceb617ee85058bc29da7ff126a9d594779dc34b/benchmarks/task43_hp_adaptivity/v18_p8_stage_launch.sh
[tests]: https://github.com/Rookie1234567/MyFEniCS/blob/5ceb617ee85058bc29da7ff126a9d594779dc34b/src/test/test_task43_p8_execution_recovery.py
