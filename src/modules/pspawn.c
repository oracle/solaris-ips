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
 * Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
 * Use is subject to license terms.
 */

#include <Python.h>
#include <stdlib.h>
#include <string.h>
#include <spawn.h>
#include <sys/types.h>

/* SpawnFileAction documentation */
PyDoc_STRVAR(fileact_doc,
"SpawnFileAction() -> spawn file action object\n\
\n\
Creates a Python object that encapsulates the posix_spawn_file_action_t\n\
type.  This is used by the posix_spawn(3C) interface to control actions\n\
on file descriptors in the new process.  This object implements the\n\
following methods.\n\
\n\
add_close(fd) -- Add the file descriptor fd to the list of fds to be\n\
  closed in the new process.\n\
add_open(fd, path, oflag, mode) -- Open the file at path with flags \n\
  oflags and mode, assign it to the file descriptor numbered fd in the new\n\
  process.\n\
add_dup2(fd, newfd) -- Take the file descriptor in fd and dup2 it to newfd\n\
  in the newly created process.\n\
add_close_childfds(fd) -- Add all file descriptors above 2 except fd\n\
(optionally) to list of fds to be closed in the new process.\n\
\n\
Information about the underlying C interfaces can be found in the\n\
following man pages:\n\
\n\
posix_spawn(3C)\n\
posix_spawn_file_actions_addclose(3C)\n\
posix_spawn_file_actions_addopen(3C)\n\
posix_spawn_file_actions_adddup2(3C)\n\
\n");


/* FileAction typedef */

typedef struct {
	PyObject_HEAD
	posix_spawn_file_actions_t *fa;
} FileAction;

/* FileAction methods */

PyDoc_STRVAR(addclose_doc,
"add_close(fd) -> None\n\
\n\
Add the file descriptor fd to the list of descriptors to be closed in \n\
the new process.\n");

static PyObject *
fa_addclose(PyObject *obj, PyObject *args)
{
	int fd;
	int rc;
	PyObject *v;
	FileAction *self = (FileAction *)obj;

	rc = PyArg_ParseTuple(args, "i", &fd);
	if (rc == 0) {
		return (NULL);
	}

	rc = posix_spawn_file_actions_addclose(self->fa, fd);
	if (rc != 0) {
		v = Py_BuildValue("(is)", rc, strerror(rc));
		PyErr_SetObject(PyExc_OSError, v);
		Py_DECREF(v);
		return (NULL);
	}

	Py_INCREF(Py_None);
	return (Py_None);
}

PyDoc_STRVAR(adddup2_doc,
"add_dup2(fd, newfd) -> None\n\
\n\
Take the file descriptor in fd and dup2 it to newfd in the newly \n\
created process.\n");

static PyObject *
fa_adddup2(PyObject *obj, PyObject *args)
{
	int fd;
	int newfd;
	int rc;
	PyObject *v;
	FileAction *self = (FileAction *)obj;

	rc = PyArg_ParseTuple(args, "ii", &fd, &newfd);
	if (rc == 0) {
		return (NULL);
	}

	rc = posix_spawn_file_actions_adddup2(self->fa, fd, newfd);
	if (rc != 0) {
		v = Py_BuildValue("(is)", rc, strerror(rc));
		PyErr_SetObject(PyExc_OSError, v);
		Py_DECREF(v);
		return (NULL);
	}

	Py_INCREF(Py_None);
	return (Py_None);
}

PyDoc_STRVAR(addopen_doc,
"add_open(fd, path, oflag, mode) -> None\n\
\n\
Open the file at path with flags oflags and mode, assign it to \n\
the file descriptor numbered fd in the new process.\n");

static PyObject *
fa_addopen(PyObject *obj, PyObject *args)
{
	int fd;
	int rc;
	const char *path;
	int oflag;
	mode_t mode;
	PyObject *v;
	FileAction *self = (FileAction *)obj;

	rc = PyArg_ParseTuple(args, "isiI", &fd, &path, &oflag, &mode);
	if (rc == 0) {
		return (NULL);
	}

	rc = posix_spawn_file_actions_addopen(self->fa, fd, path, oflag, mode);
	if (rc != 0) {
		v = Py_BuildValue("(is)", rc, strerror(rc));
		PyErr_SetObject(PyExc_OSError, v);
		Py_DECREF(v);
		return (NULL);
	}

	Py_INCREF(Py_None);
	return (Py_None);
}

struct walk_data {
	int skip_fd;
	posix_spawn_file_actions_t *fap;
};

static int
walk_func(void *data, int fd)
{
	int rc;
	PyObject *v;
	struct walk_data *wd = (struct walk_data *)data;

	if ((fd > 2) && (fd != wd->skip_fd)) {
		rc = posix_spawn_file_actions_addclose(wd->fap, fd);
		if (rc != 0) {
			v = Py_BuildValue("(is)", rc, strerror(rc));
			PyErr_SetObject(PyExc_OSError, v);
			Py_DECREF(v);
			return (-1);
		}
	}

	return (0);
}

PyDoc_STRVAR(addclosechildfds_doc,
"add_close_childfds([except]) -> SpawnFileAction\n\
\n\
Add to a SpawnFileAction a series of 'closes' that will close all of\n\
the fds > 2 in the child process.  A single fd may be skipped, provided that\n\
it is given as the optional except argument.\n");

static PyObject *
fa_addclosechildfds(PyObject *obj, PyObject *args)
{
	int except_fd = -1;
	int rc;
	struct walk_data wd = { 0 };
	FileAction *self = (FileAction *)obj;

	rc = PyArg_ParseTuple(args, "|i", &except_fd);
	if (rc == 0) {
		return (NULL);
	}

	/* set up walk_data for fdwalk */
	wd.skip_fd = except_fd;
	wd.fap = self->fa;

	/* Perform the walk.  PyErr set by walk_func */
	(void) fdwalk(walk_func, &wd);

	Py_INCREF(Py_None);
	return (Py_None);
}

/* FileAction method descriptor */

static PyMethodDef fa_methods[] = {
	{ "add_close", fa_addclose, METH_VARARGS, addclose_doc },
	{ "add_open", fa_addopen, METH_VARARGS, addopen_doc },
	{ "add_dup2", fa_adddup2, METH_VARARGS, adddup2_doc },
	{ "add_close_childfds", fa_addclosechildfds, METH_VARARGS, addclosechildfds_doc },
	{ NULL, NULL }  /* Sentinel */
};

/* FileAction object functions */

static PyObject *
fa_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	FileAction *new;

	new = (FileAction *)type->tp_alloc(type, 0);
	if (new == NULL) {
		return (NULL);
	}

	new->fa = malloc(sizeof (posix_spawn_file_actions_t));
	if (new->fa == NULL) {
		Py_DECREF(new);
		return (PyErr_NoMemory());
	}

	return ((PyObject *)new);
}

static int
fa_init(PyObject *obj, PyObject *args, PyObject *kwds)
{
	PyObject *v;
	int rc;
	FileAction *self = (FileAction *)obj;


	rc = posix_spawn_file_actions_init(self->fa);
	/*
	 * The file_actions routines don't set errno, so we have to use
	 * strerror, and create the exception tuple by hand.
	 */
	if (rc != 0) {
		v = Py_BuildValue("(is)", rc, strerror(rc));
		PyErr_SetObject(PyExc_OSError, v);
		Py_DECREF(v);
		return (-1);
	}

	return (0);
}

static void
fa_dealloc(PyObject *obj)
{
	FileAction *self = (FileAction *)obj;

	if (self->fa != NULL) {
		(void) posix_spawn_file_actions_destroy(self->fa);
		free(self->fa);
	}
	self->ob_type->tp_free((PyObject *)self);
}

/* FileAction object descriptor */

static PyTypeObject FileActionType = {
	PyObject_HEAD_INIT(NULL)
	0,				/* ob_size */
	"pkg.pspawn.FileAction",	/* tp_name */
	sizeof (FileAction),		/* tp_basicsize */
	0,				/* tp_itemsize */
	fa_dealloc,			/* tp_dealloc */
	0,				/* tp_print */
	0,				/* tp_getattr */
	0,				/* tp_setattr */
	0,				/* tp_compare */
	0,				/* tp_repri */
	0,				/* tp_as_number */
	0,				/* tp_as_sequence */
	0,				/* tp_as_mapping */
	0,				/* tp_hash */
	0,				/* tp_call */
	0,				/* tp_str */
	0,				/* tp_getattro */
	0,				/* tp_setattro */
	0,				/* tp_as_buffer */
	Py_TPFLAGS_DEFAULT,		/* tp_flags */
	fileact_doc,			/* tp_doc */
	0,				/* tp_traverse */
	0,				/* tp_clear */
	0,				/* tp_richcompare */
	0,				/* tp_weaklistoffset */
	0,				/* tp_iter */
	0,				/* tp_iternext */
	fa_methods,			/* tp_methods */
	0,				/* tp_members */
	0,				/* tp_getset */
	0,				/* tp_base */
	0,				/* tp_dict */
	0,				/* tp_descr_get */
	0,				/* tp_descr_set */
	0,				/* tp_dictoffset */
	fa_init,			/* tp_init */
	0,				/* tp_alloc */
	(newfunc)fa_new			/* tp_new */
};

/* Module methods */


PyDoc_STRVAR(spawnp_doc,
"posix_spawnp(file, args, fileactions=None, env=None) -> pid\n\
\n\
Invoke posix_spawnp(3C).  File is the name of the executeable file, \n\
args is a sequence of arguments supplied to the newly executed program. \n\
If fileactions is defined, it must be a SpawnFileActions object.  This \n\
defines what actions will be performed upon the file descriptors of \n\
the spawned executable.  The environment, if provided, also must \n\
be a sequence object.");

static PyObject *
pspawn(PyObject *self, PyObject *args, PyObject *kwds)
{
	pid_t pid;
	int rc;
	int len;
	int i;
	char *spawn_file;
	char **spawn_args;
	PyObject *in_args;
	PyObject *obj;
	PyObject *v;
	PyObject *args_seq;
	PyObject *retval = NULL;
	char **spawn_env = NULL;
	PyObject *in_env = NULL;
	PyObject *env_seq = NULL;
	FileAction *fileact = NULL;
	posix_spawn_file_actions_t *s_action = NULL;

	static char *kwlist[] = {"file", "args", "fileaction", "env", NULL};

	rc = PyArg_ParseTupleAndKeywords(args, kwds, "sO|OO", kwlist,
	    &spawn_file, &in_args, &fileact, &in_env);
	if (rc == 0) {
		return (NULL);
	}

	args_seq = PySequence_Fast(in_args, "Args must be a sequence type.");
	if (args_seq == NULL) {
		return (NULL);
	}
	len = PySequence_Size(args_seq);
	spawn_args = malloc(sizeof (char *) * (len + 1));
	if (spawn_args == NULL) {
		(void) PyErr_NoMemory();
		goto out_args;
	}

	for (i = 0; i < len; i++) {
		obj = PySequence_Fast_GET_ITEM(args_seq, i);
		spawn_args[i] = PyString_AsString(obj);
		/* AsString will set exception if it returns NULL */
		if (spawn_args[i] == NULL) {
			goto out_args;
		}
	}
	spawn_args[len] = NULL;

	/* Process env, if supplied by caller */
	if (in_env != NULL) {
		env_seq = PySequence_Fast(in_env,
		    "env must be a sequence type.");
		if (env_seq == NULL) {
			goto out_args;
		}
		len = PySequence_Size(env_seq);
		spawn_env = malloc(sizeof (char *) * (len + 1));
		if (spawn_env == NULL) {
			(void) PyErr_NoMemory();
			goto out_env;
		}

		for (i = 0; i < len; i++) {
			obj = PySequence_Fast_GET_ITEM(env_seq, i);
			spawn_env[i] = PyString_AsString(obj);
			/* AsString will set exception if it returns NULL */
			if (spawn_env[i] == NULL) {
				goto out_env;
			}
		}
		spawn_env[len] = NULL;
	}

	/* setup file actions, if passed by caller */
	if (fileact != NULL) {
		if (!PyObject_TypeCheck(fileact, &FileActionType)) {
			PyErr_SetString(PyExc_TypeError,
			    "fileact must be a SpawnFileAction object.");
			goto out_env;
		}
		s_action = fileact->fa;
	}

	/* Now do the actual spawn */
	rc = posix_spawnp(&pid, spawn_file, s_action, NULL, spawn_args,
	    spawn_env);
	if (rc != 0) {
		v = Py_BuildValue("(is)", rc, strerror(rc));
		PyErr_SetObject(PyExc_OSError, v);
		Py_DECREF(v);
		goto out_env;
	}

	/* Success.  Return the pid as an integer object. */
	retval = PyInt_FromLong(pid);

	/* cleanup.  Free memory, release unused references */
out_env:
	if (spawn_env) {
		free(spawn_env);
	}
	if (env_seq) {
		Py_DECREF(env_seq);
	}
out_args:
	if (spawn_args) {
		free(spawn_args);
	}
	Py_DECREF(args_seq);

	return (retval);
}


/* Module method descriptor */

static PyMethodDef module_methods[] = {
	{ "posix_spawnp", (PyCFunction)pspawn, METH_KEYWORDS, spawnp_doc },
	{ NULL, NULL }  /* Sentinel */
};

/* Module init */
PyMODINIT_FUNC
initpspawn(void)
{
	PyObject* m;

	if (PyType_Ready(&FileActionType) < 0) {
		return;
	}

	m = Py_InitModule3("pspawn", module_methods, "posix_spawn module");

	if (m == NULL) {
		return;
	}

	Py_INCREF(&FileActionType);
	PyModule_AddObject(m, "SpawnFileAction", (PyObject *)&FileActionType);
}
