---
layout: default
title: "CKAD Preparation — Use Ingress Rules to Expose Applications"
date: 2026-10-19
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261019-ckad/article.webp"
summary: "Complete the CKAD series with a practical Ingress lab: route HTTP requests by host and path, configure TLS, and troubleshoot controller classes and backend ports. Then identify the limits of Ingress that lead into the next article on Kubernetes Gateway API."
---

# CKAD Preparation — Use Ingress Rules to Expose Applications

This final chapter of our [CKAD preparation series](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html) covers **Use Ingress rules to expose applications**. In the [Services chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261018-ckad/article_EN.html), we gave an application a stable endpoint and diagnosed its backends. Now we will put HTTP routing in front of two Services and choose a backend using the request's hostname and path.

We will also terminate TLS, break two parts of the routing configuration, and restore them. The chapter closes the CKAD roadmap and introduces the questions we will explore next with **Kubernetes Gateway API**.

## Understand the Three Moving Parts

An **Ingress** declares HTTP routing rules. An **Ingress controller** watches those rules and configures the proxy or load balancer that handles requests. An **IngressClass** identifies the implementation responsible for a class of Ingress resources. Creating an Ingress object alone does not deploy a controller or make an endpoint reachable.

The client reaches the controller first. The controller matches a rule, finds the referenced Service and its backend port, and forwards the request to the application. Depending on the implementation, forwarding may use backend Pod addresses directly; do not assume every request crosses the Service's ClusterIP.

Ingress is a stable API whose feature set is frozen; Kubernetes has no plan to remove it. It remains relevant to this CKAD requirement, while new networking capabilities are developed through Gateway API. See the [Kubernetes Ingress overview](https://kubernetes.io/docs/concepts/services-networking/ingress/).

## Prepare a Disposable Lab

The commands use **Bash**, `kubectl`, `curl` and OpenSSL with `-addext` support. Use a disposable Kubernetes cluster with Linux nodes and working Pod networking. This lab installs its own controller and requires permission to create a namespace, RBAC resources and an IngressClass, as well as application resources.

The examples were verified on Kubernetes **1.35.1**, with **Traefik 3.7.15** and **whoami 1.11.0**. The application manifests use the standard `networking.k8s.io/v1` Ingress API. Traefik-specific settings are kept in the controller setup.

```bash
git clone https://github.com/Supaahiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261019-ckad
kubectl config current-context
kubectl get namespace ckad-ingress --ignore-not-found
kubectl get ingressclass ckad-ingress --ignore-not-found
kubectl get clusterrole,clusterrolebinding ckad-ingress-controller --ignore-not-found
```

If any of these named resources already exists, use another disposable cluster or update all lab names consistently before continuing. Cleanup removes these resources.

```bash
kubectl apply -f manifests/01-namespace.yaml
kubectl apply -f manifests/02-controller-rbac.yaml
kubectl apply -f manifests/03-controller.yaml
kubectl rollout status deployment/ingress-controller -n ckad-ingress --timeout=180s
kubectl get ingressclass ckad-ingress -o yaml
```

The setup creates a controller scoped to the `ckad-ingress` namespace and class. It reads application Services, EndpointSlices, Ingresses and TLS Secrets using a dedicated ServiceAccount. Its IngressClass contains:

```yaml
spec:
  controller: traefik.io/ingress-controller
```

The controller listens on container ports 8000 and 8443, exposed by its ClusterIP Service on ports 80 and 443. We enable `strictPrefixMatching` so prefix matching respects path-element boundaries, and enable TLS on the HTTPS entrypoint. These are explicit Traefik settings, documented in its [Ingress provider configuration](https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-ingress/) and [TLS entrypoint configuration](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/ingress/#enabling-tls-via-http-options-on-entrypoint).

## Deploy Two Backends

```bash
kubectl apply -f manifests/04-applications.yaml
kubectl rollout status deployment/web -n ckad-ingress --timeout=120s
kubectl rollout status deployment/api -n ckad-ingress --timeout=120s
kubectl get services -n ckad-ingress
kubectl get endpointslices -n ckad-ingress -l kubernetes.io/service-name=api
```

The `web` and `api` Deployments run small [whoami HTTP servers](https://github.com/traefik/whoami/tree/v1.11.0). Responses include `Name: web` or `Name: api`, the Pod hostname and the received request. Both application Services expose **port 80**, mapping to their Pods' named port `http`, which is **8080**.

The name `api` is just our second application's name. It does not refer to the Kubernetes API server or to Gateway API.

## Declare Host and Path Rules

Apply `manifests/05-ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: storefront
  namespace: ckad-ingress
spec:
  ingressClassName: ckad-ingress
  rules:
    - host: shop.ckad.test
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
    - host: admin.ckad.test
      http:
        paths:
          - path: /status
            pathType: Exact
            backend:
              service:
                name: api
                port:
                  number: 80
```

```bash
kubectl apply -f manifests/05-ingress.yaml
kubectl get ingress storefront -n ckad-ingress
kubectl describe ingress storefront -n ckad-ingress
```

`ingressClassName` references the **IngressClass name**, not its controller identifier. Each backend Service must exist in the Ingress namespace, and `backend.service.port` identifies a **Service port**, by name or number. Here it is 80, not container port 8080. These fields are defined in the [Ingress API reference](https://kubernetes.io/docs/reference/kubernetes-api/networking/ingress-v1/).

`Exact` matches a path literally, including its trailing slash. `Prefix` matches complete path elements: `/api` matches `/api/items`, but not `/apix`. Matching is case-sensitive. The specification prefers the longest matching path, then Exact over Prefix for equal matches. `ImplementationSpecific` delegates matching semantics to the controller. See the [path-type rules](https://kubernetes.io/docs/concepts/services-networking/ingress/#path-types).

We use a separate host for the Exact exercise, so its success or failure is visible without a catch-all rule on that host.

## Send Requests Through the Controller

Open a separate terminal and keep this command running:

```bash
kubectl port-forward -n ckad-ingress service/ingress-controller 8080:80 8443:443
```

From the first terminal, send an HTTP request with the desired host:

```bash
curl --noproxy '*' --fail -H 'Host: shop.ckad.test' http://127.0.0.1:8080/
curl --noproxy '*' --fail -H 'Host: shop.ckad.test' http://127.0.0.1:8080/api/items
curl --noproxy '*' --fail -H 'Host: admin.ckad.test' http://127.0.0.1:8080/status
```

Expect `Name: web`, `Name: api` and `Name: api`, respectively. Allow a few seconds for the controller to reconcile a new or changed rule.

| Host header | Request path | Expected result |
| --- | --- | --- |
| `shop.ckad.test` | `/` | `web` |
| `shop.ckad.test` | `/api/items` | `api`; the more specific prefix wins |
| `shop.ckad.test` | `/apix` | `web`; `/api` is not a matching path element |
| `shop.ckad.test` | `/API/items` | `web`; path matching is case-sensitive |
| `admin.ckad.test` | `/status` | `api`; Exact match |
| `admin.ckad.test` | `/status/` | No matching rule; HTTP 404 in this setup |
| `unknown.ckad.test` | `/` | No matching host; HTTP 404 in this setup |

Try the negative cases without `--fail` so you can inspect their responses:

```bash
curl --noproxy '*' -i -H 'Host: admin.ckad.test' http://127.0.0.1:8080/status/
curl --noproxy '*' -i -H 'Host: unknown.ckad.test' http://127.0.0.1:8080/
```

There is no `defaultBackend` here. The `/` Prefix rule is a catch-all **only for `shop.ckad.test`**; it does not match every hostname. Unmatched requests can behave differently if the controller or Ingress has a default backend configured.

The response to `/api/items` includes `GET /api/items`: matching the prefix did not remove it. Ingress has no standard path-rewrite field. An application must serve the forwarded path, or you must configure a controller-specific rewrite mechanism.

Setting `Host` in these HTTP requests does not create DNS records. Port-forward reaches the controller through the Kubernetes API connection, so these tests exercise the controller's routing and its connection to the application. They do not verify public DNS, an external load balancer, or workstation routing to a node. An empty Ingress `ADDRESS` is expected with this lab's controller setup.

For an external deployment, expose the controller through the environment's supported mechanism and point the application's DNS names at that reachable endpoint. Application Services can remain ClusterIP.

## Diagnose an Incorrect Backend Port

A common mistake is putting the container port into the Ingress backend. Change only the `/api` rule from Service port 80 to 8080:

```bash
kubectl patch ingress storefront -n ckad-ingress --type=json \
  --patch-file manifests/patches/06-wrong-service-port.yaml
curl --noproxy '*' -i -H 'Host: shop.ckad.test' http://127.0.0.1:8080/api/items
kubectl describe ingress storefront -n ckad-ingress
kubectl get service api -n ckad-ingress -o yaml
kubectl get endpointslices -n ckad-ingress -l kubernetes.io/service-name=api -o yaml
kubectl logs -n ckad-ingress deployment/ingress-controller --tail=30
```

The request stops reaching `api`. The Service still has ready backends on 8080, but it exposes only **Service port 80**. In the tested controller, the logs report `service port not found`; depending on routing configuration, a rejected route may result in a fallback response or an error. The status code alone is not enough to locate the fault.

To isolate the backend, open another terminal with:

```bash
kubectl port-forward -n ckad-ingress service/api 18080:80
```

Then test it directly from the first terminal:

```bash
curl --noproxy '*' --fail http://127.0.0.1:18080/api/items
```

This should still return `Name: api`. Stop this extra forward with **Ctrl+C**, restore the Ingress port and retry through the controller:

```bash
kubectl patch ingress storefront -n ckad-ingress --type=json \
  --patch-file manifests/patches/06-restore-service-port.yaml
curl --noproxy '*' --fail -H 'Host: shop.ckad.test' http://127.0.0.1:8080/api/items
```

If the direct backend check also fails, continue with the [Service troubleshooting exercises](https://supaahiro.github.io/schwifty-lab/blog-posts/20261018-ckad/article_EN.html): selectors, endpoint readiness, ports and application listeners.

## Diagnose a Class That No Controller Handles

The API can accept an Ingress whose class does not have a matching controller. Demonstrate this with a temporary class-name change:

```bash
kubectl patch ingress storefront -n ckad-ingress --type=merge \
  -p '{"spec":{"ingressClassName":"unclaimed-ckad"}}'
kubectl get ingress storefront -n ckad-ingress -o yaml
kubectl get ingressclass
curl --noproxy '*' -i -H 'Host: shop.ckad.test' http://127.0.0.1:8080/
```

After reconciliation, our controller stops providing the application route. The Ingress object still exists. Successful `kubectl apply` or `patch` output therefore does not prove that any controller has configured the route.

Restore the class and retest:

```bash
kubectl patch ingress storefront -n ckad-ingress --type=merge \
  -p '{"spec":{"ingressClassName":"ckad-ingress"}}'
curl --noproxy '*' --fail -H 'Host: shop.ckad.test' http://127.0.0.1:8080/
```

## Add TLS Termination

Create a short-lived self-signed certificate for both lab hostnames. Keep the key in a temporary directory rather than in the repository:

```bash
TLS_DIR=$(mktemp -d)
openssl req -x509 -nodes -days 2 -newkey rsa:2048 \
  -keyout "$TLS_DIR/tls.key" -out "$TLS_DIR/tls.crt" \
  -subj '/CN=shop.ckad.test' \
  -addext 'subjectAltName=DNS:shop.ckad.test,DNS:admin.ckad.test'

kubectl create secret tls ingress-lab-tls -n ckad-ingress \
  --cert="$TLS_DIR/tls.crt" --key="$TLS_DIR/tls.key"
kubectl patch ingress storefront -n ckad-ingress --type=merge \
  --patch-file manifests/patches/07-tls.yaml
```

The patch adds this standard Ingress TLS configuration:

```yaml
spec:
  tls:
    - hosts:
        - shop.ckad.test
        - admin.ckad.test
      secretName: ingress-lab-tls
```

The `kubernetes.io/tls` Secret contains `tls.crt` and `tls.key` and resides in the Ingress namespace. Its certificate must cover the requested hostname. The controller terminates client TLS and forwards plain HTTP to these lab backends; encrypting the backend connection would require additional configuration. See [TLS Secrets](https://kubernetes.io/docs/concepts/configuration/secret/#tls-secrets).

Keep the original port-forward running and test HTTPS:

```bash
curl --noproxy '*' --fail --cacert "$TLS_DIR/tls.crt" \
  --resolve shop.ckad.test:8443:127.0.0.1 \
  https://shop.ckad.test:8443/api/items
curl --noproxy '*' --fail --cacert "$TLS_DIR/tls.crt" \
  --resolve admin.ckad.test:8443:127.0.0.1 \
  https://admin.ckad.test:8443/status
```

Both requests return `Name: api`. `--resolve` supplies the connection address while keeping the URL hostname for HTTP and TLS SNI. `--cacert` trusts our generated certificate for these requests. Setting only an HTTP `Host` header on an IP-based HTTPS URL would not set the TLS hostname correctly. See the [curl options reference](https://curl.se/docs/manpage.html#--resolve).

Without `--cacert`, verification of this self-signed certificate fails. A hostname outside the certificate's names also fails validation. These are expected TLS failures, not broken Service selectors. The test uses certificate verification rather than `curl -k`.

Our controller already enables TLS on its HTTPS entrypoint; the Ingress TLS block selects the certificate. HTTP remains available on 8080: adding `spec.tls` does not establish a portable HTTP-to-HTTPS redirect policy. Such behavior depends on the controller configuration.

## Troubleshoot the Request in Order

| Observation | Inspect next |
| --- | --- |
| Cannot connect to the entrypoint | Controller readiness, exposure method, port-forward, routing and firewall |
| Request reaches the proxy but no route matches | Host header, path, path type, IngressClass and controller configuration |
| Route targets an unavailable backend | Service name and port, namespace, EndpointSlices and readiness |
| Certificate verification fails | URL hostname/SNI, certificate SANs, trust, Secret name and namespace |
| Proxy reaches the backend but the response is unexpected | Forwarded path, application logs and any controller-specific rewrites |

Useful commands include:

```bash
kubectl describe ingress storefront -n ckad-ingress
kubectl get ingressclass ckad-ingress -o yaml
kubectl get pods,services -n ckad-ingress
kubectl get endpointslices -n ckad-ingress -l kubernetes.io/service-name=api -o yaml
kubectl logs -n ckad-ingress deployment/ingress-controller --tail=50
kubectl logs -n ckad-ingress deployment/api --tail=20
kubectl get secret ingress-lab-tls -n ckad-ingress
kubectl get networkpolicies -n ckad-ingress
```

A 404 may come from the controller or the application; a 5xx response may have several causes. Compare the route, controller logs and direct backend access before changing resources. In clusters with enforced NetworkPolicies, allow the controller's traffic to the application Pods. As covered in the [NetworkPolicies chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261017-ckad/article_EN.html), enforcement requires support from the networking/CNI implementation.

## Clean Up

Stop both port-forward commands if they are still running. Delete the lab namespace and the three cluster-scoped resources created for it:

```bash
kubectl delete namespace ckad-ingress
kubectl delete ingressclass ckad-ingress
kubectl delete clusterrolebinding ckad-ingress-controller
kubectl delete clusterrole ckad-ingress-controller

if [ -n "${TLS_DIR:-}" ]; then
  rm -f "$TLS_DIR/tls.key" "$TLS_DIR/tls.crt"
  rmdir "$TLS_DIR"
fi
```

## Beyond CKAD: Where Ingress Reaches Its Limits

This completes our CKAD roadmap: host and path routing, Service backend selection, TLS and troubleshooting all work together in this final lab.

Ingress covers basic HTTP/HTTPS exposure. Header matching, traffic splits and request transformations often require controller-specific extensions, while shared entrypoints complicate ownership. The next article will examine how **Kubernetes Gateway API** addresses these limits:

| Requirement | Direction offered by Gateway API |
| --- | --- |
| Separate infrastructure and application responsibilities | `GatewayClass`, `Gateway` and route resources with distinct ownership |
| Express richer HTTP routing without vendor annotations for every feature | Structured `HTTPRoute` matches, filters and weighted backends |
| Share entrypoints across teams with explicit attachment rules | Gateway listeners and controlled route attachment |
| Understand whether routing configuration was accepted | Status conditions on Gateways and routes |

Gateway API needs a supporting implementation; check its conformance for the features you use. It defines Kubernetes networking resources, rather than a complete API-management product. The [Gateway API overview](https://kubernetes.io/docs/concepts/services-networking/gateway/) introduces the model; our follow-up will compare it with Ingress through practical examples.
