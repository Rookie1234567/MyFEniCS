# V30：结束轻量入口和合成审核的准备链

本轮只修复能明确定位的软件接线问题，再验收已经准备的工作。审核器像一张证据核对表：正确包必须能写出并通过，缺计数、坏因子资格或错向量必须因对应原因被拒绝。它不求解Maxwell方程；小矩阵和成本分析也不产生新的场。结果为`LIGHT_ENTRY_AND_SYNTHETIC_CHECKER_QUALIFIED`，原微型物理解、原尺寸资格和神经20%收益均未改变。

| 范围／数据身份 | 实际执行与来源 |
|---|---|
| 合同 | [Review V27](../review_report_v27.md) @ `0a0f03390247ef37b12a04cadc61d091320203c0`；[独立审阅证据](records/review_v27_independent_checks.json)55链接、1,408,289 B逐项hash核对 |
| worktree | canonical NN-Lab／`task42_neural_coarse_inverse`；origin tracking同名，common为既有task-repository.git |
| source／measured | `1a18f520dae3ecd702a1369b0d9241ec3e81802a`为实现、launcher和worker；22编译文件hash与提交一致，文档HEAD分开 |
| 原物理边界／not_run | 0.7nm、384hex/p3/q15、18144 trace＋40端口、原MPC／材料／背景未改；未读取任何真实数值载荷、参考或权重 |
| 总时钟 | UTC／monotonic934544.490998906／boot_id `fd8f4b00-1e17-46af-a6fa-da3a32dbeba3`冻结；06:39:09.630103Z开始，轻量2700 s、总3600 s；未刷新 |
| 本轮冻结 | 唯一监督任务COMPLETED／exit0，06:46:31.384243Z关闭队列；之后只做静态证据、文档与Git交付 |

## A：修复内容与正负控制

| 改动 | 为什么需要／代价 | 最终资格证据 |
|---|---|---|
| 重复keyword | 原模块无法编译；拆为`snapshot_label`标签和`snapshot`路径/hash，无数学变化 | 22文件真实编译及完整模块导入／执行通过 |
| 输出目录 | collector创建`records`父路径；fixture故意给全新目录，公共atomic writer不改 | 新嵌套目录端到端写出3份JSON，完整正例通过 |
| 32变异负例 | 每例先运行未变异正控制，再要求具体ValueError/KeyError和完整错误消息 | 32项全部通过，[逐Gate清单](records/checker_acceptance_v30.json)；不接受任意OSError |
| 专门IO反例 | 第二次调用注入明确路径的FileNotFoundError，确认它会逃出数据变异验收 | `test_io_error_cannot_satisfy_a_data_mutation_gate`通过，正控制先真实执行 |
| V30 namespace | 复用原launcher、入口、DiagnosticWindow；只加显式`--v30`／`--batch v30` | 原V29默认名称保留；V30 scratch与输出独立，V26–V29窗口／ledger和V29原结果hash不变 |

没有改因子数、36次作用、35次单列端口、浮点容差、rank或CPU策略。合成测试的文件、metadata和小数组全部来自临时fixture，7个reader仅存在于证书库存，不是读取生产因子。

| 合成数据情形 | measured审核行为 |
|---|---|
| positive／weak | 正信号／STATE_DEPENDENT_INCONCLUSIVE按原预登记判定 |
| beta=0 | 合法零系数仍可完整审核，不强制非零 |
| zero／duplicate／nearzero | REDUNDANT_OR_UNRESOLVED保留，不硬凑rank10 |
| solved baseline | g10=null，不用0掩盖零分母 |
| partial actor记录 | PARTIAL_UNRESOLVED，不授予CHECKED |
| 零消费／因子资格失败／回流向量改100／残差范数翻倍 | 明确拒绝；32变异覆盖来源、计数、manifest/ledger、数组、状态、支持、尺度、抵消和重组 |

## B：完整轻量入口及固定代数

唯一受监督命令如下，运行前source已提交且clean。没有临时mkdir补丁、AST函数抽取或跳过失败组件。

```bash
set -e
export TASK042_CACHE_NAMESPACE=v30 PYTHONDONTWRITEBYTECODE=1
source scripts/activate_task042.sh pure
python -m benchmarks.task042_diagnostic_auxiliary --v30 \
  python -m benchmarks.task042_v29_light_checks --batch v30
```

| 检查／measured | 数量／结果 | 原始入口 |
|---|---:|---|
| 准入前`compile(...,'exec')` | 22/22，模块未执行／NumPy未导入 | [编译](records/compilation_v30.json)、[stdout](records/compile_stdout_v30.txt) |
| 最小回归 | 7 passed，pytest1.26 s，含进程启动2.486083292 s | [stdout](records/minimal_stdout_v30.txt)、[JUnit](records/minimal_junit_v30.xml) |
| 完整scope | 原155＋新7＝162 passed，pytest10.86 s，含启动12.198941457 s | [stdout](records/full_scope_stdout_v30.txt)、[JUnit](records/full_scope_junit_v30.xml) |
| 去重／执行次数 | 162个不同测试，最小7项在全scope重复，实际169次执行 | 不将169称为不同测试数，无CI／full-repo通过声明 |
| 原样入口 | PASSED／exit0；inner14.790799552 s | [entry](records/entry_result_v30.json)、[worker raw](records/worker_stdout_v30.txt.gz) |
| 两份冻结CPU快照 | 各48逻辑CPU；候选`[11,22,26]`／`[]` | [重算索引](records/cpu_exclusions_v30.json)，逐核JSON／CSV含PID/TID/start及SMT排除 |

CPU重算使用冻结tick/start和原策略，不重新采样邻任务。当前准入选CPU21，仅对本次有效；历史低忙率核仍可因宽affinity／SMT规则排除，不意味着48核持续满载，也不允许忽略桌面或Codex线程。

全空间补项给外域输入一个直接入口，代价为J两解、六外块各一解及两次原A传播。固定三fixture仅检验这个传统块代数，未接入真实PC。

```math
B_{\rm ret}=B_J-(I-B_JA)L_OAB_J,\qquad
B_{\rm full}=B_J+(I-B_JA)L_O(I-AB_J),
```

```math
B_{\rm full}-B_{\rm ret}=(I-B_JA)L_O.
```

| 固定fixture／complex128 | 操作尺度归一最大误差／限值 | 结果／直观边界 |
|---|---:|---|
| NON_HERMITIAN_8，seed422901 | 8.129925522e-17／1e-12 | 差式、顺序、复线性、支持和三角分解通过 |
| NON_CONTRACTION_2 | 1.905282407e-16／1e-12 | A=[[1,2],[3,1]]、r=[0,1]；旧返回0，新返回[-2,1]，真实剩余[0,6]；残差放大6倍 |
| SINGULAR_LOCAL_2 | 不求逆／不添加shift | J零主块按预期拒绝，保留失败身份 |

[三种原始记录](records/full_space_algebra_v30.json)。满秩局部块的三角乘积说明代数可逆，不要求A正定或Hermitian；它不保证迭代收縮，不能外推真实Maxwell的效果。V29三fixture仍NOT_RUN，Review V27小矩阵是审阅测量，本轮是新source的原样执行，三者不混写。

## C：成本和20%神经门槛

缓存分析模块现在能够整体导入并运行，完整账绑定已有JSON hash，不重新读大数组或因子。[成本账](records/complete_cost_ledger_v30.json)同时保留measured／derived／unknown和嵌套关系。

| 费用／载荷 | 值、单位与口径 | 仍缺什么 |
|---|---|---|
| V24／V25／V26 actor | 1977.711696／25.665227／33.262622 s，历史研发 | 不是合格N=1求解时间 |
| V26两薄LS | 0.008964091074 s，嵌在33.262622 s actor内；约0.026949% | 免费替代也不能在同诊断口径达到20%，不是全解比例 |
| V26准备／reload／原作用／port | 原JSON明细保留，不与actor再相加 | 部署冷准备、驻留复用和exclusive费用unknown |
| 七套A＋LU／纯LU下界 | 1,591,420,032／795,710,016 B，derived载荷 | 同时RSS、页、副本、pivot、hash buffer和workspace另计 |
| 完整packet／旧基／暖链、审核／IO | unknown | 不抹掉训练／LSQR／循环路线及失败成本 |
| 最佳合格非神经完整N=1 | 时间、同时峰unknown | 无完整合格配对，不能计算NN20%通过率 |

```math
T_{\rm removed}-T_{\rm added}\ge0.20T_{\rm base},\qquad
M_{\rm new,simultaneous}\le0.80M_{\rm base,simultaneous}.
```

相同正确性下，时间或同时峰达到20%改善，另一项仍须合规。Tadded包括数据、训练、加载、推理、额外精确修正、审核和IO；N=1不假定摊销。只学习同八／九方向的系数不能超该空间的精确最小残差。传统块代数或入口工程修复的收益不归给网络。

## 资源、停止与下一步

| shared-workstation资源／预算 | measured值／限额与口径 |
|---|---|
| 唯一准入 | CPU21，候选21／37；原5%／SMT规则保持，内存／磁盘／PSI通过；startup probe1.276687813 s，完整launcher启动exclusive费用unknown计elapsed |
| 监督wall | 18.785166597 s≤120 s；总窗口内提前结束，不等待或再准入 |
| 累计监督 | 历史21.163846770＋本轮18.785166597＝39.949013367 s≤600 s；审阅9.043027862 s单列 |
| 树RSS／swap | 195,633,152 B／0；dedicated subreaper parent＋所有后代，27样本，0.5 s请求；warn1GiB／hard2GiB，无kernel cgroup限制声明 |
| 余量 | effective MemAvailable约1.497 TB；system reserve216,310,038,528 B＋neighbor growth137,438,953,472 B；原shared envelope保留 |
| 线程／ABI | pure独立`.venv`，NumPy1.26.4／SciPy1.11.4，三个BLAS getter1；MPI1/math1，DataLoader0；不装载FE/Torch，不升级ABI |
| 原始证据／存储 | admission与resources无损gzip，stdout/stderr/JUnit保存；[存储](records/storage_v30.json)将TMP和代码计入新增，实测时点明确 |
| 本轮真实库存 | 全部0；虚构fixture库存不计真实S/SH、factor或PC |
| 历史账 | formal研发下界77,161.557139 s、旧auxiliary／完整N=1 unknown保留；V26–V29 closed/hash不变 |
| 未运行 | 真实回流eta10/g10、Bfull真实部署、PDE／场／功率／训练均NOT_RUN；不是负结果；旧V24 0/5、V23 0/6不改 |

watchdog没有记录资源／健康停止，自身后代已清理；未证明绝对零干扰。没有subagents、重置卡、GPU、其他分支或邻任务配置修改。GitHub精确页面Cache miss，视觉NOT_VERIFIED；本地结构检查与运行前12项文档合同测试分别记录，未重复启动监督测试。

下一次真实诊断若获新review授权，仍缺七bundle真实source/row/hash与原作用见证、两冷态与V26九方向缓存资格、真实完整消费和端口/恢复审核；启动还要fresh资源Gate、独立deadline／自有锁和监督，以及含加载／资格／计算／审核的完整费用。当前合成通过只关闭软件准备链，不授予读取真实载荷或延长旧窗口的许可。

唯一建议是让下一review基于已关闭的轻量Gate，决定是否授权一次固定两冷态真实回流方向诊断；本批不实施。不merge、不扩大模型，封存后等待审阅。
