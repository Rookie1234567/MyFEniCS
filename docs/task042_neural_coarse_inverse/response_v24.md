# V24最新进度：按Review V21新增§10修复后仅执行首块

已核对主机无V24数值actor并安全同步至0e0a9f49ae0310cd9b219d39f059f97f8a86bfa3。两个控制流缺口已最小修复，26项focused回归通过。失败SETUP仅凭true标志不再准入；公共证据封存后独立复算，只有粗层失败时L8仍可行。四路各首4周期，不再自动LW8；第五reader只供必要恢复。原窗口不刷新，无重置卡，无dot/master操作。以下阶段记录为早先真实历史；正式数值即将按Gate推进，其source由实际run绑定。

# V24续行记录：账户接口及执行审批已恢复

2026-10-02T14:07Z之后实际只读主机核验通过：新候选核CPU15、PSI full avg10=0、原系统/邻增长余量和磁盘Gate通过。周额度用尽时允许使用现有余额；明确禁止使用重置卡，未调用重置功能。以下认证阻塞是早先真实历史，保留原始失败；本批现继续原Review V21队列，原heavy-stop15:34:23.502588Z、deadline16:04:23.502588Z保持。当前真实数值仍未运行，后续来源与计数由正式run绑定。

# Response V24：八块局部解与粗层配对已实现，正式计算受执行服务阻塞

按 Review V21 完成新数值核、六个 one-run 入口、定向回归和入口验证。**真实 SETUP、LW、LCW、LZ、LCZ、VERIFY 均未运行**，没有新的场、通过点或数值负结果。本批停止原因是执行服务认证不可用；不能判断固定八块方法有效或无效，也没有完整有限元、神经增量、目标规模或 merge 资格。

本次拟改变每次残差修正：先把全部独立边／面未知量按八个固定几何区域分组，在每组内部解完整局部耦合；再比较是否追加原有低阶空间中的最小残差粗校正。外层仍保留跨块耦合、全部有限元未知量及 40 个端口。代价是八块局部完整 LU、每次八个三角求解，以及组合路线的原算子作用与大型薄矩阵读取。当前只有实现和小模型证据，尚无这一方法的真实 micro 数值结论。

## 实際执行、未运行与停止原因

| 阶段 | 实际证据 | 本轮分类 |
|---|---|---|
| 身份／合同 | canonical linked worktree；同分支安全 fetch/ff 至 Review `c3370061c6693eab70e20c34965ec7d640b978bd` | 完成 |
| C1/C2 实现 | 数值核位于 `src/solvers/local_block_coarse.py`、`local_block_study.py`；薄 runner、角色 reader、监督与六 dat 已接线 | 已提交实现 |
| 小型回归 | 最终 28 passed、2 个已消费历史接线用例 deselected；包含四条新实际 dat→stage→右 PC→GMRES→close→保存→独立审核 fixture | 小模型通过，非正式 FE 资格 |
| 新入口验证 | 六项 `scripts/run_case.py --validate-only` 均 valid；source clean | 完成 |
| 首次 SETUP 准入 | 无空闲物理核，数值 actor 未创建；外层队列退出 0 不能解释为数值成功 | ADMISSION_BLOCKED |
| 有界资源复核 | 12:30:47.492979Z 主机只读检查发现 CPU27 可用；这不是永久保留核 | 当时准入检查通过 |
| 受监督队列重试 | 自动审批服务令牌刷新失败，403 区域不支持；工具明确表示命令未执行 | EXECUTION_BLOCKED |
| 真实 SETUP／四路线／VERIFY | 没有数值 actor、局部因子、D_L、周期或新场；未读取 REF7 | NOT_RUN |
| 文档提交／push | 服务故障后的记录仅在本地保存；未绕过审批写 canonical Git 或推送 | 待服务恢复 |

自动审批错误原文为 `Failed to refresh token: 403 Forbidden: Country, region, or territory not supported`；它是审批服务无法完成审核，不是认定 Task042 操作不安全。随后网页工具独立返回 `401 token_expired` 并提示重新登录。用户对本批的授权仍有效。恢复需要客户端／账户侧重新认证；不改工作站网络、共享配置或权限策略绕过检查。

原始 journal 中首次准入退出的 `dependent_not_run: local block numerical Gate` 是队列的泛化分支描述。实际 worker traceback 是无空闲物理核，SETUP 数值 Gate 根本未执行。原始记录保留；[独立分流记录](outcomes/records/qualification_and_dispatch_v24.json)明确区分准入、审批故障与数学失败。

## 实现身份与固定模型

当前实现 HEAD `370b7bbe2455448b320ca4272eb62950e4715ecc`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。唯一分支 `task42_neural_coarse_inverse`，upstream `origin/task42_neural_coarse_inverse`；本地 tracking 比较 ahead 1／behind 0，仅反映最后成功 fetch。没有正式运行源码 SHA；上述 HEAD 是已提交实现身份，不能冒充数值 run source。

工作树 `/home/fenics/Projects/NN-Lab`，common Git `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，origin `git@github-myfenics:Rookie1234567/MyFEniCS.git`。没有 reset、其他 worktree 操作、origin／全局配置修改或历史重写。交付文档若尚未提交，工作树修改状态单独列于最终 receipt，不声称 clean／已推送。

原 0.7nm／384hex／p3／h0.175nm／q15、三维缺口、入射、背景及双 Floquet/DtN 保持；trace18144、内部13824、slave2082、top20+bottom20、完整 z18184。材料继续离线读取 canonical `input/materials/si_optical_constants_v1.json`，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`；source `0.699999988` 仅明确 alias 至 nominal `0.7`。Si n=0.999885140474+4.32477054e-6i、epsilon=n*n、mu=1；未重新索要或替换用户数值。

物理／材料／模式／action／map／T/U/R／父状态身份见[来源记录](outcomes/records/source_inventory_v24.json)。本轮的上游 hash 是冻结读取合同，不将尚未执行的真实成员核验写成通过。新 SETUP 不读取暖向量；WARM 只解压 trace/port/z/residual；ZERO 不读取暖解、神经数据或循环方向；VERIFY 只有队列冻结后才允许读 REF7。目前这些大型状态均未由 V24 数值 actor 解压。

## 数学与容量边界

```math
A=\bar S,\qquad A_b=E_bAE_b^H=K_b-C_bH_{hat}^{-1}F_b,
\qquad Lr=\sum_b E_b^H A_b^{-1}E_b r.
```

每块累加原全部 cell Schur／Floquet／共享贡献，不按 owner 单元截断，不分别凝聚 curl/mass，也不假定 F=Cᴴ。局部规格固定 complex128、LAPACK 部分选主元完整 LU、每 apply 固定一次 lu_solve，无 shift/drop/ILU／精化。外层及审核保持独立旧 ActionPacket；class64 数值 Gate 留待真实 SETUP。

```math
Jr=TR^{-1}U^Hr,\qquad LCr=Lr+J(r-ALr),
\qquad D_L=U^H\operatorname{Dop}T.
```

U 是原方程作用像，T 是 trace 空间；Hhat 不是 Hp。D_L 通过最多32列缓冲构造，固定一次小 SVD、固定 1e-12 相对安全阈值。二维反例回归确认：原 A 和局部块可逆仍可能得到奇异 LC。旧 UᴴT 检查不能替代新 D_L。whole-overlap 数值分辨率检查另列，未修改阈值、删秩或构造伪逆。

| derived 规划；不是 RSS | 值 | 合同限额 |
|---|---:|---:|
| 八块行数 | 2913/2676/2289/2076/2439/2220/1863/1668 | 每块≤4096 |
| 总行／完整实体 | 18144／2448 | 全行各一次、同实体矩不拆分 |
| 一套 A_b | 677215296 B | — |
| 一套 LU | 677215296 B | — |
| A_b+LU | 1354430592 B | ≤2 GiB |
| pivot 上界 | 145152 B | 另计 |
| 新工作区保守规划 | 746594352 B | 包含临时副本、粗检查及 Krylov |
| 全部同时规划 | 5709615024 B | ≤8 GiB |

容量算术通过；真实局部 rcond、主块原作用、重载 solve、组合恒等式和 D_L 安全性仍 NOT_RUN。实际新局部矩阵／因子／新 D_L 数量均为0；不得登记它们已存在。部署若执行，应明确 `LOCAL8_DENSE_LU_PRESENT`，组合另有 `GLOBAL_TALL_IMAGE_QR_PRESENT`。没有构造 global fine K/A、global p4 LU、私有 audit CSR、隐藏 fallback 或新 W/QR；这不构成目标规模 factor-free／可扩展资格。

## 有界修复、成本和隔离

两个预正式根因保留失败证据。R01：SciPy1.11.4 f2py GETRS 临时原地调整 pivots，传入只读 mmap 导致 SIGSEGV；改为每 reader 私有的小整数 pivot 工作区，矩阵和 LU 文件仍只读，不修改安装栈。R02：二维奇异反例的 1×1 D_L 在舍入后可能得到相对奇异值比1；新增独立整块分辨率检查，仍保留原 1e-12 比值门限。修复次数2/4；修复编辑耗时未单独实测，以600+180秒保守上界记录，包含在总 elapsed，不能再相加冒充成本。

六段已监督辅助／失败准入 wall 合计43.5801978582秒；其中最终 focused 9.7799590731秒、six-dat validate 3.9001575120秒、首次准入队列3.7742129019秒。正式 FE／setup／求解／VERIFY wall=0。历史 formal 研发下界仍75124.91759302444秒；旧辅助和每个暖解的完整上游拆账仍 unknown，不补造精确累计。

六段顺序监督的最大采样同时树峰为156880896 B；这是已监督的小测试／准入区间峰，**不是完整实现和编辑期间的 RSS 峰，也不是八块部署内存**。自身 swap／VRAM／OOC 均0；失败后所有被监督后代已清理。测试按当时空闲核分别选0、44、28、39、40，未把旧核号固定为正式运行核。

保留受控共享工作站准入：MPI1、数学／Torch1、DataLoader0、GPU不用；独立环境、TMP/JIT/bytecode/model cache 和自有锁。既有 FE ABI preflight complex128/int64/MPI1 通过，无 JIT。原生库前缀只读复用；没有 ABI／BLAS／CUDA 重装或邻任务修改。正式监督配置保持0.5秒整树 warn12GiB/hard16GiB、ownswap0、原 PSI 和余量保护；无 delegated cgroup，因此不声称 kernel 连续硬限制生效。尚未启动数值负载，不据此声称数学意义上的零干扰或无争用加速。

start=2026-10-02T12:04:23.502588Z，monotonic=867658.363474344，boot_id=fd8f4b00-1e17-46af-a6fa-da3a32dbeba3；heavy-stop=15:34:23.502588Z，deadline=16:04:23.502588Z。实现、修复、审批等待及交付均在原窗口内计时；恢复服务不得刷新窗口。真实最终交付时钟见[deadline](outcomes/records/deadline_repair_v24.json)和本地 receipt。

## 资格与下一步

LW／LCW／LZ／LCZ 接受周期均0，FIRST_EQUATION_PASS 不存在；Schur/native/port/恢复、E/H/curl、40复通道、R/T/A/A_volume、逐通道功率及能量均没有新测量。空的场／功率 CSV 是未运行的显式记录，不是零场或通过。仅引用已有 V21-C-FINAL 的历史 Schur2.5281170328e-6、native9.80413346383e-7、单通道功率差1.71964465112e-6说明原暖点仍未合格，未把它当成本轮新审核结果。

当前无法区分局部收益与粗层额外收益，也没有 NN 训练增量。唯一下一建议是：客户端恢复认证后，在**同一不可刷新窗口仍有效**且 fresh 资源准入通过时，继续这六个已验证入口的原授权队列。若窗口已经耗尽，保存这些未运行项，由下一 review 授权新的时间窗口；不扩大块数、overlap、shift、模型或精度范围。

[详细结果](outcomes/local_block_coarse_pair_v24.md)、[测试](outcomes/records/test_results_v24.json)、[费用](outcomes/records/resource_costs_v24.json)、[分流](outcomes/records/qualification_and_dispatch_v24.json)、[审批故障](outcomes/records/approval_block_v24.json)。旧 task/review/response/raw 与负结果保持；GitHub 精确页面视觉 **NOT_VERIFIED**，本地结构检查不代替视觉。只允许推送本执行分支，不 merge。
