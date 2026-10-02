# Response V10：两胞元 full3D p4 的 Q0–Q2 运算审计通过

**结论：两胞元参考结构的 Q0–Q2 有界三维运算资格通过；尚未授予 quotient 求逆、外层求解或目标规模资格。** 固定 clean source `35dd9e5c39939d14bbded98f288007aff4a08368`、tree `38fde56b7e8988194699a8943145d7b087f22318` 的独立 checker 为 **4842/4842，evidence_valid=true**。本轮只检查原方程的表示、作用及恢复，没有 global/q factor、PDE solve 或官方物理输出。

两胞元结构把原80个三维单元按 y 平移相位拆成两个40-cell三维空间，每个空间仍保留边、面、胞元内部及全部 y 通道。它希望将未来参考算子的建立和运算限制在较小空间；代价是必须证明相位、原始端口、内部恢复及四个分支都与原三维方程相同。此次完成这些运算门；实际收益、求逆成本和大型收敛仍待测。原全Ny矩阵及 maps 保持历史 validation authority 身份，候选 setup 不借用旧 full maps，不创建候选 fullNy S/F/Q。

## 完整覆盖与误差含义

以下误差表示“新表示对原表示的运算差异”，不是已求得物理解的残差。CSR比较逐项包含全部稀疏矩阵元素；FE列桥接包含所有内部通道。跨块泄漏表示不同平移分支之间还剩多少数值耦合，norm和max均使用两侧较弱的对角块缩放。

| 对象 | 实测覆盖 | 授予范围 |
|---|---:|---|
| 原三维离散 | 80 cells；15872 independent /8640 interior /7232 trace | 与V9冻结p4权威比较 |
| 两个本地三维空间 | 每侧40 cells；7936 independent /4320 interior /3616 trace；8940 storage | 全部内部与MPC slave语义保留 |
| 原物理端口 | 两sector 228 /304；四q端口76 /152 /152 /152，合计532 aliases | 原mode对象、顺序、截止与alias不合并 |
| 四个增广q块 | q0=1884；q1/q2/q3=1960 | 全CSR norm/max门各≤1e−11 |
| 四q FE桥接 | 每q全部3968列 | 最大相对列差≤1e−12；不以随机抽列代替 |
| fresh原作用与完整恢复 | 两侧各4320内部RHS条目全非零，全部port RHS保留 | manufactured state 的原volume+DtN运算及native storage恢复 |
| 自身实际basis /Gauss | local dimension300；degree23、144 facet points | 同一次live carrier逐模式raw资格 |

| 运算指标 | 保存字段的精确最大值 |
|---|---:|
| 四CSR相对Frobenius差 | 7.623844459299511e−16 |
| 四CSR相对最大元素差 | 1.2633342716896627e−15 |
| 每q全部3968 FE列差 | 1.112995121386375e−15 |
| 十二cross控制相对norm /max | 6.7295961749368e−16 /1.0462045068457151e−15 |
| 532模式raw fold /reverse lift | 3.5511349852001364e−15 /5.034776843574962e−15 |
| fresh原FE作用差 | 9.123615983914468e−16 |
| 完整增广reduce作用差 | 8.012802270233163e−15 |
| 完整原storage恢复差 | 2.0082399999380633e−13 |

**十二cross控制的来源必须分别解释：** 四个同twist off-block来自本次fresh local贡献；八个跨twist控制来自不可变旧原S/maps，使用刚通过的全部3968 FE列等价关系，并由两组fresh full-original action witness补充。不能称为本次候选独立重组装了全部十二cross blocks。完整恢复采用原有108×108 cell-interior LU；global/q numeric factor_count=0不表示没有使用胞元内部LU。每sector记录20个共享LU buffer。

## raw先保存，再逐层核算原cutoff

两个live sector都在mask之前保存raw泛函、literal oracle、原mode身份和typed-array packet，随后检查既有component mask及最终C/D mask。原相对cutoff `1e−13`、绝对floor `1e−30`保持；没有通过改阈值或删除泄漏来通过Gate。以下支持计数是逐模式条目相加，不是独立FE行数。

| sector | component raw /retained /lost条目 | final raw /retained /lost条目 | 全mask绝对rank-one三角上界 |
|---|---:|---:|---:|
| b0，228模式 | 350208 /58384 /291824 | 116768 /116752 /16 | 6.143727009446718e−10 |
| b1，304模式 | 466944 /77832 /389112 | 155664 /155656 /8 | 5.120808720269152e−10 |

所有mask引入条目为0，unchanged-policy defect为0；component最大loss norm分别1.7180923288855802e−13、1.8518128112281432e−13。上述绝对三角上界核算逐模式损失，不是完整求和算子的已认证相对norm。每侧五态action/recovery及532模式raw双向运输保留在receipt/ledger；局部receipt的deferred列表保留其原时点范围，由外层Q0–Q2记录补齐union、maps、块比较和manufactured恢复，不能据此改判Q3–Q5。

## 实际资源与未测成本

| 监督运行 | wall seconds | 采样同时整树RSS bytes | 状态 |
|---|---:|---:|---|
| worker | 334.13608062599815 | 741564416 | exit0、swap0、后代清场 |
| 独立checker | 10.395193903998006 | 312737792 | exit0、swap0、后代清场 |

两次按顺序运行，derived总wall为344.53127452999615s，满足本轮总600s及整树1.5GiB准入；每次分配另留128MiB证据空间。RSS为采样峰，不是未采样硬峰；两个run的峰值不相加。串行complex128/int32、MPI1、math threads1 ABI绑定成功，未证明与历史WSL或工作站ABI等价。

| 已记录setup或named payload | b0 | b1 |
|---|---:|---:|
| local build seconds | 21.705134513002122 | 21.820452462001413 |
| kernel seconds | 21.435770449010306 | 21.56794404699758 |
| local Schur相关seconds | 0.2079198300052667 | 0.19012704101623967 |
| retained local Schur bytes | 11796480 | 11796480 |
| direct trace port payload bytes | 4669440 | 6225920 |
| unique port owner bytes | 4809504 | 6295888 |
| resident原H /Hhat各自bytes | 831744 /831744 | 1478656 /1478656 |

每侧assembly临时raw tensor23040000B、oriented Schur11796480B，身份缓存93312B；对象生命周期、共享和alias不同，不能相加当RSS。final assembly/插入/预分配字段为null、action-only未运行；没有独立pure-LU、pure-PC apply、quotient inverse或outer solve计时。worker事件显示b0列桥接57.1976s、raw资格110.8114s、完整恢复132.9571s；b1相应204.4741/293.8034/316.2017s，全部cross控制331.7056s。事件与监督时钟未声明精确offset，不能把采样峰硬归因某个数值阶段。此次包含大量证据检查，不与V9 worker wall作加速比较。

## 身份与尚未资格项

[compact证据](outcomes/records/two_cell_p4_v10/two_cell_p4_v10_compact.json)绑定运行命令、input、ABI、原始记录和资源hash；[独立复核](outcomes/records/two_cell_p4_v10/independent_verification.json)核对1267个冻结源文件、2222项artifact hash及1064个raw packet JSON描述符，确认4842个唯一门均通过。它只读保存证据，没有导入solver、加载数组运算、重跑checker/JIT/PDE/factor/solve；[完整范围](outcomes/records/two_cell_p4_v10/independent_findings_zh.md)保留来源区别。独立receipt SHA256为 `9ee0c10eef98fc10c125cf178c4aa949b9dea7de4292cf7a37bb132c20d9f184`。

audit report SHA256为 `d0bade55828b8e842f240ad3eb8b5d79d9adfdeb06976ad5be8e0a8fb2aeb37f`，checker为 `e3afab9490fce0a19f3ac868dbecac73957ddb2da5d528c1086a57c5e2b86b0f`。checker的artifact hash是canonical descriptor digest，单独manifest文件hash对应格式化文件字节，两者用途不同；解析后的descriptor完全相同。旧 `ad356715da86ab34fa6b10838cccc8629b3f6e8b` p4权威保持原身份，显式old/new dependency diff已逐项核对。

同source/tree的已存source/ABI测试Gate为183 passed、1 evidence-only skip、4 actual-FFCx/532测试deselected，watchdog summary SHA256 `a0337869b6ae1b1cd25a0c0aac2213b83470bcc0c585e3f00c7fb8948d3f6f99`；compileall及CLI合同通过。这不是full repository CI或ordinary default的数值回归。既有默认、其他分支、V5–V9失败和受控停止保持原分类。

Q3–Q5 quotient inverse、完整物理forcing、outer replacement、非可分三维notch及完整物理输出仍未资格。后续snapshot rehydration仅为计划：须用public carrier constructor及完整physical/local assembly/maps/source绑定和精确numeric digest；历史raw JIT provenance须与新建volume/recovery分开记录，目前未实现、未运行。p6、强对比、目标模态截断/几何/连续精度、官方R/T/A、MPI/restart及跨机器ABI均未资格。

用户目标仍为原尺寸50×25×140 nm规则Si光栅、λ=0.7 nm、≤2 TB整机物理RAM及≤48h solve，并保留未来完整三维缺口能力。本轮只提供scaled full3D架构证据，不作目标能力承诺。继续补足main Task40extra与MyFEniCSx_task37_extra；大型工作站运行由用户执行。本报告由已验证的external草稿整合；GitHub发布及渲染验收由后续发布回执记录。
