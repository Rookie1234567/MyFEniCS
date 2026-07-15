# Task032 回归摘要

研究实现提交前的 complex128 Docker 回归：

```text
Task32 serial/MPI1 test_32--test_40 = 41 passed
Task32 MPI2 selected distributed set = each rank 29 passed, 2 skipped
Task32 MPI4 selected distributed set = four ranks each 29 passed, 2 skipped
full src/test serial = 212 passed, 10 skipped, 299 subtests passed
existing Case080 checker before formal record extension = 294/294 passed
```

MPI skip 是既有的重型负向/tracking 分工；MPI runner 和其余测试仍覆盖截面
assembly/eigenvector ownership、trace projection、Hybrid block、direct solve、
Modal-Schur、memory-minimal lifecycle 和 selected field reconstruction。

容器内 checker 曾停在 Windows bind mount 上的 `git status --short`。全量测试已
完成后主动停止该临时容器，避免孤儿 Git 进程；随后在宿主 PowerShell 运行同一
checker，13.2 s 完成 294/294。该事件不是数值失败。
