# Response V74：正式Review V72执行结果

H准备时限用尽，未进入完整迭代。本轮拟把同一粗骨架上的边界值，用每个宏区域内的原Maxwell方程延拓到内部，让粗校正包含区域传播；细层1943745个FE未知量、38块局部校正、restart128和0.7nm物理全部不变。规划960个小区域，实际881个已形成并保存延拓。该准备增加局部因子与存储成本，完整迭代效果尚未检验；没有NN训练。

对象仍是有限缩尺的完整三维NOTCH，原κ=(8.94046081729244,0.7821889682108057,0)、canonical Si材料、grazing1°/azimuth5°/s和全部828物理模式不变。原四面体内部767280个系数按V70包恢复；新的宏内部765675行属于既有retained接口，只用于延拓粗函数形状，正式细层方程没有减少未知量。

| 固定对象 | 实际结果 | 判定边界 |
|---|---|---|
| 25576tet/p5/828、真实三维NOTCH、原κ | H准备时限用尽，未进入完整迭代 | 历史连续精度FAIL保持 |
| 粗层6240 FE+828 port | 规划7068行；881/960宏已保存，局部numeric=881 | 新E_H与旧E0分开；完整粗层pass_gate=False |
| 全域FGMRES | KSP.solve=0，迭代步=0，未返回retained | 原true与完整场另查 |
| 全局细层K/S/LU | 新生产读取、形成及factor均0 | 父局部内部LU与本批881宏numeric存在；迭代38块+E_H numeric=0，不能称factor-free |

## 粗层数学与容量

宏外表面明确归入共享骨架；真实MPC、唯一owner与复对偶只施加一次。延拓包含全部实际非零J-port项，反向含V_j^H r_J。新E_H由局部贡献及非Hermitian消元修正直接累加，端口基础项一次，不形成全局fine骨架Schur或A*Z全列库。

| 见证 | 全域Galerkin相对差 | 完整对偶运算尺度差 | 宏内部齐次行相对差 |
|---|---|---|---|
| 两个全域见证 | NOT_RUN | NOT_RUN | NOT_RUN |

局部最大解残差3.14928402084e-14、运算尺度8.72055996087e-16，最大放大0.0342799558781；门1e-10。以上局部误差来自producer实际求解记录；保存数组checker独立检查文件/成员hash、有限性、形状及唯一owner，不能替代未运行的全域Galerkin和完整复对偶见证。保存延拓载荷993648360B，见[局部资格](outcomes/records/harmonic_lift_qualification_v74.json)，载荷与RSS分开。38块加新粗层双倍symbolic=unknown / NOT_RUN，硬门80GiB；新E_H未完成时该估计为unknown，不能沿用旧E0批准numeric。每factor仍用liveRSS+所有未分解双倍估计+实际future(至少12GiB)≤96GiB。具体INFOG与numeric/释放见[factor库存](outcomes/records/local_coarse_factor_inventory_v74.json)。

## 原方程与完整物理

正式I约定retained从零开始，内部特解按原b恢复；本批I未运行。只有原式联合门过才有official功率。V70参照应在候选冻结后评分，本批没有候选，参照场未读；没有参照初始化、造RHS或挑选粗列。

| 原式量 | 实际 | 原门 |
|---|---|---|
| true | unknown / NOT_RUN | 1e-6 |
| native | unknown / NOT_RUN | 1e-6 |
| augmented | unknown / NOT_RUN | 1e-6 |
| port | unknown / NOT_RUN | 1e-6 |
| MPC_identity | unknown / NOT_RUN | 1e-10 |

| 物理场 | 候选分母 | V70分母，同一分子 | 严格同离散门 |
|---|---|---|---|
| 六场 | NOT_RUN | NOT_RUN | 1e-6 |

原240点、物理复通道、每mode功率、恢复/Schur-original和独立能量逐项见[独立检查](outcomes/records/scientific_checks_v74.json)。没有本批候选时这些项均NOT_RUN，不能把空值当0或把旧V70场抄成新场。未进入KSP不是不收敛，也不否决尚未检验的新粗基。strict=False；direct1e-10单列而不混用formal1e-6。

| 功率量 | 实际 | 输出资格 |
|---|---|---|
| R_total | unknown / NOT_RUN | official=False |
| T_total | unknown / NOT_RUN | 同上 |
| A=1-R-T | unknown / NOT_RUN | 不代替体吸收 |
| A_volume | unknown / NOT_RUN | 独立材料体积分 |
| 独立能量缺陷 | unknown / NOT_RUN | 1e-5 |

实际保存的本批数组留ignored，由[完整物理](outcomes/records/complete_physics_v74.json)和[增量库存](outcomes/records/array_inventory_v74.json)引用，不复制历史嵌套manifest。没有完整候选时不存在本批六场/240点/828输出，V70参考系数保持未读。

## 生命周期、费用与失败

原4小时H与14小时总窗从2026-10-11T13:00:55.333861Z冻结，不刷新。881个宏保存后，活跃阶段时间被重复计入造成第一次提前退出；原failed记录、源身份和全部费用保持，在清场边界修复并复用健康包。第一次基础Galerkin耗时4210.528095266083s但没有原子检查点，第二次只能重新生成并收费；事前4650s上界预测已被实际运行超过，不称免费恢复。第二次若耗尽原H时限便停止依赖迭代，不以剩余总窗口扩H。该停止是准备预算结果，完整粗基数值效果仍未检验。实际余量与预测见[最终费用](outcomes/records/resource_costs_final_v74.json)。

881个已保存宏的数值因子均在写出lift后释放，第二次退出时没有正在分解的宏。H控制器及后代已清场。正式迭代协议为：合法retained/RHS/尺度/packet先保存，再释放KSP及全部PC因子，记录RSS，随后恢复完整FE和物理输出；本批未进入这些I步骤，没有虚构释放39个未创建因子的收据。

| 费用口径 | 证据 / 边界 |
|---|---|
| 本轮完整研究费用 | 原窗elapsed与不重叠wrapper/独立命令下界分列，最终结算含文档及IO |
| prepared-start完整进程 | I未运行，完整单场T_N1无法定义；已发生准备增量逐收据结算，父准备不免费 |
| 从几何开始的packet-only cold N=1 | unknown；V70父构造带global-S，未测可移除后的冷链 |
| 历史已知唯一费用下界 | 368681.67300891416s；本批另加，不抹失败、不叠加嵌套子计时 |
| 同时峰与采样 | 已结算科学/资产消费采样峰9.27562713623GiB；最大gap=2.94492567121s；swap=0B。最终费用含随后文档检查，0.5s仅配置 |
| 目标V/Z库 | 257条主库derived 4841028816B；trace+port与全部FE分开，不是实测RSS |

- 存储门遗漏V74接线，误用V51额度；已增加本批专属dispatch与资源回归，失败未启动数值worker。 历史失败不改。
- 通过的测试没有放入runner标准资格指针；核对同源收据后补指针，未重跑科学计算。 历史失败不改。
- H把活跃时间重复算作未分段适配时间，881宏后提前退出；已修正扣重，继续使用原首次时钟，未保存的基础项重复费用保留。 历史失败不改。
- 定点测试命令误写类名；改为实际测试类，无PDE。 历史失败不改。
- 辅助命令直接传不可执行Python文件；补资格化解释器，以python -m运行。 历史失败不改。
- 保存checker误把自己的post进程当科学actor；改为核对自身role和目录，原失败日志及费用保留。 历史失败不改。
- 监督建立前的启动耗时未扣进剩余量；已在worker启动前重取V74额度并补纯回归。本次在原14400.013秒记录并发送TERM，未延长H。 历史失败不改。
- 文档renderer没有兼容明确的minimal_repair字段；补字段消费，无数值重放。 历史失败不改。

本冻结候选未授通用生产或原尺寸0.7nm/2TB48h资格；传统求解改变不归NN20。唯一下一pilot：仍是同一harmonic候选：先将基础Galerkin按精确局部支撑分组并原子保存，以现有健康宏包完成新E_H及两个全域见证，再在新的明确合同中执行原固定迭代；不改变粗空间或PC参数。本轮不自行开启该批次。

## 源码、测试与交付

Review commit 6fcc95ea94b869d738c00c5f3e11c7025dd52f13，base ccd357885f7f9be84efe3be07868cc94f13d93fc；canonical /home/fenics/Projects/NN-Lab；唯一分支task42_neural_coarse_inverse/upstream origin/task42_neural_coarse_inverse。PREFLIGHT与第一次H的source为c133795e69d8cecef9aa3e813c4c8df67b52cd87；第二次H为0f36cce833b9bd063ca91a1af919d66c1753be0e；清场后截止修复与最终资格/保存消费为3a9a0d2b4f03966d99d50b22e49a7adf6cd2dc28。全attempt/source绑定见记录，最终文档HEAD另列，不把后续文档提交当运行source。

最终12项新增数学/端口对偶/计数/计费/接线回归、相关compile/Ruff与四one-run validate通过；没有full pytest/CI。前一source的qualification stdout旧数量10不用于验收，当时unittest实际11；最终输出已从实际stderr取得12，见[测试](outcomes/records/tests_manifest_v74.json)。单次15项文档检查与新字节验收另见同记录；GitHub视觉NOT_VERIFIED。

[原始版本](outcomes/records/raw_archive_index_v74.json) · [源码绑定](outcomes/records/source_bindings_v74.json) · [研究消费契约](outcomes/records/retained_iterative_contract_v74.json) · [依赖组](outcomes/records/selective_merge_manifest_v74.json) · [closed/清场](outcomes/records/closure_v74.json)。最终完整remote SHA/clean/upstream收据在tmp/task042/v74/delivery_git_receipt.json。本批结束后暂停，不merge、不改master/邻支、不通知隔壁、不自动新窗口。
