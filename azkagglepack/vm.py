import os
import traceback

import paramiko

from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import DiskCreateOption

from msrestazure.azure_exceptions import CloudError

SKU_D4S_V3 = "Standard_D4s_v3"
SKU_D8S_V3 = "Standard_D8s_v3"
SKU_D16S_V3 = "Standard_D16s_v3"
SKU_NC6 = "Standard_NC6"
SKU_NC6_V2 = "Standard_NC6_v2"

import yaml

from haikunator import Haikunator
import logging

log = logging.getLogger("azkagglepack")


class AzureVM:
    def __init__(self, vm_name=None, config_file=None, group_name=None):

        if config_file:
            config = yaml.load(open(config_file, "r"))
        else:
            config = os.environ

        self._tenant_id = config["AZURE_TENANT_ID"]
        self._client_id = config["AZURE_CLIENT_ID"]
        self._client_secret = config["AZURE_CLIENT_SECRET"]
        self._subscription_id = config["AZURE_SUBSCRIPTION_ID"]
        self._credentials = ServicePrincipalCredentials(client_id=self._client_id,
                                                        secret=self._client_secret,
                                                        tenant=self._tenant_id)
        self._resource_client = ResourceManagementClient(self._credentials, self._subscription_id)
        self._compute_client = ComputeManagementClient(self._credentials, self._subscription_id)
        self._network_client = NetworkManagementClient(self._credentials, self._subscription_id)
        self._hkn = Haikunator()
        self.vm_name = vm_name if vm_name else self._hkn.haikunate(token_length=0)
        self.group_name = group_name if group_name else vm_name

    def create(self, sku, location, os_disk_size_gb=50, data_disk_size_gb=100):
        vm_name = self.vm_name
        grp_name = self.group_name

        self._resource_client.resource_groups.create_or_update(self.group_name, {"location": location})

        create_vars = {"vnet_name": vm_name + "-vnet",
                       "subnet_name": vm_name + "-subnet",
                       "os_disk_name": vm_name + "-osdisk",
                       "data_disk_name": vm_name + "-data-0",
                       "addressPrefix": "10.0.0.0/16",
                       "storage_account_name": vm_name.replace("-", "") + "storacc",
                       "ip_config_name": vm_name + "-ip-config",
                       "nic_name": vm_name + "-nic",
                       "vm_reference": \
                           {"publisher": "microsoft-dsvm",
                            "offer": "linux-data-science-vm-ubuntu",
                            "sku": "linuxdsvmubuntu",
                            "version": "latest"}
                       }

        try:
            nic = self._create_nic(self._network_client)
            vm_params = self._create_vm_params(nic.id, create_vars["vm_reference"])
        except CloudError:
            log.error('A VM operation failed:\n{}'.format(traceback.format_exc()))
        else:
            log.info('All VM operations completed successfully!')
        finally:
            # Delete Resource group and everything in it
            log.debug('\nDelete Resource Group')
            delete_async_operation = self._resource_client.resource_groups.delete(self.group_name)
            delete_async_operation.wait()
            log.debug("\nDeleted: {}".format(self.group_name))

    def stop(self):
        pass

    def start(self):
        pass

    def resize(self, ):
        pass

    def resizeOSDisk(self, new_size_gb):
        pass

    def resizeDataDisk(self, new_size_gb):
        pass

    def run_command(self):
        pass
