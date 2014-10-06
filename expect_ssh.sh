#!/usr/bin/expect
if { $argc != 3 } {
  puts "Usage: $argv0 host password command\r"
  exit 1
}

set timeout 60
set host [lindex $argv 0]
set passwd [lindex $argv 1]
set cmd [lindex $argv 2]

spawn ssh -q -l root -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" $host $cmd
expect {
    "*yes/no*" { send "yes\r" ; exp_continue; }
    "*assword:" { send "$passwd\r"; exp_continue;}
    "~#" {send "logout\r";}
}
exit 0

