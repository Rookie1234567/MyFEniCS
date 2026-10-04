# V23：宽面片的一维积分、实际资格拦截与冷成本出口

面片较宽时，传播波在一个面内反复振动。低点数求积可能漏掉这些振动。新组件把面上有限元多项式与波的积分直接算出，保留既有几何、方向和端口处理；本轮验证它能否比可靠q60带来足够的完整局部收益。结果是**都够准，解析方案未过20%成本门，推荐q60并结束额外优化**。

## 1. 实际求解入口先关闭

给定保存D/H的准确点积，不等于D/H本身是准确物理积分。新 `strict_port_admission` 将可读负场、局部组件和严格完整角色分开；缺项、UNKNOWN、schema错误、当前caller expected不匹配、文件不存在或hash改变均拒绝。campaign入口及direct correction在依赖加载/求解哨兵前调用同一守卫。即使完整资格将来为真，Review V22本批新Maxwell求解权限仍为0。

保存E3/E4的算术误差约9.68e-17/3.89e-17；实际背景原点投影差约0.7732/0.1769、两oracle差约1.9582/0.2611，均远超1e-10。仿射exact-sum布尔证明没有保留可直接绑定的relative标量，按UNKNOWN拒绝。新裁决不改旧PASS/FAIL。[全部原字段及文件身份](records/strict_admission_v23.json)、[新checker](records/independent_checker_v23.json)。单独p6角色失败不否决独立p4局部组件；共享物理失败阻断所有依赖者。

## 2. 换元和真实消费

接收方在[0,1]积分，旧解析矩在[-1,1]；中心相位和1/2尺度都必须保留：

```math
I_\ell(\omega)=\int_0^1 P_\ell(2t-1)e^{i\omega t}\,dt
=e^{i\omega/2}i^\ell j_\ell(\omega/2).
```

`unit_interval_moments`复用已有 `fourier_legendre`，没有复制新的Bessel算法。`IntervalFacetAdapter`只替换两个一维矩，按原接收方的张量收缩、协变Piola乘面积、上下参考点相位返回同一线性泛函。caller冻结系数、物理k、J、origin和side的expected身份；只支持轴对齐仿射平面、实切向频率和可逆表示的原点相位，未覆盖输入拒绝，普通接收方默认不改。

真实消费示例从只读Task042 `31774b6282f61280fe33c162f9f48bf4ea526ce6`、SHA `81b0f3cf42e01402a650555f92db1425d92dc9cd658bfd4c0a172be743cf159f` 提取既有 `FacetPolynomial` 类。没有导入整条runner、布局或owner类；该类原q60方法作为主要对照，适配作为显式候选。[可运行包/补丁](../../../benchmarks/cases/portable_interval_facet/README.md)、[函数及依赖](records/minimal_integration_v23.json)。不同线的材料/模型/权限不移植，原H始终取整个50×25nm周期单元的定义，未以面片或边界范数替代。

## 3. 固定局部资格及分母

| 预先冻结的范围 | 实际覆盖与限制 |
| --- | --- |
| 面片跨度 | x=16.5/78、8.5/58nm；y=25/4nm；旧25/36只保留一个转换回归 |
| 一维频率 | x发布最大阶142的正负范围，含物理kx入射；y n=-35…35及0；共1213个频率，每个ℓ0…6，完整数组留ignored |
| 局部真实基 | 原生N1E hex p4/p6各300/882列；所有边/面/内部列保留，未按幅值删项；非恒等Basix方向变换，独立积分点重构≤8.92e-16 |
| 实际作用 | 每p有24个固定面/模式/极化case，双x宽、上下法向、s/p、非零ky、3条复方向和非零原端口载荷；原H范围29.44378…1250 |
| 独立oracle | 标准库Decimal80/110整数多项式积分；固定独立64点高精度Gauss一次交叉，不调用producer的Bessel/Legendre系数变换 |
| 明确不授予 | 全32060有序模式、真实全目标网格/原场敏感α、完整空气/全局PDE或原尺寸解资格；本轮仅局部组件 |

80/110位积分在输出binary64后相同；零频Gauss自一致约9.77e-88，极限正负频的独立Gauss/级数输出相同。原record中的 `quad_recurrence` 是保留的字段名，本次实现实际为Decimal幂级数。局部高精度矩的收缩使用extended累积，再转complex128；它仍使用已保存binary64原生面系数，不声称任意强相消场均可准确恢复。[原资格](records/facet_qualification_v23.json)。

非零载荷是seed4212301预登记的局部原坐标gp测试向量；不是主线实际全目标入射RHS。它核验 `(D c+gp)/H` 的非齐次消费，接收线的实际背景、完整模式与RHS仍须自己的资格。原型这里只比较局部面泛函，没有用随机载荷构造一个新Maxwell解。

最终checker另从保存数组逐case/方向重算，864行CSV保留分子、参考范数、实际分母、近零标记。矩绝对门是单位区间自然尺度1e-12；B/D/H、forward、原H投影和共轭adjoint用原参考范数，近零地板1e-12，门1e-10。漏中心相位、错误长度/side/系数/k/材料/modes/source、错误共轭、损坏数组/schema和不可逆相位均有负控或实际拒绝fixture。全局旧敏感H最小5.8e-168的FAIL不由本次健康局部H通过覆盖。

## 4. 唯一冷生命周期的完整成本

| measured，同source/相同固定作用 | 解析 | 原接收方q60 |
| --- | ---: | ---: |
| 最大区间绝对误差 | 3.55444798e-16 | 9.08280501e-14 |
| 最坏逐case/方向原分母相对差 | 1.65719809e-13 | 1.97675419e-11 |
| 完整launcher到summary，s | 64.46514550 | 64.61506060 |
| worker内首次读取/系数/积分/写出/check，s | 0.65439739 | 0.50336585 |
| 首次原生系数，s | 0.29162636 | 0.32792660 |
| 导入provider/积分/收缩/适配，s | 0.32638148 | 0.13044908 |
| 写出及独立checker，s | 0.00975775 | 0.01841238 |
| 同时树采样峰，B | 175190016 | 114491392 |
| 自身swap/OOC | 0/0 | 0/0 |

完整成本包括规定的60s稳定窗口，不能用worker的亚秒量冒充全流程。每种仅一次新进程，重新构造面系数；既有Python字节码和整机磁盘页缓存没有清除，不宣称硬件冷缓存。两条都有8次p+1小型Vandermonde坐标转换求解，完整计费，它们不是Maxwell/Gram因子。树峰是约0.5s采样同时RSS，非连续内核硬限；共享机单次计时没有稳定性证书，不给微秒级排名。

解析方案完整时间仅改善0.2320%，RSS增加53.0159%；worker内也更慢。无≥20%同精度完整局部净增益。故**推荐已有合格q60，关闭额外解析优化/测速**；解析组件只留显式候选，接收方按自己的完整keys、实际载荷、材料和调用链资格决定是否消费。[完整费用](records/resource_costs_v23.json)、[成本原记录](records/local_cold_comparison_v23.json)。本批全部Maxwell全局/局部factor、solve、Gram和NN训练0。

## 5. 交付、历史及停止边界

source与文档HEAD分开：[run index](records/run_index_v23.json)。P0为 `765aeafc615ebfb0c842bd2fdad195a696271a71`，局部生产与两冷进程为 `b5034e5ffab657146024ac429fe410f005049d3d`，逐case独立checker为 `7a7c6b5a3a0c65a93e362644b50ad84ae0d20f2c`。47项最终fixture、本地Ruff/compileall通过，无full pytest/CI；[失败/修复](records/repair_log_v23.json)、[六类依赖](records/selective_merge_manifest_v23.json)、[视觉](records/render_check_v23.json)。

原两态/所有失败、M3600较好/Mfinal退化、D0成本否决/D1未运行、历史未测尾段和失联费用均保留。原尺寸50×25×140nm、Si17/120nm、λ0.7完整三维FE、2e12B整机和172800s仍未达成；FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED不变。本轮不是NN重启、传统完成器或新的场求解，未修改其他线，无production/merge approval。整批一次交棒后停止；没有真实接收方新缺口，不再自动安排数值或归档批次。
