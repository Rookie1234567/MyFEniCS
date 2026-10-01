# Task42extra NN-V3：第三台笔记本入口

这是独立的WSL研究分支，研究**学习迭代修正**以及**同一模块作为FGMRES预条件器**，最终指向0.7nm三维非可分周期Maxwell前向仿真。它不是另外两条task42的续跑目录，也不是已经验证的求解器。

| 身份 | 值 |
|---|---|
| Repository | Rookie1234567/MyFEniCS |
| Branch / upstream | task42extra_NN-V3-learned-iteration / origin/task42extra_NN-V3-learned-iteration |
| 固定base | 5b489b7264b75a9461577303ff0f6bc8907c19dd |
| Task directory | docs/task042extra_nn_v3_learned_iteration |
| 执行端 | 第三台独立笔记本；WSL Linux；用户已选当前空目录 |
| 本次发布身份 | 文献和任务规划；PLANNED_NOT_RUN；不修改旧分支或master |

## 阅读顺序

先读根AGENTS、docs/AGENTS及仓库原则，再读[任务书](task.md)、[文献调研](literature_review.md)、[当前summary](outcomes/summary.md)。以后继续时必须同时读本目录新增的补充合同、最新review和response。两个旧分支的冻结证据在任务书里给出，只读理解，不执行其待办。

任务书中的F0到F5是首轮完整授权：环境与原作用资格、多层学习模块、非学习对照、两个固定训练种子、独立学习迭代和FGMRES对照、条件transfer、成本与目标容量报告。遇到局部工程阻塞先有据修复，能独立继续的工作继续，不只交安装结果。

## 在空WSL目录开始

保持现有Windows Codex客户端，实际命令在WSL中执行。当前目录本身成为仓库根；检查真实路径、WSL/Linux文件系统、owner/权限、symlink和目录内容后再clone，不在Windows挂载盘正式运行，不假定工作站路径。

```bash
GIT_TERMINAL_PROMPT=0 git clone --single-branch \
  --branch task42extra_NN-V3-learned-iteration \
  https://github.com/Rookie1234567/MyFEniCS.git .
```

已存在正确工作树则核对身份后续接；未知非空目录不删除、不reset/clean。使用独立环境/缓存，不访问工作站canonical Git，不SSH操作其他设备。

## 可直接交给Codex的启动文本

```text
请在当前第三台笔记本的WSL空目录独立执行NN-V3任务，不要操作另外两条task42或其他项目。

仓库：Rookie1234567/MyFEniCS
唯一分支：task42extra_NN-V3-learned-iteration
固定base：5b489b7264b75a9461577303ff0f6bc8907c19dd
任务目录：docs/task042extra_nn_v3_learned_iteration

先检查当前WSL目录、Linux文件系统、权限和内容。目录为空才把本分支直接clone到当前目录，不再嵌套MyFEniCS；已有正确clone时核对origin/branch/upstream/HEAD并安全续接，不能强制覆盖。保持Windows Codex客户端，所有项目命令实际用WSL的git/python/MPI执行。

完整读根/目录AGENTS、仓库原则、任务书、文献调研以及本目录最新review/response/summary，旧两分支只读。先记录真实CPU/RAM/WSL/磁盘/ABI；在本目录准备私有FE/ML环境和缓存，CPU即可，不以没有CUDA为阻塞。不改系统或其他环境、不SSH工作站、不索取密钥。

按task.md完成本轮F0–F5全部可执行工作，不仅完成初始化。主线是一个算子条件化、setup缓存、残差复线性的多层修正模块，以同一冻结权重分别运行独立迭代N、受保护迭代N-safe和右预条件FGMRES32的P，并与非学习及未训练对照比较。不要重新做FEINN坐标场训练或旧p4强逆。

先资格化原0.7nm三维micro的matrix-free作用、复伴随、Floquet、端口和完整恢复。新clone缺少旧ignored数组时在本机依照提交接口重建，不使用旧工作站路径或准确解训练。严格分离训练/validation/test及独立reference审核。

首轮资源和43200秒累计数值/辅助预算遵守任务书；一次一条heavy进程树，自身swap=0。局部工程失败在有据修复上限内自行处理，独立阶段继续；不能改物理/门限/数据边界凑PASS，不能因某个独立迭代失败跳过FGMRES对照。

完成后写response_v1.md、表格化outcomes/summary.md、compact原始记录、全成本/资源、scalability、tests和changed_files，并在本分支追加两份development总账。所有结果注明measured/derived/predicted/not_run。运行source SHA与最终文档HEAD分列。只推送本分支，不合并master，不强推，然后报告精确HEAD、工作树、实际命令/环境、真残差、场/通道误差、冷/热成本、NN是否有真实收益，停止等待review。
```

## 当前交付边界

本发布只增加本任务目录的文档，不包含已完成的NN实现、训练权重或新数值结果。分支继承的旧研究代码并未因此取得production资格。GitHub页面视觉渲染、WSL环境和正式数值Gate须分别报告，不能以文档存在替代执行通过。
