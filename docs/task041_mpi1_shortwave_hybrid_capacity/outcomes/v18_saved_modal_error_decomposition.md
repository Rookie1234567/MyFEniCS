# V18存档modal-row五项误差分解

## 目的和范围

第一次PC作用中保存的modal-row检查失败后，P0把同次保存的复数分量逐行拆成五项。它回答的是“已存差额落在哪些已记录项”，不重放会改变现场的矩阵作用或求解器。输入绑定到V16 Invocation `6344a904b8df435a88a7466dd739da76`的冻结数组。

V16在第一次PC apply的V15 modal-row门被拒绝：存档最大`eta_inf=0.017996403128522177`，阈值`1e-10`。没有完成outer iteration、最终五项原方程残差、recovery、E/H、official R/T/A、A_volume、衍射或physics。服务标签`IMPLEMENTATION_FAILURE`不是实现缺陷证明；V14旧M400根因仍为`UNCONFIRMED`。

本分析没有重放原A、B/P4、LU、solver或谱计算，也没有生成新FE/P4/QEP/800列矩阵。全表以90位Decimal计算，归档binary64实虚值用`Decimal.from_float`精确转换；四个代表行259、631、707、105再以120位交叉核验，归一化差均小于`1e-30`。800行五项闭合最大相对值为`9.5454e-77`。

| P0结论 | 数值 | 含义 |
|---|---:|---|
| 行门 | 732/800 reject，68/800 pass；阈值`1e-10` | 第一次PC apply的逐行合同结果，不是最终原方程残差 |
| 主导项 | `e_K`在800/800行、包含全部732失败行均为唯一最大复数项 | 定位到已存组合余项，不能区分projection、y/q/g构造、列反馈或直接B差 |
| `e_C` | 全表最大`abs(e_C)/C-dot gamma参考界=0.00934249`，无行超过1 | 原A C字节及输入修正缺失，不能称纯舍入误差 |
| `e_S` | 失败行最大`abs(e_S)/abs(d)=5.369824e-5`；S-dot参考比值在零基行68、140为4.6773和1.8031 | `e_S`是存档S_B LU解残差，gamma点积参考界不保证LU solve误差；两个超界不使其成为主导项 |
| `e_sub`与`e_sum` | 各799/800行精确为零；零基行91的两项各`2.5e-111+0i`，相对`abs(d)`为`4.97724e-91` | 行259两项精确为零，但不能推广为全800行精确为零 |
| 向量二范数指标 | `eta_terms_2=3.257659348665526e-14` | 整个800项模态向量指标，不是row259单行指标 |

## 五项定义和V15尺度

令`p_C=HP(Ca)`，`p_S=HP(S_B a)`。这里HP表示把保存的binary64输入精确转为Decimal后做高精度复数乘加；`p_S`是用保存的S_B与owner解a重算的点积，不是把LU残差改写成矩阵作用误差。

| 项 | 复数定义 | 含义 |
|---|---|---|
| `e_sub` | `d-(w_modal-r_modal)` | 保存的d与保存的w、r重新相减后的一致性 |
| `e_sum` | `w_modal-(t_bottom+t_top+t_constraint)` | 保存的w与原A组成项和的一致性 |
| `e_C` | `t_constraint-p_C` | S_B/C路径与原A constraint-action的差 |
| `e_K` | `(t_bottom+t_top+p_C-p_S+g)-r_modal` | 剩余组合项；主导不说明其内部来源 |
| `e_S` | `p_S-g` | 保存的S_B LU解方程残差项，不是单次S_B点积误差 |

这些定义满足`d=e_sub+e_sum+e_C+e_K+e_S`至已核闭合精度。V15逐行尺度`s_V15`是**已经计算的组成向量的模长之和**：`abs(t_bottom)+abs(t_top)+abs(t_constraint)+abs(r_modal)`。它不是“矩阵乘法未相消数据尺度”。V15门仍使用真实`d=w_modal-r_modal`，无分母floor。

每行另存`sum_j abs(C_ij)*abs(a_j)`、Schur尺度`s_S,i=sum_j abs(S_B,ij)*abs(a_j)+abs(g_i)`等操作尺度和复点积gamma参考预算。Schur componentwise BERR为`abs((S_B a-g)_i)/s_S,i`。gamma参考模型将复点积拆成实、虚两路各`2n`个实乘积求和，以各自绝对乘积和乘`gamma_(2n+2)`后合成复模界；假设有限正常运算、不溢出下溢且无FTZ/DAZ，不声称复现原BLAS/MPI归约顺序或系数生成误差。表中的`gamma_C`、`gamma_S`分别是C点积与S_B点积的该参考上界；它们不构成S_B LU残差的界。

## 代表行五项和组成尺度

代表行按保存的选择规则选取：零基行259是最高`eta_inf`行；631是拒绝行中`abs(d)`最大者；707是拒绝行V15组成尺度的较低中位次序代表；105是通过行中`eta_inf`最低者。四行均通过120位交叉核验。下表复数用科学记数法约写，完整数值见[行摘要JSON](../../../results/task041_v18_modal_error_analysis_prepared_20261016/p0_rowwise_complex_summary.json)。

| 零基行 | V15分类与`eta_inf` | `abs(d)` / `s_V15` | d | `e_sub` | `e_sum` | `e_C` | `e_K` | `e_S` |
|---:|---|---|---|---|---|---|---|---|
| 259 | reject; 1.7996e-2 | 1.1476e-18 / 6.3769e-17 | -1.133e-18-1.798e-19i | 0 | 0 | 5.709e-33-2.334e-32i | -1.133e-18-1.798e-19i | -2.404e-32+4.725e-32i |
| 631 | reject; 3.2307e-7 | 7.5661e-17 / 2.3419e-10 | -7.197e-17-2.335e-17i | 0 | 0 | -6.212e-27-3.136e-26i | -7.197e-17-2.335e-17i | -1.644e-25-1.187e-24i |
| 707 | reject; 2.3051e-8 | 1.7571e-20 / 7.6228e-13 | -8.334e-22+1.755e-20i | 0 | 0 | -3.163e-28+1.646e-29i | -8.334e-22+1.755e-20i | 7.572e-28+2.515e-27i |
| 105 | pass; 6.8292e-16 | 1.9158e-18 / 2.8054e-3 | -8.132e-19-1.735e-18i | 0 | 0 | -6.806e-21+1.591e-19i | -7.905e-19-1.893e-18i | -1.583e-20-1.176e-21i |

| 零基行 | `s_sub / s_sum / s_C / s_K / s_S` | `sum abs(C_ij)*abs(a_j)` | Schur尺度`s_S,i` | Schur componentwise BERR | `gamma_C` | `gamma_S` | C点积相消比 | S点积相消比 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 259 | 2.2952e-18 / 6.4917e-17 / 3.6281e-16 / 6.3769e-17 / 6.7948e-16 | 3.3107e-16 | 6.7948e-16 | 7.8022e-17 | 6.4821e-29 | 1.1986e-28 | 9.5892e-2 | 7.8022e-17 |
| 631 | 1.5132e-16 / 2.3419e-10 / 3.3622e-10 / 2.4669e-10 / 6.0802e-9 | 2.1912e-10 | 6.0802e-9 | 1.9712e-16 | 4.4073e-23 | 1.2866e-21 | 5.3438e-1 | 1.0289e-3 |
| 707 | 3.5142e-20 / 7.6228e-13 / 1.0092e-12 / 3.1316e-12 / 4.0120e-12 | 6.2809e-13 | 4.0120e-12 | 6.5474e-16 | 1.1797e-25 | 5.0608e-25 | 6.0682e-1 | 4.1900e-1 |
| 105 | 3.8317e-18 / 2.8054e-3 / 2.8502e-3 / 2.8054e-3 / 1.3182e-4 | 1.4476e-3 | 1.3182e-4 | 1.2038e-16 | 2.5713e-16 | 2.3898e-17 | 9.6900e-1 | 1.2038e-16 |

## S-dot参考界超界行

两行是仅有的S-dot通用参考界超界项。`e_S`仍是S_B LU解残差；这个点积求和模型不是LU solve误差保证。

| 零基行 | modal-row BERR eta（binary64 / 90位） | Schur componentwise BERR | `abs(d)` | `e_S`复数 | `abs(e_S)/abs(d)` | `abs(e_S)/gamma_S` |
|---:|---|---:|---:|---|---:|---:|
| 68 | 4.790578625393529e-7 / 4.7905786253935201e-7 | 8.6845369373e-13 | 2.9355390085e-20 | 2.8950599295e-26-2.8286712698e-25i | 9.6862882779e-6 | 4.6773313009 |
| 140 | 2.448298381310218e-7 / 2.4482983813102229e-7 | 3.3068498130e-13 | 2.6444120320e-20 | -3.1151527772e-25-2.8837440159e-25i | 1.6052776279e-5 | 1.8031153672 |

这两行仍由`e_K`主导：`real(e_K/d)`分别约为`0.9999912326`和`0.9999929643`。失败行中位`real(e_K/d)=0.9999999999999368`；中位`abs(e_K-d)/abs(d)=2.3706578534e-9`，这是复数差的相对模，不是角度。失败行最大`abs(e_S)/abs(d)=5.3698240409972e-5`。因此不做P1 LU修正或C点积对照的理由是e_K对每条失败行都主导、e_S相对d小且C身份不完整；不是“所有项都落在舍入界内”。

## Owner Schur二范数核对

同一归档owner解a、S_B与g的高精度复算给出实际向量相对残差`norm2(S_B a-g)/norm2(g)`。这是二范数残差比，不是componentwise BERR；旧owner记录中的binary64字段另列，不替代此量。

| 量 | 归档数组高精度复算 | 已存owner记录字段 | 语义 |
|---|---:|---:|---|
| `norm2(g)` | 0.002996074190479625294 | — | 高精度分母 |
| `norm2(S_B a-g)` | 2.93131484696791e-19 | — | 用已存S_B、a、g重算的二范数残差 |
| 比值 | 9.78385267054636e-17 | `1.9821704747745833e-16` | 左值是`norm2(S_B a-g)/norm2(g)`；右值是原owner LU记录中的binary64 `relative_backward_error`，保留其旧值但不称为componentwise BERR |

## 方向、相消、身份与缺项

C与S_B点积相消比定义为点积模长除以输入绝对乘积和。800行C比值中位数0.776、最小0.01245；S_B比值中位数`8.6845e-13`、最小`6.781e-18`。row259的S_B相消比为`7.8022e-17`。这些比例描述项间相消，不证明舍入或LU错误。

C矩阵归档自`system.modal_constraint`；原A另用`internal_modal_constraint_matrix`。同一上下文和布局有记录，但独立的原A C矩阵字节和输入修正缺失，故e_C只能表述为作用一致性差。存档S_B内容SHA为`d4b25b721327c5b0f8261a15f96a61022507a5ae84ebe66c087cafd4832d3bfc`，C快照SHA为`b720ee6eab372f56e389241973e2573e0913f804fb90726f29c4543cc1fc1286`，布局SHA为`db70fd5ee69f64337780912877872fc61ce3809f87e66fe3ccd4de8d9a39c5f8`。

对同一RUN的`run_manifest.json`、`supervisor_summary.json`、`consumer/numerical_output/v13_modal_row_evidence/index.json`、根`factor_inventory.json`和consumer `factor_inventory.json`做了缺项核对。index列出S_B ready、terminal numeric reject和rank-vector index；owner source slice逐字节对应`r_modal`，owner target slice逐字节对应a。target数组还打包`z_b/z_t/a`，但每rank的bottom/top边界没有保存，不能按`local_size`猜一半。上述被核metadata没有实际L行、L到modal target的映射、同次y/q/Ly/Lq、column-feedback terms或target side split。factor inventory中的大写`Q`是计数器，不是q向量。故Lz为`not_run`；不拿source RHS的r_modal、`C-S_B`或`r-g`替代缺失向量。

## 后续最小证据请求

如需继续区分e_K，下一份review可限定一次**同一冻结RHS、同一固定B/S_B及同一a身份上的单次PC作用**，记录两侧y/q路径的四次实际B作用、同一action/source/target身份下的L实际行及L到modal target的映射、每rank target的bottom/top split、同次y/q/z、Ly/Lq/Lz与g，并保存original-A中C矩阵字节、输入修正和作用输入hash。请求读取原800列反馈：若相同身份的已存列反馈存在则只读核对；若不存在，明确记为`missing/not_persisted`，不得为本方案重算800列。即便取得单次作用的中间量，也只能形成Review V18给出的三组组合项：`(Lz-Ly+Lq)+(g-r+Ly)+((C-S_B)a-Lq)`；最后一组仍混合旧列构造舍入与这次直接作用差，不能称为恢复了旧列反馈。

若所需真实B或P4无法从现存存档读取、必须重新构造，则需要新的Review/计算额度；耗时和峰值未知。旧场约49.6 GB的process-tree峰值不能保证新场资源够用。本场大型额度2/2已耗尽，因此这只是未来证据请求，不是本轮计算授权。

## 执行、资源与证据

| 项目 | 记录 | 解释与边界 |
|---|---|---|
| V16运行身份 | Invocation `6344a904b8df435a88a7466dd739da76`；unit `task041-v16-m400-20261015t141300z.service`；runtime HEAD `c662a70b4af4d742f7a8305d0efd63342423c775` | P0读取此运行的冻结数据，不改runtime |
| `evidence_index.json` | `775c453b8c60699fd3f64ef4e4a3c1a1934c8616784d0777652adc3d9aaedfd9` | index record in `input_bindings` |
| `launch_manifest.json` | `4d36167b092a8c47c9dfecc8a55e865a291eab070135016142f88f699c6d3283` | run launch identity |
| `packet_manifest.json` | `63b7635e99dd476a94c97a07aa469be8c5087ef55fadeb7e8f908b1ded0d84e2` | selected producer packet |
| `rank_vector_index.npz` | `8739c76e681f900923b900c9df0ef75cf421d39cabb54650c4b9ad19b6a76d85` | rank-local source/target vectors |
| `run_manifest.json` | `cad2cfdd14e37c0799a03d5d9172b7f581161d575dd7045566af14951afa12ca` | run identity |
| `s_b_ready.npz` | `4a5f2e6d264b28e0d9b44af4306d6efafa897b5d154cb9f9fac6d02d7161def5` | saved S_B, owner solve and modal terms |
| `supervisor_summary.json` | `237e4a6d983d8a2b113d30ec6a39dc453b7a80769594f0d21aab380a826b63e2` | terminal and supervision summary |
| `terminal_numeric_reject.npz` | `e84fffe96bf19418714099d8f2496069c73c282ff452ec58c0854860deb40c54` | same-attempt terminal row arrays |
| 分析源码与派生输出 | as-run及research-only副本SHA均为`b4534e947bc5bc41d760cbca71b27c0809192bbe581111ead7890c05b118e64c`；P0 JSON SHA `5fd9ce422c73ebb9ec56aea119349c93e645786a2bbd8a67c931a222cadb53a0`；更正后全表摘要SHA `04c863e43c25ca8a8f2220fd20150e4e42e51238735a55b5c67d4ff3d21e1f3a` | P0原JSON没有改写；派生摘要修正只纠正文案和两条S-dot参考界解释 |
| 内存检查 | 单进程；六个数学线程环境变量全为1。分析器在每行后读取本进程`VmHWM`并检查2 GiB预算；无`RLIMIT_AS`或内核硬限 | 这是用户态逐行检查，不是内核强制上限。外层最终`RUSAGE_CHILDREN`最大RSS为92,078,080 B；child记录的最终VmHWM为92,192,768 B；这些终值不等于“只在child结束后才检查” |
| wall与V5 | 成功child wall 27.411684530088678 s；分析器内部phase 27.029757865937427 s；schema拒绝child 0.41583875683136284 s；V5新增一次27.82752328692004 s | 一个attempt entry包含两个不连续child时段；V5旧307项前缀不变，现308项、651301.9334897036 s、SHA `5fdb531b68e8ccd40587eb26ca921b3358a8a917c47129fcc3d89935568277bb` |

同一源码可从[research-only checker](../../../benchmarks/research/task041_v18_saved_modal_error_decomposition.py)审阅。以下是完整复现命令示例；输出路径必须保持为尚不存在的新文件，本轮未执行该命令：

```bash
cd /home/fenics/Projects/MyFEniCS
source .venv/bin/activate_myfenics_native.sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
test "$MYFENICS_NATIVE_COMPLEX_ENV" = 1
python benchmarks/research/task041_v18_saved_modal_error_decomposition.py \
  --analyze \
  --repo-root /home/fenics/Projects/MyFEniCS \
  --output results/task041_v18_modal_error_analysis_prepared_20261016/reproduction_example_not_run.json
```

若示例输出路径已存在，执行前改为新的ignored路径；分析器拒绝覆盖既有文件。完整输入、输出与缺项列表见[closeout index](../../../results/task041_v18_modal_error_analysis_prepared_20261016/p0_analysis_closeout_index.json)。fixture两次早期相消失败及一次schema拒绝原样保留，均不是solver数值失败。V16采样时timer为active；后续主控只读确认timer/service已停止，本次没有恢复timer。

本outcome是存档诊断，不是求解通过。原始P0 JSON、V16 runtime raw、V5历史和保护stash均未改。
