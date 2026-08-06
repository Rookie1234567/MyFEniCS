# Task037 Review Report V7.1：Task37b 远程分支交接更正

## 0. 优先级

本文件仅更正 `review_report_v7.md` 中 Task37b 分支交接的范围；其余选择性合入、测试、master 推送和排除清单全部保持不变。

若本文件与 V7 的以下内容冲突，以本文件为准：

```text
Task37b remote branch push
Task37b branch creation requirements
Codex final report fields
```

## 1. 更正后的授权

只有 Task37 选择性合入全部通过、`master` 已成功推送，并确认：

```text
local master SHA == origin/master SHA
master worktree  == clean
```

才允许创建并推送 Task37b 分支：

```text
codex/20260807-task37b-hybrid-iterative-development
```

该分支必须精确从更新后的 `origin/master` 创建，然后推送至远程并设置 upstream。

## 2. 必须执行的分支状态

创建和推送后必须满足：

```text
local Task37b SHA  == origin/master SHA
remote Task37b SHA == origin/master SHA
upstream           == origin/codex/20260807-task37b-hybrid-iterative-development
ahead / behind     == 0 / 0
worktree           == clean
```

允许的 Git 操作等价于：

```bash
git fetch origin
git switch master
git pull --ff-only origin master
git switch -c codex/20260807-task37b-hybrid-iterative-development origin/master
git push -u origin codex/20260807-task37b-hybrid-iterative-development
```

实际命令可因本地状态调整，但不得改变上述最终身份。

## 3. 仍然禁止的操作

Task37b 分支推送后立即停止。此交接阶段仍然禁止：

```text
创建 task.md
创建任何 Task37b 文档
修改源码或测试
产生新提交
运行 PDE
开始 Hybrid iterative 实现
从非最新 origin/master 创建分支
强制覆盖同名本地或远程分支
```

如果同名本地分支或远程分支已经存在，禁止 force push、删除或移动；应停止并报告：

```text
local branch SHA
remote branch SHA
相对 origin/master 的 ahead/behind
是否可以安全复用
```

## 4. 为什么必须推送远程

Task37b 后续任务书将由主审直接写入该远程分支，因此远程 ref 必须先存在，并与最新 `origin/master` 完全一致。

## 5. 更正后的最终回报

在 V7 原有回报字段之外，必须明确报告：

```text
Task37b local branch name and SHA
Task37b remote branch name and SHA
Task37b upstream
Task37b local ahead/behind
Task37b worktree status
confirmation that no Task37b files or commits were created
```

## 6. 最终更正结论

```text
Task37b local branch creation = authorized only after master push
Task37b remote branch push    = required after local creation
Task37b task.md               = not authorized in this handoff
Task37b implementation        = not authorized in this handoff
```
