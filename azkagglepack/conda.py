

def install_conda_env(vm, conda_env_file, remote_file_prefix = None):
    remote_conda_path = f"/home/{vm.admin_user}/{remote_file_prefix}_conda_dependencies.yml"
    vm.put_file(local_path=conda_env_file, remote_path=remote_conda_path)
    vm.run_cmd("source /etc/profile;" +
               f"conda env create -f {remote_conda_path}")

def install_jupyter(vm, env_name):
    vm.run_cmd("source /etc/profile;" +
               f"source activate {env_name};" +
               f'python -m ipykernel install --name {env_name} ' +
               f'--display-name "Python ({env_name})"')

def install_ssh_key(vm, local_key_path):
    vm.put_file(local_key_path, f"/home/{vm.admin_user}/.ssh/id_rsa")
    vm.run_cmd(f"chmod 600 /home/{vm.admin_user}/.ssh/id_rsa")

def clone_repo(vm, repo_addr):
    vm.run_cmd(f"git clone -q {repo_addr}")

def create_links(vm, project_alias):
    remote_work_dir = f"/home/{vm.admin_user}/{project_alias}"
    remote_data_dir = f"/home/{vm.admin_user}/data/{project_alias}"
    vm.run_commands([f"cd /home/{vm.admin_user}/{project_alias};ln -s {remote_data_dir} input",
                     f"cd /home/{vm.admin_user}/notebooks;ln -s {remote_work_dir} {project_alias}"])