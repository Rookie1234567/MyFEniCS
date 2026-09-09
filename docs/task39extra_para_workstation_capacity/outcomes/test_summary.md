# 测试与证据资格

性能实现提交：`f124679e75915758076d9240bd4bef2f5c772752`。测试均使用本worktree原生activation和complex128/int32 ABI；真实FE及MPI测试在宿主机CPU23执行。没有隔壁文件/进程修改，没有CI通过声明。

| 检查 | 实际结果 | 范围 / 限制 |
|---|---|---|
| 原生R0小FE | 1 passed，387.14 s | 早期CPU2限频环境，不作提速baseline |
| R0 focused | 70 passed、1 deselected，774.76 s | 早期记录；非最终性能代码回归 |
| mode bridge focused | 56 passed、1 deselected，2.07 s | 修复前后12浮点末位差身份桥、原V5合同 |
| 新性能定向FE/缓存/采样 | 5 passed，125.44 s | 真p4 CSR冷/热缓存逐位一致，p4/p6随机复向量作用逐位一致 |
| 旧V5/native/监督回归初次 | 86 passed、1 failed、1 deselected，34.24 s | 唯一失败为旧worker身份校验错误分类；原日志保留 |
| 两行分类修复后监督/MPI回归 | 11 passed，31.51 s | 含上述失败项，真实MPI1 soft/hard stop与后代清场 |
| 最终native监督与纯测试 | 3 passed、3 deselected，2.10 s | 新增真实native supervisor的PSS跳采测试；另外3项FE测试已在相同数值代码通过，不重复编译 |
| Ruff | 新模块/新测试/改动的physical action通过；其余修改文件65项均为基线已有，无新增 | 保留逐文件baseline/current比较；不声称全库lint通过 |
| 文档合同（原则、回顾、总账Markdown） | 20 passed，0.05 s | 最终任务材料本地检查 |
| compileall / git diff --check | 受影响模块通过 / 通过 | 未跑全库pytest，未跑CI |

这里按实际命令报告，不把重复运行相加当独立测试数。新测试文件共有6项，分两次覆盖全部；相关旧回归87项在分类修复后分组覆盖。唯一历史deselected项`test_real_e1_inputs_load_without_fe`需要未随Git提供的ignored diagnostic_audit.json，之前已实际失败于FileNotFoundError，未篡改成通过。

本次有一条回归命令使用了错误旧文件名，exit4、no tests ran；更正后才取得上表86/1结果。首次独立p6诊断以脚本方式启动时未找到tmp namespace，改用模块方式后完成；都不是formal PDE retry。新文件的5项Ruff格式提示已修复，未作无关代码整理。

监督分类修复只把`cooperative_stop_identity_and_signal`异常记为MONITORING_FAILED，保留原异常与清场；没有放宽RSS/swap或时间上限。其余监督改动为native PSS约5秒采样，RSS/swap照常读取。FE优化使用严格浮点、禁止FMA contraction，不使用fast-math。逐行诊断与拒绝方案见[kernel evidence](records/kernel_performance.json)，日志hash见[test evidence](records/performance_tests.json)。
