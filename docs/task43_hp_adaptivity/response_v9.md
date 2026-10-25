# Task43 V9 执行回应：D3 启动链与固定 fixture 的有限复核

本轮依据 V8 review `ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba` 的前瞻授权，完成一次 D3 支持运行。被审固定代码提交是 `c245dd060882df4dc6f30224ac0fa8be93f764d2`；实际 D3 源码 HEAD 为 `ef1e1ca5bb0b79f7cf5f6b6ce828d0e352ac44ba`，该 HEAD 比固定代码多包含 review 文档。主控核对的 8 个 tracked source 项均与固定代码 SHA 一致，D3 实际使用的 shell/probe 两文件也与冻结哈希一致。

这项 probe 检查 Python 启动、MPI/native 库导入、CPU affinity 记录和固定测试能否按受控顺序到达。它能发现启动阶段偏离，但没有建立或求解 Maxwell 方程，因此不能回答网格精度、物理量误差或同精度成本问题。

## 结果

| 项目 | 实测 / 核验 | 范围与限制 |
|---|---|---|
| 新正式 PDE / formal dispatch | 0 / 0；历史额度仍为 5/6，A1 2/2、A2 3/3，最后一槽封存 | D3 是已耗用的单次 support run，不是 formal attempt；没有重试 |
| S1 静态准备 | root review `PASS_STATIC_FOR_NEXT_STAGE`、issues=[]；15/15 ELF 身份匹配、61条直接依赖边、3个桥接对象 | 只读路径/包/ELF证据；S1 未 source activation、未导入 native 库，不能证明进程实际映射了全部文件 |
| S2 候选固定 | `ADOPTED_EXISTING_FIXED_BYTES`、issues=[]；2个driver的实际SHA均匹配冻结目标 | 保留 V8 的顺序失败和初次复制失败，不追认它们为通过 |
| 运行前 synthetic sanity | 19/19通过，内部计时 `0.04185436898842454 s`，wrapper `0.22 s` | stdlib/AST合成输入；未执行probe顶层/main，两个嵌套计时不相加 |
| 固定 S2 fixture | 20 passed，pytest报告 `0.91 s`；worker和外层退出码均0 | 四个冻结node selector展开为 `1+4+12+3=20` 个合成场景；不是full suite，不含mesh、装配、solver或PDE |
| 导入与 ABI | native import到达完成；MPI1、Open MPI 4.1.6、NumPy 1.26.4、PETSc 3.19.6、complex128/int64；记录线程变量均为1 | 只证明本次单rank受控链所记录的值，不证明多MPI或生产流程 |
| affinity trace | 6个trace文件、1010行；44个getter均读到CPU `[1]`；0个成功setter、0个signal、0个trace错误或未分类setter | `strace`从`taskset`之后开始，不构成完整生命周期或loader闭包证明；TID没有独立`start_ticks` |
| watchdog资源与清理 | whole wall `8.763570327777416 s`，13个样本，同时进程树RSS采样峰`180887552 B`，task VmSwap采样峰0 B，全局换入/换出增量0/0页；清理标志true、剩余子PID为空 | 第13行为最后样本：elapsed `8.639170113019645 s`、RSS `38014976 B`、swap 0、exit 0。PSS按profile禁用；RSS/swap是采样值而非连续峰值 |
| root终态审计 | `PASS_LIMITED_ENGINEERING`，scope=`LIMITED_FIXED_CHAIN_AND_20_TEST_BYTES_ONLY`，issues=[]；8/8 source、2/2 driver字节保持一致；8个相关host PID/TID在终态核验时均不存在 | 不授予生产ABI、科学端点、CI或merge资格。审计原件与SHA见[终态记录](outcomes/records/v9_d3_resume_closeout_v1.json) |

D3 的 `cache_metadata_stable=true` 只表示watchdog在未设置 `--cache-path` 时对空SHA `e3b0…` 的记录保持稳定；本轮没有检查全局或JIT cache状态。`trace_sync=true`和阶段采样支持已记录进程身份，但trace从`taskset`后开始，不能据此声称启动器之前或全部线程的全生命周期affinity已经被trace覆盖。

四个实际pytest node selector分别是 `test_synthetic_joint_authority_fixture_passes_only_as_a_coherent_bundle`、`test_synthetic_joint_authority_fixture_rejects_common_missing_identity`、`test_synthetic_joint_authority_fixture_rejects_each_failure_independently`、`test_a2_postprocess_writer_failures_keep_original_error_and_primary`。它们在worker中的固定展开数依次为1、4、12、3；这些都是合成fixture，不是PDE原件重放。

## 阶段顺序、身份与费用

V8 的准备顺序负项仍成立：候选早于静态输入核查生成，机械复制第一次失败；原始控制消息时间和候选整理与停令之间的精确先后没有可恢复证据，继续标为 `UNKNOWN`。V9 的 S1 静态核查和 root 独立复核之后，S2采用了现存的固定字节，执行一次19项sanity；随后对8项源码再做hash核对并保存不可后验替换的 `prelaunch_snapshot`，之后才启动一次D3。V8的“sanity、native import、20项测试均未运行”只属于V8停止时的阶段快照。S1检查的四个MCA选择器为 `OMPI_MCA_pml`、`OMPI_MCA_pml_base_pml`、`OMPI_MCA_btl`、`OMPI_MCA_mtl`；在被检查的登录shell中均未设置。普通配置为 `pml=^ucx`、`btl=^uct,openib,ofi`、`mtl=^ofi`。这些是S1静态输入事实，不代表S1曾启动worker；61条直接依赖的逐项SONAME、候选路径、realpath、对象hash/BuildID和package映射由已有静态stdout解析而来，见 [direct edge map](outcomes/records/v9_d3_sources/preparation/direct_needed_edge_map.json)。

费用按互斥阶段记录：V8准备`9.464030618 s`；V9静态动作由执行代理`45.19 s`、root override检查`0.06 s`、root S1 review内部`0.007662117946892977 s`、S2采用`0.001154409721493721 s`及源码冻结`0.46455399272963405 s`组成，小计`45.72337052039802 s`；V8与V9静态动作小计`55.18740113839802 s`。sanity只运行`1/1`，wrapper`0.22 s`；内部`0.04185436898842454 s`是嵌套参考，不另加。root终态审计处理`0.04148901393637061 s`单列。上述非D3、明确计时的准备/审核动作合计`55.44889015233439 s`；D3 watchdog whole wall`8.763570327777416 s`作为独立运行区间，不把这些阶段简单相加称为campaign墙钟。收尾只读时误拼了两个sanity文件名；单条cat退出码未单独保存，后续命令使组合shell返回0，实际带下划线的文件随后只读找到并核对，耗时`not_measured`，没有重跑sanity或D3（详见closeout path error记录）。未计时的文档编辑、人工阅读和Git/静态整理也标为`not_measured`。完整轻量原件、逐项来源hash及只读审计脚本在 [V9 D3 archive](outcomes/records/v9_d3_sources/README.md)。**未检查GitHub rendered view**；本地文档可读不等同于远端页面渲染通过。

## 科学与合并边界

accepted9/R9仍是最后接受状态。五项能力不变：空间与选择 `PARTIAL`；精度 `NOT_PASSED`；相近精度下更少FE `NOT_ESTABLISHED`；同精度全过程成本 `NOT_ESTABLISHED`；迭代 `NOT_RUN / NOT_QUALIFIED`。0.7 nm未运行。A1/A2重试、A1_R、A2_R、B/C、成本campaign、迭代与其他后续路径继续锁定，formal最后一槽封存；没有新READY或production merge approval。D3结果只支持固定启动链和20个fixture的有限工程范围，不能提升五项能力，也不是科学方法失败或成功的证据。

V8 及更早的review、合同、原始失败记录和数值原件均未改写。记录链接：[D3 closeout](outcomes/records/v9_d3_resume_closeout_v1.json)、[prelaunch snapshot](outcomes/records/v9_d3_sources/preparation/prelaunch_snapshot.json)、[root终态审计副本](outcomes/records/v9_d3_sources/preparation/root_terminal_audit.json)、[当前结果总账](outcomes/summary.md)及[选择性合并清单](outcomes/selective_merge_manifest.md)。本轮没有合并许可；所有生产合并仍待外部review和用户授权。
