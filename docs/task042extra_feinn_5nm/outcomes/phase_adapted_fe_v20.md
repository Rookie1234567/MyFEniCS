# V20：固定横向相位的完整三维有限元空间

把已知横向传播振荡放进基函数，可能使有限元只需描述较慢的余量；这改变了表示空间，仍解完整三维Maxwell方程。本批实际完成实现、解析资格、两个p3全场和唯一p6参考尝试；收益尚未资格化。原M5神经优化不恢复，没有训练或神经增益。

## 1. 新空间与固定物理身份

```math
E_h=g u_h,\quad g=e^{i(k_x x+k_y y)},\quad
\mathrm{curl}E_h=g\bigl(\mathrm{curl}u_h+i\kappa\times u_h\bigr),\quad \kappa=(k_x,k_y,0).
```

物理cfg的kx/ky、端口波数、导纳、极化和参考面保持原值；包络u只在MPC中去掉已提取相位一次。基函数在所有积分点含g，磁场从物理curl恢复；没有给FE系数乘中心点相位。原体/DtN求积degree15不改，q30只用于独立差积分。ordinary default和旧M5的A/G/背景身份未重定义。

| 固定输入 | 值 / 来源 |
| --- | --- |
| 模型 | 原50×25×140nm几何乘7/135，λ0.7nm、掠角1°、φ0、s；Si/air、三维缺口 |
| κ与单位 | (8.97461192517716,0,0) rad/nm；原点(0,0,0)；没有提取z相位 |
| 精确几何/网格 | 2374d0d556aed7a415202757daa2b94b76ad399b接口；G0=6×4×14，GX560=10×4×14，固定有理分段 |
| 材料 | Review/接口Si=0.99988517036884961+4.3236152269189515e-6i，μr=1；本地旧表差异明确记录而不替换 |
| 全端口 | m−8…8、n−2…2，上下s/p，共340；top z=6.7407407407407405nm，bottom z=−0.5185185185185185nm |
| 全自由度与约束 | 完整N1curl边/面/内部、Piola、orientation、双周期角点与master顺序；不退回trace场 |

[设计/材料/网格/模式/packet hashes](records/design_binding_v20.json)与[逐次运行](records/run_index_v20.json)。物理模型hash相同不表示离散hash相同；相位/普通空间分开。实际cell标签G0=224 air/24 substrate/88 grating，8 notch cell，非可分y/z见证通过。

## 2. A资格与两次正式修复

| 联合检查，无量纲 measured | 实际量 | 限值 / 边界 |
| --- | ---: | --- |
| κ0作用 / 实际旧完整RHS | 0 / 0 | ≤1e-10；3非零复方向含内部与端口 |
| 独立物理体 / B-D-H / RHS | 1.40871e-15 / 2.33466e-15 / 1.29076e-15 | ≤1e-10；独立gψ导数不读取producer F |
| A/AH共轭转置配对 | 1.79029e-15 | ≤1e-10 |
| 解析制造场原弱式 / 场 | 9.11093e-14 / 9.25858e-12 | ≤1e-10；三分量非零curl、源非b=Ax自造 |
| Floquet / H / Gauss制造载荷 | 1.27113e-14 / 4.08487e-13 / 2.826e-16 | ≤1e-10，边/面/内部全族 |
| q15→30 | 4.95508e-12 | ≤1e-8，仅一次2q复核 |
| 空气双向原残差 | 7.68239e-12 / 8.52783e-12 | ≤1e-10，横向波数相同、z符号相反 |
| 独立Poynting逐级与解析差 | 2.74336e-12 / 1.99840e-13 | 36完整模式、逐级≤1e-6；R≈0/T≈1，闭合≤2.91e-12 |

负控实际改输入/算式后被拒绝：漏iκ×u差0.0606、重复相位1.469、漏内部载荷0.00570、错端口1.469、旧背景0.513。每单元边/面/内部矩数量36/72/36，不只核边或trace。原A air_plane_power是振幅平方proxy；另做物理Poynting小fixture补验，不追改旧记录含义。[原20门与补验](records/qualification_v20.json)。

流程限定：独立物理Poynting补验在B/C之后才落盘，B启动前只有原20门，其中power项是振幅平方proxy。事后补验增强当前科学证据，不追认联合前置当时已完整；B的原恢复失败和所有费用不改。

正式修复1只改空气fixture准确稀疏求解；修复2准确换端口坐标并保全失败场，未改物理门。第二轮之后不再重放B；E3/O6及保存场诊断独立完成。[完整修复账](records/repair_log_v20.json)。初始UFL复数、路径/metadata/schema/fixture错误按开发定向测试解决，原失败、费用都在测试索引，未假作科学成功。

## 3. B原方程与恢复：小残差仍不等于可靠端口

单元内部凝聚是先准确消去只属于该单元的内部系数，再解较小的共享边/面和端口系统，最后恢复全部内部场；它不是丢掉内部物理。本批仅用它产生必要准确参考/对照，不作训练、粗逆或生产求解器推广。

| 角色 / FE复数数 | native | 增广 / total原方程 | 独立物理弱式 | 原恢复 / 1e-10门 |
| --- | ---: | --- | ---: | --- |
| O3修复，27648 measured | 9.92671e-12 | 9.89742e-12 / 1.26527e-10 | 1.26528e-10 | 2.41579e-4 FAIL |
| E3，27648 measured | 8.53571e-11 | 8.44607e-11 / 6.81744e-12 | 6.10735e-12 | 1.55624e-3 FAIL |
| E4，65280 derived | NOT_RUN | NOT_RUN | NOT_RUN | E3前置未过 |
| O6，365760 measured packet | NOT_RUN solve | NOT_RUN | 仅未解算子配对通过 | 凝聚前置失败，无场 |

p3通道原H最小5.81594e-168，边界相位最小1.90566e-84。原alpha范数O3/E3为5.54e17/1.08e16；边界beta范数1.619/0.254。边界恢复相对误差2.38e-13/1.27e-13，但原alpha恢复仍超门，不能把beta门代替alpha原门。主误差模式包括top(0,−2,p)、(0,2,s)等倏逝通道。[原字段及坐标观察](records/physical_comparison_v20.json)。

O6在新p6 packet已保存后，由严格内部/端口支撑检查拒绝。B和D各2264非零项，仅120个不同内部行；最大5.40e-13/6.13e-14，相对全块范数3.93e-14/4.10e-14。**值很小不是精确零的证明，本批未删除。** 因此没有建立p6 condensed CSR或global factor，没有再次启动p6，也没有拿p3/p4替换它。[独立原数组支撑核查](records/independent_checker_v20.json)。

三次p3 MUMPS symbolic/numeric/solve全计费。修复后先检查凝聚真残差、保存最小恢复场，再检查原恢复门；即使该门失败，finally仍释放factor/KSP/矩阵，记录RSS下降，之后C另起独立物理后处理。O3/E3失败场分别hash 4e00c42335cd179529c88bcea2c8e4b8a5b27cf3bc415a4611fd9957c6dbac42 / d95fb546834f09ea2d05209010b8c93a7d2066f9c947958e7b7af8512e82f1cf；未改向量。O3首失败场NOT_RETAINED不补造。

## 4. C物理全场、通道、区域与成本

独立进程只加载已冻结未合格场，重新验证编号、MPC、背景仿射、原native/total和gψ物理弱式，再重建物理E/H/curl。2112精确公共子单元切分包含固定区域边界；q15/q30差3.39275e-12，无整体相位拟合。如下相对差的主分母是实际E3范数，因没有合格O6，**只能称两空间争议，不能判哪条更准确**。

| 量，code/nm体积分，measured | O3/E3绝对差 | E3范数 / 实际分母 | 相对差 |
| --- | ---: | ---: | ---: |
| total E L2 | 6.274954586 | 6.242118730 | 1.005260370 |
| total curl/k0 与H | 6.274399956 | 6.241551233 | 1.005262910 |
| scattered E L2 | 6.145952849 | 0.896340905 | 6.856713574 |
| scattered curl/k0 与H | 6.202130719 | 0.896247227 | 6.920111471 |

H_code=curl(E)/(i k0 μr)，本模型μr=1，因此H和scaled-curl的L2差及范数恒等；单位沿原code归一化，不宣称SI磁场绝对值。[四类全场/分母与六区域](records/physical_comparison_v20.json)、[24行区域CSV](records/regions_v20.csv)、[12行六点复样本CSV](records/samples_v20.csv)。界面邻域为原1nm×7/135nm固定宽度、若干整平面union，区域重叠；不是薄层收敛证明。

| 同一全场差 / E3区域分母 | total E相对差 | scattered E相对差 |
| --- | ---: | ---: |
| air | 1.006536204 | 6.854391303 |
| substrate | 1.000033029 | 6.885614356 |
| grating | 1.003766750 | 6.853707737 |
| notch | 1.001092866 | 6.885484351 |
| interface_band | 1.005458978 | 6.912378414 |

四类通道为total projection、scattered projection、origin outgoing、boundary outgoing；不能把total投影直接称出射。top outgoing=total−incident，bottom outgoing=total；boundary乘原参考面相位。全部按side/(m,n)/s-p/k/e/参考面精确对齐。独立checker逐模式重算，不用整体通道范数掩盖单项失败。通道主分母max(abs(E3_j),1e-12)，完整绝对量和近零数量保留。四类最大相对差约246/22286/246/246，全都未过1e-4；该巨大origin量还含倏逝坐标敏感性，不能仅看它断定物理能量。[680行原复值及逐级功率](records/channels_v20.csv)。

R/T/A/A_volume、R00_s/p/total见[Response](../response_v20.md#1-实际完成和未过门)。E3的R/T等与已公布主线Gx784标量差约1e-8…1e-7，属于有用的标量一致性信号；没有其原场，也没有我们的合格O6，**不是1e-4全场或同成本资格**。可选Gx784原场查找仅查登记相关路径，一次无可用结果，不重算主线、不复制dot存储。

完整成本见[资源账](records/resource_costs_v20.json)：O3首/修复172.37/154.98s，E3 176.60s，O6 1752.71s，C 1380.81s，checker5.18s；全部失败、cold导出、保存/测试/等待和发布归完整父时钟，嵌套时间不重复相加。数值树峰4929130496B，0.5s RSS采样、swap0；轻任务2GiB，数值16GiB，factor内部规划12GiB。控制链最早原memory_scope/source_state文字未及时更新而根tmux实际已监督，后续源码已修正；保留该metadata限定，不回写原记录。新p6实际12类F载荷149361408B，native packet231550696B；早期48类9.76GiB预测不是实际峰，也未通过p6因子容量门。

## 5. 原尺寸后续准入判断

**决定：NO_GO_ORIGINAL_TARGET / CROSS_SPACE_ACCURACY_UNRESOLVED。** 本批不授权原尺寸solve，原精度和十进制2e12B/172800s边界不变。需要先使原坐标恢复及普通参考资格闭合，才有依据讨论网格减少；停止本批相位候选的自动晋级，不恢复M5训练。

| 准入项，derived或UNKNOWN | 普通空间现有证据 | 相位空间现有证据 / 原尺寸缺口 |
| --- | --- | --- |
| 全FE计数 | periodic x/y、open z：3NxNyNz p³+2NxNy p²；GX560p6=365760 measured | G0p3=27648 measured；p4=65280 derived not_run；约13.23倍向量差不是精度收益 |
| 全内部 / trace+端口 | p6内部252000，剩113760+340仅derived未装配 | p3内部12096，剩15552+340实测；原尺寸合格网格/NxNyNz UNKNOWN |
| 物理端口 | 小模型340完整；原目标数量/截断由主线独立资格，不重造32060库存 | 固定相位不减少原物理端口；原目标准确端口与耦合成本UNKNOWN |
| 积分/类别/冷成本 | p6已导出12 tensor classes；packet/F实测；未走symbolic | p3新空间12类；q15/30小模型检查通过，原尺寸cold JIT/振荡端口求积UNKNOWN |
| 同时对象/因子 | p3准确因子生命周期实测；p6只到packet，完整因子workspace未资格化 | 16GiB小模型RSS不证明2e12B整机；原尺寸装配/因子/恢复/output overlap UNKNOWN |
| 精度及20%收益 | 无合格O6全场，主线自身1%证书不可转1e-4 | 跨空间差大、恢复失败、E4未运行；同精度全流程wall/RSS优势UNKNOWN |
| 完整时间/唯一下一候选 | 不重求已成功主线Gx784；利用本批保存p6 packet先解决结构零/原恢复资格 | 若未来review解决authority后，仅同G0固定κ相位p4；本批不运行、不扫描 |

当前不能给原尺寸候选网格、全内存或48h保证；不是证明gVh类数学上无效。下一审阅应针对已有原数组明确内部端口理论零迹是否被浮点求积污染、原origin坐标恢复门如何被可靠满足，再决定有限单候选资格；若无可验证出口，就停止该表示路线。没有新传统PC、端口数据库或存储计划。

最终状态：FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT；本批NN=NOT_TESTED；D0成本否决/D1未运行及M3600改善/Mfinal退化全部保留。主线拥有普通空间精度和原尺寸工程，dot拥有真实C1/持久/后端；本支不操作其他分支。依赖组和未晋级边界见[manifest](records/selective_merge_manifest_v20.json)。
