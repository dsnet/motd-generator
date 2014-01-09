# MOTD Generator #

## Introduction ##

Feel free to modify the scripts as you see fit!

![motd](http://code.digital-static.net/motd-generator/raw/tip/doc/motd.png)

## Files ##

* **motd_gen.py**: Script to generate informative MOTD display
* **motd_stat.py**: Statistic gathering daemon for MOTD
* **motd_stat**: Init.d script to start the motd_stat daemon

## Installation ##

```bash
# Be root to install
su

# Download the archive
SRC_VERSION=tip
curl http://code.digital-static.net/motd-generator/get/$SRC_VERSION.tar.gz | tar -zxv

# Move local copy
SRC_ROOT=/usr/local/motd_gen
mv *-motd-generator-* $SRC_ROOT

# Setup the daemon service
ln -s $SRC_ROOT/motd_stat /etc/init.d/
update-rc.d motd_stat defaults
service motd_stat start

# Nuke old MOTD file
rm /etc/motd
touch /etc/motd

# Prevent other modules from print redundant information
sed -i -e 's|\(PrintLastLog\s*\)yes|\1no|' /etc/ssh/sshd_config
sed -i -e 's|\(PrintMotd\s*\)yes|\1no|' /etc/ssh/sshd_config
sed -i -e 's|\(^\s*session.*pam_mail.so\)|#\1|' /etc/pam.d/*
sed -i -e 's|\(^\s*session.*pam_motd.so\)|#\1|' /etc/pam.d/*
sed -i -e 's|\(^\s*session.*pam_lastlog.so\)|#\1|' /etc/pam.d/*
/etc/init.d/ssh restart

# Print the custom MOTD upon every login
echo -e "
if [ -e $MOTD_HOME/motd_gen.py ]; then
\tif [ -x /usr/bin/dircolors ]; then
\t\t$MOTD_HOME/motd_gen.py --color --warn --border
\telse
\t\t$MOTD_HOME/motd_gen.py --border
\tfi
fi" >> /etc/profile
```
