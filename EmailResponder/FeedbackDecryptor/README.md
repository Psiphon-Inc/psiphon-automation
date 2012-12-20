# Diagnostic Feedback Email Attachment Decryptor

## Setup

### System Configuration

```shell
# Prereqs
sudo apt-get install -y python-pip python-dev libssl-dev swig mongodb
sudo pip install rfc6266 pynliner cssutils BeautifulSoup mako pymongo boto
sudo pip install M2Crypto
```

#### M2Crypto issues

Check that M2Crypto installed properly. Open a Python REPL, and then type `import M2Crypto`. If you receive either of these errors:

```
ImportError: No module named __m2crypto
ImportError: /usr/local/lib/python2.7/dist-packages/M2Crypto-0.21.1-py2.7-linux-x86_64.exx/__m2crypto.so: undefined symbol: SSLv2_method
```

Then `sudo pip uninstall M2Crypto`.

...and then pull the source from here:  
http://chandlerproject.org/Projects/MeTooCrypto

...and follow the instructions for code mods here:  
http://code.google.com/p/grr/wiki/M2CryptoFromSource

#### Create limited-privilege user

The daemon will run as this user.

```shell
sudo useradd -s /bin/false maildecryptor
```

### Get source files

Use Mercurial to get the source files. Also acquire the necessary
configuration files from your secure document repository. These files are: 
`conf.json` and the PEM file (the latter can be extracted from psinet).

## Installing

Use the included script:

```shell
/maildecryptor/maildecryptor_install.sh
```

This will create the directory to run from, copy the files, and set the file
permissions.

## Running

Use the Upstart utilities.

```shell
sudo start maildecryptor
```
