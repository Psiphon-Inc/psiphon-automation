Psiphon 3 Circumvention System README
================================================================================
----BEGIN ssh-with-no-handshake NOTES----

Two design statements:

1. If a transport can connect without first making an extra-transport request,
   then it should.
    - In order to connect with VPN, an initial handshake is required in order to 
      get server credentials. So that doesn't qualify.
    - SSH and OSSH, on the other hand, do not, in theory, require an initial 
      handshake. So we will embed those credentials and then connect without an
      initial handshake.

2. Any extra-transport requests should try HTTPS (8080, then 443) and then fail
   over to setting up and making request through any available transports that
   don't require an extra-transport request to connect.
    - Failure requests, post-disconnect stats request, and VPN handshake requests
      all must be done extra-transport. Until now, those depended on HTTPS being
      available. This change will make it so that those requests succeed if HTTPS
      *or* SSH *or* OSSH are available.

TODO

- Current server iptables settings probably need to be modified to allow the 
  handshake (etc.) to succeed through the transport.

- Make sure to test generated client. Embedded values should be different format now.

- Test real campaign (regexes, speed test, discovery).

- Test failover to temp-transport in ServerRequest. It won't happen naturally.
  Like, HTTPS is never going to fail for us in debugging without special effort.

- Determine if WinHttpGetIEProxyConfigForCurrentUser is the correct/best way to
  deterine the correct local proxy settings (both when our LocalProxy is and 
  isn't up). See HTTPSRequest::GetSystemDefaultHTTPSProxy().
  - SystemProxySettings has some code to determine local proxy info, but then
    we need to figure out which connection name to use. And maybe using a 
    WinHTTP function in HTTPSRequest makes more sense.

- Test None/null values in the handshake JSON. For example, I think the upgrade
  version can theoretically be None/null. The desired behaviour is that it get
  the default empty string value when pulling it out of JSON.

- Known bug that might be too minor to fix: If polipo or plonk crashes, 
  LocalProxy will try to send its last /status before the SystemProxySettings
  are restored (cleared). ServerRequest will first try HTTPS:8080 and HTTPS:443
  through the proxy, which will quickly fail (because either polipo or plonk isn't 
  there); then it will brink up a temp transport (which may or may not work --
  the "current transport" is excluded from consideration). This is surely 
  fixable, but it's not immediately obvious how. And it'll be unusual. And 
  it will sometimes succeed.

- Rethink if it makes sense to exclude the "current" transport from 
  temp/failover transports. 

- Make sure session reconstruction is okay with the fact that the final /status
  might use a different protocol than the rest of the session. (Better be.)

- After resuming from system sleep, my system ended up in a state where I could
  no longer connect at all -- even after closing the app and clearing proxy 
  settings and restarting it. (Hopefully after reboot...)

- If one "synchronized exit" worker threat exits messily, the other one should
  not do the clean, StopImminent exit. In particular, if Plonk does, Polipo 
  should not try to do a final /status (until cleanup) -- it won't succeed, 
  and it'll take a long time.

- Temp-transport failover (like, one of the transports actually failing) might
  not be behaving correctly. Test.

- Maybe now, maybe future: Remember which method worked last time for 
  extra-transport requests, and skip to it next time.

----END ssh-with-no-handshake NOTES----
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


Security Properties
--------------------------------------------------------------------------------

Psiphon 3 is a circumvention system. To accomplish its design goals, it uses computer
security technology including encryption and digital signatures. Using these algorithms
does not mean Psiphon 3 offers additional security properties such as privacy or
authentication of destination sites for users' Internet traffic.

- Confidentiality. Traffic routed between a user's computer and a Psiphon proxy is encrypted
and authenticated (using standard SSH and L2TP/IPSec VPN algorithms). The purpose of this
encryption is to evade censorship based on deep-packet inspection of traffic, not to add
confidentiality to the user's Internet traffic. The user's traffic is plaintext to the Psiphon
proxy and to the Internet at large as it egresses from the Psiphon proxy. Put simply,
Psiphon does not add HTTPS or equivilent security where it is not already in place at the
application level.

- Anonymity. Psiphon is not an anonymity solution such as
[Tor](https://www.torproject.org).
If a user connects to a Psiphon proxy which is beyond the monitoring of the censor he or she
is circumventing, then the censor will only see that the user is sending encrypted traffic to
a Psiphon proxy. The censor will know the user is using Psiphon. Psiphon does not defend against
traffic analysis attacks the censor may deploy against traffic flowing to Psiphon proxies. 
The Psiphon proxy will know where the user is coming from, what their unencrypted traffic is, and
what their destination is, and so the user is necessarily putting trust in the entity running the
Psiphon proxy.

- Integrity. Psiphon was not designed to add integrity to Internet traffic. However, in the case
where a censor is intercepting SSL/TLS traffic using compromised root CA keys, Psiphon adds
integrity; but only if the user has secured a trusted client out of band and is using a Psiphon
proxy beyond the control of the censor. Simply, the user's HTTPS traffic happens to bypass the
censors man-in-the-middle attack, and the Psiphon authentication system does not rely on the 
commercial Certificate Authority for most use cases. See the design paper for details on
Psiphon PKI.

- Availability. Psiphon is designed to make available Internet content that's otherwise censored.
This is its primary design goal.


Documentation
--------------------------------------------------------------------------------

IMPORTANT: See the 
[design paper](https://bitbucket.org/psiphon/psiphon-circumvention-system/downloads/DESIGN.pdf), 
included with this software distribution, for important information regarding 
security limitations and user privacy issues.


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
