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
        sys.exit(1)
try:
        import gtk
        import gtk.glade
        import gobject
except:
        sys.exit(1)

import pkg.client.bootenv as bootenv
import pkg.client.imageplan as imageplan
import pkg.client.pkgplan as pkgplan
import pkg.client.progress as progress
import pkg.search_errors as search_errors
import pkg.client.retrieve as retrieve
from pkg.misc import TransferTimedOutException
import pkg.gui.enumerations as enumerations
import pkg.gui.filelist as filelist
import pkg.fmri as fmri
import pkg.gui.thread as guithread
from pkg.gui.filelist import CancelException

class InstallUpdate(progress.ProgressTracker):
        def __init__(self, install_list, parent, image_update = False):
                progress.ProgressTracker.__init__(self)
                self.gui_thread = guithread.ThreadRun()
                self.install_list = install_list
                self.parent = parent
                self.image_update = image_update
                self.gladefile = parent.gladefile
                self.create_plan_dialog_gui()
                self.create_installupdate_gui()
                self.create_downloaddialog_gui()
                self.create_installation_gui()
                self.create_network_down_gui()
                if not image_update:
                        list_of_packages = self.prepare_list_of_packages()
                else:
                        list_of_packages = install_list
                self.thread = Thread(target = self.plan_the_install_updateimage, args = (list_of_packages, ))
                self.thread.start()
                self.createplandialog.run()

        def update_createplan_progress(self, action):
                textiter = self.createplantextbuffer.get_end_iter()
                self.createplantextbuffer.insert(textiter, action)
                self.createplanprogress.pulse()

        def update_download_progress(self, cur_bytes, total_bytes):
                progress = float(cur_bytes)/total_bytes
                self.downloadprogress.set_fraction(progress)
                a = str(cur_bytes/1024)
                b = str(total_bytes/1024)
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

        def download_stage(self, rebuild=False):
                self.gui_thread.run()
                if not rebuild:
                        self.installupdatedialog.hide()
                if rebuild:
                        self.installingdialog.hide()
                self.downloadingfilesdialog.show()
                self.nfiles = 0
                self.nbytes = 0
                for package_plan in self.ip.pkg_plans:
                        if self.gui_thread.is_cancelled():
                                return
                        try:
                                self.preexecute(package_plan)
                        except TransferTimedOutException:
                                self.downloadingfilesdialog.hide()
                                self.networkdown.show()
                                return
                        except URLError, e:
                                #if e.reason[0] == 8:
                                self.downloadingfilesdialog.hide()
                                self.networkdown.show()
                                return
                        except CancelException:
                                self.downloadingfilesdialog.hide()
                                return

                self.ip.progtrack.download_done()
                self.downloadingfilesdialog.hide()

                try:
                        be = bootenv.BootEnv(self.ip.image.get_root())
                except RuntimeError:
                        be = bootenv.BootEnvNull(self.ip.image.get_root())

                if self.image_update:
                        be.init_image_recovery(self.ip.image)
                        if self.ip.image.is_liveroot():
                                return 1
                try:
                        self.installation_stage()
                        if self.image_update:
                                be.activate_image()
                        else:
                                be.activate_install_uninstall()
                        ret_code = 0
                except RuntimeError, e:
                        if self.image_update:
                                be.restore_image()
                        else:
                                be.restore_install_uninstall()
                        ret_code = 1
                except search_errors.InconsistentIndexException, e:
                        ret_code = 2
                except search_errors.PartialIndexingException, e:
                        ret_code = 2
                except search_errors.ProblematicPermissionsIndexException, e:
                        ret_code = 2
                except Exception, e:
                        if self.image_update:
                                be.restore_image()
                        else:
                                be.restore_install_uninstall()
                        self.ip.image.cleanup_downloads()
                        raise

                self.ip.image.cleanup_downloads()
                if ret_code == 0:
                        self.ip.image.cleanup_cached_content()
                elif ret_code == 2:
                        return_code = 0
                        return_code = self.rebuild_index()
                        if return_code == 1:
                                return
                        self.download_stage(True)
                                
        def rebuild_index(self, pargs):
                """pkg rebuild-index

                Forcibly rebuild the search indexes. Will remove existing indexes
                and build new ones from scratch."""
                quiet = False
                
                try:
                        self.ip.image.rebuild_search_index(self.ip.image.progtrack)
                except search_errors.InconsistentIndexException, iie:
                        return 1
                except search_errors.ProblematicPermissionsIndexException, ppie:
                        return 1

        def installation_stage(self):
                self.gui_thread.run()
                self.installingdialog.show()
                self.ip.state = imageplan.PREEXECUTED_OK

                if self.ip.nothingtodo():
                        self.ip.state = imageplan.EXECUTED_OK
                        self.ip.progtrack.actions_done()
                        return

                actions = [ (p, src, dest)
                            for p in self.ip.pkg_plans
                            for src, dest in p.gen_removal_actions()
                            ]

                actions.sort(key = lambda obj:obj[1], reverse=True)

                self.ip.progtrack.actions_set_goal("Removal Phase", len(actions))
                for p, src, dest in actions:
                        p.execute_removal(src, dest)
                        self.ip.progtrack.actions_add_progress()
                self.ip.progtrack.actions_done()

                # generate list of update actions, sort and execute

                update_actions = [ (p, src, dest)
                            for p in self.ip.pkg_plans
                            for src, dest in p.gen_update_actions()
                            ]

                install_actions = [ (p, src, dest)
                            for p in self.ip.pkg_plans
                            for src, dest in p.gen_install_actions()
                            ]

                # move any user/group actions into modify list to
                # permit package to add user/group and change existing
                # files to that user/group in a single update
                # iterate over copy since we're modify install_actions

                for a in install_actions[:]:
                        if a[2].name == "user" or a[2].name == "group":
                                update_actions.append(a)
                                install_actions.remove(a)

                update_actions.sort(key = lambda obj:obj[2])

                self.ip.progtrack.actions_set_goal("Update Phase", len(update_actions))

                for p, src, dest in update_actions:
                        p.execute_update(src, dest)
                        self.ip.progtrack.actions_add_progress()

                self.ip.progtrack.actions_done()

                # generate list of install actions, sort and execute

                install_actions.sort(key = lambda obj:obj[2])

                self.ip.progtrack.actions_set_goal("Install Phase", len(install_actions))

                for p, src, dest in install_actions:
                        p.execute_install(src, dest)
                        self.ip.progtrack.actions_add_progress()
                self.ip.progtrack.actions_done()

                # handle any postexecute operations

                for p in self.ip.pkg_plans:
                        p.postexecute()

                self.ip.state = imageplan.EXECUTED_OK

        def actions_done(self):
                if self.parent != None:
                        gobject.idle_add(self.update_package_list)
                gobject.idle_add(self.installingdialog.hide)

        def update_package_list(self):
                for pkg in self.ip.pkg_plans:
                        pkg_name = pkg.get_xfername()
                        self.update_install_list(pkg_name)
                self.parent.update_package_list()
                        
        def update_install_list(self, pkg_name):
                for row in self.install_list:
                        if row[enumerations.NAME_COLUMN] == pkg_name:
                                row[enumerations.MARK_COLUMN] = True
                                return
	  
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
                verbose = False
                noexecute = False
                for image in list_of_packages:
                        # Take a list of packages, specified in pkg_list, and attempt
                        # to assemble an appropriate image plan.  This is a helper
                        # routine for some common operations in the client.
                        #
                        # This method checks all authorities for a package match;
                        # however, it defaults to choosing the preferred authority
                        # when an ambiguous package name is specified.  If the user
                        # wishes to install a package from a non-preferred authority,
                        # the full FMRI that contains an authority should be used
                        # to name the package.

                        pkg_list = list_of_packages.get(image)

                        error = 0
                        self.ip = imageplan.ImagePlan(image, self, filters = filters)

                        self.load_optional_dependencies(image)

                        for p in pkg_list:
                                try:
                                        conp = image.apply_optional_dependencies(p)
                                        matches = list(image.inventory([ conp ],
                                            all_known = True))
                                except RuntimeError:
                                        # XXX Module directly printing.
                                        error = 1
                                        continue

                                pnames = {}
                                pmatch = []
                                npnames = {}
                                npmatch = []
                                for m, state in matches:
                                        if m.preferred_authority():
                                                pnames[m.get_pkg_stem()] = 1
                                                pmatch.append(m)
                                        else:
                                                npnames[m.get_pkg_stem()] = 1
                                                npmatch.append(m)

                                if len(pnames.keys()) > 1:
                                        # XXX Module directly printing.
                                        error = 1
                                        continue
                                elif len(pnames.keys()) < 1 and len(npnames.keys()) > 1:
                                        # XXX Module directly printing.
                                        error = 1
                                        continue

                                # matches is a list reverse sorted by version, so take
                                # the first; i.e., the latest.
                                if len(pmatch) > 0:
                                        self.ip.propose_fmri(pmatch[0])
                                else:
                                        self.ip.propose_fmri(npmatch[0])

                        if error != 0:
                                raise RuntimeError, "Unable to assemble image plan"


                        self.evaluate(image)

                return


        def evaluate(self, image):
                assert self.ip.state == imageplan.UNEVALUATED

                self.ip.progtrack.evaluate_start()

                outstring = ""
                
                # Operate on a copy, as it will be modified in flight.
                for f in self.ip.target_fmris[:]:
                        self.ip.progtrack.evaluate_progress()
                        try:
                                self.evaluate_fmri(f, image)
                        except KeyError, e:
                                outstring += "Attemping to install %s causes:\n\t%s\n" % \
                                    (f.get_name(), e)
                        except NameError:
                                gobject.idle_add(self.creating_plan_net_error)
                                return
                if outstring:
                        raise RuntimeError("No packages were installed because "
                            "package dependencies could not be satisfied\n" +
                            outstring)                        
                                
                for f in self.ip.target_fmris:
                        self.ip.add_pkg_plan(f)
                        self.ip.progtrack.evaluate_progress()

                for f in self.ip.target_rem_fmris[:]:
                        self.ip.evaluate_fmri_removal(f)
                        self.ip.progtrack.evaluate_progress()

                self.ip.progtrack.evaluate_done()

                self.ip.state = imageplan.EVALUATED_OK

                gobject.idle_add(self.ip.progtrack.evaluate_done)

        def evaluate_fmri(self, pfmri, image):

                if self.gui_thread.is_cancelled():
                        return
                gobject.idle_add(self.update_createplan_progress, self.parent._("Evaluating: %s\n") % pfmri.get_fmri())

                self.ip.progtrack.evaluate_progress()
                m = image.get_manifest(pfmri)

                # [manifest] examine manifest for dependencies
                for a in m.actions:
                        if a.name != "depend":
                                continue

                        type = a.attrs["type"]

                        f = fmri.PkgFmri(a.attrs["fmri"],
                            self.ip.image.attrs["Build-Release"])

                        if self.ip.image.has_version_installed(f) and \
                                    type != "exclude":
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
                        if type == "optional" and \
                            not self.ip.image.attrs["Policy-Require-Optional"]:
                                required = False
                        elif type == "transfer" and \
                            not self.ip.image.older_version_installed(f):
                                required = False
                        elif type == "exclude":
                                excluded = True
                        elif type == "incorporate":
                                self.ip.image.update_optional_dependency(f)
                                if self.ip.image.older_version_installed(f) or \
                                    self.ip.older_version_proposed(f):
                                        required = True
                                else:
                                        required = False

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

                        # This will be the newest version of the specified
                        # dependency package, coming from the preferred
                        # authority, if it's available there.
                        cf = self.ip.image.inventory([ a.attrs["fmri"] ],
                            all_known = True, preferred = True,
                            first_only = True).next()[0]

                        # XXX LOG "adding dependency %s" % pfmri

                        #msg("adding dependency %s" % cf)

                        self.ip.propose_fmri(cf)
                        self.evaluate_fmri(cf, image)

        def load_optional_dependencies(self, image):
                for fmri in image.gen_installed_pkgs():
                        if self.gui_thread.is_cancelled():
                                return
                        mfst = image.get_manifest(fmri, filtered = True)

                        for dep in mfst.gen_actions_by_type("depend"):
                                required, min_fmri, max_fmri = dep.parse(image)
                                if required == False:
                                        image.update_optional_dependency(min_fmri)

        def creating_plan_net_error(self):
                self.createplandialog.hide()
                self.networkdown.show()

        def preexecute(self, package_plan):
                flist = filelist.FileList(self,
                    package_plan.image,
                    package_plan.destination_fmri,
                    self.gui_thread,
                    maxbytes = None
                    )

                package_plan._PkgPlan__progtrack.download_start_pkg(package_plan.get_xfername())

                # retrieval step
                if package_plan.destination_fmri == None:
                        package_plan.image.remove_install_file(package_plan.origin_fmri)

                        try:
                                os.unlink("%s/pkg/%s/filters" % (
                                    package_plan.image.imgdir,
                                    package_plan.origin_fmri.get_dir_path()))
                        except EnvironmentError, e:
                                if e.errno != errno.ENOENT:
                                        raise

                for src, dest in itertools.chain(*package_plan.actions):
                        if dest:
                                dest.preinstall(package_plan, src)
                                if dest.needsdata(src):
                                        flist.add_action(dest)
                        else:
                                src.preremove(package_plan)

                # Tell flist to get any remaining files
                flist.flush()
                package_plan._PkgPlan__progtrack.download_end_pkg()

        def act_output(self):
                return

        def act_output_done(self):
                return

        def cat_output_start(self): 
                return

        def cat_output_done(self): 
                return

        def ind_output(self):
                return

        def ind_output_done(self):
                return
                
        def ver_output(self): 
                return

        def ver_output_error(self, actname, errors): 
                return

        def eval_output_start(self):
                return

        def eval_output_progress(self):
                return

        def dl_output(self):
                gobject.idle_add(self.dl_output_idle, self.dl_cur_nbytes, self.dl_goal_nbytes)

                return
        def dl_output_idle(self, cur_nbytes, goal_nbytes):
                self.update_download_progress(cur_nbytes, goal_nbytes)

        def dl_output_done(self):
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
                npkgs = 0
                for package_plan in self.ip.pkg_plans:
                        npkgs += 1
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
                self.ip.progtrack.download_set_goal(npkgs, self.total_files_count, self.total_download_count)
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

