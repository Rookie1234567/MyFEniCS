# M4Y full-space packed-patch PC：正式结果与固定权重诊断

## 结论先行

M4Y 是一个 research-only 的 full-space 局部预条件器实验。它复用 M3Y 的 84 份只读 packed Cholesky 因子，让 252 个 cell patch 产生局部修正，再用一次真实的 full-space `B0` action 做统一缩放。它的作用是低内存地生成一个修正方向，不是直接完成 PDE，也不自动保证高频误差会下降。

正式 checkerboard source 的残差为 `0.9931217079734292`，限值为 `0.70`，因此 M4Y 正式结论是：

| 项目 | 结论 |
| --- | --- |
| source | `766154ae731ee9fac6d23492801ed7ac6e318616` |
| watchdog | `RC=0`，`PASS` |
| checker | `RC=1`，`status=gate_failed` |
| 最终分类 | `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED` |
| 原因 | 只有 checkerboard source 的正式 rho 超过 `0.70` |
| 失败类型 | 不是 execution、JIT、RSS、swap 或 resource failure |

用户明确授权原文为：“我允许你继续正式允许，不用管v11里的限制，继续执行任务”。按上下文解释为：用户允许继续正式运行并越过 V11 中被点名忽略的阶段/次数限制。该授权没有放宽 full-space、数值、RSS `<2,000,000,000 B`、swap=0、true residual、physics 或 provenance Gate。M4Y 失败保持冻结，不能包装成 execution-fix 或 PASS。

## 正式 M4Y 五类 source

rho 表示一次局部修正后，剩余误差相对于修正前误差的比例；越小越好。`repeat=0` 表示 correction/action 的重复结果满足固定确定性检查，`wall ratio` 是局部 PC 与一次 action 的时间比。

| source | rho | 限值 | repeat | wall ratio | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| gradient-dominated | `0.5726363196244373` | `0.90` | `0` | `1.0648731722995044` | PASS |
| curl-dominated | `0.5119565347353272` | `0.90` | `0` | `1.0527972304686382` | PASS |
| mixed | `0.5651932967410976` | `0.80` | `0` | `1.0546199852088745` | PASS |
| checkerboard/high-frequency | **`0.9931217079734292`** | **`0.70`** | `0` | `1.0540019605701865` | **FAIL** |
| physical-RHS-like | `0.4860142993018098` | `0.90` | `0` | `1.061045779894205` | PASS |

checkerboard 的 rho 接近 1，说明这个局部修正几乎没有压低该高频模式。其他四类 source 都通过各自限值，所以失败是明确的数值覆盖范围问题，不是整个 worker 没有运行。

compact 中的 `independent_recompute=false` 是 checker 将 source Gate 合并为一个最终布尔后的结果；它不表示数组或 omega 的独立重算不一致。checker 已重算 correction、action 和 omega，且其他结构 checks 均通过；真正触发失败的是 `rho=0.9931217079734292 > 0.70`。

## 资源、身份与架构 Gate

| 项目 | 实测/要求 |
| --- | ---: |
| isolated stage peak | `1,290,907,648 B` |
| online peak | `909,246,464 B` |
| stage / online process gone | `true / true` |
| swap | `0` |
| M3Y packed store retained | `525,196,562 B` |
| evidence workspace | `69,520,800 B` |
| M4Y PC workspace | `11,151,552 B` |
| factor reuse / factor copy | `168 / 0` |
| p6 identity | `252 cells / 252 local cells / 882 local rows / 173802 global rows / 9210 constraints` |
| loaded store | `84 factors / 252 cells / mmap read-only / retained gate=true` |
| full-space identity | `fine_space=uncondensed_fullspace` |

M3Y store 的 `525,196,562 B` 在固定 `560,000,000 B` retained envelope 内；M4Y 只读取共享 factor，252 个 cell 没有复制成 252 份 factor。所有禁用 materialization 均为 false：global matrix、global constraint matrix、cell Schur、trace slab、KSP、DtN、PDE 均未物化，`ordinary_default=false`。`909,246,464 B` 是 M4Y online process-tree peak，不是 PDE peak；PDE 的 full process-tree RSS 尚未测量。

## 最终代码后的 focused 验证

这些是 M4Y 最终代码后的实现回归，不是正式资格化；本轮文档收口没有重跑它们。

| 验证 | 结果 |
| --- | --- |
| `test309` + `test307` + `test308` + `test294` | 合计 `18 passed` |
| 相关 `compileall` | pass |
| AST duplicate-literal-key 检查 | pass |
| `git diff --check` | pass |
| Ruff | unavailable |
| full repository pytest | `not_run` |

## M4Y-W：固定权重位置诊断

M4Y-W 只做一次离线、固定的结构诊断，不是第二次资格化。它比较：A 正式使用的左侧 PoU；B 不除重叠计数的 additive Schwarz；C 输入和输出都除以平方根重叠计数的 symmetric sqrt-PoU。没有调参、线性组合、颜色、顺序选择或结果驱动的候选筛选。

状态固定为 `BEST_CASE_STRUCTURE_DIAGNOSTIC_ONLY / not_formal_pass`。A 逐位复现正式 M4Y 的 correction/action；B、C 的 checkerboard 也没有达到 `0.70`。

| source | 限值 | A left-PoU | B unweighted | C sqrt-PoU |
| --- | ---: | ---: | ---: | ---: |
| gradient-dominated | `0.90` | `0.5726363196244373` | `0.6522833075546219` | `0.5389466254290002` |
| curl-dominated | `0.90` | `0.5119565347353272` | `0.5860664196870441` | `0.5006462879867353` |
| mixed | `0.80` | `0.5651932967410976` | `0.644166345359071` | `0.534162054038329` |
| checkerboard/high-frequency | **`0.70`** | **`0.9931217079734292`** | **`0.9602175114`** | **`0.9732722411`** |
| physical-RHS-like | `0.90` | `0.4860142993018098` | `0.5544966067454279` | `0.4825702522346798` |

诊断的最大 RSS 为 `886,696 KiB`，swap=`0`。B/C 仍失败，说明单纯把重叠权重放在合并前或合并后，并不能修复 checkerboard 方向；这只是结构机制的诊断，不足以证明 SPD、global solver 或 PDE 资格。

| M4Y-W 证据 | SHA |
| --- | --- |
| script | `56ae70156cb5bf27dd3ebdee194233b7fc2554135b21d29bc50f370a6281b1b0` |
| JSON | `78a8bbf4ec4ffa4b8aa6a9ff9e55ffca7bbd01fcb050e199c23b9cc9a7e1b1dd` |
| stdout | `ad83738cc4acf9fbb6e535bcafbd72a0a1623dca6bdc74e44dca15296ae62f01` |

## 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| M4Y raw | `benchmarks/artifacts/task037_extra_development/m4y_766154a_run1`；tree digest `7db097d4c894e152753ab3c3a618f6556fd1cebec50fff6fbb2bee359e2d6580` |
| watchdog summary | `m4y_watchdog_summary.json`；`f56a0b0fb607d07045362d9dce4dc62174e57992c0af779e9a57b0099d92b03c` |
| worker summary | `m4y_worker_summary.json`；`e37bacc6901faefa7844aa2a2894011f5da7ffcf623a1c6d4d5d4ffd32e778c4` |
| online timeline | `online_timeline.json`；`cd7dbe1c41a1505cfc842aeed9ed911cd9f82a2eb79bab0e0fa048db69fe7bad` |
| M4Y compact | `benchmarks/cases/101_task37_extra_development/records/m4y_full_packed_patch_pc.json`；`7c227b67f288ca88990f1bc966f1266ff28eb280d0bc9623ab1354f527634812` |
| frozen M2 compact | `benchmarks/cases/101_task37_extra_development/records/m2_high_complement_patch_oracle_v2.json`；`ebd512aa0e4b6823d5d95c5f816cc6e898c9fd97392af4f7346c83ba3ac4e31f` |

## 后续边界

M5、M6、PDE、RTA、full true residual、direct-authority physics comparison 和最终 PDE process-tree RSS 均为 `not_run_yet`/`not_measured`。因此当前没有达到“full PDE process-tree RSS 严格小于 2,000,000,000 B、swap=0、true residual 和直接法物理对照通过”的最终目标。M4Y-W 自身不提供后续 qualification；M5 独立 research lane 的继续依据仅是用户本轮明确授权，不意味着 M4Y 打开了 M5 或其他 Gate。ordinary default 保持不变。
