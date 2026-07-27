# Task000 p6/h10 本地可行性

## 结论

`blocked`。Task000 未启动 p6/h10 PDE，未依赖 OOM kill，也未把 40 GiB
swap 当作可用内存。阻断来自启动前的 source/resource Gate。

## 权威 case 与身份

- 权威 case：`benchmarks/cases/096_hybrid_channel_memory_closure`
- 固定模型：Task034 rectangular block grating，13.5 nm，80 degree，S polarization
- 固定离散：structured hexahedral p6/h10，252 cells
- 正式历史 ranks：MPI8
- 历史六路 source SHA：`244b62e1fb4f299a468363cf90a2dd548dc34ff6`
- 当前 Task000 base HEAD：`5f43fb1ca01be2e323e5573b337d4ea0fca2164f`
- 当前工作树：Task000 实施中、dirty；不能生成 formal sample
- compact authority：
  `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json`
- frozen significant-channel reference：Case095/Case096 tracked records

权威 Full3D 入口由 `benchmarks.run_task033_full3d_watchdog` 的
`--degree 6 --h-nm 10 --task035c-p6-h10-gate` 路径保护；Hybrid 入口由
`benchmarks.run_task032_phase6_augmented` 的同名显式 Gate 保护。未提供该 Gate、
source dirty、身份偏离或 reference hash 不符时都 fail closed。

## 历史资源证据

| p6/h10 路径 | rows | matrix NNZ | 历史峰值 GiB | 历史总时间 s |
|---|---:|---:|---:|---:|
| Full3D standard | 173,882 | 210,353,168 | 34.041 | 2,581.55 |
| Full3D static | 51,272 | 41,989,040 | 14.722 | 260.74 |
| Hybrid standard M120 | 52,292 | 60,434,236 | 11.077 | 942.03 |
| Hybrid static M120 | 17,168 | 12,313,232 | 7.544 | 322.78 |
| Hybrid standard M160 | 52,372 | 60,434,236 | 11.247 | 1,014.71 |
| Hybrid static M160 | 17,248 | 12,313,232 | 7.929 | 393.84 |

当前 WSL 的总内存为 14,654,963,712 bytes（13.65 GiB），预检时可用
13,805,522,944 bytes（12.86 GiB）。Full3D static 的历史 14.722 GiB 已超过
WSL 总内存，Full3D standard 更远超预算。历史 static Hybrid 虽在纯容量上较小，
但它不是当前 v1 thin forward schema 的 Full3D runner，且正式证据绑定另一 source
SHA；不能把它偷换成当前正式样本。

## Gate 结果

| Gate | 结果 | 说明 |
|---|---|---|
| environment/complex ABI | PASS | M3 serial/MPI2、MUMPS、PEP、FFCx 均通过 |
| authoritative case identified | PASS | Case096 p6/h10 six-path authority |
| compact record hashes/contracts | PASS | Case095 19/19 hashes；Case096/runner tests 21/21 |
| exact current source match | FAIL | historical `244b62e...` != current `5f43fb1...` |
| clean source | FAIL | Task000 changes尚未提交 |
| Full3D safe-memory probability | FAIL | 14.722 GiB minimum authority > 13.65 GiB WSL total |
| swap policy | PASS (not launched) | 40 GiB swap remained unused; swap completion is forbidden |
| launch decision | BLOCKED | no mesh/assembly/factorization/solve started |

## Development smoke used for local scaling context

The single 13.5 nm 2D complex-absorption development smoke passed with:

- 1,785 cells; 14,452 Nedelec DoF; 14,482 rows; 247,181 NNZ;
- true residual `2.977956804883729e-14`;
- authoritative auxiliary-DtN `R/T/A = 3.6625211715e-6 /
  0.882172452104589 / 0.11782388537423949`;
- `A_volume = 0.11782388537423974`;
- solver elapsed 2.065 s; end-to-end wall 4.41 s;
- maximum RSS 341,716 KiB (333.7 MiB); swaps 0.

This smoke validates the local entry and Gate mechanics only. Its scale is far too small to
override measured p6/h10 memory authority.

## Controlled-stop policy if revisited

A later task may revisit p6/h10 only after producing a clean exact-source reference and a
model-specific memory plan. It must use one forward process, one thread per rank, a watchdog
with readable process-tree RSS/PSS/USS/swap, and pre-factorization termination below the WSL
safe ceiling. OOM kill or swap-heavy completion is not an acceptable outcome.
