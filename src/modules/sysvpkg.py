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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import string, sys, errno
from pkg.package import Package
from pkg.dependency import Dependency

class PkgMapLine(object):
	"""A class that represents a single line of a SysV package's pkgmap.
	This class should probably disappear once pkg.Content is a bit more
	fleshed out.
	"""

	def __init__(self, line):
		array = line.split(' ')
		try:
			self.part = int(array[0])
		except ValueError:
			self.part = 1
			array[0:0] = "1"
			
		self.type = array[1]

		if self.type == 'i':
			(self.pathname, self.size, self.chksum,
			    self.modtime) = array[2:]
			return

		self.klass = array[2]

		if self.type == 'f' or self.type == 'e' or self.type == 'v':
			(self.pathname, self.mode, self.owner, self.group,
			    self.size, self.chksum, self.modtime) = array[3:]

		elif self.type == 'b' or self.type == 'c':
			(self.pathname, self.major, self.minor, self.mode,
			    self.owner, self.group) = array[3:]

		elif self.type == 'd' or self.type == 'x' or self.type == 'p':
			(self.pathname, self.mode, self.owner, self.group) = \
				array[3:]

		elif self.type == 'l' or self.type == 's':
			(self.pathname, self.target) = array[3].split('=')

		else:
			raise ValueError("Invalid file type: " + self.type)

class SolarisPackage(Package):
	"""A SolarisPackage represents a System V package for Solaris.
	"""

	def __init__(self, path):
		self.pkgpath = path
		# self.pkginfo = PkgInfo(path + "/pkginfo")
		self.pkginfo = self.readPkginfoFile()
		deps = self.readDependFile()

		Package.__init__(self, self.pkginfo['VENDOR'],
			self.pkginfo['PKG'], self.pkginfo['VERSION'], deps, [])

		# XXX Change this to add Contents objects.
		# XXX Are Contents objects by reference, or do they actually
		#     contain the bits in a package?
		self.manifest = self.readPkgmapFile()

	def readDependFile(self):
		try:
			fp = file(self.pkgpath + "/install/depend")
		except IOError, (err, msg):
			# Missing depend file is just fine
			if err == errno.ENOENT:
				return []
			else:
				raise

		deps = []
		for line in fp:
			line = line.rstrip('\n')

			if len(line) == 0 or line[0] == '#':
				continue

			if line[0] == 'P':
				(type, pkg, desc) = line.split(None, 2)
				deps += [ Dependency(self.pkginfo['PKG'], pkg) ]

		return deps

	def readPkginfoFile(self):
		pkginfo = {}

		fp = file(self.pkgpath + "/pkginfo")

		for line in fp:
			line = line.lstrip().rstrip('\n')

			if len(line) == 0 or line[0] == '#':
				continue

			(key, val) = line.split('=', 1)
			pkginfo[key] = val.strip('"')

		return pkginfo

	def readPkgmapFile(self):
		pkgmap = []

		fp = file(self.pkgpath + "/pkgmap")

		for line in fp:
			line = line.rstrip('\n')

			if len(line) == 0 or line[0] == '#':
				continue

			if line[0] == ':':
				continue

			pkgmap += [ PkgMapLine(line) ]

		return pkgmap

if __name__ == "__main__":
	pkg = SolarisPackage(sys.argv[1])

	for key in sorted(pkg.pkginfo):
		print key + '=' + pkg.pkginfo[key]

	print

	for obj in pkg.manifest:
		print obj.type + ' ' + obj.pathname

	print

	for d in pkg.dependencies:
		print d
