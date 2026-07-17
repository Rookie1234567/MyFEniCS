# Memory Report

Toy GPU training on Quadro RTX 8000 used 20,136,960 peak allocated bytes and 25,165,824 peak reserved bytes. The model is deliberately reduced-coordinate and does not contain a dense `n_s × n_s` layer.

The real h5 baseline recorded 1.602940 GiB peak including RTA. The guarded one-slab ILU+NN run recorded 1.654888 GiB, an increase of 3.241%, so it passes the `<=10%` memory guard but fails time acceleration decisively. The rank256/hidden512 checkpoint occupies 45,094,912 bytes. Its RTX 8000 training peak allocated/reserved was 277,752,832/291,504,128 bytes.

No ILU-removal claim is made: the accepted Lane-B candidate retains ILU and adds NN correction, inference and residual-check storage. WSL exposes about 228 GiB host memory and 32 GiB swap; no h3/h2 run was unlocked after the h5 time Gate failed.
