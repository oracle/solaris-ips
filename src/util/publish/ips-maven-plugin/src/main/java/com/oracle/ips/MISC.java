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

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.file.CopyOption;
import java.nio.file.FileVisitResult;
import static java.nio.file.FileVisitResult.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.SimpleFileVisitor;
import static java.nio.file.StandardCopyOption.COPY_ATTRIBUTES;
import static java.nio.file.StandardCopyOption.REPLACE_EXISTING;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Arrays;
import java.nio.file.FileAlreadyExistsException;
import java.util.EnumSet;
import java.nio.file.FileVisitOption;
import java.util.regex.*;
import org.apache.maven.plugin.MojoExecutionException;
/**
 * 
 * Miscellaneous methods class.
 */
public class MISC{
        /**
         * file path separator.
         */
        public static final String FSEP = File.separator;
        /**
         * Copy options.
         */
        public static final CopyOption[] copyOpt = new CopyOption[]{
            COPY_ATTRIBUTES, REPLACE_EXISTING};
        /**
         * move options.
         */
        public static final CopyOption[] moveOpt = new CopyOption[]{
            REPLACE_EXISTING};

        /**
         * Delete a directory.
         * @param directory String directory name.
         * @throws MojoExecutionException 
         */
        public static void deleteDirectory(String directory) throws
            MojoExecutionException{
                Path dir = Paths.get(directory);
                try {
                        Files.walkFileTree(dir, new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult visitFile(Path file,
                            BasicFileAttributes attrs) throws IOException {
                                Files.delete(file);
                                return CONTINUE;
                        }

                        @Override
                        public FileVisitResult postVisitDirectory(Path dir,
                            IOException exc) throws IOException {
                              if (exc == null) {
                                  Files.delete(dir);
                                  return CONTINUE;
                              } else {
                                  throw exc;
                              }
                          }
                      });
                } catch (IOException e) {
                        throw new MojoExecutionException(String.format("Cannot "
                            + " delete directory: %s. Please check the "
                            + "permission.", directory));
                }
        }

        /**
         * Run command.
         * @param command   String[] command arguments.
         * @return  String result message.
         * @throws MojoExecutionException 
         */
        public static String commandline_run(String[] command)
            throws MojoExecutionException{
                int retcode = -1;
                try{
                        ProcessBuilder pb = new ProcessBuilder(
                            command);
                        pb.redirectErrorStream(true);
                        Process p = pb.start();
                        retcode = p.waitFor();
                        BufferedReader in = new BufferedReader(new
                            InputStreamReader(p.getInputStream()));
                        String msg = "";
                        String line;
                        while ((line = in.readLine()) != null) {
                                msg += (line + "\n");
                        }
                        if(retcode != 0){
                                throw new MojoExecutionException(msg);
                        }
                        return msg;
                }catch(IOException e){
                        throw new MojoExecutionException("Failed to execute"
                            + " the command: " + Arrays.toString(command));
                }
                catch(InterruptedException e){
                        throw new MojoExecutionException("Process "
                            + "interrupted.");
                }
        }

        /**
         * Check whether filter array contains specified element.
         * @param filter    String[] array of filters.
         * @param element   element.
         * @return check result.
         */
        private static boolean ArrayContains(String[] filter, Path element){
                boolean contain = false;
                if(filter == null){
                        return contain;
                }
                for(int i = 0; i < filter.length; i++){
                        if(filter[i].equals(element.toString())
                            || element.startsWith(filter[i])){
                                contain = true;
                        }
                }
                return contain;
        }

        /**
         * Copy directory tree.
         * @param srcPath   String source path.
         * @param destPath  String destination path.
         * @param copyHidden    String whether to copy hidden.
         * @param filter    String[] filters.
         * @throws MojoExecutionException 
         */
        public static void copyDirectoryTree(String srcPath, String destPath,
            boolean copyHidden, final String [] filter) throws
            MojoExecutionException{
                try{
                        final Path sourceDir = Paths.get(srcPath);
                        final Path targetDir = Paths.get(destPath);
                        final boolean copyHiddenF = copyHidden;
                        Files.walkFileTree(sourceDir, EnumSet.of(
                            FileVisitOption.FOLLOW_LINKS), Integer.MAX_VALUE,
                            new SimpleFileVisitor<Path>() {
                                @Override
                                public FileVisitResult preVisitDirectory(
                                    Path dir, BasicFileAttributes attrs)
                                    throws IOException  {
                                        Path target = targetDir.resolve(
                                            sourceDir.relativize(dir));
                                        try {
                                                boolean copy = true;
                                                if(!copyHiddenF &&
                                                    dir.toFile().isHidden()){
                                                        copy = false;
                                                }
                                                if(ArrayContains(filter, dir)){
                                                        copy = false;
                                                }
                                                if(copy){
                                                        Files.copy(dir,
                                                            target, copyOpt);
                                                }
                                        } catch (FileAlreadyExistsException e){
                                                if (!Files.isDirectory(target))
                                                throw e;
                                        }
                                        return FileVisitResult.CONTINUE;
                                }
                                @Override
                                public FileVisitResult visitFile(Path file,
                                    BasicFileAttributes attrs)
                                    throws IOException {
                                        boolean copy = true;
                                        if(!copyHiddenF &&
                                            file.toFile().isHidden()){
                                                copy = false;
                                        }
                                        if(ArrayContains(filter, file)){
                                                copy = false;
                                        }
                                        if(copy){
                                                Files.copy(file,
                                                        targetDir.resolve(
                                                        sourceDir.relativize(
                                                        file)), copyOpt);
                                        }
                                        return FileVisitResult.CONTINUE;
                                }
                        });
                }catch(IOException e){
                        e.printStackTrace();
                        throw new MojoExecutionException(String.format("Cannot "
                            + " copy directory: %s to %s. Please check the "
                            + "permission.", srcPath, destPath));
                }
        }

        /**
         * Check validity on generated IPS package.
         * @param projectRoot   String project root.
         * @param publisher     String publisher.
         * @param pkgName       String package name.
         * @param version       String version.
         * @param checkfile     boolean whether to check file.
         * @return  String check result.
         * @throws MojoExecutionException 
         */
        public static String checkPackage(String projectRoot, String publisher,
            String pkgName, String version, boolean checkfile) throws
            MojoExecutionException{
                BufferedReader br = null;
                Pattern pfmri = Pattern.compile("set\\s+name=pkg.fmri\\s+value=pkg://([^\\r\\n]+?)/([^\\r\\n]+?)@([\\d\\.]+?),");
                Pattern pfile = Pattern.compile("file\\s+([^\\r\\n]+?)\\s+path");
                try{
                        String manifestPath = projectRoot + FSEP
                            + "ips_manifest.p5m";
                        String ipsProtoPath = projectRoot + FSEP
                            + "ips_proto";
                        if(!Files.exists(Paths.get(manifestPath))){
                                throw new MojoExecutionException(String.format(
                                    "ips_manifest.p5m file does not exist "
                                    +"in the current project root %s.",
                                    projectRoot));
                        }
                        if(!Files.exists(Paths.get(ipsProtoPath))){
                                throw new MojoExecutionException(String.format(
                                    "ips_proto directory does not exist "
                                    +"in the current project root %s.",
                                    projectRoot));
                        }
                        br = new BufferedReader(new FileReader(manifestPath));
                        while(br.ready()){
                                String line = br.readLine();
                                Matcher m = pfmri.matcher(line);
                                if(m.find()){
                                        if(publisher != null &&
                                            !m.group(1).equals(publisher)){
                                                return
                                                String.format("publisher: "
                                                + "\'%s\' in ips_manifest.p5m "
                                                + "is different from provided: "
                                                + "\'%s\'.", m.group(1),
                                                publisher);
                                        }
                                        if(pkgName != null &&
                                            !m.group(2).equals(pkgName)){
                                                return
                                                String.format("pkgName: \'%s\' "
                                                + "in ips_manifest.p5m is "
                                                + "different from provided: "
                                                + "\'%s\'.", m.group(2),
                                                pkgName);
                                        }
                                        if(version != null &&
                                            !m.group(3).equals(version)){
                                                return
                                                String.format("version: \'%s\' "
                                                + "in ips_manifest.p5m is "
                                                + "different from provided: \'"
                                                + "%s\'.", m.group(3), version);
                                        }
                                }
                                if(checkfile){
                                        m = pfile.matcher(line);
                                        if(m.find()){
                                                String protoFilePath =
                                                    ipsProtoPath + FSEP
                                                    + m.group(1);
                                                if(!Files.exists(Paths.get(
                                                    protoFilePath))){
                                                        return
                                                        String.format("Proto "
                                                        + "file \'%s\' does "
                                                        + "not exist.",
                                                        protoFilePath);
                                                }
                                        }
                                }
                        }
                }catch(IOException e){
                        throw new MojoExecutionException("Checking package "
                        + "operation failed.");
                }
                finally{
                        try{
                                br.close();
                        }catch(Exception e){}
                }
                return null;
        }
}

