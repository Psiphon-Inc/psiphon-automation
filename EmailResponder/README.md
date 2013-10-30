
# Psiphon Email Autoresponder README

## Setup

### OS

1. Used Ubuntu 11.10 Server 64-bit. AMI IDs can be found via here: <https://help.ubuntu.com/community/EC2StartersGuide>
  * Security Group must allow port 25 (SMTP) through (and SSH, so configuration
    is possible.)
  * Assign a static IP ("Elastic IP") to the instance. (Note that this will
    change the public DNS name you SSH into.)

2. OS updates

  ```
  sudo apt-get update
  sudo apt-get upgrade
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
   relevant auth.log entries without adding this regex.)

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

   * Set the system mail name to the public DNS name of the instance. When
     we're ready to go live, this will change to the real domain name.

     * UPDATE: Don't change to the real domain name. Leave it as the instance
       public DNS name.

2. Change aliases.

   * Edit `/etc/aliases` so that it looks like this:

      ```
      postmaster: ubuntu
      root: ubuntu
      support: forwarder@localhost
      ```

   * Reload aliases map: `sudo newaliases`

3. DEFUNCT, because there's too much noise: Add `.forward` file for "normal"
   (probably "ubuntu") user. In the file, put the email address that error mail
   should go to.

4. Edit `/etc/postfix/main.cf`

   * Change `myhostname` to be the public DNS name of the instance, or the domain
     name that's pointing to the instance.

   * Change `mydestination` to be:

     ```
     mydestination = $myhostname localhost.$mydomain localhost $extradomains
     ```

   * `extradomains` is a custom variable that will hold all of the domains that
     our server accepts mail for (and responds to). So, you will have:

     ```
     extradomains = example1.com example2.com
     ```

     Note that the variable can be missing or empty and that's okay.

   * Change `smtpd_use_tls` to `no`

   * Add these two lines to the end. They cause all email that doesn't
     correspond to a real address to be forwarded to the `mail_responder` account
     (which will then do the response processing).

     ```
     local_recipient_maps =
     luser_relay = mail_responder+$local@localhost
     ```

   * Reduce the maximum message size. Something like:

     ```
     message_size_limit = 8192000
     ```

   * See the bottom of this README for a sample `main.cf` file.

(Note: If too much error email is being sent to the postmaster, we can also
add this line:
`notify_classes =`
)

5. By default, if an uncaught error occurs (which shouldn't occur, but...),
   postfix responds to the user with a bounce email that gives a lot of internal
   details about the error. This is undesirable, so we'll disable this in postfix.

   ```
   sudo nano /etc/postfix/master.cf
   ```

   Comment out the bounce line, so it looks like this:

   ```
   #bounce    unix  -       -       -       -       0       bounce
   ```

6. Check the contents of `/etc/mailname`. It should be the FQDN of the current
   instance's public name. If you're using an EC2 Static IP (which you surely
   are), then the value in `/etc/mailname` is probably the public name that the
   instance had *before* you assigned the static IP (at which point it got a new
   public name). Make sure this is updated to the correct value.

7. Reload postfix conf and restart:

   ```
   sudo postfix reload
   sudo /etc/init.d/postfix restart
   ```


### Logwatch and Postfix-Logwatch

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


### Source files and cron jobs

Install mercurial:

```
sudo apt-get install mercurial
```

In the `ubuntu` user home directory, get the Psiphon source:

```
hg clone https://bitbucket.org/psiphon/psiphon-circumvention-system
```

Go into the email responder source directory:

```
cd psiphon-circumvention-system/EmailResponder
```

The `install.sh` script does the following:

   - copy files from the source directory to the `mail_responder` home directory

   - modify those files, if necessary

   - set the proper ownership on those files

   - create the cron jobs needed for the running of the system

The `settings.py` file must first be edited. See the comment at the top of that
file for instructions.

The script requires the `crontab` python package:

```
sudo apt-get install python-pip
sudo pip install --upgrade python-dateutil python-crontab
```

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


### Amazon AWS services

1. Install boto
   
   ```
   sudo pip install boto
   ```

2. It's best if the AWS user being used is created through the AWS IAM interface
   and has only the necessary privileges.

3. Put AWS credentials into boto config file. Info here: <http://code.google.com/p/boto/wiki/BotoConfig>

   We've found that using `~/.boto` doesn't work, so create `/etc/boto.cfg` and put
   these lines into it:

   ```
   [Credentials]
   aws_access_key_id = <your access key>
   aws_secret_access_key = <your secret key>
   ```

   Ensure that the file is readable by the `mail_responder` user.


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
GRANT ALL ON <DB name in settings.py>.* TO '<username in settings.py>'@'localhost';
```


## DKIM

NOTE: In the past we have occasionally turned off DKIM support. We found that it was by far the most time-
consuming step in replying to an email, and of questionable value.

For information about DKIM (DomainKeys Identified Mail) see dkim.org, RFC-4871,
and do some googling.

A handy DKIM DNS record generator can be found here:
<http://www.dnswatch.info/dkim/create-dns-record>

A couple of python packages are required:

```
sudo pip install --upgrade dnspython pydkim
```

See the DKIM section of `settings.py` for more values that must be set/changed.


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
    "attachments": null | [[<bucketname>, <bucketfilename>, <attachmentfilename>], ...]
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
    "attachments": null
  },
  {
    "email_addr": "multipart-email@example.com",
    "body":
        [
          ["plain", "English - https://example.com/en.html\n\u0641\u0627\u0631\u0633\u06cc - https://example.com/fa.html"],
          ["html", "<a href=\"https://example.com/en.html\">English - https://example.com/en.html</a><br>\u0641\u0627\u0631\u0633\u06cc - https://example.com/fa.html<br>"]
        ],
    "attachments": [["aaaa-bbbb-cccc-dddd", "Psiphon3.exe", "Psiphon3.asc"],
                  ["aaaa-bbbb-cccc-dddd", "PsiphonAndroid.apk", "PsiphonAndroid.apk"]]
  },
  {
    "email_addr": "justtext@example.com",
    "body":
        [
          ["plain", "Here's a download link. Please expect another email with attachments. https://example2.com/en.html"]
        ],
    "attachments": null
  },
  {
    "email_addr": "justtext@example.com",
    "body":
        [
          ["plain", "Here's a download link. Please expect another email with attachments. https://example2.com/en.html"]
        ],
    "attachments": [["aaaa-bbbb-cccc-dddd", "Psiphon3.exe", "Psiphon3.asc"],
                  ["aaaa-bbbb-cccc-dddd", "PsiphonAndroid.apk", "PsiphonAndroid.apk"]]
  },
  {
    "email_addr": "simplebody@example2.com",
    "body": "Just a string",
    "attachments": null
  },
  {
    "email_addr": "attachment@example3.com",
    "body": "I have an attachment",
    "attachments": [["aaaa-bbbb-cccc-dddd", "Psiphon3.exe", "Psiphon3.asc"]]
  }
]
```

Things to notice about the format:

* There can be multiple entries for the same email address. This will result
    in multiple emails being sent in response to a request. The intention is
    that one email will not have attachments (and so will likely not be flagged
    as spam), and the second email will have attachments. NOTE: The order of
    entries is important -- responses will be sent in the order of the entries
    (so put the non-attachment entry before the attachment entry).

* The email address must be lower-case.

* The email body can be a just a string, which will be interpreted as 'plain'
    mimetype, or an array of one or more tuples which are `["mimetype", "body"]`.
    Mimetypes can be 'plain' or 'html' (so there's really no reason to specify
    more than two).

* There can be multiple domains served by the same responder server, so the
    whole email address is important.

* The attachment can be null.

* The attachment file will have to exist at: `{bucketname}/{bucketfilename}`

* The `attachmentfilename` value is the name of the attachment that's
    displayed in the email. It must be a filetype that won't be rejected by most
    mail clients (so, for example, not .exe). When using a fake file extension,
    we don't want to use an extension that typically has a file association
    (since we don't want anyone accidentally double-clicking and trying to open
    it before renaming it).

NOTE: The *last* mimetype will be the one that's preferred by mail clients,
  so you should put the 'html' body last.


## Appendix

* In order for our responses to not be flagged as spam, these guidelines should
  be followed:
  <http://docs.amazonwebservices.com/ses/latest/DeveloperGuide/index.html?SPFSenderIDDKIM.html>

* Be sure to peruse the `settings.py` file.


## Sample `main.cf`

```
# See /usr/share/postfix/main.cf.dist for a commented, more complete version


# Debian specific:  Specifying a file name will cause the first
# line of that file to be used as the name.  The Debian default
# is /etc/mailname.
#myorigin = /etc/mailname

smtpd_banner = $mail_name ESMTP
biff = no

# appending .domain is the MUA's job.
append_dot_mydomain = no

# Uncomment the next line to generate "delayed mail" warnings
#delay_warning_time = 4h

readme_directory = no

# TLS parameters
smtpd_tls_cert_file=/etc/ssl/certs/ssl-cert-snakeoil.pem
smtpd_tls_key_file=/etc/ssl/private/ssl-cert-snakeoil.key
smtpd_use_tls=no
smtpd_tls_session_cache_database = btree:${data_directory}/smtpd_scache
smtp_tls_session_cache_database = btree:${data_directory}/smtp_scache

# See /usr/share/doc/postfix/TLS_README.gz in the postfix-doc package for
# information on enabling SSL in the smtp client.

myhostname = example.com
alias_maps = hash:/etc/aliases
alias_database = hash:/etc/aliases
myorigin = /etc/mailname
extradomains = otherdomain1.com otherdomain2.com
mydestination = $myhostname localhost.$mydomain localhost <ec2 external domain name> <ec2 internal domain name> $extradomains
relayhost =
mynetworks = 127.0.0.0/8 [::ffff:127.0.0.0]/104 [::1]/128
mailbox_size_limit = 0
recipient_delimiter = +
inet_interfaces = all


# PSIPHON ADDITIONS

# Notify postmaster of all errors
# Note that if this results in too much pointless mail, we can just remove these values.
#notify_classes = bounce, 2bounce, delay, policy, protocol, resource, software
notify_classes = delay, policy, resource, software

# Add a catch-all for all addresses
local_recipient_maps =
luser_relay = mail_responder+$local@localhost

# Tarpit those bots/clients/spammers who send errors or scan for accounts
smtpd_error_sleep_time = 20s
smtpd_soft_error_limit = 1
smtpd_hard_error_limit = 3
smtpd_junk_command_limit = 2

# Reduce the message size limit. There's no reason for large messages to be coming in.
message_size_limit = 8192000

# Reject messages that don't meet these criteria
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
   permit

# Without this, some of the above reject lines can be bypassed.
smtpd_helo_required = yes
```


## Elastic Mail Responder

### Additional CloudWatch metrics

Created by `mon-put-instance-data.pl`. Run as a cron job installed by `create_cron_jobs.py`.


### Setup

Derived from this: <http://boto.readthedocs.org/en/latest/autoscale_tut.html>

Assumes that the base AMI and Load Balancer are already created.

The overall reason/rationale for this scaling policy is something like this:

Most of the time we have a very stable daily number of requests. It sometimes
grows and contracts, but generally it's predictable. We would like our "normal"
state to be sufficient but not overkill -- saving money is important. We also
sometimes have major spikes in requests -- like, sudden increases of 10x or 20x.
This can result from a TV program mentioning us and all the viewers hitting us
at the same time. In the past we have choked and lost requests and/or taken a 
very long time to respond. We would like to be able to cope with such situations
more gracefully.

So our approach to scaling will be to go up very fast, and then let the pool
shrink if the capacity isn't needed. This will probably be our best chance of
coping with a sudden 20x request increase.

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
