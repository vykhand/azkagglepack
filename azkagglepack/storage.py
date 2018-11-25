import os
from azure.storage.blob import BlockBlobService
#import tgt_salt.utils as u
import logging
#import tgt_salt.constants as C

#log = logging.getLogger(C.LOGGER)
import glob

#conf = u.get_config()


class StorageHelper(object):
    def __init__(self, storage_account=None, storage_key=None, container=None):
        try:
            acc = storage_account if storage_account \
                else os.environ.get("AZURE_STORAGE_ACCOUNT",
                                    conf["AZURE_STORAGE_ACCOUNT"])
            kee = storage_key if storage_key else os.environ.get("AZURE_STORAGE_KEY",
                                                                 conf["AZURE_STORAGE_KEY"])
            self.blob = BlockBlobService(account_name=acc, account_key=kee)
            self.container = container if container else os.environ.get("AZURE_CONTAINER_NAME", C.RUNS_CONTAINER)

        except KeyError as e:
            log.error("Please set storage account, key, and container")
            raise e

    def set_container_name(self, container):
        self.container = container

    def get_blob(self, to_folder, blob_name):
        folders = blob_name.split("/")[:-1]
        os.makedirs(os.path.join(to_folder, *folders), exist_ok=True)
        self.blob.get_blob_to_path(
            self.container, blob_name=blob_name,
            file_path=os.path.join(to_folder, blob_name))

    def save_blob(self, file_path, folder=None):
        blob_path = folder + "/" + os.path.basename(file_path) if folder else os.path.basename(file_path)

        self.blob.create_blob_from_path(
            self.container, blob_path, file_path)

    def blob_exists(self, file_path, folder=None):
        basename = os.path.basename(file_path)
        blob_name = folder + "/" + basename if folder else basename
        files = [n.name for n in self.blob.list_blobs(self.container) if n.name == blob_name]
        return len(files) > 0

    def get_folder(self, blob_folder, to_folder):
        files = [n.name for n in self.blob.list_blobs(self.container) if n.name.startswith(blob_folder + "/")]

        for f in files:
            os.makedirs(os.path.join(to_folder, *f.split("/")[:-1]), exist_ok=True)
            log.debug("downloading file " + f)
            self.get_blob(to_folder=to_folder, blob_name=f)

    def upload_folder(self, folder, storage_folder=None):
        """Uploads folders and all its subfolders to root folder in a container."""
        log.debug(f"uploading folder {folder} to contailer:{self.container}")

        base_folder = ((storage_folder + "/") if storage_folder else "") + \
                      os.path.basename(folder)
        sz = 0
        for i, (root, subfolders, files) in enumerate(os.walk(folder)):
            blob_folder = base_folder + "/" + os.path.relpath(root, folder).replace(os.path.sep, "/").lstrip(".")
            for f in files:
                self.save_blob(os.path.join(root, f), blob_folder.rstrip("/"))
                sz += os.path.getsize(os.path.join(root, f))
                # log.debug(f"Uploading file: {f} to container: {self.container} folder: {blob_folder}")
        log.info(f"Uploaded {i} files to contailer:{self.container}, total size: {sz/2**30:.2f}GB")



