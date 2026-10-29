# V20 保存R10响应：证据索引（未完成科学诊断）

本目录记录输入、四次支持调用及失败，不包含新PDE或新场。所有完整旧NPZ、源码快照和资源原件在 `benchmarks/artifacts/task43/v20_saved_r10_response/` 或输入锁列明的旧目录中保留。下列文件的内容是实际原件或明确标注的派生摘录，不能把目录存在视为通过。

| 层次 | 入口 | 实际覆盖 |
|---|---|---|
| 固定输入 | [input_lock.json](input_lock.json)、[180单元静态映射](locked_cell_degree_map.csv)、[主控独立映射](root_static_map_read.json) | 原JSON/已提交CSV交叉核；两原NPZ只做外层文件hash，不在槽外打开成员 |
| 准备 | [static_preparation.json](static_preparation.json)、[静态失败](static_preparation_failures.json)、[预审](root_static_review.json) | 分支/FF/身份；普通路径/schema错误保留；AST和shell静态检查不冒称pytest |
| T1 | [manifest](T1/run_manifest.json)、[test XML](T1/tests.xml)、[root判断](T1/root_decision.json) | 6通过/1失败/5未运行；文字断言失败 |
| T2 | [manifest](T2/run_manifest.json)、[test XML](T2/tests.xml)、[root判断](T2/root_decision.json) | 节点7–12共6通过，前6历史复用；不是最终12项批次 |
| D1 | [manifest](D1/run_manifest.json)、[失败原行](D1/worker.log.txt)、[root判断](D1/root_decision.json) | q8到达J锚点复现失败，q10未运行；没有完成阶次 |
| D2 | [manifest](D2/run_manifest.json)、[test XML](D2/tests.xml)、[root判断](D2/root_decision.json) | 同worker第1项ULP fixture失败，后2项及真实两阶未运行 |
| D2修正 | [原fixture摘录](D2/fixture_witness_excerpt.json)、[修复身份](post_D2_static_fix.json) | 排序JSON导致并列最大witness不同；最后修复仅静态，NOT_RUN |
| 主控终态 | 各槽 `root_closeout.json`、`root_decision.json`、`strace/`、`resources_compact.jsonl`、[supervisor终态](supervisors_post_exit.json) | 亲读全部trace/资源/退出并分类；自动审计的非零退出“UNCLASSIFIED”由手工decision明确归类，原自动记录保留 |
| 归档身份 | [文件hash索引](index.json)、[仅stdlib终态读取脚本](root_closeout_reader.py.txt) | 脚本只读新终态/源码hash/主机进程；没有重跑旧审计器、checker或NPZ |

本轮最多4次支持已全部使用，whole为71.744198859秒，阶段内pytest与watchdog时间不重复相加。原D1/D2失败均保留，后续可用时间不构成新次数。费用与精确未运行项见[机器结果](../v20_saved_r10_response_results_v1.json)和[Response V20](../../../response_v20.md)。

没有新的180单元科学响应表、612通道科学复现表或位置提案；主控表级复核因此未运行，不生成虚假的空表或PASS标签。上面的180项CSV仅是原输入几何/阶数映射。R9/R10旧J/G可作为历史背景，不能替代两阶保存数组重算。两原包内禁止的六个holdout/control数组不打开；D1读取q8的八个允许成员，D2只完成输入外hash与合成fixture，未到真实成员读取。

完整trace仅记录affinity调用及退出，不能当作文件读取的系统调用审计；输入边界由固定reader和成员访问fixture约束。RSS和swap是离散采样，PSS未启用；trace从taskset之后开始；空cache元数据不能证明共享cache稳定。未宣称完整MPI/生产ABI、全仓CI或科学精度资格。

本目录内原日志/XML可能保留pytest原始尾空格；不得为格式检查修剪原证据。最终文档/测试修复提交不追认为T1/T2/D1/D2运行HEAD。
