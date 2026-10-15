---
layout: default
title: "CKAD Preparation — Understand ServiceAccounts"
date: 2026-10-15
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261015-ckad/article.webp"
summary: "Assign Kubernetes identities to workloads with ServiceAccounts. Grant access to one ConfigMap, compare automatic and explicit token projection, request short-lived tokens, and change a Deployment's identity in a runnable lab."
---

## Introduction

This article continues our [*CKAD preparation series*](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html), in the **Application Environment, Configuration and Security** domain:

> Understand ServiceAccounts

The [previous chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261012-ckad/article_EN.html) supplied application credentials through Secrets. A workload that calls the Kubernetes API also needs an identity. In our [authentication and authorization chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261008-ckad/article_EN.html), we briefly used a ServiceAccount for that purpose. Now we will examine how Pods select that identity and receive its credentials.

Our application will read one ConfigMap directly from the API. We will grant precisely that access, compare Pods with and without an automatically mounted token, configure an explicit projection, and change the identity of a Deployment.

## Identity, Credentials and Permissions

A ServiceAccount represents a non-human identity in Kubernetes. It is a namespaced API object: `config-reader` in one namespace is a different identity from `config-reader` in another. RBAC can still grant that identity access in other namespaces. Ordinary human users are usually managed outside the Kubernetes API. See the [ServiceAccount overview](https://kubernetes.io/docs/concepts/security/service-accounts/).

Three pieces work together:

| Piece | What it answers | Our example |
|---|---|---|
| ServiceAccount | Which identity does this workload use? | `config-reader` |
| Token | How can a client authenticate as that identity? | A token projected into a Pod |
| RBAC Role and RoleBinding | Which API requests may that identity make? | Get the `demo-settings` ConfigMap |

Creating a ServiceAccount does not grant application-resource permissions. Mounting its token does not grant them either. Conversely, disabling token automounting does not revoke permissions already granted to that identity.

This identity is also separate from the Linux UID inside a container. Our examples run as UID 1000, but their Kubernetes API identity is determined by the ServiceAccount credential used in the request.

## Prerequisites and Resources

Use a disposable Kubernetes cluster with Linux nodes and RBAC enabled, plus a compatible `kubectl` supporting `create token`. You need permission to create namespaces, ConfigMaps, ServiceAccounts, Roles, RoleBindings, Pods and Deployments; execute commands in Pods; request ServiceAccount tokens; and impersonate ServiceAccounts for the `auth can-i` checks. A local lab administrator context is suitable.

The namespace `ckad-serviceaccounts` must not already exist. The lab expects the usual ServiceAccount admission and projected-token behavior of a modern Kubernetes cluster. Additional policies, injected containers, or existing broad RBAC grants can change the results.

The lab was tested on **Kubernetes 1.35.1**, including identity defaulting, automount precedence, allowed and denied API requests, explicit token projection, TokenRequest authentication, Deployment identity changes, and admission rejection of a missing ServiceAccount.

Commands with `\` continuations use Bash syntax; in PowerShell, put those commands on one line. Commands shown after entering a container shell use `sh`. We never need to print a live token or disable TLS certificate verification.

```bash
git clone https://github.com/SupaaHiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261015-ckad
kubectl config current-context
```

Confirm that the context points to your lab cluster. Apply the numbered manifests in order. The `manifests/rejected/` directory contains an intentional admission failure, to submit only when instructed.

## Step 1: Observe the Default Identity

Create the namespace and a sample ConfigMap:

```bash
kubectl apply -f manifests/01-lab-setup.yaml
kubectl wait -n ckad-serviceaccounts --for=create serviceaccount/default --timeout=30s
kubectl get serviceaccounts -n ckad-serviceaccounts
```

The namespace receives a ServiceAccount named `default`. If you do not select another account, the ServiceAccount admission controller assigns that namespace's default account to new Pods. Our `02-default-pod.yaml` deliberately omits `serviceAccountName`:

```bash
kubectl apply -f manifests/02-default-pod.yaml
kubectl wait -n ckad-serviceaccounts --for=condition=Ready pod/default-identity --timeout=120s
kubectl get pod default-identity -n ckad-serviceaccounts -o jsonpath='{.spec.serviceAccountName}'
# default
```

Inspect the admitted Pod and the credential directory:

```bash
kubectl get pod default-identity -n ckad-serviceaccounts -o yaml
kubectl exec -n ckad-serviceaccounts default-identity -- ls /var/run/secrets/kubernetes.io/serviceaccount
# ca.crt  namespace  token
```

Look for a projected volume with a generated name beginning `kube-api-access-`. It supplies the token, the API server's CA certificate and the namespace. The token authenticates the request, while the CA certificate lets the client verify the server. The namespace file is ordinary context, not a credential.

Modern clusters use the TokenRequest API to obtain Pod-bound tokens, which the kubelet refreshes. The projected token is not a token Secret listed on the ServiceAccount. In Kubernetes 1.24 and later, creating a ServiceAccount no longer automatically creates the legacy long-lived token Secret. A `SECRETS` count of zero is therefore normal. See [ServiceAccount administration](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/).

The default identity normally has no application-resource permissions unless bindings grant them; standard authenticated discovery permissions are a separate matter. It is not a namespace administrator.

## Step 2: Select a Dedicated ServiceAccount

Create `manifests/03-serviceaccount.yaml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: config-reader
  namespace: ckad-serviceaccounts
automountServiceAccountToken: false
```

```bash
kubectl apply -f manifests/03-serviceaccount.yaml
kubectl get serviceaccount config-reader -n ckad-serviceaccounts -o yaml
```

`automountServiceAccountToken` is top-level on a ServiceAccount; it is not under `spec`. We disable automatic credential mounting for Pods that inherit this setting, then opt in explicitly for the API client.

For quick manifest generation, the imperative equivalent starts with:

```bash
kubectl create serviceaccount config-reader -n ckad-serviceaccounts --dry-run=client -o yaml
```

That prints a skeleton without creating another object. Add the desired fields before applying it.

The Deployment in `manifests/04-api-reader.yaml` selects the account inside its **Pod template**:

```yaml
spec:
  template:
    spec:
      serviceAccountName: config-reader
      automountServiceAccountToken: true
```

The Pod-level value overrides the ServiceAccount-level value. A ServiceAccount name in a Pod reference is resolved within the Pod's namespace. See [configuring ServiceAccounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

```bash
kubectl apply -f manifests/04-api-reader.yaml
kubectl rollout status deployment/api-reader -n ckad-serviceaccounts --timeout=120s
kubectl get pods -n ckad-serviceaccounts -l app=api-reader -o custom-columns=NAME:.metadata.name,SA:.spec.serviceAccountName
kubectl exec -n ckad-serviceaccounts deployment/api-reader -- ls /var/run/secrets/kubernetes.io/serviceaccount
```

The Pod uses `config-reader` and has the credential files. The full manifest also supplies resource requests and limits, a non-root UID and a read-only root filesystem.

Before granting application access, check:

```bash
kubectl auth can-i get configmap/demo-settings -n ckad-serviceaccounts \
  --as=system:serviceaccount:ckad-serviceaccounts:config-reader
# no
```

The authenticated username follows `system:serviceaccount:<namespace>:<name>`. ServiceAccount authentication also supplies groups such as `system:serviceaccounts` and the namespace's ServiceAccount group. Here we bind the account directly; an impersonation check using only `--as` does not reproduce every group-based authorization context. See [ServiceAccount authentication](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#service-account-tokens).

`--as` requires impersonation permission in your current context. It checks authorization as the specified identity; it does not test a token. We will make a real authenticated request next.

## Step 3: Grant Access to One ConfigMap

The Role in `manifests/05-reader-rbac.yaml` contains:

```yaml
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["demo-settings"]
    verbs: ["get"]
```

The RoleBinding selects our account:

```yaml
subjects:
  - kind: ServiceAccount
    name: config-reader
    namespace: ckad-serviceaccounts
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: read-demo-settings
```

Both objects live in `ckad-serviceaccounts`. This rule allows a named read, not listing all ConfigMaps or reading Secrets. `resourceNames` narrows the objects to which the rule applies. See [RBAC resource references](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources).

We need this grant because the application calls the API itself. Supplying a ConfigMap or Secret through a declared Pod volume is handled by the kubelet and does not require granting that same read permission to the Pod's ServiceAccount.

```bash
kubectl apply -f manifests/05-reader-rbac.yaml
kubectl auth can-i get configmap/demo-settings -n ckad-serviceaccounts \
  --as=system:serviceaccount:ckad-serviceaccounts:config-reader
# yes
kubectl auth can-i list configmaps -n ckad-serviceaccounts \
  --as=system:serviceaccount:ckad-serviceaccounts:config-reader
# no
kubectl auth can-i get secrets -n ckad-serviceaccounts \
  --as=system:serviceaccount:ckad-serviceaccounts:config-reader
# no
```

Open a shell in the application container:

```bash
kubectl exec -it -n ckad-serviceaccounts deployment/api-reader -- sh
```

Inside the container, define a small helper that rereads the token for each request:

```sh
SA_DIR=/var/run/secrets/kubernetes.io/serviceaccount
NAMESPACE=$(cat "$SA_DIR/namespace")
API=https://kubernetes.default.svc

api_get() {
  curl -sS --max-time 10 --cacert "$SA_DIR/ca.crt" \
    -H "Authorization: Bearer $(cat "$SA_DIR/token")" \
    -o /dev/null -w 'HTTP %{http_code}\n' \
    "$API/api/v1/namespaces/$NAMESPACE/$1"
}

api_get configmaps/demo-settings
# HTTP 200
api_get configmaps
# HTTP 403
api_get secrets
# HTTP 403

exit
```

Your kubeconfig identity authorizes `kubectl exec`; the requests from inside the container authenticate with the mounted ServiceAccount token. `curl` does not inherit the administrator credentials from your terminal. Remove `-o /dev/null` if you want to inspect the ConfigMap or the API's denial message.

The HTTP 200 followed by HTTP 403 results are the expected outcome: the client authenticates successfully, but its rights are limited. In this helper, `curl` reports the HTTP code without using `--fail`, so a 403 is not itself a shell-command failure.

## Step 4: Keep the Identity Without Automounting a Token

The `no-api` Pod selects the same account but omits a Pod-level automount override:

```yaml
spec:
  serviceAccountName: config-reader
```

It inherits `automountServiceAccountToken: false` from the ServiceAccount:

```bash
kubectl apply -f manifests/06-no-api-pod.yaml
kubectl wait -n ckad-serviceaccounts --for=condition=Ready pod/no-api --timeout=120s
kubectl get pod no-api -n ckad-serviceaccounts -o jsonpath='{.spec.serviceAccountName}'
# config-reader
kubectl exec -n ckad-serviceaccounts no-api -- sh -c 'test ! -e /var/run/secrets/kubernetes.io/serviceaccount/token && echo "No automatic token mount"'
# No automatic token mount
```

The account's RBAC grant still exists. The API reader from Step 3 still works because that Pod explicitly enables automounting. The two Pods share an identity selection, but do not have the same mounted credentials.

| ServiceAccount setting | Pod setting | Automatic credential mount |
|---|---|---|
| Unset | Unset | Enabled by default |
| `false` | Unset | Disabled |
| `false` | `true` | Enabled |
| `true` or unset | `false` | Disabled |

This setting controls automatic API credential injection. It does not block network access, revoke the identity, prevent an explicit token projection, or remove credentials supplied by another mechanism. Changes to the ServiceAccount's automount setting also do not rewrite already-created Pods.

## Step 5: Project a Token Explicitly

Sometimes an application needs credentials at a chosen path, with an explicit lifetime or audience. `manifests/07-projected-token-pod.yaml` keeps automatic mounting disabled and defines its own projected volume:

```yaml
volumes:
  - name: api-credentials
    projected:
      sources:
        - serviceAccountToken:
            expirationSeconds: 600
            path: token
        - configMap:
            name: kube-root-ca.crt
            items:
              - key: ca.crt
                path: ca.crt
        - downwardAPI:
            items:
              - path: namespace
                fieldRef:
                  fieldPath: metadata.namespace
```

The container mounts it read-only at `/var/run/ckad-api`. The three sources supply the credential, CA and namespace separately; projecting a token alone would not supply the other two files.

The omitted `audience` defaults to the API server audience. `600` requests a ten-minute lifetime, the minimum for this projection. An audience identifies the intended recipient, not a set of RBAC permissions. A custom audience must match what the receiving service accepts; an arbitrary string does not make the token valid for the Kubernetes API. See [ServiceAccount token projection](https://kubernetes.io/docs/concepts/storage/projected-volumes/#serviceaccounttoken-projected-volumes).

```bash
kubectl apply -f manifests/07-projected-token-pod.yaml
kubectl wait -n ckad-serviceaccounts --for=condition=Ready pod/projected-client --timeout=120s
kubectl exec -n ckad-serviceaccounts projected-client -- ls /var/run/ckad-api
# ca.crt  namespace  token
kubectl exec -it -n ckad-serviceaccounts projected-client -- sh
```

Inside this container:

```sh
SA_DIR=/var/run/ckad-api
NAMESPACE=$(cat "$SA_DIR/namespace")
curl -sS --max-time 10 --cacert "$SA_DIR/ca.crt" \
  -H "Authorization: Bearer $(cat "$SA_DIR/token")" \
  -o /dev/null -w 'HTTP %{http_code}\n' \
  "https://kubernetes.default.svc/api/v1/namespaces/$NAMESPACE/configmaps/demo-settings"
# HTTP 200
exit
```

The kubelet obtains and refreshes projected tokens. Applications must reread the token file as it changes; copying its contents into a permanent environment variable defeats that refresh. Avoid `subPath` for this mount because projected-volume updates do not reach it. Pod-bound tokens are tied to the Pod and ServiceAccount lifecycle. See the [bound token mechanism](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/#bound-service-account-token-volume-mechanism).

## Step 6: Request a Short-lived Token with kubectl

For a client outside a Pod, `kubectl create token` uses the TokenRequest API. Capture the result without printing it. In Bash:

```bash
service_account_token=$(kubectl create token config-reader -n ckad-serviceaccounts --duration=10m)
# Use the variable with the intended client, then remove the shell variable.
unset service_account_token
```

Or in PowerShell:

```powershell
$serviceAccountToken = kubectl create token config-reader -n ckad-serviceaccounts --duration=10m
# Use the variable with the intended client, then remove the shell variable.
Remove-Variable serviceAccountToken
```

`--duration` is a request; the server can issue a different lifetime. Without `--audience`, the request targets the Kubernetes API server. The CLI also supports explicit audiences and binding a token to an existing Pod, Secret or Node. Those options do not grant new permissions. The caller needs permission to create the `serviceaccounts/token` subresource. See the [create token reference](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_token/).

A token requested this way is not automatically refreshed by your shell, and without binding flags it is not tied to one particular Pod. Unsetting a variable removes your local reference; it does **not** revoke the token. Do not commit it or paste it into logs. For ordinary in-cluster clients, use the kubelet-managed projection and a client library that reloads the file.

Long-lived Secrets of type `kubernetes.io/service-account-token` still exist for compatibility, but are not the normal source of credentials for these Pods. An ordinary application Secret from the previous chapter is not automatically a ServiceAccount token.

## Step 7: Change a Deployment's Identity

`serviceAccountName` belongs to the Pod specification. You cannot replace the identity of an existing Pod by editing that field; change the workload template and let the controller create replacement Pods.

Record the current Pod name, then select the default account:

```bash
kubectl get pods -n ckad-serviceaccounts -l app=api-reader
kubectl set serviceaccount deployment api-reader default -n ckad-serviceaccounts
kubectl rollout status deployment/api-reader -n ckad-serviceaccounts --timeout=120s
kubectl get pods -n ckad-serviceaccounts -l app=api-reader -o custom-columns=NAME:.metadata.name,SA:.spec.serviceAccountName
```

The replacement Pod uses `default`. Its template still sets `automountServiceAccountToken: true`, so it receives a token for that identity. Open a new shell in `deployment/api-reader` and repeat the named ConfigMap request from Step 3: expect **HTTP 403**, because our RoleBinding names `config-reader`, not `default`.

Restore the intended account:

```bash
kubectl set serviceaccount deployment api-reader config-reader -n ckad-serviceaccounts
kubectl rollout status deployment/api-reader -n ckad-serviceaccounts --timeout=120s
```

Repeat the request from a new container shell: it returns **HTTP 200** again. The [set serviceaccount command](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_set/kubectl_set_serviceaccount/) updates workload Pod templates. For declarative management, make the same choice in the manifest; our checked-in Deployment already declares `config-reader`.

## Troubleshooting the Identity Chain

Submit the deliberately missing account reference without storing the Pod:

```bash
kubectl create --dry-run=server -f manifests/rejected/08-missing-serviceaccount.yaml
```

Expect an error identifying ServiceAccount `does-not-exist` as not found. This is the intended result. Unlike the missing application Secret in the previous chapter, a missing ServiceAccount is rejected during admission; there is no running Pod to inspect. For a Deployment with that reference, inspect ReplicaSet events when Pod creation fails.

| Symptom | Check |
|---|---|
| Workload uses `default` unexpectedly | `spec.template.spec.serviceAccountName` in the workload and the admitted Pod's `spec.serviceAccountName` |
| No token file | Pod override, ServiceAccount automount setting, and explicit projections or custom paths |
| `SECRETS` is zero on the account | Normal for modern projected tokens; inspect the Pod's volume instead |
| HTTP 401 | Token validity, expiry and audience; Pod or ServiceAccount deletion |
| HTTP 403 | Authenticated identity, requested verb/resource/name, RoleBinding subject and namespace |
| TLS or connection failure | CA trust, API endpoint, DNS and network access before diagnosing RBAC |
| `auth can-i --as` itself is forbidden | Your kubeconfig identity lacks impersonation permission |

ServiceAccounts can also provide `imagePullSecrets` defaults for new Pods. That is a reference to registry credentials, separate from the API bearer token and its RBAC grants. The registry Secret must be in the Pod's namespace; the previous chapter covers its format. Cloud workload identity likewise requires a provider-specific trust configuration, not merely a Kubernetes RoleBinding.

## Clean-up

Delete only the namespace created for this lab:

```bash
kubectl delete namespace ckad-serviceaccounts
```

This removes the lab workloads, ServiceAccounts, namespaced RBAC resources and ConfigMap. No ClusterRole or ClusterRoleBinding was created, and the rejected Pod was never stored.

## Wrapping Up: What We've Covered

We selected a dedicated workload identity, granted it access to one ConfigMap, and verified both allowed and denied API calls. We then separated identity selection from token mounting, supplied an explicit projection, requested a short-lived token, and observed the new Pods created when a Deployment changed accounts.

For CKAD practice, explain the chosen account, credential source and required permission before running each API request. Next, we will explore **application security**, including SecurityContexts and Linux capabilities.
