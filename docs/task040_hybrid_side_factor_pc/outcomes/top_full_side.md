# T40-9 top full side

## Status: not_run_by_gate

T40-9 的 top route 依赖 bottom 路线资格，且只能在前置 Gate 通过后执行。由于 T40-3
mandatory rho、worst rho 和 preferred rho 均失败，top bare-F/full-side 没有运行；没有
top factor、residual、RSS、wall 或 swap 结论。

## V1-8 收口

Top full-side 为 `not_run_by_gate`。V1-2 硬停止后没有创建 top factor、residual、physical
output 或资源测点；最新峰值不能作为 top 或完整 workflow 的测量。

## V2-G 收口

V2-E top full-side 为 `not_run_by_gate`。V2-B2 projected-transmission 数值负结果触发
停止，未创建 top factor，也未运行 top/full workflow 测量。
