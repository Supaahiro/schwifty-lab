---
layout: default
title: "CKAD Preparation — Provide and Troubleshoot Access to Applications via Services"
date: 2026-10-18
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261018-ckad/article.webp"
summary: "Expose an application through Kubernetes Services and troubleshoot its traffic path. Test DNS, ClusterIP, NodePort and headless discovery, then diagnose and repair selector, targetPort and readiness failures using EndpointSlices."
---

# CKAD Preparation — Provide and Troubleshoot Access to Applications via Services

This chapter covers the CKAD requirement **Provide and troubleshoot access to applications via Services**. We will expose two HTTP replicas, access them from a client Pod, and deliberately break the configuration to learn where to look when a Service stops working.

The [previous chapter on NetworkPolicies](https://supaahiro.github.io/schwifty-lab/blog-posts/20261017-ckad/article_EN.html) covered which connections are permitted. Here, we follow how clients find an application and reach its backend Pods. The [CKAD series index](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html) links the rest of the roadmap.

## Choose the Access Pattern

A normal Service provides a stable virtual IP and DNS name while backend Pods can be replaced. For a Service with a selector, Kubernetes discovers matching Pods in the same namespace and maintains EndpointSlices describing the backends.

| Configuration | What it provides | Typical use |
| --- | --- | --- |
| `ClusterIP` | An internal virtual IP; the default Service type | Communication inside the cluster |
| `NodePort` | A ClusterIP plus an allocated port on eligible node addresses | Access through a reachable node address |
| `LoadBalancer` | An external load balancer supplied by a supporting implementation | External application access |
| `ExternalName` | A DNS CNAME pointing to another DNS name; no traffic proxy | Referencing an existing DNS destination |
| Headless: `clusterIP: None` | Backend addresses through DNS, without a Service virtual IP | Direct backend discovery |

Headless is a Service configuration, not an additional `type` value. A LoadBalancer needs infrastructure that implements it; declaring the type alone does not guarantee an external address. These options are described in the [Service documentation](https://kubernetes.io/docs/concepts/services-networking/service/#publishing-services-service-types).

## Prepare the Lab

Use a disposable cluster with Linux nodes, IPv4 networking, working cluster DNS, and permission to create a namespace, Deployments, Pods and Services. You also need permission to inspect EndpointSlices and use `exec` and `port-forward`.

The commands use **Bash**. DNS examples assume the usual `cluster.local` cluster domain; substitute your configured domain if it differs. The lab was verified on Kubernetes **1.35.1**. It creates no NetworkPolicies; additional cluster policies must permit the test traffic.

```bash
git clone https://github.com/Supaahiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261018-ckad
kubectl config current-context
kubectl get namespace ckad-services --ignore-not-found
```

If `ckad-services` already exists, choose an unused namespace and update the manifests and commands consistently. The cleanup deletes that namespace.

```bash
kubectl apply -f manifests/01-namespace.yaml
kubectl apply -f manifests/02-web-deployment.yaml
kubectl rollout status deployment/web -n ckad-services --timeout=120s
kubectl get pods -n ckad-services -l app=web -o wide --show-labels
```

The Deployment runs two BusyBox HTTP servers on port **8080**. Each returns its Pod name at `/` and serves a readiness file at `/ready`. Its named container port is `http`, and its readiness probe uses that name:

```yaml
ports:
  - name: http
    containerPort: 8080
readinessProbe:
  httpGet:
    path: /ready
    port: http
  periodSeconds: 2
  failureThreshold: 1
```

The complete Deployment is in `manifests/02-web-deployment.yaml`. Its non-root containers write into an `emptyDir` mounted at `/www`.

## Create a ClusterIP Service

Apply `manifests/03-web-service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: ckad-services
spec:
  type: ClusterIP
  selector:
    app: web
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
```

```bash
kubectl apply -f manifests/03-web-service.yaml
kubectl apply -f manifests/04-client.yaml
kubectl wait -n ckad-services --for=condition=Ready pod/client --timeout=120s
kubectl get service web -n ckad-services
kubectl exec -n ckad-services client -- wget -T 3 -qO- http://web
```

The response is a Pod name such as `web-<replicaset-hash>-<suffix>`. The client connects to Service port 80, and the Service's `targetPort: http` resolves to the selected Pod's named port, 8080.

| Field | Value in this lab | Meaning |
| --- | --- | --- |
| `containerPort` | `8080`, named `http` | Describes the container port; declaring it does not start a listener |
| Service `port` | `80` | Port used by clients connecting to the Service IP |
| Service `targetPort` | `http` → `8080` | Destination port on the backend Pod |
| Service `nodePort` | Allocated later | Port used with a node IP for the NodePort Service |

The Service selector must match the **Pod labels**, which a Deployment places in `spec.template.metadata.labels`. Matching only the Deployment object's own labels is insufficient. A named `targetPort` must match a port name on the selected Pods. See the [Service API reference](https://kubernetes.io/docs/reference/kubernetes-api/core/service-v1/) for selector and port semantics.

## Follow DNS, the Service IP and EndpointSlices

From a Pod in the same namespace, the short name `web` is enough. Try the namespace-qualified name and inspect the DNS record explicitly:

```bash
kubectl exec -n ckad-services client -- wget -T 3 -qO- http://web.ckad-services
kubectl exec -n ckad-services client -- \
  nslookup -type=A web.ckad-services.svc.cluster.local.
```

The DNS answer contains the Service's ClusterIP. The trailing dot makes the name absolute; this avoids BusyBox `nslookup` reporting failures for extra search-suffix queries. From another namespace, use the namespace-qualified or fully qualified name. See [DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/).

Test the same Service without DNS, then test one Pod directly:

```bash
SERVICE_IP=$(kubectl get service web -n ckad-services -o jsonpath='{.spec.clusterIP}')
POD=$(kubectl get pods -n ckad-services -l app=web -o jsonpath='{.items[0].metadata.name}')
POD_IP=$(kubectl get pod "$POD" -n ckad-services -o jsonpath='{.status.podIP}')

kubectl exec -n ckad-services client -- wget -T 3 -qO- "http://$SERVICE_IP"
kubectl exec -n ckad-services client -- wget -T 3 -qO- "http://$POD_IP:8080"
```

Keep these variables in the same terminal for the failure exercises. They describe the current resources; if you replace the Pod, refresh `POD` and `POD_IP`.

Inspect the backend records:

```bash
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web -o yaml
```

Expect two Pod addresses, backend port **8080**, and `conditions.ready: true`. A Service can own multiple slices, so inspect the whole label-selected set. The control plane manages these records; repair the Service or workload rather than manually editing its generated slices. The [EndpointSlice documentation](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/) explains ownership, ports and endpoint conditions.

For a DNS-only failure, compare the correct query above with this intentionally misspelled name:

```bash
kubectl exec -n ckad-services client -- \
  nslookup -type=A web-typo.ckad-services.svc.cluster.local.
```

Expect `NXDOMAIN`. Correct the name; changing the Service selector would not repair this lookup. If the correct name also fails, inspect the client's `/etc/resolv.conf` and cluster DNS before assuming that the application is down.

## Use port-forward for a Local Check

In a separate terminal, keep this command running:

```bash
kubectl port-forward -n ckad-services service/web 8088:80
```

Then, from your workstation:

```bash
curl --fail http://127.0.0.1:8088
```

You should receive a Pod name. Port 80 refers to the Service port, which `kubectl` resolves to the selected Pod's target port. Stop forwarding with **Ctrl+C**.

This creates a temporary tunnel to a selected Pod through the Kubernetes API connection. It does not exercise the Service ClusterIP forwarding path or cluster DNS. A successful local request therefore does not prove that in-cluster Service traffic works. It also does not create a persistent external endpoint. See the [`kubectl port-forward` reference](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/).

## Failure 1: The Selector Matches No Pods

Change the Service selector to `app: missing-web` using the supplied patch:

```bash
kubectl patch service web -n ckad-services --type=merge \
  --patch-file manifests/patches/05-wrong-selector.yaml
kubectl get pods -n ckad-services -l app=missing-web
kubectl get pods -n ckad-services -l app=web --show-labels
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web -o yaml
kubectl exec -n ckad-services client -- wget -T 3 -qO- http://web
```

After reconciliation, there are no backend addresses for `web`, and the request fails. Depending on the network implementation, it may time out or be refused. The Pods are still running, and the normal Service DNS record still resolves because the Service still exists:

```bash
kubectl exec -n ckad-services client -- \
  nslookup -type=A web.ckad-services.svc.cluster.local.
kubectl exec -n ckad-services client -- wget -T 3 -qO- "http://$POD_IP:8080"
```

The direct Pod request succeeds. This combination points to backend selection, not a missing DNS record or a failed HTTP process.

Restore the selector, then recheck the endpoints and request:

```bash
kubectl patch service web -n ckad-services --type=merge \
  --patch-file manifests/patches/05-restore-selector.yaml
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web
kubectl exec -n ckad-services client -- wget -T 3 -qO- http://web
```

Allow a few seconds for EndpointSlice and network rule updates after each patch. Recheck the expected state before moving to the next failure.

## Failure 2: The Service Uses the Wrong Backend Port

Now keep the selector correct but change `targetPort` to numeric port **9090**:

```bash
kubectl patch service web -n ckad-services --type=merge \
  --patch-file manifests/patches/06-wrong-target-port.yaml
kubectl describe service web -n ckad-services
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web -o yaml
kubectl exec -n ckad-services client -- wget -T 3 -qO- http://web
kubectl exec -n ckad-services client -- wget -T 3 -qO- "http://$POD_IP:8080"
```

This time the EndpointSlices still contain two ready Pod addresses, but their port is **9090**. The Service request fails while the direct request to 8080 succeeds. Readiness remains healthy because its named port still resolves to the actual HTTP listener on 8080.

An endpoint being ready does not mean every port number in a Service points to a working application listener. Compare all three values: the application's listening port, the Pod's named port, and the Service's `targetPort`.

Restore `targetPort: http`:

```bash
kubectl patch service web -n ckad-services --type=merge \
  --patch-file manifests/patches/06-restore-target-port.yaml
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web -o yaml
kubectl exec -n ckad-services client -- wget -T 3 -qO- http://web
```

Once the backend port is 8080 again and the network rules have converged, the request succeeds.

## Failure 3: A Running Pod Is Not Ready

Remove the readiness file from the Pod selected earlier. Its HTTP process continues serving `/`, but `/ready` returns 404:

```bash
kubectl exec -n ckad-services "$POD" -- rm /www/ready
kubectl wait -n ckad-services --for=condition=Ready=false "pod/$POD" --timeout=60s
kubectl get pods -n ckad-services -l app=web
kubectl describe pod "$POD" -n ckad-services
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web -o yaml
```

The affected Pod remains **Running**, with **0/1** containers ready. Its endpoint remains visible in the slice with `ready: false`; the other replica stays ready. This is different from the empty backend set caused by the selector mistake.

After the updates propagate, new requests through the Service go to the healthy replica. The unready Pod is still directly reachable in this lab:

```bash
kubectl exec -n ckad-services client -- wget -T 3 -qO- "http://$POD_IP:8080"
kubectl exec -n ckad-services client -- sh -c \
  'for i in 1 2 3 4 5; do wget -T 3 -qO- http://web; done'
```

The first command prints the affected Pod's name; the loop prints the other Pod's name. Readiness failure does not itself restart the container. If all replicas were unready, this Service would have no ready backends. We leave `publishNotReadyAddresses` at its default, `false`.

Restore the readiness file and wait for recovery:

```bash
kubectl exec -n ckad-services "$POD" -- touch /www/ready
kubectl wait -n ckad-services --for=condition=Ready "pod/$POD" --timeout=60s
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web -o yaml
```

Both endpoints become ready again. The [readiness probe documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#define-readiness-probes) explains this separation between process lifecycle and eligibility for Service traffic.

## Reach a Service Through a NodePort

Create a separate Service so the original ClusterIP example remains available:

```bash
kubectl apply -f manifests/07-nodeport-service.yaml
kubectl get service web-nodeport -n ckad-services
kubectl get nodes -o wide
```

The manifest uses `type: NodePort`, the same selector, Service port 80 and `targetPort: http`. Kubernetes allocates `nodePort`, avoiding a hard-coded port collision.

Read the assigned port and the first node's internal IPv4 address, then test from the client Pod:

```bash
NODE_PORT=$(kubectl get service web-nodeport -n ckad-services -o jsonpath='{.spec.ports[0].nodePort}')
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
kubectl exec -n ckad-services client -- wget -T 3 -qO- "http://$NODE_IP:$NODE_PORT"
```

This verifies the node-address/NodePort path from inside the cluster. An external client also needs a route to an eligible node address and firewall access to the port. Node IPs inside local VMs or containers may not be reachable directly from your workstation. Use your cluster's documented exposure mechanism; `localhost:<nodePort>` is not universally supported.

For a LoadBalancer Service that remains `<pending>`, inspect its events and whether a load-balancer controller and address pool are available. If an external address exists but access fails, check the external route and firewall as well as the same selectors, ports and readiness conditions used above. This lab does not provision an external load balancer or verify workstation-to-NodePort routing.

## Compare a Headless Service

`manifests/08-headless-service.yaml` selects the same Pods but sets `clusterIP: None`. Its port is **8080**, matching the backend listener:

```bash
kubectl apply -f manifests/08-headless-service.yaml
kubectl get service web-headless -n ckad-services
kubectl exec -n ckad-services client -- \
  nslookup -type=A web-headless.ckad-services.svc.cluster.local.
kubectl exec -n ckad-services client -- wget -T 3 -qO- http://web-headless:8080
```

The DNS answer contains the two ready Pod IPs, not a Service ClusterIP. The client connects directly to a returned address on 8080. There is no Service virtual-IP translation from port 80 in this path, and a headless Service does not guarantee an even distribution of requests by the client.

For comparison, an `ExternalName` Service provides a DNS alias rather than selecting these Pods. When troubleshooting that type, inspect the CNAME target and its resolution; also consider whether the original hostname is suitable for the destination's HTTP host or TLS certificate.

## A Practical Troubleshooting Order

Start with the failing request's source, destination, protocol and port. A timeout alone does not identify the cause.

| Observation | Next check |
| --- | --- |
| Service name fails, but ClusterIP works | Name, namespace, cluster DNS and client resolver configuration |
| No backend addresses | Service selector, Pod labels and namespace |
| Backend addresses exist but are not ready | Readiness probe, Pod events and application dependencies |
| Ready endpoints exist, but Service access fails | Endpoint port, actual listener, protocol and Service forwarding |
| Direct Pod access also fails | Application process, listener binding, Pod networking and NetworkPolicies |
| In-cluster access works, external access fails | Node/LB address, routing, firewalls and external traffic settings |

Useful inspection commands include:

```bash
kubectl describe service web -n ckad-services
kubectl get pods -n ckad-services -l app=web -o wide --show-labels
kubectl get endpointslices -n ckad-services -l kubernetes.io/service-name=web -o yaml
kubectl logs -n ckad-services "$POD"
kubectl get networkpolicies -n ckad-services
```

Inspect policies in the source namespace too if the client is elsewhere. As discussed in the [NetworkPolicies introduction](https://supaahiro.github.io/schwifty-lab/blog-posts/20261017-ckad/article_EN.html), enforcement requires a supporting CNI/networking implementation. Service forwarding itself may be implemented by kube-proxy or an alternative data plane, so node-level diagnosis depends on the cluster.

Use the Kubernetes [Debug Services guide](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/) for a broader investigation. Here we use EndpointSlices to inspect backends; the legacy Endpoints API has been deprecated since Kubernetes 1.33.

## Clean Up

Stop any running `port-forward` command with **Ctrl+C**, then delete only the lab namespace:

```bash
kubectl delete namespace ckad-services
```

The central troubleshooting habit is to compare the same application at successive points: DNS name, Service IP, endpoint address and application port. Each comparison narrows the problem before you change the configuration.
