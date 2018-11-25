


def setup_kaggle_cli(vm, kaggle_file):
    vm.run_commands(["source /etc/profile; pip install kaggle"])
    vm.run_cmd(f"mkdir /home/{vm.admin_user}/.kaggle")
    vm.put_file(kaggle_file, f"/home/{vm.admin_user}/.kaggle/kaggle.json")


def download_data_from_kaggle(vm, competition_name, competition_alias):
    vm.run_cmd(f"mkdir -p ~/data/{competition_alias}")
    vm.run_cmd("source /etc/profile;kaggle competitions download -c {} -p ~/data/{}".format(competition_name,
                                                                                                competition_alias))

def upload_data_to_blob(vm, competition_alias, container_name, storage_account, storage_key):
    vm.run_commands(['echo export AZURE_STORAGE_ACCOUNT="{}" >> /home/vykhand/{}-env.sh'.format(storage_account,
                                                                                                    competition_alias),
                         'echo export AZURE_STORAGE_KEY="{}" >> /home/vykhand/{}-env.sh'.format(storage_key,
                                                                                                competition_alias)])

    vm.run_cmd("source /etc/profile;" +
                   f"source /home/{vm.admin_user}/{competition_alias}-env.sh;" +
                   f"az storage blob upload-batch -s /home/{vm.admin_user}/data/{competition_alias} -d {competition_alias}")


def download_data_from_blob(vm, competition_alias, container_name, storage_account, storage_key):
    vm.run_cmd(f"mkdir -p ~/data/{competition_alias}")
    vm.run_commands(['echo export AZURE_STORAGE_ACCOUNT="{}" >> /home/vykhand/{}-env.sh'.format(storage_account,
                                                                                                    competition_alias),
                         'echo export AZURE_STORAGE_KEY="{}" >> /home/vykhand/{}-env.sh'.format(storage_key,
                                                                                                competition_alias)])

    vm.run_cmd("source /etc/profile;" +
                   f"source /home/{vm.admin_user}/{competition_alias}-env.sh;" +
                   f"az storage blob download-batch -d /home/{vm.admin_user}/data/{competition_alias} -s {competition_alias}")


