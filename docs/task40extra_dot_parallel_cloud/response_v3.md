# Response V3：完整三维参考逆架构的有界实测

真实小型三维FFCx/MPC Maxwell系统保留全部2048独立DoF（含480 cell interiors）、4个y块和532真实DtN aliases。规则x-z异质光栅A0的完整参考逆通过；同一网格的2-cell三维缺口由原A FGMRES求解，generic all-q /真实incident分别4/3步，full true residual5.2744e-15/5.8469e-13，与完整direct场差9.4051e-14/5.0376e-13。真实incident在notch中产生1.4217e-5非零q相对场分量，独立checker重算通过。

这是缩放7/135、p2、phi0的full3D代数架构资格，不是原尺寸50×25×140nm目标解、物理精度或2TB/48h证明。没有二维/2.5D替换、n0 projection、材料平均、端口别名合并或production默认变化。全4块dense payload16,785,408B对67,117,056B full dense oracle的比例不能用于推算MUMPS目标fill。

成功source18d7d0a27f73705366f8cb747c11cb9e68cc0ef6。attempt2 whole-tree RSS638,885,888B、8.839s、swap0、后代清场；warm JIT。attempt1 API失败及695,042,048B/20.437s原证据保留。最终独立checker12 residual/direct检查+all-q/aliases/nonzero-q及targeted3 tests通过；full pytest/MPI2+/Ruff/CI/GitHub rendered view未运行。非零y Bloch、p4/p6、可扩展单cellblock生成与target尺度都待独立资格。

[完整结果/数学/历史区别/容量边界](outcomes/y_orbit_full3d_pilot_v1.md)；[compact](outcomes/records/y_orbit_full3d_pilot_v1.json)；[复现](../../benchmarks/cases/task40extra_dot_parallel_cloud/y_orbit_reference/README.md)。仅本独占分支本地提交，远端等价发布由协调方管理；无raw git push/PR/merge。后续先提交phi5和真实p4有界实验计划，不自动继续计算。
