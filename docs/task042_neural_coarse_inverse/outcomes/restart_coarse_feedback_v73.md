# Task042 V73：重启长度与粗层反馈的完整同离散对照

两条固定对照没有取得完整同离散解资格；结束当前重启/粗层组合，不继续尾部。 本次实际求解和恢复完整25576tet/p5/828候选，独立原式及六场评分决定科学结论。代码与保存数组checker成功仅说明执行链和证据可信，不替代方程门。本批无神经训练；历史P6/L5连续精度FAIL、原尺寸0.7nm、2TB/48h及NN20%均未升级。

## 问题、改变与固定控制

计算仍是缩尺s=7/135的真实三维NOTCH、0.7nm、原canonical材料、入射与κ、双周期及828个物理端口。完整FE1943745，内部767280，保留边面FE1176465，加端口1177293行。局部packet及边界来自V70，38个重叠局部块和7068行粗层来自V71；没有重建分区、映射或Galerkin矩阵。

重启会丢弃此前迭代方向。R128只把保留方向数从32改成128，PC与正交化保持原配置；B128在相同128方向配置中增加一次粗层反馈，把局部修正重新产生的粗分量消掉。两条都从物理保留向量零开始，内部固定特解正常恢复；没有参照场初值。

设C=Z E0⁻¹ Zᴴ，B为原38块RAS，A为当前缩放接口作用。R128使用C+B(I−AC)；B128使用C+(I−CA)B(I−AC)，实际步骤为zc=Cr、rc=r−Azc、v=Brc、z=zc+v−C(Av)。复数非Hermitian下采用真实共轭对偶，没有把I−CA替换成(I−AC)ᴴ。RIGHT FGMRES/restart128/max256、原norm/尺度/容差和Classical Gram-Schmidt保持，实际KSP view见[PC记录](records/PC_qualification_v73.json)。

每条进程各建立39个numeric，未保存的旧因子没有冒称重载。当前生产/PC/迭代global fine K/S读取、形成、因子均0；父内部LU、38局部LU及全局有界粗LU仍存在，不称factor-free。父V70 BUILD形成过global S，所以本批prepared-start声明不能扩大到几何起点packet-only cold。

## 原方程与完整场

| 路线 | 实做步 / 保存候选步 | retained true | 原true | native | augmented | port | 联合方程 / 严格场 |
|---|---:|---:|---:|---:|---:|---:|---|
| R128 | 256 / 256 | 0.994418150467 | 0.992693268155 | 0.992693268155 | 0.994417931363 | 0.00228909658346 | False / False |
| B128 | 195 / 192 | 0.995072797554 | 0.995072797554 | 0.995072797554 | 0.995072797554 | 4.03994303604e-13 | False / False |

retained门1e-11；独立原true/native/augmented/port各1e-6；恢复/MPC/Schur-original运算尺度各1e-10。direct目标1e-10单列，不用native替代其他失败项。每32步、候选通过和末态检查；未按短期下降率截断。原始曲线、RHS、retained和固定缩放分别绑定，[残差历史](records/residual_history_v73.json)保留完整失败状态。

R128完成256步。B128在195步被HotTracePacket残留的单实例600次上限打断，当时全批started=1150，未达1600总门；这是预算接线错误，不是资源否决或方法正常返回。已同轮修复并定点验收。两次正式KSP尝试槽用完，未再求解；从已独立审核的192步checkpoint完成全场消费。193–195步没有合法完整返回，剩余61步未执行，不能写成B128完成256步。B128以下场/原式属于192步候选；准确性失败成立，但不据此断言其未执行尾部的结果。故本批没有取得合格完整解，而B128的全256步科学对照未完成。

固定转移只使用物理RHS及V72失败残差，未读取准确参照选择参数、造RHS或warm-start。反馈前后真实残差/粗分量、绝对与运算尺度完整保存；有限代数通过不保证迭代收敛。见[反馈与逐factor资格](records/PC_qualification_v73.json)。

| 固定输入 | 输入残差/原RHS | 粗修正后/原RHS | M1一次后/原RHS | M2一次后/原RHS | M2粗约束绝对缺陷 | M2粗约束/运算尺度 |
|---|---:|---:|---:|---:|---:|---:|
| physical_RHS | 1 | 0.487639686028 | 60.7130442268 | 77.9655797366 | 1.14991924076e-10 | 1.37422243297e-11 |
| V72_failed_residual | 0.999209919609 | 0.485638429097 | 58.4882577276 | 77.8935772881 | 1.35487100384e-10 | 1.66195831139e-11 |

M2消除了粗测试分量，但单次校正的完整Euclidean残差反而放大；这与粗约束通过并不矛盾。诊断中的最优复标量仅离线评分，没有进入正式PC。两条实际FGMRES是独立完整判断，不能据此认定唯一根因已经定位。

| 相同步数 | R128原true | B128原true | R128累计迭代含检查(s) | B128累计迭代含检查(s) |
|---|---:|---:|---:|---:|
| 32 | 0.998859209781 | 0.999368221074 | 483.786530923 | 624.031104415 |
| 128 | 0.992675296094 | 0.99507279952 | 1772.90364498 | 2337.06123336 |
| 192 | 0.992675827113 | 0.995072797554 | 2610.97941635 | 3458.09873694 |

这里比较共同步数；每步成本并不相同，B128每次PC比R128多一次原作用及粗解。完整作用种类与冷读/numeric/输出费用另列，不能用步数或本表授同精度加速比。

新候选全部冻结、actor退出后唯一VERIFY才读取V70。六场是total/scattered E、H、curl，全部保留原gVh，不投影、校幅相或改floor。同基同几何先减系数再积分，一次分子同时给候选和V70参照分母评分；两种均须过门。原V72约630的候选分母比值不改写。

| 路线 / 场 | 全域/候选 | 全域/V70 | 原240点/候选 | 原240点/V70 | 门 |
|---|---:|---:|---:|---:|---|
| R128 / E_total | 88.9879231297 | 0.988887497881 | 89.006585611 | 0.988889808445 | ≤1e-6 |
| R128 / H_total | 88.9858518287 | 0.988887500243 | 88.5204139034 | 0.988844170412 | ≤1e-6 |
| R128 / curl_total | 88.9858518287 | 0.988887500243 | 88.5204139034 | 0.988844170412 | ≤1e-6 |
| R128 / E_scattered | 1.05075191883 | 6.88391647442 | 1.05371220583 | 6.83521143869 | ≤1e-6 |
| R128 / H_scattered | 1.05073013005 | 6.88400992225 | 1.05370299101 | 6.83522162891 | ≤1e-6 |
| R128 / curl_scattered | 1.05073013005 | 6.88400992225 | 1.05370299101 | 6.83522162891 | ≤1e-6 |
| B128 / E_total | 101.428821619 | 0.990238282756 | 101.486943291 | 0.990243914488 | ≤1e-6 |
| B128 / H_total | 101.426324627 | 0.990238285075 | 100.882428881 | 0.990199684038 | ≤1e-6 |
| B128 / curl_total | 101.426324627 | 0.990238285075 | 100.882428881 | 0.990199684038 | ≤1e-6 |
| B128 / E_scattered | 1.05066879792 | 6.89331965757 | 1.05362530606 | 6.84457102662 | ≤1e-6 |
| B128 / H_scattered | 1.05064704626 | 6.89341323273 | 1.05361422901 | 6.84459139245 | ≤1e-6 |
| B128 / curl_scattered | 1.05064704626 | 6.89341323273 | 1.05361422901 | 6.84459139245 | ≤1e-6 |

实际参考面复通道、逐mode功率、R/T/A/A_volume差、独立能量及q23/q31运算尺度见[完整物理](records/complete_physics_v73.json)与[独立checker](records/scientific_checks_v73.json)。原六场1e-6、功率/体吸收1e-8、逐mode1e-9、能量1e-5保持；双分母不择优授PASS。official只来自原方程通过场，失败候选的功率仅diagnostic。

| 路线 / 功率 | 当前候选实测 | official |
|---|---:|---|
| R128 / R00_s | 0.977637324955 | False |
| R128 / R00_p | 2.08470949633e-12 | False |
| R128 / R00_total | 0.977637324957 | False |
| R128 / R_total | 0.97763732967 | False |
| R128 / T_total | 0.000111797446579 | False |
| R128 / A_balance | 0.0222508728829 | False |
| R128 / A_volume_total | 2.23673842057e-06 | False |
| R128 / energy_closure_error | -0.0222486361445 | False |
| B128 / R00_s | 0.980244979452 | False |
| B128 / R00_p | 3.68366283403e-12 | False |
| B128 / R00_total | 0.980244979455 | False |
| B128 / R_total | 0.980245118665 | False |
| B128 / T_total | 8.6432350105e-05 | False |
| B128 / A_balance | 0.0196684489852 | False |
| B128 / A_volume_total | 1.72676045503e-06 | False |
| B128 / energy_closure_error | -0.0196667222248 | False |

## 实际容量、生命周期与完整费用

因子双倍symbolic总门80GiB，整树96/112/128GiB。每factor前检查live RSS+全部未分解双倍估计+future≤96GiB；future至少12GiB且枚举长Krylov库、PC/审核/恢复工作区。逐CSR读取、分解并释放输入，没有同时装载全部局部矩阵。主V/Z257条载荷4841028816B=4.50856GiB为derived，完整FE与trace+port分开，不当作实测RSS或目标容量资格。

| 路线 | prepared进程链(s) | KSP子计时(s) | 新numeric | factor释放前→后单进程GiB |
|---|---:|---:|---:|---:|
| R128 | 6009.00250631 | 3496.05065566 | 39 | 38.2918128967 → 7.81424331665 |
| B128 | 6396.80511518 | unknown | 39 | 42.9400405884 → 12.4624710083 |

KSP和所有因子释放并记录RSS后才完整恢复/输出，两个KSP不共驻。本批采样树峰43.598033905GiB，实际最大gap2.56954960711s，名义0.5s不等于连续硬峰。ownswap观测0B、OOC0，MPI1/math/CPU1/GPU0以及原宿主/cgroup/PSI/384GiB邻增长和CPU-SMT/heavy锁门保持，没有修改其他任务。

全域作用started/completed=1153/1152，上限1600；资格/诊断、PC内部、外层、显式true和PUBLIC原式全部照计。全批KSP attempts=2，new numeric=78。每类调用及PC子计时见[费用](records/resource_costs_final_v73.json)，正交化未单独分段时保留unknown余额，不把所有step wall归PC。

started与completed差1来自上述被旧上限拒绝、尚未执行kernel的外层调用，失败上界仍计费。B128异常前的PC分类总时间未成功保存，明确unknown；其实际每步wall、因子子时间、原作用计数和整条失败进程费用保持。补消费者的numeric与KSP均0，不重复分解39因子。

本窗按保守更早边界2026-10-11T06:57:14.246493+00:00冻结，heavy-stop17:57:14.246493UTC、交付截止18:57:14.246493UTC，不重开V72或刷新预算。第一次精确工作时刻在上下文恢复中不可取，已显式使用前次交付的更早边界；该未知间隔只计入预算elapsed，不冒称实测费用。已知不重叠wall下界13767.5969621s（监督wrapper加单独定点测试），历史已知下界354820.600359s，未分段实现/等待/提交与历史文档尾部保留unknown。

上述表格与费用数字是2026-10-11T12:11:15.599935+00:00保存的结算快照；之后一次文档验收、清场及最后归档的实际增量由[最终费用记录](records/resource_costs_final_v73.json)补齐，旧快照不冒称最终全批数值。修复前的两次定点测试消费也保留在repair journal，不把已知失败费用置零。

prepared-start完整诊断尝试和研究费用分列，合格解T_N1取决于方程及严格场联合门；几何起点packet-only cold仍unknown。新实际存储5.28538879566GiB，历史库存172.25544903GiB，自由空间2556.42856598GiB。本批32GiB/Task664GiB/free50GiB和512MiB证据余量按实际去重inode核验。完整数组ignored，不复制父大包、不删除失败。

## 修复、未运行与下一步

本轮修复long-restart/future显式传递及precommit最小Gate接线，失败stderr与定点复验保留；正式运行错误如有均追加[repair journal](records/repair_journal_v73.json)。活跃计算期间tracked源码与HEAD不变，合法returned向量先保存，后处理只补消费，没有为JSON/文档重新factor。旧V71 CAPACITY_BLOCKED、V72数值FAIL与历史费用原样保持。

最初7个focused测试通过；预算接线和无求解补消费修复后，最终11个相关数学/scope/释放/真实PETSc128测试、compile/Ruff及4dat validate通过。一次15项文档合同与增量链接/表格收据见[测试](records/tests_manifest_v73.json)。CI未运行，GitHub视觉NOT_VERIFIED。无global fine LU后备、p/h/M改动、旧PDE重解、粗Galerkin重建或NN训练。

唯一下一建议：关闭本固定restart/PC组合；将当前未解残差中的跨区波动传播作为唯一后续粗空间候选，先预登记有界波动/谐波内容和完整同离散对照，不再加restart或续原尾部。 该项未执行。没有合格完整解就不授同正确性速度/内存改善；原尺寸2TB48h与NN20仍未取得。

## 身份与证据

review commit f1504cffd4bdcd7bfe025c0ff8e544298e1b7995；base ccd357885f7f9be84efe3be07868cc94f13d93fc；canonical /home/fenics/Projects/NN-Lab，唯一分支task42_neural_coarse_inverse，upstream origin/task42_neural_coarse_inverse。实际数值sources={"R128": "5e35ab9b1fac5e9e7101616db29a8fb7e4af39f2", "B128": "5e35ab9b1fac5e9e7101616db29a8fb7e4af39f2"}，独立VERIFY source在[source身份](records/source_identity_v73.json)，与最终文档HEAD分开。

[数组增量](records/array_inventory_v73.json) · [源码增量](records/source_bindings_v73.json) · [原始版本](records/raw_archive_index_v73.json) · [研究消费契约](records/retained_iterative_contract_v73.json) · [依赖分组](records/selective_merge_manifest_v73.json) · [closed/清场](records/closure_v73.json)。精确最终HEAD/remote/clean/upstream收据在tmp/task042/v73/delivery_git_receipt.json；不merge、不改master/邻支、不通知隔壁、不自动开下一窗口。
