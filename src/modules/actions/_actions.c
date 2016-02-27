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
 * Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
 */

#include <Python.h>

#include <stdbool.h>
#include <string.h>

static PyObject *MalformedActionError;
static PyObject *InvalidActionError;
static PyObject *UnknownActionError;
static PyObject *aclass_attribute;
static PyObject *aclass_depend;
static PyObject *aclass_directory;
static PyObject *aclass_driver;
static PyObject *aclass_file;
static PyObject *aclass_group;
static PyObject *aclass_hardlink;
static PyObject *aclass_legacy;
static PyObject *aclass_license;
static PyObject *aclass_link;
static PyObject *aclass_signature;
static PyObject *aclass_unknown;
static PyObject *aclass_user;

static const char *notident = "hash attribute not identical to positional hash";
static const char *nohash = "action type doesn't allow payload";

static inline int
add_to_attrs(PyObject *attrs, PyObject *key, PyObject *attr, bool concat)
{
	int ret;
	PyObject *list;
	PyObject *av = PyDict_GetItem(attrs, key);

	if (av == NULL)
		return (PyDict_SetItem(attrs, key, attr));

	if (PyList_CheckExact(av)) {
		if (concat) {
			Py_ssize_t len;
			PyObject *str, *oldstr;

			/*
			 * PyList_GET_ITEM() returns a borrowed reference.
			 * We grab a reference to that string because
			 * PyString_Concat() will steal one, and the list needs
			 * to have one around for when we call into
			 * PyList_SetItem().  PyString_Concat() returns a new
			 * object in str with a new reference, which we must
			 * *not* decref after putting into the list.
			 */
			len = PyList_GET_SIZE(av);
			oldstr = str = PyList_GET_ITEM(av, len - 1);
			Py_INCREF(oldstr);
			/* decrefing "attr" is handled by caller */
			PyString_Concat(&str, attr);
			if (str == NULL)
				return (-1);
			return (PyList_SetItem(av, len - 1, str));
		}

		return (PyList_Append(av, attr));
	} else if (concat) {
		Py_INCREF(av);
		/* decrefing "attr" is handled by caller */
		PyString_Concat(&av, attr);
		if (av == NULL)
			return (-1);
		ret = PyDict_SetItem(attrs, key, av);
		Py_DECREF(av);
		return (ret);
	}

	if ((list = PyList_New(2)) == NULL)
		return (-1);

	/* PyList_SET_ITEM steals references. */
	Py_INCREF(av);
	PyList_SET_ITEM(list, 0, av);
	Py_INCREF(attr);
	PyList_SET_ITEM(list, 1, attr);
	ret = PyDict_SetItem(attrs, key, list);
	Py_DECREF(list);
	return (ret);
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

/*
 * Note that action parsing does not support line-continuation ('\'); that
 * support is provided by the Manifest class.
 */

/*ARGSUSED*/
static PyObject *
fromstr(PyObject *self, PyObject *args, PyObject *kwdict)
{
	char *s = NULL;
	char *str = NULL;
	char *hashstr = NULL;
	char *keystr = NULL;
	int *slashmap = NULL;
	int strl, typestrl;
	int i, ks, vs, keysize;
	int smlen, smpos;
	int hash_allowed;
	bool concat = false;
	char quote;
	PyObject *act_args = NULL;
	PyObject *act_class = NULL;
	PyObject *act_data = NULL;
	PyObject *action = NULL;
	PyObject *hash = NULL;
	PyObject *attrs = NULL;
	PyObject *key = NULL;
	PyObject *attr = NULL;
	enum {
		KEY,	/* key			*/
		UQVAL,	/* unquoted value	*/
		QVAL,	/* quoted value		*/
		WS	/* whitespace		*/
	} state, prevstate;

	/*
	 * If malformed() or invalid() are used, CLEANUP_REFS can only be used
	 * after.  Likewise, PyMem_Free(str) should not be called before using
	 * malformed() or invalid().  Failure to order this properly will cause
	 * corruption of the exception messages.
	 */
#define	malformed(msg) set_malformederr(str, i, (msg))
#define	invalid(msg) set_invaliderr(str, (msg))
#define	CLEANUP_REFS \
	PyMem_Free(str);\
	Py_XDECREF(key);\
	Py_XDECREF(attr);\
	Py_XDECREF(attrs);\
	Py_XDECREF(hash);\
	free(hashstr);

	/*
	 * Positional arguments must be included in the keyword argument list in
	 * the order you want them to be assigned.  (A subtle point missing from
	 * the Python documentation.)
	 */
	static char *kwlist[] = { "string", "data", NULL };

	/* Assume data=None by default. */
	act_data = Py_None;

	/*
	 * The action string is currently assumed to be a stream of bytes that
	 * are valid UTF-8.  This method works regardless of whether the string
	 * object provided is a Unicode object, string object, or a character
	 * buffer.
	 */
	if (PyArg_ParseTupleAndKeywords(args, kwdict, "et#|O:fromstr", kwlist,
	    "utf-8", &str, &strl, &act_data) == 0) {
		return (NULL);
	}

	s = strpbrk(str, " \t\n");

	i = strl;
	if (s == NULL) {
		malformed("no attributes");
		PyMem_Free(str);
		return (NULL);
	}

	/*
	 * The comparisons here are ordered by frequency in which actions are
	 * most likely to be encountered in usage by the client grouped by
	 * length.  Yes, a cheap hack to squeeze a tiny bit of additional
	 * performance out.
	 */
	typestrl = s - str;
	hash_allowed = 0;
	if (typestrl == 4) {
		if (strncmp(str, "file", 4) == 0) {
			act_class = aclass_file;
			hash_allowed = 1;
		} else if (strncmp(str, "link", 4) == 0)
			act_class = aclass_link;
		else if (strncmp(str, "user", 4) == 0)
			act_class = aclass_user;
	} else if (typestrl == 6) {
		if (strncmp(str, "depend", 6) == 0)
			act_class = aclass_depend;
		else if (strncmp(str, "driver", 6) == 0)
			act_class = aclass_driver;
		else if (strncmp(str, "legacy", 6) == 0)
			act_class = aclass_legacy;
	} else if (typestrl == 3) {
		if (strncmp(str, "set", 3) == 0)
			act_class = aclass_attribute;
		else if (strncmp(str, "dir", 3) == 0)
			act_class = aclass_directory;
	} else if (typestrl == 8) {
		if (strncmp(str, "hardlink", 8) == 0)
			act_class = aclass_hardlink;
	} else if (typestrl == 7) {
		if (strncmp(str, "license", 7) == 0) {
			act_class = aclass_license;
			hash_allowed = 1;
		} else if (strncmp(str, "unknown", 7) == 0)
			act_class = aclass_unknown;
	} else if (typestrl == 9) {
		if (strncmp(str, "signature", 9) == 0) {
			act_class = aclass_signature;
			hash_allowed = 1;
		}
	} else if (typestrl == 5) {
		if (strncmp(str, "group", 5) == 0)
			act_class = aclass_group;
	}

	if (act_class == NULL) {
		if ((act_args = Py_BuildValue("s#s#", str, strl,
		    str, typestrl)) != NULL) {
			PyErr_SetObject(UnknownActionError, act_args);
			Py_DECREF(act_args);
			PyMem_Free(str);
			return (NULL);
		}

		/*
		 * Unable to build argument list for exception; so raise
		 * general type exception instead.
		 */
		PyErr_SetString(PyExc_TypeError, "unknown action type");
		PyMem_Free(str);
		return (NULL);
	}

	ks = vs = typestrl;
	prevstate = state = WS;
	if ((attrs = PyDict_New()) == NULL) {
		PyMem_Free(str);
		return (NULL);
	}
	for (i = s - str; str[i]; i++) {
		if (state == KEY) {
			keysize = i - ks;
			keystr = &str[ks];

			if (str[i] == ' ' || str[i] == '\t' || str[i] == '\n') {
				if (PyDict_Size(attrs) > 0 || hash != NULL) {
					malformed("whitespace in key");
					CLEANUP_REFS;
					return (NULL);
				} else {
#if PY_MAJOR_VERSION >= 3
					hash = PyUnicode_FromStringAndSize(
					    keystr, keysize);
#else
					hash = PyString_FromStringAndSize(
					    keystr, keysize);
#endif
					if (hash == NULL) {
						CLEANUP_REFS;
						return (NULL);
					}
					if (!hash_allowed) {
						invalid(nohash);
						CLEANUP_REFS;
						return (NULL);
					}
					hashstr = strndup(keystr, keysize);
					prevstate = state;
					state = WS;
				}
			} else if (str[i] == '=') {
#if PY_MAJOR_VERSION >= 3
				key = PyUnicode_FromStringAndSize(
				    keystr, keysize);
#else
				key = PyString_FromStringAndSize(
				    keystr, keysize);
#endif
				if (key == NULL) {
					CLEANUP_REFS;
					return (NULL);
				}

				if (keysize == 4 && strncmp(keystr, "data",
				    keysize) == 0) {
					invalid("invalid key: 'data'");
					CLEANUP_REFS;
					return (NULL);
				}
				if (!hash_allowed && keysize == 4 &&
				    strncmp(keystr, "hash", keysize) == 0) {
					invalid(nohash);
					CLEANUP_REFS;
					return (NULL);
				}

				/*
				 * Pool attribute key to reduce memory usage and
				 * potentially improve lookup performance.
				 */
#if PY_MAJOR_VERSION >= 3
				PyUnicode_InternInPlace(&key);
#else
				PyString_InternInPlace(&key);
#endif

				if (i == ks) {
					malformed("impossible: missing key");
					CLEANUP_REFS;
					return (NULL);
				} else if (++i == strl) {
					malformed("missing value");
					CLEANUP_REFS;
					return (NULL);
				}
				if (str[i] == '\'' || str[i] == '\"') {
					prevstate = state;
					state = QVAL;
					quote = str[i];
					vs = i + 1;
				} else if (str[i] == ' ' || str[i] == '\t' ||
				    str[i] == '\n') {
					malformed("missing value");
					CLEANUP_REFS;
					return (NULL);
				} else {
					prevstate = state;
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
				 * final attribute string; it is not used for
				 * line continuation which is only supported
				 * by the Manifest class.
				 */
				if (slashmap == NULL) {
					smlen = 16;
					slashmap = calloc(smlen, sizeof (int));
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
					    smlen * sizeof (int));
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
				prevstate = state;
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

#if PY_MAJOR_VERSION >= 3
					attr = PyUnicode_FromStringAndSize(
					    sattr, attrlen - o);
#else
					attr = PyString_FromStringAndSize(
					    sattr, attrlen - o);
#endif
					if (attr == NULL) {
						free(sattr);
						CLEANUP_REFS;
						return (NULL);
					}
					free(sattr);
				} else {
					Py_XDECREF(attr);
#if PY_MAJOR_VERSION >= 3
					attr = PyUnicode_FromStringAndSize(
					    &str[vs], i - vs);
#else
					attr = PyString_FromStringAndSize(
					    &str[vs], i - vs);
#endif
					if (attr == NULL) {
						CLEANUP_REFS;
						return (NULL);
					}
				}

				if (strncmp(keystr, "hash=", 5) == 0) {
					char *as = PyBytes_AsString(attr);
					if (hashstr && strcmp(as, hashstr)) {
						invalid(notident);
						CLEANUP_REFS;
						return (NULL);
					}
					hash = attr;
					attr = NULL;
				} else {
#if PY_MAJOR_VERSION >= 3
					PyUnicode_InternInPlace(&attr);
#else
					PyString_InternInPlace(&attr);
#endif

					if (add_to_attrs(attrs, key, attr,
					    concat) == -1) {
						CLEANUP_REFS;
						return (NULL);
					}
					concat = false;
				}
			}
		} else if (state == UQVAL) {
			if (str[i] == ' ' || str[i] == '\t' || str[i] == '\n') {
				prevstate = state;
				state = WS;
				Py_XDECREF(attr);
#if PY_MAJOR_VERSION >= 3
				attr = PyUnicode_FromStringAndSize(&str[vs],
				    i - vs);
#else
				attr = PyString_FromStringAndSize(&str[vs],
				    i - vs);
#endif
				if (strncmp(keystr, "hash=", 5) == 0) {
					char *as = PyBytes_AsString(attr);
					if (hashstr && strcmp(as, hashstr)) {
						invalid(notident);
						CLEANUP_REFS;
						return (NULL);
					}
					hash = attr;
					attr = NULL;
				} else {
#if PY_MAJOR_VERSION >= 3
					PyUnicode_InternInPlace(&attr);
#else
					PyString_InternInPlace(&attr);
#endif
					if (add_to_attrs(attrs, key, attr,
					    false) == -1) {
						CLEANUP_REFS;
						return (NULL);
					}
				}
			}
		} else if (state == WS) {
			if (str[i] != ' ' && str[i] != '\t' && str[i] != '\n') {
				state = KEY;
				ks = i;
				if (str[i] == '=') {
					malformed("missing key");
					CLEANUP_REFS;
					return (NULL);
				} else if (prevstate == QVAL &&
				    (str[i] == '\'' || str[i] == '\"')) {
					/*
					 * We find ourselves with two adjacent
					 * quoted values, which we concatenate.
					 */
					state = QVAL;
					quote = str[i];
					vs = i + 1;
					concat = true;
				}
				prevstate = WS;
			}
		}
	}

	/*
	 * UQVAL is the most frequently encountered end-state, so check that
	 * first to avoid unnecessary state comparisons.
	 */
	if (state == UQVAL) {
		Py_XDECREF(attr);
#if PY_MAJOR_VERSION >= 3
		attr = PyUnicode_FromStringAndSize(&str[vs], i - vs);
#else
		attr = PyString_FromStringAndSize(&str[vs], i - vs);
#endif
		if (strncmp(keystr, "hash=", 5) == 0) {
			char *as = PyBytes_AsString(attr);
			if (hashstr && strcmp(as, hashstr)) {
				invalid(notident);
				CLEANUP_REFS;
				return (NULL);
			}
			hash = attr;
			attr = NULL;
		} else {
#if PY_MAJOR_VERSION >= 3
			PyUnicode_InternInPlace(&attr);
#else
			PyString_InternInPlace(&attr);
#endif
			if (add_to_attrs(attrs, key, attr, false) == -1) {
				CLEANUP_REFS;
				return (NULL);
			}
		}
	} else if (state == QVAL) {
		if (slashmap != NULL)
			free(slashmap);

		malformed("unfinished quoted value");
		CLEANUP_REFS;
		return (NULL);
	} else if (state == KEY) {
		malformed("missing value");
		CLEANUP_REFS;
		return (NULL);
	}

	PyMem_Free(str);
	Py_XDECREF(key);
	Py_XDECREF(attr);

	/*
	 * Action parsing is done; now build the list of arguments to construct
	 * the object for it.
	 */
	if ((act_args = Py_BuildValue("(O)", act_data)) == NULL) {
		if (hash != NULL && hash != Py_None)
			Py_DECREF(hash);
		Py_DECREF(attrs);
		return (NULL);
	}

	/*
	 * Using the cached action class assigned earlier based on the type,
	 * call the action constructor, set the hash attribute, and then return
	 * the new action object.
	 */
	action = PyObject_Call(act_class, act_args, attrs);
	Py_DECREF(act_args);
	Py_DECREF(attrs);
	if (action == NULL) {
		if (hash != NULL && hash != Py_None)
			Py_DECREF(hash);
		return (NULL);
	}

	if (hash != NULL && hash != Py_None) {
		if (PyObject_SetAttrString(action, "hash", hash) == -1) {
			Py_DECREF(hash);
			Py_DECREF(action);
			return (NULL);
		}
		Py_DECREF(hash);
	}

	return (action);
}

static PyMethodDef methods[] = {
	{ "fromstr", (PyCFunction)fromstr, METH_VARARGS | METH_KEYWORDS },
	{ NULL, NULL, 0, NULL }
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef actionmodule = {
	PyModuleDef_HEAD_INIT,
	"_action",
	NULL,
	-1,
	methods
};
#endif

static PyObject *
moduleinit(void)
{
	PyObject *action_types = NULL;
	PyObject *pkg_actions = NULL;
	PyObject *sys = NULL;
	PyObject *sys_modules = NULL;
	PyObject *m;

#if PY_MAJOR_VERSION >= 3
	if ((m = PyModule_Create(&actionmodule)) == NULL)
		return (NULL);
#else
	/*
	 * Note that module initialization functions are void and may not return
	 * a value.  However, they should set an exception if appropriate.
	 */
	if (Py_InitModule("_actions", methods) == NULL)
		return (NULL);
#endif

	/*
	 * We need to retrieve the MalformedActionError object from pkg.actions.
	 * We can't import pkg.actions directly, because that would result in a
	 * circular dependency.  But the "sys" module has a dict called
	 * "modules" which maps loaded module names to the corresponding module
	 * objects.  We can then grab the exception from those objects.
	 */

	if ((sys = PyImport_ImportModule("sys")) == NULL)
		return (NULL);

	if ((sys_modules = PyObject_GetAttrString(sys, "modules")) == NULL)
		return (NULL);

	if ((pkg_actions = PyDict_GetItemString(sys_modules, "pkg.actions"))
	    == NULL) {
		/* No exception is set */
		PyErr_SetString(PyExc_KeyError, "pkg.actions");
		Py_DECREF(sys_modules);
		return (NULL);
	}
	Py_DECREF(sys_modules);

	/*
	 * Each reference is DECREF'd after retrieval as Python 2.x doesn't
	 * provide a module shutdown/cleanup hook.  Since these references are
	 * guaranteed to stay around until the module is unloaded, DECREF'ing
	 * them now ensures that garbage cleanup will work as expected during
	 * process exit.  This applies to the action type caching below as well.
	 */
	MalformedActionError = \
	    PyObject_GetAttrString(pkg_actions, "MalformedActionError");
	Py_DECREF(MalformedActionError);
	InvalidActionError = \
	    PyObject_GetAttrString(pkg_actions, "InvalidActionError");
	Py_DECREF(InvalidActionError);
	UnknownActionError = \
	    PyObject_GetAttrString(pkg_actions, "UnknownActionError");
	Py_DECREF(UnknownActionError);

	/*
	 * Retrieve the list of action types and then store a reference to each
	 * class for use during action construction.  (This allows avoiding the
	 * overhead of retrieving a new reference for each action constructed.)
	 */
	if ((action_types = PyObject_GetAttrString(pkg_actions,
	    "types")) == NULL) {
		PyErr_SetString(PyExc_KeyError, "pkg.actions.types missing!");
		return (NULL);
	}

	/*
	 * cache_class borrows the references to the action type objects; this
	 * is safe as they should remain valid as long as the module is loaded.
	 * (PyDict_GetItem* doesn't return a new reference.)
	 */
#define	cache_class(cache_var, name) \
	if ((cache_var = PyDict_GetItemString(action_types, name)) == NULL) { \
		PyErr_SetString(PyExc_KeyError, \
		    "Action type class missing: " name); \
		Py_DECREF(action_types); \
		return (NULL); \
	}

	cache_class(aclass_attribute, "set");
	cache_class(aclass_depend, "depend");
	cache_class(aclass_directory, "dir");
	cache_class(aclass_driver, "driver");
	cache_class(aclass_file, "file");
	cache_class(aclass_group, "group");
	cache_class(aclass_hardlink, "hardlink");
	cache_class(aclass_legacy, "legacy");
	cache_class(aclass_license, "license");
	cache_class(aclass_link, "link");
	cache_class(aclass_signature, "signature");
	cache_class(aclass_unknown, "unknown");
	cache_class(aclass_user, "user");

	Py_DECREF(action_types);

	return (m);
}

#if PY_MAJOR_VERSION >= 3
PyMODINIT_FUNC
PyInit__actions(void)
{
	return (moduleinit());
}
#else
PyMODINIT_FUNC
init_actions(void)
{
	moduleinit();
}
#endif
