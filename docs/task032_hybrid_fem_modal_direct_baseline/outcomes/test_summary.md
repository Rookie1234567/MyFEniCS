# Task032 回归摘要

## 实现回归

在 complex128 Docker 环境完成：

```text
Task32 serial/MPI1 test_32--test_40 = 41 passed
Task32 MPI2 selected distributed set = each rank 29 passed, 2 skipped
Task32 MPI4 selected distributed set = four ranks each 29 passed, 2 skipped
full src/test serial = 212 passed, 10 skipped, 299 subtests passed
```

MPI skip 是既有的重型负向/tracking 分工；其余测试和正式 runner 仍覆盖截面
assembly/eigenvector ownership、trace projection、Hybrid block、augmented direct、
Modal-Schur、memory-minimal 生命周期与 selected field reconstruction。

## 正式 evidence Gate

```text
Case080 checker before final-record extension = 294/294 passed
Case080 final checker = 302/302 passed
formal main records = h5/h3 x M120/M160, all clean and physical gates pass
formal memory records = six paths, all numeric pass, zero swap, correct source/image identity
formal parameter smoke = 30/30 pass
h2 decision gate = pass with h2_unlock=false
```

`h2_unlock=false` 仍被 checker 视为通过，因为任务书要求预测超过阈值时停止，
不是要求无条件运行 h2。

## 已解释的环境事件

容器内 checker 曾停在 Windows bind mount 上的 `git status --short`。数值测试完成
后停止临时容器，随后在宿主 PowerShell 运行同一 checker，约 13.2 s 完成
294/294。最终扩展 checker 也在宿主重复通过 302/302。该事件是挂载上的 Git
性能问题，不是数值失败或 MPI 死锁。
