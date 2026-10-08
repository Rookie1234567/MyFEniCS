#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include <petscmat.h>
#include <petscoptions.h>
#include <petscpkg_version.h>
#include <petscversion.h>
#include <petsc4py/petsc4py.h>

/*
 * Narrow staged MUMPS LU bridge.  The installed petsc4py C API getters are
 * imported through petsc4py/petsc4py.h.  The source Mat is borrowed;
 * source_keepalive holds its Python wrapper until the owned factor is
 * destroyed.  The caller must not explicitly destroy that source Mat first.
 * No KSP or hidden setup path exists here.
 */

typedef struct {
  PyObject_HEAD
  Mat source;                    /* borrowed PETSc handle */
  Mat factor;                    /* owned MatGetFactor result */
  MatFactorInfo factor_info;     /* public PETSc factor-info value */
  PyObject *source_keepalive;
  PetscInt icntl14_requested;
  PetscInt icntl14_actual;
  PetscErrorCode icntl14_error_code;
  int source_keepalive_released;
  int symbolic_attempts;
  PetscErrorCode symbolic_error_code;
  int symbolic_completed;
  int numeric_attempts;
  PetscErrorCode numeric_error_code;
  int numeric_completed;
  int destroy_attempts;
  PetscErrorCode destroy_error_code;
  int factor_released;
} LUStageFactor;

static PyTypeObject LUStageFactorType = {PyVarObject_HEAD_INIT(NULL, 0)};
static PyTypeObject *petsc_mat_python_type = NULL;
static PyTypeObject *petsc_vec_python_type = NULL;

static int dict_set_long(PyObject *dict, const char *key, long value)
{
  PyObject *item = PyLong_FromLong(value);
  int status;
  if (!item) return -1;
  status = PyDict_SetItemString(dict, key, item);
  Py_DECREF(item);
  return status;
}

static int dict_set_petsc_int(PyObject *dict, const char *key, PetscInt value)
{
  PyObject *item = PyLong_FromLongLong((long long)value);
  int status;
  if (!item) return -1;
  status = PyDict_SetItemString(dict, key, item);
  Py_DECREF(item);
  return status;
}

static PyObject *petsc_int_pair(PetscInt first, PetscInt second)
{
  PyObject *result = PyTuple_New(2);
  PyObject *left = NULL;
  PyObject *right = NULL;
  if (!result) return NULL;
  left = PyLong_FromLongLong((long long)first);
  right = PyLong_FromLongLong((long long)second);
  if (!left || !right) {
    Py_XDECREF(left);
    Py_XDECREF(right);
    Py_DECREF(result);
    return NULL;
  }
  PyTuple_SET_ITEM(result, 0, left);
  PyTuple_SET_ITEM(result, 1, right);
  return result;
}

static int dict_set_bool(PyObject *dict, const char *key, int value)
{
  PyObject *item = value ? Py_True : Py_False;
  Py_INCREF(item);
  if (PyDict_SetItemString(dict, key, item) < 0) {
    Py_DECREF(item);
    return -1;
  }
  Py_DECREF(item);
  return 0;
}

static int dict_set_string(PyObject *dict, const char *key, const char *value)
{
  PyObject *item = PyUnicode_FromString(value);
  int status;
  if (!item) return -1;
  status = PyDict_SetItemString(dict, key, item);
  Py_DECREF(item);
  return status;
}

static int dict_set_none(PyObject *dict, const char *key)
{
  Py_INCREF(Py_None);
  if (PyDict_SetItemString(dict, key, Py_None) < 0) {
    Py_DECREF(Py_None);
    return -1;
  }
  Py_DECREF(Py_None);
  return 0;
}

static PyObject *lifecycle_dict(const LUStageFactor *self)
{
  PyObject *result = PyDict_New();
  if (!result) return NULL;
  if (dict_set_string(result, "source_matrix_ownership",
                      "borrowed; Python wrapper retained as keepalive") < 0 ||
      dict_set_string(result, "factor_ownership",
                      "owned from MatGetFactor until destroy") < 0 ||
      dict_set_petsc_int(result, "icntl14_requested",
                         self->icntl14_requested) < 0 ||
      (self->icntl14_error_code
           ? dict_set_none(result, "icntl14_actual")
           : dict_set_petsc_int(result, "icntl14_actual",
                                self->icntl14_actual)) < 0 ||
      dict_set_long(result, "icntl14_error_code",
                    (long)self->icntl14_error_code) < 0 ||
      dict_set_bool(result, "source_keepalive_released",
                    self->source_keepalive_released) < 0 ||
      dict_set_long(result, "symbolic_attempts", self->symbolic_attempts) < 0 ||
      dict_set_long(result, "symbolic_error_code",
                    (long)self->symbolic_error_code) < 0 ||
      dict_set_bool(result, "symbolic_completed", self->symbolic_completed) < 0 ||
      dict_set_long(result, "numeric_attempts", self->numeric_attempts) < 0 ||
      dict_set_long(result, "numeric_error_code",
                    (long)self->numeric_error_code) < 0 ||
      dict_set_bool(result, "numeric_completed", self->numeric_completed) < 0 ||
      dict_set_long(result, "destroy_attempts", self->destroy_attempts) < 0 ||
      dict_set_long(result, "destroy_error_code",
                    (long)self->destroy_error_code) < 0 ||
      dict_set_bool(result, "factor_released", self->factor_released) < 0) {
    Py_DECREF(result);
    return NULL;
  }
  return result;
}

static void release_source_keepalive_if_factor_gone(LUStageFactor *self)
{
  if (!self->factor) {
    self->source = NULL;
    Py_CLEAR(self->source_keepalive);
    self->factor_released = 1;
  }
}

static void LUStageFactor_dealloc(LUStageFactor *self)
{
  if (self->factor) {
    self->destroy_attempts += 1;
    self->destroy_error_code = MatDestroy(&self->factor);
  }
  /* If PETSc leaves the factor alive after a failed final MatDestroy, keep
   * the source Python reference's owned reference alive rather than expose
   * a dangling borrowed Mat to the still-live backend factor. */
  release_source_keepalive_if_factor_gone(self);
  Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *LUStageFactor_lifecycle(LUStageFactor *self,
                                         PyObject *Py_UNUSED(ignored))
{
  return lifecycle_dict(self);
}

static PyObject *matrix_layout_dict(Mat matrix)
{
  PetscInt global_rows = 0, global_columns = 0;
  PetscInt local_rows = 0, local_columns = 0;
  PetscInt row_first = 0, row_last = 0;
  PetscInt column_first = 0, column_last = 0;
  PetscErrorCode ierr;
  PyObject *result = NULL;
  PyObject *global_size = NULL;
  PyObject *local_size = NULL;
  PyObject *row_ownership = NULL;
  PyObject *column_ownership = NULL;

  ierr = MatGetSize(matrix, &global_rows, &global_columns);
  if (!ierr) ierr = MatGetLocalSize(matrix, &local_rows, &local_columns);
  if (!ierr) ierr = MatGetOwnershipRange(matrix, &row_first, &row_last);
  if (!ierr) ierr = MatGetOwnershipRangeColumn(
      matrix, &column_first, &column_last);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError,
                 "PETSc factor layout query failed: error %d", (int)ierr);
    return NULL;
  }

  result = PyDict_New();
  global_size = petsc_int_pair(global_rows, global_columns);
  local_size = petsc_int_pair(local_rows, local_columns);
  row_ownership = petsc_int_pair(row_first, row_last);
  column_ownership = petsc_int_pair(column_first, column_last);
  if (!result || !global_size || !local_size || !row_ownership ||
      !column_ownership ||
      PyDict_SetItemString(result, "global_size", global_size) < 0 ||
      PyDict_SetItemString(result, "local_size", local_size) < 0 ||
      PyDict_SetItemString(result, "row_ownership", row_ownership) < 0 ||
      PyDict_SetItemString(result, "column_ownership", column_ownership) < 0) {
    Py_XDECREF(result);
    Py_XDECREF(global_size);
    Py_XDECREF(local_size);
    Py_XDECREF(row_ownership);
    Py_XDECREF(column_ownership);
    return NULL;
  }
  Py_DECREF(global_size);
  Py_DECREF(local_size);
  Py_DECREF(row_ownership);
  Py_DECREF(column_ownership);
  return result;
}

static PyObject *LUStageFactor_layout_raw(LUStageFactor *self,
                                          PyObject *Py_UNUSED(ignored))
{
  PyObject *result = NULL;
  PyObject *source_layout = NULL;
  PyObject *factor_layout = NULL;
  if (!self->factor) {
    PyErr_SetString(PyExc_RuntimeError, "factor handle has been destroyed");
    return NULL;
  }
  result = PyDict_New();
  if (!result) return NULL;
  if (self->source) source_layout = matrix_layout_dict(self->source);
  else {
    Py_INCREF(Py_None);
    source_layout = Py_None;
  }
  if (self->symbolic_completed) {
    factor_layout = matrix_layout_dict(self->factor);
  } else {
    /* Before symbolic analysis the backend factor's final ownership layout
     * is not yet evidence.  Expose the borrowed source layout only. */
    Py_INCREF(Py_None);
    factor_layout = Py_None;
  }
  if (!source_layout || !factor_layout ||
      PyDict_SetItemString(result, "source", source_layout) < 0 ||
      PyDict_SetItemString(result, "factor", factor_layout) < 0) {
    Py_XDECREF(source_layout);
    Py_XDECREF(factor_layout);
    Py_DECREF(result);
    return NULL;
  }
  Py_DECREF(source_layout);
  Py_DECREF(factor_layout);
  return result;
}

static PyObject *LUStageFactor_release_source_keepalive(
    LUStageFactor *self, PyObject *Py_UNUSED(ignored))
{
  if (!self->factor || !self->numeric_completed) {
    PyErr_SetString(PyExc_RuntimeError,
                    "source release requires a live factor after numeric stage");
    return NULL;
  }
  self->source = NULL;
  Py_CLEAR(self->source_keepalive);
  self->source_keepalive_released = 1;
  return lifecycle_dict(self);
}

static PyObject *LUStageFactor_symbolic(LUStageFactor *self,
                                        PyObject *Py_UNUSED(ignored))
{
  if (!self->factor) {
    PyErr_SetString(PyExc_RuntimeError, "factor handle has been destroyed");
    return NULL;
  }
  if (self->symbolic_attempts) {
    PyErr_SetString(PyExc_RuntimeError,
                    "symbolic stage can be called only once per factor handle");
    return NULL;
  }
  self->symbolic_attempts += 1;
  self->symbolic_error_code = MatLUFactorSymbolic(
      self->factor, self->source, NULL, NULL, &self->factor_info);
  if (self->symbolic_error_code) {
    PyErr_Format(PyExc_RuntimeError,
                 "MatLUFactorSymbolic failed: PETSc error %d",
                 (int)self->symbolic_error_code);
    return NULL;
  }
  self->symbolic_completed = 1;
  return lifecycle_dict(self);
}

static PyObject *LUStageFactor_numeric(LUStageFactor *self,
                                       PyObject *Py_UNUSED(ignored))
{
  if (!self->factor) {
    PyErr_SetString(PyExc_RuntimeError, "factor handle has been destroyed");
    return NULL;
  }
  if (!self->symbolic_completed) {
    PyErr_SetString(PyExc_RuntimeError,
                    "numeric stage requires successful symbolic stage");
    return NULL;
  }
  if (self->numeric_attempts) {
    PyErr_SetString(PyExc_RuntimeError,
                    "numeric stage can be called only once per factor handle");
    return NULL;
  }
  self->numeric_attempts += 1;
  self->numeric_error_code = MatLUFactorNumeric(
      self->factor, self->source, &self->factor_info);
  if (self->numeric_error_code) {
    PyErr_Format(PyExc_RuntimeError,
                 "MatLUFactorNumeric failed: PETSc error %d",
                 (int)self->numeric_error_code);
    return NULL;
  }
  self->numeric_completed = 1;
  return lifecycle_dict(self);
}

static PyObject *LUStageFactor_solve(LUStageFactor *self, PyObject *args)
{
  PyObject *rhs_object = NULL;
  PyObject *solution_object = NULL;
  Vec rhs;
  Vec solution;
  PetscErrorCode ierr;
  if (!PyArg_ParseTuple(args, "OO:solve", &rhs_object, &solution_object))
    return NULL;
  if (!self->factor || !self->numeric_completed) {
    PyErr_SetString(PyExc_RuntimeError,
                    "solve requires a live factor after successful numeric stage");
    return NULL;
  }
  if (!PyObject_TypeCheck(rhs_object, petsc_vec_python_type) ||
      !PyObject_TypeCheck(solution_object, petsc_vec_python_type)) {
    PyErr_SetString(PyExc_TypeError, "rhs and solution must be petsc4py Vec objects");
    return NULL;
  }
  rhs = PyPetscVec_Get(rhs_object);
  solution = PyPetscVec_Get(solution_object);
  if (!rhs || !solution) {
    PyErr_SetString(PyExc_ValueError, "rhs or solution PETSc Vec has been destroyed");
    return NULL;
  }
  ierr = MatSolve(self->factor, rhs, solution);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError, "MatSolve failed: PETSc error %d", (int)ierr);
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *LUStageFactor_solve_transpose(LUStageFactor *self,
                                                PyObject *args)
{
  PyObject *rhs_object = NULL;
  PyObject *solution_object = NULL;
  Vec rhs;
  Vec solution;
  PetscErrorCode ierr;
  if (!PyArg_ParseTuple(args, "OO:solve_transpose", &rhs_object,
                        &solution_object))
    return NULL;
  if (!self->factor || !self->numeric_completed) {
    PyErr_SetString(PyExc_RuntimeError,
                    "transpose solve requires a live factor after numeric stage");
    return NULL;
  }
  if (!PyObject_TypeCheck(rhs_object, petsc_vec_python_type) ||
      !PyObject_TypeCheck(solution_object, petsc_vec_python_type)) {
    PyErr_SetString(PyExc_TypeError,
                    "rhs and solution must be petsc4py Vec objects");
    return NULL;
  }
  rhs = PyPetscVec_Get(rhs_object);
  solution = PyPetscVec_Get(solution_object);
  if (!rhs || !solution) {
    PyErr_SetString(PyExc_ValueError,
                    "rhs or solution PETSc Vec has been destroyed");
    return NULL;
  }
  ierr = MatSolveTranspose(self->factor, rhs, solution);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError,
                 "MatSolveTranspose failed: PETSc error %d", (int)ierr);
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *LUStageFactor_mat_solve_common(
    LUStageFactor *self, PyObject *args, int transpose)
{
  PyObject *rhs_object = NULL;
  PyObject *solution_object = NULL;
  Mat rhs;
  Mat solution;
  PetscErrorCode ierr;
  const char *method_name = transpose ? "mat_solve_transpose" : "mat_solve";
  if (!PyArg_ParseTuple(args, "OO", &rhs_object, &solution_object))
    return NULL;
  if (!self->factor || !self->numeric_completed) {
    PyErr_SetString(PyExc_RuntimeError,
                    "matrix solve requires a live factor after numeric stage");
    return NULL;
  }
  if (!PyObject_TypeCheck(rhs_object, petsc_mat_python_type) ||
      !PyObject_TypeCheck(solution_object, petsc_mat_python_type)) {
    PyErr_SetString(PyExc_TypeError,
                    "rhs and solution must be petsc4py Mat objects");
    return NULL;
  }
  rhs = PyPetscMat_Get(rhs_object);
  solution = PyPetscMat_Get(solution_object);
  if (!rhs || !solution) {
    PyErr_SetString(PyExc_ValueError,
                    "rhs or solution PETSc Mat has been destroyed");
    return NULL;
  }
  ierr = transpose ? MatMatSolveTranspose(self->factor, rhs, solution)
                   : MatMatSolve(self->factor, rhs, solution);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError,
                 "%s failed: PETSc error %d", method_name, (int)ierr);
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *LUStageFactor_mat_solve(LUStageFactor *self, PyObject *args)
{
  return LUStageFactor_mat_solve_common(self, args, 0);
}

static PyObject *LUStageFactor_mat_solve_transpose(LUStageFactor *self,
                                                    PyObject *args)
{
  return LUStageFactor_mat_solve_common(self, args, 1);
}

static int mumps_control_index(PyObject *object, const char *name,
                               PetscInt *index)
{
  long long value;
  if (PyBool_Check(object) || !PyLong_Check(object)) {
    PyErr_Format(PyExc_TypeError, "%s index must be a non-bool integer", name);
    return -1;
  }
  value = PyLong_AsLongLong(object);
  if (PyErr_Occurred()) return -1;
  if (value < 1 || value > (long long)PETSC_MAX_INT) {
    PyErr_Format(PyExc_ValueError, "%s index is outside the PetscInt range", name);
    return -1;
  }
  *index = (PetscInt)value;
  return 0;
}

static PyObject *LUStageFactor_set_mumps_icntl(LUStageFactor *self,
                                               PyObject *args)
{
  PyObject *index_object = NULL;
  PyObject *value_object = NULL;
  PetscInt index = 0;
  PetscInt value;
  PetscErrorCode ierr;
  if (!PyArg_ParseTuple(args, "OO:set_mumps_icntl", &index_object,
                        &value_object))
    return NULL;
  if (!self->factor) {
    PyErr_SetString(PyExc_RuntimeError, "factor handle has been destroyed");
    return NULL;
  }
  if (self->symbolic_attempts) {
    PyErr_SetString(PyExc_RuntimeError,
                    "MUMPS controls cannot change after symbolic has started");
    return NULL;
  }
  if (mumps_control_index(index_object, "ICNTL", &index) < 0) return NULL;
  if (PyBool_Check(value_object) || !PyLong_Check(value_object)) {
    PyErr_SetString(PyExc_TypeError,
                    "ICNTL value must be a non-bool integer");
    return NULL;
  }
  {
    long long parsed = PyLong_AsLongLong(value_object);
    if (PyErr_Occurred()) return NULL;
    if (parsed < (long long)PETSC_MIN_INT ||
        parsed > (long long)PETSC_MAX_INT) {
      PyErr_SetString(PyExc_ValueError, "ICNTL value is outside PetscInt range");
      return NULL;
    }
    value = (PetscInt)parsed;
  }
  ierr = MatMumpsSetIcntl(self->factor, index, value);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError,
                 "MatMumpsSetIcntl failed: PETSc error %d", (int)ierr);
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *LUStageFactor_get_mumps_icntl(LUStageFactor *self,
                                               PyObject *args)
{
  PyObject *index_object = NULL;
  PetscInt index = 0;
  PetscInt value = 0;
  PetscErrorCode ierr;
  if (!PyArg_ParseTuple(args, "O:get_mumps_icntl", &index_object)) return NULL;
  if (!self->factor) {
    PyErr_SetString(PyExc_RuntimeError, "factor handle has been destroyed");
    return NULL;
  }
  if (mumps_control_index(index_object, "ICNTL", &index) < 0) return NULL;
  ierr = MatMumpsGetIcntl(self->factor, index, &value);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError,
                 "MatMumpsGetIcntl failed: PETSc error %d", (int)ierr);
    return NULL;
  }
  return PyLong_FromLongLong((long long)value);
}

static int append_option_lookup(PyObject *entry, const char *scope,
                                const char *prefix, const char *option,
                                int is_real, int is_name)
{
  PetscBool found = PETSC_FALSE;
  PetscErrorCode ierr;
  PetscInt integer_value = 0;
  PetscReal real_value = 0.0;
  char key[96];
  int key_length;
  PyObject *value = NULL;

  key_length = snprintf(key, sizeof(key), "%s_present", scope);
  if (key_length < 0 || (size_t)key_length >= sizeof(key)) return -1;
  if (is_name)
    ierr = PetscOptionsHasName(NULL, prefix, option, &found);
  else if (is_real)
    ierr = PetscOptionsGetReal(NULL, prefix, option, &real_value, &found);
  else
    ierr = PetscOptionsGetInt(NULL, prefix, option, &integer_value, &found);
  if (dict_set_bool(entry, key, found) < 0) return -1;

  key_length = snprintf(key, sizeof(key), "%s_query_error_code", scope);
  if (key_length < 0 || (size_t)key_length >= sizeof(key) ||
      dict_set_long(entry, key, (long)ierr) < 0) return -1;

  if (ierr || !found) {
    value = Py_None;
    Py_INCREF(value);
  } else if (is_name) {
    value = Py_None;
    Py_INCREF(value);
  } else if (is_real) {
    value = PyFloat_FromDouble((double)real_value);
  } else {
    value = PyLong_FromLongLong((long long)integer_value);
  }
  if (!value) return -1;
  key_length = snprintf(key, sizeof(key), "%s_value", scope);
  if (key_length < 0 || (size_t)key_length >= sizeof(key) ||
      PyDict_SetItemString(entry, key, value) < 0) {
    Py_DECREF(value);
    return -1;
  }
  Py_DECREF(value);
  return 0;
}

static int append_mumps_option(PyObject *rows, const char *factor_prefix,
                               const char *kind, PetscInt index,
                               int is_real, const char *suffix)
{
  char option[64];
  PyObject *row = NULL;
  PetscBool factor_present = PETSC_FALSE;
  PetscBool global_present = PETSC_FALSE;
  long factor_error = 0;
  long global_error = 0;
  int option_length;
  int status = -1;

  if (suffix) {
    option_length = snprintf(option, sizeof(option), "-%s", suffix);
  } else {
    option_length = snprintf(option, sizeof(option), "-mat_mumps_%s_%d", kind,
                             (int)index);
  }
  if (option_length < 0 || (size_t)option_length >= sizeof(option)) return -1;

  row = PyDict_New();
  if (!row) return -1;
  if (dict_set_string(row, "name", option) < 0 ||
      dict_set_string(row, "kind", suffix ? "thread_setting" : kind) < 0 ||
      dict_set_petsc_int(row, "index", suffix ? 0 : index) < 0) goto done;

    if (append_option_lookup(row, "factor_prefix",
                           factor_prefix && factor_prefix[0] ? factor_prefix : NULL,
                             option, is_real, suffix != NULL) < 0) goto done;
  factor_present = PyObject_IsTrue(
      PyDict_GetItemString(row, "factor_prefix_present"));
  if (factor_present < 0) goto done;
  factor_error = PyLong_AsLong(
      PyDict_GetItemString(row, "factor_prefix_query_error_code"));
  if (PyErr_Occurred()) goto done;
  if (append_option_lookup(row, "global", NULL, option, is_real,
                           suffix != NULL) < 0) goto done;
  global_present = PyObject_IsTrue(PyDict_GetItemString(row, "global_present"));
  if (global_present < 0) goto done;
  global_error = PyLong_AsLong(
      PyDict_GetItemString(row, "global_query_error_code"));
  if (PyErr_Occurred()) goto done;

  if (factor_present || global_present || factor_error || global_error) {
    if (PyList_Append(rows, row) < 0) goto done;
  }
  status = 0;

done:
  Py_DECREF(row);
  return status;
}

static PyObject *LUStageFactor_mumps_options_raw(
    LUStageFactor *self, PyObject *Py_UNUSED(ignored))
{
  const char *prefix = NULL;
  MatType source_type = NULL, factor_type = NULL;
  MPI_Comm comm;
  PetscErrorCode prefix_error, source_type_error, factor_type_error;
  int mpi_size = -1, mpi_rank = -1;
  int mpi_size_error, mpi_rank_error;
  PyObject *result = NULL, *rows = NULL;
  PetscInt i;
  PetscErrorCode ierr;
  PetscInt checked = 0;

  if (!self->factor || !self->source) {
    PyErr_SetString(PyExc_RuntimeError, "factor/source handle has been destroyed");
    return NULL;
  }
  prefix_error = MatGetOptionsPrefix(self->factor, &prefix);
  source_type_error = MatGetType(self->source, &source_type);
  factor_type_error = MatGetType(self->factor, &factor_type);
  comm = PetscObjectComm((PetscObject)self->factor);
  mpi_size_error = MPI_Comm_size(comm, &mpi_size);
  mpi_rank_error = MPI_Comm_rank(comm, &mpi_rank);

  result = PyDict_New();
  rows = PyList_New(0);
  if (!result || !rows) goto fail;
  if (dict_set_string(result, "schema",
                      "task041.w0p7.factor_mumps_options.v1") < 0 ||
      dict_set_string(result, "options_database",
                      "PETSc active options database via public PetscOptionsGetInt/GetReal/HasName") < 0 ||
      dict_set_string(result, "factor_options_prefix",
                      prefix && !prefix_error ? prefix : "") < 0 ||
      dict_set_string(result, "factor_solver", "MATSOLVERMUMPS") < 0 ||
      dict_set_string(result, "requested_factor_kind", "MAT_FACTOR_LU") < 0 ||
      dict_set_long(result, "comm_size", (long)mpi_size) < 0 ||
      dict_set_long(result, "comm_rank", (long)mpi_rank) < 0 ||
      dict_set_long(result, "factor_prefix_error_code", (long)prefix_error) < 0 ||
      dict_set_long(result, "source_type_error_code", (long)source_type_error) < 0 ||
      dict_set_long(result, "factor_type_error_code", (long)factor_type_error) < 0 ||
      dict_set_long(result, "mpi_size_error_code", (long)mpi_size_error) < 0 ||
      dict_set_long(result, "mpi_rank_error_code", (long)mpi_rank_error) < 0 ||
      dict_set_string(result, "source_matrix_type",
                      source_type && !source_type_error ? source_type : "") < 0 ||
      dict_set_string(result, "factor_matrix_type",
                      factor_type && !factor_type_error ? factor_type : "") < 0) goto fail;

  for (i = 1; i <= 40; ++i) {
    if (append_mumps_option(rows, prefix, "icntl", i, 0, NULL) < 0) goto fail;
    ++checked;
  }
  for (i = 1; i <= 15; ++i) {
    if (append_mumps_option(rows, prefix, "cntl", i, 1, NULL) < 0) goto fail;
    ++checked;
  }
  if (append_mumps_option(rows, prefix, "", 0, 0,
                          "mat_mumps_use_omp_threads") < 0) goto fail;
  ++checked;

  if (prefix_error) {
    ierr = prefix_error;
  } else if (source_type_error) {
    ierr = source_type_error;
  } else if (factor_type_error) {
    ierr = factor_type_error;
  } else if (mpi_size_error != MPI_SUCCESS) {
    ierr = (PetscErrorCode)mpi_size_error;
  } else if (mpi_rank_error != MPI_SUCCESS) {
    ierr = (PetscErrorCode)mpi_rank_error;
  } else {
    ierr = 0;
  }
  if (dict_set_long(result, "checked_option_count", (long)checked) < 0 ||
      PyDict_SetItemString(result, "options", rows) < 0 ||
      dict_set_string(result, "status", ierr ? "query_error" : "queried") < 0 ||
      dict_set_long(result, "query_error_code", (long)ierr) < 0) goto fail;
  Py_DECREF(rows);
  return result;

fail:
  Py_XDECREF(rows);
  Py_XDECREF(result);
  return NULL;
}

static PyObject *LUStageFactor_set_mumps_cntl(LUStageFactor *self,
                                              PyObject *args)
{
  PyObject *index_object = NULL;
  PyObject *value_object = NULL;
  PetscInt index = 0;
  PetscReal value;
  PetscErrorCode ierr;
  if (!PyArg_ParseTuple(args, "OO:set_mumps_cntl", &index_object,
                        &value_object))
    return NULL;
  if (!self->factor) {
    PyErr_SetString(PyExc_RuntimeError, "factor handle has been destroyed");
    return NULL;
  }
  if (self->symbolic_attempts) {
    PyErr_SetString(PyExc_RuntimeError,
                    "MUMPS controls cannot change after symbolic has started");
    return NULL;
  }
  if (mumps_control_index(index_object, "CNTL", &index) < 0) return NULL;
  value = (PetscReal)PyFloat_AsDouble(value_object);
  if (PyErr_Occurred()) return NULL;
  if (!isfinite((double)value)) {
    PyErr_SetString(PyExc_ValueError, "CNTL value must be finite");
    return NULL;
  }
  ierr = MatMumpsSetCntl(self->factor, index, value);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError,
                 "MatMumpsSetCntl failed: PETSc error %d", (int)ierr);
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *LUStageFactor_get_mumps_cntl(LUStageFactor *self,
                                              PyObject *args)
{
  PyObject *index_object = NULL;
  PetscInt index = 0;
  PetscReal value = 0.0;
  PetscErrorCode ierr;
  if (!PyArg_ParseTuple(args, "O:get_mumps_cntl", &index_object)) return NULL;
  if (!self->factor) {
    PyErr_SetString(PyExc_RuntimeError, "factor handle has been destroyed");
    return NULL;
  }
  if (mumps_control_index(index_object, "CNTL", &index) < 0) return NULL;
  ierr = MatMumpsGetCntl(self->factor, index, &value);
  if (ierr) {
    PyErr_Format(PyExc_RuntimeError,
                 "MatMumpsGetCntl failed: PETSc error %d", (int)ierr);
    return NULL;
  }
  return PyFloat_FromDouble((double)value);
}

static const char *info_label(int infog_api, int index)
{
  if (!infog_api && index == 3) return "local_complex_factor_entries";
  if (!infog_api && index == 4) return "local_integer_factor_entries";
  if (!infog_api && index == 15) return "local_symbolic_in_core_work_estimate";
  if (infog_api && index == 1) return "global_mumps_error_status";
  if (infog_api && index == 2) return "global_mumps_error_detail";
  if (infog_api && index == 3) return "global_complex_factor_entries";
  if (infog_api && index == 4) return "global_integer_factor_entries";
  if (infog_api && index == 16) return "global_max_symbolic_in_core_work_estimate";
  if (infog_api && index == 17) return "global_sum_symbolic_in_core_work_estimate";
  if (infog_api && index == 18)
    return "global_numeric_max_rank_allocated_memory";
  if (infog_api && index == 19)
    return "global_numeric_sum_ranks_allocated_memory";
  if (infog_api && index == 32) return "global_analysis_strategy";
  return "meaning_not_bound_by_this_record";
}

static const char *info_unit(int infog_api, int index)
{
  if ((!infog_api && index == 3) || (infog_api && index == 3))
    return "raw_entry_count_with_negative_million_encoding";
  if ((!infog_api && index == 4) || (infog_api && index == 4))
    return infog_api ? "raw_entry_count_with_negative_million_encoding"
                     : "raw_integer_entry_count";
  if ((!infog_api && index == 15) ||
      (infog_api && (index == 16 || index == 17 || index == 18 || index == 19)))
    return "million_bytes_10^6_bytes; raw integer retained";
  if (infog_api && index == 32)
    return "enum; 1=sequential,2=parallel; raw integer retained";
  return "unknown; raw integer retained; no conversion";
}

static const char *info_meaning_status(int infog_api, int index)
{
  if ((!infog_api && (index == 3 || index == 4 || index == 15)) ||
      (infog_api && (index == 1 || index == 2 || index == 3 || index == 4 ||
                     index == 16 || index == 17 || index == 18 || index == 19 ||
                     index == 32)))
    return "verified_against_MUMPS_5.6.2_user_guide";
  return "unknown_index_meaning_raw_preserved";
}

static PyObject *info_entry(LUStageFactor *self, int infog_api, int index)
{
  PetscInt raw = 0;
  PetscErrorCode ierr;
  PyObject *entry = PyDict_New();
  PyObject *value;
  if (!entry) return NULL;
  ierr = infog_api ? MatMumpsGetInfog(self->factor, (PetscInt)index, &raw)
                   : MatMumpsGetInfo(self->factor, (PetscInt)index, &raw);
  if (ierr) {
    value = Py_None;
    Py_INCREF(value);
  } else {
    value = PyLong_FromLongLong((long long)raw);
  }
  if (!value) {
    Py_DECREF(entry);
    return NULL;
  }
  if (PyDict_SetItemString(entry, "raw_value", value) < 0) {
    Py_DECREF(value);
    Py_DECREF(entry);
    return NULL;
  }
  Py_DECREF(value);
  if (dict_set_long(entry, "index", index) < 0 ||
      dict_set_long(entry, "query_error_code", (long)ierr) < 0 ||
      dict_set_string(entry, "api", infog_api ? "MatMumpsGetInfog" : "MatMumpsGetInfo") < 0 ||
      dict_set_string(entry, "label", info_label(infog_api, index)) < 0 ||
      dict_set_string(entry, "unit", info_unit(infog_api, index)) < 0 ||
      dict_set_string(entry, "meaning_status",
                      info_meaning_status(infog_api, index)) < 0 ||
      dict_set_string(entry, "scope",
                      infog_api
                          ? "MUMPS global field returned on this rank; do not sum replicated INFOG values across ranks"
                          : "MUMPS rank-local field queried from this calling rank") < 0) {
    Py_DECREF(entry);
    return NULL;
  }
  return entry;
}

static int append_info_entry(PyObject *list, LUStageFactor *self,
                             int global_scope, int index)
{
  PyObject *entry = info_entry(self, global_scope, index);
  int status;
  if (!entry) return -1;
  status = PyList_Append(list, entry);
  Py_DECREF(entry);
  return status;
}

static PyObject *LUStageFactor_analysis_info_raw(LUStageFactor *self,
                                                 PyObject *Py_UNUSED(ignored))
{
  static const int info_indices[] = {3, 4, 15};
  static const int infog_indices[] = {3, 4, 5, 6, 7, 16, 17, 32};
  PyObject *result = NULL;
  PyObject *info = NULL;
  PyObject *infog = NULL;
  PyObject *actual_value = NULL;
  PetscInt actual_icntl14 = 0;
  PetscErrorCode icntl_error;
  size_t i;

  if (!self->factor || !self->symbolic_completed) {
    PyErr_SetString(PyExc_RuntimeError,
                    "analysis INFO is available only after successful symbolic stage");
    return NULL;
  }
  if (self->numeric_attempts != 0) {
    PyErr_SetString(PyExc_RuntimeError,
                    "analysis INFO snapshot is unavailable after numeric was attempted");
    return NULL;
  }
  info = PyList_New(0);
  infog = PyList_New(0);
  result = PyDict_New();
  if (!info || !infog || !result) goto fail;

  icntl_error = MatMumpsGetIcntl(self->factor, 14, &actual_icntl14);
  if (icntl_error) {
    actual_value = Py_None;
    Py_INCREF(actual_value);
  } else {
    actual_value = PyLong_FromLong((long)actual_icntl14);
  }
  if (!actual_value) goto fail;
  {
    int set_status = PyDict_SetItemString(result, "icntl14_actual", actual_value);
    /* actual_value is owned in both branches above.  Consume that one owned
     * reference before branching so the shared failure path cannot DECREF it
     * a second time (and never treats borrowed Py_None as owned). */
    Py_CLEAR(actual_value);
    if (set_status < 0) goto fail;
  }

  for (i = 0; i < sizeof(info_indices) / sizeof(info_indices[0]); ++i) {
    if (append_info_entry(info, self, 0, info_indices[i]) < 0) goto fail;
  }
  for (i = 0; i < sizeof(infog_indices) / sizeof(infog_indices[0]); ++i) {
    if (append_info_entry(infog, self, 1, infog_indices[i]) < 0) goto fail;
  }
  if (PyDict_SetItemString(result, "INFO_api_raw_by_rank", info) < 0 ||
      PyDict_SetItemString(result, "INFOG_api_raw_by_rank", infog) < 0 ||
      dict_set_string(result, "rank_scope",
                      "each process queries its own factor handle; no cross-rank sum is performed") < 0 ||
      dict_set_string(result, "stage",
                      "after_MatLUFactorSymbolic_before_numeric") < 0 ||
      dict_set_string(result, "solver", "MATSOLVERMUMPS") < 0 ||
      dict_set_string(result, "factor_type", "MAT_FACTOR_LU") < 0 ||
      dict_set_petsc_int(result, "icntl14_requested",
                         self->icntl14_requested) < 0 ||
      dict_set_long(result, "icntl14_query_error_code",
                    (long)icntl_error) < 0 ||
      dict_set_string(result, "ordering_input",
                      "rowperm=NULL,colperm=NULL; actual public ICNTL(7)/(28) and post-analysis INFOG(7)/(32) are recorded separately") < 0 ||
      dict_set_string(result, "index_documentation_status",
                      "analysis indices INFO(3,4,15), INFOG(3,4,7,16,17,32), plus numeric INFOG(18,19), are verified against MUMPS 5.6.2 User Guide; all returned raw values are retained") < 0 ||
      dict_set_string(result, "documentation_source",
                      "MUMPS 5.6.2 User Guide pp. 93-94 and 97-99; Ubuntu source package mumps_5.6.2.orig.tar.gz SHA256 13a2c1aff2bd1aa92fe84b7b35d88f43434019963ca09ef7e8c90821a8f1d59a; PDF SHA256 32acdd3e09fb69f9fab16c94ae67768d15c61ac9c27abf66eb1e0e6ecd904050") < 0 ||
      dict_set_long(result, "numeric_attempts", self->numeric_attempts) < 0 ||
      dict_set_bool(result, "numeric_completed", self->numeric_completed) < 0 ||
      dict_set_none(result, "byte_estimate") < 0 ||
      dict_set_string(result, "interpretation_note",
                      "MUMPS 5.6.2 INFO(15)/INFOG(16,17) are documented in million bytes; raw integers remain unchanged and are not RSS upper bounds. Entry-count encodings are retained without decoding. No byte estimate is synthesized from unknown fields.") < 0) {
    goto fail;
  }
  Py_DECREF(info);
  Py_DECREF(infog);
  return result;

fail:
  Py_XDECREF(actual_value);
  Py_XDECREF(info);
  Py_XDECREF(infog);
  Py_XDECREF(result);
  return NULL;
}

static PyObject *LUStageFactor_destroy(LUStageFactor *self,
                                       PyObject *Py_UNUSED(ignored))
{
  if (self->factor) {
    self->destroy_attempts += 1;
    self->destroy_error_code = MatDestroy(&self->factor);
    if (!self->factor) release_source_keepalive_if_factor_gone(self);
    else if (!self->destroy_error_code) self->destroy_error_code = PETSC_ERR_PLIB;
  } else {
    self->factor_released = 1;
  }
  return lifecycle_dict(self);
}

static PyObject *module_numeric_event_count(PyObject *module,
                                            PyObject *Py_UNUSED(ignored))
{
  PyObject *result = PyDict_New();
  PetscLogEvent event = 0;
  PetscEventPerfInfo perf_info;
  PetscErrorCode ierr;
  (void)module;
  if (!result) return NULL;

#if defined(PETSC_USE_LOG)
  ierr = PetscLogEventGetId("MatLUFactorNum", &event);
  if (!ierr) ierr = PetscLogEventGetPerfInfo(PETSC_DETERMINE, event, &perf_info);
  if (dict_set_string(result, "event", "MatLUFactorNum") < 0 ||
      dict_set_string(result, "scope", "this MPI rank; PETSC_DETERMINE stage query") < 0 ||
      dict_set_bool(result, "compiled_with_logging", 1) < 0 ||
      dict_set_long(result, "query_error_code", (long)ierr) < 0 ||
      (ierr ? dict_set_none(result, "count") :
              dict_set_long(result, "count", (long)perf_info.count)) < 0) {
    Py_DECREF(result);
    return NULL;
  }
#else
  ierr = PETSC_ERR_SUP;
  if (dict_set_string(result, "event", "MatLUFactorNum") < 0 ||
      dict_set_string(result, "scope", "this MPI rank; PETSc built without event logging") < 0 ||
      dict_set_bool(result, "compiled_with_logging", 0) < 0 ||
      dict_set_long(result, "query_error_code", (long)ierr) < 0 ||
      dict_set_none(result, "count") < 0) {
    Py_DECREF(result);
    return NULL;
  }
#endif
  return result;
}

static PyObject *LUStageFactor_numeric_info_raw(LUStageFactor *self,
                                                PyObject *Py_UNUSED(ignored))
{
  static const int infog_indices[] = {1, 2, 18, 19};
  PyObject *result = NULL;
  PyObject *infog = NULL;
  size_t i;
  if (!self->factor || self->numeric_attempts < 1) {
    PyErr_SetString(PyExc_RuntimeError,
                    "numeric INFO requires a live factor after a numeric attempt");
    return NULL;
  }
  infog = PyList_New(0);
  result = PyDict_New();
  if (!infog || !result) goto fail;
  for (i = 0; i < sizeof(infog_indices) / sizeof(infog_indices[0]); ++i) {
    if (append_info_entry(infog, self, 1, infog_indices[i]) < 0) goto fail;
  }
  if (PyDict_SetItemString(result, "INFOG_api_raw_by_rank", infog) < 0 ||
      dict_set_string(result, "stage",
                      "after_MatLUFactorNumeric_attempt") < 0 ||
      dict_set_bool(result, "numeric_completed", self->numeric_completed) < 0 ||
      dict_set_long(result, "numeric_attempts", self->numeric_attempts) < 0 ||
      dict_set_long(result, "numeric_error_code",
                    (long)self->numeric_error_code) < 0 ||
      dict_set_string(result, "documentation_source",
                      "MUMPS 5.6.2 User Guide pp. 93-94 and 97-99; Ubuntu source package mumps_5.6.2.orig.tar.gz SHA256 13a2c1aff2bd1aa92fe84b7b35d88f43434019963ca09ef7e8c90821a8f1d59a; PDF SHA256 32acdd3e09fb69f9fab16c94ae67768d15c61ac9c27abf66eb1e0e6ecd904050") < 0 ||
      dict_set_string(result, "interpretation_note",
                      "MUMPS 5.6.2 INFOG(18) is numeric allocated memory on the maximum-memory rank and INFOG(19) is the sum across ranks, both in million bytes. Values are returned on each rank and must not be summed again across ranks. Raw values are retained; they are not process RSS or a hard memory bound.") < 0) {
    goto fail;
  }
  Py_DECREF(infog);
  return result;

fail:
  Py_XDECREF(infog);
  Py_XDECREF(result);
  return NULL;
}

static PyMethodDef LUStageFactor_methods[] = {
  {"symbolic", (PyCFunction)LUStageFactor_symbolic, METH_NOARGS,
   "Run MatLUFactorSymbolic only."},
  {"numeric", (PyCFunction)LUStageFactor_numeric, METH_NOARGS,
   "Run MatLUFactorNumeric explicitly after symbolic."},
  {"solve", (PyCFunction)LUStageFactor_solve, METH_VARARGS,
   "Solve with an explicitly numerically factored matrix."},
  {"solve_transpose", (PyCFunction)LUStageFactor_solve_transpose, METH_VARARGS,
   "Solve the transposed system with the existing numeric factor."},
  {"mat_solve", (PyCFunction)LUStageFactor_mat_solve, METH_VARARGS,
   "Solve multiple RHS columns with the existing numeric factor."},
  {"mat_solve_transpose", (PyCFunction)LUStageFactor_mat_solve_transpose,
   METH_VARARGS,
   "Solve multiple transposed RHS columns with the existing numeric factor."},
  {"layout_raw", (PyCFunction)LUStageFactor_layout_raw, METH_NOARGS,
   "Read public PETSc global/local sizes and ownership ranges."},
  {"release_source_keepalive",
   (PyCFunction)LUStageFactor_release_source_keepalive, METH_NOARGS,
   "Drop the retained source Python wrapper after numeric factorization."},
  {"set_mumps_icntl", (PyCFunction)LUStageFactor_set_mumps_icntl,
   METH_VARARGS, "Set one explicit MUMPS ICNTL before symbolic analysis."},
  {"get_mumps_icntl", (PyCFunction)LUStageFactor_get_mumps_icntl,
   METH_VARARGS, "Read back one MUMPS ICNTL from the live factor."},
  {"mumps_options_raw", (PyCFunction)LUStageFactor_mumps_options_raw,
   METH_NOARGS,
   "Read the factor prefix, matrix types, communicator, and MUMPS option overrides through public PETSc APIs."},
  {"set_mumps_cntl", (PyCFunction)LUStageFactor_set_mumps_cntl,
   METH_VARARGS, "Set one explicit MUMPS CNTL before symbolic analysis."},
  {"get_mumps_cntl", (PyCFunction)LUStageFactor_get_mumps_cntl,
   METH_VARARGS, "Read back one MUMPS CNTL from the live factor."},
  {"analysis_info_raw", (PyCFunction)LUStageFactor_analysis_info_raw, METH_NOARGS,
   "Read raw MUMPS INFO/INFOG values after symbolic and before numeric."},
  {"numeric_info_raw", (PyCFunction)LUStageFactor_numeric_info_raw, METH_NOARGS,
   "Read raw MUMPS INFOG numeric-stage memory fields after numeric attempt."},
  {"lifecycle", (PyCFunction)LUStageFactor_lifecycle, METH_NOARGS,
   "Return factor ownership and staged-call status."},
  {"destroy", (PyCFunction)LUStageFactor_destroy, METH_NOARGS,
   "Attempt MatDestroy and return the actual cleanup status."},
  {NULL, NULL, 0, NULL}
};

static PyObject *module_create_lu_stage(PyObject *module, PyObject *args,
                                        PyObject *kwargs)
{
  static char *keywords[] = {"source", "icntl14", NULL};
  PyObject *source_object = NULL;
  PyObject *icntl_object = NULL;
  long long icntl14;
  PetscInt actual_icntl14 = 0;
  PetscBool available = PETSC_FALSE;
  PetscErrorCode ierr;
  LUStageFactor *factor;

  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO:create_lu_stage", keywords,
                                  &source_object, &icntl_object)) return NULL;
  if (!PyObject_TypeCheck(source_object, petsc_mat_python_type)) {
    PyErr_SetString(PyExc_TypeError, "source must be a petsc4py Mat object");
    return NULL;
  }
  if (PyBool_Check(icntl_object) || !PyLong_Check(icntl_object)) {
    PyErr_SetString(PyExc_TypeError, "icntl14 must be an explicit non-bool integer");
    return NULL;
  }
  icntl14 = PyLong_AsLongLong(icntl_object);
  if (PyErr_Occurred()) return NULL;
  if (icntl14 < 0 || icntl14 > (long long)PETSC_MAX_INT) {
    PyErr_SetString(PyExc_ValueError, "icntl14 is outside the installed PetscInt range");
    return NULL;
  }

  factor = PyObject_New(LUStageFactor, &LUStageFactorType);
  if (!factor) return NULL;
  memset(((char *)factor) + sizeof(PyObject), 0,
         sizeof(LUStageFactor) - sizeof(PyObject));
  factor->source_keepalive = source_object;
  Py_INCREF(source_object);
  factor->source = PyPetscMat_Get(source_object);
  factor->icntl14_requested = (PetscInt)icntl14;
  if (!factor->source) {
    PyErr_SetString(PyExc_ValueError, "source PETSc Mat has been destroyed");
    Py_DECREF((PyObject *)factor);
    return NULL;
  }

  ierr = MatFactorInfoInitialize(&factor->factor_info);
  if (!ierr) {
    ierr = MatGetFactorAvailable(factor->source, MATSOLVERMUMPS,
                                 MAT_FACTOR_LU, &available);
  }
  if (!ierr && !available) ierr = PETSC_ERR_SUP;
  if (!ierr) {
    ierr = MatGetFactor(factor->source, MATSOLVERMUMPS, MAT_FACTOR_LU,
                        &factor->factor);
  }
  if (!ierr) {
    ierr = MatMumpsSetIcntl(factor->factor, 14,
                            factor->icntl14_requested);
  }
  if (!ierr) {
    ierr = MatMumpsGetIcntl(factor->factor, 14, &actual_icntl14);
    factor->icntl14_error_code = ierr;
    if (!ierr) {
      factor->icntl14_actual = actual_icntl14;
      if (actual_icntl14 != factor->icntl14_requested) {
        factor->icntl14_error_code = PETSC_ERR_ARG_INCOMP;
        ierr = PETSC_ERR_ARG_INCOMP;
      }
    }
  } else {
    factor->icntl14_error_code = ierr;
  }
  if (ierr) {
    if (factor->factor) MatDestroy(&factor->factor);
    if (!factor->factor) release_source_keepalive_if_factor_gone(factor);
    Py_DECREF((PyObject *)factor);
    PyErr_Format(PyExc_RuntimeError,
                 "MUMPS LU factor creation/ICNTL(14) setup or read-back failed: PETSc error %d",
                 (int)ierr);
    return NULL;
  }
  return (PyObject *)factor;
}

static PyMethodDef module_methods[] = {
  {"create_lu_stage", (PyCFunction)(void(*)(void))module_create_lu_stage,
   METH_VARARGS | METH_KEYWORDS,
   "Create a MUMPS LU factor with an explicit ICNTL(14); no factorization runs."},
  {"numeric_event_count_raw", (PyCFunction)module_numeric_event_count, METH_NOARGS,
   "Read this rank's PETSc MatLUFactorNum event count without synthesizing a value."},
  {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module_definition = {
  PyModuleDef_HEAD_INIT,
  "petsc_lu_stage_bridge",
  "Small public-PETSc-API bridge for separate MUMPS LU symbolic/numeric stages.",
  -1,
  module_methods,
  NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC PyInit_petsc_lu_stage_bridge(void)
{
  PyObject *module = NULL;
  if (import_petsc4py() < 0) return NULL;
  petsc_mat_python_type = &PyPetscMat_Type;
  petsc_vec_python_type = &PyPetscVec_Type;

  LUStageFactorType.tp_name = "petsc_lu_stage_bridge.LUStageFactor";
  LUStageFactorType.tp_basicsize = sizeof(LUStageFactor);
  LUStageFactorType.tp_flags = Py_TPFLAGS_DEFAULT;
  LUStageFactorType.tp_doc = "Owned staged MUMPS factor; source Mat is borrowed.";
  LUStageFactorType.tp_methods = LUStageFactor_methods;
  LUStageFactorType.tp_dealloc = (destructor)LUStageFactor_dealloc;
  if (PyType_Ready(&LUStageFactorType) < 0) goto fail;

  module = PyModule_Create(&module_definition);
  if (!module) goto fail;
  Py_INCREF(&LUStageFactorType);
  if (PyModule_AddObject(module, "LUStageFactor",
                         (PyObject *)&LUStageFactorType) < 0) {
    Py_DECREF(&LUStageFactorType);
    goto fail;
  }
  if (PyModule_AddIntConstant(module, "petsc_int_sizeof",
                              (long)sizeof(PetscInt)) < 0 ||
      PyModule_AddIntConstant(module, "petsc_scalar_sizeof",
                              (long)sizeof(PetscScalar)) < 0 ||
      PyModule_AddIntConstant(module, "petsc_version_major",
                              PETSC_VERSION_MAJOR) < 0 ||
      PyModule_AddIntConstant(module, "petsc_version_minor",
                              PETSC_VERSION_MINOR) < 0 ||
      PyModule_AddIntConstant(module, "petsc_version_subminor",
                              PETSC_VERSION_SUBMINOR) < 0 ||
      PyModule_AddIntConstant(module, "mumps_package_version_major",
                              PETSC_PKG_MUMPS_VERSION_MAJOR) < 0 ||
      PyModule_AddIntConstant(module, "mumps_package_version_minor",
                              PETSC_PKG_MUMPS_VERSION_MINOR) < 0 ||
      PyModule_AddIntConstant(module, "mumps_package_version_subminor",
                              PETSC_PKG_MUMPS_VERSION_SUBMINOR) < 0) {
    goto fail;
  }
#if defined(PETSC_USE_COMPLEX)
  if (PyModule_AddIntConstant(module, "petsc_complex_scalar", 1) < 0)
    goto fail;
#else
  if (PyModule_AddIntConstant(module, "petsc_complex_scalar", 0) < 0)
    goto fail;
#endif
  return module;

fail:
  Py_XDECREF(module);
  return NULL;
}
