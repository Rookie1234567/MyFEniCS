# V31：实际工作流接线与前测停止证据

本轮把旧组件测试连接成真实study调用链，检查写出和审核之间是否能实际传递两个指定样本。好处是合成环境中即可发现接线错误；代价为一次有界前测与原始证据。它没有读取生产因子，不代替真实方向诊断或物理解。

| 工作包／数据身份 | 实测或实现 | 资格与证据 |
|---|---|---|
| relative修复／measured合成 | 显式复用原归一化函数；完整study调用穿过原未定义行，七bundle／两态／保存／collector通过 | 生产Gate和容差不变，[测试](records/tests_v31.json)；整条正式链仍未资格化 |
| V31路由／measured小回归 | 新IO/window、profile/run_case、worker与父监督、collector显式后缀、费用结算；旧默认保留 | V31 schema、旧dat拒绝、closed/active/consumed拒绝测试通过 |
| 固定summary计费／measured | carry39.94901336694602s，固定pre/check文件纳入集合并去重 | 不靠仅扫描aux目录的旧glob漏计；历史closed不重开 |
| 完整前测／measured | source99739709…：110测试，109通过／1失败；new V31共8项，7通过／1失败 | 原102受影响scope通过；没有全仓或CI资格，[原始stdout](records/tests_stdout_v31.txt.gz) |
| 新fixture根因／failed | 缺require_live/ledger/auxiliary_wall，绑定时AttributeError，未触达预期InputError | 不是真实回流失败；没有把任意IO异常判为通过，[trace](records/tests_v31.json) |
| 最小修复／implemented | source4734b22d…补三个接口，误调用即AssertionError；17文件静态通过 | runtime NOT_RUN，不将修前109/1追溯为通过 |
| 正式诊断／not_run | 单dat已创建但未运行；正式准入0、actor0、checker0 | Review V28前测新错误即停止，唯一前测额度已用尽 |

合成正例保持18144／40正式尺寸；原作用仅在16个活跃坐标上非平凡，其他行有对角作用。真实数学函数、PortBlocks/BarAction、return_direction/extend_nine、writer、Stage.finish、write-ahead结算及collector执行；仅IO／reader／上游资格为接口桩。没有18144方阵。七合成reader与S34/SH2等计数由调用实际产生，并由断言审核；它们不是生产文件读取或新正式消费。只在断言通过后删除成功的临时合成载荷；失败和partial fixture保留。

| 费用／存储对象 | 值与口径 | 不能推断什么 |
|---|---|---|
| pre监督／shared-workstation | 12.731162693s；entry9.115107226s／pytest7.99s均嵌套 | 不相加重复计费，不算真实actor速度 |
| V27起累计 | 52.68017605994828s／600s，历史39.94901336694602s不清零 | 不重置旧额度或借结项时间续算 |
| 采样同时树峰／swap | 254,758,912B／0；实际采样间隔0.586–1.005s | 不是payload总和、瞬时绝对峰或kernel硬限 |
| 原seven A＋LU／derived | 1,591,420,032B；本轮实际未读取 | 历史设置、冷读、部署驻留、完整N=1费用仍须保留unknown |
| actor规划／derived | 4,807,239,744B≤8GiB | 不冒充实测RSS；前测失败后未正式准入 |
| 本轮费用归因 | 新真实A、factor／solve／LU／QR／FE／训练0；准入和实现成本计总elapsed | 不把传统机制或合成资格归NN |

两冷态eta9历史为0.966205505618／0.981968429990，eta10/g10本轮null。内部抵消、创新与e9对准、真实增益及冷因子资格均NOT_RUN。原完整残差／E/H／功率也未生成；V24 0/5、V23 0/6保留。真实checker未运行，不借成功fixture给它授予资格。

身份与原始记录：[预登记](records/preregistration_v31.json)、[输入库存](records/input_inventory_v31.json)、[环境](records/environment_v31.json)、[资源及累计账](records/resource_costs_v31.json)、[存储](records/storage_v31.json)、[run index](records/run_index_v31.json)、[旧窗口hash](records/evidence_integrity_v31.json)。[response_v31](../response_v31.md)给出完整SHA。窗口10:12:35.920648Z提前closed，active=null、后代清空；无再次准入、无真实载荷和新FE结果。

神经20%仍要求相同完整正确性下相对最佳合格非神经N=1，完整耗时或同时峰降低至少20%，另一项合规。没有完整合格基线或NN配对，不得计算通过率；原尺寸／2TB／48h仍未资格化。下一步仅建议独立关闭修后fixture软件Gate，是否允许真实诊断由新review决定，本批不实施。

| selective merge依赖组 | 行为／依赖与测试 | 当前建议 |
|---|---|---|
| production numerical/core | relative显式导入；原公式／阈值不变，实际study合成已触达 | 等待review，未新增fresh PDE资格 |
| reusable runner/window | opt-in V31路由、固定summary计费；旧默认scope通过 | 等待完整前测，不升普通默认 |
| checker/benchmark | collector显式v31后缀保留v28默认；合成checker通过 | 修后scope未再运行，未整体资格化 |
| compact evidence/docs | 原始109/1、计数、费用、停止和历史hash | 可审阅；保留负结果与unknown |
| research-only/do-not-merge | V31合成接线桩、dat／plan，真实actor未运行 | 不合入master或当生产求解器 |

GitHub视觉NOT_VERIFIED，本地结构检查另列。无subagents、重置卡、dot修改、其他分支或merge。
