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
 * Copyright (c) 2023, Oracle and/or its affiliates.
 */

/*
 * The following is a C reimplementation of urllib.parse.quote function. IPS
 * uses quote so extensively that the standard pure Python implementation has
 * significant performance drawbacks.
 */

#include <Python.h>

#define	MAX_STACK_QUOTE_SIZE 1024

/*ARGSUSED*/
static PyObject *
fast_quote(PyObject *self, PyObject *args)
{
	const static char quote_map[256][3] = {
		"%00", "%01", "%02", "%03", "%04", "%05", "%06", "%07",
		"%08", "%09", "%0A", "%0B", "%0C", "%0D", "%0E", "%0F",
		"%10", "%11", "%12", "%13", "%14", "%15", "%16", "%17",
		"%18", "%19", "%1A", "%1B", "%1C", "%1D", "%1E", "%1F",
		"%20", "%21", "%22", "%23", "%24", "%25", "%26", "%27",
		"%28", "%29", "%2A", "%2B", "%2C", "-", ".", "/",
		"0", "1", "2", "3", "4", "5", "6", "7",
		"8", "9", "%3A", "%3B", "%3C", "%3D", "%3E", "%3F",
		"%40", "A", "B", "C", "D", "E", "F", "G",
		"H", "I", "J", "K", "L", "M", "N", "O",
		"P", "Q", "R", "S", "T", "U", "V", "W",
		"X", "Y", "Z", "%5B", "%5C", "%5D", "%5E", "_",
		"%60", "a", "b", "c", "d", "e", "f", "g",
		"h", "i", "j", "k", "l", "m", "n", "o",
		"p", "q", "r", "s", "t", "u", "v", "w",
		"x", "y", "z", "%7B", "%7C", "%7D", "~", "%7F",
		"%80", "%81", "%82", "%83", "%84", "%85", "%86", "%87",
		"%88", "%89", "%8A", "%8B", "%8C", "%8D", "%8E", "%8F",
		"%90", "%91", "%92", "%93", "%94", "%95", "%96", "%97",
		"%98", "%99", "%9A", "%9B", "%9C", "%9D", "%9E", "%9F",
		"%A0", "%A1", "%A2", "%A3", "%A4", "%A5", "%A6", "%A7",
		"%A8", "%A9", "%AA", "%AB", "%AC", "%AD", "%AE", "%AF",
		"%B0", "%B1", "%B2", "%B3", "%B4", "%B5", "%B6", "%B7",
		"%B8", "%B9", "%BA", "%BB", "%BC", "%BD", "%BE", "%BF",
		"%C0", "%C1", "%C2", "%C3", "%C4", "%C5", "%C6", "%C7",
		"%C8", "%C9", "%CA", "%CB", "%CC", "%CD", "%CE", "%CF",
		"%D0", "%D1", "%D2", "%D3", "%D4", "%D5", "%D6", "%D7",
		"%D8", "%D9", "%DA", "%DB", "%DC", "%DD", "%DE", "%DF",
		"%E0", "%E1", "%E2", "%E3", "%E4", "%E5", "%E6", "%E7",
		"%E8", "%E9", "%EA", "%EB", "%EC", "%ED", "%EE", "%EF",
		"%F0", "%F1", "%F2", "%F3", "%F4", "%F5", "%F6", "%F7",
		"%F8", "%F9", "%FA", "%FB", "%FC", "%FD", "%FE", "%FF"};

	int i, j;
	PyObject* string = NULL;
	if (!PyArg_ParseTuple(args, "O", &string)) {
		return (NULL);
	}

	if (PyBytes_Check(string)) {
		/* do nothing */
	} else if (PyUnicode_Check(string)) {
		/* convert to bytes like encode() would. */
		string = PyUnicode_AsEncodedString(string, NULL, NULL);
	} else {
		PyErr_SetString(PyExc_TypeError,
		    "argument 1 must be bytes or str");
		return (NULL);
	}

	Py_ssize_t size = PyBytes_GET_SIZE(string);
	const char *bstring = PyBytes_AS_STRING(string);

	if (size <= MAX_STACK_QUOTE_SIZE) {
		/*
		 * Short strings are handled directly on stack without
		 * the need to allocate additional memory.
		 */
		char buffer[MAX_STACK_QUOTE_SIZE * 3 + 1];

		for (i = 0, j = 0; i < size; i++) {
			const char *val = quote_map[(unsigned char)bstring[i]];
			buffer[j++] = val[0];
			if (val[1]) {
				buffer[j++] = val[1];
				buffer[j++] = val[2];
			}
		}
		buffer[j] = 0;
		return (PyUnicode_FromString(buffer));
	}

	/*
	 * This assumes that strings are mostly safe ASCII and won't
	 * be much longer when quoted.
	 */
	int mbuffer_size = size * 1.5;
	char *mbuffer;

	if ((mbuffer = (char *)PyMem_RawMalloc(mbuffer_size)) == NULL) {
		return (NULL);
	}

	for (i = 0, j = 0; i < size; i++) {
		/* Ensure enough space for a quoted value and trailing 0. */
		if (j >= mbuffer_size - 4) {
			mbuffer_size *= 1.5;
			if ((mbuffer = (char *)PyMem_RawRealloc(
			    mbuffer, mbuffer_size)) == NULL) {
				PyMem_RawFree(mbuffer);
				return (NULL);
			}
		}
		const char *val = quote_map[(unsigned char)bstring[i]];
		mbuffer[j++] = val[0];
		if (val[1]) {
			mbuffer[j++] = val[1];
			mbuffer[j++] = val[2];
		}
	}
	mbuffer[j] = 0;

	PyObject *res = PyUnicode_FromString(mbuffer);
	PyMem_RawFree(mbuffer);
	return (res);
}

static PyMethodDef methods[] = {
	{ "fast_quote", (PyCFunction)fast_quote,
	    METH_VARARGS },
	{ NULL, NULL, 0, NULL }
};

static struct PyModuleDef miscmodule = {
	PyModuleDef_HEAD_INIT,
	"_misc",
	NULL,
	-1,
	methods
};

PyMODINIT_FUNC
PyInit__misc(void)
{
	PyObject *module = PyModule_Create(&miscmodule);
	PyModule_AddIntConstant(
	    module, "MAX_STACK_QUOTE_SIZE", MAX_STACK_QUOTE_SIZE);
	return (module);
}
