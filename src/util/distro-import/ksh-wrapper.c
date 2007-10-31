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

/*
 * The version of ksh88 traditionally shipped with Solaris implements
 * three undocumented options which are used by the wordexp(3C)
 * implementation in libc to tell the shell to do word expansion.
 * wordexp() expects to call ksh(1) with its first argument being
 * <dash><control-E> along with optional 'u' and 'N' options in the same
 * string, signifying the WRDE_NOCMD and WRDE_REUSE flag values from
 * <wordexp.h> respectively.
 *
 * This program is based on the alternate, non-default but ksh93-aware
 * version of wordexp() from usr/src/lib/libc/port/regex/wordexp.c and
 * allows the use of the pre-existing wordexp() to be used as-is with
 * ksh93.  It replaces /usr/bin/ksh and acts as wrapper around ksh93(1),
 * turning the undocumented options into their ksh93 equivalents while
 * avoiding the requirement to recompile libc with WORDEXP_KSH93 set to
 * 1.  It attempts to return the same meaningful (!) exit codes returned
 * by the original /usr/bin/ksh and expected by the implementation of
 * wordexp() in the event of an error.
 *
 * When the standard version of libc is eventually compiled with
 * WORDEXP_KSH93 set to 1, this program should be deleted with all due
 * haste.
 */

/*
 * This code is MKS code ported to Solaris originally with minimum
 * modifications so that upgrades from MKS would readily integrate.
 * The MKS basis for this modification was:
 *
 *	$Id: wordexp.c 1.22 1994/11/21 18:24:50 miked
 *
 * Additional modifications have been made to this code to make it
 * 64-bit clean.
 */

/*
 * wordexp, wordfree -- POSIX.2 D11.2 word expansion routines.
 *
 * Copyright 1985, 1992 by Mortice Kern Systems Inc.  All rights reserved.
 * Modified by Roland Mainz <roland.mainz@nrubsig.org> to support ksh93.
 *
 */

#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <wordexp.h>

/*
 * |mystpcpy| - like |strcpy()| but returns the end of the buffer
 * We'll add this later (and a matching multibyte/widechar version)
 * as normal libc function.
 *
 * Copy string s2 to s1.  s1 must be large enough.
 * return s1-1 (position of string terminator ('\0') in destination buffer).
 */
static char *
mystpcpy(char *s1, const char *s2)
{
	while ((*s1++ = *s2++))
		;
	return (s1-1);
}

/*
 * Do word expansion.
 * We built a mini-script in |buff| which takes care of all details,
 * including stdin/stdout/stderr redirection, WRDE_NOCMD mode and
 * the word expansion itself.
 */
int
main(int argc, char *argv[])
{
	const char *word;
	int flags = 0;
	char *args[10];
	pid_t pid;
	char *cp;
	int rv = 0;
	int status;
	const char *path;

	path = "/usr/bin/ksh93";

	/*
	 * If not called from wordexp(), just exec ksh93.
	 */
	if (argc == 1 || argv[1][0] != '-' || argv[1][1] != '\005') {
		(void) execv(path, argv);
		exit(WRDE_ERRNO);

	}

	/*
	 * If 'u' or 'N' are specified, they will come in that order.
	 */
	cp = argv[1] + 2;
	if (*cp == 'u') {
		flags |= WRDE_UNDEF;
		++cp;
	}
	if (*cp == 'N')
		flags |= WRDE_NOCMD;

	/*
	 * Fork/exec shell
	 */
	if ((pid = fork()) == -1)
		exit(WRDE_ERRNO);

	if (pid == 0) {	 /* child */
		/*
		 * Calculate size of required buffer (which is size of the
		 * input string (|word|) plus all string literals below;
		 * this value MUST be adjusted each time the literals are
		 * changed!!!!).
		 */
		word = argv[2];
		size_t bufflen = 124+strlen(word); /* Length of |buff| */
		char *buff = malloc(bufflen);
		char *currbuffp; /* Current position of '\0' in |buff| */
		int i;

		i = 0;

		/* Start filling the buffer */
		buff[0] = '\0';
		currbuffp = buff;

		if (flags & WRDE_UNDEF)
			currbuffp = mystpcpy(currbuffp, "set -o nounset ; ");
		if ((flags & WRDE_SHOWERR) == 0) {
			/*
			 * The newline ('\n') is neccesary to make sure that
			 * the redirection to /dev/null is already active in
			 * the case the printf below contains a syntax
			 * error...
			 */
			currbuffp = mystpcpy(currbuffp, "exec 2>/dev/null\n");
		}
		/* Squish stdin */
		currbuffp = mystpcpy(currbuffp, "exec 0</dev/null\n");

		if (flags & WRDE_NOCMD) {
			/*
			 * Switch to restricted shell (rksh) mode here to
			 * put the word expansion into a "cage" which
			 * prevents users from executing external commands
			 * (outside those listed by ${PATH} (which we set
			 * explicitly to /usr/no/such/path/element/)).
			 */
			currbuffp = mystpcpy(currbuffp, "set -o restricted\n");

			(void) putenv("PATH=/usr/no/such/path/element/");

		}

		(void) snprintf(currbuffp, bufflen,
		    "print -f \"%%s\\000\" %s", word);

		args[i++] = strrchr(path, '/') + 1;
		args[i++] = "-c";
		args[i++] = buff;
		args[i++] = NULL;

		(void) execv(path, args);
		_exit(127);
	}

	if (waitpid(pid, &status, 0) == -1)
		exit(WRDE_ERRNO);

	rv = WEXITSTATUS(status); /* shell WRDE_* status */

	/*
	 * Map ksh93 errors to ksh88 errors expected by the traditional
	 * wordexp() implementation.
	 */
	if (rv != 0) {
		if (flags & WRDE_NOCMD)
			rv = 4;
		else if (flags & WRDE_UNDEF)
			rv = 5;
		else
			rv = 6;
	}
	return (rv);
}
