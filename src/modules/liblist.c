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

#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
#include <liblist.h>

static void copyto_liblist_cb(libnode_t *, void *, void *);

liblist_t *
liblist_alloc()
{
	liblist_t *n;

	if ((n = malloc(sizeof (liblist_t))) == NULL)
		return (NULL);

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

	if ((n = malloc(sizeof (libnode_t))) == NULL)
		return (NULL);

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

void
liblist_foreach(liblist_t *lst, void (*cb)(libnode_t *, void *, void *),
    void *info, void *info2)
{
	if (!lst)
		return;

	libnode_t *n = lst->head;

	while (n) {
		cb(n, info, info2);
		n = n->next;
	}
}

static liblist_t *
liblist_copy(liblist_t *lst)
{
	if (!lst)
		return (NULL);

	liblist_t *nl = NULL;

	if (!(nl = liblist_alloc()))
		return (NULL);

	liblist_foreach(lst, copyto_liblist_cb, nl, NULL);

	return (nl);
}


/* callbacks */

/*ARGSUSED2*/
void
setver_liblist_cb(libnode_t *n, void *info, void *info2)
{
	liblist_t *vers = (liblist_t *)info;

	libnode_t *vn = vers->head;

	while (vn) {
		if (vn->nameoff == n->nameoff) {
			n->verlist = liblist_copy(vn->verlist);
			break;
		}
		vn = vn->next;
	}
}

/*ARGSUSED2*/
static void
copyto_liblist_cb(libnode_t *n, void *info, void *info2)
{
	liblist_t *lst = (liblist_t *)info;
	if (liblist_add(lst, n->nameoff) == NULL) {
		assert(0); /* XXX */
	}
	lst->tail->verlist = liblist_copy(n->verlist);
}
