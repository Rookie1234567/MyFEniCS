# Response V75：正式Review V73执行结果

本轮已进入并完成一次256步FGMRES，完整原方程残差仍为0.999209813227，相对起点1仅下降0.0790186773232%。门是1e-6；继续增加步数没有证据，本批不延长、不重开、不换参数。已恢复并保存全部有限元系数、六场、原240点及全部828复模式/功率；这些场不满足原方程，功率只能作诊断，不能称可用物理解。

这里的“局部Maxwell-harmonic粗空间”是把同一粗骨架的边界值，用每个小区域内的原电磁方程延拓到内部，尝试让全局校正包含传播信息；再用38个重叠局部块修正剩余误差。它只改变求解过程中的校正，物理方程和1943745个FE未知量不变。新增代价是局部延拓准备、粗矩阵和因子；数学一致不保证迭代收敛。本批没有NN训练。

| 固定0.7nm有限三维NOTCH | 实际结果 | 判定 |
|---|---:|---|
| 25576tet/p5/828；原κ、真实材料/入射/双周期 | full FE1943745，retained FE1176465+828=1177293 | 同一s=7/135缩尺问题；不是原尺寸 |
| 粗层6240 FE+828port | 7068行，完整新E_H | 全域数学PASS；非旧E0 |
| 960宏 | 881旧复用、79新numeric、0真实重算 | 旧source/hash及费用保留 |
| 正式KSP | 1次，RIGHT/restart128，累计256步 | 残差FAIL，无下降率早停或参考warm-start |
| 原true / retained显式true | 0.999209813227 / 0.998989109972 | 分别超1e-6 / 1e-11 |
| 生产global fine K/S读取、形成、LU | 0 / 0 / 0 | 父单元内部LU、79宏numeric及38+1 PC因子存在；非factor-free |
| 独立同离散全场 | False | 两固定分母FAIL，旧连续精度FAIL保持 |

## 健康复用与可恢复准备

881个旧宏经文件/成员hash、shape、finite和唯一owner检查，固定宏0/121/880重新形成局部作用、未factor。局部相对差最大6.52537939195e-15，保存correction配对差0；不是假称重审了881个原局部残差。当前缓存代码变更由不变数学AST与明确兼容收据连接到旧producer c133795e69d8cecef9aa3e813c4c8df67b52cd87，旧identity未修改。[兼容收据](outcomes/records/reuse_compatibility_v75.json)

基础Galerkin现在按确定cell-ID分100个互斥块原子保存，25576cell各一次，零支撑cell也登记；完整C/D/H端口基础仅一次。新算100块、回读已有块0块，最终完整base有检查后回读。完整base路径与block路径不能混加；半写对象不准入。旧V74基础项没有提交检查点，因此本次真正新算，未冒称免费恢复。完整base实测20.8739274901s；当前没有失败重播。旧首次4210.528095s及第二次未完成前缀仍留旧账，不称新核加速比。[基础清单](outcomes/records/base_checkpoint_manifest_v75.json)

一次52实际cell的小配对保留各自矩阵、方向、材料和全局列；最大差7.33248491435e-16。抽取/原乘/批乘分别0.0255814/0.0220841/0.0197435s，仅是有界小配对，不能据此给完整PDE速度比。准备路径继续完成79个缺项，保存lift后释放每宏因子，健康881未重分解。保存全部lift载荷1030762088B，与RSS分开。[完整准备](outcomes/records/harmonic_completion_v75.json)

| 全域seed7403见证 | Galerkin相对差 | 宏内部齐次行相对差 | 完整复对偶运算尺度 |
|---|---:|---:|---:|
| 0 | 1.65246377717e-14 | 1.25347046631e-14 | 1.00301219203e-16 |
| 1 | 1.65701218738e-14 | 1.34915925704e-14 | 8.2385855497e-17 |

另以独立随机fine向量/seed7404核对完整primal/dual，运算尺度差1.37853062174e-17，门1e-10；包括实际非零内部-port延拓及其Hermitian回拉，未以某个A*Z向量自证全部对偶。[数学及独立重算](outcomes/records/full_Galerkin_duality_v75.json)

## 实际迭代与完整原式

原物理retained零初值；内部特解正常恢复，所以不是全部FE系数强置零。38块+新E_H共39个numeric在逐因子live容量Gate后创建，各自新分解并计费。coarse-first仍为C_H r+B_RAS(r-A C_H r)，无B128末尾反馈。actual KSP view证明RIGHT/FGMRES/restart128/max256、原norm/正交化/尺度；没有读取V70场初始化、造RHS或挑选粗列。

| 步数 | retained显式相对残差 | 未凝聚完整原true | port残差 |
|---|---:|---:|---:|
| 0 | 1 | 1 | 0.0849805988388 |
| 32 | 0.999923750395 | 0.99992505761 | 0.0145150647394 |
| 64 | 0.99977562595 | 0.999988437569 | 0.00972767219263 |
| 96 | 0.999486267942 | 0.99977264803 | 0.00702326933654 |
| 128 | 0.998989120176 | 0.999210629605 | 0.00443870776023 |
| 160 | 0.998989120161 | 0.999210622284 | 0.00443878049785 |
| 192 | 0.998989120097 | 0.999210709229 | 0.00443893456475 |
| 224 | 0.998989119753 | 0.999210693719 | 0.00443911186775 |
| 256 | 0.998989109972 | 0.999209813227 | 0.00443877490164 |

128步后几乎停滞，完整256步已检验该固定候选，不再补旧尾部或增加restart。原body使用独立PUBLIC_BASIX系数先收缩q15及真实q63三角边界，不读生产矩阵来自证；每32步、末态及退出检查保存。全批列作用539，started/completed相同，上限800；其中PC内部fine作用、外层作用、显式true和独立原式分别收费，计数见[残差](outcomes/records/residual_history_v75.json)。

| 原式/身份 | 实际 | 固定门 | 判定 |
|---|---:|---:|---|
| true | 0.999209813227 | 1e-6 | FAIL |
| native | 0.999209813227 | 1e-6 | FAIL |
| augmented | 0.998989102672 | 1e-6 | FAIL |
| port | 0.00443877490164 | 1e-6 | FAIL |
| MPC_identity | 2.23366724626e-18 | 1e-10 | PASS |
| rhs_q47_q63 | 1.36927008636e-15 | 1e-10 | PASS |

内部恢复运算尺度5.64800350439e-16；Schur-original 1.37325424947e-15，均≤1e-10。独立direct目标1e-10仍FAIL，不能拿恢复恒等式PASS代替方程求解FAIL。[actor和独立checker分列](outcomes/records/scientific_checks_v75.json)

## 六场、点值与全部模式

候选和全批hash冻结、actor退出后，唯一VERIFY才读V70参考。相同basis/mesh/DOF先减系数，再直接求物理差场；不投影、不校幅相，不为两分母重复积分。六场同时保存原差分分子、候选分母及固定V70分母；门为严格同离散1e-6，均FAIL。

| 物理量 | 全域候选分母 | 全域V70分母 | 240点候选分母 | 240点V70分母 | 严格判定 |
|---|---:|---:|---:|---:|---|
| E_total | 496.101600409 | 0.997988393182 | 496.053260312 | 0.997988193787 | FAIL |
| H_total | 496.04128227 | 0.997988393842 | 496.838177654 | 0.998004325859 | FAIL |
| curl_total | 496.04128227 | 0.997988393842 | 496.838177654 | 0.998004325859 | FAIL |
| E_scattered | 1.05035990355 | 6.947270297 | 1.05329154358 | 6.89809952494 | FAIL |
| H_scattered | 1.05033833514 | 6.94736459285 | 1.05327530393 | 6.89853968701 | FAIL |
| curl_scattered | 1.05033833514 | 6.94736459285 | 1.05327530393 | 6.89853968701 | FAIL |

| 模式/功率量 | 实际 | 资格或严格差门 |
|---|---:|---|
| 828参考面复通道相对差 | 1.23868580693 | 1e-6 |
| 逐mode功率最大绝对差 | 0.919712779481 | 1e-9 |
| 候选R_total / T_total / A_balance | 0.995930923674 / 3.66406224285e-06 / 0.00406541226358 | diagnostic，official=False |
| 零级R00_s / R00_p / R00_total | 0.995930923252 / 1.48283446953e-14 / 0.995930923252 | 物理s/p分别及两者之和；diagnostic |
| 独立A_volume | 7.33404057442e-08 | 真实Im(epsilon)体积分，不用1-R-T代替 |
| 独立能量R+T+A_volume-1 | -0.00406533892318 | 绝对值≤1e-5 |
| R/T/A/A_volume差 | R_total=0.919712364448, T_total=0.905661497068, A_balance=0.0140508673795, A_volume=0.0181162062985 | 各≤1e-8 |

完整六场由保存native包络、实际mesh/basis/MPC/κ解释，E含解析相位，H和curl含全部Cκ；原240点全量保存，828模式键/侧/极化/参考面/复振幅/逐mode功率未删。R00_s、R00_p、R00_total各由原输出单独定义；全部原输出路径和hash见[完整物理](outcomes/records/complete_physics_v75.json)。当前场尚非原方程的解，这些功率及误差只能诊断；不以能量或total单项覆盖FAIL。[唯一比较与两分母](outcomes/records/paired_results_v75.json)

直观上，候选体内总场太小，候选分母下总E误差约496，而固定V70分母下仍约0.998；后一项说明不是近零分母制造的假失败。候选R接近1、T仅约3.66e-6，也与同离散参照严重不一致。正确恢复与低存储接口没有解决全局迭代误差，不能靠延长这个停滞尾部替代新的机制证据。

## 生命周期、实际资源与成本

retained/RHS/尺度/packet/source先保存。KSP及38+1因子释放后RSS从38.9947052002GiB降到8.55443954468GiB，然后恢复767280内部系数；独立原式后释放热映射及无用对象，再输出全部物理。无合法向量丢失、补factor或补KSP。[真实因子/释放](outcomes/records/factor_inventory_v75.json)

PC双倍symbolic总74.7740268707GiB，≤80GiB；每factor均检查live RSS+全部未分解双倍symbolic+逐项future(至少12GiB)≤96GiB，不仅看最大patch。96/112/128GiB整树规划/警戒/采样停止不变；科学及资格监督集合采样峰44.0530548096GiB、最大实际gap1.72800772986s，0.5s只是配置，连续峰unknown。ownswap/OOC=0；MPI1/CPU/math1/GPU0、qualified complex128/int64、原宿主/cgroup/PSI/邻增长/SMT/heavy锁门保持，没有修改邻任务或系统。

| 本批不重叠命令 | 秒 | 口径 |
|---|---:|---|
| HARMONIC_PREPARE_one_run01 | 1430.78610369 | measured；完整wrapper到后代清场，不叠加worker |
| HARMONIC_one_run01 | 5912.21047086 | measured；完整wrapper到后代清场，不叠加worker |
| PREFLIGHT_one_run01 | 258.778903038 | measured；完整wrapper到后代清场，不叠加worker |
| VERIFY_COST_one_run01 | 510.941100167 | measured；完整wrapper到后代清场，不叠加worker |
| auxiliary_focused01 | 95.8619318579 | measured；完整wrapper到后代清场，不叠加worker |
| auxiliary_pre02 | 95.6526721551 | measured；完整wrapper到后代清场，不叠加worker |

FGMRES solve含监控/检查3639.99508977s，嵌套PC三角解/作用/原式及IO只作细分、不再叠加wrapper。复用准备后的完整候选进程5912.21047086s；另计唯一CHECK 510.941100167s，合计6423.15157102s。这是失败候选的完整可测费用，不是合格物理解的速度收益。

本批科学/资格阶段费用快照UTC=2026-10-12T02:08:03.123477+00:00：研究elapsed 9884.12176156s，不重叠wrapper下界8304.23118176s，未分段间隔单列；V74+本批命令下界21535.344498s。历史唯一费用下界381912.78632514126s仍保留，最终文档/收口费用和Git尾段由[最终账](outcomes/records/resource_costs_final_v75.json)及tmp/task042/v75/delivery_git_receipt.json补齐，不把未知interval填0。

本批当前准备+候选+CHECK增量下界7853.93767471s不含881旧宏及V70/V71必需准备；完整必要N=1、从几何开始去global-S历史的packet-only cold仍unknown。旧失败重复Galerkin是研究费用，不能拼进正常一次构建并称加速；未配平同正确性，不授生产时间/内存比。257条retained V/Z主库derived 4841028816B，完整FE库另计；derived载荷不是RSS或2TB资格。

新增存储快照3929007047B、自由空间2683572899840B；32GiB新ignored/696GiBTask/free50GiB及512MiB证据余量全程受控。大数组ignored，只提交增量hash指针，不复制父大包。实际全库存和收口后值见最终账与[增量库存](outcomes/records/array_inventory_v75.json)。

## 修复边界、决定与交付

C1完成基础持久化、旧881数学兼容、单一12hscope及计数；C2保存partial宏身份并消除PC重复骨架所有权。正式科学/资格命令未失败，交付metadata脚本一次多余括号的编译失败已留证并定点修复；文档辅助启动另有一次多传--导致FileNotFoundError，检查进程尚未启动；已去掉分隔符，只补文档并保留91.337305s失败费用。无PDE重播，数值停滞不当bug。旧V74 failed/source/raw/cost均未改写；本次不是重开V74时钟。首次UTC2026-10-11T23:23:19Z，heavy-stop2026-10-12T10:23:19Z，交付截止11:23:19Z；同boot monotonic固定，无新阶段刷新。修复和未运行范围见[记录](outcomes/records/repair_journal_v75.json)。

本批全部四个one-run角色实际完成，正式solve仅一次；未执行的是额外尾部、参数/空间扫描、NN训练和原尺寸PDE，因合同及固定负结果关闭，未写PASS。唯一下一建议：在新正式合同中评估一个真正不同、能处理波传播的粗校正机制，并仍以同一完整原方程验收；不要继续调这个harmonic+38RAS组合或再补尾部。本轮不自动立项或开V76。

Review02703c5ce56a18b134b50eded39645cb422a0d95，base ccd357885f7f9be84efe3be07868cc94f13d93fc；canonical /home/fenics/Projects/NN-Lab，唯一分支task42_neural_coarse_inverse。PREFLIGHT source48d5a09211d547a59a68c96e8cfd6ef75bd7d0f4；完整H/I/VERIFY source6009967437ed5853ddd9f5f71780f3cf00c32bbd；后续文档HEAD独立记录，不冒充数值source。[源码/真实输入/resolved/环境](outcomes/records/source_bindings_v75.json)

最终改动后21个targeted方法、相关compile/Ruff及四dat真实validate已通过；科学检查和数值FAIL分别列。一次15项文档检查及增量链接/表格/hash另列，无full pytest/CI，GitHub视觉NOT_VERIFIED。[测试](outcomes/records/tests_manifest_v75.json) · [原始版本](outcomes/records/raw_archive_index_v75.json) · [依赖组](outcomes/records/selective_merge_manifest_v75.json) · [接口消费契约](outcomes/records/retained_iterative_contract_v75.json) · [closed/清场](outcomes/records/closure_v75.json)

不授连续精度、原尺寸0.7nm/2TB48h或NN20。closed/active null、后代清场、自有锁释放、clean/upstream和remote完整HEAD以最终交付收据实核。只推送当前分支后暂停，不merge、不改邻支、不通知隔壁、不自动开新窗口。
