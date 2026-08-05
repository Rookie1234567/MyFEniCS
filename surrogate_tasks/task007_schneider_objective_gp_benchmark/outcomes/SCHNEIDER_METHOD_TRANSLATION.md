# Schneider-style objective-GP method translation

本任务将每个给定 synthetic measurement 转换为二维 `(h,w)` 上的标量 negative-log-posterior objective。GP 学习的是 `log10(F+1e-12)`，而不是完整 Maxwell response；expected improvement 在 stored-response replay universe 中选择下一次 oracle query。

本版本没有 objective derivative observations，也没有运行新 FEM；P0/P1/P2 使用固定 8-start Matérn-5/2 ARD exact GP，P3 在连续二维域上做 posterior-mean MAP。Case141 的 11 个完整点仅作为 external replay targets，不能改写为 Task006 formal blind pass。
