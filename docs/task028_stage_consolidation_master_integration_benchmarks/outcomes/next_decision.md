# 下一步决策

## 当前顺序

1. 推送包含 `response_v4.md` 的 Task28 分支。
2. 按用户明确许可，以普通 merge commit 合并到 `master`，保留完整 task/review/response 历史。
3. 在更新后的 `master` 执行轻量 release check。
4. 从该 `master` 创建 `codex/20260713-task29-stage4-direct-memory-forensics`。
5. Task29 先记录 master base、merge commit、分支、工作树、镜像 digest、主机内存/swap/cgroup，再执行 h5/h3 内存剖析；h2 继续受条件 Gate 锁定。

## 明确保留

Task29 不覆盖 Task28 canonical records，不继承历史 research branch 的失败 runner，不改变 ordinary default，并同时遵守 `task.md`、COMSOL 强制补充和参考报告。
