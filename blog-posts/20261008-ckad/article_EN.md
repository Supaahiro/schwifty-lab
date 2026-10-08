---
layout: default
title: "CKAD Preparation — Understand Authentication, Authorization and Admission Control"
date: 2026-10-08
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261008-ckad/article.webp"
summary: "Follow a Kubernetes API request through authentication, RBAC authorization and admission control. Use a ServiceAccount, test namespace-scoped permissions, and see why Pod Security can reject a request that RBAC allows."
---

## Introduction

This article continues our [*CKAD preparation series*](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html), in the **Application Environment, Configuration and Security** domain. This time we cover:

> Understand authentication, authorization and admission control

In the [previous article](https://supaahiro.github.io/schwifty-lab/blog-posts/20260720-ckad/article_EN.html), we gave an operator permission to watch custom resources and update their status. Those RBAC rules answered one question: what is the operator allowed to do?

There are two other questions around that decision. How does the API server know which operator is calling? And if that identity can create a Pod, does Kubernetes accept *any* Pod it submits?

We'll follow those three checks with a small lab: create an identity, grant it access to Pods in one namespace, call the API with its credentials, then submit a Pod that is authorized but rejected by admission control.

## Three Checks for an API Request

For a request that creates a Kubernetes object, the access-control sequence looks like this:

```mermaid
flowchart LR
  Client["kubectl / application"] --> AuthN["Authentication<br/>Who is calling?"]
  AuthN --> AuthZ["Authorization<br/>May they do this?"]
  AuthZ --> Mutate["Mutating admission<br/>Adjust the object"]
  Mutate --> Validate["Validating admission<br/>Check policy"]
  Validate --> Store["Persist the object"]
```

This is the access-control view; schema validation and other API processing also happen. A failed check stops the request. Read operations such as `get`, `list` and `watch` still require authorization, but bypass admission control. See the official [authorization overview](https://kubernetes.io/docs/reference/access-authn-authz/authorization/) and [admission control reference](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/).

| Stage | Question | Example |
|---|---|---|
| Authentication | Who is making this request? | Verify a ServiceAccount token or client certificate |
| Authorization | Can this identity perform this verb on this resource here? | Allow listing Pods in `ckad-access` |
| Admission control | Does this operation satisfy the configured policies? | Reject a Pod that requests privileged mode |

These checks govern access to the **Kubernetes API**. They don't implement login for your web application or decide whether one Pod can connect to another over the network.

## Prerequisites

Use a disposable Kubernetes cluster with Linux nodes, RBAC and the built-in Pod Security admission controller enabled, on Kubernetes 1.25 or newer. You'll need `kubectl`, permission to create namespaces and RBAC resources, and permission to impersonate ServiceAccounts. A local Docker Desktop, kind or Minikube lab with its administrator context is suitable.

The accompanying manifests and commands were tested on Kubernetes 1.35.1.

The two lab namespaces, `ckad-access` and `ckad-access-other`, should not already exist. Additional policies or Pod Security exemptions configured on your cluster can change the results.

Commands use `kubectl` in full. The shell commands inside the container use `sh`, regardless of whether your local terminal is Bash or PowerShell. Examples with `\` line continuations use Bash syntax; in PowerShell, put those commands on one line.

## Getting the Resources

```bash
git clone https://github.com/SupaaHiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261008-ckad
kubectl config current-context
```

Check that the context is your lab cluster, then run the files in the order shown below. The `manifests/rejected/` directory contains an intentionally invalid request to use with server-side dry-run.

## Step 1: Give the Caller an Identity

Kubernetes distinguishes ordinary users from ServiceAccounts. Human identities normally come from an external identity system, a client certificate, or another configured authenticator; there is no ordinary `User` API object to create with `kubectl`. A kubeconfig tells the client which cluster and credentials to use. A ServiceAccount, on the other hand, is a namespaced Kubernetes resource. See [Authenticating](https://kubernetes.io/docs/reference/access-authn-authz/authentication/).

Create the namespaces and the ServiceAccount:

```bash
kubectl apply -f manifests/01-namespaces.yaml
kubectl apply -f manifests/02-serviceaccount.yaml
```

The ServiceAccount manifest is small:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: pod-reader
  namespace: ckad-access
```

Its authenticated username is `system:serviceaccount:ckad-access:pod-reader`. The namespace is part of the identity: a `pod-reader` in a different namespace is a different caller. ServiceAccount authentication also assigns groups, including `system:serviceaccounts`, `system:serviceaccounts:ckad-access` and `system:authenticated`.

An identity alone does not grant access to application resources. Before adding permissions, check:

```bash
kubectl auth can-i list pods -n ckad-access --as=system:serviceaccount:ckad-access:pod-reader
# no
```

`--as` asks the API server to impersonate this identity. Your current kubeconfig user must be allowed to impersonate it. This checks authorization; it does **not** prove that the ServiceAccount's token works. We'll make a real authenticated request in Step 3.

This lab binds permissions directly to the ServiceAccount. When debugging group-based grants, also account for the caller's groups; an impersonation check with only a username is not a complete reproduction of every authentication context.

## Step 2: Grant a Small Set of Permissions with RBAC

RBAC connects permission rules to identities using four resource types:

| Resource | Purpose |
|---|---|
| `Role` | Define permissions within one namespace |
| `ClusterRole` | Define reusable rules, including rules for cluster-scoped resources |
| `RoleBinding` | Grant a Role, or a ClusterRole's namespaced permissions, in the binding's namespace |
| `ClusterRoleBinding` | Grant a ClusterRole across the cluster |

A ClusterRole does not grant access by existing. In particular, a RoleBinding that references a ClusterRole still grants namespaced access only in the binding's namespace. Permissions from multiple bindings add together; RBAC has no explicit deny rule. These scope rules are described in [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Our `manifests/03-reader-rbac.yaml` starts with:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: ckad-access
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
```

The empty API group is the core group used by Pods. Deployments would use `apiGroups: ["apps"]`. Resource names are plural, and `pods/log` is a separate subresource: permission to read a Pod does not automatically include its logs.

The second document in the file attaches those rules to our identity:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pod-reader
  namespace: ckad-access
subjects:
  - kind: ServiceAccount
    name: pod-reader
    namespace: ckad-access
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: pod-reader
```

Apply it, then check the boundaries:

```bash
kubectl apply -f manifests/03-reader-rbac.yaml

kubectl auth can-i list pods -n ckad-access --as=system:serviceaccount:ckad-access:pod-reader
# yes
kubectl auth can-i get pods --subresource=log -n ckad-access --as=system:serviceaccount:ckad-access:pod-reader
# yes
kubectl auth can-i create pods -n ckad-access --as=system:serviceaccount:ckad-access:pod-reader
# no
kubectl auth can-i get secrets -n ckad-access --as=system:serviceaccount:ckad-access:pod-reader
# no
kubectl auth can-i list pods -n ckad-access-other --as=system:serviceaccount:ckad-access:pod-reader
# no
```

For `kubectl auth can-i`, use `--subresource=log`. Writing `pods/log` in that command means a Pod *named* `log`, unlike the RBAC manifest syntax. The [command reference](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/) includes the subresource form.

## Step 3: Authenticate from a Pod

Our `api-client` Pod runs a container with `curl` and selects the identity with:

```yaml
spec:
  serviceAccountName: pod-reader
```

The full manifest also sets `runAsUser: 1000`, giving the kubelet a numeric UID to check against `runAsNonRoot: true` even though the container image declares its user by name.

Create it using your administrator context:

```bash
kubectl apply -f manifests/04-api-client.yaml
kubectl wait -n ckad-access --for=condition=Ready pod/api-client --timeout=120s
kubectl get pod api-client -n ckad-access -o yaml
```

In the live Pod, look for a projected volume with a generated name starting with `kube-api-access-`. It contains a ServiceAccount token, the cluster CA certificate and the namespace. The ServiceAccount admission controller adds this API-access volume by default. The kubelet obtains time-limited tokens and refreshes them; applications should reread the token file as needed. The mechanism is described in [Managing Service Accounts](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/).

Now open a shell in the container:

```bash
kubectl exec -it -n ckad-access api-client -- sh
```

Your administrator credentials authorize the `exec` operation. The `curl` requests **inside** the container use the Pod's ServiceAccount token:

```sh
SA_DIR=/var/run/secrets/kubernetes.io/serviceaccount
API=https://kubernetes.default.svc

# A real authenticated request: list Pods in our namespace.
curl -sS --cacert "$SA_DIR/ca.crt" \
  -H "Authorization: Bearer $(cat "$SA_DIR/token")" \
  -o /dev/null -w 'HTTP %{http_code}\n' \
  "$API/api/v1/namespaces/ckad-access/pods"
# HTTP 200

# Same token, different resource: RBAC does not grant access.
curl -sS --cacert "$SA_DIR/ca.crt" \
  -H "Authorization: Bearer $(cat "$SA_DIR/token")" \
  -o /dev/null -w 'HTTP %{http_code}\n' \
  "$API/api/v1/namespaces/ckad-access/secrets"
# HTTP 403

# Invalid credentials: authentication fails before the RBAC check.
curl -sS --cacert "$SA_DIR/ca.crt" \
  -H 'Authorization: Bearer deliberately-invalid' \
  -o /dev/null -w 'HTTP %{http_code}\n' \
  "$API/api/v1/namespaces/ckad-access/pods"
# HTTP 401

exit
```

We validate the server's certificate with the mounted CA; there is no need for `--insecure`. Omitting `-o /dev/null` shows the response body, which is useful when diagnosing a denial.

For a workload that doesn't call the API, `automountServiceAccountToken: false` disables this automatic credential mount. It doesn't remove RBAC permissions from the identity. Modern clusters also don't automatically create a long-lived token Secret for each new ServiceAccount. When an external client needs a short-lived token, `kubectl create token <serviceaccount>` uses the TokenRequest API. We'll explore ServiceAccounts further in their own chapter; see [Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

## Step 4: Authorize Creation, Then Test Admission

So far our ServiceAccount can read Pods. Give it permission to create them as well:

```bash
kubectl apply -f manifests/05-creator-rbac.yaml
kubectl auth can-i create pods -n ckad-access --as=system:serviceaccount:ckad-access:pod-reader
# yes
```

This file adds a second Role and RoleBinding granting only `create` on `pods`. The existing read permissions remain. Granting Pod creation is meaningful access: a caller may be able to run workloads using other ServiceAccounts or mounted resources in that namespace, so this lab grant is not a general-purpose security boundary. The RBAC documentation discusses these [privilege escalation risks](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

The namespace we created in Step 1 has these labels:

```yaml
pod-security.kubernetes.io/enforce: baseline
pod-security.kubernetes.io/enforce-version: latest
```

The built-in **Pod Security admission** controller evaluates Pods against the `baseline` standard here. `latest` selects the policy version shipped with the API server; a namespace can instead pin a supported version such as `v1.35`.

Three modes are available: `enforce` rejects violations, `warn` returns a warning while allowing the request, and `audit` adds an annotation to the API audit event while allowing it. The security levels are `privileged`, `baseline` and `restricted`. This example uses baseline's prohibition on privileged containers. See [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/) and the [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

First submit a regular Pod as our ServiceAccount, without storing it:

```bash
kubectl create --dry-run=server -f manifests/06-admitted-pod.yaml \
  --as=system:serviceaccount:ckad-access:pod-reader -o yaml
```

The response should be a Pod object. It also shows defaults applied during API processing, including `serviceAccountName: default`: the request caller and the identity assigned to the resulting workload are separate choices. This Pod opts out of API credential automounting.

Next submit `manifests/rejected/privileged-pod.yaml`, which adds:

```yaml
securityContext:
  privileged: true
```

```bash
kubectl create --dry-run=server -f manifests/rejected/privileged-pod.yaml \
  --as=system:serviceaccount:ckad-access:pod-reader
```

Expect an error containing:

```text
violates PodSecurity "baseline:latest": privileged
```

The identity can create Pods, but this particular Pod violates policy. **`kubectl auth can-i` returning `yes` does not guarantee that a submitted object will be admitted.**

Use `--dry-run=server` for this comparison: it runs the request through the API server without persisting the object. `--dry-run=client` only builds the object locally and cannot test cluster admission policy. Admission webhooks must support dry-run for a server-side dry-run request to succeed. See [API dry-run](https://kubernetes.io/docs/reference/using-api/api-concepts/#dry-run).

We use `create` because the permission we granted is `create`. An `apply` workflow can also need read or patch permissions; a denial for one of those verbs would test a different part of RBAC.

## Step 5: Recognize Mutation and Validation

Admission can change an object or reject it. Mutating admission runs before validating admission, so validation sees the object after admission mutations. For example:

| Mechanism | Example behavior |
|---|---|
| ServiceAccount admission | Select the default ServiceAccount if omitted and arrange API credential mounting |
| LimitRanger | Supply configured resource defaults or reject requests that violate limits |
| ResourceQuota | Reject a request that would exceed a namespace quota |
| Pod Security admission | Reject a Pod that violates the namespace's configured security standard |
| Admission webhooks | Call an external service to mutate an object or evaluate policy |

Kubernetes also supports `ValidatingAdmissionPolicy` for declarative checks using CEL, without an external webhook server; that API is stable from Kubernetes 1.30. We don't need to install a webhook or policy engine for this lab. The [admission controller reference](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/) and [ValidatingAdmissionPolicy documentation](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/) cover these mechanisms.

One useful debugging detail: Pod Security `enforce` checks the **Pods** created by a Deployment. The Deployment itself can be accepted while its ReplicaSet fails to create Pods. In that case, inspect ReplicaSet events for the admission error rather than expecting a running Pod to troubleshoot.

## Troubleshooting: Read the Whole Error

| Symptom | What to check |
|---|---|
| `Unauthorized` / HTTP 401 | Invalid or expired credentials; token issuer and audience; chosen kubeconfig user |
| `Forbidden` naming a user, resource, verb and namespace | Role rules, binding subjects, API group and namespace |
| `Forbidden` with `violates PodSecurity`, quota text, or a webhook denial | The requested object's fields and the applicable admission policy |
| `cannot impersonate resource "serviceaccounts"` | The current caller lacks impersonation permission; the target identity's permissions haven't been tested yet |
| `can-i` says `yes`, creation fails | Admission rules, schema errors, or additional verbs required by the actual command |

Both authorization and admission can return HTTP 403. The status code alone isn't enough to distinguish them. A timeout, DNS failure or certificate trust error can happen before either check.

For an RBAC problem, inspect the rules and the binding together:

```bash
kubectl get role,rolebinding -n ckad-access
kubectl describe role pod-reader -n ckad-access
kubectl describe rolebinding pod-reader -n ckad-access
kubectl auth can-i --list -n ckad-access --as=system:serviceaccount:ckad-access:pod-reader
```

## Clean-up

Remove only the namespaces created for this lab:

```bash
kubectl delete namespace ckad-access ckad-access-other
```

This removes the Pods, ServiceAccounts, Roles and RoleBindings in them. The server-side dry-run Pods were never stored, and we created no ClusterRoles or ClusterRoleBindings.

## Wrapping Up: What We've Covered

We followed an API request through three separate decisions: verifying the caller's identity, checking its allowed actions, and evaluating the requested object against admission policy.

The lab showed the distinction directly: a valid ServiceAccount token could read Pods but not Secrets; a RoleBinding granted access in only one namespace; and permission to create Pods still didn't allow a privileged Pod past baseline admission.

For CKAD practice, repeat the permission checks with a different namespace, resource or verb and explain each result before running the command. Being able to locate the failing stage is what makes these errors manageable under time pressure.
