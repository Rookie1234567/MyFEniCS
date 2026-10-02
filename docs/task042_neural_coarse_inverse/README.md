# V24续行记录：账户接口及执行审批已恢复

2026-10-02T14:07Z之后实际只读主机核验通过：新候选核CPU15、PSI full avg10=0、原系统/邻增长余量和磁盘Gate通过。周额度用尽时允许使用现有余额；明确禁止使用重置卡，未调用重置功能。以下认证阻塞是早先真实历史，保留原始失败；本批现继续原Review V21队列，原heavy-stop15:34:23.502588Z、deadline16:04:23.502588Z保持。当前真实数值仍未运行，后续来源与计数由正式run绑定。

# 最新导航：V24 / Review V21：实现已提交，正式数值执行受认证阻塞

本轮已实现固定八块局部完整LU与同规格粗层配对的数值核、角色reader、有限队列和六个one-run入口。最终小模型定向回归28 passed，六入口均validate；正式SETUP和LW/LCW/LZ/LCZ/VERIFY均NOT_RUN。首次队列未通过空闲物理核准入，数值actor未创建；有界复核找到核后，启动重试因自动审批服务令牌刷新403而未执行。这不是方法的数值负结果；没有新的原方程/场/功率资格或神经增量。

[正式Review](review_report_v21.md)、[本地待提交Response](response_v24.md)、[结果](outcomes/local_block_coarse_pair_v24.md)、[分流](outcomes/records/qualification_and_dispatch_v24.json)、[源码/入口](outcomes/records/run_index_v24.json)、[审批故障](outcomes/records/approval_block_v24.json)。没有正式actor，旧导航不授权重跑历史campaign。

唯一下一建议：恢复Codex客户端认证后，原窗口仍有效且fresh资源准入通过时继续已验证的原队列；窗口耗尽则等待下一review明确新的时间窗口，不扩大数值范围。
以下历史正文逐字保留；旧“当前”只指其当时阶段。

# 最新导航：V23 / Review V20 已收口

[Review](review_report_v20.md)、[Response](response_v23.md)、[结果](outcomes/p1_image_minres_comparison_v23.md)、[Gate](outcomes/records/qualification_and_dispatch_v23.json)、[source/run](outcomes/records/run_index_v23.json)。S/D/M/Z/V完成，六状态0/6完整资格；同T原作用像QR可信但未突破暖平台，零trace散射未求出。数值已清场等待review，不merge。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# 最新导航：V22 / Review V19 已收口

[Review](review_report_v19.md)、[Response](response_v22.md)、[结果](outcomes/p1_trace_galerkin_correction_v22.md)、[Gate](outcomes/records/qualification_and_dispatch_v22.json)、[run/source](outcomes/records/run_index_v22.json)。S/N/P/Z/V完成，T未准入；粗层资格通过，0/3新候选原方程与完整物理通过。队列已清场，等待review；旧阶段只作历史，不merge。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# 最新导航：V21 / Review V18 已收口

[Review](review_report_v18.md)、[Response](response_v21.md)、[详细结果](outcomes/exact_action_recycled_correction_v21.md)、[Gate](outcomes/records/qualification_and_dispatch_v21.json)、[run/source](outcomes/records/run_index_v21.json)、[费用](outcomes/records/resource_costs_v21.json)。D0/A/B/C/V已执行，条件T/Z按原进展准入。数值队列清场后等待review，不能依旧导航继续旧实验；不merge。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# 最新导航：V20 / Review V17 已收口

[Review V17](review_report_v17.md)、[Response V20](response_v20.md)、[结果](outcomes/fixed_p3_ilu0_port_v20.md)、[原Gate](outcomes/records/qualification_and_dispatch_v20.json)、[source/run](outcomes/records/run_index_v20.json)、[费用](outcomes/records/resource_costs_v20.json)。S0/N/P0/P40/V已实际完成，0/5资格；T/C未准入。正式数值清场于窗口内，总elapsed交付超限单列。等待review，不merge。

以下历史正文保留，旧“当前”仅指其当时阶段。

# 最新导航：V19 / Review V16 已收口

[Review V16](review_report_v16.md)、[Response V19](response_v19.md)、[完整结果](outcomes/post_lsqr_residual_polish_v19.md)、[原Gate](outcomes/records/qualification_and_dispatch_v19.json)、[run/source](outcomes/records/run_index_v19.json)、[费用](outcomes/records/resource_costs_v19.json)。C0/P/L/VERIFY已实际执行，完整0/8资格；数值队列退出，当前仅等待review，不merge。下方“当前/待运行”是历史，不能继续旧campaign。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# 最新导航：V18 / Review V15 已完成

[Review V15](review_report_v15.md)、[Response V18](response_v18.md)、[完整结果](outcomes/gmres_repair_residual_completion_v18.md)、[独立Gate](outcomes/records/qualification_and_dispatch_v18.json)、[source/run index](outcomes/records/run_index_v18.json)、[费用](outcomes/records/resource_costs_v18.json)。F0/G64/G256/R/VERIFY均已实际执行，8冻结状态0合格；数值队列已退出，等待review，不merge。下方所有旧“当前/待运行”只是历史，不授权继续旧campaign。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# 当前导航：V17可恢复全空间续算已完成

最新合同为[Review V14](review_report_v14.md)，执行结果[Response V17](response_v17.md)、[完整证据](outcomes/resumable_full_trace_campaign_v17.md)、[run index](outcomes/records/run_index_v17.json)。旧版本导航仅为历史，不构成继续运行授权；当前清场等待review，不merge。
以下历史正文逐字保留；旧版本的“当前”只指其当时阶段。

# 最新执行导航：V16 / Review V13

本批为原有限元全空间校正，固定随机神经／多项式基只作辅助。三路线均实际启动，GPOLY/GNN资源中断、终态证据缺失；一次独立FE验证已收口；完整资格0/6。先读[Response V16](response_v16.md)、[正式Review V13](review_report_v13.md)、[完整结果](outcomes/augmented_full_trace_lsqr_v16.md)、[run/source](outcomes/records/run_index_v16.json)与[费用](outcomes/records/resource_costs_v16.json)。

五项one-run dat位于input/task042_neural_coarse_inverse/v16_*.dat，均显式opt-in；本轮已执行项不能在新的review前自行重跑。以下旧导航／初始化命令为历史，现工作树已正确登记于canonical common git。

# 当前入口：V15局部表示配对已完成

最新正式合同[Review V12](review_report_v12.md)，回应[Response V15](response_v15.md)，[结果](outcomes/local_trace_representation_v15.md)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index_v15.json)。六个规定V15 dat已实现并实际执行；局部1544/组合3098、8状态0合格，多项式组合更好，无神经训练增量。旧p4路线关闭；全部有限队列已完成，等待review。以下“当前/最新”和初始化命令都是保留历史，不是待执行步骤。

# 当前入口：V14正交trace与有限hidden位置重求

最新正式执行合同：[Review V11](review_report_v11.md)；本轮已完成：[Response V14](response_v14.md)、[方法与结果](outcomes/orthonormal_trace_reprofile_v14.md)、[统一summary](outcomes/summary.md)、[raw Gate/分流](outcomes/records/qualification_and_dispatch_v14.json)、[run index](outcomes/records/run_index_v14.json)。新家族ORTHONORMAL_NEURAL_FE_BASIS，6固定+2有界新点、独立10状态，decoder合格但物理全部失败；等待review。下方旧最新导航/初始化命令为历史，不需要再执行Git准备或旧campaign。


# 当前 V13 交付导航

[Review V10](review_report_v10.md)是本批正式合同；[Response V13](response_v13.md)、[切向／响应／联合补偿结果](outcomes/tangent_scale_head_compensation_v13.md)、[summary](outcomes/summary.md)、[run index](outcomes/records/run_index_v13.json)为最新入口。三个固定头切向通过新向量Gate；B收益不可分辨后继续C，两个合格联合方向实际接受1步，J相对改善仅7.149e-7，按门限不再继续。独立一次FE验证3个冻结状态，原Schur约0.798、native约0.309、散射误差约0.734，仍不合格。旧V11头1e-8、V12标量FD及全部负结果保留，不称精确VarPro或神经求解成功。一次末尾JSON错误仅恢复已保存证据，实际候选source与恢复source分列。

四个规定V13入口均已实现并经 `scripts/run_case.py` 实际one-run；有限Taylor复核及记录恢复各有显式独立dat，不表示无限重执行。求解／验证队列已经冻结，无新p4参考、GPU、最大模型或merge；等待review。以下V12及更早“当前／最新”全部是保留的历史导航，不能作为新的待执行合同。

# 当前 V12 交付导航

[Review V9](review_report_v9.md)授权固定头真实残差偏导及有界隐藏更新，明确不要求旧 V11 输出头先过 `1e-8` 驻点 Gate。[Response V12](response_v12.md)、[完整负结果](outcomes/actual_loss_block_descent_v12.md)、[最新 summary](outcomes/summary.md)、[run index](outcomes/records/run_index_v12.json)为本批入口。T1 对 M2/物理残差完成分账；T2 的实际三方向 FD 未出现规定稳定区，故 T3 不运行；有限 F 八次试探均使损失升高，接受隐藏步0、头建议0。T4 独立确认原方程和散射场仍失败。旧 M2/实际头内部门限与全部原结果保留，p4 强逆关闭、最终0.7nm／48小时未合格；只推送本执行分支待 review，不合并 master。以下 V11 与更早“当前”是历史导航原文。

# V11 历史交付导航

[Review V8](review_report_v8.md)是本轮正式合同；[Response V11](response_v11.md)、[完整结果](outcomes/stable_head_varpro_v11.md)、[最新summary](outcomes/summary.md)和[run index](outcomes/records/run_index_v11.json)为当前交付。原0.7 nm／384hex／p3／40端口保持；小系数制造问题通过，大系数在一次同分解修正后仍未过1e-8，实际稳定头的物理残差一致性亦未过1e-8。真实隐藏参数更新0次，独立FE场及原方程仍失败；旧p4路线关闭，最终目标未合格。下方带“当前／最新”的V7/V8及初始说明均是**历史原文**，不代表当前合同或状态。

# 当前 V8 交付导航

[Response V8](response_v8.md)、[尺度与执行对照](outcomes/scaling_and_execution_v8.md)、[最新summary](outcomes/summary.md)。列尺度负结果、batch等价与共享微基准成本正信号分别记录；旧p4路线关闭，不自动长训练／p6／大目标。Review V5为本轮合同，原文及以下历史导航保留。

# V7 当前入口：材料已授权，继续神经FE单次求解

最新执行合同为 [Review V4](review_report_v4.md)，数值方法／精度／资源沿用 [Review V3](review_report_v3.md)。0.7／2nm用户原值已固化，5／13.5nm旧输入核验值同表保存；唯一canonical材料为 [si_optical_constants_v1.json](../../input/materials/si_optical_constants_v1.json)，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`。nominal0.7使用source标签0.699999988原行，不插值；外部数据库元数据缺失不再阻塞。

本批 `V7_MATERIAL_FIXED_NEURAL_FE_CONTINUATION` 在已有384-cell/p3三维缺口几何上续跑真实S/Sᴴ、完整上下端口和恢复；真实N1通过后顺序NEURAL-TRACE／FREE-FE-OPT／FE-LSQR，再按条件独立验证。旧p4路线关闭，旧teacher／seed420620封存；不做四波长扫描、不启动最终规模。累计10小时预算包含V6已有费用，各路线仍最多2小时／2000完整closure或算子配对。Git、受控共享CPU、独立环境／缓存、自有锁和16/12GiB树监督继续；无合并授权。

本批已实际完成材料固化、真实N1、三条路线和独立p3盲验证。三候选全部未通过原方程／同离散场／功率Gate，p4 enrichment未准入；材料不再阻塞，最终目标仍未资格化。见 [Response V7](response_v7.md)、[完整结果](outcomes/neural_fe_single_solve_v7.md)、[summary](outcomes/summary.md)。只有等待review的一个最小建议，未启动最大模型或旧p4路线。

所有正式运行使用独立V7 one-run dat，经 `scripts/run_case.py`；唯一参考后处理错误只修复范数表达式、复用原参考重放验证，没有重分解或训练。源码／输入／模型／数据hash与全部费用见 [run index](outcomes/records/run_index_v7.json)、[resource costs](outcomes/records/resource_costs_v7.json)。

以下首次创建说明仅为历史，不代表当前状态，原文保留。

# Task042：NN-Lab 入口

唯一初始执行合同是 [task.md](task.md)。本目录目前只有任务文档，没有新实现、训练、PDE或性能结果。后续review、response、outcomes均留在同一分支。

| 项目 | 值 |
|---|---|
| 执行分支 | `task42_neural_coarse_inverse` |
| 冻结base | `ccd357885f7f9be84efe3be07868cc94f13d93fc`，来自`task39extra_para_workstation_capacity` |
| 本机工作树 | `/home/fenics/Projects/NN-Lab`，目录本身即仓库根 |
| 首轮问题 | 神经辅助低内存p4迭代粗逆；不是直接代理完整Maxwell场或R/T/A |
| 顺序 | 隔离与轻测试 → 单一13.5 nm小FE → teacher/可表达性oracle → 线性与NN → 严格粗逆 → 条件p6嵌入 |
| 正确性 | 原A4粗返回1e-10；条件p6原A6残差1e-6和完整物理/场检查 |
| 部署边界 | 候选不构造global p4 LU；teacher/参考进程单独运行和释放 |
| 资源 | 一次一项heavy；Task042空闲窗口RSS<=16 GiB，训练单GPU<=8 GiB |
| 当前状态 | `PLANNED_NOT_RUN`；现场环境与资源尚未核验 |
| 首轮交付 | 本目录`response_v1.md`与`outcomes/`，由Codex实际执行后写入 |
| 合并 | `NOT_APPROVED` |

## Linux命令行准备

以下命令由用户在已经登录远程工作站的Linux终端执行。`mkdir`只建目录，`git fetch`下载本分支对象，`git worktree add`将该分支检出到独立目录；不是在旧运行目录切分支。canonical Git路径来自已有工作站交接，脚本会先核对存在及origin；不满足时停止，不自动clone到另一个不登记的仓库。

先建目录：

```bash
mkdir -p /home/fenics/Projects/NN-Lab
ls -ld /home/fenics/Projects/NN-Lab
```

再执行整个括号块。它仅适合第一次初始化；目录非空或本地分支已存在时会停止，禁止为了重试使用rm/reset/--force。

```bash
(
  set -euo pipefail
  REPO=/home/fenics/Projects/Maxwell3D-Lab/task-repository.git
  TARGET=/home/fenics/Projects/NN-Lab
  BRANCH=task42_neural_coarse_inverse

  test -d "$REPO" || { echo 'STOP: canonical Git目录不存在，请核对原工作站记录。'; exit 1; }
  test -d "$TARGET" || { echo 'STOP: 请先创建NN-Lab目录。'; exit 1; }
  test ! -L "$TARGET" || { echo 'STOP: NN-Lab不能是指向旧任务的符号链接。'; exit 1; }
  ORIGIN=$(git --git-dir="$REPO" remote get-url origin)
  case "$ORIGIN" in
    https://github.com/Rookie1234567/MyFEniCS|https://github.com/Rookie1234567/MyFEniCS.git|git@github.com:Rookie1234567/MyFEniCS|git@github.com:Rookie1234567/MyFEniCS.git)
      ;;
    *) echo 'STOP: origin与预期仓库不一致，请人工核对，不修改origin。'; exit 1 ;;
  esac
  if [ -n "$(find "$TARGET" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo 'STOP: NN-Lab非空，不覆盖。'; exit 1
  fi
  if git --git-dir="$REPO" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    echo 'STOP: 本地分支已存在，请先检查worktree list，不重复创建。'
    git --git-dir="$REPO" worktree list
    exit 1
  fi

  git --git-dir="$REPO" -c gc.auto=0 fetch \
    --no-auto-maintenance --no-write-fetch-head --no-tags origin \
    "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  git --git-dir="$REPO" worktree add --track -b "$BRANCH" \
    "$TARGET" "refs/remotes/origin/$BRANCH"

  git -C "$TARGET" status --short --branch
  git -C "$TARGET" rev-parse HEAD
  git -C "$TARGET" rev-parse --abbrev-ref '@{upstream}'
  git --git-dir="$REPO" worktree list
)
```

成功后再进入新目录：

```bash
cd /home/fenics/Projects/NN-Lab
pwd
git branch --show-current
sed -n '1,100p' docs/task042_neural_coarse_inverse/task.md
```

应显示分支`task42_neural_coarse_inverse`、upstream `origin/task42_neural_coarse_inverse`。linked worktree中`.git`是指向common Git登记的文件，这是正常结构，不要把旧目录的`.git`或`.venv`复制进来。Git历史/refs共享，不等于工作文件、Python环境、缓存和运行资源共享；环境与资源隔离继续按task执行。

认证提示由用户自己在终端处理，不向聊天粘贴密码/私钥/token。Codex执行网络操作前使用非交互认证检查；失败应报告而不是静默卡住。不需要sudo，不改全局Git配置，不在原任务目录pull/checkout。

## 发给Codex的执行要点

在NN-Lab打开新会话，读取根/目录AGENTS、仓库原则、本README及完整task.md。先F0；若原2 nm或其他heavy运行，只做允许的轻量工作并以`WAITING_FOR_SHARED_WORKSTATION`交付，不能因此改旧watchdog或抢占硬件。资源空闲且各Gate通过后可顺序完成获授权阶段，不逐小步等待确认，不越过真实精度/资源失败。

只提交推送`task42_neural_coarse_inverse`。第一轮结束报告精确HEAD、source/输入/模型身份、无global p4因子证据、线性/NN对照、真实残差、全过程RSS/VRAM/时间及未运行项；不把目录/分支创建等同于环境已隔离或神经方案已通过。


## V9 最新有限批次入口

[Review V6](review_report_v6.md)授权固定误差定位；[Response V9](response_v9.md)及[完整结果](outcomes/frozen_error_localization_v9.md)为本轮交付。六状态齐次恢复/物理区域/原方程作用核验完成，没有新求解、训练、PC或loss变更。旧p4路线关闭，V7/V8负结果保留；后续建议等待review，未自动执行。


## V10 最新自主批次入口

[Review V7](review_report_v7.md)授权单个七小时窗口的原方程幅相／端口、固定隐藏线性头与随机特征对照，明确覆盖旧只诊断与仅本任务heavy独占限制。[Response V10](response_v10.md)、[完整结果](outcomes/autonomous_neural_head_v10.md)为本轮交付。A/B1/B0/C及D1/D2已完成，四候选均严格负结果，E/P条件未满足；全部可执行路径结束后提前收口，不重复计算填满窗口。旧p4路线关闭，历史与普通default不改；下一制造RHS建议仅提议未执行，推送后等待review，不merge。
