# V71有界两层接口迭代：实际准备与容量否决

把已经保存的单元响应变成可重复调用的作用，可避免每次重新读取映射；随后用重叠小区域与一个有上限的粗空间准备迭代加速器。本轮完成了这两步的真实数据准备和独立审核，但**全部因子的预计驻留总和超限，未启动完整迭代**。局部组件通过不代替新0.7nm物理解。

| 模型 / 方法 | 实际数据与资格 | 费用 / 具体边界 |
|---|---|---|
| O，25576tet/p5/828原局部包热作用 | FE/port差最大5.21847e-16/6.43620e-17；非零内部/port恢复与原恒等式1.46527e-14 | 首次71.80037s，三热作用1.22402/1.23099/1.31844s；不是完整求解速度 |
| P，4×2×4 core与一层周期halo | 因行门分成38块，最大68680行；唯一core写回；局部合计374068350存储项 | local双倍symbolic79520000000B；不形成全局细层K/S |
| p2 trace Galerkin＋全部828端口 | 实际7068行，稀疏Z23529162项；两完整作用差1.46468e-15/1.49729e-15 | 粗层802000000B；粗装配2856.99821s嵌套于P |
| 合计容量门 | **80322000000B＝74.8056918383GiB > 64GiB** | 数值factor local/coarse/fine均0，PC实际apply与正式FGMRES未运行 |
| 独立VERIFY | 46包、所有38CSR、原随机RHS、owner、Z/E0/INFOG及复对偶复算一致 | 整体pass_gate=false；不是返回场审核PASS |
| 新完整方程、六场、240点、828功率/吸收/能量 | **NOT_RUN_CAPACITY_BLOCKED** | 无候选，不发布official RTA，不读取旧场评分 |

原尺度s=7/135、λ0.7nm真实NOTCH、canonical材料/入射/κ、全部Cκ、双周期未变。完整FE1943745/内部767280/retained1177293；新增作用仍有父局部内部LU，不能称factor-free或distributed。旧V70完整解/strict direct FAIL和空间精度FAIL保持，未授连续/原尺寸/2TB48h/NN20。

| 完整分段 / 资源 | measured |
|---|---:|
| O / P / VERIFY one-run wall | 219.764406361 / 3392.80855081 / 207.839279009s |
| 累计原action / 计数上下界 | 8 / [8,8]，无未返回调用 |
| 全批当前采样树峰 | 9444700160B＝8.79606246948GiB |
| 实际最大gap / ownswap / OOC | 1.60104868095s / 0 / 0；不是连续硬峰 |
| 完整新T_N1 / 配平生产比 | NOT_RUN / unknown |

全部输入都先实现、9项定点回归/相关compile与Ruff/4个dat validate后clean提交；ordinary默认不变，无full pytest或历史PDE重放。原窗口首次00:37:53.636300Z冻结，14h/12h/末1h不刷新；在固定PC容量拒绝且可执行队列结束后收口，不为跑满窗口改PC。全部失败、元数据修复和监督费用单独保留。

唯一下一pilot为新合同下总symbolic约束的事前几何二分（至多64块）并复用已资格Z/E0，达到原64GiB门后才作同一FGMRES；本轮未执行。不能把本轮8.8GiB设置峰与V70完整LU的111.3GiB峰直接当相同正确性内存收益。

[完整回应](../response_v71.md) · [真实执行/source](records/run_index_v71.json) · [组件作用](records/hot_operator_qualification_v71.json) · [全部局部/粗层](records/bounded_pc_inventory_v71.json) · [独立checker](records/scientific_checks_v71.json) · [完整成本与未知](records/resource_costs_final_v71.json) · [retained接口合同](records/retained_iterative_contract_v71.json) · [raw/source增量](records/raw_archive_index_v71.json) · [merge依赖组](records/selective_merge_manifest_v71.json)。GitHub视觉NOT_VERIFIED；CI NOT_RUN。
