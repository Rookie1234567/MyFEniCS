# Task43 正式审阅 V8：保留准备负项，恢复同一未消耗的 D3 条件许可

审阅日期：2026-10-25（Asia/Singapore）。固定被审提交：`c245dd060882df4dc6f30224ac0fa8be93f764d2`。本报告只审查提交内容和静态证据，没有执行候选 sanity、原生导入、ABI、pytest、collect-only、支持 driver、旧场处理或 PDE；没有修改既有 review、冻结合同或失败记录，也没有合并分支。

## 0. 正式裁决

**本轮部分接受：接受文档、勘误和有访问范围限定的准备负项归档；不验收为“静态准备完成”或“D3 已资格化”。本轮阻止 D3 启动是正确的，因为输入、依赖、sanity 和源码冻结均未完成。提前生成固定文本违反 V7 明确顺序，但不会使这些字节永久失效；机械复制失败也不是 sanity、ABI 或 driver 失败。**

**本报告明确批准继续有限静态准备、执行尚未使用的一次无 native sanity，并在新前置门全部满足后，恢复原来尚未消耗的同一个 D3 支持许可。D3 仍为 0/1，不新增第二个槽位，不重置 V6 已用支持次数。** 使用现有唯一候选目录、原 hash、原输出 root 和原命令；不能通过删除、改名或重演历史失败来制造“原顺序通过”。准备合格后直接完成这一轮，不再为相同范围重复申请许可。

| 裁决对象 | V8 结论 |
|---|---|
| 文档、当前状态与勘误 | **接受，带限定**；没有发现把静态核对扩大为科学或生产 PASS |
| 受控停止证据 | 接受“不启动”的决定和执行方承认的顺序/监督偏差；完整操作与停止时序 **未独立复原** |
| 工程准备 | **部分接受 / 未完成**；15 项 ELF 摘要不是完整输入和依赖核验 |
| 当前资源 / ABI / 测试 | V8 没有资源实测；历史 strict CPU1 仍 NOT_PASSED；本轮完整有限 ABI NOT_REACHED，sanity/native/20 项均 NOT_RUN |
| 静态续接与 sanity | **批准**，限第 9 节；只用一次尚未执行的 sanity，失败不得边改边重跑 |
| D3 及固定 20 项 | **有条件恢复原 0/1 许可**；第 9 节前置完成后可执行一次，20 项仅在同次前门满足后执行 |
| 正式 PDE / 下游 | **不批准**；正式 5/6、A1 2/2、A2 3/3，最后一槽封存 |
| 合并 | **没有本次实际 merge approval**；档案可保留，生产资格另判，仍不执行合并 |

本报告第 9 节是下一轮统一执行决策；V7 第 9.3–9.6 节、固定脚本和附录 A 作为被引用的冻结规格继续有效。关于“现有候选怎样恢复、静态错误怎样处理、次数如何计费”，以本报告的明确说明为准，不另建平行 addendum、controller 或新合同。

## 1. 身份、实际差异与审阅范围

| 身份 / 范围 | 直接核对结果 |
|---|---|
| 仓库 / 唯一执行分支 | `Rookie1234567/MyFEniCS` / `task43_hp_adaptivity` |
| 固定被审 SHA | `c245dd060882df4dc6f30224ac0fa8be93f764d2` |
| 固定 tree | `17dbec24b66cbf53ebef3a1a1f067c63cc9b8e4c` |
| 直接父 / 原执行权威 | `dc6c3c59cabebefec76f928f261a25670a2a8857`，正式 V7 review |
| 长期代码基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4`；本轮没有新的数值源码变化 |
| 远端 | 审阅开始时准确指向固定被审提交；提交本报告前再次核对，以预期旧 SHA 保护更新，不覆盖后续工作 |
| 工作站 worktree | 干净及 origin 0/0 属交付方报告；本审阅未登录工作站亲证 |
| 实际差异 | 1 个提交、8 个路径，全部在 `docs/`，增加 488 行、删除 11 行 |
| 历史保护 | diff 没有涉及旧 review、合同、失败 records、测试、数值代码、watchdog 或 activation |

8 个变化路径是本轮 response、401 行 closeout JSON，以及 Task43 README/summary/manifest、仓库 docs README、模型总账、开发进展。主控/代理是谁、使用何种模型，不改变证据门槛。[固定差异][DIFF]

已完整阅读三层 AGENTS、仓库工作原则、任务书、V7 执行规则及附录、本轮 response/closeout；核对当前导航、汇总、manifest、总账和进展的完整补丁与相关上下文。审阅缓存的 211 份文件逐一与固定 tree 的 Git blob 身份相符；相关测试和启动器直接按文本检查，没有导入它们。另读文档渲染标准并对本报告做文档静态检查和 GitHub 渲染核对，未将这些检查记为 pytest。

下文短名 `closeout` 指 `docs/task43_hp_adaptivity/outcomes/records/v8_d3_preparation_closeout_v1.json`；`response`、`README`、`summary`、`manifest` 分别指本任务当前文件。除明确标注上游源码或 V7 review 外，行号均固定于本次被审 SHA。

## 2. 审阅者实际核到了什么

| 材料 | 本审阅直接核验 | 不能由此推出 |
|---|---|---|
| 两份机械准备脚本 | 从 closeout 内完整行数组重建文本，分别与所列脚本 SHA 相符；静态检查失败位置、后续复制和恢复行为 | 未亲见工作站脚本执行、退出码文件或原始 stderr |
| 两份 patch | Git 中候选 patch 与 V7 附录原文本的字节数、SHA 对应 V8 归档引用 | 未读取工作站归档副本 |
| 两份候选 | 记录中的目标 hash 与 V7 冻结目标相符，机械操作与得到这些字节相容 | 未读取实际 `/tmp` 或 ignored candidate_draft 文件；没有执行 sanity |
| 15 个 ELF 摘要 | 路径唯一、SHA/Build-ID 格式正确；前 12 项各字段与 V7 表相同；3 个新增插件的 NEEDED 缺口可直接识别 | 未读取安装文件或原 readelf stdout；没有历史 mapped-file 证明或实际加载/ABI 证明 |
| 计时 | 独立用十进制定点算术核对小计，检查没有重复把 subtotal 加一次 | 不是亲测进程 wall，更不是全轮、D3 或同精度 PDE 成本 |
| 不运行结论 | 与已提交命令、状态和差异一致，没有把候选创建当执行 | 未现场核实际进程、输出 root；Git 文件本身不能证明任意外部命令从未发生 |
| 主控核对 12 项原件 | 12 个引用与其文本/字段可做有限交叉核对 | `mismatches=[]` 是执行侧复核记录，不是本审阅访问了 12 份原件 |

可重建的两份脚本分别是：

- `mechanical_prepare.sh`：1410 字节，SHA256 `ceeeace0abdfa7b0200e47946aa6ecb9a08c3d6bd63dc43bac6c435f4f7bfc9b`。
- `candidate_relocate.sh`：969 字节，SHA256 `d6875199fb9705674bdfe23c0f09ac6462b04a50fae1edf4f0d9d263c3bd6091`。

两条 patch stdout 和由既有字段重建的 relocation hash 输出也与对应引用一致。这是**提交文本的内部绑定核验**；可重建输出不等于亲见执行。完整原始输出仍标“未核验”。[closeout:298–399][CLOSE]

## 3. 按严重程度排列的问题与验收标准

### V8-01 · P2：输入、直接依赖与最终源码冻结未完成，当前不能立即派发 D3

**位置：** closeout:62–80、228–266、396；response:23、33；V7 review:250、253。

15 个 ELF 对象只是识别出的二进制文件及其静态属性。NEEDED 是文件声明要链接的库名，不是已经查明该库最终来自哪个实际文件。当前特别缺少：

| 已列插件 | 仍需绑定的关键直接依赖 | 为何不能用旧表代替 |
|---|---|---|
| `mca_mtl_psm.so` | `libpsm_infinipath.so.1` | 它与已列的 `libinfinipath.so.4` 不是同一个名字；需查其自身 realpath、身份和 NEEDED |
| `mca_mtl_psm2.so` | `libpsm2.so.2` 到已列版本文件的映射 | 版本文件存在不自动证明该 SONAME 在当前搜索路径中绑定它 |
| `mca_btl_ofi.so` | `libmca_common_ofi.so.10`、`libfabric.so.1` | 两项均不在 15 个对象身份表中，不能跳过装载链的中间对象 |

activation/MCA、插件发现和 ELF 元数据三个检查步骤的脚本与 stdout 只留 ignored 原件引用；response 所摘 `mtl=^ofi`、`btl=^uct,openib,ofi`、`pml=^ucx` 没有取代完整来源、覆盖优先级和 worker 输入核查。源码冻结也明确 NOT_COMPLETED。

**影响：** 即使候选顺序正确、hash 正确，这些缺项仍足以阻止现在启动。它们是准备缺口，不是环境已被证明损坏。

**最小整改 / 验收：** 按第 9.2 节补齐有限的实际输入及依赖映射、保存可审命令/必要输出/退出码，确认相关输入没有未解释覆盖；再绑定 8 项固定源码及实际 HEAD/status/diff。不要扩成系统全库递归清查、provider 扫描或环境重建。旧表中“未收录”不等于机器上“缺库”。[closeout][CLOSE] · [V7 权威][R7]

### V8-02 · P2：明确的准备顺序偏差必须保留，但机械恢复与永久失效被混在同一停止解释中

**位置：** closeout:24–29、301–320、351–371；response:3、9、15、21、35；V7 review:243、247–255。

V7:247 明文要求按顺序完成；250 行是实际输入核验，251 行才是构造候选。因此提前生成是执行代理的顺序偏差，主控没有及时在步骤转换处拦住也有责任。不能用最终 hash 一样把历史顺序改写为通过。

但以下三件事必须分开：

1. **提前生成：** 违反程序顺序，未触及模型或运行，没有自动造成候选内容污染。
2. **首次 cp 失败：** patch 实际改了临时 `preserved-D2` 副本，后续却从未生成的 `proposed-D3/run_d3.sh` 复制。保存脚本有 `set -e`，与 exit 1 后未执行 hash/wc 相符。这是具体、可局部修复的文件路径错误。
3. **relocation：** 先保存 patched 中间件，再复制到规定候选路径，最后从 tracked 原件恢复临时 D2 副本。脚本文本没有导入、测试、driver 或 PDE，也没有改 tracked 历史归档。这不自动构成未经授权的新方案或 driver 重试。

**对停止的裁决：** 冻结 D3 启动正确；作为一次保守收口暂停送审可以接受。把顺序偏差解释为“相同候选永久失效”或“剩余只读核验也必然不可继续”，没有数值或证据上的必要，属于过度保守的延伸。V7 对已提前产生固定文本的恢复办法没有写清，本报告补足这一边界；不能用停止代替把原本可完成的有限工作做完。

**验收：** 原 V8 FAILED_BY_ORDER 和监督责任保留；只在新记录中建立当前时间的输入核验、候选采用、sanity、源码冻结顺序。复核并前瞻采用现有固定候选，不删除重建以伪造“第一次就按序完成”。D3 仍 0/1；未调用唯一 launcher 的机械命令不消耗 driver。[根规则普通错误处理][ROOT] · [任务执行规则][TASKRULE] · [V7:243–255][R7]

### V8-03 · P3：Git 证据不足以独立重建主控发现、停止与 relocation 的先后

**位置：** closeout:24–29、37、269–282、389–399；response:15、21。

记录承认提前生成，给出了两个机械脚本、退出码与局部计时，但没有带来源的全局事件序列、主控停止指令锚点或可靠时间戳。`candidate_regenerated_after_stop=false` 不能自行证明所有候选整理均在禁令前；文件操作时间也不能被臆造为控制消息时间。

**影响：** 可以接受责任承认和不运行结论的记录，不能声称主控及时停止已由外部原件完整验证；也不能因缺证据反向指控“停令后违令恢复”。当前 12 个 hash 引用没有覆盖所有 stderr、exit、time、targets 文件；三个静态检查步骤只有路径/hash，外审可读性仍有限。

**最小整改 / 验收：** 从现存工具历史和原件只读提取一张短事件表：操作、原命令/消息来源、已知顺序、退出结果、时间是否可靠。能找到停止消息就绑定摘录；找不到标 UNKNOWN，不补造时间，不重演失败。下一轮把必要的输入检查命令、关键 stdout、退出码及其原件身份放入同一轻量记录。历史无法恢复的时间本身不无限期阻止前瞻工作；新的当前前置必须有可核身份。

### V8-04 · P3，非启动阻塞：个别导航和计时展示仍需避免误读

**位置：** README:80；closeout:283–296；response:27。

README 历史段末仍写“V7 当前状态见上文”，下一次正常文档收口改为指向最新当前段即可，不为此另开测试或审阅轮。账面和 `9.464030618` 算术正确，但其中多条计时文件只到 0.01 秒，不能理解为整批动作均有纳秒测量精度。保留原值，正文称“已明确计时步骤约 9.464 秒”，无需重测。

## 4. A：停止、机械失败、恢复与次数的独立判断

| 事件 / 判断 | V8 实际证据 | 审阅分类 |
|---|---|---|
| 输入核验完成前生成候选 | 执行方承认，V7 顺序明确 | 准备顺序不合格；完整现场时序未核验 |
| patch 后复制不存在路径，exit 1 | 嵌入脚本及混合摘录相互一致，错误位置可定位 | 机械准备失败；不是 sanity 断言失败、ABI 失败、环境失败或数值失败 |
| 移动既有 patched 字节、恢复临时 D2 | relocation 完整文本及预期输出身份可审 | 机械整理；未显示 tracked 历史改写；是否位于 STOP 前缺独立时序 |
| 两次路径输出含字面量反斜杠 n | 已留失败格式声明和最终输出身份 | exit 0 不代表输出格式合格；可局部修正，不是 driver |
| 主控先读不存在 timing ledger，exit 1 | `&&` 后 hash 命令未执行，另有独立 hash 动作 | 读取顺序错误；不能把后续成功冒充该失败命令的结果 |
| 不启动 D3 | 输入/依赖不全、sanity 未运行、源码冻结未完成 | 正确；即使没有顺序偏差也不能启动 |
| 将未用 D3 视为已消耗或永久取消 | V7 仅以唯一 launcher 开始执行计数 | 不成立；仍 0/1，下一步按本报告前瞻恢复 |

临时目录叫 `preserved-D2` 不等于 tracked 历史原件。操作它的副本后保留 patched 中间件、恢复副本，不是改写仓库历史；本轮 diff 也没有相关历史文件变化。相反，任何旧 record、合同或真实原始日志都仍不可覆盖。

原 `mechanical_prepare.sh` 的 `test ! -e "$prep"` 是该准备脚本自行设置的“候选目录须不存在”检查。V7 要求不存在的是正式输出 root，允许在唯一脚本目录准备文件。**恢复时不要重新执行这份失败准备脚本**，否则合法保留的目录会再次触发机械失败。[closeout:307–318][CLOSE] · [V7:274][R7]

## 5. B：ELF、输入、费用与工作站补核范围

### 5.1 15 项摘要的结论

15 项路径唯一，64 位 SHA256 和 40 位 Build-ID 格式正确；前 12 项 path、SHA、Build-ID、NEEDED、package、version 与 V7 逐字段相同。新增 3 项是两个 PSM MTL 插件和 BTL OFI 插件。没有发现摘要内部的转录漂移；**这些一致性不证明当前实际文件未变，也不证明历史进程加载了它们。**[V7 装载表][LOADER7] · [V8 表:81–265][CLOSE]

普通系统配置里 `pml=^ucx` 与 worker-local 请求 `ob1` 不必然冲突。已核的 OpenMPI 4.1.6 上游源码中，override 文件优先于环境，环境优先于普通参数文件；长环境名与短环境名也需区别。因此不能仅凭两个字符串不同停机，也不能只看当前父 shell 的变量 unset 就认定 worker 输入合格。要查**实际来源与优先级**；上游源码仍不是 Ubuntu 安装文件的历史映射证明。[MCA 初值优先级:1799–1818][UPVARORDER] · [长短环境名及 override:1631–1655][UPVARENV]

V7 已核的“PML 组件筛选先于 CM 相关加载”机制仍提供一次 OB1 确认的理由。本轮没有新运行推翻或验证它；无需再加一种参数假设。BTL/OFI 或其他路径可能仍导致 setter，失败后不得立即扫描其他 MCA 参数。

### 5.2 费用重算与非运行状态

| 计费组 | 已提交数值，秒 | 审阅 |
|---|---:|---|
| 七条有原计时文件的命令 | 0.03 + 0.05 + 0.05 + 0.11 + 0.06 + 0.06 + 8.91 = 9.27 | 算术一致 |
| 从保存 stdout 提取 ELF 摘要 | 0.07547461 | 不等于重新扫描或加载 ELF |
| 主控独立候选 hash 动作 | 0.084304108 | 与先前 ledger 读取失败分列 |
| 主控 ledger 读取失败 | 0.0342519 | 失败费用保留 |
| 已明确计时动作之和 | 9.464030618 | 未见 subtotal 重复相加；约 9.464 秒 |
| 首次提取、人工阅读及未独立计时操作 | not_measured | 不补造；后续文档/Git 收口也非已测全生命周期 |
| D3 whole-watchdog / RSS / affinity / swap / cleanup | NOT_RUN / 无本轮实测 | 不能由静态时间或未创建 root 推成资源门通过 |

D3 计数与准备费用分账是正确的。没有新增 dispatch、sanity、native import、完整 ABI、20 项测试或 PDE 的已提交运行证据；记录明确它们未运行/未到达。该小计不能用于数值加速、同精度成本或工作站资源验收。

### 5.3 尚未亲读的工作站原件：明确清单

下表所有工作站原件均为**本审阅未核验**。下一轮优先读取现存原件补最小摘录，不要求重跑旧命令或重审八个历史 support 根。

| 原件位置（相对 canonical worktree，除注明外） | 待补核内容 |
|---|---|
| `benchmarks/artifacts/task43/v7_preparation_audit/raw/activation_mca_inspect.*` | 原 shell、stdout/stderr、exit/time；实际读取了哪些 activation、参数文件与环境 |
| 同目录 `plugin_discovery.*`、`elf_static_metadata.*`、`elf_static_targets.txt` | 命令、对象来源、15 项摘要、原退出状态；新增相关依赖另记当前读取 |
| 同目录三版 `v7_elf_paths*` | 两次格式失败及最终 12 行输出；首次命令/计时未保存的缺口保留 |
| 同目录 `mechanical_prepare.*`、`candidate_relocate.*` | 分开的 stdout/stderr/time 与 exit；两份完整脚本和中间件保留 |
| 同目录 `initial_git_status.txt`、`initial_head.txt`、`branch.txt`、`upstream.txt` | 当时身份；不能用现在状态代替旧状态 |
| `benchmarks/artifacts/task43/v7_preparation_audit/candidate_draft/` 的四文件及 `/tmp/task43_v7_d3_proposal/` | shell、probe、两 patch 的真实字节；旧 patched 中间件和恢复后 D2 副本 |
| 现存控制消息 / 工具调用历史 | 主控何时发现并禁止进一步操作；缺失则 UNKNOWN |
| 对应安装 ELF、activation 和参数文件 | 当前实际 path/realpath、来源及 hash；仍不等于历史进程映射 |
| 唯一 D3 输出 root 及对应进程情况 | 启动前确认未存在、没有同名已启动工作；本审阅未现场确认 |

## 6. C：勘误、当前文档和历史保护

V7-03/04 的订正在 response:29 正确：PMIx setup 对应已保存的 Python TID 4071459 栈；已保存 orted TID 4071475 栈只支持 opal/hwloc、ess_hnp、orte_daemon 这条链，未作“所有 orted 栈均不含 PMIx”的过强断言。CM 加载位于 MPI 初始化链内部，不称初始化之前。100 秒工作停止与 120 秒含清理上限分开，未追溯延长历史运行，也未称本轮实测通过。[response][RESPONSE]

README:66–80、summary:3–17、manifest:3–14、总账/进展:3–5 和 docs README 的当前 Task43 入口，均保留准备未完成、零 dispatch、未运行测试、五能力原状态和无合并资格。V7/V5 的主要旧当前标题已归入历史；README:80 小导航遗留按 V8-04 处理。docs README 删除/更新的是当前导航摘要，没有删除历史失败原件。[README][README] · [summary][SUMMARY] · [manifest][MANIFEST] · [总账][REGISTRY] · [进展][PROGRESS] · [docs 导航][DOCS]

本轮归档值得保留，但不能把“原件列了 hash”“当前 JSON 可解析”“主控说一致”当作完整启动链、生产 ABI 或科学精度通过。没有发现当前文档作出这种资格扩张。

## 7. 测试与五项科学能力

测试文件 `src/test/test_task43_v3_failure_safe_order.py` 实际 SHA256 仍为：

`52f94e28306d2d7f83f602c5e654c8953e544f00091ae3013378d52d040b7a43`

其非空/长度/十六进制身份检查、共同缺失身份反例、12 个独立否决例和 3 个 writer 故障例未变化。四个允许 selector 静态展开仍为 1+4+12+3=20；反例重新绑定引用和 hash、保留原 primary 字节的逻辑没有被本轮改动。**全部仍 NOT_RUN，没有 collect，更没有用历史通过替代最终字节验证。** 测试内合成联合读取 helper 仍不是已部署生产 consumer。[固定测试][TEST]

| 能力 | 状态 | 本轮不能改变它的原因 |
|---|---|---|
| 空间 | PARTIAL | 无新 local h、mixed-p、多层联合空间数值见证 |
| 选择 | PARTIAL | accepted9/R9 仍最后接受态；R10 拒绝未回写 |
| 精度 | NOT_PASSED | 原独立精度失败未解决；候选文件与支持测试不验证空间解 |
| 同精度全过程成本 | NOT_ESTABLISHED | 没有新同精度合格端点；静态支持费用不是数值全过程 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 未接线、未运行 direct-equivalent 迭代核验 |

R9 的低于对照 DoF、R10 的有限离散比较，以及历史 A1 受控停止、A2 primary partial/extra 负项、未完整端点和 LIMITED 清理结论，均保留原适用范围。这里不重新计算这些结果。正式总额 5/6、A1 2/2、A2 3/3、最后一槽封存不变。

## 8. 合并资格单独裁决

| 依赖组 | V8 判断与剩余阻塞 |
|---|---|
| 文档 / 轻量证据 | response_v8、closeout、当前导航/汇总和本 review 可保留研究档案；未来 docs-only 迁移须连同限定和链接依赖，总账只迁 Task43 段落。**本次没有实际 merge approval** |
| test-only | 固定测试静态可审，20 项未执行；不能凭文档取得动态或生产资格，不能脱离 checkpoints/A2 导入依赖单文件搬走 |
| 研究入口 | h100/A2/checkpoints 与 native runner 显式诊断路径本轮未变；无新完整现场端点，维持 research-only |
| 共享启动 / watchdog | 仍沿用旧版本证据边界；临时 OB1/HWLOC 设置不能迁入共享 activation 或默认配置 |
| 数值核心 | 无 V8 数值变化或 fresh PDE；旧 overlay 部分失效和相关核心共享文件资格缺口继续存在 |
| 整分支 / 大型原件 / 未验默认 | 不整体合并，不提交大型 ignored 原件，不提升 production default |

支持诊断或 20 项未来成功不自动改变上表。实际合并仍需独立明确的 merge approval、用户授权及后续 Codex 执行；本轮不合并。

## 9. 下一轮统一授权：补完准备，采用现存候选，恢复同一 D3

### 9.1 许可、次数与恢复含义

**批准继续有限静态准备；批准一次尚未执行的无 native sanity；在以下门全部满足后，批准恢复同一个尚未使用的 D3，及同次运行中的固定 20 项测试。** 这不是新加第二个 D3、不是恢复 V6 额度，更不是正式 PDE。

历史 V8 顺序失败保持。新记录从本报告起建立“实际输入/依赖完成 → 采用现存候选 → sanity → 当前源码冻结 → 唯一 launch”的前瞻顺序。主控必须逐步阅读实际结果，不能只接收代理 PASS 标签。前门合格后直接完成授权工作，不再以已经登记的旧顺序偏差要求额外审阅。

静态操作仍每条≤60秒，按 V7 的累计已测静态上限600秒记账，已有9.464030618秒不归零；可计时的后续操作继续累计，not_measured单列。不得把账面剩余时间当第二次sanity或driver许可，也不得声称由此得到整轮总wall。

### 9.2 S1：先补实际输入、有限依赖与可外审摘录

1. **保全并厘清历史。** 读取第5.3节已有原件，补短事件表、两机械脚本的现存原始退出/输出和可恢复的停止指令来源。无法恢复的旧时间或命令写UNKNOWN/未保存。禁止重演失败来生成“原日志”。原件可复用，不全量重核八个旧support根。
2. **核实际启动输入。** 只读核 tracked activation 及其实际 source 的现存venv activation、相关环境长短变量名、用户/系统参数、override/参数文件选择来源。保存相关原文本、路径/realpath、hash、命令/退出码。允许的干预仍仅固定worker-local两变量；不能清除或改写共享配置。普通低优先级的 `pml=^ucx` 不因字面不同自动否决；发现实际高优先级覆盖、activation改写、输入漂移或无法解释来源才停止。
3. **完成有界依赖映射。** 复用15项仍能核对的原元数据，必要时只读重核当前身份；对这15项的直接NEEDED给出SONAME→实际path/realpath的映射，已有对象复用。补齐 `libpsm_infinipath.so.1`、`libmca_common_ofi.so.10`、`libfabric.so.1` 三个关键桥接对象的hash/Build-ID/包/NEEDED及其直接映射，核已有libpsm2/MPI/PMIx别名。对直接出现的系统基础库仅登记当前解析位置/包来源，不递归全系统，不扫描所有provider。相关边找不到、身份歧义或解析受未解释搜索路径影响则停止；缺表项不能冒充缺库。
4. **静态工具与错误范围。** 只用文件读取、哈希、包数据库、`readelf`等不加载被查库的手段；不用`ldd`、`ompi_info`、native导入、安装或重新构建环境。普通读取命令的路径/转义/输出格式或记录schema错误，可在预算内局部修正并只重做该静态步骤，保存每次失败；这种修复不自动终止整轮、不计sanity或driver。不得借“格式修复”修改候选、测试、数值输入或忽略实际身份冲突。

历史不可恢复的小计/控制时间本身不是永久启动阻塞；当前必要原件、实际输入和候选身份不可核则是阻塞。该区别避免为补一条无法追溯的旧时间而停止所有实质工作。

### 9.3 S2：在原目录前瞻采用现存固定字节

保留唯一目录 `/tmp/task43_v7_d3_proposal`。**不要重跑 `mechanical_prepare.sh`，不要重新应用patch，不删除、清空或改名现有目录以绕开其错误的不存在检查。**

主控独立核该目录与durable candidate_draft两份候选的字节、大小和hash。核对通过后，在新preflight写“当前采用已有固定草稿”，并引用原V8失败，不写“历史生成顺序通过”。

若/tmp已自然消失，仅允许从V8持久候选归档恢复缺失的同名文件到同一路径，恢复前核归档准确字节、恢复后再核；不覆盖任何存在且不同的文件，不重造patch，不另选目录。若归档也缺失、任一现存候选hash不符或新方案才可运行，保全现场并停止。

| 固定对象 | 不可改的身份 |
|---|---|
| shell | `/tmp/task43_v7_d3_proposal/run_d3.sh`；4166字节；SHA256 `e84d2eb0bfcd257549fcd85b336d5ce9ea5f8faa72eef5261e7ca936d076127a` |
| probe | `/tmp/task43_v7_d3_proposal/probe_import_affinity.py`；14891字节、371行；SHA256 `fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4` |
| 来源 | V7保存D2 shell加既有候选patch；D2 probe加V7附录A。历史D2与两份patch原字节不变 |
| 输出root | `/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1`；启动前必须不存在 |

候选目录已存在是本次明确允许的事实；正式输出root已存在仍是拒绝条件。两者不可混淆。启动前只读核相关现有进程/身份，确认没有已启动的同一D3；不终止其他任务。

### 9.4 S3：一次无 native sanity，然后冻结实际源码

**允许尚未执行的这一次 sanity。** 仅用stdlib/AST/合成字符串，按V7附录A验证完整CPU1记录、非CPU1、失败调用、unfinished/resumed、未知mask、栈帧和不明token分类；核实际PML字段和检查顺序。只提取需要的解析函数/文本，不执行probe顶层/main，不导入numpy、dolfinx、MPI/PETSc或项目模块，不读取真实进程trace来冒充合成sanity。

唯一sanity验证命令开始执行即计这一次；若解释器或断言未到达，相应项仍记NOT_RUN，但本轮不得另发第二次sanity命令。启动、解析或断言失败均保存实际到达点，停止进入D3，不修改候选或换名再跑。不把尚未运行的断言记作失败，不将静态文件hash检查计作sanity。执行前可以人工审查sanity文本，减少机械错误；不得预先另跑一套等价验证来绕过一次限制。

sanity成功后，绑定固定8项source路径：`h100_anchor.py`、`a2_native_p6_diagnostic.py`、`candidate_checkpoints.py`、`src/io/native_capacity_profile.py`、固定test文件、watchdog、tracked activation、`workspace_environment_v1.json`；完整路径以保存D2 shell:12–21为准。与本次固定提交对应字节逐项比对，尤其测试SHA保持本报告第7节值。[固定source_paths][SHELL2]

实际HEAD可以包含本review和有限文档提交，但不得忽略代码漂移。保存branch/upstream、HEAD/status/diff、manifest和实际候选hash；前置快照另有不可后验替换的原件/hash。新轻量preflight标明本review SHA、V7冻结规格引用、原0/1余量、旧顺序负项及当前全部前门结果。缺项或冲突不得写READY、不得启动。

### 9.5 S4：唯一D3及资源门

| 项目 | 唯一允许范围 |
|---|---|
| 工作区 / 分支 | `/home/fenics/Projects/NN-Lab-V2` / `task43_hp_adaptivity`；canonical worktree核对通过 |
| 唯一命令 | `bash /tmp/task43_v7_d3_proposal/run_d3.sh` |
| 次数 | 原D3 **0/1 → 最多1/1**；唯一命令开始执行即消耗。目录/shell/preflight/导入/ABI/测试失败也计数，无重试 |
| worker-local输入 | `HWLOC_COMPONENTS=-x86`、`OMPI_MCA_pml=ob1`；保留原变量键、唯一root和trace路径；不改共享activation |
| CPU / MPI / 线程 | affinity严格[1]；MPI world size1；OMP/OPENBLAS/MKL/BLIS/NUMEXPR/VECLIB六变量均1；不增mpiexec |
| profile / cap | `task43_hp_adaptivity_resource_v1`；`PHYSICAL_NATIVE_NODE_CAP_BYTES=8589934592`；0.25秒采样 |
| RSS | 同时进程树采样RSS低于实际launch cap，且≤8GiB；保留可用内存/reserve导出的更严格门 |
| swap | task VmSwap=0；全局pswpin/pswpout另存基线/末态/增量，不混作任务归因；缺失或非零按V7限定资格 |
| 时间 | 100秒停止工作；whole-watchdog含清理验收≤120秒，累计同为≤120秒；额外20秒仅供清理，不继续测试 |
| 资源异常 | 按原watchdog/主控身份核验停止，保留原分类、退出码、末行资源和清理结果；不终止邻近任务 |

输出root只能由这次launcher创建；若事前存在，前置拒绝且保留现场，不清空重用。若仍然调用launcher而被拒绝，已经消耗一次，不能再解释为“尚未真正导入”。

只允许这一个driver，不另开native preflight、import-only、collect-only、恢复pytest或其他支持诊断。失败很快、时间剩余、修复局部错误都不恢复次数。若为必要清理超出120秒，如实记超限，只完成清理，不据此延长业务或补跑。

### 9.6 同次20项测试、完整终态和停止条件

顺序保持：身份保存 → watchdog/strace → startup真实环境与affinity → 逐模块导入/trace门 → 原有有限MPI/PETSc ABI preflight → pytest导入门 → 固定20项 → 最后snapshot → 完全退出/清理 → 主控独立终态复核。

四个selector均位于本报告第7节固定测试文件：

| selector | 数量 |
|---|---:|
| `test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle` | 1 |
| `test_synthetic_joint_authority_fixture_rejects_common_missing_identity` | 4 |
| `test_synthetic_joint_authority_fixture_rejects_each_failure_independently` | 12 |
| `test_a2_postprocess_writer_failures_keep_original_error_and_primary` | 3 |

不扩成整文件、全仓测试、FFCx witness、A1 main sentinel、旧场处理或模型。前门失败，20项保持NOT_RUN；完整有限ABI未到达与执行失败分开。原pytest批次无额外fail-fast开关，允许既定20项的一次批次；测试断言失败如实保留，不另起恢复批次。资源/affinity/监控异常一旦确认仍立即停止，不能等批次结束。

输入不符、成功setter mask不等于[1]、失败或不完整/未知setter、可读TID或资源成员affinity偏离、关键身份/trace不可读、ABI失败、RSS/reserve/task swap/时间门、监控或清理异常，均按V7否决continuation。合法[1]成功setter本身不否决；失败调用不误记成成功改绑。只对已核PID/start_ticks的本任务watchdog发停止信号。

完整退出后，主控亲读所有最终raw trace，包括解释器/运行时退出尾段，独立分类全部setter token，交叉核阶段记录、PID/PPID/start_ticks/TID和逐行资源。probe成功集合或单个PASS标签不能替代该复核。保留实际driver/source快照、环境、manifest、所有trace、阶段/terminal、watchdog summary/resources/log、外层退出码、信号和最终后代清除；Git只提交轻量索引、必要摘录和可审脚本。

20项即使全通过，只能在所有前门和终态满足时增加这次固定启动链及20项测试的有限工程资格。若trace/输入/退出/清理不完整，仍INCOMPLETE/NOT_QUALIFIED；若setter偏离，strict CPU1未通过；若ABI失败，测试未运行；若断言失败，测试目标未通过。任何情况都没有自动重试。

### 9.7 交付与仍禁止的工作

下一次交付使用 `response_v9.md` 和一份必要的 `outcomes/records/v9_d3_resume_closeout_v1.json`，其中前置快照与终态分段绑定；不是新增并行合同。附上现存原件的最小可审摘录和当前缺失依赖映射。更新当前README、summary、manifest、模型总账、进展和必要导航，旧V8负项留作历史，不覆写。

明确分开：旧9.464030618秒小计、后续静态计时、一次sanity、D3 whole-watchdog及未计时工作，避免嵌套时间重复计费。报告sanity与driver的实际次数、到达阶段、资源、测试和所有失败；目录/命令未调用时仍0/1，调用后无论结果都1/1。没有启动时不能伪造watchdog终态或资源通过。

**不批准任何正式PDE或其他参数诊断。** A1/A2 q重试、A1_R、A2_R、B/C、fresh baseline、同精度全过程成本campaign、迭代、0.7nm、NN/FTT继续锁定。支持成功不解锁正式封存槽或生产合并。完成这一有限工作后提交并推送同一执行分支，回读远端SHA，再等待审阅；不操作master、不合并。

## 10. 结项意见

V8 的价值是保存了准备错误、静态片段和正确的资格边界，没有把未运行项包装为成功。但它没有完成V7授权的输入准备或取得新的启动证据。后续应补上真正缺失的输入/依赖与一次sanity，再使用同一个未消耗D3；不再通过删除重造候选、放大普通文件错误或增加文档轮次来代替这一步。

本报告给的是**前瞻恢复条件许可**，没有将旧顺序、CPU1负结果或科学失败改为通过。工程归档验收、支持执行授权、科学资格与合并资格分别裁决。审阅只新增本文件，完整review提交SHA由提交完成后的交付回复给出。

## 固定证据入口

[DIFF]: https://github.com/Rookie1234567/MyFEniCS/compare/dc6c3c59cabebefec76f928f261a25670a2a8857...c245dd060882df4dc6f30224ac0fa8be93f764d2
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/dc6c3c59cabebefec76f928f261a25670a2a8857/docs/task43_hp_adaptivity/review_report_v7.md
[CLOSE]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/outcomes/records/v8_d3_preparation_closeout_v1.json
[RESPONSE]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/response_v8.md
[ROOT]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/AGENTS.md
[TASKRULE]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/AGENTS.md
[LOADER7]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_source_loader_audit_v1.json
[SHELL2]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/outcomes/records/v7_affinity_driver_sources/d2/run_d2.sh
[TEST]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/src/test/test_task43_v3_failure_safe_order.py
[README]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/README.md
[SUMMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/outcomes/summary.md
[MANIFEST]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md
[REGISTRY]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/development_model_registry.md
[PROGRESS]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/development_progress.md
[DOCS]: https://github.com/Rookie1234567/MyFEniCS/blob/c245dd060882df4dc6f30224ac0fa8be93f764d2/docs/README.md
[UPVARORDER]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_var.c#L1795-L1818
[UPVARENV]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_var.c#L1631-L1655
