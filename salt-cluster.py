import sys
import subprocess
import httplib
import getopt
import json
import socket
import Queue
import threading
import traceback
import time
import re

# script to start a salt master via docker, fix up minion
# configs and start salt clients via docker, get all the
# hostnames and ips and populate the relevant files
# (/etc/hosts, etc) appropriately

VERSION = "0.1.8"

class SELinux(object):
    """
    in case you're running a specific ubuntu container
    under an os with selinux enabled, this lets deal
    with that so things like sshd don't break horribly
    """
    @staticmethod
    def find_mount():
        'locate the selinux fs mount point via proc'
        with open('/proc/mounts', 'r') as mountinfo:
            mounts = mountinfo.read().splitlines()
        for entry in mounts:
            if entry.startswith('selinuxfs '):
                _, mntpoint, _ = entry.split(' ', 2)
                return mntpoint
        return None

class DockerError(Exception):
    """
    placeholder for some sort of interesting
    exception handling, to be expanded someday
    """
    pass


class LocalHTTPConnection(httplib.HTTPConnection):
    """
    our own httpconnection class with
    a timeout on the connect call;
    if the module class had it we wouldn't have to
    do this horrible workaround
    """
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
    """
    build or run a docker image
    """
    def __init__(self, docker, selinux_hack):
        self.docker = docker
        self.selinux_hack = selinux_hack
        if selinux_hack:
            self.host_selinuxfs = SELinux.find_mount()
        else:
            self.host_selinuxfs = None

    def build(self, dockerfile_contents, image_repo, image_tag):
        """
        build an image from the specified docker
        contents with a canonical name constructed
        from the image repo name and the
        os and salt version info in the image tag
        """
        # we only keep the last layer so that we can purge easily
        command = [self.docker, 'build', '--rm', '-t',
                   get_image_name(image_repo, image_tag), '-']
        stdoutdata = None
        stderrdata = None
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            stdoutdata, stderrdata = proc.communicate(dockerfile_contents)
            if proc.returncode:
                if stderrdata:
                    sys.stderr.write(stderrdata)
                if stdoutdata:
                    sys.stderr.write(stdoutdata)
                raise DockerError("Error building docker image %s (%s)\n"
                                  % (get_image_name(image_repo, image_tag),
                                     stderrdata))
        except Exception:
            sys.stderr.write('Failed to build docker image ' +
                             get_image_name(image_repo, image_tag) + "\n")
            raise

    # docker run -i -t -v /sys/fs/selinux:/selinux:ro imagename
    def create(self, image_name, container_name=None):
        """
        create a container based on a specified image;
        this is the equivalent of the docker-run command
        this will also provide the selinux volume to
        the container, if requested
        """
        config = {"Hostname":"", "Domainname":"", "User":"",
                  "Memory":0, "MemorySwap":0, "CpuShares":0,
                  "AttachStdin":True, "AttachStdout":True, "AttachStderr":True,
                  "PortSpecs":None, "ExposedPorts":{},
                  "Tty":True, "OpenStdin":True, "StdinOnce":True,
                  "Env":None, "Cmd":None, "Dns":None,
                  "Image":image_name,
                  "VolumesFrom":"",
                  "WorkingDir":"", "Entrypoint":None,
                  "NetworkDisabled":False}

        if self.host_selinuxfs:
            config['Volumes'] = {"/selinux": {}}

        config_string = json.dumps(config)
        url = "/containers/create"
        if container_name:
            url = url + "?name=" + container_name

        get_url(url, "POST", config_string)


class PupaasClient(object):
    """
    the dreaded 'puppet as a service' class
    this knows how to talk to the pupaas server
    and do very simple things like applying a
    manifest or retrieving a fact
    """
    def __init__(self, port):
        self.port = port

    def apply_manifest(self, instance_name, manifest):
        """
        apply a puppet manifest via puppet as a service
        (it must already exist on the instance in the
        appropriate location)
        """
        url = '/apply/' + manifest
        method = 'POST'
        try:
            http_conn = httplib.HTTPConnection(instance_name,
                                              timeout=20, port=self.port)
        except Exception:
            raise httplib.HTTPException(
                "failed to establish http connection to " +
                instance_name)

        http_conn.request(method, url, headers={
            "User-Agent": "run_salt_client.py/0.0 (salt testbed configurator)"})
        try:
            response = http_conn.getresponse(buffering=True)
        except httplib.HTTPException:
            raise httplib.HTTPException('failed to apply ' + manifest + ' on ' +
                                instance_name)

        data = response.read()
        if response.status == 200 or response.status == 204:
            return True
        else:
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to apply ' + manifest + ' on ' +
                          instance_name, " with response code " +
                          str(response.status))

    def add_manifest(self, instance_name, manifest, contents):
        """
        add a puppet manifest to the instance, with the
        specified contents, via puppet as a service
        """
        url = '/manifest/' + manifest
        method = 'DELETE'
        try:
            http_conn = httplib.HTTPConnection(instance_name, timeout=20,
                                              port=self.port)
        except Exception:
            raise httplib.HTTPException(
                "failed to establish http connection to " + instance_name)

        http_conn.request(method, url, headers={
            "User-Agent": "run_salt_client.py/0.0 (salt testbed configurator)"})
        response = http_conn.getresponse(buffering=True)
        data = response.read()
        if (response.status != 200 and response.status != 404 and
            response.status != 201 and response.status != 204):
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to delete ' + manifest + ' on ' +
                          instance_name, " with response code " +
                          str(response.status))

        url = '/manifest/' + manifest
        method = 'PUT'

        http_conn.request(
            method, url, contents,
            headers={"User-Agent":
                     "run_salt_client.py/0.0 (salt testbed configurator)"})
        response = http_conn.getresponse(buffering=True)
        data = response.read()
        if (response.status == 200 or response.status == 204 or
            response.status == 201):
            return True
        else:
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to put ' + manifest + ' on ' +
                          instance_name, " with response code " +
                          str(response.status))

    def get_fact(self, instance_name, fact):
        'get a puppet fact from the instance via puppet as a service'
        url = '/fact/' + fact
        method = 'GET'
        try:
            http_conn = httplib.HTTPConnection(instance_name,
                                              timeout=20, port=self.port)
        except Exception:
            raise httplib.HTTPException(
                "failed to establish http connection to " + instance_name)

        http_conn.request(
            method, url,
            headers={"User-Agent":
                     "run_salt_client.py/0.0 (salt testbed configurator)"})
        response = http_conn.getresponse(buffering=True)
        data = response.read()
        if response.status == 200:
            return data.rstrip()
        else:
            if data:
                sys.stderr.write(data + "\n")
            raise IOError('failed to retrieve fact ' + fact + ' on ' +
                          instance_name, " with response code " +
                          str(response.status))


class SaltMaster(object):
    """
    manage configuration, starting and stopping
    a salt master container
    """
    def __init__(self, prefix, tag_text, puppet, host_selinuxfs):
        self.tag = get_salt_tag_from_text("1:" + tag_text)
        self.host_selinuxfs = host_selinuxfs
        self.hostname = self.get_name(prefix)
        self.fingerprint = None
        self.ip_addr = None
        self.ip_host = {}
        self.puppet = puppet

    def start_salt(self):
        'start salt on the master container'
        # set up config file first, so we don't hit puppet bug
        # 7165 (ensure running causes start, refresh from file
        # update causes restart, fixed in puppet 3.2)
        # the salt master doesn't do well withthe quick start-restart
        contents = ("import 'salt.pp'\n"
                    "class { 'salt::master::conffile':}\n")
        self.puppet.add_manifest(self.ip_addr,
                                 'manifests/salt_master_config.pp', contents)
        self.puppet.apply_manifest(self.ip_addr,
                                   'manifests/salt_master_config.pp')
        contents = ("import 'salt.pp'\n"
                    "class { 'salt::master': ensure => 'running' }\n")
        self.puppet.add_manifest(self.ip_addr,
                                 'manifests/salt_master_start.pp', contents)
        self.puppet.apply_manifest(self.ip_addr,
                                   'manifests/salt_master_start.pp')

    def stop_salt(self):
        'stop salt on the master'
        contents = ("import 'salt.pp'\n"
                    "class { 'salt::master': ensure => 'stopped' }\n")
        self.puppet.add_manifest(self.hostname,
                                 'manifests/salt_master_stop.pp', contents)
        self.puppet.apply_manifest(self.hostname,
                                   'manifests/salt_master_stop.pp')

    def configure_container(self):
        """
        configure the salt master container and save
        its key fingerprint (minions need this)
        """

        # get salt master ip
        if not self.ip_addr:
            self.ip_addr = get_ip(self.hostname)
            self.ip_host[self.hostname] = self.ip_addr

        self.start_salt()
        # need this so master can generate keys before we ask for them
        time.sleep(5)
        self.fingerprint = self.get_salt_key_fingerprint(self.ip_addr)

    def get_salt_key_fingerprint(self, instance_name):
        """
        get the salt master key fingeprint
        via puppet as a service on the container
        """
        result = self.puppet.get_fact(instance_name, 'salt_key_fingerprint')
        return result.strip("\n")

    def start_container(self):
        'start the salt master container'
        if not is_running(self.hostname):
            start_container(self.hostname, self.host_selinuxfs)

    def get_name(self, prefix):
        """
        get the name of the salt master container
        given the prefix (basename) of the container
        the format looks like ariel/salt:precise-v0.17.1-git
        """
        if not self.tag:
            return None
        return ("-".join([prefix, self.tag['image'],
                          sanitize(self.tag['version']), self.tag['package']]))

    def stop_container(self):
        'stop the salt master container'
        if is_running(self.hostname):
            stop_container(self.hostname)


class SaltCluster(object):
    """
    manage creation, startup and shutdown of a cluster of salt
    containers, including mixed salt versions and ubuntu
    distros
    """
    def __init__(self, master_prefix, saltminion_prefix, paas_port,
                 docker_path, minion_tags_text, master_tag,
                 selinux, docker_create, docker_force, verbose):
        self.repo = 'ariel/salt'
        self.verbose = verbose
        self.saltminion_prefix = saltminion_prefix
        self.minion_tags_text = minion_tags_text
        self.minion_tags = self.get_minion_tags()
        self.docker_path = docker_path
        self.docker_create = docker_create
        if not self.docker_create:
            self.puppet = PupaasClient(paas_port)
        else:
            self.puppet = None
        self.minion_count = None
        self.docker_force = docker_force
        self.docker = Docker(docker_path, selinux)
        self.minion_ips_hosts = {}
        self.minion_count = self.get_minion_count()
        self.master = SaltMaster(master_prefix, master_tag,
                                 self.puppet, selinux)
        self.queue = None
        self.stop_completed = False
        self.config_completed = False

    def get_minion_tags(self):
        """
        given a text string like this:
        3:precise:v0.17.1:git,1:trusty:2014.1.10+ds-1_all:deb
        turn it into a dict of tags describing each group of
        minions to be set up or managed, in this case
        3 builds from the precise image with v0.17.1 from git
        and 1 trusty build using the deb package 2014.1.10_ds-1
        """
        salt_tags = []
        if not self.minion_tags_text:
            return
        for entry in self.minion_tags_text.split(","):
            salt_tags.append(get_salt_tag_from_text(entry))
        return salt_tags

    def get_minion_count(self):
        """
        get the total number of minions by looking at
        the minion tags and adding up the counts per tag
        """
        if not self.minion_tags:
            return None
        count = 0
        for entry in self.minion_tags:
            count = count + int(entry['minions'])
        return count

    def start_salt_minion(self, instance_name):
        'start salt on the specified instance'
        contents = "import 'salt.pp'\nclass { 'salt::minion::conffile': salt_master => '%s', master_fingerprint => '%s' }\n" % (self.master.hostname, self.master.fingerprint)
        self.puppet.add_manifest(instance_name,
                                 'manifests/salt_minion_config.pp',
                                 contents)
        self.puppet.apply_manifest(instance_name,
                                   'manifests/salt_minion_config.pp')

        contents = "import 'salt.pp'\nclass { 'salt::minion': ensure => 'running', salt_master => '%s', master_fingerprint => '%s' }\n" % (self.master.hostname, self.master.fingerprint)
        self.puppet.add_manifest(instance_name,
                                 'manifests/salt_minion_start.pp',
                                 contents)
        self.puppet.apply_manifest(instance_name,
                                   'manifests/salt_minion_start.pp')

    def stop_salt_minion(self, instance_name):
        'stop salt on the specified instance'
        contents = "import 'salt.pp'\nclass { 'salt::master': ensure => 'stopped', salt_master => '%s', master_fingerprint => '%s' }\n"% (self.master.hostname, self.master.fingerprint)
        self.puppet.add_manifest(instance_name,
                                 'manifests/salt_minion_stop.pp',
                                 contents)
        self.puppet.apply_manifest(instance_name,
                                   'manifests/salt_minion_stop.pp')

    def get_salt_minion_name(self, instance_number):
        """
        get the container name for the salt
        minion with the given instance number;
        these names are generated from the tag
        covering the instance numbers
        """
        if not self.minion_tags:
            return None
        count = 0
        for entry in self.minion_tags:
            count = count + int(entry['minions'])
            if count >= instance_number:
                return ("-".join([self.saltminion_prefix, str(instance_number),
                                  entry['image'], sanitize(entry['version']),
                                  entry['package']]))
        return None

    def start_minion_container(self, instance_number):
        """
        start the minion container for the specified instance;
        if it is already running it will be stopped first
        """
        self.stop_minion_container(instance_number)

        instance_name = self.get_salt_minion_name(instance_number)
        start_container(instance_name, self.docker.host_selinuxfs)

    def start_cluster(self, instance_no=None):
        """
        start the salt master container followed
        by the minion containers
        """
        display(self.verbose, "Starting salt master container...")
        self.master.start_container()

        if instance_no:
            todo = [instance_no]
        else:
            todo = range(1, self.minion_count + 1)

        for i in todo:
            display(self.verbose, "Starting minion container " + str(i) + "...")
            self.start_minion_container(i)

    def configure_minion_container(self, instance_name, ip_addr):
        """
        update the etc hosts file on the specified container
        (so it knows the ip address of the master, container
        ips are generated anew every time they are restarted)
        and then start the salt minion on it
        """
        update_etc_hosts(instance_name, self.master.ip_host)
        self.start_salt_minion(ip_addr)

    def do_config_jobs(self):
        """
        get jobs off the queue (a minion
        instance number plus an ip) and update their
        /etc/hosts file of that minion with the
        specified ip, until another thread tells me I
        am done (by setting the stop_completed var)
        """
        while not self.config_completed:
            # fixme when do we know there will be no
            # more jobs for us on the queue?

            try:
                (i, instance_name, ip_addr) = self.queue.get(True, 1)
            except Queue.Empty:
                continue

            display(self.verbose, "Configuring salt minion " + str(i) +"...")
            try:
                self.configure_minion_container(instance_name, ip_addr)
            except Exception:
                traceback.print_exc(file=sys.stderr)
#                traceback.print_stack(file=sys.stderr)
                sys.stderr.write("problem configuring container " +
                                 str(i) + ", continuing\n")
            self.queue.task_done()

    def configure_cluster(self, instance_no=None):
        """
        configure the salt master
        update the /etc/hosts on the master with ips
          of all minions
        update /etc/hosts on each minion with the master ip
        """
        # configuration is slow (puppet apply, salt key generation
        # etc) so do concurrent in batches
        display(self.verbose, "Pre-configuring salt master...")
        self.master.configure_container()

        self.config_completed = False
        self.queue = Queue.Queue()
        if instance_no:
            num_threads = 1  # :-P
        else:
            # maybe a bug.  serious issues with multiple threads
            num_threads = 1
        threads = start_threads(num_threads, self.do_config_jobs)

         # collect all the ips, we need them for master /etc/hosts
        for i in range(1, self.minion_count + 1):
            instance_name = self.get_salt_minion_name(i)
            ip_addr = get_ip(instance_name)
            self.minion_ips_hosts[instance_name] = ip_addr

        if instance_no:
            todo = [instance_no]
        else:
            todo = range(1, self.minion_count + 1)

        for i in todo:
            instance_name = self.get_salt_minion_name(i)
            update_etc_hosts(instance_name, self.master.ip_host)
            self.queue.put_nowait((i, instance_name,
                                   self.minion_ips_hosts[instance_name]))

        # everything on the queue done?
        self.queue.join()

        # notify threads to go home, and wait for them to do so
        self.config_completed = True
        for thr in threads:
            thr.join()

        display(self.verbose, "Updating /etc/hosts on salt master...")
        update_etc_hosts(self.master.hostname, self.minion_ips_hosts)

    def stop_minion_container(self, instance_number):
        'stop the specified salt minion container'
        instance_name = self.get_salt_minion_name(instance_number)
        if is_running(instance_name):
            stop_container(instance_name)

    def do_stop_jobs(self):
        """
        get jobs off the queue (a minion
        instance number) and stop the specified
        container until another thread tells me I
        am done (by setting the stop_completed var)
        """
        while not self.stop_completed:
            try:
                i = self.queue.get(True, 1)
            except Queue.Empty:
                continue

            display(self.verbose, "Stopping salt minion container "
                    + str(i) + "...")
            try:
                self.stop_minion_container(i)
            except Exception:
                sys.stderr.write("problem stopping container " +
                                 str(i) + ", continuing\n")
            self.queue.task_done()

    def stop_cluster(self, instance_no=None):
        """
        stop the cluster of salt containers,
        doing the master first and then the minions
        (I wonder if we should do this the other way around
        now that I think about it)
        """
        # because we give the docker stop command several seconds to
        # complete and we are impatient, run these in parallel
        # in batches
        display(self.verbose, "Stopping salt master container...")
        self.master.stop_container()

        self.stop_completed = False
        self.queue = Queue.Queue()
        if instance_no:
            num_threads = 1
        else:
            # this was 20 but make it 1 for right now, 0.7.5 possible bug?
            num_threads = 1
        threads = start_threads(num_threads, self.do_stop_jobs)

        if instance_no:
            todo = [instance_no]
        else:
            todo = range(1, self.minion_count + 1)
        for i in todo:
            self.queue.put_nowait(i)

        # everything on the queue done?
        self.queue.join()

        # notify threads to go home, and wait for them to do so
        self.stop_completed = True
        for thr in threads:
            thr.join()

    def delete_cluster(self, instance_no=None):
        """
        delete containers for this cluster
        """
        if instance_no:
            todo = [instance_no]
        else:
            todo = range(1, self.minion_count + 1)
        for i in todo:
            instance_name = self.get_salt_minion_name(i)
            if container_exists(instance_name):
                display(self.verbose, "Deleting minion container " + str(i))
                try:
                    delete_container(instance_name)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    traceback.print_stack(file=sys.stderr)
                    sys.stderr.write("Failed to delete container " +
                                     str(i) + "... continuing\n")

        if not instance_no:
            if container_exists(self.master.hostname):
                display(self.verbose, "Deleting salt master container")
                delete_container(self.master.hostname)

    def purge_cluster(self, instance_no=None):
        """
        remove all images connected
        with this cluster, if no instance number is supplied
        """
        if instance_no is None:

            # NOTE that there are no intermediate images (check this!)
            for entry in self.minion_tags:
                if image_exists(self.repo, entry):
                    display(self.verbose,
                            "Deleting minion image %s" %
                            get_image_name(self.repo, entry))
                    delete_image(get_image_id(self.repo, entry))

        if image_exists(self.repo, self.master.tag):
            display(self.verbose, "Deleting master image %s" %
                    get_image_name(self.repo, self.master.tag))
            delete_image(get_image_id(self.repo, self.master.tag))

    def gen_dockerfile_from_tag(self, tag):
        """
        generate appropriate content for a salt minion dockerfile
        given the ubuntu version, the version of salt and the
        package source (git or deb) desired.
        """
        deb_path = "salt/debs"
        dockerfile_contents = "FROM %s:{image}base\n" % self.repo
        if tag['package'] == 'git':
            dockerfile_contents += """
RUN cd /src/salt && git fetch --tags && git checkout {version} && python ./setup.py install --force
CMD python /usr/sbin/pupaas.py && /usr/sbin/sshd -D
"""
        elif tag['package'] == 'deb':
            dockerfile_contents += """
RUN dpkg -i /root/salt/salt-common_{version}.deb

# skip any postinst steps, we don't trust them

# minion
RUN dpkg --unpack /root/salt/salt-minion_{version}.deb
RUN rm -f /var/lib/dpkg/info/salt-minion.postinst
RUN dpkg --configure salt-minion

# master
RUN dpkg --unpack /root/salt/salt-master_{version}.deb
RUN rm -f /var/lib/dpkg/info/salt-master.postinst
RUN dpkg --configure salt-master

# do these here, these files may get overwritten by deb install :-(
# remove the files first in case they are symlinks to upstart job
RUN rm -f /etc/init.d/salt-master && cp /root/salt-master /etc/init.d/salt-master
RUN rm -f /etc/init.d/salt-minion && cp /root/salt-minion /etc/init.d/salt-minion
RUN chmod 755 /etc/init.d/salt-master /etc/init.d/salt-minion

RUN mkdir -p /usr/local/bin
RUN if [ -f /usr/bin/salt ]; then ln -s /usr/bin/salt* /usr/local/bin/; fi

CMD python /usr/sbin/pupaas.py && /usr/sbin/sshd -D
"""
        dockerfile_contents = dockerfile_contents.format(
            image=tag['image'], version=tag['version'], path=deb_path)

        return dockerfile_contents

    def get_tag(self, instance_no):
        """
        find the tag (ubuntu version, salt version,
        package type) that governs a specified instance
        number
        """
        if instance_no is None:
            return None
        count = 0
        for entry in self.minion_tags:
            count = count + int(entry['minions'])
            if count >= instance_no:
                return entry
        return None

    def create_cluster(self, instance_no=None):
        """
        create the salt master image and container
        and the salt minion image and containers,
        deleting pre-existing ones if requested
        """
        if instance_no is None:
            if self.docker_force:
                display(self.verbose, "Deleting cluster if it exists...")
                self.delete_cluster()
            tags_todo = self.minion_tags
        else:
            if self.docker_force:
                display(self.verbose, "Deleting instance if it exists...")
                self.delete_cluster(instance_no)
            tags_todo = [self.get_tag(instance_no)]

        # don't build the same image twice
        created_images = []
        for entry in tags_todo:
            # don't build the same image twice
            if get_image_name(self.repo, entry) not in created_images:

                if self.docker_force or not image_exists(self.repo, entry):
                    minion_image_name = get_image_name(self.repo, entry)
                    display(self.verbose, "Building image for minion, %s" %
                            minion_image_name)
                    dockerfile_contents = self.gen_dockerfile_from_tag(entry)
                    self.docker.build(dockerfile_contents, self.repo, entry)
                    created_images.append(minion_image_name)

        master_image_name = get_image_name(self.repo, self.master.tag)
        if self.docker_force or not image_exists(self.repo, self.master.tag):
            display(self.verbose, "Building image for master, %s" %
                    master_image_name)
            dockerfile_contents = self.gen_dockerfile_from_tag(self.master.tag)
            self.docker.build(dockerfile_contents, self.repo, self.master.tag)
            created_images.append(get_image_name(self.repo, self.master.tag))
        if self.docker_force or not container_exists(self.master.hostname):
            display(self.verbose, "Creating salt master container %s" %
                    self.master.hostname)
            self.docker.create(master_image_name, self.master.hostname)

        if instance_no is None:
            to_do = range(1, self.minion_count + 1)
        else:
            to_do = [instance_no]

        for instance_no in to_do:
            self.create_minion_container(instance_no)

    def create_minion_container(self, instance_no):
        """
        create the specified minion container
        note that the image from which it will be
        created is pre-determined by the minion_tags
        attribute
        """
        minion_instance_name = self.get_salt_minion_name(instance_no)
        if self.docker_force or not container_exists(minion_instance_name):
            display(self.verbose, "Creating salt minion container " + str(instance_no))
            self.docker.create(get_image_name(self.repo,
                                              self.get_tag(instance_no)),
                               minion_instance_name)


def sanitize(text):
    'make text safe for use as container name'
    return re.sub("[^a-zA-Z0-9_.\-]", "", text)

def get_image_id(image_repo, image_tag):
    """
    given the image repo and tag (where
    tag cotains info about the ubuntu version, salt
    version and package type of the image),
    retrieve the image id from docker via the api
    and return it
    """
    image_name = get_image_name(image_repo, image_tag)
    url = "/images/json"
    output = get_url(url)
    for entry in output:
        if (entry['Id'].startswith(image_name) or
            image_name in entry['RepoTags']):
            return entry['Id']
    return False

def display(verbose, message):
    """
    placeholder to display a message with special
    formatting if it's verbose; for now, it just
    prints it
    """
    if verbose:
        print message

def update_etc_hosts(instance_name, hosts_ips):
    """
    for the given instance name, update
    the /etc/hosts file with the specified
    hosts and ip addresses
    """
    # we will hack the file listed in HostsPath for the container. too bad
    hosts_file = get_hosts_file(instance_name)
    if not hosts_file:
        return
    header = ["# saltcluster additions"]

    with open(hosts_file, 'r+b') as hosts:
        while 1:
            # read each line
            entry = hosts.readline()
            if not entry:
                break
            # toss any entries made by previous runs
            if entry.startswith('# saltcluster additions'):
                header = []
                hosts.truncate()
                break

    salt_entries = [hosts_ips[name] + "   " + name for name in hosts_ips]
    contents = "\n".join(header + salt_entries) + "\n"

    with open(hosts_file, 'a') as hosts:
        hosts.write(contents)


def start_container(instance_name, host_selinuxfs):
    """
    start a container via the docker api,
    including a mount of the dreaded selinux fs
    if necessary
    """
    url = "/containers/" + instance_name + "/start"
    config = {#"Binds":["/sys/fs/selinux:/selinux:ro"],
              "ContainerIDFile":"",
              "LxcConf":[],
              "Privileged":False,
              "PortBindings":{},
              "Links":None,
              "PublishAllPorts":False
          }

#    if host_selinuxfs:
#        config['Binds'] = [host_selinuxfs + ':/selinux:ro']

    config_string = json.dumps(config)
    get_url(url, "POST", config_string)

def is_running(instance_name):
    'check if the specified container is running'
    return container_exists(instance_name, check_all=False)

def start_threads(count, target):
    """
    start the specified number of threads
    to execute the specified function ('target')
    """
    threads = []
    for _ in range(1, count+1):
        thr = threading.Thread(target=target)
        thr.daemon = True
        thr.start()
        threads.append(thr)
    return threads

def get_salt_tag_from_text(text):
    """
    convert count and version information for
    a minion, like     3:precise:v0.17.1:git
    into a tag with each field nicely labelled
    """
    fields = text.split(':')
    return {
        'minions': fields[0], # minion count
        'image': fields[1],   # image base eg precise, lucid etc
        'version': fields[2], # salt version eg v0.17.1
        'package': fields[3]  # package type eg git deb...
    }

def container_exists(container_name, check_all=True):
    """
    check if the specified container exists;
    if check_all is False then only running
    containers will be checked to see if it
    is among them
    """
    url = "/containers/json"
    if check_all:
        url = url + "?all=1"
    output = get_url(url)
    for entry in output:
        if (entry['Id'].startswith(container_name) or
            container_name in [n[1:] for n in entry['Names']]):
            return True
    return False

def get_hosts_file(instance_name):
    """
    for a specified container, find the name
    of the /etc/hosts file; you would be surprised how
    annoying docker is about allowing updates to this
    file (hint: it doesn't)
    """
    url = "/containers/" + instance_name + "/json"
    output = get_url(url)
    result = output['HostsPath'].strip()
    if not result:
        sys.stderr.write('got: ' + output + "\n")
        raise DockerError('Failed to get hosts file name for ' + instance_name)
    return result

def is_hex_digits(string):
    """
    return true if the string provided consists
    only of hex digits
    """
    return all(c in '0123456789abcdefABCDEF' for c in string)

def stop_container(instance_name):
    'stop the specified container'
    # FIXME we should just shoot the processes on these containers
    url = "/containers/" + instance_name + "/stop?t=5"
    get_url(url, 'POST')

def delete_container(instance_name):
    'delete the specified container'
    url = "/containers/" + instance_name
    get_url(url, 'DELETE')

def delete_image(instance_name):
    'delete the specified image'
    url = "/images/" + instance_name
    get_url(url, 'DELETE')

def image_exists(image_repo, image_tag):
    """
    given the image repo name and the
    image tag (os version and salt package info),
    check if the image exists already
    """
    image_name = get_image_name(image_repo, image_tag)
    url = "/images/json"
    output = get_url(url)
    for entry in output:
        if (entry['Id'].startswith(image_name) or
            image_name in entry['RepoTags']):
            return True
    return False

def get_image_name(repo, tag):
    """
    given the image repo name and
    the image tag (os version and salt package info),
    return the name of the image
    (these names are fixed based on the above info)
    """
    # only a-zA-Z0-9._- allowed in image names, package names can have + so remove that
    version_sanitized = tag['version'].replace('+', '_')
    return "%s:%s-%s-%s" % (repo, tag['image'], version_sanitized, tag['package'])

def get_ip(instance_name):
    """
    get the ip address of the specified container,
    if it is running (if not, no ip address is
    assigned and an exception will be raised)
    """
    url = "/containers/" + instance_name + "/json"
    output = get_url(url)
    result = output['NetworkSettings']['IPAddress'].strip()
    if not result or not is_ip(result):
        # fixme output is a dict not a string d'oh
        sys.stderr.write('got: ' + output + "\n")
        raise DockerError('Failed to get ip of ' + instance_name)
    return result

# fixme this is only ipv4... which is fine for right now
def is_ip(string):
    'check that a text string is an ip address'
    try:
        fields = string.split('.')
    except Exception:
        return False
    if not len(fields) == 4:
        return False
    for octet in fields:
        if not octet.isdigit():
            return False
        if int(octet) > 255:
            return False
    return True

def get_url(url, method='GET', content=None):
    """
    retrieve a specified docker api url
    via the local socket
    """
    try:
        http_conn = LocalHTTPConnection("/var/run/docker.sock", timeout=20)
    except Exception:
        print "failed to establish http connection to localhost for docker"
        raise

    hdr = {"User-Agent": "test-docker-api.py"}
    if content:
        hdr["Content-Type"] = "application/json"

    http_conn.request(method, url, body=content, headers=hdr)
    response = http_conn.getresponse(buffering=True)
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
        raise IOError('failed to get url ' + url,
                      " with response code " + str(response.status))

def usage(message=None):
    """
    display a helpful usage message with
    an optional introductory message first
    """
    if message is not None:
        sys.stderr.write(message)
        sys.stderr.write("\n")
    help_text = """Usage: salt-cluster.py --miniontags string --mastertag string
                          [--master string] [--prefix string]
                          [--docker string] [--port num]
                          [--create] [--force] [--selinux]
                          [--start] [--configure] [--stop]
                          [--delete] [--purge] [--version] [--help]

This script starts up a salt master container and a cluster of
salt minion containers, with all hostnames and ips added to the
appropriate config files as well as the salt master key fingerprint.

Options:

  --miniontags (-t) string specifying how many minions from which
                    base image and running which version of salt should
                    be started up, in the following format:
                    <num_minions>:<image>:<saltvers>:<ptype>[,<num_minions>:<image>:<saltvers>:<ptype>...]
                    example: 3:precise:v0.17.1:git,2:trusty:0.17.5+ds-1_all:deb
                    version for git repos must be the tag or branch
                    version for debs must be the string such that
                    salt-common_<version>.deb is the package name to be used
  --mastertag (-T)  string specifying which base image and running which
                    version of salt should be used for the master,
                    in the following format:
                    <image>:<saltvers>:<ptype>
                    examples: precise:v0.17.5:git or trusty:2014.1.10+ds-1:deb
  --master    (-M)  base name to give salt master instance
                    default: 'master' (name will be completed
                    by the image version, tag and packagetype,  i.e.
                    'master-precise-v0.15.0-git')
  --minion    (-m)  base name for all salt minion instance names
                    default: 'minion'  (name will be completed by the
                    the instance number followed by the image version, tag
                    and packagetype, i.e. 'minion-25-precise-v0.15.0-git')
  --docker    (-d)  full path to docker executable
                    default: '/usr/bin/docker'
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
  --purge     (-p)  purge images, implies 'stop' and 'delete'
  --instance  (-i)  specific instance number in case you want to
                    stop/start/configure/delete only one
  --verbose   (-V)  show progress messages as the script runs
  --version   (-v)  print version information and exit
  --help      (-h)  display this usage message

If multiple of 'create', 'start', configure', 'stop', 'delete', 'purge'
are specified, each specified option will be done on the cluster in the
above order.
"""
    sys.stderr.write(help_text)
    sys.exit(1)

def show_version():
    'show the version of this script'
    print "salt-cluster.py " + VERSION
    sys.exit(0)

def handle_action(cluster, instance, actions, verbose):
    """
    execute the actions marked as true,
    in the proper order
    """
    if actions['create']:
        if verbose:
            print "Creating cluster..."
        cluster.create_cluster(instance)
    if actions['start']:
        if verbose:
            print "Starting cluster..."
        cluster.start_cluster(instance)
    if actions['configure']:
        if verbose:
            print "Configuring cluster..."
        cluster.configure_cluster(instance)
    if actions['stop']:
        if verbose:
            print "Stopping cluster..."
        cluster.stop_cluster(instance)
    if actions['delete']:
        if verbose:
            print "Deleting cluster..."
        cluster.delete_cluster(instance)
    if actions['purge']:
        if verbose:
            print "Purging cluster..."
        cluster.purge_cluster(instance)

def main():
    'main entry point, does all the work'
    saltmaster_prefix = 'master'
    saltminion_prefix = 'minion'
    pupaas_port = 8010
    docker = "/usr/bin/docker"
    selinux = False
    create = False
    force = False
    miniontags = None
    mastertag = None
    start = False
    configure = False
    stop = False
    delete = False
    purge = False
    verbose = False
    instance = None

    try:
        (options, remainder) = getopt.gnu_getopt(
            sys.argv[1:], "M:m:d:p:P:t:T:i:HCfsSDVvh",
            ["master=", "mastertag=", "minion=", "docker=",
             "port=", "miniontags=", "matertag=",
             "instance=", "selinuxhack", "create",
             "force", "start", "configure", "stop",
             "delete", "purge",
             "verbose", "version", "help"])

    except getopt.GetoptError as err:
        usage("Unknown option specified: " + str(err))
    for (opt, val) in options:
        if opt in ["-M", "--master"]:
            saltmaster_prefix = val
        elif opt in ["-m", "--minion"]:
            saltminion_prefix = val
        elif opt in ["-d", "--docker"]:
            docker = val
        elif opt in ["-i", "--instance"]:
            if not val.isdigit():
                usage("instance must be a number")
            instance = int(val)
        elif opt in ["-p", "--port"]:
            if not val.isdigit():
                usage("port must be a number")
            pupaas_port = int(val)
        elif opt in ["-t", "--miniontags"]:
            miniontags = val
        elif opt in ["-T", "--mastertag"]:
            mastertag = val
        elif opt in ["-H", "--selinuxhack"]:
            selinux = True
        elif opt in ["-c", "--create"]:
            create = True
        elif opt in ["-C", "--configure"]:
            configure = True
        elif opt in ["-f", "--force"]:
            force = True
        elif opt in ["-s", "--start"]:
            start = True
        elif opt in ["-S", "--stop"]:
            stop = True
        elif opt in ["-D", "--delete"]:
            stop = True
            delete = True
        elif opt in ["-p", "--purge"]:
            stop = True
            delete = True
            purge = True
        elif opt in ["-V", "--verbose"]:
            verbose = True
        elif opt in ["-v", "--version"]:
            show_version()
        elif opt in ["h", "--help"]:
            usage()
        else:
            usage("Unknown option specified: <%s>" % opt)

    if len(remainder) > 0:
        usage("Unknown option(s) specified: <%s>" % remainder[0])

    if not miniontags:
        usage("The mandatory option 'miniontags' was not specified.\n")
    if not mastertag:
        usage("The mandatory option 'mastertag' was not specified.\n")

    cluster = SaltCluster(saltmaster_prefix, saltminion_prefix, pupaas_port,
                    docker, miniontags, mastertag, selinux, create,
                    force, verbose)
    actions = {'create': create, 'start': start,
               'configure': configure, 'stop': stop,
               'delete': delete, 'purge': purge}
    handle_action(cluster, instance, actions, verbose)

if __name__ == '__main__':
    main()
