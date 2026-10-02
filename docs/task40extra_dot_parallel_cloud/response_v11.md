# Response V11 两胞元 full3D p4 完整恢复逆通过

**结论：两胞元参考逆已通过有界 scaled full3D p4 的 Q3–Q5 求逆、原完整载荷、真实三维缺口和逐模式输出门。** 数值worker固定在 `5e0364cd`，独立saved-only checker固定在 `029a0cd8`；checker为 **312/312，evidence_valid=true**。这两次不是同HEAD，差异仅checker与新增checker测试，数值、配置、输入和ABI依赖保持相同。V10的Q0–Q2继续保持其原审计身份。

参考逆先把完整三维载荷分送到两个40-cell空间，精确消去并恢复每个胞元内部未知量，在四个较小的平移相位分支上分别求解，最后拼回原80-cell三维场。它改变参考逆的建立与应用流程，避免候选全Ny矩阵；没有减少物理维度或删除y通道。代价是须验证相位、所有内部载荷、原端口及恢复逐层一致。本轮证明该小夹具的架构成立，目标尺寸的速度、容量和光学精度仍待独立验证。

## 从历史端口快照到本次新体积恢复

通过公共carrier构造器恢复已资格的原C/D/H，保留历史raw/literal与原primary JIT上下文；本次新volume/recovery另有身份，不能把旧raw receipt称为本次新same-live资格。实际网格、finalized MPC、dofmap、Basix、材料、配置、ABI及源文件逐项绑定。两个twist各20类300×300 raw/oriented tensor、native row inventory与恢复缓存配方完全相等；四个fresh q CSR对保存authority的norm/max差均为0，全部比较完成后才分解。

| 对象 | 完整覆盖与实测 |
|---|---|
| 原full3D | 80 cells；15872独立FE、8640内部、7232 trace；17204 native storage |
| 两个本地full3D空间 | 每个twist含40 cells；7936独立FE、4320内部、8940 storage；两个local branches覆盖四q |
| 原端口 | sector228/304；q端口76/152/152/152；完整532原aliases逐项保留 |
| 四个q因子 | 1884/1960/1960/1960行；四个同时保留；不复用±q；无L/U统计副本 |
| generic块检查 | 最大true residual 6.942412042682798e-13；linearity 3.188667119831649e-13；repeat 0；原门1e−10/1e−11 |
| 增广控制 | 各q任意非零内部及76/152/152/152非零port RHS；原FE/port/native残差及有效RHS符号独立检查 |

完整载荷没有被替换为trace载荷。regular与notch均检查generic、interior_only、physical、notch_supported四类原载荷；interior_only覆盖全部8640内部条目。残差由完整原FFCx volume作用加全部DtN贡献重算，不从凝聚残差推导。下表“场差”对照不可变V9 full-period p4保存场，**不是新full p4 direct对照或连续误差**。

| 完整原方程 | 最大原true residual | 最大保存场相对差 | 真实notch迭代数 |
|---|---:|---:|---:|
| regular A4 四载荷 | 5.26717490249291e-12 | 5.151923989527659e-13 | 不适用 |
| 原80-cell A1真实两cell缺口四载荷 | 7.966735639625955e-12 | 2.609464583066699e-14 | generic/interior/physical/support =4/4/3/4 |

缺口只改原80-cell的两cell，不周期复制缺口。outer仍对原完整三维A1做right FGMRES；最终auxiliary ports从最终A1场重新恢复。physical非零q比例 `3.088700602650845e-05`，采样off-q扰动比例 `0.707088125664911`，说明实际存在三维跨分支耦合。四个采样right-PC缺陷为 `0.0001869652272038134` 至 `0.0020506757354826605`，仅为弱扰动见证；不是operator norm、强扰动或大型收敛证明。

8个完整输出packet每个覆盖532模式。每packet的plane total/outgoing auxiliary、E、H及power diagnostic共5种量，分别对独立原系数与不可变V9输出比较，共80组×532；global totals/incidents另有32组×532绑定。全部沿原1e−10局部运算尺度门通过，最差原系数误差 `6.547443391315771e-17`，V9输出差 `1.6491826589632798e-15`。它们授予离散输出一致性，official R/T/A与目标32060-mode截断收敛仍未资格。

## 首个checker失败及显式保存证据修正

首个checker因历史 `ad356715` 的old full_Q不满足canonical CSR存储顺序而失败：15872行全未排序、107840 entries、0 duplicates、payload2220292B；保存失败checker `b8934c88` 与traceback。问题是旧validation map的存储顺序，不是候选数值失败。

修正仅允许被完整HEAD、raw哈希、dtype、形状和entry count钉住的历史full_Q：在独立新checker目录建立显式private row-sort copy，保存逐行精确置换；不合并duplicates、不变indptr、系数字节或原raw hash。两组raw/sorted作用差为 `1.1143963020473478e-16` 与 `1.1479773711663522e-16`，沿原1e−12门通过。候选CSR严格门、原算子与所有残差/输出阈值不变；未重跑PDE。静态[source审阅](outcomes/records/quotient_inverse_v11/checker_sort_static_review.json)与后续[配对artifact归档核验](outcomes/records/quotient_inverse_v11/independent_verification.json)分别记录，不能互相替代。

## 资源测试与资格边界

| 保存监督阶段 | wall seconds | 采样同时整树RSS bytes | 实际状态 |
|---|---:|---:|---|
| prefactor worker /checker | 147.7486319649979 /6.317829518004146 | 653615104 /375324672 | PASS19；0 q factor、无PDE |
| solve worker | 145.83506661900174 | 788480000 | PASS；4 factors、完整3D恢复逆 |
| 首个checker | 5.795336663999478 | 384798720 | FAILED canonical CSR Gate；保留 |
| 新saved-only checker | 7.072437755996361 | 300224512 | PASS312；无PDE重跑 |

以上均swap0、后代清场，MPI1/math threads1、complex128/int32；cap1.5GiB、600s及128MiB证据reserve不变。RSS是整个worker的同时采样峰，不是factor bytes或未采样硬峰；独立进程峰不相加。四factor setup `1.1669898219988681`s，包含其入口/检查；27次full恢复PC调用、108次q-factor调用。没有纯PC成本或L/U占用副本，不能据此外推大型加速。总512MiB factor allowance按实际已保留数量j扣减为512MiB×(4−j)/4，已有因子计入当前RSS，另留128MiB reserve。这是准入政策；未知fill/workspace仍unknown，不是内存预测。

保存inverse测试为267 passed、1 evidence-only skip、4 actual-FFCx/532 deselected及55 subtests；首个staging位置合同测试actual exit1对expected2的失败保留。checker-sort测试68 passed＋81 subtests，监督wall `2.015948161999404`s/RSS79220736B；不是全库CI。全部V5–V9失败、受控停止及不可变V9/V10 authority保留。

[compact](outcomes/records/quotient_inverse_v11/quotient_inverse_v11_compact.json)保留完整SHA、命令、ABI、source-diff三类标签、342项worker artifact清单入口与原阈值；[prefactor独立归档](outcomes/records/quotient_inverse_v11/prefactor_independent_verification.json)只授予其19项prefactor范围。配对记录已完成只读保存证据复核，receipt `95543f51`：worker1275/checker1276源码inventory、342 worker artifacts、7排序witness与46保留prefactor artifacts重哈希，1761 primary evidence files、325972516 streamed bytes、31888 metadata/stability checks、0 mismatch。该归档只独立核对原字节与JSON binding，不重新计算残差、逐行置换或作用差；312项数值门来自独立受监督checker。报告短hash `32a9ee70`、fresh checker `48d45202`；完整哈希由compact与receipt核对，不用短hash作为身份门。本次归档仅读取JSON和哈希，未导入solver、解码数值数组、装配、factor、solve或重跑checker。

用户目标仍为50×25×140 nm规则Si光栅、17nm线宽/120nm线高、λ0.7nm、≤2TB整机物理RAM及≤48h solve，并保留未来非可分三维缺口能力。本两cell路线p6、强对比、目标几何/连续/截断精度、官方R/T/A、MPI、跨机器ABI、checkpoint/restart及原尺寸目标能力均未资格。下一交付仍是冻结source/environment/config与用户工作站可自行执行的一条分级验证命令；本次只补足main Task40extra与MyFEniCSx_task37_extra的云端架构证据，未完成大型资格或发布/render Gate。
