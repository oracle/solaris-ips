/*
 * CDDL HEADER START
 *
 * The contents of this file are subject to the terms of the
 * Common Development and Distribution License (the "License").
 * You may not use this file except in compliance with the License.
 *
 * You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
 * or http://www.opensolaris.org/os/licensing.
 * See the License for the specific language governing permissions
 * and limitations under the License.
 *
 * When distributing Covered Code, include this CDDL HEADER in each
 * file and include the License file at usr/src/OPENSOLARIS.LICENSE.
 * If applicable, add the following below this CDDL HEADER, with the
 * fields enclosed by brackets "[]" replaced with your own identifying
 * information: Portions Copyright [yyyy] [name of copyright owner]
 *
 * CDDL HEADER END
 */

/*
 * Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
 */

#include <Python.h>

#include <sys/types.h>
#include <stdlib.h>

#include "solver.h"

typedef void
confunc_t(void *ptr, void *userarg);

typedef struct
{
	int capacity;
	int cnt;
	void **buffer;
} container_t;

/*
 * create a container
 */

static inline container_t *
con_alloc(int initial_capacity)
{
	container_t *ptr = (container_t *) malloc(sizeof (container_t));
	ptr->capacity = initial_capacity;
	ptr->buffer = malloc(sizeof (void *) * ptr->capacity);
	ptr->cnt = 0;
	return (ptr);
}

/*
 * add a pointer to a container
 */

static inline void
con_addptr(container_t *container, void *ptr)
{
	if (container->cnt == container->capacity)
		container->buffer = realloc(container->buffer,
		    sizeof (void *) * (container->capacity += 1000));
	container->buffer[container->cnt++] = ptr;
}

/*
 * iterate over the void pointers in a container
 */

static inline void
con_iterptrs(container_t *container, void *usr_arg, confunc_t *func)
{
	int i;
	for (i = 0; i < container->cnt; i++)
		func(container->buffer[i], usr_arg);
}

/*
 * delete a container
 */

static inline void
con_delete(container_t *container)
{
	free(container->buffer);
	free((void *) container);
}

/* 
 * allocate a ref-cnted pointer to a chunk of memory of specified size
 * returns w/ refcnt set to 1.  Be able to retrieve size.
 */

static inline void *
alloc_refcntptr(size_t size)
{
	long *ptr = malloc(size + sizeof (long) *2);
	*ptr++ = size;
	*ptr++ = 1;
	return ((void *) ptr);
}

/*
 * increment reference count on refcnted pointer
 */

static inline void *
inc_refcntptr(void *ptr)
{
	long *lptr = (long *) ptr;

	lptr[-1]++;

	return (ptr);
}

/*
 * decrement (and free if needed) refcnted pointer
 */

static inline void
dec_refcntptr(void *ptr)
{
	long *lptr = (long *) ptr;

	if (--(lptr[-1]) == 0)
		free((void*) (lptr - 2));
}

static inline long
size_refcntptr(void *ptr)
{
	long *lptr = (long *) ptr;
	return (lptr[-2]);
}


/*
 * routines dealing explicitly w/ containers of refcnted pointers
 */

/*
 * duplicate a container of refcnted pointers
 */

static inline void
cpyptr(void *ptr, void *usr)
{
	con_addptr((container_t *) usr, inc_refcntptr(ptr));
}

/*ARGSUSED*/
static inline void
decptr(void *ptr, void *usr)
{
	dec_refcntptr(ptr);
}

static inline container_t *
refcntcon_dup(container_t *old)
{
	container_t *new = con_alloc(old->capacity);
	con_iterptrs(old, new, cpyptr);
	return (new);
}

static inline void
refcntcon_del(container_t *old)
{
	if (old != NULL) {
		con_iterptrs(old, NULL, decptr);
		con_delete(old);
	}
}

#define RETURN_NEEDS_RESET BAILOUT(PyExc_RuntimeError, "msat_solver failed; reset needed")
#define RETURN_NEEDS_INTLIST BAILOUT(PyExc_TypeError, "List of integers expected")
#define RETURN_NOT_SOLVER BAILOUT(PyExc_TypeError, "msat_solver expected")

#define BAILOUT(exception, string) {PyErr_SetString(exception, string); return (NULL);}


#if PY_MAJOR_VERSION >= 3
# define PyInt_AsLong PyLong_AsLong
#endif

typedef struct
{
	PyObject_HEAD
	solver *msat_instance;
	int msat_needs_reset;
	container_t *msat_clauses;
} msat_solver;


static void msat_dealloc(msat_solver *self);
extern PyMethodDef msat_methods[];
static int msat_init(msat_solver * self, PyObject *args, PyObject *kwds);
static PyObject *
msat_new(PyTypeObject *type, PyObject *args, PyObject *kwds);

static PyTypeObject minisat_solvertype = {
#if PY_MAJOR_VERSION >= 3
	PyVarObject_HEAD_INIT(NULL, 0)
#else
	PyObject_HEAD_INIT(NULL)
	0, /*ob_size*/
#endif
	"solver.msat_solver", /*tp_name*/
	sizeof (msat_solver), /*tp_basicsize*/
	0, /*tp_itemsize*/
	(destructor) msat_dealloc, /*tp_dealloc*/
	0, /*tp_print*/
	0, /*tp_getattr*/
	0, /*tp_setattr*/
	0, /*tp_compare*/
	0, /*tp_repr*/
	0, /*tp_as_number*/
	0, /*tp_as_sequence*/
	0, /*tp_as_mapping*/
	0, /*tp_hash */
	0, /*tp_call*/
	0, /*tp_str*/
	0, /*tp_getattro*/
	0, /*tp_setattro*/
	0, /*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT, /*tp_flags*/
	"msat_solver object", /*tp_doc*/
	0, /*tp_traverse*/
	0, /*tp_clear*/
	0, /*tp_richcompare*/
	0, /*tp_weaklistoffset*/
	0, /*tp_iter*/
	0, /*tp_iternext*/
	msat_methods, /*tp_methods*/
	0, /*tp_members*/
	0, /*tp_getset*/
	0, /*tp_base*/
	0, /*tp_dict*/
	0, /*tp_descr_get*/
	0, /*tp_descr_set*/
	0, /*tp_dictoffset*/
	(initproc) msat_init, /*tp_init*/
	0, /*tp_alloc*/
	msat_new /*tp_new*/
};

/*ARGSUSED*/
static void
msat_dealloc(msat_solver *self)
{
	refcntcon_del(self->msat_clauses);
	if (self->msat_instance != NULL) 
		solver_delete(self->msat_instance);
#if PY_MAJOR_VERSION >= 3
	Py_TYPE(self)->tp_free((PyObject*) self);
#else
	self->ob_type->tp_free((PyObject*) self);
#endif
}

static void
add_clauses(void *ptr, void *arg)
{
	msat_solver *self = (msat_solver *) arg;
	lbool ret = solver_addclause(self->msat_instance,
	    (lit*) ptr, (lit*) ((char *) ptr + size_refcntptr(ptr)));

	if (ret == l_False)
		self->msat_needs_reset = 1;
}

/*ARGSUSED*/
static PyObject *
msat_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	msat_solver *self;
	msat_solver *prototype_solver;
	int arg_count = PyTuple_Size(args);

	if ((self = (msat_solver *) type->tp_alloc(type, 0)) == NULL)
		return (NULL);
	
	/*
	 * we optionally allow another server instance
	 * to be passed in to initialize the new solver
	 */
	switch (arg_count) {
	case 0:
		if ((self->msat_instance = solver_new()) == NULL) {
			Py_DECREF(self);
			return (NULL);
		}
		self->msat_instance->verbosity = 0;
		self->msat_needs_reset = 0;
		self->msat_clauses = con_alloc(1000);
		return (PyObject *) self;
	case 1:
		prototype_solver = (msat_solver *) PyTuple_GetItem(args, 0);
		if (prototype_solver == NULL) {
			Py_DECREF(self);
			return (NULL);
		}
		if (!PyObject_TypeCheck((PyObject *) prototype_solver,
		    &minisat_solvertype)) {
			Py_DECREF(self);
			RETURN_NOT_SOLVER;
		}
		if (prototype_solver->msat_needs_reset != 0) {
			Py_DECREF(self);
			RETURN_NEEDS_RESET;
		}
		self->msat_instance = solver_new();
		self->msat_instance->verbosity =
		    prototype_solver->msat_instance->verbosity;
		self->msat_clauses =
		    refcntcon_dup(prototype_solver->msat_clauses);
		self->msat_needs_reset = 0;
		con_iterptrs(self->msat_clauses, self, add_clauses);
		return (PyObject *) self;
	default:
		RETURN_NOT_SOLVER;
	}

}

/*ARGSUSED*/
static int
msat_init(msat_solver * self, PyObject *args, PyObject *kwds)
{
	return (0);
}

/*ARGSUSED*/
static PyObject *
msat_reset(msat_solver *self, PyObject *args)
{
	int v = self->msat_instance->verbosity;
	solver_delete(self->msat_instance);
	self->msat_instance = solver_new();
	self->msat_needs_reset = 0;
	self->msat_instance->verbosity = v;
	Py_RETURN_NONE;
}

static PyObject *
msat_set_verbosity(msat_solver *self, PyObject *args)
{
	int index;

	if (!PyArg_ParseTuple(args, "i", &index))
		return (NULL);

	self->msat_instance->verbosity = index;

	Py_RETURN_NONE;
}

static PyObject *
msat_adjust(msat_solver *self, PyObject *args)
{
	int index;

	if (!PyArg_ParseTuple(args, "i", &index))
		return (NULL);
	solver_setnvars(self->msat_instance, index);

	Py_RETURN_NONE;
}

/*ARGSUSED*/
static PyObject *
msat_get_variables(msat_solver *self, PyObject *args)
{
	if (self->msat_needs_reset)
		RETURN_NEEDS_RESET;

	return (Py_BuildValue("i", solver_nvars(self->msat_instance)));
}

/*ARGSUSED*/
static PyObject *
msat_get_added_clauses(msat_solver *self, PyObject *args)
{
	return (Py_BuildValue("i", solver_nclauses(self->msat_instance)));
}

static int *
msat_unpack_integers(PyObject *list, int *nout)
{
	int i;
	int n;
	int *is;

	if (!PyList_Check(list))
		RETURN_NEEDS_INTLIST;

	n = PyList_Size(list);

	if ((is = (int *) alloc_refcntptr(n * sizeof (int))) == NULL) {
		PyErr_NoMemory();
		return (NULL);
	}

	/* each iteration: minisat_add(int) */
	for (i = 0; i < n; i++) {
		int l;
		int v;

		if ((l = PyInt_AsLong(PyList_GetItem(list, i))) == -1
		&& PyErr_Occurred()) {
			dec_refcntptr(is);
			RETURN_NEEDS_INTLIST;
		}

		v = abs(l) - 1;
		is[i] = (l > 0) ? toLit(v) : lit_neg(toLit(v));
	}

	*nout = n;
	return (is);
}

/*ARGSUSED*/
static PyObject *
msat_add_clause(msat_solver *self, PyObject *args)
{
	int *is;
	int n;
	lbool ret;
	PyObject *list;

	if (self->msat_needs_reset)
		RETURN_NEEDS_RESET;

	if (!PyArg_ParseTuple(args, "O", &list))
		return (NULL);

	if ((is = msat_unpack_integers(list, &n)) == NULL)
		return (NULL);

	con_addptr(self->msat_clauses, is);

	if (n == 0) {
		dec_refcntptr(is);
		RETURN_NEEDS_INTLIST;
	}

	ret = solver_addclause(self->msat_instance, is, &(is[n]));

	if (ret == l_True)
		Py_RETURN_TRUE;
	else if (ret == l_False) {
		self->msat_needs_reset = 1;
		Py_RETURN_FALSE;
	}

	Py_RETURN_NONE;
}

static PyObject *
msat_solve(msat_solver *self, PyObject *args, PyObject *keywds)
{
	int *as;
	int *as_top;
	int n;
	PyObject *assume;
	lbool ret;
	int limit;

	static char *kwlist[] = {"assume", "limit", NULL};

	if (self->msat_needs_reset)
		RETURN_NEEDS_RESET;

	if (!PyArg_ParseTupleAndKeywords(args, keywds, "|Oi", kwlist,
	&assume, &limit))
		return (NULL);

	if ((as = msat_unpack_integers(assume, &n)) == NULL)
		return (NULL);

	if (n > 0) {
		as_top = &(as[n]);
	} else {
		dec_refcntptr(as);
		as = NULL;
		as_top = NULL;
	}

	ret = solver_solve(self->msat_instance, as, as_top);

	if (as != NULL)
		dec_refcntptr(as);

	if (ret)
		Py_RETURN_TRUE;
	else {
		self->msat_needs_reset = 1;
		Py_RETURN_FALSE;
	}
}

static PyObject *
msat_dereference(msat_solver *self, PyObject *args)
{
	int literal;

	if (self->msat_needs_reset)
		RETURN_NEEDS_RESET;

	if (!PyArg_ParseTuple(args, "i", &literal))
		return (NULL);

	if (self->msat_instance->model.ptr[literal] == l_True)
		Py_RETURN_TRUE;

	Py_RETURN_FALSE;
}

/*
 * Should we provide enough Python to allow the use of a higher level function
 * to build clauses, or should we just leave that to the caller?
 */

PyMethodDef msat_methods[] = {
	{ "reset", (PyCFunction) msat_reset,
		METH_VARARGS,
		"Reset solver after solution failure"},
	{ "set_verbose", (PyCFunction) msat_set_verbosity,
		METH_VARARGS,
		"specify level of debugging output"},
	{ "hint_variables", (PyCFunction) msat_adjust,
		METH_VARARGS, NULL},
	{ "get_variables", (PyCFunction) msat_get_variables,
		METH_VARARGS, NULL},
	{ "get_added_clauses", (PyCFunction) msat_get_added_clauses,
		METH_VARARGS, NULL},
	{ "add_clause", (PyCFunction) msat_add_clause,
		METH_VARARGS,
		"Add another clause (as list of integers) to solution space"},
	{ "solve", (PyCFunction) msat_solve,
		METH_VARARGS | METH_KEYWORDS,
		"Attempt to satisfy current clauses and assumptions."},
	{ "dereference", (PyCFunction) msat_dereference,
		METH_VARARGS,
		"Retrieve literal value in solution, if available after solve "
		"attempt."},
	{ NULL, NULL, 0, NULL}
};


static PyMethodDef no_module_methods[] = {
	{NULL} /* Sentinel */
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef solvermodule ={
	PyModuleDef_HEAD_INIT,
	"solver",
	NULL,
	-1,
	msat_methods
};
#endif

static PyObject *
moduleinit()
{
	PyObject *m;

	if (PyType_Ready(&minisat_solvertype) < 0)
		return NULL;
#if PY_MAJOR_VERSION >= 3
	m = PyModule_Create(&solvermodule);
#else
	m = Py_InitModule3("solver", no_module_methods,
	    "MINISAT SAT solver module");
#endif
	Py_INCREF(&minisat_solvertype);
	PyModule_AddObject(m, "msat_solver", (PyObject*) &minisat_solvertype);
	return m;
}

#if PY_MAJOR_VERSION >= 3
PyMODINIT_FUNC
PyInit_solver(void)
{
	return moduleinit();
}
#else
PyMODINIT_FUNC
initsolver(void)
{
	moduleinit();
}
#endif
