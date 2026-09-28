# 准确性、性能与完整资源口径

| 比较项 | 当前结果 | 判定原因 |
|---|---|---|
| 去global p4 LU | not_run | 无真实candidate/参考构造，F0无因子不等于内存收益 |
| R-B0传统低内存 | not_run | 固定PC、原A4内层还未实现 |
| R-LIN线性降维 | not_run | 数据/表示未建立 |
| R-NN相对R-LIN | not_run | 无模型/严格粗返回/端到端计时，G-neural无结论 |
| 原A4 rho<=1e-10、port/recovery | not_run（真实FE） | toy验证器通过只记组件接口证据 |
| 原A6 rho<=1e-6及全部物理对照 | not_run | F4前置未通过，F5没有启动 |
| G-memory>=20% / G-time>=20% | not_run | 没有相同物理本轮R-LU分母 |
| G-neural>=10%或额外数值资格 | not_run | 无同预算R-LIN/R-NN结果 |
| N=1/10/100、break-even | not_run | teacher、训练、setup、完整solve均未测，不假设正单次节省 |

所有R/T/A、A_volume、R00_s/p/total、逐通道功率/复振幅、selected E/H、场L2/scaled-curl、能量误差以及DoF/rows/NNZ，都在 [统一CSV](records/full_p6_comparison.csv) 写为 `not_run`。没有减少通道或省验算，也没有把历史测量移进本轮表。

## F0 全部有监督调用

单位：时间s、内存B；RSS为专用subreaper父+全部后代在同一采样时刻之和，不是单worker VmHWM或对象载荷。采样0.1s，own VmSwap所有样本0，全部后代清场；采样峰不能排除样本间更短峰。

| 调用 | source / 数据身份 | wall s | tree RSS peak B | 分类 |
|---|---|---:|---:|---|
| CPU ML依赖安装 | 初期dirty development | 54.551683 | 190951424 | completed |
| 31测试初检 | dirty development | 2.096333 | 83984384 | passed |
| 33测试初检 | dirty development | 1.461182 | 67633152 | passed |
| pure import初检 | clean2c9b54b | 1.459420 | 45719552 | passed |
| FE import初检 | clean2c9b54b | 3.719178 | 179027968 | failed，错误cache API |
| pure import最终 | clean9934c2e | 1.376872 | 44138496 | passed |
| FE import最终 | clean9934c2e | 2.260087 | 120582144 | passed，complex128/int64 |
| CPU ML import最终 | clean9934c2e | 3.640839 | 236548096 | passed，CPU-only |
| 33测试最终 | clean9934c2e | 1.659649 | 67231744 | passed |
| toy残差证据提取 | 9934c2e +仅交付文档dirty | 1.751461 | 65552384 | completed |
| 文档检查器初检 | 9934c2e +仅交付文档dirty | 2.616270 | 57163776 | failed，检查器自引用/代码围栏误报；既有27测试/Ruff/compile通过 |
| 文档检查器针对复查 | 9934c2e +仅交付文档dirty | 2.954395 | 57368576 | passed，27静态测试及全部定向检查通过 |

前9项顺序wall合计72.22524276096374s，加入toy提取为73.97670381999342s；最大采样同时RSS236,548,096B（约0.220302GiB），没有相加不同阶段峰。[运行账](records/bounded_f0_runs.json)和[索引](records/run_index.json)保留全部值、raw SHA和范围；最后文档/Ruff/compile/ignore检查单列在[测试摘要](test_summary.md)，纳入最终索引。

加入两次上述文档检查后，已监督顺序工作流wall合计79.54736903001322s；最终发布核验/文档闭环另列run index。缓存大小由du实读：新FE venv16,072,704B、ML venv820,117,504B、Task042 tmp369,111,040B，results/artifacts各4096B目录；没有PDE结果或JIT核。这是磁盘占用，不能和RSS相加。

Task042没有运行GPU工作，VRAM peak记 `not_run/null`，不拿0充当测量峰。FE导入映射libcuda但没有执行GPU算子；ML为CPU构建、CUDA不可见且Torch context未初始化。邻GPU100%只是资源阻塞证据。

没有在编辑器/工具代理外层做连续采样；Git、只读审阅、venv创建和文档编辑的全过程wall/RSS未独立测量，写 `未记录`，不伪造整段会话峰或把这些轻开销作为solver时间。所有实际数值研究为not_run，无正式PDE资源曲线、VRAM、R-LU factor存储或候选向量账。

## F1–F5将保留的成本与内存边界

| 项目 | future完整账范围 / 本轮状态 |
|---|---|
| CPU成本 | mesh/JIT、A4/A6 setup、teacher factor/solve/release、流式数据、POD、训练、加载、B0/线性/NN apply、内层A4/恢复/port check、p6 solve/recovery/checker；均not_run |
| RAM | weights、basis、编码/解码、所有cell/patch/bottom factors、port、内/外Krylov、恢复/audit、Python/Torch/BLAS allocator、临时通信；实际unique backing去重；均not_run |
| GPU | 单卡<=8GiB，传输/同步/allocator allocated和reserved分别记录；当前not_run |
| teacher/deployment | 分阶段、分进程退出并核实释放；候选从构建起禁止global p4 factor；本轮二者均未创建 |
| hard Gate | 闲置时treeRSS16GiB/warning12GiB、MPI1/math1、own swap0、reserve和磁盘合同、artifacts20GiB；未因F0成功放宽 |

停止原因是共享资源占用。没有执行后发现数值停滞，也没有把正常实现错误当作算法参数调优理由。
