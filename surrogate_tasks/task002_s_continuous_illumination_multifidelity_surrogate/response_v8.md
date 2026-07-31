# Task002 Review V7 response：M4E 完成，等待 Review V8

Required M4E 已完成。

1. `_mode_projection_from_solution` 已改为纯切向 E/mode projection；Ny3/Ny4、
   中心角和高掠射点的全 power-carrying S/P auxiliary/direct 最大差异为
   `9.11e-14–1.09e-12`，全部通过 `1e-10` Gate。
2. 唯一 production identity 已冻结为 Full3D static uniform N1curl p5/h10/MPI2，
   `(Nx,Ny,Nz)=(6,4,14)`；Ny3 被 hard quarantine。
3. clean implementation baseline 为
   `10e3356ba8364286a452077f71d7e3b92ea24cd5`。96/16/4096/8 四个 tuple hash
   全部保持不变。
4. 16 corners、原 index 40、54.25°/54.50°/54.75° alias canary 和三类切向
   diagnostic 全部通过原 Gate。
5. 新 Case119 campaign 完成 96/96 training 和 16/16 frozen validation，112 条
   production sample 全部 measured-pass、zero swap、cleanup complete；Case117 与
   Ny3 的 56 个 pass 未复用。
6. `task002_m4e_p5_ny4_112_v3` compact dataset 已生成。独立 exact-design checker
   确认 96/16 恰好覆盖、无 missing/extra、一个 SHA、Ny4-only、observable v3-only，
   file hashes 与 array identities 全部通过；Case119 checker 6/6 通过。
7. 用户请求暂停造成的 index 4 attempt 1 已作为 `interrupted_retryable` 原样保存；
   无 formal record、zero swap、cleanup complete。attempt 2 从头运行并通过，未跳点。

focused Task002 tests 41 passed；Task000/001/002 范围回归 80 passed；Case117
immutable-stop、Case118 13/13、Case119 6/6、compileall 和 `git diff --check`
均通过。

frozen validation 没有用于模型选择。本轮未开始 PCE、GP、validation scoring、
active learning、angle DOE 或 inversion，现停止等待 Review V8。
