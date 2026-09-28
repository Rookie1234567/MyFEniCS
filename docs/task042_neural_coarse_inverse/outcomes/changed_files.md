# Task042 实际变化与依赖分组

| Selective merge组 | 变化与数值行为 | 依赖/验证/fresh证据 | 建议顺序和边界 |
|---|---|---|---|
| production numerical/core | 没有把研究逆提升生产默认；旧p6 action/runtime仅显式`borrowed_p4_witness`/`retain_coarse_schur` opt-in | paired默认拒绝/ownership测试、noncommuting原p4测试、真实F1 A4/A6/恢复 | 先审查opt-in与所有权；本轮无合格F5，不能宣布production逆替换 |
| research-only numerical | `coarse_inverse_protocol.py`、`learned_coarse_inverse.py`、`learned_coarse_runtime.py`、`learned_coarse_data.py`、`learned_coarse_packets.py`、`learned_reduced_correction.py`、`learned_training.py` | 原方程/有界局部PC/strict return→p4同身份→teacher packet/POD→线性/NN；pure tests与F1/F2/F3/F4实际记录 | 协议→原p4 witness/容量→离线数据/表示→候选；严格逆失败，维持research opt-in |
| reusable runner/watchdog | `benchmarks/subreaper_watchdog.py`新增可选memory_envelope/health/include_pss；原默认不变 | 既有subreaper语义，资源触线orphan/setsid清理且sibling不受信号；可读健康资源检查 | 先验证own descendants范围和cgroup权限声明；不合并其他任务共享规则 |
| research orchestration | `src/runners/task042_shared.py`、`task042_experiment.py`、`task042_coarse_stages.py`、`task042_training.py`及`src/io/task042_profile.py` | 自有flock、clean source、隔离ABI、逐阶段退出；src承载算法，runner仅装配/记录 | 所有numerical/data模块之后；普通runner新增显式dispatcher，不复制每case solver |
| checker/benchmark/tests | `src/test/test_task042_*`、解析研究profile枚举和input validation opt-in | tiny complex arrays/真实80mode元数据/borrowed witness/资源监督；同组16 RHS及独立raw Gate重算 | 核心接口/枚举变化的focused验证，不运行邻heavy下full pytest或MPI2/4 |
| local activation/config | `scripts/activate_task042.sh`、`task042_preflight.py`、`task042_bounded_check.py`、Task042 dat/profile/依赖lock/尺度模型 | 单核/线程/缓存realpath、FE/ML分环境、CPU-only FP64、每dat一次明确阶段 | 配置→ABI/probe→数值；不得把本机readonly prefix路径当普遍部署配置 |
| compact evidence/docs | 本outcomes/v2 JSON/CSV、`response_v2.md`、本分支progress/registry Task042段 | 所有实际source/input/dataset/model hash、误差与failed/not_run、过程时间/RSS | 可独立审阅负结果；原task/review/response_v1/F0数值records保留 |
| do-not-merge | `.venv/.venv-ml`、results/artifacts、raw logs/time lines、JIT/bytecode/cache、Q/模型/checkpoint/teacher包 | ignored仅NN-Lab；不包含旧大结果/factor，也不向Git提交大矩阵/权重 | 本地复現artifact，Git只提交必要轻量hash记录 |

所有代码路径与data provenance见[架构](architecture_and_oracle.md)、[数据模型](dataset_and_model_provenance.md)。研究模块名字带Task042的部分承担固定范围入口/记录，不把新的p4数学只实现于benchmark脚本；通用core函数参数化。已有A4/A6物理、传递、DtN库存、材料/几何、BAL_H方程和最终门限保留；既有task/review及其他任务源码、环境、watchdog、锁未修改。仅两个原solver/runtime opt-in点与明确research dispatcher/schema分支改变现有文件。

## 真实实现提交及失败修复

| 完整SHA | 阶段/实际作用 |
|---|---|
| `ae5b7d2b79dec38056e4a8b9bd986429989455dd` | 共享CPU profile、F1原方程与有界PC；首次缺pyvista导入失败，无JIT |
| `23cb4710e3ed2c8f7c51fd2b3f4e4dd952bea716` | NN-Lab graphics依赖固定后一次重试；CFFI缺setuptools，保留失败 |
| `f194e455cf904d255fbb30151f21d12be19bc56b` | 独立setuptools与complex CFFI资格；真实p6/p4构建后默认action拒绝材料化p4，非数值失败 |
| `7188564f1a284049ddac3eb32a77ccbda84c5c6b` | 明确借用p4 witness接口，paired旧行为测试；实际mode complex JSON serialization失败 |
| `cca180f875bd22146f2d30fa4d004e372135dfbb` | complex元数据和数组形状最小修复；F1接口实际通过、B0非零失败保存 |
| `b72448bb2117a0221f041f1b47ac41049750a3c7` | 真实teacher、batch packet/native检查；384对实际生成 |
| `d9de8ad69bfeeac4860e5187e1738c902a3d808e` | teacher资格绑定、表示容量、F1失败state完整audit；oracle实际四rank |
| `28a814d1c740c5c23916fe8053c0de7435608a80` | FP64 CPU MLP/冻结推理与F4候选；静态发现F4-B0手写schema enum漏登记，此source无正式数值负载 |
| `a221d881bae9405c98e351df2b0b9533582e6d50` | enum最小修复/all-phase input test；CPU实际训练300epoch |
| `7216efa605bae155ee383fd716c0fae422448b52` | model/dataset/basis资格绑定、真实训练摘要；三条F4均在此同一clean源码运行 |

这是局部实现/元数据修复顺序，原失败资源与错误保留，未以参数扫描反复求数值成功。最终交付另修正零RHS报告不携带前一个native audit缓存；返回/迭代算法及冻结F4结果不变、不重放、不冒充新文档source。最终测试、静态检查和后续文档HEAD另记录。[run index](records/run_index_v2.json)是每次实际clean运行的身份权威，非最新HEAD回填。


## V3 最新有限诊断（原V2正文保留）

V3新增research-only `learned_geometry_overlap.py`、几何/预算/phase测试和`task042_diagnostics.py`；旧backend只可选observer，默认不变。两独立dat/diagnostic_v3.json显式opt-in、V3活动样本准入、CPU纠正和compact CSV/JSON/response/两总账新增段。numeric SHA与文件hash见[运行账](records/run_index_v3.json)。原task/review/response_v1/v2、原v2JSON/CSV和raw保护，未修改邻任务或共享配置；未获production/merge资格。

最终仅修正Task042 watchdog测试从原始整树样本断言后代；未改变监督器/数值源码，原失败记录保留。冻结numeric source仍7fc3f1434cf4f38f43e5244ebfed3a19d0780a26。
