# V5 v2：局部线性代数诊断受控停止

## 结论

用户补充授权了一次 fresh V5 v2 LA0/LA1 formal attempt。第一次启动层 lifecycle stop 和旧 N2 v1 negative 均保持不变；本次不修 marker、不重跑，也不进入 LA2。

本次 formal 的最终分类是：

```text
CONTROLLED_STOP_LA1_MARKER_REGISTRATION / NOT_QUALIFIED
```

worker 已经抓到与旧 N2 v1 相同的第一个失败 exact class，并独立完成了 LA1 数值诊断；但 worker 在写 `linear_algebra_diagnostic` marker 时触发 `ValueError: unknown N2 marker: linear_algebra_diagnostic`，因此 worker/checker 均为 `rc=1`。这属于 runner lifecycle/marker registration 缺陷，不是把 LA1 数值结果冒充 formal PASS 的理由。

## formal 身份与实际命令

| 项目 | 实际值 |
|---|---|
| lifecycle ownership 修复 commit | `ae599854d08fcd16e3f1d204017bc4bc04482bbf` |
| formal source SHA | `ae599854d08fcd16e3f1d204017bc4bc04482bbf` |
| case | p6/h10 MPI1 |
| ABI | qualified WSL/Linux；complex128/int32；MPI1；threads=1 |
| case root | `benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/` |
| root 启动前状态 | 不存在；未由外层命令预建 |
| frozen input | `input/templates/full3d_iterative_example.dat` |
| Gate | `<= 1.0e-11`，未改变 |

完整 outer watchdog command（case root 在启动前不存在）为：

```text
cd /home/shenjh/Projects/MyFEniCSx_task37_extra && source scripts/activate_myfenics_wsl.sh && python -m benchmarks.run_task038_full3d_n2_la0 --watchdog \
  --watchdog-record /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/record.json \
  --watchdog-raw /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/watchdog.raw.json \
  --watchdog-compact /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/watchdog.compact.json \
  --watchdog-log /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/worker.log \
  --watchdog-marker-dir /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/raw/markers \
  --watchdog-poll-seconds 1.0 --watchdog-timeout-seconds 600 \
  --watchdog-command mpiexec -n 1 python -m benchmarks.run_task038_full3d_n2_la0 --stage la0 --case p6-h10-mpi1 --input input/templates/full3d_iterative_example.dat \
  --raw-dir /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/raw \
  --record /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/record.json \
  --marker-dir /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_n2_la_v2/ae59985/p6_h10_mpi1/raw/markers \
  --expected-source-sha ae599854d08fcd16e3f1d204017bc4bc04482bbf --expected-mpi-size 1
```

其中 outer watchdog 的 poll 为 `1.0 s`、timeout 为 `600 s`、hard stop 为 `2,000,000,000 B`、swap Gate 为 `0`；上面 inner command 与 `watchdog.raw.json` 中的 command/path 完全一致。

## marker 与停止边界

实际 worker marker 顺序为：

```text
preflight → mesh_space_mpc → subdomain_inventory → local_factor_build → failure
```

失败事实：

```text
ValueError: unknown N2 marker: linear_algebra_diagnostic
worker rc=1; independent checker rc=1
```

因此 `linear_algebra_diagnostic` 没有成功写入，checker 按合同拒绝把此 record 判为 formal completion。不存在 LA2、fresh N2 complete setup、MPI2、N3、N4 或后续 PDE 运行。

## measured + independently_recomputed 数值事实

| 指标 | 值 |
|---|---:|
| failed class digest | `0c6b9830423f8baf83b6714ac178c724b63af1359d01b3ca5badd1d40c070a67` |
| class slot / rows | `1 / 882` |
| class order SHA-256 | `a7b649d25c7f843a160816a3c4fe3836243e9639eb7c0ba43dd2901955511028` |
| representative tag / widths | `1 / [8.25, 8.333333333333332, 10.0]` |
| canonical row descriptor SHA-256 | `dc472b4bc91616cb54740593e8df75feb966197d16f7593e0542db1baa5db5c5` |
| old residual agreement | `0` relative |
| Hermitian defect | `9.757433025229162e-17` |
| lambda min / max | `0.00045043462322559666 / 25934.54102501312` |
| kappa2 | `57576704.11589122` |
| factorization residual | `8.158904706122267e-16` |
| packed roundtrip | exact；relative `0` |

| 路径 | residual | normalized backward error | repeat |
|---|---:|---:|---|
| S0 packed + generic solve | `1.0426245523812324e-11` | `9.01854818500637e-19` | exact |
| S1 dedicated triangular solve | `9.316208748538303e-12` | `8.058382790658791e-19` | exact |
| S2 direct B solve（diagnostic） | `2.544882468429781e-11` | `2.2012856990841358e-18` | exact |
| S3 S1 + one refinement | `6.672944399115928e-12` | `5.771998219478778e-19` | exact |

独立 checker 的 numerical decision 为 `Path T` candidate；这不是 formal Gate PASS，也没有修改 production triangular solve。S0–S3 pairwise relative differences 的最大值为 `1.135334055192972e-12`；S0/S1、S0/S2、S0/S3、S1/S2、S1/S3、S2/S3 分别为 `5.50661841184164e-14`、`1.1076672952087521e-12`、`1.1639072994451218e-13`、`1.135334055192972e-12`、`1.2167290670560742e-13`、`1.114956805311016e-12`。

临时数组字节为 derived：`18,761,904 B`；库内部 workspace 未测量。SciPy 为 `1.11.4`，路径 `/usr/lib/python3/dist-packages/scipy/__init__.py`，使用 `scipy.linalg.solve_triangular` 的 `ztrtrs`。

## 资源事实

| 指标 | 值 | 解释 |
|---|---:|---|
| process-tree memory authority peak | `1,487,814,656 B` | 低于 2 GB hard line，但不是完整 N2 qualification |
| process-tree swap | `0 B` | watchdog swap gate=true |
| authority samples | `145` | sampled elapsed 约 `145.004 s` |
| termination | `already_exited` / no orphan / no SIGKILL | worker 自行返回 `rc=1`，watchdog 未外部终止 |
| post-setup retained | not run | 未到完整 setup |

资源峰值低于 hard line，但由于 worker/checker rc=1 和 marker contract fail，overall resource/lifecycle qualification 仍为 false；不能把它写成完整 N2 `<2 GB` 通过。

## 证据索引

以下 hash/bytes 均由现有文件只读重算：

| artifact | bytes | SHA-256 |
|---|---:|---|
| `raw/failed_B.npy` | `12,446,912` | `ec6fa132758735531e272532529bc43a0ac6f1cbf8c1e3c3f3656f19383fcbcd` |
| `raw/failed_rhs.npy` | `14,240` | `da2a800306714ebe4218ae03fa09493d782a18351f5aa6c05eec7e15cb300983` |
| `raw/markers/preflight.json` | `241` | `f00e412e133f3211c54365f9bb2c28f87c09094d73e438288eff8d4b33c45638` |
| `raw/markers/mesh_space_mpc.json` | `267` | `9643d8711f5f07dbdb9a2101eb995ac438f209925b7be4c2f3e7a46521ec3ace` |
| `raw/markers/subdomain_inventory.json` | `260` | `089b722c6920d1c7bb4001fc8868d12035a388cd5296c2375669ed4a94e9493e` |
| `raw/markers/local_factor_build.json` | `277` | `85bfe801510f887bacb824209a80787c3b9feb327a65d64ca322053d374315e1` |
| `raw/markers/failure.json` | `314` | `0fe53cdf312ba794a06f5da7b1e13f54a6ebf418401af85e69810acc6a903789` |
| `raw/mesh/mesh_3d.h5` | `31,720` | `f64e182acd195201ccaed060a20080f52582c3d6aa9d68fdf12d214789870af2` |
| `raw/mesh/mesh_3d.xdmf` | `607` | `967b0641b2402e74b12bc5c460acd0a9c19cedefbc22953e124fc94395552d5f` |
| `raw/mesh/mesh_3d_partition_note.txt` | `1,353` | `0a3e481d76798fa867ac1151dee5b3899920e623606faf36f175ee670c9ed974` |
| `record.json` | `14,248` | `f75759ea0be1af5d751167c611fafda6832c0636e9cf870f9c788583aebe5dd7` |
| `watchdog.raw.json` | `204,656` | `c20eb9d429f8f968f6f5818971fcbbf2fcb72a9c4f3fe94c98e405ad5efc276e` |
| `watchdog.compact.json` | `2,348` | `f41d8bcbbc8ada1a9941fe162b73af32dd6682d05f9f087bc90138e794a1822a` |
| `worker.log` | `1,977` | `e5129b1450bac03ef52189cb4fd89381c2d1a4cdcadb1ac73cc608a8a1d208be` |
| tracked checker compact `n2_local_factor_la_v2.json` | `3,933` | `9610f69826092a31a69d6c3a7cbcb8cefd69ada0954c767b11953abafed47d44` |

历史证据复核：旧 N2 v1 compact SHA 为 `d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40`；第一次 LA0 lifecycle compact SHA 为 `e0d161d2827b2bed390fe4ab6ef7238891606edc094adb0513a3e0ba4c10a739`。两者均未修改。当前 v2 checker compact 是独立 checker 的原始 `passed=false` 输出，不覆盖 v1。

## 后续边界与 selective merge

LA2、fresh N2 MPI1/MPI2、N3、N4、T6-F、official physics、T7–T9 和 full 0.7 nm PDE 全部 `not_run`。watchdog ownership 修复与真实 subprocess E2E 可审阅；LA0 marker runner/LA1 diagnostic 仍为 `research-only/not-qualified`。不提升 production triangular solve，不改写旧 N2 negative。
