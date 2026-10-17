---
layout: default
title: "CKAD Preparation — Demonstrate Basic Understanding of NetworkPolicies"
date: 2026-10-17
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261017-ckad/article.webp"
summary: "A short introduction to Kubernetes NetworkPolicies: CNI support, ingress and egress, Pod selectors, and additive allow rules. Continue with the existing Redis lab to test blocked and permitted connections."
---

# CKAD Preparation — Demonstrate Basic Understanding of NetworkPolicies

This chapter introduces the CKAD requirement **Demonstrate basic understanding of NetworkPolicies**, in the Services and Networking domain. We will cover the essential concepts, then continue with the existing [Testing Kubernetes NetworkPolicy](https://supaahiro.github.io/schwifty-lab/blog-posts/20251018-ckad/article_EN.html) article for the full practical walkthrough.

The [previous chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261016-ckad/article_EN.html) covered application SecurityContexts. Here, the focus moves to network communication between workloads. You can find the complete roadmap in the [CKAD series index](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html).

## First, Check CNI Support

> **NetworkPolicies require support from the cluster's CNI plugin or networking solution.** Without an implementation that enforces them, creating NetworkPolicy objects has no effect on traffic.

Check the plugin and configuration actually installed in your cluster. The API accepting a manifest is not evidence that connections are being filtered. This prerequisite is explicit in the [Kubernetes NetworkPolicy documentation](https://kubernetes.io/docs/concepts/services-networking/network-policies/#prerequisites).

## What a NetworkPolicy Describes

A NetworkPolicy controls traffic at the IP address and port level. Its rules describe allowed communication for selected Pods.

| Part | Meaning |
| --- | --- |
| `spec.podSelector` | Selects the Pods protected by the policy, within its namespace; `{}` selects all Pods there. |
| `policyTypes` | Identifies the directions covered: `Ingress` for incoming connections, `Egress` for outgoing connections, or both. |
| `ingress` / `egress` | Describe allowed peers and ports. Peers can be selected using Pod labels, namespace labels or IP ranges. |

A peer `podSelector` on its own matches Pods in the policy's namespace. Combine it with a `namespaceSelector` in the same peer entry to select matching Pods in matching namespaces. See the [NetworkPolicy API reference](https://kubernetes.io/docs/reference/kubernetes-api/networking/network-policy-v1/) for the fields.

## Remember How Policies Combine

- **Isolation is per direction.** Without a policy selecting a Pod for a direction, NetworkPolicy does not restrict that direction. A policy selecting it for ingress introduces ingress isolation; egress is considered separately.
- **Allowed traffic is additive.** When several policies select a Pod, their allow rules combine. A default-deny policy does not override another policy's allowance, and policy order does not matter.
- **Both ends must permit a connection.** When applicable, the source Pod's egress policy and the destination Pod's ingress policy must both allow it.

These rules explain why adding a policy can open a path without removing the existing default-deny policy. The official documentation describes [Pod isolation and policy combination](https://kubernetes.io/docs/concepts/services-networking/network-policies/#the-two-sorts-of-pod-isolation).

## Continue with the Redis Lab

In our existing example, a Redis Pod listens on TCP port **6379**. We apply a default-deny ingress policy, then allow access to Redis from Pods carrying the label `access: redis`. A client without that label should fail to connect; after adding it and recreating the client, the connection should succeed.

The article includes the Redis Pod and Service, the client, a Python connectivity test, both policies, and cleanup commands:

**[Continue to the full lab: Testing Kubernetes NetworkPolicy →](https://supaahiro.github.io/schwifty-lab/blog-posts/20251018-ckad/article_EN.html)**

This is an ingress-focused exercise. Before starting, confirm CNI support and test both the blocked and permitted cases. The lab uses `k` as shorthand for `kubectl`; in Bash, define `alias k=kubectl`, or replace `k` with `kubectl` in its commands.
