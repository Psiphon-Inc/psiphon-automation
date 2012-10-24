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

- Chinese/Farsi characters in subject okay?
