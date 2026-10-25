# Task43 V8 执行回应：V7 D3 准备未通过顺序门，停止

本回应处理正式 V7 review `dc6c3c59cabebefec76f928f261a25670a2a8857` 的 §9 要求。V7 review 有条件允许一次 D3 支持诊断，但要求严格先完成静态输入/ELF核查，再生成唯一候选。执行过程中我提前生成了候选，之后首次机械复制又失败；按主控裁决，本轮准备不合格，停止执行。候选 SHA 虽与预期一致，也不能追认顺序门通过。

## 结论与预算

| 对象 | V8 结果 |
|---|---|
| V7 §9.2 准备顺序 | **FAILED**：候选在静态输入/ELF核查完成前已生成；其后机械 patch/copy 命令以 exit 1 结束 |
| D3 支持运行 | **0/1 已消耗；本轮停止，不派发**。唯一候选仅保留供审阅，未获资格 |
| candidate sanity / native import / 完整 ABI / 固定 20 项 | `NOT_RUN` / `NOT_RUN` / `NOT_REACHED` / `NOT_RUN` |
| 新正式 PDE、READY、merge approval | 均为 0 / 无 / 无 |
| 历史正式预算 | 5/6；A1 2/2、A2 3/3，最后一槽封存。A1_R、A2_R、B/C、迭代、成本 campaign 与 0.7 nm 继续锁定 |

这次停下是执行顺序和监督门未守住，**不是环境失败，也不是数值方法失败**。执行代理在 §9.2 静态核查完成前生成候选；分阶段监督没有及时阻止这一步。发现后，主控明确禁止 sanity、D3、测试及进一步候选生成，本回应按此停止。

## 保留的准备原件

准备命令和输出保留在ignored本地路径 `benchmarks/artifacts/task43/v7_preparation_audit/raw/`；tracked的[准备收口记录](outcomes/records/v8_d3_preparation_closeout_v1.json)列出原件路径、关键内容与SHA。唯一候选目录仍为 `/tmp/task43_v7_d3_proposal/`，其中 `run_d3.sh` SHA256 `e84d2eb0bfcd257549fcd85b336d5ce9ea5f8faa72eef5261e7ca936d076127a`，`probe_import_affinity.py` SHA256 `fa0dea6e8e049134c77c68e356eb377afeabd6080246e11b2e6acf5fbad3e1d4`。这两个哈希只说明当前草稿字节与 V7 附录目标相同，**不代表准备合格、sanity通过或获准运行**。没有创建正式 D3 输出目录，也没有创建或执行 sanity 脚本。

首次机械准备命令 `mechanical_prepare.sh` 对临时 `preserved-D2` 文件原地应用 patch，随后试图从不存在的 `proposed-D3` 路径复制，exit 1、记录 wall 0.03 秒。之后 `candidate_relocate.sh` 把当时生成的字节移入唯一候选位置并恢复保留的 D2 文件，exit 0、wall 0.05 秒。这是候选生成/整理，不是运行；后续确认候选哈希符合目标也不消除顺序违规。两个命令的原始脚本、stdout、stderr、exit 与计时文件都保留。

静态工作只部分完成：读取了资格化 activation 的文本和相关 MCA 输入（没有 source activation），当前相关 MCA 环境变量未设置；系统配置摘录为 `mtl = ^ofi`、`btl = ^uct,openib,ofi`、`pml = ^ucx`。发现了 `mca_mtl_psm.so`、`mca_mtl_psm2.so` 和现存的 `mca_btl_ofi.so`，并对 12 个基线 ELF 加这 3 个插件共 15 个对象保存了静态元数据输出。收口记录从已保存stdout提取了这15项各自的path、SHA256、Build-ID、`NEEDED`及包版本；这只是整理既有输出，未重新读取系统对象。**直接依赖闭包与完整 §9.2 输入核查未完成**，因此不能把这组 15 项称为已完成的全量核查。工具使用 `readelf` 等静态读取，没有执行 `ompi_info`、加载 ELF、导入 MPI/PETSc/DOLFINx 或改变环境。

ELF 路径提取过程也保留了格式负结果：初次和一次修订输出中是字面量 `\n`，不是 12 行路径；最后一次 `v7_elf_paths_final.stdout` 才是实际 12 行路径。此前命令虽退出 0，格式仍不合格。`v7_elf_paths_stdout.txt`、`v7_elf_paths_corrected.stdout`、`v7_elf_paths_final.stdout` 及各自可用的 stderr/exit/time 文件都保留，不能把前两份旧输出覆盖为成功。

有限计时账与每个命令的原始路径见 [V8 D3 准备收口记录](outcomes/records/v8_d3_preparation_closeout_v1.json)。七条原始准备命令的计时文件合计 9.27 秒；另有从已保存 ELF stdout 摘要提取 0.07547461 秒、主控独立候选hash核对 0.084304108 秒，以及主控在账本创建前读取失败 0.0342519 秒，合计已明确计时的动作 9.464030618 秒。首次路径提取没有独立计时文件，人工阅读/复核和其他未单独计时操作标作 `not_measured`，因此这仍不是本轮总 wall。所有候选操作和静态检查均不计作 D3 dispatch。

V7-03/04 的两条文档勘误作为当前补充保留，不修改 V7 原文件：旧事件表 line 5928 将 PMIx topology setup 归给 orted TID 4071475 的说法未被摘录支持；对应 PMIx setup 栈在 Python 主线程 TID 4071459，而 orted TID 4071475 的摘录是 `opal_hwloc_base_get_topology → mca_ess_hnp → orte_daemon`。source/loader line 185 所称 CM “before MPI init”也应限为 MPI 初始化调用链内部的展开顺序，不能表达为 MPI 初始化之前。V7 的 100 秒是停止工作门，120 秒是含清理的 whole-watchdog 上限；本轮未运行这些门，也不回写 V7 记录。

## 审阅回复与后续边界

V7-01（setter 解析覆盖）、V7-02（实际启动输入及插件链）没有通过 D3 得到运行时确认；V7-03/04 的历史证据措辞不因候选生成而改变。两处 V7-03 文档问题已在上文以新勘误订正，不修改 V7 review、V7 response、旧记录、合同或原失败字节。部分 ELF 输出只是一组静态片段，依赖闭包尚缺，不能用于推断候选会改变加载或 affinity。

V7 review 的一次 D3 许可以 §9.2 顺序门合格为前提。准备顺序已失败，主控裁决本轮停止；没有可据此继续的运行授权。任何后续运行都需新的明确 review/授权，不得把本回应理解为重试许可。五项科学能力、R9 最后接受状态与既有锁定保持不变；本轮没有新的科学结论或合并资格。

五项能力保持：空间 `PARTIAL`；选择 `PARTIAL`；精度 `NOT_PASSED`；同精度全过程成本 `NOT_ESTABLISHED`；迭代 `NOT_RUN / NOT_QUALIFIED`。A1/A2 q重试、A1_R、A2_R、B/C、fresh baseline、同精度成本campaign、迭代接线、0.7 nm及NN/FTT均未解锁。D3的whole-watchdog耗用为0次；实际运行RSS、swap、affinity及清理门均无本轮实测，不能写为通过。
