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
# Copyright (c) 2012, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""This module implements PrintEngine (abstract), POSIXPrintEngine and
LoggingPrintEngine, which take output messages from e.g. a progress tracker and
render them to a file, a terminal, or a logger."""

import curses
import errno
import logging
import os
import re
import six
import termios
import time
from abc import ABCMeta, abstractmethod

from pkg.misc import PipeError, force_str


class PrintEngineException(Exception):
        """Exception indicating the failure to create PrintEngine."""
        def __str__(self):
                return "PrintEngineException: {0}".format(" ".join(self.args))

class PrintEngine(six.with_metaclass(ABCMeta, object)):
        """Abstract class defining what a PrintEngine must know how to do."""

        def __init__(self):
                pass

        @abstractmethod
        def isslow(self):
                """Returns true if out_file is 'slow' (<=9600 baud)."""
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
                self.__ttymode = ttymode

                if not self.__ttymode:
                        return

                self.__putp_re = re.compile(r"\$<[0-9]+>")
                self.__el = None
                if not self._out_file.isatty():
                        raise PrintEngineException("Not a TTY")

                try:
                        curses.setupterm(None, self._out_file.fileno())
                        self.__cr = curses.tigetstr("cr")
                        self.__el = curses.tigetstr("el")
                except curses.error:
                        raise PrintEngineException("Unknown terminal "
                            "'{0}'".format(os.environ.get("TERM", "")))

        def putp(self, string):
                """This routine loosely emulates python's curses.putp, but
                works on whatever our output file is, instead just stdout"""

                assert self.__ttymode

                # Hardware terminals are pretty much gone now; we choose
                # to drop delays specified in termcap (delays are in the
                # form: $<[0-9]+>).
                self._out_file.write(self.__putp_re.sub("", force_str(string)))

        def isslow(self):
                """Returns true if out_file is 'slow' (<=9600 baud)."""
                b = termios.B38400   # assume it's fast if we can't tell.
                try:
                        b = termios.tcgetattr(self._out_file)[5]
                except termios.error:
                        pass
                return b <= termios.B9600

        def erase(self):
                """Send sequence to erase the current line to _out_file."""
                if self.__el:
                        self.putp(self.__cr)
                        self.putp(self.__el)
                        self.putp(self.__cr)
                else:
                        # fallback mode if we have no el; overwrite with
                        # spaces.
                        self.putp(self.__cr)
                        self._out_file.write(self.__nchars_printed * ' ')
                        self.putp(self.__cr)

        def cprint(self, *args, **kwargs):
                """Core print routine.  Acts largely like py3k's print command,
                (supports 'sep' and 'end' kwargs) with an extension:

                erase=true: Erase any content on the present line, intended for
                use in overwriting."""

                sep = kwargs.get("sep", ' ')
                outmsg = sep.join(args) + kwargs.get("end", '\n')

                if kwargs.get("erase"):
                        assert self.__ttymode
                        self.erase()
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
                if npos == -1:
                        self.__nchars_printed += len(outmsg)
                else:
                        # there was an nl or cr, so only the portion
                        # after that counts.
                        self.__nchars_printed = len(outmsg) - (npos + 1)

                try:
                        self._out_file.write(outmsg)
                        self._out_file.flush()
                        #
                        # if indeed we printed a newline at the end, we know
                        # that an additional newline is definitely not needed on
                        # flush.
                        #
                        if outmsg.endswith("\n"):
                                self.__needs_nl = False
                except IOError as e:
                        if e.errno == errno.EPIPE:
                                raise PipeError(e)
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
                self._stringio = six.StringIO()
                self._pxpe = POSIXPrintEngine(self._stringio, False)

        def isslow(self):
                """Returns true if out_file is 'slow' (<=9600 baud)."""
                return False

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
        # just test that it works
        pe.isslow()
        pe.flush()


def test_posix_printengine(output_file, ttymode):
        """Test driver for POSIX print engine.  This is maintained as a
        standalone function in order to support the 'runprintengine' test
        utility in $SRC/tests/interactive/runprintengine.py; it is also
        called by the test suite."""

        pe = POSIXPrintEngine(output_file, ttymode=ttymode)

        standout = ""
        sgr0 = ""
        if ttymode:
                # We assume that setupterm() has been called already.
                standout = curses.tigetstr("smso") or ""
                sgr0 = curses.tigetstr("sgr0") or ""

        pe.cprint("Testing POSIX print engine; ttymode is {0}\n".format(
            ttymode))

        # If we're not in ttymode, then the testing is simple.
        if not ttymode:
                pe.cprint("testing  1  2  3")
                pe.cprint("testing flush (2)")
                pe.flush()
                return

        # We assume setupterm() has been called.
        standout = curses.tigetstr("smso") or ""
        sgr0 = curses.tigetstr("sgr0") or ""
        pe.cprint("Now we'll print something and then erase it;")
        pe.cprint("you should see a blank line below this line.")
        pe.cprint("IF YOU CAN SEE THIS, THE TEST HAS FAILED", end='')
        pe.cprint("", erase=True)

        pe.cprint("You should see an X swishing back and forth; from")
        pe.cprint("left to right it should be inverse.")
        # Unused variable 'y'; pylint: disable=W0612
        for y in range(0, 2):
                for x in range(0, 30, 1):
                        pe.cprint(" " * x, erase=True, end='')
                        pe.putp(standout)
                        pe.cprint("X", end='')
                        pe.putp(sgr0)
                        time.sleep(0.050)
                for x in range(30, -1, -1):
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
        # just test that it works
        pe.isslow()

