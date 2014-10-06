#!/usr/bin/expect

if { $argc != 4 } {
  puts "Usage: $argv0 host password file location\r"
  exit 1
}

set host [lindex $argv 0]
set passwd [lindex $argv 1]
set file [lindex $argv 2]
set location [lindex $argv 3]

spawn scp -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" -pq "$file" "root@$host:$location"
expect {
    "*yes/no*" { send "yes\r" ; exp_continue; }
    "*assword:" { send "$passwd\r"; exp_continue;}
    "100%" {sleep 1;}
}
exit 0
