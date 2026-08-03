# Task036 Response V6：direct Hybrid 修复的阶段现状、证据与下一步审查请求

## 0. 文档身份

```text
document                         = Task036 Response V6 / progress checkpoint
date                             = 2026-08-03 Asia/Shanghai
branch                           = codex/20260730-task36-forward-solver-bugfix-hardening
checkpoint_base_HEAD             = d3bed04a33778baf84d6c0938bd4ad305cb36edf
reviewed_review                  = review_report_v6.md including section 11
reviewed_reply                   = reply_review_report_v6.md
ordinary_default                 = unchanged
master                           = not_modified / not_merged
iterative_solver                 = forbidden_and_not_run
current_wavelength               = 13.5 nm
current_discretization           = p5/h10/Ny4
current_task_status              = active_research_checkpoint
final_compressed_Hybrid_status   = not_yet_demonstrated
current_0p7nm_status             = not_solved
```

本文是给 ChatGPT 做下一轮技术审阅的**阶段性回执**。它记录到本次提交前为止已经证明、
已经证伪和仍未运行的内容。它不是最终任务结项，不申请合并 `master`，也不把研究 runner
提升为 production 默认路径。

用户的目标保持不变：只研究 **direct Hybrid**，首先在可以运行 Full3D 的冻结模型上证明
Hybrid 能在小掠射角和 P 偏振下完整恢复 Full3D，同时降低整作业内存和耗时；通过后才进入
p6、加密网格和最终 `0.7 nm / 2 TB` 路线。未经用户明确许可，不开发迭代法。

---

## 1. 结论先行

| 问题 | 当前状态 | 已有证据 | 不能外推的内容 |
|---|---|---|---|
| Hybrid 域分解能否处理小掠射角和 P 偏振 | **PASS** | 完整 1200 维 FE trace-chain 在五个 grazing/P 点与 Full3D 完整通道对齐 | 不能据此说低维 Hybrid 已修好 |
| 原始 physical-QEP M120/M240 是否足够 | **CONTROLLED NEGATIVE** | A007-P 仅 `51/80`、`52/80` 通道通过，M120→M240 几乎不改善 | 不再靠继续增大 M 修复 |
| M120 中间传播是否应保留 | **RETAIN** | selected M120 space 内 40/60/100 nm exact FE operator 对照约 `2e-11` | 只证明 core 内传播，不证明端口完整 |
| exact FE trace-chain 是否正确 | **PASS / research oracle** | 五点全通道、true residual、R/T/A、同源码 A007 资源对照 | 11×1200 稠密块链不是 0.7 nm 方案 |
| discrete-Bloch B1 在总维数不超过 360 时是否成功 | **CONTROLLED NEGATIVE** | v4 的 r=120 best-trial residual 仍为 `8.886e-5`，且 Petrov rank 356/360 | 只否定本批 B1，不否定所有 POD/RCWA/低秩方法 |
| reachable-source POD 路线 | **C1a scaffold PASS** | 两端共享 primal POD 公式和 pure fixture 已实现并通过 | 尚无 96-RHS live teacher、reduced solve 或 holdout |
| corrected compressed Hybrid 是否已与 Full3D 对齐 | **NOT RUN** | 当前还没有可资格化的低秩 trial/test pair | 不得报告通道、R/T/A 或最终内存通过 |
| `0.7 nm / 2 TB` | **NOT SOLVED** | 只有 13.5 nm 的正确性 oracle 和历史 p6 资源正信号 | 没有 0.7 nm mesh、rank、factor 或整作业实测 |

最关键的判断是：**Hybrid 的数学分区和 direct Schur 链已经被证明是可行的；尚未解决的是
如何把完整 1200 维端口压缩到远低于 1200 维而不丢失 joint-Cauchy 与全部衍射通道。**

---

## 2. 当前冻结模型和名词口径

本轮所有新的 B1/C1 研究均围绕同一冻结尺度：

| 字段 | 当前值 | 说明 |
|---|---:|---|
| wavelength | `13.5 nm` | 不是 0.7 nm |
| polynomial / mesh | `p5/h10/Ny4` | 当前可运行的资格化尺度 |
| mesh identity | `(6,4,14)` | 继承 one-cell / exact-chain authority |
| core-facing interfaces | `z=10 nm`、`z=110 nm` | M120 core 跨越的中间区确为 `100 nm` |
| trace planes / cells | `11 / 10` | full FE trace-chain |
| original / active trace rows per plane | `1250 / 1200` | 1200 是 Floquet 独立坐标，不是模式数 |
| exact trace-chain rows | `11×1200=13200` | 研究 oracle 的全局 trace 未知量 |
| M per direction | `120` | forward 120 + reciprocal/backward 120 |
| M120 core primal columns per side | `240` | 后文所有 `d_port` 都以此为起点 |
| physical incoming columns | bottom 48 + top 48 = `96` | C1 可达源空间的最大原始维数 |

这里的“exact Hybrid”是完整 FE trace 的 direct 域分解；“原始 Hybrid”是 M120/M240
physical-QEP 截断端口；“compressed Hybrid”是仍在研究的 `M120 + corrector` 路线。三者
不得混称。

---

## 3. 已经完成的正确性证明：Full3D 与 exact FE-trace Hybrid

### 3.1 同源码 A007-P 主点

同一 normalized source identity：

```text
ce88c5ec4da54bb05a5cc5bfc8b16f02f13ac4807d6b2280f76e0c9155688ac7
```

| 指标 | Full3D direct | exact FE-trace Hybrid direct | 判定 |
|---|---:|---:|---|
| channels | `80/80` | `80/80` | pass |
| full true residual | `4.817e-13` | `7.444e-14` | pass |
| R | `0.62583914320438716` | `0.62583914320430711` | pass |
| T | `0.006252192503172611` | `0.006252192503165086` | pass |
| A_volume | `0.36790866429305147` | `0.36790866429248181` | pass |
| closure | `+6.113e-13` | `-4.596e-14` | pass |
| max outgoing complex-amplitude delta | reference | `4.009e-13` | pass |
| max per-key power delta | reference | `8.005e-14` | pass |
| external wall | `134.523771716 s` | `125.002722556 s` | Hybrid低 `7.08%` |
| simultaneous process-tree peak | `9.398071289 GiB` | `7.704593658 GiB` | Hybrid低 `18.02%` |
| swap | `0` | `0` | pass |

内存是同一 watchdog 口径的 simultaneous process-tree RSS peak，时间是外层整作业 wall；
不是对象体积估算，也不是单进程历史峰值。

### 3.2 五个 grazing/P 点

| case | theta / phi | channels | Hybrid true residual | max amplitude delta | dR / dT / dA_volume |
|---|---:|---:|---:|---:|---:|
| A002-P | `89.5° / 15°` | `92/92` | `3.974e-13` | `3.780e-12` | `5.498e-12 / 3.773e-15 / 4.711e-13` |
| A003-P | `89.5° / 30°` | `80/80` | `3.625e-13` | `3.381e-12` | `5.257e-12 / 1.009e-14 / 2.224e-13` |
| A007-P | `89.5° / 90°` | `80/80` | `7.444e-14` | `4.009e-13` | `8.005e-14 / 7.525e-15 / 5.697e-13` |
| A008-P | `89.0° / 0°` | `80/80` | `5.087e-14` | `8.673e-13` | `9.594e-13 / 3.957e-14 / 1.302e-12` |
| A046-P | `80.0° / 45°` | `88/88` | `6.832e-13` | `4.599e-13` | `1.527e-14 / 3.929e-13 / 7.044e-14` |

因此“小掠射角/P 导致 Hybrid 原理失效”已经被否定。完整 FE trace 能闭合，说明原始误差
主要来自接口截断空间，而不是 Maxwell 物理、分区或 direct Schur 消元本身。

---

## 4. 原始 M120/M240 Hybrid 为什么仍判失败

A007-P 的历史同源 direct 对照如下；该表的旧资源采样口径与第3节不同，只用于说明
M 扩张的数值趋势，不做精确资源百分比混算。

| 路径 | channels | max amplitude error | true residual | wall | peak |
|---|---:|---:|---:|---:|---:|
| Full3D direct | `80/80` | reference | `4.249e-13` | `530.001 s` | `10.230 GiB` |
| original Hybrid M120 | `51/80`，29 fail | `7.655e-6` | `2.229e-12` | `338.198 s` | `5.567 GiB` |
| original Hybrid M240 | `52/80`，28 fail | `7.641e-6` | `2.452e-12` | `683.927 s` | `7.496 GiB` |

M120→M240 只多通过一个通道，主误差几乎不变，内存和时间却明显增加。另有 exact
joint-Cauchy 审计显示：selected M120 core 的传播 action 在 40/60/100 nm 只差约 `2e-11`，
但端点 traction/joint-Cauchy 仍有明显缺口。因此当前保留 M120 作为长程 core，不再把
M120/M240 当作完整全局端口，也不继续 M480/M492 扫描。

---

## 5. exact FE-trace Hybrid 的资源边界

完整 FE trace-chain 虽然正确，但它保留：

```text
13200 trace rows
31 × 1200² = 44,640,000 stored complex block entries
```

同输入 Full3D static matrix 为 `26,952,096` NNZ。trace-chain 行数较少，但 Schur blocks
变稠密；A007 的整作业峰值只下降约 18%，所以它是正确性老师算子，不是可直接放大到
0.7 nm 的生产方案。

历史 p6/h10 static campaign 曾测得：

| 历史对象 | peak | 说明 |
|---|---:|---|
| Full3D static | `14.722 GiB` | 历史同批 campaign |
| modal Hybrid M120 static | `7.544 GiB` | 约为 Full3D 的 51.2% |

这组数据证明真正低维 Hybrid 有节省内存的潜力，也接近用户所记得的“约 14 GB 对 7 GB”；
但该 M120 空间尚未通过本任务的 grazing/P 全通道合同，不能作为已修复结果。当前 p5 exact
oracle 的正式同源资源值是第3节的 `9.398 GiB` 对 `7.705 GiB`。

---

## 6. Review V6 后已执行的 B1 路线

### 6.1 目标

B1 保留 240 列 M120 core，再从同一 one-cell FE/Schur 离散产生的 discrete-Bloch
joint-Cauchy columns 中加入 `r=40/80/120` corrector。总端口维数为：

```text
d_port = 240 + r = 240 / 280 / 320 / 360
```

它不是迭代法，也不是新的 Full3D PDE 扫描；最大 basis/action 只构造一次，各 rank 读取
同一 nested prefix。

### 6.2 v1--v4 的含义

| 版本 | 作用与结果 | 是否能作数值结论 |
|---|---|---|
| v1 | 接通真实 D1/Q4a/B1 plumbing；先发现缺失 `right_multipliers`，后发现 cleanup `destroy` 问题；约 `449 s / 2.168 GiB` | 否，未进入有效容量判定 |
| v2 | 使用旧的 Euclidean `L^H R` paired whitening；得到 r0/r40/r80/r120 residual 约 `9.51e-5 / 1.726e-2 / 1.655e-2 / 9.214e-3` | 否，旧算法错误地按坐标重叠删除 trial/test 方向 |
| v3 | 改用真实 Petrov `K=L^H(SR)` 后 fail closed；`663.127 s / 2.37484 GiB` | 只证明 Petrov rank Gate 被触发，尚无 best-trial 数据 |
| v4 | 在不改变 Gate 的前提下补充 rank/best-trial 可观测性；自然完成并生成四档诊断 | **是，本批 B1 的正式受控负结果** |

### 6.3 v4 数值结果

| r | d_port | trial/test rank | Petrov rank | min singular relative | best-trial endpoint residual | solve status |
|---:|---:|---:|---:|---:|---:|---|
| 0 | 240 | `240/240` | `240` | `1.699e-4` | `9.367535806e-5` | solved |
| 40 | 280 | `280/280` | `240` | `1.271e-16` | `9.356921361e-5` | rank deficient |
| 80 | 320 | `320/320` | `276` | `1.276e-16` | `9.349354982e-5` | rank deficient |
| 120 | 360 | `360/360` | `356` | `3.370e-16` | `8.885746566e-5` | rank deficient |

r=0 的实际 endpoint/full 11-plane residual 均约 `9.512e-5`，Petrov stationarity 为
`5.068e-14`。r=40/80/120 因 Petrov operator rank 不闭合而没有求解，相关实际 residual
保持 `null`，没有用伪逆、fallback 或放宽阈值伪装通过。

最重要的是 best-trial：即使完全忽略 test/Petrov 问题，r=120 的 trial space 对真实 RHS
能达到的最佳端点 residual 也只有 `8.886e-5`，相对 r=0 只改善约 5%，距离 `1e-9` 目标
仍差近五个数量级。因此正式分类为：

```text
DISCRETE_BLOCH_LOW_RANK_NOT_DEMONSTRATED_IN_THIS_BATCH
```

不能再靠调整 Petrov 阈值、继续追加同一 v9 mode pool 或超过 d=360 来挽救本批 B1。

### 6.4 v4 资源与 artifact

| 字段 | measured value |
|---|---:|
| outer return code | `0` |
| wall | `671.659421682 s` |
| process-tree peak RSS sum / max | `2.369438 / 2.355366 GiB` |
| swap | `0` |
| stderr | empty |
| numerical status | `partial_b1_reachable_physics_measurement` |
| reachable physics Gate | `not_run` |
| reduced-solve holdout | `not_run` |

证据目录：
`benchmarks/artifacts/task036/direct_d1d/d3bed04a-20260803-b1-a004-reachable-v4/`

| artifact | SHA256 |
|---|---|
| `memory_profile_summary.json` | `2a5ed2a997a66153c8d649096bfc1b386b47fd8afb46793273d7c64114a5a471` |
| `memory_profile_timeseries.csv` | `55757c862508d568336cc7f46f85071644c1f233d8685c28685965b03d077013` |
| `stdout.txt` | `88ff559376a2117b43ee5e61a014acebe5494f013d10c05bad939b334afdab2c` |
| `stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

`2.37 GiB` 只是 B1 研究链到该停止点的实测峰值，不是未来完整 compressed Hybrid 的
预测内存。该运行没有 recovery、96 通道后处理或最终 direct candidate，因此不能拿它与
Full3D 的 `9.398 GiB` 直接宣称最终节省比例。

---

## 7. B1 失败后转入的 C1 reachable-source/POD 路线

### 7.0 与原 Review V6 批次边界的关系

原 `review_report_v6.md` 第11节和 `reply_review_report_v6.md` 明确把 POD 延期，并要求 R1
结束后先提交 `response_v6.md` 等待审阅。B1 v4 得到 controlled negative 后，用户又明确要求
任务在 Hybrid 修复前不要停止、由本监督线程代为审批和规划、由隔壁线程开发，并强调不能只
做完手上工作后报告失败。基于这个**后续用户级指令**，监督只放行了 C1a 的 pure primal
capacity scaffold，以便在不启动新 PDE、不发明 adjoint、不写 actual solver 的前提下准备
下一条可判定路线。

因此：

```text
C1a authority = post-Review user instruction + supervisory bounded approval
C1a status    = pure scaffold only
C1b live      = not_run
```

本文不声称 Review V6 原文已经批准 POD；相反，当前推送正是把这一最小越过原批次边界的实现
交给 ChatGPT 复审。ChatGPT 若不同意，应明确要求撤回或冻结 C1a；若同意，才进入第11节的
一次 C1b 96-RHS live Gate。

### 7.1 为什么转向真实可达源

B1 的 discrete-Bloch pool 尝试用一组通用 one-cell 模态补端口，但真实 RHS 的 best-trial
残差没有下降。下一条有界路线不是继续堆模式，而是问：**外部实际可以施加的 96 个 incoming
channel 在 exact trace-chain 中产生的响应，是否落在一个远低于 1200 维的物理流形上。**

exact trace-chain 已支持矩阵 RHS，可一次求解：

```text
X_teacher shape = (13200, 96)
```

而不是运行 96 次独立 Full3D PDE。若这 96 个响应在去掉 M120 core 后的谱快速衰减，就可能
形成真正面向物理输入的端部 corrector；若不衰减，也会较快得到有意义的负结论。

### 7.2 C1a 已完成的纯算法 scaffold

当前新增的 `build_primal_reachable_pod_prefixes()` 只处理 primal trial capacity。对 bottom/top
共同 source coefficient，做一次全局两端投影：

$$
G_{core}=\sum_s C_s^H G C_s,
\qquad
B=\sum_s C_s^H G T_s,
$$

$$
R_s=T_s-C_sG_{core}^{-1}B,
\qquad
G_{res}=\operatorname{Herm}\left(\sum_sR_s^HGR_s\right).
$$

然后对 `G_res` 做降序特征分解。同一个 source-space eigenvector 同时作用于 bottom/top，
因此 corrector 是“两端共享系数”，端口维数始终为：

```text
d_port = d_core + r
```

而不是错误的 `d_core + 2r`。96 个 source columns 决定 `effective_r<=96`，所以请求
`r=120` 时只能明确饱和到 96，不 padding、不复制列；理论最大总维数为 `240+96=336`。

C1a 输出已包含：

- raw source columns/rank；
- residual singular spectrum；
- `r=0/40/80/96/120` nested prefixes；
- 每档 effective r、next singular ratio、discarded energy；
- global core orthogonality；
- joint corrector metric identity；
- bottom/top shared corrector arrays。

### 7.3 traction 公式的监督纠偏

exact teacher 的端点总 equilibrium action 在解上等于 RHS，不能直接当成 core-facing
traction。正确 raw-outward cell traction 必须只取 cell contribution：

```text
bottom cell input = [X0; J.primal(X1)]
q_bottom          = first block of cell_action(input)

top cell input    = [X9; J.primal(X10)]
q_top             = J.dual(last block of cell_action(input))
```

joint columns 为 `[X0;q_bottom]` 与 `[X10;q_top]`；cell action 已采用 raw-outward 约定，
top 不再额外乘负号。C1a 的 tiny non-Hermitian 三平面 fixture 显式证明 cell-only traction 与
加入 endpoint action 后的 total equilibrium block 不相等，防止再次把 RHS 当 traction。

### 7.4 C1a 当前验证结果

| 检查 | 结果 |
|---|---|
| B1/C1a existing pure test | `1 passed` |
| transfer primal/dual congruence test | `1 passed` |
| r=0 baseline prefix | passed |
| shared bottom/top coefficient and `d_core+r` shape | passed |
| source-rank saturation | passed |
| swapped top source identity negative | passed |
| Ruff check, two touched Python files | passed |
| compileall, two touched Python files | passed |
| `git diff --check` | passed |
| live/PDE after C1a | **not_run** |

这只说明公式、shape、rank 语义和坐标合同在 pure fixture 上闭合。C1a 的 status 明确为
`trial_capacity_scaffold`，没有生成 left/test basis，也没有调用 reduced Petrov solve。

---

## 8. C1 尚未证明的关键事项

### 8.1 96-RHS teacher 尚未正式运行

目前没有实际的 `(13200,96)` exact teacher matrix、谱尾或 best-trial residual。C1a 的
`r=40/80/96` 是否有用仍然未知。

### 8.2 A004 不能作为独立 holdout

A004 actual RHS 属于同一 96-channel incoming source span；现有审计给出
`top_b_vs_incoming_relative≈1.10e-12`。如果全部 96 个 source response 都用于建基和选 rank，
再用 A004 验证只能称为 same-operator source-span plumbing/capacity，不是独立泛化证据。

真正 holdout 必须使用未参与建基和选 rank 的不同 operator，例如不同角度、方位、偏振或
几何点，并在 reduced operator 上重新求解。不同 Bloch phase 下 trace 坐标和 gauge 不能
直接相减，必须先冻结可审计的跨 operator canonicalization。

### 8.3 test/Petrov space 尚未建立

仓库目前没有权威的 96-column physical adjoint-load builder。为提高效率并避免猜测，C1a
只做 primal capacity；它没有伪造 adjoint loads。即使 primal 谱很好，后续仍需从以下方向中
选择并资格化一个 test 构造：

1. 与 96 个 physical sources 对应的真实 adjoint teacher batch；或
2. 明确定义的 minimum-residual/test action，且证明 full explicit residual 和 observable；
3. 其他由下一轮 review 批准的、与非 Hermitian/有损 Maxwell 一致的 Petrov construction。

### 8.4 最终资源尚未测量

C1 teacher/POD 离线构造峰值、最终 reduced operator rows/NNZ、cold setup、warm repeated
solve 和 whole-job wall 均未实测。不得把 Q4a/B1 的 `2.18--2.37 GiB` 当作未来 Hybrid
预测值。

---

## 9. 当前代码改动及目的

相对 checkpoint base `d3bed04a...`，本次提交文档前的代码差异为：

| 文件 | `+/-` | 目的 | 当前定位 |
|---|---:|---|---|
| `benchmarks/run_task036_transfer_optimal_port_capacity.py` | `+1220/-17` | v9 pool binding、endpoint Cauchy mapping、B1 prefixes/Petrov/harmonic/live diagnostic、C1a shared primal POD | task-local research runner；不得原样提升 production |
| `src/solvers/one_cell_discrete_bloch.py` | `+28/-4` | 将 endpoint E/traction columns 提取为可复用函数，并保持原 balance API | 小型 reusable numerical helper |
| `src/test/test_216_task036_transfer_capacity_discrete.py` | `+674/-0` | orientation、whole-block、Petrov、harmonic、cell-only traction、C1a POD pure fixtures | task-focused regression |

累计代码为 `+1922/-21`，明显超过“约 500 行前应复审”的治理提醒。这里没有把代码规模
解释为数值失败，但必须如实说明：大部分增量属于从 R1 mode-pool、B1 live plumbing 到 C1a
的研究 runner 累积，不是一次小型 production patch。当前没有新增 package、scheduler、
campaign、retry、fallback、自动 rank tuner、iterative solver 或 ordinary-default 改动。

本次提交把这些代码作为**可审阅 research checkpoint**推送；未来选择性合并前必须把
reusable solver helper、研究 runner、测试和负证据分组，不能整体照搬到 `master`。

发布复审还确认了三个可复现性边界：

- 两个新 live 入口当前是 Python-import-only，未增加 CLI flag；v4 使用 artifact 中记录的
  `python -c` 命令调用。对本地受控研究足够，但不应称为完整公共 runner 接口；
- v9 JSON/NPZ 位于 ignored artifact 目录，远程 Git 只包含绑定哈希、代码和本报告中的紧凑
  数值，不包含大文件本体；
- `v9_endpoint_cauchy_arrays()` 的 `map_gate` 记录继承上游已执行的 transfer roundtrip/dual
  qualification，并非在该 helper 内重新计算。当前冻结调用可解释，若未来抽成通用 API，
  应把这种 provenance 依赖改成显式输入或在调用层报告。

---

## 10. 测试和证据边界

### 10.1 已有 exact-oracle 资格化证据

- qualified WSL environment，PETSc `complex128/int32`；
- serial test214：`13 passed / 1 skipped`；
- MPI8 seam targeted test：各 rank 通过；
- exact A007 同源码 Full3D/Hybrid direct；
- 另外四个 grazing/P exact Hybrid 对照；
- Ruff、compileall、diff-check；
- zero swap、正式 process-tree watchdog。

### 10.2 当前未提交代码的局部验证

- transfer congruence + B1/C1a pure tests 通过；
- v4 serial live 自然完成并保留 hash-bound artifact；
- Ruff、compileall、`git diff --check` 通过。

### 10.3 未完成

- `ruff format --check`：**not pass**；runner 与 solver helper 在 `d3bed04a` 基线版本上已会
  返回需要重排，当前 test216 的新增研究夹具也会被 formatter 调整。本 checkpoint 未为此
  全文件机械重排约 7600 行 runner；Ruff lint 本身通过，后续 production 整理时必须单独
  收敛格式；
- final code checkpoint 后的 full repository pytest：`not_run`；
- GitHub Actions/CI：没有通过声明；
- C1 96-RHS live teacher：`not_run`；
- C1 reduced direct solve：`not_run`；
- independent holdout：`not_run`；
- compressed candidate 的 96/80 channel、R/T/A：`not_run`；
- p6 compressed candidate：`not_run`；
- 0.7 nm：`not_run`。

---

## 11. 建议的下一阶段 Gate

### C1b：一次 96-RHS primal teacher

只允许一个 watchdog 受控的 exact-chain matrix-RHS run：

1. bottom/top incoming source identity 明确绑定，共计 96 列；
2. exact teacher full residual `<=1e-8`；
3. 使用第7.3节的 cell-only traction，不使用 total endpoint RHS；
4. 形成两端 shared POD 的 r=`0/40/80/96/120(saturated)` 前缀；
5. 报告谱、discarded energy、core orthogonality、metric identity；
6. 报告 source-span best-trial endpoint/full-trace residual；
7. 不进行 observable、holdout 或 Petrov 成功声明。

若 r=96 的 best-trial/full source-span residual 仍远高于 `1e-9`，则 C1 primal capacity 直接
受控失败，不再开发 adjoint/test，也不扩大 source/rank。

### C1c：只有 primal capacity 通过后才建立 test space

冻结一个物理可解释的 test/Petrov construction，要求：

- trial/test/Petrov operator rank 闭合；
- full explicit residual `<=1e-9`；
- 无 pinv、regularization、retry、fallback；
- A004 只作 source-span plumbing，不作独立 holdout。

### C2：独立 reduced-solve holdout

在未参与 C1 建基/选 rank 的不同 operator 上：

1. 从 reduced operator 和 physical RHS 独立求解；
2. 不允许 teacher solution projection 冒充 solve；
3. 比较全部复通道、R/T/A_volume、closure 和 full residual；
4. 通过后才运行小型 grazing/P 确认矩阵，必要时最多五个 MPI8 并行 case；
5. 同时实测 whole-job peak 和 external wall。

工程目标仍是：

```text
whole-job peak <= 0.70 * same-input Full3D
whole-job external wall <= same-input Full3D
zero swap
```

`0.70--0.80` 只能称数学正结果/工程 review zone，不能称 Hybrid 修复完成。

---

## 12. 面向 0.7 nm / 2 TB 的后续路线

当前不能直接从 13.5 nm exact oracle 外推 0.7 nm。合格路线至少需要：

1. **13.5 nm p5 anchor**：compressed direct Hybrid 在 A004/A007 及独立 holdout 全部通过；
2. **p6 与动态 trace dimension**：去除当前 1200-row、10-cell 等冻结假设；
3. **加密网格资源标定**：实测 rows、NNZ、factor fill、resident/transient basis 和 whole-job peak；
4. **波长 continuation**：`13.5→5→2→1→0.7 nm`，每一级重新选择 M/r/h/p，不能固定 M120；
5. **2 TB Gate**：每一级 direct factorization 前做上界校准和受控停止，预测不得冒充实测；
6. **多 RHS/角度服务**：分别报告 cold basis build 与 warm repeated solve；
7. **迭代法保持下一任务**：只有用户明确授权后才研究，不用于掩盖当前 direct 接口压缩未闭合。

如果 13.5 nm 的 reachable-source/POD、RCWA/Fourier 或其他低秩端口最终都需要接近完整
1200 维，结论应是“当前离散未证明低秩 direct Hybrid”，届时再由用户决定 RCWA 独立求解、
其他层次压缩或后续迭代路线，而不是把接近 full trace 的方法包装成成功。

---

## 13. 请求 ChatGPT 审阅的具体问题

1. 是否同意将 B1 `d<=360` 结论冻结为本批 controlled negative，不再追加 v9 模态或改阈值？
2. 是否同意用户授权后的 C1 路线先做 primal reachable-source capacity，而不在缺少权威
   adjoint-load builder 时猜测 paired adjoint POD？
3. 是否同意两端使用同一 source coefficient 的 global shared POD，而不是 bottom/top 各自
   增加 r 列？
4. C1 primal 通过后，优先批准 physical-adjoint batch 还是 minimum-residual test construction？
5. 对跨角度/Floquet phase 的独立 holdout，建议采用何种 canonical trace/gauge identity？
6. 是否批准 C1b 只做一次 96-RHS exact teacher，在 r=96 不过时立即停止？
7. 当前三文件 research diff 是否可作为后续选择性整理的审阅 checkpoint，还是需要先拆出
   `endpoint_cauchy_columns` reusable helper 再继续？

---

## 14. Git、发布与合并边界

- 本文及三份代码差异只提交到
  `codex/20260730-task36-forward-solver-bugfix-hardening`；
- 不切换、不修改、不合并 `master`；
- 不创建 PR；ChatGPT 应直接在同一 Task36 分支提交下一版 review；
- `benchmarks/artifacts/task036/` 的 heavy artifacts 受 ignore 保护，不随 Git 推送；文档保留
  相对路径和 SHA256；
- 本检查点不是 clean-source final qualification，也不是 selective-merge approval；
- `outcomes/summary.md` 和项目级 `docs/development_progress.md` 的最终闭环仍待任务完成前补齐。

---

## 15. 当前最终判断

```text
exact FE-trace direct Hybrid correctness       = pass
small-grazing / P domain decomposition         = pass
original physical-QEP M120/M240 global port    = controlled negative
M120 long-range core                           = retain
B1 discrete-Bloch M120+r, d<=360              = controlled negative
C1 primal reachable-source POD scaffold        = pure-fixture pass
C1 96-RHS teacher                              = not_run
C1/C2 reduced direct solve and holdout          = not_run
compressed direct Hybrid repair                 = unresolved
0.7 nm / 2 TB                                   = unresolved
iterative solver                                = forbidden / not_run
```

现在不是“前面全部失败”，也不是“Hybrid 已经修好”。已经可靠证明的是：完整 trace 的 direct
Hybrid 与 Full3D 可以在最担心的小掠射角/P 条件下对齐；已经可靠否定的是：原始 M120/M240
和本批 discrete-Bloch v9 corrector 在既定 rank 内不足。当前唯一高效率问题是：96 个真实可达
source 的 exact 响应能否被 `M120 + <=96` 个共享 corrector 压缩。C1b 一次批量 teacher 就应
首先回答这个问题，再决定是否值得投入 test/Petrov 与独立 holdout。
