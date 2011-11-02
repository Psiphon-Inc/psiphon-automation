Psiphon 3 Circumvention System README
================================================================================


Overview
--------------------------------------------------------------------------------

The Psiphon 3 Circumvention System is a relay-based Internet censorship 
circumventer.

The system consists of a client application, which configures a users computer
to direct Internet traffic; and a set of servers, which proxy client traffic to
the Internet. As long as a client can connect to a Psiphon server, it can
access Internet services that may be blocked to the user via direct connection.

Features:

- Automatic discovery. Psiphon 3 clients ship with a set of known Psiphon
  servers to connect to. Over time, clients discover additional servers that are
  added to a backup server list. As older servers become blocked, each client will
  have a reserve list of new servers to draw from as it reconnects. To ensure that
  an adversary cannot enumerate and block a large number of servers, the Psiphon 3
  system takes special measures to control how many servers may be discovered by
  a single client.

- Mobile ready. A Psiphon 3 client Android app will be available as part of the
  beta launch, and other mobile platforms are in the works.

- Zero install. Psiphon 3 is delivered to users as a minimal footprint, zero
  install application that can be downloaded from any webpage, file sharing site
  or shared by e-mail and passed around on a USB key. We keep the file size small
  and avoid the overhead of having to install an application.

- Custom branding.  Psiphon 3 offers a flexible sponsorship system which
  includes sponsor-branded clients. Dynamic branding includes graphics and text on
  the client UI; and a region-specific dynamic homepage mechanism that allows a
  different home page to open depending on where in the world the client is run.

- Chain of trust. Each client instance may be digitally signed to certify its
  authenticity. Embedded server certificates certify that Psiphon servers the
  client connects to are the authentic servers for that client.

- Privacy. Psiphon 3 is designed to respect user privacy. User statistics are
  logged in aggregate, but no individual personally identifying information, such
  as user IP addresses, are retained in PsiphonV log files.

- Agile transport. Psiphon 3 features a pluggable architecture with multiple
  transport mechanisms, including VPN and SSH tunneling. In the case where one
  transport protocol is blocked by a censor, Psiphon automatically switches over
  to another mechanism.

Coming soon:

- IPv6 compatibility.  Psiphon 3 is designed to be IPv6 compatible. This ensures
  the system is ready for the next generation Internet, and in the immediate term
  offers some additional circumvention capabilities as IPv6-based censorship lags
  behind the tools used to censor IPv4 traffic.


Documentation
--------------------------------------------------------------------------------

IMPORTANT: See the [design paper](https://bitbucket.org/psiphon/psiphon-circumvention-system/downloads/DESIGN.pdf), incuded with this software distribution, for
important information regarding security limitations and user privacy issues.


Compatibility
--------------------------------------------------------------------------------

Supported transport mechanisms:

- L2TP/IPSec VPN
- HTTP/SOCKS Proxy over SSH Tunnel

Planned transport mechanisms:

- PPTP VPN
- DNS tunnel

Supported client platforms:

- Windows XP/Vista/7
- Android [TODO: version]

Planned client platforms:

- Mac OS X

Server platform:

- Debian 6.0


Installation
--------------------------------------------------------------------------------

Please see the INSTALL file.


Source Tree
--------------------------------------------------------------------------------

    \...
     CHANGES
     INSTALL
     LICENSE
     README
     Automation\...             Build, Install, & Deploy Scripts
     Automation\Tools\...       3rd party Build Tools
     Client\...                 Clients
     Client\psiclient\...       Windows Client
     Data\...                   Network Database
     Data\Banners\...           Branding Assets
     Data\CodeSigning\...       Authenticode Keys
     EmailResponder\...         Email Autoresponder Server
     Server\...                 Web Server and Server Scripts


Licensing
--------------------------------------------------------------------------------

Please see the LICENSE file.


Contacts
--------------------------------------------------------------------------------

For more information on Psiphon Inc, please visit our web site at:

[www.psiphon.ca](http://www.psiphon.ca)
