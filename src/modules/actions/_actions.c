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
 * Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
 */

#include <Python.h>

#include <string.h>

static PyObject *MalformedActionError;
static PyObject *InvalidActionError;

static char *notident = "hash attribute not identical to positional hash";

static int
add_to_attrs(PyObject *attrs, PyObject *key, PyObject *attr)
{
	int contains, ret;

	contains = PyDict_Contains(attrs, key);
	if (contains == 0) {
		return (PyDict_SetItem(attrs, key, attr));
	} else if (contains == 1) {
		PyObject *av = PyDict_GetItem(attrs, key);
		Py_INCREF(av);
		if (PyList_Check(av)) {
			ret = PyList_Append(av, attr);
			Py_DECREF(av);
			return (ret);
		} else {
			PyObject *list;
			if ((list = PyList_New(2)) == NULL)
				return (-1);
			PyList_SET_ITEM(list, 0, av);
			Py_INCREF(attr);
			PyList_SET_ITEM(list, 1, attr);
			ret = PyDict_SetItem(attrs, key, list);
			Py_DECREF(list);
			return (ret);
		}
	} else if (contains == -1)
		return (-1);

	/* Shouldn't ever get here */
	return (0);
}

static void
set_malformederr(const char *str, int pos, const char *msg)
{
	PyObject *val;

	if ((val = Py_BuildValue("sis", str, pos, msg)) != NULL) {
		PyErr_SetObject(MalformedActionError, val);
		Py_DECREF(val);
	}
}

static void
set_invaliderr(const char *str, const char *msg)
{
	PyObject *val;

	if ((val = Py_BuildValue("ss", str, msg)) != NULL) {
		PyErr_SetObject(InvalidActionError, val);
		Py_DECREF(val);
	}
}

/*ARGSUSED*/
static PyObject *
_fromstr(PyObject *self, PyObject *args)
{
	char *s = NULL;
	char *str = NULL;
	char *hashstr = NULL;
	char *keystr = NULL;
	int *slashmap = NULL;
	int strl;
	int i, ks, vs, keysize;
	int smlen, smpos;
	char quote;
	PyObject *type = NULL;
	PyObject *hash = NULL;
	PyObject *attrs = NULL;
	PyObject *ret = NULL;
	PyObject *key = NULL;
	PyObject *attr = NULL;
	enum {
		KEY,    /* key            */
		UQVAL,  /* unquoted value */
		QVAL,   /* quoted value   */
		WS      /* whitespace     */
	} state;

	/*
	 * If malformed() or invalid() are used, CLEANUP_REFS can only be used
	 * after.  Likewise, PyMem_Free(str) should not be called before using
	 * malformed() or invalid().  Failure to order this properly will cause
	 * corruption of the exception messages.
	 */
#define malformed(msg) set_malformederr(str, i, (msg))
#define invalid(msg) set_invaliderr(str, (msg))
#define CLEANUP_REFS \
	PyMem_Free(str);\
	Py_XDECREF(key);\
	Py_XDECREF(type);\
	Py_XDECREF(attr);\
	Py_XDECREF(attrs);\
	Py_XDECREF(hash);\
	free(hashstr);

	/*
	 * The action string is currently assumed to be a stream of bytes that
	 * are valid UTF-8.  This method works regardless of whether the string
	 * object provided is a Unicode object, string object, or a character
	 * buffer.
	 */
	if (PyArg_ParseTuple(args, "et#", "utf-8", &str, &strl) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}

	s = strpbrk(str, " \t");

	i = strl;
	if (s == NULL) {
		malformed("no attributes");
		PyMem_Free(str);
		return (NULL);
	}

	if ((type = PyString_FromStringAndSize(str, s - str)) == NULL) {
		PyMem_Free(str);
		return (NULL);
	}

	PyString_InternInPlace(&type);

	ks = vs = s - str;
	state = WS;
	if ((attrs = PyDict_New()) == NULL) {
		PyMem_Free(str);
		Py_DECREF(type);
		return (NULL);
	}
	for (i = s - str; str[i]; i++) {
		if (state == KEY) {
			keysize = i - ks;
			keystr = &str[ks];

			if (str[i] == ' ' || str[i] == '\t') {
				if (PyDict_Size(attrs) > 0 || hash != NULL) {
					malformed("whitespace in key");
					CLEANUP_REFS;
					return (NULL);
				}
				else {
					if ((hash = PyString_FromStringAndSize(
						keystr, keysize)) == NULL) {
						CLEANUP_REFS;
						return (NULL);
					}
					hashstr = strndup(keystr, keysize);
					state = WS;
				}
			} else if (str[i] == '=') {
				if ((key = PyString_FromStringAndSize(
					keystr, keysize)) == NULL) {
					CLEANUP_REFS;
					return (NULL);
				}

				if (keysize == 4 && strncmp(keystr, "data",
					keysize) == 0) {
					invalid("invalid key: 'data'");
					CLEANUP_REFS;
					return (NULL);
				}

				/*
				 * Pool attribute key to reduce memory usage and
				 * potentially improve lookup performance.
				 */
				PyString_InternInPlace(&key);

				if (i == ks) {
					malformed("impossible: missing key");
					CLEANUP_REFS;
					return (NULL);
				}
				else if (++i == strl) {
					malformed("missing value");
					CLEANUP_REFS;
					return (NULL);
				}
				if (str[i] == '\'' || str[i] == '\"') {
					state = QVAL;
					quote = str[i];
					vs = i + 1;
				} else if (str[i] == ' ' || str[i] == '\t') {
					malformed("missing value");
					CLEANUP_REFS;
					return (NULL);
				}
				else {
					state = UQVAL;
					vs = i;
				}
			} else if (str[i] == '\'' || str[i] == '\"') {
				malformed("quote in key");
				CLEANUP_REFS;
				return (NULL);
			}
		} else if (state == QVAL) {
			if (str[i] == '\\') {
				if (i == strl - 1)
					break;
				/*
				 * "slashmap" is a list of the positions of the
				 * backslashes that need to be removed from the
				 * final attribute string.
				 */
				if (slashmap == NULL) {
					smlen = 16;
					slashmap = calloc(smlen, sizeof(int));
					if (slashmap == NULL) {
						PyMem_Free(str);
						return (PyErr_NoMemory());
					}
					smpos = 0;
					/*
					 * Terminate slashmap with an invalid
					 * value so we don't think there's a
					 * slash right at the beginning.
					 */
					slashmap[smpos] = -1;
				} else if (smpos == smlen - 1) {
					smlen *= 2;
					slashmap = realloc(slashmap,
						smlen * sizeof(int));
					if (slashmap == NULL) {
						PyMem_Free(str);
						return (PyErr_NoMemory());
					}
				}
				i++;
				if (str[i] == '\\' || str[i] == quote) {
					slashmap[smpos++] = i - 1 - vs;
					/*
					 * Keep slashmap properly terminated so
					 * that a realloc()ed array doesn't give
					 * us random slash positions.
					 */
					slashmap[smpos] = -1;
				}
			} else if (str[i] == quote) {
				state = WS;
				if (slashmap != NULL) {
					char *sattr;
					int j, o, attrlen;

					attrlen = i - vs;
					sattr = calloc(1, attrlen + 1);
					if (sattr == NULL) {
						PyMem_Free(str);
						free(slashmap);
						return (PyErr_NoMemory());
					}
					/*
					 * Copy the attribute from str into
					 * sattr, removing backslashes as
					 * slashmap indicates we should.
					 */
					for (j = 0, o = 0; j < attrlen; j++) {
						if (slashmap[o] == j) {
							o++;
							continue;
						}
						sattr[j - o] = str[vs + j];
					}

					free(slashmap);
					slashmap = NULL;

					if ((attr = PyString_FromStringAndSize(
						sattr, attrlen - o)) == NULL) {
						free(sattr);
						CLEANUP_REFS;
						return (NULL);
					}
					free(sattr);
				} else {
					Py_XDECREF(attr);
					if ((attr = PyString_FromStringAndSize(
					    &str[vs], i - vs)) == NULL) {
						CLEANUP_REFS;
						return (NULL);
					}
				}

				if (!strncmp(keystr, "hash=", 5)) {
					char *as = PyString_AsString(attr);
					if (hashstr && strcmp(as, hashstr)) {
						invalid(notident);
						CLEANUP_REFS;
						return (NULL);
					}
					hash = attr;
					attr = NULL;
				} else {
					PyString_InternInPlace(&attr);
					if (add_to_attrs(attrs, key, attr) == -1) {
						CLEANUP_REFS;
						return (NULL);
					}
				}
			}
		} else if (state == UQVAL) {
			if (str[i] == ' ' || str[i] == '\t') {
				state = WS;
				Py_XDECREF(attr);
				attr = PyString_FromStringAndSize(&str[vs], i - vs);
				if (!strncmp(keystr, "hash=", 5)) {
					char *as = PyString_AsString(attr);
					if (hashstr && strcmp(as, hashstr)) {
						invalid(notident);
						CLEANUP_REFS;
						return (NULL);
					}
					hash = attr;
					attr = NULL;
				} else {
					PyString_InternInPlace(&attr);
					if (add_to_attrs(attrs, key, attr) == -1) {
						CLEANUP_REFS;
						return (NULL);
					}
				}
			}
		} else if (state == WS) {
			if (str[i] != ' ' && str[i] != '\t') {
				state = KEY;
				ks = i;
				if (str[i] == '=') {
					malformed("missing key");
					CLEANUP_REFS;
					return (NULL);
				}
			}
		}
	}

	if (state == QVAL) {
		if (slashmap != NULL)
			free(slashmap);

		malformed("unfinished quoted value");
		CLEANUP_REFS;
		return (NULL);
	}
	if (state == KEY) {
		malformed("missing value");
		CLEANUP_REFS;
		return (NULL);
	}

	if (state == UQVAL) {
		Py_XDECREF(attr);
		attr = PyString_FromStringAndSize(&str[vs], i - vs);
		if (!strncmp(keystr, "hash=", 5)) {
			char *as = PyString_AsString(attr);
			if (hashstr && strcmp(as, hashstr)) {
				invalid(notident);
				CLEANUP_REFS;
				return (NULL);
			}
			hash = attr;
			attr = NULL;
		} else {
			PyString_InternInPlace(&attr);
			if (add_to_attrs(attrs, key, attr) == -1) {
				CLEANUP_REFS;
				return (NULL);
			}
		}
	}

	PyMem_Free(str);
	if (hash == NULL)
		hash = Py_None;

	ret = Py_BuildValue("OOO", type, hash, attrs);
	Py_XDECREF(key);
	Py_XDECREF(attr);
	Py_DECREF(type);
	Py_DECREF(attrs);
	if (hash != Py_None)
		Py_DECREF(hash);
	return (ret);
}

static PyMethodDef methods[] = {
	{ "_fromstr", _fromstr, METH_VARARGS },
	{ NULL, NULL }
};

PyMODINIT_FUNC
init_actions(void)
{
	PyObject *sys, *pkg_actions;
	PyObject *sys_modules;

	if (Py_InitModule("_actions", methods) == NULL)
		return;

	/*
	 * We need to retrieve the MalformedActionError object from pkg.actions.
	 * We can't import pkg.actions directly, because that would result in a
	 * circular dependency.  But the "sys" module has a dict called
	 * "modules" which maps loaded module names to the corresponding module
	 * objects.  We can then grab the exception from those objects.
	 */

	if ((sys = PyImport_ImportModule("sys")) == NULL)
		return;

	if ((sys_modules = PyObject_GetAttrString(sys, "modules")) == NULL)
		return;

	if ((pkg_actions = PyDict_GetItemString(sys_modules, "pkg.actions"))
		== NULL) {
		/* No exception is set */
		PyErr_SetString(PyExc_KeyError, "pkg.actions");
		return;
	}

	MalformedActionError = \
		PyObject_GetAttrString(pkg_actions, "MalformedActionError");
	InvalidActionError = \
		PyObject_GetAttrString(pkg_actions, "InvalidActionError");
}
