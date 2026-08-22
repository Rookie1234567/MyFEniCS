# N2 local spectral setup：fresh MPI1 v2 controlled negative

## 结论

v3 LA1 已证明专用三角解能修复原先那个已诊断 class。随后把这个唯一窄修提交
为 `b20de4960db4210f510195cff6136c72cd990b3f`，保持 B0、exact-class 顺序、fixed
RHS、`1e-11` Gate、factor layout 和 owner routing 不变，并进行一次全新的 cold
N2 p6/h10 MPI1 setup。

完整 class registration 在后续 class 上仍得到 fixed-RHS residual 超过 Gate：

`1.1089747142000698e-11 > 9.999999999999999e-12`。

因此 N2 MPI1 是真实 numerical Gate failure；这不是 watchdog、marker、路径、JIT
或 object lifecycle failure。N2 未完成，不能进入 coarse/contraction/PDE。

## Fresh formal result

| 项目 | 实际值 | 分类 |
|---|---:|---|
| source SHA | `b20de4960db4210f510195cff6136c72cd990b3f` | clean formal source |
| case / attempt | p6/h10 MPI1 / 唯一一次 | no rerun |
| fixed RHS residual | `1.1089747142000698e-11` | FAIL，limit `1e-11` |
| excess over limit | `1.089747142000698e-12`（约 `10.89747142000698%`） | numerical Gate |
| marker | `preflight → mesh_space_mpc → JIT → subdomain_inventory → local_factor_build → failure` | fail early |
| marker span / watchdog elapsed | `25.492487193 s` / `27.134127181983786 s` | measured |
| worker / watchdog / checker rc | `1 / 1 / 1` | controlled negative |
| process-tree peak | `1,504,804,864 B` | below 2 GB at failure point only |
| process-tree swap | `0 B` | measured Gate pass at sampled stages |
| post-setup sample | `0` | not run |
| termination | worker自行 rc=1；watchdog未发 SIGTERM/SIGKILL；already_exited/no orphan | not a watchdog stop |

worker record 是 `controlled_negative`；watchdog `stop_reason=natural_exit` 仅表示
没有外部终止，而 compact 的 `natural_exit=false` 因为 worker rc=1。独立 checker
返回 `passed=false`，并对缺少成功 setup schema fail-closed；没有把部分资源峰值写成
完整 setup PASS。

## 未运行项

失败发生在 local factor build。标准 N2 worker 没有记录本次失败类 digest、代表 cell
identity 或 rows；不能用 v3 已知 class digest冒充本次身份。因此以下均为
`not_run_by_numerical_gate`，不是额外失败：252 patch/cell inventory最终闭合、
exact-class count、factor bytes全量审计、8 modes、regional rank16、top rank32、
Z16/Z32/AZ32/E32、zero identity apply、post-setup retained、canonical identity、
MPI2、N3/N4、T6-F/EH/RTA、T7–T9 和 full 0.7 nm PDE。

`1,504,804,864 B` 只是失败点前 cold process-tree peak；它不能证明 complete setup
低于 2 GB，也不能证明 post-setup retained 低于 1.8 GB。

## 证据索引

| artifact | bytes | SHA-256 |
|---|---:|---|
| tracked v2 checker compact `outcomes/records/n2_local_spectral_setup_mpi1_v2.json` | 3,521 | `d88330f2c9b038946c8f0b15e22b5850e6812c868366fa50f04e1e9b3962f763` |
| ignored worker record | 6,617 | `fa24d8dd1462ee3823fff9f49144bd32fb9172d7cf09720efe7d26da19942d3c` |
| ignored watchdog raw | 40,310 | `7bb37b3765201fb01e6477f36d4adca6a604c09f987a8c53e95a73dde4c0ba5e` |
| ignored watchdog compact | 2,353 | `d6283c7c68529dc2e928ad2a371de0e55e83bc541b363448de4622ee0a3c1215` |
| ignored worker log | 2,532 | `8b0511e4cd7a8714d2908ec41a80efc9101d43ab3a76f3a5f3ca31e3c3211ee3` |
| ignored mesh H5 | 31,720 | `dbab57afb43ea7105ad34d87efb692471ff2e8f3acdada2e7b14f70ad6eb6033` |
| ignored mesh XDMF | 607 | `967b0641b2402e74b12bc5c460acd0a9c19cedefbc22953e124fc94395552d5f` |
| ignored partition note | 1,353 | `0a3e481d76798fa867ac1151dee5b3899920e623606faf36f175ee670c9ed974` |

raw root：
`benchmarks/artifacts/task038_extra_full3d_n2_formal_v2/b20de49/p6_h10_mpi1/`。

旧 N2 v1、第一次 LA0 startup stop、v2 marker failure 和 v3 LA0/LA1 raw/compact
均保留，未覆盖、未删除、未重分类。当前结论只停止 N2 lane；不授权 MPI2 或任何后续
coarse/PDE 阶段。
