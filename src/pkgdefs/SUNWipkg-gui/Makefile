#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

MACH:sh = uname -p

ROOT = ../../../proto/root_$(MACH)
PKGARCHIVE = ../../../packages/$(MACH)

# by default create only the sysv package; failure of the IPS package to build
# may confuse without enlightening.
install: sysv-pkg

sysv-pkg: $(PKGARCHIVE) prototype
	pkgmk -a $(MACH) -o -r $(ROOT) -d $(PKGARCHIVE)

prototype: FRC
	rm -f prototype
	(cd $(ROOT); pkgproto .) | \
		nawk 'BEGIN { \
			print "i pkginfo"; \
			print "i copyright" \
		} \
		$$1 == "d" { \
			$$4 = "755" \
		} \
		$$1 == "f" { \
			$$4 = "444" \
		} \
		$$1 == "f" && $$3 ~ /bin\/packagemanager/ { \
			$$4 = "755" \
		} \
		{ \
			$$5 = "root"; \
			$$6 = "bin"; \
		} \
		$$3 ~ /(share(\/gnome|\/applications(\/packagemanager.desktop|\/addmoresoftware.desktop)|\/applications|\/icons|\/icons\/package\-manager|\/icons\/hicolor|\/icons\/hicolor\/48x48|\/icons\/hicolor\/48x48\/apps|\/icons\/hicolor\/48x48\/apps\/packagemanager.png|\/icons\/package\-manager(\/status_installed.png|\/status_checkmark.png|\/status_newupdate.png)))$$/ { \
			$$6 = "other"; \
		} \
		$$3 ~ /(share(\/gnome\/help\/package\-manager\/C|\/package\-manager|\/package\-manager\/data|\/package\-manager(\/packagemanager.glade|\/PM_app_48x.png|\/PM_package_36x.png|\/update_all24x.png|\/remove24x.png|\/reload24x.png|\/install_update24x.png|\/legend_installed.png|\/legend_newupdate.png|\/new_star_24x.png)))$$/ { \
			$$6 = "bin"; \
		} \
                $$3 ~ /^(usr(\/share)?|etc(\/gconf(\/schemas(\/packagemanager-preferences.schemas)?)?)?)$$/ { \
                        $$6 = "sys"; \
                } \
		$$3 ~ /^(usr(\/bin(\/packagemanager)?)?|usr(\/(lib(\/python2.4(\/vendor-packages(\/pkg(\/gui(\/installupdate.pyc|\/repository.py|\/repository.pyc|\/imageinfo.pyc|\/imageinfo.py|\/enumerations.pyc|\/enumerations.py|\/__init__.pyc|\/__init__.py|\/installupdate.py|\/beadmin.py|\/beadmin.pyc)?)?)?)?)?)?)?|usr(\/share(\/gnome(\/help(\/package-manager(\/C(\/figures\/package_manager.png|\/figures\/update_all.png|\/legal.xml|\/package-manager.xml)?)?)?)?)?)?|usr(\/share(\/package-manager(\/PM_app_48x.png|\/packagemanager.glade|\/update_all24x.png|\/install_update24x.png|\/PM_package_36x.png|\/reload24x.png|\/legend_installed.png|\/legend_newupdate.png|\/new_star_24x.png|\/remove24x.png)?)?)?|etc(\/gconf(\/schemas(\/packagemanager-preferences.schemas)?)?)?|usr(\/share(\/applications(\/packagemanager.desktop|\/addmoresoftware.desktop)?)?)?|usr(\/share(\/icons(\/hicolor(\/48x48(\/apps(\/packagemanager.png)?)?)?)?)?)?|usr(\/share(\/icons(\/package-manager(\/status_checkmark.png|\/status_installed.png|\/status_newupdate.png)?)?)?)?)$$/ { \
			print \
		}' > prototype

$(PKGARCHIVE):
	[ -d $(PKGARCHIVE) ] || mkdir -p $(PKGARCHIVE)

FRC:
