CREATE DATABASE IF NOT EXISTS diagnostic_feedback;
USE diagnostic_feedback;

CREATE TABLE IF NOT EXISTS diagnostic_data (
    id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
    obj_id CHAR(24) NOT NULL UNIQUE,
    datetime DATETIME NOT NULL,
    platform SET('windows', 'android') NOT NULL,
    version INT NOT NULL,
    INDEX(obj_id),
    INDEX(datetime)
    );

CREATE TABLE IF NOT EXISTS windows_system (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL,
    os_name VARCHAR(255) CHARACTER SET utf8,
    os_version VARCHAR(255) CHARACTER SET utf8,
    os_architecture VARCHAR(255) CHARACTER SET utf8,
    os_servicePackMajor INT,
    os_servicePackMinor INT,
    os_freePhysicalMemoryKB LONG,
    os_freeVirtualMemoryKB LONG,
    os_language_lcid VARCHAR(255) CHARACTER SET utf8,
    os_locale_lcid VARCHAR(255) CHARACTER SET utf8,
    os_country_code VARCHAR(255) CHARACTER SET utf8,
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
    net_original_proxy_flags VARCHAR(255) CHARACTER SET utf8,
    net_original_proxy_address VARCHAR(255) CHARACTER SET utf8,
    net_original_proxy_bypass VARCHAR(255) CHARACTER SET utf8,
    net_original_proxy_connectionName VARCHAR(255) CHARACTER SET utf8,
    misc_slowMachine BOOLEAN,
    misc_mideastEnabled BOOLEAN,
    user_group_users BOOLEAN,
    user_group_power BOOLEAN,
    user_group_guest BOOLEAN,
    user_group_admin BOOLEAN,
    psiphon_info_propagationChannelID VARCHAR(255) CHARACTER SET utf8,
    psiphon_info_sponsorID VARCHAR(255) CHARACTER SET utf8,
    psiphon_info_clientVersion VARCHAR(255) CHARACTER SET utf8,
    psiphon_info_transport VARCHAR(255) CHARACTER SET utf8,
    psiphon_info_splitTunnel BOOLEAN,
    FOREIGN KEY (diagnostic_data_id) REFERENCES diagnostic_data(id) ON DELETE CASCADE ON UPDATE CASCADE
    );

CREATE TABLE IF NOT EXISTS windows_sec_info (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL,
    sec_type SET('firewall', 'antivirus', 'antispyware') NOT NULL,
    enabled BOOLEAN,
    versionNumber VARCHAR(255) CHARACTER SET utf8,
    productUpToDate BOOLEAN,
    definitionsUpToDate BOOLEAN,
    productState LONG,
    securityProvider VARCHAR(255) CHARACTER SET utf8,
    displayName VARCHAR(255)  CHARACTER SET utf8,
    FOREIGN KEY (diagnostic_data_id) REFERENCES diagnostic_data(id) ON DELETE CASCADE ON UPDATE CASCADE
    );

CREATE TABLE IF NOT EXISTS user_feedback (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL,
    connectivity INT,
    speed INT,
    compatibility INT,
    server_id VARCHAR(255) CHARACTER SET utf8,
    FOREIGN KEY (diagnostic_data_id) REFERENCES diagnostic_data(id) ON DELETE CASCADE ON UPDATE CASCADE
    );

CREATE TABLE IF NOT EXISTS android_system (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL,
    isRooted BOOLEAN,
    browserOnly BOOLEAN,
    language CHAR(2),
    networkTypeName VARCHAR(255) CHARACTER SET utf8,
    sys_build_tags VARCHAR(255) CHARACTER SET utf8,
    sys_build_brand VARCHAR(255) CHARACTER SET utf8,
    sys_build_version_release VARCHAR(255) CHARACTER SET utf8,
    sys_build_version_codename VARCHAR(255) CHARACTER SET utf8,
    sys_build_version_sdk INT,
    sys_build_cpu_abi VARCHAR(255) CHARACTER SET utf8,
    sys_build_model VARCHAR(255) CHARACTER SET utf8,
    sys_build_manufacturer VARCHAR(255) CHARACTER SET utf8,
    psiphon_info_sponsorID VARCHAR(255) CHARACTER SET utf8,
    psiphon_info_propagationChannelID VARCHAR(255) CHARACTER SET utf8,
    psiphon_info_clientVersion VARCHAR(255) CHARACTER SET utf8,
    FOREIGN KEY (diagnostic_data_id) REFERENCES diagnostic_data(id) ON DELETE CASCADE ON UPDATE CASCADE
    );

CREATE TABLE IF NOT EXISTS server_response_check (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL,
    timestamp datetime,
    server_id VARCHAR(255) CHARACTER SET utf8,
    responded BOOLEAN,
    responseTime INT,
    regionCode CHAR(2),
    FOREIGN KEY (diagnostic_data_id) REFERENCES diagnostic_data(id) ON DELETE CASCADE ON UPDATE CASCADE
    );

CREATE TABLE IF NOT EXISTS selected_region (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    diagnostic_data_id INTEGER NOT NULL,
    timestamp datetime,
    regionCode CHAR(2),
    FOREIGN KEY (diagnostic_data_id) REFERENCES diagnostic_data(id) ON DELETE CASCADE ON UPDATE CASCADE
    );
