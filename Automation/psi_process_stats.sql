-- Table: processed_logs

-- DROP TABLE processed_logs;

CREATE TABLE processed_logs
(
  host_id text,
  last_timestamp text,
  CONSTRAINT processed_logs_pkey PRIMARY KEY (host_id)
)
WITH (
  OIDS=FALSE
);
ALTER TABLE processed_logs OWNER TO postgres;
GRANT ALL ON TABLE processed_logs TO postgres;
GRANT ALL ON TABLE processed_logs TO psiphon3;

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

-- Index: session_reconstruction_index

-- DROP INDEX session_reconstruction_index;

CREATE INDEX session_reconstruction_index
  ON disconnected
  USING btree
  (session_id, host_id, relay_protocol, "timestamp");

-- Index: existing_session_reconstruction_index

-- DROP INDEX existing_session_reconstruction_index;

CREATE INDEX existing_session_reconstruction_index
  ON disconnected
  USING btree
  (session_id);

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

-- Index: session_connected_id_index

-- DROP INDEX session_connected_id_index;

CREATE INDEX session_connected_id_index
  ON "session"
  USING btree
  (connected_id);
