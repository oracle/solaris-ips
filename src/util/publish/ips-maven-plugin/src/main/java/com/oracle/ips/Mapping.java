/*
 * CDDL HEADER START
 *
 * The contents of this file are subject to the terms of the
 * Common Development and Distribution License (the "License").
 * You may not use this file except in compliance with the License.
 *
 * You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
 * or http://www.opensolaris.org/os/licensing.
 * See the License for the specific language governing permissions
 * and limitations under the License.
 *
 * When distributing Covered Code, include this CDDL HEADER in each
 * file and include the License file at usr/src/OPENSOLARIS.LICENSE.
 * If applicable, add the following below this CDDL HEADER, with the
 * fields enclosed by brackets "[]" replaced with your own identifying
 * information: Portions Copyright [yyyy] [name of copyright owner]
 *
 * CDDL HEADER END
 *
 *
 *
 * Copyright (c) 2015, 2017, Oracle and/or its affiliates. All rights reserved.
 */

package com.oracle.ips;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedList;
import java.util.List;

public class Mapping
{

    /** Destination directory name. */
    private String directory;

    /** File mode (octal string) to assign to files when installed. */
    private String filemode;

    /** User name for files when installed. */
    private String username;

    /** Group name for files when installed. */
    private String groupname;

    /** Mapping information for source directories. */
    private List<Source> sources;

    /** Mapping information for dependencies. */
    private Dep dependency;

    /** 
     * Method to get destination directory.
     * @return  String directory name.
     */
    public String getDirectory()
    {
        return directory;
    }

    /** 
     * Method to set destination directory.
     * @param dir   directory name.
     * @return  Nothing.
     */
    public void setDirectory( String dir )
    {
        directory = dir;
    }

    /**
     * Method to get file mode.
     * @return  String directory name.
     */
    public String getFilemode()
    {
        return filemode;
    }

    /**
     * Method to set file mode.
     * @param fmode   file mode.
     * @return  Nothing.
     */
    public void setFilemode( String fmode )
    {
        filemode = fmode;
    }

    /** 
     * Method to get user name.
     * @return  String user name.
     */
    public String getUsername()
    {
        return username;
    }

    /**
     * Method to set user name.
     * @param uname   user name to be set.
     * @return  Nothing.
     */
    public void setUsername( String uname )
    {
        username = uname;
    }

    /** 
     * Method to get group name.
     * @return  String group name.
     */
    public String getGroupname()
    {
        return groupname;
    }

    /**
     * Method to set user name.
     * @param grpname   group name to be set.
     * @return  Nothing.
     */
    public void setGroupname( String grpname )
    {
        groupname = grpname;
    }

    /**
     * Method to get sources.
     * @return  List sources.
     */
    public List<Source> getSources()
    {
        return sources;
    }

    /**
     * Method to set source list.
     * @param srclist   source list.
     * @return  Nothing.
     */
    public void setSources( List<Source> srclist )
    {
        sources = srclist;
    }

    /**
     * Method to get dependency.
     * @return  Dep dependency.
     */
    public Dep getDep()
    {
        return dependency;
    }

    /**
     * Method to set dependency.
     * @param dep   dependency.
     * @return  Nothing.
     */
    public void setDep( Dep dep)
    {
        dependency = dep;
    }

    /**
     * Method to get destination.
     * @return  String destination directory.
     */
    public String getDestination()
    {
        return directory;
    }
}

