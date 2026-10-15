# 324-cell 恢复检查器调查：同 raw 的 Schur 传递仍失败，完整解未资格化

日期：2026-10-15。模型：18×2×9＝324 cells，z 分层 2/5/2，完整 p6、ordinary p4，BAL_H，FGMRES restart=32、正交化 refine_always。此报告只归档本轮已保存证据；不替代原始失败记录，也不改变任何验收阈值。

## 1. 当前结论

本轮证据已推进到全部 324 cells、共享 trace 与 80 个原始端口模式的保存 x8 回放。新增同 raw 对照确认：不能将全部异常归因于 split/raw 两条装配路线差异。当前可分清四件事：

1. **局部 checker 的自消盲点已实测。** 两个真实 cell 的旧内部公式给零，独立 raw 块给非零；不依赖 LU/H 的 helper 能检测制造错误和真实 cell 扰动。
2. **原始和 global raw 两个 identity 门仍 FAIL。** 原值 2.4309679506887283e-10；完整 raw 四块重建后为 1.88449868884189e-10，均大于不变的 1e-10。
3. **与 native 相同算子家族的 split 路径能重现保存作用。** 分别执行 curl/mass kernel，再独立完成全局 scatter、复 MPC 拉回与原端口组合，所得完整残差与保存 native 的相对差为 1.9173085240314842e-14。此项是独立装配一致性，非跨算子家族真值、Schur 恢复资格或求解收敛。
4. **同一 raw 到原保存 Schur 的 trace 传递仍 FAIL。** 65 个定向类的 LU/H/F/S 均匹配原四项 hash，原场和保存 r_s 未替换，trace 传递相对差仍为 6.565891347696912e-10 > 1e-10。internal 与 port 各自通过不能抵消此失败。

既有对照量出了 combined-rank2 raw 与 split-rank1 native 两条路径之间的差异，并表明几何差异不是唯一解释；新的同 raw 负证据说明同路线恢复/Schur 传递也必须独立排查，尚未证明任何单一原因解释全部失败。**生产修改仍只是提案，未实施；没有 accepted field、官方 R/T/A 或空间收敛结论。** 原始 x8 真实残差约 0.0463，诊断续段累计耐久 72 步的残差约 0.02184，均未改变。

## 2. 两段求解：科学结论与成本分别记账

“真实 native 残差”指把恢复后的完整场代回原始离散算子，衡量原方程还有多少未满足；“recovery identity”则比较原始作用和凝聚/恢复表示是否一致。前者是求解质量，后者是两条计算路径的一致性。进程正常退出、资源门通过都不能代替这两个科学判据。

| 阶段（measured） | 监督墙钟时间 / s | 外迭代及保存状态 | 原始科学判据 | 结论 |
|---|---:|---|---|---|
| 首次 native 求解 | 333.752768448001 | 8 步完成，保存完整未资格场 | identity＝2.4309679506887283e-10 > 1e-10；native＝0.04626585819263524 > 1e-6 | 第 8 步由 identity 门停止；不是完成 200 步的收敛试验 |
| 从 x8 开始的诊断续段 | 601.0627218169975（含终止清理） | 本段 67 步完成，第 68 步 PC 在途；耐久 checkpoint 为本段 64 步 | 最近 native＝0.021842359971579305，identity＝2.463975257620764e-10，均未过原门 | 600 s 硬限触发 TIME_LIMIT，SIGTERM；无最终完整场包 |

首段 pure KSP 为 57.066331987 s，solver clock 为 75.06004874999053 s，均与 333.752768448001 s 的整段监督时间不同。独立最终 native 重算为 0.046265858192633735；不能用这点显示位差改变上述结论。

续段重新建立 Krylov 基和因子，使用原 x8 非零初值，并非不间断 200 步 FGMRES。计入先前 8 步后，总完成 75 步，保守预算计费 76 步；最新耐久点累计为 72 步。checkpoint64 不能抹掉已完成的 65–67 步及在途 68 步；32/64 的重复 monitor 不计作新迭代。200 步上限名义剩余 124 步不等于授权自动续跑。

本段第 67 步只有递推残差 0.021785871751169337，不能冒充该步的独立 native 残差。11 条 native identity FAIL 记录（含重复采样）全部保留。残差下降只是诊断观察，未证明最终可收敛，也不能据此断言已形成 200 步平台。

## 3. 保存包复核排除了什么

同一完整场、原 RHS 和 retained checkpoint 的对应 payload 逐字节一致；两份保存的独立 native 残差向量之差范数为 0。identity 绝对差为 3.426276423814599e-10，全在非 slave 行，slave 分量为 0。四项分母保存值为 1.4094288749647617，独立重算为 1.409428874964764，相对差重算为 2.4309679506887184e-10，仍 FAIL。

这项保存包复核支持排除本次包混淆，并在观测误差尺度上反对 native 重复作用不稳定的解释；它本身不构成原始算子正确性或跨来源算子资格证明。内部大操作尺度为 1738561.7200576293，不能替换原来的四项 identity 分母以获得“通过”。

## 4. cell164：真实对象上的最小机制验证

凝聚先消去单元内部未知量，再从边界/接口未知量恢复内部场。旧检查把恢复得到的内部向量分别送进同一个 LU 重构作用再相减；若两路恰好使用相同的恢复值，就可能相互抵消，而遗漏原始耦合块的误差。独立原始块检查直接计算 Aii·i + Ait·t（本次内部 RHS 和该 cell 的端口贡献为零），避免以恢复公式检查恢复公式。

cell164 按实际独立 interior 行上保存 identity 差最大者选定，远离上下端口平面。原始/定向张量、映射及 MPC 展开身份门通过，LU/H/F/S 四个身份与原始保存 recipe 一致；保存 Aii/Ait/Ati/Att 哈希不等于四块作用都完成独立检验。本次实际数值比较仅覆盖该 cell 的内部行。

| 同一保存 x8 的 cell164 指标（measured） | 范数 |
|---|---:|
| 旧 binary64 内部残差 | 0 |
| 冻结 Ht 的 wider / grouped 旧公式 | 0 |
| 原始块 binary64 残差 | 2.3234124683004288e-11 |
| 原始块 wider 残差 | 2.2163696344155388e-11 |
| 保存的独立 native 内部残差 | 3.061290494933839e-11 |
| raw wider 与保存 native 的向量差 | 2.058170613669388e-11 |

因此自消盲点已经在当前对象上获得证据，不再只是历史 108/144-cell 的类比。但 raw wider 与 native 仍存在非零差距；尚未说明全部来源。不能将其表述为“纯舍入已证实”或“identity 已修复”。首次 cell164 回放未直接记录 i 与 Ht 的逐字节比较，因此该首次记录本身不足以证明两者身份；随后两单元回归补上了直接逐字节证据，见第 5 节。

平台所谓 longdouble/complex256 实际只有 64 位有效尾数（binary64 为 53 位），不是 113 位四倍精度，更不是精确算术。扩展精度只作用于冻结 binary64 输入的乘加；没有高精度装配或高精度因子分解。

此单元诊断监督 4.277201388991671 s，1 次原始局部张量读取、1 次 fresh binary64 局部因子、0 次 wider 因子、0 次外迭代、0 次全局 A 作用、0 个全局 coarse 因子；没有构建完整 finebank 或 p4 空间，未更新解。本次单元诊断本身不覆盖共享 trace 或全局恢复 identity；后续全局结果见第 6 节，完整收敛原因仍未闭合。

## 5. 源码审计与最小检查器回归

只读审计未发现本条实际路径的 RHS、端口符号或共享行重复累加错误。实际 caller 使用 rhs_is_mpc_dual=True；native 与凝聚共用同一 B/D/H，恢复修正的符号正确。

另有两个离开当前路径的 API 缺陷：raw RHS 模式下 native/Schur 的 MPC 对偶转换不一致；泛型 direct B 接口对重复行的 buffered 累加与 reduced 路径不同。实际 caller 和 carrier 的约束使这两项不触发，不能将其写成本次 324-cell 的致因。

### 独立 raw 内部检查器：两单元候选修复已实测

新的独立 helper 只接收原始 Aii/Ait、内部/trace 向量、RHS 和显式 Bi/alpha，不接收 LU 或 H，因而不会沿旧公式发生相同的自消。它检查原始内部方程的余量；仍同时保留旧指标，未更改总 identity 公式或阈值，生产源码未修改。

| 真实保存 x8 对照（measured） | cell164（最大差单元） | cell8（普通对照） |
|---|---:|---:|
| i 与 binary64 Ht 逐字节一致 | true | true |
| 旧内部残差范数 | 0 | 0 |
| 新 raw checker，binary64 | 2.3234124683004288e-11 | 1.1048928515542827e-11 |
| 新 raw checker，wider | 2.2163696344155388e-11 | 1.0880962252647429e-11 |
| 保存 native 内部残差范数 | 3.061290494933839e-11 | 1.536984445137231e-11 |
| raw wider 与保存 native 的向量差 | 2.058170613669388e-11 | 1.031587430953019e-11 |

cell8 在读取 packet 残差前，按“中间物理层、严格非端口、排除 164 后最小实际 cell 索引”选定，非事后挑选小误差案例。两单元的全部 9 项映射/内部-trace 身份门均通过；四 raw 块 hash 绑定及原始 LU/H/S/F 匹配，实际作用仍仅测内部行。

为检验新 checker 会否漏掉非零项，两真实 cell 另用人为制造的非零内部 RHS 和预定内部扰动做控制。扰动响应与 −Aii·delta 的差分别为 8.374080860394655e-13 / 2.1655963865675918e-13，通过各自操作尺度舍入容差 6.960003470816775e-7 / 3.612476267806251e-7。它们是局部响应回归的绝对容差，不是完整 identity 的 1e-10 相对门；制造 RHS 不替代原 RHS，也没有修改保存的原场。

一个 2×2 人为错误 H、非零 RHS、非零 Bi·alpha 反例中，旧公式仅给 2.7755575615628914e-17，新 checker 给 0.1442220510185597，与显式原始方程 0.14422205101855962 一致。缺失 Bi 拒绝、Bi 不能忽略及扰动检测等 9 项控制均通过。这个反例证明 helper 能看见指定错误，不能冒称真实 PDE 残差或真实端口资格；两个真实 cell 的端口支持均为空，非零 Bi 只在制造例中覆盖。

此回归监督 6.031764024985023 s，21 个资源采样，采样进程树峰值 410787840 B，child exit0 且无残留进程。两个 cell 依次重建，各 1 次局部 binary64 因子（合计 2 次）、0 次全局 coarse 因子、0 次外迭代，最大同时仅保留一份 cell raw/factor bundle；无生产修改、无原场更新。这一阶段可称“局部 checker 候选修复已实测”，不能据此宣称生产全局集成、共享 trace、总 identity 或 BAL_H 收敛问题已验收。后续共享行回放没有改变原始 FAIL。

独立终审已核对全部 21 行资源采样、10 次实际准入、两次完整映射与原始 payload 身份，以及 i/Ht 直接哈希；结论为局部独立 checker 指定回归通过，全局 identity 与求解验收仍未证明。5 项 pure tests 的通过来自原测试日志，终审未重新执行科学计算。

## 6. 新增全局回放：区分 raw 与 split 两条计算路径

“combined-rank2 raw”先形成原始单元矩阵，再乘保存场；“split-rank1”直接调用原始 curl 和 mass 作用 kernel，再相减。这两条路线在数学上对应同一离散问题，但张量形成、局部几何、乘加与求和顺序并不相同。对严重抵消的小差值，有限精度结果可能不同；复现路线差异不等于已分离所有致因。

### 6.1 两真实 cell 的 split 路径逐字节重现 native

使用实际几何和原始缓存 curl/mass kernel，cell164/8 的内部 residual 均与保存 native 逐字节相同，向量差范数为 0。cell164 改成 canonical 几何后相差 7.230315837169761e-13，而 canonical split 与 raw wider 仍差 2.0544752055933004e-11；cell8 的实际/canonical 几何与输出完全相同，split 与 raw wider 仍差 1.031587430953019e-11。因此不能只归因于几何坐标。各项是向量差范数，不能直接相加成“原因百分比”。本实验仍未将 rank2 张量形成和 contraction 乘加误差分别隔离。

### 6.2 global raw：覆盖完整四块和端口，原门仍失败

逐流读取 44 个原始张量、65 个定向类，覆盖全部 324 cells 的 882 个局部行与内部/trace 四块。每 cell 用保存场作用原始矩阵，经共享行累加和原始复 MPC 对偶拉回，最后仅在全局层面一次性计算 RHS 减体积作用与端口作用。端口项使用实际重建的四个原始 surface form 与完整 80-mode carrier；B·alpha 和 B·Hp^-1·ep 独立计算，后者使用保存 Hp^-1·ep。没有新 factor、Hp solve 或 FGMRES。

| 完整保存 x8 比较（measured） | 绝对差范数 | 四项尺度 | 相对差及原限值 | 判定 |
|---|---:|---:|---|---|
| 原 Schur/恢复表示 vs native | 3.426276423814599e-10 | 1.4094288749647617 | 2.4309679506887283e-10 > 1e-10 | 原 FAIL 保留 |
| global raw 四块恢复 vs native | 2.656066866886911e-10 | 1.4094288749647177 | 1.88449868884189e-10 > 1e-10 | 仍 FAIL |
| global split 独立装配 vs native | 2.7023099960048763e-14 | 1.4094288749745847 | 1.9173085240314842e-14 < 1e-10（诊断限值） | 仅同家族装配一致性 |

raw-native 差分成 active trace 1.306239486609056e-10、interior 2.3126672058464763e-10、slave 0；完整 raw 内部余量范数为 2.4321210504256346e-10。新版与旧版四项尺度仅差 −4.39648317751562e-14，没有更换分母来取得通过。尺度里的 native 输出由保存 effective RHS 减保存 residual 重建，非本轮新增 native Ax。

### 6.3 global split：完整共享行装配复现，但不是 Schur 验收

在同一个 x8 上执行 648 次原始 split kernel（每 cell 各 curl/mass 一次），保留原始实际几何、方向、共轭 MPC、共享行 scatter 以及全部 80 模式端口项。global split 与保存 native 差为 2.7023099960048763e-14，其中 trace 约同值、interior 4.372524718613955e-27、slave 0。全局并非逐字节相同；两单元内部的逐字节结果不能推广为全局逐字节相等。

split-volume 与 combined raw-volume 的向量差为 2.6560669860016805e-10，与 raw-native 全局偏差同量级。错误 mass 符号、遗漏 MPC pullback、错误 B·alpha 符号的控制分别给 1278.1506004627797、519.0844755159277、0.8669880395436156，说明本装配对照能检出这些指定错误。

这里复用了 native 家族原始 kernel，独立的是装配和残差组合过程。因此该结果不能授予原 raw/Schur/recovery identity、连续误差或最终场资格。旧 2.43097e-10 和 raw 1.88450e-10 两个 FAIL 同时保留；未接入 live RetainedOuterAdapter/solver，未进行新的迭代求解。生产路径修复及其资格验证仍待完成。

特别要注意：同家族 split 装配一致性对任意给定场都可能成立，并不说明该场已解出方程。最终 native residual 能拦住大的方程误差，也不能单独保证 Schur/F 传递正确。当前实际门保持 native 全场 1e-6、port 1e-8、internal/identity/Schur-port 各 1e-10；saved 跨来源 1e-9 检查尚未执行。此前拟议的“同 rank2 raw 的 e_FE 与保存 Schur/F 传递”对照现已完成受限保存场回放，trace 门失败，见下节。这是新增诊断负结果，不是生产修复或资格通过。

独立终审核对了 109 个资源采样、9 个准入门、12 份保存数组的 layout/hash/norm，以及 7 条保存向量公式的逐字节关系；raw03 的 6 个既有向量保持不变。按行分量来自运行时分区，独审只核对范数平方闭合；遗漏 MPC 的控制值来自运行时，未导出的 unrestricted 向量没有再次独立重算。

### 6.4 新增同 raw → 原保存 Schur 对照：trace 门仍 FAIL

此对照不再拿 combined raw 与 native split 互比，而是在同一 raw 路线上，检查完整内部余量经过原 F 传递后能否重现原来保存的 Schur 残差。逐类重建 65 份原始 LU/H/F/S，**每类在使用前都与原四项 payload hash 完全一致**；44 个 raw 类和 324 cells 全覆盖，原场与原保存 r_s 不变，不另造更有利的 r_s。四项身份合同包含原 LU 数组 hash，不额外声称存在独立 pivot hash。

trace 检查计算保存 r_s,t 与“raw_e,t 加逐 cell 共轭 MPC 拉回的 F·raw_e,i”之差；port 检查保留原 B/D/Hp 和非零内部 B/D 项（各 4908 个非零条目）。trace 尺度在运行前已声明为保存 r_s,t、f_t、拉回后 raw 体积 trace、B·alpha trace 这四个范数，加逐 cell F·raw_e,i 散射项范数之和。它是单独的传递门，不能替换旧 native identity 的分母或覆盖旧 FAIL。

| 同 raw 传递检查（measured） | 绝对范数 | 事前定义的操作尺度 | 相对值 / 限值 | 结果 |
|---|---:|---:|---|---|
| trace 传递差 | 1.0318252087243511e-9 | 1.5714929688659558 | 6.565891347696912e-10 / 1e-10 | FAIL |
| port 传递差 | 1.1198348455945077e-27 | 11.52187425135603 | 9.719207319613928e-29 / 1e-10 | 此项 PASS |
| raw 四块 internal 余量 | 2.378929984709598e-10 | 1738561.7200576295 | 1.3683322008440068e-16 / 1e-10 | 此项 PASS，非全局 identity PASS |

独立保存向量复核重算 trace 绝对差为 1.0318252087243505e-9、相对值为 6.565891347696908e-10，结论相同；两条 trace/port 保存公式逐字节一致，8 份向量 hash/norm 与原场/r_s 身份核对通过。分母求和及保存 Schur 范数经独立复核，未保存的 raw/B/D/Hp 作用范数及逐 cell 尺度项仍属运行时观测，不冒称再次执行原始作用。

本次按四块分别收缩/分组得到的 internal 范数 **2.378929984709598e-10**，与前次 whole882 直接作用中的 **2.4321210504256346e-10** 不是同一算术记录，不能相互替换。internal 的大操作尺度与 trace 或原 identity 尺度也不同，不应仅因 1.368e-16 很小就推断整体恢复正确。

监督 21.134923851001076 s，采样进程树峰值 479621120 B，81 个资源采样与 71 个准入门全核对，exit0、无残留进程。65 次 fresh 局部因子合计 6.790045437199296 s，总传递计算 11.785484534979332 s，均包含于监督墙钟，不能再相加；0 个全局因子、0 次 FGMRES，未保存局部因子，未改生产源或控制流。首类 S 由测试循环别名额外保留 2985984 B 至函数返回，仍在原 128 MiB 局部预留内，未据此领取释放或驻留 credit。

这项负证据与原 native identity FAIL 同时存在：split 装配的一致性不能证明 Schur/F 传递正确，也不能解释或消除全部异常。当前继续做局部误差分解，生产变更和新 FGMRES 尚未发生，完整场验收仍关闭。

## 7. 资源与资格边界


| 运行（measured） | 地址空间硬限 | 进程树 RSS 门 | 采样进程树 RSS 峰值 / B | 退出与清理 |
|---|---|---|---:|---|
| 首次求解 | 7 GiB | 8 GiB | 3003396096 | exit0，已验证进程退出；科学 FAIL 保留 |
| 诊断续段 | 7 GiB | 8 GiB | 3004440576 | TIME_LIMIT / exit -15，无残留进程；未证明 Python finalizer、cache RESTORED 或逐 native owner 析构 |
| cell164 回放 | 7 GiB | 8 GiB | 390860800 | exit0，已验证无残留进程 |
| 两单元 checker 回归 | 7 GiB | 8 GiB | 410787840 | exit0，已验证无残留进程；全局资格仍未通过 |

四次均记录 zero swap。RSS 是采样同时进程树口径，不是对象累计大小；未计 allocator-release 或映射驻留回收 credit。首段和续段新 artifact cap 各为 128 MiB，cell164 和两单元 checker 各为 64 MiB。资源通过不授予求解、物理或生产资格。

新增阶段仍受 AS 7 GiB、进程树 8 GiB、120 s、64 MiB 新 artifact 上限及 zero-swap 约束。以下时间为各次监督完整墙钟，失败尝试也计费，不能只报成功重试。

| 新增阶段（measured） | 监督时间 / s | 采样进程树 RSS 峰值 / B | 结论及实际失败边界 |
|---|---:|---:|---|
| 两cell split candidate01 | 1.7574325010064058 | 117923840 | CFFI 导出名误用 C-only alias，首 curl 扩展载入后失败；0 次 kernel，无 mesh/raw 工作 |
| 两cell split candidate02 | 6.537583021010505 | 462667776 | 修正实际导出及接口预检，8 次局部 kernel，exit0 |
| global raw candidate01 | 36.70586303700111 | 409399296 | 324-cell raw 工作已完成；surface 原始 O0/g0 options 门拒绝，无 surface module/kernel |
| global raw candidate02 | 12.57078115499462 | 408920064 | raw 与原 surface/carrier 工作已完成，complex 元数据 JSON 序列化失败；阶段根据 traceback/控制流判定，失败 surface JSON 未写出 |
| global raw candidate03 | 12.317749255016679 | 433082368 | 仅修元数据编码后完整产出；exit0，科学 identity 仍 FAIL |
| global split candidate01 | 28.16528852900956 | 520204288 | 648 split calls、324 raw cell actions、80 modes；exit0，仅装配一致性通过 |
| same raw → Schur candidate01 | 21.134923851001076 | 479621120 | 65 个原 hash 匹配的局部因子；exit0，trace 传递 FAIL，未改生产 |

所有尝试均保存原失败和已执行工作，监督确认无残留进程，不据此推断逐 native handle 析构或 allocator 已回收。global raw 三次合计 236 个资源采样和 17 个准入门经独立审计；数值结果与过程退出分别判断。

费用账已更新到 v116，完整保留上述失败和成功阶段。账中 128 个阶段的已知终态时间字段为 28280.248524167997 s，继承的累计下界字段为 36415.681737541 s；这两个字段范围不同，不能相加，也不是精确端到端耗时。准备时间单列且非零，不能因最终成功而冲销旧费用。相邻 JSON 仅记录小型摘要与账本 SHA256，不上传账本或其重型数据。

下一步应优先分解同 raw trace 传递的局部误差，同时保留 raw/native 路线差的独立记录；生产接口、trace-only/port-only/mixed 与完整 RHS 回归仍未验收。当前工作为保存场诊断，不能以此重标旧解或自动续跑。不得用 native residual 反推被检查量、替换 identity 分母或放宽阈值。

## 8. 证据与发布边界

相邻 [evidence.json](evidence.json) 保存源文件 SHA256、关键标量、成本记账和未资格项。原始证据入口以文件 basename/相对路径标识，重型 payload 仍留云端，不随报告上传。

- native_solver_attempt01_terminal_review.json
- native_solver_attempt01_saved_packet_vector_review.json
- native_diagnostic_attempt01_terminal_review.json
- recovery_identity_readonly_audit_20261015/report_zh.md
- phase4_step8_cell_replay_source_terminal_review.json
- phase4_step8_cell_replay_candidate01/attempt01/{summary,result,selection}.json
- phase4_step8_internal_checker_candidate01/attempt01/{summary,result}.json
- phase4_step8_internal_checker_source_terminal_review.json
- phase4_step8_split_kernel_source_terminal_review.json
- phase4_step8_global_raw_source_terminal_review.json
- phase4_step8_global_split_replay_candidate01/attempt01/{summary,result}.json
- phase4_step8_global_split_source_terminal_review.json
- phase4_execution_ledger_v115.json、phase4_execution_ledger_v116.json（仅绑定摘要与哈希，不上传原账）
- phase4_step8_same_raw_schur_source_terminal_review.json
- phase4_step8_same_raw_schur_saved_vector_review.json
- phase4_step8_same_raw_schur_candidate01/attempt01/{summary,result}.json

本次仅 connector 发布中文报告和小 JSON，范围限 docs/task40extra_dot_parallel_cloud。未发布实现代码、矩阵、因子、完整场、数组或大归档；此次发布不附带额外计算。源码审计基线为 322e62e11a80969b3a35f0cbb08b25c11c539ea6；报告提交的远端 HEAD 与该计算来源身份必须区分。
