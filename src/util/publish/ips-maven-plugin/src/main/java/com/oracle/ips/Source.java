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

import java.util.List;
import java.util.regex.Pattern;

/**
 * A description of a location where files to be packaged can be found.
 */
public class Source
{
    // // // Properties

    /** The source location. */
    private String location;

    /** The list of inclusions. */
    private List<String> includes;

    /** The list of exclusions. */
    private List<String> excludes;

    /** The destination. */
    private String destination;

    /** The target OS name. */
    private String targetOSName;

    /** The target OS name pattern. */
    private Pattern targetOSNamePattern;

    /** 
     * Method to get source location.
     * @return  String source location.
     */
    public String getLocation()
    {
        return location;
    }

    /** 
     * Method to set source location.
     * @param loc   source location.
     * @return  Nothing.
     */
    public void setLocation( String loc )
    {
        location = loc;
    }

    /** 
     * Method to get include contents.
     * @return  List includes.
     */
    public List<String> getIncludes()
    {
        return includes;
    }

    /**
     * Method to set includes.
     * @param incl   list of includes.
     * @return  Nothing.
     */
    public void setIncludes( List<String> incl )
    {
        includes = incl;
    }

    /**
     * Method to get exclude contents.
     * @return  List includes.
     */
    public List<String> getExcludes()
    {
        return excludes;
    }

    /**
     * Method to set excludes.
     * @param incl   list of excludes.
     * @return  Nothing.
     */
    public void setExcludes( List<String> excl )
    {
        excludes = excl;
    }

    /**
     * Method to get Destination.
     * @return  String destination.
     */
    public String getDestination()
    {
        return this.destination;
    }

    /**
     * Method to set Destination.
     * @param destination   destination
     * @return  Nothing.
     */
    public void setDestination( String destination )
    {
        this.destination = destination;
    }

    /**
     * Method to get target OS name.
     * @return  String target OS name.
     */
    public String getTargetOSName()
    {
        return this.targetOSName;
    }

    /**
     * Method to set target OS name.
     * @param targetOSName   target OS name.
     * @return  Nothing.
     */
    public void setTargetOSName( String targetOSName )
    {
        this.targetOSName = targetOSName;
        this.targetOSNamePattern = targetOSName != null ? Pattern.compile( targetOSName ) : null;
    }

    /**
     * Method to check OS name match.
     * @param osname    OS name.
     * @return  boolean match result.
     */
    boolean matchesOSName( String osName )
    {
        return targetOSNamePattern == null ? true : targetOSNamePattern.matcher( osName ).matches();
    }

    /** {@inheritDoc} */
    public String toString()
    {
        StringBuilder sb = new StringBuilder();
        sb.append( "{" );

        if ( location == null )
        {
            sb.append( "nowhere" );
        }
        else
        {
            sb.append( "\"" + location + "\"" );
        }

        if ( includes != null )
        {
            sb.append( " incl:" + includes );
        }

        if ( excludes != null )
        {
            sb.append( " excl:" + excludes );
        }

        if ( destination != null )
        {
            sb.append( " destination: " );
            sb.append( destination );
        }

        sb.append( "}" );
        return sb.toString();
    }
}

