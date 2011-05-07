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
 * Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
 */

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <Python.h>

PyDoc_STRVAR(pmkdirat_doc,
"mkdirat(fd, path, mode)\n\
\n\
Invoke mkdirat(2).");

/*ARGSUSED*/
static PyObject *
pmkdirat(PyObject *self, PyObject *args)
{
	int		fd, rv;
	char		*path;
	mode_t		mode;

	rv = PyArg_ParseTuple(args, "isI", &fd, &path, &mode);
	if (rv == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}

	rv = mkdirat(fd, path, mode);
	if (rv != 0)
		return PyErr_SetFromErrno(PyExc_OSError);

	Py_RETURN_NONE;
}

PyDoc_STRVAR(popenat_doc,
"openat(fd, path, oflag, mode) -> fd\n\
\n\
Invoke openat(2).");

/*ARGSUSED*/
static PyObject *
popenat(PyObject *self, PyObject *args, PyObject *kwds)
{
	int		fd, oflag, rv;
	char		*path;
	mode_t		mode;

	/* Python based arguments to this function */
	static char	*kwlist[] = {"fd", "path", "oflag", "mode", NULL};

	rv = PyArg_ParseTupleAndKeywords(args, kwds, "isiI", kwlist,
	    &fd, &path, &oflag, &mode);
	if (rv == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}

	rv = openat(fd, path, oflag, mode);
	if (rv < 0)
		return PyErr_SetFromErrno(PyExc_OSError);

	return (PyInt_FromLong(rv));
}

PyDoc_STRVAR(prenameat_doc,
"renameat(fromfd, old, tofd, new)\n\
\n\
Invoke renameat(2).");

/*ARGSUSED*/
static PyObject *
prenameat(PyObject *self, PyObject *args)
{
	int		fromfd, tofd, rv;
	char		*old, *new;

	rv = PyArg_ParseTuple(args, "isis", &fromfd, &old, &tofd, &new);
	if (rv == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}

	rv = renameat(fromfd, old, tofd, new);
	if (rv != 0)
		return PyErr_SetFromErrno(PyExc_OSError);

	Py_RETURN_NONE;
}

PyDoc_STRVAR(punlinkat_doc,
"unlinkat(fd, path, flag)\n\
\n\
Invoke unlinkat(2).");

/*ARGSUSED*/
static PyObject *
punlinkat(PyObject *self, PyObject *args)
{
	int		fd, flags, rv;
	char		*path;

	rv = PyArg_ParseTuple(args, "isi", &fd, &path, &flags);
	if (rv == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}

	rv = unlinkat(fd, path, flags);
	if (rv != 0)
		return PyErr_SetFromErrno(PyExc_OSError);

	Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
	{ "mkdirat", (PyCFunction)pmkdirat, METH_VARARGS, pmkdirat_doc },
	{ "openat", (PyCFunction)popenat, METH_KEYWORDS, popenat_doc },
	{ "renameat", (PyCFunction)prenameat, METH_VARARGS, prenameat_doc },
	{ "unlinkat", (PyCFunction)punlinkat, METH_VARARGS, punlinkat_doc },
	{ NULL, NULL }
};

void
initsyscallat() {
	if (Py_InitModule("syscallat", methods) == NULL) {
		/* Initialization failed */
		return;
	}
}
