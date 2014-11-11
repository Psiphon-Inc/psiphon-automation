# Copyright (c) 2013, Psiphon Inc.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import time
import datetime
import inspect

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import sqlalchemy

import logger
import datastore
from utils import coalesce
from config import config


# TODO: Set to False
_DEBUG = False


# We are using the "declarative" "autoload" mode of SQLAlchemy. You can find a
# nice little intro to it here: http://www.blog.pythonlibrary.org/2010/09/10/sqlalchemy-connecting-to-pre-existing-databases/
# It allows us to introspect the table structure rather than repeat the
# `CREATE TABLE` info here.


engine = create_engine(config['sqlExporterDBConnectionString'], echo=_DEBUG)
Base = declarative_base(engine)


_table_class_registry = []
def _table_class(cls):
    _table_class_registry.append(cls)
    return cls


# We specifically *don't* do this, since this is a special meta table and
# we don't want to register it.
#@_table_class
class DiagnosticData(Base):
    __tablename__ = 'diagnostic_data'
    __table_args__ = {'autoload': True}

    @classmethod
    def create(cls, diagnostic_info):
        obj = cls()

        obj_id = coalesce(diagnostic_info, '_id')
        if not obj_id:
            # This shouldn't happen, since this field is added by MongoDB
            raise ValueError('diagnostic_info missing _id')

        obj.obj_id = str(obj_id)

        obj.datetime = coalesce(diagnostic_info, 'datetime')
        obj.platform = coalesce(diagnostic_info, ('Metadata', 'platform'))
        obj.version = coalesce(diagnostic_info, ('Metadata', 'version'))

        return obj


@_table_class
class WindowsSystem(Base):
    __tablename__ = 'windows_system'
    __table_args__ = {'autoload': True}

    @classmethod
    def create(cls, diagnostic_info):
        if coalesce(diagnostic_info, ('Metadata', 'platform')) != 'windows':
            return None

        obj = cls()

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'OSInfo'))
        obj.os_name = coalesce(base, 'name')
        obj.os_version = coalesce(base, 'version')
        obj.os_architecture = coalesce(base, 'architecture')
        obj.os_servicePackMajor = coalesce(base, 'servicePackMajor')
        obj.os_servicePackMinor = coalesce(base, 'servicePackMinor')
        obj.os_freePhysicalMemoryKB = coalesce(base, 'freePhysicalMemoryKB')
        obj.os_freeVirtualMemoryKB = coalesce(base, 'freeVirtualMemoryKB')
        obj.os_language_lcid = coalesce(base, ('LanguageInfo', 'lcid_string'))
        obj.os_locale_lcid = coalesce(base, ('LocaleInfo', 'lcid_string'))

        # This is an array of country info, and we'll use the last one.
        # (For the hacky reason that in the ['CA', 'PR', 'US'] case we want 'US'.)
        country_code_info = coalesce(base, 'CountryCodeInfo', [None])
        obj.os_country_code = coalesce(country_code_info[-1], 'country_code')

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'NetworkInfo', 'Current', 'Internet'))
        obj.net_current_internet_connected = coalesce(base, 'internetConnected')
        obj.net_current_internet_conn_modem = coalesce(base, 'internetConnectionModem')
        obj.net_current_internet_conn_configured = coalesce(base, 'internetConnectionConfigured')
        obj.net_current_internet_conn_lan = coalesce(base, 'internetConnectionLAN')
        obj.net_current_internet_conn_proxy = coalesce(base, 'internetConnectionProxy')
        obj.net_current_internet_conn_offline = coalesce(base, 'internetConnectionOffline')
        obj.net_current_internet_ras_installed = coalesce(base, 'internetRASInstalled')

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'NetworkInfo', 'Original', 'Internet'))
        obj.net_original_internet_connected = coalesce(base, 'internetConnected')
        obj.net_original_internet_conn_modem = coalesce(base, 'internetConnectionModem')
        obj.net_original_internet_conn_configured = coalesce(base, 'internetConnectionConfigured')
        obj.net_original_internet_conn_lan = coalesce(base, 'internetConnectionLAN')
        obj.net_original_internet_conn_proxy = coalesce(base, 'internetConnectionProxy')
        obj.net_original_internet_conn_offline = coalesce(base, 'internetConnectionOffline')
        obj.net_original_internet_ras_installed = coalesce(base, 'internetRASInstalled')

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'NetworkInfo', 'Original', 'Proxy'), [])
        # There's an array of proxy info, typically one per network connection.
        # We don't need to export all of them, so we'll take the one that doesn't
        # have a named network connection.
        proxy = filter(lambda p: not coalesce(p, 'connectionName'), base)
        proxy = proxy[0] if proxy else (base[0] if base else None)
        obj.net_original_proxy_flags = coalesce(proxy, 'flags')
        obj.net_original_proxy_address = coalesce(proxy, 'proxy')
        obj.net_original_proxy_bypass = coalesce(proxy, 'bypass')
        obj.net_original_proxy_connectionName = coalesce(proxy, 'connectionName')

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'Misc'))
        obj.misc_slowMachine = coalesce(base, 'slowMachine')
        obj.misc_mideastEnabled = coalesce(base, 'mideastEnabled')

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'UserInfo'))
        obj.user_group_users = coalesce(base, 'inUsersGroup')
        obj.user_group_power = coalesce(base, 'inPowerUsersGroup')
        obj.user_group_guest = coalesce(base, 'inGuestsGroup')
        obj.user_group_admin = coalesce(base, 'inAdminsGroup')

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'PsiphonInfo'))
        obj.psiphon_info_propagationChannelID = coalesce(base, 'PROPAGATION_CHANNEL_ID')
        obj.psiphon_info_sponsorID = coalesce(base, 'SPONSOR_ID')
        obj.psiphon_info_clientVersion = coalesce(base, 'CLIENT_VERSION')
        obj.psiphon_info_transport = coalesce(base, 'selectedTransport')
        obj.psiphon_info_splitTunnel = coalesce(base, 'splitTunnel')

        return obj


@_table_class
class WindowsSecInfo(Base):
    __tablename__ = 'windows_sec_info'
    __table_args__ = {'autoload': True}

    @classmethod
    def create(cls, diagnostic_info):
        if coalesce(diagnostic_info, ('Metadata', 'platform')) != 'windows':
            return None

        objs = []
        for sec_name, sec_type in (('AntiSpywareInfo', 'antispyware'), ('AntiVirusInfo', 'antivirus'), ('FirewallInfo', 'firewall')):
            for item in coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation', 'SecurityInfo', sec_name), []):
                obj = cls()
                obj.sec_type = sec_type
                obj.displayName = coalesce(item, 'displayName')

                data_version = coalesce(item, 'version')

                [setattr(obj, key, val) for key, val in coalesce(item, data_version, {}).iteritems()]

                objs.append(obj)

        return objs


@_table_class
class UserFeedback(Base):
    __tablename__ = 'user_feedback'
    __table_args__ = {'autoload': True}

    @classmethod
    def create(cls, diagnostic_info):
        # Android feedback gets submitted to the individual servers
        if coalesce(diagnostic_info, ('Metadata', 'platform')) != 'windows':
            return None

        results = coalesce(diagnostic_info, ('Feedback', 'Survey', 'results'))

        if not results:
            return None

        connectivity = filter(lambda r: coalesce(r, 'title') == 'Connectivity', results)
        speed = filter(lambda r: coalesce(r, 'title') == 'Speed', results)
        compatibility = filter(lambda r: coalesce(r, 'title') == 'Compatibility', results)

        obj = cls()
        obj.connectivity = coalesce(connectivity[0], 'answer') if connectivity else None
        obj.speed = coalesce(speed[0], 'answer') if speed else None
        obj.compatibility = coalesce(compatibility[0], 'answer') if compatibility else None

        # If the user was never able to connect to a server, then this feedback
        # can't be considered to be for a particular server. But if the user
        # has been (or is) connected to a server, we'll use the one they last
        # connected to.
        diagnostic_history = coalesce(diagnostic_info, ('DiagnosticInfo', 'DiagnosticHistory'), [])
        connected_msg = 'ConnectedServer' if coalesce(diagnostic_info, ('Metadata', 'platform')) != 'windows' else 'ConnectingServer'
        connected_entries = [entry for entry in diagnostic_history if coalesce(entry, 'msg') == connected_msg]
        if connected_entries:
            obj.server_id = coalesce(connected_entries[-1], ('data', 'ipAddress'))

        return obj


@_table_class
class AndroidSystem(Base):
    __tablename__ = 'android_system'
    __table_args__ = {'autoload': True}

    @classmethod
    def create(cls, diagnostic_info):
        if coalesce(diagnostic_info, ('Metadata', 'platform')) != 'android':
            return None

        obj = cls()

        base = coalesce(diagnostic_info, ('DiagnosticInfo', 'SystemInformation'))
        obj.isRooted = coalesce(base, 'isRooted')
        obj.language = coalesce(base, 'language')
        obj.networkTypeName = coalesce(base, 'networkTypeName')
        obj.sys_build_tags = coalesce(base, ('Build', 'TAGS'))
        obj.sys_build_brand = coalesce(base, ('Build', 'BRAND'))
        obj.sys_build_version_release = coalesce(base, ('Build', 'VERSION__RELEASE'))
        obj.sys_build_version_codename = coalesce(base, ('Build', 'VERSION__CODENAME'))
        obj.sys_build_version_sdk = coalesce(base, ('Build', 'VERSION__SDK_INT'))
        obj.sys_build_cpu_abi = coalesce(base, ('Build', 'CPU_ABI'))
        obj.sys_build_model = coalesce(base, ('Build', 'MODEL'))
        obj.sys_build_manufacturer = coalesce(base, ('Build', 'MANUFACTURER'))
        obj.psiphon_info_sponsorID = coalesce(base, ('PsiphonInfo', 'SPONSOR_ID'))
        obj.psiphon_info_propagationChannelID = coalesce(base, ('PsiphonInfo', 'PROPAGATION_CHANNEL_ID'))
        obj.psiphon_info_clientVersion = coalesce(base, ('PsiphonInfo', 'CLIENT_VERSION'))

        BROWSER_ONLY_STATUS_ID = 'psiphon_running_browser_only'
        CONNECTION_STATUS_IDS = (BROWSER_ONLY_STATUS_ID, 'psiphon_running_whole_device')
        connection_log_ids = [coalesce(s, 'id') for s in coalesce(diagnostic_info,
                                                                  ('DiagnosticInfo', 'StatusHistory'),
                                                                  default_value=[],
                                                                  required_types=(list, tuple))
                              if coalesce(s, 'id') in CONNECTION_STATUS_IDS]
        if connection_log_ids:
            # The last connection log is the one we'll use as representative
            obj.browserOnly = connection_log_ids[-1] == BROWSER_ONLY_STATUS_ID

        return obj


@_table_class
class ServerResponseCheck(Base):
    __tablename__ = 'server_response_check'
    __table_args__ = {'autoload': True}

    @classmethod
    def create(cls, diagnostic_info):
        # This is for both platforms

        objs = []
        for entry in coalesce(diagnostic_info, ('DiagnosticInfo', 'DiagnosticHistory'), []):
            # DiagnosticHistory is a pretty free form set of data. The only type
            # of data that goes into it that we care about here are the
            # ServerResponseCheck entries.
            if coalesce(entry, 'msg') != 'ServerResponseCheck':
                continue

            obj = cls()
            obj.timestamp = coalesce(entry, 'timestamp')
            obj.server_id = coalesce(entry, ('data', 'ipAddress'))
            obj.responded = coalesce(entry, ('data', 'responded'))
            obj.responseTime = coalesce(entry, ('data', 'responseTime'))
            obj.regionCode = coalesce(entry, ('data', 'regionCode'))
            objs.append(obj)

        return objs


@_table_class
class SelectedRegion(Base):
    __tablename__ = 'selected_region'
    __table_args__ = {'autoload': True}

    @classmethod
    def create(cls, diagnostic_info):
        # This is for both platforms

        objs = []
        for entry in coalesce(diagnostic_info, ('DiagnosticInfo', 'DiagnosticHistory'), []):
            # DiagnosticHistory is a pretty free form set of data. The only type
            # of data that goes into it that we care about here are the
            # SelectedRegion entries.
            if coalesce(entry, 'msg') != 'SelectedRegion':
                continue

            obj = cls()
            obj.timestamp = coalesce(entry, 'timestamp')
            obj.regionCode = coalesce(entry, ('data', 'regionCode'))
            objs.append(obj)

        return objs


_SLEEP_TIME_SECS = 60


def _diagnostic_record_iter():
    while True:
        last_timestamp = _get_last_timestamp()
        for rec in datastore.get_sqlexporter_diagnostic_info_iterator(last_timestamp):
            yield rec

        # Take this opportunity to trim the DB
        _truncate_db()

        time.sleep(_SLEEP_TIME_SECS)


def _new_session():
    metadata = Base.metadata
    Session = sessionmaker(bind=engine)
    session = Session()
    return session


def _truncate_db():
    session = None

    cutoff = datetime.datetime.now() - datetime.timedelta(seconds=datastore.DIAGNOSTIC_DATA_LIFETIME_SECS)

    try:
        session = _new_session()

        # This delete will cascade.
        session.query(DiagnosticData).filter(DiagnosticData.datetime < cutoff).delete()

        session.commit()
    except:
        if session:
            session.rollback()
        raise
    finally:
        if session:
            session.close()


def _get_last_timestamp():
    session = _new_session()
    most_recent = session.query(DiagnosticData).order_by(DiagnosticData.datetime.desc()).first()
    session.close()

    if most_recent is None:
        most_recent = datetime.datetime(1970, 1, 1)
    else:
        most_recent = most_recent.datetime

    return most_recent


def _sanitize_session(session):
    '''
    Modifies the `session` object directly.
    '''
    for obj in session:
        for attrname, _ in inspect.getmembers(obj.__class__, inspect.isdatadescriptor):
            if attrname.startswith('__'):
                continue
            attrval = getattr(obj, attrname)
            if isinstance(attrval, (str, unicode)):
                setattr(obj, attrname, attrval.encode('utf-8'))


def _process_diagnostic_info(diagnostic_info):
    # We are not supporting old Android diagnostic data packages
    if coalesce(diagnostic_info, ('Metadata', 'platform')) == 'android' \
       and coalesce(diagnostic_info, ('Metadata', 'version'), 0, int) < 2:
        return

    session = None

    try:
        session = _new_session()

        diagnostic_data = DiagnosticData.create(diagnostic_info)
        session.add(diagnostic_data)

        # Get the ID for the new DiagnosticData object, so we can FK it.
        session.flush()

        for table_class in _table_class_registry:
            objs = table_class.create(diagnostic_info)

            if not objs:
                continue

            if not isinstance(objs, (tuple, list)):
                objs = (objs,)

            for obj in objs:
                setattr(obj, 'diagnostic_data_id', diagnostic_data.id)
                session.add(obj)

        _sanitize_session(session)
        session.commit()
    except sqlalchemy.exc.IntegrityError as e:
        if session:
            session.rollback()

        # Note that MySQL discards milliseconds ("fractional seconds": http://dev.mysql.com/doc/refman/5.0/en/datetime.html).
        # This means that the "last timestamp" will actually be a smaller value
        # than the timestamp of the last-inserted record. This means that there
        # will always(?) be an attempt to re-insert the last-inserted record,
        # which will result in an exception. We need to ignore it and carry on.
        expected = e.orig.args[1].startswith('Duplicate entry') and e.orig.args[1].endswith("for key 'obj_id'")

        if not expected:
          raise
    except:
        if session:
            session.rollback()
        raise
    finally:
        if session:
            session.close()


def go():
    # Note that `_diagnostic_record_iter` throttles itself if/when there are
    # no records to process.
    for diagnostic_info in _diagnostic_record_iter():
        try:
            _process_diagnostic_info(diagnostic_info)
        except Exception as e:
            if _DEBUG:
                raise

            logger.exception()
            logger.error(str(e))
