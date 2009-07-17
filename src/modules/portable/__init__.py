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

# The portable module provide access to methods that require operating system-
# specific implementations. The module initialization logic selects the right
# implementation the module is loaded.  The module methods then
# delegate to the implementation class object. 
#
# The documentation for the methods is provided in this module.  To support
# another operating system, each of these methods must be implemented by the
# class for that operating system even if it is effectively a no-op. 
#
# The module and class must be named using os_[impl], where
# [impl] corresponds to the OS distro, name, or type of OS
# the class implements.  For example, to add specific support
# for mandrake linux (above and beyond existing support for
# generic unix), one would create os_mandrake.py.
#           
# The following high-level groups of methods are defined in this module:
#                
#   - Platform Attribute Methods: These methods give access to
#     attributes of the underlying platform not available through
#     existing python libraries.  For example, the list of implemented
#     ISAs of a given platform.
#              
#   - Account access: Retrieval of account information (users and
#     groups), in some cases for dormant, relocated OS images.
#             
#   - Miscellaneous filesystem operations: common operations that
#     differ in implementation or are only available on a subset
#     of OS or filesystem implementations, such as chown() or rename().  

# This module exports the methods defined below.  They are defined here as 
# not implemented to avoid pylint errors.  The included OS-specific module 
# redefines the methods with an OS-specific implementation.

# Platform Methods
# ----------------
def get_isainfo():
        """ Return the information for the OS's supported ISAs.
        This can be a list or a single string."""
        raise NotImplementedError

def get_release():
        """ Return the information for the OS's release version.  This
        must be a dot-separated set of integers (i.e. no alphabetic
        or punctuation)."""
        raise NotImplementedError
        
def get_platform():
        """ Return a string representing the current hardware model
        information, e.g. "i86pc"."""
        raise NotImplementedError

def get_file_type(paths):
        """ Return a list containing the file type for each file in paths."""
        raise NotImplementedError

# Account access
# --------------
def get_group_by_name(name, dirpath, use_file):
        """ Return the group ID for a group name.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        group ID is retrieved from the operating system.
        Exceptions:        
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def get_user_by_name(name, dirpath, use_file):
        """ Return the user ID for a user name.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        user ID is retrieved from the operating system.
        Exceptions:
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def get_name_by_gid(gid, dirpath, use_file):
        """ Return the group name for a group ID.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        group name is retrieved from the operating system.
        Exceptions:
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def get_name_by_uid(uid, dirpath, use_file):
        """ Return the user name for a user ID.
        If use_file is true, an OS-specific file from within the file tree
        rooted by dirpath will be consulted, if it exists. Otherwise, the 
        user name is retrieved from the operating system.
        Exceptions:
            KeyError if the specified group does not exist"""
        raise NotImplementedError

def is_admin():
        """ Return true if the invoking user has administrative
        privileges on the current runtime OS (e.g. are they the
        root user?)."""
        raise NotImplementedError

def get_userid():
        """ Return a string representing the invoking user's id."""
        raise NotImplementedError

def get_username():
        """ Return a string representing the invoking user's username."""
        raise NotImplementedError


# Miscellaneous filesystem operations
# -----------------------------------
def chown(path, owner, group):
        """ Change ownership of a file in an OS-specific way.
        The owner and group ownership information should be applied to
        the given file, if applicable on the current runtime OS.
        Exceptions:        
            EnvironmentError (or subclass) if the path does not exist
            or ownership cannot be changed"""
        raise NotImplementedError

def rename(src, dst):
        """ Change the name of the given file, using the most
        appropriate method for the OS.
        Exceptions:
            OSError (or subclass) if the source path does not exist
            EnvironmentError if the rename fails."""
        raise NotImplementedError

def link(src, dst):
        """ Link the src to the dst if supported, otherwise copy
        Exceptions:
           OSError (or subclass) if the source path does not exist or the link
           or copy files"""
        raise NotImplementedError

def remove(path):
        """ Remove the given file in an OS-specific way
        Exceptions:
           OSError (or subclass) if the source path does not exist or 
           the file cannot be removed"""
        raise NotImplementedError

def copyfile(src, dst):
        """ Copy the contents of the file named src to a file named dst.
        If dst already exists, it will be replaced. src and dst are
        path names given as strings.
        This is similar to python's shutil.copyfile() except that
        the intention is to deal with platform specifics, such as
        copying metadata associated with the file (e.g. Resource
        forks on Mac OS X).
        Exceptions: IOError if the destination location is not writable"""
        raise NotImplementedError

def split_path(path):
        """ Splits a path and gives back the components of the path.  
        This is intended to hide platform-specific details about splitting
        a path into its components.  This interface is similar to
        os.path.split() except that the entire path is split, not just
        the head/tail.

        For platforms where there are additional components (like
        a windows drive letter), these should be discarded before
        performing the split."""
        raise NotImplementedError

def get_root(path):
        """ Returns the 'root' of the given path.  
        This should include any and all components of a path up to the first
        non-platform-specific component.  For example, on Windows,
        it should include the drive letter prefix.

        This is intended to be used when constructing or deconstructing
        paths, where the root of the filesystem is significant (and
        often leads to ambiguity in cross-platform code)."""
        raise NotImplementedError

# File type constants
# -------------------
ELF, EXEC, UNFOUND = range(0, 3)


import platform
import util as os_util

osname = os_util.get_canonical_os_name()
ostype = os_util.get_canonical_os_type()
distro = platform.dist()[0].lower()

fragments = [distro, osname, ostype]
for fragment in fragments:
        modname = 'os_' + fragment

        # try the most-specific module name first (e.g. os_suse),
        # then try the more generic OS Name module (e.g. os_linux),
        # then the OS type module (e.g. os_unix)        
        try:
                exec('from %s import *' % modname)
                break
        except ImportError:
                pass
else:
        raise ImportError(
            "cannot find portable implementation class for os " + str(fragments))
