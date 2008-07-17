#!/usr/bin/python2.4
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

import sys
import os
import itertools
import errno
from urllib2 import URLError
from threading import Thread
try:
        import pygtk
        pygtk.require("2.0")
except:
        pass
try:
        import gtk
        import gtk.glade
        import gobject
except:
        sys.exit(1)
import pkg.client.progress as progress
import pkg.gui.enumerations as enumerations
import pkg.client.imageplan as imageplan
import pkg.client.retrieve as retrieve
import pkg.gui.filelist as filelist
import pkg.fmri as fmri
import pkg.client.pkgplan as pkgplan
import pkg.gui.thread as guithread

class InstallUpdate(progress.ProgressTracker):
        def __init__(self, install_list, parent):
                progress.ProgressTracker.__init__(self)
                self.gui_thread = guithread.ThreadRun()
                self.install_list = install_list
                self.parent = parent
                self.gladefile = parent.gladefile
                self.create_plan_dialog_gui()
                self.create_installupdate_gui()
                self.create_downloaddialog_gui()
                self.create_installation_gui()
                self.create_network_down_gui()
                list_of_packages = self.prepare_list_of_packages()
                self.thread = Thread(target = self.plan_the_install_updateimage, args = (list_of_packages, ))
                self.thread.start()
                self.createplandialog.run()

        def update_createplan_progress(self, action):
                textiter = self.createplantextbuffer.get_end_iter()
                self.createplantextbuffer.insert(textiter, action)
                self.createplanprogress.pulse()

        def update_download_progress(self, nfiles, nbytes):
                progress = float(nbytes)/self.total_download_count
                self.downloadprogress.set_fraction(progress)
                a = str(nbytes/1024)
                b = str(self.total_download_count/1024)
                c = "Downloaded: " + a + " / " + b + " KB"
                self.downloadprogress.set_text(c)#str(int(progress*100)) + "%")

        def update_update_progress(self, current, total):
                progress = float(current)/total
                self.installingprogress.set_fraction(progress)

        def update_install_progress(self, current, total):
                progress = float(current)/total
                self.installingprogress.set_fraction(progress)

        def create_plan_dialog_gui(self):
                gladefile = self.gladefile
                wTreePlan = gtk.glade.XML(gladefile, "createplandialog") 
                self.createplandialog = wTreePlan.get_widget("createplandialog")
                self.createplantextview = wTreePlan.get_widget("createplantextview")
                self.createplanprogress = wTreePlan.get_widget("createplanprogress")
                self.createplantextbuffer = self.createplantextview.get_buffer()
                self.createplanprogress.set_pulse_step(0.1)
                try:
                        dic = \
                            {
                                "on_cancelcreateplan_clicked":self.on_cancelcreateplan_clicked,
                            }
                        wTreePlan.signal_autoconnect(dic)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s.\
                            Check create_plan_dialog_gui()')\
                            % error
                return

        def create_network_down_gui(self):
                gladefile = self.gladefile
                wTreePlan = gtk.glade.XML(gladefile, "networkdown") 
                self.networkdown = wTreePlan.get_widget("networkdown")
                try:
                        dic = \
                            {
                                "on_networkdown_close_clicked":self.on_networkdown_close_clicked,
                            }
                        wTreePlan.signal_autoconnect(dic)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s.\
                            Check create_network_down_gui()')\
                            % error
                return

        def create_installupdate_gui(self):
                gladefile = self.gladefile
                wTree = gtk.glade.XML(gladefile, "installupdate") 
                self.installupdatedialog = wTree.get_widget("installupdate")
                self.summary_label = wTree.get_widget("packagenamelabel3")
                self.warning_label = wTree.get_widget("label5")
                self.treeview = wTree.get_widget("treeview1")
                self.installed_updated_column = gtk.TreeViewColumn('Installed/Updated')
                self.treeview.append_column(self.installed_updated_column)
                self.cell = gtk.CellRendererText()
                self.installed_updated_column.pack_start(self.cell, True)
                self.installed_updated_column.add_attribute(self.cell, 'text', 0)
                self.treeview.expand_all()
                try:
                        dic = \
                            {
                                "on_cancel_button_clicked":self.on_cancel_button_clicked,
                                "on_next_button_clicked":self.on_next_button_clicked,
                            }
                        wTree.signal_autoconnect(dic)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s.Check create_installupdate_gui()')\
                            % error
                return

        def create_downloaddialog_gui(self):
                gladefile = self.gladefile
                wTree = gtk.glade.XML(gladefile, "downloadingfiles") 
                self.downloadingfilesdialog = wTree.get_widget("downloadingfiles")
                self.downloadtextview = wTree.get_widget("downloadtextview")
                self.downloadprogress = wTree.get_widget("downloadprogress")
                self.downloadtextbuffer = self.downloadtextview.get_buffer()
                try:
                        dic = \
                            {
                                "on_canceldownload_clicked":self.on_cancel_download_clicked,
                            }
                        wTree.signal_autoconnect(dic)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s.Check create_downloaddialog_gui()')\
                            % error
                return

        def create_installation_gui(self):
                gladefile = self.gladefile
                wTree = gtk.glade.XML(gladefile, "installingdialog") 
                self.installingdialog = wTree.get_widget("installingdialog")
                self.installingtextview = wTree.get_widget("installingtextview")
                self.installingprogress = wTree.get_widget("installingprogress")
                self.installingtextbuffer = self.installingtextview.get_buffer()
                return

        def on_cancel_download_clicked(self, widget):
                self.gui_thread.cancel()
                self.downloadingfilesdialog.destroy()

        def on_networkdown_close_clicked(self, widget):
                self.gui_thread.cancel()
                self.networkdown.destroy()

        def on_cancelcreateplan_clicked(self, widget):
                self.gui_thread.cancel()
                self.createplandialog.destroy()

        def on_cancel_button_clicked(self, widget):
                self.gui_thread.cancel()
                self.installupdatedialog.destroy()

        def on_next_button_clicked(self, widget):
                self.download_thread = Thread(target = self.download_stage, args = ())
                self.download_thread.start()

        def download_stage(self):
                self.gui_thread.run()
                self.installupdatedialog.hide()
                self.downloadingfilesdialog.show()
                self.nfiles = 0
                self.nbytes = 0
                for package_plan in self.ip.pkg_plans:
                        if self.gui_thread.is_cancelled():
                                return
                        try:
                                self.preexecute(package_plan)
                        except URLError, e:
                                #if e.reason[0] == 8:
                                self.downloadingfilesdialog.hide()
                                self.networkdown.show()
                                return
                if self.gui_thread.is_cancelled():
                        return
                self.downloadingfilesdialog.hide()
                self.installation_stage()

        def installation_stage(self):
                self.gui_thread.run()
                self.installingdialog.show()
                assert self.ip.state == imageplan.EVALUATED_OK
                # generate list of update actions, sort and execute
                actions_update = \
                    [ (p, src, dest)
                        for p in self.ip.pkg_plans
                        for src, dest in p.gen_update_actions()
                    ]
                actions_update.sort(key = lambda obj:obj[2])
                actions_install = \
                    [ (p, src, dest)
                        for p in self.ip.pkg_plans
                        for src, dest in p.gen_install_actions()
                    ]
                actions_install.sort(key = lambda obj:obj[2])
                progress = 0
                fmri = []
                total_progress = len(actions_update) + len(actions_install)
                for p, src, dest in actions_update:
                        if not p.destination_fmri in fmri:
                                gobject.idle_add(self.add_info_to_installtext, self.parent._("Updating:  ") + p.destination_fmri.get_name() + "\n")
                                fmri.append(p.destination_fmri)
                        progress = progress + 1
                        p.execute_update(src, dest)
                        gobject.idle_add(self.update_update_progress, progress, total_progress)
                # generate list of install actions, sort and execute
                for p, src, dest in actions_install:
                        if not p.destination_fmri in fmri:
                                gobject.idle_add(self.add_info_to_installtext, self.parent._("Installing:  ") + p.destination_fmri.get_name() + "\n")
                                fmri.append(p.destination_fmri)
                        progress = progress + 1
                        p.execute_install(src, dest)
                        gobject.idle_add(self.update_install_progress, progress, total_progress)
                self.ip.state = imageplan.EXECUTED_OK
                self.ip.image.cleanup_downloads()
                gobject.idle_add(self.postexecute, self.ip)

        def postexecute(self, ip):
                for p in ip.pkg_plans:
                        p.postexecute()
                self.actions_done()

        def actions_done(self):
                if self.parent != None:
                        self.parent.update_package_list()
                self.installingdialog.hide()

	  
        def prepare_list_of_packages(self):
                ''' This method return the dictionary of images and newest marked packages'''
                fmri_to_install_update = {}
                for row in self.install_list:
                        if row[enumerations.MARK_COLUMN]:
                                image = row[enumerations.IMAGE_OBJECT_COLUMN]
                                packages = row[enumerations.PACKAGE_OBJECT_COLUMN]
                                im = fmri_to_install_update.get(image)
                                if im:
                                        im.append(max(packages))
                                else:
                                        fmri_to_install_update[image] = [max(packages), ]
                return fmri_to_install_update

        def plan_the_install_updateimage(self, list_of_packages):
                '''Function which plans the image'''
                self.gui_thread.run()
                filters = []
                for image in list_of_packages:
                        self.ip = imageplan.ImagePlan(image, self, filters = filters)
                        fmris = list_of_packages.get(image)
                        for fmri in fmris:
                                if self.gui_thread.is_cancelled():
                                        return
                                self.ip.propose_fmri(fmri)
                        assert self.ip.state == imageplan.UNEVALUATED
                        self.ip.progtrack.evaluate_start()
                        for f in self.ip.target_fmris[:]:
                                try:
                                        self.evaluate_fmri(self.ip, f)
                                except NameError:
                                        gobject.idle_add(self.creating_plan_net_error)
                                        return
                        self.ip.state = imageplan.EVALUATED_OK
                        gobject.idle_add(self.ip.progtrack.evaluate_done)
                return  

        def creating_plan_net_error(self):
                self.createplandialog.hide()
                self.networkdown.show()

        def evaluate_fmri(self, ip, pfmri):
                if self.gui_thread.is_cancelled():
                        return
                gobject.idle_add(self.update_createplan_progress, self.parent._("Evaluating: %s\n") % pfmri.get_fmri())
                # [image] do we have this manifest?
                if not self.ip.image.has_manifest(pfmri):
                        retrieve.get_manifest(self.ip.image, pfmri)
                m = self.ip.image.get_manifest(pfmri)
                # [manifest] examine manifest for dependencies
                for a in m.actions:
                        if a.name != "depend":
                                continue
                        f = fmri.PkgFmri(a.attrs["fmri"],
                            self.ip.image.attrs["Build-Release"])
                        self.ip.image.fmri_set_default_authority(f)
                        if self.ip.image.has_version_installed(f):
                                continue
                        # XXX This alone only prevents infinite recursion when a
                        # cycle member is on the commandline, as we never update
                        # target_fmris.  Is target_fmris supposed to be just
                        # what was specified on the commandline, or include what
                        # we've found while processing dependencies?
                        # XXX probably should just use propose_fmri() here
                        # instead of this and the has_version_installed() call
                        # above.
                        if self.ip.is_proposed_fmri(f):
                                continue
                        # XXX LOG  "%s not in pending transaction;
                        # checking catalog" % f
                        required = True
                        excluded = False
                        if a.attrs["type"] == "optional" and \
                            not self.ip.image.attrs["Policy-Require-Optional"]:
                                required = False
                        elif a.attrs["type"] == "exclude":
                                excluded = True
                        if not required:
                                continue
                        if excluded:
                                raise RuntimeError, "excluded by '%s'" % f
                        # treat-as-required, treat-as-required-unless-pinned,
                        # ignore
                        # skip if ignoring
                        #     if pinned
                        #       ignore if treat-as-required-unless-pinned
                        #     else
                        #       **evaluation of incorporations**
                        #     [imageplan] pursue installation of this package
                        #     -->
                        #     backtrack or reset??
                        # XXX Do we want implicit freezing based on the portions
                        # of a version present?
                        mvs = self.ip.image.get_matching_fmris(a.attrs["fmri"])
                        # fmris in mvs are sorted with latest version first, so
                        # take the first entry.
                        cf = mvs[0]
                        # XXX LOG "adding dependency %s" % pfmri
                        self.ip.propose_fmri(cf)
                        self.evaluate_fmri(ip, cf)
                pp = pkgplan.PkgPlan(self.ip.image, self.ip.progtrack)
                try:
                        pp.propose_destination(pfmri, m)
                except RuntimeError:
                        print "pkg: %s already installed" % pfmri
                        return
                pp.evaluate(self.ip.filters)
                self.ip.pkg_plans.append(pp)

        def preexecute(self, package_plan):
                """Perform actions required prior to installation or removal of a package.
                This method executes each action's preremove() or preinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                flist = None
                flist_supported = True
                if flist_supported:
                        package_plan.progtrack.download_start_pkg(package_plan.get_xfername())
                # retrieval step
                if package_plan.destination_fmri == None:
                        package_plan.image.remove_install_file(package_plan.origin_fmri)
                        try:
                                os.unlink("%s/pkg/%s/filters" % (
                                    package_plan.image.imgdir,
                                    package_plan.origin_fmri.get_dir_path()))
                        except OSError, e:
                                if e.errno != errno.ENOENT:
                                        raise
                for src, dest in itertools.chain(*package_plan.actions):
                        if dest:
                                dest.preinstall(package_plan, src)
                        else:
                                src.preremove(package_plan)
                        if dest and dest.needsdata(src) and flist_supported:
                                if self.gui_thread.is_cancelled():
                                        package_plan.image.cleanup_downloads()
                                        return
                                if flist and flist.is_full():
                                        try:
                                                flist.get_files(self.gui_thread)
                                                if self.gui_thread.is_cancelled():
                                                        package_plan.image.cleanup_downloads()
                                                        return
                                                self.nfiles = self.nfiles + flist.get_nfiles()
                                                self.nbytes = self.nbytes + flist.get_nbytes()
                                                gobject.idle_add(self.update_download_progress, self.nfiles, self.nbytes)
                                        except filelist.FileListException:
                                                flist_supported = False
                                                flist = None
                                                continue
                                        flist = None
                                if flist is None:
                                        flist = filelist.FileList(
                                            self,
                                            package_plan.image,
                                            package_plan.destination_fmri
                                            )
                                flist.add_action(dest)
                # Get any remaining files
                if flist:
                        try:
                                flist.get_files(self.gui_thread)
                                if self.gui_thread.is_cancelled():
                                        package_plan.image.cleanup_downloads()
                                        return
                                self.nfiles = self.nfiles + flist.get_nfiles()
                                self.nbytes = self.nbytes + flist.get_nbytes()
                                gobject.idle_add(self.update_download_progress, self.nfiles, self.nbytes)
                        except filelist.FileListException:
                                pass
                        flist = None
                if flist_supported:
                        package_plan.progtrack.download_end_pkg()

        def act_output(self, force = False):
                return

        def act_output_done(self):
                return

        def eval_output_start(self):
                return

        def download_file_path(self, file_path):
                gobject.idle_add(self.add_file_to_downloadtext, file_path)

        def add_file_to_downloadtext(self, file_path):
                textiter = self.downloadtextbuffer.get_end_iter()
                self.downloadtextbuffer.insert(textiter, self.parent._("Downloading: ") + file_path + "\n")

        def add_info_to_installtext(self, text):
                textiter = self.installingtextbuffer.get_end_iter()
                self.installingtextbuffer.insert(textiter, text)

        def eval_output_done(self):
                self.createplandialog.hide()
                if self.gui_thread.is_cancelled(): #If the evaluation was cancelled, return
                        return
                updated_installed = \
                    [
                        ["Packages To Be Installed:"],
                        ["Packages To Be Updated:"]
                    ]
                self.treestore = gtk.TreeStore(str)
                install_iter = None 
                updated_iter = None
                install_count = 0
                updated_count = 0
                self.total_download_count = 0
                self.total_files_count = 0
                for package_plan in self.ip.pkg_plans:
                        if package_plan.origin_fmri and package_plan.destination_fmri:
                                if not updated_iter:
                                        updated_iter = self.treestore.append(None, updated_installed[1])
                                dt = self.get_datetime(package_plan.destination_fmri.version)
                                dt_str = (":%02d%02d") % (dt.month, dt.day)
                                pkg_version = package_plan.destination_fmri.version.get_short_version() + dt_str
                                pkg = package_plan.destination_fmri.get_name() + "@" + pkg_version
                                updated_count = updated_count + 1
                                self.treestore.append(updated_iter, [pkg])
                        elif package_plan.destination_fmri:
                                if not install_iter:
                                        install_iter = self.treestore.append(None, updated_installed[0])
                                dt = self.get_datetime(package_plan.destination_fmri.version)
                                dt_str = (":%02d%02d") % (dt.month, dt.day)
                                pkg_version = package_plan.destination_fmri.version.get_short_version() + dt_str
                                pkg = package_plan.destination_fmri.get_name() + "@" + pkg_version
                                install_count = install_count + 1
                                self.treestore.append(install_iter, [pkg])
                        xferfiles, xfersize = package_plan.get_xferstats()
                        self.total_download_count = self.total_download_count + xfersize
                        self.total_files_count = self.total_files_count + xferfiles
                self.treeview.set_model(self.treestore)
                self.treeview.expand_all()
                updated_str = self.parent._("%d packages will be updated\n")
                if updated_count == 1:
                        updated_str = self.parent._("%d package will be updated\n")
                install_str = self.parent._("%d packages will be installed\n\n")
                if install_count == 1:
                        install_str = self.parent._("%d package will be installed\n\n")
                self.summary_label.set_text((updated_str + install_str + 
                    self.parent._("%d MB will be downloaded"))%(updated_count, install_count,
                    (self.total_download_count/1024/1024)))
                self.createplandialog.hide()
                self.installupdatedialog.show()
                return True

        def get_datetime(self, version):
                dt = None
                try:
                        dt = version.get_datetime()
                except AttributeError:
                        dt = version.get_timestamp()
                return dt

