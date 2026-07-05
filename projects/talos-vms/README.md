# Talos VMs on VMware ESXi

This repository provides an Ansible playbook to provision VMs on a VMware ESXi host for use with SideroLabs Omni and Talos.

## Prerequisites

- A running VMware ESXi hypervisor and credentials
- Python 3.13.14 and pip
- Ansible (ansible-core)
- ovftool (VMware OVF Tool) for OVF/OVA conversion
- Access to the SideroLabs Omni portal to generate/download a Talos ISO

## Create a Virtual Environment

Create a venv:

```bash
# Make sure you are on a linux partition and not on the windows mount (/mnt/c)
cd $HOME
mkdir ansible

python -m venv .venv
```

Activate it:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (cmd.exe)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

## Install prerequisites

Install Ansible and related tooling:

```bash
pip install ansible-core==2.21.1 ansible-lint==26.6.0 pyvmomi==9.1.0.0 requests==2.34.2
```

> **Note:** install `ansible-core` here, **not** the `ansible` meta-package (the community bundle). The bundle ships ~85 collections into the environment's `site-packages/ansible_collections`; installing collections via `ansible-galaxy` below (into `~/.ansible/collections`) then leaves two copies of the same collection and `ansible-lint` warns:
> `Another version of 'community.vmware' ... was found installed ... only the first one will be used`.
> Keeping only `ansible-core` here makes the Galaxy install the single source of collections. If you layer a `.venv` on top of a conda env, also ensure the `ansible` bundle is **not** installed at the conda-env level (`pip uninstall ansible` in that env), otherwise its bundled collections leak in the same way.

Install required Ansible collections:

```bash
ansible-galaxy collection install -r requirements.yml
```

## Prepare an OVA template

OVF/OVA are virtual appliance formats. Use OVF Tool to convert if needed.

1. On the ESXi host create a minimal VM to act as the template and export it as an OVF (or OVA).
2. If you exported an OVF, convert it locally to OVA:

```bash
ovftool talos-vm0.ovf talos-vm0.ova
```

3. Place the OVA where the playbook host can access it and update the `ova_file` variable in your inventory or `group_vars` (for example, `group_vars/all.yaml`) to point to that path.

## Create an Ansible Vault for secrets

Use Ansible Vault to store ESXi credentials and other secrets. Do not commit the vault file or its password.

Create the vault:

```bash
ansible-vault create vault/vault-keyring.yaml
```

Example contents (inside the vault):

```yaml
ova_deployment_hostname: "esxi.example.com"
ova_deployment_username: "root"
ova_deployment_password: "your-esxi-password"
```

You can edit the vault with `ansible-vault edit` or supply a vault ID / file with `--vault-id` when running playbooks.

## Configure host_vars

For each VM to create, add `host_vars/<hostname>.yaml` with at least the MAC address and NIC name. Example `host_vars/talos-vm0.yaml`:

```yaml
mac_address: "00:50:56:aa:bb:cc"
nic_name: "vmnic0"
```

Adjust additional host-specific variables as required.

## Fix permissions on WSL (if needed)

If you work from the Windows partition (/mnt/c), you must enable NTFS extended attributes:

```yaml
[automount]
options = "metadata,uid=1000,gid=1000,umask=022"
```

To apply the changes, restart WSL:

```bash
wsl --shutdown
```

This causes files under /mnt/c to store permissions in NTFS extended attributes (user.LxUid, user.LxGid, user.LxMode), and makes your user (uid 1000) the actual owner.

👉 Now chmod, chown, and umask work correctly, and Ansible will see consistent permissions.

## Generate Talos ISO

Generate or download a Talos ISO from the SideroLabs Omni portal and place it where the playbook host can access it. Update `talos_iso_path` in your inventory or `group_vars/all.yaml` to point to the ISO.

## Deploy

Run the deployment playbook:

```bash
ansible-playbook -i hosts.yaml playbooks/deploy.yaml --ask-vault-pass
```

If you want, you can also perform a syntax check on the playbook before running it:

```bash
ansible-lint
```

Enter the vault password when prompted (or use `--vault-id`).

## Common variables

- `ova_file`: path to the OVA template (local or remote)
- `talos_iso_path`: path to the Talos ISO to attach to new VMs
- `ova_deployment_hostname`: ESXi host FQDN or IP
- `ova_deployment_username`: ESXi user
- `ova_deployment_password`: ESXi password

Place these in `group_vars/all.yaml` or the appropriate vars file for your inventory.

## Troubleshooting

- ovftool not found: install OVF Tool and ensure it is on PATH.
- Permission issues on WSL: enforce restrictive permissions (see section above).
- Inventory not found: verify `hosts.yaml` or `inventory/hosts` path and permissions.
- Vault errors: verify the vault password or vault-id being used.

## Security

- Never commit `vault/vault-keyring.yaml` or any plaintext credentials.
- Protect the vault password and use secure methods in CI/CD (vault IDs, environment variables, or restricted vault password files).

## License and Support

Refer to the repository LICENSE file for licensing. For issues, open a GitHub issue in this repository.
