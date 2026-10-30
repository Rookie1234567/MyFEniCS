# Task44：小样本代理软件准备（非有限元结果）

代理模型用少量已合格的有限元结果学习“六层厚度 → 三个功率比”，减少后续完整求解次数。本实现只准备这条软件链，并用人为构造的平滑函数检查接线；**目前本文件没有有限元训练数据，也没有小尺度物理代理成功结论**。

## 1. 范围与当前证据

| 项目 | 状态/实际值 | 解释 |
|---|---|---|
| 执行位置 | 当前 own cloud，`task40extra_dot_parallel_cloud` | 不触工作站；唯一 publisher 集中提交 |
| 新用户窗口 | 截止 2026-11-01 11:29:46 UTC | 48 h 内说明可行性，尽量少样本；不把旧 20/40/80 或 100 点当必须数量/研究停止门 |
| 首轮设计 | train 8、dev 4、blind 6，共 18 个不同六维几何 | A–D 是训练前四点；其余训练点不局限于对角线；只有 FE 资格允许才生成标签 |
| 扩充 | 有开发/CV依据才增加 4 个训练点 | 既有训练点及 dev/blind 坐标保持不变，不强求填满大库 |
| FE 标签与物理结论 | **not_run / 0 个由本模块生成** | 模块不导入 FE、不启动 PDE、不用插值冒充 FE |
| 定向软件测试 | 23 tests passed，4.461 s | `unittest`；包括 synthetic GP、负例、盲标签消费门，不是 FE 精度或资源资格 |
| Python / 包 | Python 3.12.14；NumPy 2.3.5；SciPy 1.17.0；scikit-learn 1.8.0 | 使用云端现成轻量环境，无新增安装；不是 Maxwell ABI 资格 |
| Ruff / pytest / CI | 未运行 | 该轻量环境未装 Ruff/pytest；不声称 CI 通过 |

编码/审读阶段从 2026-10-30 11:26:50 UTC 开始，首轮源码/文档交付约 11:46 UTC；六次已记录定向测试分别 4.101、4.639、4.758、4.685886、4.857、4.461 s，合计 27.501886 s（均为软件/合成测试，不含命令启动和编码审阅）。软件测试成本单列，不挪作正式 PDE 费用；正式计算时间账仍由数值 owner 统一登记。预算建议函数使用传入的真实剩余时间、近期较慢完整样本耗时 ×1.3 和收口余量，不重置时钟、不自动跑算例、不再套用旧“超过 10 min 就结束研究”。

## 2. 固定坐标与可重复设计

`surrogate_design_v1.json` 是**只有坐标、没有功率标签**的设计文件。

| 摘要种类 | SHA-256 |
|---|---|
| 文件字节 | `a86aa2eca9435065a4c95fd352c2f21a5a4281c68462865c1be777b1371dc22b` |
| canonical JSON 设计身份 | `c5abea8da0f257138c61793b4bb87ca2e33f1996e295321861b712e86fff54b2` |
| 固定六个 blind 几何列表 | `fc046a8983cf4cc380b13d517e5c07223effcc6b6ed48ea225ff1b78b7621f01` |

种子 `440700`，开发与盲集候选池用种子 +1/+2。先产生各维分层的 512 点 Latin-hypercube 候选池，再逐次选择离已选点尽量远的点（greedy maximin）。**被选子集/每个训练前缀不声称仍是完整 LHS**。设计按完整六个厚度检查唯一性，不按单个厚度去重，不把六参数改成固定总高。

默认 8/4/6 是小规模可行性试验，不是样本量充分的证明。可选旧 80/10/10 设计也可生成；20、40、80 只是同一训练列表的嵌套前缀，没有义务执行。正式追加用 `extend_training()` 保持当前 holdout 坐标，不能通过重新生成一个更大设计悄悄替换 blind。

## 3. 模型与验收口径

| 部分 | 实现 | 限制 |
|---|---|---|
| 输入 | 每维固定 `(t−0.5)/0.5` | 不用 dev/blind 估计范围 |
| 主模型 | 三个独立 GP；Matérn 5/2；六个独立长度尺度 ARD | 用有限样本学习光滑响应，不保证全六维域误差 |
| 输出标准化 | 当前训练集的均值/总体标准差；近常量输出 scale=1 | 每个 CV fold 重新 fit，绝不带入该 fold 的留出标签 |
| 数值正则 | GP 标准化单位 `alpha=1e-8`；长度尺度边界 `[0.02,20]`，零额外优化重启 | 这是数值正则，不是声称 FE 噪声为某个已知 σ |
| 基线 | 训练均值；截距+六斜率的 ridge 线性模型，斜率惩罚 `1e-8` | 记录实际 rank/condition；小 fold 也不删点；没有无正则 28 系数二次拟合 |
| 内部诊断 | ≤12 点 LOOCV，否则固定五折；每 fold 单独拟合全部预处理/超参数 | 报告 held/train 索引、fold scaler、警告；仅训练标签参加拟合 |
| 输出 | `R_total`、`T_total`、`R00_total` | 不训练全场，不改变 FE 输出，不剪裁预测来掩盖错误 |
| 误差 | 原始无量纲功率比 MAE、max error；目标 `1e-3` | 必须说明是 dev 还是 final blind；六个 blind 点通过不等于连续域保证 |
| 不确定度 | GP posterior std | **不是实际误差上界** |
| 响应是否足够变化 | train/evaluation range、已检查点加密差、重复噪声（未知则 NOT_MEASURED/null）、均值/线性改善 | 加密差只限检查点/配置，不是全域 noise bound；若均值已达标、变化接近加密/实测重复差异或几何 affine rank<7，标证据不足 |

每个输出记录最差点的完整厚度、sample_id、绝对误差、预测 std；单凭这些不杜撰具体 FE/物理误差原因。学习曲线要求相同开发集、相同数据资格及真正嵌套且未改动的训练标签；换策略属于另行标注的模型比较。

API 语义参考 [scikit-learn GP 文档](https://scikit-learn.org/stable/modules/gaussian_process.html) 与 [Matérn 核文档](https://scikit-learn.org/stable/modules/generated/sklearn.gaussian_process.kernels.Matern.html)。本地实际包版本如上，调用并经合成测试验证；未因网页最新版替换本地环境。

## 4. 合格数据入口合同

`src/surrogate/data.py` 只消费 owner 从正式记录导出的轻量 **compact**。它从数值字段重新检查门，不仅相信 `status`；这仍不等于重新计算有限元或代替独立审查。真实 compact 的字段必须绑定真实输入、源码、结果、监督回执及其 SHA，禁止用 synthetic fixture 的占位 SHA/假资源值导出正式数据。

| 对象 | 必需字段/门 |
|---|---|
| 共同资格 | `schema=sixlayer-qualification-v1`、`data_kind=measured_fe`、同批 `generator_sha256/materials_sha256/source_sha256`、`checks` |
| 四类对照 | `propagation_mesh/layer_z_mesh/dtn_evanescent/top_air_gap`；实际 A–D 厚度、双方 config/evidence SHA、双方 qualified run、三个原始输出；逐输出差 ≤`2e-4` |
| 对照物理 | 双方冻结 `.7 nm/p6/89°/90°/S/周期/柱横截面/六层次序/六厚度/材料 SHA` 一致；baseline generator 等于共同资格 |
| 对照数值 | 明列 x/y subdivisions、八层 subdivisions、二维倏逝扩展数、top_gap；只准该类数值键单调扩展；gap 为 `.5→1`、底参考面 `−.5` |
| 样本 | `sample_id/thickness_nm/status/data_kind`、同批三个 SHA、资格 canonical SHA、`physics`、actual DOFs、input/physical-model/run-manifest/evidence/mesh/DtN-modes SHA |
| 求解/输出 | full true residual ≤`1e-6`；R/T/R00_s/p/total/A_balance/A_volume 全有限；R00 求和一致；不掩盖负功率；体积能量闭合 ≤`1e-5` |
| 资源 | 完整 wall/stage times、simultaneous process-tree full-pipeline peak ≤`10e9 B`、task swap 0、sampling/swap 完整、actual available gate、样本数/最低 available ≥1 GiB、supervision SHA、exit0/cleanup |

`data.py` 的 `FIXED_PHYSICS`、`_comparison_contract()`、`validate_record()` 定义精确字段；`src/test/test_task44_surrogate.py::synthetic_fixture()` 提供**仅供软件测试**的完整结构例子。材料来源是否正确仍需材料资格；字段中的 materials SHA 不自动证明物性正确。

`generator_sha256` 包含数值生成版本。若改变网格/模式/精度策略，旧数据不得换个标签混入同一批；必须新资格或明确同精度版本处理。异常记录保留于 owner 总账，本模块拒绝缺失中间点、重复点、跨 split 点及不合格点，不静默过滤或插值补齐。

## 5. 盲测保护与命令

训练入口没有 blind 参数。盲集的**标签**另存 protected 路径，不在设计文件、训练目录、开发报告中。先根据训练 CV、开发误差、响应变化和成本明确冻结理由，再把模型（含每输出超参数/scaler）、训练身份、采样策略/设计、资格及当前源码摘要绑定为 freeze。打开盲标签前用 package metadata 核对、预测时再次硬核 NumPy/SciPy/scikit-learn 版本与训练模型一致；统计 runtime 独立于 FE runtime，不把两者混称同一 ABI 资格。

只有 `blind` 命令核对 freeze 全部身份后才打开标签；打开前在**标签真实路径派生**的 ledger 中以独占创建写入永久 `evaluation_started`。成功另写 completed，失败保留暴露记录；同一路径换 report/freeze 名不会重新获得盲资格。路径保护不是恶意用户沙箱：**owner 必须固定正式 blind 路径和上表几何 SHA，禁止复制标签换名重获“独立”**。盲后调参需披露原盲组失效；工程失败不抹去已经发生的标签暴露。

```bash
# 只有设计，无 PDE/标签。已有 surrogate_design_v1.json 不覆盖。
python scripts/run_surrogate.py design --output /new/path/design.json

# 真实 owner compact 合格后，单线程训练/诊断；此时仍不读 blind。
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python scripts/run_surrogate.py train --design design.json \
  --qualification qualification.json --train-records train.json \
  --dev-records dev.json --output experiment.json

# 依据实际 train-CV/dev 明确是否值得进入一次小规模盲评。
python scripts/run_surrogate.py freeze --design design.json \
  --qualification qualification.json --experiment experiment.json \
  --reason '填写实际训练CV、开发误差、响应变化与成本支持的冻结理由' \
  --output freeze.json

# 最后才能执行；当前没有正式 FE 标签，不执行此命令。
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python scripts/run_surrogate.py blind --design design.json \
  --qualification qualification.json --experiment experiment.json \
  --freeze freeze.json --blind-records protected/blind.json --output blind_report.json
```

所有输出用 exclusive-create，防止覆盖旧冻结或负结果。模型为纯 JSON 数据，不用 pickle。正式 PDE 仍只走仓库 `scripts/run_case.py`，GP 入口不替代它。

## 6. 软件测试与下一步

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m unittest src.test.test_task44_surrogate -v
```

覆盖默认/旧可选设计、A–D/嵌套/跨组唯一、加四点保持 holdout、错材料/p/波长/非目标数值变化、非有限残差、坏能量、资源/版本失败、bool/文本伪数值、synthetic 禁止冒 FE、每 fold scaler、JSON 重载、原单位误差、均值已够/重复噪声大于响应时证据不足、统计包版本变更拒绝、freeze 错配不打开盲标签、一次消费及失败暴露保留。

下一项不是“加更多算法”：等待 owner 的材料/数值资格与真实最小样本，适配其正式 compact 后先评价 8+4 的诊断。若响应几乎不变、数值差异过大、成本不合适或数据不足，应据实报告相应可行性边界；不强行制造代理通过，更不外推标准尺寸。
