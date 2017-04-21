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
import java.io.FileWriter;
import java.io.IOException;

import java.nio.file.*;
import java.util.Iterator;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.*;
import org.jdom2.Document;
import org.jdom2.Element;
import org.jdom2.JDOMException;
import org.jdom2.Namespace;
import org.jdom2.input.SAXBuilder;
import org.jdom2.output.Format;
import org.jdom2.output.XMLOutputter;

@Mojo( name = "autoconf",
       requiresProject = false)
/**
 * AutoConfgurer to attach a sample configuration to a project pom.xml.
 * This is served as a initial setup of ips-maven-plugin. Not much
 * customization here, and users need to modify the generated pom.xml to
 * fulfill their needs.
 */
public class AutoConfigurer extends AbstractMojo{
        private static final String FSEP = File.separator;

        /*
         * operation: specifying how to attach the ips-maven-plugin
         * to the project for build. It allows the following values:
         *     package: attach the goal 'packager' to package phase.
         *              This is default operation.
         *     install: attach the goal 'installer' to install phase.
         *              The package operation is included in this
         *              operation.
         *     deploy:  attach the goal 'deployer' to deploy phase.
         *              The package operation is included in this
         *              operation.
         *     all:     attach all goals to corresponding phase.
         *     revert:  revert back to the original pom.xml.
         */
        @Parameter(property="operation")
        private String operation = "package";
        public void setOperation(String op){
                operation = op;
        }

        /** Property to set project root. Default: current directory.*/
        @Parameter(property="projectRoot")
        private String pRoot = System.getProperty("user.dir");
        public void setPRoot(String pr)
        {
                pRoot = pr;
        }

        /** Property to set publisher. Default: PUBLISHER_NAME.*/
        @Parameter(property="publisher")
        private String publisher = "PUBLISHER_NAME";
        public void setPublisher(String pub)
        {
                publisher = pub;
        }

        /** Property to set local IPS repository path. Default: null.*/
        @Parameter(property="localRepoPath")
        private String localRepoPath;
        public void setLocalRepoPath(String lrp){
                localRepoPath = lrp;
        }

        /** Property to set remote IPS repository path. Default: null.*/
        @Parameter(property="remoteRepoPath")
        private String remoteRepoPath;
        public void setRemoteRepoPath(String lrp){
                remoteRepoPath = lrp;
        }

        /** Property to set install directory. Default: /usr/local/java_apps.*/
        @Parameter(property="installDir")
        private String installDir="/usr/local/java_apps";
        public void setInstallDir(String dir)
        {
                installDir = dir;
        }

        /** Main execution method. */
        public void execute() throws MojoExecutionException
        {
                if(pRoot == null){
                        getLog().error("No project root is set for "
                                + "auto-config. please use -DprojectRoot "
                                + "to set the path of a project root.");
                        throw new MojoExecutionException("");
                }
                if(!Paths.get(pRoot).isAbsolute()){
                        pRoot = System.getProperty("user.dir") + FSEP
                            + pRoot;
                }
                String pomPath = pRoot + FSEP + "pom.xml";
                String oldPomPath = pRoot + FSEP + ".pom.xml.old";
                String usePkgCommand = "true";
                try {
                        if(!Files.exists(Paths.get("/usr/bin/pkgsend"))
                            || !Files.exists(Paths.get("/usr/bin/pkgmogrify"))
                            || !Files.exists(Paths.get("/usr/bin/pkgrepo")))
                        {
                                usePkgCommand = "false";
                        }
                        if(operation.equals("revert")){
                                if(Files.exists(Paths.get(oldPomPath))){
                                        Files.copy(Paths.get(oldPomPath),
                                            Paths.get(pomPath), MISC.copyOpt);
                                        Files.delete(Paths.get(oldPomPath));
                                }else{
                                        getLog().info("Nothing to revert");
                                }
                                return;
                        }
                        if(!Files.exists(Paths.get(oldPomPath))){
                                Files.copy(Paths.get(pomPath),
                                    Paths.get(oldPomPath), MISC.copyOpt);
                        }
                        SAXBuilder builder = new SAXBuilder();
                        File xmlFile = new File(pomPath);

                        Document doc = (Document) builder.build(xmlFile);
                        Element project = doc.getRootElement();
                        Namespace ns = project.getNamespace();
                        if(project == null){
                                throw new MojoExecutionException(String.format(
                                    "The pom file %s is invalid. \'project\' "
                                    + "tag is missing.", pomPath));
                        }
                        String artifactId = project.getChild("artifactId",
                            ns).getTextTrim();
                        String version = project.getChild("version",
                            ns).getTextTrim();
                        String type = "jar";
                        if(project.getChild("packaging", ns) != null){
                                type = project.getChild("packaging",
                                    ns).getTextTrim();
                        }
                        String productName = artifactId + "-" + version + "."
                            + type;
                        Element build = project.getChild("build", ns);
                        if(build == null){
                                build = new Element("build", ns);
                                build.addContent(new Element("plugins", ns));
                                project.addContent(build);
                        }else{
                                Element plugins =
                                    project.getChild("build", ns).getChild(
                                    "plugins", ns);
                                if(plugins != null &&
                                    !plugins.getChildren().isEmpty()){
                                        Iterator itr =
                                            (plugins.getChildren()).iterator();
                                        while(itr.hasNext()){
                                            Element aplugin =
                                                (Element)itr.next();
                                            String artId = aplugin.getChild(
                                                "artifactId", ns).getTextTrim();
                                            if(artId.equals("ips-maven-plugin")
                                                ){
                                                    throw new
                                                    MojoExecutionException(
                                                        "The pom.xml "
                                                        + "already contains \'"
                                                        + "ips-maven-plugin. "
                                                        + "manual "
                                                        + "configuration or "
                                                        + "revert into the old "
                                                        + "pom.xml is "
                                                        + "recommended.");
                                            }
                                        }
                                }else{
                                        build.addContent(
                                            new Element("plugins", ns));
                                }
                        }
                        Element plugins =
                            project.getChild("build", ns).getChild("plugins",
                                ns);

                        Element plugin = new Element("plugin", ns);
                        plugin.addContent(new Element("groupId", ns).setText(
                            "com.oracle.ips"));
                        plugin.addContent(new Element("artifactId", ns).setText(
                            "ips-maven-plugin"));
                        plugin.addContent(new Element("version", ns).setText(
                            "1.0-alpha-1"));

                        Element configuration = new Element(
                            "configuration", ns);

                        configuration.addContent(new Element(
                            "projectRoot", ns).setText("${basedir}"));
                        configuration.addContent(new Element(
                            "pkgName", ns).setText("PKG_NAME"));
                        configuration.addContent(new Element(
                            "publisher", ns).setText(publisher));
                        String ipsVersion = version;
                        if(version.contains("-")){
                                ipsVersion = version.split("-")[0];
                        }
                        configuration.addContent(new Element(
                            "version", ns).setText(ipsVersion));
                        configuration.addContent(new Element(
                            "projectSummary", ns).setText("Project summary "
                            + "text goes here!"));
                        configuration.addContent(new Element(
                            "projectDescription", ns).setText(
                            "Project description text goes here!"));
                        plugin.addContent(configuration);

                        Element executions = new Element("executions", ns);
                        Element execution =
                            new Element("execution", ns).addContent(
                            new Element("id", ns).setText("ips-packager"));
                        Element packConfigurations =
                            new Element("configuration", ns);
                        Element mappings = new Element("mappings", ns);
                        Element mappingInstall = new Element("mapping", ns);
                        mappingInstall.addContent(
                            new Element("directory", ns).setText(installDir
                            + FSEP +"bin"));
                        mappingInstall.addContent(
                            new Element("filemode", ns).setText("0755"));
                        mappingInstall.addContent(
                            new Element("username", ns).setText("root"));
                        mappingInstall.addContent(
                            new Element("groupname", ns).setText("bin"));
                        Element sourcesInstall = new Element("sources", ns);
                        sourcesInstall.addContent(
                            new Element("source", ns).addContent(
                                new Element("location", ns).setText(
                                "${project.build.directory}" + FSEP
                                + productName))
                            );
                        mappingInstall.addContent(sourcesInstall);
                        mappings.addContent(mappingInstall);

                        Element mappingDep = new Element("mapping", ns);
                        mappingDep.addContent(
                            new Element("directory", ns).setText(installDir
                            + FSEP + "lib"));
                        mappingDep.addContent(
                            new Element("filemode", ns).setText("0755"));
                        mappingDep.addContent(
                            new Element("username", ns).setText("root"));
                        mappingDep.addContent(
                            new Element("groupname", ns).setText("bin"));
                        mappingDep.addContent(new Element("dep", ns).addContent(
                            new Element("includeProjectDep", ns).setText(
                            "true")));
                        mappings.addContent(mappingDep);

                        packConfigurations.addContent(mappings);
                        execution.addContent(packConfigurations);
                        execution.addContent(new Element("phase", ns).setText(
                            "package"));
                        Element goals = new Element("goals", ns);
                        goals.addContent(new Element("goal", ns).setText(
                            "packager"));
                        execution.addContent(goals);
                        executions.addContent(execution);
                        if(operation.equals("install") || operation.equals(
                            "all")){
                                if(usePkgCommand.equals("false")){
                                        getLog().warn("PKG5 commands are not "
                                            + "available. \'installer\' goal "
                                            + "will not be attached");
                                }else{
                                        execution = new Element("execution",
                                            ns);
                                        execution.addContent(
                                            new Element("id", ns).setText(
                                            "ips-install"));
                                        Element installConfiguration =
                                            new Element("configuration", ns);
                                        if(localRepoPath == null){
                                                localRepoPath = pRoot
                                                    + FSEP + "ips_local_repo";
                                        }
                                        if(!Files.exists(Paths.get(
                                            localRepoPath))){
                                                String[] comm = {"/bin/sh",
                                                    "-c", String.format(
                                                    "/usr/bin/pkgrepo create "
                                                    + "%s", localRepoPath)};
                                            MISC.commandline_run(comm);
                                        }
                                        installConfiguration.addContent(
                                            new Element(
                                            "localRepoPath", ns).setText(
                                            localRepoPath));

                                        execution.addContent(
                                            installConfiguration);
                                        execution.addContent(new Element(
                                            "phase", ns).setText("install"));
                                        goals = new Element("goals", ns);
                                        goals.addContent(
                                            new Element("goal", ns).setText(
                                            "installer"));
                                        execution.addContent(goals);
                                        executions.addContent(execution);
                                }
                        }
                        if(operation.equals("deploy") ||
                            operation.equals("all")){
                                if(usePkgCommand.equals("false")){
                                        getLog().warn("pkg commands are not "
                                            + "available. \'deployer\' goal "
                                            + "will not be attached");
                                }else{
                                        execution = new Element("execution",
                                            ns);
                                        execution.addContent(
                                            new Element("id", ns).setText(
                                            "ips-deployer"));
                                        Element deployConfiguration =
                                            new Element("configuration", ns);
                                        if(remoteRepoPath == null){
                                                remoteRepoPath =
                                                    "to be configured";
                                        }
                                        deployConfiguration.addContent(
                                            new Element("remoteRepoPath"
                                            , ns).setText(remoteRepoPath));
                                        execution.addContent(
                                            deployConfiguration);
                                        execution.addContent(new Element(
                                            "phase", ns).setText("deploy"));
                                        goals = new Element("goals", ns);
                                        goals.addContent(new Element(
                                            "goal", ns).setText("deployer"));
                                        execution.addContent(goals);
                                        executions.addContent(execution);
                                }
                        }
                        plugin.addContent(executions);
                        plugins.addContent(plugin);
                        XMLOutputter xmlOutput = new XMLOutputter();

                        xmlOutput.setFormat(Format.getPrettyFormat());

                        xmlOutput.output(doc, new FileWriter(pomPath));
                }catch (IOException io) {
                        throw new MojoExecutionException(io.getMessage());
                }catch (JDOMException e) {
                        throw new MojoExecutionException(e.getMessage());
                }
        }
}
