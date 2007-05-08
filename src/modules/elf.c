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

#include <elf.h>
#include <gelf.h>

#include <sys/stat.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <port.h>
#include <unistd.h>

#include "Python.h"

/*
 * For ELF operations: Need to check if a file is an ELF object.
 */
PyObject *
elf_is_elf_object(PyObject *self, PyObject *args)
{
	char *f;
	int fd;
	char ident[EI_NIDENT];

	if (PyArg_ParseTuple(args, "s", &f) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}

	if ((fd = open(f, O_RDONLY)) < 0) {
		PyErr_SetFromErrnoWithFilename(PyExc_OSError, f);
		return (NULL);
	}

	if (read(fd, ident, EI_NIDENT) < EI_NIDENT)
		/* Can't be a valid ELF file. */
		return (Py_BuildValue("i", 0));

	if (strncmp(ident, ELFMAG, strlen(ELFMAG)) == 0)
		return (Py_BuildValue("i", 1));

	return (Py_BuildValue("i", 0));
}

PyObject *
get_info(PyObject *self, PyObject *args)
{
	char *f;

	if (PyArg_ParseTuple(args, "s", &f) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}
}

/*
 * For ELF-completeness: Need to get the DT_NEEDED and DT_RPATH (and also
 * DT_RUNPATH??) values out of an ELF object's .dynamic section.
 */
/*
 * Returns directories as a string?  Or as a list?
 */
PyObject *
get_runpath(PyObject *self, PyObject *args)
{
	char *f;

	if (PyArg_ParseTuple(args, "s", &f) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}
}

/*
 * Returns list of needed libraries.
 */
PyObject *
get_libs(PyObject *self, PyObject *args)
{
	char *f;

	if (PyArg_ParseTuple(args, "s", &f) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}
}

/*
 * For advanced ELF-completeness:  Need to examine the version bindings on each
 * needed library and also to extract the versions offered by a particular
 * library.
 */
/*
 * Returns list of needed library-version pairs.
 *
 * XXX get_versioned_libs and get_libs() can share a common core function.
 */
PyObject *
get_versioned_libs(PyObject *self, PyObject *args)
{
	char *f;

	if (PyArg_ParseTuple(args, "s", &f) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}
}

/*
 * For ELF nontriviality: Need to turn an ELF object into a unique hash.
 *
 * From Eric Saxe's investigations, we see that the following sections can
 * generally be ignored:
 *
 *    .SUNW_signature, .comment, .SUNW_ctf, .debug, .plt, .rela.bss, .rela.plt,
 *    .line, .note
 *
 * Conversely, the following sections are generally significant:
 *
 *    .rodata.str1.8, .rodata.str1.1, .rodata, .data1, .data, .text
 *
 * Accordingly, we will hash on the latter group of sections to determine our
 * ELF hash.
 *
 * XXX Should we hash in C, or defer to a higher level function?
 */
PyObject *
get_significant_sections(PyObject *self, PyObject *args)
{
	char *f;

	if (PyArg_ParseTuple(args, "s", &f) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (NULL);
	}
}

static PyMethodDef methods[] = {
	{ "is_elf_object", elf_is_elf_object, METH_VARARGS },
	{ NULL, NULL }
};

void initelf() {
	Py_InitModule("elf", methods);
}
