#!/usr/bin/python2.4
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
#

"""
Most of the generic unix methods of our superclass can be used on
Solaris. For the following methods, there is a Solaris-specific
implementation in the 'arch' extension module.
"""

import os
import subprocess
import tempfile

from os_unix import \
    get_group_by_name, get_user_by_name, get_name_by_gid, get_name_by_uid, \
    is_admin, get_userid, get_username, chown, rename, remove, link, \
    copyfile, split_path, get_root
from pkg.portable import ELF, EXEC, UNFOUND
import pkg.arch as arch

def get_isainfo():
        return arch.get_isainfo()

def get_release():
        return arch.get_release()

def get_platform():
        return arch.get_platform()

def get_file_type(actions, proto_dir):
        t_fd, t_path = tempfile.mkstemp()
        t_fh = os.fdopen(t_fd, "w")
        for a in actions:
                t_fh.write(os.path.join(proto_dir, a.attrs["path"]) + "\n")
        t_fh.close()
        res = subprocess.Popen(["/usr/bin/file", "-f", t_path],
            stdout=subprocess.PIPE).communicate()[0].splitlines()
        remove(t_path)
        assert(len(actions) == len(res))
        for i, file_out in enumerate(res):
                file_out = file_out.strip()
                a = actions[i]
                proto_file = os.path.join(proto_dir, a.attrs["path"])
                colon_cnt = proto_file.count(":") + 1
                tmp = file_out.split(":", colon_cnt)
                res_file_name = ":".join(tmp[0:colon_cnt])
                if res_file_name != proto_file:
                        raise RuntimeError("pf:%s rfn:%s file_out:%s" %
                            (proto_file, res_file_name, file_out))
                file_type = tmp[colon_cnt].strip().split()
                joined_ft = " ".join(file_type)
                if file_type[0] == "ELF":
                        yield ELF
                elif file_type[0] == "executable":
                        yield EXEC
                elif joined_ft == "cannot open: No such file or directory":
                        yield UNFOUND
                else:
                        yield " ".join(file_type)
                
