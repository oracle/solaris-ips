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

#ifndef _LIBLIST_H_
#define _LIBLIST_H_

#include <sys/types.h>

struct libnode;
struct liblist;

typedef struct libnode {
	off_t		nameoff;	/* offset of name of this node in */
					/* a particular name table 	  */
	struct liblist	*verlist;	/* version string list head	  */
	struct libnode	*next;		/* next node			  */
} libnode_t;

typedef struct liblist {
	libnode_t	*head;
	libnode_t	*tail;
} liblist_t;


/* liblist utils */
liblist_t *liblist_alloc();
void liblist_free(liblist_t *lst);
libnode_t *liblist_add(liblist_t *lst, off_t off);
void liblist_foreach(liblist_t *lst, void (*cb)(libnode_t *, void *, void *), 
    void *info, void *info2);

/* callbacks */
void setver_liblist_cb(libnode_t *n, void *info, void *info2);

#endif	/* _LIBLIST_H_ */
