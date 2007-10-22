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

#ifndef _ELFEXTRACT_H_
#define _ELFEXTRACT_H_

#include <sys/types.h>
#include "liblist.h"

#ifndef MIN
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#endif

typedef struct dyninfo {
	off_t		runpath;	/* offset in table of the runpath */
	off_t		def;		/* offset in table of the vdefname*/
	off_t		dynstr;		/* string table			  */
	liblist_t 	*deps;		/* dependency list (also contains */
					/* 	offsets)		  */
	liblist_t 	*vers;		/* version provided list (also	  */
					/* 	contains offsets)	  */
	unsigned char	hash[20];	/* SHA1 Hash of significant segs. */
	Elf		*elf;		/* elf data -- must be freed	  */
} dyninfo_t;

typedef struct hdrinfo {
	int type;			/* e_type		*/
	int bits;			/* 32/64		*/
	int arch;			/* e_machine		*/
	int data;			/* e_ident[EI_DATA]	*/
	int osabi;			/* e_ident[EI_OSABI]	*/
} hdrinfo_t;

extern int iself(int fd);
extern int iself32(int fd);
extern dyninfo_t *getdynamic(int fd);
extern void dyninfo_free(dyninfo_t *dyn);
extern hdrinfo_t *getheaderinfo(int fd);

extern char *pkg_string_from_type(int type);
extern char *pkg_string_from_arch(int arch);
extern char *pkg_string_from_data(int data);
extern char *pkg_string_from_osabi(int osabi);

#endif
