# T40-5 bottom bare-F scalable PC

## Status: not_run_by_gate

T40-5 需要先有通过 T40-4 的 bounded patch core，再构造 bottom bare-F PC 并进行 one-apply
Gate。由于 T40-3 `TRANSMISSION_MECHANISM_FAIL`，本阶段未运行；没有 bottom scalable PC
residual、factor cap、FGMRES checkpoint、RSS、wall 或 swap 数值。

不能据此判断 bottom bare-F 的所有 iterative side inverse 都不可行。
