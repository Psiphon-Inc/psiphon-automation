
# Psiphon Email Autoresponder README


## How the autoresponder works

Our supported domains have MX records configured to point to mail responder server (specifically, the load balancer in front of the server).

On the server, Postfix is configured to use [virtual domains and aliases](http://www.postfix.org/VIRTUAL_README.html#virtual_alias). These aliases all point to a local, limited-privilege `mail_responder` user. 

In the home directory for this user, there is a [`.forward` file](https://bitbucket.org/psiphon/psiphon-circumvention-system/src/tip/EmailResponder/forward?at=default) that points to our [`mail_process.py` file](https://bitbucket.org/psiphon/psiphon-circumvention-system/src/tip/EmailResponder/mail_process.py?at=default) using Postfix's [pipe](http://www.postfix.org/pipe.8.html) functionality.

So, when a Postfix receives an email, it checks that it's for a valid domain and address, and then passes it off to `mail_process.py`. That code processes the request, generates the proper responses, and sends them.

Typically two responses are send: one via Amazon SES that has links to the downloads but no attachments, and one with attachments via local Postfix using SMTP.


### Future improvements

In the current implementation, `mail_process.py` is run for each email that is processed. This is suboptimal. It would be better if the mail processor were a service that ran continuously.

We could probably use Postfix's [virtual mailbox](http://www.postfix.org/VIRTUAL_README.html#virtual_mailbox) configuration to write incoming email to disk and then processing the mail files.


## Setup

### OS

1. Used Ubuntu 11.10 Server 64-bit. AMI IDs can be found via here: <https://help.ubuntu.com/community/EC2StartersGuide>
    * Security Group must allow port 25 (SMTP) through (and SSH, so
      configuration is possible.)
    * Assign a static IP ("Elastic IP") to the instance. (Note that this will
      change the public DNS name you SSH into.)

2. OS updates

    ```
    sudo apt-get update
    sudo apt-get upgrade
    sudo apt-get install mercurial python-pip libwww-perl libdatetime-perl rsyslog-gnutls
    sudo reboot
    ```

3. Create a limited-privilege user that will do most of the mail processing.

    Ref: <http://www.cyberciti.biz/tips/howto-linux-shell-restricting-access.html>

    Add `/usr/sbin/nologin` to `/etc/shells`:

    ```
    sudo useradd -s /usr/sbin/nologin mail_responder
    ```

    Also create a home directory for the user:

    ```
    sudo mkdir /home/mail_responder
    sudo chown mail_responder:mail_responder /home/mail_responder
    ```

4. Create a stub user that will be used for forwarding `support@` emails.

    ```
    sudo useradd -s /usr/sbin/nologin forwarder
    sudo mkdir /home/forwarder
    sudo chown forwarder:forwarder /home/forwarder
    sudo -uforwarder sh -c 'echo "oursupportaddress@example.com" > /home/forwarder/.forward'
    ```

5. Install NTP, otherwise it's possible for the clock to drift and SES requests
   to be rejected. (This has happened.)

   ```
   sudo apt-get install ntp
   ```


### SSH, fail2ban

NOTE: This hasn't been updated since the change to "elastic" mail responders.

For extra security, we'll have SSH listen on a non-standard port and use
fail2ban to prevent brute-force login attempts on SSH. Alternatively/additionally,
EC2 security groups or OS firewall policies can restrict the incoming IPs
allowed to access the SSH port.

1. Change SSH port number.

   ```
   sudo nano /etc/ssh/sshd_config
   ```

   Change 'Port' value to something random. Make sure EC2 security group allows
   this port through for TCP.

2. Install fail2ban.

   ```
   sudo apt-get install fail2ban
   ```

3. Configure fail2ban to use non-standard SSH port. Create or edit `/etc/fail2ban/jail.local`:

   ```
   [ssh]
   port = ssh,<port#>
   [ssh-ddos]
   port = ssh,<port#>
   ```

4. Edit `/etc/fail2ban/filter.d/sshd.conf`, and add the following line to the
   failregex list:

   ```
   ^%(__prefix_line)spam_unix\(sshd:auth\): authentication failure; logname=\S* uid=\S* euid=\S* tty=\S* ruser=\S* rhost=<HOST>(?:\s+user=.*)?\s*$
   ```

   (We found with the Psiphon 3 servers that fail2ban wasn't detecting all the
   relevant auth.log entries without adding this regex. It looks like a [bug in fail2ban](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=648020) before v0.8.7.)

5. Restart ssh and fail2ban:

   ```
   sudo service ssh restart
   sudo service fail2ban restart
   ```


### Postfix


1. Install postfix:

   ```
   sudo apt-get install postfix
   ```

   During installation:

   * Choose the "Internet Site option".

   * Leave the default for the "mail name".

2. Change aliases.

   * Edit `/etc/aliases` so that it looks like this:

       ```
       postmaster: ubuntu
       root: ubuntu
       support: forwarder@localhost
       ```

   * Reload aliases map: 

       ```
       sudo newaliases
       ```

3. Generate a unique 2048-bit Diffie-Hellman group. This helps mitigate crypto threats such as [Logjam](https://weakdh.org/). Go get a coffee while it's generating.

    ```
    sudo su
    mkdir -p /etc/ssl/private
    chmod 710 /etc/ssl/private
    openssl dhparam -out /etc/ssl/private/dhparams.pem 2048
    chmod 600 /etc/ssl/private/dhparams.pem
    exit
    ```

4. Edit `/etc/postfix/main.cf`

    * See the bottom of this README for a sample `main.cf` file.

    (Note: If too much error email is being sent to the postmaster, we can also
    add this line:
    `notify_classes =`
    )

5. When sending mail via our local Postfix we don't want to have to make a TLS
   connection. So we'll run an instance of `stmpd` on `localhost` on a different
   port and use that for sending. Add these two lines to `master.cf`. NOTE: The 
   port specified must match the one in `settings.LOCAL_SMTP_SEND_PORT`.
   (I don't think it matters where in the file you add it. I put it before the `pickup` line.)

    ```
    127.0.0.1:2525      inet  n       -       -       -       -       smtpd
      -o syslog_name=postfix2
      -o smtpd_tls_security_level=none
      -o smtpd_banner=localhost
      -o myhostname=localhost
      -o smtpd_recipient_restrictions=permit_mynetworks,reject_unauth_destination
      -o virtual_alias_domains=
      -o virtual_alias_maps=
      -o smtpd_helo_restrictions=permit
      -o smtpd_sender_restrictions=permit
      -o smtpd_data_restrictions=permit
    ```

6. Add [`postgrey`](http://postgrey.schweikert.ch/) for "[greylisting](http://projects.puremagic.com/greylisting/)":

   ```
   sudo apt-get install postgrey   
   ```

   Actually using postgrey is handled in our example `main.cf` config.

7. Reload postfix conf and restart:

   ```
   sudo postfix reload
   sudo service postfix restart
   ```

### Logwatch and Postfix-Logwatch

Optional, but if logwatch is not present then the stats processing code will need to be changed.

1. Install `logwatch` and `build-essential`

   ```
   sudo apt-get install logwatch build-essential
   ```

2. Install `postfix-logwatch`.

   - Download current version from: http://logreporters.sourceforge.net/

   - Extract the archive, enter the new directory, and execute:
     
     ```
     sudo make install-logwatch
     ```


### Amazon AWS services

1. Install boto
   
   ```
   sudo pip install --upgrade boto
   ```

2. It's best if the AWS user being used is created through the AWS IAM
   interface and has only the necessary privileges. See the appendix for
   permission policies.

3. Put AWS credentials into boto config file. Info here: 
   <http://code.google.com/p/boto/wiki/BotoConfig>

   We've found that using `~/.boto` doesn't work, so create `/etc/boto.cfg` and
   put these lines into it:

   ```
   [Credentials]
   aws_access_key_id = <your access key>
   aws_secret_access_key = <your secret key>
   ```

   Ensure that the file is readable by the `mail_responder` user.


### Source files and cron jobs

In the `ubuntu` user home directory, get the Psiphon source:

```
hg clone https://bitbucket.org/psiphon/psiphon-circumvention-system
```

Go into the email responder source directory:

```
cd psiphon-circumvention-system/EmailResponder
```

The `settings.py` file must be edited. See the comment at the top of that
file for instructions.

The `install.sh` script does the following:

   - copy files from the source directory to the `mail_responder` home directory

   - modify those files, if necessary

   - set the proper ownership on those files

   - create the cron jobs needed for the running of the system

The script requires the `crontab` python package:

```
sudo pip install --upgrade python-dateutil python-crontab qrcode
```

(TODO: Mention that "Email Responder Configuration" steps below need to be taken before installing.)

To run the install script:

```
sh install.sh
```


### Logging

* The install script copies the file `20-psiphon-logging.conf` to `/etc/rsyslog.d/`.

  * This copies the mail responder logs to a dedicated log file that will be
    processed to get statisitics about use.

  * It also sends postfix logs to the Psiphon log processor.

* Enable RFC 3339 compatible high resolution timestamp logging format (required
  for stats processing).

  In `/etc/rsyslog.conf`, ensure this line is commented out:

  ```
  #$ActionFileDefaultTemplate RSYSLOG_TraditionalFileFormat
  ```

* Turn off "repeated message reduction" (the syslog feature that results in
  "last message repeated X times" instead of repeated logs). For our stats, we
  need a line per event, not a compressed view.

  In `/etc/rsyslog.conf`, change this:

  ```
  $RepeatedMsgReduction on
  ```

  to this:

  ```
  $RepeatedMsgReduction off
  ```

  (TODO: Can this be turned off for only `mail_responder.log`?)

* Restart the logging service:

  ```
  sudo service rsyslog restart
  ```

**TODO**: Describe remote logstash setup. 


## Stats

* Stats will be derived from the contents of `/var/log/mail_responder.log`

* `mail_stats.py` can be executed periodically to email basic statisitics to a 
  desired email address. The sender and recipient addresses can be found (and 
  modified) in `settings.py`.

  * `mail_stats.py` is run from `psiphon-log-rotate.conf`. This makes sense
    because it uses `syslog.1`, which is created after a log rotation.

* The emailing is done with the same code that the responder itself uses.


## Blacklist

Users will only receive responses to three requests per day (configurable),
after which they are "blacklisted". The blacklist is cleared once a day
(configurable).

The blacklist code requires the following package be installed:

```
sudo apt-get install mysql-server python-mysqldb python-sqlalchemy
```

Create the DB and user. TODO: Move this into `install.sh`.

```
mysql -uroot
CREATE USER '<username in settings.py>'@'localhost' IDENTIFIED BY '<password in settings.py>';
CREATE DATABASE <DB name in settings.py>;
GRANT ALL ON <DB name in settings.py>.* TO '<username in settings.py>'@'localhost';
\q
```


## DKIM

NOTE: In the past we have occasionally turned off DKIM support. We found that
it was by far the most time- consuming step in replying to an email, and of
questionable value. To disable, change [this
function](https://bitbucket.org/psiphon/psiphon-circumvention-system/src/7baa67
1232d8164de8e7a8f0beb4ff7e38e9530c/EmailResponder/mail_process.py?at=default#cl
-311) to just `return raw_email`.

For information about DKIM (DomainKeys Identified Mail) see dkim.org, RFC-4871,
and do some googling.

A handy DKIM DNS record generator can be found here:
<http://www.dnswatch.info/dkim/create-dns-record>

A couple of python packages are required:

```
sudo pip install --upgrade dnspython dkimpy
```

See the DKIM section of `settings.py` for more values that must be set/changed.


## SPF

Add this DNS TXT record on the domain you will be sending from:

```
"spf2.0/pra include:amazonses.com ip4:<outbound IP address of server> ~all"
"v=spf1 include:amazonses.com ip4:<outbound IP address of server> ~all"
```


## Email Responder Configuration

The configuration file contains the addresses that the responder will respond 
to, and the message bodies that will sent back to those addresses. The 
configuration file is stored in a S3 bucket so that all instances of the
mail responder can access it. This bucket and key are specific in `settings.py`.

The file is in JSON format, with these fields:

```
[
  {
    "email_addr": <emailaddress>,
    "body": [[<mimetype>, <body>], ...],
    "attachments": null | [[<bucketname>, <bucketfilename>, <attachmentfilename>], ...],
    "send_method": "SMTP" | "SES"
  }
...
]

For example:
[
  {
    "email_addr": "multipart-email@example.com",
    "body":
        [
          ["plain", "English - https://example.com/en.html\n\u0641\u0627\u0631\u0633\u06cc - https://example.com/fa.html"],
          ["html", "<a href=\"https://example.com/en.html\">English - https://example.com/en.html</a><br>\u0641\u0627\u0631\u0633\u06cc - https://example.com/fa.html<br>"]
        ],
    "attachments": null,
    "send_method": "SES"
  },
  {
    "email_addr": "multipart-email@example.com",
    "body":
        [
          ["plain", "English - https://example.com/en.html\n\u0641\u0627\u0631\u0633\u06cc - https://example.com/fa.html"],
          ["html", "<a href=\"https://example.com/en.html\">English - https://example.com/en.html</a><br>\u0641\u0627\u0631\u0633\u06cc - https://example.com/fa.html<br>"]
        ],
    "attachments": [["aaaa-bbbb-cccc-dddd", "Psiphon3.exe", "Psiphon3.ex_"],
                  ["aaaa-bbbb-cccc-dddd", "PsiphonAndroid.apk", "PsiphonAndroid.apk"]],
    "send_method": "SMTP"
  },
  {
    "email_addr": "justtext@example.com",
    "body":
        [
          ["plain", "Here's a download link. Please expect another email with attachments. https://example2.com/en.html"]
        ],
    "attachments": null,
    "send_method": "SES"
  },
  {
    "email_addr": "justtext@example.com",
    "body":
        [
          ["plain", "Here's a download link. Please expect another email with attachments. https://example2.com/en.html"]
        ],
    "attachments": [["aaaa-bbbb-cccc-dddd", "Psiphon3.exe", "Psiphon3.ex_"],
                  ["aaaa-bbbb-cccc-dddd", "PsiphonAndroid.apk", "PsiphonAndroid.apk"]]
    "send_method": "SMTP"
  },
  {
    "email_addr": "simplebody@example2.com",
    "body": "Just a string",
    "attachments": null,
    "send_method": "SES"
  },
  {
    "email_addr": "attachment@example3.com",
    "body": "I have an attachment",
    "attachments": [["aaaa-bbbb-cccc-dddd", "Psiphon3.exe", "Psiphon3.ex_"]],
    "send_method": "SMTP"
  }
]
```

Things to notice about the format:

* There can be multiple entries for the same email address. This will result
    in multiple emails being sent in response to a request. The intention is
    that one email will not have attachments (and so will likely not be flagged
    as spam), and the second email will have attachments. NOTE: The order of
    entries is important -- responses will be sent in the order of the entries
    (so put the non-attachment entry before the attachment entry, because it
    will send faster).

* The email address must be lower-case.

* The email body can be a just a string, which will be interpreted as 'plain'
    mimetype, or an array of one or more tuples which are `["mimetype",
    "body"]`. Mimetypes can be 'plain' or 'html' (so there's really no reason
    to specify more than two).

    NOTE: The *last* mimetype will be the one that's preferred by mail clients,
    so you should put the 'html' body last.

* There can be multiple domains served by the same responder server, so the
    whole email address is important.

* The attachment can be null.

* The attachment file will have to exist and be accessible in S3 at:
    `{bucketname}/{bucketfilename}`

* The `attachmentfilename` value is the name of the attachment that's
    displayed in the email. It must be a filetype that won't be rejected by
    most mail clients (so, for example, not .exe). When using a fake file
    extension, we don't want to use an extension that typically has a file
    association (since we don't want anyone accidentally double-clicking and
    trying to open it before renaming it).

* Once upon a time, Amazon SES had a whitelist of attachment types that it 
    would send, which did not include executables (even renamed ones). So our
    responder is configured up to use SES for email without attachments, and
    SMTP for email with attachments. It appears that SES's policy may have
    changed, and that now it blacklists rather than whitelists [certain
    attachment types](http://docs.aws.amazon.com/ses/latest/DeveloperGuide
    /mime-types.html).


## Appendices

* In order for our responses to not be flagged as spam, these guidelines should
  be followed:
  <http://docs.amazonwebservices.com/ses/latest/DeveloperGuide/index.html?SPFSenderIDDKIM.html>

* Be sure to peruse the `settings.py` file.


### Sample `main.cf`

```
myhostname = mx.example.com
my_ec2_publicname = ec2-11-22-33-44.compute-1.amazonaws.com

smtpd_banner = ESMTP $mail_name $myhostname $my_ec2_publicname

# Disable local mail notifications
biff = no

# appending .domain is the MUA's job.
append_dot_mydomain = no

# Uncomment the next line to generate "delayed mail" warnings
#delay_warning_time = 4h

readme_directory = no

#
# TLS parameters
#
# See: http://www.postfix.org/TLS_README.html

# Set these always
smtpd_tls_session_cache_database = btree:${data_directory}/smtpd_scache
smtp_tls_session_cache_database = btree:${data_directory}/smtp_scache

# If you don't want to use TLS, use these lines:
#smtpd_tls_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem
#smtpd_tls_key_file=/etc/ssl/private/ssl-cert-snakeoil.key
#smtpd_use_tls=no

# To use TLS, use these lines:
smtpd_tls_cert_file=/etc/postfix/mx.psiphon3.com.crt
smtpd_tls_key_file=/etc/postfix/mx.psiphon3.com.key
smtpd_tls_CAfile=/etc/postfix/mx.psiphon3.com-bundle
smtpd_tls_received_header=yes
tls_random_source=dev:/dev/urandom

# Postfix runs in a chroot jail, so it can't access /etc/ssl/certs. Instead use:
smtp_tls_CAfile=/etc/ssl/certs/ca-certificates.crt

# These two can be set to 'may' to use encryption oppotunistically, but not require it.
# Note that this level of security will mean that connections to and from some
# mail servers will fail. It works with all of the major webmail providers, 
# though. It's probably best to not reply at all than to reply unencrypted to
# a sketchy mail provider that might be in-country.
smtpd_tls_security_level=encrypt
smtp_tls_security_level=verify

# Handy for debugging:
#smtp_tls_loglevel=2

# Avoid POODLE (etc.) vulnerabilities by forbidding SSLv2 and SSLv3
smtpd_tls_mandatory_protocols = !SSLv2, !SSLv3
smtpd_tls_protocols = !SSLv2, !SSLv3
smtp_tls_mandatory_protocols = $smtpd_tls_mandatory_protocols
smtp_tls_protocols = $smtpd_tls_protocols

# Prevent weak cipher use
smtpd_tls_mandatory_exclude_ciphers = aNULL, eNULL, EXPORT, DES, RC4, MD5, PSK, aECDH, EDH-DSS-DES-CBC3-SHA, EDH-RSA-DES-CDC3-SHA, KRB5-DE5, CBC3-SHA
smtpd_tls_exclude_ciphers = $smtpd_tls_mandatory_exclude_ciphers

# Use "high"-security cipherss, and use our preference order, rather than the client's
tls_preempt_cipherlist = yes
smtpd_tls_mandatory_ciphers = high
smtp_tls_mandatory_ciphers = $smtpd_tls_mandatory_ciphers
smtpd_tls_ciphers = $smtpd_tls_mandatory_ciphers
smtp_tls_ciphers = $smtp_tls_mandatory_ciphers

# Use a custom 2048-bit DH group (anti-Logjam-ish). 
# The params file should be generated with:
# mkdir -p /etc/ssl/private
# chmod 710 /etc/ssl/private
# openssl dhparam -out /etc/ssl/private/dhparams.pem 2048
# chmod 600 /etc/ssl/private/dhparams.pem
smtpd_tls_dh1024_param_file = /etc/ssl/private/dhparams.pem

# /TLS

alias_maps = hash:/etc/aliases
alias_database = hash:/etc/aliases

mydestination = localhost.$mydomain localhost
relayhost =
mynetworks = 127.0.0.0/8 [::ffff:127.0.0.0]/104 [::1]/128
mailbox_size_limit = 0
recipient_delimiter = +
inet_interfaces = all

# Prevent attempts to use IPv6. Avoids unnecessary failed attempts.
inet_protocols = ipv4

# Notify postmaster of all errors
# Note that if this results in too much pointless mail, we can just remove these values.
#notify_classes = bounce, 2bounce, delay, policy, protocol, resource, software
#notify_classes = delay, policy, resource, software
notify_classes =


#
# SMTPD (receiving) config
#

# Tarpit those bots/clients/spammers who send errors or scan for accounts
smtpd_error_sleep_time = 20s
smtpd_soft_error_limit = 1
smtpd_hard_error_limit = 3
smtpd_junk_command_limit = 2

# Reject messages that don't meet these criteria
# The `10023` is the postgrey greylisting service.
smtpd_recipient_restrictions =
   permit_mynetworks,
   reject_invalid_helo_hostname,
   reject_non_fqdn_helo_hostname,
   reject_non_fqdn_sender,
   reject_non_fqdn_recipient,
   reject_unknown_sender_domain,
   reject_unknown_recipient_domain,
   reject_unauth_destination,
   reject_rbl_client zen.spamhaus.org,
   reject_rbl_client bl.spamcop.net,
   reject_rbl_client cbl.abuseat.org,
   reject_rbl_client b.barracudacentral.org,
   reject_rbl_client dnsbl.sorbs.net,
   check_policy_service inet:127.0.0.1:10023,
   permit

# Without this, some other rules can be bypassed.
smtpd_helo_required = yes

# Reject some peers based on their HELO.
smtpd_helo_restrictions = 
  permit_mynetworks,
  reject_unknown_helo_hostname,
  check_helo_access hash:/home/mail_responder/helo_access,
  permit

# Don't accept mail from domains that don't exist.
smtpd_sender_restrictions = reject_unknown_sender_domain

# Block clients that speak too early.
smtpd_data_restrictions = reject_unauth_pipelining


#
# SMTP (sending) config
#

smtp_tls_note_starttls_offer = yes

# Use different sending TLS policies for different peers.
#smtp_tls_policy_maps = hash:/home/mail_responder/client_tls_policy


#
# Message and queue limits
#

# Reduce the message size limit. There's no reason for large messages to be coming in.
message_size_limit = 8192000

# Setting this to 0 indicates that "mail delivery should be tried only once"
# http://www.postfix.org/postconf.5.html#bounce_queue_lifetime
bounce_queue_lifetime = 0
# Consider a message undeliverable when it hits this time limit
# http://www.postfix.org/postconf.5.html#maximal_queue_lifetime
maximal_queue_lifetime = 1h


#
# Supported addresses
#

# This file contains the domains we support. Its contents will replace this path.
# We rely on an external command (cron job) to reload the postfix config when
# this file changes.
# NOTE: the user home path here might differ with your particular setup.
virtual_alias_domains = /home/mail_responder/postfix_responder_domains
virtual_alias_maps = hash:/home/mail_responder/postfix_address_maps
```


### Elastic Mail Responder

#### Additional CloudWatch metrics

Created by `mon-put-instance-data.pl`. Run as a cron job installed by 
`create_cron_jobs.py`.


#### Setup

Derived from this: <http://boto.readthedocs.org/en/latest/autoscale_tut.html>

Assumes that the base AMI and Load Balancer are already created.

The overall reason/rationale for this scaling policy is something like this:

Most of the time we have a very stable daily number of requests. It sometimes
grows and contracts, but generally it's predictable. We would like our "normal"
state to be sufficient but not overkill -- saving money is important. We also
sometimes have major spikes in requests -- like, sudden increases of 10x or
20x. This can result from a TV program mentioning us and all the viewers
hitting us at the same time. In the past we have choked and lost requests
and/or taken a very long time to respond. We would like to be able to cope with
such situations more gracefully.

So our approach to scaling will be to go up very fast, and then let the pool
shrink if the capacity isn't needed. This will probably be our best chance of
coping with a sudden 20x request increase.

NOTE: AWS has recently added the ability to manage scaling stuff (launch
configs, scaling groups) via the EC2 web console. We now use that instead of
Python+boto.


```python

access_id, secret_key = <high-enough privilege user creds>

# It's possible to have the auto-scaling group go across availability zones
# but we probably don't need that, and it will be easier to keep track of if we
# keep all the instances in one zone.
availability_zone = 'us-east-1a'
region = 'us-east-1'

launch_config_name = <something meaningful>
image_id = <AMI ID>
key_name = <key pair name>
security_group = <VPC SG ID, not name>
autoscaling_group_name = <something meaningful>
load_balancer_name = <name for LB created in web interface>
vpc_zone_identifier = <subnet ID>

instance_type = 'm1.large'
min_size = 1
max_size = 10

alert_action = <alert action ARN>

from boto.ec2.autoscale import AutoScaleConnection, LaunchConfiguration, AutoScalingGroup, ScalingPolicy
import boto.ec2.cloudwatch
from boto.ec2.cloudwatch import MetricAlarm

conn = AutoScaleConnection(access_id, secret_key)

conn.get_all_groups()  # empty list if there aren't any

# Create the Launch Configuration
lc = LaunchConfiguration(name=launch_config_name,
                         image_id=image_id,
                         instance_type=instance_type,
                         key_name=key_name,
                         security_groups=[security_group],
                         instance_monitoring=True)
conn.create_launch_configuration(lc)

# After creating an object, we fetch it back so that we have the defaults filled in.
lc = conn.get_all_launch_configurations(names=[lc.name])[0]

# Create the Autoscaling Group
ag = AutoScalingGroup(group_name=autoscaling_group_name,
                      load_balancers=[load_balancer_name],
                      availability_zones=[availability_zone],
                      launch_config=lc.name,
                      min_size=min_size, max_size=max_size,
                      vpc_zone_identifier=vpc_zone_identifier,
                      termination_policies=['NewestInstance'],
                      connection=conn)
conn.create_auto_scaling_group(ag)
ag = conn.get_all_groups(names=[ag.name])[0]

conn.get_all_activities(ag)  # should spit out info about instances spinning up

# Create the scaling policies

# Cooldown is the wait time after taking a scaling action before allowing 
# another scaling action. We'll make it long enough to properly observe the 
# change resulting from the scaling action.

# Because we sometimes have major sudden traffic spikes, we're going to scale
# up by multiple instances.
scale_up = 4
scale_down = -1

scale_up_policy = ScalingPolicy(
            name='scale_up', adjustment_type='ChangeInCapacity',
            as_name=ag.name, scaling_adjustment=scale_up, cooldown=300)
conn.create_scaling_policy(scale_up_policy)
scale_up_policy = conn.get_all_policies(
            as_group=ag.name, policy_names=[scale_up_policy.name])[0]

scale_down_policy = ScalingPolicy(
            name='scale_down', adjustment_type='ChangeInCapacity',
            as_name=ag.name, scaling_adjustment=scale_down, cooldown=300)
conn.create_scaling_policy(scale_down_policy)
scale_down_policy = conn.get_all_policies(
            as_group=ag.name, policy_names=[scale_down_policy.name])[0]

cloudwatch = boto.ec2.cloudwatch.connect_to_region(
            region,
            aws_access_key_id=access_id,
            aws_secret_access_key=secret_key)

# This causes values to be viewed in aggregate across the ASG.
alarm_dimensions = { "AutoScalingGroupName": ag.name }

# CPU

scale_up_actions = [scale_up_policy.policy_arn, alert_action]
scale_down_actions = [scale_down_policy.policy_arn, alert_action]

scale_up_alarm = MetricAlarm(
            name='scale_up_on_cpu', namespace='AWS/EC2',
            metric='CPUUtilization', statistic='Average',
            comparison='>', threshold='70',
            period='60', evaluation_periods=2,
            alarm_actions=scale_up_actions,
            dimensions=alarm_dimensions)
cloudwatch.create_alarm(scale_up_alarm)

scale_down_alarm = MetricAlarm(
            name='scale_down_on_cpu', namespace='AWS/EC2',
            metric='CPUUtilization', statistic='Average',
            comparison='<', threshold='40',
            period='60', evaluation_periods=2,
            alarm_actions=scale_down_actions,
            dimensions=alarm_dimensions)
cloudwatch.create_alarm(scale_down_alarm)

# Disk usage

disk_alarm_dimensions = dict(alarm_dimensions, 
                             **{'Filesystem': '/dev/xvda1', 'MountPath': '/'})

scale_up_alarm = MetricAlarm(
            name='scale_up_on_diskspace', namespace='System/Linux',
            metric='DiskSpaceUtilization', statistic='Average',
            comparison='>', threshold='80',
            period='60', evaluation_periods=2,
            alarm_actions=scale_up_actions,
            dimensions=disk_alarm_dimensions)
cloudwatch.create_alarm(scale_up_alarm)

scale_down_alarm = MetricAlarm(
            name='scale_down_on_diskspace', namespace='System/Linux',
            metric='DiskSpaceUtilization', statistic='Average',
            comparison='<', threshold='50',
            period='60', evaluation_periods=2,
            alarm_actions=scale_down_actions,
            dimensions=disk_alarm_dimensions)
cloudwatch.create_alarm(scale_down_alarm)

# Memory usage

scale_up_alarm = MetricAlarm(
            name='scale_up_on_memory', namespace='System/Linux',
            metric='MemoryUtilization', statistic='Average',
            comparison='>', threshold='80',
            period='60', evaluation_periods=2,
            alarm_actions=scale_up_actions,
            dimensions=alarm_dimensions)
cloudwatch.create_alarm(scale_up_alarm)

scale_down_alarm = MetricAlarm(
            name='scale_down_on_memory', namespace='System/Linux',
            metric='MemoryUtilization', statistic='Average',
            comparison='<', threshold='50',
            period='60', evaluation_periods=2,
            alarm_actions=scale_down_actions,
            dimensions=alarm_dimensions)
cloudwatch.create_alarm(scale_down_alarm)

# Request processing time

scale_up_alarm = MetricAlarm(
            name='scale_up_on_processing_time', namespace='Psiphon/MailResponder',
            metric='processing_time', statistic='Average',
            comparison='>', threshold='10000',
            period='60', evaluation_periods=2,
            alarm_actions=scale_up_actions,
            dimensions=alarm_dimensions)
cloudwatch.create_alarm(scale_up_alarm)

scale_down_alarm = MetricAlarm(
            name='scale_down_on_processing_time', namespace='Psiphon/MailResponder',
            metric='processing_time', statistic='Average',
            comparison='<', threshold='5000',
            period='60', evaluation_periods=2,
            alarm_actions=scale_down_actions,
            dimensions=alarm_dimensions)
cloudwatch.create_alarm(scale_down_alarm)

#
# Destroying the setup
# 

ag.shutdown_instances()
# Then wait for instances to shut down
ag.delete()
lc.delete()

#
# Updating the AMI
#

# Determine the Autoscaling Group we used.
print(conn.get_all_groups())
ag_index = <figure out from all LCs>
ag = conn.get_all_groups()[ag_index]

print(conn.get_all_launch_configurations())
old_lc_index = <figure out from all LCs>

old_lc = conn.get_all_launch_configurations()[old_lc_index]

new_image_id = <AMI ID>
new_lc_name = <different from old LC name>

lc = LaunchConfiguration(name=new_lc_name,
                         image_id=new_image_id,
                         instance_type=old_lc.instance_type,
                         key_name=old_lc.key_name,
                         security_groups=old_lc.security_groups,
                         instance_monitoring=old_lc.instance_monitoring)
conn.create_launch_configuration(lc)

ag.launch_config_name = lc.name
ag.update()

conn.delete_launch_configuration(old_lc.name)
```


### AWS user IAM policies

These are the policies that you should create for the IAM user under which all
AWS activities are run.

(These can all be combined, but ours are separate right now, so...)

`EmailResponderCloudWatchGet`:

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Stmt1393018224000",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics"
      ],
      "Resource": [
        "*"
      ]
    }
  ]
}
```

`EmailResponderCloudWatchPut`:

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Sid": "Stmt1382640894000",
      "Resource": [
        "*"
      ],
      "Effect": "Allow"
    }
  ]
}
```

`EmailResponderEC2DescribeTags`:

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "ec2:DescribeTags"
      ],
      "Sid": "Stmt1382730333000",
      "Resource": [
        "*"
      ],
      "Effect": "Allow"
    }
  ]
}
```

`EmailResponderS3Config`:

Note:
  * `psiphon-automation` should be replaced with whatever you configured in
    `settings.py` for `CONFIG_S3_BUCKET`.
  * `EmailResponder` should be replaced with whatever you configured in
    `settings.py` for `CONFIG_S3_KEY`.

```
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::psiphon-automation"
      ],
      "Condition": {
        "StringLike": {
          "s3:prefix": "EmailResponder/*"
        }
      }
    },
    {
      "Action": [
        "s3:GetObject", "s3:PutObject"
      ],
      "Effect": "Allow",
      "Resource": [
        "arn:aws:s3:::psiphon-automation/EmailResponder/*"
      ]
    }
  ]
}
```

`EmailResponderSES`:

```
{
    "Statement": [
        {
            "Sid": "Stmt1319220339894",
            "Action": [
                "ses:*"
            ],
            "Effect": "Allow",
            "Resource": [
                "*"
            ]
        }
    ]
}
```
