#!/usr/bin/env python
# -*- coding: utf-8 -*-
# crowdin_sync.py
#
# Updates Crowdin source translations and pushes translations
# directly to CarbonROM's Gerrit.
#
# Copyright (C) 2014 The CyanogenMod Project
# Modifications Copyright (C) 2014 CarbonROM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ################################# IMPORTS ################################## #

from __future__ import print_function

import argparse
import git
import os
import subprocess
import sys

from xml.dom import minidom
from lxml import etree

# ################################# GLOBALS ################################## #

_DIR = os.path.dirname(os.path.realpath(__file__))
_COMMITS_CREATED = False

# ################################ FUNCTIONS ################################# #


def run_subprocess(cmd, silent=False):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True)
    comm = p.communicate()
    exit_code = p.returncode
    if exit_code != 0 and not silent:
        print("There was an error running the subprocess.\n"
              "cmd: %s\n"
              "exit code: %d\n"
              "stdout: %s\n"
              "stderr: %s" % (cmd, exit_code, comm[0], comm[1]),
              file=sys.stderr)
    return comm, exit_code

def push_as_commit(base_path, path, name, branch, username):
    print('Committing %s on branch %s' % (name, branch))

    # Get path
    path = os.path.join(base_path, path)
    if not path.endswith('.git'):
        path = os.path.join(path, '.git')

    # Create repo object
    repo = git.Repo(path)

    # Remove previously deleted files from Git
    files = repo.git.ls_files(d=True).split('\n')
    if files and files[0]:
        repo.git.rm(files)

    # Add all files to commit
    repo.git.add('-A')

    # Create commit; if it fails, probably empty so skipping
    try:
        repo.git.commit(m='Automatic translation import')
    except:
        print('Failed to create commit for %s, probably empty: skipping'
              % name, file=sys.stderr)

    # Push commit
    try:
        repo.git.push('ssh://%s@review.carbonrom.org:29418/%s' % (username, name),
                      'HEAD:refs/for/%s%%topic=translation' % branch)
        print('Successfully pushed commit for %s' % name)
    except:
        print('Failed to push commit for %s' % name, file=sys.stderr)

    _COMMITS_CREATED = True

def check_run(cmd):
    p = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
    ret = p.wait()
    if ret != 0:
        print('Failed to run cmd: %s' % ' '.join(cmd), file=sys.stderr)
        sys.exit(ret)

# ############################################################################ #

def parse_args():
    parser = argparse.ArgumentParser(
        description="Synchronising CarbonROM's translations with Crowdin")
    sync = parser.add_mutually_exclusive_group()
    parser.add_argument('-u', '--username', help='Gerrit username')
    parser.add_argument('-b', '--branch', help='CarbonROM branch')
    parser.add_argument('-c', '--config', help='Custom yaml config')
    parser.add_argument('--upload-sources', action='store_true',
                        help='Upload sources to Crowdin')
    parser.add_argument('--upload-translations', action='store_true',
                        help='Upload translations to Crowdin')
    parser.add_argument('--download', action='store_true',
                        help='Download translations from Crowdin')
    parser.add_argument('--local-download', action='store_true',
                        help='local Download translations from Crowdin')
    return parser.parse_args()

# ################################# PREPARE ################################## #

def check_dependencies():
    # Check for Ruby version of crowdin-cli
    cmd = ['gem', 'list', 'crowdin-cli', '-i']
    if run_subprocess(cmd, silent=True)[1] != 0:
        print('You have not installed crowdin-cli.', file=sys.stderr)
        return False
    return True


def load_xml(x):
    try:
        return minidom.parse(x)
    except IOError:
        print('You have no %s.' % x, file=sys.stderr)
        return None
    except Exception:
        # TODO: minidom should not be used.
        print('Malformed %s.' % x, file=sys.stderr)
        return None


def check_files(files):
    for f in files:
        if not os.path.isfile(f):
            print('You have no %s.' % f, file=sys.stderr)
            return False
    return True

# ################################### MAIN ################################### #

def upload_sources_crowdin(branch, config):
    if config:
        print('\nUploading sources to Crowdin (custom config)')
    else:
        print('\nUploading sources to Crowdin (AOSP supported languages)')
        config=branch + ".yaml"

    check_run(['crowdin-cli',
                '--config=%s/config/%s' % (_DIR, config),
               'upload', 'sources', '--branch=%s' % branch])

def upload_translations_crowdin(branch, config):
    if config:
        print('\nUploading translations to Crowdin (custom config)')
    else:
        print('\nUploading translations to Crowdin '
              '(AOSP supported languages)')
        config=branch + ".yaml"

    check_run(['crowdin-cli',
                '--config=%s/config/%s' % (_DIR, config),
               'upload', 'translations', '--branch=%s' % branch,
               '--no-import-duplicates', '--import-eq-suggestions',
               '--auto-approve-imported'])

def local_download(base_path, branch, xml, config):
    if config:
        print('\nDownloading translations from Crowdin (custom config)')
    else:
        print('\nDownloading translations from Crowdin '
              '(AOSP supported languages)')
        config=branch + ".yaml"

    check_run(['crowdin-cli',
               '--config=%s/config/%s' % (_DIR, config),
               'download', '--branch=%s' % branch])

    print('\nRemoving useless empty translation files')
    empty_contents = {
        '<resources/>',
        '<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2"/>',
        ('<resources xmlns:android='
         '"http://schemas.android.com/apk/res/android"/>'),
        ('<resources xmlns:android="http://schemas.android.com/apk/res/android"'
         ' xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2"/>'),
        ('<resources xmlns:tools="http://schemas.android.com/tools"'
         ' xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2"/>'),
        ('<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">\n</resources>'),
        ('<resources xmlns:android='
         '"http://schemas.android.com/apk/res/android">\n</resources>'),
        ('<resources xmlns:android="http://schemas.android.com/apk/res/android"'
         ' xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">\n</resources>'),
        ('<resources xmlns:tools="http://schemas.android.com/tools"'
         ' xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">\n</resources>'),
        ('<resources>\n</resources>')
    }

    xf = None
    dom1 = None
    cmd = ['crowdin-cli', '--config=%s/config/%s' % (_DIR, config), 'list', 'translations']
    comm, ret = run_subprocess(cmd)
    if ret != 0:
        sys.exit(ret)
    # Split in list and remove last empty entry
    xml_list=str(comm[0]).split("\n")[:-1]
    for xml_file in xml_list:
        try:
            print("opening "+ base_path + xml_file)
            tree = etree.XML(open(base_path + xml_file).read().encode())
            etree.strip_tags(tree,etree.Comment)
            treestring = etree.tostring(tree,encoding='UTF-8')
            xf = "".join([s for s in treestring.decode().strip().splitlines(True) if s.strip()])
            for line in empty_contents:
                if line in xf:
                    print('Removing ' + base_path + xml_file)
                    os.remove(base_path + xml_file)
                    break
        except IOError:
            print("File not found: " + xml_file)
            sys.exit(1)
        except etree.XMLSyntaxError:
            print("XML Syntax error in file: " + xml_file)
            sys.exit(1)
    del xf
    del dom1

def download_crowdin(base_path, branch, xml, username, config):
    local_download(base_path, branch, xml, config)
    print('\nCreating a list of pushable translations')
    # Get all files that Crowdin pushed
    paths = []
    if config:
        files = ['%s/config/%s' % (_DIR, config)]
    else:
        files = ['%s/config/%s.yaml' % (_DIR, branch)]
    for c in files:
        cmd = ['crowdin-cli', '--config=%s' % c, 'list', 'project',
               '--branch=%s' % branch]
        comm, ret = run_subprocess(cmd)
        if ret != 0:
            sys.exit(ret)
        for p in str(comm[0]).split("\n"):
            paths.append(p.replace('/%s' % branch, ''))

    print('\nUploading translations to Gerrit')
    items = [x for sub in xml for x in sub.getElementsByTagName('project')]
    all_projects = []

    for path in paths:
        path = path.strip()
        if not path:
            continue

        if "/res" not in path:
            print('WARNING: Cannot determine project root dir of '
                  '[%s], skipping.' % path)
            continue
        result = path.split('/res')[0].strip('/')
        if result == path.strip('/'):
            print('WARNING: Cannot determine project root dir of '
                  '[%s], skipping.' % path)
            continue

        if result in all_projects:
            continue

        # When a project has multiple translatable files, Crowdin will
        # give duplicates.
        # We don't want that (useless empty commits), so we save each
        # project in all_projects and check if it's already in there.
        all_projects.append(result)

        # Search android/default.xml or config/%(branch)_extra_packages.xml
        # for the project's name
        for project in items:
            path = project.attributes['path'].value
            if not (result + '/').startswith(path +'/'):
                continue
            if result != path:
                if path in all_projects:
                    break
                result = path
                all_projects.append(result)

            br = project.getAttribute('revision') or branch

            push_as_commit(base_path, result,
                           project.getAttribute('name'), br, username)
            break

def main():
    args = parse_args()
    default_branch = args.branch

    base_path = os.getenv('CARBON_CROWDIN_BASE_PATH')
    if base_path is None:
        print('You have not set CARBON_CROWDIN_BASE_PATH')
        sys.exit(1)
    if default_branch is None:
        default_branch = os.getenv('CARBON_CROWDIN_BRANCH')
        if default_branch is None:
            print('You have not set CARBON_CROWDIN_BRANCH')
            sys.exit(1)

    if not check_dependencies():
        sys.exit(1)

    xml_android = load_xml(x='%s/android/carbon-default.xml' % base_path)
    if xml_android is None:
        sys.exit(1)

    xml_extra1 = load_xml(x='%s/android/carbon-aosp.xml' % base_path)
    if xml_extra1 is None:
        sys.exit(1)

    xml_extra2 = load_xml(x='%s/config/%s_extra_packages.xml'
                           % (_DIR, default_branch))
    if xml_extra2 is None:
        sys.exit(1)

    if args.config:
        files = ['%s/config/%s' % (_DIR, args.config)]
    else:
        files = ['%s/config/%s.yaml' % (_DIR, default_branch)]
    if not check_files(files):
        sys.exit(1)

    if args.download and args.username is None:
        print('Argument -u/--username is required for translations download')
        sys.exit(1)

    if args.upload_sources:
        upload_sources_crowdin(default_branch, args.config)
    if args.upload_translations:
        upload_translations_crowdin(default_branch, args.config)
    if args.download:
        download_crowdin(base_path, default_branch, (xml_android, xml_extra1, xml_extra2),
                         args.username, args.config)
    if args.local_download:
        local_download(base_path, default_branch, (xml_android, xml_extra1, xml_extra2),
                         args.config)

    if _COMMITS_CREATED:
        print('\nDone!')
        sys.exit(0)
    else:
        print('\nNothing to commit')
        sys.exit(-1)

if __name__ == '__main__':
    main()
