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
 * Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
 */

#include <stdlib.h>
#include <stdio.h>
#include <liblist.h>

#include <Python.h>

static int copyto_liblist_cb(libnode_t *, void *, void *);

liblist_t *
liblist_alloc(void)
{
	liblist_t *n;

	if ((n = malloc(sizeof (liblist_t))) == NULL) {
		(void) PyErr_NoMemory();
		return (NULL);
	}

	n->head = NULL;
	n->tail = NULL;

	return (n);
}

void
liblist_free(liblist_t *lst)
{
	if (!lst)
		return;

	libnode_t *n = lst->head;
	libnode_t *temp = NULL;

	while (n) {
		liblist_free(n->verlist);
		temp = n;
		n = n->next;
		free(temp);
	}

	free(lst);
}

libnode_t *
liblist_add(liblist_t *lst, off_t off)
{
	libnode_t *n = NULL;

	if (!lst)
		return (NULL);

	if ((n = malloc(sizeof (libnode_t))) == NULL) {
		(void) PyErr_NoMemory();
		return (NULL);
	}

	n->nameoff = off;
	n->verlist = NULL;
	n->next = NULL;

	if (!lst->head) {
		lst->head = n;
		lst->tail = n;
	} else {
		lst->tail->next = n;
		lst->tail = n;
	}

	return (n);
}

int
liblist_foreach(liblist_t *lst, int (*cb)(libnode_t *, void *, void *),
    void *info, void *info2)
{
	if (!lst)
		return (0);

	libnode_t *n = lst->head;

	while (n) {
		if (cb(n, info, info2) == -1)
			return (-1);
		n = n->next;
	}

	return (0);
}

static liblist_t *
liblist_copy(liblist_t *lst)
{
	if (!lst)
		return (NULL);

	liblist_t *nl = NULL;

	if (!(nl = liblist_alloc()))
		return (NULL);

	if (liblist_foreach(lst, copyto_liblist_cb, nl, NULL) == -1)
		return (NULL);

	return (nl);
}


/* callbacks */

/*ARGSUSED2*/
int
setver_liblist_cb(libnode_t *n, void *info, void *info2)
{
	liblist_t *vers = (liblist_t *)info;

	libnode_t *vn = vers->head;

	while (vn) {
		if (vn->nameoff == n->nameoff) {
			if ((n->verlist = liblist_copy(vn->verlist)) == NULL)
				return (-1);
			break;
		}
		vn = vn->next;
	}

	return (0);
}

/*ARGSUSED2*/
static int
copyto_liblist_cb(libnode_t *n, void *info, void *info2)
{
	liblist_t *lst = (liblist_t *)info;
	if (liblist_add(lst, n->nameoff) == NULL)
		return (-1);
	lst->tail->verlist = liblist_copy(n->verlist);
	return (0);
}
