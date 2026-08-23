# T40-10 both-side setup

## Status: not_run_by_gate

T40-10 原计划只做 bottom/top 两侧 setup，不做完整 solve。它仍要求前置传输机制和两侧
side route 通过；T40-3 失败后按顺序停止，因此没有 both-side factor inventory、资源或
生命周期测量。

## V1-8 收口

Both-side setup 为 `not_run_by_gate`。V1-2 硬停止发生在依赖它的 projected screen 之前，
因此没有 two-side factor inventory、资源或生命周期测量。

## V2-G 收口

V2-E both-side setup 为 `not_run_by_gate`。V2-B2 数值 Gate 未通过，未进入两侧 setup，
没有新的 factor、资源或生命周期结果。
