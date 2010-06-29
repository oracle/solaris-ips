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
 * Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
 */

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <libgen.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stropts.h>
#include <sys/ioccom.h>
#include <sys/stat.h>
#include <sys/systeminfo.h>
#include <sys/types.h>
#include <sys/varargs.h>
#include <unistd.h>
#include <libintl.h>
#include <locale.h>

#include <libzonecfg.h>

static void usage_err(void) __NORETURN;
static void usage(char *msg, ...) __NORETURN;

static char *bname = NULL;

#if !defined(TEXT_DOMAIN)		/* should be defined by cc -D */
#define	TEXT_DOMAIN	"SYS_TEST"	/* Use this only if it wasn't */
#endif

static void
usage_err(void)
{
	(void) printf(gettext("%s ipkg brand error: invalid usage\n"), bname);

	(void) fprintf(stderr,
	    gettext("usage:\t%s verify <xml file>\n\n"), bname);

	exit(1);
}

static void
err(char *msg, ...)
{
	char	buf[1024];
	va_list	ap;

	va_start(ap, msg);
	/*LINTED*/
	(void) vsnprintf(buf, sizeof (buf), msg, ap);
	va_end(ap);

	(void) printf(gettext("%s ipkg brand error: %s\n"), bname, buf);

	exit(1);
	/*NOTREACHED*/
}

static int
do_verify(char *xmlfile)
{
	zone_dochandle_t	handle;
	struct zone_fstab	fstab;
	struct zone_dstab	dstab;

	if ((handle = zonecfg_init_handle()) == NULL)
		err(gettext("internal libzonecfg.so.1 error"), 0);

	if (zonecfg_get_xml_handle(xmlfile, handle) != Z_OK) {
		zonecfg_fini_handle(handle);
		err(gettext("zonecfg provided an invalid XML file"));
	}

	zonecfg_fini_handle(handle);
	return (0);
}

int
main(int argc, char *argv[])
{
	(void) setlocale(LC_ALL, "");
	(void) textdomain(TEXT_DOMAIN);

	bname = basename(argv[0]);

	if (argc < 3)
		usage_err();

	if (strcmp(argv[1], "verify") == 0) {
		if (argc != 3)
			usage_err();
		return (do_verify(argv[2]));
	}

	usage_err();
	/*NOTREACHED*/
}
