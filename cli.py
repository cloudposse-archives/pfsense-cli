#!/usr/bin/env python
import mechanize
import ssl
import time
import os
import re
import gzip
import pprint

from optparse import OptionParser
from os import listdir

ssl._create_default_https_context = ssl._create_unverified_context # pylint: disable=W0212

NOW = int(time.time())

pp = pprint.PrettyPrinter(indent=4)

# pfSense is booting, then packages will be reinstalled in the background.
# Do not make changes in the GUI until this is complete.

class PfSenseWebAPI:
    def __init__(self):
        self.browser = mechanize.Browser()
        self.browser.set_handle_robots(False)

    def login(self,username,password,host):
        self.username = username
        self.password = password
        self.host = host
        response = self.browser.open('https://' + self.host + '/index.php')
        self.browser.form = list(self.browser.forms())[0]

        control = self.browser.form.find_control('usernamefld')
        control.value = self.username

        control = self.browser.form.find_control('passwordfld')
        control.value = self.password

        response = self.browser.submit()

    def snort_enable(self):
        for link in self.browser.links():
            if 'Snort' in link.text:
                print "Found link " + link.url
                self.browser.click_link(link)
                response = self.browser.follow_link(link)
                break
        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.set_all_readonly(False)

        # Enable the first interface
        self.browser.form.find_control("ldel_0").disabled = True
        self.browser.form.find_control("id").value = '0'
        self.browser.form.find_control("toggle").value = 'start'
        self.browser.form.find_control("by2toggle").value = ''

        response = self.browser.submit()
        request = self.browser.request
        html = response.read()
        #print html

        return

    def set_admin_password(self, new_password):
        response = self.browser.open('https://' + self.host + '/system_usermanager.php?act=edit&userid=0')
        self.browser.form = list(self.browser.forms())[0]
        control = self.browser.form.find_control("passwordfld1")
        control.value = new_password
        control = self.browser.form.find_control("passwordfld2")
        control.value = new_password

        response = self.browser.submit(name='save')
        html = response.read()
        print html

        return


    def squidguard_enable(self):
        for link in self.browser.links():
            if 'SquidGuard Proxy Filter' in link.text:
                self.browser.click_link(link)
                response = self.browser.follow_link(link)
                break

        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.find_control("squidguard_enable").items[0].selected = True
        response = self.browser.submit(name='submit')

        request = self.browser.request
        pp.pprint(request.data)

        html = response.read()
        #    print html

        return


    def squidguard_download(self):
        response = self.browser.open('https://' + self.host + '/squidGuard/squidguard_blacklist.php')
        self.browser.form = list(self.browser.forms())[0]
        control = self.browser.form.find_control('blacklist_url')
        blacklist = control.value
        print "Found blacklist: " + blacklist

        response = self.browser.submit(name='blacklist_download_start')
        html = response.read()

        # Start the download
        response = self.browser.open('https://' + self.host + '/squidGuard/squidguard_blacklist.php?getactivity=yes&blacklist_download_start=yes&blacklist_url=' + blacklist)

        # Block until completed
        while True:
            response = self.browser.open('https://' + self.host + '/squidGuard/squidguard_blacklist.php?getactivity=yes')
            html = response.read()
            print html
            if "Blacklist update complete" in html:
                break
        return

    def restore_backup(self):
        for link in self.browser.links():
            if 'Backup & Restore' in link.text:
                self.browser.click_link(link)
                response = self.browser.follow_link(link)
                break

        #local_file = '/tmp/pfsense-config-1512885035.xml'
        local_file = '/tmp/pfsense_dmz_config.xml'

        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.find_control("decrypt").items[0].selected = False
        self.browser.form.add_file(open(local_file, "rb"), "", 'config.xml')
        response = self.browser.submit(name='restore')
        html = response.read()
        print html

        return

    def download_backup(self):
        for link in self.browser.links():
            if 'Backup & Restore' in link.text:
                self.browser.click_link(link)
                response = self.browser.follow_link(link)
                break

        self.browser.form = list(self.browser.forms())[0]
        self.browser.form.find_control("donotbackuprrd").items[0].selected = False
        response = self.browser.submit(name='backup')
        xml = response.read()

        if COMPRESSION:
            filename = '%s/pfsense-config-%d.xml.gz' % (BACKUPDIR, NOW)
            output = gzip.open(filename, 'w')
        else:
            filename = '%s/pfsense-config-%d.xml' % (BACKUPDIR, NOW)
            output = open(filename, 'w')
        output.write(xml)
        output.close()
        return

def main():
    usage = "usage: %prog [options] arg"
    parser = OptionParser(usage)
    parser.add_option("-u", "--username", dest="username",
                      help="login as username")
    parser.add_option("-p", "--password", dest="password",
                      help="login with password")
    parser.add_option("-H", "--host", dest="host",
                      help="login to pfSense host")
    parser.add_option("-r", "--restore-backup",
                      dest="config")
    parser.add_option("-S", "--enable-squidguard",
                      action="store_true")
    parser.add_option("-D", "--squidguard-download",
                      action="store_true")
    parser.add_option("-T", "--enable-snort",
                      action="store_true")
    parser.add_option("-P", "--set-admin-password",
                      dest="new_password")
    parser.add_option("-g", "--download-backup",
                      action="store_true")

    (opts, args) = parser.parse_args()

    #if len(args) != 1:
    #    parser.error("incorrect number of arguments")
    #if opt.verbose:
    #    print "reading %s..." % options.filename

    api = PfSenseWebAPI()
    api.login(opts.username, opts.password, opts.host)

    if opts.squidguard_download:
        api.squidguard_download()

    if opts.enable_squidguard:
        api.squidguard_enable()

    if opts.new_password:
        api.set_admin_password(opts.new_password)

    if opts.enable_snort:
        api.snort_enable()

    if opts.download_backup:
        download_backup()

#    if opts.restore_backup:
#        api.restore_backup()

if __name__ == "__main__":
    main()
