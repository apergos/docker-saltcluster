class salt::common {
        file { '/etc/salt':
                ensure => 'directory'
        }
}

class salt::minion::conffile ($salt_master = 'salt_master', $master_fingerprint = '') {
        include salt::common      
        file { '/etc/salt/minion':
                ensure => 'present',
                content => template('salt-minion-config.templ')
        }
}

class salt::minion ($ensure = false, $salt_master = 'salt_master', $master_fingerprint = '') {
        include salt::minion::conffile

        # ensure should be one of 'stopped' or 'running'
        service { 'salt-minion':
                provider => 'base',
                ensure => $ensure,
                enable => false,
                subscribe => File['/etc/salt/minion'],
                start => '/etc/init.d/salt-minion start',
                stop => '/etc/init.d/salt-minion stop',
                restart => '/etc/init.d/salt-minion restart',
                status => '/etc/init.d/salt-minion status'
        }
}

class salt::master::conffile {
        include salt::common      
        file { '/etc/salt/master':
                ensure => 'present',
                source => 'puppet:///files/salt-master-config'
        }
}

class salt::master ($ensure = false) {
        include salt::master::conffile

        service { 'salt-master':
                provider => 'base',
                ensure => $ensure,
                enable => false,
                subscribe => File['/etc/salt/master'],
                hasstatus => false,
                start => '/etc/init.d/salt-master start',
                stop => '/etc/init.d/salt-master stop',
                restart => '/etc/init.d/salt-master restart',
                status => '/etc/init.d/salt-master status'
        }
}
