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
 *  Copyright (c) 2014, Oracle and/or its affiliates. All rights reserved.
 */

#include <Python.h>
#include <sha2.h>
#include "structmember.h"

/*
 * A hash module computes SHA512/t. Now it only supports SHA512/256 and
 * SHA512/224.
 *
 * The default hash function is SHA512/256. Change your hash function to
 * SHA512/224 with the argument t=224 when you create a hash object.
 *
 * Hash objects have methods update(arg), digest() and hexdigest(), and an
 * attribute hash_size.
 *
 * For example:
 *
 * >>> import pkg.sha512_t
 * >>> a = pkg.sha512_t.SHA512_t()
 * >>> a.update("abc")
 * >>> a.digest()
 * 'S\x04\x8e&\x81\x94\x1e\xf9\x9b.)\xb7kL}\xab\xe4\xc2\xd0\xc64\xfcmF\xe0\xe2
 * \xf11\x07\xe7\xaf#'
 * More condensed:
 *
 * >>> pkg.sha512_t.SHA512_t("abc").hexdigest()
 * '53048e2681941ef99b2e29b76b4c7dabe4c2d0c634fc6d46e0e2f13107e7af23'
 *
 * >>> pkg.sha512_t.SHA512_t(t=224).hexdigest()
 * '4634270f707b6a54daae7530460842e20e37ed265ceee9a43e8924aa'
 *
 */

typedef struct {
	PyObject_HEAD
	SHA512_CTX shc;
	int hash_size;
} SHA512_t_Object;

static void
py_dealloc(SHA512_t_Object* self)
{
	self->ob_type->tp_free((PyObject*)self);
}

/*
 * Create an SHA512_t object, with optional arguments: string message and
 * hash size.
 *
 */

/*ARGSUSED*/
static int
py_init(SHA512_t_Object *self, PyObject *args, PyObject *kwds)
{
	PyObject *strObj = NULL;
	char *message;
	/* Default hash algorithm is SHA512/256. */
	self->hash_size = 256;
	static char *kwlist[] = {"message", "t", NULL};

	if (PyArg_ParseTupleAndKeywords(args, kwds, "|Si", kwlist,
	    &strObj, &self->hash_size) == 0)
		return (-1);

	if (self->hash_size != 256 && self->hash_size != 224) {
		PyErr_SetString(PyExc_ValueError, "The module "
		    "only supports SHA512/256 or SHA512/224.\n");
		return (-1);
	}

	SHA512_t_Init(self->hash_size, &self->shc);
	if (strObj != NULL) {
		if ((message = PyBytes_AsString(strObj)) == NULL)
			return (-1);
		SHA512_t_Update(&self->shc, message, strlen(message));
	}
	return (0);
}

/*
 * Update the hash object with a string object. Repeated calls are equivalent
 * to a single call with the concatenation of all the strings.
 *
 */

static char py_update_doc[] = "\n\
Update the hash object with the string arguments.\n\
\n\
@param message: input message to digest\n\
\n\
@return: None\n\
";

/*ARGSUSED*/
static PyObject *
py_update(SHA512_t_Object* self, PyObject *args)
{
	PyObject *strObj = NULL;
	char *message;

	if (!PyArg_ParseTuple(args, "S", &strObj))
		return (NULL);

	if (strObj != NULL) {
		if ((message = PyBytes_AsString(strObj)) == NULL)
			return (NULL);
		SHA512_t_Update(&self->shc, message, strlen(message));
	}
	Py_RETURN_NONE;
}

/*
 * Return the digest of the strings passed to the py_update() method so far.
 *
 */

static char py_digest_doc[] = "\n\
Return the digest of the strings passed to the update() method so far.\n\
\n\
@return: string of digest of messages\n\
";

/*ARGSUSED*/
static PyObject *
py_digest(SHA512_t_Object* self, PyObject *args)
{
	int size = self->hash_size / 8;
	unsigned char buffer[size];
	SHA512_CTX shc;
	shc = self->shc;
	SHA512_t_Final(buffer, &shc);
	return (PyString_FromStringAndSize((const char *)buffer, size));
}

/*
 * Return a string with a hex representation of the digest of the strings
 * passed to the py_update() method so far.
 *
 */

static char py_hexdigest_doc[] = "\n\
Return hexadecimal digest of the strings passed to the update() method\
so far.\n\
\n\
@return: string of double length and hexadecimal digest of the messages\n\
";

/*ARGSUSED*/
static PyObject *
py_hexdigest(SHA512_t_Object* self, PyObject *args)
{
	int i;
	int buffer_size = self->hash_size / 8;
	int result_size = self->hash_size / 4;
	unsigned char buffer[buffer_size];
	unsigned char result[result_size];
	char hexchars[16] = "0123456789abcdef";
	SHA512_CTX shc;
	shc = self->shc;
	SHA512_t_Final(buffer, &shc);
	for (i = 0; i < buffer_size; i++) {
		result[2 * i] = \
		    hexchars[(buffer[i] & 0xf0) >> 4];
		result[2 * i + 1] = \
		    hexchars[buffer[i] & 0x0f];
	}
	return (PyString_FromStringAndSize((const char *)result, result_size));
}

static PyMemberDef SHA512_t_members[] = {
	{ "hash_size", T_INT, offsetof(SHA512_t_Object, hash_size), 0,
	    "hash size"},
	{ NULL }  /* Sentinel */
};

static PyMethodDef SHA512_t_methods[] = {
	{ "update", (PyCFunction)py_update, METH_VARARGS,
	    py_update_doc },
	{ "digest", (PyCFunction)py_digest, METH_NOARGS,
	    py_digest_doc },
	{ "hexdigest", (PyCFunction)py_hexdigest, METH_NOARGS,
	    py_hexdigest_doc },
	{ NULL }  /* Sentinel */
};

static PyTypeObject SHA512_t_Type = {
	PyObject_HEAD_INIT(NULL)
	0,	/* ob_size */
	"sha512_t.SHA512_t",	/* tp_name */
	sizeof (SHA512_t_Object),	/* tp_basicsize */
	0,	/* tp_itemsize */
	(destructor)py_dealloc,	/* tp_dealloc */
	0,	/* tp_print */
	0,	/* tp_getattr */
	0,	/* tp_setattr */
	0,	/* tp_compare */
	0,	/* tp_repr */
	0,	/* tp_as_number */
	0,	/* tp_as_sequence */
	0,	/* tp_as_mapping */
	0,	/* tp_hash */
	0,	/* tp_call */
	0,	/* tp_str */
	0,	/* tp_getattro */
	0,	/* tp_setattro */
	0,	/* tp_as_buffer */
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
	"SHA512/t objects",	/* tp_doc */
	0,	/* tp_traverse */
	0,	/* tp_clear */
	0,	/* tp_richcompare */
	0,	/* tp_weaklistoffset */
	0,	/* tp_iter */
	0,	/* tp_iternext */
	SHA512_t_methods,	/* tp_methods */
	SHA512_t_members,	/* tp_members */
	0,	/* tp_getset */
	0,	/* tp_base */
	0,	/* tp_dict */
	0,	/* tp_descr_get */
	0,	/* tp_descr_set */
	0,	/* tp_dictoffset */
	(initproc)py_init,	/* tp_init */
};

static PyMethodDef sha512_t_methods[] = {
	{ NULL }  /* Sentinel */
};

PyMODINIT_FUNC
initsha512_t(void)
{
	PyObject* m;

	SHA512_t_Type.tp_new = PyType_GenericNew;
	if (PyType_Ready(&SHA512_t_Type) < 0)
		return;

	m = Py_InitModule3("sha512_t", sha512_t_methods,
	    "This module provides SHA512_t hashing.");

	if (m == NULL)
		return;

	Py_INCREF(&SHA512_t_Type);
	PyModule_AddObject(m, "SHA512_t", (PyObject *)&SHA512_t_Type);
}
