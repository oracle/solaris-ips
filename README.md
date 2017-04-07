# Solaris Image Packaging System

## Introduction

Image Packaging System (IPS) is an integrated solution to manage system software lifecycle since Oracle Solaris 11. It relies on a network-centric and efficient approach with automatic software dependency checking and validation, and it builds on the foundation of ZFS as the default root file system. Using IPS, administrators can easily and reliably install or replicate an exact set of software package versions across many different client machines, and get a much clearer understanding of any differences between software versions installed on a system.


## Prerequisites

IPS developement requires a few of external dependency packages. The entire list can be found in src/pkg/external_deps.txt.


## Build, Testing and Deployment

Once all dependency packages are installed, IPS source can be built by the following command:
>       $ cd src; make install

The above will generate a proto directory under root directory. Inside proto directory, build_i386
directory contains python-version specific builds; root_i386 contains complete IPS build with
directory structure preserved.

Generally, testing of the new build can be done by the following command:
>       $cd src/tests; sudo ./run.py -j 8

The above will run all test cases in 8 parallel processes. Other options are
also available by typing ./run.py -h.

Tests running can also be done by using make:
>       $cd src; sudo make test;

Make targets: test-27 and test-34 are available for testing for different python versions.


IPS applications and libraries can be packaged and published into an IPS repository:
>       $cd src; make packages;

The above command generates IPS related packages and publish them into packages/i386/repo.

## Usage Examples

* Example 1 Create an Image With Publisher Configured

    Create a new, full image, with publisher example.com, stored at /aux0/example_root.

>         $ pkg image-create -F -p example.com=http://pkg.example.com:10000 \
>         /aux0/example_root

* Example 2 Create an Image With No Publisher Configured

    Create a new, full image with no publishers configured at /aux0/example_root.

>         $ pkg image-create -F /aux0/example_root

* Example 3 Install a Package

    Install the latest version of the widget package in the current image.

>         $ pkg install application/widget

* Example 4 Add a Publisher

    Add a new publisher example.com, with a repository located at http://www.example.com/repo.

>         $ pkg set-publisher -g http://www.example.com/repo example.com

* Example 5 Add and Automatically Configure a Publisher

    Add a new publisher with a repository located at /export/repo using automatic configuration.

>         $ pkg set-publisher -p /export/repo

For more examples, please refer to List of References or main page section pkg(1) on Solaris operating system.

## How to Contribute

Please refer to CONTRIBUTING.md file


## List of References

1. [Packaging and Delivering Software With the Image Packaging System in Oracle® Solaris 11.2](https://docs.oracle.com/cd/E36784_01/html/E36856/)
2. [Introducing the Basics of Image Packaging System (IPS) on Oracle Solaris 11](http://www.oracle.com/technetwork/articles/servers-storage-admin/o11-083-ips-basics-523756.html)
3. [Oracle Solaris 11 Cheatsheet for Image Packaging System](http://www.oracle.com/technetwork/server-storage/solaris11/documentation/ips-one-liners-032011-337775.pdf)


