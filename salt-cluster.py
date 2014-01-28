import os
import sys
import re
import time
import subprocess
import httplib
import getopt
import json
import socket
import Queue
import threading
import traceback

# script to start a salt master via docker, fix up minion
# configs and start salt clients via docker, get all the
# hostnames and ips and populate the relevant files
# (/etc/hosts, etc) appropriately

VERSION = "0.1"

class SELinux(object):
    @staticmethod
    def find_mount():
        with open('/proc/mounts','r') as f:
            mounts = f.read().splitlines()
        for m in mounts:
            if m.startswith('selinuxfs '):
                ftype, mntpoint, junk = m.split(' ',2)
                return mntpoint
        return None

class DockerError(Exception):
    pass

class LocalHTTPConnection(httplib.HTTPConnection):
    def __init__(self, socket_name, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        httplib.HTTPConnection.__init__(self, 'localhost', timeout=timeout)
        self.socket_name = socket_name

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_name)
        sock.settimeout(None)
        self.sock = sock

class Docker(object):
    def __init__(self, docker, selinux_hack):
        self.docker = docker
        self.selinux_hack = selinux_hack
        if selinux_hack:
            self.host_selinuxfs = SELinux.find_mount()
        else:
            self.host_selinuxfs = None

    def get_image_name(self, repo, tag):
        return repo + ":" + tag

    def get_url(self, url, method='GET', content=None):
        try:
            httpConn = LocalHTTPConnection("/var/run/docker.sock", timeout=20)
        except:
            print "failed to establish http connection to localhost for docker"
            raise

        h = {"User-Agent": "test-docker-api.py"}
        if content:
            h["Content-Type"] = "application/json"

        httpConn.request(method, url, body=content, headers=h)
        response = httpConn.getresponse(buffering=True)
        data = response.read()
        if (response.status == 200 or response.status == 201 or
            response.status == 204):
            if data:
                return json.loads(data.decode('utf-8'))
            else:
                return ""
        else:
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to get url ' + url, " with response code " + str(response.status))

    def build(self, dockerfile_contents, image_repo, image_tag):
        # we only keep the last layer so the user can cleanup easily
        command = [ self.docker, 'build', '-rm', '-t', self.get_image_name(image_repo,image_tag), '-' ]
        stdoutdata = None
        stderrdata = None
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            stdoutdata, stderrdata = proc.communicate(dockerfile_contents)
            if proc.returncode:
                if stderrdata:
                    sys.stderr.write(stderrdata)
                if stdoutdata:
                    sys.stderr.write(stdoutdata)
                raise DockerError("Error building docker image %s:%s (%s)\n" % (image_repo, image_tag, stderrdata))
        except:
            sys.stderr.write('Failed to build docker image ' + image_repo + ':' + image_tag + "\n")
            raise

    # docker run -i -t -v /sys/fs/selinux:/selinux:ro ariel/salt:tagno
    def create(self, image_name, container_name = None, container_command = None):
        config = { "Hostname":"", "Domainname":"", "User":"",
                   "Memory":0, "MemorySwap":0, "CpuShares":0,
                   "AttachStdin":True, "AttachStdout":True, "AttachStderr":True,
                   "PortSpecs":None, "ExposedPorts":{},
                   "Tty":True, "OpenStdin":True, "StdinOnce":True,
                   "Env":None, "Cmd":None, "Dns":None,
                   "Image":image_name,
                   "VolumesFrom":"",
                   "WorkingDir":"", "Entrypoint":None,
                   "NetworkDisabled":False }

        if self.host_selinuxfs:
            config['Volumes'] = { "/selinux": {} }

        config_string = json.dumps(config)
        url = "/containers/create"
        if container_name:
            url = url + "?name=" + container_name

        self.get_url(url, "POST", config_string)

    def start(self, instance_name):
        url = "/containers/" + instance_name + "/start"
        config = { "Binds":["/sys/fs/selinux:/selinux:ro"],
                   "ContainerIDFile":"",
                   "LxcConf":[],
                   "Privileged":False,
                   "PortBindings":{},
                   "Links":None,
                   "PublishAllPorts":False
        }

        if self.host_selinuxfs:
            config['Binds'] = [ self.host_selinuxfs + ':/selinux:ro' ]

        config_string = json.dumps(config)
        self.get_url(url, "POST", config_string)

    def stop(self, instance_name):
        # FIXME we should just shoot the processes on these containers
        url = "/containers/" + instance_name + "/stop?t=5"
        self.get_url(url, 'POST')

    def delete_container(self, instance_name):
        url = "/containers/" + instance_name
        self.get_url(url, 'DELETE')

    def delete_image(self, instance_name):
        url = "/images/" + instance_name
        self.get_url(url, 'DELETE')

    def is_running(self, instance_name):
        return self.container_exists(instance_name, check_all=False)

    def image_exists(self, image_repo, image_tag):
        image_name = image_repo + ":" + image_tag
        url = "/images/json"
        output = self.get_url(url)
        for entry in output:
            if (entry['Id'].startswith(image_name) or
                image_name in entry['RepoTags']):
                return True
        return False

    def get_image_id(self, image_repo, image_tag):
        image_name = image_repo + ":" + image_tag
        url = "/images/json"
        output = self.get_url(url)
        for entry in output:
            if (entry['Id'].startswith(image_name) or
                image_name in entry['RepoTags']):
                return entry['Id']
        return False

    def container_exists(self, container_name, check_all=True):
        url = "/containers/json"
        if check_all:
            url = url + "?all=1"
        output = self.get_url(url)
        for entry in output:
            if (entry['Id'].startswith(container_name) or
                container_name in [ n[1:] for n in entry['Names']]):
                return True
        return False

    def get_hosts_file(self, instance_name):
        url = "/containers/" + instance_name + "/json"
        output = self.get_url(url)
        result = output['HostsPath'].strip()
        if not result:
            sys.stderr.write('got: ' + output + "\n")
            raise DockerError('Failed to get hosts file name for ' + instance_name)
        return result

    def get_ip(self, instance_name):
        url = "/containers/" + instance_name + "/json"
        output = self.get_url(url)
        result = output['NetworkSettings']['IPAddress'].strip()
        if not result or not self.is_ip(result):
            # fixme output is a dict not a string d'oh
            sys.stderr.write('got: ' + output + "\n")
            raise DockerError('Failed to get ip of ' + instance_name)
        return result

    def is_hex_digits(self, string):
        return all(c in '0123456789abcdefABCDEF' for c in string)

    # fixme this is only ipv4... which is fine for right now
    def is_ip(self, string):
        try:
            fields = string.split('.')
        except:
            return False
        if not len(fields) == 4:
            return False
        for f in fields:
            if not f.isdigit():
                return False
            if int(f) > 255:
                return False
        return True

class Pupaas_client(object):
    def __init__(self, port):
        self.port = port

    def apply_puppet_manifest(self, instance_name, manifest):
        url =  '/apply/' + manifest
        method = 'POST'
        try:
            httpConn = httplib.HTTPConnection(instance_name, timeout=20, port=self.port)
        except:
            raise httplib.HTTPException("failed to establish http connection to " + instance_name)

        httpConn.request(method, url, headers={"User-Agent": "run_salt_client.py/0.0 (salt testbed configurator)"})
        response = httpConn.getresponse(buffering=True)
        data = response.read()
        if response.status == 200 or response.status == 204:
            return True
        else:
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to apply ' + manifest + ' on ' + instance_name, " with response code " + str(response.status))

    def add_puppet_manifest(self, instance_name, manifest, contents):
        url = '/manifest/' + manifest
        method = 'DELETE'
        try:
            httpConn = httplib.HTTPConnection(instance_name, timeout=20, port=self.port)
        except:
            raise httplib.HTTPException("failed to establish http connection to " + instance_name)

        httpConn.request(method, url, headers={"User-Agent": "run_salt_client.py/0.0 (salt testbed configurator)"})
        response = httpConn.getresponse(buffering=True)
        data = response.read()
        if (response.status != 200 and response.status != 404 and
            response.status != 201 and response.status != 204):
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to delete ' + manifest + ' on ' + instance_name, " with response code " + str(response.status))

        url = '/manifest/' + manifest
        method = 'PUT'

        httpConn.request(method, url, contents, headers={"User-Agent": "run_salt_client.py/0.0 (salt testbed configurator)"})
        response = httpConn.getresponse(buffering=True)
        data = response.read()
        if (response.status == 200 or response.status == 204 or
            response.status == 201):
            return True
        else:
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to put ' + manifest + ' on ' + instance_name, " with response code " + str(response.status))

    def get_puppet_fact(self, instance_name, fact):
        url =  '/fact/' + fact
        method = 'GET'
        try:
            httpConn = httplib.HTTPConnection(instance_name, timeout=20, port=self.port)
        except:
            raise httplib.HTTPException("failed to establish http connection to " + instance_name)

        httpConn.request(method, url, headers={"User-Agent": "run_salt_client.py/0.0 (salt testbed configurator)"})
        response = httpConn.getresponse(buffering=True)
        data = response.read()
        if response.status == 200:
            return data.rstrip()
        else:
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to retrieve fact ' + fact + ' on ' + instance_name, " with response code " + str(response.status))
    

class Salt_cluster(object):
    def __init__(self, saltmaster_host, saltminion_prefix, minion_count, paas_port, docker_path, salt_tag, selinux, docker_create, docker_force, verbose):
        self.verbose = verbose
        self.saltmaster_host = saltmaster_host + "-" +  salt_tag
        self.saltminion_prefix = saltminion_prefix
        self.minion_count = minion_count
        self.salt_tag = salt_tag
        self.docker_path = docker_path
        self.docker_create = docker_create
        if not self.docker_create:
            self.p = Pupaas_client(paas_port)
        self.docker_force = docker_force
        self.d = Docker(docker_path, selinux)
        self.master_fingerprint = None
        self.master_ip = None
        self.master_ip_host = {}
        self.minion_ips_hosts = {}

        self.discover_minion_count()

    def discover_minion_count(self):
        # how many containers do we have with that tag
        # (minions only please)?
        count = 0
        if not self.minion_count:
            url = "/containers/json?all=1"
            output = self.d.get_url(url)
            # u'Names': [u'/saltmaster-v0.17.1'],
            for entry in output:
                for n in entry['Names']:
                    if self.saltminion_prefix in n and n.endswith(self.salt_tag):
                        count = count + 1
            self.minion_count = count

    def start_salt_master(self):
        contents = "import 'salt.pp'\nclass { 'salt::master': ensure => 'running' }\n"
        self.p.add_puppet_manifest(self.master_ip, 'manifests/salt_master_start.pp', contents)
        self.p.apply_puppet_manifest(self.master_ip, 'manifests/salt_master_start.pp')

    def start_salt_minion(self, instance_name):
        contents = "import 'salt.pp'\nclass { 'salt::minion': ensure => 'running', salt_master => '%s', master_fingerprint => '%s' }\n" % (self.saltmaster_host, self.master_fingerprint)
        self.p.add_puppet_manifest(instance_name, 'manifests/salt_minion_start.pp', contents)
        self.p.apply_puppet_manifest(instance_name, 'manifests/salt_minion_start.pp')

    def stop_salt_master(self):
        contents = "import 'salt.pp'\nclass { 'salt::master': ensure => 'stopped' }\n"
        self.p.add_puppet_manifest(self.saltmaster_host, 'manifests/salt_master_stop.pp', contents)
        self.p.apply_puppet_manifest(self.saltmaster_host, 'manifests/salt_master_stop.pp')

    def stop_salt_minion(self, instance_name):
        contents = "import 'salt.pp'\nclass { 'salt::master': ensure => 'stopped', salt_master => '%s', master_fingerprint => '%s' }\n"% (self.saltmaster_host, self.master_fingerprint)
        self.p.add_puppet_manifest(instance_name, 'manifests/salt_minion_stop.pp', contents)
        self.p.apply_puppet_manifest(instance_name, 'manifests/salt_minion_stop.pp')

    def update_etc_hosts(self, instance_name, hosts_ips):
        # we will hack the file listed in HostsPath for the container. too bad
        hosts_file = self.d.get_hosts_file(instance_name)
        if not hosts_file:
            return
        header = [ "# saltcluster additions" ]

        with open(hosts_file,'r+b') as f:
            while 1:
                # read each line
                e = f.readline()
                if not e:
                    break
                # toss any entries made by previous runs
                if e.startswith('# saltcluster additions'):
                    header = []
                    f.truncate()
                    break

        salt_entries = [ hosts_ips[name] + "   " + name for name in hosts_ips ]
        contents = "\n".join(header + salt_entries) + "\n"

        with open(hosts_file,'a') as f:
            f.write(contents)

    def get_salt_key_fingerprint(self, instance_name):
        result = self.p.get_puppet_fact(instance_name, 'salt_key_fingerprint')
        return result.strip("\n")

    def get_salt_minion_name(self, instance_number):
        return self.saltminion_prefix + "-" + str(instance_number) + "-" + self.salt_tag

    def start_minion_container(self, instance_number):
        self.stop_minion_container(instance_number)

        instance_name = self.get_salt_minion_name(instance_number)
        self.d.start(instance_name)

    def start_master_container(self):
        if not self.d.is_running(self.saltmaster_host):
            self.d.start(self.saltmaster_host)

    def start_cluster(self, instance_no = None):
        if self.verbose:
            print "Starting salt master container..."
        self.start_master_container()

        if instance_no:
            todo = [ instance_no ]
        else:
            todo = range(1, self.minion_count + 1)

        for i in range(1, self.minion_count + 1):
            if self.verbose:
                print "Starting minion container " + str(i) + "..."
            self.start_minion_container(i)

    def pre_configure_master_container(self):
        # get salt master ip
        if not self.master_ip:
            self.master_ip = self.d.get_ip(self.saltmaster_host)
            self.master_ip_host[self.saltmaster_host] = self.master_ip

        self.start_salt_master()
        self.master_fingerprint = self.get_salt_key_fingerprint(self.master_ip)

    def configure_minion_container(self, instance_number, instance_name, ip):
        self.update_etc_hosts(instance_name,self.master_ip_host)
        self.start_salt_minion(ip)

    def do_config_jobs(self):
        while not self.config_completed:
            # fixme when do we know there will be no
            # more jobs for us on the queue?

            try:
                (i, instance_name, ip) = self.queue.get(True, 1)
            except Queue.Empty:
                continue
                
            if self.verbose:
                print "Configuring salt minion " + str(i) +"..."
            try:
                self.configure_minion_container(i, instance_name, ip)
            except Exception, err:
                traceback.print_exc(file=sys.stderr)
#                traceback.print_stack(file=sys.stderr)
                sys.stderr.write("problem configuring container " + str(i) + ", continuing\n")
            self.queue.task_done()

    def start_threads(self, count, target):
        threads = []
        for i in range(1, count+1):
            t = threading.Thread(target=target)
            t.daemon = True
            t.start()
            threads.append(t)
        return threads

    def configure_cluster(self, instance_no = None):
        # configuration is slow (puppet apply, salt key generation
        # etc) so do concurrent in batches
        if self.verbose:
            print "Pre-configuring salt master..."
        self.pre_configure_master_container()

        self.config_completed = False
        self.queue = Queue.Queue()
        if instance_no:
            num_threads = 1  # :-P
        else:
            # maybe a bug.  serious issues with multiple threads
            num_threads = 1
        threads = self.start_threads(num_threads, self.do_config_jobs)

         # collect all the ips, we need them for master /etc/hosts
        for i in range(1, self.minion_count + 1):
            instance_name = self.get_salt_minion_name(i)
            ip = self.d.get_ip(instance_name)
            self.minion_ips_hosts[instance_name] = ip

        if instance_no:
            todo = [ instance_no ]
        else:
            todo = range(1, self.minion_count + 1)

        for i in todo:
            instance_name = self.get_salt_minion_name(i)
            self.update_etc_hosts(instance_name,self.master_ip_host)
            self.queue.put_nowait((i, instance_name, self.minion_ips_hosts[instance_name]))

        # everything on the queue done?
        self.queue.join()

        # notify threads to go home, and wait for them to do so
        self.config_completed = True
        for t in threads:
            t.join()

        if self.verbose:
            print "Updating /etc/hosts on salt master..."
        self.update_etc_hosts(self.saltmaster_host, self.minion_ips_hosts)

    def stop_minion_container(self, instance_number):
        instance_name = self.get_salt_minion_name(instance_number)
        if self.d.is_running(instance_name):
            self.d.stop(instance_name)

    def stop_master_container(self):
        if self.d.is_running(self.saltmaster_host):
            self.d.stop(self.saltmaster_host)

    def do_stop_jobs(self):
        while not self.stop_completed:
            try:
                i = self.queue.get(True, 1)
            except Queue.Empty:
                continue
                
            if self.verbose:
                print "Stopping salt minion container " + str(i) + "..."
            try:
                self.stop_minion_container(i)
            except:
                sys.stderr.write("problem stopping container " + str(i) + ", continuing\n")
            self.queue.task_done()

    def stop_cluster(self, instance_no = None):
        # because we give the docker stop command several seconds to
        # complete and we are impatient, run these in parallel
        # in batches
        if self.verbose:
            print "Stopping salt master container..."
        self.stop_master_container()

        self.stop_completed = False
        self.queue = Queue.Queue()
        if instance_no:
            num_threads = 1
        else:
            # this was 20 but make it 1 for right now, 0.7.5 possible bug?
            num_threads = 1
        threads = self.start_threads(num_threads, self.do_stop_jobs)

        if instance_no:
            todo = [ instance_no ]
        else:
            todo = range(1, self.minion_count + 1)
        for i in todo:
            self.queue.put_nowait(i)

        # everything on the queue done?
        self.queue.join()

        # notify threads to go home, and wait for them to do so
        self.stop_completed = True
        for t in threads:
            t.join()

    def delete_cluster(self, instance_no = None):
        if instance_no:
            todo = [ instance_no ]
        else:
            todo = range(1, self.minion_count + 1)
        for i in todo:
            instance_name = self.get_salt_minion_name(i)
            if self.d.container_exists(instance_name):
                if self.verbose:
                    print "Deleting minion container " + str(i)
                try:
                    self.d.delete_container(instance_name)
                except:
                    traceback.print_exc(file=sys.stderr)
                    traceback.print_stack(file=sys.stderr)
                    sys.stderr.write("Failed to delete container " + str(i) + "... continuing\n")

        if not instance_no:
            if self.d.container_exists(self.saltmaster_host):
                if self.verbose:
                    print "Deleting salt master container"
                self.d.delete_container(self.saltmaster_host)

            # NOTE that there are no intermediate images, since the dockerfile
            # has one command and that's it, yay
            if self.d.image_exists('ariel/salt', self.salt_tag):
                if self.verbose:
                    print "Deleting salt image for " + self.salt_tag
                self.d.delete_image(self.d.get_image_id('ariel/salt', self.salt_tag))

    def create_cluster(self, instance_no = None):
        dockerfile_contents = """
FROM ariel/salt:base
RUN cd /src/salt && git fetch --tags && git checkout {tag} && python ./setup.py install --force
CMD python /usr/sbin/pupaas.py && /usr/sbin/sshd -D
"""
        dockerfile_contents = dockerfile_contents.format(tag = self.salt_tag)
        if self.docker_force:
            if instance_no:
                if self.verbose:
                    print "Deleting instance if it exists..."
                self.delete_cluster(instance_no)
            else:
                if self.verbose:
                    print "Deleting cluster if it exists..."
                self.delete_cluster()

        if self.docker_force or not self.d.image_exists('ariel/salt', self.salt_tag):
            if self.verbose:
                print "Building image for salt tag..."
                self.d.build(dockerfile_contents, 'ariel/salt', self.salt_tag)

        image_name = self.d.get_image_name('ariel/salt', self.salt_tag)
        if self.docker_force or not self.d.container_exists(self.saltmaster_host):
            if self.verbose:
                print "Creating salt master container"
            self.d.create(image_name, self.saltmaster_host)

        if instance_no:
            instance_name = self.get_salt_minion_name(instance_no)
            if self.docker_force or not self.d.container_exists(instance_name):
                print "Creating salt minion " + str(instance_no)
                self.d.create(image_name, instance_name)
        else:
            for i in range(1, self.minion_count + 1):
                instance_name = self.get_salt_minion_name(i)
                if self.docker_force or not self.d.container_exists(instance_name):
                    print "Creating salt minion " + str(i)
                    self.d.create(image_name, instance_name)

def usage(message = None):
    if message is not None:
        sys.stderr.write(message)
        sys.stderr.write("\n")
    help_text = """Usage: salt-cluster.py --tag string [--master string] [--prefix string]
                          [--docker string] [--count num] [--port num]
                          [--create] [--force] [--selinux]
                          [--start] [--configure]
                          [--stop] [--delete] [--version] [--help]

This script starts up a salt master container and a cluster of
salt minion containers, with all hostnames and ips added to the
appropriate config files as well as the salt master key fingerprint.

Options:

  --master    (-M)  base name to give salt master instance
                    default: 'saltmaster' (name will be completed
                    by the tag, i.e. 'saltmaster-v0.15.0')
  --minion    (-m)  base name for all salt minion instance names
                    default: 'minion'  (name will be completed by the
                    the instance number followed by the tag, i.e.
                    'minion-25-v0.15.0')
  --docker    (-d)  full path to docker executable
                    default: '/usr/bin/docker'
  --number    (-n)  number of salt minion instances to run
                    default: 100
  --port      (-p)  port number for pupaas on each instance
                    default: 8001
  --create    (-c)  create instances
  --force     (-f)  create containers / images even if they already exist
                    this option can only be used with 'create'
  --selinux   (-s)  mount selinuxfs from host on /selinux ro
                    this is a hack that allows apps in the container
                    to behave as though selinux is disabled (when run
                    with the right libselinux1), even if the kernel
                    has it enabled
                    this option can only be used with 'create'
  --start     (-s)  start instances
  --configure (-C)  configure running instances
  --stop      (-S)  stop running instances
  --delete    (-D)  delete instances, implies 'stop'
  --instance  (-i)  specific instance number in case you want to
                    stop/start/configure/delete only one
  --verbose   (-V)  show progress messages as the script runs
  --version   (-v)  print version information and exit
  --help      (-h)  display this usage message

If multiple of 'create', 'start', configure', 'stop', 'delete' are specified,
each specified option will be done on the cluster in the above order.
"""
    sys.stderr.write(help_text)
    sys.exit(1)

def show_version():
    print "salt-cluster.py " + VERSION
    sys.exit(0)

if __name__ == '__main__':
    saltmaster_host = 'saltmaster'
    saltminion_prefix = 'minion'
    pupaas_port = 8010
    docker = "/usr/bin/docker"
    selinux = False
    create = False
    force = False
    tag = None
    minion_count = None
    start = False
    configure = False
    stop = False
    delete = False
    verbose = False
    instance = None

    try:
        (options, remainder) = getopt.gnu_getopt(sys.argv[1:], "M:m:n:d:p:t:i:HCfsSDVvh", ["master=","minion=", "docker=", "number=", "port=","tag=", "instance=", "selinuxhack", "create", "force", "start", "configure", "stop", "delete", "verbose", "version","help"])
    except getopt.GetoptError as err:
        usage("Unknown option specified: " + str(err))
    for (opt, val) in options:
        if opt in ["-M", "--master"]:
            saltmaster_host = val
        elif opt in ["-m", "--minion" ]:
            saltminion_prefix = val
        elif opt in ["-d", "--docker" ]:
            docker = val
        elif opt in ["-n", "--number" ]:
            if not val.isdigit():
                usage("'number' option requires a number")
            minion_count = int(val)
        elif opt in ["-i", "--instance" ]:
            if not val.isdigit():
                usage("instance must be a number")
            instance = int(val)
        elif opt in ["-p", "--port" ]:
            if not val.isdigit():
                usage("port must be a number")
            pupaas_port = int(val)
        elif opt in ["-t", "--tag" ]:
            tag = val
        elif opt in ["-H", "--selinuxhack" ]:
            selinux = True
        elif opt in ["-c", "--create" ]:
            create = True
        elif opt in ["-C", "--configure" ]:
            configure = True
        elif opt in ["-f", "--force" ]:
            force = True
        elif opt in ["-s", "--start" ]:
            start = True
        elif opt in ["-S", "--stop" ]:
            stop = True
        elif opt in ["-D", "--delete" ]:
            delete = True
            stop = True
        elif opt in ["-V", "--verbose" ]:
            verbose = True
        elif opt in ["-v", "--version" ]:
            show_version()
        elif opt in ["h", "--help" ]:
            usage()
        else:
            usage("Unknown option specified: <%s>" % opt)

    if len(remainder) > 0:
        usage("Unknown option(s) specified: <%s>" % remainder[0])

    if not tag:
        usage("The mandatory option 'tag' was not specified.\n")

    s = Salt_cluster(saltmaster_host, saltminion_prefix, minion_count, pupaas_port, docker, tag, selinux, create, force, verbose)
    if create:
        if not minion_count:
            minion_count = 100
        if verbose:
            print "Creating cluster..."
        s.create_cluster(instance)
    if start:
        if verbose:
            print "Starting cluster..."
        s.start_cluster(instance)
    if configure:
        if verbose:
            print "Configuring cluster..."
        s.configure_cluster(instance)
    if stop:
        if verbose:
            print "Stopping cluster..."
        s.stop_cluster(instance)
    if delete:
        if verbose:
            print "Deleting cluster..."
        s.delete_cluster(instance)
