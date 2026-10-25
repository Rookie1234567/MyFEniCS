# Task43 正式审阅 V6：静态身份修复接受，CPU1 门未过，停止新增运行

审阅日期：2026-10-25。固定被审提交：`cab17f542bfffeb6598eedfed3194d07ea047630`。本轮执行权威为正式 V5 review 提交 `b5a4b69c25c6be92faf0116e119904c438cbe297` 的第 9 节。本报告直接审查固定源码、提交差异和 Git 轻量证据；没有执行 pytest、导入探针、项目函数、模型计算或旧场后处理。

## 1. 分开裁决

| 维度 | V6 决定 | 准确边界 |
|---|---|---|
| 工程整改 | **部分接受；S2 实现按静态审查接受** | 身份共同缺失的已知漏判已被代码阻止，四个反例构造合理；20 项动态案例仍为 NOT_RUN。S1 在已提交证据范围内可接受；D2 放行前置未满足，另有轻量元数据矛盾待解释 |
| 资源资格 | **严格 CPU1 = NOT_PASSED** | D1 有可读非 CPU1 资源样本；D2 有成功 CPU0 系统调用，阶段末恢复及离散采样无偏离都不能冲销。时限、RSS、swap、清理仅按轻量记录接受有限结论 |
| 科学资格 | **PARTIAL / CONTROLLED_NEGATIVE 保持** | 本轮没有新增科学端点，不能由支持诊断的失败或静态修复判断 h/p 方法成功或失败 |
| 下一轮运行型非 PDE 诊断 | **不批准；新增支持 driver = 0** | 先完成第 9 节限定的旧证据只读分析和一个未执行的局部启动方案。本报告不授予第三次导入、ABI 检查或 pytest |
| 新增正式计算 | **不批准；PDE / dispatch / attempt / READY = 0** | 正式累计仍为 5/6，A1 2/2、A2 3/3，最后一槽继续封存 |
| 合并 | **不授予 production 或整分支 merge approval** | 研究档案可保留；文档和 test-only 修复的未来选择性迁移条件见第 8 节。本次只新增本 review，不实际合并 |

CPU affinity 是一个线程被允许运行的 CPU 集合。严格 CPU1 要求集合保持为 [1]；先设置 taskset 或最后恢复为 [1]，并不能证明中间从未改变。另一方面，文件身份检查回答的是“这几份文件是否具备必要身份并相互绑定”，与场解是否准确、求解是否便宜是不同问题。[V5] · [RESPONSE6] · [CLOSE6]

## 2. 固定身份、全部差异和审阅方法

### 2.1 Git 身份

| 对象 | 独立核对结果 |
|---|---|
| 仓库 / 执行分支 | Rookie1234567/MyFEniCS / task43_hp_adaptivity |
| 固定被审 SHA | cab17f542bfffeb6598eedfed3194d07ea047630 |
| 固定 tree | 11776105752cb74b1f4f0777bc662d663a6b7197 |
| 直接父提交 / 正式 V5 review | b5a4b69c25c6be92faf0116e119904c438cbe297 |
| 长期代码基线 | 405e3aff42ac421a4c99315df1ed9b96941ecbe4 |
| 基线祖先关系 | compare 为 ahead 66、behind 0，merge base 正是指定基线 |
| V5 review 至本轮对象 | 1 个提交，9 个路径，1857 行新增、0 行删除 |
| 远端身份 | 审阅开始及发布本 review 前再次读取均指向固定被审 SHA；没有将后续字节纳入本轮测试对象 |
| 工作站本地状态 | “工作树干净、ahead/behind=0/0”是执行方交付陈述；本审阅未访问 canonical worktree，不能独立确认这一工作站事实 |
| 本 review SHA | 由只新增本报告的 Git commit object 确定，交付消息返回完整值；文件内不制造自身 SHA 的循环引用 |

已检查全部 9 个路径：一个 Python 测试文件、两份新 JSON、response_v6，以及 Task43 README、summary、selective merge manifest、仓库模型总账和开发进展。与直接父版本相比，数值核心、A1/A2 入口、watchdog、activation、冻结合同、旧 review、旧 response、READY 和历史失败记录均未变化。[DIFF6]

本轮运行记录的 source_head 为 V5 review 的 b5a4b69…，同时其逐文件清单已包含修改后 S2 测试文件的 52f94e… 字节。这表示“以该 HEAD 为基础的本轮文件快照”，不是干净 b5a4b69 的测试，也不是对最终 cab17f5 整棵树的动态验证。两次本来就没有到 pytest，因此不得把 source 清单当作测试通过清单。[CLOSE6，265–313、581–629 行][CLOSE6]

### 2.2 本审阅亲自核对了什么

完整阅读三层 AGENTS、任务书、V5 review、response_v6、两份 V6 JSON；检查当前 README、summary、manifest、模型总账和开发进展，并追溯所需 V5 记录。取得的 197 个 tracked 缓存文件均与固定 tree 的 Git blob 相符；这证明审阅所用字节身份， **不等于逐个重新验证了 197 个文件的运行行为** 。

独立静态核对包括：

- 对比测试源码及 AST：只有既有联合读取 helper 改变，新增一个四参数反例函数；原生成器、正例、12 个独立否决和三类 writer 故障函数体保持原字节。
- 重算最终测试文件 SHA256、S1 文件绑定，以及 S1 中四条内嵌原始资源行的 UTF-8 字节长度和 hash，解析其成员身份、状态和 affinity。
- 对照六个旧运行的摘要、18 个原件 hash 引用和退出码说明；核对两次新运行的启动上下文字符串、源码 hash 字典、费用算术与资源口径。
- 直接阅读 Git 内的 syscall 行、代表调用栈、PID/PPID/start_ticks/TID 摘录；阅读相关上游 hwloc、PSM、PSM2 源码和 Linux 状态字段文档。

上述是文件读取、字节/hash、JSON 和 AST 静态检查，没有执行测试 helper，没有创建或重算场 NPZ，没有运行工作站原始脚本。 **工作站 ignored 完整 trace、resources、driver/probe 快照、终态原件和历史场 NPZ 均未独立核验。** 具体缺口见第 7 节。

## 3. 按严重程度排列的问题

本次没有发现需要回滚数值代码的新增 P0/P1 缺陷。下列 P2 表示继续运行或资格判断的阻塞，P3 表示需要有限修正的证据/文档问题；它们不等同于 h/p 数值方法的失败。

### V6-01 · P2：D2 不满足条件性放行前置，主控只处理了部分已知来源

**定位：** V5 review 第 9.1 节 D2、第 9.2.8 条；closeout 第 55、217–264、359–387、545–579 行；response_v6 第 26 行。[V5] · [CLOSE6] · [RESPONSE6]

D1 的统计和代表栈已经包含三类 setter：hwloc 196 次、libinfinipath 2 次、libpsm2 2 次。两条网络库 CPU0 栈明确属于 D1，并非 D2 才产生的新问题。主控在 D2 前只审查了 hwloc，没有将另外四次调用纳入原因分类，就进入“修复后确认”。

V5 的 D2 许可有前提：已有证据先将问题定位到可局部修复的启动/检查路径；若 D1 后仍未定位，应有限结项。 **本次 D2 的放行审查没有充分满足该前提。** 禁用一个来源后观察到该来源消失，提供了局部诊断信息；它不能追认一次准备充分、整体原因已处理的确认。

影响与裁决：

- D2 保留为有效的负向支持证据，同时保留“前置审查不完整”的监督责任。
- 两次都计入 2/2，失败不退还次数，D2 不改名为预检以抵扣；费用全额保留。
- 及时停止、没有进入 pytest/PDE、没有超时，并不能使此前的错误放行变为合格。
- 当前回应已经诚实承认遗漏，这是可接受的整改记录；它没有关闭原因分类和后续授权问题。

**最小整改与验收：** 只从已保存原件完成 D1/D2 全事件分类、关键脚本静态差异和实际库身份核对；给出一个具体、未执行的局部启动方案。全部已见调用类别必须有解释或显式“未知”，不得再依据一个代表栈直接运行。详细允许范围见第 9 节。

### V6-02 · P2：严格 CPU1 仍失败，现有轻量包不足以批准新的运行链

**定位：** closeout 第 26–32、119–156、402–427、447–543、694–753 行；两版脚本仅列路径/hash和摘录于第 59–81、359–382 行。[CLOSE6]

D1 的两个资源成员样本状态为小写 t，affinity 分别是 [33]、[30]。这不是 Z 态缺测。D2 的资源采样没有捕获偏离，但四条 syscall 中两次成功设置 [0]、两次恢复 [1]，已足够否决严格 CPU1。两个导入后 TID 快照全为 [1] 不改变这个结论。

还存在一个直接影响新授权的证据边界：两版完整 shell/probe 只在 ignored 目录，Git 给出的是不同 hash 和部分摘录。由当前提交可以证明 tracked activation/数值入口没有改动，却不能独立证明两版 ignored probe 的全部差异仅限预期配置，也不能审查 trace 同步、完整枚举和停止逻辑的实际实现。`trace_sync=true` 是一项记录，不能替代读取实现及对应原件。

**影响：** 资源资格未建立，20 项测试仍未执行，完整 ABI 检查仍未到达。CPU1 失败不自动否定已知文件保护逻辑，也不是测试断言失败；它阻止把本轮当作合格运行链、最终测试或成本资格。

**最小整改与验收：** 提交已有脚本的必要完整文本及差异，核对已有 trace 的完整性和角色分类。解释真实加载的库与拟修改启动项之间的关系，未知项保留未知。本次不要求全仓重跑、环境重建或任何模型；原 CPU1 负结果永久保留，不能通过改定义追溯放宽。

### V6-03 · P3：两个源码快照汇总 false 与逐项 hash 字典不一致

**定位：** closeout 第 **293、609 行** 的 `source_snapshot_all_match_manifest: false`，对应第 283–303、599–619 行的两组清单。[CLOSE6]

独立核对发现：分别去掉 snapshot 键中该次 run 的 `source_snapshot/` 前缀后，两组都恰有 8 个唯一相对路径，与 source manifest 的键集合和每项 hash 完全相等；所列 8 项 source hash 也均与固定 Git 文件一致。这与汇总 false 存在未解释的矛盾。

这不是已证实的真实源码漂移。也不能直接断言“只是路径前缀比较错误”：原生成器和 ignored snapshot 未被本审阅访问，false 可能还代表未披露的检查。

**最小整改：** 只读核对已有生成器、manifest、snapshot 和 source_status，在一份新的轻量补核记录中解释 false 的判定含义及实际差异。若确为键规范化问题，给出 8 项对应表和原件逐项核对；若有原件缺失或漂移，按真实缺口记录。不得覆盖本轮原 JSON 或把两个 false 无解释地改成 true。

**验收标准：** 汇总与逐项字节证据有可复核的一致解释；历史值仍可追溯；没有为修正该元数据新增 driver、测试或 PDE。

### V6-04 · P3：当前入口仍混有旧“最新”标题，个别完整性措辞需收窄

**定位：** Task43 README 第 8、57 行；summary 第 17、47 行；模型总账第 9 行；progress 第 7 行；manifest 第 5 行。[README6] · [SUMMARY6] · [REGISTRY6] · [PROGRESS6] · [MANIFEST6]

最新追加段落准确写明 S2 NOT_RUN、完整 ABI NOT_REACHED、CPU1 NOT_PASSED；没有发现将 20 项伪报通过。但 README 顶部“当前状态”仍把 V5 F1–F4 和 25 项历史通过称为“本轮”，几处旧标题仍称“最新”。progress 的“完整 PID/TID/affinity trace … 见 compact”也容易让读者误以为完整原 trace 已入 Git；实际是身份摘录、代表栈、统计和原件索引。

manifest 的“首个 dolfinx 导入内停止”应精确为“首个显式 dolfinx 导入返回后的检查点停止”：closeout 明确记录 `last_completed_import=dolfinx`、`stop_stage=native_import_complete`。导入本身已可触发 MPI/PETSc 初始化，尚未执行的是后续完整 ABI 检查。

**最小整改与验收：** 只更新当前导航/说明，把旧段落标为历史，把完整原件与 Git 摘录分开，并使用准确停止阶段。保留旧 review/response/合同/失败记录原字节；不改历史测试数，不把本轮文案追认为此前测试覆盖。不需要为了这些文字修改重跑功能测试。

## 4. S2 身份 helper：静态实现接受，动态验收未完成

联合读取 helper 的作用是同时核查 summary、comparison、terminal 和 primary 文件。如果所有文件恰好一起丢掉身份，仅检查“彼此相等”会把几个共同缺值误当作一致。新增的存在性和格式检查正面处理了这个已知漏洞。[CODE，786–879 行][CODE]

### 4.1 实现与反例构造

第 823–834 行在相等性判断前，分别要求 source 为 40 位字符串、contract/plan 为 64 位字符串，且每一位属于 ASCII 十六进制字符。None、空串、错误类型、长度不符或非十六进制值都不能通过这段逻辑。后续各文件身份仍必须相等，所以不能靠所有文件共同缺失绕过。格式正确仅说明值形状合理，不证明它就是外部获准的 source/contract；这里仍是 test-only 约定，不是生产身份认证。

第 894–985 行的四个反例不是依靠故意留下坏 hash 取巧：

1. 先生成原一致包并要求其通过 helper。
2. 同步移除 summary、comparison、primary identity 的 source、contract、plan之一或全部。
3. 另写 `primary_missing_identity.npz`，将同一新引用同时接入 summary 和 terminal；terminal 的缺值与整个反例保持一致。
4. 落盘 comparison/terminal 后重新计算它们的实际 hash，再写 summary。
5. 保留测量与 COMPLETED 状态，核对新的 comparison/primary/terminal hash，并在第 979 行要求原 primary NPZ hash 不变。
6. 最后要求新包被拒绝。

因此静态上，拒绝原因针对身份存在性，而不是残留的引用错配。“保留原正例字节”应精确理解为原生成器/正例用例源码未变、反例中原 primary 文件不被覆盖；反例的 summary/comparison/terminal 本来就有意改写，不能说整个包所有文件均未改变。

### 4.2 最终字节与案例清单

最终文件 SHA256：

`52f94e28306d2d7f83f602c5e654c8953e544f00091ae3013378d52d040b7a43`

| 直接相关函数 | 固定行号 | 静态案例数 | 本轮运行结果 |
|---|---:|---:|---|
| test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle | 882 | 1 | NOT_RUN |
| test_synthetic_joint_authority_fixture_rejects_common_missing_identity | 903 | 4 | NOT_RUN |
| test_synthetic_joint_authority_fixture_rejects_each_failure_independently | 1005 | 12 | NOT_RUN |
| test_a2_postprocess_writer_failures_keep_original_error_and_primary | 1064 | 3 | NOT_RUN |
| 合计 | — | 20 | 0 项执行；不是 20 项通过，也不是 20 项断言失败 |

本审阅对前后函数源码的静态比较支持“原正例、12 个独立否决和三类 writer 故障保留”。但 helper 自身改变后，历史案例通过不能替代最终字节验证；S2 只关闭 V5-02 的已知静态缺陷，动态验收仍待今后另行授权。当前无需继续扩写 helper、增加生产 consumer、启用 A2_R 或新建 controller。[CODE] · [CLOSE6，8–24 行][CLOSE6]

## 5. S1、D1/D2：哪些证据成立，哪些没有被本审阅重验

### 5.1 S1：可接受的历史摘录一致性，不是六份原流重验

S1 两个历史 source_records 的 hash 与固定 Git 字节相符；六个运行的分类、worker exit、清理、wall、采样数及 18 个 resources/summary/worker.log hash 引用与 V5 记录对应。[S1] · [VALIDATION5] · [RESOURCE5]

S1 第 99、303、502、673 行嵌入四条完整异常资源行。本审阅亲自重算其不含换行的 UTF-8 长度和 SHA256，长度依次为 6564、5744、4854、5314 字节，均与声明一致；解析所得 PID/start_ticks、PPID、state/affinity 和时间字段与旁侧摘录一致。

三个活进程邻域为 [1]→[0]→[1]；另一个邻域为 [1]→Z态缺 affinity→该身份不再出现。前后多数行仅有字段摘录及 hash，只有上述四条异常行给出完整原字节。因此可说“核对了 Git 内的四条原始行字节和邻域身份”，不可说“亲读并重算了工作站全部 118 行资源流”。

第 787–799 行正确区分 watchdog summary 没有 launcher exit 字段，与 V5 compact 单独保存的外层退出码 2、2、0、2、2、0。字段 null 不表示 worker 退出未知或清理失败。第 805–904 行提供脚本快照路径/hash，但完整旧脚本未入 Git；“无直接 setter”“导入顺序”等仍是对原件的执行方读取记录，只有保存 cmdline 可作部分交叉核对。

### 5.2 D1/D2 身份、终态及费用

下表数值来自 Git compact 的实测记录；本审阅核对内部一致性、引用和求和， **未从工作站完整资源流重新计算峰值或清理结论** 。[CLOSE6，119–215、314–356、447–543、630–674 行][CLOSE6]

| 项目 / 单位 | D1 | D2 |
|---|---|---|
| worker PID / start_ticks / PPID | 4071459 / 284920539 / 4071446 | 4076967 / 284948743 / 4076949 |
| 导入后记录的 TID | 4071459、4071491、4071492 | 4076967、4077003、4077004 |
| 导入后 TID affinity | 三者均 [1]，仅该阶段快照 | 三者均 [1]，仅该阶段快照 |
| 成功 setter 总数 | 200：hwloc 196、libinfinipath 2、libpsm2 2 | 4：libinfinipath 2、libpsm2 2 |
| mask 统计 | [0] 6、[1] 10、其他 184 | [0] 2、[1] 2 |
| 资源行 / 成员观察 | 16 / 51 | 13 / 40 |
| probe / watchdog worker / outer exit | 23 / 23 / 2 | 23 / 23 / 2 |
| probe / watchdog 终态 | STOPPED_AFTER_IMPORT / WORKER_FAILED | STOPPED_AFTER_IMPORT / WORKER_FAILED |
| whole-watchdog / 秒 | 10.266887816600502 | 10.469862679950893 |
| 同时进程树采样 RSS 峰 / B | 161480704 | 160063488 |
| task VmSwap 采样峰 / B | 0 | 0 |
| global pswpin / pswpout 增量 / 页 | 0 / 0 | 0 / 0 |
| 后代终态 | descendants_cleared=true，剩余列表为空 | descendants_cleared=true，剩余列表为空 |
| 完整 ABI / pytest | NOT_REACHED / NOT_RUN | NOT_REACHED / NOT_RUN |
| 严格 CPU1 | NOT_PASSED | NOT_PASSED |

两个 launch_context_text 字符串的 SHA256 与各自引用相符；记录中的逐文件 source hash 可与固定 Git 文件核对。完整脚本原字节及 source snapshot 原件仍未访问，且第 3 节指出了汇总 false 的矛盾。

whole-watchdog 重新求和为 **20.736750496551394 秒** ，两次采样峰中的最大值为 **161480704 B** 。启动命令的 watchdog 阈值为 100 秒，低于每次 whole-watchdog 120 秒上限，符合预留清理时间的说明；没有将 120 秒解释为可在 100 秒停止门后继续工作的许可。

这两次按记录均在时限、8 GiB RSS、task VmSwap 和清理限额内；global swap 页增量另列，不与 task swap 混算。完整原件未核，不能升级为本审阅亲自复算的全过程资源 PASS。二者属于支持定位费用，包含 strace 观察开销，与旧 V5 的 84.84608844062313 秒、正式 PDE 成本和未监控静态工作分账；不构成同精度加速证据。次数 2/2 已耗尽，未用完的 240 秒不产生第三次权限。

### 5.3 系统调用、离散样本和推断必须分开

D1 的三份代表栈可以直接读到 orted/hwloc、主 worker 的 libinfinipath 与 libpsm2 调用。hwloc 代表栈来自 orted，不能把 196 次全都称作主 Python 或数值 worker 的 setter。D1 的 200 是完整原流的执行方汇总；Git 未逐条列全，本审阅不能重新枚举证明其完备性。成功 setter 数包含恢复到 [1] 的调用，不等于同样数量的偏离事件。[CLOSE6，217–264 行][CLOSE6]

D2 第 402–427 行列出四条成功调用，按时序为：

| trace 时间 / 秒 | 设置 mask | 返回值 |
|---|---|---:|
| 1792924496.505904 | [0] | 0 |
| 1792924496.634936 | [1] | 0 |
| 1792924496.913518 | [0] | 0 |
| 1792924497.103494 | [1] | 0 |

这四行已直接反证“全程 affinity=[1]”；不需要等待资源采样再次捕获。它们说明允许 CPU 集合发生了变化，不能仅由此推算 CPU0 上的实际工作量。两条 CPU0 调用还保存了完整代表栈，恢复调用只有 syscall 行；完整原 trace 未独立访问。

D1 第 706–743 行的两个资源成员为同一 PID/start_ticks，state=t、affinity=[33]/[30]。Linux 将小写 t 定义为 tracing stop，Z 为 zombie，两者不可混用。[LINUX_STAT] 这些字段摘录与 syscall 都支持本次发生偏离，但采样行时间、逐成员读取时间和 syscall 时刻不能未经原流重验就强行一一配对。

D2 的 13 行/40 条成员观察无偏离只是有限采样结果；它与短时 syscall 偏离并不矛盾。导入后多个 TID 也不直接意味着多个 MPI rank 或多个数值计算线程。

### 5.4 上游源码支持机制解释，但没有完成实机因果绑定

为减少下一轮盲试，本审阅直接读了三类 primary source：

- hwloc 2.10.0 文档第 1340–1348 行规定组件名前加负号表示禁用；topology-x86.c 第 1364–1420 行的 look_procs 保存原 mask、逐 CPU 绑定探测、最后恢复。因此 worker 局部设置 `HWLOC_COMPONENTS=-x86` 与本次观察到 hwloc setter 消失在机制上相容。它会改变补充拓扑发现，不能视为通用 CPU1 锁。[HWLOC_DOC] · [HWLOC_X86]
- intel/psm 固定提交的 ipath_time.c 第 52、112–132、189–191 行：加载期 constructor init_picos_per_cycle 保存 mask，临时选择 CPU0 做周期计时校准，随后恢复。[PSM_TIME]
- opa-psm2 固定提交的 opa_time.c 第 84、137–157、216–218 行有同类构造函数与绑定/恢复机制。[PSM2_TIME]

后两者与已提交 dlopen/MPI 初始化调用栈和两对 [0]→[1] 相符。但尚未将上游源码绑定到工作站实际 `libinfinipath.so.4.0 +0x39e2`、`libpsm2.so.2.2 +0x626a` 的包版本、Build-ID 和偏移。结论只能是 **有具体源码支持的机制解释，实机精确根因尚未确证** ；不能据此认定 V5 更早的三条历史 CPU0 样本也必由这些函数造成。

这也解释为何不能盲试常见“禁止 endpoint 绑核”的 MPI/HFI 参数：加载期计时构造函数未必受相同开关控制。下一步应先查实际库及加载链，不是参数矩阵。

## 6. 测试、ABI 与当前文档的资格边界

1. **20 项全部 NOT_RUN。** 两次 driver 在首个显式 dolfinx 导入返回后的检查点因 trace 证据停止；没有进入 pytest，不存在通过数，也不存在 S2 断言失败。不得将 V5 的 25 passed、30 passed/1 failed、局部 2 passed 拼接成当前 20 项或最终同字节通过。[RESPONSE6，11、22–24 行][RESPONSE6]
2. **完整 MPI/PETSc ABI 检查 NOT_REACHED。** 栈中出现 PetscInitialize、PMPI_Init_thread 表明导入已间接触发初始化；这与完整检查没执行并不矛盾。shell 的解释器路径、activation marker、MPI/线程请求和历史 complex128/int64/MUMPS 记录不能替代本轮实测。
3. **未监控静态检查另记。** closeout 第 681–692 行只报告 shell 语法和 JSON 解析，原逐命令 stdout 未留；S2 bytecode compilation 明确不作通过声明，wall/RSS 为 not_measured。本审阅自己的静态检查不补写成执行方测试。
4. **没有全仓、CI 或 production PASS。** 原全仓收集与 SLEPc/complex PETSc ABI 阻塞继续保留；本次不要求为 test-only 静态修复重跑全仓或完整 p6 FFCx witness。
5. **当前新增状态段落基本一致。** response、summary、manifest、registry、progress 的 V6 段均保留 NOT_RUN/NOT_REACHED/NOT_PASSED、2/2、5/6 和科学锁定；第 V6-04 项只要求收窄导航与完整性表述，不撤销真实历史通过记录。
6. **历史“104 项 hash 一致”不纳入本轮独立核验。** 该旧陈述没有持久逐项清单，本轮不能重复引用为亲自访问原件的证明。当前 197 个 Git blob 核对、两组 8 项字典核对与 ignored 原件核验是三个不同范围。

单文件原子保存、联合一致性 fixture、真实入口 mesh 前 sentinel，以及真实模型现场仍是不同层次。V6 没有修改生产 consumer，也没有部署新的联合读取防线；不能把 test-only 的 true 当作 official endpoint 授权。[MANIFEST6] · [V5]

## 7. 工作站仍需补核的具体原件

以下原件本审阅均未访问。其 hash 是定位和绑定信息，不是已亲读原件的证明。补核只读已有数据，不重新启动运行。

| 原件范围 | 已提交内容 / 本审阅实际核验 | 仍需工作站补核 |
|---|---|---|
| 六次 V5 support | S1、V5 两份 compact；四条内嵌资源原行字节、邻域摘录、18 项 hash 引用 | S1 driver_source_audit 指定的六组完整 shell/preflight/helper 快照；六份完整 resources/summary/worker.log；外层退出记录；完整 118 行及异常前后原行 |
| D1 run root | `benchmarks/artifacts/task43/v6_support/d1_affinity_trace_attempt1` 的路径/hash、3 个代表栈、统计、阶段与资源摘录 | driver_snapshot/run_d1.sh、probe_import_affinity.py；全部 strace/sched.*；probe_stages.jsonl、probe_terminal.json；watchdog/resources.jsonl、summary.json、worker.log；launch_command/context/launcher_exit 文件 |
| D2 run root | `benchmarks/artifacts/task43/v6_support/d2_hwloc_x86_disabled_attempt1` 的同类索引，另有四条 syscall | driver_snapshot/run_d2.sh、probe_import_affinity.py；全部 strace/sched.*；对应阶段、终态、资源、退出与清理原件 |
| 两次源码身份 | 固定 Git 的 8 个文件字节与 compact hash 相符；两组 snapshot 字典规范化后相等 | source_sha256.txt、source_snapshot_sha256.txt、source_snapshot/、source_head.txt、source_status.txt及生成两个 false 的原检查代码 |
| 实际动态库 | 栈中路径、无符号偏移与上游源码机制 | 实际 libhwloc、libinfinipath、libpsm2 和相关 OpenMPI 组件的只读包版本、ELF Build-ID、文件 hash/依赖与可取得源码对应关系 |
| 旧 A1/A2 数值场 | 当前 Git 历史审计与终态引用，未变化 | 原始场、向量、矩阵、资源及完整日志均未重验；V6 无需以 fresh PDE 或旧场重采样补造 |

D1/D2 run root 的工作站前缀为记录中 `/home/fenics/Projects/NN-Lab-V2/`。若原件不可取得，保持“未独立核验/原件缺失”的具体分类；不得为让这一表完整而重跑、重建 trace 或伪造旧脚本。

## 8. 科学能力与选择性合并

### 8.1 五项能力及正式额度

| 能力 / 额度 | V6 状态 | 依据与边界 |
|---|---|---|
| 空间 | PARTIAL | 既有 mixed-p 与局部 h 资格只覆盖原已验范围；没有新增多层 h、空间或真实数值见证 |
| 选择 | PARTIAL | accepted9/R9 为最后接受状态；R10 拒绝、无 transition10，后验控制不回流选择 |
| 精度 | NOT_PASSED | R9 为 110472 FE、对照 237600 FE，但独立精度仍失败；更少自由度不能与精度条件拆开宣布成功 |
| 同精度全过程成本 | NOT_ESTABLISHED | 支持诊断 wall 不是模型或完整研究成本；同一空间 q 稳定性、启动费用与不同生命周期耗时不能构成同精度优势 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 没有新的接线、迭代求解或 direct-equivalent 证据 |
| 正式预算 | 5/6；A1 2/2、A2 3/3，最后一槽封存 | 本轮新增正式 PDE/dispatch/attempt/READY 均为 0，不扩大、不跨组重分配 |

上述继承固定 summary 与历史 review 的限定，未在本轮重算数值。旧 A1_q2 在已构网/进入装配后因缺 ledger 被主控停止；旧 A2_q3 的 primary partial、extra 显式残差未严格下降、7200 秒停止、完整 endpoint 缺失和 LIMITED 清理边界均保留。V6 工程失败不证明 h/p 方法失败，工程修复也不证明独立精度通过。[SUMMARY6] · [V5]

### 8.2 合并按组裁决

| 组 | 文件、依赖与已审证据 | 本次资格 / 剩余阻塞 |
|---|---|---|
| 文档 / 轻量研究档案 | 本 review、response_v6、两份 V6 JSON、README/summary/manifest；registry/progress 的 Task43 补丁；所引用历史轻量证据 | 可在研究分支保留，并作为未来 docs-only 迁移候选。先关闭 V6-03/04 的当前解释问题；目标 clean base 和链接闭包未验，不授予此次实际 merge approval，不能整文件覆盖其他任务总账 |
| test-only 身份修复 | `src/test/test_task43_v3_failure_safe_order.py`；依赖 candidate_checkpoints writer、A2 fail-closed 实现及其既有导入链 | 静态实现接受，动态 20 项未运行；不能把这个大测试文件无依赖地搬入基线，也不能将 helper 升级为生产 consumer。未来迁移需精确 diff、目标依赖闭包和另行获准的直接节点证据 |
| 研究入口 | `benchmarks/task43_hp_adaptivity/h100_anchor.py`、`a2_native_p6_diagnostic.py`、candidate_checkpoints、native workflow/failure-safe tests、既有 ledger 与 native runner 依赖 | V6 未改动，维持 research-only。旧有限工程修复不撤销；无新现场端点或生产资格，不启用 A2_R/controller |
| reusable watchdog / 启动 | `benchmarks/subreaper_watchdog.py`、test_354、native capacity/ledger；tracked activation；本轮 ignored driver/probe | 旧 watchdog 证据按原版本保留。V6 未改 tracked watchdog/activation；实际导入链 CPU1 失败，局部 HWLOC 设置不是已验默认配置，不批准迁移为共享启动修复 |
| 数值核心及共享依赖 | manifest A–D 原子依赖组，含网格/axis/profile 前置及对应测试；尤其 common_3d_case_flow、dtn_port_3d、hcurl_variable_p_reduction、solve_maxwell_3d_stage_4b_block_grating | V6 无新数值变化或资格。旧 overlay 为 59/66 路径、核心共享 23/27 同字节的历史范围；四个变化共享文件未由该旧 overlay 资格化。不得以本轮 fixture 替代目标生产证据 |
| 整分支、旧 READY、未资格化默认路径、大型 ignored 原件 | 全 research branch 和尚未解锁研究项 | **Do-not-merge** ；本次不向 master 写入，不执行任何实际合并 |

本轮不存在可以自动执行的 selective merge approval。未来即使某一组取得明确 approval，仍须用户授权和后续 Codex 具体执行；研究档案保留、工程验收和生产批准不能混为一个 PASS。[MANIFEST6] · [V5]

## 9. 下一轮唯一允许范围：静态补核，新增运行额度为零

### 9.1 明确授权决定

**不批准继续运行型“有限非 PDE 诊断”。批准一次有限的既有证据只读分析、当前文档订正和一个未执行启动方案的交付。** 理由是已保存数据尚可回答具体问题：哪些 setter 被漏分类、两版 probe 是否只改了预期项、汇总 false 如何产生、实际网络库的加载机制是什么。在这些问题没有完成静态核对前，再给一个参数运行没有足够依据。

| 项目 | 新授权上限 |
|---|---:|
| 新支持 driver / 导入探针 / ABI 运行 | 0 次 |
| 新 watchdog 运行及其单次 / 累计墙钟预算 | 0 次 / 0 秒 / 0 秒 |
| pytest、collect-only、项目 fixture 或测试 helper 执行 | 0 次 |
| 正式 PDE / dispatch / attempt / READY | 0 |
| A1/A2 q 重试及封存 formal 槽使用 | 0 |

这不是把新运行改名为“静态检查”。只读文件解析、hash、源码差异和 ELF 元数据读取可以使用不导入项目或数值库的小工具；不得 source 并执行新启动链、dlopen 待查库、导入 dolfinx/MPI/PETSc、运行 pytest 收集或调用项目函数。不得安装依赖、改共享 activation、MPI/ABI、系统配置、cgroup 或其他任务环境。

### 9.2 一次有限补核交付

| 顺序 | 允许动作 | 可执行验收标准 |
|---|---|---|
| R1 完整分类已有事件 | 只读 D1/D2 已有全部 trace，形成轻量事件表 | 每个成功 setter 列 trace 文件/hash/原行号、时间、TID、target PID、mask、返回值、首个非 libc 调用库/偏移、可证角色及阶段；核对 200/4 总数与类别小计，区分 [1] 恢复和非 [1] 设置；未知不猜。若原汇总有误，追加更正并保留原值 |
| R2 核对已有启动脚本与库身份 | 读取两版完整 shell/probe、source/status/manifest/snapshot；读取实际库文件和包/ELF 元数据，不加载它们 | 提供两版关键原字节及静态差异，说明父子链、trace 同步/解析/停止位置和未到达测试节点；解释 V6-03。将网络库直接调用及加载入口与可取得源码绑定；无法精确符号化时写出限度，不以未证假设宣布根因 |
| R3 只提出一个局部启动方案 | 在 R1/R2 后，若证据足够，写出一个未执行 worker-shell 改动提案 | 说明针对哪一已确认加载路径、预期消除哪些 setter、对拓扑/通信发现有何影响、为何不改数值合同/共享 ABI；给出准确候选脚本 diff、拟用命令和新目录。不得落入共享默认，不列参数网格，不自动执行 |
| R4 文档收口后停审 | 一份 response_v7 和必要的新轻量补核记录，有限更新当前 README/summary/manifest/registry/progress | 明确静态已核、动态 NOT_RUN、ABI NOT_REACHED、CPU1 历史 NOT_PASSED及费用口径；关闭 V6-04；提交推送同一分支后停止等待新的审阅 |

只读处理限定于上述 8 次既有支持运行、与其直接相关的脚本/库和本轮元数据；不启动全仓扫描、环境摸底或新控制框架。单条只读处理最多 60 秒，批量解析/哈希等可计时处理累计上限 600 秒，结果保存小表或必要文本；不把它包装为新的 watchdog driver。未计时的人工阅读和静态操作如实记 not_measured，不补造全过程耗时。若原件缺失、身份不符、需要动态导入/安装才能继续，或只读处理触及该上限，记录缺口并结束本轮，不另开运行。

S2 代码本轮无需进一步修改；原 20 个节点保持待验证，不能为了拿到通过而绕过资源/ABI前置。未来如申请一次动态确认，必须先审阅 R1–R3 的具体方案，另行给出新增支持额度、唯一目录/命令、CPU1/MPI1/单数值线程、RSS≤8 GiB、task swap=0、时限、失败不重试和清理条件； **本段只是未来申请所需材料，不是条件满足后自动生效的许可。** 未来最小目标可限定为第 4.2 节四个 selector，共 20 项；本次没有获准执行的测试节点。

不顺带加入 A1 真实-main sentinel：当前 strace 包裹改变直接父进程拓扑，不能为了附加测试再次弱化实际 watchdog 父身份或重现 V5 拓扑错误。若未来确需该节点，必须独立说明真实父链及测试目的；它不是这 20 项身份 fixture 的必要前提。

### 9.3 正式计算及全部下游继续锁定

A1/A2 q 重试、A1_R、A2_R、B、C、fresh baseline、同精度全过程成本 campaign、迭代接线、0.7 nm、NN/FTT 均不批准。最后一槽没有自动使用权，支持诊断的修复或 fixture 成功也不解锁它。

未来正式计算申请必须另行说明科学问题、为什么已有 partial 不足、固定输入、唯一模型/目录/命令、具体 attempt 与组/总额度调整、共同及分支入口 Gate、资源停止规则和必须持久化的完整端点。R/B/C 还须满足原冻结依赖和合格前置端点；同精度成本须先有独立精度资格和可比生命周期，迭代须有合格空间/端点与单独接线授权。不能用新工程支持结果替代这些条件。

## 10. 正式结论

本轮修复了一个明确的测试内身份缺值漏洞，并留下了能够解释部分 affinity 现象的负向证据。应承认这部分工程进展，同时明确 D2 没有完成必要的放行前审查，当前 CPU1、完整 ABI 和最终测试资格均未建立。

本次接受 S2 的静态实现和限定范围的研究档案，工程总体验收为部分接受；不新增 driver 或正式计算，不授予生产/整分支合并批准。下一步只有第 9 节的静态补核与待审提案。所有旧精度失败、accepted9/R9、R10 拒绝、extra 严格下降负项、资源终态、配额和冻结规则保持原样。

## 固定证据与上游资料

下列仓库代码和当前文档链接均固定到 cab17f5…；行号以该提交原文件为准。V5 权威链接固定到正式 review 提交。上游资料只支持接口语义和候选机制，不替代工作站原件、实际构建身份或运行资格。

[DIFF6]: https://github.com/Rookie1234567/MyFEniCS/compare/b5a4b69c25c6be92faf0116e119904c438cbe297...cab17f542bfffeb6598eedfed3194d07ea047630
[V5]: https://github.com/Rookie1234567/MyFEniCS/blob/b5a4b69c25c6be92faf0116e119904c438cbe297/docs/task43_hp_adaptivity/review_report_v5.md
[RESPONSE6]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/response_v6.md
[CLOSE6]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/outcomes/records/v6_affinity_support_closeout_v1.json
[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/outcomes/records/v6_s1_v5_support_affinity_context_v1.json
[CODE]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/src/test/test_task43_v3_failure_safe_order.py
[VALIDATION5]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/outcomes/records/v5_focused_validation_v1.json
[RESOURCE5]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/outcomes/records/v5_root_resource_recheck.json
[README6]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/README.md
[SUMMARY6]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/outcomes/summary.md
[MANIFEST6]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md
[REGISTRY6]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/development_model_registry.md
[PROGRESS6]: https://github.com/Rookie1234567/MyFEniCS/blob/cab17f542bfffeb6598eedfed3194d07ea047630/docs/development_progress.md
[HWLOC_DOC]: https://github.com/open-mpi/hwloc/blob/hwloc-2.10.0/doc/hwloc.doxy#L1340-L1348
[HWLOC_X86]: https://github.com/open-mpi/hwloc/blob/hwloc-2.10.0/hwloc/topology-x86.c#L1364-L1420
[PSM_TIME]: https://github.com/intel/psm/blob/e5b9f1cbf432161639cb5c51d17b196c92eb4278/ipath/ipath_time.c#L112-L198
[PSM2_TIME]: https://github.com/cornelisnetworks/opa-psm2/blob/be99e35465b0de6a37d9c30408256f1dc5b12ea6/opa/opa_time.c#L137-L224
[LINUX_STAT]: https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html

