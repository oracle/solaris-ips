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
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.*;
import org.apache.maven.project.MavenProject;

@Mojo( name = "installer",
     requiresProject = false)
public class Installer extends AbstractMojo{
        private static final String FSEP = File.separator;

        /* Property to set project root. Default: current directory */
        @Parameter(property="projectRoot")
        private String pRoot = System.getProperty("user.dir");
        public void setPRoot(String pr)
        {
                pRoot = pr;
        }

        /* Property to set local repository path. Default: null.*/
        @Parameter(property="localRepoPath")
        private String localRepoPath;
        public void setLocalRepoPath(String lrp){
                localRepoPath = lrp;
        }

        @Component
        protected MavenProject aproject;

        @Parameter( defaultValue = "${reactorProjects}")
        private List reactorProjects;

        @Parameter(property="publisher")
        private String publisher;
        public void setPublisher(String pub)
        {
                publisher = pub;
        }

        /* Property to set publisher. Default: null. */
        @Parameter(property="publisher")
        private String _pub;

        /* Main execution method. */
        public void execute() throws MojoExecutionException
        {
                getLog().info("IPS Maven Plugin Installer");
                final int size = reactorProjects.size();
                MavenProject lastProject = (MavenProject) reactorProjects.get(
                    size - 1);
                if (lastProject != aproject) {
                        getLog().info("Not the last module. Skipped!");
                        return;
                }
                if(!Files.exists(Paths.get("/usr/bin/pkgsend"))
                    || !Files.exists(Paths.get("/usr/bin/pkgrepo")))
                {
                        getLog().error("PKG5 commands are not available."
                            + "\'installer\' goal will not be executed.");
                        throw new MojoExecutionException("");
                }
                if(!Paths.get(pRoot).isAbsolute()){
                        pRoot = System.getProperty("user.dir") + FSEP
                            + pRoot;
                }
                getLog().info(String.format("Running as %s.",
                    System.getProperty("user.name")));
                String manifestPath = pRoot + FSEP
                    + "ips_manifest.p5m";
                String ipsProtoPath = pRoot + FSEP
                    + "ips_proto";

                if(_pub != null && !_pub.equals(publisher)){
                        String msg = MISC.checkPackage(pRoot, _pub,
                            null, null, false);

                        if(msg != null){
                                throw new MojoExecutionException(msg + "\n"
                                + "please make sure publisher provided by "
                                + "-Dpublisher option is the same as in the "
                                + "manifest.");
                        }
                        publisher = _pub;
                }

                String msg = MISC.checkPackage(pRoot, publisher == null?
                    "":publisher, null, null, false);
                if(msg != null){
                        throw new MojoExecutionException(msg + "\n" + "please "
                            +"make sure publisher in pom.xml is the same as in "
                            + "the manifest.");
                }

                msg = MISC.checkPackage(pRoot, null, null, null, true);
                if(msg != null){
                        throw new MojoExecutionException(msg + "\n" + "please "
                            + "check the ips_proto directory and re-run "
                            + "packager goal.");
                }

                if(localRepoPath == null){
                        throw new MojoExecutionException("The local "
                        + "repository path is not provided. Please use "
                        + "-DlocalRepoPath option or configure the path in "
                        + "pom.xml.");
                }
                if(publisher == null){
                        throw new MojoExecutionException("The publisher "
                        + "name is not provided. Please use -Dpublisher option "
                        + "configure the path in pom.xml.");
                }

                if (!Files.exists(Paths.get(localRepoPath))){
                        getLog().error(String.format("Cannot install. Local "
                            + "repository at %s does not exist.",
                            localRepoPath));
                        throw new MojoExecutionException("");
                }

                String[] command = {"/bin/sh", "-c",
                    String.format("/usr/bin/pkgsend -s %s publish -d %s %s",
                    localRepoPath, ipsProtoPath, manifestPath)};
                try{
                        String message = MISC.commandline_run(command);
                        getLog().info(message);
                }catch(MojoExecutionException e){
                        getLog().error(String.format("Error occurs during "
                            + "publish package to local repository: %s\n"
                            + e.getMessage(), localRepoPath));
                        throw new MojoExecutionException("");
                }
        }
}

