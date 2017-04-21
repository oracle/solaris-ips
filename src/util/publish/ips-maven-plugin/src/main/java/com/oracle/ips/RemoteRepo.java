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
import java.util.ArrayList;
import java.util.List;
import org.apache.maven.artifact.Artifact;
import org.apache.maven.artifact.DefaultArtifact;
import org.apache.maven.artifact.repository.ArtifactRepository;
import org.apache.maven.artifact.repository.ArtifactRepositoryFactory;
import org.apache.maven.artifact.resolver.*;
import org.apache.maven.artifact.UnknownRepositoryLayoutException;
import org.apache.maven.artifact.handler.manager.ArtifactHandlerManager;
import org.apache.maven.repository.Proxy;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.project.*;
import org.apache.maven.project.MavenProject;
import org.eclipse.aether.RepositorySystemSession;
import org.eclipse.aether.graph.*;
import org.eclipse.aether.util.filter.PatternExclusionsDependencyFilter;
import org.apache.maven.settings.Settings;

public class RemoteRepo{

    private final ArtifactRepository local;

    private final List<ArtifactRepository> remoteRepos;

    private final ProjectBuilder projectBuilder;

    private final ProjectDependenciesResolver projectDependenciesResolver;

    private final RepositorySystemSession session;

    private final ArtifactResolver artifactResolver;

    private final MavenProject aproject;

    private final ArtifactHandlerManager ahm;

    private static RemoteRepo instance = null;

    private Packager pkg = null;

    private RemoteRepo(Settings setting, ArtifactRepository loc,
        ArtifactRepositoryFactory repoFactory, ProjectBuilder pb,
        ProjectDependenciesResolver resolver, ArtifactResolver ar,
        RepositorySystemSession sess, MavenProject aproj,
        ArtifactHandlerManager ahm, Packager pg)
        throws MojoExecutionException
    {
            local = loc;
            remoteRepos = new ArrayList<ArtifactRepository>();
            try{
                    ArtifactRepository artRepo =
                        repoFactory.createArtifactRepository(
                        "central", "http://repo1.maven.apache.org/maven2",
                        "default", null, null);
                    try{
                        Proxy aProx = new Proxy();
                        aProx.setHost(setting.getActiveProxy().getHost());
                        aProx.setProtocol(setting.getActiveProxy().getProtocol());
                        aProx.setPort(setting.getActiveProxy().getPort());
                        artRepo.setProxy(aProx);
                    }catch(Exception e){
                        System.out.println("Skipping proxy setting.");
                    }
                    remoteRepos.add(artRepo);
            }catch(UnknownRepositoryLayoutException e){
                    throw new MojoExecutionException("The repository layout "
                    + "\'default\' is unknown.");
            }
            projectBuilder = pb;
            projectDependenciesResolver = resolver;
            artifactResolver = ar;
            session = sess;
            aproject = aproj;
            pkg = pg;
            this.ahm = ahm;
    }

    public static RemoteRepo build(Settings setting, ArtifactRepository loc,
        ArtifactRepositoryFactory arf, ProjectBuilder pb,
        ProjectDependenciesResolver resolver,
        ArtifactResolver aresolver, RepositorySystemSession session,
        MavenProject aproj, ArtifactHandlerManager ahm, Packager pg) throws
        MojoExecutionException{
            instance = new RemoteRepo(setting, loc, arf, pb, resolver,
                aresolver, session, aproj, ahm, pg);
            return instance;
    }

    public List<Artifact> resolveDependencies(List<Artifact> incls,
      List<String> excls) throws MojoExecutionException{
        List<Artifact> allDeps = new ArrayList<Artifact>();
        DependencyFilter df =
            new PatternExclusionsDependencyFilter(excls);
        pkg.getLog().info(incls.get(0).getType());
        for(Artifact art : incls){
            try{
                //Resolve artifact itself.
                art.setRepository(remoteRepos.get(0));
                art.setArtifactHandler(ahm.getArtifactHandler(art.getType()));
                art.setScope(Artifact.SCOPE_COMPILE_PLUS_RUNTIME);
                ArtifactResolutionRequest arr =
                    new ArtifactResolutionRequest();
                arr.setArtifact(art);
                arr.setLocalRepository(local);
                arr.setRemoteRepositories(remoteRepos);
                Artifact rArt = (Artifact)artifactResolver.resolve(arr
                    ).getArtifacts().toArray()[0];
                allDeps.add(rArt);

                ProjectBuildingRequest prq =
                    new DefaultProjectBuildingRequest();
                prq.setLocalRepository(local);
                prq.setRemoteRepositories(remoteRepos);
                MavenProject jarProject = projectBuilder.build(
                    art, prq).getProject();
                jarProject.setRemoteArtifactRepositories(remoteRepos);
                //Resolve transtive dependencies.
                DefaultDependencyResolutionRequest drr =
                    new DefaultDependencyResolutionRequest(jarProject,
                    session);
                drr.setResolutionFilter(df);
                List<Dependency> deps = projectDependenciesResolver.resolve(
                    drr).getResolvedDependencies();
                for(Dependency dep : deps){
                        DefaultArtifact aArt = new DefaultArtifact(
                            dep.getArtifact().getGroupId(),
                            dep.getArtifact().getArtifactId(),
                            dep.getArtifact().getVersion(),
                            "", "", "", null);
                        aArt.setFile(dep.getArtifact().getFile());
                        allDeps.add(aArt);
                }
            }catch(ProjectBuildingException e){
                    throw new MojoExecutionException("Dependency projects build "
                        + "failed for " + art);
            }catch(NullPointerException e){
                    throw new MojoExecutionException("Errors occurs during "
                        + "resolving dependencies for " + art);
            }catch(DependencyResolutionException e){
                    throw new MojoExecutionException(
                        "Dependency resolution failed for " + art);
            }catch(UnsupportedOperationException e){
                    throw new MojoExecutionException("Unsupported operation occurs "
                        + "during resolving dependencies for " + art);
            }catch(Exception e){
                    e.printStackTrace();
                    throw new MojoExecutionException("Dependency resolution "
                        + "failed for " + art);
            }
        }
        return allDeps;
    }

    public List<Artifact> gatherProjectDependencies()
        throws MojoExecutionException{
            List<Artifact> projDeps = new ArrayList<Artifact>();
            DefaultDependencyResolutionRequest drr =
                new DefaultDependencyResolutionRequest(aproject,
                session);
            List<Dependency> deps = null;
            try{
                    deps = projectDependenciesResolver.resolve(
                        drr).getResolvedDependencies();
            }catch(DependencyResolutionException e){
                    throw new MojoExecutionException("Dependency resolution "
                        + "failed for project dependencies.");
            }
            for(Dependency dep : deps){
                    try{
                            DefaultArtifact aArt = new DefaultArtifact(
                                dep.getArtifact().getGroupId(),
                                dep.getArtifact().getArtifactId(),
                                dep.getArtifact().getVersion(),
                                "", "", "", null);
                            aArt.setFile(dep.getArtifact().getFile());
                            projDeps.add(aArt);
                    }catch(UnsupportedOperationException e){
                        throw new MojoExecutionException("Unsupported "
                            + "operation occurs during adding dependency "
                            + dep);
                    }
            }
            return projDeps;
    }

    public void copyArtifacts(List<Artifact> arts, String destPath)
        throws MojoExecutionException{
            try{
                    for(Artifact art : arts){
                            Files.copy(art.getFile().toPath(), Paths.get(
                                destPath + File.separator
                                + art.getFile().getName()), MISC.copyOpt);
                    }
            }catch(IOException e){
                    throw new MojoExecutionException(e.getMessage());
            }
    }
}
