# Diagnostic Feedback Email Attachment Decryptor

## System Configuration

```shell
# Prereqs
sudo apt-get install -y python-pip
sudo pip install rfc6266

# Install the Upstart service file
sudo cp maildecryptor.conf /etc/init/
```

## TODO:  

### README stuff

- Where should the source files be copied?
- What user should the daemon run as?

### Code stuff

- Use Gmail cert pinning for pop and smtp. (I think it'll work...)
  - To make it less likely that a MitM-with-bad-cert attack would work.
  - Steps:
    - Pull down certs for `pop.gmail.com` and `smtp.gmail.com` and save to files. 
    - Specify those files in `conf.json`.
    - Pass cert to `certfile` arg of `poplib.POP3_SSL` and `smtplib.SMTP_SSL`.
