class salt::common {
        file { '/etc/salt':
                ensure => 'directory'
        }
}

class salt::minion ($ensure = false, $salt_master = 'salt_master', $master_fingerprint = '') {
        include salt::common      
        file { '/etc/salt/minion':
                ensure => 'present',
                content => template('salt-minion-config.templ')
        }

        # ensure should be one of 'stopped' or 'running'
        service { 'salt-minion':
                ensure => $ensure,
                enable => false,
                subscribe => File['/etc/salt/minion']
        }
}

class salt::master ($ensure = false) {
        include salt::common      
        file { '/etc/salt/master':
                ensure => 'present',
                source => 'puppet:///files/salt-master-config'
        }
        service { 'salt-master':
                ensure => $ensure,
                enable => false,
                subscribe => File['/etc/salt/master']
        }
}
