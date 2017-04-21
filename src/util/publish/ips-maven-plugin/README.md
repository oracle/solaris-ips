Copyright (c) 2015, 2017, Oracle and/or its affiliates. All rights reserved.

# User guide for ips-maven-plugin

## 1. Introduction.
Ips-maven-plugin is for converting maven based Java project deliverables into
IPS (Image Packaging System) style software package which can then be used
and managed with IPS. Ips-maven-plugin support both single-module or multi-module
maven project. For a multi-module project, we support build the entire project
as a whole and generating a single IPS package with a manifest including all
the products from the sub-modules.

## 2. Configuration.

### 2.1 Download and install maven.
Maven can be downloaded from http://maven.apache.org/download.cgi. Tested on
Maven version 3.3.3. Please use that version and following the install
instructions for different platforms. Current version also depends on
jdk1.7 above.

### 2.2 Install ips-maven-plugin with maven.
With ips-maven-plugin source code, User can run the following command under
ips-maven-plugin folder to install the ips-maven-plugin into local repository.

       $ mvn install

If user would like use a deployed version, there are two options: When running
as a side-effect, the plugin must be added into pom.xml of a project
as below (For details, please refer to sections 3, 5):

```xml
       <build>
           <plugins>
               <plugin>
                   <groupId>com.oracle.ips</groupId>
                   <artifactId>ips-maven-plugin</artifactId>
                   <version>REPLACE_WITH_THE_ACTUAL_VERSION</version>
                   ... configuration goes here
                   ... execution rules as well
                   ...
               </plugin>
           </plugins>
       </build>
```

When running standalone, the plugin will be downloaded from maven central,
and no installation necessary. However, for 'packager' goal, due to the
complexity of mapping rules, the configuration cannot be fully done using
command line options. As a result, user still need to add a plugin section
as above with mapping configurations. Note, the configuration section should
be right inside of <plugin> block. Otherwise, it will not take effect. This
is different from running the plugin as a side-effect. The latter one allows
not only plugin level configuration but also execution level configuration
which means <configuration> block can be right inside of <execution> block.
For more information, please see section 4.2 and section 5.

## 3. Run ips-maven-plugin as a side-effect.

Assume user did follow section 2.

User can configure ips-maven-plugin as side-effect in pom.xml of a project.
This means the plugin will be executed along with default maven phases such
as mvn package, mvn install and mvn deploy. User can include the following
section into pom.xml:

```xml
       <build>
           <plugins>
               <plugin>
                   <groupId>com.oracle.ips</groupId>
                   <artifactId>ips-maven-plugin</artifactId>
                   <version>REPLACE_WITH_THE_ACTUAL_VERSION</version>
                   <configuration>
                       <projectRoot>${basedir}</projectRoot>
                       <pkgName>${project.name}</pkgName>
                       <publisher>a publisher name</publisher>
                       <version>a numerical version number</version>
                       <projectSummary>project summary</projectSummary>
                       <projectDescription>project description
                       </projectDescription>
                   </configuration>
               </plugin>
            </plugins>
       </build>
```

${basedir} can be filled as the project root directory by maven.
${project.name} refers the project name.

Note that version should be numerical without leading zeros. 01.1, 1.01 and
0.1-SNAPSHOT are invalid version numbers. This is the IPS convention. Please
see https://docs.oracle.com/cd/E53394_01/html/E54820/pkgterms.html#PKDEVgludb
for details. Also version here only refer to the component version.
The release version will be automatic retrieve from the current system.
The branch version is always 0. User can manually change them. The timestamp
will be generated during publishing the package into local repository or
remote repository.

There are three goals user can configure in pom.xml, which are packager,
installer and deployer. For details, please see section 5.


## 4. Run ips-maven-plugin as standalone goals.

User should follow section 1 install ips-maven-plugin first or use a
deployed version.

### 4.1 User can also run goals of ips-maven-plugin on commandline.
The command format is:

           $ mvn group:artifact:goal

Currently the supported goals are autoconf, gradlepom, packager,
installer and deployer.

List of available goals as group:artifact:goal format:

           com.oracle.ips:ips-maven-plugin:autoconf
               [-DprojectRoot=<project root path>] -Doperation=<all, package,
               install, deploy, revert> [-DlocalRepoPath=<local repository
               path>] [-DremoteRepoPath=<a remote repository path>]
               [-DinstallDir=<a root install directory>]
               [-Dpublisher=<publisher>]

           com.oracle.ips:ips-maven-plugin:packager
               Currently only partially supported on command line. Configuration
               in pom.xml is recommended. Configuration about the file or
               directory mappings in pom.xml is compulsory for delivering file
               actions. Configuring the mappings is not supported as a command
               line option. Please see section 5 for examples. For special
               notes on multi-module project, please see section 4.2 for
               details.
               [-DprojectRoot=<project root path>] [-DpkgName=<package name>]
               [-Dpublisher=<publisher>] [-Dversion=<version>]
               [-DprojectSummary=<project summary>]
               [-DprojectDescription=<project description>]

           com.oracle.ips:ips-maven-plugin:installer
               [-DprojectRoot=<project root path>] [-DlocalRepoPath=<local
               repository path>] -Dpublisher=<publisher>

           com.oracle.ips:ips-maven-plugin:deployer
               [-DprojectRoot=<project root path>] -DremoteRepoPath=<a remote
               repository path> -dpublisher=<publisher>

           com.oracle.ips:ips-maven-plugin:gradlepom
               -DgradlePath=<gradle binary path> [-DprojectRoot<project root
               path>]


### 4.2 Detailed description

       [Goal name]

           com.oracle.ips:ips-maven-plugin:autoconf

       [Description]

           Automatically configure ips-maven-plugin and its goals as a
           side-effect for a project. The pom.xml file will be modified by
           attaching the plugin artifact and its goals in build environment
           section of the project. Which goal(s) will be attached is based
           on the the operation user specified. Whether the goal 'installer'
           and 'deployer' will be attached also depend on whether PKG5
           commands are available or not, because those goals need PKG5
           commands for execution. The original pom.xml will be stored as a
           hidden file named .pom.xml.old. User can use revert operation to
           go back this pom.xml.

       [Options]

           -DprojectRoot=<project root path>
               Specify the root path of the project. The default value is
               the current working directory.

           -Doperation=<all, package, install, deploy, revert>
               Specify which goal(s) will be attached to pom.xml of the
               project. The default value is package. -Doperation=package
               attaches only the 'packager' goal. -Doperation=all attaches
               'packager', 'installer' and 'deployer' goals. Since install
               and deploy phases are executed after package phase,
               -Doperation=install will attach goals 'packager' and
               'installer'. -Doperation=deploy will attach goals 'packager'
               and 'deployer'. -Doperation=revert reverts the modified
               pom.xml into the original one.

           -DlocalRepoPath=<local repository path>
               Specify the local repository path for 'installer' goal. The
               default value is <projectRoot>/ips_local_repo. If this
               repository does not exist, it will created if PKG5 commands
               are available in the current operating system. If PKG5
               commands are not available, the 'installer' goal will not be
               attached to pom.xml of the project.

           -DremoteRepoPath=<a remote repository path>
               Specify the remote repository path for 'deployer' goal. If
               not specified, the remote repository path will be empty.
               User can edit the modified pom.xml later on to add
               appropriate remote repository path.

           -DinstallDir=<a root install directory>
               Specify the root install directory for where to install the
               software. The default value is /usr/local/java_apps. By
               default, the software binary path will be
               /usr/local/java_apps/bin. The software dependency path will
               be /usr/local/java_apps/lib. Those are reflected in the
               mapping section of the 'package' goal. User can modify those
               paths in the modified pom.xml file.

           -Dpublisher=<publisher>
               Specify the publisher name. The default value is 'solaris'.

       [Goal name]

           com.oracle.ips:ips-maven-plugin:packager

       [Description]

           Generate a ips-like manifest named ips_manifest.p5m and a proto
           directory named ips_proto containing all files which will be
           installed according to the manifest. User should attach this goal
           to the package phase of the project and specify the mappings
           between source directories or files of the project and
           destination directories or files for installation. User should
           also specify direct dependencies as artifact coordinates in this
           section. This goal can be executed as a side-effect or executed on
           the command line based on the mappings configuration information in
           pom.xml. Missing mappings information cause this goal only generate
           the header of the ips manifest without directories or files
           actions information. For a sample pom.xml configuration, please see
           section 5.

           When running this goal as a standalone, the following section could
           be included into a project pom.xml to provide mappings (note the
           mapping in the example is right inside of <plugin> block):
```xml
           <build>
               <plugins>
                   <plugin>
                       <groupId>com.oracle.ips</groupId>
                       <artifactId>ips-maven-plugin</artifactId>
                       <version>REPLACE_WITH_THE_ACTUAL_VERSION</version>
                       <configuration>
                           <projectRoot>${basedir}</projectRoot>
                           <pkgName>${project.name}</pkgName>
                           <publisher>a publisher name</publisher>
                           <version>a numerical version number</version>
                           <projectSummary>project summary</projectSummary>
                           <projectDescription>project description
                           </projectDescription>
                           <mappings>
                               <mapping>
                                   <directory>/usr/local/bin</directory>
                                   <filemode>440</filemode>
                                   <username>root</username>
                                   <groupname>bin</groupname>
                                   <sources>
                                       <source>
                                           <location>target/classes</location>
                                       </source>
                                   </sources>
                               </mapping>
                           </mappings>
                       </configuration>
                   </plugin>
                </plugins>
           </build>
```

           For more mapping examples, please see section 5.

           For multi-module support, this plugin currently designates the last
           module in the build order to responsible for generating the
           ips_manifest.p5m file. If user uses <includeProjectDep> tab in the
           <dep> mapping section of the pom.xml configuration, The plugin will
           traverse each sub-module and dump all dependencies of that sub-module
           into the user specified directory using <directory> tab in the
           mapping. User can also benefit from the maven property variables like
           ${project.artifactId} to dump dependencies for each sub-module into 
           a different directory by substituting the ${project.artifactId}
           variable under each sub-module. However for all other files or
           directories. It is currently not supported for automatic dumping.
           User should specify mappings for each sub-module separately into to 
           deliver the directory or files into the correct locations in the
           ips_proto folder. For an example, please see section 5.5.

       [Options]

           -DprojectRoot=<project root path>
               Specify the root path of the project. The default value is
               the current working directory.

           -DpkgName=<package name>
               Specify the package name of the about-to-be-generated ips
               package. The default value is the current project artifact ID.

           -Dversion=<version>
               Specify the version number of the about-to-be-generated ips
               package.

           -DprojectSummary=<project summary>
               Specify the project summary for the about-to-be-generated ips
               package. The default value is 'none'.

           -DprojectDescription=<project description>
               Specify the project description for the about-to-be-generated
               ips package. The default value is 'none'.


       [Goal name]

           com.oracle.ips:ips-maven-plugin:installer

       [Description]

           Install generated ips like package into a local repository. This
           goal can only be executed if there are PKG5 commands available
           in the current operating system. This goal can be executed
           either on command line or as a side effect attached to install
           phase of the project.In order to be executed as a site-effect,
           User should configure pom.xml, please see section 5 for examples.

       [Options]

           -DprojectRoot=<project root path>
               Specify the root path of the project. The default value is the
               current working directory.

           -DlocalRepoPath=<local repository path>
               Specify the local repository path for this goal. The default
               value is <projectRoot>/ips_local_repo. If the repository
               specified does not exist, the plugin will report errors.

           -Dpublisher=<publisher>
               Specify the publisher name for this goal. If user does not
               specify it on command line and it is already configured in
               ips-maven-plugin configuration section in pom.xml. This goal
               will use that value.


       [Goal name]

           com.oracle.ips:ips-maven-plugin:deployer

       [Description]

           publish the generated ips package to the remote repository. This
           goal can only be executed if there are PKG5 commands available in
           the current operating system. This goal can be executed either on
           command line or as a side effect attached to deploy phase of the
           project. In order to be executed as a site-effect, User should
           configure pom.xml, please see section 5 for examples.

       [Options]

           -DprojectRoot=<project root path>
               Specify the root path of the project. The default value is the
               current working directory.

           -DremoteRepoPath=<local repository path>
               Specify the remote repository path for this goal.

           -Dpublisher=<publisher>
               Specify the publisher name for this goal. If user does not
               specify it on command line and it is already configured in
               ips-maven-plugin configuration section in pom.xml. This goal
               will use that value.


       [Goal name]

           com.oracle.ips:ips-maven-plugin:gradlepom

       [Description]

           Generate pom.xml for gradle project, so that other goals can work on
           the generated pom.xml.

       [Options]

           -DgradlePath=<gradle binary path>
               Specify the path of the gradle binary, since generating the
               pom.xml rely on gradle.

           -DprojectRoot=<project root path>
               Specify the root path of the project. The default value is the
               current working directory.


## 5. Examples.

### 5.1 Attach 'packager' goal as a side effect for execution.

Inside ips-maven-plugin section and after the configuration section, user
can attach executions as following: (note that the configuration section
in the execution section can only be recognized when running as a side
effect. If user wish to run standalone plugin goals, everything in the
following configuration section should be moved into plugin level
configuration.)

```xml
       <executions>
           <execution>
               <id>ips-packager</id>
               <configuration>
                   <mappings>
                       <mapping>
                           <directory>/usr/local/sbin/landfill</directory>
                           <filemode>440</filemode>
                           <username>root</username>
                           <groupname>bin</groupname>
                           <sources>
                               <source>
                                   <location>target/classes</location>
                               </source>
                           </sources>
                       </mapping>
                       <mapping>
                           <directory>/usr/local/lib</directory>
                           <filemode>750</filemode>
                           <username>root</username>
                           <groupname>sys</groupname>
                           <dep>
                               <includes>
                                   <include>jmock:jmock:1.2.0</include>
                                   <include>javax.servlet:servlet-api:2.4</include>
                               </includes>
                               <excludes>
                                    <exclude>junit:junit:2.0</exclude>
                               </excludes>
                               <includeProjectDep>true</includeProjectDep>
                           </dep>
                       </mapping>
                       <mapping>
                           <directory>/usr/local/sbin</directory>
                           <filemode>750</filemode>
                           <username>root</username>
                           <groupname>bin</groupname>
                           <sources>
                               <source>
                                   <location>target/application.jar</location>
                               </source>
                           </sources>
                       </mapping>
                       <mapping>
                          <directory>/usr/local/sbin/application.jar</directory>
                          <sources>
                            <softlinkSource>
                              <location>/usr/bin/symbolic_link_app.jar</location>
                            </softlinkSource>
                            <softlinkSource>
                              <location>/bin/symbolic_link_app.jar</location>
                            </softlinkSource>
                          </sources>
                       </mapping>
                   </mappings>
               </configuration>
               <phase>package</phase>
               <goals>
                   <goal>
                       packager
                   </goal>
               </goals>
           </execution>
       </executions>
```

The above configuration shows four different usages of mappings. The
first mapping section shows a mapping from one directory to another. The
source section is the source directory, the <directory> section is the
destination directory. In this case, every file in the source directory
'target/classes' relative to the current project root will be copied
into the destination directory '/usr/local/sbin/landfill'. Every file in
that directory will be installed with filemode, username and groupname
specified in the <filemode>, <username> and <groupname> section. If any
directory contains this directory before, the filemode, username and
groupname will be updated to current ones.

The second mapping shows a mapping of all project dependencies to the
destination directory. User can use <include> tab to include dependencies
to be distributed and use <exclude> tab to exclude any unwanted
dependencies. The format is groupId:artifactId:version:type. The type
can be omitted for default type 'jar'. The dependencies will have
filemode, username and groupname according to user's specifications.
<includeProjectDep> tab is a convenient way to include all project
dependencies listed in pom.xml. If user expects including the exact
dependencies listed in pom.xml, specifying true in <includeProjectDep>
is enough. User only need to use <include> or <exclude> tabs if more
dependencies are needed such as runtime dependencies not listed as
project dependencies.

The third mapping is to map a file into a directory. The file
'target/application.jar relative to the current project root will have
filemode, username and groupname specified in this section. If any
directory contains this file before, the filemode, username and
groupname will be updated to current ones.

The fourth one is a little bit interesting and may be confusing. It does
not copy files around but create a link action instead. A link action in
IPS delivers a symbolic link. Path in <directory> block is the actual
file we would like to create a link on. Path in <softlinkSource> will be
the symbolic link to be created. So the link actions will look like the
following in the generated ips manifest:
link path=usr/bin/symbolic_link_app.jar target=usr/local/sbin/application.jar
link path=bin/symbolic_link_app.jar target=usr/local/sbin/application.jar

So the above four cases are mostly used mapping rules. More mapping
rules will be added in future release versions.

### 5.2 Attach 'installer' goal as a side-effect for execution.
User can attach this goal right after the 'packager' goal. 'packager'
goal is a prerequisite for this goal. (note that the configuration
section in the execution section can only be recognized when running as
a side effect. If user wish to run standalone plugin goals, everything
in the following configuration section should be moved into plugin level
configuration.)

```xml
       <execution>
           <id>ips-install</id>
           <configuration>
               <localRepoPath>a_local_repo_path</localRepoPath>
           </configuration>
           <phase>install</phase>
           <goals>
               <goal>
                   installer
               </goal>
           </goals>
       </execution>
```

### 5.3 Attach 'deployer' goal as a side-effect for execution.
User can attach this goal right after the 'packager' goal. 'packager'
goal is a prerequisite for this goal. (note that the configuration
section in the execution section can only be recognized when running as
a side effect. If user wish to run standalone plugin goals, everything in
the following configuration section should be moved into plugin level
configuration.)

```xml
       <execution>
           <id>ips-deployer</id>
           <configuration>
               <remoteRepoPath>http://remote_repo_path</remoteRepoPath>
           </configuration>
           <phase>deploy</phase>
           <goals>
               <goal>
                   deployer
               </goal>
           </goals>
       </execution>
```

### 5.4 Complete configured pom.xml example.

```xml
       <project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/maven-v4_0_0.xsd">
           <modelVersion>4.0.0</modelVersion>
           <groupId>ips_system_test</groupId>
           <artifactId>ips_system_test</artifactId>
           <packaging>jar</packaging>
           <version>1.0-SNAPSHOT</version>
           <name>ips_system_test</name>
           <url>http://maven.apache.org</url>
           <build>
               <plugins>
                   <plugin>
                       <groupId>com.oracle.ips</groupId>
                       <artifactId>ips-maven-plugin</artifactId>
                       <version>REPLACE_WITH_THE_ACTUAL_VERSION</version>
                       <configuration>
                           <projectRoot>${basedir}</projectRoot>
                           <pkgName>${project.name}</pkgName>
                           <publisher>testdemo</publisher>
                           <version>1.0</version>
                           <projectSummary>${project.name}</projectSummary>
                           <projectDescription>${project.description}</projectDescription>
                       </configuration>
                       <executions>
                           <execution>
                               <id>ips-packager</id>
                               <configuration>
                                   <mappings>
                                       <mapping>
                                           <directory>/usr/local/sbin/landfill</directory>
                                           <filemode>440</filemode>
                                           <username>root</username>
                                           <groupname>bin</groupname>
                                           <sources>
                                               <source>
                                                   <location>target/classes</location>
                                               </source>
                                           </sources>
                                       </mapping>
                                       <mapping>
                                           <directory>/usr/local/lib</directory>
                                           <filemode>750</filemode>
                                           <username>root</username>
                                           <groupname>sys</groupname>
                                           <dep>
                                               <includes>
                                                   <include>jmock:jmock:1.2.0</include>
                                                   <include>javax.servlet:servlet-api:2.4</include>
                                               </includes>
                                               <excludes>
                                                   <exclude>junit:junit:2.0</exclude>
                                               </excludes>
                                               <includeProjectDep>true</includeProjectDep>
                                           </dep>
                                       </mapping>
                                       <mapping>
                                           <directory>/usr/local/sbin</directory>
                                           <filemode>750</filemode>
                                           <username>root</username>
                                           <groupname>bin</groupname>
                                           <sources>
                                               <source>
                                                   <location>target/ips_system_test-1.0-SNAPSHOT.jar</location>
                                               </source>
                                           </sources>
                                       </mapping>
                                   </mappings>
                               </configuration>
                               <phase>package</phase>
                               <goals>
                                   <goal>
                                       packager
                                   </goal>
                               </goals>
                           </execution>
                           <execution>
                               <id>ips-install</id>
                               <configuration>
                                   <localRepoPath>local_repo_path</localRepoPath>
                               </configuration>
                               <phase>install</phase>
                               <goals>
                                   <goal>
                                       installer
                                   </goal>
                               </goals>
                           </execution>
                           <execution>
                               <id>ips-deployer</id>
                               <configuration>
                                   <remoteRepoPath>http://remote_repo_path</remoteRepoPath>
                               </configuration>
                               <phase>deploy</phase>
                               <goals>
                                   <goal>
                                       deployer
                                   </goal>
                               </goals>
                           </execution>
                       </executions>
                   </plugin>
               </plugins>
           </build>
           <dependencies>
               <dependency>
                   <groupId>junit</groupId>
                   <artifactId>junit</artifactId>
                   <version>4.11</version>
               </dependency>
               <dependency>
                   <groupId>javax.servlet</groupId>
                   <artifactId>servlet-api</artifactId>
                   <version>2.4</version>
               </dependency>
           </dependencies>
       </project>
```

### 5.5 A multi-module mapping configuration example.
```xml
        <mappings>
                <mapping>
                    <directory>/tmp/bin/mod1</directory>
                    <filemode>0755</filemode>
                    <username>root</username>
                    <groupname>bin</groupname>
                    <sources>
                        <source>
                            <location>mod1/target/classes</location>
                        </source>
                    </sources>
                </mapping>
                <mapping>
                    <directory>/tmp/bin/mod2</directory>
                    <filemode>0755</filemode>
                    <username>root</username>
                    <groupname>bin</groupname>
                    <sources>
                        <source>
                            <location>mod2/target/classes</location>
                        </source>
                    </sources>
                </mapping>
                <mapping>
                    <directory>/tmp/lib/${project.artifactId}</directory>
                    <filemode>440</filemode>
                    <username>root</username>
                    <groupname>bin</groupname>
                    <dep>
                        <includeProjectDep>true</includeProjectDep>
                    </dep>
                </mapping>
        </mappings>
```

The first two mappings configure how the binaries of the two sub-modules
are distributed. The last mapping configure how the project dependencies
in each sub-module are distributed. The path in <directory> tab will be
substituted for each sub-module during the package phase. Please do not
use <include> or <exclude> tab in this mapping because other than project
dependencies, any extra dependencies specified in this mapping will be
delivered to the last sub-module packaged, because our plugin designate
the last module to copy file or directories, and ${project.artifactId}
will be substituted as the last sub-module's artifact ID. We will
possibly propose a better design or fix it in the later phase.
