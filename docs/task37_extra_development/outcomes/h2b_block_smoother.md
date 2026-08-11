# H2B element-block smoother：primary formal hard stop

本记录属于 Review V8 的 H2B primary evidence。它只讨论 full-space matrix-free action 上的局部
element-block smoother 试验，不是 PDE、KSP、DtN、field、RTA 或直接法物理结果。

## 先用通俗语言说明方法

element-block smoother 把相邻有限元单元的小块局部方程拿出来解，再把这些局部修正加回整个
full-space/全空间。这里的局部块来自同一 material、几何宽度、方向和 Floquet 约束模式的 exact class；同一
class 只保存一个 constrained factor，避免每个 cell 都保存一份大 dense factor。

- **coercive B0**：V8 合同严格规定本轮局部代理为
  B0 = K_curl + k0^2 * M_|epsilon|。代码表达式写作
  (1/mu_r) * K_curl + k0^2 * M_|epsilon|；本固定配置 mu_r=1，因此数值完全相同，没有改变
  operator，也没有把原始物理算子或 PDE 改成另一个问题。
- **PoU 权重**：一个全局行可能被多个 cell 看到；把每个 cell 的修正除以该行的出现次数，
  使这些贡献加起来只算一次。
- **coloring**：把没有共享 independent/master 行的 cell 放进同一颜色。每种颜色可以合并成
  一次 full-space action，而不是每个 cell 调一次 action。

收益是少存 global matrix、Schur/slab factor 和 per-cell factor；代价是局部修正必须真的收敛。
本次资源、cache 和局部 factor 证据通过，但固定 unit-step forward/reverse sweep 数值发散，故
整体不合格。

## 结论与永久边界

| 项目 | 实际结论 |
|---|---|
| Review | V8 |
| H2B primary | **FAIL_NUMERIC / NOT_QUALIFIED** |
| formal attempt | #2/3；第 3 次未使用 |
| H2C/H2D/H4 | locked / not_run |
| fallback | 禁止；未实现、未运行 |
| attempt2 source | b6b83b338156ab039324aaa8b2705992dd3815ae，start/end clean；attempt1 source 为 135b410... |
| watchdog / checker | formal watchdog RC=0；checker RC=1, gate_failed |
| checker problems | ["sources"] |
| ordinary default | unchanged |

永久 full-space identity 没有被 H2B 改写：

| identity | 值 |
|---|---|
| rows / constraints | 173802 / 9210 |
| fine space | uncondensed_fullspace |
| condensation | false |
| global matrix / global constraint matrix | false / false |
| condensed Schur / cell Schur / slab matrix | false / 0 / 0 |
| slab factor / KSP / DtN / PDE solve | 0 / false / false / false |
| static condensed operator / trace slab PC | false / false |
| B2/B4 local Krylov | false |
| fullspace patch lane | true（候选 lane；不表示本轮 patch 已通过） |
| interior recovery | false |
| ordinary default changed | false |

## Attempt 1：runtime-path controlled failure

第一次尝试不是数值失败，也不是资源 Gate 失败。stage 在启动后因 worker command 把 qualified
.venv symlink resolve 成 /usr/bin/python3.12，导致 runtime identity 不闭合；online 没有
启动。

| 项目 | 实际值 |
|---|---|
| source | 135b410d4f2b5c48bf60b915b20e557503d41ec7 |
| raw | [h2b_primary_135b410_run1](../../../benchmarks/artifacts/task037_extra_development/h2b_primary_135b410_run1) |
| stage elapsed / peak | 25.1384719 s / 1,278,312,448 B |
| stage swap | 0 B |
| online | not run |
| 原始 compact | [h2b_block_smoother_attempt1_runtime_path_failure.json](../../../benchmarks/cases/101_task37_extra_development/records/h2b_block_smoother_attempt1_runtime_path_failure.json) |
| compact SHA | c5d5676a2b96ae77499cea85b83418d13ede7116acd74d8099489e8569b90ff8 |
| raw watchdog SHA | c7c34ffda4db7bef72fe659f64646461fd374010f18ade6a2ccad160effcb3a5 |

唯一修复是用绝对路径但保留 .venv/bin/python 表达，不再解析 symlink；没有放宽 runtime、RSS、
swap 或数值 Gate。attempt1 raw 和 compact 均保留，未覆盖。

## Attempt 2：资源和生命周期实际通过

| 阶段 | elapsed | process-tree peak | swap | termination | Gate |
|---|---:|---:|---:|---|---|
| stage | 25.302699346095324 s | 1,281,990,656 B | 0 B | null | <1,800,000,000 B PASS |
| online | 897.7731916790362 s | 685,731,840 B | 0 B | null | <1,450,000,000 B PASS |
| watchdog total | 923.2641486080829 s | — | 0 B | normal | lifecycle PASS |

online 记录了 cells=252、local nloc=882、rows=173802、constraints=9210。R2 factor store
加载后为 24 classes / 16 unique factors / 8 exact numeric deduplications，verified retained
factor payload 为 201,933,812 B；smoother 的 factor_plus_work_bytes=217,953,872 B，低于
500,000,000 B。所有 factor values/pivots finite，factorization residual 最大
8.540193602788576e-16，solve residual 最大 4.861914019080286e-11。

| smoother audit | 实际值 |
|---|---:|
| independent / slave identity rows | 164592 / 9210 |
| colors | 8 |
| action count per apply / total | 16 / 160 |
| apply count | 10 |
| PoU closure | 0.0 |
| multiplicity min / max | 1 / 4 |
| same-color rows disjoint | true |

Cache/lifecycle 也通过：form_jit_cache_hit=true、cache before/after 完全一致、
c_source_regeneration=false、online compiler descendants 为空；stage 进程在 online 启动前已
全部回收。上述事实解释了为什么本次不是 JIT、资源或 process-tree hard stop。

| timing | 实际值 |
|---|---:|
| action median | 5.2700307331979275 s |
| smoother apply median | 81.75569056347013 s |
| smoother/action ratio | 15.513323299702968（<=30） |

## 五类 residual source 与失败 Gate

每个 source 都执行两次 apply；correction/residual 的首尾 SHA 相等，故 deterministic 为真。
norm 是 full-space denominator，numerator 是独立 B0 action 后的 full residual 范数；没有
外部 slave mask Gate。

| source | norm | numerator | rho | Gate | independent action error | finite / deterministic |
|---|---:|---:|---:|---|---:|---|
| gradient-dominated | 401.43444486160365 | 1.8236791166835445e27 | 4.542906419782354e24 | <=1.00 FAIL | 8.334049342656613e9 | true / true |
| curl-dominated | 1117.3124238712332 | 2.9432007351569727e27 | 2.6341788315209565e24 | <=1.00 FAIL | 4.897899039354024e9 | true / true |
| mixed | 0.9999999999999929 | 4.361198568985456e24 | 4.361198568985487e24 | <=0.85 FAIL | 7.869345437306756e9 | true / true |
| checkerboard/high-frequency | 405.69939610504724 | 3.1380586845851435e30 | 7.734935557489985e27 | <=0.70 FAIL | 1.4144039991387195e13 | true / true |
| physical-RHS-like | 1337.244782969651 | 1.7449118694333262e27 | 1.304855993199958e24 | <=1.00 FAIL | 2.4474983919033117e9 | true / true |

这里的 official independent_action_relative_error 使用原始 RHS 的 denominator 归一化；五项都远大于
1e-11，所以 official source check 与 rho Gate 一起失败。下面的
closure_error_relative_to_action 只是额外的 derived root-cause metric，它改用巨大的
action/residual numerator 作归一化，不能替代 official Gate，也不能放宽 1e-11 或 rho 限值。

独立检查按 independent_action_relative_error * denominator / independent_residual_numerator
重算 action 相对闭合误差：

| source | closure error relative to action |
|---|---:|
| gradient-dominated | 1.8345192642237808e-15 |
| curl-dominated | 1.8593646645190038e-15 |
| mixed | 1.8043997109577477e-15 |
| checkerboard/high-frequency | 1.8285918332818007e-15 |
| physical-RHS-like | 1.8756846768210790e-15 |

这五个值接近舍入误差，说明保存的 residual 与独立 action 回算一致；失败来自 smoother 产生
的 correction/action 过大，而不是 action callback 的非线性或状态错乱。

## factor 离线诊断与 mapping 边界

离线读取冻结 R2 manifest 的 16 个 factor，未构建 mesh、FE、JIT 或 PDE。固定 RHS 为
q1=normalized(ones(882)) 与 q2=normalized((1..882)+i*(-1)^index)。下表给出 factor 到 R0
class 的完整绑定；m/o 是 material tag/orientation，I/X/Y/C 分别表示 interior、edge/face-x、
edge/face-y、含 corner 的组合模式。

| factor | R0 class → m/o/kind |
|---:|---|
| 0 | 0→1/0/C; 1→1/0/X |
| 1 | 2→1/0/Y; 3→1/0/I |
| 2 | 4→1/32769/X |
| 3 | 5→1/32769/I |
| 4 | 6→2/0/I |
| 5 | 7→2/36873/X |
| 6 | 8→2/36873/I |
| 7 | 9→2/4680/C; 10→2/4680/X |
| 8 | 11→2/4680/Y; 12→2/4680/I |
| 9 | 13→2/576/Y; 14→2/576/I |
| 10 | 15→1/0/Y; 16→1/0/I |
| 11 | 17→1/32769/I |
| 12 | 18→2/36873/I |
| 13 | 19→2/4680/Y; 20→2/4680/I |
| 14 | 21→3/0/Y; 22→3/0/I |
| 15 | 23→3/32769/I |

固定 RHS 的 solve gain 范围为 q1=649.1236..876.3024、q2=458.5952..529.3610，
solution max-abs 范围为 97.70889..151.4110，16 个 factor 全部 finite。该诊断没有发现
factor_id/class_id、cell row ordering、orientation 或 expansion pattern 的错绑；R2 loader 和
checker 已逐 class 绑定 class/constraint/expansion SHA，smoother 只按 class 解析对应 factor。

代码路径也保持单一语义：Cᴴ B_c C 只在代表性 transformed-block 构造处计算一次；smoother
local RHS 直接为 residual[独立行]，没有再乘 Cᴴ；每个 cell solve 后只除一次 multiplicity，
每个 color 只调用一次 exact action。

## 根因、hard stop 与证据

结论为 **C：primary fixed-unit colored smoother 的 genuine algorithm failure**。更精确地说，
单个 factor 的离线 solve 是 finite 且没有 1e24 级单因子放大；但全局 8-color forward/reverse
固定 unit-step composition 在真实 B0 上发散，导致五类 rho 均远超 Gate。它不是 action/JIT/
resource/PDE 失败，也不能写成 factor/smoother PASS。

所有 rho > 1.20，因此 Review V8 的 face-pair fallback 条件不满足；本阶段 hard stop。H2C、
H2D、H4、PDE、KSP、DtN、field、RTA 和 direct-method comparison 均未运行。

## Evidence 与复现

正式 attempt2 raw：[h2b_primary_b6b83b3_run2](../../../benchmarks/artifacts/task037_extra_development/h2b_primary_b6b83b3_run2)；canonical compact：[h2b_block_smoother.json](../../../benchmarks/cases/101_task37_extra_development/records/h2b_block_smoother.json)。

| evidence | SHA256 |
|---|---|
| compact file | e95d39a52321f5d3a568d54912dc74ee0893cd5fc82a4c4dac1fb8dc3fcc9d7c |
| compact embedded evidence | f7248727afed040d28e3a263377f2318c21bc420d571841b9d5a277d089062c6 |
| h2b watchdog summary | 179fabc904c08201324debd0cac027e2eeb7cfbe94a65d491e7f775f5ac2bd6b |
| stage summary | baf004d0e51cd96aa2e075d9baa9b7cb53e152c9505cb8ac16219bc6ca544c4c |
| online summary | 4202b3f15f181251e1be42528fc751e3bd1fc4953e882b2cfaed05596804efa5 |
| stage timeline | 30e12c65fdfc768e7d78dc2dfa2008603e33f758f7d60160d4c166bf7477f542 |
| online timeline | 7bb92ce9cd90d08b3f0b33d930db3d502df41006438c66371d34de2e7913232c |

Attempt2 的完整 raw 文件 SHA 已由 compact raw_artifacts 闭包保存；raw 为 ignored，不提交 Git。

合同复现命令：

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

本次 evidence 收口另对同一 raw 执行了一次 lightweight checker，RC=1；输出与保存的 attempt2
compact byte-identical，没有启动 worker/heavy。

## 未运行与后续边界

H2B primary 的 resource/lifecycle 通过不能抵消 source contraction Gate 失败。由于 rho>1.20
且 V8 禁止 fallback，本轮不再使用第三次 formal 预算。H2C/H2D/H4/PDE/DtN/KSP/RTA 不得由本记录
推断为通过；继续工作必须等待新的 Review 授权。
