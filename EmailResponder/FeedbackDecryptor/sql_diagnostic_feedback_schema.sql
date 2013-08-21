CREATE DATABASE IF NOT EXISTS diagnostic_feedback;
USE diagnostic_feedback;

CREATE TABLE IF NOT EXISTS diagnostic_data (
    id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
    obj_id CHAR(24) NOT NULL UNIQUE,
    datetime DATETIME NOT NULL,
    platform VARCHAR(32) NOT NULL,
    version INT NOT NULL,
    INDEX(obj_id),
    INDEX(datetime)
    );

CREATE TABLE IF NOT EXISTS windows_system (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    os_name VARCHAR(255),
    os_version VARCHAR(255),
    os_architecture VARCHAR(255),
    os_servicePackMajor INT,
    os_servicePackMinor INT,
    os_freePhysicalMemoryKB LONG,
    os_freeVirtualMemoryKB LONG,
    os_language_lcid VARCHAR(255),
    os_locale_lcid VARCHAR(255),
    os_country_code VARCHAR(255),
    net_current_internet_connected BOOLEAN,
    net_current_internet_conn_modem BOOLEAN,
    net_current_internet_conn_configured BOOLEAN,
    net_current_internet_conn_lan BOOLEAN,
    net_current_internet_conn_proxy BOOLEAN,
    net_current_internet_conn_offline BOOLEAN,
    net_current_internet_ras_installed BOOLEAN,
    net_original_internet_connected BOOLEAN,
    net_original_internet_conn_modem BOOLEAN,
    net_original_internet_conn_configured BOOLEAN,
    net_original_internet_conn_lan BOOLEAN,
    net_original_internet_conn_proxy BOOLEAN,
    net_original_internet_conn_offline BOOLEAN,
    net_original_internet_ras_installed BOOLEAN,
    net_original_proxy_flags VARCHAR(255),
    net_original_proxy_address VARCHAR(255),
    net_original_proxy_bypass VARCHAR(255),
    net_original_proxy_connectionName VARCHAR(255),
    misc_slowMachine BOOLEAN,
    misc_mideastEnabled BOOLEAN,
    user_group_users BOOLEAN,
    user_group_power BOOLEAN,
    user_group_guest BOOLEAN,
    user_group_admin BOOLEAN,
    psiphon_info_propagationChannelID VARCHAR(255),
    psiphon_info_sponsorID VARCHAR(255),
    psiphon_info_clientVersion VARCHAR(255),
    psiphon_info_transport VARCHAR(255),
    psiphon_info_splitTunnel BOOLEAN
    );

CREATE TABLE IF NOT EXISTS windows_sec_info (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    sec_type SET('firewall', 'antivirus', 'antispyware') NOT NULL,
    enabled BOOLEAN,
    versionNumber VARCHAR(255),
    productUpToDate BOOLEAN,
    definitionsUpToDate BOOLEAN,
    productState LONG,
    securityProvider VARCHAR(255),
    displayName VARCHAR(255)
    );

CREATE TABLE IF NOT EXISTS windows_status_history (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    sec_type SET('firewall', 'antivirus', 'antispyware'),
    debug BOOLEAN,
    timestamp DATETIME,
    message VARCHAR(255)
    );

CREATE TABLE IF NOT EXISTS windows_server_response_check (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    timestamp DATETIME,
    server_id VARCHAR(255),
    server_responded BOOLEAN,
    server_responseTime INT
    );

CREATE TABLE IF NOT EXISTS user_feedback (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    connectivity INT,
    speed INT,
    compatibility INT
    );

CREATE TABLE IF NOT EXISTS android_system (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    isRooted BOOLEAN,
    language CHAR(2),
    networkTypeName VARCHAR(255),
    sys_build_tags VARCHAR(255),
    sys_build_brand VARCHAR(255),
    sys_build_version_release VARCHAR(255),
    sys_build_version_codename VARCHAR(255),
    sys_build_version_sdk INT,
    sys_build_cpu_abi VARCHAR(255),
    sys_build_model VARCHAR(255),
    sys_build_manufacturer VARCHAR(255),
    psiphon_info_sponsorID VARCHAR(255),
    psiphon_info_propagationChannelID VARCHAR(255),
    psiphon_info_clientVersion VARCHAR(255)
    );

CREATE TABLE IF NOT EXISTS android_status_history (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    datetime datetime,
    priority INT,
    msg VARCHAR(255),
    throwable text
    );

CREATE TABLE IF NOT EXISTS android_server_response (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL REFERENCES diagnostic_data(id),
    datetime datetime,
    server_id VARCHAR(255),
    responded BOOLEAN,
    responseTime INT
    );

