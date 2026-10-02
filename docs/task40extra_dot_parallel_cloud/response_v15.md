# Response V15：Y 成功证据与 X/XZ/Y 校准对照

**Y attempt2 fresh worker 与 automatic saved-only independent checker 均 PASS**，同一clean源 `9511930c29414d9db3c25124d7c2a745de211f96`。p4、phi5、mesh **4×6×5**，全global120 cells、三个local各40 cells，完整12960 interiors；**Ny6/K3、6q/3twists、manual532 ports**，8组输出各532且可表示。20xz groups，每组36global/12local/24cross pairs均受原始完整算子与方程/输出门约束。[worker summary](outcomes/records/direct_Y_v15/compact_record.json) · [checker summary](outcomes/records/direct_Y_v15/compact_record.json)

本次沿周期y方向增加网格层数，把完整三维参考问题分成三个带不同相位的局部空间，建立六个q分块因子，再恢复全部原三维未知量。它检查这套分块与恢复流程能否跨越原先仅两个局部空间的假设；仍以完整原方程和全部端口输出核验，未降低有限元阶数或省略内部未知量。原artifact链接指向记录实际路径和哈希的compact。

worker监督 **1748.504063969s / RSS1,606,623,232 B**，checker监督 **565.966512849s / RSS1,707,114,496 B**，均COMPLETED/exit0、swap0、identity complete、子进程清除，分别按3GiB/4500s研究边界监督。checker `gate_pass=true`，**421direct+33520raw+30operator+51281shared=85252 passing entries**；entries不解释为全局unique names。成功schema无evidence_valid字段；内嵌watchdog link精确绑定实际checker summary，checker numeric factor calls0，没有PDE重跑。

六个q augmented rows **1884/1884/1884/1960/1884/1884**，六CSR payload共 **52,709,744 B**；factor/control setup **5.747859236s** 包含controls/I/O，纯LU和per-PC成本未知。按root提取、report hash绑定的scalar摘要：notch generic/interior/physical/supported迭代 **4/4/3/4**，max regular true-original residual≈**8.92748e-12**、max notch≈**7.28650e-12**、physical nonzero-q≈**4.06863e-5**；physical sample PC defect≈**0.000186918786**；max sample（interior_only）≈**0.001783457**，normbound=false。notch coupling≈0.7071035仅相对于notch delta，不是整体强耦合证明。

| Y阶段 | 监督秒 | 进程树RSS峰值 B |
|---|---:|---:|
| fresh worker |1748.504063969|1,606,623,232|
| saved checker |565.966512849|1,707,114,496|

X/XZ/Y的完整对照见下列comparison。X按2GiB/1800s，XZ/Y按3GiB/4500s研究边界；时间/RSS包括各自evidence与控制开销，不构成纯solver性能比较。更多指标及exact hashes见 [comparison](outcomes/calibration_comparison_v15_zh.md)。

**Y使用新aligned3cell notch**，在7/135缩放前沿periodic-y移 **−25/12**，box为(25,33.5,25/6,100/6,40,80)×7/135；与旧box宽度/体积相同，但**不是旧X/XZ same-field或discrete-control对照**。X/XZ旧two-cell合同保留。Y较小sample defect和physical迭代数属于不同受控研究点观察，不证明目标accuracy改善。

原Y attempt1 **WORKER_FAILED /88.704822665s /factor0** 保留：protected H validation仍乘2，identity1/2、area diagnostic乘2，阻挡K3。修复只把这三个validation/metadata表达式改为validatedK、1/K、local_area×K；实际C/D/H assembly与H denominator不改，rtol仍32eps、atol0。[原失败](outcomes/records/direct_Y_v15/compact_record.json) · [independent source review](outcomes/records/direct_Y_v15/compact_record.json)

all532 H公式诊断显示旧K2门全失败、相同门K3全通过，最大K3误差3.4745643136670377e-16；**local H是formula重算值，未保存为旧local carrier**。实际first-two-y-axis period为0.4320987654320988，global_period_y/3为0.43209876543209874，相差1ulp；该差异与全部4个bitwidth classes均未舍入/合并，未声称exact-area相等。[diagnostic](outcomes/records/direct_Y_v15/compact_record.json)

formal **201 tests PASS**（23.642s；监督25.747335450s/RSS324546560 B），clean preflight绑定source/ABI/manual532/fresh headroom、FE/JIT/factor/PDE calls0。initial198 stale test失败及随后198 PASS均保存原分类与日志。source/ABI/资源/数值checker receipt绑定见 [compact record](outcomes/records/direct_Y_v15/compact_record.json)、[manifest](outcomes/records/direct_Y_v15/manifest.json)。

**主要accuracy仍未解决**。三个点都是same optical size、manual532、p4、weak perturbation校准；未资格化原AUTO32060、p6、目标几何/场精度、扩大electrical/optical size或用户2TB/48h容量。独立read-only最终pair linkage已**PASS：152 checks、0 failures**，原[receipt](outcomes/records/direct_Y_v15/independent_Y_final_pair_linkage_v1.json)字节完整保存（SHA5110624d16a0834fa9a38296045e85ef52d84c774cae7a20fe9f78d4ed084561）。该审查认证已记录的checker结果与修正后的physical/max标签；它没有数值重算。本次文档归档没有数组/events批量重读或数值重跑。
