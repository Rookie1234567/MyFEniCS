# 精度、全过程性能与内存

本轮比较的是同一M5、同全部独立FE、同原方程/材料/模式/初值的三条路线。坐标网络通过积分产生边、面和内部矩；FREE直接优化完整复系数。DUAL用正定测试内积衡量弱残差，增加真实稀疏Gram因子成本。LE与LD不能直接按数字大小比较精度。

| 路线 | native / augmented | 散射E L2 / scaled-curl | selected total E/H | 出射复通道 | R/T/A_balance/A_volume |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 0.928287/0.928287 | 0.999215/0.999234 | 0.678586/0.671902 | 0.270177 | 0.837415/0.113261/0.0493242/0.465089 |
| FEINN-DUAL | 1.10264/1.10264 | 0.998885/0.998906 | 0.678322/0.671303 | 0.270119 | 0.837391/0.113257/0.0493519/0.464992 |
| FREE-FE-DUAL | 0.596914/0.596914 | 0.991925/0.991755 | 0.672954/0.670815 | 0.27518 | 0.845194/0.115246/0.0395601/0.459627 |

严格全量误差与自然尺度见[physics](records/blind_physics_v1.json)：full FE total/scattered E的L2、curl/k0、6点复E/H逐点和整体、40级ordered port/出射/scattered复幅、逐级功率。字段absolute与denominator保留；E自然尺度sqrt750 nm^(3/2)、点E/H尺度1、port尺度1；全局相位不拟合。候选失败值仅作diagnostic，参考同p3，不称continuum。

| 路线 | closure尝试 / 完成 / 完整外层 | 实际完整wall / s (derived) | 从零归属 / s | 运行树峰 / GiB | own swap / B |
| --- | --- | --- | --- | --- | --- |
| FEINN-EUC | 2219/2219/578 | 10692.4 | 10783.2 | 0.65601 | 0 |
| FEINN-DUAL | 2387/2387/586 | 10689.9 | 11429.5 | 1.31262 | 0 |
| FREE-FE-DUAL | 4000/4000/649 | 2903.75 | 3643.38 | 1.27242 | 0 |

| 辅助量 / 单位 | 实测值 | 含义 |
| --- | --- | --- |
| Gram rows / NNZ | 31968 / 7336179 | 全部独立p3；材料无关正定测试内积 |
| Gram CSR payload / B | 146851456 | 数组体积，不是RSS |
| 首次装配 / s | 648.765 | 完整计入DUAL/FREE从零成本，研究实账只计实际一次 |
| 资格factor setup / s | 110.571 | RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR；LLᴴ/AMD |
| symbolic L NNZ | 1.88397e+07 | symbolic后容量Gate，非dense inverse |
| CHOLMOD current / peak B | 5.44919e+08 / 6.33593e+08 | 辅助因子也计资源 |
| 资格Gsolve max true relative | 9.13339e-12 | 限值1e-11；训练各路线另逐次检查 |

| 路线 / research-only | fresh setup / s | 全部Gsolve / s / count | max true residual | factor current / peak B |
| --- | --- | --- | --- | --- |
| FEINN-EUC | 0 | 0 / 0 | not_run | not_run/not_run |
| FEINN-DUAL | 128.442 | 810.233 / 2390 | 6.10176e-13 | 5.44919e+08/6.33593e+08 |
| FREE-FE-DUAL | 113.025 | 1394.34 / 4003 | 7.53354e-13 | 5.44919e+08/6.33593e+08 |

完整from-zero归属、监督实账、UTC启动至最终summary边界、失败/安装/test/参考费用见[resource](records/resource_costs_v1.json)。表中相对精度与功率分别审核，低loss不等于求得准确解。总RTA闭合用独立A_volume，A_balance自身定义不构成独立证据。

EUC自身不加载Gram；DUAL和FREE同一无解准备、fresh Gram factor分别计费。共享E1准备的数组、owner、坐标、FFCx和端口成本不可从基准删除。timer粗化修正第一次H除法的setup/port重复；raw port timer只作非累加诊断，互斥账包含全部导入/监督/发布开销。表中RSS为采样同时整树最大，payload不能替代RSS；各阶段峰值不相加。

原局部tensor缓存2654208 B，全部native packet8348760 B；每次当前体作用全cell临时127401984 B，AH还需conjugate临时。网络权重71728 B只是少量常驻项，另有坐标/矩cache、8cell图、recompute VJP、Adam一二阶统计、L-BFGS history20、FE向量、Gram CSR/factor和端口COO。Adam统计未包含在raw L-BFGS history字段；它仍在实测RSS中，不将该字段冒充全部optimizer memory。实际训练history与cache bytes见route_results。

度量信号 `inconclusive_not_equal_accuracy`；神经增量 `inconclusive_not_equal_accuracy`。本轮共享环境不具备可信的20%性能反事实。目标临时对象和Gram预测见[目标计划](target_5nm_scale_plan.md)，不是可扩展solver/PC资格。
