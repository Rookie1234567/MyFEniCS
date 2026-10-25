# Task43 Review V6 执行回应：affinity trace、装载身份与有限后续假设

本回应对应正式审阅文件 [review_report_v6.md](review_report_v6.md)，该 review 提交为 `9e11b6e0804c2fd51e99353ec306483af0621580`，其被审代码提交为 `cab17f542bfffeb6598eedfed3194d07ea047630`；V7本轮起点也是 `9e11b6e0804c2fd51e99353ec306483af0621580`，任务数值基线为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`。本轮只读整理旧 trace、启动器与静态 ELF/package 信息；没有改测试或数值源码，也没有运行测试、driver、项目导入或模型计算，新增 formal dispatch/PDE/READY 为 0。

## 对 Review V6 §9 四项要求的逐项回应

| Review项 | 本轮处理 | 尚未闭合的边界 |
|---|---|---|
| V6-01：D2放行前遗漏已知 setter 来源 | 将D1/D2全部204条成功setter逐事件列出；D1含hwloc 196、libinfinipath 2、libpsm2 2，D2仍含两类网络库setter各2次；明确记录D2前监督审查遗漏 | 不能把旧决策归因环境未知或数值方法；D3未运行 |
| V6-02：strict CPU1与新链未过门 | 保留两次CPU1偏离和V6原负结果；仅提出worker-local `OMPI_MCA_pml=ob1`静态假设 | 全程CPU1不通过；候选未创建、未预检、未执行，不证明CM/PSM调用会消失 |
| V6-03：source snapshot汇总false与逐项表不一致 | 新解析器对路径键规范化后，D1/D2均为8/8文件哈希匹配；原件和旧false值保留 | 原生成器未找到，无法归因原false的确切成因，不将历史字段改写成true |
| V6-04：旧latest与完整性措辞 | 当前文档把V5/V6/V3旧段落标为历史，区分Git内204事件表/代表栈与仍在ignored目录的12份完整raw trace；将停止点写明为首个显式`dolfinx`导入返回后的`native_import_complete` | 两次导入中观察到setter；完整MPI/PETSc ABI检查`NOT_REACHED`，20项S2动态案例`NOT_RUN` |

本轮未授权也未执行任何后续support probe、S2测试、正式模型、READY或合并。A1/A2 q重试、A1_R、A2_R、B/C、fresh baseline、同精度成本campaign、迭代、0.7 nm、NN/FTT继续锁定。正式预算仍为5/6（A1 2/2、A2 3/3），最后一槽封存。

CPU affinity 是操作系统允许某个线程运行的 CPU 集合。这里严格要求 CPU 1，即集合只能是 `[1]`；某个导入期线程成功把自身集合设为 `[0]` 或其他集合，就不能因稍后恢复为 `[1]` 而记作全程通过。`strace` 中的 setter 事件只代表记录到的成功系统调用，不等于对所有线程连续采样。

## R1：D1/D2 trace 全事件清单

[逐事件索引](outcomes/records/v7_affinity_trace_event_inventory_v1.json)从 12 份原始 trace 逐条整理出 204 个 `sched_setaffinity` 事件；每行绑定原 trace 文件 SHA、行号、去掉换行符后的原始 syscall 行 SHA、时间、TID、目标参数、CPU mask、返回值、首个非 libc 调用帧和可证的阶段/角色。主控又独立核对了 12 份 trace SHA 与 204 条原始行，未发现不一致。

| 原 driver | 事件数和首个非 libc 调用库 | CPU mask 统计 | 终态范围 |
|---|---|---|---|
| D1，首个显式 `dolfinx` 导入返回后在 `native_import_complete` 停止 | 200 次成功 setter：`libhwloc` 196、`libinfinipath` 2、`libpsm2` 2；未分类0 | `[1]` 10次；非 `[1]` 190次 | 导入过程已触发setter；停止点在该导入返回之后，不代表完整ABI检查已执行 |
| D2，worker shell 设置 `HWLOC_COMPONENTS=-x86` 后停止 | 4 次成功 setter：`libinfinipath` 2、`libpsm2` 2、`libhwloc` 0；未分类0 | `[1]` 2次；非 `[1]` 2次（`[0]`） | 屏蔽 hwloc x86 组件没有消除两类网络库的 setter |

R1记录及D1/D2 closeout compact保留了 D1 两条 `[33]`、`[30]` 的资源成员样本和相应 trace 事件。它们是局部采样与 syscall 证据，不构成连续全线程监控。V6两个支持运行合计 whole-watchdog `20.736750496551394 s`；task VmSwap采样峰均为0，global `pswpin/pswpout`增量均为0页，资源时限和最终清理记录成立，但严格 CPU1 门未通过。旧 summary 没有单独保存 launcher exit 字段；compact 引用的历史外层退出码保持独立，不将空字段解释成未知 worker 或清理失败。

## R2：旧支持原件与当前装载栈静态身份

[source/loader审计记录](outcomes/records/v7_affinity_source_loader_audit_v1.json)列出六个 V5 support 根与 V6 D1/D2 两个根的逐文件 SHA 映射，并保留 D1/D2 四份实际shell/probe文本和两份机械差异文本：[驱动快照与diff目录](outcomes/records/v7_affinity_driver_sources/)。12份完整原始trace仍留在ignored artifacts；Git仅保存204条事件表、代表栈摘录和索引，不包含完整trace。V5六根原件仍按原路径/hash保留；V6两个根的八条源码清单分别与其 `source_snapshot` 逐字节匹配，记录的 source HEAD 是 `b5a4b69c25c6be92faf0116e119904c438cbe297`，状态中既有测试文件修改和 S1 未跟踪输入，符合当时取证范围，并不等同于干净工作树。

实际启动链由 watchdog 启动子 shell；`exec taskset … strace … python` 后，probe 的直接父进程是 strace，不能冒充 watchdog。D1 probe PID/PPID 为 `4071459/4071446`，D2为 `4076967/4076949`；MPI singleton 初始化另产生 orted。原 probe 保存PID、start_ticks和各TID的亲和性。本轮不添加 A1 真实-main sentinel，也不弱化直接父身份检查。

probe 在每个阶段先计数自身 trace 中的 `sched_getaffinity`，逐TID读取亲和性，再最多等待1.5秒，直到 trace 中 getter 数量达到预期增量；随后读取所有 trace 文件，筛选返回0的 setter 并解析mask。`trace_sync=true` 仅说明这道局部同步检查成立，不证明所有后代持续受控。两次均在首个显式 `dolfinx` 导入返回后的 `native_import_complete` 发现非 `[1]` setter，probe退出23、watchdog记 `WORKER_FAILED`、外层退出2。导入已触发底层MPI/PETSc初始化，但随后完整 `_native_abi_check()` 为 `NOT_REACHED`。D1原计划的collect-only与D2四个selector的20项测试均 `NOT_RUN`。

两版机械差异除独立目录与名称外，还包括D2 worker增加 `HWLOC_COMPONENTS=-x86`、probe记录/校验该值，以及将D1未到达的collect-only分支改为D2未到达的20项定向测试；不能把D1→D2描述成只改了一个环境变量。两版完整原字节及差异均已保留，旧trace与失败终态未改。

V6旧记录把 D1/D2 的 `source_snapshot_all_match_manifest` 写成 `false`。本轮新解析器仅在去掉 `source_snapshot/` 路径前缀后比较键与 SHA，两个 driver 都是8/8匹配。原始比较生成器没有在保留范围内找到，因此本轮不推断当时 `false` 的精确产生原因。六个 V5 的输入身份也按原记录逐项保留；不改写任何旧 summary、trace、resources 或 source manifest。

| 当前安装文件 | 当前包版本 | SHA256 / Build ID | 解释边界 |
|---|---|---|---|
| `libhwloc.so.15.7.0` | `libhwloc15 2.10.0-1build1` | `86dff44a…` / `a3560ac1…` | 当前安装的静态文件身份；D1 trace 有对应 hwloc setter 调用帧 |
| `libinfinipath.so.4.0` | `libpsm-infinipath1 3.3+20.604758e7-6.3build1` | `0b7ad2e8…` / `eb3058c4…` | 当前安装的 PSM 库；两次 trace 都有 setter |
| `libpsm2.so.2.2` | `libpsm2-2 11.2.185-2build1` | `7adf30d6…` / `1d3e92a2…` | 当前安装的 PSM2 库；两次 trace 都有 setter |
| OpenMPI `4.1.6-7ubuntu2` 的 `mca_pml_cm.so` / `mca_pml_ob1.so` | `libopenmpi3t64:amd64` | `fc4f371d…` / `44359298…`；`cfa0e739…` / `4a20d812…` | 当前包内两种 PML 模块均存在；静态安装信息不证明当时选择了哪个模块 |
| trace中的 PMIx 路径 `.../pmix2/lib/libpmix.so.2.13.1` | `libpmix2t64:amd64 5.0.1-4.1build1` | `2d53cf2c…` / `f197acdd…` | trace路径与当前alias解析的realpath相同 |
| `mca_ess_singleton.so` | `libopenmpi3t64:amd64 4.1.6-7ubuntu2` | `2981b3b5…` / `ce9137a5…` | 本轮记录曾多录一个`c`，现据主控只读核对值订正；原 inline metadata stdout 未保存 |

审计JSON另列以上 ELF 的完整 SHA、Build ID、SONAME、`NEEDED` 和包身份。它们是本轮查得的当前安装文件，并非 D1/D2 当时映射文件的留档字节，不能冒称为历史运行时二进制证明。trace的 unwound stack 显示 setter 的首个非 libc 帧是 PSM 库；栈上还经过 OpenMPI 通用 component repository/open 路径和 `mca_pml_cm.so`。相邻 `mca_pml_cm_add_procs` 只作栈上下文，不认定为 setter 的直接函数。固定的 hwloc 2.10 文档和实现链接见记录中的 `fixed_source_references`。

## R3：待审的单一 worker-only 假设，不执行

完整机械候选差异仅保存在 [D2→D3 unified diff](outcomes/records/v7_affinity_driver_sources/d2_to_d3_candidate.patch)，SHA256 `6ab689218e31c4977afec560b55cacfb3e59e62b1416340f875fa4755e790497`。它只拟将 D2 support root/脚本路径改到新目录、保留 D2 probe 的原字节，并在 worker shell 增加 `OMPI_MCA_pml=ob1`；D2 的 `HWLOC_COMPONENTS=-x86`、资格化 activation、watchdog、CPU1、MPI1、线程及资源参数不变。为兼容原 probe，两个 `TASK43_V6_D2_*` 环境变量名也沿用，仅把其值指向新目录。拟议路径 `benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1` 和 `/tmp/task43_v7_d3_proposal/run_d3.sh` 均未创建；候选命令仅为 `bash /tmp/task43_v7_d3_proposal/run_d3.sh`，未执行。拟保留100秒whole-watchdog、RSS≤8 GiB、task swap=0及现有更严格资源门；即使未来获准，也不得自动重试或扩时，本轮没有任何新增运行额度。

这个设置只是请求 OpenMPI 选择 OB1 的待审假设。现有栈只能证明 D1/D2 的 PSM setter 路径经过 CM PML 组件装载上下文，不能证明该环境变量会避免加载/构造 CM 模块，也不能保证 PSM setter 消失。它会改变 MPI 通信路径；即使未来单 rank 导入不再观察到 setter，也不能据此取得多 MPI 或数值资格。未来若要运行，必须有新的书面授权，重新冻结并审阅完整启动链；如果 ABI/affinity 门允许 probe 到达测试阶段，D2 保留 probe 的4个固定 node IDs、20个展开案例也须一并授权。本轮没有创建可执行 runner，没有执行该候选或这些案例。

## R4：状态和范围

| 项目 | 当前结论 |
|---|---|
| V7改动 | 只新增只读审计记录、保留脚本/diff和文档；没有改数值源码、V6 driver、共享环境或冻结合同 |
| 测试与运行 | 新support driver、导入、pytest、模型/网格/solver/PDE均为0；S2 helper保留既有静态修正，20个案例仍 `NOT_RUN` |
| 预算 | 新增 formal dispatch 为0；历史 formal 为5/6，A1 2/2、A2 3/3，最后1槽封存；V6两次support额度已用，V7没有新support尝试 |
| 五项能力 | 空间 `PARTIAL`；选择 `PARTIAL`；精度 `NOT_PASSED`；同精度全过程成本 `NOT_ESTABLISHED`；迭代 `NOT_RUN / NOT_QUALIFIED`；0.7 nm未运行 |
| 研究/合并资格 | R9仍是最后接受状态；CPU1导入链没有通过，OB1候选未执行；没有新endpoint、READY或production merge approval |

R1/R2处理记录的显式计时小计为 `24.384309872 s`；人工阅读及未记时的 shell/文件检查未计时，因此这不是本轮全部工作的精确总耗时。未运行 full suite、FFCx witness、旧场恢复/采样/积分或任何正式模型。V6的审查监督遗漏和 D1/D2 负结果均按原件保留，没有归因于数值方法失败。

主控最终只读核对415个文件引用hash全部一致，候选patch仅在内存中按原文本核对，未生成runner。暂存后的全范围 `git diff --check` 曾报21处尾随空格，全部位于三份unified diff的合法单空格空白上下文行；逐行核实后保留补丁原字节，其余文件的定向格式检查通过。该静态检查失败与复核费用均留在处理账本，不是pytest或支持driver运行。
