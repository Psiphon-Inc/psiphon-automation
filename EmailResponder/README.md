# Psiphon Email Autoresponder README


## How the autoresponder works

Our supported domains have MX records configured to point to mail responder server (specifically, the load balancer in front of the server).

On the server, Postfix is configured to use [virtual domains and aliases](http://www.postfix.org/VIRTUAL_README.html#virtual_alias). These aliases all point to a local, limited-privilege `mail_responder` user.

In the home directory for this user, there is a [`.forward` file](https://github.com/Psiphon-Inc/psiphon-automation/blob/master/EmailResponder/forward) that points to our [`mail_process.py` file](https://github.com/Psiphon-Inc/psiphon-automation/blob/master/EmailResponder/mail_process.py) using Postfix's [pipe](http://www.postfix.org/pipe.8.html) functionality.

So, when a Postfix receives an email, it checks that it's for a valid domain and address, and then passes it off to `mail_process.py`. That code processes the request, generates the proper responses, and sends them.

Typically two responses are send: one via Amazon SES that has links to the downloads but no attachments, and one with attachments via local Postfix using SMTP.


### Future improvements

In the current implementation, `mail_process.py` is run for each email that is processed. This is suboptimal. It would be better if the mail processor were a service that ran continuously.

We could probably use Postfix's [virtual mailbox](http://www.postfix.org/VIRTUAL_README.html#virtual_mailbox) configuration to write incoming email to disk and then process the mail files.


## Setup

### OS

1. Used Ubuntu 22.04 Server 64-bit.
    * Put behind appropriate load balancer, which must forward port 25 (SMTP).
    * Use an IAM role that allows appropriate access. See the appendix for an example.

2. OS updates

    ```
    sudo apt update
    sudo apt upgrade
    sudo apt install default-libmysqlclient-dev python3-pip python3-dev
    sudo reboot
    ```

    It is recommended that you create root cronjob for regular updates. Like so:
    ```
    @daily /usr/bin/env unattended-upgrade
    ```
    (But be warned: This can install/update packages that break things.)

3. Create a limited-privilege user that will do most of the mail processing.

    Ref: <https://www.cyberciti.biz/tips/howto-linux-shell-restricting-access.html>

    Add `/usr/sbin/nologin` to `/etc/shells`:
    ```
    sudo -s
    echo "/usr/sbin/nologin" >> /etc/shells
    exit
    ```

    Create our user:
    ```
    sudo useradd -s /usr/sbin/nologin mail_responder
    ```

    Also create a home directory for the user:
    ```
    sudo mkdir /home/mail_responder
    sudo chown mail_responder:mail_responder /home/mail_responder
    ```

    As a convenience, create an alias to run commands as the user:
    ```
    echo "alias smr='sudo -umail_responder'" >> ~/.bash_aliases
    . ~/.bash_aliases
    ```


### Postfix

1. Install postfix:

   ```
   sudo apt install postfix
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

3. Edit `/etc/postfix/main.cf` and `/etc/postfix/master.cf`.

   See `main.cf.sample` and `master.cf.sample` in this repo for exemplars.

   Note: If too much error email is being sent to the postmaster, we can also add this line to `main.cf`:
   `notify_classes =`

4. When sending mail via our local Postfix we don't want to have to make a TLS
   connection. So we'll run an instance of `smtpd` on `localhost` on a different
   port and use that for sending. Update `/etc/postfix/master.cf` to match `master.cf.example`. NOTE: The
   port specified must match the one in `settings.LOCAL_SMTP_SEND_PORT`.

5. Add [`postgrey`](http://postgrey.schweikert.ch/) for "[greylisting](http://projects.puremagic.com/greylisting/)":

   ```
   sudo apt install postgrey
   ```

   Actually using postgrey is handled in our example `main.cf` config.

6. Install SpamAssassin.

   ```
   sudo apt install spamassassin spamc libmail-dkim-perl
   ```

   Edit `/etc/default/spamassassin` to set `CRON=1`.

   Some spamassassin configuration is already present in `master.cf.example`.

   Our non-default values in `/etc/spamassassin/local.cf` are as follows:
   ```
   report_safe 0
   required_score 3.0
   ```

   Note that `install.sh` also copies our custom score values in `50_scores.cf` to `/etc/spamassassin/`.

   Enable and run:
   ```
   sudo update-rc.d spamassassin enable
   sudo service spamassassin start
   ```

7. DKIM verification:

   Install OpenDKIM, using [these instructions](https://www.digitalocean.com/community/tutorials/how-to-install-and-configure-dkim-with-postfix-on-debian-wheezy), but skipping the signing stuff.

   When editing `/etc/opendkim.conf`, just paste this at the bottom:
   ```
   ### PSIPHON

   AutoRestart             Yes
   AutoRestartRate         10/1h
   UMask                   002
   Syslog                  Yes
   SyslogSuccess           Yes
   LogWhy                  Yes

   Canonicalization        relaxed/simple

   ExternalIgnoreList      refile:/etc/opendkim/TrustedHosts
   InternalHosts           refile:/etc/opendkim/TrustedHosts

   Mode                    v
   SignatureAlgorithm      rsa-sha256

   Socket                  inet:12301@localhost

   SoftwareHeader          yes
   AlwaysAddARHeader       yes
   ```

   `/etc/opendkim/TrustedHosts` should contain this:
   ```
   127.0.0.1
   localhost
   # depends what subnet we're in
   192.168.12.0/24

   # TODO: Derive from settings.py (or something)
   mx.psiphon3.com
   *.psiphon3.com
   mx.respondbot.net
   *.respondbot.net
   ```

   Note: With the configuration described here, DKIM will be verified twice -- once before SpamAssassin and once after SA delivers it back to Postfix. I think we either need to use dovecot instead of sendmail for re-delivery from SA, or (better) switch from SA to Amavis.

   ```
   sudo service opendkim restart
   ```

8. Obtain SSL certificate for incoming STARTTLS connections. TODO: details.

   File paths for the key, cert, and CA bundle can be found/set in `main.cf` under `smtpd_tls_key_file`, `smtpd_tls_cert_file`, `smtpd_tls_CAfile`. The key file permissions should be 0400; the other two should be like 0644. They should be owned by `root`.

9. Restart Postfix:
   ```
   sudo service postfix restart
   ```

### Logwatch and Postfix-Logwatch

TODO: Still needed?

Optional, but if logwatch is not present then the stats processing code will need to be changed.

Install `logwatch` and `build-essential`:
```
sudo apt install logwatch build-essential
```


### Source files and cron jobs

In the `ubuntu` user home directory, get the Psiphon source:

```
git clone https://github.com/Psiphon-Inc/psiphon-automation.git
```

Go into the email responder source directory:

```
cd psiphon-automation/EmailResponder
```

The `settings.py` file must be edited. See the comment at the top of that
file for instructions.

The `install.sh` script does the following:

   - copy files from the source directory to the `mail_responder` home directory

   - modify those files, if necessary

   - set the proper ownership on those files

   - create the cron jobs needed for the running of the system

(TODO: Mention that "Email Responder Configuration" steps below need to be taken before installing.)

To run the install script:

```
sh install.sh
```

(On the very first run, expect the error `postmap: fatal: open postfix_address_maps: No such file or directory`. That file gets created by the first call.)

### Logging

* The install script copies the file `20-psiphon-logging.conf` to `/etc/rsyslog.d/`.

  * This copies the mail responder logs to a dedicated log file that will be
    processed to get statistics about use.

  * It also sends postfix logs to the Psiphon log processor. (Currently disabled.)

* Enable RFC 3339 compatible high resolution timestamp logging format (required
  for stats processing).

  In `/etc/rsyslog.conf`, ensure this line is commented out:

  ```
  #$ActionFileDefaultTemplate RSYSLOG_TraditionalFileFormat
  ```

* Turn off "repeated message reduction" (the syslog feature that results in
  "last message repeated X times" instead of repeated logs). For our stats, we
  need a line per event, not a compressed view.

  In `/etc/rsyslog.conf`, change this `$RepeatedMsgReduction on` to `off`.

  (TODO: Can this be turned off for only `mail_responder.log`?)

* Restart the logging service:

  ```
  sudo service rsyslog restart
  ```


### Nagios

## Nagios monitoring

Install NCPA by following the instructions [here](https://repo.nagios.com/?repo=deb-ubuntu).

`/usr/local/ncpa/etc/ncpa.cfg.d/psiphon.cfg`
`/usr/local/ncpa/plugins/*`
https://github.com/Psiphon-Inc/psi-nagios/blob/master/objects/psiphon/ec2/ec2-linux-services.cfg
https://github.com/Psiphon-Inc/psi-nagios/blob/master/objects/psiphon/ec2/ec2-hosts.cfg

TODO: Expand.


## Stats

* Stats will be derived from the contents of `/var/log/mail_responder.log`

* `mail_stats.py` can be executed periodically to email basic statistics to a
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
sudo apt install mysql-server
```

Create the DB and user. TODO: Move this into `install.sh`.

```
sudo mysql -uroot
CREATE USER '<username in settings.py>'@'localhost' IDENTIFIED BY '<password in settings.py>';
CREATE DATABASE <DB name in settings.py>;
GRANT ALL ON <DB name in settings.py>.* TO '<username in settings.py>'@'localhost';
\q
```


## Filebeat

We use Filebeat to send logs to our ELK stack. At this time we are limited to version 6.8.6 (check with the stats team for updates). It can be installed like:
```
curl -L -O https://artifacts.elastic.co/downloads/beats/filebeat/filebeat-6.8.6-amd64.deb && yes | sudo dpkg -i filebeat-6.8.6-amd64.deb
```

The config file to use can be found at <https://github.com/Psiphon-Inc/elk/blob/main/beats/filebeat/mailresponder.yml>. It should be copied to `/etc/filebeat/filebeat.yml`. Ensure that file is world-readable.

The CA and client certs and keys can be found in CipherShare at `PsiphonV/Cloud/EmailResponder/filebeat`. Copy those to the location indicated in the config file. (Or anywhere else, but then update `filebeat.yml`.)

Enable and start the service:
```
sudo systemctl enable filebeat.service
sudo service filebeat start
```


## DKIM signing

NOTE: In the past we have occasionally turned off DKIM support. We found that
it was by far the most time-consuming step in replying to an email, and of
questionable value. To disable, change [this
function](https://github.com/Psiphon-Inc/psiphon-automation/blob/0bd64e4801f4ae85a237f4c5ea356744248d657e/EmailResponder/mail_process.py#L436) to just `return raw_email`.

For information about DKIM (DomainKeys Identified Mail) see dkim.org, RFC-4871,
and do some googling.

A handy DKIM DNS record generator can be found here:
<http://www.dnswatch.info/dkim/create-dns-record>

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


### Elastic Mail Responder

#### Setup

**NOTE: This section is very old.**

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


### AWS IAM role policies

The EC2 instance should be given a role that gives needed access.

For example (note that there are values to fill in):
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "Stmt1433875609000",
            "Effect": "Allow",
            "Action": [
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics",
                "cloudwatch:PutMetricData"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "Stmt1433875643000",
            "Effect": "Allow",
            "Action": [
                "autoscaling:DescribeAutoScalingInstances"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "Stmt1433875688000",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket"
            ],
            "Condition": {
                "StringLike": {
                    "s3:prefix": "<your settings.CONFIG_S3_KEY value>/*"
                }
            },
            "Resource": [
                "arn:aws:s3:::<your settings.CONFIG_S3_BUCKET value>"
            ]
        },
        {
            "Sid": "Stmt1433875777000",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject"
            ],
            "Resource": [
                "arn:aws:s3:::<your settings.CONFIG_S3_BUCKET value>/<your settings.CONFIG_S3_KEY value>/*"
            ]
        },
        {
            "Sid": "Stmt1433875819000",
            "Effect": "Allow",
            "Action": [
                "ses:*"
            ],
            "Resource": [
                "*"
            ]
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
