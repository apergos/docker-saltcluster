# fact: salt_key_fingerprint
# only generated on the salt master if the
# master public key is present

Facter.add("salt_key_fingerprint") do
  setcode do
    fingerprint = ""
    if File.exist? "/etc/salt/pki/master/master.pub"
      hostname = Facter.value('hostname')
      output = Facter::Util::Resolution.exec('/usr/local/bin/salt-key -f master.pub ' + hostname)
      output.each_line do |s|
        if s =~ /^master\.pub:  (\S+)/ then
          fingerprint = $1
          break
        end
      end
    end
    fingerprint
  end
end
