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
 * Copyright (c) 2012, 2015, Oracle and/or its affiliates. All rights reserved.
 */

#include <Python.h>

/*ARGSUSED*/
static PyObject *
_allow_facet(PyObject *self, PyObject *args, PyObject *kwargs)
{
	PyObject *action = NULL;
	PyObject *facets = NULL;
	PyObject *keylist = NULL;

	PyObject *act_attrs = NULL;
	PyObject *attr = NULL;
	PyObject *value = NULL;

	PyObject *res = NULL;
	PyObject *all_ret = Py_True;
	PyObject *any_ret = NULL;
	PyObject *facet_ret = NULL;
	PyObject *ret = Py_True;
	Py_ssize_t fpos = 0;
	Py_ssize_t klen = 0;
	/* This parameter is ignored. */
	PyObject *publisher = NULL;
	static char *kwlist[] = {"facets", "action", "publisher", NULL};

	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|O:_allow_facet",
		kwlist, &facets, &action, &publisher))
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
		char *as = PyBytes_AS_STRING(attr);
		if (strncmp(as, "facet.", 6) != 0)
			continue;

		PyObject *facet = PyDict_GetItem(facets, attr);
		if (facet != NULL) {
			facet_ret = facet;
		} else {
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

					if (fval != NULL) {
						facet_ret = fval;
						goto prep_ret;
					}

					/*
					 * If wildcard facet value cannot be
					 * retrieved, cleanup and return.
					 */
					CLEANUP_FREFS;
					return (NULL);
				}
				Py_DECREF(match);
			}

			/*
			 * If facet is unknown to the system and no facet
			 * patterns matched it, then allow the action if it is
			 * not a debug or optional facet.  The trailing '.' is
			 * to encourage namespace usage.
			 */
			if (strncmp(as, "facet.debug.", 12) == 0 ||
			    strncmp(as, "facet.optional.", 15) == 0) {
				facet_ret = Py_False;
			} else {
				facet_ret = Py_True;
			}
		}

prep_ret:
		if (facet_ret != NULL) {
			char *vs = PyBytes_AS_STRING(value);
			if (strcmp(vs, "all") == 0) {
				/*
				 * If facet == 'all' and is False, then no more
				 * facets need to be checked; this action is not
				 * allowed.
				 */
				if (facet_ret == Py_False) {
					all_ret = Py_False;
					break;
				}
			} else if (facet_ret == Py_True) {
				/*
				 * If facet != 'all' and is True, then we've met
				 * the 'any' condition.
				 */
				any_ret = Py_True;
			} else if (facet_ret == Py_False && any_ret == NULL) {
				/*
				 * If facet != 'all' and is False, and no other
				 * facets are yet True, tentatively reject this
				 * action.
				 */
				any_ret = Py_False;
			}
		}

		/*
		 * All facets must be explicitly checked to determine if all the
		 * facets that == 'all' are True, and that (if present) at least
		 * one other facet that is != 'all' is True.
		 */
		facet_ret = NULL;
	}

	CLEANUP_FREFS;
	if (all_ret == Py_False || any_ret == Py_False)
		ret = Py_False;

	Py_INCREF(ret);
	return (ret);
}

/*ARGSUSED*/
static PyObject *
_allow_variant(PyObject *self, PyObject *args, PyObject *kwargs)
{
	PyObject *action = NULL;
	PyObject *vars = NULL;
	PyObject *act_attrs = NULL;
	PyObject *attr = NULL;
	PyObject *value = NULL;
	Py_ssize_t pos = 0;
	/* This parameter is ignored. */
	PyObject *publisher = NULL;
	static char *kwlist[] = {"vars", "action", "publisher", NULL};

	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|O:_allow_variant",
		kwlist, &vars, &action, &publisher))
		return (NULL);

	if ((act_attrs = PyObject_GetAttrString(action, "attrs")) == NULL)
		return (NULL);

	while (PyDict_Next(act_attrs, &pos, &attr, &value)) {
		char *as = PyBytes_AS_STRING(attr);
		if (strncmp(as, "variant.", 8) == 0) {
			PyObject *sysv = PyDict_GetItem(vars, attr);
			char *av = PyBytes_AsString(value);
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

			sysav = PyBytes_AsString(sysv);
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
	{ "_allow_facet", (PyCFunction)_allow_facet,
	    METH_VARARGS | METH_KEYWORDS },
	{ "_allow_variant", (PyCFunction)_allow_variant,
	    METH_VARARGS | METH_KEYWORDS },
	{ NULL, NULL, 0, NULL }
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef varcetmodule = {
	PyModuleDef_HEAD_INIT,
	"_varcet",
	NULL,
	-1,
	methods
};
#endif

#if PY_MAJOR_VERSION >= 3
	PyMODINIT_FUNC
	PyInit__varcet(void)
	{
		return PyModule_Create(&varcetmodule);
	}
#else
	PyMODINIT_FUNC
	init_varcet(void)
	{
		Py_InitModule("_varcet", methods);
	}
#endif
