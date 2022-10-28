import imp
import os
import mock
import jsonpatch

imp.load_source('validated_config_db_connector', \
    os.path.join(os.path.dirname(__file__), '..', 'config', 'validated_config_db_connector.py'))
import validated_config_db_connector

from unittest import TestCase
from mock import patch
from generic_config_updater.gu_common import EmptyTableError
from validated_config_db_connector import ValidatedConfigDBConnector
from swsscommon.swsscommon import ConfigDBConnector

from utilities_common.db import Db

SAMPLE_TABLE = 'VLAN'
SAMPLE_KEY = 'Vlan1000'
SAMPLE_VALUE_EMPTY = None
SAMPLE_VALUE = 'test'
SAMPLE_VALUE_DICT = {'sample_field_key': 'sample_field_value'}
SAMPLE_PATCH = [{"op": "add", "path": "/VLAN", "value": "sample value"}]


class TestValidatedConfigDBConnector(TestCase):
    '''

        Test Class for validated_config_db_connector.py

    '''
    def test_validated_set_entry_empty_table(self): 
        mock_generic_updater = mock.Mock()
        mock_generic_updater.apply_patch = mock.Mock(side_effect=EmptyTableError)
        with mock.patch('validated_config_db_connector.GenericUpdater', return_value=mock_generic_updater):
            remove_entry_success = validated_config_db_connector.ValidatedConfigDBConnector.validated_set_entry(mock.Mock(), SAMPLE_TABLE, SAMPLE_KEY, SAMPLE_VALUE_EMPTY)
            assert not remove_entry_success

    def test_validated_mod_entry(self):
        mock_generic_updater = mock.Mock()
        with mock.patch('validated_config_db_connector.GenericUpdater', return_value=mock_generic_updater):
            successful_application = validated_config_db_connector.ValidatedConfigDBConnector.validated_mod_entry(mock.Mock(), SAMPLE_TABLE, SAMPLE_KEY, SAMPLE_VALUE_DICT)
            assert successful_application

    def test_validated_delete_table_invalid_delete(self):
        mock_generic_updater = mock.Mock()
        mock_generic_updater.apply_patch = mock.Mock(side_effect=ValueError)
        with mock.patch('validated_config_db_connector.GenericUpdater', return_value=mock_generic_updater):
            delete_table_success = validated_config_db_connector.ValidatedConfigDBConnector.validated_delete_table(mock.Mock(), SAMPLE_TABLE)
            assert not delete_table_success

    def test_create_gcu_patch(self):
        expected_gcu_patch = jsonpatch.JsonPatch([{"op": "add", "path": "/PORTCHANNEL", "value": {}}, {"op": "add", "path": "/PORTCHANNEL/PortChannel01", "value": {}}, {"op": "add", "path": "/PORTCHANNEL/PortChannel01", "value": "test"}])
        with mock.patch('validated_config_db_connector.ConfigDBConnector.get_table', return_value=False):
            with mock.patch('validated_config_db_connector.ConfigDBConnector.get_entry', return_value=False):
                created_gcu_patch = validated_config_db_connector.ValidatedConfigDBConnector.create_gcu_patch(ValidatedConfigDBConnector(ConfigDBConnector()), "add", "PORTCHANNEL", "PortChannel01", SAMPLE_VALUE)
                assert expected_gcu_patch == created_gcu_patch

    def test_apply_patch(self):
        mock_generic_updater = mock.Mock()
        mock_generic_updater.apply_patch = mock.Mock(side_effect=EmptyTableError)
        with mock.patch('validated_config_db_connector.GenericUpdater', return_value=mock_generic_updater):
            with mock.patch('validated_config_db_connector.ValidatedConfigDBConnector.validated_delete_table', return_value=True):
                apply_patch_success = validated_config_db_connector.ValidatedConfigDBConnector.apply_patch(mock.Mock(), SAMPLE_PATCH, SAMPLE_TABLE)
                assert not apply_patch_success
