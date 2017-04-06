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
 * Copyright (c) 2010, 2012, Oracle and/or its affiliates. All rights reserved.
 * Use is subject to license terms.
 */

#ifndef	_ZONEPROXY_IMPL_H
#define	_ZONEPROXY_IMPL_H

#ifdef	__cplusplus
extern "C" {
#endif

#define	ZP_DOOR_PATH "/system/volatile/zoneproxy_door"


#define	ZP_CMD_NEW_LISTENER	1
#define	ZP_CMD_REMOVE_LISTENER	2
#define	ZP_CMD_ZONE_ADDED	3
#define	ZP_CMD_ZONE_REMOVED	4
#define	ZP_CMD_PING		5

#define	ZP_STATUS_OK		0
#define	ZP_STATUS_PERMISSION	1
#define	ZP_STATUS_INVALID	2
#define	ZP_STATUS_ERROR		3
#define	ZP_STATUS_UNKNOWN	4

#ifdef	__cplusplus
}
#endif

#endif	/* _ZONEPROXY_IMPL_H */
