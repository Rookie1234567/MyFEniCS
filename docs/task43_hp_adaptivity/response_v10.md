# Task43 V10 回应：三条派生证据的有限静态纠正

本轮依据正式V9 review `9be37f5dda06039e50400d395baa732e70012976` 第9节执行E1–E3。工作区为登记的canonical worktree `/home/fenics/Projects/NN-Lab-V2`，分支为 `task43_hp_adaptivity`。从被审交付 `782c57fe4339fac2fe73fca2942b0d654024dda5` 安全fetch、fast-forward到review，新增内容只有review；没有覆盖其他工作。没有改数值、测试、driver、activation、冻结合同或历史记录。

正式V9 review已接受**固定D3启动链与固定20项测试的有限工程证据**。本轮保留这一结果，只纠正归档关联错误。实际历史D3运行HEAD仍是 `ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba`，固定被审代码是 `c245dd060882df4dc6f30224ac0fa8be93f764d2`；后续文档提交不是当时运行源码。长期源码基线仍为 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`。

## E1：原文与错误所在层

依赖表记录“某个库需要另一个库”，每个对象同时带文件身份和元数据，便于追溯输入。主控亲读了原stdout的三个EDGE末尾及紧随的BRIDGE块，再对照旧JSON和新逐字段差异：原采集文本各块清楚、对象元数据一致，**错误已经确定发生在后续派生记录关联层**；无法恢复旧JSON生成器、具体解析语句、调用和生成时间，继续标为 `UNKNOWN`。相邻污染模式本身不足以证明具体代码根因，也不能倒推出当时launch必然错误放行。

| 旧JSON字段行 / 边 | 原stdout边界 | 更正内容 |
|---|---|---|
| 781–795：`mca_btl_ofi.so → ld-linux-x86-64.so.2` | EDGE 415–420；下一BRIDGE 423–431 | 移除误挂的PSM元数据；SONAME恢复loader，NEEDED为空，package及owner恢复libc6/loader路径 |
| 829–844：`libpsm_infinipath.so.1.16 → libc.so.6` | EDGE 447–453；下一BRIDGE 454–462 | 移除误挂的common_ofi元数据；SONAME恢复libc，NEEDED只含loader，package及owner恢复libc6/libc路径 |
| 885–904：`libmca_common_ofi.so.10.0.2 → libc.so.6` | EDGE 485–491；下一BRIDGE 492–504 | 移除误挂的fabric元数据；SONAME恢复libc，NEEDED只含loader，package及owner恢复libc6/libc路径 |

每条更正4字段，共12字段；三条的realpath、文件hash和Build-ID均未变。其余58条的原字段未变。完整旧值、新值和行号见[逐字段差异](outcomes/records/v10_static_evidence_sources/corrected/direct_needed_edge_field_diff.json)；[边界摘录](outcomes/records/v10_static_evidence_sources/corrected/direct_needed_raw_boundary_excerpts.json)保留必要原文。

| 身份 | SHA256 |
|---|---|
| 既有 `raw/map_direct_needed_paths.stdout` | `42700961db2b4ca1ae2206d93c18a6e0ad8986ec72b818b26a192b082eb005c4` |
| 既有 `raw/map_direct_needed_paths.sh`，仅阅读归档，未执行 | `1568de57c0911a88c062df5b9d504ae42fad3e0b93217f730e55f2631ee1b8b2` |
| 原V9 v1依赖表，保留原字节 | `d013d64d8c9e300e39b04b927ba23c3e9e5c55d1f02cded732550cd4093401e3` |
| 本轮纠正版依赖表 | `858950cdb8fa02301bb9b7f88a399a3c34b68134a6bc181b28f9753feb3b6bcf` |
| 本轮逐字段差异 | `18dd3e98316575c174145129f326843b26366a6ea03a83a4a8fa397c0e626e29` |

原采集脚本只输出文本，不生成旧JSON；可恢复的原采集退出码为0、已有计时37.52秒，属于旧费用，不在本轮重复计费。保存原命令、退出信息及派生UTC的入口见[本轮纠正记录](outcomes/records/v10_static_evidence_correction_v1.json)。

V9-02补充材料也只取自同批hash-bound旧文本：tracked activation的实际venv source行、venv身份、MCA长短变量、普通参数文件、override与搜索路径来源。原记录的 `pml=^ucx` 是普通低优先级配置，不能只因与worker-local `ob1` 字面不同就否定已接受的D3。安装字符串、包归属及路径事实不是构建头文件或完整运行时映射证明。本轮没有source activation、读取当前ELF或执行环境探针；具体摘录、脚本与命令/hash索引见纠正记录。

## E2：主控独立核算

代理用EDGE/BRIDGE分块，主控另用PACKAGE终止的分块方式，只解析既存文本。主控还从已绑定的 `recheck_15_elf.stdout` 重建旧15对象所需边集合，然后与最终纠正版的每条原字段、边界行号及逐字段差异进行比较；没有只相信代理的数量或PASS标签。

| 核算项 | 实际结果 |
|---|---|
| 唯一 `(parent, needed_soname)` 键 / parent | 61 / 18，无重复键或缺边 |
| 集合覆盖 | 旧15对象48边 + 三桥13边，互不相交并恰好覆盖61边 |
| resolved对象 | 24个realpath，各自hash、Build-ID、SONAME、NEEDED、package及owner一致；同path或同path/hash无冲突 |
| 名称及别名 | 61个needed名均等于对应SONAME；candidate→realpath绑定有旧原文。三个桥及MPI、PMIx、libpsm2绑定保持 |
| 全字段比较 | 最终61条全部原字段与主控独立结果一致；3条/12字段差异及三处行号范围均相符 |
| 输入原件复核 | 主控另核14份activation/MCA相关原输出与采集脚本hash，匹配旧root S1 manifest |

这些检查证明保存文本及其新派生表的一致性，不是重新资格化当前安装文件、生产ABI或科学端点。原v1及所有V8/V6失败、历史review、合同和正式失败记录均保持原字节。

## E3：失败、费用与交付边界

本轮局部静态错误均保留，修复只重做有关步骤：代理parser初次误解BRIDGE头格式；一次输出虽exit0但旧JSON行号范围错误；随后范围闭区间断言失败，最后修正成功。主控独立核算初次正则表达式跨块匹配失败；交叉比较一次过早读取旧产物，一次未跟随更正字段名而KeyError，之后逐字段比较成功。另有读取不存在 `derived/accounting.json` 的cat错误，以及代理裸 `python` 不存在的辅助读取错误；后两项没有执行Python脚本或native模块。它们不能写成“本轮零失败”，也不应称作PDE、sanity或支持运行失败。

失败输出、脚本快照、退出码、计时及被替代产物索引见[纠正记录](outcomes/records/v10_static_evidence_correction_v1.json)。计时旧小计保留 `55.18740113839802 s`，本轮新增已测动作与历史费用分列；原D3 whole-watchdog及旧sanity不重复计入。人工阅读、编辑、未独立计时的Git操作和辅助读取列为 `not_measured`；不补造整轮wall。最终费用和文档核验结果以该记录及收尾索引为准。

新增support driver、sanity、native import、ABI运行、pytest、collect-only、PDE、formal dispatch、READY全部为 **0**。没有重跑D3终态审计程序或旧采集入口。sanity1/1、D3 1/1保持耗尽；正式5/6、A1 2/2、A2 3/3，最后一槽封存。

空间 `PARTIAL`、选择 `PARTIAL`、精度 `NOT_PASSED`、同精度全过程成本 `NOT_ESTABLISHED`、迭代 `NOT_RUN / NOT_QUALIFIED` 不变。accepted9/R9、R10拒绝、旧独立精度失败、A1受控停止和A2历史负结果不改。A1/A2 q重试、A1_R、A2_R、B/C、fresh baseline、成本campaign、迭代、0.7 nm、NN/FTT继续锁定。静态整改不提供新运行许可、生产资格或merge approval；只提交同一执行分支，等待正式审阅。
