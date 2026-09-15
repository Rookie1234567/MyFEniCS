# h1.5 PORD64 isolated build recipe

This is a compact record of the already executed task-local build, not a new
build framework.  The old int32/int64 prefix was not modified.

## Inputs and compiler recipes

The MUMPS 5.5.1 `Makefile.inc` supplied `OUTC=-o `, `AR=/usr/bin/ar cr `,
`LIBEXT=.a`, `CDEFS=-DAdd_`, `ORDERINGSC=-Dpord`, and the PORD include path.
The PORD copy was built with the following effective command family on
`taskset -c 10-13`, `-j4`:

```sh
taskset -c 10-13 make -C /tmp/task39extra-pord64/PORD/lib realclean
taskset -c 10-13 make -C /tmp/task39extra-pord64/PORD/lib -j4 \
  CC=mpicc \
  CFLAGS='-fPIC -Wno-lto-type-mismatch -Wno-stringop-overflow -g -O -DPORD_INTSIZE64' \
  OUTC='-o ' AR='/usr/bin/ar cr ' LIBEXT=.a RANLIB=/usr/bin/ranlib
```

The 14 PORD C objects and the MUMPS bridge were compiled with
`-DPORD_INTSIZE64`; no global `-DINTSIZE64` was used.  The bridge effective
argv was:

```sh
taskset -c 10-13 /usr/bin/mpicc \
  -fPIC -Wno-lto-type-mismatch -Wno-stringop-overflow -g -O \
  -I/tmp/task39extra-pord64/PORD/include \
  -I/tmp/task39extra_para_int64_stack/src/petsc/int64-complex/externalpackages/MUMPS_5.5.1/include \
  -DAdd_ -Dpord -DPORD_INTSIZE64 \
  -c /tmp/task39extra_para_int64_stack/src/petsc/int64-complex/externalpackages/MUMPS_5.5.1/src/mumps_pord.c \
  -o /tmp/task39extra-pord64/mumps_pord.o
```

## Archive replacement and PETSc relink

The exact already-executed replacement sequence was:

```sh
cp "$OLD/prefix/petsc/lib/libmumps_common.a" "$NEW/lib/libmumps_common.a"
cp "$NEW/PORD/lib/libpord.a" "$NEW/lib/"
/usr/bin/ar d "$NEW/lib/libmumps_common.a" mumps_pord.o
/usr/bin/ar r "$NEW/lib/libmumps_common.a" "$NEW/mumps_pord.o"
/usr/bin/ranlib "$NEW/lib/libmumps_common.a"
```

The task-local PETSc shared library was then linked on CPU10–13 using the
existing object-argument file and the existing `PETSC_EXTERNAL_LIB_BASIC`
fragment, with the MUMPS `-L`/rpath directed to the new library directory:

```sh
taskset -c 10-13 bash -c 'cd "$1"; exec /usr/bin/mpicc \
  -shared -fPIC -Wall -Wwrite-strings -Wno-unknown-pragmas \
  -Wno-lto-type-mismatch -Wno-stringop-overflow -fstack-protector \
  -fvisibility=hidden -g -O -Wl,-soname,libpetsc.so.3.19 \
  -o "$2/petsc/lib/libpetsc.so.3.19.6" \
  @"$3" -Wl,-rpath,"$2/lib" -L"$2/lib" $4' bash \
  /tmp/task39extra_para_int64_stack/src/petsc \
  /tmp/task39extra-pord64 \
  /tmp/task39extra_para_int64_stack/src/petsc/int64-complex/lib/libpetsc.so.3.19.6.args \
  "$PETSC_EXTERNAL_LIB_BASIC"
```

The link object list is the 71,895-byte `libpetsc.so.3.19.6.args`; its SHA256
is `7b30a5af06a178df7103d473da30abed0095a34ad488dd709413eb3e8edc0576`.
The `petscvariables` source for `PETSC_EXTERNAL_LIB_BASIC` has SHA256
`39c4624aba7dbcb6d7bba79604f1dff1d79d9eab97a419feb29f7769a90e397c`.
The resulting SONAME is `libpetsc.so.3.19`; the resulting library SHA256 is
`cf7fdfff5ce3b4d4ca3037eed646c21f07268483e9bd69bafef637b0e507f79d`.

## petsc4py metadata isolation

The original task-local `petsc4py` package/extension was copied to
`/tmp/task39extra-pord64/petsc/lib/petsc4py`, and the existing int64 PETSc
headers were copied to `/tmp/task39extra-pord64/petsc/include`.  Only the new
copy of `lib/petsc4py/lib/petsc.cfg` was edited:

```ini
PETSC_DIR  = /tmp/task39extra-pord64/petsc
PETSC_ARCH =
```

The copied cfg SHA256 is
`dee2054039c439457a61b8a5f2400a50d85ebb48f53e0ed82f59f09d4df0cb02`.
The final opt-in activation is
`scripts/activate_task39extra_pord64.sh`; it unsets `LD_PRELOAD` and
`SLEPC_DIR`, puts the new PETSc/PORD paths first, and unsets `PKG_CONFIG_PATH`
because this new prefix contains no `.pc` files.
