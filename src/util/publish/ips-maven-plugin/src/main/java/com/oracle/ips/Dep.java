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

import java.util.ArrayList;
import java.util.List;

import org.apache.maven.artifact.Artifact;
import org.apache.maven.artifact.DefaultArtifact;
import org.apache.maven.artifact.versioning.InvalidVersionSpecificationException;
import org.apache.maven.artifact.versioning.VersionRange;
import org.apache.maven.plugin.MojoExecutionException;

/**
 * A description of the set of project dependencies to include in the mapping. If no    includes or excludes are specified,
 * all dependencies will be included in the mapping.
 */
public class Dep
{
    /** List of dependencies to include. */
    private List<Artifact> includes;

    /** List of dependencies to exclude. */
    private List<String> excludes;

    /** by default do not include project dependencies. **/
    private boolean includeProjectDep = false;

    // // // Bean methods

    /** 
     * Method to get whether to include project dependency or not.
     * @return  boolean.
     */
    public boolean getIncludeProjectDep(){
            return includeProjectDep;
    }

    /** 
     * Method to set whether to include project dependencies
     * @param ipd   boolean value to indicate whether to include project
     *              dependencies.
     * @return  Nothing.
     */
    public void setIncludeProjectDep(boolean ipd){
            includeProjectDep = ipd;
    }
    /**
     * Retrieve the list of dependencies to include.
     * @return  List list of includes.
     */
    public List<Artifact> getIncludes()
    {
        return includes;
    }

    /**
     * Set the list of dependencies to include.
     * @param incls   list of includes.
     * @return  Nothing.
     */
    public void setIncludes( List<String> incls )
        throws MojoExecutionException
    {
        includes = parseList(incls);
    }

    /**
     * Retrieve the list of dependencies to exclude.
     * @return  List list of excludes.
     */
    public List<String> getExcludes()
    {
        return excludes;
    }

    /**
     * Set the list of dependencies to exclude.
     * @param excls   list of excludes.
     * @return  Nothing.
     */
    public void setExcludes( List<String> excls )
        throws MojoExecutionException
    {
        excludes = excls;
    }
 
    public String toString()
    {
        StringBuilder sb = new StringBuilder();
        sb.append( "[dependencies" );

        if ( includes != null )
        {
            sb.append( " include [" + includes + "]" );
        }

        if ( excludes != null )
        {
            sb.append( " exclude [" + excludes + "]" );
        }
        
        sb.append( "]" );
        return sb.toString();
    }

    /**
     * Parse the list of dependencies.
     * @param in   list of input.
     * @return  List of artifacts.
     */
    private List parseList( List<String> in )
        throws MojoExecutionException
    {
        List<Artifact> retval = new ArrayList<Artifact>();
        for ( String s : in )
        {
            // Make sure we have group and artifact
            int p1 = s.indexOf( ":" );
            if ( p1 == -1 )
            {
                throw new MojoExecutionException( "Include and exclude must include both group and artifact IDs." );
            }

            // Find end of artifact and create version range
            int p2 = s.indexOf( ":", ( p1 + 1 ) );
            VersionRange vr = null;
            // Default type is jar.
            String type = "jar";
            if ( p2 == -1 )
            {
                p2 = s.length();
                try
                {
                    vr = VersionRange.createFromVersionSpec( "[0,]" );
                }
                catch ( InvalidVersionSpecificationException ex )
                {
                    throw new MojoExecutionException( "Default version string is invalid!" );
                }
            }
            else
            {
                // Find type.
                int p3 = s.indexOf( ":", ( p2 + 1 ) );
                if(p3 == -1){
                        try
                        {
                            vr = VersionRange.createFromVersionSpec( s.substring( p2 + 1 ) );
                        }
                        catch ( InvalidVersionSpecificationException ex )
                        {
                            throw new MojoExecutionException( "Version string "
                                + s.substring( p2 + 1 ) + " is invalid." );
                        }
                }else{
                        type = s.substring(p3 + 1);
                        try
                        {
                            vr = VersionRange.createFromVersionSpec( s.substring( p2 + 1, p3 ) );
                        }
                        catch ( InvalidVersionSpecificationException ex )
                        {
                            throw new MojoExecutionException( "Version string "
                                + s.substring( p2 + 1, p3 ) + " is invalid." );
                        }
                }
            }
            retval.add(
                new DefaultArtifact( s.substring( 0, p1 ), s.substring( p1 + 1, p2 ), vr,
                    null, type, "", null ) );
        }

        return retval;
    }
}
