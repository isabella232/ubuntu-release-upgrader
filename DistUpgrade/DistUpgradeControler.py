# DistUpgradeControler.py 
#  
#  Copyright (c) 2004,2005 Canonical
#  
#  Author: Michael Vogt <michael.vogt@ubuntu.com>
# 
#  This program is free software; you can redistribute it and/or 
#  modify it under the terms of the GNU General Public License as 
#  published by the Free Software Foundation; either version 2 of the
#  License, or (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
#  USA


import apt
import apt_pkg
import sys
import os
import subprocess
import logging
import re
import statvfs
from DistUpgradeConfigParser import DistUpgradeConfig

from aptsources import SourcesList, SourceEntry, is_mirror
from gettext import gettext as _
from DistUpgradeCache import MyCache

            

class DistUpgradeControler(object):
    def __init__(self, distUpgradeView):
        self._view = distUpgradeView
        self._view.updateStatus(_("Reading cache"))
        self.cache = None

        self.config = DistUpgradeConfig()
        self.sources_backup_ext = "."+self.config.get("Files","BackupExt")
        
        # some constants here
        self.fromDist = self.config.get("Sources","From")
        self.toDist = self.config.get("Sources","To")
        self.origin = self.config.get("Sources","ValidOrigin")

        # forced obsoletes
        self.forced_obsoletes = self.config.getlist("Distro","ForcedObsoletes")

        # turn on debuging in the cache
        apt_pkg.Config.Set("Debug::pkgProblemResolver","true")
        fd = os.open("/var/log/dist-upgrade-apt.log",
                     os.O_RDWR|os.O_CREAT|os.O_TRUNC)
        os.dup2(fd,1)
        os.dup2(fd,2)

    def openCache(self):
        self.cache = MyCache(self._view.getOpCacheProgress())


    def rewriteSourcesList(self, mirror_check=True):
        logging.debug("rewriteSourcesList()")

        # this must map, i.e. second in "from" must be the second in "to"
        # (but they can be different, so in theory we could exchange
        #  component names here)
        fromDists = [self.fromDist,
                     self.fromDist+"-security",
                     self.fromDist+"-updates",
                     self.fromDist+"-backports"
                    ]
        toDists = [self.toDist,
                   self.toDist+"-security",
                   self.toDist+"-updates",
                   self.toDist+"-backports"
                   ]

        # list of valid mirrors that we can add
        valid_mirrors = self.config.getListFromFile("Sources","ValidMirrors")

        self.sources_disabled = False

        # look over the stuff we have
        foundToDist = False
        for entry in self.sources:
            # ignore invalid records (but update disabled ones)
            # or cdrom entries
            if entry.invalid or entry.uri.startswith("cdrom:") or entry.disabled:
                continue
            logging.debug("examining: '%s'" % entry)
            # check if it's a mirror (or offical site)
            validMirror = False
            for mirror in valid_mirrors:
                if not mirror_check or is_mirror(mirror,entry.uri):
                    validMirror = True
                    # security is a special case
                    res = not entry.uri.startswith("http://security.ubuntu.com") and not entry.disabled
                    if entry.dist in toDists:
                        # so the self.sources.list is already set to the new
                        # distro
                        logging.debug("entry '%s' is already set to new dist" % entry)
                        foundToDist |= res
                    elif entry.dist in fromDists:
                        foundToDist |= res
                        entry.dist = toDists[fromDists.index(entry.dist)]
                        logging.debug("entry '%s' updated to new dist" % entry)
                    else:
                        # disable all entries that are official but don't
                        # point to either "to" or "from" dist
                        entry.disabled = True
                        self.sources_disabled = True
                        logging.debug("entry '%s' was disabled (unknown dist)" % entry)
                    # it can only be one valid mirror, so we can break here
                    break
            # disable anything that is not from a official mirror
            if not validMirror:
                entry.disabled = True
                self.sources_disabled = True
                logging.debug("entry '%s' was disabled (unknown mirror)" % entry)
        return foundToDist

    def updateSourcesList(self):
        logging.debug("updateSourcesList()")
        self.sources = SourcesList()
        if not self.rewriteSourcesList(mirror_check=True):
            logging.error("No valid mirror found")
            res = self._view.askYesNoQuestion(_("No valid mirror found"),
                             _("While scaning your repository "
                               "information no mirror entry for "
                               "the upgrade was found."
                               "This cam happen if you run a internal "
                               "mirror or if the mirror information is "
                               "out of date.\n\n"
                               "Do you want to rewrite your "
                               "'sources.list' file anyway? If you choose "
                               "'Yes' here it will update all '%s' to '%s' "
                               "entries.\n"
                               "If you select 'no' the update will cancel."
                               ) % (self.fromDist, self.toDist))
            if res:
                # re-init the sources and try again
                self.sources = SourcesList()
                if not self.rewriteSourcesList(mirror_check=False):
                    #hm, still nothing useful ...
                    prim = _("Generate default sources?")
                    secon = _("After scanning your 'sources.list' no "
                              "valid entry for '%s' was found.\n\n"
                              "Should default entries for '%s' be "
                              "added? If you select 'No' the update "
                              "will cancel.") % (self.fromDist, self.toDist)
                    if not self._view.askYesNoQuestion(prim, secon):
                        self.abort()

                    # add some defaults here
                    # FIXME: find mirror here
                    uri = "http://archive.ubuntu.com/ubuntu"
                    comps = ["main","restricted"]
                    self.sources.add("deb", uri, self.toDist, comps)
                    self.sources.add("deb", uri, self.toDist+"-updates", comps)
                    self.sources.add("deb",
                                     "http://security.ubuntu.com/ubuntu/",
                                     self.toDist+"-security", comps)
            else:
                self.abort()
        
        # write (well, backup first ;) !
        self.sources.backup(self.sources_backup_ext)
        self.sources.save()

        # re-check if the written self.sources are valid, if not revert and
        # bail out
        # TODO: check if some main packages are still available or if we
        #       accidently shot them, if not, maybe offer to write a standard
        #       sources.list?
        try:
            sourceslist = apt_pkg.GetPkgSourceList()
            sourceslist.ReadMainList()
        except SystemError:
            logging.error("Repository information invalid after updating (we broke it!)")
            self._view.error(_("Repository information invalid"),
                             _("Upgrading the repository information "
                               "resulted in a invalid file. Please "
                               "report this as a bug."))
            return False

        if self.sources_disabled:
            self._view.information(_("Third party sources disabled"),
                             _("Some third party entries in your souces.list "
                               "where disabled. You can re-enable them "
                               "after the upgrade with the "
                               "'software-properties' tool or with synaptic."
                               ))
        return True

    def _logChanges(self):
        # debuging output
        logging.debug("About to apply the following changes")
        inst = []
        up = []
        rm = []
        for pkg in self.cache:
            if pkg.markedInstall: inst.append(pkg.name)
            elif pkg.markedUpgrade: up.append(pkg.name)
            elif pkg.markedDelete: rm.append(pkg.name)
        logging.debug("Remove: %s" % " ".join(rm))
        logging.debug("Install: %s" % " ".join(inst))
        logging.debug("Upgrade: %s" % " ".join(up))

    def doPreUpdate(self):
        # FIXME: check out what packages are downloadable etc to
        # compare the list after the update again
        self.obsolete_pkgs = self.cache._getObsoletesPkgs()
        self.foreign_pkgs = self.cache._getForeignPkgs(self.origin, self.fromDist, self.toDist)
        logging.debug("Foreign: %s" % " ".join(self.foreign_pkgs))
        logging.debug("Obsolete: %s" % " ".join(self.obsolete_pkgs))

    def doUpdate(self):
        self.cache._list.ReadMainList()
        progress = self._view.getFetchProgress()
        # FIXME: retry here too? just like the DoDistUpgrade?
        #        also remove all files from the lists partial dir!
        currentRetry = 0
        maxRetries = int(self.config.get("Network","MaxRetries"))
        while currentRetry < maxRetries:
            try:
                res = self.cache.update(progress)
            except IOError, e:
                logging.error("IOError in cache.update(): '%s'. Retrying (currentRetry: %s)" % (e,currentRetry))
                currentRetry += 1
                continue
            # no exception, so all was fine, we are done
            return True
                
        self._view.error(_("Error during update"),
                         _("A problem occured during the update. "
                           "This is usually some sort of network "
                           "problem, please check your network "
                           "connection and retry."), "%s" % e)
        return False


    def _checkFreeSpace(self):
        " this checks if we have enough free space on /var and /usr"
        err_sum = _("Not enough free disk space")
        err_long= _("The upgrade aborts now. "
                    "Please free at least %s of disk space on %s. "
                    "Empty your trash and remove temporary "
                    "packages of former installations using "
                    "'sudo apt-get clean'.")

        # first check for /var (or where the archives are downloaded too)
        archivedir = apt_pkg.Config.FindDir("Dir::Cache::archives")
        st_archivedir = os.statvfs(archivedir)
        free = st_archivedir[statvfs.F_BAVAIL]*st_archivedir[statvfs.F_FRSIZE]
        logging.debug("required download: %s " % self.cache.requiredDownload)
        logging.debug("free on %s: %s " % (archivedir, free))
        if self.cache.requiredDownload > free:
            free_at_least = apt_pkg.SizeToStr(self.cache.requiredDownload-free)
            self._view.error(err_sum, err_long % (free_at_least,archivedir))
            return False
        
        # then check for /usr assuming that all the data goes into /usr
        # this won't catch space problems when e.g. /boot,/usr/,/ are all
        # seperated partitions, but with a fragmented
        # patition layout we can't do a lot better because we don't know
        # the space-requirements on a per dir basis inside the deb without
        # looking into each
        logging.debug("need additional space: %s" % self.cache.additionalRequiredSpace)
        dir = "/usr"
        st_usr = os.statvfs(dir)
        if st_archivedir == st_usr:
            # we are on the same filesystem, so we need to take the space
            # for downloading the debs into account
            free -= self.cache.additionalRequiredSpace
            logging.debug("/usr on same fs as %s, taking dl-size into account, new free: %s" % (archivedir, free))
        else:
            free = st_usr[statvfs.F_BAVAIL]*st_usr[statvfs.F_FRSIZE]
            logging.debug("/usr on different fs than %s, free: %s" % (archivedir, free))

        if self.cache.additionalRequiredSpace > free:
            free_at_least = apt_pkg.SizeToStr(self.cache.additionalRequiredSpace-free)
            logging.error("not enough free space, we need addional %s" % free_at_least)
            self._view.error(err_sum, err_long % (free_at_least,dir))
            return False

        # FIXME: we should try to esitmate if "/" has enough free space,
        # linux-restricted-modules and linux-image- are both putting there
        # modules there and those take a lot of space
            
        return True

    def askDistUpgrade(self):
        if not self.cache.distUpgrade(self._view):
            return False
        changes = self.cache.getChanges()
        # log the changes for debuging
        self._logChanges()
        # check if we have enough free space 
        if not self._checkFreeSpace():
            return False
        # ask the user if he wants to do the changes
        res = self._view.confirmChanges(_("Do you want to start the upgrade?"),
                                        changes,
                                        self.cache.requiredDownload)
        return res

    def doDistUpgrade(self):
        currentRetry = 0
        fprogress = self._view.getFetchProgress()
        iprogress = self._view.getInstallProgress()
        # retry the fetching in case of errors
        maxRetries = int(self.config.get("Network","MaxRetries"))
        while currentRetry < maxRetries:
            try:
                res = self.cache.commit(fprogress,iprogress)
            except SystemError, e:
                # installing the packages failed, can't be retried
                self._view.getTerminal().call(["dpkg","--configure","-a"])
                self._view.error(_("Could not install the upgrades"),
                                 _("The upgrade aborts now. Your system "
                                   "can be in an unusable state. A recovery "
                                   "was run (dpkg --configure -a)."),
                                 "%s" % e)
                return False
            except IOError, e:
                # fetch failed, will be retried
                logging.error("IOError in cache.commit(): '%s'. Retrying (currentTry: %s)" % (e,currentRetry))
                currentRetry += 1
                continue
            # no exception, so all was fine, we are done
            return True
        
        # maximum fetch-retries reached without a successful commit
        logging.debug("giving up on fetching after maximum retries")
        self._view.error(_("Could not download the upgrades"),
                         _("The upgrade aborts now. Please check your "\
                           "internet connection or "\
                           "installation media and try again. "),
                           "%s" % e)
        # abort here because we want our sources.list back
        self.abort()



    def doPostUpgrade(self):
        self.openCache()
        # check out what packages are cruft now
        # use self.{foreign,obsolete}_pkgs here and see what changed
        now_obsolete = self.cache._getObsoletesPkgs()
        now_foreign = self.cache._getForeignPkgs(self.origin, self.fromDist, self.toDist)
        logging.debug("Obsolete: %s" % " ".join(now_obsolete))
        logging.debug("Foreign: %s" % " ".join(now_foreign))

        # now get the meta-pkg specific obsoletes and purges
        for pkg in self.config.getlist("Distro","MetaPkgs"):
            if self.cache.has_key(pkg) and self.cache[pkg].isInstalled:
                self.forced_obsoletes.extend(self.config.getlist(pkg,"ForcedObsoletes"))
        logging.debug("forced_obsoletes: %s", self.forced_obsoletes)

        # check what packages got demoted
        demotions_file = self.config.get("Distro","Demotions")
        demotions = set()
        if os.path.exists(demotions_file):
            map(lambda pkgname: demotions.add(pkgname.strip()),
                filter(lambda line: not line.startswith("#"),
                       open(demotions_file).readlines()))
        installed_demotions = filter(lambda pkg: pkg.isInstalled and pkg.name in demotions, self.cache)
        if len(installed_demotions) > 0:
            self._view.information(_("Some software no longer officially "
                                     "supported"),
                                   _("These installed packages are "
                                     "no longer officially supported, "
                                     "and are now only "
                                     "community-supported ('universe').\n\n"
                                     "If you don't have 'universe' enabled "
                                     "these packages will be suggested for "
                                     "removal in the next step. "),
                                   "\n".join([pkg.name for pkg in installed_demotions]))
       
        # mark packages that are now obsolete (and where not obsolete
        # before) to be deleted. make sure to not delete any foreign
        # (that is, not from ubuntu) packages
        remove_candidates = now_obsolete - self.obsolete_pkgs
        remove_candidates |= set(self.forced_obsoletes)
        logging.debug("remove_candidates: '%s'" % remove_candidates)
        logging.debug("Start checking for obsolete pkgs")
        for pkgname in remove_candidates:
            if pkgname not in self.foreign_pkgs:
                if not self.cache._tryMarkObsoleteForRemoval(pkgname, remove_candidates, self.foreign_pkgs):
                    logging.debug("'%s' scheduled for remove but not in remove_candiates, skipping", pkgname)
        logging.debug("Finish checking for obsolete pkgs")

        # get changes
        changes = self.cache.getChanges()
        logging.debug("The following packages are remove candidates: %s" % " ".join([pkg.name for pkg in changes]))
        summary = _("Remove obsolete packages?")
        actions = [_("_Skip This Step"), _("_Remove")]
        # FIXME Add an explanation about what obsolete pacages are
        #explanation = _("")
        if len(changes) > 0 and \
               self._view.confirmChanges(summary, changes, 0, actions):
            fprogress = self._view.getFetchProgress()
            iprogress = self._view.getInstallProgress()
            try:
                res = self.cache.commit(fprogress,iprogress)
            except (SystemError, IOError), e:
                self._view.error(_("Error during commit"),
                                 _("Some problem occured during the clean-up. "
                                   "Please see the below message for more "
                                   "information. "),
                                   "%s" % e)
            
    def abort(self):
        """ abort the upgrade, cleanup (as much as possible) """
        self.sources.restoreBackup(self.sources_backup_ext)
        # generate a new cache
        self._view.updateStatus(_("Restoring originale system state"))
        self.openCache()
        sys.exit(1)

    
    # this is the core
    def dapperUpgrade(self):
        # sanity check (check for ubuntu-desktop, brokenCache etc)
        self._view.updateStatus(_("Checking package manager"))
        self._view.setStep(1)

        self.openCache()
        if not self.cache.sanityCheck(self._view):
            abort(1)

        # run a "apt-get update" now
        if not self.doUpdate():
            sys.exit(1)

        # do pre-upgrade stuff (calc list of obsolete pkgs etc)
        self.doPreUpdate()

        # update sources.list
        self._view.setStep(2)
        self._view.updateStatus(_("Updating repository information"))
        if not self.updateSourcesList():
            self.abort()
        # then update the package index files
        if not self.doUpdate():
            self.abort()

        # then open the cache (again)
        self._view.updateStatus(_("Checking package manager"))
        self.openCache()
        # now check if we still have some key packages after the update
        # if not something went seriously wrong
        for pkg in self.config.getlist("Distro","BaseMetaPkgs"):
            if not self.cache.has_key(pkg):
                # FIXME: we could offer to add default source entries here,
                #        but we need to be careful to not duplicate them
                #        (i.e. the error here could be something else than
                #        missing sources entires but network errors etc)
                logging.error("No '%s' after sources.list rewrite+update")
                self._view.error(_("Invalid package information"),
                                 _("After your package information was "
                                   "updated the essential package '%s' can "
                                   "not be found anymore.\n"
                                   "This indicates a serious error, please "
                                   "report this as a bug.") % pkg)
                self.abort()

        # calc the dist-upgrade and see if the removals are ok/expected
        # do the dist-upgrade
        self._view.setStep(3)
        self._view.updateStatus(_("Asking for confirmation"))
        if not self.askDistUpgrade():
            self.abort()

        self._view.updateStatus(_("Upgrading"))            
        if not self.doDistUpgrade():
            # don't abort here, because it would restore the sources.list
            sys.exit(1) 
            
        # do post-upgrade stuff
        self._view.setStep(4)
        self._view.updateStatus(_("Searching for obsolete software"))
        self.doPostUpgrade()

        # done, ask for reboot
        self._view.setStep(5)
        self._view.updateStatus(_("System upgrade is complete."))            
        # FIXME should we look into /var/run/reboot-required here?
        if self._view.confirmRestart():
            subprocess.call(["reboot"])
        
    def run(self):
        self.dapperUpgrade()


