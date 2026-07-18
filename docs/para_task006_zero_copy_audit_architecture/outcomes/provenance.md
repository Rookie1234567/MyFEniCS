# Task006 provenance

## P0 repository identity

| 项目 | 值 |
|---|---|
| branch | `ChatGPT/20260715-para-task-neural-local-pc` |
| entry HEAD | `7f9c5774dc5e5ddacd3337d48eb690cc19308606` |
| remote | `origin = https://github.com/Rookie1234567/MyFEniCS.git` |
| dirty status at entry | clean |
| branch/pull/push/merge | 均未执行 |
| Task005 Review V1 | 已读并由 `response_v1.md` 接受/修正 |
| H identity | consumed screening split |
| V identity | 未用于 Task005 candidate selection |

## P0 clean validation identity

| 项目 | 值 |
|---|---|
| clean SHA | `9822bc5d84375bf1cd3039aec7ca1e849413c0ed` |
| tracked source dirty | false |
| WSL kernel | `6.18.33.2-microsoft-standard-WSL2` |
| complex Python | 3.12.3 |
| NumPy | 1.26.4 |
| formal baseline | h5 / MPI4 / one thread per rank |
| partition policy | contiguous research policy |
| complete tests | 209 passed, 12 skipped |
| diff check | PASS |
| Case095 artifact ignore | PASS，`.gitignore:58` |

## 冻结 R4 checkpoint 与 dataset identity

候选固定为 Task005 `A_D0_R64`，没有 retraining。

| slab | weights SHA-256 | operator fingerprint | samples SHA-256 |
|---:|---|---|---|
| 0 | `6c150ff3e6ed4ac6bd0a16ce206e8f1fe364cb0d7c02020e77f4fa3854224a03` | `1902aca501c27d2884e6f5d35105c77f3125d4b4d422087fdb7cb9282cb017db` | `e5a1bd93352c0c087952ea8efd800e597353736da833e8514b4a1d28eaa63347` |
| 5 | `b8375337d8373b2a10d05829602a89a340911be4dbe43b702ffb7afbf7e52fa7` | `55b799f1d4e20e64addcf41c6bdf0d576746dac2fa37efcc11d29d79602d055e` | `0742e556520d08ac810f0d4e4397598b129a2c39245763ec38914367e172b012` |
| 9 | `7597bffae0f761663e7503e89b55f443a5e2665dc10eeab414ae735ccb0970a8` | `0fe7e9f597345f6a10bd924ebc43e15198815e151654173c0659d7dbf0306784` | `1d0796d5aabf492a4df2e3f48d4123ae7bd7ecef5fe7e1a61f7eaef99031ce4c` |
| 15 | `9a8091bae6a2e60655f1cce55719b1c6e924694f9fed0a7fea2b58ae722de6f5` | `47a3c63845d6110f196d3829ad11570774c6b97784d88ef3b5da57734127b883` | `9eb0f767ba64177dbd3a9fd422b730d0a4c0e983b8fe1a1e5af0f80598fd0a38` |

每个实测 weights SHA 与 checkpoint manifest 中的 `weights_sha256` 一致；每个
manifest 的 operator fingerprint 与对应 teacher dataset 一致。heavy artifacts
位于 `benchmarks/artifacts/cases/094/`，只读复用并保持 Git ignored。

## P1 implementation identity

| 项目 | 值 |
|---|---|
| clean implementation SHA | `0b20f2554a9cc0526efa893f941174fb81918472` |
| formal run | h5 / MPI4 / 16 slabs / 64 probes |
| reference | Task005 captured CSR，逐 slab ephemeral load/release |
| output | `benchmarks/artifacts/cases/095/p1_borrowed_0b20f25/` |
| full tests | 212 passed, 12 skipped |
| branch operations | 无 |

## P2 Q0 calibration identity

| 项目 | 值 |
|---|---|
| clean implementation SHA | `ac039bd` |
| corpus accessed | Q0 = Task005 V only |
| forbidden Q1-Q5 access | none |
| model | frozen `A_D0_R64`，no retraining |
| ILU reference | PETSc complex128，ILU(0)+RCM，256 V samples/slab |
| q | 64 / 128 / 256 / 512 / 1024 / 2048 |
| seeds | one and two deterministic procedural seeds |
| selected/locked certificate | none |
| heavy result | `benchmarks/artifacts/cases/095/q0/proxy_calibration_ac039bd/` |

P2 worker 以无 usable family 的预期非零退出码结束，并完整保存
`calibration.json`；这表示 Gate failure，不是崩溃或卡住。
