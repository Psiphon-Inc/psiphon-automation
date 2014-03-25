# Host Reports

## Web page with graphs

This directory contains a little website that displays graphs of the host report data found in `./data/`. Currently, the date-usercount data undergoes a linear regression, they are sorted by steepest decline, and then the first (worst) 50 are displayed.

The site can be served with any static file server. (But I really don't recommend Python's `SimpleHTTPServer`, because it's not good.) The `webserver.sh` script uses Twisted, which can be installed like so:

```
sudo apt-get install python-twisted
```

The web server can probably be run by adding something like this to `crontab`:

```
@reboot cd /opt/PsiphonV/psiphon-circumvention-system/Automation/host_reports && ./webserver.sh start
```
