# X/XZ/Y：离散研究点对照

三个点各自完成原始方程、完整恢复与全部532输出门。以下是engineering校准观察；主要accuracy仍未解决。

| 指标 | X | XZ | Y |
|---|---:|---:|---:|
| mesh |6×4×5|6×4×7|4×6×5|
| global/local cells |120 /2×60|168 /2×84|120 /3×40|
| interiors |12960|18144|12960|
| q因子 |4|4|6|
| CSR payload B |54078536|73801544|52709744|
| setup秒（controls/I/O included） |3.956874416|6.217330755|5.747859236|
| worker秒 |1535.146719|2392.338773|1748.504064|
| worker peakRSS B |1422172160|1669115904|1606623232|
| checker秒 |590.104325|754.005583|565.966513|
| checker peakRSS B |1567666176|1594347520|1707114496|
| notch迭代 generic/interior/physical/supported |4/4/4/5|4/4/4/5|4/4/3/4|
| max regular true-original residual |7.57683e-11|7.60336e-11|8.92748e-12|
| max notch true-original residual |4.71095e-12|4.58254e-12|7.28650e-12|
| physical nonzero-q relative |9.79164e-5|8.95626e-5|4.06863e-5|
| actual physical sample PC defect |0.0134232|0.0134233|0.000186918786|
| max sample PC defect² |0.0134232|未单独绑定|0.001783457（interior_only）|
| research cap/wall |2GiB/1800s|3GiB/4500s|3GiB/4500s|

²X max来自已归档四个source scalars（physical最大）；V14仅绑定XZ physical sample，未单独绑定其全source max；Y max来自interior_only。physical sample与max sample分别列出，均normbound=false。残差是各自离散方程求解误差，不是场/几何误差；CSR不是factor fill/RSS，setup不是纯LU/per-PC时序。

共同条件是p4、phi5、same outer optical geometry、fixed manual532。X/XZ保留old aligned2cell notch；Y为同宽度/体积但缩放前periodic-y移−25/12的新aligned3cell notch，故Y不是旧same-field/discrete-control收敛比较。场误差、目标accuracy、AUTO32060/p6、扩大electrical-size及2TB48h容量没有在此表获得资格。

来源：[V13 X](../response_v13.md)、[V14 XZ](../response_v14.md)、[V15 Y](../response_v15.md)。旧档字节保持不变；精确值和范围见 [compact JSON](records/direct_Y_v15/compact_record.json)。

Y corrected physical/max labels与最终pair linkage已有独立read-only验证：152 checks/0 failures，原[receipt](records/direct_Y_v15/independent_Y_final_pair_linkage_v1.json)逐字节保存；该验证不构成新的数值重算或accuracy证明。
