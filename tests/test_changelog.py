#!/usr/bin/python


import apt
import logging
import os
import os.path
import sys
import time
import unittest

sys.path.insert(0, "../")
from UpdateManager.Core.MyCache import MyCache


class TestChangelogs(unittest.TestCase):

    def setUp(self):
        self.cache = MyCache(apt.progress.base.OpProgress())

    def test_get_changelogs_uri(self):
        pkgname = "gcc"
        # test binary changelogs
        uri = self.cache._guess_third_party_changelogs_uri_by_binary(pkgname)
        pkg = self.cache[pkgname]
        self.assertEqual(uri,
                         pkg.candidate.uri.replace(".deb", ".changelog"))
        # test source changelogs
        uri = self.cache._guess_third_party_changelogs_uri_by_source(pkgname)
        self.assertTrue("gcc-defaults_" in uri)
        self.assertTrue(uri.endswith(".changelog"))
        # and one without a "Source" entry, we don't find something here
        self.assertEqual(self.cache._guess_third_party_changelogs_uri_by_source("apt"), None)
        # one with srcver == binver
        pkgname = "libgtk2.0-dev"
        uri = self.cache._guess_third_party_changelogs_uri_by_source(pkgname)
        pkg = self.cache[pkgname]
        self.assertTrue(pkg.candidate.version in uri)
        self.assertTrue("gtk+2.0" in uri)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == "-v":
        logging.basicConfig(level=logging.DEBUG)
    unittest.main()
    
