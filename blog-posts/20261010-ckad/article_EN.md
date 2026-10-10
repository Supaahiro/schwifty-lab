---
layout: default
title: "CKAD Preparation — Understand ConfigMaps"
date: 2026-10-10
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261010-ckad/article.webp"
summary: "Create ConfigMaps from literals and files, inject configuration through environment variables and volumes, and compare update behavior with subPath mounts. Practice immutable ConfigMaps and diagnose missing keys with a runnable Kubernetes lab."
---

## Introduction

This article continues our [*CKAD preparation series*](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html), in the **Application Environment, Configuration and Security** domain:

> Understand ConfigMaps

In the [previous chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261009-ckad/article_EN.html), we controlled the resources an application can consume. Now we will supply the settings it needs without rebuilding its container image.

Our lab uses the same configuration in several ways. We will change it while a container runs, inspect which values change, and then recreate the Pod to compare the results. That experiment answers a common troubleshooting question: why does Kubernetes show the new configuration while the application still uses the old one?

## What a ConfigMap Contains

A ConfigMap stores non-confidential configuration as key/value pairs. It is namespaced, and ordinary Pod references resolve within the Pod's namespace. Use Secrets for credentials; ConfigMaps provide no secrecy.

Unlike a Deployment, a ConfigMap has no `spec`. Its `data` values are UTF-8 strings; `binaryData` contains base64-encoded binary values. Keys may contain letters, digits, `.`, `-` and `_`, and cannot appear in both fields. The total stored data must fit within 1 MiB. See the [ConfigMap concept documentation](https://kubernetes.io/docs/concepts/configuration/configmap/).

This is the first object in `manifests/02-configmaps.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-settings
  namespace: ckad-configmaps
data:
  APP_MODE: lab
  LOG_LEVEL: info
  RETRY_COUNT: "3"
```

Quote values such as `"3"` or `"true"` when writing YAML so that the parser preserves them as strings. Kubernetes does not interpret our `RETRY_COUNT` setting; the application decides what that string means.

We keep a second ConfigMap, `app-files`, for a complete properties file:

```yaml
data:
  application.properties: |
    greeting=Hello from a ConfigMap
    color=blue
```

Here `application.properties` is **one key**, whose value is the entire multiline string. `greeting` and `color` are properties inside that string, not separate ConfigMap keys.

## Prerequisites and Resources

Use a disposable Kubernetes cluster with Linux nodes, `kubectl`, and permission to create a namespace, ConfigMaps, Pods and a Deployment. The namespace `ckad-configmaps` must not already exist. Additional admission policies or injected containers can change the lab results.

The manifests and commands were tested on **Kubernetes 1.35.1**, including the delayed volume refresh, the unchanged `subPath` mount, the rollout, the rejected immutable update and recovery from a missing key.

Commands use `kubectl` in full. Commands with `\` continuations use Bash syntax; in PowerShell, put them on one line. Commands passed to `sh` run inside the Linux container.

```bash
git clone https://github.com/SupaaHiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261010-ckad
kubectl config current-context
```

Verify that the context points to your lab cluster. Apply the numbered files in the order shown below: some later files change earlier objects, and the `rejected/` example is supposed to fail. The `patches/` directory contains a patch, not a standalone resource.

## Step 1: Create and Inspect ConfigMaps

```bash
kubectl apply -f manifests/01-namespace.yaml
kubectl apply -f manifests/02-configmaps.yaml
kubectl get configmaps -n ckad-configmaps
kubectl describe configmap app-settings -n ckad-configmaps
kubectl get configmap app-files -n ckad-configmaps -o yaml
```

You should find `app-settings` with three data entries and `app-files` with one. Your namespace may also contain the automatically provided `kube-root-ca.crt` ConfigMap.

For a quick imperative exercise, create three additional objects:

```bash
kubectl create configmap literal-demo -n ckad-configmaps \
  --from-literal=COLOR=blue --from-literal=RETRIES=3

kubectl create configmap file-demo -n ckad-configmaps \
  --from-file=application.properties=src/application.properties

kubectl create configmap envfile-demo -n ckad-configmaps \
  --from-env-file=src/demo.env

kubectl get configmap literal-demo file-demo envfile-demo -n ckad-configmaps -o yaml
```

Compare the resulting `data` maps:

| Input | Result in our example |
|---|---|
| `--from-literal` | Two keys: `COLOR` and `RETRIES` |
| `--from-file=key=path` | One key, `application.properties`, containing the file's text |
| `--from-env-file` | Two keys: `EXAMPLE_MODE` and `EXAMPLE_RETRIES` |

Using `--from-file=src/demo.env` instead would store the whole env file under a single key. `--from-env-file` parses `KEY=value` lines; quotes are preserved as part of the value, so our sample file does not quote them. A directory passed to `--from-file` supplies eligible regular files, without recursively reading subdirectories. The official [ConfigMap task guide](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/) explains these creation modes.

To generate YAML without creating another object:

```bash
kubectl create configmap generated-demo -n ckad-configmaps \
  --from-literal=APP_MODE=practice --dry-run=client -o yaml
```

For repeatable imperative updates, the same pattern can feed `kubectl apply`:

```bash
kubectl create configmap generated-demo -n ckad-configmaps \
  --from-literal=APP_MODE=practice --dry-run=client -o yaml | kubectl apply -f -
```

## Step 2: Read Configuration from the Environment

Our Deployment combines two environment mechanisms:

```yaml
envFrom:
  - configMapRef:
      name: app-settings
env:
  - name: MODE
    valueFrom:
      configMapKeyRef:
        name: app-settings
        key: APP_MODE
  - name: LOG_LEVEL
    value: warning
```

`envFrom` imports the entries together. `configMapKeyRef` selects a single entry and lets us give the environment variable a different name. The explicit `LOG_LEVEL` entry takes precedence over the value imported by `envFrom`. With several `envFrom` sources, the last source wins for duplicate names; explicit `env` entries take precedence over them. See the [Container API reference](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/#Container).

Apply the full Deployment and inspect the running container:

```bash
kubectl apply -f manifests/03-deployment.yaml
kubectl rollout status deployment/config-demo -n ckad-configmaps --timeout=120s
kubectl exec -n ckad-configmaps deployment/config-demo -- printenv APP_MODE MODE LOG_LEVEL RETRY_COUNT
```

Expected values, in that order:

```text
lab
lab
warning
3
```

Notice that the explicit override already makes `LOG_LEVEL` differ from `app-settings`. Reading only the ConfigMap is insufficient to reconstruct a container's environment.

Choose portable environment variable names such as `APP_MODE`. ConfigMap keys containing punctuation may be awkward for shells and application libraries even when your Kubernetes version accepts them as environment names. Map a particular key to a suitable name with `configMapKeyRef`, or consume a properties file through a volume.

## Step 3: Mount Configuration as Files

The same Deployment declares this volume:

```yaml
volumes:
  - name: config
    configMap:
      name: app-files
      items:
        - key: application.properties
          path: settings/application.properties
```

`items` selects the key to project and gives its file a relative path. The container mounts the volume twice:

```yaml
volumeMounts:
  - name: config
    mountPath: /etc/config
    readOnly: true
  - name: config
    mountPath: /etc/app.properties
    subPath: settings/application.properties
    readOnly: true
```

Read both paths:

```bash
kubectl exec -n ckad-configmaps deployment/config-demo -- cat /etc/config/settings/application.properties
kubectl exec -n ckad-configmaps deployment/config-demo -- cat /etc/app.properties
```

Both initially contain:

```properties
greeting=Hello from a ConfigMap
color=blue
```

The first mount exposes a directory tree. The second exposes just the selected file at `/etc/app.properties`, leaving the other files under `/etc` visible. Mounting a whole volume over an existing directory hides that directory's original contents for the container. This makes mounting a ConfigMap over a populated configuration directory a choice to check carefully. See [Volumes](https://kubernetes.io/docs/concepts/storage/volumes/#configmap).

These configuration files are read-only. If an application must rewrite its configuration, it can copy the input into a writable volume such as `emptyDir`; that copy then needs its own update strategy.

Our Deployment has `automountServiceAccountToken: false` and no RoleBinding. Environment injection and volume projection are performed by Kubernetes. They do not require the application to call the API. An application that instead reads or watches ConfigMaps through the API needs credentials and appropriate RBAC permissions.

## Step 4: Pass a Setting as a Command Argument

The short-lived Pod in `manifests/04-args-pod.yaml` reads `APP_MODE` through `configMapKeyRef`, then runs:

```yaml
command: ["/bin/echo"]
args: ["Mode=$(APP_MODE)"]
```

```bash
kubectl apply -f manifests/04-args-pod.yaml
kubectl wait -n ckad-configmaps --for=jsonpath='{.status.phase}'=Succeeded pod/config-args --timeout=120s
kubectl logs -n ckad-configmaps config-args
```

Expected output:

```text
Mode=lab
```

Kubernetes expands `$(APP_MODE)` in the container's `command` and `args`. No shell is running in this example, so `$APP_MODE` would not be an equivalent expression here. See [Define a Command and Arguments for a Container](https://kubernetes.io/docs/tasks/inject-data-application/define-command-argument-container/).

## Step 5: Change the ConfigMaps While the Pod Runs

Now apply new values to **both** ConfigMaps:

```bash
kubectl apply -f manifests/05-updated-configmaps.yaml
kubectl get configmap app-settings app-files -n ckad-configmaps -o yaml
kubectl exec -n ckad-configmaps deployment/config-demo -- printenv APP_MODE MODE LOG_LEVEL RETRY_COUNT
```

The API now contains `APP_MODE: production` and `RETRY_COUNT: "5"`, but the running container still prints `lab`, `lab`, `warning`, `3`.

Check the directory mount again:

```bash
kubectl exec -n ckad-configmaps deployment/config-demo -- cat /etc/config/settings/application.properties
```

It eventually changes to:

```properties
greeting=Hello from an updated ConfigMap
color=green
```

Propagation is asynchronous: retry the command if you still see blue. The delay depends on kubelet synchronization and its ConfigMap change-detection strategy. Do not assume an immediate refresh or a universal fixed timeout. [Mounted ConfigMap updates](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically) describes the mechanism.

Now read the `subPath` mount:

```bash
kubectl exec -n ckad-configmaps deployment/config-demo -- cat /etc/app.properties
```

It still contains `color=blue`. Our comparison is:

| Consumption method | Existing container after the update |
|---|---|
| `envFrom` / `configMapKeyRef` | Keeps its original environment |
| Environment-expanded command argument | Does not rerun the command |
| Normal ConfigMap volume mount | File contents eventually change |
| ConfigMap mounted with `subPath` | Mounted file does not receive the update |

Changing a ConfigMap alone does not change this Deployment's Pod template, so it does not trigger a rollout. Explicitly recreate its Pods:

```bash
kubectl rollout restart deployment/config-demo -n ckad-configmaps
kubectl rollout status deployment/config-demo -n ckad-configmaps --timeout=120s
kubectl exec -n ckad-configmaps deployment/config-demo -- printenv APP_MODE MODE LOG_LEVEL RETRY_COUNT
kubectl exec -n ckad-configmaps deployment/config-demo -- cat /etc/app.properties
```

The new container prints `production`, `production`, `warning`, `5`, and the `subPath` file is now green too. `LOG_LEVEL` remains `warning` because we explicitly set it in the Pod template.

A refreshed file does not prove that an application has reloaded its settings. Our `cat` commands open the file each time; a real server might read it once at startup or keep an old file descriptor open. Choose a restart or reload mechanism that the application actually supports. The official [updating configuration tutorial](https://kubernetes.io/docs/tutorials/configuration/updating-configuration-via-a-configmap/) explores these cases further.

## Step 6: Make a ConfigMap Immutable

Create the separate `release-config-v1` object:

```bash
kubectl apply -f manifests/06-immutable-configmap.yaml
```

Its relevant fields are:

```yaml
immutable: true
data:
  APP_MODE: stable
```

Try the intentionally invalid data update without storing it:

```bash
kubectl apply --dry-run=server -f manifests/rejected/07-immutable-update.yaml
```

Expect a rejection containing `field is immutable`. The lab succeeds when this request fails, and the stored value remains `stable`:

```bash
kubectl get configmap release-config-v1 -n ckad-configmaps -o yaml
```

After setting `immutable: true`, you cannot change `data` or `binaryData`, or switch immutability off. Metadata remains editable. To release different data, create another ConfigMap, such as `release-config-v2`, then update the workload's reference to it. For a Deployment, that reference change modifies the Pod template and causes a rollout. Keep the older object for as long as workloads or rollback revisions need it. See [immutable ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/#immutable-configmaps).

The [earlier Kustomize chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20260103-ckad/article_EN.html) offers a related workflow: `configMapGenerator` normally adds a content hash to the generated name and updates recognized workload references. Changed configuration can therefore produce a changed Pod template. Old generated ConfigMaps still need a deliberate cleanup policy; generating a new name does not by itself delete them.

## Step 7: Diagnose a Required Key That Does Not Exist

Our final Pod references the existing `app-settings` object but asks for `REQUIRED_MODE`, which we have not defined:

```bash
kubectl apply -f manifests/08-missing-key-pod.yaml
kubectl get pod missing-key -n ckad-configmaps
kubectl describe pod missing-key -n ckad-configmaps
```

After scheduling and image preparation, expect `CreateContainerConfigError`. In the events, look for a message identifying the missing `REQUIRED_MODE` key. The API accepted the Pod; the kubelet cannot construct the container's required environment. An empty log is unsurprising because the container has not started.

Supply the key with the provided merge patch:

```bash
kubectl patch configmap app-settings -n ckad-configmaps --type=merge \
  --patch-file=manifests/patches/09-required-key.yaml
kubectl wait -n ckad-configmaps --for=condition=Ready pod/missing-key --timeout=120s
kubectl exec -n ckad-configmaps missing-key -- printenv REQUIRED_MODE
```

Expected output:

```text
recovered
```

The kubelet retries and the same Pod can start once its prerequisite exists. This differs from changing the environment of a container that is already running.

A `configMapKeyRef` can set `optional: true`. If that object or key is absent, Kubernetes allows startup without supplying that environment variable; your application must handle the absence. Required volume references can instead prevent mounting, with `FailedMount` events. Optional volume references allow missing configuration, and missing selected keys produce no corresponding files. Use optional references when absent configuration is an intentional application case. See [optional ConfigMap references](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/#optional-references).

## Troubleshooting Checklist

| Observation | What to inspect |
|---|---|
| `configmap ... not found` | Exact object name and the Pod's namespace |
| `CreateContainerConfigError` | Required `env` / `envFrom` references and Pod events |
| `FailedMount` | ConfigMap volume name, selected `items` keys and events |
| New API value, old environment | Pod creation time and whether a rollout occurred |
| Directory file changes, single file does not | Whether the latter uses `subPath` |
| File changes, application behavior does not | Application reload behavior and open file handles |
| Environment differs from the ConfigMap | Explicit `env` overrides and ordering of `envFrom` sources |
| API rejects a ConfigMap edit | `immutable`, string types and object size |

For CKAD practice, recreate the lab with different names and a different namespace. Before each command, predict whether it changes the API object, a projected file, or a running process's settings.

## Clean-up

Delete only the namespace created for this exercise:

```bash
kubectl delete namespace ckad-configmaps
```

This removes the Deployment, its Pods, both standalone Pods, and all the ConfigMaps created during the lab. The rejected immutable update was never stored.
