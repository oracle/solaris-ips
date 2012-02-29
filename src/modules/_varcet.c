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
 * Copyright (c) 2012, Oracle and/or its affiliates. All rights reserved.
 */

#include <Python.h>

/*ARGSUSED*/
static PyObject *
_allow_facet(PyObject *self, PyObject *args)
{
	PyObject *action = NULL;
	PyObject *facets = NULL;
	PyObject *keylist = NULL;

	PyObject *act_attrs = NULL;
	PyObject *attr = NULL;
	PyObject *value = NULL;

	PyObject *res = NULL;
	PyObject *ret = Py_True;
	Py_ssize_t fpos = 0;
	Py_ssize_t klen = 0;

	if (!PyArg_UnpackTuple(args, "_allow_facet", 2, 2, &facets, &action))
		return (NULL);

	if ((act_attrs = PyObject_GetAttrString(action, "attrs")) == NULL)
		return (NULL);

	if ((keylist = PyObject_GetAttrString(facets,
	    "_Facets__keylist")) == NULL) {
		Py_DECREF(act_attrs);
		return (NULL);
	}
	klen = PyList_GET_SIZE(keylist);

	if ((res = PyObject_GetAttrString(facets, "_Facets__res")) == NULL) {
		Py_DECREF(act_attrs);
		Py_DECREF(keylist);
		return (NULL);
	}

#define	CLEANUP_FREFS \
	Py_DECREF(act_attrs);\
	Py_DECREF(keylist);\
	Py_DECREF(res);

	while (PyDict_Next(act_attrs, &fpos, &attr, &value)) {
		char *as = PyString_AS_STRING(attr);
		if (strncmp(as, "facet.", 6) != 0)
			continue;

		PyObject *facet = PyDict_GetItem(facets, attr);
		if (facet == Py_True) {
			CLEANUP_FREFS;
			Py_INCREF(facet);
			return (facet);
		}

		if (facet == NULL) {
			Py_ssize_t idx = 0;

			/*
			 * Facet is unknown; see if it matches one of the
			 * wildcard patterns set.
			 */
			for (idx = 0; idx < klen; idx++) {
				PyObject *key = PyList_GET_ITEM(keylist, idx);
				PyObject *re = PyDict_GetItem(res, key);
				PyObject *match = PyObject_CallMethod(re,
				    "match", "O", attr);
				if (match != Py_None) {
					PyObject *fval = PyDict_GetItem(
					    facets, key);

					Py_DECREF(match);
					CLEANUP_FREFS;
					if (fval == NULL)
						return (NULL);
					Py_INCREF(fval);
					return (fval);
				}
				Py_DECREF(match);
			}

			/*
			 * If facet is unknown to the system and no facet
			 * patterns matched it, be inclusive and allow the
			 * action.
			 */
			CLEANUP_FREFS;
			Py_RETURN_TRUE;
		}

		/* Facets are currently OR'd. */
		ret = Py_False;
	}

	CLEANUP_FREFS;
	Py_INCREF(ret);
	return (ret);
}

/*ARGSUSED*/
static PyObject *
_allow_variant(PyObject *self, PyObject *args)
{
	PyObject *action = NULL;
	PyObject *vars = NULL;
	PyObject *act_attrs = NULL;
	PyObject *attr = NULL;
	PyObject *value = NULL;
	Py_ssize_t pos = 0;

	if (!PyArg_UnpackTuple(args, "_allow_variant", 2, 2, &vars, &action))
		return (NULL);

	if ((act_attrs = PyObject_GetAttrString(action, "attrs")) == NULL)
		return (NULL);

	while (PyDict_Next(act_attrs, &pos, &attr, &value)) {
		char *as = PyString_AS_STRING(attr);
		if (strncmp(as, "variant.", 8) == 0) {
			PyObject *sysv = PyDict_GetItem(vars, attr);
			char *av = PyString_AsString(value);
			char *sysav = NULL;

			if (sysv == NULL) {
				/*
				 * If system variant value doesn't exist, then
				 * allow the action if it is a debug variant
				 * that is "false".
				 */
				if ((strncmp(as, "variant.debug.", 14) == 0) &&
				    (strncmp(av, "false", 5) != 0)) {
					Py_DECREF(act_attrs);
					Py_RETURN_FALSE;
				}
				continue;
			}

			sysav = PyString_AsString(sysv);
			if (strcmp(av, sysav) != 0) {
				/*
				 * If system variant value doesn't match action
				 * variant value, don't allow this action.
				 */
				Py_DECREF(act_attrs);
				Py_RETURN_FALSE;
			}
		}
	}

	Py_DECREF(act_attrs);
	Py_RETURN_TRUE;
}

static PyMethodDef methods[] = {
	{ "_allow_facet", (PyCFunction)_allow_facet, METH_VARARGS },
	{ "_allow_variant", (PyCFunction)_allow_variant, METH_VARARGS },
	{ NULL, NULL, 0, NULL }
};

PyMODINIT_FUNC
init_varcet(void)
{
	Py_InitModule("_varcet", methods);
}
