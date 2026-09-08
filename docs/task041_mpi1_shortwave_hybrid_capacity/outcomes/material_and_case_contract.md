# 材料与 case contract

## 3 nm retry identity

| 项目 | 冻结值 |
|---|---|
| material | tungsten；`n=[0.99735217495, 0.000883207249]` |
| geometry / discretization | rectangular block grating；p6/h3；3 nm |
| case | `task041_3nm_exact_side_hybrid_iterative_p6h3_m800` |
| M / MPI | `M800 / MPI8` |
| DtN | physical，`auto_propagating` |
| side path | exact-side；side correction=`1` |
| MUMPS | non-OOC；factor-only；ICNTL14=`40` |
| effective outer solver | fixed right GMRES，restart=`10` |
| input SHA | `5f61d2b913a21a0761cc00e280ab5bb540ab30ac3917f662b9f3bfd1d78e1e9f` |
| physical SHA | `0bb67e4a1b811efa9ffa2238fb969b15a7eadbae3755814d6427342496da3a81` |
| resolved SHA | `726e1dc7551fccd697441c02400dddd89f60ee61a7ab934e4d494fb910edb782` |

20260908 是 consumer-only implementation retry：consumer source=`2dbe7ff76d734c7689740a656ba7c0fdb5ceadcb`，读取 producer source=`48f56ad46c49519de363b90695d1ed219236c662` 的 packet；cross-source reuse 明确记录，未改写 packet。20260907 fresh attempt 的失败阶段为 `consumer_exit(solution_snapshot_destroyed)`，不与 retry residual 混合。

## 5 nm 两套身份

Task039 inherited record 的 source=`9e31ecf189081afcb8ca27b0374ec89af0094e2d`、input=`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`。Task041 本机 MPI8 reproduction 的 source=`def547cfd139b6377b0cae2ba1736ec3591814b0`、input=`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`、physical=`8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c`、resolved=`d6f9de274db352e7b11eafed6867e6535edb7872af3547fa7fd958d02997798f`。两者均为 5 nm/p6h4/M480/MPI8，但不能混称为同一 run。

不修改物理、M、mesh、solver identity、ordinary defaults 或旧 authority。
