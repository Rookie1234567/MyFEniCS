# Gate-CD 精确单元张量并行与端口断点缓存

## 范围与运行隔离

用户授权在后续计算中使用 4/8/16/32 个空闲物理核，先做小网格串并行对照，同时测量时间和内存。实现位于独立 worktree `task40_gate_cd_parallel_exec`，从 `fab43f513f1696ed161e1fcbf43a9018ad54b4db` 派生。当前 Gate-CD a5、N32、N14 的源码、进程、CPU 绑定和运行配置均未修改。本轮是局部计算和小网格装配验证，没有新增完整场求解、全局分解或 R/T/A 结果。

| 功能 | 实现与边界 |
|---|---|
| 多核计算 | 一个独立 Python 进程计算一种精确单元类别的原始复数张量。父进程仍按既有顺序做方向变换、局部 Schur 消元、MPC 与 PETSc 插入；不是多进程同时修改同一全局矩阵 |
| 不改变精度 | 保持 P6、q21/default、complex128、原有材料项加法顺序和完整 float64 几何键；不做坐标舍入、材料合并、降阶或降低积分阶数 |
| 单元缓存 | 每类 `.npy` 加 SHA256 完成记录；原子写入、每键锁、损坏拒绝、半写入不命中。父进程只读映射；不是持久化全局 MUMPS 因子 |
| 端口缓存 | q81 四组稀疏数组和归一化分母按模态落盘；恢复连续完成前缀，余下模态继续组装。独立 namespace，不放宽旧 q160 provider 的资格条件 |
| 缓存身份 | 单元绑定编译库 SHA、完整几何、材料 tag、算子/元/积分信息；端口绑定实际 mesh/DoF/MPC/边界、材料入射、模式清单、q、cutoff、源码与数值扩展 ABI |
| 准入 | 额外选择空闲且不同物理核，排除邻任务核及其 SMT 兄弟；64 GiB available floor，PSS 关闭，无固定 RSS cap。仍须正常 case 审阅与 fresh，附加合同不代替它们 |

这里的“落盘复用”是以后相同数值身份的计算直接读回已完成的积分结果。几何、材料、模式、积分或数值源码身份变化会拒绝相应命中，不能把不同网格的端口数组直接搬过去。启动合同仍绑定完整 Git commit；缓存另对生产 `src/**/*.py`（不含测试）取内容指纹，因此仅提交新输入或文档不会无故使所有单元缓存失效。局部单元键逐类检查，新网格中完全相同的类别才可复用；端口缓存采用完整 mesh/DoF/MPC 身份，更保守。当前 a5 没有这个新导出钩子，不从正在运行的进程提取内存，也不为启用新缓存而重启它。

## 对照设计

1. 八个实际 swept Q1 hex，P6 N1curl、非零 x/y Floquet 相位、复数有损 curl+mass、q21。串行和新路径比较凝聚矩阵、非零 RHS、随机非零 trace 下的内部场恢复，门为相对误差 `2e-10`。不做全局 factor/solve。
2. 从实际 Gate-CD 的 808 个精确 raw 类中均匀抽取 32 个不同几何/材料类。4/8/16/32 档各使用空缓存，所有张量逐字节比较。四核批次是这 32 类的完整字节参考；独立串行等价性由八单元测试和此前两个真实类别的串行/双核验证提供。不能把四核批次称为串行基线。
3. P6/q81 实际 surface assemblers + MPC：完整构建作为参考，在两个模态完成后模拟中断，再恢复完成四模态；随后禁止调用实际 assembler，检查全部缓存命中仍能完成。
4. 时间按阶段记录；内存使用同一瞬间 supervisor 与全部子进程的 RSS 总和，不能相加各 worker 的历史峰值。RSS 可能重复计入共享映射，PSS 未采。短于采样间隔的阶段标 `NOT_SAMPLED`。

本轮并行的是原始单元张量积分，局部消元和全局 MUMPS 并行不在此实现内。整个模型的提速不能直接等于该积分阶段的提速。八单元测试可并发的类别不足32，其后续8/16/32档命中相同缓存，只验证接线；实际冷缓存扩展性由32类测试单独给出。

## 实测记录

最终表由保存的 benchmark report 与 watchdog 时间区间重算，收口前不填写预测值。

| 并行进程 / 物理核 | 32类冷计算 / s | 相对四核加速 | 冷计算整树RSS峰 / GB | 全缓存命中 / s |
|---:|---:|---:|---:|---:|
| 4 | 1444.49 | 1.00× | 0.738 | 0.606 |
| 8 | 729.28 | 1.98× | 1.417 | 0.477 |
| 16 | 368.03 | 3.92× | 2.754 | 0.407 |
| 32 | 199.81 | 7.23× | 5.388 | 0.362 |

全部32个张量在四个档位逐字节相同；各档实际最大活跃 exec worker 数分别为4/8/16/32，所有采样任务swap为0。这里的GB为十进制10⁹ B；这是32个真实类别的局部积分批次，不是整个Gate-CD模型的耗时或峰值。七个材料tag被抽到：101/102/103/104/105/110/123。

八单元P6/q21的串行构建为1573.50 s，四核冷构建371.17 s（4.24×）；凝聚矩阵、非零RHS、内部场恢复的相对差均为0。后续8/16/32配置使用同一已填充缓存，分别为2.67/2.68/2.66 s，不能称为冷并行扩展性。该测试含JIT的完整工作流采样树RSS峰为2.883 GB；串行构建区间约0.801 GB、四核冷构建区间约1.476 GB。区间内存通过watchdog elapsed与初始新鲜monotonic样本对齐，不能把5秒缓存的NUMA时间戳当作每条资源采样时间。

P6/q81端口测试：4模态，中断并保留前2个后恢复，全部稀疏数组和H逐字节一致；再次全部命中时实际surface assembler调用数为0。初次含FFCx编译的树RSS峰为5.586 GB；已有编译缓存的单独四项live复测树峰约0.492 GB，任务swap为0。

建议在fresh确有足够空闲物理核时使用32核处理这类原始张量；本批次从16到32核仍有1.84×收益，新增测试树RSS约2.63 GB。若空闲核不足则选择8或16核。这个建议只适用于已测积分阶段，全局矩阵、局部Schur和MUMPS仍可能占主要时间/内存，不能用5.39 GB代替正式场容量检查。

机器可读结果、各阶段资源口径、源码/数值AST绑定、产物SHA及原路径见 [compact证据](records/exact_parallel_cache_20261102.json)。


## 后续使用

`p6_condensed_direct` 仅在精确 Gate-CD route 且显式提供 hash-bound 合同时启用新路径，默认行为保持原样。新计算仍须使用审核过的 clean source、完整 case fresh 和自己的 watchdog。以下命令仅生成附加执行合同，不启动 FE；`resolved.json` 必须是该次运行将传入 runner 的完整 resolved payload。

```bash
source scripts/activate_task40_phi90_pord64.sh
python -m benchmarks.prepare_exact_cache_contract \
  --resolved-json /absolute/reviewed/resolved.json \
  --workers 8 --exclude-cpus <当前活动任务及监督CPU列表> \
  --tensor-root /absolute/cache/tensors \
  --carrier-root /absolute/cache/carrier \
  --output /absolute/reviewed/exact-cache.json
```

将输出的绝对路径与 SHA256 作为本次冻结服务环境中的 `TASK40_EXACT_CACHE_CONTRACT` 和 `TASK40_EXACT_CACHE_CONTRACT_SHA256`。fresh 时再次确认核与内存，不能长期复用过时的 CPU 采样。源码/输入/环境变动需要重新绑定。已经通过的缓存身份仍完整验证，不因选择更多 CPU 省略校验。

## 证据和失败记录

大型缓存、矩阵和 watchdog 流均保留于 ignored `tmp/`，不提交 Git；compact 汇总和 SHA 索引进入本目录 `records/`。P2 pilot 的 degree 元数据与坐标 shape 接线失败、第一次 P6 watchdog PSS 枚举错误均保留，修正后局部重测。旧 `test_task39extra_p3_surface_vector_workspace.py` 的五个 fake-context 失败，在未修改的 `fab43f51` worktree 中复现相同失败，不改写为本实现通过。

仍保留 `FULL_DTN_NOT_VERIFIED`。小网格装配等价和缓存字节一致不等于新的完整 Gate-CD 物理资格，也不消除有限模态或网格离散误差。

## 依赖与合入顺序

| 分组 | 内容 | 性质 |
|---|---|---|
| reusable core | parallel_tensor_cache、raw_tensor_execution、carrier_checkpoint 与三个 builder 接线 | 显式 opt-in；默认关闭 |
| runner | exact_cache_contract/admission、p6 direct 接线 | hash-bound 附加合同，保留正常 fresh |
| validation | 两种局部基准、carrier 实测、资源汇总、回归测试 | 研究/验证，不新增物理 case |
| compact docs | 本记录、JSON 汇总、模型总账/summary 链接 | 证据入口 |
| 不合入 | ignored 编译缓存、张量 payload、watchdog 全流、原运行目录 | 主机本地保留 |

最终冻结前聚焦回归 **46 passed / 3.97 s**，包括缓存正负例、真实Gate-CD loader绑定、P6/q81中断恢复及四项原凝聚装配/恢复/MPC/预分配锚点。专属watchdog自然exit0并清场，树RSS峰481,185,792 B、任务swap0。全仓库pytest未运行；上述原分支已存在的5个fake-context失败单独保留。
