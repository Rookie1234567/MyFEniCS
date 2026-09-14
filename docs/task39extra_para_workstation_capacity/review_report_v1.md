# Review V1：5 nm 结果验收与用户指定的 2 nm 两网格尝试

本审查记录 2026-09-14 用户的新指令。原任务的算法、数值和物理 Gate 继续执行；以下执行顺序、材料和时间合同以本次用户指令为准。

## 1. 5 nm 已核验和已推送的结果

5 nm Si、p6/h4 的 run `20260911T065955.813489Z` 使用数值源码 `85a681b9bd61104466888546b83df87c27806169`。698 次迭代后，从原始数组独立重算的 full true residual 为 `9.986638454029182e-7`。同一保存结果经修复后的 checker 复核，`independent_output_gates_passed=true`，`gate_failures=[]`；未重跑有限元。

| 量 | 实测或独立重算结果 |
|---|---:|
| DtN 完整通道数 | 600 |
| R | 0.7331834812424759 |
| T | 0.00022243948430485038 |
| A_balance | 0.26659407927321926 |
| A_volume | 0.26659407694262094 |
| 独立体吸收能量闭合误差 | 2.33059826992843e-9 |
| p4 最终原方程相对残差最大值 | 9.989282114125241e-11 |

检查器修复 `d64398cb1fecd90867071688dca94e501235cf7a` 只处理显式 `None` 时间门限，保留有限时间门限和所有非时间 Gate；4 项定向测试通过。结果提交 `414be774d0534ace01d0d9da47707d0075a74c18` 已推送，主控通过 `git ls-remote` 独立确认远程 `refs/heads/task39extra_para_workstation_capacity` 为该完整 SHA。

资源采样曾断档约 8 小时 34 分。可观测同期整树 RSS 峰为 `50161172480 B`，观测到的本任务 swap 峰为 0；这些记录不能填补断档。保留 `NOT_CONTINUOUS_RESOURCE_PASS`、原父 wait 退出码 `UNAVAILABLE` 和原始失败 checker/launching 记录。数值和自身物理输出通过，不等于全过程资源资格或连续极限精度通过。

补齐远端可读的独立 checker、完整必要的 600 通道复振幅小证据及来源 hash 索引，并更新模型总账。大场、矩阵、因子和原始大日志继续留在 ignored artifact 目录。

## 2. 本次新增的执行合同

| 项目 | 用户确认的合同 |
|---|---|
| 材料 | Si / silicon；沿用 Si 密度 2.33 g/cm³ |
| 波长 | 2 nm |
| 光学常数 | delta=0.00119851693，beta=0.000213688647 |
| 解释 | n=0.99880148307+0.000213688647i，epsilon=n*n；来源为本轮用户输入 |
| 首次尝试 | p6/h1.5 |
| 后续尝试 | p6/h2，单独输入和结果目录；不得覆盖首次尝试 |
| 时间 | 两次均无 screen、solve、workflow 或 campaign 时间上限 |
| 迭代 | zero start、restart32、max2048；128 步 screen 及原进展判据保留 |
| 方法 | 原 V5 BAL_H、A6/H6 原路径、准确全局 p4 LU，无新算法或 PC |
| 运行位置 | 本 worktree、本分支；MPI1、线程1、CPU23；不修改邻任务文件或进程 |

用户直接指定 2 nm，覆盖旧任务的 S3 先决顺序；5 nm 的监督缺口和 R2 的历史负结果不追溯改判。0.7/1/3 nm 的材料数据不构成本轮运行请求，也不新增波长扫描或 h1 网格。

## 3. 容量与正式启动审核

用户已授权提高本任务内存阈值。按当前宿主和实际 cgroup 的可用量确定生效 cap，仍遵守原任务的 hard ceiling、planning ceiling、系统 reserve 和零新增换页合同；不能只修改 `.dat` 中的显示值。若严格 node1 绑定导致旧 cap 过低，应先明确仅作用于本任务新进程的 NUMA 分配方案及真实可用量，审核后接线，不迁移邻任务的页或关闭系统 swap。

本次 2 nm 准备时，严格 node1 的 MemFree 约为 612.56 GiB，显著低于整机可用量。为落实用户提高阈值和跨节点使用内存的授权，批准两份新 2 nm 输入显式使用 `preferred_node1`：worker 仍在 CPU23，`numactl --preferred=1` 优先从 node1 分配，允许不足时从其他获准节点分配。这只影响本任务新进程，不迁移现有任务的页。复用全局 `memory_envelope()`、系统 reserve 和同一资源 watchdog，实际 cap 在启动时以 bytes 冻结；不得继承旧 strict-node1 cap。保持旧输入的 `membind_node1` 行为。该接线仅需现有配置枚举、命令前缀、隔离记录和对应小测试，不新增内存管理框架。P0/P2 仍须分别通过自身容量门限，允许跨节点不构成 numeric 自动放行。

先核实 h1.5 的实际轴网格、FE 行数、通道和稀疏索引容量，再决定后续装配。宽松 NNZ 上界越过 int32 不能单独证明失败；如以结构下界判定，需要给出与当前 FE、MPC、矩阵构造和 PETSc ABI 相符的验证。不得为确认溢出而先分配明知越界的巨型矩阵。

用户于 2026-09-14 07:31（北京时间）在执行专用任务中进一步明确：“那你用int64啊，还是先算h1.5的”。这覆盖旧任务只允许复用已有 int64 栈的限制。先检查可复用依赖；若缺少匹配栈，允许在本任务独立目录准备 complex128/int64 环境，使 PETSc/petsc4py、DOLFINx/MPC、MPI、MUMPS 等保持兼容。不得替换现有已资格化 int32 环境或邻项目依赖；不得仅修改 NumPy dtype、截断索引或混用 ABI。

新环境先完成轻量 ABI、相关组件和原数值合同资格检查，记录完整版本、构建选项、导入路径与源码身份，再按 P0→P1→P2→P3→P4 推进 h1.5。只做必要环境和索引兼容工作，不开发新求解器；需要用户凭据时遵守根 AGENTS 的密钥规则。h2 保持后续单独尝试，两个网格各自记录阶段和证据，一张网格的结果不能冒充另一张。

正式运行必须绑定 clean source SHA、输入和物理身份，并从启动起具有持续资源监督。复用现有 supervisor，将其生命周期与当前对话工具调用分开；先用有界、无 PDE 的父子进程检查验证独立存活、采样和收尾。不得在已经发生监督断档后补称全过程通过。

主控审阅最小代码 diff、相关测试、P0 和资源准入后放行正式启动。明确迁移错误按原任务最小修复，不扩大到防御框架或求解器开发；没有 master merge approval。

## 4. 64 位接线的阶段审查

已审 `fullspace_v17_p3_oracle.py` 的库加载及整数宽度改动：从当前进程 maps 取得唯一实际 PETSc 库，`MatMumps*` 的 PetscInt 参数和整数输出缓冲按运行时 32/64 位匹配，C 错误码和枚举仍为 `c_int`。该改动修复接口兼容，不改变 A/b、PC 或数值门限。现有两项真实 MUMPS 小矩阵测试在新 int64 与原 int32 环境各通过一次；原环境仍为 complex128/int32。

新栈为 PETSc/petsc4py 3.19.6、DOLFINx 0.10.0、MPC 0.10.1，MUMPS 实际版本 5.5.1，与旧栈的 5.6.1 分开记录。PETSc 3.19 的 MUMPS 接口采用行列编号 32 位、NNZ 计数 64 位的组合，本例行数在 32 位范围内；不要求将 MUMPS 全部整数重编为 64 位。构建中的错误系统库链接已弃用并保留记录。实际 p4/MPC 资格、完整导入链、输入新 hash、P0、有效内存 cap 和独立监督生命周期仍须在正式启动前完成，不把小矩阵通过写成整张 h1.5 网格已通过。

首个准备包的 `2.482534153247273e-16` 残差来自手工 4×4 AIJ，与另外创建的 p4 空间及 MPC finalize 分开记录。后续已补齐实际装配链：8 个 hexa、N1curl p4、1944 行，空 MPC 为 700896 NNZ，非空复约束为 701496 NNZ；两者 CSR/PetscInt 均为 int64，MUMPS 原矩阵相对残差分别约 `3.2794e-11`、`2.9041e-11`。主控已读取探针源码，接受该组件资格；不把此小矩阵当作整张 h1.5 的数值证据。

独立监督补证也已完成。最终临时 launcher 使用日志重定向、`start_new_session=True`、`stdin=DEVNULL`；启动调用返回后，监督父 PID 1488472/start_ticks 145656569 仍以 PPID1、CPU9 存活，后续调用记录样本从 25 增至 29，最终 31 样本、自然 COMPLETED、exit0、子进程清场、swap0。另首轮样本也持续至启动工具返回之后。这两项缺口关闭，不再扩大见证。批准已审准备改动完成相关检查后 clean 提交并开展 P0；正式 P1 装配仍待实际 P0 结构、通道与容量账审核。

新 P0 不得沿用旧 5 nm 的 `volume upper=340954696` 作为严格上界：实际 volume NNZ 为 `342181856`，已构成反例。MPC `create_sparsity_pattern` 保留标准结构并追加 master 行列，按真实单元支持集合计数才能覆盖这部分。修正预测口径，不追溯否定 5 nm 的实测结果；宽松上界超过 cap 也不能单独判真实容量失败。

P0 初次实际网格计数得到 54332 cells、p4 10604228 rows、p6 35594790 rows；这些属于准备阶段计数。其首次 `expanded_cells=0` 和相应容量数值不可用：脚本误以 slave 列表序号索引按本地 DOF 编号组织的 master offsets，并混用了 local/global 标号。已要求仅修正统计脚本，按每 cell 的本地 DOF 与 `mpc.masters.links(slave)` 的并集重算。此问题不在 FEM 装配实现中，不改变数学或正式源，也不构成容量失败。

修正后的实际 p4 计数已核验：4700 个单元追加 master 支持，最大单元支持 376，cell-to-slave 与逐 DOF 核对不一致数为 0。`sum(|support|²)=5012622944` 可作体矩阵结构的保守上界，对应单份 int64/complex128 CSR 载荷 `120387784488 B`。该数不包含端口增广、副本、因子或求解对象，不能称 RSS 上界或完整 P0 放行；不再重复 FE/MPC 计数。

## 5. h1.5 P0 装配计划审查

2 nm 现有动态 inventory 为 3904 modes（3902 propagating），mode hash `4b62741e84970cc5312c88039244ad5ba30065ea92dcf72a949773fef8de6364`。每 z 端口 578 个边界 cell，p4 单元支持最大 376，因此每 mode 的单侧 functional 支持不超过 217328；线性增广的 port-added NNZ 上界为 1696900928，总增广上界 6709523872。计数未生成全局 DtN 或 p4 AIJ。此前开始全部 carrier 积分的开发探针已按精确 PID/start_ticks 停止、清场，不作为正式运行或容量通过证据。

既有 p4 载荷公式包含 volume+augmentation、int64/complex128、COO 转换及 p4 向量，得 498938445392 B。补计实际 p6 存储长度的 65 个 FGMRES 基向量、BAL_H coupling 等工作向量、部分装配元数据与两级 trace 的保守支持及构造期副本，准备合计为 1256737280880 B。另预留 128 GiB 工程余量，覆盖 mesh/MPC/owner-transfer Python 容器、reference tables、JIT/allocator 与未逐个枚举的临时对象，总装配规划为 1394176234352 B，低于本次规划线 1622325310464 B，剩余 228149076112 B。工程余量是规划分配，不是实测或数学意义上的 RSS 严格上界；本计划不含 LU，不能直接批准 numeric。

接受上述 P0 规划进入正式 P1 的方向。执行专用完成对应记录及已要求的 focused 检查、clean 提交后，主控核对该 source SHA、输入 hash 和 detached 启动/监督命令再放行。保留所有实测资源 Gate，P2 必须用真实 symbolic 估计与同一时刻 RSS 单独核验 numeric/outer/recovery 预算。无需继续扩大预检、添加新算法或新资源框架。

主控已读取临时 launcher `/tmp/task39extra-2nm-h1p5-launch.py`：CPU9 执行 task-local activation 后单次 `run_case.py`，Popen 使用 `stdin=DEVNULL`、独立日志、`start_new_session=True`；worker 的 CPU23/preferred-node1 由已审输入和原 launcher 生成，无嵌套 MPI 或第二套 watchdog。批准已审 WIP 完成限定检查、clean 提交并记录完整 SHA/hash 后由执行专用直接启动 h1.5；该条件满足后不再增加许可环节。P2 使用既有 symbolic/reference_budget 的实际数值自动判准入并提交阶段证据，不引入人工暂停，也不预先宣称 LU 通过。启动后核验实际 parent/worker 身份、独立存活、采样连续性和 fresh cap，执行专用继续监督并在异常、阶段实质变化或终态通知主控。

## 6. h1.5 首次正式 setup 失败的审查方向

运行 `20260914T013346.036155Z`（clean source `296afa6a6c231b6ab067ad928c9f827ee72f5e98`）在约 5175.9 s 后以 `WORKER_FAILED` / exit4 结束，原日志为 `only affine geometry is qualified`。末阶段为 H6 setup，未进入 P2、numeric 或 outer，无 R/T/A。15434 个资源样本、同期整树 RSS 峰 `5115244544 B`、job swap 0、global pswp 增量 0，且 descendants 已清场；这不是已证实的内存边界或收敛失败。

异常文本不能证明当前几何非仿射。先核对 boundary-fitted 轴网格各 cell 的实际 Q1 坐标和 Jacobian，并区分真实几何变化与绝对坐标参与导数求和的浮点消去误差。允许执行专用做无完整 H6/AIJ/LU/outer 的轻量几何调查。候选最小修复是用单元局部坐标计算 Jacobian，利用形函数导数和为零的恒等式改善平移不变性；须先证明根因，不放大现有 128·eps 判据，不改 mesh/material/quadrature、不引入非仿射新方法。

具体小 diff 必须有当前 h1.5 实际 cell 的前后误差与阈值证据、平移不变性、真实非仿射负例，以及对原 FFCx 算子/对角项的定向回归。共享根因的相邻调用点可同批最小修复；不因无关文档重跑完整旧成功案例。保留首次负结果、计入迁移 retry 账，修复审阅与 clean 提交后才能使用原输入开始新的正式 run，不覆盖本次目录。

首次只读探针的 1156 个触发 cell 来自三个人工选点，部分位于 Basix 参考单元之外；该证据保留为消去误差的诊断示例，不能称正式积分规则的触发统计。正式重试前用原 positive diagonal / action 的 FFCx 积分规则补核实际网格，无需构建完整 H6。原日志未捕获 traceback，两个候选调用点使用同一异常文字，不能仅凭文字唯一定位到 partial assembly。

另核实本次资源 watchdog 一直独立采样，但执行专用对话结束后没有独立的终态通知动作，实际终态直到用户再次查询才上报。前次主控把资源监督和自动通知一并验收，证据不足。重试前补最小只读独立 observer：固定本 run 和 PID/start_ticks，低频、增量读取已有记录，重大阶段、采样失鲜或终态才通知并保存回执；不发送 FEM 信号、不重启、不修改资源 Gate。通知接口与无 PDE 事件自测须先审阅，不扩大为新 watchdog 框架。

后续正式规则补证已核对：从同 ABI 的单单元 p6 空间及 DG0 系数取得原 form/action 的 FFCx degree15、512 点规则，两者点/权重 hash 相同。在实际 54332 个 Q1 cell 上使用默认求和顺序，绝对坐标触发数为 25432，局部坐标触发数为 0；最坏候选用生产逐 cell 表达式复核，误差 `9.501427422620168e-14` 超过原阈值 `4.263256414560682e-14`。局部坐标最大差 `1.5543122344752192e-15`，保持正 determinant。此前三人工点、字面系数/优化求和的诊断统计与此补证分开。接受三处仅增加 `x = x - x[0]` 的改动：数学映射不变，不放宽 128·eps、不支持新的非仿射几何。

通知代码审阅已修正实际 `result.data[].id/status` 路由、失败保留 pending/成功后去重、终态回执后退出、真实资源 timestamp 与实际阶段名。无 PDE 自测覆盖活动 turn、失败重试、失鲜和终态；主控已实际收到标为 SELFTEST 的通知。正式启动后仍需确认独立 observer PID/日志在启动调用结束后继续存在，不能把一次性接口回执当作持续运行证明。

最终 357/362 定向检查为 **16 passed、1 skipped，94.21 s**；跳过项是明确的 MPI2 专项，本次合同为 MPI1。p3 装配 MPC 对角参考相对差 `9.14128559598911e-16`，p6 原 FFCx action 与正项/分量/packed 对照均保持原 `1e-11` 容差通过，平移仿射与真实非仿射负例通过。初次裸 `pytest` 命中 `/usr/bin/pytest` 的系统解释器，导致 13 项 CFFI 缺 setuptools；改为已激活 `.venv` 的 `python3 -m pytest` 后通过，未安装包或重建运行环境，保留该测试调用负记录。

批准已审三行修复、现有测试增补、最小通知脚本及本轮失败/验证/回复记录完成 clean 提交并正常推送本执行分支后，直接用同一 h1.5 输入启动一个新的正式 run。无需再次请求许可、重跑 P0 FE 计数或旧完整成功案例。启动仍使用已审 detached launcher、CPU23/MPI1、CPU9 监督、preferred_node1、实际 fresh cap 与原数值/物理/P2 Gate，无时间上限；保留首次失败目录并计入一次该根因迁移重试。只读 observer 同步以 CPU9、独立 session、固定新 run 与 PID/start_ticks 启动，通知本主控线程；启动后核验 watchdog 持续采样及 observer 独立存活，再按实质阶段或异常通知。
