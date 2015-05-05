# **************************************************************************
# *
# * Authors: J. Burguet Castell (jburguet@cnb.csic.es)
# *
# * Unidad de Bioinformatica of Centro Nacional de Biotecnologia, CSIC
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# **************************************************************************
"""
Check the local configuration files, and/or create them if requested
or if they do not exist.
"""

import sys
import os
from os.path import join, exists, dirname, basename, islink, isdir
import time
import optparse
# We use optparse instead of argparse because we want this script to
# be compatible with python >= 2.3

try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser  # Python 3

def ansi(n):
    "Return function that escapes text with ANSI color n."
    return lambda txt: '\x1b[%dm%s\x1b[0m' % (n, txt)

black, red, green, yellow, blue, magenta, cyan, white = map(ansi, range(30, 38))


def main():
    parser = optparse.OptionParser(description=__doc__)
    add = parser.add_option  # shortcut
    add('--overwrite', action='store_true',
        help=("Rewrite the configuration files using the original templates."))
    options, args = parser.parse_args()

    if args:  # no args which aren't options
        sys.exit(parser.format_help())

    globalIsLocal = (os.environ['SCIPION_CONFIG'] ==
                     os.environ['SCIPION_LOCAL_CONFIG'])  # if we used --config
    if globalIsLocal:
        localSections = []
    else:
        localSections = ['DIRS_LOCAL']

    try:
        templatesDir = join(os.environ['SCIPION_HOME'], 'config', 'templates')
        # Global installation configuration files.
        for fpath, tmplt in [
                (os.environ['SCIPION_CONFIG'], 'scipion'),
                (os.environ['SCIPION_PROTOCOLS'], 'protocols'),
                (os.environ['SCIPION_HOSTS'], 'hosts')]:
            if not exists(fpath) or options.overwrite:
                createConf(fpath, join(templatesDir, tmplt + '.template'),
                           remove=localSections)
            else:
                checkConf(fpath, join(templatesDir, tmplt + '.template'),
                          remove=localSections)

        if not globalIsLocal:  # which is normally the case
            # Local user configuration files (well, only "scipion.conf").
            if not exists(os.environ['SCIPION_LOCAL_CONFIG']):
                #  It might make sense to add   "or options.overwrite" ...
                createConf(os.environ['SCIPION_LOCAL_CONFIG'],
                           join(templatesDir, 'scipion.template'),
                           keep=localSections)
            else:
                checkConf(os.environ['SCIPION_LOCAL_CONFIG'],
                          join(templatesDir, 'scipion.template'),
                          keep=localSections)

        # After all, check some extra things are fine in scipion.conf
        checkPaths(os.environ['SCIPION_CONFIG'])
    except Exception:
        # This way of catching exceptions works with Python 2 & 3
        sys.stderr.write('Error: %s\n' % sys.exc_info()[1])
        sys.exit(1)


def createConf(fpath, ftemplate, remove=[], keep=[]):
    "Create config file in fpath following the template in ftemplate"
    # Remove from the template the sections in "remove", and if "keep"
    # is used only keep those sections.

    # Create directory and backup if necessary.
    dname = dirname(fpath)
    if not exists(dname):
        os.makedirs(dname)
    elif exists(fpath):
        if not exists(join(dname, 'backups')):
            os.makedirs(join(dname, 'backups'))
        backup = join(dname, 'backups',
                      '%s.%d' % (basename(fpath), int(time.time())))
        print(yellow("* Creating backup: %s" % backup))
        os.rename(fpath, backup)

    # Read the template configuration file.
    print(yellow("* Creating configuration file: %s" % fpath))
    cf = ConfigParser()
    cf.optionxform = str  # keep case (stackoverflow.com/questions/1611799)
    assert cf.read(ftemplate) != [], 'Missing file: %s' % ftemplate
    for section in set(remove) - set(keep):
        cf.remove_section(section)
    if keep:
        for section in set(cf.sections()) - set(keep):
            cf.remove_section(section)

    # Update with our guesses.
    if 'BUILD' in cf.sections() and 'JAVA_HOME' in cf.options('BUILD'):
        cf.set('BUILD', 'JAVA_HOME', guessJavaHome())

    # Create the actual configuration file.
    cf.write(open(fpath, 'w'))
    print("Please edit it to reflect the configuration of your system.\n")


def checkPaths(conf):
    "Check that some paths in the config file actually make sense"

    print("Checking paths in %s ..." % conf)
    cf = ConfigParser()
    cf.optionxform = str  # keep case (stackoverflow.com/questions/1611799)
    assert cf.read(conf) != [], 'Missing file: %s' % conf
    get = lambda x: cf.get('BUILD', x)  # short notation
    allOk = True
    for var in ['MPI_LIBDIR', 'MPI_INCLUDE', 'MPI_BINDIR',
                'JAVA_HOME', 'JAVA_BINDIR']:
        if not os.path.isdir(get(var)):
            print("  Path to %s (%s) should exist but it doesn't." %
                  (var, red(get(var))))
            allOk = False
    for fname in [join(get('JAVA_BINDIR'), 'java'),
                  get('JAVAC'), get('JAR'),
                  join(get('MPI_BINDIR'), get('MPI_CC')),
                  join(get('MPI_BINDIR'), get('MPI_CXX')),
                  join(get('MPI_BINDIR'), get('MPI_LINKERFORPROGRAMS')),
                  join(get('MPI_INCLUDE'), 'mpi.h')]:
        if not exists(fname):
            print("  Cannot find file: %s" % red(fname))
            allOk = False
    if allOk:
        print(green("All seems fine with %s" % conf))
    else:
        print(red("Errors found."))
        print("Please edit %s and check again." % conf)


def checkConf(fpath, ftemplate, remove=[], keep=[]):
    "Check that all the variables in the template are in the config file too"

    # Remove from the checks the sections in "remove", and if "keep"
    # is used only check those sections.
    cf = ConfigParser()
    cf.optionxform = str  # keep case (stackoverflow.com/questions/1611799)
    assert cf.read(fpath) != [], 'Missing file %s' % fpath
    ct = ConfigParser()
    ct.optionxform = str
    assert ct.read(ftemplate) != [], 'Missing file %s' % ftemplate

    # Keep only the sections we want to compare from the files.
    for section in set(remove) - set(keep):
        ct.remove_section(section)
        cf.remove_section(section)
    if keep:
        for section in set(ct.sections()) - set(keep):
            ct.remove_section(section)
            cf.remove_section(section)

    df = dict([(s, set(cf.options(s))) for s in cf.sections()])
    dt = dict([(s, set(ct.options(s))) for s in ct.sections()])
    # That funny syntax to create the dictionaries works with old pythons.

    if df == dt:
        print(green("All the expected sections and options found in " + fpath))
    else:
        print("Found differences between the configuration file\n  %s\n"
              "and the template file\n  %s" % (fpath, ftemplate))
        sf = set(df.keys())
        st = set(dt.keys())
        for s in sf - st:
            print("Section %s exists in the configuration file but "
                  "not in the template." % red(s))
        for s in st - sf:
            print("Section %s exists in the template but "
                  "not in the configuration file." % red(s))
        for s in st & sf:
            for o in df[s] - dt[s]:
                print("In section %s, option %s exists in the configuration "
                      "file but not in the template." % (red(s), red(o)))
            for o in dt[s] - df[s]:
                print("In section %s, option %s exists in the template "
                      "but not in the configuration file." % (red(s), red(o)))


def guessJavaHome():
    "Guess the system's JAVA_HOME"

    candidates = []

    # First check if the system has a favorite one.
    if 'JAVA_HOME' in os.environ:
        candidates.append(os.environ['JAVA_HOME'])

    # Add also all the ones related to a "javac" program.
    for d in os.environ.get('PATH', '').split(':'):
        if not isdir(d) or 'javac' not in os.listdir(d):
            continue
        javaBin = unref(join(d, 'javac'))
        if javaBin.endswith('/bin/javac'):
            javaHome = javaBin[:-len('/bin/javac')]
            candidates.append(javaHome)
            if javaHome.endswith('/jre'):
                candidates.append(javaHome[:-len('/jre')])

    # Check in order if for any of our candidates, all related
    # directories and files exist. If they do, that'd be our best guess.
    for javaHome in candidates:
        allExist = True
        for path in ['include', join('bin', 'javac'), join('bin', 'jar')]:
            if not exists(join(javaHome, path)):
                allExist = False
        if allExist:
            return javaHome

    print(red("Warning: could not detect a suitable JAVA_HOME."))
    if candidates:
        print(red("Our candidates were:\n  %s" % '\n  '.join(candidates)))
    return '/usr/lib64/jvm/java-1.7.0-openjdk-1.7.0'  # not found, default value


def unref(path):
    "Return the final file or directory to which the symbolic link path points"
    # If the path is not a symbolic link, it just returns it.

    for i in range(100):
        if islink(path):
            path = os.readlink(path)
        elif exists(path):
            break
        else:
            continue
    else:  # too many iterations (> 100)
        raise RuntimeError("Link screwed: %s" % path)

    return path



if __name__ == '__main__':
    main()
