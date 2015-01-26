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

from __future__ import print_function
import config

hostname = config.get("hostname", default="pkg")

header = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
	<head>
	<title>pkg log summary</title>
 
	<!-- Source File -->
	<link rel="stylesheet" type="text/css"
	href="http://yui.yahooapis.com/2.5.1/build/reset-fonts-grids/reset-fonts-grids.css" />
	<link rel="stylesheet" type="text/css"
	href="http://yui.yahooapis.com/2.5.1/build/base/base-min.css" />
	<link rel="stylesheet" type="text/css"
	href="http://yui.yahooapis.com/2.5.1/build/base/fonts-min.css" />

	<!-- Sam Skin CSS for TabView --> 
	<link rel="stylesheet" type="text/css"
	href="http://yui.yahooapis.com/2.5.1/build/tabview/assets/skins/sam/tabview.css" />

	<!-- JavaScript Dependencies for Tabview: --> 
	<script type="text/javascript"
	src="http://yui.yahooapis.com/2.5.1/build/yahoo-dom-event/yahoo-dom-event.js"></script> 
	<script type="text/javascript"
	src="http://yui.yahooapis.com/2.5.1/build/element/element-beta-min.js"></script> 

	<!-- Source file for TabView --> 
	<script type="text/javascript"
	src="http://yui.yahooapis.com/2.5.1/build/tabview/tabview-min.js"></script>

	<!--Dependencies for DataTable -->
	<!--CSS file (default YUI Sam Skin) -->
	<link type="text/css" rel="stylesheet"
	href="http://yui.yahooapis.com/2.5.2/build/datatable/assets/skins/sam/datatable.css">
	<script type="text/javascript"
	src="http://yui.yahooapis.com/2.5.2/build/yahoo-dom-event/yahoo-dom-event.js"></script>
	<script type="text/javascript"
	src="http://yui.yahooapis.com/2.5.2/build/datasource/datasource-beta-min.js"></script>
	<!-- Source files -->
	<script type="text/javascript"
	src="http://yui.yahooapis.com/2.5.2/build/datatable/datatable-beta-min.js"></script>

	<style type="text/css">

	div.section {
		clear: both;
		border-top: 1px solid #aaa;
		padding-bottom: 1em;
		margin-left: 2em;
		margin-right: 2em;
	}

	div.section h2 {
		font-size: 170%%;
	}
	div.section h3 {
		font-size: 150%%;
	}
	div.section p {
		font-size: 140%%;
	}

	div.colwrapper {
		margin-left: auto; /* center */
		margin-right: auto;
		/* width: 1000px; */
	}
	div.lcolumn {
		float: left;
		margin-left: 2em;
		margin-right: 0em;
	}
	div.rcolumn {
		float: right;
		margin-right: 2em;
		margin-left: 0em;
	}
	
	</style>

	</head>
	<body class="yui-skin-sam">
	<h1><img src="http://{0}/logo" alt="{1}"/> {2} Statistics</h1>
""".format(hostname, hostname, hostname)

print(header)
