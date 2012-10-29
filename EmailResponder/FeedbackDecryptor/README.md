# Diagnostic Feedback Email Attachment Decryptor

## Get source files

TODO:

* config file, pem, etc.

* make sure chmod a+r


## System Configuration

```shell
# Prereqs
sudo apt-get install -y python-pip
sudo pip install rfc6266
sudo pip install --upgrade pycrypto

# Install the Upstart service file
sudo cp maildecryptor.conf /etc/init/
```

### `chroot` prep

#### Install Jailkit

Get and decompress latest release from here: http://olivier.sessink.nl/jailkit/

```shell
./configure
make
sudo make install
```

#### Create the `chroot` jail

Edit `/etc/jailkit/jk_init.ini` and add this to the top:

```ini
[maildecryptor]
comment = Psiphon maildecryptor
paths = /maildecryptor, /bin/false
includesections = python

[python]
comment = Python plus modules
paths = python, /usr/lib/python2.7, /usr/local/lib/python2.7, /usr/include/python2.7, /usr/share/pyshared
devices = /dev/urandom
includesections = uidbasics, myuidbasics, netbasics

[myuidbasics]
comment = Tweaked to reflect Ubuntu locations... MAY NEED TO BE ALTERED FOR 64-BIT
paths = /lib/i386-linux-gnu/libnsl*, /usr/lib/i386-linux-gnu/libnsl*, /lib/libnss_*, /lib/i386-linux-gnu/libnss_*, /usr/lib/i386-linux-gnu/libnss*, /usr/lib/i386-linux-gnu/nss, /etc/nsswitch.conf, /etc/ld.so.conf
```

Create the `chroot` (will take a while):

```shell
sudo mkdir -p /var/chroot/maildecryptor
sudo jk_init -j /var/chroot/maildecryptor maildecryptor
```

Create the user to run as.

```shell
sudo useradd -s /bin/false maildecryptor
sudo jk_jailuser -v --shell=/bin/false --jail=/var/chroot/maildecryptor maildecryptor maildecryptor
```

#### TODO

##### Get the Upstart chroot working.

This works:

```shell
sudo chroot --userspec=maildecryptor:maildecryptor /var/chroot/maildecryptor python /maildecryptor/maildecryptor_runner.py
```

And so does Upstart without `chroot=`. But not with it. And not with `setuid` or `start-stop-daemon`.

##### Other

Make note about running `jk_update` periodically (after `apt-get update`).


## TODO:

### README stuff

- Where should the source files be copied?
- What user should the daemon run as?

### Code stuff

- Chinese/Farsi characters in subject okay?
