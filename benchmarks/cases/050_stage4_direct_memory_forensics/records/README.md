# Case050 records

此目录只保存通过 Task029 Gate 后选定的轻量、可审查 summary record。开发期间的 candidate JSON、完整 memory timeline、solver log、mesh、field、factor 与 OOC scratch 全部保留在 gitignored 的 `benchmarks/artifacts/cases/050/`。

Task28 的 direct/workstation canonical records 不得复制覆盖到此目录。

## 已冻结记录

- `h5_baseline.json`：MPI4、p2、default MUMPS 的完整 h5 baseline；source SHA 为 `208aaab149ca5c2be0aae09a8d893bfa02e3f8cc`，数值 Gate、factor inventory 与零 swap 均通过。

h3 尚未运行；h2 仍由 guarded Gate 锁定。
