---
layout: default
title: "CKAD Preparation — Understand Application Security"
date: 2026-10-16
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261016-ckad/article.webp"
summary: "Configure application security with Pod and container SecurityContexts. Run as non-root, share volumes with fsGroup, use a read-only root filesystem, restrict Linux capabilities, and verify seccomp and Pod Security Admission in a runnable lab."
---

# CKAD Preparation — Understand Application Security

This chapter covers the CKAD requirement **Understand Application Security (SecurityContexts, Capabilities, etc.)**. We will configure a workload's Linux identity, control where it can write, and observe which operations its processes can perform.

The [previous chapter on ServiceAccounts](https://supaahiro.github.io/schwifty-lab/blog-posts/20261015-ckad/article_EN.html) assigned an identity for requests to the Kubernetes API. A process also has an operating-system identity: its UID, GID and supplementary groups. Changing `runAsUser` changes that Linux identity; it does not grant Kubernetes RBAC permissions.

Return to the [CKAD series index](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html) for the full roadmap. The chapter on [authentication, authorization and admission control](https://supaahiro.github.io/schwifty-lab/blog-posts/20261008-ckad/article_EN.html) explains the API admission stage that we will revisit at the end.

## Choose the Right SecurityContext

Security settings appear at two levels. In a Deployment, the Pod-level path starts at `spec.template.spec.securityContext`, and the container-level path is under `spec.template.spec.containers`.

| Setting | Pod level | Container level | Purpose |
| --- | --- | --- | --- |
| `runAsUser`, `runAsGroup` | Yes | Yes | Select process UID and primary GID |
| `runAsNonRoot` | Yes | Yes | Require a nonzero UID |
| `fsGroup`, `supplementalGroups` | Yes | No | Configure additional group access |
| `seccompProfile` | Yes | Yes | Select a syscall-filtering profile |
| `allowPrivilegeEscalation` | No | Yes | Control privilege gains through execution |
| `readOnlyRootFilesystem` | No | Yes | Make the container root filesystem read-only |
| `capabilities`, `privileged` | No | Yes | Control privileged Linux operations |

When the same supported field is set at both levels, the container value takes precedence for that container. Pod settings provide defaults, so inspect each container for overrides. The [Pod API reference](https://kubernetes.io/docs/reference/kubernetes-api/core/pod-v1/) describes the individual fields and their scope.

## Prepare the Lab

Use a disposable cluster with Linux nodes, Kubernetes 1.35 or later, and permission to create namespaces and Pods, set namespace labels, and execute commands in containers. Pod Security Admission must be enabled without an exemption for these requests. The manifests pin its policy version to `v1.35`; they were tested on Kubernetes **1.35.1** with containerd.

The examples use **Bash**, including line continuations and pipelines. The commands executed inside the containers use BusyBox `sh`.

```bash
git clone https://github.com/Supaahiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261016-ckad
kubectl config current-context
kubectl version
kubectl get namespace ckad-security ckad-security-restricted --ignore-not-found
```

If either namespace already exists, choose unused names consistently throughout the manifests and commands before proceeding. These exercises create and later delete both namespaces.

Apply `manifests/01-namespaces.yaml`:

```bash
kubectl apply -f manifests/01-namespaces.yaml
```

It creates `ckad-security-restricted` with Restricted enforcement and `ckad-security` with Baseline enforcement. The main application runs in the Restricted namespace. The Baseline namespace contains the deliberate UID conflict and the root capability comparison. Keep these examples in their assigned namespaces, and apply files in the order shown rather than recursively applying the whole directory.

## Run Two Containers with Explicit Identities

The full `manifests/02-hardened-pod.yaml` contains:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: hardened
  namespace: ckad-security-restricted
spec:
  nodeSelector:
    kubernetes.io/os: linux
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 3000
    fsGroup: 2000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: busybox:1.37
      command: ["sh", "-c", "exec sleep 86400"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: data
          mountPath: /data
    - name: helper
      image: busybox:1.37
      command: ["sh", "-c", "exec sleep 86400"]
      securityContext:
        runAsUser: 1001
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      emptyDir: {}
```

Create the Pod and inspect both identities:

```bash
kubectl apply -f manifests/02-hardened-pod.yaml
kubectl wait -n ckad-security-restricted --for=condition=Ready pod/hardened --timeout=120s
kubectl exec -n ckad-security-restricted hardened -c app -- id
kubectl exec -n ckad-security-restricted hardened -c helper -- id
```

Expected output in this lab:

```text
uid=1000 gid=3000 groups=2000,3000
uid=1001 gid=3000 groups=2000,3000
```

The `app` container inherits UID 1000. The helper overrides only `runAsUser`, so it uses UID 1001 while retaining the Pod's primary group and supplementary filesystem group. Group display order can vary; other images can also contribute group memberships through `/etc/group`.

`runAsNonRoot: true` is a guard, not a request to pick an arbitrary non-root user. Explicit numeric UIDs make the intended identity clear. They do not create an `/etc/passwd` entry or repair image file permissions. A real application image must work with its selected UID, including any startup scripts and writable directories.

We disable automatic ServiceAccount token mounting because these containers make no Kubernetes API calls. That setting is separate from their Linux permissions.

## Share a Writable Volume with fsGroup

Create a group-writable file as the application, then append to it as the helper:

```bash
kubectl exec -n ckad-security-restricted hardened -c app -- \
  sh -c 'umask 0002; echo created-by-app > /data/message'
kubectl exec -n ckad-security-restricted hardened -c helper -- \
  sh -c 'echo updated-by-helper >> /data/message; cat /data/message'
kubectl exec -n ckad-security-restricted hardened -c app -- \
  stat -c '%u:%g:%a' /data/message
```

Expected results:

```text
created-by-app
updated-by-helper
1000:2000:664
```

The file belongs to UID 1000 and group 2000. Both processes belong to group 2000, and mode `664` grants group write access. The `umask` matters: a group membership alone does not make a file writable.

`fsGroup` supplies a supplementary group and participates in ownership and permission setup for supported volumes. This lab demonstrates it with `emptyDir`. It does not recursively rewrite the container image's files, and storage-driver behavior matters for other volume types. See the [security context volume example](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/#set-the-security-context-for-a-pod) for details.

Now try writing outside that volume:

```bash
kubectl exec -n ckad-security-restricted hardened -c app -- touch /tmp/probe
```

The command intentionally fails with **Read-only file system**. `/tmp` is part of this container's read-only root filesystem, while `/data` is a separate writable mount. A production application that needs temporary files can receive another `emptyDir` mounted at `/tmp`; caches and data directories need the same deliberate treatment.

`readOnlyRootFilesystem` does not make every attached volume read-only. Use `volumeMounts[].readOnly: true` when a particular mount should also reject writes.

## Verify Privilege Escalation and seccomp Settings

Inspect the application container's main process:

```bash
kubectl exec -n ckad-security-restricted hardened -c app -- \
  sh -c 'grep -E "^(CapEff|NoNewPrivs|Seccomp):" /proc/1/status'
```

Expected values:

```text
CapEff: 0000000000000000
NoNewPrivs: 1
Seccomp: 2
```

Spacing in `/proc` output can differ. These fields tell us that the process has no effective Linux capabilities, has the no-new-privileges flag set, and is running with seccomp filtering.

`allowPrivilegeEscalation: false` sets Linux's `no_new_privs` flag. It prevents `execve` from granting privileges through mechanisms such as set-user-ID executables or file capabilities. It does not revoke capabilities already granted to the process or change UID 0 into a non-root identity. The [kernel documentation for no_new_privs](https://docs.kernel.org/userspace-api/no_new_privs.html) explains that boundary.

`seccompProfile.type: RuntimeDefault` selects the container runtime's default syscall filter. Its exact rules depend on the runtime and version. `Localhost` selects a profile already installed on the node; `Unconfined` opts out of seccomp filtering. The value `Seccomp: 2` confirms filter mode, but does not identify the profile or enumerate its blocked syscalls. Our lab checks the active mode, not a custom syscall policy. See Kubernetes' [seccomp tutorial](https://kubernetes.io/docs/tutorials/security/seccomp/) for profile-specific testing.

## Diagnose a runAsNonRoot Conflict

The intentional failure in `manifests/failures/03-root-conflict.yaml` combines these Pod settings:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 0
  seccompProfile:
    type: RuntimeDefault
```

The Baseline namespace permits the request, but the kubelet cannot start this container with UID 0 while enforcing `runAsNonRoot`:

```bash
kubectl apply -f manifests/failures/03-root-conflict.yaml
kubectl wait -n ckad-security \
  --for=jsonpath='{.status.containerStatuses[0].state.waiting.reason}'=CreateContainerConfigError \
  pod/root-conflict --timeout=90s
kubectl describe pod root-conflict -n ckad-security
```

Expect **CreateContainerConfigError** and an event explaining that `runAsNonRoot` conflicts with UID 0. The Pod object exists, but its application process has not started. A successful API dry-run would not prove that the container can run.

Fix the UID while retaining the guard. Most Pod security fields cannot be changed in place, so delete this disposable Pod and recreate it using the supplied local patch:

```bash
kubectl delete pod root-conflict -n ckad-security
kubectl patch --local -f manifests/failures/03-root-conflict.yaml \
  --type=merge --patch-file manifests/patches/03-nonroot.yaml -o yaml | \
  kubectl apply -f -
kubectl wait -n ckad-security --for=condition=Ready pod/root-conflict --timeout=120s
kubectl exec -n ckad-security root-conflict -- id
```

The patch sets `runAsUser: 1000`; the replacement starts with that UID. For a Deployment, update the Pod template and allow a rollout to replace its Pods instead.

Another possible error involves an image whose `USER` is a name rather than a numeric UID: the kubelet may be unable to verify that it is non-root. Choose a compatible numeric UID or fix the image metadata instead of removing the guard without understanding the cause.

## Drop Capabilities and Add One Back

Linux capabilities divide privileged operations into separate permissions. For example, `CAP_CHOWN` permits arbitrary changes to file ownership. Kubernetes capability names omit the `CAP_` prefix, so the manifest uses `CHOWN`. See the [Linux capabilities reference](https://man7.org/linux/man-pages/man7/capabilities.7.html).

`manifests/04-capabilities.yaml` starts two containers as UID 0 in the Baseline namespace, each with its own writable `emptyDir`. Both use a read-only root filesystem, `RuntimeDefault` seccomp and `allowPrivilegeEscalation: false`. Their capability configuration is the difference:

For `no-caps`:

```yaml
capabilities:
  drop: ["ALL"]
```

For `chown-only`:

```yaml
capabilities:
  drop: ["ALL"]
  add: ["CHOWN"]
```

This is a controlled root-process comparison, not the configuration of the non-root application above. Create it:

```bash
kubectl apply -f manifests/04-capabilities.yaml
kubectl wait -n ckad-security --for=condition=Ready pod/capability-lab --timeout=120s
kubectl exec -n ckad-security capability-lab -c no-caps -- id
kubectl exec -n ckad-security capability-lab -c chown-only -- id
```

Both commands report UID 0. Try changing a new file's owner in the first container:

```bash
kubectl exec -n ckad-security capability-lab -c no-caps -- \
  sh -c 'touch /work/probe && chown 1234 /work/probe'
```

`touch` succeeds, but `chown` intentionally fails with **Operation not permitted**. Root without the relevant capability cannot perform this ownership change.

Repeat the operation in the second container:

```bash
kubectl exec -n ckad-security capability-lab -c chown-only -- \
  sh -c 'touch /work/probe && chown 1234 /work/probe'
kubectl exec -n ckad-security capability-lab -c chown-only -- \
  stat -c '%u' /work/probe
```

This succeeds and prints `1234`. To repeat the experiment, remove `/work/probe` in each container first: after a successful ownership change, the new owner affects later file operations.

Inspect the main processes:

```bash
kubectl exec -n ckad-security capability-lab -c no-caps -- \
  sh -c 'grep -E "^(CapEff|NoNewPrivs):" /proc/1/status'
kubectl exec -n ckad-security capability-lab -c chown-only -- \
  sh -c 'grep -E "^(CapEff|NoNewPrivs):" /proc/1/status'
```

The effective capability masks are `0000000000000000` and `0000000000000001`. The low bit represents `CHOWN`. Both processes still show `NoNewPrivs: 1`: using an explicitly granted capability is different from gaining a new privilege during execution.

Avoid treating `privileged: true` as a way to fix a missing permission. Privileged mode grants all Linux capabilities and overrides protections such as seccomp and AppArmor. Select the specific permission the workload needs, subject to cluster policy. Kubernetes documents these interactions in its [Linux kernel security constraints guide](https://kubernetes.io/docs/concepts/security/linux-kernel-security-constraints/).

## Distinguish Admission Policy from Runtime Configuration

The Restricted policy requires Linux containers to drop `ALL` capabilities and permits only `NET_BIND_SERVICE` to be added back. `CHOWN` is allowed by Baseline, but not by Restricted. These are admission rules governing which configurations may be created; the runtime and kernel enforce the resulting process settings. See the [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

`manifests/rejected/05-restricted-capability.yaml` describes a non-root Pod with `allowPrivilegeEscalation: false`, `RuntimeDefault`, and `drop: ["ALL"]`, but also adds `CHOWN`. Test its admission without persisting it:

```bash
kubectl create --dry-run=server -f manifests/rejected/05-restricted-capability.yaml
kubectl get pod forbidden-capability -n ckad-security-restricted --ignore-not-found
```

The first command intentionally fails with **violates PodSecurity** and identifies the forbidden capability. The second returns no Pod. Compare that with `root-conflict`: there, admission succeeded and the kubelet refused to start the container. If this dry-run succeeds, verify that Pod Security Admission is active and that your namespace or user is not exempt.

Restricted does not require `readOnlyRootFilesystem: true`; we added it to give the application a narrower writable filesystem. Admission compliance is one input to application hardening, and application behavior still needs testing.

## Recognize the Other Controls

AppArmor and SELinux add mandatory access controls alongside user/group permissions and capabilities. AppArmor uses profiles; SELinux uses labels and policy. Kubernetes exposes them through `appArmorProfile` and `seLinuxOptions` in security contexts, but enforcement depends on node support and the available profiles or policies. This lab does not install or test custom AppArmor or SELinux configurations. The [kernel security guide](https://kubernetes.io/docs/concepts/security/linux-kernel-security-constraints/#apparmor-and-selinux-policy-based-mandatory-access-control) explains their roles.

Application security also includes the image and dependencies, Secret handling, network access and API permissions. A SecurityContext controls this workload's process environment; it does not replace a NetworkPolicy or an RBAC rule.

## Troubleshoot by the Failure Stage

| Observation | What to check |
| --- | --- |
| `Forbidden` mentioning PodSecurity during creation | Namespace enforcement labels and the rejected field |
| `CreateContainerConfigError` mentioning `runAsNonRoot` | Effective UID, image `USER` and container overrides |
| `Permission denied` while opening a file | UID, group membership, ownership and mode bits |
| `Read-only file system` | Root filesystem setting and whether the path has a writable volume mount |
| `Operation not permitted` on a privileged operation | Effective capabilities and other active kernel policies |
| Pod starts but the application exits | Logs, startup scripts, writable paths and assumptions about its user |

An error message is a clue, not a complete policy diagnosis. Our `chown` comparison changes one capability between otherwise equivalent containers, which makes the result easier to interpret.

During CKAD practice, locate the field before editing:

```bash
kubectl explain pod.spec.securityContext
kubectl explain pod.spec.containers.securityContext
kubectl explain pod.spec.containers.securityContext.capabilities
```

Then verify both configuration and behavior: inspect the admitted manifest, check events if startup fails, and use `id`, `/proc` and a small operation inside the container when it runs.

## Clean Up

Delete only the two namespaces created for this lab:

```bash
kubectl delete namespace ckad-security ckad-security-restricted
```

This removes the Pods and their `emptyDir` data. The exercises have demonstrated separate controls for process identity, writable storage, available capabilities, privilege gains and syscall filtering, plus the admission rules that decide which combinations the cluster accepts.
