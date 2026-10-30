/* Public PETSc API only. MatFactorInfo is compiled from the actual header,
 * never mirrored in Python or inferred from private PETSc/MUMPS layouts. */
#include <petscmat.h>

int myfenics_petsc_int_bytes(void) { return (int)sizeof(PetscInt); }
int myfenics_petsc_scalar_bytes(void) { return (int)sizeof(PetscScalar); }
int myfenics_mumps_symbolic(Mat factor, Mat matrix) {
    MatFactorInfo info;
    PetscErrorCode error = MatFactorInfoInitialize(&info);
    if (error) return error;
    return MatLUFactorSymbolic(factor, matrix, NULL, NULL, &info);
}
int myfenics_mumps_numeric(Mat factor, Mat matrix) {
    MatFactorInfo info;
    PetscErrorCode error = MatFactorInfoInitialize(&info);
    if (error) return error;
    return MatLUFactorNumeric(factor, matrix, &info);
}
