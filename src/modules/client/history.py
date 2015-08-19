#!/usr/bin/python
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
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

import copy
import errno
import os
import shutil
import six
import sys
import traceback
import xml.dom.minidom as xmini

import pkg
import pkg.client.api_errors as apx
import pkg.client.bootenv as bootenv
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.portable as portable

# Constants for the (outcome, reason) combination for operation result
# and reason.  The first field, 'outcome' should be a single word to allow easy
# extraction from 'pkg history' but 'reason' may be a phrase.
# Indicates that the user canceled the operation.
RESULT_CANCELED = ["Canceled", "None"]
# Indicates that the operation had no work to perform or didn't need to make
# any changes to the image.
RESULT_NOTHING_TO_DO = ["Ignored", "Nothing to do"]
# Indicates that the operation succeeded.
RESULT_SUCCEEDED = ["Succeeded", "None"]
# Indicates that the user or client provided bad information which resulted in
# operation failure.
RESULT_FAILED_BAD_REQUEST = ["Failed", "Bad Request"]
# Indicates that the operation failed due to a configuration error (such as an
# invalid SSL Certificate, etc.).
RESULT_FAILED_CONFIGURATION = ["Failed", "Configuration"]
# Indicates that the operation failed due to package constraints or because of
# a restriction enforced by the client (e.g. pkg(5) out of date).
RESULT_FAILED_CONSTRAINED = ["Failed", "Constrained"]
# Indicates an operation failed because the image was already in use.
RESULT_FAILED_LOCKED = ["Failed", "Locked"]
# Indicates that a search operation failed.
RESULT_FAILED_SEARCH = ["Failed", "Search"]
# Indicates that there was a problem reading, writing, or accessing a file.
RESULT_FAILED_STORAGE = ["Failed", "Storage"]
# Indicates that a transport error caused the operation to fail.
RESULT_FAILED_TRANSPORT = ["Failed", "Transport"]
# Indicates that the operation failed due to an actuator problem
RESULT_FAILED_ACTUATOR = ["Failed", "Actuator"]
# Indicates that the operation failed due to not enough memory
RESULT_FAILED_OUTOFMEMORY = ["Failed", "Out of Memory"]
# Indicates that the operation failed because of conflicting actions
RESULT_CONFLICTING_ACTIONS = ["Failed", "Conflicting Actions"]
# Indicates that the operation failed for an unknown reason.
RESULT_FAILED_UNKNOWN = ["Failed", "Unknown"]

# Operations that are discarded, not saved, when recorded by history.
DISCARDED_OPERATIONS = ["contents", "info", "list"]

# Cross-reference table for errors and results.  Entries should be ordered
# most-specific to least-specific.
error_results = {
    apx.ImageLockedError: RESULT_FAILED_LOCKED,
    apx.InvalidCatalogFile: RESULT_FAILED_STORAGE,
    apx.BENamingNotSupported: RESULT_FAILED_BAD_REQUEST,
    apx.InvalidBENameException: RESULT_FAILED_BAD_REQUEST,
    apx.CertificateError: RESULT_FAILED_CONFIGURATION,
    apx.PublisherError: RESULT_FAILED_BAD_REQUEST,
    apx.CanceledException: RESULT_CANCELED,
    apx.ImageUpdateOnLiveImageException: RESULT_FAILED_BAD_REQUEST,
    apx.ProblematicPermissionsIndexException: RESULT_FAILED_STORAGE,
    apx.PermissionsException: RESULT_FAILED_STORAGE,
    apx.SearchException: RESULT_FAILED_SEARCH,
    apx.PlanCreationException: RESULT_FAILED_CONSTRAINED,
    apx.NonLeafPackageException: RESULT_FAILED_CONSTRAINED,
    apx.IpkgOutOfDateException: RESULT_FAILED_CONSTRAINED,
    apx.InvalidDepotResponseException: RESULT_FAILED_TRANSPORT,
    apx.ConflictingActionErrors: RESULT_CONFLICTING_ACTIONS,
    fmri.IllegalFmri: RESULT_FAILED_BAD_REQUEST,
    KeyboardInterrupt: RESULT_CANCELED,
    MemoryError: RESULT_FAILED_OUTOFMEMORY,
}

class _HistoryOperation(object):
        """A _HistoryOperation object is a representation of data about an
        operation that a pkg(5) client has performed.  This class is private
        and not intended for use by classes other than History.

        This class provides an abstraction layer between the stack of
        operations that History manages should these values need to be
        manipulated as they are set or retrieved.
        """

        result_l10n = {}    # Static variable for dictionary

        def __copy__(self):
                h = _HistoryOperation()
                for attr in ("name", "start_time", "end_time", "start_state",
                    "end_state", "username", "userid", "be", "be_exists",
                    "be_uuid", "current_be", "current_new_be", "new_be",
                    "new_be_exists", "new_be_uuid", "result", "release_notes",
                    "snapshot"):
                        setattr(h, attr, getattr(self, attr))
                h.errors = [copy.copy(e) for e in self.errors]
                return h

        def __setattr__(self, name, value):
                if name not in ("result", "errors", "be", "be_uuid",
                    "current_be", "current_new_be", "new_be", "new_be_exists",
                    "new_be_uuid", "snapshot"):
                        # Force all other attribute values to be a string
                        # to avoid issues with minidom.
                        value = str(value)

                return object.__setattr__(self, name, value)

        def __str__(self):
                return """\
Operation Name: {0}
Operation Result: {1}
Operation Start Time: {2}
Operation End Time: {3}
Operation Start State:
{4}
Operation End State:
{5}
Operation User: {6} ({7})
Operation Boot Env.: {8}
Operation Boot Env. Currrent: {9}
Operation Boot Env. UUID: {10}
Operation New Boot Env.: {11}
Operation New Boot Env. Current: {12}
Operation New Boot Env. UUID: {13}
Operation Snapshot: {14}
Operation Release Notes: {15}
Operation Errors:
{16}
""".format(self.name, self.result, self.start_time, self.end_time,
    self.start_state, self.end_state, self.username, self.userid,
    self.be, self.current_be, self.be_uuid, self.new_be, self.current_new_be,
    self.new_be_uuid, self.snapshot, self.release_notes, self.errors)

        # All "time" values should be in UTC, using ISO 8601 as the format.
        # Name of the operation performed (e.g. install, update, etc.).
        name = None
        # When the operation started.
        start_time = None
        # When the operation ended.
        end_time = None
        # The starting state of the operation (e.g. image plan pre-evaluation).
        start_state = None
        # The ending state of the operation (e.g. image plan post-evaluation).
        end_state = None
        # Errors encountered during an operation.
        errors = None
        # username of the user that performed the operation.
        username = None
        # id of the user that performed the operation.
        userid = None
        # The boot environment on which the user performed the operation
        be = None
        # The current name of the boot environment.
        current_be = None
        # The uuid of the BE on which the user performed the operation
        be_uuid = None
        # The new boot environment that was created as a result of the operation
        new_be = None
        # The current name of the new boot environment.
        current_new_be = None
        # The uuid of the boot environment that was created as a result of the
        # operation
        new_be_uuid = None
        # The name of the file containing the release notes, or None.
        release_notes = None

        # The snapshot that was created while running this operation
        # set to None if no snapshot was taken, or destroyed after successful
        # completion
        snapshot = None

        # The result of the operation (must be a list indicating (outcome,
        # reason)).
        result = None

        def __init__(self):
                self.errors = []

        @property
        def result_text(self):
                """Returns a tuple containing the translated text for the
                operation result of the form (outcome, reason)."""

                if not _HistoryOperation.result_l10n:
                        # since we store english text in our XML files, we
                        # need a way for clients obtain a translated version
                        # of these messages.
                        _HistoryOperation.result_l10n = {
                            "Canceled": _("Canceled"),
                            "Failed": _("Failed"),
                            "Ignored": _("Ignored"),
                            "Nothing to do": _("Nothing to do"),
                            "Succeeded": _("Succeeded"),
                            "Bad Request": _("Bad Request"),
                            "Configuration": _("Configuration"),
                            "Constrained": _("Constrained"),
                            "Locked": _("Locked"),
                            "Search": _("Search"),
                            "Storage": _("Storage"),
                            "Transport": _("Transport"),
                            "Actuator": _("Actuator"),
                            "Out of Memory": _("Out of Memory"),
                            "Conflicting Actions": _("Conflicting Actions"),
                            "Unknown": _("Unknown"),
                            "None": _("None")
                        }

                if not self.start_time or not self.result:
                        return ("", "")
                return (_HistoryOperation.result_l10n[self.result[0]],
                    _HistoryOperation.result_l10n[self.result[1]])


class History(object):
        """A History object is a representation of data about a pkg(5) client
        and about operations that the client is executing or has executed.  It
        uses the _HistoryOperation class to represent the data about an
        operation.
        """

        # The directory where the history directory can be found (or
        # created if it doesn't exist).
        root_dir = None
        # The name of the client (e.g. pkg, etc.)
        client_name = None
        # The version of the client (e.g. 093ca22da67c).
        client_version = None
        # How the client was invoked (e.g. 'pkg install -n foo').
        client_args = None

        # A stack where operation data will actually be stored.
        __operations = []

        # A private property used by preserve() and restore() to store snapshots
        # of history and operation state information.
        __snapshot = None

        # These attributes exist to fake access to the operations stack.
        operation_name = None
        operation_username = None
        operation_userid = None
        operation_current_be = None
        operation_be = None
        operation_be_uuid = None
        operation_current_new_be = None
        operation_new_be = None
        operation_new_be_uuid = None
        operation_start_time = None
        operation_end_time = None
        operation_start_state = None
        operation_end_state = None
        operation_snapshot = None
        operation_errors = None
        operation_result = None
        operation_release_notes = None

        def __copy__(self):
                h = History()
                for attr in ("root_dir", "client_name", "client_version"):
                        setattr(h, attr, getattr(self, attr))
                object.__setattr__(self, "client_args",
                    [copy.copy(a) for a in self.client_args])
                # A deepcopy has to be performed here since this a list of dicts
                # and not just History operation objects.
                h.__operations = [copy.deepcopy(o) for o in self.__operations]
                return h

        def __getattribute__(self, name):
                if name == "client_args":
                        return object.__getattribute__(self, name)[:]

                if not name.startswith("operation_"):
                        return object.__getattribute__(self, name)

                ops = object.__getattribute__(self, "_History__operations")
                if not ops:
                        return None

                return getattr(ops[-1]["operation"], name[len("operation_"):])

        def __setattr__(self, name, value):
                if name == "client_args":
                        raise AttributeError("'history' object attribute '{0}' "
                            "is read-only.".format(name))

                if not name.startswith("operation_"):
                        return object.__setattr__(self, name, value)

                ops = object.__getattribute__(self, "_History__operations")
                if name == "operation_name":
                        if not ops:
                                ops = []
                                object.__setattr__(self,
                                    "_History__operations", ops)

                        ops.append({
                            "pathname": None,
                            "operation": _HistoryOperation()
                        })
                elif not ops:
                        raise AttributeError("'history' object attribute '{0}' "
                            "cannot be set before 'operation_name'.".format(
                            name))

                op = ops[-1]["operation"]
                setattr(op, name[len("operation_"):], value)

                # Access to the class attributes is done through object instead
                # of just referencing self to avoid any of the special logic in
                # place interfering with logic here.
                if name == "operation_name":
                        # Before a new operation starts, clear exception state
                        # for the current one so that when this one ends, the
                        # last operation's exception won't be recorded to this
                        # one.  If the error hasn't been recorded by now, it
                        # doesn't matter anyway, so should be safe to clear.
                        # sys.exc_clear() isn't supported in Python 3, and
                        # couldn't find a replacement.
                        try:
                                sys.exc_clear()
                        except:
                                pass

                        # Mark the operation as having started and record
                        # other, relevant information.
                        op.start_time = misc.time_to_timestamp(None)
                        try:
                                op.username = portable.get_username()
                        except KeyError:
                                op.username = "unknown"
                        op.userid = portable.get_userid()

                        ca = None
                        if sys.argv[0]:
                                ca = [sys.argv[0]]
                        else:
                                # Fallback for clients that provide no value.
                                ca = [self.client_name]

                        ca.extend(sys.argv[1:])
                        object.__setattr__(self, "client_args", ca)
                        object.__setattr__(self, "client_version", pkg.VERSION)

                elif name == "operation_result":
                        # Record when the operation ended.
                        op.end_time = misc.time_to_timestamp(None)

                        # Some operations shouldn't be saved -- they're merely
                        # included in the stack for completeness or to support
                        # client functionality.
                        if op.name not in DISCARDED_OPERATIONS and \
                            value != RESULT_NOTHING_TO_DO:
                                # Write current history and last operation to a
                                # file.
                                self.__save()

                        # Discard it now that it is no longer needed.
                        del ops[-1]

        def __init__(self, root_dir=".", filename=None, uuid_be_dic=None):
                """'root_dir' should be the path of the directory where the
                history directory can be found (or created if it doesn't
                exist).  'filename' should be the name of an XML file
                containing serialized history information to load.
                'uuid_be_dic', if supplied, should be a dictionary of BE uuid
                information, as produced by
                pkg.client.bootenv.BootEnv.get_uuid_be_dic(), otherwise that
                method is called each time a History object is created.
                """
                # Since this is a read-only attribute normally, we have to
                # bypass our setattr override by calling object.
                object.__setattr__(self, "client_args", [])

                # Initialize client_name to what the client thinks it is.  This
                # will be overridden if we load history entries off disk.
                self.client_name = pkg.client.global_settings.client_name

                self.root_dir = root_dir
                if filename:
                        self.__load(filename, uuid_be_dic=uuid_be_dic)

        def __str__(self):
                ops = self.__operations
                return "\n".join([str(op["operation"]) for op in ops])

        @property
        def path(self):
                """The directory where history files will be written to or
                read from.
                """
                return os.path.join(self.root_dir, "history")

        @property
        def pathname(self):
                """Returns the pathname that the history information was read
                from or will attempted to be written to.  Returns None if no
                operation has started yet or if no operation has been loaded.
                """
                if not self.operation_start_time:
                        return None

                ops = self.__operations
                pathname = ops[-1]["pathname"]
                if not pathname:
                        return os.path.join(self.path,
                            "{0}-01.xml".format(ops[-1]["operation"].start_time))
                return pathname

        @property
        def notes(self):
                """Generates the lines of release notes for this operation.
                If no release notes are present, no output occurs."""

                if not self.operation_release_notes:
                        return
                try:
                        rpath = os.path.join(self.root_dir,
                            "notes", 
                            self.operation_release_notes)
                        for a in open(rpath, "r"):
                                yield a.rstrip()

                except Exception as e:
                        raise apx.HistoryLoadException(e)

        def clear(self):
                """Discards all information related to the current history
                object.
                """
                self.client_name = None
                self.client_version = None
                object.__setattr__(self, "client_args", [])
                self.__operations = []

        def __load_client_data(self, node):
                """Internal function to load the client data from the given XML
                'node' object.
                """
                self.client_name = node.getAttribute("name")
                self.client_version = node.getAttribute("version")
                try:
                        args = node.getElementsByTagName("args")[0]
                except IndexError:
                        # There might not be any.
                        pass
                else:
                        ca = object.__getattribute__(self, "client_args")
                        for cnode in args.getElementsByTagName("arg"):
                                try:
                                        ca.append(cnode.childNodes[0].wholeText)
                                except (AttributeError, IndexError):
                                        # There may be no childNodes, or
                                        # wholeText may not be defined.
                                        pass

        @staticmethod
        def __load_operation_data(node, uuid_be_dic):
                """Internal function to load the operation data from the given
                XML 'node' object and return a _HistoryOperation object.
                """
                op = _HistoryOperation()
                op.name = node.getAttribute("name")
                op.start_time = node.getAttribute("start_time")
                op.end_time = node.getAttribute("end_time")
                op.username = node.getAttribute("username")
                op.userid = node.getAttribute("userid")
                op.result = node.getAttribute("result").split(", ")

                if len(op.result) == 1:
                        op.result.append("None")

                # older clients simply wrote "Nothing to do" instead of
                # "Ignored, Nothing to do", so work around that
                if op.result[0] == "Nothing to do":
                        op.result = RESULT_NOTHING_TO_DO

                if node.hasAttribute("be_uuid"):
                        op.be_uuid = node.getAttribute("be_uuid")
                if node.hasAttribute("new_be_uuid"):
                        op.new_be_uuid = node.getAttribute("new_be_uuid")
                if node.hasAttribute("be"):
                        op.be = node.getAttribute("be")
                        if op.be_uuid:
                                op.current_be = uuid_be_dic.get(op.be_uuid,
                                    op.be)
                if node.hasAttribute("new_be"):
                        op.new_be = node.getAttribute("new_be")
                        if op.new_be_uuid:
                                op.current_new_be = uuid_be_dic.get(
                                    op.new_be_uuid, op.new_be)
                if node.hasAttribute("release-notes"):
                        op.release_notes = node.getAttribute("release-notes")

                def get_node_values(parent_name, child_name=None):
                        try:
                                parent = node.getElementsByTagName(parent_name)[0]
                                if child_name:
                                        cnodes = parent.getElementsByTagName(
                                            child_name)
                                        return [
                                            cnode.childNodes[0].wholeText
                                            for cnode in cnodes
                                        ]
                                return parent.childNodes[0].wholeText
                        except (AttributeError, IndexError):
                                # Assume no values are present for the node.
                                pass
                        if child_name:
                                return []
                        return

                op.start_state = get_node_values("start_state")
                op.end_state = get_node_values("end_state")
                op.errors.extend(get_node_values("errors", child_name="error"))

                return op

        def __load(self, filename, uuid_be_dic=None):
                """Loads the history from a file located in self.path/history/
                {filename}.  The file should contain a serialized history
                object in XML format.
                """

                # Ensure all previous information is discarded.
                self.clear()

                try:
                        if not uuid_be_dic:
                                uuid_be_dic = bootenv.BootEnv.get_uuid_be_dic()
                except apx.ApiException as e:
                        uuid_be_dic = {}

                try:
                        pathname = os.path.join(self.path, filename)
                        d = xmini.parse(pathname)
                        root = d.documentElement
                        for cnode in root.childNodes:
                                if cnode.nodeName == "client":
                                        self.__load_client_data(cnode)
                                elif cnode.nodeName == "operation":
                                        # Operations load differently due to
                                        # the stack.
                                        self.__operations.append({
                                            "pathname": pathname,
                                            "operation":
                                                self.__load_operation_data(
                                                cnode, uuid_be_dic)
                                            })
                except KeyboardInterrupt:
                        raise
                except Exception as e:
                        raise apx.HistoryLoadException(e)

        def __serialize_client_data(self, d):
                """Internal function used to serialize current client data
                using the supplied 'd' (xml.dom.minidom) object.
                """

                assert self.client_name is not None
                assert self.client_version is not None

                root = d.documentElement
                client = d.createElement("client")
                client.setAttribute("name", self.client_name)
                client.setAttribute("version", self.client_version)
                root.appendChild(client)

                if self.client_args:
                        args = d.createElement("args")
                        client.appendChild(args)
                        for entry in self.client_args:
                                arg = d.createElement("arg")
                                args.appendChild(arg)
                                arg.appendChild(
                                    d.createCDATASection(str(entry)))

        def __serialize_operation_data(self, d):
                """Internal function used to serialize current operation data
                using the supplied 'd' (xml.dom.minidom) object.
                """

                if self.operation_userid is None:
                        raise apx.HistoryStoreException("Unable to determine "
                            "the id of the user that performed the current "
                            "operation; unable to store history information.")
                elif self.operation_username is None:
                        raise apx.HistoryStoreException("Unable to determine "
                            "the username of the user that performed the "
                            "current operation; unable to store history "
                            "information.")

                root = d.documentElement
                op = d.createElement("operation")
                op.setAttribute("name", self.operation_name)
                # Must explictly convert values to a string due to minidom bug
                # that causes a fatal whenever using types other than str.
                op.setAttribute("username", str(self.operation_username))
                op.setAttribute("userid", str(self.operation_userid))
                op.setAttribute("result", ", ".join(self.operation_result))
                op.setAttribute("start_time", self.operation_start_time)
                op.setAttribute("end_time", self.operation_end_time)

                if self.operation_be:
                        op.setAttribute("be", self.operation_be)
                if self.operation_be_uuid:
                        op.setAttribute("be_uuid", self.operation_be_uuid)
                if self.operation_new_be:
                        op.setAttribute("new_be", self.operation_new_be)
                if self.operation_new_be_uuid:
                        op.setAttribute("new_be_uuid",
                            self.operation_new_be_uuid)
                if self.operation_snapshot:
                        op.setAttribute("snapshot", self.operation_snapshot)
                if self.operation_release_notes:
                        op.setAttribute("release-notes", self.operation_release_notes)

                root.appendChild(op)

                if self.operation_start_state:
                        state = d.createElement("start_state")
                        op.appendChild(state)
                        state.appendChild(d.createCDATASection(
                            str(self.operation_start_state)))

                if self.operation_end_state:
                        state = d.createElement("end_state")
                        op.appendChild(state)
                        state.appendChild(d.createCDATASection(
                            str(self.operation_end_state)))

                if self.operation_errors:
                        errors = d.createElement("errors")
                        op.appendChild(errors)

                        for entry in self.operation_errors:
                                error = d.createElement("error")
                                errors.appendChild(error)
                                error.appendChild(
                                    d.createCDATASection(str(entry)))

        def __save(self):
                """Serializes the current history information and writes it to
                a file in self.path/{operation_start_time}-{sequence}.xml.
                """
                d = xmini.Document()
                d.appendChild(d.createElement("history"))
                self.__serialize_client_data(d)
                self.__serialize_operation_data(d)

                if not os.path.exists(self.path):
                        try:
                                # Only the right-most directory should be
                                # created.  Assume that if the parent structure
                                # does not exist, it shouldn't be created.
                                os.mkdir(self.path, misc.PKG_DIR_MODE)
                        except EnvironmentError as e:
                                if e.errno not in (errno.EROFS, errno.EACCES,
                                    errno.ENOENT):
                                        # Ignore read-only file system and
                                        # access errors as it isn't critical
                                        # to the image that this data is
                                        # written.
                                        raise apx.HistoryStoreException(e)
                                # Return, since without the directory, the rest
                                # of this will fail.
                                return
                        except KeyboardInterrupt:
                                raise
                        except Exception as e:
                                raise apx.HistoryStoreException(e)

                # Repeatedly attempt to write the history (only if it's because
                # the file already exists).  This is necessary due to multiple
                # operations possibly occuring within the same second (but not
                # microsecond).
                pathname = self.pathname
                for i in range(1, 100):
                        try:
                                f = os.fdopen(os.open(pathname,
                                    os.O_CREAT|os.O_EXCL|os.O_WRONLY,
                                    misc.PKG_FILE_MODE), "w")
                                d.writexml(f,
                                    encoding=sys.getdefaultencoding())
                                f.close()
                                return
                        except EnvironmentError as e:
                                if e.errno == errno.EEXIST:
                                        name, ext = os.path.splitext(
                                            os.path.basename(pathname))
                                        name = name.split("-", 1)[0]
                                        # Pick the next name in our sequence
                                        # and try again.
                                        pathname = os.path.join(self.path,
                                            "{0}-{1:>02d}{2}".format(name,
                                            i + 1, ext))
                                        continue
                                elif e.errno not in (errno.EROFS,
                                    errno.EACCES):
                                        # Ignore read-only file system and
                                        # access errors as it isn't critical
                                        # to the image that this data is
                                        # written.
                                        raise apx.HistoryStoreException(e)
                                # For all other failures, return, and avoid any
                                # further attempts.
                                return
                        except KeyboardInterrupt:
                                raise
                        except Exception as e:
                                raise apx.HistoryStoreException(e)

        def purge(self, be_name=None, be_uuid=None):
                """Removes all history information by deleting the directory
                indicated by the value self.path and then creates a new history
                entry to record that this purge occurred.
                """
                self.operation_name = "purge-history"
                self.operation_be = be_name
                self.operation_be_uuid = be_uuid

                try:
                        shutil.rmtree(self.path)
                except KeyboardInterrupt:
                        raise
                except EnvironmentError as e:
                        if e.errno in (errno.ENOENT, errno.ESRCH):
                                # History already purged; record as successful.
                                self.operation_result = RESULT_SUCCEEDED
                                return
                        raise apx.HistoryPurgeException(e)
                except Exception as e:
                        raise apx.HistoryPurgeException(e)
                else:
                        self.operation_result = RESULT_SUCCEEDED

        def abort(self, result):
                """Intended to be used by the client during top-level error
                handling to indicate that an unrecoverable error occurred
                during the current operation(s).  This allows History to end
                all of the current operations properly and handle any possible
                errors that might be encountered in History itself.
                """
                try:
                        # Ensure that all operations in the current stack are
                        # ended properly.
                        while self.operation_name:
                                self.operation_result = result
                except apx.HistoryStoreException:
                        # Ignore storage errors as it's likely that whatever
                        # caused the client to abort() also caused the storage
                        # of the history information to fail.
                        return

        def log_operation_start(self, name, be_name=None, be_uuid=None):
                """Marks the start of an operation to be recorded in image
                history."""
                self.operation_name = name
                self.operation_be = be_name
                self.operation_be_uuid = be_uuid

        def log_operation_end(self, error=None, result=None, release_notes=None):
                """Marks the end of an operation to be recorded in image
                history.

                'result' should be a pkg.client.history constant value
                representing the outcome of an operation.  If not provided,
                and 'error' is provided, the final result of the operation will
                be based on the class of 'error' and 'error' will be recorded
                for the current operation.  If 'result' and 'error' is not
                provided, success is assumed."""

                if error:
                        self.log_operation_error(error)
                        self.operation_new_be = None
                        self.operation_new_be_uuid = None

                if error and not result:
                        try:
                                # Attempt get an exact error match first.
                                result = error_results[error.__class__]
                        except (AttributeError, KeyError):
                                # Failing an exact match, determine if this
                                # error is a subclass of an existing one.
                                for entry, val in six.iteritems(error_results):
                                        if isinstance(error, entry):
                                                result = val
                                                break
                        if not result:
                                # If a result could still not be determined,
                                # assume unknown failure case.
                                result = RESULT_FAILED_UNKNOWN
                elif not result:
                        # Assume success if no error and no result.
                        result = RESULT_SUCCEEDED
                if release_notes:
                        self.operation_release_notes = release_notes
                self.operation_result = result

        def log_operation_error(self, error):
                """Adds an error to the list of errors to be recorded in image
                history for the current operation."""

                if self.operation_name:
                        out_stack = None
                        out_err = None
                        use_current_stack = True
                        if isinstance(error, Exception):
                                # Attempt to get the exception's stack trace
                                # from the stack.  If the exception on the stack
                                # isn't the same object as the one being logged,
                                # then we have to use the current stack (which
                                # is somewhat less useful) instead of being able
                                # to find the code location of the original
                                # error.
                                type, val, tb = sys.exc_info()
                                if error == val:
                                        output = traceback.format_exc()
                                        use_current_stack = False

                        if isinstance(error, six.string_types):
                                output = error
                        elif use_current_stack:
                                # Assume the current stack is more useful if
                                # the error doesn't inherit from Exception or
                                # we can't use the last exception's stack.
                                out_stack = "".join(traceback.format_stack())

                                if error:
                                        # This may result in the text
                                        # of the error itself being written
                                        # twice, but that is necessary in case
                                        # it is not contained within the
                                        # output of format_exc().
                                        out_err = str(error)
                                        if not out_err or out_err == "None":
                                                out_err = \
                                                    error.__class__.__name__

                                output = "".join([
                                    item for item in [out_stack, out_err]
                                    if item
                                ])

                        self.operation_errors.append(output.strip())

        def create_snapshot(self):
                """Stores a snapshot of the current history and operation state
                information in memory so that it can be restored in the event of
                client failure (such as inability to store history information
                or the failure of a boot environment operation).  Each call to
                this function will overwrite the previous snapshot."""

                attrs = self.__snapshot = {}
                for attr in ("root_dir", "client_name", "client_version"):
                        attrs[attr] = getattr(self, attr)
                attrs["client_args"] = [copy.copy(a) for a in self.client_args]
                # A deepcopy has to be performed here since this a list of dicts
                # and not just History operation objects.
                attrs["__operations"] = \
                    [copy.deepcopy(o) for o in self.__operations]

        def discard_snapshot(self):
                """Discards the current history and operation state information
                snapshot."""
                self.__snapshot = None

        def restore_snapshot(self):
                """Restores the last snapshot taken of history and operation
                state information completely discarding the existing history and
                operation state information.  If nothing exists to restore, this
                this function will silently return."""

                if not self.__snapshot:
                        return

                for name, val in six.iteritems(self.__snapshot):
                        if not name.startswith("__"):
                                object.__setattr__(self, name, val)
                self.__operations = self.__snapshot["__operations"]
