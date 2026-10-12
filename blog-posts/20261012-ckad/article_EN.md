---
layout: default
title: "CKAD Preparation — Create & Consume Secrets"
date: 2026-10-12
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261012-ckad/article.webp"
summary: "Create Kubernetes Secrets from literals, files and manifests. Consume credentials through environment variables and volumes, observe rotation and subPath behavior, and diagnose missing Secrets and keys with a runnable lab."
---

## Introduction

This article continues our [*CKAD preparation series*](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html), in the **Application Environment, Configuration and Security** domain:

> Create & consume Secrets

In the [previous chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261011-ckad/article_EN.html), we defined the resources our application needs. We also used [ConfigMaps](https://supaahiro.github.io/schwifty-lab/blog-posts/20261010-ckad/article_EN.html) for ordinary settings. Credentials need a different resource: a Secret.

Our lab will give a container the same fake password through environment variables and mounted files. We will rotate it, compare what the running container sees, and repair two workloads that cannot start because their Secret references are incomplete.

## What a Secret Does

A Secret is a namespaced object for confidential data such as passwords, tokens and private keys. Ordinary Pod references resolve in the Pod's namespace. A Secret has no `spec`; its payload lives in `data` or is supplied through `stringData`. Individual Secrets have a 1 MiB size limit. `Opaque` is the general-purpose type used in this lab. See the [Secret overview](https://kubernetes.io/docs/concepts/configuration/secret/).

**Base64 is encoding, not encryption.** Anyone who can read a Secret's data can decode it. Kubernetes stores Secrets unencrypted in etcd by default unless encryption at rest is configured. Limit access through RBAC, including `list` and `watch`: these can expose values too. A caller allowed to create workloads may also obtain a Secret by mounting it. These boundaries connect to our [authentication and authorization chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261008-ckad/article_EN.html); see [good practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

Every credential below is deliberately fake and safe to publish. Real credentials belong outside public Git history, shell history, screenshots and application logs. Encoding a real password before committing it would not make it safe.

## Prerequisites and Resources

Use a disposable Kubernetes cluster with Linux nodes, `kubectl`, and permission to create a namespace, Secrets, Pods and a Deployment, and to execute commands in the lab containers. The namespace `ckad-secrets` must not already exist. Additional admission policies and quotas can affect the results.

The lab was tested on **Kubernetes 1.35.1**, including literal and file creation, environment and volume injection, non-root file access, password rotation, the Deployment rollout, immutable Secret rejection, and recovery from both missing dependencies.

Commands with `\` continuations use Bash syntax; in PowerShell, put those commands on one line. File creation and decoding examples identify their shell explicitly. Container commands use Linux tools.

```bash
git clone https://github.com/SupaaHiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261012-ckad
kubectl config current-context
```

Check that the current context is your lab cluster. Apply the numbered files as directed. `manifests/failures/` contains intentionally broken workloads, and `manifests/patches/` contains partial objects for `kubectl patch`; do not recursively apply the whole directory.

## Step 1: Create and Inspect a Secret

Start with the namespace and the declarative Secret:

```bash
kubectl apply -f manifests/01-namespace.yaml
kubectl apply -f manifests/02-secret.yaml
```

The Secret manifest contains:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-credentials
  namespace: ckad-secrets
type: Opaque
stringData:
  USERNAME: demo-user
  PASSWORD: demo-only-v1
```

`stringData` accepts ordinary strings. The API merges them into `data`, whose serialized values use base64. If both fields supply the same key, `stringData` wins. Quote numeric-looking or Boolean-looking values so they remain strings. `stringData` is an input convenience, not a field returned by a later read, and it does not work well with server-side apply. This lab uses ordinary client-side apply. See [managing Secrets with configuration files](https://kubernetes.io/docs/tasks/configmap-secret/managing-secret-using-config-file/).

Compare these views:

```bash
kubectl get secret app-credentials -n ckad-secrets
kubectl describe secret app-credentials -n ckad-secrets
kubectl get secret app-credentials -n ckad-secrets -o yaml
```

`get` reports type `Opaque` and two data entries. `describe` shows key names and byte counts. The YAML view exposes the encoded values; the apply annotation can also contain the original clear-text manifest. Treat that output as sensitive when using real credentials.

To decode our fake password in Bash:

```bash
kubectl get secret app-credentials -n ckad-secrets -o jsonpath='{.data.PASSWORD}' | base64 --decode
# demo-only-v1
```

On macOS, use `base64 -D` if `--decode` is unavailable. In PowerShell:

```powershell
$encodedPassword = kubectl get secret app-credentials -n ckad-secrets -o jsonpath='{.data.PASSWORD}'
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedPassword))
```

There is no decryption key involved. We have just reversed an encoding.

### Create from Literals or Files

For a quick imperative exercise, create a separate Secret:

```bash
kubectl create secret generic literal-credentials -n ckad-secrets \
  --from-literal=USERNAME=demo-user --from-literal=PASSWORD=demo-only-v1
```

Do not pre-encode values passed to `--from-literal` or `--from-file`; `kubectl` handles encoding. To generate YAML without creating an object, add `--dry-run=client -o yaml`. See [managing Secrets with kubectl](https://kubernetes.io/docs/tasks/configmap-secret/managing-secret-using-kubectl/).

Create a temporary file containing exactly our fake password, with no trailing newline. In Bash:

```bash
printf '%s' 'demo-file-password' > lab-password.txt
```

Or in PowerShell:

```powershell
[IO.File]::WriteAllText((Join-Path $PWD 'lab-password.txt'), 'demo-file-password')
```

Then, in either shell:

```bash
kubectl create secret generic file-credentials -n ckad-secrets \
  --from-file=PASSWORD=lab-password.txt
```

`PASSWORD` is the Secret key, and the file's entire contents become its value. Without `PASSWORD=`, the filename becomes the key. An accidental newline is part of the credential, which can explain a failed login even when the visible characters look correct. Remove the temporary file with `rm lab-password.txt` in Bash or `Remove-Item -LiteralPath lab-password.txt` in PowerShell.

## Step 2: Consume Credentials in a Container

Our Deployment runs a single BusyBox container so we can inspect exactly what Kubernetes supplies:

```bash
kubectl apply -f manifests/03-deployment.yaml
kubectl rollout status deployment/secret-reader -n ckad-secrets --timeout=120s
```

The full manifest gives the container small resource requests and limits, runs it as UID/GID 1000, and disables ServiceAccount token automounting. It needs no Kubernetes API credentials to read its injected environment or files.

### Select Keys with `secretKeyRef`

This fragment maps a Secret key to an application variable:

```yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: app-credentials
        key: PASSWORD
```

The checked-in manifest also maps `USERNAME` to `DB_USER`. Check the supplied values:

```bash
kubectl exec -n ckad-secrets deployment/secret-reader -- printenv DB_USER DB_PASSWORD
# demo-user
# demo-only-v1
```

### Import Keys with `envFrom`

The same container demonstrates the bulk form:

```yaml
envFrom:
  - prefix: IMPORTED_
    secretRef:
      name: app-credentials
```

```bash
kubectl exec -n ckad-secrets deployment/secret-reader -- printenv IMPORTED_USERNAME IMPORTED_PASSWORD
# demo-user
# demo-only-v1
```

We deliberately use both forms to compare them. For an application that needs only one credential, selecting that key avoids injecting unrelated entries. `secretKeyRef` goes under an individual `env` entry; `secretRef` goes under `envFrom`. The [credential injection task](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/) shows both forms.

### Mount Keys as Files

The Deployment also defines this volume:

```yaml
volumes:
  - name: credentials
    secret:
      secretName: app-credentials
      defaultMode: 0440
      items:
        - key: USERNAME
          path: username
        - key: PASSWORD
          path: password
```

And these mounts inside the container:

```yaml
volumeMounts:
  - name: credentials
    mountPath: /etc/demo-credentials
    readOnly: true
  - name: credentials
    mountPath: /etc/demo-password
    subPath: password
    readOnly: true
```

The first mount exposes a directory. `items` selects keys and names their files; unlisted keys are not projected. The second mount selects just the volume's `password` file using `subPath`.

`0440` is an octal YAML file mode granting owner and group read access. In JSON, use decimal `288`. The Pod's `fsGroup: 1000` makes these files readable to our non-root process. Check the actual target files, not just the symlinks:

```bash
kubectl exec -n ckad-secrets deployment/secret-reader -- sh -c 'id; ls -lnL /etc/demo-credentials/username /etc/demo-credentials/password'
kubectl exec -n ckad-secrets deployment/secret-reader -- cat /etc/demo-credentials/password
kubectl exec -n ckad-secrets deployment/secret-reader -- cat /etc/demo-password
# Both cat commands print demo-only-v1, without a trailing newline.
```

The process receives decoded bytes; it does not need to run `base64`. File permissions must agree with the process identity. See [Secret file permissions](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/#set-posix-permissions-for-secret-keys).

## Step 3: Rotate the Password and Observe the Difference

Update only the password:

```bash
kubectl patch secret app-credentials -n ckad-secrets --type=merge \
  --patch-file=manifests/patches/rotate-password.yaml
```

The patch is:

```yaml
stringData:
  PASSWORD: demo-only-v2
```

Now compare all three consumption paths. The volume projection is asynchronous, so allow time for it to refresh:

```bash
kubectl exec -n ckad-secrets deployment/secret-reader -- printenv DB_PASSWORD IMPORTED_PASSWORD
# demo-only-v1
# demo-only-v1

kubectl exec -n ckad-secrets deployment/secret-reader -- cat /etc/demo-credentials/password
# Eventually: demo-only-v2

kubectl exec -n ckad-secrets deployment/secret-reader -- cat /etc/demo-password
# demo-only-v1
```

| Consumption path | Existing container after the Secret update |
|---|---|
| `env` / `envFrom` | Keeps the values supplied at container startup |
| Ordinary Secret volume | Files are eventually updated; the application must reread them |
| Secret volume through `subPath` | Does not receive automatic updates |

The kubelet's synchronization and cache propagation determine the volume delay. A program that reads a file only once can still retain the old password after projection changes. See [Secret volume updates](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod).

Changing a Secret does not change this Deployment's Pod template, so it does not itself trigger a rollout. Recreate the workload's Pods deliberately:

```bash
kubectl rollout restart deployment/secret-reader -n ckad-secrets
kubectl rollout status deployment/secret-reader -n ckad-secrets --timeout=120s
kubectl exec -n ckad-secrets deployment/secret-reader -- printenv DB_PASSWORD IMPORTED_PASSWORD
kubectl exec -n ckad-secrets deployment/secret-reader -- cat /etc/demo-password
# All now use demo-only-v2.
```

This experiment changes the Kubernetes object only. In a real password rotation, the database or external service must accept the new credential too; plan the overlap and application reload together. Reapplying `02-secret.yaml` would restore `demo-only-v1` because that file still declares the original value.

## Step 4: Try an Immutable Secret

Create the separate, versioned Secret:

```bash
kubectl apply -f manifests/04-immutable-secret.yaml
```

Its distinguishing field is top-level `immutable: true`. Try changing its password without persisting anything:

```bash
kubectl patch secret fixed-credentials-v1 -n ckad-secrets --type=merge \
  --patch-file=manifests/patches/rotate-password.yaml --dry-run=server
```

Expect an error containing `field is immutable`. This rejection is a successful exercise. The data cannot be changed and immutability cannot be reversed. For a new credential, create a new Secret such as `fixed-credentials-v2` and update the workload reference. See [immutable Secrets](https://kubernetes.io/docs/concepts/configuration/secret/#immutable-secrets).

The main Deployment still uses the mutable `app-credentials` Secret; this immutable example does not affect the rotation experiment.

## Step 5: Diagnose Missing Keys and Missing Secrets

These files are accepted by the API server, but their containers cannot start successfully until we repair the dependencies. A successful `kubectl apply` alone does not prove a workload can consume a Secret.

### An Existing Secret with a Missing Key

```bash
kubectl apply -f manifests/failures/05-missing-key.yaml
kubectl get pod missing-key -n ckad-secrets
kubectl describe pod missing-key -n ckad-secrets
```

After the kubelet tries to start the container, expect `CreateContainerConfigError` and an event about the missing `API_TOKEN` key in `app-credentials`. Our Pod references that key with `secretKeyRef`; it is not optional.

Repair the dependency by adding the expected fake token:

```bash
kubectl patch secret app-credentials -n ckad-secrets --type=merge \
  --patch-file=manifests/patches/add-token.yaml
kubectl wait -n ckad-secrets --for=condition=Ready pod/missing-key --timeout=180s
kubectl exec -n ckad-secrets missing-key -- printenv API_TOKEN
# demo-token
```

The kubelet retries and can now start the container. The original `secret-reader` container does not gain a new `IMPORTED_API_TOKEN` environment variable while running, and its volume still projects only the two keys listed in `items`.

### A Missing Secret Volume

```bash
kubectl apply -f manifests/failures/06-missing-secret.yaml
kubectl describe pod missing-secret -n ckad-secrets
```

Expect a `FailedMount` event identifying `late-credentials` as missing. This is a volume setup failure, so it need not display the same waiting reason as the environment-variable example.

Create the dependency in the Pod's namespace:

```bash
kubectl create secret generic late-credentials -n ckad-secrets --from-literal=TOKEN=demo-late-token
kubectl wait -n ckad-secrets --for=condition=Ready pod/missing-secret --timeout=180s
kubectl exec -n ckad-secrets missing-secret -- cat /etc/late-credentials/TOKEN
# demo-late-token
```

Useful checks when a similar workload fails:

| Symptom | Check |
|---|---|
| `CreateContainerConfigError` | Secret name, key spelling and namespace in `secretKeyRef` |
| `FailedMount` | Secret existence and every key selected by volume `items` |
| `Permission denied` reading a mounted file | Process UID/GID, file mode and Pod `fsGroup` |
| Old password after an update | Environment versus volume, `subPath`, projection delay and application reload |
| Authentication fails with apparently correct text | Unexpected newline, accidental double encoding, or external service still expecting the old credential |

Required Secret dependencies prevent startup when missing. `optional: true` permits an absent dependency, but does not generate a usable credential; choose it only when the application can handle absence. See [optional Secrets](https://kubernetes.io/docs/concepts/configuration/secret/#optional-secrets).

## Recognize Other Secret Types

The main lab uses `Opaque`. Two other common tasks have dedicated creation commands.

For TLS, supply an existing PEM certificate and matching private key:

```bash
kubectl create secret tls web-tls -n ckad-secrets --cert=server.crt --key=server.key
```

This produces type `kubernetes.io/tls` with `tls.crt` and `tls.key`. It stores the pair; it does not issue a certificate or configure a server to use it. The [TLS command reference](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_secret_tls/) describes the required inputs.

For a private registry, import a Docker configuration file containing suitable registry credentials:

```bash
kubectl create secret generic registry-credentials -n ckad-secrets \
  --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson=registry-config.json
```

Reference it in a Pod's `spec`, or a Deployment's `spec.template.spec`:

```yaml
imagePullSecrets:
  - name: registry-credentials
```

The Secret must be in the same namespace. The kubelet uses it to authenticate an image pull; the setting does not inject credentials into the application. A local Docker config that only points to a credential helper is not equivalent to a file containing registry auth data. See [pulling an image from a private registry](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/).

These two commands are templates for your own certificate files and registry configuration, separate from the runnable fake-credential lab. We do not include private keys or registry credentials in the repository, or perform a private registry pull here.

## Clean-up

Remove only the namespace created for this exercise:

```bash
kubectl delete namespace ckad-secrets
```

This removes the lab Deployment, Pods and Secrets, including the optional examples if you created them. If you still have `lab-password.txt`, remove that local temporary file too.

## Wrapping Up: What We've Covered

We created Secrets through manifests, literals and files, mapped keys to environment variables, and mounted decoded values as files. Rotating one password exposed the different update behavior of environment variables, ordinary volumes and `subPath` mounts. We also tested an immutable Secret and repaired missing dependencies by reading Pod events.

For CKAD practice, repeat the lab from a clean namespace and predict each result before inspecting it. Next, we will look more closely at **ServiceAccounts**, the identities used by workloads when they communicate with the Kubernetes API.
