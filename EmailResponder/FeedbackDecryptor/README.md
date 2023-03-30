# Diagnostic Feedback Decryptor

This is a collection of services that monitor email and an S3 bucket for
encrypted diagnostic feedback. They then decrypt and store that data, and then
send an email with the data.


## How it works

There are 4 services:
* `s3decryptor`: Reads encrypted feedback packages from S3, parses and processes them, and stores the data in mongodb.
* `autoresponder`: Reads mongodb to check for new feedback where the user should be send an email response.
* `mailsender`: Reads mongodb to check for new feedback that should be formatted and emailed to the Psiphon team.
* `statschecker`: Utility service that periodically sends feedback stats in an email to the Psiphon team.
* `maildecryptor`: _Defunct_. Feedback used to also come via email attachments, but this method is no longer used.


## Setup

### System Configuration

#### Instance

At this time, the latest version of Ubuntu supported by MongoDB is 20.04, so we're stuck
with that. The default version of Python on 20.04 is 3.8, but 3.9 is available as
`python3.9`, so we'll use that. If/when we upgrade the OS, look for instances of
"python3.9" and change them to "python3".

Additionally, this should not be necessary, but seems to be required before running `install.sh`:
```
sudo python3.9 -m pip install cryptography
```

The EC2 instance should use an IAM role with the following policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::<from config[s3BucketName]>",
                "arn:aws:s3:::<from config[s3BucketName]>/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "ses:SendEmail",
                "ses:SendRawEmail"
            ],
            "Resource": [
                "arn:aws:ses:<arn for SES address that is being sent from>"
            ]
        }
    ]
}
```

#### Packages

```shell
sudo apt install -y python3-pip python3-testresources mysql-server
```

From the [official MongoDB instructions](http://docs.mongodb.org/manual/tutorial/install-mongodb-on-ubuntu/).

#### Create limited-privilege user

The daemon will run as this user.

```shell
sudo useradd -s /bin/false feedback_decryptor
```

### Get source files

Clone this repo. Also acquire the necessary configuration files from your secure document
repository. These files are: `conf.json` and the PEM file (the latter can be extracted
from psinet).

`Automation/psi_ops_stats_credentials.py` will need to be created. TODO: Details.

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

## Psiphon server database

To ensure that Psiphon server IP addresses don't end up stored in email, MySQL, etc., we check for IPs in feedback and replace them with pseudonyms (so that we can still tell what server is being referenced). This requires a copy of the Psiphon server database (or a lightweight version of it). It is periodically updated from CipherShare.

Install `wine` using [the official instructions](https://wiki.winehq.org/Ubuntu). Obtain `CipherShareScriptingClient.exe`.

## Running

Use the systemd utilities. For example:

```shell
sudo systemctl restart s3decryptor
sudo systemctl restart mailsender
sudo systemctl restart statschecker
```

## Nagios monitoring

Install NCPA by following the instructions [here](https://repo.nagios.com/?repo=deb-ubuntu).

`/usr/local/ncpa/etc/ncpa.cfg.d/psiphon.cfg`
`/usr/local/ncpa/plugins/*`
https://github.com/Psiphon-Inc/psi-nagios/blob/master/objects/psiphon/ec2/ec2-linux-services.cfg
https://github.com/Psiphon-Inc/psi-nagios/blob/master/objects/psiphon/ec2/ec2-hosts.cfg

TODO: Expand.
