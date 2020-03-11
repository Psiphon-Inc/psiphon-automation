# Diagnostic Feedback Decryptor

This is a collection of services that monitor email and a S3 bucket for
encrypted diagnostic feedback. They then decrypt and store that data, and then
send an email with the data.

## TODO

### Additional items to include in feedback

#### Android

+ output from uname -a or something that shows information about the kernel version and build

## How it works

There are 4 services:
* `s3decryptor`: Reads encrypted feedback packages from S3, parses and processes them, and stores the data in mongodb.
* `autoresponder`: Reads mongodb to check for new feedback where the user should be send an email response.
* `mailsender`: Reads mongodb to check for new feedback that should be formatted and emailed to the Psiphon team.
* `statschecker`: Utility service that periodically sends feedback stats in an email to the Psiphon team.
* `maildecryptor`: Defunct. Feedback used to also come via email attachments, but this method is no longer used.


## Setup

### System Configuration

#### Mongodb

From the instructions [here](http://docs.mongodb.org/manual/tutorial/install-mongodb-on-ubuntu/):

```
apt-key adv --keyserver keyserver.ubuntu.com:80 --recv 9DA31620334BD75D9DCB49F368818C72E52529D4
echo "deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu bionic/mongodb-org/4.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-4.0.list
sudo apt-get update
sudo apt-get install mongodb-org
sudo service mongod enable
sudo service mongod start
```

#### Everything else

```shell
# Prereqs
sudo apt-get install -y python-pip python-dev libssl-dev swig
sudo pip install --upgrade rfc6266 pynliner cssutils BeautifulSoup mako pymongo boto requests numpy html2text pytz pydns sqlalchemy
sudo pip install --upgrade M2Crypto
```

#### pynliner issues

The pynliner library has a [Unicode-related issue that affects us](https://github.com/rennat/pynliner/issues/10).
Until it is resolved/released, we will need to [manually patch the code](https://github.com/rmgorman/pynliner/commit/f21f7aa44d1077f781a278ccb62f792bc4bec150).

#### M2Crypto issues

Check that M2Crypto installed properly. Open a Python REPL, and then type
`import M2Crypto`. If you receive either of these errors:

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
# From within the FeedbackDecryptor directory:
./install.sh
```

This will create the directory to run from, copy the files, and set the file
permissions.

## Create the S3 bucket

Create a bucket in S3 with the following bucket policy:

```json
{
  "Version": "2008-10-17",
  "Statement": [
    {
      "Sid": "Allow public upload",
      "Effect": "Allow",
      "Principal": {
        "AWS": "*"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::your_bucketname_here/*"
    },
    {
      "Sid": "Require that read be granted to bucket owner",
      "Effect": "Deny",
      "Principal": {
        "AWS": "*"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::your_bucketname_here/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-acl": "bucket-owner-full-control"
        }
      }
    }
  ]
}
```

## Configure

`sample_conf.json` must be renamed (or copied) to `conf.json` and all values
must be filled in.

## Running

Use the systemd utilities. For example:

```shell
sudo systemctl restart maildecryptor
sudo systemctl restart s3decryptor
sudo systemctl restart mailsender
sudo systemctl restart statschecker
```
