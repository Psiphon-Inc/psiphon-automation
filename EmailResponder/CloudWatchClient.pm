# Copyright 2013 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not 
# use this file except in compliance with the License. A copy of the License 
# is located at
#
#        http://aws.amazon.com/apache2.0/
#
# or in the "LICENSE" file accompanying this file. This file is distributed 
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either 
# express or implied. See the License for the specific language governing 
# permissions and limitations under the License.

package CloudWatchClient;

use strict;
use warnings;
use base 'Exporter';
our @EXPORT = qw();
use Switch;
use Digest::SHA qw(hmac_sha256_base64);
use URI::Escape qw(uri_escape_utf8);
use Compress::Zlib;
use File::Basename;
use LWP;

use LWP::Simple qw($ua get);
$ua->timeout(2); # timeout for meta-data calls

our $client_version = '1.1.0';
our $service_version = '2010-08-01';
our $compress_threshold_bytes = 2048;
our $meta_data_ttl = 21600; # 6 hours
our $max_meta_data_ttl = 86400; # 1 day
our $http_request_timeout = 5; # seconds

# RFC3986 unsafe characters
our $unsafe_characters = "^A-Za-z0-9\-\._~";

our $region;
our $avail_zone;
our $instance_id;
our $image_id;
our $instance_type;
our $as_group_name; 	 
our $meta_data_loc = '/var/tmp/aws-mon';

#
# Queries meta data for the current EC2 instance.
#
sub get_meta_data
{
  my $resource = shift;
  my $use_cache = shift;
  my $data_value = read_meta_data($resource, $meta_data_ttl);
  
  if (!defined($data_value) || length($data_value) == 0) {
    my $base_uri = 'http://169.254.169.254/latest/meta-data';
    $data_value = get $base_uri.$resource;
    if ($use_cache) {
      write_meta_data($resource, $data_value);
    }
  }
  
  return $data_value;
}

#
# Reads meta-data from the local filesystem.
#
sub read_meta_data
{
  my $resource = shift;
  my $default_ttl = shift;
  
  my $location = $ENV{'AWS_EC2CW_META_DATA'};
  if (!defined($location) || length($location) == 0) { 	 
    $location = $meta_data_loc if ($meta_data_loc); 	 
  }
  my $meta_data_ttl = $ENV{'AWS_EC2CW_META_DATA_TTL'};
  $meta_data_ttl = $default_ttl if (!defined($meta_data_ttl));
  
  my $data_value;
  if ($location)
  {
    my $filename = $location.$resource;
    if (-d $filename) {
      $data_value = `/bin/ls $filename`;
      chomp($data_value);
    } elsif (-e $filename) {
      my $updated = (stat($filename))[9];
      my $file_age = time() - $updated;
      if ($file_age < $meta_data_ttl)
      {
        open MDATA, "$filename";
        while(my $line = <MDATA>) {
          $data_value .= $line;
        }
        close MDATA;
        chomp $data_value;
      }
    }
  }
  
  return $data_value;
}

#
# Writes meta-data to the local filesystem. 	 
# 	 
sub write_meta_data 	 
{ 	 
  my $resource = shift; 	 
  my $data_value = shift; 	 
   
  if ($resource && $data_value) 	 
  { 	 
    my $location = $ENV{'AWS_EC2CW_META_DATA'}; 	 
    if (!defined($location) || length($location) == 0) { 	 
      $location = $meta_data_loc if ($meta_data_loc); 	 
    } 	 

    if ($location) 	 
    { 	 
      my $filename = $location.$resource; 	 
      my $directory = dirname($filename); 	 
      `/bin/mkdir -p $directory` unless -d $directory; 	 

      open MDATA, ">$filename"; 	 
      print MDATA $data_value; 	 
      close MDATA; 	 
    } 	 
  } 	 
}

#
# Builds up ec2 endpoint URL for this region.
#
sub get_ec2_endpoint
{
  my $region = get_region();
  
  if ($region) {
    return "https://ec2.$region.amazonaws.com/"; 
  }
  
  return 'https://ec2.amazonaws.com/';
}

#
# Obtains Auto Scaling group name by making EC2 API call.
#
sub get_auto_scaling_group
{
  if ($as_group_name) {
    return (200, $as_group_name);
  }

  # Try getting AS group name from the local cache and avoid calling EC2 API for
  # at least several hours. AS group name is not something that changes at all
  # but just in case if it changes at some point, read the value from the tag.
  
  my $resource = '/as-group-name';
  $as_group_name = read_meta_data($resource, $meta_data_ttl);
  if ($as_group_name) {
    return (200, $as_group_name);
  }

  my $opts = shift;
  
  my %ec2_opts = ();
  $ec2_opts{'aws-credential-file'} = $opts->{'aws-credential-file'};
  $ec2_opts{'aws-access-key-id'} = $opts->{'aws-access-key-id'};
  $ec2_opts{'aws-secret-key'} = $opts->{'aws-secret-key'};
  $ec2_opts{'short-response'} = 0;
  $ec2_opts{'retries'} = 1;
  $ec2_opts{'verbose'} = $opts->{'verbose'};
  $ec2_opts{'verify'} = $opts->{'verify'};
  $ec2_opts{'user-agent'} = $opts->{'user-agent'};
  $ec2_opts{'version'} = '2011-12-15';
  $ec2_opts{'url'} = get_ec2_endpoint();
  $ec2_opts{'aws-iam-role'} = $opts->{'aws-iam-role'};
  
  my %ec2_params = ();
  $ec2_params{'Action'} = 'DescribeTags';
  $ec2_params{'Filter.1.Name'} = 'resource-id';
  $ec2_params{'Filter.1.Value.1'} = get_instance_id();
  $ec2_params{'Filter.2.Name'} = 'key';
  $ec2_params{'Filter.2.Value.1'} = 'aws:autoscaling:groupName';
  
  my ($code, $reply) = call(\%ec2_params, \%ec2_opts);
  
  if ($code == 200)
  {
    my $pattern = "<value>(.*?)<\/value>";
    $reply =~ /$pattern/s;
    if ($1) {
      $reply = $1;
      write_meta_data($resource, $reply);
    }
    else {
      undef $reply;
    }
  }
  else
  {
    my $pattern = "<Message>(.*?)<\/Message>";
    $reply =~ /$pattern/s;
    $reply = $1 if ($1);
  }
  
  # In case when EC2 API call fails for whatever reason, keep using the older
  # value if it is present. Only ofter one day, assume this value is obsolete.
  # AS group name is not something that is changing on the fly anyway.
  
  if (!$as_group_name)
  {
    # EC2 call failed, so try using older value for AS group name
    $as_group_name = read_meta_data($resource, $max_meta_data_ttl);
    if ($as_group_name) {
      return (200, $as_group_name);
    }
  }

  return ($code, $reply);
}

#
# Obtains EC2 instance id from meta data.
#
sub get_instance_id
{
  if (!$instance_id) {
    $instance_id = get_meta_data('/instance-id', 1);
  }
  return $instance_id;
}

#
# Obtains EC2 instance type from meta data.
#
sub get_instance_type
{
  if (!$instance_type) {
    $instance_type = get_meta_data('/instance-type', 1);
  }
  return $instance_type;
}

#
# Obtains EC2 image id from meta data.
#
sub get_image_id
{
  if (!$image_id) {
    $image_id = get_meta_data('/ami-id', 1);
  }
  return $image_id;
}

#
# Obtains EC2 avilability zone from meta data.
#
sub get_avail_zone
{
  if (!$avail_zone) {
    $avail_zone = get_meta_data('/placement/availability-zone', 1);
  }
  return $avail_zone;
}

#
# Extracts region from avilability zone.
#
sub get_region
{
  if (!$region) {
    my $azone = get_avail_zone();
    if ($azone) {
      $region = substr($azone, 0, -1);
    }
  }
  return $region;
}

#
# Buids up the endpoint based on the provided region.
#
sub get_endpoint
{
  my $region = get_region();
  
  if ($region) {
    return "https://monitoring.$region.amazonaws.com/";
  }
  
  return 'https://monitoring.amazonaws.com/';
}

#
# Read credentials from the IAM Role Metadata.
#
sub prepare_iam_role
{
  my $opts = shift;
  my $verbose = $opts->{'verbose'};
  my $outfile = $opts->{'output-file'};
  my $iam_role = $opts->{'aws-iam-role'};
  my $iam_dir = "/iam/security-credentials/";

  # if am_role is not explicitly specified 
  if (!defined($iam_role)) {
    my $roles = get_meta_data($iam_dir, 0);
    my $nr_of_roles = $roles =~ tr/\n//;

    print_out("No credential methods are specified. Trying default IAM role.", $outfile) if $verbose;
    if ($roles eq "") {
      return(0, "No IAM role is associated with this EC2 instance.");
    } elsif ($nr_of_roles == 0) {
      # if only one role
      $iam_role = $roles;
    } else {
      $roles =~ s/\n/, /g; # puts all the roles on one line 
      $roles =~ s/, $// ; # deletes the comma at the end
      return(0, "More than one IAM roles are associated with this EC2 instance: $roles.");
    }
  }
  my $role_content = get_meta_data(($iam_dir.$iam_role), 0);

  # Could not find the IAM role metadata
  if(!$role_content) {
    my $roles = get_meta_data($iam_dir, 0);
    my $roles_message;
    if($roles) {
      $roles =~ s/\n/, /g; # puts all the roles on one line
      $roles =~ s/, $// ; # deletes the comma at the end
      $roles_message = "Available roles: " . $roles;
    } else {
      $roles_message = "This EC2 instance does not have an IAM role associated with it.";
    }
    return(0, "Failed to obtain credentials for IAM role $iam_role. $roles_message");
  }

  print_out("Using IAM role <$iam_role>", $outfile) if $verbose;
  my $id;
  my $key;
  my $token;
  while ($role_content =~ /(.*)\n/g ) {
    
    my $line = $1;
    if ( $line =~ /"AccessKeyId"[ \t]*:[ \t]*"(.+)"/) {
      $id = $1;
      next;
    }
  
    if ( $line =~ /"SecretAccessKey"[ \t]*:[ \t]*"(.+)"/) {
      $key = $1;
      next;
    }
    
    if ( $line =~ /"Token"[ \t]*:[ \t]*"(.+)"/) {
      $token = $1;
      next;
    }
    
  }

  my $role_statement = "from IAM role <$iam_role>";
  if (!defined($id) && !defined($key)) {
    return(0, "Failed to parse AWS access key id and secret key $role_statement.");
  } elsif (!defined($id)) {
    return(0, "Failed to parse AWS access key id $role_statement.");
  } elsif (!defined($key)) {
    return(0, "Failed to parse AWS secret key $role_statement.");
  }
  
  $opts->{'aws-access-key-id'} = $id;
  $opts->{'aws-secret-key'} = $key;
  $opts->{'aws-security-token'} = $token;
  return(1,'');
}

#
# Checks if credential set is present. If not, reads credentials from file.
#
sub prepare_credentials
{
  my $opts = shift;
  my $verbose = $opts->{'verbose'};
  my $outfile = $opts->{'output-file'};
  my $aws_access_key_id = $opts->{'aws-access-key-id'};
  my $aws_secret_key = $opts->{'aws-secret-key'};
  my $aws_credential_file = $opts->{'aws-credential-file'};
  
  if (defined($aws_access_key_id) && !$aws_access_key_id) {
    return(0, 'Provided empty AWS access key id.');
  }
  if (defined($aws_secret_key) && !$aws_secret_key) {
    return(0, 'Provided empty AWS secret key.');
  }  
  if ($aws_access_key_id && $aws_secret_key) {
    return(1, '');
  }
  
  if (!defined($aws_credential_file) || length($aws_credential_file) == 0) {
    my $env_creds_file = $ENV{'AWS_CREDENTIAL_FILE'};
    if (defined($env_creds_file) && length($env_creds_file) > 0) {
      $aws_credential_file = $env_creds_file;
    }
  }
  
  if ($aws_credential_file)
  {
    my $file = $aws_credential_file;
    open(FILE, '<:utf8', $file) or return(0, "Failed to open AWS credentials file <$file>");
    print_out("Using AWS credentials file <$aws_credential_file>", $outfile) if $verbose;
    
    while (my $line = <FILE>)
    {
      $line =~ /^$/ and next; # skip empty lines
      $line =~ /^#.*/ and next; # skip commented lines
      $line =~ /^\s*(.*?)=(.*?)\s*$/ or return(0, "Failed to parse AWS credential entry '$line' in <$file>.");
      my ($key, $value) = ($1, $2);
      switch ($key)
      {
        case 'AWSAccessKeyId' { $aws_access_key_id = $value; }
        case 'AWSSecretKey'   { $aws_secret_key = $value; }
      }
    }
    close (FILE);

    $opts->{'aws-access-key-id'} = $aws_access_key_id;
    $opts->{'aws-secret-key'} = $aws_secret_key;
  }
  
  if (!$aws_access_key_id || !$aws_secret_key) {
    # if all the credential methods failed, try iam_role
    # either the default or user specified IAM role
    return prepare_iam_role($opts);
  }
  
  return (1, '');
}

#
# Returns UTC time in required format.
#
sub get_timestamp
{
  my $time = shift;
  sprintf("%04d-%02d-%02dT%02d:%02d:%02d.000Z",
    sub {($_[5]+1900,$_[4]+1,$_[3],$_[2],$_[1],$_[0])}->(gmtime($time)));
}

#
# Prints out diagnostic message to a file or standard output.
#
sub print_out
{
  my $text = shift;
  my $filename = shift;
  
  if ($filename)
  {
    open OUT_STREAM, ">>$filename";
    print OUT_STREAM "$text\n";
    close OUT_STREAM;
  }
  else
  {
    print "$text\n";
  }
}

#
# Builds the service invocation payload including the signature.
#
sub build_payload
{
  my $params = shift;
  my $opts = shift;
  
  $params->{'AWSAccessKeyId'} = $opts->{'aws-access-key-id'};
  $params->{'Timestamp'} = get_timestamp(time());
  $params->{'SignatureMethod'}  = 'HmacSHA256';
  $params->{'SignatureVersion'} = '2';
  
  # if working with an IAM role, include the Security Token
  if($opts->{'aws-security-token'}) {
    $params->{'SecurityToken'} = $opts->{'aws-security-token'};
  }
  
  my $endpoint = $opts->{'url'};
  my $endpoint_name = $endpoint;
  if ( !($endpoint_name =~ s!^https?://(.*?)/?$!$1!) ) {
    return (0, "Invalid AWS endpoint URL <$endpoint>");
  }

  my $sign_data = '';
  $sign_data .= 'POST';
  $sign_data .= "\n";
  $sign_data .= $endpoint_name;
  $sign_data .= "\n";
  $sign_data .= '/';
  $sign_data .= "\n";

  my @args = ();
  for my $key (sort keys %{$params}) {
    my $value = $params->{$key};
    my ($ekey, $evalue) = (uri_escape_utf8($key, $unsafe_characters), 
      uri_escape_utf8($value, $unsafe_characters));
    push @args, "$ekey=$evalue";
  }
  
  my $query_string = join '&', @args;
  $sign_data .= $query_string;
  
  my $signature = hmac_sha256_base64($sign_data, $opts->{'aws-secret-key'}).'=';
  my $payload = $query_string.'&Signature='.uri_escape_utf8($signature);
  
  return (1, $payload);
}

#
# Makes a remote invocation to CloudWatch service.
#
sub call
{
  my $params = shift;
  my $opts = shift;
  
  my $endpoint;
  if (defined($opts->{'url'})) {
    $endpoint = $opts->{'url'};
  }
  else {
    $endpoint = get_endpoint();
    $opts->{'url'} = $endpoint;
  }
  
  if (!defined($opts->{'version'})) {
    $opts->{'version'} = $service_version;
  }
  $params->{'Version'} = $opts->{'version'};
  
  my $user_agent_string = "CloudWatch-Scripting/$client_version";
  if (defined($opts->{'user-agent'})) {
    $user_agent_string = $opts->{'user-agent'};
  }

  my $res_code;
  my $res_msg;
  my $payload;
  
  ($res_code, $res_msg) = prepare_credentials($opts);
  
  if ($res_code == 0) {
    return ($res_code, $res_msg);
  }
  
  ($res_code, $payload) = build_payload($params, $opts);
  
  if ($res_code == 0) {
    return ($res_code, $payload);
  }
  
  my $user_agent = new LWP::UserAgent(agent => $user_agent_string);
  $user_agent->timeout($http_request_timeout);
  my $request = new HTTP::Request 'POST', $endpoint;
  
  $request->content_type('application/x-www-form-urlencoded');
  $request->content($payload);
  
  if (defined($opts->{'enable-compression'}) && length($payload) > $compress_threshold_bytes) {
    $request->encode('gzip');
  }
  
  my $response;
  my $keep_trying = 1;
  my $call_attempts = 1;
  my $verbose = $opts->{'verbose'};
  my $outfile = $opts->{'output-file'};
  
  print_out("Endpoint: $endpoint", $outfile) if $verbose;
  print_out("Payload: $payload", $outfile) if $verbose;
  
  # initial and max delay in seconds between retries
  my $delay = 4; 
  my $max_delay = 16;
  
  if (defined($opts->{'retries'})) {
    $call_attempts += $opts->{'retries'};
  }  
  if (defined($opts->{'max-backoff-sec'})) {
    $max_delay = $opts->{'max-backoff-sec'};
  }

  my $response_code = 0;
  
  if ($opts->{'verify'}) {
    return (200, 'This is a verification run, not an actual response.');
  }
  
  for (my $i = 0; $i < $call_attempts && $keep_trying; ++$i)
  {
    my $attempt = $i + 1;
    $response = $user_agent->request($request);
    $response_code = $response->code;
    if ($verbose) {
      print_out("Received HTTP status $response_code on attempt $attempt", $outfile);
      if ($response_code != 200) {
        print_out($response->content, $outfile);
      }
    }
    $keep_trying = 0;
    if ($response_code >= 500) {
      $keep_trying = 1;
    } elsif ($response_code == 400) {
      # special case to handle throttling fault
      my $pattern = "<Code>Throttling<\/Code>";
      if ($response->content =~ m/$pattern/) {
        print_out("Request throttled.", $outfile) if $verbose;
        $keep_trying = 1;
      }
    }
    if ($keep_trying && $attempt < $call_attempts) {
      print_out("Waiting $delay seconds before next retry.", $outfile) if $verbose;
      sleep($delay);
      my $incdelay = $delay * 2;
      $delay = $incdelay > $max_delay ? $max_delay : $incdelay;
    }
  }
  
  my $response_content = $response->content;
  print_out($response_content, $outfile) if ($verbose && $response_code == 200);

  if ($opts->{'short-response'}) {
    my $pattern = $response->is_success ?
      "<RequestId>(.*?)<\/RequestId>" : "<Message>(.*?)<\/Message>";
    $response_content =~ /$pattern/s;
    if ($1) {
      $response_content = $1;
    }
  }

  return ($response->code, $response_content);
}

1;
