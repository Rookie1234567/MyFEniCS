# Task041 Review V18回应：V16首次PC行拒绝的存档分解

## 结论

V16唯一M400/MPI8 Invocation在第一次PC作用时触发原有modal-row门：存档最大逐行指标为`0.017996403128522177`，高于`1e-10`。随后只对同次冻结的800行binary64分量做了90位Decimal分解，并对四个代表行做120位交叉核验。没有重新执行原A、B/P4、求解器、LU、FE或谱计算。

复算显示`e_K`是800/800行以及全部732个门失败行中的唯一最大复数项。它与`d=w-r`接近同向，但不能据此区分projection、y/q或g构造、列反馈或直接B作用差。`C`快照来自`system.modal_constraint`，原A独立使用`internal_modal_constraint_matrix`；独立的原A C字节和输入修正未保存，所以`e_C`只能称约束作用一致性差，不能归因为纯乘法舍入。

| 项目 | 存档事实 | 结论边界 |
|---|---|---|
| P0门结果 | 800行中732 reject、68 pass；最高行零基259，global modal index 302659；90位复算eta为`0.017996403128522126…` | 原门阈值仍为`1e-10`；这是已存行数据复算，不是新原A作用或solver pass |
| 主导误差项 | `e_K`是800/800行及全部732个失败行的唯一最大项；失败行最大`abs(e_S)/abs(d)=5.369824e-5` | 只能定位到已存组合余项，不能证明代码缺陷或锁定其内部来源 |
| S点积参考界 | 通用S-dot gamma参考比值在零基行68、140分别为4.6773和1.8031；两行Schur componentwise BERR分别为`8.68454e-13`和`3.30685e-13` | `e_S`是存档S_B LU解残差；点积gamma参考界不保证LU solve误差。两处超界不能写成LU误差失败 |
| 拆分与求和一致性 | `e_sub`、`e_sum`各799/800行在90位计算中精确为零；唯一非零行91，两项各为`2.5e-111+0i`，相对`abs(d)`为`4.98e-91`；行259两项精确为零 | 不推广为800行全部精确为零 |
| P1 | 未执行LU修正、C点积对照或Lz；大型构造额度2/2已用尽 | `L`、映射、同次y/q/Ly/Lq、列反馈、target side split及原A的独立C身份资料缺失；V14旧根因仍`UNCONFIRMED` |
| 唯一费用 | V5从307项增至308项；新增`27.82752328692004 s`，top为`651301.9334897036 s`，SHA `5fdb531b68e8ccd40587eb26ca921b3358a8a917c47129fcc3d89935568277bb` | 一条entry包含schema拒绝child `0.41583875683136284 s`及成功分析child `27.411684530088678 s`两个不连续区间；不是连续parent wall |

详细输入身份、缺项清点和输出hash见[closeout index](../../results/task041_v18_modal_error_analysis_prepared_20261016/p0_analysis_closeout_index.json)、[中心outcome](outcomes/v18_saved_modal_error_decomposition.md)与[compact machine record](outcomes/records/task041_v18_p0_saved_modal_error_decomposition_20261016.json)。原始P0 JSON、runtime raw、旧失败和ledger前缀均保留。

## 误差项与代表行

高精度项定义为`p_C=HP(Ca)`、`p_S=HP(S_B a)`。HP将冻结binary64输入逐项精确转为Decimal再做复数乘加。V15行尺度`s_V15`是已计算组成向量模长之和`abs(t_bottom)+abs(t_top)+abs(t_constraint)+abs(r_modal)`，不是矩阵乘法未相消数据尺度。

| 零基行 | 分类和eta_inf | abs(d) | sum abs(C_ij)*abs(a_j) | Schur componentwise BERR |
|---:|---|---:|---:|---:|
| 259 | reject，1.7996e-2 | 1.1476e-18 | 3.3107e-16 | 7.8022e-17 |
| 631 | reject，3.2307e-7 | 7.5661e-17 | 2.1912e-10 | 1.9712e-16 |
| 707 | reject，2.3051e-8 | 1.7571e-20 | 6.2809e-13 | 6.5474e-16 |
| 105 | pass，6.8292e-16 | 1.9158e-18 | 1.4476e-3 | 1.2038e-16 |

行259是最高eta行；631是拒绝行中abs(d)最大者；707是拒绝行V15组成尺度的较低中位次序代表；105是通过行中eta最低者。四行均做120位交叉核验。S-dot参考界仅在零基行68、140超过1；这两行的e_S是存档LU解残差，不能用通用点积gamma界判断LU求解误差。

owner范数从保存的S_B、a、g重算为`norm2(S_B a-g)/norm2(g)`：分母`0.002996074190479625294`、残差`2.93131484696791e-19`、比值`9.78385267054636e-17`。旧owner字段`1.9821704747745833e-16`仍保留为归档binary64 `relative_backward_error`，不是componentwise BERR，二者不混称。

失败行`real(e_K/d)`中位数为`0.9999999999999368`；中位`abs(e_K-d)/abs(d)`为`2.3706578534e-9`，不是角度。gamma比较的两个e_S超界行、复数分量和BERR详表见中心outcome。

对实际RUN的`run_manifest.json`、`supervisor_summary.json`、modal-row `index.json`及根/consumer `factor_inventory.json`的只读清点确认：实际L行和映射、同次y/q/Ly/Lq、列反馈项、每rank target的bottom/top split均未保存；uppercase `Q`是计数器，不是q向量。owner source slice匹配r_modal、target slice匹配a，但打包的z_b/z_t/a没有边界，不能从local_size猜切分。原A的`internal_modal_constraint_matrix`独立字节与输入修正也缺失，因此C差不能归为纯舍入。closeout index逐项列出所查路径与可用索引。

分析器每处理一行都会调用`_enforce_peak_budget()`（as-run源码第1061–1062行），读取本进程`VmHWM`并按2 GiB阈值检查；这是行间用户态预算检查，不是内核硬限。child最终`VmHWM`为92,192,768 B，外层wait后的`RUSAGE_CHILDREN`为92,078,080 B；后两个是最终资源收据，不能据此说峰值只在child结束后才读取。脚本未设置`RLIMIT_AS`。

如未来要区分e_K，最小证据请求是同一冻结RHS、同一固定B/S_B及同一a身份的一次PC作用，捕获y/q两侧共四次B作用、实际L行及modal映射、每rank side split、同次y/q/z、Ly/Lq/Lz与g，以及original-A的C字节、输入修正和作用hash。原800列反馈只请求按身份只读检查：若已存则读取；若缺失则继续标`missing/not_persisted`，本请求不重算800列。新作用至多支持三组组合项分解；`(C-S_B)a-Lq`仍混有旧列构造舍入和本次直接作用差，不能宣称还原旧列反馈。若缺少真实B/P4而需重建，需新review和计算额度，成本与峰值未知；旧约49.6 GB峰值不能保证新场够用。本轮大型额度2/2已耗尽。

V16 record中timer的`active`是采样时原值；后续主控只读确认timer/service已卸载并停用。本次未恢复timer。本回应回答Review V18。
