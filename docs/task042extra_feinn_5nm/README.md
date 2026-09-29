# Task42extra：NN-Lab-V2 / 5 nm compatible FEINN

本目录对应独立支线，不是原 Task042 的新版本或旧粗逆续跑。唯一初始执行合同为 [task.md](task.md)，目录规则见 [AGENTS.md](AGENTS.md)。

| 项目 | 冻结身份 / 当前状态 |
|---|---|
| 远程仓库 | Rookie1234567/MyFEniCS |
| 执行分支 | `task42extra_feinn_5nm` |
| 冻结base | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`，来自 `task42_neural_coarse_inverse` |
| 工作树根 | `/home/fenics/Projects/NN-Lab-V2`；用户只建空目录，Codex完成Git和环境 |
| 首轮问题 | 5 nm、Si/air、非可分三维缺口、双Floquet/Fourier-DtN；384 hex/p3小型资格试验 |
| 方法 | 坐标网络→完整Nédélec边/面/内部矩→原native全FE残差；对比欧氏与Riesz对偶loss |
| 与Task042区别 | 不仅训练trace、不求p4逆；端口仅准确解析消元；内部FE系数由网络矩产生 |
| 辅助成本 | 小型DUAL路线允许准确稀疏Gram因子，必须全程记账；不称无全局因子生产方案 |
| 执行端 | 工作站原生Linux；独立worktree/环境/cache；已有项目只读，不改其运行 |
| 共享上限 | 初始轻测试1核/2GiB；正式pilot1核、MPI1、线程1、RSS hard16GiB、swap0、无GPU |
| 首轮预算 | 有载及辅助累计≤16h；每条候选≤3h/4000closure；是停止上限，不是成功承诺 |
| 当前结果 | `PLANNED_NOT_RUN`；新环境、算子、训练、资源均未运行 |
| 目标边界 | 首轮不是目标尺寸5nm，不是0.7nm/48h或任意三维资格；不merge |

## 用户只需要创建目录

在已登录工作站的Linux终端执行：

```bash
mkdir -p /home/fenics/Projects/NN-Lab-V2
ls -ld /home/fenics/Projects/NN-Lab-V2
find /home/fenics/Projects/NN-Lab-V2 -mindepth 1 -maxdepth 1 -print
```

最后一条无输出表示空目录。已有文件时不要清空；交给Codex按任务书检查。不需要用户运行git init/clone或安装包。

## Codex启动顺序

从本空目录开始，先识别已登记canonical common Git directory并仅fetch本分支，登记linked worktree；本目录本身是repo根，不嵌套MyFEniCS。既有记录的common目录为 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`，必须现场核验。

检出后先读根/目录AGENTS、仓库原则、本task和冻结base的review/response，再按E0–E5推进。不要在旧NN-Lab执行checkout/pull/install/训练，不向旧分支或master写入。权限、资源或物理Gate不通过时保存真实原因并完成仍可做的独立部分，不无限等待。

后续结果由Codex写入本目录 `outcomes/` 与 `response_v1.md`，本分支review闭环；`task.md`不可由Codex覆盖。推送精确refspec为 `HEAD:refs/heads/task42extra_feinn_5nm`。
