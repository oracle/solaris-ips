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
#include "liblist.h"
#include "elfextract.h"

static void
pythonify_ver_liblist_cb(libnode_t *n, void *info, void *info2)
{
	PyObject *pverlist = (PyObject*)info;
	PyObject *ent;
	char *st = (char*)info2;

	ent = Py_BuildValue("s", (char*)(st + n->nameoff));

	PyList_Append(pverlist, ent);
}

static void
pythonify_liblist_cb(libnode_t *n, void *info, void *info2)
{
	PyObject *pdep = (PyObject*)info;
	char *st = (char*)info2;
	
	PyObject *pverlist;

	pverlist = PyList_New(0);
	liblist_foreach(n->verlist, pythonify_ver_liblist_cb, pverlist, st);
	PyList_Append(pdep,
	    Py_BuildValue("[s,O]", (char*)(st + n->nameoff), pverlist));
}

/*
 * Open a file named by python, setting an appropriate error on failure.
 */
int
py_get_fd(PyObject *args)
{
	int fd;
	char *f;
	
	if (PyArg_ParseTuple(args, "s", &f) == 0) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (-1);
	}

	if ((fd = open(f, O_RDONLY)) < 0) {
		PyErr_SetFromErrnoWithFilename(PyExc_OSError, f);
		return (-1);
	}

	return (fd);
}

/*
 * For ELF operations: Need to check if a file is an ELF object.
 */
PyObject *
elf_is_elf_object(PyObject *self, PyObject *args)
{
	int fd, ret;

	if ((fd = py_get_fd(args)) < 0)
		return (NULL);

	ret = iself(fd);

	close(fd);

	return (Py_BuildValue("i", ret));
}

/*
 * Returns information about the ELF file in a dictionary
 * of the following format:
 *
 *  { type: exe|so, bits: 32|64, arch: sparc|intel, end: lsb|msb }
 *
 * XXX Currently assumes only input types are exe or so,
 * 	and only architectures are "sparc" or "intel." 
 * 	There is room for improved granularity in both
 * 	fields.
 * 	
 */
PyObject *
get_info(PyObject *self, PyObject *args)
{
	int fd;
	int type = 0, bits = 0, arch = 0, data = 0;
	PyObject *pdict = NULL;
	
	if ((fd = py_get_fd(args)) < 0)
		return (NULL);

	if (iself32(fd)) {
		Elf32_Ehdr *hdr;
		if (!(hdr = gethead32(fd))) {
			PyErr_SetString(PyExc_RuntimeError, 
			    "failed to get ELF32 header");
		}
		else {
			type = hdr->e_type;
			bits = 32;
			arch = hdr->e_machine;
			data = hdr->e_ident[EI_DATA];
			free(hdr);
		}
	}
	else {
		Elf64_Ehdr *hdr;
		if (!(hdr = gethead64(fd))) {
			PyErr_SetString(PyExc_RuntimeError, 
			    "failed to get ELF64 header");
		}
		else {
			type = hdr->e_type;
			bits = 64;
			arch = hdr->e_machine;
			data = hdr->e_ident[EI_DATA];
			free(hdr);
		}
	}

	pdict = PyDict_New();
	PyDict_SetItemString(pdict, "type", 
	    Py_BuildValue("s", type == ET_EXEC ? "exe" : "so"));
	PyDict_SetItemString(pdict, "bits", Py_BuildValue("i", bits));
	PyDict_SetItemString(pdict, "arch",
	    Py_BuildValue("s", arch == EM_SPARC ? "sparc" : "intel"));
	PyDict_SetItemString(pdict, "end",
	    Py_BuildValue("s", data == ELFDATA2LSB ? "lsb" : "msb"));

	close(fd);
	return (pdict);
}

/*
 * Returns a dictionary with the relevant information.  No longer 
 * accurately titled "get_dynamic," as it returns the hash as well.
 *
 * The hash is currently of the following sections (when present):
 * 		.text .data .data1 .rodata .rodata1
 *
 * Dictionary format:
 * { runpath: "/path:/entries", deps: ["file", ["versionlist"]],
 * 	hash: "sha1hash" }
 *
 */
PyObject *
get_dynamic(PyObject *self, PyObject *args)
{
	int 	fd;
	dyninfo_t 	*dyn = NULL;
	PyObject	*pdep = NULL;
	PyObject	*pdict = NULL;

	if ((fd = py_get_fd(args)) < 0)
		return (NULL);

	if (iself32(fd))
		dyn = getdynamic32(fd);
	else
		dyn = getdynamic64(fd);

	if (!dyn) {
		PyErr_SetString(PyExc_RuntimeError,
		    "failed to load dynamic section");
		return (NULL);
	}
	
	pdep = PyList_New(0);
	liblist_foreach(dyn->deps, pythonify_liblist_cb, pdep, dyn->st);

	pdict = PyDict_New();
	PyDict_SetItemString(pdict, "runpath",
	    Py_BuildValue("s",(char*)(dyn->st + dyn->runpath)));
	PyDict_SetItemString(pdict, "deps", pdep);
	PyDict_SetItemString(pdict, "hash", Py_BuildValue("s", dyn->hash));
	
	liblist_free(dyn->deps);
	free(dyn->st);
	free(dyn);
	close(fd);

	return (pdict);
}

/* XXX below implemented in get_dynamic now? */


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

	return (NULL);
}

static PyMethodDef methods[] = {
	{ "is_elf_object", elf_is_elf_object, METH_VARARGS },
	{ "get_info", get_info, METH_VARARGS },
	{ "get_dynamic", get_dynamic, METH_VARARGS },
	{ NULL, NULL }
};

void initelf() {
	Py_InitModule("elf", methods);
}
