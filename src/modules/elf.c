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
 *  Copyright (c) 2009, 2013, Oracle and/or its affiliates. All rights reserved.
 */

#include <sys/stat.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <unistd.h>

#include <elf.h>
#include <gelf.h>

#include <liblist.h>
#include <elfextract.h>

#include <Python.h>

/*
 * When getting information about ELF files, sometimes we want to decide
 * which types of hash we want to calculate. This structure is used to
 * return information from arg parsing Python method arguments.
 *
 * 'fd'      the file descriptor of an ELF file
 * 'sha1'    an integer > 0 if we should calculate an SHA-1 hash
 * 'sha256'  an integer > 0 if we should calculate an SHA-2 256 hash
 *
 */
typedef struct
{
    int fd;
    int sha1;
    int sha256;
} dargs_t;

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

static dargs_t
py_get_dyn_args(PyObject *args, PyObject *kwargs)
{
	int fd = -1;
	char *f;
        int get_sha1 = 1;
        int get_sha256 = 0;

        dargs_t dargs;
        dargs.fd = -1;
        /*
         * By default, we always get an SHA-1 hash, and never get an SHA-2
         * hash.
         */
        dargs.sha1 = 1;
        dargs.sha256 = 0;

        static char *kwlist[] = {"fd", "sha1", "sha256", NULL};

	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|ii", kwlist, &f,
            &get_sha1, &get_sha256)) {
		PyErr_SetString(PyExc_ValueError, "could not parse argument");
		return (dargs);
	}

	if ((fd = open(f, O_RDONLY)) < 0) {
		PyErr_SetFromErrnoWithFilename(PyExc_OSError, f);
		return (dargs);
	}

        dargs.fd = fd;
        dargs.sha1 = get_sha1;
        dargs.sha256 = get_sha256;
	return (dargs);
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
 * accurately titled "get_dynamic," as can return hashes as well.
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
 *      pkg.elf.sha256: "sha2hash"
 * }
 *
 * If any item is empty or has no value, it is omitted from the
 * dictionary.
 *
 * The keyword arguments "sha1" and "sha256" are allowed, which
 * take Python booleans, declaring which hashes should be
 * computed on the input file.
 *
 * XXX: Currently, defs contains some duplicate entries.  There
 * may be meaning attached to this, or it may just be something
 * worth trimming out at this stage or above.
 *
 */
/*ARGSUSED*/
static PyObject *
get_dynamic(PyObject *self, PyObject *args, PyObject *keywords)
{
	int 	i;
        dargs_t         dargs;
	dyninfo_t 	*dyn = NULL;
	PyObject	*pdep = NULL;
	PyObject	*pdef = NULL;
	PyObject	*pdict = NULL;
	char		hexhash[41];
        char            hexsha256[65];
	char		hexchars[17] = "0123456789abcdef";

	dargs = py_get_dyn_args(args, keywords);
        if (dargs.fd < 0)
		return (NULL);

	if ((dyn = getdynamic(dargs.fd, dargs.sha1, dargs.sha256)) == NULL)
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

        if (dargs.sha1 > 0) {
                for (i = 0; i < 20; i++) {
                        hexhash[2 * i] = hexchars[(dyn->hash[i] & 0xf0) >> 4];
                        hexhash[2 * i + 1] = hexchars[dyn->hash[i] & 0x0f];
                }
                hexhash[40] = '\0';
        	PyDict_SetItemString(pdict, "hash", Py_BuildValue("s", hexhash));
        }

        if (dargs.sha256 > 0) {
                for (i = 0; i < 32; i++) {
                        hexsha256[2 * i] = \
                            hexchars[(dyn->hash256[i] & 0xf0) >> 4];
                        hexsha256[2 * i + 1] = hexchars[dyn->hash256[i] & 0x0f];
                }
                hexsha256[64] = '\0';
                PyDict_SetItemString(pdict, "pkg.content-type.sha256",
                    Py_BuildValue("s", hexsha256));
        }
	goto out;

err:
	PyDict_Clear(pdict);
	Py_DECREF(pdict);
	pdict = NULL;

out:
	if (dyn != NULL)
            dyninfo_free(dyn);

	(void) close(dargs.fd);
	return (pdict);
}

static PyMethodDef methods[] = {
	{ "is_elf_object", elf_is_elf_object, METH_VARARGS },
	{ "get_info", get_info, METH_VARARGS },
	{ "get_dynamic", (PyCFunction)get_dynamic,
        METH_VARARGS | METH_KEYWORDS},
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
