# Task43 资源 profile 接线记录

本记录只资格化 Task43 的 watchdog 资源身份与环境门，不代表 180-cell current、参考场或自适应精度已经通过。使用的 profile 为 `task43_hp_adaptivity_resource_v1`：任务树 RSS 上限不超过 192 GiB，有效 reserve 为 `max(64 GiB, 15% × effective total memory)`，规划上限不超过 RSS 上限，任务树 `VmSwap` 必须为零；全局 swap 只观察。旧 profile 默认规则保持不变。

在真实 `supervise` 父进程及其 worker 子进程间的轻量 smoke 中，worker 调用正式环境门并核对收到的标记。实测 envelope 为：effective total `2,163,100,385,280 B`、effective available `1,857,486,647,296 B`、reserve `324,465,057,792 B`（15%）、launch/planning cap 均为 `206,158,430,208 B`（192 GiB）；profile identity 一致，worker gate 为 `verified`，watchdog 分类 `COMPLETED`，子进程已清场。`h100_anchor` 的 preflight 现也要求该环境门，并把通过的 cap/reserve/profile 身份写入环境记录；MPI ranks 的门结果必须一致。

## 检查结果

| 检查 | 结果 | 证据 |
|---|---|---|
| Task43 profile/resource 与 h100 preflight targeted pytest | PASS，11 项 | `task43-initial-profile`、`task43-resource-profile`；最终日志 `/tmp/task43/resource-gate-targeted-final3.log`，SHA-256 `6f661ff2192436f19a54f578ab5e94f390315d7812a55ab08996136abea68686` |
| 既有 watchdog legacy 生命周期及 Task40 host-floor 回归 | PASS，7 项 | `test_orphan_setsid_child_is_sampled_and_reaped[False]` 与 `test_task40para_host_floor_policy.py`，4.52 s |
| compileall、F-select Ruff、Task43 profile/runner/tests Ruff、`git diff --check` | PASS | 使用已资格化 Task40 complex128/int64 activation；MPI1，PETSc `complex128`/`int64` |
| watchdog worker string smoke 的中间版本 | FAIL（测试命令拼接语法错误，非数值失败） | worker 因多余 `}` 产生 `SyntaxError`，summary 为 `WORKER_FAILED`，watchdog 仍清理子进程；保留日志 `/tmp/task43/resource-gate-targeted-final.log`，SHA-256 `ec1e4f57e6b8739f3f5f2e0fe5e1981b19eee47201ed9489116c8825c90bd068` |
| `test_196_task036_forward_solver_hardening.py` collection | NOT RUN | 导入旧 Hybrid 路径时 `slepc4py.SLEPc._initialize/register` 与 PETSc Viewer 冲突并抛出 `ValueError: key: 1211220, cannot register`；G0 环境记录注明 direct 路径 `SLEPc=NOT_LOADED_NOT_REQUIRED_BY_DIRECT_PATH`，本轮未重装或混用 ABI。该文件当前没有 diff。 |

轻量测试绑定当时 `HEAD=96e41e15987b7e8929bd5f486c6ee5c074a19911` 的 dirty worktree；资源实现、runner preflight 与测试已包含在随后提交中。参考原始系数资产和待资格化角色见 [`existing_validation_fields_v1.json`](records/existing_validation_fields_v1.json)：Y6_1 仅拟作 selection reference、Y6_2 仅拟作 calibration、Y5_1 保留 holdout；三者仍须完成恢复身份检查，不能据此开始 marking。
