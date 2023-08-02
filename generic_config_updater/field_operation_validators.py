import os
import re
import json
import jsonpointer
import subprocess
from sonic_py_common import device_info
from .gu_common import GenericConfigUpdaterError
from swsscommon.swsscommon import SonicV2Connector

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
GCU_TABLE_MOD_CONF_FILE = f"{SCRIPT_DIR}/gcu_field_operation_validators.conf.json"
GET_HWSKU_CMD = "sonic-cfggen -d -v DEVICE_METADATA.localhost.hwsku"

def get_asic_name():
    asic = "unknown"
    
    if os.path.exists(GCU_TABLE_MOD_CONF_FILE):
        with open(GCU_TABLE_MOD_CONF_FILE, "r") as s:
            gcu_field_operation_conf = json.load(s)
    else:
        raise GenericConfigUpdaterError("GCU table modification validators config file not found")
    
    asic_mapping = gcu_field_operation_conf["helper_data"]["rdma_config_update_validator"]
    asic_type = device_info.get_sonic_version_info()['asic_type'] 

    if asic_type == 'cisco-8000':
        asic = "cisco-8000"
    elif asic_type == 'mellanox' or asic_type == 'vs' or asic_type == 'broadcom':
        proc = subprocess.Popen(GET_HWSKU_CMD, shell=True, universal_newlines=True, stdout=subprocess.PIPE)
        output, err = proc.communicate()
        hwsku = output.rstrip('\n')
        if asic_type == 'mellanox' or asic_type == 'vs':
            spc1_hwskus = asic_mapping["mellanox_asics"]["spc1"]
            spc2_hwskus = asic_mapping["mellanox_asics"]["spc2"]
            spc3_hwskus = asic_mapping["mellanox_asics"]["spc3"]
            if hwsku.lower() in [spc1_hwsku.lower() for spc1_hwsku in spc1_hwskus]:
                asic = "spc1"
                return asic
            if hwsku.lower() in [spc2_hwsku.lower() for spc2_hwsku in spc2_hwskus]:
                asic = "spc2"
                return asic
            if hwsku.lower() in [spc3_hwsku.lower() for spc3_hwsku in spc3_hwskus]:
                asic = "spc3"
                return asic
        if asic_type == 'broadcom' or asic_type == 'vs':
            broadcom_asics = asic_mapping["broadcom_asics"]
            for asic_shorthand, hwskus in broadcom_asics.items():
                if asic != "unknown":
                    break
                for hwsku_cur in hwskus:
                    if hwsku_cur.lower() in hwsku.lower():
                        asic = asic_shorthand
                        break

    return asic


def rdma_config_update_validator(patch_element):
    asic = get_asic_name()
    if asic == "unknown":
        return False
    version_info = device_info.get_sonic_version_info()
    build_version = version_info.get('build_version')
    version_substrings = build_version.split('.')
    branch_version = None
    
    for substring in version_substrings:
        if substring.isdigit() and re.match(r'^\d{8}$', substring):
            branch_version = substring
    
    path = patch_element["path"]
    table = jsonpointer.JsonPointer(path).parts[0]
    
    # Helper function to return relevant cleaned paths, considers case where the jsonpatch value is a dict
    # For paths like /PFC_WD/Ethernet112/action, remove Ethernet112 from the path so that we can clearly determine the relevant field (i.e. action, not Ethernet112)
    def _get_fields_in_patch():
        cleaned_fields = []

        field_elements = jsonpointer.JsonPointer(path).parts[1:]
        cleaned_field_elements = [elem for elem in field_elements if not any(char.isdigit() for char in elem)]
        cleaned_field = '/'.join(cleaned_field_elements).lower()
        

        if 'value' in patch_element.keys() and isinstance(patch_element['value'], dict):
            for key in patch_element['value']:
                if len(cleaned_field) > 0:
                    cleaned_fields.append(cleaned_field + '/' + key)
                else:
                    cleaned_fields.append(key)
        else:
            cleaned_fields.append(cleaned_field)

        return cleaned_fields
    
    if os.path.exists(GCU_TABLE_MOD_CONF_FILE):
        with open(GCU_TABLE_MOD_CONF_FILE, "r") as s:
            gcu_field_operation_conf = json.load(s)
    else:
        raise GenericConfigUpdaterError("GCU table modification validators config file not found")

    tables = gcu_field_operation_conf["tables"]
    scenarios = tables[table]["validator_data"]["rdma_config_update_validator"]
    
    cleaned_fields = _get_fields_in_patch()
    for cleaned_field in cleaned_fields:
        scenario = None
        for key in scenarios.keys():
            if cleaned_field in scenarios[key]["fields"]:
                scenario = scenarios[key]
                break
    
        if scenario is None:
            return False
        
        if scenario["platforms"][asic] == "":
            return False

        if patch_element['op'] not in scenario["operations"]:
            return False
    
        if branch_version is not None:
            if asic in scenario["platforms"]:
                if branch_version < scenario["platforms"][asic]:
                    return False
            else:
                return False

    return True


def read_statedb_entry(table, field):
    state_db = SonicV2Connector(host="127.0.0.1")
    state_db.connect(state_db.STATE_DB)
    return state_db.get(state_db.STATE_DB, table, field)


def port_config_update_validator(patch_element):
    if patch_element["op"] == "remove":
        return True
    
    # for PORT speed and fec configs, need to ensure value is allowed based on StateDB
    patch_element_str = json.dumps(patch_element)
    path = patch_element["path"]
    match = re.search(r"Ethernet\d+", path)
    if match:
        port = match.group(0)
    else:
        return False
    value = patch_element.get("value")
        
    if "fec" in patch_element_str:
        if path.endswith("fec"):
            fec_value = value
        elif isinstance(value, dict):
            try:
                fec_value = value["fec"]
            except KeyError:
                return False
            
        supported_fecs_str = read_statedb_entry('{}|{}'.format("PORT_TABLE", port), "supported_fecs")
        if supported_fecs_str:
            if supported_fecs_str != 'N/A':
                supported_fecs_list = supported_fecs_str.split(',')
            else:
                supported_fecs_list = []
        else:
            supported_fecs_list = [ "rs", "fc", "none"]
        if fec_value not in supported_fecs_list:
            return False
        
    if "speed" in patch_element_str:
        if path.endswith("speed"):
            speed_value = value
        elif isinstance(value, dict):
            try:
                speed_value = value["speed"]
            except KeyError:
                return False
            
        supported_speeds_str = read_statedb_entry('{}|{}'.format("PORT_TABLE", port), "supported_speeds") or ''
        supported_speeds = [int(s) for s in supported_speeds_str.split(',') if s]
        if supported_speeds and int(speed_value) not in supported_speeds:
            return False
    
    return True
