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

/*
 * These functions, although common to all actions, could not be placed in
 * _actions.c due to module import dependencies.
 */
#include <Python.h>

static PyObject *nohash;

static void
set_invalid_action_error(const char *name, PyObject *action,
    PyObject *key_aname)
{
	PyObject *exc = NULL;
	PyObject *val = NULL;
	PyObject *pkg_actions = NULL;

	if ((pkg_actions = PyImport_ImportModule("pkg.actions")) == NULL) {
		/* No exception is set */
		PyErr_SetString(PyExc_KeyError, "pkg.actions");
		return;
	}

	/*
	 * Obtain a reference to the action exception type so that SetObject can
	 * build the appropriate exception object using the created list of
	 * arguments.
	 */
	if ((exc = PyObject_GetAttrString(pkg_actions, name)) == NULL) {
		Py_DECREF(pkg_actions);
		return;
	}
	Py_DECREF(pkg_actions);

	if ((val = Py_BuildValue("OO", action, key_aname)) != NULL) {
		PyErr_SetObject(exc, val);
		Py_DECREF(val);
	}
	Py_DECREF(exc);
}

/*
 * These routines are expected to return NULL in an exception case per CPython
 * calling conventions.  Whenver NULL is returned, an exception should already
 * be set, either by the function that was just called and failed, or by the
 * routine.  If the routine is successful, it is expected to return a PyObject
 * of some kind even if the return value is ignored by consumers.  The expected
 * return value is usually None.
 */

/*ARGSUSED*/
static inline PyObject *
_generic_init_common(PyObject *action, PyObject *data, PyObject *attrs)
{
	PyObject *key_aname = NULL;
	PyObject *key_attr = NULL;
	PyObject *path_attr = NULL;
	char *path = NULL;
	char invalid_path = 0;

	/*
	 * Before doing anything else to the action, action attributes must be
	 * set as set_data() relies on it.
	 */
	if (attrs != NULL) {
		if (PyObject_SetAttrString(action, "attrs", attrs) == -1)
			return (NULL);
	} else {
		/* Caller didn't specify any keyword arguments. */
		if ((attrs = PyDict_New()) == NULL)
			return (NULL);
		if (PyObject_SetAttrString(action, "attrs", attrs) == -1) {
			Py_DECREF(attrs);
			return (NULL);
		}
		Py_DECREF(attrs);
	}

	if (data == NULL || data == Py_None) {
		/* No need to call set_data(); this is much faster. */
		if (PyObject_SetAttrString(action, "data", Py_None) == -1)
			return (NULL);
	} else {
		PyObject *res = PyObject_CallMethod(action, "set_data", "(O)",
		    data);
		if (res == NULL)
			return (NULL);
		Py_DECREF(res);
	}

	if ((key_aname = PyObject_GetAttrString(action, "key_attr")) == NULL)
		return (NULL);

	if (key_aname == Py_None) {
		Py_DECREF(key_aname);
		Py_RETURN_NONE;
	}

	if ((key_attr = PyDict_GetItem(attrs, key_aname)) == NULL) {
		PyObject *aname = PyObject_GetAttrString(action, "name");
		char *ns = PyBytes_AS_STRING(aname);

		/*
		 * set actions allow an alternate value form, so
		 * AttributeAction.__init__ will fill this in later and raise an
		 * exception if appropriate.
		 *
		 * signature actions can't require their key attribute since the
		 * value of a signature may not yet be known.
		 */
		if (strcmp(ns, "set") != 0 && strcmp(ns, "signature") != 0) {
			set_invalid_action_error("MissingKeyAttributeError",
			    action, key_aname);
			Py_DECREF(key_aname);
			return (NULL);
		}

		Py_DECREF(key_aname);
		Py_RETURN_NONE;
	}

	if (PyList_CheckExact(key_attr)) {
		PyObject *aname = PyObject_GetAttrString(action, "name");
		char *ns = PyBytes_AS_STRING(aname);
		int multi_error = 0;

		if (strcmp(ns, "depend") != 0) {
			/*
			 * Unless this is a dependency action, multiple values
			 * are never allowed for key attribute.
			 */
			multi_error = 1;
		} else {
			PyObject *dt = PyDict_GetItemString(attrs, "type");
			/*
			 * If dependency type is 'require-any', multiple values
			 * are allowed for key attribute.
			 */
			if (dt != NULL) {
				char *ts = PyBytes_AsString(dt);
				if (ts == NULL) {
					Py_DECREF(key_aname);
					Py_DECREF(aname);
					return (NULL);
				}
				if (strcmp(ts, "require-any") != 0)
					multi_error = 1;
			} else {
				multi_error = 1;
			}
		}

		Py_DECREF(aname);
		if (multi_error == 1) {
			set_invalid_action_error("KeyAttributeMultiValueError",
			    action, key_aname);
			Py_DECREF(key_aname);
			return (NULL);
		}
	}

	if ((path_attr = PyDict_GetItemString(attrs, "path")) == NULL) {
		Py_DECREF(key_aname);
		Py_RETURN_NONE;
	}

	if ((path = PyBytes_AsString(path_attr)) != NULL) {
		if (path[0] == '/') {
			PyObject *stripped = PyObject_CallMethod(
			    path_attr, "lstrip", "(s)", "/");
			if (stripped == NULL) {
				Py_DECREF(key_aname);
				return (NULL);
			}
			if (PyDict_SetItemString(attrs, "path",
			    stripped) == -1) {
				Py_DECREF(key_aname);
				Py_DECREF(stripped);
				return (NULL);
			}
			if (PyBytes_GET_SIZE(stripped) == 0)
				invalid_path = 1;
			Py_DECREF(stripped);
		} else {
			if (PyBytes_GET_SIZE(path_attr) == 0)
				invalid_path = 1;
		}
	} else {
		/* path attribute is not a string. */
		invalid_path = 1;
	}

	if (invalid_path == 1) {
		set_invalid_action_error("InvalidPathAttributeError",
		    action, key_aname);
		Py_DECREF(key_aname);
		return (NULL);
	}

	Py_DECREF(key_aname);
	Py_RETURN_NONE;
}

/*ARGSUSED*/
static PyObject *
_generic_init(PyObject *self, PyObject *args, PyObject *attrs)
{
	PyObject *action = NULL;
	PyObject *data = NULL;

	/* data is optional, but must not be specified as a keyword argument! */
	if (!PyArg_UnpackTuple(args, "_generic_init", 1, 2, &action, &data))
		return (NULL);

	return (_generic_init_common(action, data, attrs));
}

/*ARGSUSED*/
static PyObject *
_file_init(PyObject *self, PyObject *args, PyObject *attrs)
{
	PyObject *action = NULL;
	PyObject *data = NULL;
	PyObject *result = NULL;

	if (!PyArg_UnpackTuple(args, "_file_init", 1, 2, &action, &data))
		return (NULL);

	if ((result = _generic_init_common(action, data, attrs)) != NULL)
		Py_DECREF(result);
	else
		return (NULL);

	if (PyObject_SetAttrString(action, "hash", nohash) == -1)
		return (NULL);

	if (PyObject_SetAttrString(action, "replace_required", Py_False) == -1)
		return (NULL);

	Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
	{ "_file_init", (PyCFunction)_file_init, METH_VARARGS | METH_KEYWORDS },
	{ "_generic_init", (PyCFunction)_generic_init,
	    METH_VARARGS | METH_KEYWORDS },
	{ NULL, NULL, 0, NULL }
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef commonmodule = {
	PyModuleDef_HEAD_INIT,
	"_common",
	NULL,
	-1,
	methods
};
#endif

static PyObject *
moduleinit(void)
{
	PyObject *pkg_actions = NULL;
	PyObject *m;

#if PY_MAJOR_VERSION >= 3
	if ((m = PyModule_Create(&commonmodule)) == NULL)
		return NULL;
#else
	/*
	 * Note that module initialization functions are void and may not return
	 * a value.  However, they should set an exception if appropriate.
	 */
	if (Py_InitModule("_common", methods) == NULL)
		return NULL;
#endif

	if ((pkg_actions = PyImport_ImportModule("pkg.actions")) == NULL) {
		/* No exception is set */
		PyErr_SetString(PyExc_KeyError, "pkg.actions");
		return NULL;
	}

	if ((nohash = PyBytes_FromStringAndSize("NOHASH", 6)) == NULL) {
		PyErr_SetString(PyExc_ValueError,
		    "Unable to create nohash string object.");
		return NULL;
	}

	return m;
}

#if PY_MAJOR_VERSION >= 3
PyMODINIT_FUNC
PyInit__common(void)
{
	return moduleinit();
}
#else
PyMODINIT_FUNC
init_common(void)
{
	moduleinit();
}
#endif
