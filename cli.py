#!/usr/bin/env python
import mechanize
import ssl
import time
import os
import re
import gzip
import pprint
import sys
import argparse

from optparse import OptionParser
from os import listdir

ssl._create_default_https_context = ssl._create_unverified_context # pylint: disable=W0212

pp = pprint.PrettyPrinter(indent=4)


class PfSenseWebAPI:
    def __init__(self, debug_level=False):
        self.browser = mechanize.Browser()
        self.browser.set_handle_robots(False)
        self.debug_level = debug_level

    def debug(self, msg):
        if self.debug_level:
            print msg

    def login(self, username, password, host):
        self.username = username
        self.password = password
        self.host = host
        self.url = 'https://' + self.host

        self.browser.open(self.url + '/index.php')
        self.browser.form = list(self.browser.forms())[0]

        control = self.browser.form.find_control('usernamefld')
        control.value = self.username

        control = self.browser.form.find_control('passwordfld')
        control.value = self.password

        response = self.browser.submit()
        html = response.read()

        if 'Username or Password' in html:
            result = 1, "Username or Password is incorrect"
        else:
            result = 0, "Login OK"
        return result

    def wait_until_ready(self):
        while True:
            response = self.browser.open(self.url + '/index.php')
            html = response.read()
            if 'Do not make changes in the GUI' not in html \
                    and 'Packages are currently being reinstalled in the background' not in html:
                break
            print "pfSense is not ready"
            time.sleep(1)
        print "pfSense is ready"

    def snort_enable(self):
        for link in self.browser.links():
            if 'Snort' in link.text:
                print "Found link " + link.url
                self.browser.click_link(link)
                self.browser.follow_link(link)
                break
        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.set_all_readonly(False)

        # Enable the first interface
        self.browser.form.find_control("ldel_0").disabled = True
        self.browser.form.find_control("id").value = '0'
        self.browser.form.find_control("toggle").value = 'start'
        self.browser.form.find_control("by2toggle").value = ''

        response = self.browser.submit()
        self.browser.request
        html = response.read()
        self.debug(html)

        return

    def set_admin_password(self, new_password):
        self.browser.open(self.url + '/system_usermanager.php?act=edit&userid=0')
        self.browser.form = list(self.browser.forms())[0]
        control = self.browser.form.find_control("passwordfld1")
        control.value = new_password
        control = self.browser.form.find_control("passwordfld2")
        control.value = new_password

        response = self.browser.submit(name='save')
        html = response.read()
        self.debug(html)

        return

    def squidguard_enable(self):
        for link in self.browser.links():
            if 'SquidGuard Proxy Filter' in link.text:
                self.browser.click_link(link)
                self.browser.follow_link(link)
                break

        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.find_control("squidguard_enable").items[0].selected = True
        response = self.browser.submit(name='submit')

        request = self.browser.request
        pp.pprint(request.data)

        html = response.read()
        self.debug(html)

        return

    def set_squid_acl(self, allowed_subnet):
        self.browser.open(self.url + '/pkg_edit.php?xml=squid_nac.xml&id=0')
        self.browser.form = list(self.browser.forms())[0]
        control = self.browser.form.find_control('allowed_subnets')
        control.value = allowed_subnet

        response = self.browser.submit(name='submit')
        html = response.read()
        self.debug(html)

        if 'The following input errors were detected' in html:
            result = 1, "Incorrect subnet"
        else:
            result = 0, "ACLs is set"
        return result

    def squidguard_download(self):
        self.browser.open(self.url + '/squidGuard/squidguard_blacklist.php')
        self.browser.form = list(self.browser.forms())[0]
        control = self.browser.form.find_control('blacklist_url')
        blacklist = control.value
        print "Found blacklist: " + blacklist

        response = self.browser.submit(name='blacklist_download_start')
        response.read()

        # Start the download
        self.browser.open(self.url + '/squidGuard/squidguard_blacklist.php?getactivity=yes'
                                                '&blacklist_download_start=yes&blacklist_url=' + blacklist)

        # Block until completed
        while True:
            response = self.browser.open(self.url + '/squidGuard/squidguard_blacklist.php?getactivity=yes')
            html = response.read()
            self.debug(html)
            if "Blacklist update complete" in html:
                break
            time.sleep(1)
        print "Blacklist update complete"
        return

    def restore_backup(self, config):
        for link in self.browser.links():
            if 'Backup & Restore' in link.text:
                self.browser.click_link(link)
                self.browser.follow_link(link)
                break

        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.find_control("decrypt").items[0].selected = False
        self.browser.form.add_file(open(config, "rb"), "", 'config.xml')
        response = self.browser.submit(name='restore')
        html = response.read()
        self.debug(html)

        return

    def download_backup(self, backup_dir, compression):
        for link in self.browser.links():
            if 'Backup & Restore' in link.text:
                self.browser.click_link(link)
                self.browser.follow_link(link)
                break

        now = int(time.time())

        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.find_control("donotbackuprrd").items[0].selected = False
        response = self.browser.submit(name='download')
        xml = response.read()
        if '<?xml version="1.0"?>' not in xml:
            raise ValueError('Invalid non-xml response')

        if compression:
            filename = '%s/pfsense-config-%d.xml.gz' % (backup_dir, now)
            output = gzip.open(filename, 'w')
        else:
            filename = '%s/pfsense-config-%d.xml' % (backup_dir, now)
            output = open(filename, 'w')
        print "Wrote backup to %s" % filename
        output.write(xml)
        output.close()
        return

    def check_login(self):
        response = self.browser.open(self.url + '/index.php')
        html = response.read()
        if 'System Information' in html:
            result = 0, "Login OK"
        else:
            result = 1, "Login not OK"
        return result


def main():
    usage = "usage: %prog [options] [restore-backup|enable-squidguard|squidguard-download|enable-snort|set-admin" \
            "-password|download-backup|check-login|set-squid-acl] "
    parser = OptionParser(usage)
    parser.add_option("-u", "--username", dest="username",
                      help="login as username")
    parser.add_option("-p", "--password", dest="password",
                      help="login with password")
    parser.add_option("-H", "--host", dest="host",
                      help="login to pfSense host")
    parser.add_option("-c", "--config", dest="config",
                      help="config to restore")
    parser.add_option("-n", "--new-password", dest="new_password",
                      help="new password")
    parser.add_option("-z", "--compress", dest="compress", action="store_true",
                      help="compress backup")
    parser.add_option("-b", "--backup-dir", dest="backup_dir", default="/tmp",
                      help="backup directory")
    parser.add_option("-a", "--allowed-subnet", dest="allowed_subnet", default=False,
                      help="squid allowed subnet")
    parser.add_option("-d", "--debug-level", dest="debug_level", default=False,
                      help="debug-level")

    (opts, args) = parser.parse_args()

    if not args:
        parser.print_help()
        sys.exit(1)
    elif len(args) != 1:
        parser.error("Incorrect number of arguments")
        sys.exit(1)

    api = PfSenseWebAPI(opts.debug_level)
    status, message = api.login(opts.username, opts.password, opts.host)

    if status != 0:
        print (message)
        sys.exit(1)

    action = args[0]

    try:
        if action == 'squidguard-download':
            api.squidguard_download()

        elif action == 'enable-squidguard':
            api.squidguard_enable()

        elif action == 'set-admin-password':
            api.set_admin_password(opts.new_password)

        elif action == 'enable-snort':
            api.snort_enable()

        elif action == 'download-backup':
            api.download_backup(opts.backup_dir, opts.compress)

        elif action == 'restore-backup':
            api.restore_backup(opts.config)

        elif action == 'wait-until-ready':
            api.wait_until_ready()

        elif action == 'check-login':
            api.check_login()

        elif action == 'set-squid-acl':
            api.set_squid_acl(opts.allowed_subnet)

        else:
            raise ValueError('Unrecognized option: ' + action)

    except KeyboardInterrupt:
        print "Aborted"
        sys.exit(1)


if __name__ == "__main__":
    main()
    sys.exit(0)
