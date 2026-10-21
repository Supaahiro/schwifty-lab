---
layout: default
title: "Kubernetes Gateway API — What It Solves Beyond Ingress"
date: 2026-10-20
categories: [kubernetes, devops]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261020-gateway-api/article.webp"
summary: "Move beyond basic Ingress routing with Kubernetes Gateway API. Build a practical lab for header-based canaries, URL rewriting, weighted backends, controlled route attachment and cross-namespace references, then diagnose rejected configuration through status conditions."
---

# Kubernetes Gateway API — What It Solves Beyond Ingress

The [final CKAD chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261019-ckad/article_EN.html) exposed applications through Ingress using hostnames, paths and TLS. This follow-up explores the questions that appear when an entrypoint serves several teams: who owns the listener, who may attach routes, and how do we express a canary without relying on a particular controller's annotations?

**Kubernetes Gateway API** adds resources for these responsibilities and richer routing. It still needs a supporting controller. We will keep Traefik, the implementation used in the Ingress chapter, so the comparison focuses on the APIs and their configuration model.

## What Changes Compared with Ingress?

Ingress controllers can already implement advanced features through annotations, custom resources or configuration. The limitation is often what the **standard Ingress API can express**, not what the underlying proxy can do. Gateway API gives several of those features a shared schema.

| Requirement | Standard Ingress | Gateway API used in this lab |
| --- | --- | --- |
| Route by hostname and path | Built in | `HTTPRoute.hostnames` and path matches |
| Send requests with a header to a canary | Controller-specific extension | HTTP header matches |
| Split traffic between two Services | Controller-specific extension | Weighted `backendRefs` |
| Rewrite a path before forwarding | Controller-specific extension | `URLRewrite` filter, an Extended feature |
| Share a listener across application teams | Ownership and admission depend on the setup | Separate Gateway and route resources, with `allowedRoutes` |
| Reference a Service in another namespace | Ingress Service backends are namespace-local | An explicit backend namespace plus a target-side `ReferenceGrant` |
| Diagnose whether configuration is usable | Status primarily reports load-balancer addresses | Conditions such as `Accepted`, `Programmed` and `ResolvedRefs` |

Ingress remains stable and its feature set is frozen; it is not being removed. Gateway API is where Kubernetes develops new service-networking capabilities. See the [Ingress documentation](https://kubernetes.io/docs/concepts/services-networking/ingress/) and [Gateway API overview](https://kubernetes.io/docs/concepts/services-networking/gateway/).

## Separate Infrastructure from Application Routes

The [Gateway API resource model](https://gateway-api.sigs.k8s.io/docs/concepts/api-overview/) separates these objects:

- **GatewayClass** is cluster-scoped and identifies the controller implementation.
- **Gateway** declares listeners and the routes they will accept. An infrastructure team can own it.
- **HTTPRoute** declares application hostnames, matches, filters and backends. An application team can own it in its namespace.
- **ReferenceGrant** lets the owner of a target namespace authorize supported references from another namespace.

Those roles describe a useful ownership model. Kubernetes RBAC must enforce who can edit each resource; creating different resource kinds does not itself assign permissions.

Our application routes live in `gateway-store`, the Gateway in `gateway-infra`, an initially excluded route in `gateway-outsider`, and a shared backend in `gateway-shared`. We will test two separate decisions: whether a route may **attach to a Gateway**, and whether it may **reference a backend** elsewhere.

## Prepare a Disposable Lab

Use **Bash**, Docker, `kind`, `kubectl` and `curl`. The examples were verified with **kind 0.33.0**, **Kubernetes 1.35.1**, **Gateway API 1.6.3 Standard channel**, **Traefik 3.7.15** and **whoami 1.11.0**. The [Traefik Gateway provider documentation](https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-gateway/) describes its supported Gateway API version and features.

This lab creates its own cluster because it installs cluster-scoped CRDs and controller permissions. Check that `gateway-api-lab` does not already exist; if it does, choose another name consistently rather than reusing an unrelated cluster.

```bash
kind get clusters
git clone https://github.com/Supaahiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261020-gateway-api

LAB_KUBECONFIG=$(mktemp)
kind create cluster --name gateway-api-lab \
  --image kindest/node:v1.35.1 \
  --kubeconfig "$LAB_KUBECONFIG" --wait 120s

k() { kubectl --kubeconfig "$LAB_KUBECONFIG" "$@"; }
k config current-context
```

Keep this terminal open: `k` always uses the temporary kubeconfig, without changing the context in your normal configuration. Install the pinned [Gateway API release](https://github.com/kubernetes-sigs/gateway-api/releases/tag/v1.6.3), then the controller and applications:

```bash
k apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.3/standard-install.yaml
k wait --for=condition=Established crd --all --timeout=60s

k apply -f manifests/01-namespaces.yaml
k apply -f manifests/02-controller-rbac.yaml
k apply -f manifests/03-controller.yaml
k apply -f manifests/04-applications.yaml
k apply -f manifests/05-gateway.yaml
k apply -f manifests/05-app-team-rbac.yaml
k apply -f manifests/06-basic-route.yaml

k rollout status deployment/gateway-controller -n gateway-infra --timeout=180s
k rollout status deployment/store-v1 -n gateway-store --timeout=180s
k rollout status deployment/store-v2 -n gateway-store --timeout=180s
k rollout status deployment/outsider -n gateway-outsider --timeout=180s
k rollout status deployment/shared-report -n gateway-shared --timeout=180s
k wait --for=condition=Accepted gatewayclass/gateway-lab --timeout=60s
k wait --for=condition=Programmed gateway/edge -n gateway-infra --timeout=60s
```

**Apply the route examples in the order shown, not the entire manifests directory.** Files `06` through `09` are alternative versions of the same `storefront` HTTPRoute. Each replaces the preceding routing configuration; the exercises are not cumulative.

The controller's Kubernetes permissions are demo infrastructure. Its namespace watch filter limits what it watches; that filter is not an RBAC security boundary.

## Connect the Listener and the First Route

The complete `manifests/05-gateway.yaml` is:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: gateway-lab
spec:
  controllerName: traefik.io/gateway-controller
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: edge
  namespace: gateway-infra
spec:
  gatewayClassName: gateway-lab
  listeners:
    - name: http
      protocol: HTTP
      port: 8000
      hostname: "*.gateway.test"
      allowedRoutes:
        kinds:
          - kind: HTTPRoute
        namespaces:
          from: Selector
          selector:
            matchLabels:
              gateway-access: shop
```

The listener accepts HTTPRoutes from namespaces labeled `gateway-access: shop`. Initially, only `gateway-store` has that label. Hostnames on the route must also overlap the listener's hostname.

Why port **8000**? This Traefik deployment listens on entrypoint `web` at `:8000`. Its Service exposes port **80** and forwards to that container port. Traefik requires the Gateway listener port to match an entrypoint port, as explained in its [Gateway routing documentation](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/gateway-api/). This is implementation setup, not a requirement that every Gateway use port 8000.

The complete `manifests/06-basic-route.yaml` attaches to the named listener:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: storefront
  namespace: gateway-store
spec:
  parentRefs:
    - name: edge
      namespace: gateway-infra
      sectionName: http
  hostnames: ["shop.gateway.test"]
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: store-v1
          port: 80
```

The backend port is the **Service port**, not the Pod's port. With no backend namespace specified, the Service is resolved in the route's namespace.

Define a helper to inspect route status, and check the first route before sending traffic:

```bash
route_status() {
  k get httproute "$1" -n "$2" -o jsonpath='{.metadata.generation}{"\n"}{range .status.parents[*]}{.controllerName}{" "}{.parentRef.namespace}{"/"}{.parentRef.name}{" "}{.parentRef.sectionName}{"\n"}{range .conditions[*]}{.type}{"="}{.status}{" reason="}{.reason}{" observedGeneration="}{.observedGeneration}{"\n"}{end}{end}'
}
route_status storefront gateway-store
```

Expect `Accepted=True` and `ResolvedRefs=True` under parent `gateway-infra/edge`, listener `http`. **After every route edit, rerun this command until `observedGeneration` matches the generation printed on the first line**, then check the expected conditions and send requests. Reconciliation is asynchronous; a condition from an older generation does not confirm the latest change. Parent status is separate for each attachment. When changing a namespace label or a grant, wait for the expected condition values too: the route's own generation may stay unchanged.

Start a local port-forward in the background, retaining its process ID for cleanup:

```bash
kubectl --kubeconfig "$LAB_KUBECONFIG" -n gateway-infra \
  port-forward service/gateway-controller 18080:80 &
FORWARD_PID=$!
```

Wait for the `Forwarding from 127.0.0.1:18080` message. Requests travel from local port 18080 through Service port 80 to the controller's listener on 8000, then to the selected application backend. This exercises routing through the proxy; it does not test a public load balancer, external DNS or TLS.

```bash
curl --fail-with-body -sS -H 'Host: shop.gateway.test' http://127.0.0.1:18080/
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: unknown.gateway.test' http://127.0.0.1:18080/
```

The first response contains `Name: store-v1`. The second returns **404**: the listener's wildcard does not create a route for every hostname.

## Canary Selection Using a Header

Suppose testers should reach version 2 while normal requests continue to reach version 1. The `rules` section of `manifests/07-header-route.yaml` expresses both choices:

```yaml
rules:
  - matches:
      - path:
          type: PathPrefix
          value: /
        headers:
          - name: X-Release
            type: Exact
            value: canary
    backendRefs:
      - name: store-v2
        port: 80
  - matches:
      - path:
          type: PathPrefix
          value: /
    backendRefs:
      - name: store-v1
        port: 80
```

The path and header in the first match must both match. For the same path match, the header-qualified rule takes precedence over the fallback; the behavior does not depend only on placing that rule first. See the [HTTP routing guide](https://gateway-api.sigs.k8s.io/guides/user-guides/http-routing/).

```bash
k apply -f manifests/07-header-route.yaml
route_status storefront gateway-store

curl --fail-with-body -sS -H 'Host: shop.gateway.test' \
  http://127.0.0.1:18080/
curl --fail-with-body -sS -H 'Host: shop.gateway.test' -H 'X-Release: canary' \
  http://127.0.0.1:18080/
curl --fail-with-body -sS -H 'Host: shop.gateway.test' -H 'X-Release: other' \
  http://127.0.0.1:18080/
```

Expect `store-v1`, `store-v2`, then `store-v1`. The manifest contains standard HTTPRoute fields instead of a controller-specific canary annotation. A caller can supply this header, so it is a routing selector, **not an authentication mechanism**.

## Rewrite an External Path for the Backend

Now suppose clients call `/public/catalog`, but the application expects `/catalog`. First observe the current request path in the whoami response:

```bash
curl --fail-with-body -sS -H 'Host: shop.gateway.test' \
  http://127.0.0.1:18080/public/catalog
```

The backend currently sees `GET /public/catalog HTTP/...`. The first rule in `manifests/08-rewrite-route.yaml` adds a filter:

```yaml
matches:
  - path:
      type: PathPrefix
      value: /public
filters:
  - type: URLRewrite
    urlRewrite:
      path:
        type: ReplacePrefixMatch
        replacePrefixMatch: /
backendRefs:
  - name: store-v1
    port: 80
```

The full file also retains a `/` fallback to version 1. Apply it and compare the received paths:

```bash
k apply -f manifests/08-rewrite-route.yaml
route_status storefront gateway-store

curl --fail-with-body -sS -H 'Host: shop.gateway.test' \
  http://127.0.0.1:18080/public/catalog
curl --fail-with-body -sS -H 'Host: shop.gateway.test' \
  http://127.0.0.1:18080/publicity
```

The first backend request becomes `/catalog`. The second remains `/publicity`: `PathPrefix` matches path elements, not an arbitrary textual prefix. The client does not receive a redirect; the proxy changes the request it forwards.

Path rewriting is an **Extended** feature. A standard field is not a promise that every controller implements it. Verify your implementation's support; this example was exercised with the pinned Traefik version. `URLRewrite` and `RequestRedirect` cannot be combined in the same rule. See the [redirect and rewrite guide](https://gateway-api.sigs.k8s.io/guides/user-guides/http-redirect-rewrite/).

## Split Traffic Without Changing Replica Counts

Header selection is useful for explicit testing. A rollout can instead send a proportion of ordinary requests to version 2. The `backendRefs` in `manifests/09-weighted-route.yaml` are:

```yaml
backendRefs:
  - name: store-v1
    port: 80
    weight: 80
  - name: store-v2
    port: 80
    weight: 20
```

Weights are relative to their sum: `80/20` and `4/1` express the same split. Both Deployments still have one replica. This controls the distribution between backend Services independently of how many replicas each Service selects. See [HTTP traffic splitting](https://gateway-api.sigs.k8s.io/guides/user-guides/traffic-splitting/).

```bash
k apply -f manifests/09-weighted-route.yaml
route_status storefront gateway-store

set -o pipefail
for i in {1..200}; do
  curl --fail-with-body -sS -H 'Host: shop.gateway.test' \
    http://127.0.0.1:18080/ || { exit 1; }
done | sed -n 's/^Name: //p' | sort | uniq -c
```

Our verification run returned **161 responses from `store-v1` and 39 from `store-v2`**. Expect a distribution around the configured ratio, not an exact guarantee for every small batch.

Set version 2's weight to zero to stop selecting it for new requests, without scaling down its Deployment:

```bash
k patch httproute storefront -n gateway-store --type=json \
  -p='[{"op":"replace","path":"/spec/rules/0/backendRefs/1/weight","value":0}]'
route_status storefront gateway-store
```

Rerun the request loop: responses should now come from version 1. This does not cancel requests already in flight. We verified 30 requests after the update, all reaching version 1. Restore the simple route before the next exercises:

```bash
k apply -f manifests/06-basic-route.yaml
route_status storefront gateway-store
```

## Decide Which Teams May Attach Routes

The `gateway-outsider` namespace has a healthy application and Service, but lacks the namespace label required by `edge`. Its route attempts to use `blocked.gateway.test`:

```bash
k apply -f manifests/10-denied-route.yaml
route_status outsider gateway-outsider
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: blocked.gateway.test' http://127.0.0.1:18080/
```

Expect **`Accepted=False` with reason `NotAllowedByListeners`** and a 404. A valid Kubernetes object can still be rejected for attachment by the Gateway controller.

Acting as the infrastructure administrator, allow the namespace:

```bash
k label namespace gateway-outsider gateway-access=shop
route_status outsider gateway-outsider
curl --fail-with-body -sS -H 'Host: blocked.gateway.test' http://127.0.0.1:18080/
```

Once the conditions become `Accepted=True` and `ResolvedRefs=True`, the response contains `Name: outsider`. Remove the label and verify the denial returns:

```bash
k label namespace gateway-outsider gateway-access-
route_status outsider gateway-outsider
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: blocked.gateway.test' http://127.0.0.1:18080/
```

This is why namespace-label ownership matters. An application team that can change these labels could authorize its own namespace. The lab's `05-app-team-rbac.yaml` grants the `route-editor` ServiceAccount access to HTTPRoutes in `gateway-store` only. As the kind administrator, use impersonation to check that boundary:

```bash
APP_ID=system:serviceaccount:gateway-store:route-editor
k auth can-i patch httproutes.gateway.networking.k8s.io -n gateway-store --as="$APP_ID"
k auth can-i patch gateways.gateway.networking.k8s.io -n gateway-infra --as="$APP_ID"
k auth can-i patch namespaces --as="$APP_ID"
```

Expect **yes, no, no**. A denied `can-i` command exits nonzero; here that is the expected result. The lab commands themselves run as administrator so we can demonstrate both sides of the boundary. Real application identities need appropriate RoleBindings, and namespace-label changes must remain under trusted control. The [Gateway API security model](https://gateway-api.sigs.k8s.io/docs/concepts/security/) explains this division.

## Authorize a Backend in Another Namespace

Attachment permission does not authorize every backend reference. The `reports` route lives in the admitted `gateway-store` namespace, but points to `shared-report` in `gateway-shared`:

```yaml
backendRefs:
  - name: shared-report
    namespace: gateway-shared
    port: 80
```

Apply the route before creating any grant:

```bash
k apply -f manifests/11-shared-route.yaml
route_status reports gateway-store
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: reports.gateway.test' http://127.0.0.1:18080/
```

Expect **`Accepted=True` but `ResolvedRefs=False`, reason `RefNotPermitted`**. The HTTP request fails: accepting attachment is not permission to use the backend.

The owner of the **target namespace** can create `manifests/12-reference-grant.yaml`:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: ReferenceGrant
metadata:
  name: allow-store-reports
  namespace: gateway-shared
spec:
  from:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      namespace: gateway-store
  to:
    - group: ""
      kind: Service
      name: shared-report
```

This permits HTTPRoutes from `gateway-store` to reference the named Service in `gateway-shared`. It applies to routes of that kind in the source namespace, not only the `reports` route; `from` does not select an individual source route by name. See the [ReferenceGrant documentation](https://gateway-api.sigs.k8s.io/reference/api-types/referencegrant/).

```bash
k apply -f manifests/12-reference-grant.yaml
route_status reports gateway-store
curl --fail-with-body -sS -H 'Host: reports.gateway.test' http://127.0.0.1:18080/
```

With current `ResolvedRefs=True`, expect `Name: shared-report`. Revoke the grant, confirm `RefNotPermitted` and a failed request return, then restore it:

```bash
k delete referencegrant allow-store-reports -n gateway-shared
route_status reports gateway-store
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: reports.gateway.test' http://127.0.0.1:18080/
k apply -f manifests/12-reference-grant.yaml
```

| Decision | Where it is configured | What it permits |
| --- | --- | --- |
| Route attachment | `Gateway.spec.listeners[].allowedRoutes` | An eligible route attaches to that listener |
| Cross-namespace backend reference | `ReferenceGrant` in the backend namespace | Specified source kinds/namespaces reference permitted targets |
| Editing these objects | Kubernetes RBAC | An identity changes configuration |
| Pod traffic | NetworkPolicy and its enforcing network implementation | Network connections between workloads |

Route-to-Gateway attachment uses `allowedRoutes`; it does not need a ReferenceGrant for the cross-namespace parent in this lab. Neither mechanism authenticates HTTP callers or replaces NetworkPolicy. As discussed in the [NetworkPolicies chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261017-ckad/article_EN.html), policy enforcement requires support from the networking/CNI implementation.

## Troubleshoot Configuration Before Changing the Application

We can also distinguish a forbidden reference from a nonexistent backend. Break the basic storefront route deliberately:

```bash
k apply -f manifests/06-basic-route.yaml
k patch httproute storefront -n gateway-store --type=json \
  --patch-file manifests/patches/13-missing-backend.yaml
route_status storefront gateway-store
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: shop.gateway.test' http://127.0.0.1:18080/
```

The patch names `missing-store`. Expect **`Accepted=True` and `ResolvedRefs=False`, reason `BackendNotFound`**, with an unsuccessful request. Restore the existing Service reference:

```bash
k apply -f manifests/06-basic-route.yaml
route_status storefront gateway-store
curl --fail-with-body -sS -H 'Host: shop.gateway.test' http://127.0.0.1:18080/
```

After reconciliation, `ResolvedRefs=True` and `Name: store-v1` confirm the repair. These status signals answer different questions:

| Condition | What to investigate |
| --- | --- |
| GatewayClass `Accepted` | Does the intended controller recognize this class? |
| Gateway/listener `Accepted` and `Programmed` | Is the configuration accepted, and has the implementation programmed it? |
| HTTPRoute `Accepted` | Does this route attach to this parent/listener? Check namespace admission and hostname overlap. |
| HTTPRoute `ResolvedRefs` | Are the referenced resources valid and permitted? Check names, ports and grants. |

Check the relevant parent and current `observedGeneration`, not just the first `True` in the object. These conditions are not an end-to-end application health check: an accepted route with resolved references can still fail because Pods have no ready endpoints or traffic is blocked. The [Gateway API troubleshooting guide](https://gateway-api.sigs.k8s.io/docs/concepts/troubleshooting/) explains the status model.

```bash
k get gatewayclass gateway-lab -o yaml
k get gateway edge -n gateway-infra -o yaml
k describe httproute storefront -n gateway-store
k get services,pods -n gateway-store
k get endpointslices -n gateway-store -l kubernetes.io/service-name=store-v1
k get referencegrants -n gateway-shared
k logs deployment/gateway-controller -n gateway-infra --tail=50
```

Start with configuration status, then confirm actual requests, backend readiness and network reachability. An HTTP error code alone cannot identify which layer failed.

## What Gateway API Does Not Solve Automatically

The API makes more routing behavior and ownership rules explicit, but the implementation still matters. Installing CRDs alone does not provide a proxy. A resource using `v1` does not imply every optional feature is supported; check the controller's conformance and feature documentation before migrating annotations or custom resources.

Our HTTP lab deliberately used port-forwarding. A production endpoint also needs the appropriate infrastructure exposure, DNS, certificates and network access. Gateway API models HTTPS listeners and certificate references, but those configuration and operational tasks do not disappear.

Gateway API also does not, by itself, provide a complete API-management product with developer portals, subscription plans or every authentication and rate-limiting feature. Some capabilities remain implementation-specific or use additional APIs.

For an existing Ingress deployment, inventory the behavior currently supplied by annotations, map it to standard Gateway API fields where supported, identify remaining extensions, and verify both successful requests and expected denials before switching traffic.

## Clean Up

Stop the port-forward, then delete only the disposable cluster created for this article. Removing that cluster also removes its Gateway API CRDs, RBAC and application resources.

```bash
kill "$FORWARD_PID"
wait "$FORWARD_PID" 2>/dev/null || true
kind delete cluster --name gateway-api-lab --kubeconfig "$LAB_KUBECONFIG"
rm -f "$LAB_KUBECONFIG"
unset LAB_KUBECONFIG FORWARD_PID APP_ID
unset -f k route_status
```

We started with the same host-and-path routing used by Ingress, then added header selection, rewriting, weighted backends and explicit cross-namespace permissions. Those are concrete reasons to consider Gateway API when basic Ingress rules no longer express the routing and ownership model an application needs.
