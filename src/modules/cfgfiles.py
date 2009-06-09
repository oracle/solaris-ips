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

#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# NOTE: This module is inherently posix specific.  Care is taken in the modules
# that use this module to not use it on other operating systems.

import os
import fcntl
import re
import tempfile
import sys
import time
import datetime

class CfgFile(object):
    """ Solaris configuration file editor... make it easier to
        modify Solaris line-oriented configuration files from actions """

    def __init__(self, filename, separator, column_names, keys, 
                 comment_match="#", continuation_lines=False):
        
        self.filename = filename
        self.separator = separator
        self.continuation_lines = continuation_lines
        self.needswriting = False

        l = [(v[1][0], v[1][1], v[0]) for v in column_names.items()]
        l.sort()
        self.column_names = [e[2] for e in l]
        self.default_values = dict((e[2], e[1]) for e in l)

        self.comment_regexp = re.compile(comment_match)
        self.max_lengths=dict((n, 8) for n in self.column_names)

        if isinstance(keys, str):
            self.keys = [keys]
        else:
            self.keys = keys
            
        self.index = {}

        assert(set(self.column_names) >= set(self.keys))

    def __str__(self):
        return "CfgFile(%s):%s:%s:%s" % \
            (self.filename, self.keys, self.column_names, self.index) 

    def getcolumnnames(self):
        return self.column_names

    def iscommentline(self, line):
        return self.comment_regexp.match(line)
    
    def splitline(self, line):
        cols = line.split(self.separator)

        if len(cols) != len(self.column_names):
            raise RuntimeError, "line %s in %s has %d columns" % \
                (line, self.filename, len(cols))
        return cols

    def getfilelines(self):
        """ given self, return list of lines to be printed.
            default impl preserves orignal + insertion order"""
        lines = [[self.index[l][2],self.index[l][0]] for l in self.index]
        lines.sort()
        return [l[1] for l in lines]


    def readfile(self):
        if os.path.exists(self.filename):
            file = open(self.filename)
            lineno = 1
            for line in file:
                linecnt = 1;

                while self.continuation_lines and line[-2:] == "\\\n":
                    linecnt += 1
                    line += file.next()
                    
                line = line.rstrip("\n")
                if self.iscommentline(line):
                    self.index[lineno] = \
                        (line, None, lineno)
                else:
                    cols = self.splitline(line)
                    dic = dict(zip(self.column_names, cols))
                    self.index[tuple(dic[k] for k in self.keys)] = \
                        (line, dic, lineno)
#                for k, v in dic.iteritems():
#                    self.max_lengths[k] = max(len(v), self.max_lengths[k])
                lineno += linecnt
            file.close()
            self.needswriting = False
        else:
            print "no such file %s" % self.filename

    def getvalue(self, template):
        val = self.index.get(tuple(template[k] for k in self.keys), None)
        if val:
            return val[1]
        else:
            return {}

    def getdefaultvalues(self):
        """ returns dictionary of default string values - ignores
        other types """
        return dict((i, self.default_values[i])
                    for i in self.default_values
                    if isinstance(self.default_values[i], str))
    
    def updatevalue(self, template):
        """ update existing record, using orig values if missing 
            in template"""
        orig = self.index[tuple(template[k] for k in self.keys)].copy()
        for name in self.column_names:
            if name in template:
                orig[name] = template[name]
        self.setvalue(orig)

    def setvalue(self, template):
        """ set value of record in file, replacing any previous def.
            for any missing info, use defaults.  Will insert new value """
        # bring in any missing values as defaults if not None
        for field in self.column_names:
            if field not in template:
                if self.default_values[field] is None:
                    raise RuntimeError, \
                        "Required attribute %s is missing" % field
                elif callable(self.default_values[field]):
                    template[field] = self.default_values[field]()
                else:
                    template[field] = self.default_values[field]

        orig = self.index.get(tuple(template[k] for k in self.keys), None)

        if orig:
            lineno = orig[2]
            del self.index[tuple(orig[1][k] for k in self.keys)]
        else:
            lineno = max((self.index[k][2] for k in self.index)) + 1
        line = self.valuetostr(template)
        self.index[tuple(template[k] for k in self.keys)] = \
            (line, template, lineno)
        self.needswriting = True

    def removevalue(self, template):
        del self.index[tuple(template[k] for k in self.keys)]
        self.needswriting = True

    def valuetostr(self, template):
        """ print out values in file format """
        return("%s" % self.separator.join(
            [
                "%s" % template[key] for key in self.column_names
                ]))
            
    def writefile(self):
        
        if not self.needswriting:
            return

        st = os.stat(self.filename)

        tempdata = tempfile.mkstemp(dir=os.path.dirname(self.filename))
        file = os.fdopen(tempdata[0], "w")
        name = tempdata[1]

        os.chmod(name, st.st_mode)
        os.chown(name, st.st_uid, st.st_gid)

        for l in self.getfilelines():
            print >>file, l
            
        file.close()

        os.rename(name, self.filename)
    
class PasswordFile(CfgFile):
    """Manage the passwd and shadow together. Note that
       insertion/deletion of +/- fields isn't supported"""
    def __init__(self, path_prefix, lock=False):
        self.password_file = \
            CfgFile(os.path.join(path_prefix, "etc/passwd"),
                    ":",
                    {"username"   : (1, None),
                     "password"   : (2, "x"),
                     "uid"        : (3, None),
                     "gid"        : (4, None), 
                     "gcos-field" : (5, "& User"), 
                     "home-dir"   : (6, "/"),
                     "login-shell": (7, "")
                     },
                    "username", comment_match="[-+]")
        days = datetime.timedelta(seconds=time.time()).days
        self.shadow_file = \
            CfgFile(os.path.join(path_prefix, "etc/shadow"),
                    ":",
                    {"username"   : (1, None),
                     "password"   : (2, "*LK*"),
                     "lastchg"    : (3, days),               
                     "min"        : (4, ""),
                     "max"        : (5, ""),
                     "warn"       : (6, ""),
                     "inactive"   : (7, ""),
                     "expire"     : (8, ""),
                     "flag"       : (9, "")
                     },
                    "username", comment_match="[-+]")
        self.path_prefix = path_prefix
        self.lockfd = None
        if lock:
            self.lockfile()
        self.readfile()
        self.password_file.default_values["uid"] = self.getnextuid()

    def __str__(self):
        return "PasswordFile: [%s %s]" % (self.password_file, self.shadow_file)
 
    def getvalue(self, template):
        """ merge dbs... do passwd file first to get right passwd value"""
        c = self.password_file.getvalue(template).copy() 
        c.update(self.shadow_file.getvalue(template))
        return c

    def updatevalue(self, template):
        copy = template.copy()
        if "password" in copy:
            copy["password"]=""
        self.password_file.updatevalue(copy)
        self.shadow_file.updatevalue(template)    

    def setvalue(self, template):
        # ignore attempts to set passwd for passwd file
        copy = template.copy()
        if "password" in copy:
            copy["password"]="x"
        self.password_file.setvalue(copy)
        self.shadow_file.setvalue(template)

    def removevalue(self, template):
        self.password_file.removevalue(template)
        self.shadow_file.removevalue(template)

    def getnextuid(self):
        """returns next free system (<=99) uid""" 
        uids=[]
        for t in self.password_file.index.itervalues():
            if t[1]:
                uids.append(t[1]["uid"])
        for i in range(100):
            if str(i) not in uids:
                return i
        raise RuntimeError, "No free system uids"

    def getcolumnnames(self):
        names = self.password_file.column_names.copy()
        names.update(self.shadow_file.column_names)
        return names

    def readfile(self):
        self.password_file.readfile()
        self.shadow_file.readfile()

    def writefile(self):
        self.password_file.writefile()
        self.shadow_file.writefile()

    def getuser(self, username):
        return self.getvalue({"username" : username})
    
    def getdefaultvalues(self):
        a = self.password_file.getdefaultvalues()
        a.update(self.shadow_file.getdefaultvalues())
        return a

    def lockfile(self):
        fn = os.path.join(self.path_prefix, "etc/.pwd.lock")
        self.lockfd = file(fn, 'w')
        os.chmod(fn, 0600)
        fcntl.lockf(self.lockfd, fcntl.LOCK_EX, 0,0,0)
        
    def unlockfile(self):
        fcntl.lockf(self.lockfd, fcntl.LOCK_EX, 0,0,0)
        self.lockfd.close()
        self.lockfd = None
        
class GroupFile(CfgFile):
    """ manage the group file"""
    def __init__(self, path_prefix):
        CfgFile.__init__(self, os.path.join(path_prefix, "etc/group"),
                         ":",
                         {"groupname"  : (1, None),
                          "password"   : (2, ""),
                          "gid"        : (3, None),
                          "user-list"  : (4, "")
                          },
                         "groupname", comment_match="[+-]")
    
        self.readfile()
        self.default_values["gid"] = self.getnextgid()

    def getnextgid(self):
        """returns next free system (<=99) gid""" 
        gids=[]
        for t in self.index.itervalues():
            if t[1]:
                gids.append(t[1]["gid"])
        for i in range(100):
            if str(i) not in gids:
                return i
        raise RuntimeError, "No free system gids"

    def adduser(self, groupname, username):
        """"add named user to group; does not check if user exists"""
        group = self.getvalue({"groupname":groupname})
        if not group:
            raise RuntimeError, "No such group %s" % groupname
        users = set(group["user-list"].replace(","," ").split())
        users.add(username)
        group["user-list"] = ",".join(users)
        self.setvalue(group)

    def subuser(self, groupname, username):
        """ remove named user from group """
        group = self.getvalue({"groupname":groupname})
        if not group:
            raise RuntimeError, "No such group %s" % groupname
        users = set(group["user-list"].replace(","," ").split())
        if username not in users:
            raise RuntimeError, "User %s not in group %s" % (
                username, groupname)
        users.remove(username)
        group["user-list"] = ",".join(users)
        self.setvalue(group)
     
    def getgroups(self, username):
        """ return list of additional groups user belongs to """
        return sorted([
                t[1]["groupname"] 
                for t in self.index.values()
                if username in t[1]["user-list"].split(",")
                ])

    def setgroups(self, username, groups):
        current = self.getgroups(username)

        removals = set(current) - set(groups)
        additions = set(groups) - set(current)
        for g in removals:
            self.subuser(g, username)
        for g in additions:
            self.adduser(g, username)        

    def removeuser(self, username):
        for g in self.getgroups(username):
            self.subuser(g, username)
        
class FtpusersFile(CfgFile):
    """ If a username is present in this file, it denies that user
    the ability to use ftp"""

    def __init__(self, path_prefix):
        
        CfgFile.__init__(self, os.path.join(path_prefix, "etc/ftpd/ftpusers"),
                    " ",
                    {"username"   : (1, None)
                     },
                    "username")
        self.readfile()

    def getuser(self, username):
        """ returns true if user is allowed to use FTP - ie is NOT in file"""
        return not 'username' in self.getvalue({"username" : username})


    def adduser(self, username):
        """ add specified user to file, removing ability to use ftp"""
        self.setvalue({"username" : username})

    def subuser(self, username):
        """ remove specified user from file """
        self.removevalue({"username" : username})

    def setuser(self, username, value):
        if not value and self.getuser(username):
            self.adduser(username)
        elif not self.getuser(username):
            self.subuser(username)

class UserattrFile(CfgFile):
    """ manage the userattr file """
    def __init__(self, path_prefix):
        CfgFile.__init__(self, os.path.join(path_prefix, "etc/user_attr"),
                         ":",
                         {"username"    : (1, None),
                          "qualifier"   : (2, ""),
                          "reserved1"   : (3, ""),
                          "reserved2"   : (4, ""),
                          "attributes"  : (5, "")
                          },
                         "username")
        self.readfile()

    def iscommentline(self, line):
        return len(line) == 0 or self.comment_regexp.match(line)

    def splitline(self, line):
        """ return tokenized line, with attribute column a dictionary
            w/ lists for values"""
        cols = re.split("(?<=[^\\\\]):", line) #match non-escaped :
        if len(cols) != len(self.column_names):
            raise RuntimeError, "line %s in %s has %d columns rather than %s" % \
                (line, self.filename, len(cols), len(self.column_names))
        attributes=re.split("(?<=[^\\\\]);", cols[4]) # match non escaped ;

        d = {}
        for attr in attributes:
            a = re.split("(?<=[^\\\\])=", attr)
            d[a[0]] = a[1].split(",") 
        cols[4] = d
        return cols

    def valuetostr(self, template):
        """ print out string; replace attribute dictionary with proper
        string and use base class to convert entire record to a string """
        c = template.copy() # since we're mucking w/ this....
        attrdict = c["attributes"]

        str = "%s" % ";".join(
            [
                "%s=%s" % (key, ",".join(attrdict[key])) for key in attrdict
                ])
        c["attributes"] = str
        return CfgFile.valuetostr(self, c)



if __name__ == "__main__":

    if 0:
        pa = UserattrFile("/tmp")

        a = pa.getvalue({"username" : "postgres"})

        print a

        attrdict = a["attributes"]

        attrdict["profiles"].append("Wombat")
        attrdict["profiles"] = list(set(attrdict["profiles"]))

        pa.setvalue(a)

        pa.writefile()


        pa = UserattrFile("/tmp")

        a = pa.getvalue({"username" : "postgres"})

        print a

        attrdict = a["attributes"]

        p = set(attrdict["profiles"])
        p.discard("Wombat")
        attrdict["profiles"] = list(p)

        pa.setvalue(a)

        pa.writefile()

    ftp = FtpusersFile("/tmp")
    print ftp.getuser("root")
    ftp.setuser("root", True)
    print ftp.getuser("root")
    ftp.writefile()


    ftp = FtpusersFile("/tmp")
    ftp.setuser("root", False)
    print ftp.getuser("root")
    ftp.writefile()

    pw = PasswordFile("/tmp", lock=True)
    pw.unlockfile()
