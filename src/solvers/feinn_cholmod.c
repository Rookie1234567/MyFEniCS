/* Small ABI boundary to the installed CHOLMOD. No Maxwell matrix enters it. */
#include <cholmod.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    cholmod_common common;
    cholmod_sparse *a;
    cholmod_factor *l;
    size_t n;
} riesz_handle;

void riesz_free(void *opaque) {
    riesz_handle *h = opaque;
    if (!h) return;
    if (h->l) cholmod_l_free_factor(&h->l, &h->common);
    if (h->a) cholmod_l_free_sparse(&h->a, &h->common);
    cholmod_l_finish(&h->common);
    free(h);
}

void *riesz_symbolic(int64_t n, int64_t nnz, const int64_t *p,
                     const int64_t *i, const double *x) {
    riesz_handle *h = calloc(1, sizeof(*h));
    if (!h) return NULL;
    cholmod_l_start(&h->common);
    h->common.print = 0;
    h->common.nmethods = 1;
    h->common.method[0].ordering = CHOLMOD_AMD;
    h->common.supernodal = CHOLMOD_SIMPLICIAL;
    h->common.final_ll = 1;
    h->common.final_pack = 1;
    h->n = n;
    h->a = cholmod_l_allocate_sparse(n, n, nnz, 1, 1, 1,
                                    CHOLMOD_COMPLEX, &h->common);
    if (!h->a) { riesz_free(h); return NULL; }
    memcpy(h->a->p, p, (n+1)*sizeof(int64_t));
    memcpy(h->a->i, i, nnz*sizeof(int64_t));
    memcpy(h->a->x, x, 2*nnz*sizeof(double));
    h->l = cholmod_l_analyze(h->a, &h->common);
    if (!h->l || h->common.status < CHOLMOD_OK) {
        riesz_free(h); return NULL;
    }
    return h;
}

void riesz_stats(void *opaque, double *out) {
    riesz_handle *h = opaque;
    out[0] = h->common.lnz;
    out[1] = h->common.fl;
    out[2] = h->common.memory_inuse;
    out[3] = h->common.memory_usage;
    out[4] = h->l->nzmax;
    out[5] = h->l->minor;
    out[6] = h->common.status;
}

int riesz_numeric(void *opaque) {
    riesz_handle *h = opaque;
    int ok = cholmod_l_factorize(h->a, h->l, &h->common);
    return ok && h->l->minor == h->n && h->common.status == CHOLMOD_OK;
}

int riesz_solve(void *opaque, const double *rhs, double *out) {
    riesz_handle *h = opaque;
    cholmod_dense *b = cholmod_l_allocate_dense(h->n, 1, h->n,
                                               CHOLMOD_COMPLEX, &h->common);
    if (!b) return 0;
    memcpy(b->x, rhs, 2*h->n*sizeof(double));
    cholmod_dense *q = cholmod_l_solve(CHOLMOD_A, h->l, b, &h->common);
    if (q) memcpy(out, q->x, 2*h->n*sizeof(double));
    int ok = q && h->common.status == CHOLMOD_OK;
    cholmod_l_free_dense(&b, &h->common);
    if (q) cholmod_l_free_dense(&q, &h->common);
    return ok;
}
