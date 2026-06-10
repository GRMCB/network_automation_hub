# Running containerlab via Lima

containerlab has no native macOS binary and Nokia SR Linux images are
amd64-only, so this Lima config gives you a small Linux VM (with Docker +
containerlab pre-installed) that behaves like a real Linux host.

## 1. Install Lima

```bash
brew install lima
```

## 2. Edit the mount path

Open `containerlab.yaml` and change:

```yaml
mounts:
  - location: "~/path/to/openconfig-automation"
```

to the actual path of this project on your Mac, e.g.:

```yaml
mounts:
  - location: "~/repos/openconfig-automation"
```

## 3. Start the VM

```bash
limactl start --name=clab ./containerlab.yaml
```

First boot will take a few minutes — it downloads an Ubuntu amd64 image
(running under emulation on Apple Silicon) and installs Docker +
containerlab via the provisioning script.

Check progress:

```bash
limactl shell clab -- cloud-init status --wait
```

## 4. Deploy the lab

```bash
limactl shell clab
cd /workspace/containerlab
sudo containerlab deploy -t topology.clab.yml
```

## 5. Verify and get connection details

```bash
sudo containerlab inspect -t topology.clab.yml
```

The NETCONF ports (50001, 50002) defined in `topology.clab.yml` are
forwarded to your Mac via `portForwards` in `containerlab.yaml`, so Ansible
running on your Mac (`ansible/inventory.yml`) can reach the SR Linux nodes
at `127.0.0.1:50001` / `127.0.0.1:50002` — update `ansible_host` /
`ansible_port` in `inventory.yml` accordingly if you go this route, since
the management IPs (172.20.20.x) are only reachable from inside the VM.

Alternative: run Ansible *inside* the VM too (it's just Ubuntu — `pip
install ansible ansible-pyats` etc.), so it talks to the SR Linux
containers' IPs directly without needing port forwards.

## 6. Tear down

```bash
sudo containerlab destroy -t topology.clab.yml
limactl stop clab
limactl delete clab   # if you want to remove the VM entirely
```

## Notes

- `/workspace` inside the VM maps to your project directory on the Mac, so
  `topology.clab.yml` edits are shared instantly — no need to restart the VM.
- containerlab's lab state directory (`clab-oc-lab/`) will be created under
  `/workspace/containerlab/` and is gitignored already.
- If `docker` commands inside the VM say permission denied right after first
  boot, log out and back in (`limactl shell clab` again) so the
  `usermod -aG docker` group membership takes effect.
