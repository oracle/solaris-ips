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
# Copyright (c) 2012, Oracle and/or its affiliates. All rights reserved.
#

"""This module implements PrintEngine (abstract), POSIXPrintEngine and
LoggingPrintEngine, which take output messages from e.g. a progress tracker and
render them to a file, a terminal, or a logger."""

import errno
import logging
import os
import time
from abc import ABCMeta, abstractmethod
import StringIO

import pkg.client.api_errors as api_errors
from pkg.misc import PipeError


class PrintEngineException(api_errors.ApiException):
        """Exception indicating the failure to create PrintEngine."""
        pass


class PrintEngine(object):
        """Abstract class defining what a PrintEngine must know how to do."""
        __metaclass__ = ABCMeta

        def __init__(self):
                pass

        @abstractmethod
        def cprint(self, *args, **kwargs):
                """Core print routine.  Must act basically like py3k's print
                routine.  For some printengines, additional behaviors can be
                indicated via keyword args."""
                pass

        @abstractmethod
        def flush(self):
                """Make the terminal or line ready for output by another
                subsystem.  This commonly might entail issuing a newline."""
                pass


class POSIXPrintEngine(PrintEngine):
        """This is an engine for printing output to the end user which has been
        tweaked for IPS's printing needs."""

        def __init__(self, out_file, ttymode):
                """Create a printengine.

                out_file -- the file object to print to
                ttymode  -- Boolean indicating need for tty support.  Throws
                            PrintEngineException if out_file can't support.
                """
                PrintEngine.__init__(self)

                self._out_file = out_file
                self.__nchars_printed = 0
                self.__needs_nl = 0
                self.__cr = None
                self.__clear_eol = None
                self.__ttymode = ttymode

                if not self.__ttymode:
                        return

                try:
                        import curses
                        # Non-portable API; pylint: disable-msg=E0901
                        if not os.isatty(self._out_file.fileno()):
                                raise PrintEngineException(
                                    "out_file is not a TTY")

                        curses.setupterm()
                        self.__cr = curses.tigetstr("cr")
                        #
                        # Note: in the future, might want to handle
                        # clear_eol being unavailable.
                        #
                        self.__clear_eol = curses.tigetstr("el") or ""
                except KeyboardInterrupt:
                        raise
                except PrintEngineException:
                        raise
                except Exception, e:
                        raise PrintEngineException(
                            "Could not setup printengine: %s" % str(e))

        def cprint(self, *args, **kwargs):
                """Core print routine.  Acts largely like py3k's print command,
                (supports 'sep' and 'end' kwargs) with an extension:

                erase=true: Erase any content on the present line, intended for
                use in overwriting."""

                sep = kwargs.get("sep", ' ')
                outmsg = sep.join(args) + kwargs.get("end", '\n')

                clearstring = ""
                if kwargs.get("erase"):
                        assert self.__ttymode

                        clearstring = self.__cr + self.__clear_eol
                        # account for the erase setting the number of chars
                        # printed back to 0.
                        self.__nchars_printed = 0

                #
                # Setting __needs_nl is how _cprint works together with
                # the flush entrypoint.  If we're partially through
                # writing a line (which we know by inspecting the
                # line and the "end" value), then we know that if we
                # get flush()'d by a consumer, we need to issue an
                # additional newline.
                #
                if outmsg != "" and not outmsg.endswith("\n"):
                        self.__needs_nl = True

                # find the rightmost newline in the msg
                npos = outmsg.rfind("\n")
                if (npos == -1):
                        self.__nchars_printed += len(outmsg)
                else:
                        # there was an nl or cr, so only the portion
                        # after that counts.
                        self.__nchars_printed = len(outmsg) - (npos + 1)

                try:
                        self._out_file.write(clearstring + outmsg)
                        self._out_file.flush()
                        #
                        # if indeed we printed a newline at the end, we know
                        # that an additional newline is definitely not needed on
                        # flush.
                        #
                        if outmsg.endswith("\n"):
                                self.__needs_nl = False
                except IOError, e:
                        if e.errno == errno.EPIPE:
                                raise PipeError, e
                        raise

        def flush(self):
                """If we're in the middle of writing a line, this tries to
                write a newline in order to allow clean output after flush()."""
                try:
                        if self.__needs_nl:
                                self._out_file.write("\n")
                                self.__needs_nl = False
                        self._out_file.flush()
                except IOError:
                        # we consider this to be harmless.
                        pass


class LoggingPrintEngine(PrintEngine):
        """This class adapts a printengine such that it issues its output to a
        python logger from the logging module.  Note that This class is used by
        the AI (install) engine.

        The basic trick here is to use a StringIO in place of an actual file.
        We then have the POSIX print engine issue its I/O to the StringIO, then
        splitlines() the buffer and see if there are any complete lines that we
        can output.  If so, each complete line is issued to the logger, and any
        remainder is put back into the StringIO for subsequent display."""

        def __init__(self, logger, loglevel):
                PrintEngine.__init__(self)
                self._logger = logger
                self._loglevel = loglevel
                self._stringio = StringIO.StringIO()
                self._pxpe = POSIXPrintEngine(self._stringio, False)

        def cprint(self, *args, **kwargs):
                """Accumulates output into a buffer, emitting messages to
                the _logger when full lines are available."""
                self._pxpe.cprint(*args, **kwargs)

                lines = self._stringio.getvalue().splitlines(True)
                line = ""
                for line in lines:
                        if line.endswith("\n"):
                                # write out, stripping the newline
                                self._logger.log(self._loglevel, line[:-1])
                self._stringio.seek(0)
                self._stringio.truncate(0)
                # anything left without a newline?   Put it back.
                if not line.endswith("\n"):
                        self._stringio.write(line)

        def flush(self):
                """Log any partial line we've got left."""
                val = self._stringio.getvalue()
                if val:
                        # should only ever have a partial line
                        assert not "\n" in val
                        self._logger.log(self._loglevel, val)
                self._stringio.seek(0)
                self._stringio.truncate(0)


def test_logging_printengine(output_file):
        """Test driver for logging print engine.  This is maintained as a
        standalone function in order to support the 'runprintengine' test
        utility in $SRC/tests/interactive/runprintengine.py. It is also
        called by the test suite."""

        logger = logging.getLogger('test')
        ch = logging.StreamHandler(output_file)
        logger.addHandler(ch)

        pe = LoggingPrintEngine(logger, logging.WARNING)
        pe.cprint("Testing logging print engine. ", end='')
        pe.cprint("Did you see this? ", end='')
        pe.cprint("And this?")
        pe.cprint("If the previous three sentences are on the same line, "
            "it's working.")
        pe.cprint("You need to see one more line after this one.")
        pe.cprint("This should be the last line, printed by flushing", end='')
        pe.flush()


def test_posix_printengine(output_file):
        """Test driver for POSIX print engine.  This is maintained as a
        standalone function in order to support the 'runprintengine' test
        utility in $SRC/tests/interactive/runprintengine.py; it is also
        called by the test suite."""

        standout = ""
        sgr0 = ""
        ttymode = False

        # Non-portable API; pylint: disable-msg=E0901
        if os.isatty(output_file.fileno()):
                try:
                        import curses
                        curses.setupterm()
                        standout = curses.tigetstr("smso") or ""
                        sgr0 = curses.tigetstr("sgr0") or ""
                        ttymode = True
                except KeyboardInterrupt:
                        raise
                except:
                        pass

        pe = POSIXPrintEngine(output_file, ttymode=ttymode)
        pe.cprint("Testing POSIX print engine; ttymode is %s\n" % ttymode)

        # If we're not in ttymode, then the testing is simple.
        if ttymode is False:
                pe.cprint("testing  1  2  3")
                pe.cprint("testing flush (2)")
                pe.flush()
                return

        pe.cprint("You should see an X swishing back and forth; from")
        pe.cprint("left to right it should be inverse.")
        # Unused variable 'y'; pylint: disable-msg=W0612
        for y in range(0, 2):
                for x in xrange(0, 30, 1):
                        pe.cprint(" " * x + standout + "X" + sgr0,
                            erase=True, end='')
                        time.sleep(0.050)
                for x in xrange(30, -1, -1):
                        pe.cprint(" " * x + "X", erase=True, end='')
                        time.sleep(0.050)
        pe.cprint("", erase=True)
        pe.cprint("testing  1  2  3")
        pe.cprint("testing XX XX XX", end="")
        time.sleep(0.500)
        pe.cprint("testing  4  5  6\ntesting XX XX XX", erase=True, end="")
        time.sleep(0.500)
        pe.cprint("testing YY YY", end="", erase=True)
        time.sleep(0.500)
        pe.cprint("testing  7  8  9\ntesting 10 11 12", erase=True)
        time.sleep(0.500)
        pe.cprint("testing ZZ ZZ ZZ ZZ ZZ", end="")
        time.sleep(0.500)
        pe.cprint("testing 13 14 15", erase=True)

        pe.cprint("testing flush...", end='')
        pe.flush()
        pe.cprint("This should be on the next line.")
        pe.cprint("testing flush (2)")
        pe.flush()
        pe.cprint("This should be on the next line (with no nl's intervening).")
