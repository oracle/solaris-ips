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
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;
import org.apache.maven.artifact.Artifact;
import org.apache.maven.artifact.repository.ArtifactRepository;
import org.apache.maven.artifact.repository.ArtifactRepositoryFactory;
import org.apache.maven.artifact.handler.manager.ArtifactHandlerManager;
import org.apache.maven.artifact.resolver.ArtifactResolver;
import org.apache.maven.execution.MavenSession;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.*;
import org.apache.maven.project.MavenProject;
import org.apache.maven.project.ProjectBuilder;
import org.apache.maven.project.ProjectDependenciesResolver;
import org.apache.maven.settings.Settings;
import org.eclipse.aether.RepositorySystemSession;
import org.codehaus.plexus.util.DirectoryScanner;
import org.apache.commons.lang3.ArrayUtils;

@Mojo( name = "packager")
public class Packager extends AbstractMojo{

    @Component ( role = org.apache.maven.settings.Settings.class)
    protected Settings setting;
    @Parameter( property = "localRepository", readonly = true, required = true)
    protected ArtifactRepository local;

    @Component ( role = org.apache.maven.artifact.repository.ArtifactRepositoryFactory.class)
    protected ArtifactRepositoryFactory repoFactory;

    @Component ( role = org.apache.maven.project.ProjectBuilder.class)
    protected ProjectBuilder projectBuilder;

    @Component( role =
        org.apache.maven.project.ProjectDependenciesResolver.class)
    protected ProjectDependenciesResolver projectDependenciesResolver;

    @Component( role =
        org.apache.maven.artifact.resolver.ArtifactResolver.class)
    protected ArtifactResolver artifactResolver;

    @Component(role=ArtifactHandlerManager.class)
    private ArtifactHandlerManager ahm;

    @Parameter( defaultValue = "${repositorySystemSession}")
    private RepositorySystemSession session;

    @Component
    protected MavenProject aproject;

    @Component
    private MavenSession mavenSession;

    @Parameter( defaultValue = "${reactorProjects}")
    private List reactorProjects;

    private static final String FSEP = File.separator;

    @Parameter(property="pkgName")
    private String pkgName;
    public void setPkgName(String pn)
    {
            pkgName = pn;
    }

    @Parameter(property="publisher")
    private String publisher;
    public void setPublisher(String pub){
            publisher = pub;
    }

    @Parameter(property="version")
    private String version;
    public void setVersion(String ver){
            version = ver;
    }

    @Parameter(property="projectSummary")
    private String projectSummary = "none";
    public void setProjectSummary(String psum){
            if(psum != null){
                    projectSummary = psum;
            }
    }

    @Parameter(property="projectDescription")
    private String projectDescription = "none";
    public void setProjectDescription(String pd){
            if(pd != null){
                    projectDescription = pd;
            }
    }

    @Parameter(property="projectRoot")
    private String projectRoot;
    public void setProjectRoot(String pr)
    {
            projectRoot = pr;
    }

    @Parameter
    private List<Mapping> mappings = Collections.EMPTY_LIST;

    private RemoteRepo repo;

    private String metaTemplate(){
            String arch = "i386";
            String osarch = System.getProperty("os.arch");
            if(osarch.equals("sparcv9") || osarch.equals("sparc")){
                    arch = "sparc";
            }

            return String.format("set name=pkg.fmri " +
                "value=pkg://%s/%s@%s,%s-0\n"+
                "set name=pkg.summary value=\"%s\"\n" +
                "set name=pkg.description value=\"%s\"\n" +
                "set name=variant.arch value=%s\n",
                publisher, pkgName, version, System.getProperty("os.version"), projectSummary, projectDescription,
                arch);
    }

    private String getRelativePath(String aDir) throws MojoExecutionException{
        if((new File(aDir)).isAbsolute()){
                int len = aDir.length();
                int lfsep = aDir.indexOf(FSEP);
                // Path like c:\\path.
                if(lfsep == 2 && aDir.charAt(1) == ':'){
                        if(aDir.contains("/")){
                                throw new MojoExecutionException(
                                    String.format("The directory path %s is "
                                    + "invalid.", aDir));
                        }
                        //If valid absolute path.
                        if(lfsep + 1 < len - 1 && aDir.charAt(lfsep + 1)
                            == '\\'){
                                    if(lfsep + 2 > len-1){
                                            aDir = "";
                                    }else{
                                            boolean left = false;
                                            for(int i = lfsep + 2; i<len; i++){
                                                    if(aDir.charAt(i) != 
                                                        '\\'){
                                                            aDir =
                                                                aDir.substring(i);
                                                            left = true;
                                                            break;
                                                    }
                                            }
                                            if(!left){
                                                    aDir = "";
                                            }
                                    }
                        }else{
                                throw new MojoExecutionException(
                                    String.format("The directory path "
                                    + "%s is a invalid absolute path.", aDir));
                        }
                }else if(lfsep == 0){
                        // Path like /opt/path.
                        boolean left = false;
                        for(int i = lfsep + 1; i<len; i++){
                                if(aDir.charAt(i) !=
                                    '\\'){
                                        aDir =
                                            aDir.substring(i);
                                        left = true;
                                        break;
                                }
                        }
                        if(!left){
                                aDir = "";
                        }
                }
        }
        return aDir;
    }

    private void genMani_rec(String dirPath, String relPath,
        DirAction defaultAction, HashMap<String, DirAction> dirActionMap,
        HashMap<String, FileAction> mfa)throws IOException{
            //We don't actually deliver a dir action but instead we deliver all
            //all file actions inside the specific dir.
            File dir = new File(dirPath);
            String[] files = dir.list();
            if(files == null){
                    return;
            }
            //bw.write(String.format("dir path=%s "
            //    + "owner=%s group=%s mode=%s\n",
            //    relPath, dirAction.getUsername(), dirAction.getGroupname(),
            //    dirAction.getFilemode()));
            for(String file : files){
                    String newPath = dirPath + FSEP + file;
                    String newRelPath = "";
                    //We are in root level.
                    if(relPath.equals("")){
                            newRelPath = file;
                    }else{
                            newRelPath = relPath + FSEP + file;
                    }

                    File aFile = new File(newPath);
                    if(aFile.isDirectory() && !aFile.isHidden()){
                            DirAction newdefault = null;
                            if(dirActionMap.containsKey(newRelPath)){
                                    newdefault = dirActionMap.get(newRelPath);
                            }else{
                                    newdefault = defaultAction;
                            }
                            genMani_rec(newPath, newRelPath,
                                newdefault, dirActionMap, mfa);
                    }else if(aFile.isFile() && !aFile.isHidden()){
                            FileAction afa = new FileAction(newRelPath,
                                defaultAction.getFilemode(),
                                defaultAction.getUsername(),
                                defaultAction.getGroupname(),
                                newRelPath);
                            mfa.put(newRelPath, afa);
                    }
            }
    }

    private void genMani(HashMap<String, DirAction> dirActionMap,
        ArrayList<FileAction> fileActions, ArrayList<LinkAction> linkActions)
        throws MojoExecutionException{
            BufferedWriter bw = null;
            try{
                    String ipsManifest = projectRoot + FSEP + "ips_manifest.p5m";
                    FileWriter fw = new FileWriter(ipsManifest);
                    bw = new BufferedWriter(fw);
                    String meta = metaTemplate();
                    bw.write(meta);
                    //This is used to store files actions during recursively
                    //traversing the directories. Might be overwitten by
                    //fileActions.
                    HashMap<String, FileAction> mergedFileActions =
                        new HashMap<String, FileAction>();

                    //Get root dir action.
                    DirAction defaultAction = dirActionMap.get("");
                    if(defaultAction == null){
                            defaultAction = new DirAction("0755", "root",
                                "bin", "");
                    }
                    genMani_rec(ipsPkgProtoPath,
                        "", defaultAction, dirActionMap, mergedFileActions);

                    for(int i = 0; i< fileActions.size(); i++){
                            String fkey = fileActions.get(i).getDestpath();
                            if(mergedFileActions.containsKey(fkey)){
                                    mergedFileActions.put(fkey,
                                    fileActions.get(i));
                            }
                    }
                    Set faSet = mergedFileActions.entrySet();
                    Iterator faIter = faSet.iterator();
                    while(faIter.hasNext()){
                            Map.Entry me = (Map.Entry)faIter.next();
                            FileAction fa = (FileAction)me.getValue();
                            String destPath = fa.getDestpath();
                            //If the path is a windows style path, convert it
                            //to unix style.
                            if(destPath != null && !destPath.contains("/")){
                                    destPath = destPath.replaceAll(
                                        "[\\\\]+", "/");
                            }
                            bw.write(String.format("file %s path=%s "
                                + "owner=%s group=%s mode=%s\n",
                                destPath, destPath,
                                fa.getUsername(),
                                fa.getGroupname(),
                                fa.getFilemode()));
                    }
                    for(int i = 0; i< linkActions.size(); i++){
                            bw.write(String.format("link path=%s target=%s\n",
                                linkActions.get(i).getPath(),
                                linkActions.get(i).getTarget()));
                    }
            }catch(IOException e){
                    throw new MojoExecutionException("Generating manifest "
                        + "operation failed.");
            }finally{
                try{
                        bw.close();
                }catch(IOException e){}
            }
    }

    private void updateDirActionMap(Mapping mp) throws MojoExecutionException{
            String afilemode = mp.getFilemode();
            if(afilemode == null){
                    afilemode = "0755";
            }
            String ausername= mp.getUsername();
            if(ausername == null){
                    ausername = "root";
            }
            String agroupname = mp.getGroupname();
            if(agroupname == null){
                    agroupname = "bin";
            }
            if(mp.getDirectory() == null){
                    throw new MojoExecutionException("Directory "
                        + "path is missing in mapping.");
            }
            dirActionMap.put(getRelativePath(mp.getDirectory()),
                new DirAction(afilemode, ausername, agroupname,
                getRelativePath(mp.getDirectory())));
    }

    private String [] copyFilter(List<String> excludes, String srcAbsPath){
            if(excludes != null && !excludes.isEmpty()
                && excludes.get(0) != null){
                    DirectoryScanner scanner = new DirectoryScanner();
                    scanner.setIncludes(excludes.toArray(new String[0]));
                    scanner.setBasedir(srcAbsPath);
                    scanner.setCaseSensitive(false);
                    scanner.scan();
                    String[] files = scanner.getIncludedFiles();
                    String[] dirs = scanner.getIncludedDirectories();
                    String [] fileAndDirs = ArrayUtils.addAll(files, dirs);
                    if(fileAndDirs != null){
                            for(int i = 0; i < fileAndDirs.length; i++){
                                    fileAndDirs[i] = srcAbsPath + FSEP +
                                        fileAndDirs[i];
                            }
                    }
                    return fileAndDirs;
            }
            return null;
    }

    private void makeProto() throws MojoExecutionException{
            try{
                // Get all directory actions first.
                ArrayList<FileAction> fileActions = new ArrayList<FileAction>();
                ArrayList<LinkAction> linkActions = new ArrayList<LinkAction>();
                for(Mapping mp: mappings){
                    String protoDirPath = ipsPkgProtoPath + FSEP +
                        getRelativePath(mp.getDirectory());
                    boolean onlyHasSoftLink = false;
                    boolean changed = false;
                    List<Source> srcs = mp.getSources();
                    if(srcs != null){
                        for(Source src: srcs){
                            if(src.getClass().toString().contains(
                                "SoftlinkSource")){
                                    if(!changed){
                                            onlyHasSoftLink = true;
                                    }
                            }else{
                                    onlyHasSoftLink = false;
                                    changed = true;
                            }
                        }
                    }
                    if(!dirMap.contains(protoDirPath) && !onlyHasSoftLink){
                        dirMap.add(protoDirPath);
                        Files.createDirectories(Paths.get(
                            protoDirPath));
                    }
                    if(!onlyHasSoftLink){
                            updateDirActionMap(mp);
                    }
                    if(srcs != null){
                        for(Source src: srcs){
                            if(src.getLocation() == null){
                                    throw new MojoExecutionException(
                                        "Location path is missing in "
                                        + "mapping --> sources --> source.");
                            }
                            String srcAbsPath = src.getLocation();
                            if(!Paths.get(srcAbsPath).isAbsolute()){
                                    srcAbsPath = projectRoot + FSEP +
                                        src.getLocation();
                            }
                            //In this case, the source is a softlink source.
                            if(src.getClass().toString().contains(
                                "SoftlinkSource")){
                                if(src.getDestination() == null){
                                    linkActions.add(new LinkAction(
                                        getRelativePath(src.getLocation()),
                                        getRelativePath(mp.getDirectory())));
                                }else{
                                    String dest = getRelativePath(
                                        mp.getDirectory()) + FSEP +
                                        getRelativePath(src.getDestination());
                                    linkActions.add(new LinkAction(
                                        getRelativePath(src.getLocation()),
                                        dest));
                                }
                            }else{
                                if(!Files.exists(Paths.get(srcAbsPath))){
                                        throw new MojoExecutionException(
                                            String.format("File or directory: "
                                                + "%s does not exist.",
                                                srcAbsPath));
                                }
                                String [] fileFilter = copyFilter(
                                    src.getExcludes(), srcAbsPath);
                                if(Files.isDirectory(Paths.get(srcAbsPath)))
                                {
                                        MISC.copyDirectoryTree(srcAbsPath,
                                            protoDirPath, false, fileFilter);
                                }else if(Files.isRegularFile(Paths.get(
                                    srcAbsPath))){
                                        String destPath = protoDirPath + FSEP +
                                            (new File(srcAbsPath)).getName();
                                        Files.copy(Paths.get(srcAbsPath),
                                            Paths.get(destPath), MISC.copyOpt);
                                        if(mp.getDirectory() == null){
                                            throw new MojoExecutionException(
                                                "Directory path is missing in "
                                                + "mapping.");
                                        }
                                        String fn = getRelativePath(
                                            mp.getDirectory()) + FSEP +
                                            Paths.get(srcAbsPath).getFileName();
                                        String afilemode = mp.getFilemode();
                                        if(afilemode == null){
                                                afilemode = "0755";
                                        }
                                        String ausername= mp.getUsername();
                                        if(ausername == null){
                                                ausername = "root";
                                        }
                                        String agroupname = mp.getGroupname();
                                        if(agroupname == null){
                                                agroupname = "bin";
                                        }
                                        fileActions.add(new FileAction(
                                            fn, afilemode,
                                            ausername,
                                            agroupname, fn));
                                }
                            }
                        }
                    }
                    Dep deps = mp.getDep();
                    if(deps != null){
                        List<Artifact> incls = deps.getIncludes();
                        List<String> excls = deps.getExcludes();
                        repo = RemoteRepo.build(setting, local,
                            repoFactory, projectBuilder,
                            projectDependenciesResolver,
                            artifactResolver, session,
                            aproject, ahm, this);
                        if(excls == null){
                                excls = new ArrayList<String>();
                        }
                        List<Artifact> pdeps = null;
                        if(deps.getIncludeProjectDep()){
                                pdeps = repo.gatherProjectDependencies();
                        }
                        List<Artifact> combo = new ArrayList<Artifact>();

                        if(pdeps != null){
                                combo.addAll(pdeps);
                        }
                        if(incls != null && !incls.isEmpty()){
                                combo.addAll(repo.resolveDependencies(incls,
                                    excls));
                        }
                        if(!combo.isEmpty()){
                                String destPath = ipsPkgProtoPath + FSEP
                                    + getRelativePath(mp.getDirectory());
                                repo.copyArtifacts(combo, destPath);
                        }
                    }
                }
                genMani(dirActionMap, fileActions, linkActions);
            }catch(IOException e){
                    throw new MojoExecutionException("File operation failed.");
            }
    }

    private void copyPerModuleDependencies() throws MojoExecutionException{
            String ipsPkgProtoPath = String.format("%s%sips_proto", projectRoot,
                FSEP, FSEP);
            try{
                for(Mapping mp: mappings){
                        Dep deps = mp.getDep();
                        if(deps != null && deps.getIncludeProjectDep()){
                                repo = RemoteRepo.build(setting, local,
                                    repoFactory, projectBuilder,
                                    projectDependenciesResolver,
                                    artifactResolver, session,
                                    aproject, ahm, this);
                                String protoDirPath = ipsPkgProtoPath + FSEP +
                                    getRelativePath(mp.getDirectory());
                                if(!dirMap.contains(protoDirPath)){
                                        dirMap.add(protoDirPath);
                                        Files.createDirectories(Paths.get(
                                            protoDirPath));
                                }
                                updateDirActionMap(mp);
                                List<Artifact> currentProjDeps=
                                    repo.gatherProjectDependencies();
                                repo.copyArtifacts(currentProjDeps,
                                    protoDirPath);
                        }
                }
            }catch(IOException e){
                    throw new MojoExecutionException("File operation failed.");
            }
    }
    private static ArrayList<String> dirMap = new ArrayList<String>();
    private static HashMap<String, DirAction> dirActionMap = new HashMap<String,
        DirAction>();
    private String ipsPkgProtoPath = null;

    public void execute() throws MojoExecutionException
    {
            getLog().info("IPS Maven Plugin Packager");
            final int size = reactorProjects.size();
            if(projectRoot == null){
                    projectRoot = mavenSession.getExecutionRootDirectory();
            }
            if(ipsPkgProtoPath == null){
                    ipsPkgProtoPath = String.format("%s%sips_proto",
                        projectRoot, FSEP, FSEP);
            }
            MavenProject lastProject = (MavenProject) reactorProjects.get(
                size - 1);
             //First module or project, doing cleaning work.
            if(aproject == reactorProjects.get(0)){
                    Path ipsPkgProtoPathP = Paths.get(ipsPkgProtoPath);
                    if(Files.exists(ipsPkgProtoPathP)){
                            MISC.deleteDirectory(ipsPkgProtoPath);
                    }
            }
            if (lastProject != aproject) {
                    copyPerModuleDependencies();
                    getLog().info("Not the last module. Only per-module "
                        + "dependencies are copyed.");
                    return;
            }

            if(pkgName == null){
                    pkgName = mavenSession.getTopLevelProject().getArtifactId();
                    if(pkgName == null){
                            throw new MojoExecutionException("pkgName cannot "
                                + "be empty. please configure \'pkgName\' in "
                                + "pom.xml");
                    }
            }
            if(publisher == null){
                    throw new MojoExecutionException("publisher cannot be "
                        + "empty. please configure \'publisher\' in pom.xml");
            }
            if(version == null){
                    version = mavenSession.getTopLevelProject().getVersion();
                    if(version == null){
                            throw new MojoExecutionException("version cannot "
                                + "be empty. please configure \'version\' in "
                                + "pom.xml");
                    }
            }else{
                    Pattern p = Pattern.compile("[a-zA-Z]");
                    Matcher m = p.matcher(version);
                    if(m.find()){
                            throw new MojoExecutionException("Invalid version "
                                + "provided. Please configure version without "
                                + "alphabetic characters.");
                    }
                    p = Pattern.compile("0[0-9]+");
                    m = p.matcher(version);
                    if(m.find()){
                            throw new MojoExecutionException ("Invalid version "
                                +"provided. Please configure version without "
                                + "leading zeros.");
                    }
            }
            makeProto();
    }
}

