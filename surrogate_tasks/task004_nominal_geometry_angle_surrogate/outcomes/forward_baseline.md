# Forward baseline qualification

The required five-anchor qualification was attempted at the new clean SHA.
The first anchor `(120,17,0.5°,0°)` failed during MUMPS numerical factorization:

| quantity | result |
|---|---|
| solver route | Full3D static uniform N1curl p5/h10/Ny4, MPI2/thread1 |
| stage | augmented DtN direct-LU setup |
| MUMPS `INFOG(1)` | `-9` |
| MUMPS `INFO(2)` | `919260` |
| peak RSS | `5,690,605,568` bytes |
| swap | `0` bytes |
| residual / energy / observable | not measured; no formal record |

This is a controlled stop, not a pass. The earlier five-anchor run at the
previous SHA is retained as historical reference only and cannot qualify the
new SHA.
