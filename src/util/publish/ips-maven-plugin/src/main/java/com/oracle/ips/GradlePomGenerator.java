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
import java.io.*;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.*;

/**
 *
 * Generate pom.xml from gradle project.
 * This is a deprecated class and will be removed later.
 */
@Mojo ( name = "gradlepom",
        requiresProject = false)
public class GradlePomGenerator extends AbstractMojo{

        @Parameter(property="gradlePath")
        private String gradlePath = null;
        public void setGradlePath(String gp)
        {
                gradlePath = gp;
        }

        @Parameter(property="projectRoot")
        private String pRoot = System.getProperty("user.dir");
        public void setPRoot(String pr)
        {
                pRoot = pr;
        }

        public void execute() throws MojoExecutionException
        {
                if(pRoot == null){
                        getLog().error("No project root is set for "
                                + "generating pom.xml. Please use "
                                + "-DprojectRoot to set the path of a project "
                                + "root.");
                        throw new MojoExecutionException("");
                }
                if(gradlePath == null){
                        getLog().error("No gradle path is set for "
                                + "generating pom.xml. Please use "
                                + "-DgradlePath to set the path of gradle "
                                + "executable.");
                        throw new MojoExecutionException("");
                }
                if(!Paths.get(pRoot).isAbsolute()){
                        pRoot = System.getProperty("user.dir") + MISC.FSEP
                            + pRoot;
                }
                String scriptPath = pRoot + MISC.FSEP + "build.gradle";
                String origScriptPath = pRoot + MISC.FSEP +
                    ".build.gradle.orig";
                BufferedReader br = null;
                BufferedReader br2 = null;
                BufferedWriter bw = null;
                try{
                        if(!Files.exists(Paths.get(scriptPath))){
                                throw new MojoExecutionException(String.format(
                                    "No gradle build script exists in project "
                                    + "%s", pRoot));
                        }
                        String pomPath = pRoot + MISC.FSEP + "pom.xml";
                        if(Files.exists(Paths.get(pomPath))){
                                throw new MojoExecutionException("pom.xml "
                                    + "already exists for this project.");
                        }

                        Files.move(Paths.get(scriptPath),
                            Paths.get(origScriptPath), MISC.moveOpt);
                        br = new BufferedReader(new FileReader(origScriptPath));
                        bw = new BufferedWriter(new FileWriter(scriptPath));
                        boolean isJava = false;
                        boolean hasMaven = false;
                        String patJava = "\\s*apply\\s+plugin:\\s+[\'\"]java"
                            + "[\'\"]\\s*";
                        String patMaven = "\\s*apply\\s+plugin:\\s+[\'\"]maven"
                            + "[\'\"]\\s*";
                        while(br.ready()){
                                String line = br.readLine();
                                if(!isJava){
                                        isJava = line.matches(patJava);
                                }
                                if(!hasMaven){
                                        hasMaven = line.matches(patMaven);
                                }
                        }
                        br.close();
                        if(isJava){
                                br2 = new BufferedReader(new FileReader(
                                    origScriptPath));
                                int matchCount = 0;
                                while(br2.ready()){
                                        String line = br2.readLine();
                                        bw.write(line+"\n");
                                        if(!hasMaven){
                                                if(line.matches(patJava)){
                                                        bw.write("apply "
                                                        + "plugin: \'maven\'\n"
                                                        );
                                                        bw.write("task "
                                                        + "ipsMavenPluginWriteNewPom "
                                                        + "<< {\n"
                                                        + "    pom{}.writeTo(\""
                                                        + "pom.xml\")\n"
                                                        + "}\n");
                                                }
                                        }else{
                                                if(line.matches(patMaven) ||
                                                    line.matches(patJava)){
                                                        if(++matchCount == 2){
                                                                bw.write("task ipsMavenPluginWriteNewPom << {\n"
                                                                + "    pom{}.writeTo(\""
                                                                + "pom.xml\")\n"
                                                                + "}\n");
                                                                matchCount = 0;
                                                        }
                                                }
                                        }
                                }
                        }else{
                                throw new MojoExecutionException(String.format(
                                    "Project %s is unsupported. Please provide "
                                    + "a Java project.", pRoot));
                        }
                        bw.close();

                        String[] command = {
                            gradlePath, "-b", scriptPath,
                            "ipsMavenPluginWriteNewPom"};
                        MISC.commandline_run(command);

                }catch(IOException e){
                        throw new MojoExecutionException("File operation "
                            + "failed. Cannot generate pom.xml.");
                }
                finally{
                        try{
                                if(Files.exists(Paths.get(origScriptPath))){
                                        Files.move(Paths.get(origScriptPath),
                                            Paths.get(scriptPath),
                                            MISC.moveOpt);
                                }
                        }catch(IOException e){
                                throw new MojoExecutionException(String.format(
                                    "File operation failed. Cannot move %s "
                                    + "-> %s", origScriptPath, scriptPath));
                        }
                        try{
                                br.close();
                                br2.close();
                                bw.close();
                        }catch(Exception e){}
                }
        }
}

