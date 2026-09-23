# Response V27：V26 setup-efficiency 收口

## 首屏结论

V26 本轮正式运行已经完成并通过离散求解与保存输出一致性检查：126 步，最终显式真残差 `9.283164976754267e-7`。它没有匹配的独立 h7.5 reference，故结论是 `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`。

执行端曾尝试启动一次相同 profile 的 service，但没有真正开始：共享账本的一次 replay 已耗尽，service 在 worker 前返回 `Task38 input error`。因此没有新的残差，也没有把这次 gate rejection 写成第二个正式数值结果。该失败历史单列，不改变正式结果。

本批启动历史完整保留：`000330` 因缺 `--physical-pc-profile` 被预启动拒绝，`001329` 因缺 hash-bound replay evidence 被预启动拒绝；随后 source `973c0c3...` 的 `000422` worker 在 outer-route guard 处失败，实测 `64.91704543396747 s`，错误为 `only retained-space original stages use the outer adapter`；修复后才有本轮 `001753` 的 126 步正式结果。账本最终是 `2` 个 fresh workers、`1` 次 unique bug replay；完整 log/hash 索引见 [relaunch history](outcomes/records/setup_efficiency_v26_relaunch_gate_rejection_20260923T014131.json)。

## 对 review 六项的回答

### 1. 重复工作减少了什么，成本是否被证明

本轮实际测到的四项 setup 优化是：不生成 sum-factorization 不消费的完整参考表；直接构建选定的 H6 后端；在 curl/mass action 间共享只读 geometry/reference bundle（材料数据不共享）；按真实局部类型复用并批量处理 H6 对角。990-cell 配对的 diagonal setup 为 `45.07978344000003 → 4.169365248999384 s`，H6 setup 为 `84.68341056300414 → 43.2881181279954 s`；A6 physical median 为 `6.215509254499921 → 5.547621760000766 s`，operator 等价相对差均通过门槛。p6 仍使用局部 action-only 凝聚，避免完整全局 p6 矩阵；p4 使用凝聚矩阵生命周期并保留结构 map。

这些组件记录来自 [raw component pair](outcomes/records/setup_efficiency_v26_components.json) 绑定的原始/rechecked JSON，并明确 optional projection reuse 未采用。正式记录还显示 p6 retained build、p4 condensation、H6、matrix、power 和 MUMPS factor 的阶段耗时。

这些字段说明计算流程的对象和阶段发生了什么，但没有针对每个删除项的 matched component baseline。因此不能把 `259.0239490659951 s` 等阶段差直接写成某项优化的因果收益；最终端到端结果反而比 r2 慢。

### 2. 与 r2 的完整 p6/h7.5 对比

两场都是同一 990-cell、126 步、MPI1/thread1、80 modes 的完成运行，残差轨迹和最终结果在浮点误差范围内一致。V26 相对 r2：

| 口径 | V26 | r2 | V26 相对变化 |
|---|---:|---:|---:|
| full workflow 单调时间 | 3595.9571450339936 s | 3114.283619607013 s | +481.67352542698063 s，+15.46659149457179% |
| KSP phase | 2716.518828 s | 2284.681783819 s | +431.83704418100024 s，+18.90140881935669% |
| setup 单调时间 | 823.0868099959989 s | 781.971881371981 s | +41.11492862401792 s，+5.257852565220267% |
| process-tree RSS authority / worker PSS | 7381557248 / 7346483200 B | 7390937088 / 7354803200 B | V26 略低，PSS保留各自worker scope，非一般性证明 |

所以不能称 V26 加速；r2 是速度基线。

### 3. A6、full field、mode、power regression

已保存输出的独立 checker 全部通过：80/80 通道、场 finite、modal power、能量闭合和 official output identity 均通过；same-discrete FE field 的 L2/scaled-curl 也通过。最大 selected-field 相对差为 `1.49476327946998e-13`，power 最大绝对差为 `1.1657341758564144e-14`，均远低于记录限值。

这证明 V26 与 r2 的保存离散结果一致，不提供连续极限收敛或独立 high-precision reference 证明；authority limitation 保持。

### 4. 资源、swap、温度、cache 和 MUMPS

正式 `run_summary.resource_authority` 的同时 process-tree RSS 为 `7381557248 B`、swap `0 B`、13247 样本；PSS `7346483200 B` 来自 worker-emitted process-tree PSS 记录，保留其 1176 样本 scope，不与 RSS authority 混称。r2 的对应 process-tree RSS authority 为 `7390937088 B`，PSS 为 `7354803200 B`。MUMPS `INFOG(19)/INFOG(22)=4687/4326 MB`。温度没有合格记录，写 `unknown`。

V26 的跨场 numeric cache 是 build，load `0`，numeric factor 未跨场复用；本场 267 次 p4 回代使用同一已构建 factor，不能把“跨场未复用”误读成“本场每次都重新 factor”。仅 structural maps 和 prepared form 被复用。

旧 wrapper 的 strict zero-swap 字段与 worker 的 observe-only 字段不一致，原始事实保留。observe-only source 修复已经提交并由 targeted mock 覆盖，但没有用修复 source 再跑 PDE，不能把它冒充为新的 formal qualification。

### 5. T5 local disk cache

T5 `DEFERRED`。当前没有经 schema/identity 绑定的 numeric packet loader；如果补做，需要新平台范围。离线加载验证本身不消耗 PDE 配额，但本 closeout 没有合格 loader/packet，因此没有 cache-load 证据。不得从 JIT reuse、结构 map reuse 或单场计时推断 local numeric cache 收益。

### 6. 最终裁决

r2 继续作为速度 baseline。V26 只保留为显式 opt-in/review-only 的 setup-efficiency profile；不改 ordinary default，不宣称端到端提速，不继续消耗 PDE 额度，也没有 master merge approval。

## 证据入口

- [V26 outcome](outcomes/setup_efficiency_v26.md)
- [V26 compact](outcomes/records/setup_efficiency_v26_compact.json)
- [V26 decision](outcomes/records/setup_efficiency_v26_decision.json)
- [V26 components](outcomes/records/setup_efficiency_v26_components.json)
- [V26 cold build](outcomes/records/setup_efficiency_v26_cold_build.json)
- [V26 cache decision](outcomes/records/setup_efficiency_v26_cache_reuse.json)
- [保存场 FE regression](outcomes/records/setup_efficiency_v26_r2_field_regression.json)
- [通道/功率 regression](outcomes/records/setup_efficiency_v26_r2_power_regression.json)
- [动态 raw p4 checker](outcomes/records/setup_efficiency_v26_dynamic_checker.json)
- [重启前 worker gate rejection](outcomes/records/setup_efficiency_v26_relaunch_gate_rejection_20260923T014131.json)

本轮新启动没有 16 步残差表；上文表格中的 16 步、112 步和终点数据全部来自已有 V26 正式运行记录。
