# 固定源码 W0 接收入口

用户在 Review V23 结束后明确要求继续 W0，再推进原尺寸完整端口。本入口在
已登记的 FEINN 工作树内接收已有主线组件，不改其他分支，也不复制维护第二个
求解器。`dependencies.json` 列出主线固定提交的最小静态 import 闭包与每个文件
的 Git blob、SHA256 和字节数；运行时从已有 canonical Git objects 生成只读
source cache。它没有 `.git`，不是 clone、worktree 或新的源码权威。

数学 worker 和独立 checker 原样复用
`d4b6ed6b6cb2a0431cb75bba9d8fc74dc9d9e382`。本支只增加显式 one-run 接收入口、
时间/资源/持久执行绑定。两种源码 SHA 分别记录，不用 FEINN launcher SHA
冒充主线数值源码。旧主线过期窗口、ABI/模式失败和费用保持，当前独立接收窗口
包含准备、测试、导入、JIT、worker、checker、原数组保存读回及清场。

固定组件为 80 hex、p6、532 出射模式、λ0.7、φ5°，包含全部内部自由度、
方向和 MPC、非零内部/端口 RHS；输入保持字节 hash 6654ec… 不变。
这不是原尺寸求解，也没有 NN。只有完整科学 raw 与独立 checker 通过，
才可记组件通过；不能把控制冒烟、导入或单元测试记为 W0 成功。

```bash
source scripts/activate_task42extra.sh pure
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v24_w0_control.dat
# 完整收尾清场且 CONTROL_SMOKE_PASS_NO_FE 后：
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v24_w0_component.dat
```

独立 native prefix 只读复用，不安装或升级；每次生成本机 ABI 收据并逐级核对。
整树 3 GiB、MPI1/线程1、一个现场空闲物理核、自身 swap0，保留 384 GiB
邻任务增长及原系统余量。原 worker/checker 各 4500s 和 raw8GiB 门不变；
launcher、独立 tmux、监督、编译器和 worker 同树计费，任务末段保留600s。
入口拒绝未提交源码、复用旧 run 目录和不完整控制冒烟；不自动重启。

FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED
保持。只有 W0 完整结果才可决定后续端口接入；W1/W2 和全目标资格不能继承。
