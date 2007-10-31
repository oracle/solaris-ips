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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest
import tempfile
import os
import pkg.smf as smf

class TestSMF(unittest.TestCase):

	def setUp(self):
		self.passwd_tmp = tempfile.mktemp()
		self.xml_tmp = tempfile.mktemp()
		self.smf1_tmp = tempfile.mktemp()
		self.smf2_tmp = tempfile.mktemp()

		f=open(self.passwd_tmp, "w")
		f.write("root:x:0:0:Super-User:/:/bin/bash\n")
		f.write("daemon:x:1:1::/:")
		f.close

		f=open(self.xml_tmp, "w")
		f.write("""<?xml version="1.0" encoding="ISO-8859-1"?>
<?xml-stylesheet type="text/xsl" href="HelloWorld.xsl" ?>
<!-- Hello World in XML -->
<text><string>Hello, World</string></text>""")
		f.close

		#
		# This is a single-instance SMF manifest with pseudo contents;
		# we can process this with get_info and easily test the results
		#
		f=open(self.smf1_tmp, "w")
		f.write("""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM
    "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='test'>
<service name='pkg/test' type='service' version='1'>
<create_default_instance enabled='true' />
<single_instance />
<dependency
	name='usr'
	grouping='require_all'
	restart_on='none'
	type='service'>
	<service_fmri value='svc:/system/filesystem/usr' />
</dependency>
<dependency
	name='devices'
	grouping='require_all'
	restart_on='none'
	type='service'>
	<service_fmri value='svc:/system/device/local' />
</dependency>
<dependent
	name='multi-user'
	grouping='optional_all'
	restart_on='none'>
	<service_fmri value='svc:/milestone/multi-user' />
</dependent>
</service>
</service_bundle>""")
		f.close

		#
		# This is a multi-instance SMF manifest with pseudo contents;
		# we can process this with get_info and easily test the results
		#
		f=open(self.smf2_tmp, "w")
		f.write("""<?xml version="1.0"?>
<!DOCTYPE service_bundle SYSTEM
    "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name='test'>
<service name='pkg/test' type='service' version='1'>
<instance name='i1' enabled='false'>
	<dependency
		name='usr'
		grouping='require_all'
		restart_on='none'
		type='service'>
		<service_fmri value='svc:/system/filesystem/usr' />
	</dependency>
	<dependency
		name='devices'
		grouping='require_all'
		restart_on='none'
		type='service'>
		<service_fmri value='svc:/system/device/local' />
	</dependency>
	<dependent
		name='multi-user'
		grouping='optional_all'
		restart_on='none'>
		<service_fmri value='svc:/milestone/multi-user' />
	</dependent>
</instance>

<instance name='i2' enabled='false'>
	<dependency
		name='foo'
		grouping='require_all'
		restart_on='none'
		type='service'>
		<service_fmri value='svc:/system/filesystem/usr' />
	</dependency>
	<dependency
		name='bar'
		grouping='require_all'
		restart_on='none'
		type='service'>
		<service_fmri value='svc:/system/device/local' />
	</dependency>
	<dependent
		name='baz'
		grouping='optional_all'
		restart_on='none'>
		<service_fmri value='svc:/milestone/multi-user' />
	</dependent>
</instance>
</service>
</service_bundle>""")
		f.close


	def tearDown(self):
		os.remove(self.passwd_tmp)
		os.remove(self.xml_tmp)
		os.remove(self.smf1_tmp)
		os.remove(self.smf2_tmp)



	def test_is_smf_manifest1(self):
		""" ASSERT: a miscellaneous text file is not a manifest """
		self.assertEqual(smf.is_smf_manifest(self.passwd_tmp), False)

	def test_is_smf_manifest2(self):
		""" ASSERT: a miscellaneous xml file is not a manifest """
		self.assertEqual(smf.is_smf_manifest(self.xml_tmp), False)

	def test_is_smf_manifest3(self):
		""" ASSERT: an single-instance manifest is identified """
		self.assertEqual(smf.is_smf_manifest(self.smf1_tmp), True)

	def test_is_smf_manifest3(self):
		""" ASSERT: an multi-instance manifest is identified """
		self.assertEqual(smf.is_smf_manifest(self.smf2_tmp), True)

# XXX not sure what the desired behaviour is.  Currently it throws an
# exception.  Is that ok?
#	def test_is_smf_manifest4(self):
#		""" ASSERT: a non-existant file is not a manifest """
#
#
# 		self.assertEqual(smf.is_smf_manifest("/this/does/not/exist/"),
#		    False)

	def test_get_info_1(self):
		""" ASSERT: get_info returns values corresponding to sample
		    manifest """

		info = smf.get_info(self.smf1_tmp)
		self.assertEqual(info,
		    {'imposes':
		        [('optional_all', ['svc:/milestone/multi-user'])],
                     'requires':
                        [('require_all', ['svc:/system/filesystem/usr']),
                         ('require_all', ['svc:/system/device/local'])],
                     'provides':
                        ['svc:/pkg/test:default']
                    })

	#
	# Even though smf2_tmp provides multiple services, the
	# "info" object should compact the set of things which
	# are imposed and required.

# XXX: This is currently busted, and this case fails.
#	def test_get_info_2(self):
#		""" ASSERT: get_info weeds out duplicated information """
#
#		info = smf.get_info(self.smf2_tmp)
#		self.assertEqual(info,
#		    {'imposes':
#		        [('optional_all', ['svc:/milestone/multi-user'])],
#		     'requires':
#			[('require_all', ['svc:/system/filesystem/usr']),
#			 ('require_all', ['svc:/system/device/local'])],
#		     'provides':
#			 ['svc:/pkg/test:i1', 'svc:/pkg/test:i2']})

# XXX not sure what the desire behavior is here.
#	def test_get_info_3(self):
#		info = smf.get_info("/this/does/not/exist")

if __name__ == "__main__":
        unittest.main()
