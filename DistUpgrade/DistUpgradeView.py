# DistUpgradeView.py 
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

from gettext import gettext as _
import subprocess
import apt
import os

from DistUpgradeApport import *


def FuzzyTimeToStr(sec):
  " return the time a bit fuzzy (no seconds if time > 60 secs "
  if sec > 60*60*24:
    return _("%li days %li hours %li minutes") % (sec/60/60/24, (sec/60/60) % 24, (sec/60) % 60)
  if sec > 60*60:
    return _("%li hours %li minutes") % (sec/60/60, (sec/60) % 60)
  if sec > 60:
    return _("%li minutes") % (sec/60)
  return _("%li seconds") % sec


class FetchProgress(apt.progress.FetchProgress):
  def __init__(self):
    apt.progress.FetchProgress.__init__(self)
    self.est_speed = 0
  def pulse(self):
    apt.progress.FetchProgress.pulse(self)
    if self.currentCPS > self.est_speed:
      self.est_speed = (self.est_speed+self.currentCPS)/2.0
  def estimatedDownloadTime(self, requiredDownload):
    """ get the estimated download time """
    if self.est_speed == 0:
      timeModem = requiredDownload/(56*1024/8)  # 56 kbit 
      timeDSL = requiredDownload/(1024*1024/8)  # 1Mbit = 1024 kbit
      s= _("This download will take about %s with a 1Mbit DSL connection "
           "and about %s with a 56k modem" % (FuzzyTimeToStr(timeDSL),FuzzyTimeToStr(timeModem)))
      return s
    # if we have a estimated speed, use it
    s = _("This download will take about %s with your connection. " %
          FuzzyTimeToStr(requiredDownload/self.est_speed))
    return s
    


class InstallProgress(apt.progress.InstallProgress):
  """ Base class for InstallProgress that supports some fancy
      stuff like apport integration
  """
  def __init__(self):
    apt.progress.InstallProgress.__init__(self)
    self.pkg_failures = 0

  def startUpdate(self):
    # apache: workaround #95325 (edgy->feisty)
    # pango-libthai #103384 (edgy->feisty)
    bad_scripts = ["/var/lib/dpkg/info/apache2-common.prerm",
                   "/var/lib/dpkg/info/pango-libthai.postrm",
                   ]
    for ap in bad_scripts:
      if os.path.exists(ap):
        logging.debug("removing bad script '%s'" % ap)
        os.unlink(ap)
        
  def error(self, pkg, errormsg):
    " install error from a package "
    apt.progress.InstallProgress.error(self, pkg, errormsg)
    logging.error("got an error from dpkg for pkg: '%s': '%s'" % (pkg, errormsg))
    self.pkg_failures += 1
    if "/" in pkg:
      pkg = os.path.basename(pkg)
    if "_" in pkg:
      pkg = pkg.split("_")[0]
    # now run apport
    apport_pkgfailure(pkg, errormsg)

class DumbTerminal(object):
    def call(self, cmd, hidden=False):
        " expects a command in the subprocess style (as a list) "
        import subprocess
        subprocess.call(cmd)


(STEP_PREPARE,
 STEP_MODIFY_SOURCES,
 STEP_FETCH,
 STEP_INSTALL,
 STEP_CLEANUP,
 STEP_REBOOT) = range(1,7)

class DistUpgradeView(object):
    " abstraction for the upgrade view "
    def __init__(self):
        pass
    def getOpCacheProgress(self):
        " return a OpProgress() subclass for the given graphic"
        return apt.progress.OpProgress()
    def getFetchProgress(self):
        " return a fetch progress object "
        return apt.progress.FetchProgress()
    def getInstallProgress(self, cache=None):
        " return a install progress object "
        return apt.progress.InstallProgress(cache)
    def getTerminal(self):
        return DumbTerminal()
    def updateStatus(self, msg):
        """ update the current status of the distUpgrade based
            on the current view
        """
        pass
    def abort(self):
        """ provide a visual feedback that the upgrade was aborted """
        pass
    def setStep(self, step):
        """ we have 6 steps current for a upgrade:
        1. Analyzing the system
        2. Updating repository information
        3. fetch packages
        3. Performing the upgrade
        4. Post upgrade stuff
        5. Complete
        """
        pass
    def hideStep(self, step):
        " hide a certain step from the GUI "
        pass
    def confirmChanges(self, summary, changes, downloadSize,
                       actions=None, removal_bold=True):
        """ display the list of changed packages (apt.Package) and
            return if the user confirms them
        """
        self.toInstall = []
        self.toUpgrade = []
        self.toRemove = []
        self.toDowngrade = []
        for pkg in changes:
            if pkg.markedInstall: self.toInstall.append(pkg.name)
            elif pkg.markedUpgrade: self.toUpgrade.append(pkg.name)
            elif pkg.markedDelete: self.toRemove.append(pkg.name)
            elif pkg.markedDowngrade: self.toDowngrade.append(pkg.name)
        # sort it
        self.toInstall.sort()
        self.toUpgrade.sort()
        self.toRemove.sort()
        self.toDowngrade.sort()
        # no re-installs 
        assert(len(self.toInstall)+len(self.toUpgrade)+len(self.toRemove)+len(self.toDowngrade) == len(changes))
    def askYesNoQuestion(self, summary, msg, default='No'):
        " ask a Yes/No question and return True on 'Yes' "
        pass
    def confirmRestart(self):
        " generic ask about the restart, can be overriden "
        summary = _("Reboot required")
        msg =  _("The upgrade is finished and "
                 "a reboot is required. "
                 "Do you want to do this "
                 "now?")
        return self.askYesNoQuestion(summary, msg)
    def error(self, summary, msg, extended_msg=None):
        " display a error "
        pass
    def information(self, summary, msg, extended_msg=None):
        " display a information msg"
        pass
    def processEvents(self):
        """ process gui events (to keep the gui alive during a long
            computation """
        pass

if __name__ == "__main__":
  fp = FetchProgress()
  fp.pulse()
