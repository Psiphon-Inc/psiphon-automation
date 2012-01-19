#!/usr/bin/env perl


# Adapted from: http://tech.groups.yahoo.com/group/postfix-users/message/255133

use strict;
use warnings;
use Symbol;
sub count {
        my ($dir) = @_;
        my $dh = gensym();
        my $c = 0;
        opendir($dh, $dir) or die "$0: opendir: $dir: $!\n";
        while (my $f = readdir($dh)) {
                if ($f =~ m{^[A-F0-9]{5,}$}) {
                        ++$c;
                } elsif ($f =~ m{^[A-F0-9]$}) {
                        $c += count("$dir/$f");
                }
        }
        closedir($dh) or die "closedir: $dir: $!\n";
        return $c;
}

#my $qdir = `postconf -h queue_directory`; # this should work, but doesn't
#my $qdir = shift(@ARGV) or die "Usage: $0 queue-directory\n";
# Hard-coding this path is very unfortunate, but other options aren't working so well.
my $qdir = "/var/spool/postfix"; 
chdir($qdir) or die "$0: chdir: $qdir: $!\n";
printf "Incoming: %d\n", count("incoming");
printf "Active: %d\n", count("active");
printf "Deferred: %d\n", count("deferred");
printf "Bounced: %d\n", count("bounce");
printf "Hold: %d\n", count("hold");
printf "Corrupt: %d\n", count("corrupt");
