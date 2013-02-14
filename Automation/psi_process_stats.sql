-- Table: processed_logs

CREATE TABLE processed_logs
(
  host_id text,
  last_timestamp text,
  CONSTRAINT processed_logs_pkey PRIMARY KEY (host_id)
)
WITH (
  OIDS=FALSE
);

-- Table: connected

CREATE TABLE connected
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  session_id text,
  last_connected timestamp with time zone DEFAULT NULL,
  processed integer NOT NULL DEFAULT 0,
  id bigserial NOT NULL,
  CONSTRAINT connected_pkey PRIMARY KEY (id),
  CONSTRAINT connected_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, session_id, last_connected)
)
WITH (
  OIDS=FALSE
);

-- Table: disconnected

CREATE TABLE disconnected
(
  "timestamp" timestamp with time zone,
  host_id text,
  relay_protocol text,
  session_id text,
  processed integer NOT NULL DEFAULT 0,
  id bigserial NOT NULL,
  CONSTRAINT disconnected_pkey PRIMARY KEY (id),
  CONSTRAINT disconnected_unique UNIQUE ("timestamp", host_id, relay_protocol, session_id)
)
WITH (
  OIDS=FALSE
);

-- Table: discovery

CREATE TABLE discovery
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  discovery_server_id text,
  client_unknown text,
  id bigserial NOT NULL,
  CONSTRAINT discovery_pkey PRIMARY KEY (id),
  CONSTRAINT discovery_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, discovery_server_id, client_unknown)
)
WITH (
  OIDS=FALSE
);

-- Table: download

CREATE TABLE download
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  id bigserial NOT NULL,
  CONSTRAINT download_pkey PRIMARY KEY (id),
  CONSTRAINT download_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device)
)
WITH (
  OIDS=FALSE
);

-- Table: failed

CREATE TABLE failed
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  error_code text,
  id bigserial NOT NULL,
  CONSTRAINT failed_pkey PRIMARY KEY (id),
  CONSTRAINT failed_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, error_code)
)
WITH (
  OIDS=FALSE
);

-- Table: handshake

CREATE TABLE handshake
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  id bigserial NOT NULL,
  CONSTRAINT handshake_pkey PRIMARY KEY (id),
  CONSTRAINT handshake_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device)
)
WITH (
  OIDS=FALSE
);

-- Table: started

CREATE TABLE started
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  id bigserial NOT NULL,
  CONSTRAINT started_pkey PRIMARY KEY (id),
  CONSTRAINT started_unique UNIQUE ("timestamp", host_id, server_id)
)
WITH (
  OIDS=FALSE
);

-- Table: status

CREATE TABLE status
(
  "timestamp" timestamp with time zone,
  host_id text,
  relay_protocol text,
  session_id text,
  processed integer NOT NULL DEFAULT 0,
  id bigserial NOT NULL,
  CONSTRAINT status_pkey PRIMARY KEY (id),
  CONSTRAINT status_unique UNIQUE ("timestamp", host_id, relay_protocol, session_id)
)
WITH (
  OIDS=FALSE
);

-- Table: bytes_transferred

CREATE TABLE bytes_transferred
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  session_id text DEFAULT NULL,
  connected text DEFAULT NULL,
  bytes integer NOT NULL,
  id bigserial NOT NULL,
  CONSTRAINT bytes_transferred_pkey PRIMARY KEY (id),
  CONSTRAINT bytes_transferred_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, session_id, connected, bytes)
)
WITH (
  OIDS=FALSE
);

-- Table: page_views

CREATE TABLE page_views
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  session_id text DEFAULT NULL,
  connected text DEFAULT NULL,
  pagename text,
  viewcount integer NOT NULL,
  id bigserial NOT NULL,
  CONSTRAINT page_views_pkey PRIMARY KEY (id),
  CONSTRAINT page_views_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, session_id, connected, pagename, viewcount)
)
WITH (
  OIDS=FALSE
);

-- Table: https_requests

CREATE TABLE https_requests
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  session_id text DEFAULT NULL,
  connected text DEFAULT NULL,
  "domain" text,
  count integer NOT NULL,
  id bigserial NOT NULL,
  CONSTRAINT https_requests_pkey PRIMARY KEY (id),
  CONSTRAINT https_requests_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, session_id, connected, "domain", count)
)
WITH (
  OIDS=FALSE
);

-- Table: speed

CREATE TABLE speed
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  "operation" text,
  info text,
  milliseconds integer,
  "size" integer,
  id bigserial NOT NULL,
  CONSTRAINT speed_pkey PRIMARY KEY (id),
  CONSTRAINT speed_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, "operation", info, milliseconds, "size")
)
WITH (
  OIDS=FALSE
);

-- Table: feedback

CREATE TABLE feedback
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  session_id text,
  question text,
  answer text,
  id bigserial NOT NULL,
  CONSTRAINT feedback_pkey PRIMARY KEY (id),
  CONSTRAINT feedback_unique UNIQUE ("timestamp", host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, session_id, question, answer)
)
WITH (
  OIDS=FALSE
);

-- Table: "session"

CREATE TABLE "session"
(
  host_id text,
  server_id text,
  client_region text,
  client_city text DEFAULT NULL,
  client_isp text DEFAULT NULL,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  client_platform text,
  relay_protocol text,
  tunnel_whole_device int NOT NULL DEFAULT 0,
  session_id text,
  last_connected timestamp with time zone DEFAULT NULL,
  session_start_timestamp timestamp with time zone,
  session_end_timestamp timestamp with time zone,
  id bigserial NOT NULL,
  connected_id bigint NOT NULL,
  CONSTRAINT session_pkey PRIMARY KEY (id),
  CONSTRAINT connected_id FOREIGN KEY (connected_id)
      REFERENCES connected (id) MATCH SIMPLE
      ON UPDATE NO ACTION ON DELETE NO ACTION,
  CONSTRAINT session_host_id_key UNIQUE (host_id, server_id, client_region, client_city, client_isp, propagation_channel_id, sponsor_id, client_version, client_platform, relay_protocol, tunnel_whole_device, session_id, last_connected, session_start_timestamp, session_end_timestamp)
)
WITH (
  OIDS=FALSE
);

-- Session reconstruction

CREATE INDEX connected_unprocessed_index ON connected (processed) WHERE processed = 0;

CREATE INDEX disconnected_session_reconstruction_index
  ON disconnected
  (processed, session_id, relay_protocol, host_id, "timestamp");    

CREATE INDEX status_session_reconstruction_index
  ON status
  (processed, session_id, relay_protocol, host_id, "timestamp");

-- Finds the /disconnected record that matches the given /connected record.
-- Returns NULL (empty record) if not found.
-- Has the side effect of marking earlier matching /disconnected records as processed.
-- (But not the record being returned.) This is because they will never be 
-- returned from this function, so it's faster to completely exclude them.
CREATE OR REPLACE FUNCTION findMatchingDisconnect(connected_record connected) 
RETURNS disconnected AS $$
DECLARE
  result disconnected%ROWTYPE;
BEGIN

  -- Select the *nearest* matching disconnected entry (youngest that's older).
  SELECT * INTO result 
    FROM disconnected 
    WHERE processed = 0
      AND session_id = connected_record.session_id 
      AND relay_protocol = connected_record.relay_protocol
      AND host_id = connected_record.host_id
      -- And it has the closest following timestamp to the given connected record
      AND timestamp > connected_record.timestamp
    ORDER BY timestamp ASC
    LIMIT 1;

  -- Did we find a match?
  IF result IS NOT NULL THEN
    -- Mark any earlier matching /disconnected records as processed, since 
    -- they'll never be used again.
    UPDATE disconnected 
      SET processed = 1
      WHERE processed = 0
        AND session_id = result.session_id 
        AND relay_protocol = result.relay_protocol
        AND host_id = result.host_id
        -- Strictly-less-than means it won't match result.
        AND timestamp < result.timestamp;

    -- Also mark any matching /status records as processed, since they'll never
    -- be used either.
    UPDATE status 
      SET processed = 1
      WHERE processed = 0
        AND session_id = result.session_id 
        AND relay_protocol = result.relay_protocol
        AND host_id = result.host_id
        AND timestamp <= result.timestamp;

    RETURN result;
  END IF;

  RETURN NULL;

END;
$$ LANGUAGE plpgsql;

-- Finds the latest /status record that matches the given /connected record.
-- Returns NULL (empty record) if not found.
-- Has the side effect of marking earlier matching /status records as processed.
-- (But not the record being returned.) This is because they will never be 
-- returned from this function, so it's faster to completely exclude them.
CREATE OR REPLACE FUNCTION findMatchingStatus(connected_record connected) 
RETURNS status AS $$
DECLARE
  result status%ROWTYPE;
BEGIN

  -- Select the *oldest* matching status entry.
  SELECT * INTO result 
    FROM status 
    WHERE processed = 0
      AND session_id = connected_record.session_id 
      AND relay_protocol = connected_record.relay_protocol
      AND host_id = connected_record.host_id
      -- And it has the closest following timestamp to the given connected record
      AND timestamp > connected_record.timestamp
    ORDER BY timestamp DESC
    LIMIT 1;

  -- Did we find a match?
  IF result IS NOT NULL THEN
    -- Mark the earlier matching /status record and any earlier matching /status
    -- records as processed, since they'll never be used again.
    UPDATE status
      SET processed = 1
      WHERE processed = 0
        AND session_id = result.session_id 
        AND relay_protocol = result.relay_protocol
        AND host_id = result.host_id
        -- Strictly-less-than means it won't match result.
        AND timestamp < result.timestamp;

    RETURN result;
  END IF;

  RETURN NULL;

END;
$$ LANGUAGE plpgsql;

-- Reconstruct sessions from /connected, /disconnected, and /status records.
CREATE OR REPLACE FUNCTION doSessionReconstruction() RETURNS integer AS $$
DECLARE
  connected_record connected%ROWTYPE;
  disconnected_record disconnected%ROWTYPE;
  status_record status%ROWTYPE;
  result integer := 0;
  disconnected_count integer := 0;
  status_count integer := 0;
  expired_count integer := 0;
  nomatch_count integer := 0;
  session_end timestamptz;
BEGIN

  FOR connected_record IN
      SELECT * FROM connected
        WHERE processed = 0
        ORDER BY connected.timestamp ASC LOOP
    result := result + 1;
    session_end := NULL;

    -- Look for a matching /disconnected entry.
    SELECT * INTO disconnected_record FROM findMatchingDisconnect(connected_record);
    IF disconnected_record IS NOT NULL THEN
      -- Matching /disconnected entry found.
      disconnected_count := disconnected_count + 1;

      -- Setting this value will cause a session insert below
      session_end := disconnected_record.timestamp;

      -- Mark the connected and disconnected records as processed.
      UPDATE connected SET processed = 1 WHERE id = connected_record.id;
      UPDATE disconnected SET processed = 1 WHERE id = disconnected_record.id;
    ELSE
      -- No matching disconnected entry; look for a matching /status entry.
      SELECT * INTO status_record FROM findMatchingStatus(connected_record);
      IF status_record IS NOT NULL THEN
        -- Matching /status entry found. Check if it's old enough that we should
        -- close the session.
        IF (NOW() - status_record.timestamp) > '24 hours'::interval THEN
          status_count := status_count + 1;

          -- Setting this value will cause a session insert below
          session_end := status_record.timestamp;

          -- Mark the connected and status records as processed.
          UPDATE connected SET processed = 1 WHERE id = connected_record.id;
          UPDATE status SET processed = 1 WHERE id = status_record.id;
        END IF;
      ELSE
        -- No matching /disconnected or /status entry found.
        -- If this /connected entry is old, give up on it: mark it as processed
        -- so we don't have to keep checking it.
        -- And create a zero-duration session for it.

        IF (NOW() - connected_record.timestamp) > '24 hours'::interval THEN

          -- Setting this value will cause a session insert below
          session_end := connected_record.timestamp;

          -- Mark /connected record as expired.
          UPDATE connected 
            SET processed = 2
            WHERE id = connected_record.id;

          expired_count := expired_count + 1;
        ELSE
          -- No matching /disconnected or /status, but not too old to expire it.
          nomatch_count := nomatch_count + 1;
        END IF;
      END IF;
    END IF;

    IF session_end IS NOT NULL THEN
      INSERT INTO session 
        (host_id, server_id, client_region,
         client_city, client_isp,
         propagation_channel_id,
         sponsor_id, client_version, client_platform,
         relay_protocol, tunnel_whole_device, session_id,
         last_connected,
         session_start_timestamp, session_end_timestamp, connected_id)
      VALUES
        (connected_record.host_id, connected_record.server_id, 
         connected_record.client_region,
         connected_record.client_city,
         connected_record.client_isp,
         connected_record.propagation_channel_id,
         connected_record.sponsor_id, connected_record.client_version, 
         connected_record.client_platform, connected_record.relay_protocol,
         connected_record.tunnel_whole_device,
         connected_record.session_id,
         connected_record.last_connected,
         connected_record.timestamp, 
         session_end, connected_record.id);
    END IF;

  END LOOP;

  RETURN result;

END;
$$ LANGUAGE plpgsql;

-- Table: propagation_channel

CREATE TABLE propagation_channel
(
  id text,
  name text,
  CONSTRAINT propagation_channel_pkey PRIMARY KEY (id)
)
WITH (
  OIDS=FALSE
);

-- Table: sponsor

CREATE TABLE sponsor
(
  id text,
  name text,
  CONSTRAINT sponsor_pkey PRIMARY KEY (id)
)
WITH (
  OIDS=FALSE
);

-- Table: server

CREATE TABLE server
(
  id text,
  type text,
  datacenter_name text,
  CONSTRAINT server_pkey PRIMARY KEY (id)
)
WITH (
  OIDS=FALSE
);

-- View: psiphon_discovery

CREATE OR REPLACE VIEW psiphon_discovery AS
SELECT
  discovery."timestamp",
  discovery.host_id,
  discovery.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  discovery.client_region,
  discovery.client_city,
  discovery.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  discovery.client_version,
  discovery.client_platform,
  discovery.relay_protocol,
  discovery.tunnel_whole_device,
  discovery.discovery_server_id,
  discovery.client_unknown,
  discovery.id
FROM discovery
JOIN propagation_channel ON propagation_channel.id = discovery.propagation_channel_id
JOIN sponsor ON sponsor.id = discovery.sponsor_id
JOIN server ON server.id = discovery.server_id;

-- View: psiphon_download

CREATE OR REPLACE VIEW psiphon_download AS
SELECT
  download."timestamp",
  download.host_id,
  download.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  download.client_region,
  download.client_city,
  download.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  download.client_version,
  download.client_platform,
  download.relay_protocol,
  download.tunnel_whole_device,
  download.id
FROM download
JOIN propagation_channel ON propagation_channel.id = download.propagation_channel_id
JOIN sponsor ON  sponsor.id = download.sponsor_id
JOIN server ON server.id = download.server_id;

-- View: psiphon_failed

CREATE OR REPLACE VIEW psiphon_failed AS
SELECT
  failed."timestamp",
  failed.host_id,
  failed.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  failed.client_region,
  failed.client_city,
  failed.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  failed.client_version,
  failed.client_platform,
  failed.relay_protocol,
  failed.tunnel_whole_device,
  failed.error_code,
  failed.id
FROM failed
JOIN propagation_channel ON propagation_channel.id = failed.propagation_channel_id
JOIN sponsor ON  sponsor.id = failed.sponsor_id
JOIN server ON server.id = failed.server_id;

-- View: psiphon_handshake

CREATE OR REPLACE VIEW psiphon_handshake AS
SELECT
  handshake."timestamp",
  handshake.host_id,
  handshake.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  handshake.client_region,
  handshake.client_city,
  handshake.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  handshake.client_version,
  handshake.client_platform,
  handshake.relay_protocol,
  handshake.tunnel_whole_device,
  handshake.id
FROM handshake
JOIN propagation_channel ON propagation_channel.id = handshake.propagation_channel_id
JOIN sponsor ON  sponsor.id = handshake.sponsor_id
JOIN server ON server.id = handshake.server_id;

-- View: psiphon_bytes_transferred

CREATE OR REPLACE VIEW psiphon_bytes_transferred AS
SELECT
  bytes_transferred."timestamp",
  bytes_transferred.host_id,
  bytes_transferred.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  bytes_transferred.client_region,
  bytes_transferred.client_city,
  bytes_transferred.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  bytes_transferred.client_version,
  bytes_transferred.client_platform,
  bytes_transferred.relay_protocol,
  bytes_transferred.tunnel_whole_device,
  bytes_transferred.session_id,
  bytes_transferred.connected,
  bytes_transferred.bytes,
  bytes_transferred.id
FROM bytes_transferred
JOIN propagation_channel ON propagation_channel.id = bytes_transferred.propagation_channel_id
JOIN sponsor ON  sponsor.id = bytes_transferred.sponsor_id
JOIN server ON server.id = bytes_transferred.server_id;

-- View: psiphon_page_views

CREATE OR REPLACE VIEW psiphon_page_views AS
SELECT
  page_views."timestamp",
  page_views.host_id,
  page_views.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  page_views.client_region,
  page_views.client_city,
  page_views.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  page_views.client_version,
  page_views.client_platform,
  page_views.relay_protocol,
  page_views.tunnel_whole_device,
  page_views.session_id,
  page_views.connected,
  page_views.pagename,
  page_views.viewcount,
  page_views.id
FROM page_views
JOIN propagation_channel ON propagation_channel.id = page_views.propagation_channel_id
JOIN sponsor ON  sponsor.id = page_views.sponsor_id
JOIN server ON server.id = page_views.server_id;

-- View: psiphon_https_requests

CREATE OR REPLACE VIEW psiphon_https_requests AS
SELECT
  https_requests."timestamp",
  https_requests.host_id,
  https_requests.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  https_requests.client_region,
  https_requests.client_city,
  https_requests.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  https_requests.client_version,
  https_requests.client_platform,
  https_requests.relay_protocol,
  https_requests.tunnel_whole_device,
  https_requests.session_id,
  https_requests.connected,
  https_requests."domain",
  https_requests.count,
  https_requests.id
FROM https_requests
JOIN propagation_channel ON propagation_channel.id = https_requests.propagation_channel_id
JOIN sponsor ON  sponsor.id = https_requests.sponsor_id
JOIN server ON server.id = https_requests.server_id;

-- View: psiphon_speed

CREATE OR REPLACE VIEW psiphon_speed AS
SELECT
  speed."timestamp",
  speed.host_id,
  speed.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  speed.client_region,
  speed.client_city,
  speed.client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  speed.client_version,
  speed.client_platform,
  speed.relay_protocol,
  speed.tunnel_whole_device,
  speed."operation",
  speed.info,
  speed.milliseconds,
  speed."size",
  speed.id
FROM speed
JOIN propagation_channel ON propagation_channel.id = speed.propagation_channel_id
JOIN sponsor ON  sponsor.id = speed.sponsor_id
JOIN server ON server.id = speed.server_id;

-- View: psiphon_session

CREATE OR REPLACE VIEW psiphon_session AS
SELECT
  "session".host_id,
  "session".server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  "session".client_region,
  "session".client_city,
  "session".client_isp,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  "session".client_version,
  "session".client_platform,
  "session".relay_protocol,
  "session".tunnel_whole_device,
  "session".session_id,
  "session".last_connected,
  "session".session_start_timestamp,
  "session".session_end_timestamp,
  "session".id
FROM "session"
JOIN propagation_channel ON propagation_channel.id = "session".propagation_channel_id
JOIN sponsor ON  sponsor.id = "session".sponsor_id
JOIN server ON server.id = "session".server_id;

-- View: psiphon_feedback

CREATE OR REPLACE VIEW psiphon_feedback AS
SELECT
  feedback."timestamp",
  feedback.host_id,
  feedback.server_id,
  server.type AS server_type,
  server.datacenter_name AS server_datacenter_name,
  feedback.client_region,
  feedback.client_city,
  feedback.client_isp,
  feedback.propagation_channel_id,
  feedback.sponsor_id,
  propagation_channel.name AS propagation_channel_name,
  sponsor.name AS sponsor_name,
  feedback.client_version,
  feedback.client_platform,
  feedback.relay_protocol,
  feedback.tunnel_whole_device,
  feedback.session_id,
  feedback.question,
  feedback.answer,
  feedback.id
FROM feedback 
JOIN propagation_channel ON propagation_channel.id = feedback.propagation_channel_id
JOIN sponsor ON  sponsor.id = feedback.sponsor_id
JOIN server ON server.id = feedback.server_id;

