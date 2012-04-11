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
 * Copyright (c) 2011, 2012 Oracle and/or its affiliates. All rights reserved.
 */

/*
 * Notify zoneproxyd when a zone is added or removed.  If zoneproxyd is not
 * running, this does nothing.
 */

#include <sys/types.h>
#include <door.h>
#include <errno.h>
#include <fcntl.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <zone.h>
#include <zoneproxy_impl.h>

static void
usage(void)
{
	(void) fprintf(stderr, "Usage: zoneproxy-adm [-R] zonename\n");
	(void) fprintf(stderr,
	    "\tNote: zoneproxy-adm should not be run directly.\n");
	exit(2);
}

static void
notify_zoneproxyd(zoneid_t zoneid, boolean_t remove)
{
	int cmd[2];
	int fd;
	door_arg_t params;

	fd = open(ZP_DOOR_PATH, O_RDONLY);
	if (fd < 0)
		return;

	if (remove) {
		cmd[0] = ZP_CMD_ZONE_REMOVED;
	} else {
		cmd[0] = ZP_CMD_ZONE_ADDED;
	}
	cmd[1] = zoneid;
	params.data_ptr = (char *)cmd;
	params.data_size = sizeof (cmd);
	params.desc_ptr = NULL;
	params.desc_num = 0;
	params.rbuf = NULL;
	params.rsize = NULL;
	(void) door_call(fd, &params);
	(void) close(fd);
}

int
main(int argc, char *argv[])
{
	int opt;
	boolean_t remove = B_FALSE;
	zoneid_t zoneid;

	while ((opt = getopt(argc, argv, "R")) != EOF) {
		switch (opt) {
		case 'R':
			remove = B_TRUE;
			break;
		default:
			usage();
		}
	}

	if (argc - optind != 1) {
		usage();
	}

	zoneid = getzoneidbyname(argv[optind]);

	if (zoneid == -1) {
		(void) fprintf(stderr, "unable to get zone id for zone: %s",
		    argv[optind]);
		exit(1);
	}

	notify_zoneproxyd(zoneid, remove);

	return 0;
}
