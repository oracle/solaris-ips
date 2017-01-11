#!/bin/ksh
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#
   
#
# This script is run to remove a cron job.
# Packages that needs to remove cron job that cannot be removed 
# during package update can add a hardlink in the new manifest
# to this script with the same path as the cron job executable.
# The script will remove the cron job during its first scheduled
# execution.
#
                   
. /lib/svc/share/pkg5_include.sh

remove_cronjob "" `basename $0` 
