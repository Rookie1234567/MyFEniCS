# 可消费的[0,1]面积分组件候选

本包替换既有 `FacetPolynomial.integral` 的两个一维振动积分，保留原面系数收缩、Piola面积、方向、参考点相位和端口H。本轮解析与原q60都通过局部精度，解析未带来20%完整成本优势，**推荐继续已有q60**。补丁仅供接收方按自己合同选择性验收，不改其默认或工作树。

冻结接收方为Task042 `31774b6282f61280fe33c162f9f48bf4ea526ce6` 中的 `FacetPolynomial`；示例加载该类而不加载整个runner/owner/layout。`receiver_opt_in.patch`只增加显式可选委托，未选择时原方法逐行保留。最小函数、物理范围和依赖见[manifest](../../../docs/task042extra_feinn_5nm/outcomes/records/minimal_integration_v23.json)。

已真实运行的消费路径：

```bash
source scripts/activate_task42extra.sh pure
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v23_facet_qualification.dat
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v23_analytic_cold.dat
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v23_q60_cold.dat
```

以上为冻结的复现命令，**本worktree已有closed index，不再重复启动**；loader会拒绝重放同一stage。本轮输入/ABI/receiver、真实冷过程和源提交见[run index](../../../docs/task042extra_feinn_5nm/outcomes/records/run_index_v23.json)。接收方使用已有poly实例时只需调用：

```python
from benchmarks.facet_receiver_example import consume

# polynomial/k/J/origin及expected来自调用者已核hash的冻结packet；
# expected绑定side、degree、系数与k/J/origin字节，不能从未知输入自证PASS。
local = consume(polynomial, side, k, J, origin,
                implementation="analytic", expected=expected)
```

`consume`已在同组24 case × p4/p6正式过程调用；每p有三条非零复方向和非零端口载荷。它返回全部本地原生基列的切向积分，输入不得附带不同方向、长度或复切向频率。调用者继续使用自己的traction、原H和完整owner/MPC，不能把示例局部资格当全目标资格。

不需要native环境的定向fixture命令：

```bash
source scripts/activate_task42extra.sh pure
python -m pytest -q src/test/test_interval_facet_moments.py src/test/test_portable_facet_oracle.py src/test/test_strict_port_admission.py
```

实际47项最终测试、独立Decimal积分及损坏记录测试已完成。没有全32060-key计算、FE/Maxwell矩阵或solve；原尺寸材料/网格/模式/权限不能从另一任务继承。[结果和分母](../../../docs/task042extra_feinn_5nm/outcomes/portable_facet_component_v23.md)、[同精度完整成本](../../../docs/task042extra_feinn_5nm/outcomes/records/local_cold_comparison_v23.json)。
