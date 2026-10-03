# Task40 Review V6 执行回应

**状态：已完成 V6 授权的一次 Gx784 正式运行及一次保存场后处理。数值求解/恢复门和本轮 Gx/F5 配对比较通过；Gx784 仍为 authority-limited，没有匹配 direct reference。原尺寸任务仍为 NO-GO。**

## 正式 Gx784 结果

Gx784 使用 14×4×14、共 784 个单元的缩小离散模型。p6 是实际求解完整电磁场的高阶有限元；p4 在迭代中提供较低阶的校正，保留完整 p6 场但增加一个较小校正系统的装配和因子成本。本次为 Full3D、M=340 个有序端口模式、MPI1、complex128。p6 完整场向量有 530,400 行；p4 凝聚矩阵为 67,988 行、26,295,924 个 owned-row stored entries。

| 检查 | 结果 | 含义与边界 |
|---|---:|---|
| 外层 launcher / 数值分类 | worker_exit0 / DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED | launcher 正常退出；数值解通过一致性门，但没有同离散 direct reference |
| Full A6 显式真残差；释放后复核 | 9.692115162625173e-7；两次相同 | 限值 1e-6，通过 |
| native recovery identity / port residual | 6.42238071470954e-11 / 4.473743083467747e-16 | 分别低于 1e-10 / 1e-8 限值 |
| 官方 R_total / T_total / A_balance / A_volume_total | 0.07612656490058632 / 0.9057668832851113 / 0.01810655181430232 / 0.018106531117781374 | A_volume 来自材料体积分吸收；|A_balance-A_volume|=2.0696520944968322e-8，端口-体积闭合误差 2.0696520941498875e-8 |
| 零级反射 R00_s / R00_p / R00_total | 0.07612609133082268 / 1.819475255892784e-21 / 0.07612609133082268 | s/p 通道分开列出，p 通道接近零 |
| independent direct comparison | MATCHED_REFERENCE_NOT_AVAILABLE | 解不是 matched-reference pass，不能据此宣称连续收敛 |

## Gx/F5 保存场比较

后处理只读取本次 Gx784 完整保存场及已经存在的 Gx、F5 字段。比较在公共物理坐标子单元上积分，使不同网格的向量序号不会被误作同一点。checker 从原始比较字段独立重算，fresh JSON 的字段内容与保存的 checker 记录一致。

| 两场配对 | 八项场量中最大差；分母为冻结 F5 同量 L2 范数 | 11 个冻结显著模式的最大复振幅差；分母为该配对首场振幅 | R/T/A_balance/A_volume 最大绝对差 | 结论 |
|---|---:|---:|---|---|
| Gx → Gx784 | 6.419146264421262e-4（限值 1%） | 8.030064719462767e-5（限值 1%） | 2.4943069198285484e-6 / 2.314543935733049e-6 / 1.7976298405386615e-7 / 1.8065518352788912e-7（限值 1e-3） | 通过 |
| F5 → Gx784 | 6.420202550004441e-4（限值 1%） | 8.148431581802385e-5（限值 1%） | 2.4936299092420677e-6 / 2.3565318039153738e-6 / 1.370981053128162e-7 / 1.8195046935440273e-7（限值 1e-3） | 通过 |

两对均保留 340 个模式，ordered key 列表完全相同；上述四项功率分别按 R、T、吸收平衡值、体积吸收值排列。能量闭合误差约 2.0e-8 至 2.42e-8，低于 1e-5。因此 checker 分类为 tested_x_agreement_pass，只覆盖冻结的小模型及这些 x 方向配对，不代表 y 收敛、continuum convergence 或目标尺寸精度。

## 时间、资源与预算

| 阶段 | 计时口径 | 时间 | 资源口径 |
|---|---|---:|---|
| Gx784 正式运行 | full-workflow monotonic | 3431.6226415440906 s | 运行全程 |
| Gx784 正式运行 | run-summary conservative-realtime interval / shared-ledger settled debit | 3812.9144130120467 s / 3812.953841459373 s | UTC 时钟正向偏差按策略保守计费；不称为 monotonic 时长 |
| Gx784 正式运行 | watchdog interval | 3431.2005693890387 s | 同时存活进程树 RSS 峰值 7,782,744,064 B；进程树 swap 0 B；13,507 样本；身份覆盖完整、后代清空；PSS 按 profile 未采样 |
| 保存场后处理 attempt2 | watchdog monotonic interval / settled ledger charge | 1442.1525664149085 s / 1601.0044167499855 s | 同时进程树 RSS 峰值 946,765,824 B；swap 0 B；5,680 样本；身份覆盖完整、后代清空；PSS 未采样；无 PDE |

正式运行期间 WSL 全局 pswpout 增加 151 页，无法归因到该任务；因此只报告任务进程树 swap 为 0，不报告系统级 swap 为 0。共享 172,800 s 账本结算后：测量 elapsed 5418.577512204991 s，另有已核验 policy debit 0.004821757087484002 s 与 10 s conservative allowance；budget used 5428.582333962078 s，remaining 167371.41766603792 s，无活动预留。历史扣费 4.619253995631944 s、一次 V6 Q4 扣费、一次 postprocess 扣费都保留在同一账本中。

## 保留的失败与 AUTO 成本边界

首次实际保存场 readiness preflight 曾因 ValueError: Gx784 worker summary classification differs from its run manifest 停止。失败点早于 attempt2 目录、预算预留、监督器、比较 worker 和 checker；没有启动 PDE solver 或 factorization。该 preflight 没有 workflow clock sample，elapsed 保持 unknown、未收费。后续两处局部修复分别把 launcher exit 与数值分类拆开，并允许在新 V6 授权下接续已记录的 POSTPROCESS_PARENT_FAILED；修复 commit 与失败收据都留在 closeout evidence 中。

已存在的 original/repair AUTO 清单各读取一次，生成器没有重跑。两份均为 36,244,923 B、SHA256 52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d、32,060 个有序 key，最大 |m|/|n|=142/35，ordered-key digest 为 03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec。清单只代表原尺寸外部端口/模式库存，不证明内部几何/网格已合格。已有估算只描述对象字节数或候选计数，不是 RSS 或同时驻留测量：

| 已登记的 derived 量 | 数值 | 还缺什么 |
|---|---:|---|
| 单个原 H 对角 / 稠密矩阵 | 512,960 / 16,445,497,600 B | Hhat 内部修正和共存数量/时间 |
| 单个 p6 单元原张量 / 内部 LU 形状 | 12,446,784 / 3,240,000 B | LU 额外工作区、支持类数量和缓存生命周期 |
| trace Schur / 单份耦合或恢复项 | 2,985,984 / 3,110,400 B | 共享方式、方向类及 twist 实例数 |
| 272×4×14 候选 | 15,232 单元；p6 full 10,228,620，interior 6,854,400 行 | 这只是计数候选，不是合格网格 |
| 该候选 p6 retained / p4 interface | 3,126,332 / 1,346,364 行 | 不含分解填充 |
| 候选 74 个 outer vectors / retained-full scratch | 3,701,577,088 / 4,428,003,200 B | 估算来源；生命周期重叠未知，不能相加作峰值 |

目标尺度的冷 JIT/求积、C/D 与 Di/XiB、H/Hhat 并存、恢复缓存与 twist 数、投影临时对象、全部 q 因子 fill/workspace/并存、外层迭代、完整求解/恢复/输出/checker 时间及旧 AUTO 生成耗时仍为 unknown。因此 50×25×140 nm 完整求解仍 NO-GO，没有 2 TB 容量或完整工作流资格。

## 验证与证据

资格化 WSL activation、complex128 PETSc ABI 与 MPI1 检查通过。7 项 test_task40_v5_postprocess_preflight.py 定向测试通过；独立 checker fresh re-run 与保存 JSON 一致。最终文档合同测试 31 passed；证据 JSON/hash 核验与 diff check 通过，详情见 [测试摘要](outcomes/test_summary.md)。full-repository pytest、MPI4、Ruff、CI、额外 PDE、dot worker 和 master merge 均未运行或未授权。

可复核的 compact evidence、原始哈希清单与当前 run index 分别见 [V6 closeout record](outcomes/records/review_v6_gx784_postprocess_closeout_v1.json)、[run index](outcomes/records/run_index.json) 和 [outcomes summary](outcomes/summary.md)。原始场、checker、账本及服务记录继续留在 ignored artifacts；未覆盖 V5 的失败记录。


## 授权补检历史（正式运行之前）

V6 的补检授权仅覆盖缺少 clock_sample 的结算修正、直接计时字段一致性和一次同链补检；此前两次失败分别是 fixture 缺少 sys 导入和 V6 结算缺少 clock_sample，授权范围见 [补检授权记录](outcomes/records/review_v6_postprocess_retest_authorization_v1.json)。隔离副本使用原 Gx784 账本、输入和原始/修正 pre-ledger 凭据，只重绑临时文件路径及路径变化引起的哈希；生产账本身份、历史 fixed_source_sha、4.619253995631944 s 历史扣费和唯一 bug replay 计数均保留。

当时将 Gx784 review 与 postprocess preflight 两个测试文件合并执行，首轮为 17 passed、1 failed；唯一失败是旧 V5 测试匹配旧错误文案。更新该历史断言后，失败的旧 V5 replay 单测单独通过，V6 控制链没有重跑。集成测试真实运行 launcher 预算预留/结算、一次性授权、专用父监督器、_V14Runtime、V20 时间策略解析和 Q4 截止决策；数值叶节点使用无 FE 哨兵。保存场后处理测试覆盖 ready preflight、POSTPROCESS_PARENT_FAILED 接续、预留与结算、哈希绑定修复重放、监督器及 checker 命令；独立 checker 的负结果没有被 supervisor exit 0 改成精度通过，哨兵确认未导入 dolfinx、basix、petsc4py、slepc4py 或 mpi4py。上述测试结果不是正式 PDE 证据。

第一次本地 ABI 状态打印片段因没有绑定 petsc4py 模块名而触发 Python NameError；立即用 fail-fast 的更正片段重跑并通过。这是显示片段自身的错误，不是 ABI 或项目运行失败，也没有启动 PDE。Ruff 在资格化环境中不可用，因此本轮未运行，亦未安装依赖。
