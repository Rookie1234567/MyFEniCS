# Compact q 投影：显式 opt-in 的有界数组候选

## 结论与范围

候选已实现；53 项新合成测试和相关回归 94 passed / 4 skipped / 1 deselected 通过。独立只读审查为 `PASS_WITH_QUALIFICATIONS`。本检查点只归档 own-cloud 分支 `task40extra_dot_parallel_cloud` 的三个源码/测试文件及紧凑证据。实际测试基线为 `7de238a4b6f74f2b90ec42156f64a71f54ce79e5`，tree 为 `89bdf899b5dedb7fbccd0eafcd99e6aeb508a5c2`；测试时使用 hash-bound working-tree candidate，收据中的未提交状态保留为历史身份。发布不重新授予数值资格。三个源码文件随后原字节提交为 `32847dfa3371b9b0e43796a7675a4379c9ee6fb8`；远端检查点另保留其父分支已有的恢复收据。

本改动解决“把局部贡献变到 q 坐标时，一次复制整片支撑并生成完整投影矩形”的额外数组成本。新路径按小块读取 q 映射、计算同一复数投影，直接按精确非零数量建立 CSR；不经 COO 和 SciPy 稀疏矩阵相加。它补充现有本地 H6/PSS/A6/A4 优化，不重做这些路径。

这是内存优先研究候选，不保证提速。保持全部模式、原始 q 库存、共轭转置对偶与非 Hermitian D/XiB 语义。只省去精确为零的存储；没有幅值阈值、低秩压缩、截断或物理工作量缩减。数学相同不等于一般逐比特相同。

## 修改文件与启用

| 文件 | 作用 |
|---|---|
| `src/solvers/bounded_compact_q_projection.py` | 新的 owned-array 预算、分块投影、精确 CSR 合并、无向量掩码验证 |
| `src/solvers/y_orbit_two_cell_block_audit.py` | 小范围显式参数接线；默认 `None` 保留原路径 |
| `src/test/test_bounded_compact_q_projection.py` | 53 项纯 NumPy/SciPy 合成资格与资源/生命周期负测例 |

显式构造已有 compact-layout provider 时传 `compact_projection_max_owned_bytes=<正整数>`，可另传 `compact_projection_tile_width=32`。预算未给时不采用新算法；给预算但 action 不是 compact 布局时明确拒绝。没有改 ordinary runner 或默认配置。

## 精确内存口径

令当前结果 CSR 的实际 ndarray 载荷为 R；投影块 a×b；native contribution 为 m×n；cached correction 内部维数为 k。以下均是显式 NumPy 数组的推导上界，不是 RSS 测量。

| 阶段 | 同时存活 owned ndarray 的准入上界 |
|---|---|
| cached correction 投影 | `R + 16*(m*a+n*b+a*k+k*b+a*b)` |
| 普通 dense 投影 | `R + 16*(m*a+n*b+a*n+a*b)` |
| 对角 original-H 投影 | `R + 16*(m*a+n*b+a*b)`，右映射小块原位缩放 |
| CSR 合并 | `R + 16*a*b + 2*N`；N 是计数后精确新 CSR 载荷，第二份 N 为保守构造器复制余量 |
| 结果验证 | 标量扫描；无完整 finite mask / diff / array_equal 数组 |

每次投影或合并前先准入。结果增长后可继续细分尚未处理的小块；合并计划不合预算时，先释放整个旧 projected 小块，再重新计算更小块。即使 1×1 小块也无法容纳时，在下一次分配前抛出带所需字节数的 `MemoryError`，不会静默省略最终矩阵或裁掉数据。CSR int32→int64 指针运算在 int64 中计算，避免先溢出再写入宽输出。

预算不包括 q-map 构造、贡献 producer 的临时量和借用 backing、Python 对象，以及 NumPy/SciPy/BLAS 内部 packing/workspace；这些仍由现有 fresh process-tree gate 覆盖。内部工作区没有数学硬上界。合并时 fresh-RSS allowance 保守地重复计入已驻留 projected 小块，这会更保守，不会低估。最终 CSR 本身及旧/新 CSR 共存成本无法由分块消除。

## 64-port 合成示例

随机种子 20261003；native 64×64、内部维数 9、q 输出 47×53、实际支撑 39×45、小块上限 8。[原始合成脚本](records/bounded_projection_v1/run_synthetic_component.py)、[实测收据](records/bounded_projection_v1/synthetic_component_v3.json)、[独立审查](records/bounded_projection_v1/independent_review_final.json)与[回归日志](records/bounded_projection_v1/targeted_regression_v3.log)保留原字节。

| 指标 | 数值 | 身份 |
|---|---:|---|
| named-array 预算 | 160000 B | 明确参数 |
| 新投影 scratch 最大上界 | 19712 B | derived |
| 旧表达式 dense scratch 上界 | 166128 B | derived；同支撑/同公式 |
| 新路径总 owned-array 声明峰上界 | 105956 B | derived，含 CSR 共存与构造余量 |
| 返回 CSR ndarray 载荷 / nnz | 35292 B / 1755 | measured |
| 对 dense oracle 相对差 | 0 | measured；仅该小合成样本 |
| 分块组件 / dense oracle | 0.055886078 s / 0.000075258 s | measured；oracle 不构造 CSR、无逐次 gate，不能作公平提速比较 |
| process-tree RSS / 内部 workspace 上界 | 未测 / 未知 | not_run / unknown |

因此只可宣称受检查的显式数组分配上界收缩，不能宣称整进程内存节省比例或整体加速。

## 检查、修正与未资格项

- 新测试：53 passed，最终进口闭包检查未加载 dolfinx/petsc4py/basix/ffcx/mpi4py
- 相关四文件回归：94 passed、4 skipped、1 deselected，1.05 s；跳过/排除项依赖明确未读取的真实保存 fixture
- compileall / git diff --check：通过；Ruff 不在恢复环境中，未安装、未运行成功
- 环境：恢复云端 Python 3.12.13、NumPy 2.5.3、SciPy 1.18.1；MPI 不启动，BLAS/OpenMP/NumExpr 线程均为 1
- 独立审查补充：100 个预算约束随机复数案例中 83 个与 dense oracle 一致、17 个在内存预算停止；这些停止不是数值失败
- 审查发现并关闭：provider 验证掩码未入预算、gate 引用环延长 action 生命周期、结果增长后的过大 tile 误拒绝、CSR 指针窄整数运算溢出。GC-disabled 生命周期与拒绝 tile backing 释放均有回归
- 首次 43 passed / 1 failed 来自资源测试参数 3500 B 实际容纳了整块、与该测试预期不符；调整到明确触发分块且可完成的 2500 B 后通过。初始候选与中间 receipt 没有覆盖为最终身份
- 未做 FE/JIT/PDE、正式 scientific raw 读取、全仓库 pytest、生产性能/精度资格。原尺寸 0.7 nm、2 TB/48h 目标仍未资格。新路径若用于真实运行，须再做同源实际原算子/残差与资源资格

## 复现命令

在授权 repo 根目录。合成脚本会在自身目录生成 JSON，因此先把上述原始脚本复制到新建的外部 `reproduction_dir`，再运行；新输出是新复现实验，不能覆盖或继承已归档收据的时间与身份：

```bash
UCX_TLS=self OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 ../complex_env_recovery/bin/python -m pytest -q src/test/test_bounded_compact_q_projection.py src/test/test_original_port_blocks.py src/test/test_y_orbit_sparse_reference.py src/test/test_y_orbit_two_cell_inverse_contract.py -k 'not actual_original_H'
UCX_TLS=self OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH="$PWD" ../complex_env_recovery/bin/python "$reproduction_dir/run_synthetic_component.py"
```

## 冻结 SHA256

| 文件 | SHA256 |
|---|---|
| bounded_compact_q_projection.py | `ac7f73b51ce67e7a0655ab71af1136c56d70f86ca1c4e42a1634782b0672f925` |
| y_orbit_two_cell_block_audit.py | `8dcfbf8278ce2de5a969aef1db97c8d42462e486e8813e60bb9599cc6a18f5bd` |
| test_bounded_compact_q_projection.py | `10118471060f28f3b5f20f0eb6ba22a022e308e31f601a5dcc0146e46c1197eb` |

原候选 patch 与 reverse-check 属于测试时来源记录。归档的 [原始 artifact manifest](records/bounded_projection_v1/final_manifest.json)记录来源文件 hash，其中 patch 和原始报告正文未重复提交；当前报告只调整发布状态、链接及复现位置，数值内容不变。没有扩大正式数值运行资格。
