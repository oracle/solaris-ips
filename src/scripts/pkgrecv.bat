@echo off
rem
rem CDDL HEADER START
rem
rem The contents of this file are subject to the terms of the
rem Common Development and Distribution License (the "License").
rem You may not use this file except in compliance with the License.
rem
rem You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
rem or http://www.opensolaris.org/os/licensing.
rem See the License for the specific language governing permissions
rem and limitations under the License.
rem
rem When distributing Covered Code, include this CDDL HEADER in each
rem file and include the License file at usr/src/OPENSOLARIS.LICENSE.
rem If applicable, add the following below this CDDL HEADER, with the
rem fields enclosed by brackets "[]" replaced with your own identifying
rem information: Portions Copyright [yyyy] [name of copyright owner]
rem
rem CDDL HEADER END
rem
rem Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
rem Use is subject to license terms.
rem

setlocal
set CMDSCRIPT=pull.py
set MY_HOME=%~dp0
set MY_IPS_BASE=%MY_HOME%\..\..
set PYTHONPATH=%PYTHONPATH%;%MY_IPS_BASE%\usr\lib\python2.4\vendor-packages
set MY_BASE=%MY_HOME%\..\..\..
set PATH=%MY_BASE%\python;%PATH%
set PYTHONUNBUFFERED=yes

rem
rem find python.[exe/bat/cmd] on the %PATH%
rem
for %%i in (cmd bat exe) do (
    for %%j in (python.%%i) do (
        set PYEXE="%%~$PATH:j"
        if not [%PYEXE%]==[""] (
            %PYEXE% %MY_HOME%\%CMDSCRIPT% %*
            goto :EOF
        )
    )
)

rem If we didn't find it above, try to invoke it using the
rem application associated with the python file extension (.py)
rem
"%MY_HOME%\%CMDSCRIPT%" %*


