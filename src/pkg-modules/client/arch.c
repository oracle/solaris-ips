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
 * Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
 * Use is subject to license terms.
 */

#include "Python.h"

#include <sys/systeminfo.h>
#include <sys/types.h>
#include <alloca.h>
#include <stdlib.h>

static char *
get_sysinfo(int sicmd)
{
	char *buf;
	size_t bufsz = 32;
	long ret;

	if ((buf = malloc(bufsz)) == NULL)
		return (NULL);

	do {
		if ((ret = sysinfo(sicmd, buf, bufsz)) < 0)
			return (NULL);

		if (ret > bufsz) {
			bufsz = ret;
			if ((buf = realloc(buf, bufsz)) == NULL)
				return (NULL);
		} else
			break;
	} while (buf != NULL);

	return (buf);
}

/*
 * Return a list of strings constituting the architecture tags for the invoking
 * system.
 */
/*ARGSUSED*/
PyObject *
arch_isainfo(PyObject *self, PyObject *args)
{
	char *buf1;
	char *buf2;
	char *buf = NULL;
	PyObject *robj;

	buf1 = get_sysinfo(SI_ARCHITECTURE_64);
	buf2 = get_sysinfo(SI_ARCHITECTURE_32);

	if (buf1 == NULL && buf2 == NULL)
		return (NULL);

	if (buf1 == NULL && buf2)
		buf = buf2;

	if (buf2 == NULL && buf1)
		buf = buf1;

	if (buf == NULL) {
		robj = Py_BuildValue("[ss]", buf1, buf2);
	} else {
		robj = Py_BuildValue("[s]", buf);
	}

	free(buf1);
	free(buf2);

	return (robj);
}

/*
 * Return the release string ("5.11") for the invoking system.
 */
/*ARGSUSED*/
PyObject *
arch_release(PyObject *self, PyObject *args)
{
	char *buf = NULL;
	PyObject *robj;

	buf = get_sysinfo(SI_RELEASE);
	if (buf == NULL)
		return (NULL);

	robj = Py_BuildValue("s", buf);
	free(buf);

	return (robj);
}

/*
 * Return the platform tag ("i86pc") for the invoking system.
 */
/*ARGSUSED*/
PyObject *
arch_platform(PyObject *self, PyObject *args)
{
	char *buf = NULL;
	PyObject *robj;

	buf = get_sysinfo(SI_PLATFORM);
	if (buf == NULL)
		return (NULL);

	robj = Py_BuildValue("s", buf);
	free(buf);

	return (robj);
}

static PyMethodDef methods[] = {
	{ "get_isainfo", arch_isainfo, METH_VARARGS },
	{ "get_release", arch_release, METH_VARARGS },
	{ "get_platform", arch_platform, METH_VARARGS },
	{ NULL, NULL }
};

void initarch() {
	Py_InitModule("arch", methods);
}
