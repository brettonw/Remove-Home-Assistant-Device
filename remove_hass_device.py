#! /usr/bin/env python3

import json
import codecs
import sys


def list_without_indexes(original: list, id_list: list[str], index_by_id: dict[str, int]):
    new = []
    i_set = set([index_by_id[id] for id in id_list])
    for i in range(len(original)):
        if i not in i_set:
            new.append(original[i])
    return new


def from_json_file(file_name: str) -> dict:
    with codecs.open(file_name, "r", "utf-8-sig") as file:
        return json.load(file)


def to_json_file(file_name: str, data: dict):
    with open(file_name, "w", encoding="utf-8") as outfile:
        json.dump(data, outfile, ensure_ascii=False, indent=4)


core_config_entries = from_json_file("core.config_entries")
config_entries = core_config_entries["data"]["entries"]
core_entity_registry = from_json_file("core.entity_registry")
entities = core_entity_registry["data"]["entities"]
core_device_registry = from_json_file("core.device_registry")
devices = core_device_registry["data"]["devices"]

# configs have "entry_id"
config_entry_index_by_entry_id = {config_entries[i]["entry_id"]: i for i in range(len(config_entries))}

# devices have "name" and "id"
# - there is "name_by_user" on some devices
# - may be loaded "via_device_id"
# - may have "config_entries" (a list of ids)
# - may have "disabled_by": (null | "user"),
device_index_by_id = {devices[i]["id"]: i for i in range(len(devices))}
device_ids_by_name = {device["name"]: device["id"] for device in devices}
device_ids_by_name_by_user = {device["name_by_user"]: device["id"] for device in devices if device["name_by_user"] is not None}

# index the devices by config id to see if there are any configs referenced by multiple devices
device_ids_by_config_entry_id = {}
for device in devices:
    for config_entry_id in device["config_entries"]:
        if config_entry_id not in device_ids_by_config_entry_id:
            device_ids_by_config_entry_id[config_entry_id] = set()
        device_ids_by_config_entry_id[config_entry_id].add(device["id"])
for config_entry, device_id_set in device_ids_by_config_entry_id.items():
    if len(device_id_set) > 1:
        print(f"config_entry \"{config_entry}\" is referenced from {len(device_id_set)} devices")

# build the tree of device dependencies, as far as I can see, each device can only have one parent
# so there's no possibility of replication or loops
device_ids_by_parent_id = {}
for device in devices:
    via_device_id = device["via_device_id"]
    if via_device_id is not None:
        if via_device_id not in device_ids_by_parent_id:
            device_ids_by_parent_id[via_device_id] = []
        device_ids_by_parent_id[via_device_id].append(device["id"])


def get_device_id_list(device_id: str):
    # descend the tree recursively
    def internal(device_id: str, to_list: list[str]):
        to_list.append(device_id)
        if device_id in device_ids_by_parent_id:
            for child_device_id in device_ids_by_parent_id[device_id]:
                internal(child_device_id, to_list)
        return to_list
    return internal(device_id, [])


# entities are attached to a "device_id"
# - may have "disabled_by": (null | "integration")
entity_index_by_id = {entities[i]["id"]: i for i in range(len(entities))}
entity_ids_by_device_id = {}
for i in range(len(entities)):
    entity = entities[i]
    device_id = entity["device_id"]
    if device_id not in entity_ids_by_device_id:
        entity_ids_by_device_id[device_id] = set()
    entity_ids_by_device_id[device_id].add(entity["id"])

# get the id of the device we are looking for from its name
input_name = sys.argv[1]
print(f"Input: {input_name}")
target_device_id = None
if input_name in device_ids_by_name:
    target_device_id = device_ids_by_name[input_name]
if (target_device_id is None) and (input_name in device_ids_by_name_by_user):
    target_device_id = device_ids_by_name_by_user[input_name]
# if we identified a target device...
if target_device_id is not None:
    # gather the full list of devices and dependencies to remove
    device_id_list = get_device_id_list(target_device_id)
    print("Devices to remove:")
    print([device_id + " - " + devices[device_index_by_id[device_id]]["name"] for device_id in device_id_list])

    # gather the full list of config entries to be removed
    for device_id in device_id_list:
        device = devices[device_index_by_id[device_id]]
        for config_entry_id in device["config_entries"]:
            if config_entry_id in device_ids_by_config_entry_id:
                device_ids_by_config_entry_id[config_entry_id].remove(device_id)
    config_entry_id_list = []
    for config_entry_id in device_ids_by_config_entry_id.keys():
        if len(device_ids_by_config_entry_id[config_entry_id]) == 0:
            config_entry_id_list.append(config_entry_id)
    print("Config Entries to remove:")
    print([config_entry_id + " - " + config_entries[config_entry_index_by_entry_id[config_entry_id]]["title"] for config_entry_id in config_entry_id_list])

    # gather the full list of entities to remove
    entity_id_list = []
    for device_id in device_id_list:
        if device_id in entity_ids_by_device_id:
            entity_id_list.extend(entity_ids_by_device_id[device_id])
    print("Entities to remove:")
    print([entity_id + " - " + entities[entity_index_by_id[entity_id]]["name"] for entity_id in entity_id_list])

    # now actually remove the elements
    devices = list_without_indexes(devices, device_id_list, device_index_by_id)
    config_entries = list_without_indexes(config_entries, config_entry_id_list, config_entry_index_by_entry_id)
    entities = list_without_indexes(entities, entity_id_list, entity_index_by_id)

    # restore them to their places in their respective documents
    core_config_entries["data"]["entries"] = config_entries
    core_entity_registry["data"]["entities"] = entities
    core_device_registry["data"]["devices"] = devices

    # and save them out as new files
    to_json_file("core.config_entries", core_config_entries)
    to_json_file("core.entity_registry", core_entity_registry)
    to_json_file("core.device_registry", core_device_registry)
