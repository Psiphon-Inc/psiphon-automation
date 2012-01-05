-- Table: connected

-- DROP TABLE connected;

CREATE TABLE connected
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  relay_protocol text,
  session_id text,
  id bigserial NOT NULL,
  CONSTRAINT connected_pkey PRIMARY KEY (id),
  CONSTRAINT connected_timestamp_key UNIQUE ("timestamp", host_id, server_id, client_region, propagation_channel_id, sponsor_id, client_version, relay_protocol, session_id)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE connected OWNER TO postgres;
GRANT ALL ON TABLE connected TO postgres;
GRANT ALL ON TABLE connected TO psiphon3;

-- Index: connected_client_region_index

-- DROP INDEX connected_client_region_index;

CREATE INDEX connected_client_region_index
  ON connected
  USING btree
  (client_region);

-- Index: connected_sponsor_id_index

-- DROP INDEX connected_sponsor_id_index;

CREATE INDEX connected_sponsor_id_index
  ON connected
  USING btree
  (sponsor_id);

-- Index: connected_timestamp_index

-- DROP INDEX connected_timestamp_index;

CREATE INDEX connected_timestamp_index
  ON connected
  USING btree
  ("timestamp");

-- Table: disconnected

-- DROP TABLE disconnected;

CREATE TABLE disconnected
(
  "timestamp" timestamp with time zone,
  host_id text,
  relay_protocol text,
  session_id text,
  id bigserial NOT NULL,
  CONSTRAINT disconnected_pkey PRIMARY KEY (id),
  CONSTRAINT disconnected_timestamp_key UNIQUE ("timestamp", host_id, relay_protocol, session_id)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE disconnected OWNER TO postgres;
GRANT ALL ON TABLE disconnected TO postgres;
GRANT ALL ON TABLE disconnected TO psiphon3;

-- Index: session_reconstruction

-- DROP INDEX session_reconstruction;

CREATE INDEX session_reconstruction
  ON disconnected
  USING btree
  ("timestamp", host_id, relay_protocol, session_id);

-- Table: discovery

-- DROP TABLE discovery;

CREATE TABLE discovery
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  discovery_server_id text,
  client_unknown text,
  id bigserial NOT NULL,
  CONSTRAINT discovery_pkey PRIMARY KEY (id),
  CONSTRAINT discovery_timestamp_key UNIQUE ("timestamp", host_id, server_id, client_region, propagation_channel_id, sponsor_id, client_version, discovery_server_id, client_unknown)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE discovery OWNER TO postgres;
GRANT ALL ON TABLE discovery TO postgres;
GRANT ALL ON TABLE discovery TO psiphon3;

-- Table: download

-- DROP TABLE download;

CREATE TABLE download
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  id bigserial NOT NULL,
  CONSTRAINT download_pkey PRIMARY KEY (id),
  CONSTRAINT download_timestamp_key UNIQUE ("timestamp", host_id, server_id, client_region, propagation_channel_id, sponsor_id, client_version)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE download OWNER TO postgres;
GRANT ALL ON TABLE download TO postgres;
GRANT ALL ON TABLE download TO psiphon3;

-- Table: failed

-- DROP TABLE failed;

CREATE TABLE failed
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  relay_protocol text,
  error_code text,
  id bigserial NOT NULL,
  CONSTRAINT failed_pkey PRIMARY KEY (id),
  CONSTRAINT failed_timestamp_key UNIQUE ("timestamp", host_id, server_id, client_region, propagation_channel_id, sponsor_id, client_version, relay_protocol, error_code)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE failed OWNER TO postgres;
GRANT ALL ON TABLE failed TO postgres;
GRANT ALL ON TABLE failed TO psiphon3;

-- Table: handshake

-- DROP TABLE handshake;

CREATE TABLE handshake
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  client_region text,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  id bigserial NOT NULL,
  CONSTRAINT handshake_pkey PRIMARY KEY (id),
  CONSTRAINT handshake_timestamp_key UNIQUE ("timestamp", host_id, server_id, client_region, propagation_channel_id, sponsor_id, client_version)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE handshake OWNER TO postgres;
GRANT ALL ON TABLE handshake TO postgres;
GRANT ALL ON TABLE handshake TO psiphon3;

-- Table: outbound

-- DROP TABLE outbound;

CREATE TABLE outbound
(
  host_id text,
  server_id text,
  client_region text,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  relay_protocol text,
  session_id text,
  "day" timestamp without time zone,
  "domain" text,
  protocol text,
  port text,
  flow_count integer,
  outbound_byte_count integer,
  id bigserial NOT NULL,
  CONSTRAINT outbound_pkey PRIMARY KEY (id),
  CONSTRAINT outbound_host_id_key UNIQUE (host_id, server_id, client_region, propagation_channel_id, sponsor_id, client_version, relay_protocol, session_id, day, domain, protocol, port, flow_count, outbound_byte_count)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE outbound OWNER TO postgres;
GRANT ALL ON TABLE outbound TO postgres;
GRANT ALL ON TABLE outbound TO psiphon3;

-- Table: "session"

-- DROP TABLE "session";

CREATE TABLE "session"
(
  host_id text,
  server_id text,
  client_region text,
  propagation_channel_id text,
  sponsor_id text,
  client_version text,
  relay_protocol text,
  session_id text,
  session_start_timestamp timestamp with time zone,
  session_end_timestamp timestamp with time zone,
  id bigserial NOT NULL,
  connected_id bigint NOT NULL,
  CONSTRAINT session_pkey PRIMARY KEY (id),
  CONSTRAINT connected_id FOREIGN KEY (connected_id)
      REFERENCES connected (id) MATCH SIMPLE
      ON UPDATE NO ACTION ON DELETE NO ACTION,
  CONSTRAINT session_host_id_key UNIQUE (host_id, server_id, client_region, propagation_channel_id, sponsor_id, client_version, relay_protocol, session_id, session_start_timestamp, session_end_timestamp)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE "session" OWNER TO postgres;
GRANT ALL ON TABLE "session" TO postgres;
GRANT ALL ON TABLE "session" TO psiphon3;

-- Index: fki_connected_id

-- DROP INDEX fki_connected_id;

CREATE INDEX fki_connected_id
  ON "session"
  USING btree
  (connected_id);

-- Table: started

-- DROP TABLE started;

CREATE TABLE started
(
  "timestamp" timestamp with time zone,
  host_id text,
  server_id text,
  id bigserial NOT NULL,
  CONSTRAINT started_pkey PRIMARY KEY (id),
  CONSTRAINT started_timestamp_key UNIQUE ("timestamp", host_id, server_id)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE started OWNER TO postgres;
GRANT ALL ON TABLE started TO postgres;
GRANT ALL ON TABLE started TO psiphon3;

-- Table: status

-- DROP TABLE status;

CREATE TABLE status
(
  "timestamp" timestamp with time zone,
  host_id text,
  relay_protocol text,
  session_id text,
  id bigserial NOT NULL,
  CONSTRAINT status_pkey PRIMARY KEY (id),
  CONSTRAINT status_timestamp_key UNIQUE ("timestamp", host_id, relay_protocol, session_id)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE status OWNER TO postgres;
GRANT ALL ON TABLE status TO postgres;
GRANT ALL ON TABLE status TO psiphon3;

-- View: ssh_session_duration;

-- DROP VIEW ssh_session_duration;

CREATE VIEW ssh_session_duration
(
id,
connected_timestamp,
duration,
host_id,
server_id,
client_region,
propagation_channel_id,
sponsor_id,
client_version,
relay_protocol
)
AS
SELECT
disconnected.id,
connected.timestamp,
CAST(EXTRACT('epoch' FROM disconnected.timestamp-connected.timestamp) AS INTEGER),
connected.host_id,
connected.server_id,
connected.client_region,
connected.propagation_channel_id,
connected.sponsor_id,
connected.client_version,
connected.relay_protocol
FROM connected
JOIN disconnected
ON connected.session_id = disconnected.session_id
AND disconnected.relay_protocol = 'SSH';

ALTER TABLE ssh_session_duration OWNER TO postgres;
GRANT ALL ON TABLE ssh_session_duration TO postgres;
GRANT ALL ON TABLE ssh_session_duration TO psiphon3;

-- View: ossh_session_duration;

-- DROP VIEW ossh_session_duration;

CREATE VIEW ossh_session_duration
(
id,
connected_timestamp,
duration,
host_id,
server_id,
client_region,
propagation_channel_id,
sponsor_id,
client_version,
relay_protocol
)
AS
SELECT
disconnected.id,
connected.timestamp,
CAST(EXTRACT('epoch' FROM disconnected.timestamp-connected.timestamp) AS INTEGER),
connected.host_id,
connected.server_id,
connected.client_region,
connected.propagation_channel_id,
connected.sponsor_id,
connected.client_version,
connected.relay_protocol
FROM connected
JOIN disconnected
ON connected.session_id = disconnected.session_id
AND disconnected.relay_protocol = 'OSSH';

ALTER TABLE ossh_session_duration OWNER TO postgres;
GRANT ALL ON TABLE ossh_session_duration TO postgres;
GRANT ALL ON TABLE ossh_session_duration TO psiphon3;
