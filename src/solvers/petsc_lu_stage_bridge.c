#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <limits.h>
#include <string.h>

#include <petscmat.h>
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
      dict_set_long(result, "icntl14_requested",
                    (long)self->icntl14_requested) < 0 ||
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
  if (!self->factor && self->source_keepalive) {
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
  release_source_keepalive_if_factor_gone(self);
  Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *LUStageFactor_lifecycle(LUStageFactor *self,
                                         PyObject *Py_UNUSED(ignored))
{
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

static const char *info_label(int index)
{
  (void)index;
  return "unknown; raw index/value retained pending installed-version documentation";
}

static const char *info_unit(int index)
{
  (void)index;
  return "unknown; raw integer only, no byte conversion";
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
      dict_set_string(entry, "label", info_label(index)) < 0 ||
      dict_set_string(entry, "unit", info_unit(index)) < 0 ||
      dict_set_string(entry, "meaning_status", "unknown_for_installed_MUMPS_version") < 0 ||
      dict_set_string(entry, "scope",
                      "raw value returned by the named API on the calling MPI rank") < 0) {
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
  static const int info_indices[] = {3, 4};
  static const int infog_indices[] = {3, 4, 5, 6, 7, 16, 17};
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
      dict_set_long(result, "icntl14_requested",
                    (long)self->icntl14_requested) < 0 ||
      dict_set_long(result, "icntl14_query_error_code",
                    (long)icntl_error) < 0 ||
      dict_set_string(result, "ordering_input",
                      "rowperm=NULL,colperm=NULL; MUMPS/PETSc backend default") < 0 ||
      dict_set_string(result, "index_documentation_status",
                      "raw indices requested; per-index meaning not bound to installed MUMPS 5.6.2 documentation") < 0 ||
      dict_set_long(result, "numeric_attempts", self->numeric_attempts) < 0 ||
      dict_set_bool(result, "numeric_completed", self->numeric_completed) < 0 ||
      dict_set_none(result, "byte_estimate") < 0 ||
      dict_set_string(result, "interpretation_note",
                      "INFO/INFOG index meanings and units are not bound without installed-version documentation; raw values are preserved, zero is not called 0B, and no byte estimate is derived.") < 0) {
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

static PyMethodDef LUStageFactor_methods[] = {
  {"symbolic", (PyCFunction)LUStageFactor_symbolic, METH_NOARGS,
   "Run MatLUFactorSymbolic only."},
  {"numeric", (PyCFunction)LUStageFactor_numeric, METH_NOARGS,
   "Run MatLUFactorNumeric explicitly after symbolic."},
  {"solve", (PyCFunction)LUStageFactor_solve, METH_VARARGS,
   "Solve with an explicitly numerically factored matrix."},
  {"analysis_info_raw", (PyCFunction)LUStageFactor_analysis_info_raw, METH_NOARGS,
   "Read raw MUMPS INFO/INFOG values after symbolic and before numeric."},
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
  if (ierr) {
    if (factor->factor) MatDestroy(&factor->factor);
    if (!factor->factor) release_source_keepalive_if_factor_gone(factor);
    Py_DECREF((PyObject *)factor);
    PyErr_Format(PyExc_RuntimeError,
                 "MUMPS LU factor creation/ICNTL(14) setup failed: PETSc error %d",
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
  return module;

fail:
  Py_XDECREF(module);
  return NULL;
}
