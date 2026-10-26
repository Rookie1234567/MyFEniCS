# Task43 V9 正式审阅：固定 D3 与20项测试有限通过，依赖归档须局部纠正

审阅日期：2026-10-26。证据中的事件时间保留其原UTC口径。固定被审提交：`782c57fe4339fac2fe73fca2942b0d654024dda5`。审阅通过读取固定 Git 字节、提交差异、脚本与轻量实值，独立核算哈希、事件分类、资源和费用完成；没有启动 sanity、native import、ABI、pytest、collect-only、支持 driver、旧场处理或 PDE。只新增本报告，不修改历史 review、合同、失败记录，不提交 master、不合并。

## 0. 正式裁决

**本轮交付部分接受；固定启动链及固定20项测试的有限工程证据接受。** 发现一项可以直接由 Git 内容证明的 P2 问题：61条依赖边的键集合完整，但三条边把相邻桥接库的元数据挂到了 loader/libc 的文件身份上。这阻止“61条对象映射全部一致”的归档验收。它不能证明实际 D3 链接错误，也不足以否定已经保存的测试结果。下一步只需读取已有原始输出并纠正派生记录，不需要再跑一次 D3。

| 裁决维度 | 本次决定 | 适用范围 |
|---|---|---|
| 整改及证据归档 | **部分接受** | 身份、费用、次数、历史保护及终态实值相互一致；V9-01的三条派生记录必须纠正，原件访问限制继续明示 |
| 固定启动链与20项测试 | **接受有限工程资格** | 接受执行记录支持的 `PASS_LIMITED_ENGINEERING`，限于冻结 shell/probe、记录的单rank导入/有限ABI链及四个selector；审阅者未重跑、未亲读全部ignored原件 |
| 下一步执行 | **批准有限静态整改；不批准新增支持运行** | 第9节是下一轮唯一执行范围。sanity已用1/1、D3已用1/1，无重试、额外probe或补跑pytest权限 |
| 正式PDE及科学资格 | **不批准；五项能力不升级** | 正式累计5/6，A1 2/2、A2 3/3，最后一槽继续封存 |
| 合并资格 | **本次不给任何实际 merge approval** | 研究档案可保留，test-only有新的有限验证；生产核心、共享启动、研究入口和整分支均不得据此合并或提升默认行为 |

这里的“有限工程通过”表示：这次固定软件启动和所选文件保护测试，具有一致且可审的记录；它不回答 Maxwell 解是否足够准确，也不证明所有环境、求解入口或依赖已经获得生产资格。下文分别处理工程结果、证据缺陷、科学状态和运行授权，不以一个PASS合并这些结论。

## 1. 固定身份、实际差异与审阅范围

| 身份 | 核对结果 |
|---|---|
| 仓库 / 唯一分支 | `Rookie1234567/MyFEniCS` / `task43_hp_adaptivity` |
| 固定被审HEAD | `782c57fe4339fac2fe73fca2942b0d654024dda5` |
| 被审tree | `5387b10e22bf4b177ab0c724cb50b52e4f05730b` |
| 直接父提交 / V8执行权威 | `ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba` |
| 实际D3运行HEAD | `ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba`；不能替换成后来文档交付HEAD |
| 冻结源码比较对象 | `c245dd060882df4dc6f30224ac0fa8be93f764d2`；所列8项源码与运行/交付记录对应字节一致 |
| 长期代码基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 审阅开始时远端 | 分支指向固定782c57提交；相对V8 review为ahead 1、behind 0，未发现后续提交 |
| 执行工作树 | prelaunch保存clean、upstream和0/0；这是工作站记录，不是本审阅亲自检查工作站文件系统 |

[实际差异][DIFF]只有21个路径，15新增、6修改，统计为新增5093行、删除11行，全部在`docs/`。其中归档的shell/Python文件属于研究证据副本，未新增生产入口。`src/`、`benchmarks/`、tracked activation、测试代码、历史review、合同及既有失败记录没有在本轮差异中改变。相同源码字节允许绑定这次测试，不能把较新的文档提交追认为运行HEAD。

完整阅读了根、docs、Task43三层AGENTS、任务书、V8 review及第9节、V9回应、指定closeout和归档脚本/准备记录；对当前README、summary、manifest、总账、进展和导航的V9内容逐项对照。代码审核进一步读了固定测试的联合读取helper、四组案例、实际A2失败处理和checkpoint writer，以及watchdog相关资源/清理实现。[任务与规则][TASK]；[V8权威][R8]；[V9回应][RESPONSE]。

对下载的Git内容核对了固定tree的blob身份，对8项冻结源码和候选另算SHA256；用独立的标准库文本/JSON/AST处理重算边集合、字节绑定、资源求和和费用。没有执行归档的审计程序或被审项目来“验证自己的结论”。三项并行子审阅分别检查输入/费用、终态/资源、测试/候选，主审复读具体冲突与关键断言后形成本文。

## 2. 按严重程度排列的问题

### V9-01 · P2：61边派生表含三条对象身份混合，不能按“全部一致”验收

依赖表的作用，是把某个库要求的名称对应到一个实际文件，再记录这个文件的哈希、构建标识、包归属和它自身所需的库。名称、路径和元数据必须属于同一对象；只数出61条不能证明这个条件。

固定文件为`docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/direct_needed_edge_map.json`。下表行号全部针对被审782c57提交。[完整边表][EDGES]

| 位置 / 边 | 正确相互对应的字段 | 混入的字段与直接矛盾 |
|---|---|---|
| 781–795，`mca_btl_ofi.so → ld-linux-x86-64.so.2` | candidate/realpath为loader，SHA以`c20a2dc8`开头，Build-ID以`0d77dbd4`开头 | `resolved_soname`却是`libpsm_infinipath.so.1`；包归属和NEEDED也是该PSM桥接库 |
| 829–844，`libpsm_infinipath.so.1.16 → libc.so.6` | path、SHA `3a15d668…`、Build-ID `a4a7992a…`均对应libc | SONAME/包变成`libmca_common_ofi.so.10`；NEEDED混入该桥的三项 |
| 885–904，`libmca_common_ofi.so.10.0.2 → libc.so.6` | 同一libc的path、SHA和Build-ID | SONAME/包变成`libfabric.so.1`；NEEDED混入libfabric的七项 |

同文件765–778等处保留了同一libc身份的正常记录；[root S1记录][S1ROOT]28–68也分别给出了三个桥的自身身份。矛盾不依赖相信任何PASS标签。独立计数得到18个parent、61个唯一`(parent, needed_soname)`键，恰好是旧15对象48边加三桥13边，无重复或漏边。**边集合覆盖可以接受，三边的元数据一致性不能接受。**

污染模式与跨记录块未复位相容，但这只是根因推断。本审阅没有亲读原生成器执行输出，不能断言具体解析语句出错，更不能据此宣称D3实际加载了错误库。

还必须区分发生时间：`root_s1_review.json:129–133`绑定了当时的原脚本和stdout；`prelaunch_snapshot.json:74–82`绑定root S1、S2及sanity，而没有绑定这份最终派生edge map。edge map没有可用于确定其生成时刻的记录。因此，**无法由收尾错表证明主控在launch前已经看见同样的错表并错误放行**；也不能反过来宣称前门全部原件已经由外审证实。对主控的确定批评是：交付的派生表及“61条身份映射完整”表述没有通过逐字段一致性检查。

**最小整改：**保留本v1错表和历史S1/prelaunch原样，从已绑定原stdout只读提取纠正版，提交三处块边界的带原行号摘录、具体字段更正及来源。原stdout SHA256为`42700961db2b4ca1ae2206d93c18a6e0ad8986ec72b818b26a192b082eb005c4`，对应`map_direct_needed_paths.sh` SHA256为`1568de57c0911a88c062df5b9d504ae42fad3e0b93217f730e55f2631ee1b8b2`。若原件不符或不可读，保持未关闭，不重跑扫描来制造历史替代品。

**验收：**61个键、18个parent和48+13来源集合保持；每一resolved对象的realpath/hash/Build-ID/SONAME/NEEDED/package相互一致；同一realpath和hash不得对应相冲突的元数据；所需名称与SONAME不同时必须给原始别名依据；三个桥边界不能污染相邻记录。只需离线解析既有文本，不授予新sanity、pytest或D3。

### V9-02 · P3：部分前置输入只有摘要与hash，完整闭包和控制时间仍不可外审确证

位置为`s1_static_summary.json:57–124`、`root_s1_review.json:70–164`、`response_v9.md:12,27`。[静态摘要][S1]；[root S1][S1ROOT]。

tracked activation、冻结driver和派生边表可直接阅读；实际venv activation、登录shell输入、MCA参数/override原文及多数采集脚本/输出只留在ignored原件中。`root_s1_review`的“compiled sysconfdir ... known”应受`s1_static_summary`的明确限制约束：保存的是安装路径、strings及包来源，未读取构建时配置头。V8原停止消息时间、relocation与停止先后仍UNKNOWN，不能凭文件哈希补成可信时间证明。

**影响与整改：**这不是发现新的环境冲突，也不是要求全量原日志入Git；它限制“审阅者已核实完整实际输入/加载闭包”的说法。下一轮与V9-01一起，从已经保存的原件增加必要的采集脚本、MCA/activation关键原行和三处边界摘录，写清哪项是直接读到、哪项只是旧记录。`s1_static_summary`中的“未采用候选/NOT_RUN”属于S1时点，不得当成V9最终状态；新汇总应显式标注阶段。旧不可恢复时间继续UNKNOWN，不作为无期限阻塞。

**验收：**读者可把关键输入原行、命令/退出码及hash连起来，并能分辨已知、未知和推断；不将后来的静态更正或安装文件状态追认为当时完整进程映射。本项不单独撤销第5–6节的有限工程观察，不要求任何新运行。

除上述证据问题外，本次未发现足以否定固定20项测试或已提交D3终态实值的新P1/P2实现缺陷。没有凭“原件不可访问”推定成功，也没有把已披露的观测边界事后升级为新失败门。

## 3. 授权、顺序、次数与历史责任

[V8第9节][R8]明确允许先完成实际输入/有限依赖，再采用现存候选、执行一次stdlib sanity、冻结8项源码，最后使用同一个D3许可。它不要求删除重造候选，也不允许继续用旧顺序失败代替尚可完成的授权工作。

| 环节 | 已提交证据及时间（原记录UTC） | 本次判断 |
|---|---|---|
| S1输入/依赖复核 | `root_s1_review`，2026-10-25 14:52:43.364223，绑定原脚本/输出 | 前门完成的记录存在；其全量真实性有V9-02访问限定，最终派生表另有V9-01缺陷 |
| S2采用现存候选 | `root_s2_adoption`，14:53:10.347681，绑定S1 hash，记录两副本匹配、未恢复/未修改，输出root不存在 | 与V8恢复许可相符；没有用新目录或改名规避旧失败 |
| 一次sanity | 保存起止14:53:50Z，19项结果与前置绑定一致 | 使用1/1；秒级起止相同与0.22秒wrapper并不矛盾 |
| 源码冻结 | `prelaunch_snapshot`，14:54:51.886523，8源及S1/S2/sanity绑定 | 实际运行HEAD明确为ef1e1ca；八源与c245dd对应字节一致 |
| 唯一launch及终态 | 首行资源约14:55:27，trace退出约14:55:34；root终态审计15:01:14.109662 | 命令/root与旧许可一致；记录中没有第二次driver或独立pytest启动 |

这是**文件内时间、前驱hash和执行内容相互一致**的顺序证据，不能提升为外部可信时间戳证明。尤其V9-01的派生表生成时间未知，不能拿它倒推原S1发生了何种具体错误。[S2采用记录][S2]；[prelaunch][PRE]；[终态审计][TERM]。

唯一记录命令仍是`bash /tmp/task43_v7_d3_proposal/run_d3.sh`，输出root仍为`/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1`。这些在本文中是历史身份，不是可再次执行的命令授权。

V8提前生成、机械复制exit 1、随后整理及主控未及时拦截均保留；V9没有将它们改写为成功。旧控制时间不可恢复与新前瞻顺序可记录被正确分开。V6 D2前遗漏D1已有网络库setter的监督责任，也没有因D3成功消失。

| V8问题 | V9整改验收 |
|---|---|
| V8-01：输入/直接依赖/源码冻结不足 | **部分通过**：候选与8源冻结补齐，边集合齐全；三边元数据及原件可外审性按V9-01/02收口 |
| V8-02：准备顺序偏差、机械恢复与停止解释 | **通过当前前瞻采用部分**；旧生成顺序仍失败，未回写 |
| V8-03：旧控制时间不可重建 | **接受诚实限定**；UNKNOWN保留，不冒称已证明当时先后 |
| V8-04：导航/计时展示 | **当前V9内容基本通过**；费用口径正确，本文补做当前改动部分的GitHub渲染核对 |

## 4. 静态输入、ELF与MCA规则的实质判断

ELF是Linux共享库文件；NEEDED列出该文件直接要求的库名。静态检查能核文件身份及可能解析路径，但不会证明某次进程实际映射了所有这些文件。

1. **启动输入。** tracked activation设置固定的库搜索目录、清理`LD_PRELOAD`并设置线程变量，未写入PML；实际venv的activation/pyvenv.cfg及登录配置有保存hash。S1明确没有source activation或加载库。当前shell未设相关变量，只说明当时被检查的shell，不能替代运行中环境；后者另由probe记录。[activation][ACT]；[S1:57–100][S1]。
2. **长短变量与优先级。** 普通`/etc/openmpi/openmpi-mca-params.conf`的`pml=^ucx`，不因与worker-local `OMPI_MCA_pml=ob1`字面不同而自动冲突。固定OpenMPI上游源码显示：更高优先级override应先处理，环境高于普通参数文件；相关长名先于短名。因此检查`OMPI_MCA_pml_base_pml`、参数文件选择器及override来源是必要的。保存摘要声称它们未设置/相应override不存在，当前Git材料没有直接反证，但原文未亲读。[上游优先级][UPORDER]；[长短名称][UPENV]。上游代码仅支持规则解释，不被当成已安装Ubuntu二进制的逐字节证明。
3. **有界依赖。** 15项旧ELF重核记录、18个parent及48+13条边符合授权的有限范围，没有必要递归全系统。三个桥分别解析到`/usr/lib/libpsm1/libpsm_infinipath.so.1.16`、`/usr/lib/x86_64-linux-gnu/libmca_common_ofi.so.10.0.2`、`/usr/lib/x86_64-linux-gnu/libfabric.so.1.20.0`，自身NEEDED数为3、3、7。MPI、PMIx、libpsm2的别名记录与既有对象hash相容；这不免除三条错误边的纠正。[S1桥摘要][S1ROOT]；[边表][EDGES]。
4. **搜索路径与未知。** 记录称61条解析来自`ld.so.cache`，固定五个activation目录及观察到的RUNPATH没有命中这些边；没有运行`ldd`、`ompi_info`或安装动作的记录。这个结论依赖已保存的静态采集输出，不能外推为整个loader闭包、编译配置或历史内存映射已经证明。libfabric包版本与实际文件名中的版本段不同，本身不足以证明ABI冲突。

本次D3结果为“这套固定输入下没有观察到setter且固定测试完成”增加了实证。它没有建立`ob1`必然阻止所有PSM加载的普遍机制，也不能把`HWLOC_COMPONENTS=-x86`或`OMPI_MCA_pml=ob1`推广为共享默认修复。

## 5. 固定字节、19项sanity与20项测试

### 5.1 实际字节绑定

| 对象 | 独立核算的字节身份 |
|---|---|
| `v9_d3_sources/run_d3.sh` | 4166字节；SHA256 `e84d2eb0bfcd257549fcd85b336d5ce9ea5f8faa72eef5261e7ca936d076127a` |
| `v9_d3_sources/probe_import_affinity.py` | 14891字节、371行；SHA256 `fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4` |
| `v9_d3_sources/sanity_once.py` | SHA256 `fcefb49300b51356844df6b1276b6cdfc58bf881691e1d7d4414043370520ade` |
| 固定测试文件 | `src/test/test_task43_v3_failure_safe_order.py`，77310字节；SHA256 `52f94e28306d2d7f83f602c5e654c8953e544f00091ae3013378d52d040b7a43` |
| 其余7项冻结source | h100、A2、checkpoints、native capacity profile、watchdog、tracked activation、workspace环境记录，逐项与prelaunch的路径/hash/大小一致 |

这些是对Git所存内容的亲自核算；实际工作站snapshot文件没有亲读。[源码冻结清单:16–72][PRE]；[shell][SHELL]；[probe][PROBE]；[sanity][SANITY]。

### 5.2 Sanity没有偷跑probe或native入口

`sanity_once.py:46–56`只从AST提取`_successful_setters`函数，向隔离命名空间提供标准库对象。它没有执行原probe顶层或`main()`，也没有导入numpy、dolfinx、MPI/PETSc或项目模块。

19项包含12种合成文本与7项结构/身份检查。文本覆盖CPU1、非CPU1、多CPU、失败调用、unfinished/resumed、未知/空/指针mask、栈帧、未知token及非setter；混合输入的预期是3个成功setter、7个unknown。其余检查包括固定probe身份、隔离提取、PML实值先落盘再拒绝、未知/偏离的否决、其他函数AST保持、四selector保持。失败调用进入unknown门，未被错误算成成功改绑。保存结果19/19与代码相符；这是一次sanity的内部检查数，不能加到pytest通过数上。[sanity:13–30,46–115][SANITY]；[结果][SANITYRESULT]。

### 5.3 20项确实覆盖了目标缺陷，且只覆盖这些目标

| 固定selector | 个数 / 代码位置 | 直接检查到的意义与限制 |
|---|---|---|
| `test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle` | 1；test:705–783、882–891 | 写出相互绑定的小NPZ、summary、comparison、terminal，再读取文件和hash；它是合成一致包，不是物理解 |
| `test_synthetic_joint_authority_fixture_rejects_common_missing_identity` | 4；894–985 | 分别共同缺source、contract、plan或三者；写新primary并重绑引用/hash，原正例primary字节保持，避免靠陈旧hash“碰巧拒绝” |
| `test_synthetic_joint_authority_fixture_rejects_each_failure_independently` | 12；988–1058 | 分别覆盖失败terminal、非零/未知exit、状态/权限降级、缺文件、缺绑定、错hash和身份不一致；必要时同步内容hash以隔离拒绝原因 |
| `test_a2_postprocess_writer_failures_keep_original_error_and_primary` | 3；1061–1176 | sidecar、comparison降权、summary降权写失败；调用真实A2失败处理，检查原异常对象、primary原字节、测量字段、FAILED terminal及联合拒绝 |

[固定测试源码][TEST]786–879中的helper在823–834明确要求source是非空40位十六进制，contract/plan分别是非空64位十六进制，随后核多文件身份、hash、终态、退出码和权限。共同缺字段的四例不是只改一个文件，也不是只对status做断言。三项writer注入调用[真实A2处理:84–290][A2]和[checkpoint原子writer:88–191,215–229][CHECKPOINT]；它们正确展示：单个文件原子替换不等于多文件事务，残留的单份true不能给包授权。

这里的小数组如`primary_solution=[0.25+0.5j]`是人工fixture。没有PDE残差、精度或extra校正通过的含义。联合读取仍只存在于测试中，没有新生产consumer、A2_R或controller。

实际启动脚本先拒绝旧root并保存source/driver，再启动唯一watchdog/strace/probe。probe经过逐模块snapshot与有限ABI，在同一个Python进程内只调用一次`pytest.main`执行四selector；没有再用subprocess启动另一个pytest从而改变父PID。[shell:23–52,83–100][SHELL]；[probe:264–366][PROBE]。

因此，可以接受保存的“20 passed in 0.91s”作为这20项冻结字节的有限动态证据，补上V6–V8一直NOT_RUN的这一个范围；不能回写那些历史NOT_RUN。也不能说整个测试文件、历史57项、A1真实mesh边界、extra原向量/A6、全仓pytest、完整p6 FFCx witness或生产ABI已通过。实际worker.log及pytest临时NPZ没有由本审阅亲读，动态接受属于轻量实值、源码断言和记录绑定的一致性审阅。

## 6. 终态、CPU、资源与原件边界

### 6.1 已提交实值的独立核算

主要来源为`v9_d3_sources/preparation/root_terminal_audit.json`及完整归档`root_terminal_audit.py`。审计脚本确实遍历trace文本的setter token、信号与尾段，而非仅接受probe的成功列表；但脚本使用本次PID和日志期望值，是单次研究审计工具，不是通用生产资格消费者。[终态实值][TERM]；[审计脚本:26–37,63–84][TERMSCRIPT]。

| 项目 | 从Git内容可核到的结果 | 位置与边界 |
|---|---|---|
| 六份trace索引 | 959+47+1+1+1+1=1010行；六份保存的末行均exit 0 | TERM:102–147；两份主要trace全文未在Git |
| getter原行 | 44条可读摘录独立解析均为`[1]`，worker 41、orted 3 | TERM:149–370；不能称审阅者亲读了1010行 |
| setter与signal | 保存集合均为空，执行方全量审计报告0成功setter、0未知setter、0signal | TERM:147–148,371；与代码及可见摘录一致，全文无遗漏仍依赖未亲读原件 |
| 阶段身份 | 12条阶段，worker PID257450 / PPID257437 / start_ticks286512204一致 | TERM:1120–1548；不是只看最终PASS |
| 资源逐行算术 | 13行成员RSS逐行求和等于该行进程树RSS；记录的成员affinity均`[1]`，task VmSwap均0 | TERM:372–994；采样口径含watchdog和后代 |
| 同时采样RSS峰 | 第9行180887552 B，低于8GiB及实际记录门 | TERM:838–897；不是各PID历史峰相加，也不是连续真实峰 |
| 末行 | 第13行elapsed 8.639170113019645s，RSS38014976 B，VmSwap0、exit0、children为空，仅余watchdog | TERM:970–993 |
| whole-watchdog | 8.763570327777416s，低于100s工作停止阈值与120s含清理上限 | TERM:1635–1639；没有“多给20秒继续测试” |
| 全局swap | pswpin基线/末态均4250664，pswpout均7183007，增量0/0页 | TERM:1605–1624；与task VmSwap分别陈述 |
| 退出及清理 | worker/外层exit0；COMPLETED、remaining=[]、descendants_cleared=true；相关8个host PID/TID在主控核查时记为ABSENT | TERM:1025–1066,1595–1604；不是本审阅现场查询/proc |

记录父链为watchdog257436（PPID257393，start286512154）→strace257437（start286512195）→worker257450（start286512204）→orted257451（start286512301）。257454/257455在worker的task枚举中出现；257452/257453只由trace/终态索引约束，不能臆造其独立出生身份或完整角色。

从Git内嵌对象按固定代码的序列化方式，可以重建并匹配所记hash/大小的watchdog summary（3536B）、probe terminal（276B）、stages JSONL（7020B）、launch command（42B）、exit文本（2B）；四份单行trace也可由尾行重建。这比只重复hash更强，但仍是Git内部绑定核验，不等于现场访问原件。

ABI记录包含MPI world size1、Open MPI4.1.6、PETSc3.19.6、complex128/int64、NumPy1.26.4、六线程环境变量均1以及记录的模块路径/marker。probe对MPI版本的既知尾NUL处理不扩展成任意版本接受。这里是一次固定单rank导入及有限ABI检查；未覆盖SLEPc、MUMPS求解、完整FFCx或多rank生产路径。[probe:176–261][PROBE]；[TERM:1067–1119][TERM]。

### 6.2 已披露限制是否阻塞本次有限资格

| 限制 | 裁决 |
|---|---|
| trace从taskset之后开始 | 不能证明外层shell/taskset之前的全生命周期；这是冻结脚本既有边界，不事后新增为D3失败门 |
| TID没有独立start_ticks | 不能宣称每个线程身份跨完整生命周期唯一；阶段枚举、进程身份和getter仍支持本次已观察区间 |
| RSS/VmSwap为采样，PSS禁用 | 接受采样门，不宣传连续峰值；实际相邻样本间隔约0.437–0.963s，配置interval 0.25不等于实测严格4Hz |
| 没有`--cache-path` | 空SHA稳定只代表空枚举；不证明JIT/global cache稳定或已检查。进程清理另有末行/退出/后代证据，不因空cache字段自动失效 |
| 历史控制时间UNKNOWN | 保留未知；不能补造。对这次已记录前瞻流程不构成永久阻塞 |
| 完整raw trace/resources未亲读 | 有限接受必须带证据等级；不声称审阅者全文排除了所有未分类事件 |
| 执行交付未核GitHub rendered view | 本审阅已检查固定提交的V9新增/更新Markdown段落、表格及导航；不把该补核追认为Codex当时做过 |

这些限制没有在可读实值中暴露新的运行失败，不需要为此扩大诊断或重跑。它们共同阻止“全生命周期CPU1、通用OB1修复、生产ABI/CI通过”的扩大结论。

### 6.3 本审阅未亲读的工作站原件清单

| 原件范围 | 当前能核到什么 / 仍缺什么 |
|---|---|
| `benchmarks/artifacts/task43/v9_resume_preparation/raw/map_direct_needed_paths.*`及相关activation/MCA采集输出 | Git有绑定hash、摘要和错误派生表；原脚本/完整stdout未亲读，V9-01须由此解决 |
| `raw/recheck_15_elf.*`及实际安装ELF/venv/config文件 | 记录声称15/15身份保持；本审阅没有访问这些二进制或工作站实际配置 |
| `/tmp/task43_v7_d3_proposal/`、持久candidate_draft和prelaunch/source_snapshot | Git归档字节和hash可核；实际工作站副本未亲读 |
| 唯一D3 root的主worker/orted原trace、`resources.jsonl`、`worker.log` | Git提供getter、尾段、资源实值及审计脚本；未直接读取两份主trace全文、原资源流、原pytest stdout |
| 固定20项pytest生成的小NPZ/JSON与其他ignored产物 | 直接审了fixture如何生成、绑定和断言；未现场读这些临时原件 |
| V8机械操作、控制消息、历史大场/矩阵/日志 | 仅按已提交历史证据和明确UNKNOWN解释，没有重新采样、积分或求解 |

索引列出原件hash，不等于原件已由外审访问。补充有限原行可以提升可外审性；不能通过重跑生成另一份“原件”补足历史证据。

## 7. 费用、失败保留与科学状态

### 7.1 费用独立核算

| 口径 | 秒 | 是否另加 |
|---|---:|---|
| V8明确计时准备/整理 | 9.464030618 | 保留旧小计，不归零 |
| V9静态动作 | 45.72337052039802 | 45.19 + 0.06 + 0.007662117946892977 + 0.001154409721493721 + 0.46455399272963405 |
| 上述累计已测静态动作 | 55.18740113839802 | 小计，不再次与两行相加 |
| 唯一sanity wrapper | 0.22 | 计一次；内部0.04185436898842454已包含，不能另加 |
| root终态审计处理 | 0.04148901393637061 | 单列 |
| 明确计时非D3动作合计 | 55.44889015233439 | 与原记录一致；不是整轮墙钟 |
| 唯一D3 whole-watchdog | 8.763570327777416 | 独立运行窗口；pytest0.91在其中，不另加 |
| 人工阅读/编辑、部分Git整理及收尾误读文件 | not_measured | 不补造耗时，不混入watchdog |

Decimal按保存数值相加与报告舍入一致。已列静态单项如37.52秒、4.84秒低于60秒，累计55.1874秒低于600秒；没有原逐命令计时全文，不能声称审阅者重建了全部未读操作的单条时限或整轮wall。不同生命周期的准备、导入和fixture费用，更不能用于同精度求解加速比较。[closeout][CLOSE]；[S1计时][S1]。

收尾误用了`sanity.started.txt`、`sanity.finished.txt`，实际文件是`sanity_started.txt`、`sanity_finished.txt`。两条cat失败，单条exit未保存；后续成功命令令组合shell最终为0。随后只读找到了正确文件，耗时not_measured。这是保存了的收尾读取错误，不是sanity/D3失败，也没有新消耗或返还支持次数。[路径错误原记录][PATHERROR]。V8机械exit1、V6 D1/D2、V5失败和正式A1/A2负结果仍保留。

### 7.2 五项能力与正式额度

| 能力 | V9后的状态 | 本次不能替代的证据 |
|---|---|---|
| 空间 | PARTIAL | 已有mixed-p和真实局部h资格各按旧范围；一般多层h没有因导入成功而获得证明 |
| 选择 | PARTIAL | accepted9/R9为最后接受状态；R10冻结噪声门拒绝没有第10次接受 |
| 精度 | NOT_PASSED | 独立holdout及相同精度更少FE目标未通过；合成NPZ不是新场解 |
| 同精度全过程成本 | NOT_ESTABLISHED | 无合格等精度端点及同口径全过程对照；D3费用不构成数值优势 |
| 迭代 | NOT_RUN / NOT_QUALIFIED | 没有新的迭代接线、求解或证明 |

R9独立FE110472对237600控制的减少，只能作为DoF事实；独立精度仍不合格。R10与一份控制接近、A2_q3的primary小残差及同空间q稳定性，都不能替代空间精度。A1受控停止、A2未完整端点、extra显式残差未严格下降及旧LIMITED清理结论保持原样。[当前汇总][SUMMARY]；[manifest历史边界][MANIFEST]；[模型总账][REGISTRY]。

本轮新正式PDE、formal dispatch、READY均0。正式累计5/6，A1 2/2、A2 3/3，最后一槽封存。D3支持1/1及sanity1/1已耗尽，不存在用剩余时间换次数或自动动用正式封存槽的权限。

## 8. 合并资格：逐依赖组判断

| 组别 / 文件与依赖 | 本次增加的证据 | 资格及剩余阻塞 |
|---|---|---|
| 文档与轻量研究档案：`response_v9.md`、records/v9归档、Task43当前汇总和仓库导航/总账段落 | 新增可审脚本、固定测试和终态实值 | 可保留研究档案；V9-01须局部勘误，迁移应连带限定与链接。**没有实际docs merge approval**；总账不能整文件覆盖其他任务 |
| test-only：`src/test/test_task43_v3_failure_safe_order.py`中的helper/固定20项 | 最终冻结字节的20项证据补齐 | 接受这个子范围；依赖A2 failure handler与`candidate_checkpoints.py`，不能整大文件或单文件无依赖迁移，不代表生产consumer |
| 研究入口：`h100_anchor.py`、`a2_native_p6_diagnostic.py`、`candidate_checkpoints.py`、`src/runners/p6_condensed_direct.py`显式诊断接线 | 只有其中失败处理被合成fixture覆盖 | 保持research-only；A1/A2完整现场、extra/PDE和共享依赖未新增资格，不能提升default |
| 共享启动 / watchdog：tracked activation、`benchmarks/subreaper_watchdog.py`、native capacity profile | 固定单rank支持运行与清理记录 | 仅本路线有限证据；不可把worker-local OB1/HWLOC变量迁入共享activation，不替代生产资源/ABI回归 |
| 数值核心A–D及共同前置 | V9无数值改动、无fresh PDE | 继续按manifest原子依赖闭包审；旧overlay只59/66同字节、核心/共享23/27同字节，不能覆盖最终共享文件 |
| checker/benchmark：reference restore、comparison、candidate records/checkpoints等 | 本轮只增加文件保护fixture | 原场比较、参考角色、空间/端点资格继续受旧证据限定；不将合成测试等同物理checker全面通过 |
| 整分支、ignored大原件及未验默认 | 无新的全面生产证据 | **不合并**；大原件留ignored，历史负证据保留 |

旧overlay未覆盖的四个变化共享数值文件仍是`src/solvers/common_3d_case_flow.py`、`dtn_port_3d.py`、`hcurl_variable_p_reduction.py`、`solve_maxwell_3d_stage_4b_block_grating.py`。核心A–D还依赖mesh builder、Task43 axis plan和native capacity IO，不能拆掉前置只搬“看起来可复用”的文件。全仓收集/SLEPc与complex PETSc ABI阻塞没有由这20项关闭。[选择性合并清单:55–95,101–109][MANIFEST]。

工程验收、研究档案保留和merge approval是三个不同决定。本报告不执行合并；未来实际合并仍需明确审阅批准、用户授权与Codex执行，不能把本节当许可。

## 9. 下一轮唯一授权：既有证据的有限静态纠正

### 9.1 明确允许与禁止

**批准继续有限静态整改，不批准任何新增支持诊断、sanity、ABI运行、pytest、collect-only或正式PDE。** 本次已有足够的固定工程观察，剩余确定问题发生在派生证据的关联和呈现上；增加一次计算不能修复旧证据，也没有科学必要性。

唯一工作区仍为已登记canonical worktree `/home/fenics/Projects/NN-Lab-V2`，唯一分支仍为`task43_hp_adaptivity`。先fetch并核本review提交、upstream和已有改动，不覆盖其他工作。只允许修改/新增本节列出的文档与离线证据整理文件，不能改测试、数值源码、driver、activation、冻结合同或历史原件。

### 9.2 E1：先读已绑定原件，定位三个边界

1. 核既有`map_direct_needed_paths.stdout`和`.sh`与V9-01两项完整hash一致；只读相关旧stdout、采集脚本和已保存输入。保存所用原件路径/hash、原行号、边界摘录和实际可恢复的命令/退出信息。
2. 逐条解释三个异常究竟来自原采集文本、后续派生解析，还是其他已能证明的步骤。没有原生成器/时间证据就保留UNKNOWN，不把“像解析污染”写成已证明原因，不推定当时launch门必然合格或必然错误放行。
3. 对V9-02，只从同批已有原件补tracked/venv activation实际source行、相关MCA长短变量、参数/override来源、搜索路径核对的必要摘录与脚本。保留缺失，不dump无关环境或秘密，不重新扫描全系统。

### 9.3 E2：离线更正并独立核算

保留`v9_d3_sources/preparation/`及原v1全部字节。可新增`outcomes/records/v10_static_evidence_sources/`，放纠正后的edge map、最小原文摘录及只解析保存文本的stdlib整理/核算脚本快照；原件来源和新派生时间必须分别记录。不要把原采集脚本再执行一次。

必须实际核算：61个唯一边键、18个parent、48+13集合覆盖；逐对象realpath/hash/Build-ID/SONAME/NEEDED/package一致；三个桥、MPI/PMIx/libpsm2别名有对应原文；三个污染边界不再跨块串入字段。对原v1与纠正版输出逐字段差异，解释每项变化。允许离线文本解析断言和JSON/hash/链接/格式核对；它们是静态数据检查，**不计为重跑sanity或pytest，也不得执行任一被审probe函数或项目模块**。

主控必须亲读三处原边界及更正差异，再审独立核算结果；不能只采纳代理PASS或“61条数量一致”。原记录的错误不是通过修改期望值消除的。

### 9.4 E3：一次文档收口、预算和停止条件

新增一份`outcomes/records/v10_static_evidence_correction_v1.json`及`response_v10.md`即可，不新建合同、controller或平行addendum。更新当前README、summary、manifest、模型总账、开发进展及必要导航：保留D3有限工程成果，明确原782c57三条派生错误和新修正身份；V8负项、V9原记录及旧review不能改写。可从既有D3日志补短的pytest/退出原行，但不重跑终态审计程序或任何支持入口来生成新观察。

| 边界 | 允许范围 |
|---|---|
| 新支持driver / sanity / native导入 / ABI / pytest / PDE | **全部0次**；没有候选运行命令或新输出root授权 |
| 静态动作 | 文件读取、标准库解析/hash、文档与Git核对；每条≤60秒，下一轮新增已测静态动作≤300秒；沿用已测静态累计≤600秒，已有55.18740113839802秒不归零 |
| 费用 | 新动作计时与旧计时分列；未计时继续not_measured，不用剩余时间换运行次数 |
| 局部机械错误 | 路径/格式/离线解析的小错可在上述静态预算内就地修正，只重做相关静态步骤并保留失败，不无故重启整个审阅循环 |
| 原件异常 | 原件不存在、hash不符、当前所用原件的来源/字节无法绑定或预算达到：停止受影响证据更正，保存UNKNOWN/UNRESOLVED并如实交付；不得重采集或生成替代历史原件 |
| 交付 | 核对仅授权文档/证据差异、JSON/链接/格式及GitHub当前渲染；提交并推送同一分支，回读完整SHA及ahead/behind，随后等待审阅 |

历史生成时刻或不可恢复的解析步骤仍可UNKNOWN；只要所用原stdout身份可靠，不因此阻止完成当前纠正。第9节不是授予独立运行“离线probe”的新槽位：只处理已保存文本，不source activation、不执行`readelf`/`ldd`/`ompi_info`或新环境探针，不改MPI参数，不安装/重建ABI，不导入项目/native模块。文档字节变化不要求重复已经有绑定的20项测试。

### 9.5 正式计算与下游仍全部锁定

不批准A1/A2 q重试、A1_R、A2_R、B/C、fresh baseline、同精度全过程成本campaign、迭代、0.7nm或NN/FTT。正式最后一槽仍封存；sanity和D3许可均已用尽。静态勘误成功也不自动解锁任何运行或合并。

若将来提出新的科学计算，必须另行明确科学问题、合格前提、实际分支/attempt、配额变更、唯一输入/命令/root、资源/停止门及端点证据；本报告没有提前批准这些工作，也不要求为本次归档错误另造一轮数值实验。

## 10. 本次交付与验证边界

本报告的实质结果是：保留D3固定启动链和20项最终字节的有效有限成果，指出三条可复现的派生记录错误，用一次有界静态更正结束这项归档缺口。科学失败与未完成项不因工程测试改善而改变。

审阅已在固定782c57的GitHub预览检查V9回应、归档README、任务README、summary、manifest、模型总账、开发进展和docs导航的V9改动段落/表格。开发进展中更早任务的既有公式渲染错误不在本轮差异内，未改写，也没有宣称整个长文档所有历史公式通过。执行方原“未核rendered view”陈述作为历史保留。

只新增`review_report_v9.md`，报告的链接、表格与固定SHA引用在提交前做静态核对，远端更新使用预期分支HEAD保护；完整review提交SHA在交付回复中给出。提交身份和实际测试身份保持分开，没有将本文或后续字节追认为D3运行代码。

## 固定证据入口

[DIFF]: https://github.com/Rookie1234567/MyFEniCS/compare/ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba...782c57fe4339fac2fe73fca2942b0d654024dda5
[TASK]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/task.md
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba/docs/task43_hp_adaptivity/review_report_v8.md
[RESPONSE]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/response_v9.md
[CLOSE]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_resume_closeout_v1.json
[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/s1_static_summary.json
[S1ROOT]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/root_s1_review.json
[EDGES]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/direct_needed_edge_map.json
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/root_s2_adoption.json
[PRE]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/prelaunch_snapshot.json
[TERM]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/root_terminal_audit.json
[TERMSCRIPT]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/root_terminal_audit.py
[SHELL]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/run_d3.sh
[PROBE]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/probe_import_affinity.py
[SANITY]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/sanity_once.py
[SANITYRESULT]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/sanity_result.json
[PATHERROR]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/closeout_path_read_error.json
[TEST]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/src/test/test_task43_v3_failure_safe_order.py
[A2]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py
[CHECKPOINT]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/benchmarks/task43_hp_adaptivity/candidate_checkpoints.py
[ACT]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/scripts/activate_task40_phi90_pord64.sh
[SUMMARY]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/summary.md
[MANIFEST]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md
[REGISTRY]: https://github.com/Rookie1234567/MyFEniCS/blob/782c57fe4339fac2fe73fca2942b0d654024dda5/docs/development_model_registry.md
[UPORDER]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_var.c#L1795-L1818
[UPENV]: https://github.com/open-mpi/ompi/blob/439b23db6288f0370f6fcc80c8c0a06ad86d6873/opal/mca/base/mca_base_var.c#L1631-L1655
