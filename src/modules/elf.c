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
 * Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
 * Use is subject to license terms.
 */

#include <sys/stat.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <unistd.h>

#if defined (__SVR4) && defined (__sun)
/* Solaris has a built-in SHA-1 library interface */
#include <sha1.h>
#else
/*
 * All others can use OpenSSL, but OpenSSL's method names
 * are slightly different
 */
#include <openssl/sha.h>
#define SHA1_CTX SHA_CTX
#define SHA1Update SHA1_Update
#define SHA1Init SHA1_Init
#define SHA1Final SHA1_Final
#endif
#include <elf.h>
#include <gelf.h>

#include <liblist.h>
#include <elfextract.h>

#include <Python.h>

static int
pythonify_ver_liblist_cb(libnode_t *n, void *info, void *info2)
{
	PyObject *pverlist = (PyObject *)info;
	PyObject *ent;
	dyninfo_t *dyn = (dyninfo_t *)info2;
	char *str;
	
	if ((str = elf_strptr(dyn->elf, dyn->dynstr, n->nameoff)) == NULL) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		return (-1);
	}

	ent = Py_BuildValue("s", str);

	return (PyList_Append(pverlist, ent));
}

static int
pythonify_2dliblist_cb(libnode_t *n, void *info, void *info2)
{
	PyObject *pdep = (PyObject *)info;
	dyninfo_t *dyn = (dyninfo_t *)info2;
	char *str;

	PyObject *pverlist;

	pverlist = PyList_New(0);
	if (liblist_foreach(
		n->verlist, pythonify_ver_liblist_cb, pverlist, dyn) == -1)
		return (-1);

	if ((str = elf_strptr(dyn->elf, dyn->dynstr, n->nameoff)) == NULL) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		return (-1);
	}

	return (PyList_Append(pdep, Py_BuildValue("[s,O]", str, pverlist)));
}

static int
pythonify_1dliblist_cb(libnode_t *n, void *info, void *info2)
{
	PyObject *pdef = (PyObject *)info;
	dyninfo_t *dyn = (dyninfo_t *)info2;
	char *str;

	if ((str = elf_strptr(dyn->elf, dyn->dynstr, n->nameoff)) == NULL) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		return (-1);
	}

	return (PyList_Append(pdef, Py_BuildValue("s", str)));
}
/*
 * Open a file named by python, setting an appropriate error on failure.
 */
static int
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
/*ARGSUSED*/
static PyObject *
elf_is_elf_object(PyObject *self, PyObject *args)
{
	int fd, ret;

	if ((fd = py_get_fd(args)) < 0)
		return (NULL);

	ret = iself(fd);

	(void) close(fd);

	if (ret == -1)
		return (NULL);

	return (Py_BuildValue("i", ret));
}

/*
 * Returns information about the ELF file in a dictionary
 * of the following format:
 *
 *  {
 *  	type: exe|so|core|rel,
 *  	bits: 32|64,
 *  	arch: sparc|x86|ppc|other|none,
 *  	end: lsb|msb,
 *  	osabi: none|linux|solaris|other
 *  }
 *
 *  XXX: I have yet to find a binary with osabi set to something
 *  aside from "none."
 */
/*ARGSUSED*/
static PyObject *
get_info(PyObject *self, PyObject *args)
{
	int fd;
	hdrinfo_t *hi = NULL;
	PyObject *pdict = NULL;

	if ((fd = py_get_fd(args)) < 0)
		return (NULL);

	if ((hi = getheaderinfo(fd)) == NULL)
		goto out;

	pdict = PyDict_New();
	PyDict_SetItemString(pdict, "type",
	    Py_BuildValue("s", pkg_string_from_type(hi->type)));
	PyDict_SetItemString(pdict, "bits", Py_BuildValue("i", hi->bits));
	PyDict_SetItemString(pdict, "arch",
	    Py_BuildValue("s", pkg_string_from_arch(hi->arch)));
	PyDict_SetItemString(pdict, "end",
	    Py_BuildValue("s", pkg_string_from_data(hi->data)));
	PyDict_SetItemString(pdict, "osabi",
	    Py_BuildValue("s", pkg_string_from_osabi(hi->osabi)));

out:
	if (hi != NULL)
		free(hi);
	(void) close(fd);
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
 *
 * {
 *	runpath: "/path:/entries",
 *	defs: ["version", ... ],
 *	deps: [["file", ["versionlist"]], ...],
 * 	hash: "sha1hash"
 * }
 *
 * If any item is empty or has no value, it is omitted from the
 * dictionary.
 *
 * XXX: Currently, defs contains some duplicate entries.  There
 * may be meaning attached to this, or it may just be something
 * worth trimming out at this stage or above.
 *
 */
/*ARGSUSED*/
static PyObject *
get_dynamic(PyObject *self, PyObject *args)
{
	int 	fd, i;
	dyninfo_t 	*dyn = NULL;
	PyObject	*pdep = NULL;
	PyObject	*pdef = NULL;
	PyObject	*pdict = NULL;
	char		hexhash[41];
	char		hexchars[17] = "0123456789abcdef";

	if ((fd = py_get_fd(args)) < 0)
		return (NULL);

	if ((dyn = getdynamic(fd)) == NULL)
		goto out;

	pdict = PyDict_New();
	if (dyn->deps->head) {
		pdep = PyList_New(0);
		if (liblist_foreach(
			dyn->deps, pythonify_2dliblist_cb, pdep, dyn) == -1)
			goto err;
		PyDict_SetItemString(pdict, "deps", pdep);
	}
	if (dyn->def) {
		char *str;

		pdef = PyList_New(0);
		if (liblist_foreach(
			dyn->vers, pythonify_1dliblist_cb, pdef, dyn) == -1)
			goto err;
		PyDict_SetItemString(pdict, "vers", pdef);
		if ((str = elf_strptr(
			dyn->elf, dyn->dynstr, dyn->def)) == NULL) {
			PyErr_SetString(ElfError, elf_errmsg(-1));
			goto err;
		}
		PyDict_SetItemString(pdict, "def", Py_BuildValue("s", str));
	}
	if (dyn->runpath) {
		char *str;

		if ((str = elf_strptr(
			dyn->elf, dyn->dynstr, dyn->runpath)) == NULL) {
			PyErr_SetString(ElfError, elf_errmsg(-1));
			goto err;
		}
		PyDict_SetItemString(pdict, "runpath", Py_BuildValue("s", str));
	}

	for (i = 0; i < 20; i++) {
		hexhash[2 * i] = hexchars[(dyn->hash[i] & 0xf0) >> 4];
		hexhash[2 * i + 1] = hexchars[dyn->hash[i] & 0x0f];
	}
	hexhash[40] = '\0';

	PyDict_SetItemString(pdict, "hash", Py_BuildValue("s", hexhash));
	goto out;

err:
	PyDict_Clear(pdict);
	Py_DECREF(pdict);
	pdict = NULL;

out:
	if (dyn != NULL)
		dyninfo_free(dyn);

	(void) close(fd);
	return (pdict);
}

/*
 * XXX: Implemented as part of get_dynamic above.
 *
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
 */


static PyMethodDef methods[] = {
	{ "is_elf_object", elf_is_elf_object, METH_VARARGS },
	{ "get_info", get_info, METH_VARARGS },
	{ "get_dynamic", get_dynamic, METH_VARARGS },
	{ NULL, NULL }
};

PyMODINIT_FUNC
initelf(void)
{
	PyObject *m;

	if ((m = Py_InitModule("elf", methods)) == NULL)
		return;

	ElfError = PyErr_NewException("pkg.elf.ElfError", NULL, NULL);
	if (ElfError == NULL)
		return;

	Py_INCREF(ElfError);
	PyModule_AddObject(m, "ElfError", ElfError);
}
