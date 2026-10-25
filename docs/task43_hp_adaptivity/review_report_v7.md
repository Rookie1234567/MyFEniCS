# Task43 正式审阅 V7：静态取证有实质进展，批准一次有前置门的支持确认

审阅日期：2026-10-25。本文是后续执行权威；审阅本身没有运行支持 driver、原生导入、ABI、pytest、collect-only、网格、PDE 或旧场处理，也没有合并分支。本文只新增本报告，不修改既有 review、合同、失败记录、测试代码或数值源码。

## 0. 明确结论

**接受本轮 R1–R4 的有限静态工程交付，带有下述证据和文字限定；不将其判为 CPU1、ABI、测试或科学资格通过。明确批准下一轮一次且仅一次新的 D3 非 PDE 支持诊断，并条件性批准同次运行中的固定 20 项测试。** 执行必须先完成第 9 节的有限静态准备和附录 A 的两处审计收紧；原样复制 D2 probe 不在这份运行许可内。准备合格后可按本报告执行，不必再为相同范围申请一轮许可；准备不合格则停止，不自行改参数或换目录。

这次放行的依据是一个可以被否证的具体问题：在固定单 rank 环境中，局部选择 OB1 是否消除旧 CM 装载链上观察到的两类 PSM 亲和性设置，并让既定文件一致性测试到达执行阶段。本文补查了 OpenMPI 4.1.6 的加载源码，确认组件名单过滤先于相关动态加载；同时指出其他 provider 路径仍可能触发加载。因此支持做一次确认，尚不支持宣布修复成功。

| 裁决对象 | V7 正式结论 |
|---|---|
| 有限静态工程整改 | **接受，带限定** ：事件、脚本、机械差异、身份清单及费用算术可审查；两处进程/时间措辞须按本文收窄 |
| 当前资源资格 | **NOT_PASSED** ：D1/D2 的 CPU1 负结果原样保留；新诊断尚未运行 |
| 当前测试与 ABI | 20 项 **NOT_RUN** ；历史 D1/D2 的完整有限 MPI/PETSc preflight **NOT_REACHED** ；没有全仓或 CI 通过 |
| 下一轮静态工作 | **批准** ：仅第 9.2 节所列证据补采、审计修订、字节冻结与当前文档订正 |
| 下一轮支持运行 | **批准最多 1 次** ：唯一 D3 命令、目录、脚本身份、100 秒停止门及 120 秒含清理验收上限；失败不重试 |
| 新正式 PDE / 封存槽 | **不批准** ：总额仍 5/6、A1 2/2、A2 3/3，最后 1 槽封存；全部正式与下游工作继续锁定 |
| 合并 | **没有本次实际 merge approval** ：研究档案可保留，test-only 待动态验证，研究入口、共享启动、数值核心及整分支均未取得新的生产合并资格 |

## 1. 固定身份、实际差异与审阅方法

| 身份 | 核对结果 |
|---|---|
| 仓库 / 唯一执行分支 | `Rookie1234567/MyFEniCS` / `task43_hp_adaptivity` |
| 固定被审提交 | `fb9244d1ea3e688c66b1fc42e9cc575952c5080f` |
| 被审 tree | `f438fdb7b4aebfe3bb8136099cfbc9b8e6a21f1b` |
| 直接父提交 / 本轮原执行权威 | `9e11b6e0804c2fd51e99353ec306483af0621580`，正式 V6 review |
| 上轮被审代码 | `cab17f542bfffeb6598eedfed3194d07ea047630` |
| 长期基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4`；固定 HEAD 相对它 ahead 68、behind 0，merge-base 为该基线 |
| 远端 | 审阅开始时远端分支准确指向固定被审提交；提交本报告前再次核对并以预期旧 SHA 保护 ref 更新，不覆盖其他工作 |
| 工作站状态 | “干净、与 origin 0/0”是交付方报告；本审阅直接核了远端 ref/tree/diff，没有登录工作站亲证其当前 worktree 状态 |

直接比较 V6 review 到固定 HEAD：只有 1 个提交、15 个路径，全部位于 `docs/`，增加 11,101 行、删除 21 行。具体为两份新 JSON、四份历史 shell/probe、两份 D1→D2 机械 diff、一份未执行 D2→D3 patch、response_v7，以及 README、summary、manifest、registry、progress 的当前状态更新。新增 `.py/.sh` 是历史文本归档；`src/`、`benchmarks/`、共享 activation、测试及冻结合同没有变化。既有正式 review、历史 response、READY 和失败记录未出现在本轮 diff 中。[固定差异][DIFF7]

本审阅读取三层 AGENTS、仓库工作原则、任务书、V6 review 及本轮指定材料，复查相关测试、activation、watchdog；对当前状态文档审查实际补丁及历史上下文。审阅缓存的 208 份文件均与固定 tree 的 Git blob 身份吻合，这个数量是阅读缓存的字节核对范围，不是项目测试数量。另行核验 204 条事件字段、历史引用、完整保存脚本、机械 patch、计时算术与 OpenMPI 官方源码。未导入被审项目，没有执行 fixture 或提出中的 runner。

下面的行号均指固定 `fb9244d…` 原文件；涉及上游时另给固定源码提交。 **轻量记录内部一致、工作站原件真实存在、运行时因果成立是三个不同结论。** 本报告逐项区分，不因执行者模型、主控声明或 PASS 标签改变证据等级。

## 2. R1–R4 与 V6-01–V6-04 逐项验收

| 项目 | 裁决 | 直接核到的证据 | 尚存边界 / 最小行动 |
|---|---|---|---|
| R1 全部旧 setter 分类；V6-01 监督责任 | **接受，限定于 Git 事件表及交叉绑定** | 204 个 ID 唯一；按字段重建的 204 条 syscall 行 SHA 均匹配；12 份 trace 引用与 V6 closeout 一致；D1/D2 分类和 CPU mask 小计正确。response_v7:9、24–25、68 保留 D2 前漏分类责任 | 没有亲读 12 份 raw trace，不能独立证明抽取完备性。V7-03 收窄 orted/PMIx 归属。D2 仍是未满足原条件的失败确认，不追认为合格放行 |
| R2 完整脚本、源码身份及装载证据；V6-02/03 | **接受静态补证；运行资格未通过，旧 false 的原生成原因仍未知** | 四份完整 shell/probe、两份机械 diff 可重算；D1/D2 的 8 项规范化字典分别与固定 Git 字节相符；当前 ELF 表明确非历史 mapped-file 证明 | 不把路径规范化后相等写成已找到原生成器 bug。两项 MTL 插件及实际 MCA 输入仍需有限静态补采；附录 A 修未来审计门，不改旧原件 |
| R3 单一未执行方案；V6-02 | **接受为候选提案** | 完整 patch 可机械施加，得到预期 shell hash；路径、保留的环境键和 20 项目标自洽。官方源码支持 CM 动态加载前筛选这一假设 | 候选没有动态验证。下一轮仅按本报告明确新增的 1 次额度执行，并使用审计收紧后的新 probe；不把候选文本视作旧授权 |
| R4 当前文档；V6-04 | **接受，少量措辞限定** | 当前 README/summary/registry/progress 标明 V7 静态、旧阶段历史；区分完整 ignored trace 与 Git 摘录；导入返回、ABI 未到达、20 项未运行均明确 | V7-03 修调用顺序文字；V7-04 区分停止阈值与 whole-wall；manifest:26 的“V5 当前整改范围”宜改为历史段标题。其正文已经限制为 V5，未发现由此实际追加资格 |

对应 V6 问题的关闭方式：V6-01 的责任说明和遗漏清单已经闭合，历史违规放行本身不可撤销；V6-02 的“脚本不可直接审查”缺口已关闭，CPU1 资格仍开放；V6-03 的数据一致性问题已有解释，但生成器分支无法追证；V6-04 的主要导航/完整性措辞已修正，残余具体文字按第 3 节处理。不能把这张表压缩成“V6 全部门通过”。[执行回应][RESPONSE7] · [V6 权威第 9 节][V6]

## 3. 问题清单：严重性、影响和可执行验收标准

严重性含义：P2 是本次下一步放行或资格判断前必须处理的局部问题；P3 是不会推翻主要统计、但必须准确表述的证据问题。没有发现本轮越权新增 PDE 或改写历史失败的 P1 问题。

### V7-01 · P2：原 probe 会静默跳过部分 setter 记录，不能独自证明完整覆盖

**位置：** 保存的 `d2/probe_import_affinity.py:58–70`，尤其 62–68 行；阶段/收尾边界在 89–115、319–356 行；`benchmarks/subreaper_watchdog.py:556–567、652–667`。[D2 probe][PROBE2] · [watchdog][WATCHDOG]

原解析器要求同一行既有 `sched_setaffinity(` 又有返回 0，否则直接 continue。分行 unfinished/resumed、截断或不认识的格式可能既不进入成功集合，也不进入 unknown；mask 再用数字抽取，不能证明整个 mask 语法被识别。当前 Git 中的 204 条事件都是完整单行，足以判断这些已列事件的偏离； **没有证据证明旧 raw 确有漏项，本报告不据此否定 204 的历史统计。** 风险在于继续使用该门去证明新运行“没有任何偏离”。

最小整改只作用于未来 D3 的隔离 probe：所有非栈帧 setter token 必须被成功完整解析或进入明确否决集合；整数 mask 必须完整匹配。附录 A 给出唯一文本修订。对失败调用采用保守停止，不将失败调用误计为成功改绑。不能改历史 D2 probe 或旧事件表来伪造当时已有此门。

**验收：** 新 probe 的 hash 与附录相符；只用 stdlib 和合成字符串进行一次有限 sanity，覆盖 `[1]`、非 `[1]`、失败调用、unfinished、resumed、ellipsis/未知 mask 和栈帧。未知记录不能获得继续权限。运行完成后必须再检查所有最终 raw trace，含 Python/MPI 退出尾段；任何未分类 token、缺文件或成功非 CPU1 调用均否决最终资源资格。

即使收紧解析器，own-trace getter 计数只是局部同步，不是全部后代日志屏障；pytest 的检查在批次前后，watchdog 仅采样 affinity，没有自动 CPU1 终止规则；最终 snapshot 又早于解释器退出。保留现有小探针结构可以接受，前提是最终资格由完整终态复核决定，单个 `FIXTURE_TESTS_PASSED` 不授予无条件 PASS。发现运行期偏离时，主控须核 watchdog 身份后立即停止，不能等剩余时间耗尽。

### V7-02 · P2：候选记录的是 OB1 请求，尚未绑定实际 worker 输入或全部装载因果

**位置：** `d2_to_d3_candidate.patch:58–68`；D2 probe:116–135、167–252；source/loader JSON:3–166、169–220。[候选 patch][PATCH3] · [装载审计][LOADER7]

shell 中的请求值是 `ob1`，原 probe 却只记录/检查 HWLOC，不记录/检查实际 `OMPI_MCA_pml`。候选 export 还位于 activation 之前。已读 tracked activation:46–71 没有覆盖这两个变量，但共享 venv activation 原件本审阅未访问。OpenMPI 的更高优先级 override 和长/短环境名还可能影响参数解析。[activation][ACTIVATE] · [MCA 参数来源][OMPI_VAR]

最小整改：附录 A 在新 probe 的 startup snapshot 保存实际值并要求 `ob1`；执行前只读核当前 activation、相关 MCA 环境/参数文件，保存实际文本及来源，不修改共享配置。只打印硬编码请求不能作为实际输入证据。12 项当前 ELF 表还缺 CM→MTL→PSM 中间插件的元数据；有限补采 `mca_mtl_psm.so`、`mca_mtl_psm2.so` 及相关直接依赖，按存在/不存在如实记录。不要扩展成全部 MPI 参数或 provider 扫描。

**验收：** 无相关输入漂移/未解释 override；新 probe 在首个显式 native import 前核实际 `ob1`。当前包、路径、SHA、Build-ID、NEEDED 的原始命令/stdout/退出码持久化。即便满足，也只绑定本次干预输入，不宣称已证明有效 component selection 或历史 mapped-file 身份。

### V7-03 · P3：两处调用链文字超过提交证据或混淆时间顺序

1. 事件表 **5928 行** 把 PMIx topology setup 归到 orted TID 4071475。已保存的 orted 栈在 5967–5997 行，经 `libopen-pal / opal_hwloc_base_get_topology → mca_ess_hnp → orte_daemon`；包含 `pmix_hwloc_setup_topology / PMIx_Init` 的是 **5933–5964 行的 Python 主线程 4071459** 。不能排除未提交的其他 orted 栈另含 PMIx，但这句具体归属目前无对应摘录支撑。[事件表][EVENT7]
2. source/loader JSON **185 行** 的 `mca_pml_cm.so before MPI init` 容易把 unwind 展示顺序误作发生时间。保存栈及源码支持的是 **MPI 初始化调用链内部** 发生组件加载；不是在 MPI 初始化之前，也不是完整 ABI preflight 已执行。[装载审计][LOADER7] · [MPI 初始化源码][OMPI_INIT]

**最小行动与验收：** 在下一份当前说明/勘误中分别归属两条进程栈，把第二句写为初始化链内部；若要保留更强断言，提供准确 trace/TID/原行号/hash 的对应摘录。保留 V7 原记录和历史 review 的原字节，以本报告及新勘误建立前后关系。此项不改变 200/4 统计、D2 监督责任或 CPU1 失败。

### V7-04 · P3：100 秒是 watchdog 工作停止阈值，不是包含清理的 whole-wall 保证

**位置：** response_v7:54 与 D2 shell:81–85。[执行回应][RESPONSE7] · [D2 shell][SHELL2]

实际参数是 `--wall-seconds 100`，watchdog 随后还需发信号、回收进程、等待缓存元数据及写终态。下一轮明确采用 **100 秒停止工作、whole-watchdog 含清理验收不超过 120 秒** ，一次总预算同为 120 秒；这是本报告前瞻给予的新支持预算，不是追溯延长旧尝试或给 20 秒继续测试。达到停止门后只允许清理；超出含清理验收上限必须如实失败，不补记合格。

## 4. 事件、进程角色与历史负结果的直接复核

CPU affinity 表示线程被允许运行的 CPU 集合。成功把集合设为 `[0]` 后再恢复 `[1]`，仍反证“全程只允许 CPU1”；系统调用不直接告诉我们在 CPU0 上做了多少工作。读取一次 `[1]` 的资源样本，也不能抵消两个采样点之间的成功改绑。

按 Git 内全部事件字段重新分组如下；所有事件均记录 target=0、return=0，目标 0 表示调用线程本身。首个非 libc 帧用于库级分类，不能据最近导出符号推定私有函数。

| 运行 / TID / 角色 | 首个非 libc 库 | 事件 | mask=[1] | mask≠[1] |
|---|---|---:|---:|---:|
| D1 / 4071459 / Python 主线程 | hwloc | 98 | 4 | 94 |
| D1 / 4071475 / orted，按保存进程链关联 | hwloc | 98 | 4 | 94 |
| D1 / 4071459 | libinfinipath | 2 | 1 | 1 |
| D1 / 4071459 | libpsm2 | 2 | 1 | 1 |
| **D1 合计** | 三类 | **200** | **10** | **190** |
| D2 / 4076967 / Python 主线程 | libinfinipath | 2 | 1 | 1 |
| D2 / 4076967 | libpsm2 | 2 | 1 | 1 |
| **D2 合计** | 两类 | **4** | **2** | **2** |

独立核对内容包括：204 个事件 ID 唯一；trace 内原行号唯一、时间顺序一致；trace 文件名 TID 与事件 TID 相符；由时间、目标、mask、返回值重建的 204 条 syscall 行 SHA 与保存字段全部一致；12 份 trace 的引用 hash 与不可变 V6 closeout 一致。六份代表栈中五份可与 V6 旧摘录共有前缀交叉核对，另一个主线程 hwloc 栈是本轮新增摘录。 **这些证明 Git 事件台账自洽，并不等于我已逐行读了 ignored raw 或独立证明它没有遗漏。** [事件表，事件及 6157–6272 行][EVENT7] · [V6 closeout][CLOSE6]

阶段归属 `native_import_window` 是可接受的粗粒度标签，记录已说明精确嵌套 import/syscall 边界未保存。两次在首个显式 `dolfinx` 导入返回后的 `native_import_complete` 停止；保存栈中已有 PETSc/MPI 初始化，与随后 `_native_abi_check()` 未到达并不矛盾。

| 历史支持量 | D1 | D2 | 本审阅实际证据级别 |
|---|---:|---:|---|
| worker PID / PPID / start_ticks | 4071459 / 4071446 / 284920539 | 4076967 / 4076949 / 284948743 | Git 阶段和进程摘录交叉核对 |
| 资源样本 / 成员观察数 | 16 / 51 | 13 / 40 | compact 与历史引用一致，未重读完整流 |
| worker / outer exit | 23 / 2 | 23 / 2 | 保留 WORKER_FAILED，未改名抵扣 |
| whole-watchdog / s | 10.266887816600502 | 10.469862679950893 | 历史支持费用，小计 20.736750496551394 |
| 同时进程树采样 RSS 峰 / B | 161480704 | 160063488 | 摘要记录；不是独立重算的连续峰值 |
| task VmSwap / global swap 页增量 | 0 / 0、0 | 0 / 0、0 | 两种口径分列，不能以全局零证明每个瞬间任务绝无 swap |
| 清理 | 原记录完成 | 原记录完成 | 未亲核最终完整 PID/资源流；不改变原有范围 |
| CPU1 / ABI / pytest | NOT_PASSED / NOT_REACHED / NOT_RUN | 同左 | 后验整理不提升资格 |

D1 的 `[33]`、`[30]` 记录属于小写 **t 状态的 tracing stop** ，不是 Z 缺测。D2 的离散资源样本未见偏离，仍被四条成功 setter 直接否决。D2 前漏掉的四次网络库调用在 D1 中已经存在；其责任不能转成“新问题才出现”、数值方法失败，或因未超时而被豁免。[V6 closeout，706–743 行][CLOSE6] · [response_v7:9、27、33–39][RESPONSE7]

## 5. 源码、脚本、ELF 与 415 项引用究竟证明什么

### 5.1 两版启动链及源码身份

四份保存脚本的实际字节可直接审查；重新生成的 D1→D2 shell/probe diff 与提交文本相同。D1→D2 除目录外还增加 HWLOC 输入检查，并把未到达的 collect-only 改成未到达的 20 项定向测试，response 没有隐瞒这部分变化。

| 文件，相对 `v7_affinity_driver_sources/` | 字节数 | SHA256 |
|---|---:|---|
| `d1/run_d1.sh` | 3880 | `894ba384e2d12fd61e761467d9d5aace40a0d3267e50206b46c6602952d0c3b2` |
| `d1/probe_import_affinity.py` | 13284 | `d354eeaf7e2e00af652e1b131260b678f89221f6658e617e5d10472a3c6bd2b3` |
| `d2/run_d2.sh` | 4031 | `27c72228d06cff9db2eacd0b505ec871ca8ad50dd6d5705025e4c58db93eeb9d` |
| `d2/probe_import_affinity.py` | 14462 | `0ce0fd5d7bbcd20272a7d551b414a142ffcf5f859b23636384e906d5b2c553a1` |

D2 shell:23–34 在写入前拒绝已存在 root；37–52 保存脚本、8 项源码、HEAD/status 和 manifests；81–96 实际关系为 watchdog 启动子 shell，再由 exec/taskset/strace 启动 Python。 **probe 直接父进程是 strace，不能冒充 watchdog。** 因而本次新授权不包括需要真实 watchdog 直接父身份的 A1 main sentinel。[D2 shell][SHELL2] · [D1 shell][SHELL1]

D1/D2 两组 source manifest 规范化后各 8/8 相同，且所列源文件 SHA 与固定 Git 字节一致；旧 `source_snapshot_all_match_manifest=false` 原值保持。新比较能说明两个字典使用不同路径命名空间后应如何对照， **不能证明旧 false 必然由这个比较分支产生** ，因为原生成器没有找到。历史 HEAD 是 `b5a4b69…`，当时有测试修改及 S1 未跟踪材料；最终测试字节不能反向写成当时干净 HEAD 内的字节。[装载审计，2955–3051、3210–3306 行][LOADER7]

### 5.2 415 项有明细，但本次可访问范围只有其中 7 项

递归重建 `(path, sha256)` 的去重引用能得到 415 项；这比没有持久逐项清单的旧“104 项一致”有实质进步。

| 引用范围 | 数量 | 本审阅能确认的内容 |
|---|---:|---|
| 六个 V5 支持根 ignored 文件 | 336 | 清单、大小合计、历史引用的内部关系；未访问原文件 |
| 两个 V6 支持根 ignored 文件 | 60 | 各 30 项，引用与 compact 交叉核对；未访问原文件 |
| 工作站当前安装 ELF | 12 | 元数据格式与记录一致性；未亲读 ELF |
| Git 保存文件 | 7 | 四份 shell/probe、两份机械 diff、事件表，7/7 实际 Git 字节与所引 SHA 相符 |
| **合计** | **415** | **408 份外部原件未独立核验，不能写成本审阅 415 原件全通过** |

六个 V5 根文件数依次 15、17、108、116、34、46，与列表及 bytes 合计相符。候选 patch 的独立 hash 和内存应用另行核验，不混入这 415 项口径。[装载审计，support_runs、3488–3499 行][LOADER7]

本审阅未独立核验的原件范围包括：八个支持 root 中清单所指的 source/status/manifests/snapshots、完整 resources/summary/worker/outer-exit；D1/D2 的全部 `strace/sched.*`、`probe_stages.jsonl`、`probe_terminal.json`；当前库元数据对应 ELF 和原始 readelf/dpkg/sha256sum 输出。如要提升对应原件已核验的声明，须读取相应原件；这不意味着下一轮必须全量重验八个历史支持根，执行范围仍以第 9 节为准。原 inline metadata stdout 未保存，历史进程也未保存映射字节，不能重建为“当时已留存”。旧 A1/A2 数值 NPZ、场、矩阵及完整日志本轮也未访问，更没有重新采样、积分或求解。

### 5.3 库身份纠错合理，精确符号化仍有边界

当前 12 个 ELF 路径唯一，SHA256 格式均为 64 位十六进制。PMIx 的实际 trace 路径 `…/pmix2/lib/libpmix.so.2.13.1` 与别名/realpath 分列；不能再按同名文件猜同一身份。singleton 的 65 位转录值和订正后的 64 位值均有说明，当前表内部相符，原 stdout 缺失也已声明。 **接受这份更正及其限定，不声明审阅者亲自从 ELF 算出了该值。** [装载审计，41–57、149–152、3480–3486 行][LOADER7]

PSM 两类 setter 的首个非 libc 帧没有函数符号，只有库路径和偏移；附近 `mca_pml_cm_add_procs` 是 unwind 所报上下文，不是已精确定位的 setter 函数。优化/剥离符号的最近导出名不能替代对应构建的 debug information。当前包版本、NEEDED 和上游构造函数只能组成机制解释，不是旧进程映射文件的证明。

## 6. 补充机制审阅：为什么现在值得做一次确认

PML 是 OpenMPI 负责选择消息传输实现的层；CM 和 OB1 是不同实现。这里的目标是避免导入时通过某条组件装载路径触发临时改绑，代价是改变该隔离 worker 的通信选择。即使单 rank 支持探针成功，也没有证明多 rank 通信、性能或 Maxwell 求解可用。

本审阅直接读取官方 OpenMPI v4.1.6，解析到固定源码提交 `439b23db6288f0370f6fcc80c8c0a06ad86d6873`。它与记录的 Ubuntu `4.1.6-7ubuntu2` 主版本相符，但尚未逐字节绑定发行补丁/编译产物。

| 源码时序 | 直接源码依据 | 可作出的判断 |
|---|---|---|
| 先登记/读取 framework selection，再登记 components | `mca_base_framework.c:85–90、120–129、147–149`；components register:47–62 | 选择名单进入组件发现阶段，默认路径没有忽略名单 |
| 对动态组件先判断是否被 include，再 repository open | `mca_base_component_find.c:242–267、271–307` | 若有效名单为 `ob1`，该路径会排除 `cm` |
| repository open 内才动态加载 | `mca_base_component_repository.c:413–416` | 这是相关 CM 动态载入之前的过滤，具有明确可检验机制 |
| CM 的 open 打开 MTL framework | `pml_cm_component.c:107–120` | 排除该 CM 路径，有望阻断它引出的 MTL/PSM 装载链 |
| BML/BTL 还有独立路径 | `ompi_mpi_init.c:609–619`；`bml_base_frame.c:117`；OFI component:357 | BML 在 PML 之前已初始化；若实际 build 含 OFI/provider 路径，仍可能装入网络库，不能保证所有 setter 消失 |
| 最后的 PML selection 更晚 | `ompi_mpi_init.c:644–650` | “最后没选中 CM”本身不能证明初始化时未曾加载 CM |

[framework/register][OMPI_FRAME] · [components register][OMPI_REGISTER] · [动态筛选][OMPI_FIND] · [动态加载][OMPI_REPO] · [CM/MTL][OMPI_CM] · [MPI 初始化][OMPI_INIT] · [BML][OMPI_BML] · [OFI][OMPI_OFI]

因此，R3 已经具备申请一次确认的工程依据。 **假设是“这条已观察的加载路径能否被阻断”，不是“OB1 一定消除所有 PSM 或所有 CPU 偏离”。** 运行若仍有成功非 CPU1 setter、未知 setter 记录或其他否决项，应按真实新证据分类并结束本次额度；不能立即再试 BTL/MTL/PSM 参数。合法的 `[1]` 成功 setter 本身不否决。若未见非 CPU1 setter、记录完整且其他门满足，也只能报告规定观察范围内没有发现偏离，并结合完整终态检查评定有限支持资格。

## 7. 测试、计时与格式失败的资格边界

### 7.1 测试目标直接核对

固定 `src/test/test_task43_v3_failure_safe_order.py` 的 SHA256 仍为：

`52f94e28306d2d7f83f602c5e654c8953e544f00091ae3013378d52d040b7a43`

静态审查 helper:786–879 的非空/长度/十六进制身份检查，以及 903–985 的共同缺失反例：反例另写 primary、重新绑定 comparison/terminal/hash，保留原 primary 字节，不是靠随意破坏引用制造拒绝。四组 selector 的参数化确为 1+4+12+3=20。它们当前全部 **NOT_RUN** ；这是 AST/字节审阅，未做 collect，更未运行断言。[固定测试][TEST]

| 允许未来执行的 selector，均在上述同一测试文件 | 展开数 |
|---|---:|
| `test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle` | 1 |
| `test_synthetic_joint_authority_fixture_rejects_common_missing_identity` | 4 |
| `test_synthetic_joint_authority_fixture_rejects_each_failure_independently` | 12 |
| `test_a2_postprocess_writer_failures_keep_original_error_and_primary` | 3 |

这些测试检验合成文件包的一致性及失败留证，不是生产联合 consumer，也不是实际 A2 端点资格。原 probe 中有限 ABI preflight 核解释器/模块路径、MPI 库和 size1、PETSc version/complex128/int64、线程及 memory envelope；不执行完整 SLEPc/FFCx/MUMPS 求解资格。未来该检查通过也不能称全 ABI 栈或全仓 CI 通过。历史全仓收集/ABI blocker 继续保留，不为此次 test-only 修改要求重跑全仓。

### 7.2 费用没有拼成计算加速

装载审计 timing 共 24 项，23 项有计费值、1 项 `not_measured`。重新求和：outer wall 小计 **24.361711005 秒** ；按每项 outer/internal 较大值计费为 **24.384309871707483 秒** 。没有把嵌套 monotonic 时间再加一次；已列单项均低于 60 秒，测得小计低于 600 秒。[装载审计，3312–3474 行][LOADER7]

保留的失败包括 65 位 metadata 转录、编辑中事件表 hash 引用陈旧和 staged `git diff --check` 非零。三份 unified diff 中确有 **6+11+4=21** 个恰为单空格的合法上下文行；删掉这些空格会改变证据 patch 的原字节。定向格式检查可以接受，但不能把最初的非零结果改写为全范围全绿。该检查不是 pytest、ABI 或 CPU1 资格。

这些实际工具输出多数只在轻量账本中转述，本审阅验证了算术和当前文本事实，未亲证每个原工具进程。人工阅读、未计时 shell/文件操作、后续文案编辑另记 `not_measured`，不补造全轮精确总成本。V6 支持 20.736750496551394 秒属于旧 watchdog 生命周期；V7 静态处理小计属于另一口径；两者都不能证明同精度 PDE 加速。

## 8. 科学状态与合并资格分别裁决

### 8.1 五项能力及正式额度

| 项目 | 维持状态 | 具体理由 |
|---|---|---|
| 空间 | PARTIAL | 没有新增 mixed-p、local-h 或多层/联合约束的实际数值见证 |
| 选择 | PARTIAL | accepted9/R9 仍是最后接受状态，R10 拒绝不回写，不把后验控制反馈给旧选择 |
| 精度 | NOT_PASSED | R9 的 110472 独立 FE 小于对照 237600，但独立输出精度仍失败；导入、q 稳定性和 fixture 均不能替代空间精度 |
| 同精度全过程成本 | NOT_ESTABLISHED | 没有同精度合格端点及可比完整生命周期；启动诊断费用属于工程支持 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 没有新增接线或 direct-equivalent 迭代证据 |
| 正式总额 | 5/6；A1 2/2、A2 3/3；最后 1 槽封存 | V7 新 PDE/dispatch/attempt/READY 为 0；未来 D3 是独立支持额度，不抵扣或恢复正式槽 |

历史 A1_q2 在已构网/进入装配后因缺 ledger 受控停止；A2_q3 primary partial、extra full-active 严格下降负项、7200 秒停止、完整端点缺失及 LIMITED 清理结论均保持。它们没有在本轮重新计算。工程失误不能证明 hp 方法本身无效；工程修复也不能证明 hp 已达精度目标。[当前 summary][SUMMARY7] · [历史 V6 review][V6]

### 8.2 依赖组裁决

| 组 | 具体文件 / 依赖 | 本次资格及剩余阻塞 |
|---|---|---|
| 文档 / 轻量研究档案 | 本报告、response_v7、两份 V7 JSON、保存脚本/diff/patch、README/summary/manifest；registry/progress 的 Task43 补丁及被引用历史资料 | 可保留在研究分支，作为未来 docs-only 迁移候选。需带本报告限定/勘误并核目标链接闭包；总账只迁 Task43 补丁，不能覆盖其他任务。 **没有本次实际 merge approval** |
| test-only | `src/test/test_task43_v3_failure_safe_order.py`，依赖 `candidate_checkpoints.py`、A2 fail-closed 函数及既有导入链 | 静态身份修复可接受，最终字节 20 项尚未运行；不是可独立无依赖搬走的大测试文件，更不是生产 consumer。未来支持成功仍需目标分支依赖核对 |
| 研究入口 | `h100_anchor.py`、`a2_native_p6_diagnostic.py`、`candidate_checkpoints.py`、`src/runners/p6_condensed_direct.py` 的显式诊断分支及 ledger/failure-safe 依赖 | 本轮无源码改动，维持 research-only；无新现场完整端点，不解锁 A2_R/controller 或生产默认 |
| 共享启动 / watchdog | `scripts/activate_task40_phi90_pord64.sh`、`benchmarks/subreaper_watchdog.py`、native capacity/ledger 依赖；拟议隔离 D3 shell/probe | 本轮未改共享代码；局部 MCA 输入即使成功也不得迁入共享 activation。旧 watchdog 证据保留原版本边界，不授新的生产启动资格 |
| 数值核心 | manifest:58–73 的 A–D 第一原子依赖组，含 mesh/axis/profile 前置与测试 | 无 V7 数值或 fresh PDE 资格。旧 overlay 的 59/66、核心共享 23/27 同字节不能资格化四个变化共享文件；本次 20 项不能替代该 Gate |
| 整分支 / 大型原件 / 未验默认路径 | 全 research branch、ignored 场/矩阵/trace、未资格化开关 | **Do-not-merge** ；不得整体 merge/cherry-pick，不实际操作 master |

四个仍受旧 overlay 边界限制的共享文件为 `common_3d_case_flow.py`、`dtn_port_3d.py`、`hcurl_variable_p_reduction.py`、`solve_maxwell_3d_stage_4b_block_grating.py`。V7 文档没有提供它们的新生产证据。将来某组若取得明确 approval，仍须用户授权、Codex 按依赖闭包执行并报告目标 SHA；研究档案可保留不等于已经授权合并。[选择性合并清单，37、52、58–73 行][MANIFEST7]

## 9. 下一轮明确允许范围：静态准备，加一次 D3 支持确认

### 9.1 新授权、唯一目的与次数

**批准 1 次新的支持 driver，以及同次运行中门槛满足后固定 20 项测试。** 新额度只回答两件事：OB1 worker-local 输入能否消除这次受控导入链中的已观察 setter；最终 test-only 身份/二次写失败案例能否执行并满足断言。没有任何 Maxwell 模型被授权。

V6 两次 support 已用 2/2，不恢复；V7 静态轮新增 driver 为 0；本报告另给 D3 **1/1** 。唯一命令一旦开始执行即占用一次，目录拒绝、shell/preflight/导入/ABI/测试失败也占用。未用完时间、失败很快、改名或局部修复均不产生第二次运行权。禁止另外启动 native preflight、import-only、collect-only 或恢复 pytest。

### 9.2 执行前必须完成的有限静态工作

按以下顺序完成，主控逐项复核原证据，不能只接受 subagent 标签。单条静态处理上限 60 秒，明确可计时的文件/ELF/字符串处理累计上限 600 秒；手工阅读和未计时操作另记。不得通过静态名义导入 native 库或执行项目 helper。

1. **保全与勘误。** 保留旧八个支持 root、V7 原记录、历史 review/合同/负结果。当前说明采用 V7-03/04 的准确进程、时间和预算语义；新勘误写明旧路径/行号，不覆盖原事件或失败。无需追求补造已丢失生成器和 stdout。
2. **核实际输入。** 只读核当前 tracked activation 及其 source 的现存 venv activation；只核相关 MCA 环境、用户/系统参数及 override 来源。核 V7 12 项 ELF 当前身份，补两个 PSM MTL 插件，以及存在时的 BTL/OFI 与直接依赖元数据；保存命令、原 stdout、退出码、路径/realpath、SHA、Build-ID、NEEDED。用 `readelf`/包数据库/文件哈希，不用会加载组件的 `ompi_info`、新导入、安装或环境重建。缺文件如实记；存在未解释的身份漂移、覆盖输入或机制冲突就停止，不替换参数继续。
3. **只构造这一个隔离候选。** 将已审 D2 shell 机械施加原候选 patch，得到下节固定 shell；在 D2 probe 的新副本上仅施加附录 A。历史归档和共享脚本不动，不创建 controller/通用框架，也不改数值或测试代码。
4. **一次无 native sanity 与冻结。** 允许用 stdlib/AST/合成字符串检查候选文本与附录所列解析行为；这是明确获准的有限字符串验证，不是 pytest、ABI 或 driver。只加载/提取所需解析函数，不执行 probe 顶层/main，不导入 numpy/dolfinx/MPI/PETSc 或项目模块。保留命令、输入样本、输出、实际秒数；断言失败则停止本次启动准备，不自行扩大修改。静态核四个 selector 仍为 20 项、其他 main/ABI/拓扑/资源逻辑不变。
5. **冻结一次实际字节。** shell/probe/hash 必须准确匹配第 9.3 节；8 项路径以固定保存 D2 shell:12–21 的 `source_paths` 为准，source manifest 与固定被审文件一致，尤其测试 hash 不变。真实 HEAD 可以包含本 review 和有限文档提交，但必须保存 HEAD/status/diff，不能冒称历史 D2 的 HEAD 或忽略工作树代码漂移。将本 review SHA、实际源码、脚本、环境记录、唯一命令/目录、次数及资源门写入一个轻量 preflight 记录。

这五步属于本次已授予的准备范围，合格后可直接执行唯一命令。若原件不可读、hash 不符、需要额外参数/代码或无法说明输入，交付静态负项并停审；不能把条件失败解释为可以再消费一次“试试看”。

### 9.3 唯一命令、目录、字节与资源

| 项目 | 唯一允许值 |
|---|---|
| 执行工作区 | 已登记 canonical worktree `/home/fenics/Projects/NN-Lab-V2`，分支必须为 `task43_hp_adaptivity` |
| 新脚本目录 | `/tmp/task43_v7_d3_proposal`；脚本名 `run_d3.sh`、`probe_import_affinity.py` |
| 唯一命令 | `bash /tmp/task43_v7_d3_proposal/run_d3.sh` |
| 唯一输出 root | `/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1` |
| shell 来源 / hash | 原 D2 shell + 固定 `d2_to_d3_candidate.patch`；4166 字节，SHA256 `e84d2eb0bfcd257549fcd85b336d5ce9ea5f8faa72eef5261e7ca936d076127a` |
| probe 来源 / hash | 原 D2 probe + 本报告附录 A 的唯一审计修订；14891 字节、371 行，SHA256 `fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4` |
| 运行输入 | worker-local `HWLOC_COMPONENTS=-x86`、`OMPI_MCA_pml=ob1`；保留 `TASK43_V6_D2_ROOT/TRACE_PREFIX` 环境键，但值指向新 root/trace |
| CPU / MPI / 数值线程 | CPU1 mask 严格 `[1]`；MPI world size 1；OMP、OPENBLAS、MKL、BLIS、NUMEXPR、VECLIB 六个线程变量均 1；不增加 mpiexec |
| 资源 profile | `task43_hp_adaptivity_resource_v1`；`PHYSICAL_NATIVE_NODE_CAP_BYTES=8589934592`；采样间隔 0.25 秒 |
| RSS / reserve | 同时进程树采样 RSS 必须低于实际 launch cap，且绝不超过 8 GiB；保留可用内存/reserve 导出的更严格门，不强行提高 cap |
| swap | task VmSwap 必须 0；global pswpin/pswpout 基线/末态/增量另存。全局活动不能直接归因本任务；非零或缺失使零 swap 资格受限，不能写无条件 PASS |
| 时间 / 次数 | watchdog 工作停止阈值 100 秒；whole-watchdog 含清理验收≤120 秒，累计同为≤120 秒；最多 1 次，无扩时、无重试 |

输出 root 必须由这一次 launcher 创建，事先存在即拒绝，不清空、不改名、不复用旧 root。新脚本可在上述唯一 `/tmp` 目录准备，但输出 root 的证据不能预先混入其他运行。共享 activation/ABI、数值默认、MCA 系统配置、资源 policy、历史合同均不可修改。

### 9.4 顺序、停止及测试范围

实际顺序为：保存源码/脚本身份 → watchdog/strace → startup 实际环境及 affinity 门 → 原有逐模块导入与每阶段 trace 门 → 原有有限 MPI/PETSc ABI preflight → pytest 导入门 → 同一 Python 进程内第 7.1 节四个 selector → 最后 snapshot → 正常退出/清理 → 完整原件终态审阅。

不得把 20 项改成整个测试文件、全仓 pytest、collect-only、FFCx witness、A1 main sentinel、旧场采样或模型。只要前门失败，20 项保持 NOT_RUN；ABI 未到达与 ABI 执行失败分开写。pytest 批次若有断言失败，保存实际已执行/失败/未执行数量，整个支持目标不通过，不补跑失败节点。原 probe 的 pytest.main 批次没有额外 fail-fast 开关；本授权允许既定 20 项的一次批次，不允许失败后另起恢复批次。资源、affinity 或监控异常一旦可读确认，仍须立即停止，不能因批次尚未结束而等待。

以下任一情形否决 continuation：实际输入不符；成功 setter mask≠[1]；非栈帧 setter 调用失败或格式未知/不完整；可读 TID/资源成员 affinity 偏离；关键身份/trace 不可读；ABI 失败；RSS/reserve/task swap/时限门；监控异常或清理失败。失败 setter 采用保守停止，但不得把失败调用记成成功改绑。主控只对已核 PID/start_ticks 的本任务 watchdog 发信号，保留 watchdog 的原分类和原因，不终止邻近任务。到 100 秒不得继续业务；若必要清理导致含清理时长超过 120 秒，如实记录超限、只完成必要清理，不能视为获准延长测试。

### 9.5 终态必须交付什么，怎样判定

必须保留：实际 shell/probe 原字节及 hash；8 项 source 快照与 manifest、HEAD/status/diff；实际环境；PID/PPID/start_ticks/TID；全部 `probe_stages.jsonl`、`probe_terminal.json`、完整 `strace/sched.*`、watchdog resources/summary/worker.log、外层退出码；信号/停止/末行资源/清理证据；20 项实际结果和未到达原因。Git 只交轻量索引、必要摘录和可审脚本，完整日志继续 ignored；不要提交大数组。

主控在 strace/worker 完全退出后，独立读取最终全部 trace，并与逐阶段记录核对：所有 setter token 都须归类，含退出尾段、失败、unfinished/resumed 与不认识的格式；不能只重用 probe 的成功集合。逐行核资源样本与同一 PID/start_ticks，保存最终后代清除和 cache/异常信息。完整 trace hash 及事件行只读重算，原件不能改写。

| 实际结果 | 必须采用的结论 / 后续动作 |
|---|---|
| 仍有成功非 CPU1 setter | 假设未满足 strict CPU1；按库/角色/时序记录新证据，停止；不再试其他 MCA 参数 |
| 未见偏离，但 trace/输入/退出/清理不完整 | INCOMPLETE / NOT_QUALIFIED；不因 20 项通过授资源资格，不重跑补证 |
| 导入与 trace 到达，ABI 失败 | 有限启动观察可记录；ABI FAILED，20 项 NOT_RUN；不重建环境 |
| ABI 到达且 20 项有失败 | 保存真实失败项，测试目标不通过；无恢复运行 |
| 20 项全部通过，终态原件完整且所有门满足 | 只能授予这一固定 worker-local 链和 20 项最终字节的有限工程证据；不得写成生产 ABI、全仓 CI、MPI>1 或科学端点资格 |

下一次交付用 `response_v8.md` 和必要的一个 preflight/closeout 轻量记录，更新当前 summary/README/manifest/registry/progress 的相关段落；所有失败和 not_measured 留存，文档收口后提交同一分支等待审阅。不得新增框架或多份平行冻结合同。

### 9.6 正式计算与所有下游仍禁止

**不批准任何新正式 PDE。** A1/A2 q 重试、A1_R、A2_R、B/C、fresh baseline、同精度全过程成本 campaign、迭代接线、0.7 nm、NN/FTT 继续锁定；正式最后 1 槽没有自动使用权。支持成功不解锁这些工作，也不撤销原端点与科学前置。将来申请正式计算仍需单独给出科学必要性、合格前置、固定输入/模型/目录/命令、明确 attempt/组及总额度调整、资源门和必须持久化的完整端点。

## 10. 审阅结项

V7 把此前只能看到摘要的启动器和事件来源变成了可审查的 Git 文本，说明了已知监督遗漏和无法追证的部分；这是可以验收的静态进展。本文进一步核对加载时序、发现新诊断门的两处具体缺口，并把修订、唯一命令、预算、测试节点和终态否决条件固定下来。下一轮工作比单纯补文档更进一步，但只有一次可证伪支持确认。

五项科学能力不变；当前 CPU1 仍未通过、20 项仍未运行；没有正式计算或生产合并批准。本次只提交本报告到执行分支，实际启动和后续交付由 Codex 按第 9 节完成。

## 附录 A：仅用于未来隔离 D3 的审计修订

本附录是前瞻执行规格，未修改被审源码、保存 D2 原件或原候选 patch，也未创建/执行 D3 runner。shell 仍用原候选 patch；probe 从 Git 保存的 D2 原字节开始机械施加以下修订。目标是收紧记录覆盖和实际输入核对，不改变 import 顺序、ABI 检查、20 项 selector、父链、资源或数值合同。

原 D2 probe SHA256 为 `0ce0fd5d7bbcd20272a7d551b414a142ffcf5f859b23636384e906d5b2c553a1`。下列 patch 在内存机械施加后为 14891 字节、371 行，SHA256 `fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4`。本审阅只核文本、hash 和 AST；仅 `_successful_setters`、`_snapshot` 的 AST 改变，其余函数保持一致，没有执行新旧函数。

```diff
--- a/preserved-D2/probe_import_affinity.py
+++ b/proposed-D3/probe_import_affinity.py
@@ -59,13 +59,19 @@
     found: list[dict[str, str]] = []
     unknown: list[str] = []
     for path, line in lines:
-        if "sched_setaffinity(" not in line or not re.search(r"\)\s+=\s+0(?:\s|$)", line):
+        if "sched_setaffinity" not in line or line.lstrip().startswith(">"):
             continue
-        match = re.search(r"sched_setaffinity\([^,]+,\s*[^,]+,\s*\[([^\]]*)\]\)", line)
+        # D3 is conservative: any incomplete, resumed, failed or unknown setter
+        # record stops continuation; unwind-stack symbol mentions are not calls.
+        match = re.fullmatch(
+            r"\s*\d+\.\d+\s+sched_setaffinity\(-?\d+,\s*\d+,\s*"
+            r"\[(\d+(?:\s+\d+)*)\]\)\s+=\s+0\s*",
+            line,
+        )
         if match is None:
             unknown.append(f"{path.name}: {line}")
             continue
-        cpus = [int(item) for item in re.findall(r"\d+", match.group(1))]
+        cpus = [int(item) for item in match.group(1).split()]
         found.append({"trace_file": path.name, "cpus": json.dumps(cpus), "line": line})
     return found, unknown
 
@@ -117,6 +123,7 @@
         "stage": stage,
         "module": module,
         "hwloc_components": os.environ.get("HWLOC_COMPONENTS"),
+        "ompi_mca_pml": os.environ.get("OMPI_MCA_pml"),
         **_proc_identity(),
         "tids": tids,
         "affinity_by_tid": affinity_by_tid,
@@ -125,7 +132,7 @@
         "trace_files": [path.name for path in _trace_files()],
         "trace_errors": trace_errors,
         "successful_sched_setaffinity_events": setters,
-        "unparsed_successful_setters": unknown_setters,
+        "unclassified_setter_records": unknown_setters,
     }
     _append(record)
 
@@ -133,10 +140,12 @@
         return False, "trace output did not synchronously expose the getaffinity barrier"
     if os.environ.get("HWLOC_COMPONENTS") != "-x86":
         return False, "HWLOC_COMPONENTS was not set to the reviewed scoped value -x86"
+    if os.environ.get("OMPI_MCA_pml") != "ob1":
+        return False, "OMPI_MCA_pml was not set to the reviewed scoped value ob1"
     if trace_errors or unreadable_tids or not tids:
         return False, "stage process/thread identity or trace was unreadable"
     if unknown_setters:
-        return False, "successful affinity setter had an unparseable CPU mask"
+        return False, "affinity setter record was failed, incomplete or outside the reviewed grammar"
     if any(json.loads(event["cpus"]) != [1] for event in setters):
         return False, "successful sched_setaffinity event selected a mask other than [1]"
     if any(mask != [1] for mask in affinity_by_tid.values()):
```

下列是下一轮有限字符串 sanity 的预期，不是本轮已运行结果。对不能完整识别的 setter 采用保守停止；失败调用本身不代表发生了成功改绑。新字段 `unclassified_setter_records` 避免把失败/未知记录误称成功事件。

| 合成输入 | 必须得到的行为 |
|---|---|
| `1790000000.123456 sched_setaffinity(0, 128, [1]) = 0` | 完整成功记录；后续 mask 门允许 |
| 同格式的 `[0]`、`[1 2]` | 完整成功记录；后续 mask 门否决 |
| 返回 `-1 EINVAL` 的完整 setter | 进入 unclassified 并停止，不称成功改绑 |
| unfinished 或 resumed 行 | 进入 unclassified 并停止，不冒险拼接后放行 |
| `[1 ...]`、逗号/范围形式或其他未支持 mask | 进入 unclassified 并停止 |
| 前导 `>` 的 unwind 栈帧含同名函数 | 仅栈上下文，不能当 syscall 计数 |
| 其他非栈帧含 setter token 的不明行 | 进入 unclassified，不静默忽略 |
| startup 实际 PML 缺失或非 `ob1` | 已保存实际环境字段，首个显式 native import 前停止 |

该修订只针对本次有限支持诊断，不是通用 production strace parser。完整生命周期仍按第 9.5 节的独立终态复核裁决。

## 固定证据与官方源码入口

[DIFF7]: https://github.com/Rookie1234567/MyFEniCS/compare/9e11b6e0804c2fd51e99353ec306483af0621580...fb9244d1ea3e688c66b1fc42e9cc575952c5080f
[V6]: https://github.com/Rookie1234567/MyFEniCS/blob/9e11b6e0804c2fd51e99353ec306483af0621580/docs/task43_hp_adaptivity/review_report_v6.md
[RESPONSE7]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/response_v7.md
[EVENT7]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_trace_event_inventory_v1.json
[LOADER7]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_source_loader_audit_v1.json
[CLOSE6]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/records/v6_affinity_support_closeout_v1.json
[SHELL1]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_driver_sources/d1/run_d1.sh
[SHELL2]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_driver_sources/d2/run_d2.sh
[PROBE2]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_driver_sources/d2/probe_import_affinity.py
[PATCH3]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_driver_sources/d2_to_d3_candidate.patch
[TEST]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/src/test/test_task43_v3_failure_safe_order.py
[WATCHDOG]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/benchmarks/subreaper_watchdog.py
[ACTIVATE]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/scripts/activate_task40_phi90_pord64.sh
[SUMMARY7]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/summary.md
[MANIFEST7]: https://github.com/Rookie1234567/MyFEniCS/blob/fb9244d1ea3e688c66b1fc42e9cc575952c5080f/docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md
[OMPI_FRAME]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_framework.c#L85-L149
[OMPI_REGISTER]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_components_register.c#L47-L62
[OMPI_FIND]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_component_find.c#L242-L307
[OMPI_REPO]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_component_repository.c#L405-L416
[OMPI_CM]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/ompi/mca/pml/cm/pml_cm_component.c#L107-L120
[OMPI_INIT]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/ompi/runtime/ompi_mpi_init.c#L595-L650
[OMPI_BML]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/ompi/mca/bml/base/bml_base_frame.c#L117
[OMPI_OFI]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/btl/ofi/btl_ofi_component.c#L340-L357
[OMPI_VAR]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_var.c#L1622-L1655
