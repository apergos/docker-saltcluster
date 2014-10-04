import sys
import getopt

VERSION = "0.1"

DEPS_PATH = '/root/depends/'
SALT_PATH = '/root/salt/'

def get_dep_entries(packages):
    """
    given list of packages that are salt dependencies,
    generate Dockerfile ADD lines for them all
    """
    text = ""
    for package in packages:
        text = text + "ADD debs/{package}.deb {path}\n".format(
            package=package, path=DEPS_PATH)
    return text



def get_salt_deb_entries(package_versions):
    """
    given  list of salt package versions (text
    between 'salt-<something>_' and '.deb'),
    generate the Dockerfile ADD lines for
    those, plus a following blank line
    for readability
    """
    text = ""
    for version in package_versions:
        for package in ['salt-common', 'salt-master', 'salt-minion']:
            text = text + "ADD debs/{package}_{version}.deb {path}\n".format(
                package=package, version=version, path=SALT_PATH)
        text = text + "\n"
    return text

def generate(distro):
    """
    read Dockerfile.tmpl, stuff in appropriate values
    depending on the distro, write result to stdout
    """
    if distro == 'lucid':
        ubuntu_version_text = 'lucid'
        ubuntu_version_number = '10.04'
        backports = ('RUN echo "deb http://archive.ubuntu.com/ubuntu '
                     'lucid-backports main universe" >> /etc/apt/sources.list')
        preinstall = ('RUN apt-get install -y apt-utils python '
                      'python-pkg-resources python-crypto '
                      'python-jinja2 python-m2crypto python-yaml '
                      'dctrl-tools python-support')

        deps = ("# ubuntu lucid doesn't have these; "
                "we stole them from the salt ppa\n")
        deps += get_dep_entries(['libmsgpack3_0.5.4-2_amd64',
                                 'msgpack-python_0.1.9-2_amd64'])
        deps += ("# same for these, may not be needed depending "
                 "on the salt version\n"
                 "# but we install them anyways\n")
        deps += get_dep_entries(['libpgm-5.1-0_5.1.116~dfsg-2lucid1_amd64',
                                 'libzmq3_3.2.2+dfsg-1lucid_amd64',
                                 'python-zmq_13.0.0-3lucid_amd64',
                                 'python-py_1.4.12-2lucid_all',
                                 'python-six_1.2.0-2lucid_all',
                                 'python-pytest_2.3.4-3lucid_all',
                                 'python-urllib3_1.5-1lucid_all',
                                 'python-requests_1.1.0-2lucid_all'])
        deps += "RUN dpkg -i {path}*.deb\n\n".format(path=DEPS_PATH)

        salt_debs = get_salt_deb_entries([
            '0.17.1-1lucid_all',
            '0.17.5-1lucid1_all',
            '2014.1.10-1lucid1_all'])
        git = 'git-core'
        ruby = '/usr/lib/ruby/1.8'
        ssldeps = 'RUN apt-get install -y tcpd'

    elif distro == 'precise':
        ubuntu_version_text = 'precise'
        ubuntu_version_number = '12.04'
        backports = ""
        preinstall = ('RUN apt-get install -y apt-utils python '
                      'python-pkg-resources python-crypto '
                      'python-jinja2 python-m2crypto python-yaml '
                      'dctrl-tools msgpack-python python-support '
                      'libpgm-5.1.0')

        deps = "# ubuntu precise doesn't have these\n"
        deps += get_dep_entries(['libzmq3_3.2.2+dfsg-1precise_amd64',
                                 'python-zmq_13.0.0-2precise_amd64'])
        deps += "RUN dpkg -i {path}*.deb\n\n".format(path=DEPS_PATH)
        deps += "RUN apt-get install -y python-requests\n"

        salt_debs = get_salt_deb_entries([
            '0.17.1-1precise_all',
            '0.17.5-1precise1_all',
            '2014.1.10-1precise1_all'])
        git = 'git'
        ruby = '/usr/lib/ruby/1.8'
        ssldeps = ""

    elif distro == 'trusty':
        ubuntu_version_text = 'trusty'
        ubuntu_version_number = '14.04'
        backports = ""
        preinstall = ('RUN apt-get install -y apt-utils python '
                      'python-pkg-resources python-crypto '
                      'python-jinja2 python-m2crypto python-zmq '
                      'python-yaml dctrl-tools python-msgpack '
                      'libzmq3 python-zmq python-requests')
        deps = ""
        salt_debs = get_salt_deb_entries([
            '0.17.1+dfsg-1_all',
            '0.17.5+ds-1_all',
            '2014.1.10+ds-1trusty1_all'])
        git = 'git'
        ruby = '/usr/lib/ruby/vendor_ruby'
        ssldeps = ""

    dockerfile_contents = open('Dockerfile.tmpl', 'r').read().format(
        ubuntu_version_text=ubuntu_version_text,
        ubuntu_version_number=ubuntu_version_number,
        backports=backports,
        preinstall=preinstall,
        deps=deps,
        salt_debs=salt_debs,
        git=git,
        ruby=ruby,
        ssldeps=ssldeps
        )
    print dockerfile_contents

def show_version():
    'show the version of this script'
    print "generate_dockerfile.py " + VERSION
    sys.exit(0)

def usage(message=None):
    """
    display a helpful usage message with
    an optional introductory message first
    """
    if message is not None:
        sys.stderr.write(message)
        sys.stderr.write("\n")
    help_text = """Usage: generate_dockerfile.py --distro <text>
                          [--version] [--help]

This script generates a dockerfile which can be used to build
a base image for the specified ubuntu version, to be used to
create a salt cluster of docker containers.

Options:

  --distro  (-d)  string specifying ubuntu version, one of
                  'lucid', 'precise', or 'trusty'

  --version (-v)  display the version of this script and exit

  --help    (-h)  show this help message
"""
    sys.stderr.write(help_text)
    sys.exit(1)

def main():
    distro = None

    try:
        (options, remainder) = getopt.gnu_getopt(
            sys.argv[1:], "d:vh",
            ["distro=", "version", "help"])

    except getopt.GetoptError as err:
        usage("Unknown option specified: " + str(err))
    for (opt, val) in options:
        if opt in ["-d", "--distro"]:
            distro = val
        elif opt in ["-v", "--version"]:
            show_version()
        elif opt in ["-h", "--help"]:
            usage()
        else:
            usage("Unknown option specified: <%s>" % opt)

    if len(remainder) > 0:
        usage("Unknown option(s) specified: <%s>" % remainder[0])

    if distro is None:
        usage("Mandatory argument 'distro' not specified")

    if distro not in ['lucid', 'precise', 'trusty']:
        usage("Unknown distro specified")

    generate(distro)

if __name__ == '__main__':
    main()