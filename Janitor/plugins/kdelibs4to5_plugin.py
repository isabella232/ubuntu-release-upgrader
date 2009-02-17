# kdelibs4to5_plugin.py - install kdelibs5-dev if kdeblibs4-dev is installed
# Copyright (C) 2009  Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import computerjanitor
_ = computerjanitor.setup_gettext()


class Kdelibs4devToKdelibs5devPlugin(computerjanitor.Plugin):

    """Plugin to install kdelibs5-dev if kdelibs4-dev is installed.
    
    See also LP: #279621.
    
    """

    def get_cruft(self):
        fromp = "kdelibs4-dev"
        to = "kdelibs5-dev"
        cache = self.app.apt_cache
        if (fromp in cache and cache[fromp].isInstalled and
            to in cache and not cache[to].isInstalled):
                yield computerjanitor.MissingPackageCruft(cache[to],
                        _("When upgrading, if kdelibs4-dev is installed, "
                          "kdelibs5-dev needs to be installed to. See "
                          "bugs.launchpad.net, bug ##279621 for details."))
