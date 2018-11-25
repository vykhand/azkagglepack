import os
import traceback
import requests

import paramiko

from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.resource.resources.models import DeploymentMode

from msrestazure.azure_exceptions import CloudError

SKU_D2S_V3 = "Standard_D2s_v3"
SKU_D4S_V3 = "Standard_D4s_v3"
SKU_D8S_V3 = "Standard_D8s_v3"
SKU_D16S_V3 = "Standard_D16s_v3"
SKU_NC6 = "Standard_NC6"
SKU_NC6_V2 = "Standard_NC6_v2"

DSVM_TEMPLATE_URL = "https://raw.githubusercontent.com/Azure/DataScienceVM/master/Scripts/CreateDSVM/Ubuntu/azuredeploy.json"

DISK_PREMIUM_LRS = "Premium_LRS"
DISK_STANDARD_LRS = "Standard_LRS"

import yaml
import json

from haikunator import Haikunator
import logging

log = logging.getLogger("azkagglepack")

def ssh_alive(ssh_client):
    # use the code below if is_active() returns True
    try:
        transport = ssh_client.get_transport()
        transport.send_ignore()
        return True
    except Exception:
        return False


# connection is closed

class AzureVM:
    def __init__(self, vm_name=None, group_name=None, config_file=None):

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

        self.vm_name = vm_name if vm_name else "dsvm-" + self._hkn.haikunate(token_length=0)
        self.group_name = group_name if group_name else self.vm_name

        self.attach()

    def attach(self, admin_user = None, ssh_key_file = None, ssh_pass = None):

        if admin_user:
            assert(ssh_key_file or ssh_pass)
            self.admin_user = admin_user
            self.ssh_key_file = ssh_key_file
            self.ssh_pass  = ssh_pass

        self.group_exists = len([g for g in self._resource_client.resource_groups.list() \
                                 if g.name == self.group_name]) > 0
        self.vm_exists = self.group_exists \
                         and len([v for v in self._compute_client.virtual_machines.list(self.group_name) \
                                  if v.name == self.vm_name]) > 0

        if self.vm_exists:
            self.vm = self._compute_client.virtual_machines.get(self.group_name, self.vm_name)
            self.vm_status = (self
                              ._compute_client
                              .virtual_machines
                              .get(self.group_name, self.vm_name, expand='instanceView')
                              .instance_view.statuses[1].display_status)
            self.vm_hostname = "{}.{}.cloudapp.azure.com".format(self.vm_name, self.vm.location)


    def create(self, sku, location, admin_user, admin_pass=None, ssh_key_file=None,
               ssh_key_str=None, os_disk_size_gb=None, data_disk_size_gb=None,
               os_disk_type=None, data_disk_type=None):

        assert (admin_pass or ssh_key_file or ssh_key_str)

        vm_name = self.vm_name
        grp_name = self.group_name

        template = requests.get(DSVM_TEMPLATE_URL).json()

        vm_props = [i["properties"] for i in template["resources"] \
                    if i["type"] == "Microsoft.Compute/virtualMachines"][0]
        vm_stor_profile = vm_props["storageProfile"]

        if os_disk_size_gb:
            vm_stor_profile["osDisk"]["diskSizeGB"] = os_disk_size_gb
        if data_disk_size_gb:
            vm_stor_profile["dataDisks"][0]["diskSizeGB"] = data_disk_size_gb
        if os_disk_type:
            vm_stor_profile["osDisk"]["managedDisk"]["storageAccountType"] = os_disk_type
        if data_disk_type:
            vm_stor_profile["dataDisks"][0]["managedDisk"]["storageAccountType"] = data_disk_type

        if ssh_key_file:
            with open(ssh_key_file, "r") as f:
                ssh_key = f.read().replace("\n", "")
        else:
            ssh_key = ssh_key_str

        parameters = {
            'vmName': self.vm_name,
            'vmSize': sku,
            'adminUsername': admin_user,
            'adminPassword': admin_pass
        }

        if ssh_key:
            parameters["sshKeyData"] = ssh_key

            vm_os_profile = vm_props["osProfile"]
            vm_os_profile["linuxConfiguration"] = {"ssh": {
                "publicKeys": [
                    {
                        "path": "[variables('sshKeyPath')]",
                        "keyData": "[parameters('sshKeyData')]"
                    }
                ]
            }}
            template["parameters"]["sshKeyData"] = {
                "type": "string",
                "metadata": {
                    "description": "SSH public key data as a string."
                }}

            template["variables"][
                "sshKeyPath"] = "[concat('/home/',parameters('adminUsername'),'/.ssh/authorized_keys')]"

        parameters = {k: {'value': v} for k, v in parameters.items()}

        deployment_properties = {
            'mode': DeploymentMode.incremental,
            'template': template,
            'parameters': parameters
        }

        self._resource_client.resource_groups.create_or_update(self.group_name, {"location": location})

        deployment_async_operation = self._resource_client.deployments.create_or_update(self.group_name,
                                                                                        'deployment-' + vm_name,
                                                                                        deployment_properties)
        deployment_async_operation.wait()

        if admin_pass:
            self.attach(admin_user, ssh_pass=admin_pass)
        else:
            self.attach()

        if data_disk_size_gb:
            self.resize_data_partition()

        return vm_name, grp_name

    def resize_data_partition(self):
        return self.run_commands(["sudo growpart /dev/sdc 1", "sudo resize2fs /dev/sdc1"])

    def stop(self):
        op = self._compute_client.virtual_machines.deallocate(self.group_name, self.vm_name)
        op.wait()


    def start(self):
        op = self._compute_client.virtual_machines.start(self.group_name, self.vm_name)
        op.wait()
        return op

    def resize(self, new_sku):
        self.stop()
        op = self._compute_client.virtual_machines.update(self.vm_name,
                                                          self.group_name,
                                                          {"hardware_profile": {"vm_size": new_sku}})
        op.wait()
        return op

    def resizeOSDisk(self, new_size_gb):
        self.stop()
        os_disk_name = self.vm.storage_profile.os_disk.name
        os_disk = self._compute_client.disks.get(self.group_name, os_disk_name)
        os_disk.disk_size_gb = new_size_gb
        op = self._compute_client.disks.create_or_update(self.group_name, os_disk.name, os_disk)
        op.wait()
        self.start()

    def resizeDataDisk(self, new_size_gb):
        self.stop()
        disk_name = self.vm.storage_profile.data_disks[0].name
        disk = self._compute_client.disks.get(self.group_name, disk_name)
        disk.disk_size_gb = new_size_gb
        op = self._compute_client.disks.create_or_update(self.group_name, disk.name, disk)
        op.wait()
        self.start()
        self.resize_data_partition()

        return op

    def run_sdk(self, commands):
        params = {'command_id': 'RunShellScript',
                      "script": commands}

        op = self._compute_client.virtual_machines.run_command(self.group_name, self.vm_name, parameters = params)
        op.wait()
        msg = op.result().as_dict()["value"][0]["message"]
        stdout = msg[msg.find("[stdout]") + 8:msg.find("[stderr]")].lstrip("\n")
        stderr = msg[msg.find("[stderr]") + 8:].lstrip("\n")
        return [(stdout, stderr)]

    def ssh_connect(self):

        if not hasattr(self, "_ssh_client"):
            self._ssh_client = paramiko.SSHClient()
            #self._ssh_client.load_system_host_keys()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())


        if not ssh_alive(self._ssh_client):
            if hasattr(self, "ssh_key_file") and self.ssh_key_file:
                self._ssh_client.connect(self.vm_hostname, username = self.admin_user,
                                         key_filename = self.ssh_key_file)
            elif hasattr(self, "ssh_pass") and self.ssh_pass:
                self._ssh_client.connect(self.vm_hostname, username = self.admin_user,
                                         key_filename = self.ssh_key_file)
            else:
                raise ValueError("Must specify either key file or password")

    def run_ssh(self, commands, env_dict = None):
        assert(hasattr(self, "admin_user"))
        assert(hasattr(self, "ssh_key_file") or hasattr(self, "ssh_pass"))
        assert(hasattr(self, "vm_hostname"))

        self.ssh_connect()

        responses = []

        for c in commands:
            ssh_stdin, ssh_stdout, ssh_stderr = self._ssh_client.exec_command(c, environment = env_dict)
            resp = ("\n".join([l.rstrip("\n") for l in ssh_stdout.readlines()]),
                              "\n".join([l.rstrip("\n") for l in ssh_stderr.readlines()]))
            responses.append(resp)

            #if len(resp[1])>0:
            #    raise RuntimeError("Command failed: "  + resp[1])

        return responses

    def run_commands(self, commands):
        if hasattr(self, "admin_user") and (hasattr(self, "ssh_key_file") or hasattr(self, "ssh_pass")):
            res = self.run_ssh(commands)
        else:
            res =  self.run_sdk(commands)
        return res

    def run_cmd(self, cmd):
        res = self.run_commands([cmd])
        return res

    def destroy(self):
        op = self._resource_client.resource_groups.delete(self.group_name)
        op.wait()
        return op

    def put_file(self, local_path, remote_path):
        self.ssh_connect()
        sftp = self._ssh_client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

    def get_file(self, remote_path, local_path):
        self.ssh_connect()
        sftp = self._ssh_client.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()
