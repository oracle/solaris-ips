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
 * Copyright (c) 2014, Oracle and/or its affiliates. All rights reserved.
 */

#include <attr.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <sys/nvpair.h>

#include <Python.h>

/*
 * Test if a sys attr is not in the list of ignored attributes.
 */

static bool
is_supported(int attr)
{
	int ignore[] = {F_OWNERSID, F_GROUPSID, F_AV_SCANSTAMP,
	    F_OPAQUE, F_CRTIME, F_FSID, F_GEN, F_REPARSE};

	for (int i = 0; i < (sizeof (ignore) / sizeof (int)); i++)
		if (ignore[i] == attr)
			return (false);
	return (true);
}

/*
 * Decref a list and all included elements.
 */

static void
clear_list(PyObject *list)
{
	PyObject *p;
	Py_ssize_t size;

	if ((size = PyList_Size(list)) == 0) {
		Py_CLEAR(list);
		return;
	}

	for (Py_ssize_t i = 0; i < size; i++) {
		p = PyList_GetItem(list, i);
		Py_CLEAR(p);
	}
	Py_CLEAR(list);
}

/*
 * Get a dictionary containing all supported system attributes in the form:
 *
 *   { <verbose_name>: <compact_option>,
 *     ...
 *   }
 */

static char py_get_attr_dict_doc[] = "\n\
Get a dictionary containing all supported system attributes.\n\
\n\
@return: dictionary of supported system attribute in the form:\n\
    { <verbose_name>: <compact_option>,\n\
        ... \n\
    }\n\
";

/*ARGSUSED*/
static PyObject *
py_get_attr_dict(PyObject *self)
{

	PyObject *sys_attrs;

	if ((sys_attrs = PyDict_New()) == NULL)
		return (NULL);

	for (int i = 0; i < F_ATTR_ALL; i++) {
		if (!is_supported(i))
			continue;

		PyObject *str;
		if ((str = PyString_FromString(
		    attr_to_option(i))) == NULL) {
			PyDict_Clear(sys_attrs);
			Py_CLEAR(sys_attrs);
			return (NULL);
		}
		if (PyDict_SetItemString(
		    sys_attrs, attr_to_name(i), str) != 0) {
			PyDict_Clear(sys_attrs);
			Py_CLEAR(sys_attrs);
			return (NULL);
		}
	}

	return (sys_attrs);
}

/*
 * Set system attributes for a file specified by 'path'. The system attributes
 * can either be passed as a list of verbose attribute names or a string that
 * consists of a sequence of compact attribute options.
 *
 * Raises ValueError for invalid system attributes or OSError (with errno set)
 * if any of the library calls fail.
 *
 * Input examples:
 *   verbose attributes example: ['hidden', 'archive', 'sensitive', ... ]
 *
 *   compact attributes example: 'HAT'
 *
 */

static char py_fsetattr_doc[] = "\n\
Set system attributes for a file. The system attributes can either be passed \n\
as a list of verbose attribute names or a string that consists of a sequence \n\
of compact attribute options.\n\
\n\
@param path: path of file to be modified\n\
@param attrs: attributes to set\n\
\n\
@return: None\n\
";

/*ARGSUSED*/
static PyObject *
py_fsetattr(PyObject *self, PyObject *args)
{
	char *path;
	bool compact = false;
	int f;
	int sys_attr = -1;
	nvlist_t *request;
	PyObject *attrs;
	PyObject *attrs_iter;
	PyObject *attr = NULL;

	if (PyArg_ParseTuple(args, "sO", &path, &attrs) == 0) {
		return (NULL);
	}

	if (nvlist_alloc(&request, NV_UNIQUE_NAME, 0) != 0) {
		PyErr_SetFromErrno(PyExc_OSError);
		return (NULL);
	}

	/*
	 * A single string indicates system attributes are passed in compact
	 * form (e.g. AHi), verbose attributes are read as a list of strings.
	 */
	if (PyString_Check(attrs)) {
		compact = true;
	}

	if ((attrs_iter = PyObject_GetIter(attrs)) == NULL)
		goto out;

	while (attr = PyIter_Next(attrs_iter)) {
		char *attr_str = PyString_AsString(attr);
		if (attr_str == NULL) {
			goto out;
		}

		if (compact)
			sys_attr = option_to_attr(attr_str);
		else
			sys_attr = name_to_attr(attr_str);

		if (sys_attr == F_ATTR_INVAL) {
			PyObject *tstr = compact ?
			    PyString_FromString(" is not a valid compact "
			    "system attribute") :
			    PyString_FromString(" is not a valid verbose "
			    "system attribute");
			PyString_ConcatAndDel(&attr, tstr);
			PyErr_SetObject(PyExc_ValueError, attr);
			goto out;
		}

		if (!is_supported(sys_attr)) {
			PyObject *tstr = compact ?
			    PyString_FromString(" is not a supported compact "
			    "system attribute") :
			    PyString_FromString(" is not a supported verbose "
			    "system attribute");
			PyString_ConcatAndDel(&attr, tstr);
			PyErr_SetObject(PyExc_ValueError, attr);
			goto out;
		}

		if (nvlist_add_boolean_value(request, attr_to_name(sys_attr),
		    1) != 0) {
			PyErr_SetFromErrno(PyExc_OSError);
			goto out;
		}
		Py_CLEAR(attr);
	}
	Py_CLEAR(attrs_iter);

	if ((f = open(path, O_RDONLY)) == -1) {
		PyErr_SetFromErrno(PyExc_OSError);
		goto out;
	}

	if (fsetattr(f, XATTR_VIEW_READWRITE, request)) {
		PyErr_SetFromErrno(PyExc_OSError);
		close(f);
		goto out;
	}
	(void) close(f);
	nvlist_free(request);

	Py_RETURN_NONE;

out:
	nvlist_free(request);
	Py_XDECREF(attrs_iter);
	Py_XDECREF(attr);
	return (NULL);

}

/*
 * Get the list of set system attributes for file specified by 'path'.
 * Returns a list of verbose attributes by default. If 'compact' is True,
 * return a string consisting of compact option identifiers.
 *
 */

static char py_fgetattr_doc[] = "\n\
Get the list of set system attributes for a file.\n\
\n\
@param path: path of file\n\
@param compact: if true, return system attributes in compact form\n\
\n\
@return: list of verbose system attributes or string sequence of compact\n\
attributes\n\
";

/*ARGSUSED*/
static PyObject *
py_fgetattr(PyObject *self, PyObject *args, PyObject *kwds)
{
	char cattrs[F_ATTR_ALL];
	char *path;
	bool compact = false;
	int f;
	boolean_t bval;
	nvlist_t *response;
	nvpair_t *pair = NULL;
	PyObject *attr_list = NULL;

	/* Python based arguments to this function */
	static char *kwlist[] = {"path", "compact", NULL};

	if (PyArg_ParseTupleAndKeywords(args, kwds, "s|i", kwlist,
	    &path, &compact) == 0) {
		return (NULL);
	}

	if ((f = open(path, O_RDONLY)) == -1) {
		PyErr_SetFromErrno(PyExc_OSError);
		return (NULL);
	}

	if (fgetattr(f, XATTR_VIEW_READWRITE, &response)) {
		PyErr_SetFromErrno(PyExc_OSError);
		close(f);
		return (NULL);
	}
	(void) close(f);

	if (!compact) {
		if ((attr_list = PyList_New(0)) == NULL)
			return (NULL);
	}

	int count = 0;
	while (pair = nvlist_next_nvpair(response, pair)) {
		char *name = nvpair_name(pair);
		/* we ignore all non-boolean attrs */
		if (nvpair_type(pair) != DATA_TYPE_BOOLEAN_VALUE)
			continue;

		if (nvpair_value_boolean_value(pair, &bval) != 0) {
			PyErr_SetString(PyExc_OSError,
			    "could not read attr value");
			clear_list(attr_list);
			return (NULL);
		}

		if (bval) {
			if (compact) {
				if (count >= F_ATTR_ALL) {
					clear_list(attr_list);
					PyErr_SetString(PyExc_OSError, "Too "
					    "many system attributes found");
					return (NULL);
				}
				cattrs[count++] = attr_to_option(name_to_attr(
				    name))[0];
			} else {
				PyObject *str;
				if ((str = PyString_FromString(name)) == NULL) {
					clear_list(attr_list);
					return (NULL);
				}
				if (PyList_Append(attr_list, str) != 0) {
					Py_CLEAR(str);
					clear_list(attr_list);
					return (NULL);
				}
				Py_CLEAR(str);
			}
		}
	}
	nvlist_free(response);

	if (compact) {
		cattrs[count] = '\0';
		return (PyString_FromString(cattrs));
	}

	return (attr_list);
}

static PyMethodDef methods[] = {
	{ "fsetattr", (PyCFunction)py_fsetattr, METH_VARARGS, py_fsetattr_doc },
	{ "fgetattr", (PyCFunction)py_fgetattr, METH_KEYWORDS,
	    py_fgetattr_doc },
	{ "get_attr_dict", (PyCFunction)py_get_attr_dict, METH_NOARGS,
	    py_get_attr_dict_doc },
	{ NULL, NULL }
};

PyMODINIT_FUNC
initsysattr() {
	(void) Py_InitModule("sysattr", methods);
}
