# 测试与证据资格

## Review V6：组件阶段（2026-10-02）

| 检查 | 结果 | 边界 |
|---|---|---|
| 真实 5/2 nm Si、全部 600/3904 模式、有界 18-cell FE | 2 passed / 872.14 s | 每个配置一个 p4 factor，全部六个实际 full-case tensor 组独立 FFCx 见证；完整作用、H6、Aq、恢复与 C；非完整 PDE |
| 最终 RSS-only 监督 | 24 passed / 32.95 s | PSS provider 零调用、慢诊断不阻塞 RSS、RSS 触线清场、正常/失败退出及旧合同 |
| 真实 p3 共用快速路径 | 1 passed / 13.15 s | 实际 5 nm 系数、600 模式、原 FFCx tensor 与完整原作用；不启动 q3 长场 |
| MPI2/MPI4 reference-metric 对角 | 各 rank 1 passed，6.51–6.52 / 5.04–5.05 s | 小 p3 Floquet FE，同原积分对角与已装配矩阵；MPI1/math1 是正式候选 |
| 作用域、manifest 与严格粗返回最终合同 | 48 passed / 5.06 s | 真小 KSP 16 步预设停止，精化耗尽拒绝、原入口与负 schema；无完整场资格 |
| metric/fused/原积分对角最终回归 | 8 passed / 32.00 s | 真实小 FE、复多主/目标合并 fallback；新增文件 Ruff 通过，修改文件无新增 F821/F401/F811 |
| 本次 MPC metadata / p3 小 FE 定向回归 | 纯用例 21 passed / 0.87 s；实际 p3 FE 1 passed / 64.25 s（import/lint-only 变更后再次 1 passed / 31.78 s）；独立监督 6 passed / 7.04 s | 实际物理 Floquet singleton 与人工 complex multi-master/shared-target mapping 分列，均与原 FFCx cell-diagonal oracle 对照；rel≤1e-11、abs≤1e-10、fallback>0。人工映射不是物理 Floquet 见证；保留 native MPC 和 p3 shared-path 回归 |
| E3 math1/math4 bounded FE 线程对照 | 4 场自然完成；每场 5/2 nm fixture 均 `COMPONENT_PASS`，AB/BA 比较均 `BOUNDED_COMPARISON_PASS` | 18-cell/fixture；每配置一个 factor、三个固定 PC 输出。PC 首调用与第 2/3 次 warm 调用分开；2 nm warm math1/math4=1.047754、0.975515，未稳定受益，冻结 math1；8 线程未运行。math4 环境设置4、`openblas_get_num_threads()`=4、OS线程数6；报告字段`parallel_runtime=1`是`openblas_get_parallel()`的`OPENBLAS_THREAD`类型枚举，不是线程数。PC墙钟和factor numeric API墙钟/进程CPU单列；MUMPS共享内存能力unknown。详见[compact](records/v6_thread_selection.json) |

源为 Review HEAD 上 WIP，精确文件 hash、patch、日志和组件指标见 [V6 component compact](records/v6_component_and_h6_only.json)。失败留证包括 fixture metadata None、坐标形状错误；合跑监督与 FE 命令为 23 passed/2 failed，其中 watchdog 在 MPI 初始化后已有子进程时正确拒绝专用父进程合同，p3 工厂被多传一个位置参数。分开纯监督与 FE 后通过，未弱化生产 guard。新增 donor 文件只做 import/lint 修整，不改变数值公式；正式 source SHA 在后续 clean-run manifest 记录。2 nm H6-only 已以 H6_ONLY_COMPLETED 自然结束并仅按该 scope 验收；它不构成完整 PDE 资格。完整 5 nm 与 16 步 pilot 仍 NOT_RUN；未跑全仓 pytest 或 CI。纯测试与 FE 曾有一条合并命令返回 22 passed/31.71 s，该命令包含 FE 用例，因此不计作纯测试结果。


当前窄 WIP 的 Ruff baseline 对照为 HEAD 40 项、当前 40 项、新增 0；受影响文件 py_compile 与 git diff --check 通过。该结果不表示全仓 Ruff 通过。

## Review V6：P2终态与R48/Z文档收口（2026-10-04）

本次仅归档既有P2主审接受结果，并整理R48纯metadata planner、完整external-mode inventory和条件容量账；求解器源码、输入、运行参数均未改动。没有重跑FE、矩阵、factor、PDE、性能或既有H6测试，也没有重扫P2的3.38 GB resources日志。P2资源结果来自已完成的一次流式审计receipt；R48依赖已由主审复核的planner/inventory hashes。新增JSON/Markdown的本地结构、身份、哈希、链接、围栏与表格检查属于文档静态校验，不是数值测试。实际提交 `b06865d89c0b6a1a4c8480ed62622fbeddb91f6a` 的7个GitHub blob页面均为HTTP 200；服务生成的richText中189张表与该提交本地Markdown的列数及表体宽度一致，详见[渲染结构回执](records/v6_github_render_closeout.json)。本次仅补充response与本文件后，会在新提交推送后复核这两页；另外5页沿用b068提交的原字节哈希。人工视觉检查和CI均为 `NOT_RUN`。

## Review V5：5 nm rounded-tensor representative bounded component

| 检查 | 实际结果 | 范围 / 限制 |
|---|---|---|
| 105-cell真实5 nm Si FE/MPC raw-vs-candidate | `1 passed / 2986.99 s`；18 raw几何类/阶→9 tensor组/阶；p4/p6逐类代表tensor最大相对差`6.295e-16/4.348e-16`；A6动作差`3.139e-13`；Aq体积/DtN`4.104e-15/1.081e-14`；原A4返回rho raw/candidate`2.382e-11/1.658e-11` | 4个真实零阶mode；显式port RHS仅对增广矩阵单独核验，未测其原A4恢复；非完整网格/非600通道/非资源资格；[compact](records/v5_5nm_geometry_105_component_v1.json) |
| 几何身份与结果归档回归 | `7 passed / 0.76 s`，CPU24 | raw identity不合并近尺寸单元；V5冻结轴/profile合同与旧入口保持；无FEM启动 |
| targeted Ruff / py_compile / JSON / diff check | 全部通过 | 新测试、相关合同和记录检查；不等于全库lint/pytest |

候选构建用时 raw→representative：p6 tensor `892.56→447.23 s`、p4 `43.45→21.26 s`；额外逐raw类tensor复算另计 p6=`1434.48 s`、p4=`64.51 s`，不混入构建计时。完整 3780-cell setup-only 尚未运行；其启动仍等待 clean source 审核与新鲜准入。

以下历史性能实现提交为 `f124679e75915758076d9240bd4bef2f5c772752`；对应测试使用当时worktree的原生activation和complex128/int32 ABI，真实FE/MPI测试在宿主机CPU23执行。上方V5几何组件使用独立PORD64 activation与CPU10–13允许集（一次PSR快照为CPU10）；CPU24上的后续focused回归单列报告。没有隔壁文件/进程修改，没有CI通过声明。

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
| 5 nm checker no-deadline focused | 4 passed，19 deselected，0.12 s | bounded/none 的 screen、solve、workflow 门限；不启动 PDE |
| compileall / git diff --check | 受影响模块通过 / 通过 | 未跑全库pytest，未跑CI |

这里按实际命令报告，不把重复运行相加当独立测试数。新测试文件共有6项，分两次覆盖全部；相关旧回归87项在分类修复后分组覆盖。唯一历史deselected项`test_real_e1_inputs_load_without_fe`需要未随Git提供的ignored diagnostic_audit.json，之前已实际失败于FileNotFoundError，未篡改成通过。

本次有一条回归命令使用了错误旧文件名，exit4、no tests ran；更正后才取得上表86/1结果。首次独立p6诊断以脚本方式启动时未找到tmp namespace，改用模块方式后完成；都不是formal PDE retry。新文件的5项Ruff格式提示已修复，未作无关代码整理。

监督分类修复只把`cooperative_stop_identity_and_signal`异常记为MONITORING_FAILED，保留原异常与清场；没有放宽RSS/swap或时间上限。其余监督改动为native PSS约5秒采样，RSS/swap照常读取。FE优化使用严格浮点、禁止FMA contraction，不使用fast-math。逐行诊断与拒绝方案见[kernel evidence](records/kernel_performance.json)，日志hash见[test evidence](records/performance_tests.json)。

checker no-deadline 修复提交为 `d64398cb1fecd90867071688dca94e501235cf7a`；修复后对同一 5 nm run 只读执行独立 recheck，结果 `independent_output_gates_passed=true`、`gate_failures=[]`。原 checker/summary/manifest 与资源连续性缺口未被覆盖或提升。

## 2 nm h1.5 PORD64 收口检查

| 检查 | 实际结果 | 范围 / 限制 |
|---|---|---|
| 最终 `activate_task39extra_pord64.sh` imports/query/maps | PASS：petsc4py、DOLFINx、MPC 导入；`PetscInt=int64`、`complex128`、PORD query=64；唯一 PETSc map 为 `/tmp/task39extra-pord64/petsc/lib/libpetsc.so.3.19.6`；新prefix无 `.pc`，`PKG_CONFIG_PATH` 为 unset | 轻量环境检查；未启动FEM |
| PORD64 MUMPS fixture | PASS：`mat_mumps_icntl_7=4`，`INFOG(7)=4`、`INFOG(1)=0`，symbolic/numeric/solve=1/1/1，relative true residual `2.922259846318588e-11` | 8-cell、1944行、701496 NNZ组件资格；不代表h1.5整网numeric |
| PORD32 boundary fixture | PASS：`NEDGES8=2147483648` 返回 `-51/-2147`，NCMPA哨兵不变 | 受控边界证据；不是正式图NEDGES实测 |
| recipe/document JSON validation | PASS：记录JSON可解析、build recipe与新launcher存在、`bash -n` activation通过 | 临时 `/tmp/task39extra-pord64` 构建目录不入Git |
| 新 PORD64 launcher Ruff | PASS：`ruff check scripts/task39extra_2nm_h1p5_pord64_launch.py` | 仅 launcher 静态检查 |
| 既有文档合同轻检查 | **15 passed**：`.venv/bin/python -m pytest -q src/test/test_26_documentation_contract.py` | 不含 FE/MPI/全库回归 |

## 2026-09-18 实测内存重启验证

44 passed in 240.32s (0:04:00)。包含真实MUMPS小矩阵越过大预测值、实测内存分配超限清场、原p4和native/subreaper回归。ABI为PORD64、complex128/int64，原PETSc库hash不变。启动器完整Ruff、受影响模块严重错误规则及compileall、diff whitespace检查通过；未运行全库或CI。详细命令和日志hash见 [compact](records/2nm_h1p5_measured_retry_v1.json)。

文档检查为20 passed、1 failed。唯一失败来自基线已引用但HEAD及磁盘均缺失的 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2_checker.json`；不是本轮新增路径，不伪造缺失历史证据。本轮表格Markdown和任务文档合同通过。
