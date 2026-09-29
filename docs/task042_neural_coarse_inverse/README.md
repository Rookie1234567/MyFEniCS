# V7 当前入口：材料已授权，继续神经FE单次求解

最新执行合同为 [Review V4](review_report_v4.md)，数值方法／精度／资源沿用 [Review V3](review_report_v3.md)。0.7／2nm用户原值已固化，5／13.5nm旧输入核验值同表保存；唯一canonical材料为 [si_optical_constants_v1.json](../../input/materials/si_optical_constants_v1.json)，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`。nominal0.7使用source标签0.699999988原行，不插值；外部数据库元数据缺失不再阻塞。

本批 `V7_MATERIAL_FIXED_NEURAL_FE_CONTINUATION` 在已有384-cell/p3三维缺口几何上续跑真实S/Sᴴ、完整上下端口和恢复；真实N1通过后顺序NEURAL-TRACE／FREE-FE-OPT／FE-LSQR，再按条件独立验证。旧p4路线关闭，旧teacher／seed420620封存；不做四波长扫描、不启动最终规模。累计10小时预算包含V6已有费用，各路线仍最多2小时／2000完整closure或算子配对。Git、受控共享CPU、独立环境／缓存、自有锁和16/12GiB树监督继续；无合并授权。

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
