#!/bin/ksh -p
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

# To activate an ssh agent for your current shell, do
#
# $ eval `ssh-agent`
# $ ssh-add
#
# The ssh-add will iterate through your configured keys, asking for
# passwords for each.  It then caches the decrypted keys so that it can
# supply credentials to a requesting server automatically.

export ACCESS_LOG=${ACCESS_LOG:-access_log}
export LOG_HOME=$HOME/project/pkg/repo/log-scripts
export DATA_HOME=$HOME/project/pkg/data/log

# if ! ssh-add -l > /dev/null 2>&1; then
# 	echo "log: Give the SSH agent some keys."
# 	
# 	exit 1
# fi

cd $DATA_HOME

# scp -C -i key Tpkgstats@pkg.opensolaris.org:/var/apache2/logs/access_log access_log
# rsync -zP --rsync-path=/opt/sfw/bin/rsync Asch@pkg.opensolaris.org:/var/apache2/logs/access_log access_log

grep " /1p.png" access_log > access_log.ping
grep " /catalog" access_log > access_log.catalog
grep " /manifest" access_log > access_log.manifest
grep " /search" access_log > access_log.search

python $LOG_HOME/an_ping.py access_log.ping > ping.html
python $LOG_HOME/an_catalog.py access_log.catalog > catalog.html
python $LOG_HOME/an_manifest.py access_log.manifest > manifest.html
python $LOG_HOME/an_search.py access_log.search > search.html


