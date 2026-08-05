# Task007 method comparison

本报告只使用 stored-response replay；没有运行 FEM。在线查询数不包括初始训练点，首次查询计为 1。

## B0 nearest offline objective

| contract | noise | targets | exact target hits | median best F | p90 best F |
|---|---|---:|---:|---:|---:|
| J0 | N1 | 11 | 0 | 10.8023 | 29.0308 |
| J0 | N2 | 11 | 0 | 1.68295 | 5.50427 |
| J1 | N1 | 11 | 0 | 10.6995 | 29.3652 |
| J1 | N2 | 11 | 0 | 1.66984 | 5.43659 |

## B1/P0/P1/P2 discrete replay

| contract | noise | method | targets | replay/BO runs | hit fraction | median queries | p90 queries |
|---|---|---|---:|---:|---:|---:|---:|
| J0 | N1 | B1 random replay | 11 | 1100 | 1.000 | 23.000 | 39.000 |
| J0 | N1 | P0 | 11 | 66 | 1.000 | 6.000 | 8.000 |
| J0 | N1 | P1 | 11 | 66 | 1.000 | 1.000 | 2.000 |
| J0 | N1 | P2 | 11 | 11 | 1.000 | 1.000 | 1.000 |
| J0 | N2 | B1 random replay | 11 | 1100 | 1.000 | 23.000 | 39.000 |
| J0 | N2 | P0 | 11 | 66 | 1.000 | 5.500 | 7.500 |
| J0 | N2 | P1 | 11 | 66 | 1.000 | 1.000 | 3.000 |
| J0 | N2 | P2 | 11 | 11 | 1.000 | 1.000 | 1.000 |
| J1 | N1 | B1 random replay | 11 | 1100 | 1.000 | 23.000 | 39.000 |
| J1 | N1 | P0 | 11 | 66 | 1.000 | 6.000 | 8.000 |
| J1 | N1 | P1 | 11 | 66 | 1.000 | 1.000 | 2.000 |
| J1 | N1 | P2 | 11 | 11 | 1.000 | 1.000 | 1.000 |
| J1 | N2 | B1 random replay | 11 | 1100 | 1.000 | 24.000 | 39.000 |
| J1 | N2 | P0 | 11 | 66 | 1.000 | 6.000 | 7.500 |
| J1 | N2 | P1 | 11 | 66 | 1.000 | 1.000 | 3.000 |
| J1 | N2 | P2 | 11 | 11 | 1.000 | 1.000 | 1.000 |

## P3 continuous MAP

| contract | noise | within tolerance | p90 height error (nm) | p90 width error (nm) |
|---|---|---:|---:|---:|
| J1 | N1 | 0.182 | 0.569346 | 0.111024 |
| J1 | N2 | 0.000 | 0.722529 | 0.109514 |
| J0 | N1 | 0.182 | 0.567037 | 0.110981 |
| J0 | N2 | 0.000 | 0.721478 | 0.109913 |

## GP audit

- fit count: `2022`
- optimizer warnings recorded: `1626`
- boundary collisions recorded: `1558`
- external target objective values were never used before query.
- This is a synthetic replay benchmark, not formal experimental inversion.
