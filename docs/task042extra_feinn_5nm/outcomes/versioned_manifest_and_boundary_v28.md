# V28：版本化清单与全模式边界的实物资格

本轮解决的是接收端长期无法使用缺失历史原件的问题。新版本保留原物理配置，却把可获得的V27清单明确命名为独立实例，再用不同的计算路径核验其全部模式字段。通过后才让原生有限元面组件消费它。收益是得到可实际读取的边界包，代价是独立全量检查、完整数组和监督成本；它不能证明新旧清单逐字段等价，也不能替代完整体方程求解。

| 身份 / 物理范围 | 固定值 |
| --- | --- |
| 新schema / instance | schema2；W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28 |
| 清单bytes / SHA256 | 36263033 / 7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e |
| 有序key SHA256 | 03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec |
| 原物理payload SHA256 | a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f |
| 原物理 | λ0.7nm、50/25nm周期、z=-10/130nm、Si17/120nm和原三维缺口、掠角1度/phi0/s、上air/下Si、exp(-iωt)；原auto选择及归一化 |
| 原代表面 | top/bottom(100,1)，x为90/46/46/90分段；实际x宽8.5/46nm、y宽6.25nm，原Piola/方向/坐标桥(25,12.5,0)nm |
| 完整局部列 | Nédélec第一类p4=300、p6=882；非零微小内部迹保留；实际面拥有trace作用列40/84，不把这两个数当全体自由度 |

旧schema1原36244923B/SHA52d7ec80…仍严格要求，未改常量或默认。历史原件有限检索结果HISTORICAL_BYTES_UNAVAILABLE；`historical_bitwise_reproduction=false`、`equivalent_to_historical_numeric_manifest=UNKNOWN`、`historical_ledger_recovered=false`。本轮生成次数0；[身份原字段](records/input_identity_v28.json)和[预先冻结设计](records/design_v28.json)完整保存。

科学核验不调用原生成器自比：从配置独立枚举32060有序模式、重算k/beta出射支、s/p极化规范、h_code、traction、整周期/参考面H、功率和物理入射背景；416780字段检查失败0。H是模式投影的分母，不是磁场向量。普通字段最大相对1.0747787677074433e-15；固定8个极端/n=0/近截止角色另以80/110位复核。实际模式均classified propagating，倏逝/分类规则的fixture资格不扩张成实测倏逝覆盖。[全部原字段CSV绑定及高精度原值](records/mode_validation_v28.json)、[零失败CSV](records/mode_validation_failures_v28.csv)。

## 积分参照与完整作用

q60是固定积分规则，用于把振荡的模式函数同有限元面多项式相乘后积分。独立参照直接计算同一一维矩；对全部357个实际频率和ell0..6，复用71个已绑定相同二进制频率、补286个缺项。Decimal80级数、Decimal110固定64点直接积分及解析核最大差3.3422138886441676e-16。不是只抽最坏几个模式，也没有修改q或网格。[实际oracle和布局入口](records/independent_checker_v28.json)。

完整producer按≤64模式一批写出1004个chunk，partial不能准入。独立pure进程从保存的原Basix多项式/Piola/模式/矩重算组件，不调用FE生成器、积分器或求解器。投影后的模式回散布和伴随都检查；D采用原traction定义，不能假设D=B的共轭转置。原复见证、固定seed4212801通用复见证、三个非零复方向和真实物理入射均在评分之前登记，未按输出误差挑向量。

| 数值检查 / 含义 | 实际最大值、原门 |
| --- | --- |
| 一维矩绝对差 | 9.082805012334877e-14≤1e-12 |
| B / D-H列相对 | 4.869638025629009e-12 / 4.869654765441568e-12≤1e-10 |
| 三个复方向最大相对 | B第二方向6.292215481183498e-11≤1e-10 |
| 逐key原见证回散布 | 9.595725209727146e-11≤1e-10，最接近门限 |
| 原/通用完整apply | 1.0997000143116738e-14 / 8.459159160319482e-15≤1e-10 |
| 原/通用完整adjoint | 9.101407903696035e-15 / 9.99016476550359e-15≤1e-10 |
| 真实入射/背景RHS | 最坏4.731785240322477e-15≤1e-10 |
| 逐项检查与覆盖 | 1218328项、失败0；p4/p6各32060，两切向分量和全部实际频率覆盖 |

相对差分母是新实例预先冻结的完整独立参考数组范数或标量模，仅零参考采用float tiny并明确标记；没有max(1,…)。这与历史文件使用相同定义，但不是历史数组分母值。最坏top(-64,-35,p)、p6的分子4.307908906196561e-15/分母4.489404200351269e-5，near_zero=false。[逐字段最大值CSV](records/boundary_metrics_v28.csv)是compact索引，完整1218328行CSV在ignored目录按hash保留，没有以摘要替换原件。

结论为W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS。原q60通过，唯一条件分面profile没有触发；它的实现fixture通过不算实际分面数值资格。两代表面、固定向量、原分母经验资格不推广为全域算子界、体场或最终精度。保存checker及新目录消费者均把严格实际数组门重新算出，不接受自报status。

## 保全、成本与边界

实际修复与尝试见[repair log](records/repair_log_v28.json)。正确完整producer只运行一次；Unix socket及消费者接线修复没有重复它。最后一份资源准入的准备失败保留，quota只修正读第24份有效账的off-by-one，新增第25份仍拒绝；最后局部import修复沿用同一dat/hash/clock/已通过压力窗口，没有伪造fresh样本。准入24份、等待873.628663s≤900s，原资源阈值全部保持。

边界全链319.007977s、独立checker595.392221s（含启动路径修复）、独立consumer1289.617945s（含准备修复）；它们的嵌套worker/watchdog时间不能另加。[资源账](records/resource_costs_v28.json)保存所有失败、实际同时树峰、自身swap0、16GiB artifact门、独立单核与环境记录。整体最大监督采样树峰810545152B；不是完整冷启动精确峰值。数学源c354afa449fb80cfb5012e7d2ff66a3e3e64e088未改；准确各阶段source见[run index](records/run_index_v28.json)。

消费者实际复制并读取相同数值包，状态LOCAL_RELOCATED_CONSUMER_PASS；接收者指令、相对路径和主线防混用边界见[主线交付](main_handoff_v28.md)。FEINN仍暂停，NO_VERIFIED_NN_INCREMENT及FULL_TARGET_NOT_QUALIFIED不变。原尺寸E/H/curl/R/T/A等全场验收没有运行；本次确定性组件通过不计NN增益。旧M3600较好、Mfinal退化、D0否决/D1未运行、全部负结果/UNKNOWN和费用保留。
