# Task037-extra Response V8：H2B primary hard-stop consolidated handoff

本文件是 Review V8 的 consolidated handoff。旧的 [response_v7.md](response_v7.md) 保持不变，
只保留旧 H2A 资源负证据和此前冻结结论。本文件新增 H2B primary formal attempt #1、#2 及其
hard-stop 结论；R0/R1/R2 的 PASS 来自本轮 V8 对应 outcomes/records，不含混归入 response_v7。

## 阶段总表

| 阶段 | 状态 | evidence 边界 |
|---|---|---|
| H1R.0 / H1R3.0R | PASS | 既有 progress/action-only evidence |
| H1R3.1 / H1R3.2 | PASS | 既有 MPI2 identity / action-only scaling evidence |
| H2A-R0 / R1 / R2 | PASS | discovery、isolated cache-hit、constrained factor store；不等于 PDE |
| H2B primary | **FAIL_NUMERIC / NOT_QUALIFIED** | fixed unit-step 8-color smoother 的五类 full-space rho 全部失败 |
| H2C / H2D / H4 | not_run / locked_by_H2B | H2B hard stop 后未授权 |
| PDE / KSP / DtN / field / RTA | not_run | 没有本轮物理求解或后处理 |

保留的历史边界：G2=G2_FAIL、G3=prohibited、old G4=prohibited、旧 H1.2=CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED；ordinary default unchanged。旧 response_v7 中 H2A 的 FAIL_RESOURCE / NOT_QUALIFIED 不被改写。

## H2B attempt 与根因

Attempt #1 是 CONTROLLED_FAIL_EXECUTION_PROVENANCE：source 135b410...，stage
25.1384719 s、peak 1,278,312,448 B、swap 0，online 未运行。根因是 worker command
把 qualified .venv symlink 解析成系统 Python；它不是算法或 RSS 失败。修复只保留 .venv/bin/python
路径，未放宽任何 Gate。

Attempt #2 使用 source b6b83b338156ab039324aaa8b2705992dd3815ae，watchdog RC=0，checker
RC=1、status=gate_failed、problems=["sources"]。stage/online 的资源、cache-hit、factor payload、
identity 和 deterministic checks 均通过；失败项是五类 source 的 contraction rho：

| source | rho | limit | action error |
|---|---:|---:|---:|
| gradient-dominated | 4.542906419782354e24 | <=1.00 | 8.334049342656613e9 |
| curl-dominated | 2.6341788315209565e24 | <=1.00 | 4.897899039354024e9 |
| mixed | 4.361198568985487e24 | <=0.85 | 7.869345437306756e9 |
| checkerboard/high-frequency | 7.734935557489985e27 | <=0.70 | 1.4144039991387195e13 |
| physical-RHS-like | 1.304855993199958e24 | <=1.00 | 2.4474983919033117e9 |

五个 closure_error_relative_to_action 为约 1.80e-15..1.88e-15，所以失败不是 action/state
回算错；它是 primary smoother 的实际发散。这里的 official independent_action_relative_error
使用原始 RHS denominator 归一化，五项均远大于 1e-11，因此 official source check 与 rho 一起
失败；closure_error_relative_to_action 是改用巨大 action/residual numerator 的额外 derived
root-cause metric，不能替代或放宽 official Gate。16 个 factor 的离线 fixed-RHS gain 为约
459..876 且 finite，未发现 class/factor/row/orientation/constraint mapping 错绑。结论为
**C：primary algorithm genuine failure**，而非 action、JIT、resource 或 PDE failure。

## Verification

| 检查 | 结果 |
|---|---|
| test295 | 24 passed |
| focused 286–295 | 120 passed；与 formal source SHA 相同，之后无 Python 改动 |
| compileall | pass |
| canonical JSON byte/SHA | pass；与 attempt2 保存记录完全一致，SHA `e95d39...fcc9d7c` |
| links / JSON / math / whitespace | pass |
| git diff --check | pass |
| Ruff | unavailable；未声称 CI |

以上是本地验证，不是 CI 结果。

## 资源、目标与停止条件

Attempt #2 measured stage 25.302699346095324 s / 1,281,990,656 B、online
897.7731916790362 s / 685,731,840 B，均 swap 0，termination null；watchdog total
923.2641486080829 s。online 为 full-space action experiment，不是 PDE process-tree peak。

H2B 记录了 173802 rows、9210 identity rows、24 classes、16 factors、factor payload
201933812 B、smoother factor+work 217953872 B、8 colors、每次16 actions、10 applies、
action/apply median ratio 15.513323299702968。这些资源和结构事实不能把 685731840 B 解释为
用户所要求的 MPI1 PDE <2GB 结果。

用户最终目标仍未达成：本轮没有 PDE、没有 true PDE residual、没有 field/RTA，也没有 direct-method
physical comparison。因此不能宣称 PDE peak、直接法一致性或物理结果通过。

由于所有 source rho >1.20，Review V8 的唯一 face-pair fallback 条件不满足，正式流程在
H2B hard stop。H2B formal 已使用 2/3 预算，第三次未启动；不进入 H2C/H2D/H4/PDE/DtN/RTA。

## Authority 与 evidence index

| evidence | 路径 / SHA |
|---|---|
| outcome | [h2b_block_smoother.md](outcomes/h2b_block_smoother.md) |
| canonical compact | [h2b_block_smoother.json](../../benchmarks/cases/101_task37_extra_development/records/h2b_block_smoother.json)，file e95d39a52321f5d3a568d54912dc74ee0893cd5fc82a4c4dac1fb8dc3fcc9d7c |
| compact embedded evidence | f7248727afed040d28e3a263377f2318c21bc420d571841b9d5a277d089062c6 |
| attempt2 raw | [h2b_primary_b6b83b3_run2](../../benchmarks/artifacts/task037_extra_development/h2b_primary_b6b83b3_run2) |
| attempt1 negative compact | [h2b_block_smoother_attempt1_runtime_path_failure.json](../../benchmarks/cases/101_task37_extra_development/records/h2b_block_smoother_attempt1_runtime_path_failure.json) |
| frozen R2 factor manifest | [manifest.json](../../benchmarks/artifacts/task037_extra_development/h2a_r2_da8ddbb_run1/factor_store/manifest.json)，1bac2dab... |

正式 watchdog/checker 命令：

~~~bash
cd /home/shenjh/Projects/MyFEniCSx_task37_extra
export GIT_DIR="$PWD/.git-codex"
export GIT_WORK_TREE="$PWD"
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_h2b watchdog \
  --run-dir benchmarks/artifacts/task037_extra_development/h2b_primary_b6b83b3_run2
python -m benchmarks.run_task037_extra_h2b check \
  --run-dir benchmarks/artifacts/task037_extra_development/h2b_primary_b6b83b3_run2 \
  --output benchmarks/cases/101_task37_extra_development/records/h2b_block_smoother.json
~~~

本次只读 evidence 收口对同一 raw 再执行一次 lightweight checker，RC=1，canonical 与保存的
attempt2 compact byte-identical；没有启动 worker/heavy，也没有修改 raw。

## 既有结论与 selective-merge 建议

| 组别 | 建议 |
|---|---|
| H2B core + runner | research-only / do-not-promote-default；无 production numerical candidate 获资格 |
| tests / evidence / docs | 可保留用于审阅、回归和失败边界追踪 |

H2A 的旧资源负证据、response_v7.md、旧 outcomes 和 G2/G3/G4/H1 结论均未被改写。没有新增
H2C/H2D/H4 record/outcome，没有新分支、PR、merge、rebase、cherry-pick、force push 或
master/default 操作。后续只能由新的 Review 决定是否开展别的研究路线，不能把本次 H2B 失败绕过为
通过。
